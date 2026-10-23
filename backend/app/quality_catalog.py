"""Frozen exact lookup plus guarded, genuinely Atlas-backed evaluation retrieval.

Catalogue metadata is not a reviewed photograph dataset. The approved visual
reference set remains separate. No operation here writes a catalogue, live
battle, resident or Atlas index. If vector-bearing records drift after snapshot,
evaluation fails rather than silently comparing different retrieval corpora.
"""
from __future__ import annotations
import asyncio
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import inspect
import json
import math
from types import SimpleNamespace

from .catalog import CATALOG_VERSION, CHARACTER_TYPES, CharacterCatalog, normalize_key
from .config import Settings
from .repository import StoreError
from .retrieval import AtlasRetriever, RetrievalConfig, EMBEDDING_SCHEMA_VERSION

MAX_CATALOG_RECORDS = 1000
_METADATA_FIELDS = ('canonical_type_id', 'canonical_key', 'display_name', 'aliases', 'normalized_aliases',
    'description', 'template_id', 'approved_archetypes', 'default_archetype', 'approved', 'catalog_version',
    'identity_basis', 'embedding_model', 'embedding_dimensions', 'embedding_schema_version')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def metadata(record):
    return {key: deepcopy(record[key]) for key in _METADATA_FIELDS if key in record}


def _approved_records(repository):
    records = repository.read(lambda tx: tx.find('characterTypes', {'approved': True}, limit=MAX_CATALOG_RECORDS+1))
    if len(records) > MAX_CATALOG_RECORDS:
        raise StoreError('The catalogue exceeds the bounded evaluation snapshot limit.', 409, 'catalog_snapshot_limit')
    return sorted(records, key=lambda record: record['canonical_key'])


def _vector_manifest(records, config):
    manifest = []
    for record in records:
        if (record.get('embedding_model') != config['model'] or record.get('embedding_dimensions') != config['dimensions']
                or record.get('embedding_schema_version') != EMBEDDING_SCHEMA_VERSION or 'embedding' not in record):
            continue
        vector = record['embedding']
        if (not isinstance(vector, list) or len(vector) != config['dimensions']
                or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector)
                or not sum(float(x)*float(x) for x in vector)):
            raise StoreError('The catalogue contains incompatible embedding data.', 409, 'catalog_embedding_contract')
        manifest.append({'canonical_key': record['canonical_key'], 'record_hash': digest(metadata(record)),
                         'vector_hash': digest(vector)})
    return manifest


def freeze_catalog(repository, settings: Settings | None = None):
    """Call once when creating a job; persisted output contains no credentials or vectors."""
    settings = settings or repository.settings
    records = _approved_records(repository)
    retrieval = asdict(RetrievalConfig(model=settings.embedding_model, dimensions=settings.embedding_dimensions,
                                     index=settings.vector_index))
    configured = bool(hasattr(repository, 'db') and settings.embedding_model and settings.gemini_api_key)
    snapshot = {'schema': 'frozen-catalog-v1', 'catalog_version': CATALOG_VERSION,
        'builtin_records': deepcopy(CHARACTER_TYPES), 'records': [metadata(record) for record in records],
        'retrieval_config': retrieval, 'retrieval_expected': configured,
        'vector_manifest': _vector_manifest(records, retrieval) if configured else [],
        'retrieval_mode': 'guarded_atlas_vector_search' if configured else 'unavailable',
        'scope': 'Object-kind catalogue; not reviewed image reference or ground-truth data.'}
    snapshot['digest'] = digest(snapshot)
    return snapshot


class FrozenCollection:
    """The exact-query interface used by CharacterCatalog, backed only by snapshot copies."""
    def __init__(self, records): self.records = deepcopy(records)

    async def find_one(self, query, projection=None):
        alternatives = query.get('$or', [])
        for record in self.records:
            if record.get('approved') is not True: continue
            if any(all((value in record.get(key, []) if isinstance(record.get(key), list) else record.get(key) == value)
                       for key, value in part.items()) for part in alternatives):
                return deepcopy(record)
        return None


class BudgetedEmbeddingClient:
    def __init__(self, client, budget):
        self.client, self.budget = client, budget
        self.aio = SimpleNamespace(models=SimpleNamespace(embed_content=self.embed_content))

    async def embed_content(self, **kwargs):
        # Contents are bounded by the existing embedding preprocessing (1,200 characters).
        reservation = await self.budget.reserve(input_tokens=len(str(kwargs.get('contents', '')))//2+256,
                                               output_tokens=0, kind='catalog_embedding')
        response = await self.client.aio.models.embed_content(**kwargs)
        await self.budget.complete(reservation, response)
        return response


