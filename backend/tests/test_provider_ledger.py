"""Shared ledger admission tests use only in-memory repository and fake SDK calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.config import Settings
from app.provider_ledger import ProviderLedger, COLLECTION, LEDGER_ID
from app.provider_queue import ProviderQueue, ProviderFailure
from app.repository import MemoryRepository, StoreError


@pytest.fixture
def setup():
    repo = MemoryRepository(Settings(repository='memory'))
    now = [100000.]
    async def sleep(seconds):
        now[0] += seconds
        await asyncio.sleep(0)
    def queue(**kwargs):
        return ProviderQueue(clock=lambda: now[0], sleep=sleep, ledger=ProviderLedger(repo), **kwargs)
    return repo, now, queue


@pytest.mark.asyncio
async def test_restart_keeps_all_model_category_allowance_and_exact_window_boundary(setup):
    repo, now, factory = setup
    calls = []
    async def invoke(): calls.append(now[0]); return 'ok'
    first = factory(requests_per_day=2)
    await first.run('argon', invoke, 'council')
    await first.run('argon', invoke, 'reflection')
    restarted = factory(requests_per_day=2); await restarted.load_ledger()
    assert restarted.status()['counter_scope'] == 'database_rolling_window'
    assert restarted.status()['local_usage']['requests_remaining_day'] == 0
    with pytest.raises(ProviderFailure) as failure:
        await restarted.run('argon', invoke, 'council')
    assert failure.value.diagnostic.category == 'local_daily_cap' and len(calls) == 2
    now[0] = calls[0]+86400.
    await restarted.run('argon', invoke, 'council')
    assert len(calls) == 3 and restarted.status()['local_usage']['requests_last_24_hours'] == 2


def admit(ledger, request, now, **limits):
    return ledger.admit(request, now, requests_per_minute=limits.get('minute', 4),
        requests_per_day=limits.get('day', 200), interval_seconds=limits.get('interval', 15.),
        concurrency=limits.get('concurrency', 1), model='fixture', category=limits.get('category', 'agent'),
        priority=limits.get('priority'))


def test_atomic_admission_prevents_two_workers_spending_the_last_allowance(setup):
    repo, now, _ = setup
    gate = Barrier(2)
    def dispatch(identifier):
        gate.wait(timeout=5)
        return admit(ProviderLedger(repo), identifier, now[0], day=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(dispatch, ['worker-a', 'worker-b']))
    assert sum(result['admitted'] for result in results) == 1
    assert next(result for result in results if not result['admitted'])['reason'] == 'local_daily_cap'
    assert len(repo._data[COLLECTION][LEDGER_ID]['reservations']) == 1


def test_spacing_minute_cap_and_active_leases_are_shared_across_workers(setup):
    repo, now, _ = setup
    a, b = ProviderLedger(repo), ProviderLedger(repo)
    assert admit(a, 'a', now[0])['admitted']
    a.finish('a', now[0], outcome='completed')
    assert admit(b, 'b', now[0]+1)['reason'] == 'local_background_spacing'
    assert admit(b, 'b', now[0]+15)['admitted']
    assert admit(a, 'c', now[0]+30)['reason'] == 'local_concurrency'
    b.finish('b', now[0]+30, outcome='completed')
    assert admit(a, 'c', now[0]+30)['admitted']
    a.finish('c', now[0]+30, outcome='completed')
    assert admit(b, 'd', now[0]+45)['admitted']
    b.finish('d', now[0]+45, outcome='completed')
    assert admit(a, 'e', now[0]+59, interval=0)['reason'] == 'local_minute_cap'
    assert admit(a, 'e', now[0]+60)['admitted']


def test_reservation_identity_is_idempotent_and_contains_no_credentials(setup):
    repo, now, _ = setup
    ledger = ProviderLedger(repo)
    first = admit(ledger, 'same-reservation', now[0])
    second = admit(ledger, 'same-reservation', now[0])
    assert first == second
    record = repo._data[COLLECTION][LEDGER_ID]
    assert len(record['reservations']) == 1
    assert 'world_id' not in record and 'api_key' not in str(record)


@pytest.mark.asyncio
async def test_unknown_provider_outcome_remains_charged_after_restart(setup):
    repo, now, factory = setup
    async def unknown(): raise TimeoutError()
    queue = factory(requests_per_day=1)
    with pytest.raises(ProviderFailure) as error: await queue.run('argon', unknown)
    assert not error.value.diagnostic.outcome_known
    record = repo._data[COLLECTION][LEDGER_ID]['reservations'][0]
    assert record['outcome'] == 'uncertain' and record['lease_until'] > now[0]
    restarted = factory(requests_per_day=1); await restarted.load_ledger()
    assert restarted.status()['local_usage']['requests_remaining_day'] == 0


@pytest.mark.asyncio
async def test_cancellation_after_dispatch_retains_charge_but_before_dispatch_does_not(setup):
    repo, now, factory = setup
    queue = factory(); entered = asyncio.Event()
    async def blocked(): entered.set(); await asyncio.Event().wait()
    task = asyncio.create_task(queue.run('fixture', blocked)); await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert queue.status()['active'] == queue.status()['waiting'] == 0
    assert ProviderLedger(repo).snapshot(now[0])['timestamps'] == [now[0]]
    assert repo._data[COLLECTION][LEDGER_ID]['reservations'][0]['outcome'] == 'uncertain'
    preparing = asyncio.Event()
    async def prepare(): preparing.set(); await asyncio.Event().wait()
    next_queue = factory()
    now[0] += 301
    next_task = asyncio.create_task(next_queue.run('fixture', blocked, prepare=prepare))
    await preparing.wait(); next_task.cancel()
    with pytest.raises(asyncio.CancelledError): await next_task
    assert len(ProviderLedger(repo).snapshot(now[0])['timestamps']) == 1


@pytest.mark.asyncio
async def test_local_control_failure_is_not_google_error_and_retains_conservative_claim(setup):
    repo, now, factory = setup
    queue = factory()
    async def guarded(): raise StoreError('Evaluation paused.', 409, 'evaluation_paused')
    with pytest.raises(StoreError) as error: await queue.run('fixture', guarded)
    assert error.value.code == 'evaluation_paused'
    assert queue.status()['last_error'] is None
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    assert ProviderLedger(repo).snapshot(now[0])['local_aborts'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['read', 'reservation'])
async def test_storage_failure_prevents_provider_dispatch(setup, phase):
    repo, now, factory = setup
    queue = factory(); calls = []
    async def forbidden(): calls.append(True)
    def unavailable(*args, **kwargs): raise StoreError('Unconfirmed storage.', 503, 'write_unconfirmed')
    if phase == 'read': queue.ledger.snapshot = unavailable
    else: queue.ledger.admit = unavailable
    with pytest.raises(ProviderFailure) as error: await queue.run('fixture', forbidden)
    assert error.value.diagnostic.category == 'local_ledger_unavailable'
    assert not calls and queue.status()['last_error'] is None


@pytest.mark.asyncio
async def test_unconfirmed_reservation_commit_never_calls_provider_and_stays_charged(setup):
    repo, now, factory = setup
    queue = factory(); original = queue.ledger.admit; calls = []
    def commit_then_disconnect(*args, **kwargs):
        original(*args, **kwargs)
        raise StoreError('Commit outcome unconfirmed.', 503, 'write_unconfirmed')
    queue.ledger.admit = commit_then_disconnect
    async def forbidden(): calls.append(True)
    with pytest.raises(ProviderFailure): await queue.run('fixture', forbidden)
    assert not calls and len(ProviderLedger(repo).snapshot(now[0])['timestamps']) == 1


def test_cutover_is_conservative_idempotent_and_discloses_unknown_earlier_history(setup):
    repo, now, _ = setup
    ledger = ProviderLedger(repo)
    snapshot = ledger.seed_cutover([now[0]]*3, now[0], source='conservative_previous_process_count')
    assert len(snapshot['timestamps']) == 3 and snapshot['historical_usage_unknown']
    assert not snapshot['rolling_window_complete']
    assert ledger.seed_cutover([], now[0]) == snapshot
    assert ProviderLedger(repo).snapshot(now[0]+86400)['rolling_window_complete']
    assert not ProviderLedger(repo).snapshot(now[0]+86400)['timestamps']

@pytest.mark.asyncio
async def test_stale_worker_obeys_shared_slow_pace_and_legacy_reload(setup):
    from app.provider_controls import ProviderControls
    repo, now, factory = setup
    a, b = factory(), factory()
    ca, cb = ProviderControls(repo, a), ProviderControls(repo, b)
    ca.load(); cb.load()
    await ca.update('slow')
    assert b.pacing_mode == 'fast'  # Deliberately stale worker.
    calls = []
    async def invoke(): calls.append(now[0])
    await a.run('argon', invoke)
    await b.run('flash', invoke)
    assert calls[1]-calls[0] == 60.
    assert b.pacing_mode == 'slow'
    # The transaction itself enforces Slow even if a caller supplies Fast.
    result = admit(ProviderLedger(repo), 'stale-worker', now[0]+15, interval=15)
    assert not result['admitted'] and result['wait_seconds'] == 45.
    restarted = factory()
    ProviderControls(repo, restarted).load()
    assert restarted.pacing_mode == 'slow'


@pytest.mark.asyncio
async def test_restart_restores_background_clock_without_inheriting_a_recent_camera_dispatch(setup):
    from app.provider_controls import ProviderControls
    repo, now, factory = setup
    first = factory()
    await ProviderControls(repo, first).update('slow')
    calls = []
    async def call(): calls.append(now[0])
    await first.run('argon', call, 'council')
    await first.run('flash', call, 'recognition')
    assert calls == [100000., 100000.]
    snapshot = ProviderLedger(repo).snapshot(now[0])
    assert snapshot['last_dispatch_at'] == 100000.
    assert snapshot['last_background_dispatch_at'] == 100000.
    restarted = factory(); await restarted.load_ledger()
    assert restarted.pacing_mode == 'slow'
    assert restarted.status(priority='foreground')['dispatch_wait_seconds'] == 0.
    assert restarted.status(priority='background')['dispatch_wait_seconds'] == 60.
    await restarted.run('argon', call, 'council')
    assert calls == [100000., 100000., 100060.]
    assert restarted.status()['local_usage']['requests_last_24_hours'] == 2
    assert restarted.status()['local_usage']['all_requests_last_24_hours'] == 3


@pytest.mark.asyncio
async def test_late_ledger_snapshot_cannot_restore_older_pace_or_usage(setup):
    from app.provider_controls import ProviderControls
    repo, now, factory = setup
    queue = factory(); controls = ProviderControls(repo, queue)
    await controls.update('fast')
    async def call(): return 'ok'
    await queue.run('argon', call, 'council')
    older = queue.ledger_snapshot
    await controls.update('slow')
    await queue.run('argon', call, 'reflection')
    revision = queue.ledger_snapshot['revision']
    assert revision > older['revision'] and now[0] == 100060.
    queue._sync_ledger(older)  # A previously started normal-pool read returns late.
    assert queue.ledger_snapshot['revision'] == revision
    assert queue.pacing_mode == 'slow'
    assert queue.status()['local_usage']['requests_last_24_hours'] == 2
    assert queue.status()['local_usage']['all_requests_last_24_hours'] == 2
    assert queue.status()['dispatch_wait_seconds'] == 60.


def test_stale_worker_ledger_keeps_normal_requests_independent_but_cooldown_shared(setup):
    repo, now, _ = setup
    repo.transaction(lambda tx: ProviderLedger.pacing_in_transaction(tx, 'slow', now[0]))
    a, b = ProviderLedger(repo), ProviderLedger(repo)
    assert admit(a, 'island', now[0], category='council')['admitted']
    # Island's active lease and exhausted daily allowance cannot block cameras.
    assert admit(b, 'camera-a', now[0], category='recognition', day=1)['admitted']
    assert admit(a, 'camera-b', now[0], category='recognition', day=1)['admitted']
    assert admit(b, 'camera-c', now[0], category='recognition')['reason'] == 'local_concurrency'
    assert admit(b, 'island-daily', now[0], category='reflection', day=1)['reason'] == 'local_daily_cap'
    a.finish('island', now[0], outcome='completed')
    assert admit(b, 'island-soon', now[0]+15, category='council')['wait_seconds'] == 45.
    b.finish('camera-a', now[0], outcome='completed', cooldown_until=now[0]+75)
    a.finish('camera-b', now[0], outcome='completed')
    assert admit(a, 'camera-cooldown', now[0]+60, category='recognition')['reason'] == 'provider_cooldown'
    assert admit(a, 'island-cooldown', now[0]+60, category='council')['reason'] == 'provider_cooldown'
    assert admit(a, 'camera-next', now[0]+75, category='recognition', day=1)['admitted']
    assert admit(a, 'island-next', now[0]+75, category='reflection')['admitted']
    rows = repo._data[COLLECTION][LEDGER_ID]['reservations']
    assert [row['scope'] for row in rows] == ['island', 'interactive', 'interactive', 'interactive', 'island']
    assert len(rows) == 5


@pytest.mark.parametrize('category,island', [
    ('recognition', False), ('recognition_embedding', False), ('embedding', False),
    ('council', True), ('reflection', True), ('evaluation_recognition', False),
    ('quality', False), (None, True)])
def test_legacy_reservations_keep_all_usage_and_attribute_unknown_history_to_islands(setup, category, island):
    repo, now, _ = setup
    ledger = ProviderLedger(repo)
    ledger.seed_cutover([now[0]], now[0])
    def legacy(tx):
        ProviderLedger.pacing_in_transaction(tx, 'slow', now[0])
        record = tx.get(COLLECTION, LEDGER_ID)
        if category: record['reservations'][0]['category'] = category
        tx.put(COLLECTION, record)
    repo.transaction(legacy)
    snapshot = ledger.snapshot(now[0])
    assert snapshot['timestamps'] == [now[0]]
    assert snapshot['island_timestamps'] == ([now[0]] if island else [])
    assert snapshot['last_background_dispatch_at'] == (now[0] if island else None)
    result = admit(ledger, 'next-island', now[0]+15, category='council')
    assert result['admitted'] is (not island)
    if island:
        assert result['reason'] == 'local_background_spacing' and result['wait_seconds'] == 45.


@pytest.mark.asyncio
async def test_pause_during_admission_never_dispatches_and_keeps_conservative_reservation(setup):
    from threading import Event
    repo, now, factory = setup
    queue = factory(); started, release = Event(), Event()
    original = queue.ledger.admit; calls = []
    def blocked_admission(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)
    queue.ledger.admit = blocked_admission
    async def invoke(): calls.append(True)
    task = asyncio.create_task(queue.run('fixture', invoke))
    assert await asyncio.to_thread(started.wait, 5)
    queue.paused = True; release.set()
    with pytest.raises(ProviderFailure) as failure: await task
    assert failure.value.diagnostic.category == 'ai_paused'
    assert not calls and queue.status()['last_error'] is None
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    assert queue.status()['active'] == queue.status()['waiting'] == 0
    assert ProviderLedger(repo).snapshot(now[0])['active_leases'] == 0
