"""Pace changes affect real admission without sending any provider requests."""
import asyncio
import threading

import pytest

from app.config import Settings
from app.provider_controls import ProviderControls
from app.provider_queue import ProviderFailure, ProviderQueue
from app.repository import MemoryRepository
from test_provider_queue import ManualClock, drain_tasks


@pytest.mark.asyncio
async def test_faster_wakes_pending_dispatch_and_slower_extends_it():
    clock = ManualClock()
    queue = ProviderQueue(clock=clock, sleep=clock.sleep)
    queue.set_pacing('slow')
    calls = []
    async def call(): calls.append(clock.now)
    await queue.run('first', call)
    pending = asyncio.create_task(queue.run('pending', call))
    await drain_tasks()
    await clock.advance(20)
    assert calls == [100.]
    queue.set_pacing('fast')
    await asyncio.wait_for(pending, 1)
    assert calls == [100., 120.]
    pending = asyncio.create_task(queue.run('slower', call))
    await drain_tasks()
    queue.set_pacing('slow')
    await drain_tasks()
    await clock.advance(15)
    assert calls == [100., 120.]
    await clock.advance(45)
    await asyncio.wait_for(pending, 1)
    assert calls == [100., 120., 180.]
    assert queue.status()['local_usage']['requests_last_24_hours'] == 3
    assert all(future.done() for _, future in clock.sleepers)


@pytest.mark.asyncio
async def test_pace_changes_preserve_cooldown_daily_cap_and_pause():
    clock = ManualClock()
    queue = ProviderQueue(clock=clock, sleep=clock.sleep, requests_per_day=1)
    calls = []
    async def call(): calls.append(clock.now)
    queue.cooldown_until = 145.
    queue.set_pacing('slow')
    pending = asyncio.create_task(queue.run('pending', call))
    await drain_tasks()
    queue.set_pacing('fast')
    await drain_tasks()
    await clock.advance(20)
    assert calls == []
    await clock.advance(25)
    await asyncio.wait_for(pending, 1)
    queue.set_pacing('slow'); queue.set_pacing('fast')
    with pytest.raises(ProviderFailure) as exc: await queue.run('blocked', call)
    assert exc.value.diagnostic.category == 'local_daily_cap'
    queue.paused = True
    queue.set_pacing('steady')
    with pytest.raises(ProviderFailure) as exc: await queue.run('paused', call)
    assert exc.value.diagnostic.category == 'ai_paused'
    assert calls == [145.]
    assert queue.pacing()['effective_requests_per_minute'] == 2


@pytest.mark.asyncio
async def test_persisted_pace_reload_respects_new_hard_limit_and_does_not_unpause():
    repo = MemoryRepository(Settings(repository='memory', world_id='pacing-fixture'))
    queue = ProviderQueue(paused=True)
    controls = ProviderControls(repo, queue)
    assert (await controls.update('steady'))['revision'] == 1
    assert queue.paused and queue.completed == 0
    restarted = ProviderQueue(requests_per_minute=2, paused=True)
    loaded = ProviderControls(repo, restarted)
    loaded.load()
    assert loaded.status()['mode'] == 'steady'
    assert loaded.status()['effective_requests_per_minute'] == 1
    assert restarted.paused and restarted.completed == 0
    assert max(option['requests_per_minute'] for option in loaded.status()['options']) == 2


@pytest.mark.asyncio
async def test_failed_save_does_not_change_running_pace():
    repo = MemoryRepository(Settings(repository='memory'))
    controls = ProviderControls(repo, ProviderQueue())
    def fail(_): raise RuntimeError('storage unavailable')
    repo.transaction = fail
    with pytest.raises(RuntimeError): await controls.update('slow')
    assert controls.status()['mode'] == 'fast' and controls.status()['revision'] == 0


@pytest.mark.asyncio
async def test_disconnected_save_finishes_without_diverging_running_and_durable_pace():
    repo = MemoryRepository(Settings(repository='memory'))
    controls = ProviderControls(repo, ProviderQueue(paused=True))
    started, release = threading.Event(), threading.Event()
    transaction = repo.transaction
    def blocked(operation):
        started.set()
        assert release.wait(2)
        return transaction(operation)
    repo.transaction = blocked
    pending = asyncio.create_task(controls.update('slow'))
    await asyncio.to_thread(started.wait, 1)
    pending.cancel()
    await drain_tasks()
    pending.cancel()
    await drain_tasks()
    release.set()
    with pytest.raises(asyncio.CancelledError): await pending
    assert controls.status()['mode'] == 'slow' and controls.status()['paused']
    recovered = ProviderControls(repo, ProviderQueue())
    recovered.load()
    assert recovered.status()['mode'] == 'slow'


def test_routes_validate_bounded_modes_and_restore_before_worker_start():
    from fastapi.testclient import TestClient
    from backend.app.config import Settings as RuntimeSettings
    from backend.app.main import create_app
    from backend.app.repository import MemoryRepository as RuntimeRepository
    settings = RuntimeSettings(repository='memory', world_id='pace-api-fixture', ai_paused=True)
    repo = RuntimeRepository(settings)
    with TestClient(create_app(settings, repo, object())) as client:
        assert client.get('/api/observatory/pacing').json()['mode'] == 'fast'
        changed = client.post('/api/observatory/pacing', json={'mode': 'slow'})
        assert changed.status_code == 200 and changed.json()['paused']
        assert changed.json()['effective_requests_per_minute'] == 1
        for payload in ({'mode': 'unlimited'}, {'mode': 'fast', 'requests_per_minute': 99}, {'mode': 'fast', 'paused': False}):
            assert client.post('/api/observatory/pacing', json=payload).status_code == 422
        assert client.post('/api/observatory/pacing', json={'mode': 'fast'},
                           headers={'Origin': 'https://untrusted.example'}).status_code == 403
        assert client.app.state.provider_queue.completed == 0
    with TestClient(create_app(settings, repo, object())) as restarted:
        state = restarted.get('/api/observatory/pacing').json()
        assert state['mode'] == 'slow' and state['paused'] and state['revision'] == 1
