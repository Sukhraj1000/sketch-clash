"""Controlled catalogue/embedding/Atlas adapters; no network or model quality claims."""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from app.catalog import CharacterCatalog
from app.config import Settings
from app.quality_catalog import freeze_catalog, make_evaluation_catalog
from app.repository import MemoryRepository, StoreError


class Collection:
    def __init__(self, repo):
        self.repo, self.queries, self.after_query = repo, [], None
    def aggregate(self, pipeline, **kwargs):
        self.queries.append(deepcopy(pipeline))
        fields = pipeline[0]['$vectorSearch']['filter']
        rows = [doc for doc in self.repo._data['characterTypes'].values()
                if all(doc.get(k) == v for k, v in fields.items())]
        result = [{**{k: row.get(k) for k in ('canonical_type_id', 'canonical_key', 'display_name', 'description', 'template_id')},
                   'score': .9} for row in rows[:3]]
        if self.after_query: self.after_query()
        return result


class EmbedClient:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.aio = SimpleNamespace(models=SimpleNamespace(embed_content=self.embed_content))
    async def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail: raise TimeoutError('Fixture transport uncertainty')
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3, 0, 0])])


class Budget:
    def __init__(self): self.reserved, self.completed = [], []
    async def reserve(self, **kwargs):
        self.reserved.append(kwargs)
        return len(self.reserved)
    async def complete(self, reservation, response): self.completed.append(reservation)


@pytest.fixture
def configured():
    settings = Settings(repository='memory', embedding_model='gemini-embedding-2', embedding_dimensions=3,
                        gemini_api_key='fixture-not-a-secret')
    repo = MemoryRepository(settings)
    collection = Collection(repo)
    repo.db = SimpleNamespace(characterTypes=collection)
    records = CharacterCatalog.seed_records()
    mug = next(record for record in records if record['canonical_key'] == 'mug')
    mug.update(_id='mug', embedding=[1, 0, 0], embedding_model='gemini-embedding-2', embedding_dimensions=3,
               embedding_schema_version='1')
    teapot = {**deepcopy(mug), '_id': 'teapot', 'canonical_type_id': 'teapot', 'canonical_key': 'teapot',
        'display_name': 'Teapot', 'aliases': ['tea kettle'], 'normalized_aliases': ['tea-kettle'],
        'template_id': 'generic', 'description': 'A handled vessel with a pouring spout.'}
    for row in (mug, teapot): repo.transaction(lambda tx, doc=row: tx.put('characterTypes', doc))
    return repo, collection, EmbedClient(), Budget()


@pytest.mark.asyncio
async def test_frozen_exact_alias_lookup_preserves_custom_live_catalogue_without_writes(configured):
    repo, collection, client, budget = configured
    snapshot = freeze_catalog(repo)
    assert snapshot['retrieval_mode'] == 'guarded_atlas_vector_search'
    assert 'embedding' not in snapshot['records'][0]
    assert 'fixture-not-a-secret' not in repr(snapshot)
    catalog = make_evaluation_catalog(snapshot, repo, client, budget)
    frozen = await catalog.resolve_character_type('tea kettle')
    assert frozen['record']['canonical_type_id'] == 'teapot'
    # Changes in live metadata do not replace an already frozen exact result.
    repo._data['characterTypes']['teapot']['display_name'] = 'Changed later'
    assert (await catalog.resolve_character_type('tea kettle'))['record']['display_name'] == 'Teapot'
    before = deepcopy(repo._data)
    await catalog.ensure_type({'canonical_key': 'must-not-save'})
    assert repo._data == before
    assert client.calls == [] and collection.queries == [] and budget.reserved == []
    assert (await catalog.resolve_character_type('coffee mug'))['record']['canonical_type_id'] == 'mug'