class FrozenAtlasRetriever(AtlasRetriever):
    def __init__(self, snapshot, repository, client, budget):
        self.snapshot, self.repository = deepcopy(snapshot), repository
        config = RetrievalConfig(**snapshot['retrieval_config'])
        collection = repository.db.characterTypes if hasattr(repository, 'db') else None
        wrapped = BudgetedEmbeddingClient(client, budget) if client is not None and budget is not None else None
        super().__init__(collection=collection, client=wrapped, config=config)

    async def _unchanged(self):
        records = await asyncio.to_thread(_approved_records, self.repository)
        actual = _vector_manifest(records, self.snapshot['retrieval_config'])
        if actual != self.snapshot['vector_manifest']:
            raise StoreError('The vector catalogue changed after this comparison was frozen. Start a new snapshot.',
                             409, 'catalog_snapshot_changed')

    async def search(self, description):
        if not self.snapshot['retrieval_expected']:
            return {'status': 'unavailable', 'candidates': [], 'detail': 'Semantic retrieval was unavailable in this frozen baseline.',
                    'snapshot_digest': self.snapshot['digest']}
        if self.collection is None or self.client is None:
            raise StoreError('The frozen Atlas retrieval service is unavailable.', 503, 'catalog_retrieval_unavailable')
        if not self.snapshot['vector_manifest']:
            raise StoreError('The frozen catalogue has no compatible seeded embeddings.', 409, 'catalog_embeddings_missing')
        await self._unchanged()
        # Reuse the live embedding preprocessing/normalization/cache; every actual API call is budgeted.
        vector = await self.embed(description)
        pipeline = [{'$vectorSearch': {'index': self.config.index, 'path': 'embedding', 'queryVector': vector,
            'numCandidates': 60, 'limit': 3, 'filter': {'approved': True, 'embedding_model': self.config.model,
                'embedding_dimensions': self.config.dimensions, 'embedding_schema_version': EMBEDDING_SCHEMA_VERSION}}},
            {'$project': {'_id': 0, 'canonical_type_id': 1, 'canonical_key': 1, 'display_name': 1, 'description': 1,
                          'template_id': 1, 'score': {'$meta': 'vectorSearchScore'}}}]
        async def read_records():
            if inspect.iscoroutinefunction(self.collection.aggregate):
                cursor = await self.collection.aggregate(pipeline, maxTimeMS=int(self.config.timeout_seconds*1000))
                return await cursor.to_list(length=3)
            return await asyncio.to_thread(lambda: list(self.collection.aggregate(pipeline, maxTimeMS=int(self.config.timeout_seconds*1000))))
        records = await asyncio.wait_for(read_records(), timeout=self.config.timeout_seconds)
        await self._unchanged()
        frozen = {record['canonical_key']: record for record in self.snapshot['records']}
        candidates = []
        for record in records:
            original = frozen.get(record.get('canonical_key'))
            if not original or any(record.get(key) != original.get(key) for key in
                                  ('canonical_type_id', 'canonical_key', 'display_name', 'description', 'template_id')):
                raise StoreError('Atlas returned metadata outside the frozen catalogue.', 409, 'catalog_result_changed')
            candidates.append(deepcopy(record))
        return {'status': 'completed' if candidates else 'empty', 'candidates': candidates,
            'model': self.config.model, 'schema_version': EMBEDDING_SCHEMA_VERSION,
            'snapshot_digest': self.snapshot['digest'], 'mode': 'guarded_atlas_vector_search',
            'detail': 'Real Atlas semantic similarity against an unchanged frozen corpus; not identity or ownership.'}


class EvaluationCatalog(CharacterCatalog):
    async def ensure_type(self, record):
        # Service boundary: even a mistaken persist_catalog=True cannot mutate the catalogue.
        return None


def make_evaluation_catalog(snapshot, repository, client, budget):
    if not snapshot or snapshot.get('schema') != 'frozen-catalog-v1':
        raise StoreError('A frozen catalogue snapshot is required for evaluation.', 409, 'catalog_snapshot_required')
    if digest({k: v for k, v in snapshot.items() if k != 'digest'}) != snapshot.get('digest'):
        raise StoreError('The frozen catalogue snapshot failed its integrity check.', 409, 'catalog_snapshot_changed')
    catalog = EvaluationCatalog(collection=FrozenCollection(snapshot['records']),
                                retriever=FrozenAtlasRetriever(snapshot, repository, client, budget))
    catalog._aliases = {}
    for record in snapshot['builtin_records']:
        for alias in [record['canonical_key'], *record.get('aliases', [])]:
            catalog._aliases[normalize_key(alias)] = deepcopy(record)
    return catalog
