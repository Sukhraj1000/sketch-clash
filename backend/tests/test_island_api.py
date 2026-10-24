"""HTTP authority and persistence checks; no paid models or real player data."""
from copy import deepcopy

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repository import MemoryRepository
from backend.tests.test_island import Clock, seed


def test_reading_island_never_starts_simulation_or_spends_ai_budget():
    clock = Clock()
    settings = Settings(repository='memory', world_id='fixture-island-http')
    repo = MemoryRepository(settings, clock)
    seed(repo)
    app = create_app(settings, repo, object())
    with TestClient(app) as client:
        before = deepcopy(repo._data)
        for _ in range(3):
            response = client.get('/api/island')
            assert response.status_code == 200
            assert response.json()['enabled'] is False
            assert response.json()['planner']['requests_today'] == 0
            assert response.json()['runtime']['worker_active'] is True
        assert repo._data == before
        denied = client.post('/api/island/personas', json={'idempotency_key': 'too-early'})
        assert denied.status_code == 409
        assert repo._data == before


def test_start_commands_restart_and_original_collection_are_preserved():
    clock = Clock()
    settings = Settings(repository='memory', world_id='fixture-island-http')
    repo = MemoryRepository(settings, clock)
    seed(repo)
    before = repo.world()
    app = create_app(settings, repo, object())
    with TestClient(app) as client:
        start = client.post('/api/island/start', json={})
        assert start.status_code == 200
        assert len(start.json()['agents']) == 5
        assert start.json()['planner']['requests_today'] == 0
        paused = client.post('/api/island/command', json={'idempotency_key': 'pause-command-1', 'kind': 'pause'})
        assert paused.status_code == 200 and paused.json()['paused']
        stored = deepcopy(repo._data)
        replay = client.post('/api/island/command', json={'idempotency_key': 'pause-command-1', 'kind': 'pause'})
        assert replay.status_code == 200 and repo._data == stored
        assert client.post('/api/island/command', json={'idempotency_key': 'pause-command-1', 'kind': 'resume'}).status_code == 409
        assert client.post('/api/island/planner', json={'enabled': False}).status_code == 200
        # Reopening / syncing new residents must not reset the user's AI preference.
        assert client.post('/api/island/start', json={}).json()['planner']['enabled'] is False
        assert client.get('/api/world').json() == before
    with TestClient(create_app(settings, repo, object())) as reopened:
        state = reopened.get('/api/island').json()
        assert state['enabled'] and state['paused']
        assert len(state['agents']) == 5
        assert state['planner']['enabled'] is False
        assert reopened.get('/api/world').json() == before


def test_browser_cannot_inject_resources_personas_or_cross_origin_commands():
    settings = Settings(repository='memory', world_id='fixture-island-http')
    repo = MemoryRepository(settings, Clock())
    seed(repo)
    with TestClient(create_app(settings, repo, object())) as client:
        client.post('/api/island/start', json={})
        for extra in ({'resources': {'materials': 9999}}, {'persona': {'role': 'Overlord'}}, {'world_id': 'other-world'}):
            response = client.post('/api/island/command', json={'idempotency_key': 'bad-command', 'kind': 'pause', **extra})
            assert response.status_code == 422
        response = client.post('/api/island/command', json={'idempotency_key': 'foreign', 'kind': 'pause'}, headers={'Origin': 'https://untrusted.example'})
        assert response.status_code == 403
        assert client.get('/api/island').json()['paused'] is False
        assert client.post('/api/island/planner', json={'enabled': True, 'model': 'unbounded'}).status_code == 422


def test_optional_planner_failure_does_not_disable_local_simulation(monkeypatch):
    from backend.app.island_planner import IslandPlanner
    def fail_indexes(self):
        raise RuntimeError('Controlled optional service failure')
    monkeypatch.setattr(IslandPlanner, 'ensure_indexes', fail_indexes)
    settings = Settings(repository='memory', world_id='fixture-island-http')
    repo = MemoryRepository(settings, Clock())
    seed(repo)
    with TestClient(create_app(settings, repo, object())) as client:
        state = client.post('/api/island/start', json={}).json()
        assert state['enabled']
        assert state['runtime']['worker_active']
        assert state['planner']['last_status'] == 'unavailable'
        assert client.post('/api/island/personas', json={'idempotency_key': 'no-planner'}).status_code == 503
