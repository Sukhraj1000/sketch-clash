"""Island controls never create artificial delays or caps on normal requests."""
import asyncio

import pytest

from app.config import Settings
from app.provider_controls import ProviderControls
from app.provider_ledger import ProviderLedger
from app.provider_queue import ProviderQueue, ProviderFailure
from app.repository import MemoryRepository
from test_provider_queue import ManualClock, drain_tasks, HttpError


async def settle(predicate):
    async with asyncio.timeout(2):
        while not predicate(): await asyncio.sleep(.001)
    await drain_tasks()


async def make_queue(clock, durable=False, **limits):
    repo = MemoryRepository(Settings(repository='memory'))
    ledger = ProviderLedger(repo) if durable else None
    queue = ProviderQueue(clock=clock, sleep=clock.sleep, ledger=ledger, **limits)
    await ProviderControls(repo, queue).update('slow')
    return queue


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_capture_has_no_artificial_spacing_and_does_not_move_the_island_clock(durable):
    clock = ManualClock(); queue = await make_queue(clock, durable)
    calls = []
    async def call(label): calls.append((label, clock.now))
    await queue.run('argon', lambda: call('island'), 'council')
    pending = asyncio.create_task(queue.run('argon', lambda: call('island-next'), 'council'))
    await settle(lambda: queue.status()['waiting'] == 1)
    for _ in range(6):
        await queue.run('flash', lambda: call('capture'), 'recognition')
    assert calls == [('island', 100.)] + [('capture', 100.)]*6
    assert not pending.done()
    assert queue.status(priority='foreground')['dispatch_wait_seconds'] == 0
    assert queue.status()['dispatch_wait_seconds'] == 60
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    assert queue.status()['local_usage']['all_requests_last_24_hours'] == 7
    await clock.advance(60); await asyncio.wait_for(pending, 2)
    assert calls[-1] == ('island-next', 160.)
    if durable:
        snapshot = queue.ledger.snapshot(clock())
        assert snapshot['island_timestamps'] == [100., 160.]
        assert len(snapshot['timestamps']) == 8


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_active_island_call_does_not_block_normal_pool_but_normal_concurrency_is_bounded(durable):
    clock = ManualClock(); queue = await make_queue(clock, durable)
    island_entered, island_release = asyncio.Event(), asyncio.Event()
    releases = [asyncio.Event(), asyncio.Event()]; entered = []
    async def island(): island_entered.set(); await island_release.wait()
    async def normal(index):
        entered.append(index)
        if index < 2: await releases[index].wait()
    island_task = asyncio.create_task(queue.run('argon', island, 'council'))
    await island_entered.wait()
    normals = [asyncio.create_task(queue.run('flash', lambda i=i: normal(i), 'recognition')) for i in range(3)]
    await settle(lambda: entered == [0, 1])
    assert not island_task.done() and not normals[2].done()
    assert queue.status()['scopes']['island']['active'] == 1
    assert queue.status(priority='foreground')['wait_reason'] == 'local_concurrency'
    releases[0].set(); await settle(lambda: entered == [0, 1, 2])
    assert clock.now == 100. and not island_task.done()
    releases[1].set(); island_release.set()
    await asyncio.gather(island_task, *normals)
    assert queue.status()['active'] == queue.status()['waiting'] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_exhausted_island_daily_cap_does_not_reject_normal_or_evaluation_requests(durable):
    clock = ManualClock(); queue = await make_queue(clock, durable, requests_per_day=1)
    async def call(): return 'ok'
    await queue.run('argon', call, 'council')
    with pytest.raises(ProviderFailure) as error: await queue.run('argon', call, 'reflection')
    assert error.value.diagnostic.category == 'local_daily_cap'
    for category in ('recognition', 'recognition_embedding', 'embedding', 'quality', 'evaluation_recognition', 'new-normal-feature'):
        assert await queue.run('fixture', call, category) == 'ok'
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    assert queue.status()['local_usage']['all_requests_last_24_hours'] == 7
    assert queue.status(priority='foreground')['wait_reason'] is None
    assert queue.status()['wait_reason'] == 'local_daily_cap'


@pytest.mark.asyncio
async def test_full_island_pending_queue_does_not_fill_normal_queue():
    clock = ManualClock(); queue = await make_queue(clock, max_pending=1)
    entered, release = asyncio.Event(), asyncio.Event()
    async def island(): entered.set(); await release.wait()
    async def normal(): return 'ok'
    active = asyncio.create_task(queue.run('argon', island, 'council')); await entered.wait()
    pending = asyncio.create_task(queue.run('argon', normal, 'reflection')); await drain_tasks()
    with pytest.raises(ProviderFailure): await queue.run('argon', normal, 'council')
    assert await queue.run('flash', normal, 'recognition') == 'ok'
    pending.cancel()
    with pytest.raises(asyncio.CancelledError): await pending
    release.set(); await active


@pytest.mark.asyncio
async def test_foreground_priority_cannot_bypass_an_island_scope_limit():
    clock = ManualClock(); queue = await make_queue(clock)
    calls = []
    async def call(): calls.append(clock.now)
    await queue.run('argon', call, 'council')
    pending = asyncio.create_task(queue.run('argon', call, 'reflection', priority='foreground'))
    await drain_tasks(); assert calls == [100.]
    await clock.advance(60); await pending
    assert calls == [100., 160.]


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_real_provider_cooldown_still_applies_to_normal_requests_without_extra_spacing(durable):
    clock = ManualClock(); queue = await make_queue(clock, durable)
    async def fail(): raise HttpError(429, headers={'retry-after': '45'})
    async def call(): return clock.now
    with pytest.raises(ProviderFailure): await queue.run('argon', fail, 'council')
    pending = asyncio.create_task(queue.run('flash', call, 'recognition'))
    await settle(lambda: queue.status()['waiting'] == 1)
    assert queue.status(priority='foreground')['wait_reason'] == 'provider_cooldown'
    await clock.advance(45)
    assert await asyncio.wait_for(pending, 2) == 145.
    assert queue.status()['dispatch_wait_seconds'] == 15
