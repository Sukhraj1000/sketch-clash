"""Controlled image/provider/vector fixtures; not real evaluation evidence."""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from app.config import Settings
from app.images import normalize_image
from app.quality_references import (ApprovedReferences, COLLECTION, DIMENSIONS,
    INDEX, MODEL, SCHEMA, visual_reference_index_definition)
from app.repository import MemoryRepository, StoreError


class Budget:
    def __init__(self): self.calls, self.finished = [], []
    async def reserve(self, **values): self.calls.append(values); return {'number': len(self.calls)}
    async def complete(self, reservation, response): self.finished.append(reservation)


class Vectors:
    def __init__(self, repo):
        self.repo, self.pipelines = repo, []
        self.indexes = [{'name': INDEX, 'queryable': True, 'latestDefinition': visual_reference_index_definition()}]
        self.after_query = None
        self.index_writes = []
    def list_search_indexes(self, **kwargs): return deepcopy(self.indexes)
    def aggregate(self, pipeline, **kwargs):
        self.pipelines.append(pipeline)
        # Deliberately returns extra rows: adapter must enforce authoritative eligibility again.
        rows = self.repo.read(lambda tx: tx.find(COLLECTION, {'world_id': self.repo.world_id}))
        if self.after_query: self.after_query()
        return rows
    def create_search_index(self, model): self.index_writes.append(model)


@pytest.fixture
def setup():
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    vectors = Vectors(repo)
    repo.db = {COLLECTION: vectors}
    requests = []
    async def embed_content(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0] * DIMENSIONS)])
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(embed_content=embed_content)))
    return repo, vectors, requests, ApprovedReferences(repo, settings, client)


def photo(repo, colour):
    output = BytesIO()
    Image.new('RGB', (40, 40), colour).save(output, 'JPEG')
    image = normalize_image(output.getvalue(), 'image/jpeg', repo.settings)
    repo.save_media(image)
    return image


def case(repo, name='ref', *, colour='red', **changes):
    image = photo(repo, colour)
    value = {'_id': name, 'id': name, 'world_id': repo.world_id, 'revision': 1,
        'image_hash': image.image_hash, 'image_ref': image.image_ref, 'width': image.width, 'height': image.height,
        'expected': {'canonical_type_id': 'mug', 'clarification_required': False},
        'group_id': 'group-'+name, 'role': 'reference', 'review_status': 'approved',
        'shared_consent': True, 'visible_attributes': ['handle'],
        'provenance': {'reviewer': 'Engineering fixture, not a human judgement'}, **changes}
    repo.transaction(lambda tx: tx.put('qualityCases', value))
    return value


@pytest.mark.asyncio
async def test_no_approved_data_or_disabled_limit_never_calls_provider(setup):
    repo, vectors, calls, adapter = setup
    query = photo(repo, 'blue')
    for changes in ({'review_status': 'unreviewed'}, {'review_status': 'disputed'},
                    {'shared_consent': False}, {'retired': True}, {'role': 'reserved'}):
        case(repo, **changes)
        assert await adapter.retrieve(query.image_hash) == []
        assert adapter.status['status'] == 'no_approved_references'
    case(repo)
    assert await adapter.retrieve(query.image_hash, limit=0) == []
    assert not calls and not vectors.pipelines and not vectors.index_writes


@pytest.mark.asyncio
async def test_explicit_preparation_requires_consent_and_budget_and_is_idempotent(setup):
    repo, _, calls, adapter = setup
    reference = case(repo, shared_consent=False)
    with pytest.raises(StoreError, match='eligible'):
        await adapter.prepare_reference(reference['id'], Budget())
    reference = case(repo)
    with pytest.raises(StoreError, match='bounded'):
        await adapter.prepare_reference(reference['id'], None)
    assert not calls
    budget = Budget()
    result = await adapter.prepare_reference(reference['id'], budget)
    again = await adapter.prepare_reference(reference['id'], budget)
    assert result['status'] == 'prepared' and again['status'] == 'already_prepared'
    assert len(calls) == len(budget.calls) == len(budget.finished) == 1
    request = calls[0]
    assert request['model'] == MODEL and request['config'].output_dimensionality == 768
    assert len(request['contents']) == 1 and request['contents'][0].text is None
    assert request['contents'][0].inline_data.data == repo.get_media(reference['image_hash'])['data']
    saved = repo.read(lambda tx: tx.find(COLLECTION, {'world_id': repo.world_id}))[0]
    assert saved['case_revision'] == 1 and saved['embedding_schema_version'] == SCHEMA
    assert abs(sum(v*v for v in saved['embedding']) - 1) < 1e-10


@pytest.mark.asyncio
async def test_missing_index_or_unprepared_references_skip_paid_query_and_never_seed(setup):
    repo, vectors, calls, adapter = setup
    case(repo)
    query = photo(repo, 'blue')
    vectors.indexes = []
    assert await adapter.retrieve(query.image_hash) == []
    assert adapter.status['status'] == 'index_missing'
    vectors.indexes = [{'queryable': True, 'latestDefinition': visual_reference_index_definition()}]
    assert await adapter.retrieve(query.image_hash) == []
    assert adapter.status['status'] == 'not_enrolled'
    assert not calls and not vectors.index_writes


