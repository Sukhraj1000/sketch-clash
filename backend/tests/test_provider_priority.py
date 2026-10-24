"""Foreground scheduling never changes shared pace, budgets or active calls."""
import asyncio

import pytest

from app.config import Settings
from app.provider_ledger import ProviderLedger
from app.provider_queue import ProviderQueue
from app.repository import MemoryRepository
from test_provider_queue import ManualClock, drain_tasks


async def settle(predicate):
    # Durable admission uses a worker thread; yield without advancing fake time.
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.001)
    await drain_tasks()


def make_queue(clock, durable=False):
    ledger = ProviderLedger(MemoryRepository(Settings(repository='memory'))) if durable else None
    queue = ProviderQueue(clock=clock, sleep=clock.sleep, ledger=ledger)
    queue.set_pacing('slow')
    return queue


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_foreground_capture_takes_next_slot_from_unsent_council_without_extra_allowance(durable):
    clock = ManualClock(); queue = make_queue(clock, durable)
    calls = []
    async def call(label): calls.append((label, clock.now))
    await queue.run('argon', lambda: call('prime'), 'council')
    council = asyncio.create_task(queue.run('argon', lambda: call('council'), 'council'))
    await settle(lambda: queue.status()['waiting'] == 1)
    await clock.advance(20)
    capture = asyncio.create_task(queue.run('flash', lambda: call('capture'), 'recognition'))
    await settle(lambda: queue.status()['waiting'] == 2)
    assert queue.status()['scheduling']['next_category'] == 'recognition'
    assert queue.status()['active'] == 0
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    await clock.advance(40)
    await asyncio.wait_for(capture, 2)
    assert calls == [('prime', 100.), ('capture', 160.)]
    assert not council.done()
    await clock.advance(60)
    await asyncio.wait_for(council, 2)
    assert calls == [('prime', 100.), ('capture', 160.), ('council', 220.)]
    assert queue.pacing_mode == 'slow' and queue.min_dispatch_interval_seconds == 60
    assert queue.status()['local_usage']['requests_last_24_hours'] == 3
    if durable:
        assert queue.ledger.snapshot(clock())['timestamps'] == [100., 160., 220.]
    assert queue.status()['waiting'] == queue.status()['active'] == 0


@pytest.mark.asyncio
async def test_continuous_foreground_cannot_starve_a_ready_background_council():
    clock = ManualClock(); queue = make_queue(clock)
    calls = []
    async def call(label): calls.append((label, clock.now))
    await queue.run('argon', lambda: call('prime'), 'council')
    council = asyncio.create_task(queue.run('argon', lambda: call('council'), 'council'))
    await drain_tasks()
    captures = [asyncio.create_task(queue.run('flash', lambda i=i: call(f'capture-{i}'), 'recognition'))
                for i in range(5)]
    await drain_tasks()
    for _ in range(6):
        await clock.advance(60)
    await asyncio.gather(council, *captures)
    assert [label for label, _ in calls] == ['prime', 'capture-0', 'capture-1', 'capture-2',
                                          'council', 'capture-3', 'capture-4']
    assert [at for _, at in calls] == [100. + 60*i for i in range(7)]
    assert queue.status()['local_usage']['requests_last_24_hours'] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_capture', [False, True])
async def test_foreground_never_interrupts_active_call_and_cancellation_frees_priority(cancel_capture):
    clock = ManualClock(); queue = make_queue(clock)
    entered, release = asyncio.Event(), asyncio.Event(); calls = []
    async def active():
        calls.append(('active', clock.now)); entered.set(); await release.wait()
    async def call(label): calls.append((label, clock.now))
    active_task = asyncio.create_task(queue.run('argon', active, 'council'))
    await entered.wait()
    waiting = asyncio.create_task(queue.run('argon', lambda: call('next-council'), 'council'))
    capture = asyncio.create_task(queue.run('flash', lambda: call('capture'), 'recognition'))
    await drain_tasks(); await clock.advance(60)
    assert calls == [('active', 100.)] and queue.status()['active'] == 1
    assert not active_task.done()
    if cancel_capture:
        capture.cancel()
        with pytest.raises(asyncio.CancelledError): await capture
        assert queue.status()['scheduling']['waiting_foreground'] == 0
    release.set()
    await active_task
    await drain_tasks()
    if not cancel_capture:
        await capture
        assert calls == [('active', 100.), ('capture', 160.)]
        await clock.advance(60)
    await waiting
    expected = [('active', 100.), ('next-council', 160.)] if cancel_capture else [
        ('active', 100.), ('capture', 160.), ('next-council', 220.)]
    assert calls == expected
    assert queue.status()['local_usage']['requests_last_24_hours'] == len(expected)


@pytest.mark.asyncio
async def test_evaluation_recognition_can_explicitly_remain_background():
    clock = ManualClock(); queue = make_queue(clock)
    calls = []
    async def call(label): calls.append(label)
    await queue.run('argon', lambda: call('prime'), 'council')
    council = asyncio.create_task(queue.run('argon', lambda: call('council'), 'council'))
    evaluation = asyncio.create_task(queue.run('argon', lambda: call('evaluation'), 'recognition', priority='background'))
    capture = asyncio.create_task(queue.run('flash', lambda: call('capture'), 'recognition', priority='foreground'))
    await drain_tasks()
    for _ in range(3): await clock.advance(60)
    await asyncio.gather(council, evaluation, capture)
    assert calls == ['prime', 'capture', 'council', 'evaluation']