@pytest.mark.asyncio
async def test_unknown_identity_uses_real_vector_query_shape_and_counts_each_actual_embedding(configured):
    repo, collection, client, budget = configured
    catalog = make_evaluation_catalog(freeze_catalog(repo), repo, client, budget)
    first = await catalog.resolve_character_type('watering can', 'handled watering vessel')
    second = await catalog.resolve_character_type('watering can', 'handled watering vessel')
    assert first['record']['canonical_type_id'] == 'watering-can'  # Similarity must never merge identity.
    assert first['retrieval']['mode'] == 'guarded_atlas_vector_search'
    assert [r['canonical_type_id'] for r in first['related']] == ['mug', 'teapot']
    assert len(client.calls) == len(budget.reserved) == len(budget.completed) == 1
    assert budget.reserved[0]['kind'] == 'catalog_embedding'
    assert budget.reserved[0]['output_tokens'] == 0
    assert client.calls[0]['model'] == 'gemini-embedding-2'
    assert client.calls[0]['contents'].startswith('task: search result | query:')
    assert client.calls[0]['config'] == {'output_dimensionality': 3}
    query = collection.queries[0][0]['$vectorSearch']
    assert query['queryVector'] == [1, 0, 0]
    assert query['limit'] == 3 and query['numCandidates'] == 60
    assert query['filter'] == {'approved': True, 'embedding_model': 'gemini-embedding-2',
        'embedding_dimensions': 3, 'embedding_schema_version': '1'}
    assert len(collection.queries) == 2
    assert second['related'] == first['related']
    assert 'watering-can' not in repo._data['characterTypes']


@pytest.mark.asyncio
async def test_vector_drift_before_or_during_query_fails_closed(configured):
    repo, collection, client, budget = configured
    snapshot = freeze_catalog(repo)
    catalog = make_evaluation_catalog(snapshot, repo, client, budget)
    repo._data['characterTypes']['mug']['embedding'] = [0, 1, 0]
    with pytest.raises(StoreError) as before:
        await catalog.resolve_character_type('watering can')
    assert before.value.code == 'catalog_snapshot_changed'
    assert client.calls == []
    repo._data['characterTypes']['mug']['embedding'] = [1, 0, 0]
    collection.after_query = lambda: repo._data['characterTypes']['mug'].update(description='Changed during query')
    with pytest.raises(StoreError) as during:
        await catalog.resolve_character_type('watering can')
    assert during.value.code == 'catalog_snapshot_changed'
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_new_nonembedded_live_types_do_not_change_frozen_exact_or_vector_corpus(configured):
    repo, collection, client, budget = configured
    catalog = make_evaluation_catalog(freeze_catalog(repo), repo, client, budget)
    row = {'_id': 'new-live', 'canonical_key': 'new-live', 'canonical_type_id': 'new-live', 'approved': True,
           'aliases': ['answer-leak'], 'normalized_aliases': ['answer-leak'], 'description': 'Added after snapshot',
           'template_id': 'generic'}
    repo.transaction(lambda tx: tx.put('characterTypes', row))
    unknown = await catalog.resolve_character_type('answer leak')
    assert unknown['match'] == 'new_type'
    assert unknown['record']['canonical_type_id'] == 'answer-leak'
    assert all(r['canonical_key'] != 'new-live' for r in unknown['related'])


@pytest.mark.asyncio
async def test_embedding_failure_preserves_unknown_budget_and_never_becomes_fake_fallback(configured):
    repo, _, client, budget = configured
    catalog = make_evaluation_catalog(freeze_catalog(repo), repo, client, budget)
    client.fail = True
    with pytest.raises(TimeoutError): await catalog.resolve_character_type('watering can')
    assert len(budget.reserved) == 1 and budget.completed == []
    assert len(client.calls) == 1


def test_tampered_snapshot_is_rejected_and_memory_mode_is_honestly_unavailable(configured):
    repo, _, client, budget = configured
    snapshot = freeze_catalog(repo)
    snapshot['records'][0]['description'] = 'tampered'
    with pytest.raises(StoreError) as changed: make_evaluation_catalog(snapshot, repo, client, budget)
    assert changed.value.code == 'catalog_snapshot_changed'
    memory = MemoryRepository(Settings(repository='memory'))
    frozen = freeze_catalog(memory)
    assert frozen['retrieval_expected'] is False
    assert frozen['retrieval_mode'] == 'unavailable'


@pytest.mark.asyncio
async def test_incompatible_embedding_provenance_never_mixes_vectors(configured):
    repo, collection, client, budget = configured
    repo._data['characterTypes']['teapot']['embedding_model'] = 'different-model'
    snapshot = freeze_catalog(repo)
    assert [m['canonical_key'] for m in snapshot['vector_manifest']] == ['mug']
    catalog = make_evaluation_catalog(snapshot, repo, client, budget)
    result = await catalog.resolve_character_type('watering can')
    assert [r['canonical_type_id'] for r in result['related']] == ['mug']
    # Its exact metadata remains a separate, non-vector identity lookup.
    assert (await catalog.resolve_character_type('tea kettle'))['record']['canonical_type_id'] == 'teapot'
