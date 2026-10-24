"""Explicitly enrolled visual references, separate from catalogue descriptions.

Only reviewed, consented reference cases enter this adapter. Live retrieval never
enrols a photo or creates an index. Evaluation uses its frozen reference snapshot
instead of this mutable live adapter. Embedding calls contain image bytes only.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import math
import re
from typing import Any

from google.genai import types
from PIL import Image

from .repository import StoreError, key_for
from .provider_queue import AI_PAUSE_REASON, require_ai_enabled

MODEL = 'gemini-embedding-2'
DIMENSIONS = 768
SCHEMA = 'reviewed-image-v1'
COLLECTION = 'qualityReferenceVectors'
INDEX = 'quality_references_vector'
MAX_CASES = 500
MAX_REFERENCES = 3
TIMEOUT = 20
FILTER_FIELDS = ('world_id', 'role', 'review_status', 'shared_consent', 'retired',
                 'case_id', 'group_id', 'image_hash', 'embedding_model',
                 'embedding_dimensions', 'embedding_schema_version')


def visual_reference_index_definition():
    return {'fields': [{'type': 'vector', 'path': 'embedding', 'numDimensions': DIMENSIONS,
                        'similarity': 'cosine'},
                       *[{'type': 'filter', 'path': name} for name in FILTER_FIELDS]]}


def _eligible(case):
    expected = case.get('expected') or {}
    return (case.get('role') == 'reference' and case.get('review_status') == 'approved'
            and case.get('shared_consent') is True and not case.get('retired')
            and isinstance(case.get('group_id'), str) and bool(case['group_id'].strip())
            and isinstance(case.get('revision'), int) and case['revision'] > 0
            and not expected.get('clarification_required')
            and isinstance(expected.get('canonical_type_id'), str)
            and bool(re.fullmatch(r"[\w \-']{1,80}", expected['canonical_type_id']))
            and bool(case.get('provenance')))


class ApprovedReferences:
    def __init__(self, repo, settings, client=None):
        self.repo, self.settings = repo, settings
        self.collection = repo.db[COLLECTION] if hasattr(repo, 'db') else None
        self.index = getattr(settings, 'quality_reference_vector_index', INDEX)
        self._owns_client = client is None and bool(settings.gemini_api_key)
        if client is None and settings.gemini_api_key:
            from .gemini_client import create_gemini_client
            client = create_gemini_client(settings.gemini_api_key, timeout_ms=TIMEOUT * 1000)
        self.client = client
        self.provider_queue = None
        self.status = {'status': 'not_checked', 'available': False,
                       'detail': 'No visual reference search has run.'}
        self._lock = asyncio.Semaphore(1)

    async def close(self):
        """Release only the SDK client created by this adapter, never a shared client."""
        if self._owns_client and self.client is not None:
            client, self.client = self.client, None
            try:
                await client.aio.aclose()
            finally:
                client.close()

    @property
    def available(self):
        return self.status['available']

    def _state(self, status, detail, *, available=False, **extra):
        self.status = {'status': status, 'available': available, 'detail': detail,
                       'model': MODEL, 'dimensions': DIMENSIONS, 'schema_version': SCHEMA,
                       'index': self.index, **extra}

    def _snapshot(self, tx, image_hash='', exclude_groups=()):
        # Role/review/consent filtering is performed by the database query itself.
        candidates = tx.find('qualityCases', {'world_id': self.repo.world_id, 'role': 'reference',
                             'review_status': 'approved', 'shared_consent': True}, limit=MAX_CASES + 1)
        cases = tx.find('qualityCases', {'world_id': self.repo.world_id}, limit=MAX_CASES + 1)
        if len(cases) > MAX_CASES or len(candidates) > MAX_CASES:
            raise StoreError('Visual reference safety scan exceeds the bounded case limit.', 409, 'reference_limit')
        # Even a disputed or retired non-reference record blocks cross-role reuse.
        blocked = set(exclude_groups) | {c.get('group_id') for c in cases if c.get('role') != 'reference'}
        if image_hash:
            blocked.update(c.get('group_id') for c in cases if c.get('image_hash') == image_hash)
        approved = {c['id']: c for c in candidates if _eligible(c)
                    and c['group_id'] not in blocked and c.get('image_hash') != image_hash}
        return approved, blocked

    def _media(self, tx, image_hash):
        if not isinstance(image_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', image_hash):
            raise StoreError('Visual reference image hash is invalid.', 422, 'invalid_reference_media')
        media = tx.get('media', image_hash)
        data = (media or {}).get('data')
        if (not isinstance(data, bytes) or not data or len(data) > self.settings.max_upload_bytes
                or sha256(data).hexdigest() != image_hash or media.get('mime_type') not in ('image/jpeg', 'image/png')):
            raise StoreError('Visual reference media is missing or invalid.', 409, 'invalid_reference_media')
        with Image.open(BytesIO(data)) as image:
            if (image.width * image.height > self.settings.max_image_pixels
                    or max(image.width, image.height) > self.settings.inference_max_edge
                    or image.format not in ('JPEG', 'PNG')):
                raise StoreError('Visual reference image exceeds the inference limits.', 422, 'invalid_reference_media')
            image.verify()
        return media

    async def _index_ready(self):
        records = await asyncio.wait_for(asyncio.to_thread(
            lambda: list(self.collection.list_search_indexes(name=self.index))), TIMEOUT)
        if not records:
            self._state('index_missing', 'The separate visual reference vector index has not been created.')
            return False
        entry = records[0]
        fields = (entry.get('latestDefinition') or entry.get('definition') or {}).get('fields', [])
        required = visual_reference_index_definition()['fields']
        if any(field not in fields for field in required):
            self._state('index_incompatible', 'Visual reference index dimensions or filter fields do not match this adapter.')
            return False
        if not entry.get('queryable'):
            self._state('index_building', 'The visual reference index is still building.')
            return False
        return True

    async def _embed(self, media, budget=None):
        require_ai_enabled(self.settings)
        if self.provider_queue: self.provider_queue.require_enabled()
        if self.client is None:
            raise StoreError('Gemini embedding access is unavailable.', 503, 'embedding_unavailable')
        # The maximum embedding input context is reserved, rather than guessed from a label.
        reservation = None
        async with self._lock:
            async def invoke():
                nonlocal reservation
                reservation = await budget.reserve(input_tokens=8192, output_tokens=0, kind='visual_reference_embedding') if budget else None
                return await asyncio.wait_for(self.client.aio.models.embed_content(
                    model=MODEL,
                    contents=[types.Part.from_bytes(data=media['data'], mime_type=media['mime_type'])],
                    config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS)), TIMEOUT)
            response = await self.provider_queue.run(MODEL, invoke, category='evaluation_embedding' if budget else 'embedding',
                prepare=getattr(budget, 'check', None)) if self.provider_queue else await invoke()
        if budget:
            # Unknown/failed provider outcomes deliberately keep the reservation pending.
            await budget.complete(reservation, response)
        values = [float(value) for value in response.embeddings[0].values]
        if len(values) != DIMENSIONS or not all(math.isfinite(value) for value in values):
            raise ValueError('Visual embedding dimensions or values are invalid.')
        norm = math.sqrt(sum(value * value for value in values))
        if not norm or not math.isfinite(norm):
            raise ValueError('Visual embedding norm is invalid.')
        return [value / norm for value in values]

    async def retrieve(self, image_hash, limit=3, exclude_groups=(), *, budget=None, snapshot=None):
        if getattr(self.settings, 'ai_paused', False):
            self._state('ai_paused', AI_PAUSE_REASON)
            return []
        limit = max(0, min(MAX_REFERENCES, int(limit)))
        if not limit:
            self._state('disabled', 'This pipeline does not use visual references.')
            return []
        def scoped_snapshot(tx):
            approved, blocked = self._snapshot(tx, image_hash, exclude_groups)
            if snapshot is not None:
                frozen = {case['id']: case for case in snapshot if case.get('group_id') not in exclude_groups and case.get('image_hash') != image_hash}
                if any(approved.get(identifier) != case for identifier, case in frozen.items()):
                    raise StoreError('Reference eligibility changed since this evaluation snapshot.', 409, 'stale_reference')
                approved = {identifier: case for identifier, case in approved.items() if identifier in frozen}
            return approved, blocked
        try:
            approved, blocked = await asyncio.to_thread(self.repo.read, scoped_snapshot)
            if not approved:
                self._state('no_approved_references', 'No eligible reviewed, consented visual references are available.')
                return []
            if self.collection is None or self.client is None:
                self._state('unavailable', 'Atlas and Gemini embedding access are required for visual reference search.')
                return []
            if not await self._index_ready():
                return []
            # Skip paid query embedding if none of the eligible revisions is enrolled.
            def enrolled(tx):
                vectors = tx.find(COLLECTION, {'world_id': self.repo.world_id,
                    'embedding_model': MODEL, 'embedding_dimensions': DIMENSIONS,
                    'embedding_schema_version': SCHEMA}, limit=MAX_CASES + 1)
                if len(vectors) > MAX_CASES:
                    raise StoreError('Reference vector safety scan exceeds its limit.', 409, 'reference_limit')
                return [v['case_id'] for v in vectors if v.get('case_id') in approved
                    and v.get('case_revision') == approved[v['case_id']]['revision']
                    and v.get('image_hash') == approved[v['case_id']]['image_hash']]
            ids = await asyncio.to_thread(self.repo.read, enrolled)
            if not ids:
                self._state('not_enrolled', 'Approved reference images need explicit embedding preparation.')
                return []
            media = await asyncio.to_thread(self.repo.read, lambda tx: self._media(tx, image_hash))
            vector = await self._embed(media, budget)
            filters = {'world_id': self.repo.world_id, 'role': 'reference', 'review_status': 'approved',
                'shared_consent': True, 'retired': False, 'case_id': {'$in': ids},
                'image_hash': {'$ne': image_hash}, 'embedding_model': MODEL,
                'embedding_dimensions': DIMENSIONS, 'embedding_schema_version': SCHEMA}
            if blocked - {None}:
                filters['group_id'] = {'$nin': sorted(blocked - {None})}
            pipeline = [{'$vectorSearch': {'index': self.index, 'path': 'embedding', 'queryVector': vector,
                'numCandidates': 60, 'limit': min(12, limit * 4), 'filter': filters}},
                {'$project': {'_id': 0, 'case_id': 1, 'case_revision': 1, 'image_hash': 1,
                              'group_id': 1, 'embedding_model': 1, 'embedding_dimensions': 1,
                              'embedding_schema_version': 1, 'score': {'$meta': 'vectorSearchScore'}}}]
            rows = await asyncio.wait_for(asyncio.to_thread(lambda: list(
                self.collection.aggregate(pipeline, maxTimeMS=TIMEOUT * 1000))), TIMEOUT)
            # Atlas indexes are eventually consistent: recheck the authoritative cases.
            def resolve(tx):
                current, _ = scoped_snapshot(tx)
                results, seen = [], set()
                for row in rows:
                    case = current.get(row.get('case_id'))
                    if (not case or case['id'] in seen or row.get('case_revision') != case['revision']
                            or row.get('image_hash') != case['image_hash'] or row.get('group_id') != case['group_id']
                            or row.get('embedding_model') != MODEL or row.get('embedding_dimensions') != DIMENSIONS
                            or row.get('embedding_schema_version') != SCHEMA):
                        continue
                    data = self._media(tx, case['image_hash'])
                    results.append({'id': case['id'], 'image_bytes': data['data'],
                        'label': case['expected']['canonical_type_id'],
                        'visible_features': [str(v)[:120] for v in case.get('visible_attributes', [])[:12]],
                        'provenance': {**deepcopy(case['provenance']), 'case_revision': case['revision'],
                            'group_id': case['group_id'], 'embedding_model': MODEL,
                            'embedding_dimensions': DIMENSIONS, 'embedding_schema_version': SCHEMA}})
                    seen.add(case['id'])
                    if len(results) >= limit: break
                return results
            results = await asyncio.to_thread(self.repo.read, resolve)
            self._state('completed' if results else 'empty', 'Actual Atlas visual similarity search; similarity is not object identity.',
                        available=True, count=len(results))
            return results
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._state('unavailable', 'Visual reference retrieval failed; no fallback examples were substituted.',
                        error_category=type(error).__name__)
            if budget is not None or snapshot is not None: raise
            return []

    async def prepare_reference(self, case_id, budget):
        """Explicit paid operation. Caller must enforce the operator gate and supply a job budget."""
        if budget is None:
            raise StoreError('Reference preparation requires a bounded operator job.', 422, 'budget_required')
        if self.collection is None:
            raise StoreError('Atlas is required to prepare visual references.', 503, 'atlas_unavailable')
        def inspect_case(tx):
            eligible, _ = self._snapshot(tx)
            case = eligible.get(case_id)
            if not case:
                raise StoreError('This case is not an eligible consented reference.', 409, 'reference_ineligible')
            media = self._media(tx, case['image_hash'])
            identifier = key_for(self.repo.world_id, 'visual-reference', case_id, str(case['revision']), MODEL, SCHEMA)
            return case, media, identifier, tx.get(COLLECTION, identifier)
        case, media, identifier, existing = await asyncio.to_thread(self.repo.read, inspect_case)
        if existing:
            return {'case_id': case_id, 'revision': case['revision'], 'status': 'already_prepared'}
        vector = await self._embed(media, budget)
        record = {'_id': identifier, 'id': identifier, 'world_id': self.repo.world_id, 'case_id': case_id,
            'case_revision': case['revision'], 'group_id': case['group_id'], 'image_hash': case['image_hash'],
            'role': 'reference', 'review_status': 'approved', 'shared_consent': True, 'retired': False,
            'embedding': vector, 'embedding_model': MODEL, 'embedding_dimensions': DIMENSIONS,
            'embedding_schema_version': SCHEMA, 'provenance': deepcopy(case['provenance']),
            'created_at': self.repo.clock()}
        def persist(tx):
            current, _ = self._snapshot(tx)
            if current.get(case_id) != case:
                raise StoreError('The reference review changed during embedding. Nothing was enrolled.', 409, 'stale_reference')
            if not tx.get(COLLECTION, identifier): tx.put(COLLECTION, record)
        await asyncio.to_thread(self.repo.transaction, persist)
        return {'case_id': case_id, 'revision': case['revision'], 'status': 'prepared',
                'model': MODEL, 'dimensions': DIMENSIONS, 'schema_version': SCHEMA}

    async def ensure_index(self):
        """Explicit administrative setup only; never called by retrieve or preparation."""
        if self.collection is None:
            raise StoreError('Atlas is required for a visual reference index.', 503, 'atlas_unavailable')
        from pymongo.operations import SearchIndexModel
        records = await asyncio.to_thread(lambda: list(self.collection.list_search_indexes(name=self.index)))
        if not records:
            await asyncio.to_thread(self.collection.create_search_index,
                SearchIndexModel(definition=visual_reference_index_definition(), name=self.index, type='vectorSearch'))
            self._state('index_building', 'Visual reference index creation requested; readiness is not yet verified.')
        else:
            ready = await self._index_ready()
            if ready: self._state('ready', 'Visual reference index is queryable.', available=True)
        return deepcopy(self.status)