@pytest.mark.asyncio
async def test_vector_search_uses_server_filters_and_image_only_query(setup):
    repo, vectors, calls, adapter = setup
    reference = case(repo)
    await adapter.prepare_reference(reference['id'], Budget())
    query = photo(repo, 'blue')
    results = await adapter.retrieve(query.image_hash)
    assert [r['id'] for r in results] == [reference['id']]
    assert results[0]['label'] == 'mug' and results[0]['visible_features'] == ['handle']
    assert adapter.available and adapter.status['status'] == 'completed'
    search = vectors.pipelines[0][0]['$vectorSearch']
    assert search['index'] == INDEX and search['path'] == 'embedding'
    for field, value in {'world_id': repo.world_id, 'role': 'reference', 'review_status': 'approved',
        'shared_consent': True, 'retired': False, 'embedding_model': MODEL,
        'embedding_dimensions': DIMENSIONS, 'embedding_schema_version': SCHEMA}.items():
        assert search['filter'][field] == value
    assert search['filter']['case_id'] == {'$in': [reference['id']]}
    assert calls[-1]['contents'][0].inline_data.data == query.data
    assert calls[-1]['contents'][0].text is None  # No expected identity, filename or comments.
    assert not vectors.index_writes


@pytest.mark.asyncio
async def test_same_hash_excluded_groups_and_cross_role_groups_cannot_leak(setup):
    repo, _, calls, adapter = setup
    reference = case(repo)
    await adapter.prepare_reference(reference['id'], Budget())
    assert await adapter.retrieve(reference['image_hash']) == []
    query = photo(repo, 'blue')
    assert await adapter.retrieve(query.image_hash, exclude_groups=[reference['group_id']]) == []
    case(repo, 'reserved', colour='green', role='reserved', group_id=reference['group_id'], review_status='disputed')
    assert await adapter.retrieve(query.image_hash) == []
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_eventually_consistent_vector_cannot_restore_revoked_or_revised_case(setup):
    repo, vectors, _, adapter = setup
    reference = case(repo)
    await adapter.prepare_reference(reference['id'], Budget())
    query = photo(repo, 'blue')
    def revoke():
        repo.transaction(lambda tx: tx.put('qualityCases', {**reference, 'review_status': 'disputed'}))
    vectors.after_query = revoke
    assert await adapter.retrieve(query.image_hash) == []
    assert adapter.status['status'] == 'empty'
    vectors.after_query = None
    repo.transaction(lambda tx: tx.put('qualityCases', {**reference, 'revision': 2}))
    assert await adapter.retrieve(query.image_hash) == []
    assert adapter.status['status'] == 'not_enrolled'


@pytest.mark.asyncio
async def test_prepare_rechecks_case_after_provider_and_preserves_failed_reservation(setup):
    repo, _, _, adapter = setup
    reference = case(repo)
    budget = Budget()
    async def changed(**kwargs):
        repo.transaction(lambda tx: tx.put('qualityCases', {**reference, 'shared_consent': False}))
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0] * DIMENSIONS)])
    adapter.client.aio.models.embed_content = changed
    with pytest.raises(StoreError, match='changed'):
        await adapter.prepare_reference(reference['id'], budget)
    assert not repo.read(lambda tx: tx.find(COLLECTION, {'world_id': repo.world_id}))
    case(repo)
    async def fails(**kwargs): raise RuntimeError('provider transport failure')
    adapter.client.aio.models.embed_content = fails
    with pytest.raises(RuntimeError): await adapter.prepare_reference(reference['id'], budget)
    assert len(budget.calls) == 2 and len(budget.finished) == 1


@pytest.mark.asyncio
async def test_query_failure_is_unavailable_and_does_not_disclose_provider_message(setup):
    repo, vectors, _, adapter = setup
    reference = case(repo)
    await adapter.prepare_reference(reference['id'], Budget())
    query = photo(repo, 'blue')
    def fails(*args, **kwargs): raise RuntimeError('sensitive transport context')
    vectors.aggregate = fails
    assert await adapter.retrieve(query.image_hash) == []
    assert not adapter.available and adapter.status['status'] == 'unavailable'
    assert 'sensitive' not in str(adapter.status)


@pytest.mark.asyncio
async def test_preparation_budget_failure_precedes_provider(setup):
    repo, _, calls, adapter = setup
    reference = case(repo)
    class Exhausted(Budget):
        async def reserve(self, **kwargs): raise RuntimeError('budget exhausted')
    with pytest.raises(RuntimeError, match='budget exhausted'):
        await adapter.prepare_reference(reference['id'], Exhausted())
    assert not calls


def test_separate_index_has_eligibility_and_provenance_filters():
    fields = visual_reference_index_definition()['fields']
    assert fields[0] == {'type': 'vector', 'path': 'embedding', 'numDimensions': 768, 'similarity': 'cosine'}
    paths = {field['path'] for field in fields if field['type'] == 'filter'}
    assert {'world_id', 'role', 'review_status', 'shared_consent', 'retired', 'case_id',
            'group_id', 'image_hash', 'embedding_model', 'embedding_dimensions', 'embedding_schema_version'} <= paths
