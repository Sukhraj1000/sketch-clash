"""Fixture battles use real persistence contracts, never recognition or island rewards."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from backend.app.arena import ArenaStore
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repository import MemoryRepository, StoreError


def setup():
    settings = Settings(repository='memory', ai_paused=True, world_id='arena-test')
    repo = MemoryRepository(settings)
    return settings, repo, ArenaStore(repo)


def ids():
    from backend.app.combat_fixtures import get_catalog
    return [item['id'] for item in get_catalog()['fixtures'][:2]]


def test_immutable_snapshot_idempotency_and_no_live_rewards():
    _, repo, store = setup()
    before = deepcopy(repo._data)
    chosen = ids()
    record = store.create('first-match', chosen)
    assert record == store.create('first-match', chosen) == store.get(record['id'])
    assert record['source'] == 'local_fixture' and not record['island_rewards']
    assert record['immutable'] and len(record['snapshot_sha256']) == 64
    assert record['catalog_snapshot']['rules'] and record['counterfactual']
    record['fighters'][0]['price']['amount_gbp'] = 1000000
    assert store.get(record['id'])['fighters'][0]['price']['amount_gbp'] != 1000000
    assert {k: v for k, v in repo._data.items() if k != 'arenaBattles'} == before
    with pytest.raises(StoreError) as error:
        store.create('first-match', list(reversed(chosen)))
    assert error.value.code == 'arena_request_conflict'
    assert len(repo._data['arenaBattles']) == 1


def test_concurrent_retry_returns_one_seed_and_result():
    _, repo, store = setup()
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(lambda _: store.create('race', ids()), range(6)))
    assert all(record == records[0] for record in records)
    assert len(repo._data['arenaBattles']) == 1


def test_world_isolation_and_unknown_fixture_fail_without_writes():
    _, repo, store = setup()
    with pytest.raises(StoreError): store.create('bad', ['not-a-fixture', ids()[1]])
    assert not repo._data.get('arenaBattles')
    record = store.create('ok', ids())
    repo.world_id = 'other-world'
    with pytest.raises(StoreError) as error: store.get(record['id'])
    assert error.value.status == 404
    assert store.recent()['battles'] == []
    other = store.create('ok', ids())
    assert other['id'] != record['id']


def test_api_paused_no_provider_and_rejects_client_stats_seed_price():
    settings, repo, _ = setup()
    with TestClient(create_app(settings, repo, object())) as client:
        health = client.get('/api/health').json()
        assert health['ai_paused']
        catalog = client.get('/api/arena/catalog').json()
        assert catalog['storage_available'] and catalog['fixtures']
        before = deepcopy(repo._data)
        chosen = [f['id'] for f in catalog['fixtures'][:2]]
        body = {'request_id': 'http', 'fighter_ids': chosen}
        for field, value in [('seed', 9), ('price', 100000), ('stats', {'impact': 99})]:
            assert client.post('/api/arena/battles', json={**body, field: value}).status_code == 422
        assert client.post('/api/arena/battles', json={**body, 'fighter_ids': chosen[:1]}).status_code == 422
        assert client.post('/api/arena/battles', json=body, headers={'Origin': 'https://untrusted.example'}).status_code == 403
        response = client.post('/api/arena/battles', json=body)
        assert response.status_code == 200
        record = response.json()
        assert client.get('/api/arena/battles/'+record['id']).json() == record
        assert client.post('/api/arena/battles', json=body).json() == record
        assert client.get('/api/arena/battles').json()['battles'][0]['id'] == record['id']
        assert client.get('/api/health').json()['ai_paused']
        queue = client.app.state.provider_queue.status()
        assert queue['completed'] == queue['active'] == queue['waiting'] == 0
        assert {k: v for k, v in repo._data.items() if k != 'arenaBattles'} == before
