from types import SimpleNamespace
import pytest
from app.catalog import CharacterCatalog
from app.retrieval import AtlasRetriever, RetrievalConfig, embedding_input, vector_index_definition


@pytest.mark.asyncio
async def test_exact_alias_resolution_does_not_require_vector_search_or_merge_generic_types():
    catalog = CharacterCatalog()
    mug = await catalog.resolve_character_type(' COFFEE MUG ')
    spoon = await catalog.resolve_character_type('spoon')
    keyboard = await catalog.resolve_character_type('keyboard')
    assert mug['record']['canonical_type_id'] == 'mug'
    assert mug['retrieval']['status'] == 'skipped'
    assert spoon['record']['template_id'] == keyboard['record']['template_id'] == 'generic'
    assert spoon['record']['canonical_type_id'] != keyboard['record']['canonical_type_id']


@pytest.mark.asyncio
async def test_similarity_never_merges_unknown_identity_or_grants_ownership():
    class Similar:
        async def search(self, description):
            return {'status': 'completed', 'candidates': [{'canonical_type_id': 'mug', 'score': .9}]}
    resolved = await CharacterCatalog(retriever=Similar()).resolve_character_type('watering can', 'vessel with a spout')
    assert resolved['record']['canonical_type_id'] == 'watering-can'
    assert resolved['related'][0]['canonical_type_id'] == 'mug'
    assert resolved['match'] == 'new_type'


@pytest.mark.asyncio
async def test_missing_atlas_reports_unavailable_with_no_fabricated_results():
    found = await AtlasRetriever().search('handled container')
    assert found['status'] == 'unavailable' and found['candidates'] == []


def test_index_and_query_preprocessing_share_versioned_embedding_contract():
    fields = vector_index_definition(768)['fields']
    assert fields[0]['numDimensions'] == 768
    assert {'type': 'filter', 'path': 'embedding_model'} in fields
    query, options = embedding_input('  tall   bottle  ')
    doc, _ = embedding_input('tall bottle', document=True, title='Bottle')
    assert query == 'task: search result | query: tall bottle'
    assert doc == 'title: Bottle | text: tall bottle'
    assert options == {}

@pytest.mark.asyncio
async def test_atlas_adapter_uses_real_vector_query_filters_and_cached_embeddings():
    requests = []
    pipelines = []
    async def embed_content(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 2.0, 3.0])])
    class Cursor:
        async def to_list(self, length):
            return [{'canonical_type_id': 'mug', 'score': .82}]
    class Collection:
        async def aggregate(self, pipeline, **kwargs):
            pipelines.append(pipeline)
            return Cursor()
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(embed_content=embed_content)))
    retrieval = AtlasRetriever(Collection(), client, RetrievalConfig(dimensions=3))
    first = await retrieval.search('handled vessel')
    second = await retrieval.search('handled vessel')
    assert first['status'] == second['status'] == 'completed'
    assert len(requests) == 1
    search = pipelines[0][0]['$vectorSearch']
    assert search['filter']['approved'] is True
    assert search['filter']['embedding_model'] == 'gemini-embedding-2'
    assert search['filter']['embedding_dimensions'] == 3
    assert search['filter']['embedding_schema_version'] == '1'
    assert search['limit'] == 3 and search['numCandidates'] == 60
    assert first['candidates'][0]['canonical_type_id'] == 'mug'
    assert 'ownership' in first['detail']


@pytest.mark.asyncio
async def test_persisting_canonical_kind_never_writes_world_membership():
    writes = []
    class Collection:
        def update_one(self, query, update, **kwargs):
            writes.append((query, update, kwargs))
    catalogue = CharacterCatalog(Collection())
    resolved = await CharacterCatalog().resolve_character_type('spoon')
    await catalogue.ensure_type(resolved['record'])
    assert writes[0][0] == {'canonical_key': 'spoon'}
    assert '$setOnInsert' in writes[0][1]
    assert 'world_id' not in writes[0][1]['$setOnInsert']
