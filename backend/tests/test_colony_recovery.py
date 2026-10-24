"""Crash, admission and validation recovery without paid requests or Atlas writes."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from app.colony_planner import ColonyPlanner, VALIDATION_BACKOFF_MAX_SECONDS
from app.provider_queue import ProviderDiagnostic, ProviderQueue
from app.repository import MemoryRepository, StoreError
from test_colony_planner import fixture


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['capability_denied', 'invalid_report_evidence', 'invalid_proposal_evidence'])
async def test_rejected_proposal_cools_one_island_and_keeps_other_councils_available(fixture, code):
    repo, colonies, provider, clock, worker = fixture
    def reject(*args):
        raise StoreError('Unproven proposal cannot execute.', 422, code)
    original = colonies.apply_decision
    colonies.apply_decision = reject
    for i in range(6):
        run = worker.request('bad-'+str(i), 'winners')
        await worker.run(run['id'])
        clock.add(3)
    state = worker.status()
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'rejected' and saved['validation_code'] == code
    assert not colonies.applied and 'receipt' not in saved
    assert not state['auto_blocked']
    assert state['validation_backoff']['winners']['failures'] == 6
    assert 0 < state['validation_backoff']['winners']['until']-clock() <= VALIDATION_BACKOFF_MAX_SECONDS
    colonies.apply_decision = original
    clock.add(worker.interval)
    other = worker.request('healthy-island', automatic=True)
    assert other['colony_id'] == 'losers'
    await worker.run(other['id'])
    assert len(colonies.applied) == 1
    clock.add(VALIDATION_BACKOFF_MAX_SECONDS)
    resumed = worker.request('cooled-island', 'winners', automatic=True)
    await worker.run(resumed['id'])
    assert 'winners' not in worker.status()['validation_backoff']


@pytest.mark.asyncio
async def test_daily_admission_defers_without_attempt_and_resumes_same_turn(fixture):
    repo, colonies, provider, clock, worker = fixture
    worker.queue = ProviderQueue(clock=clock, requests_per_day=1)
    first = worker.request('uses-cap', 'winners'); await worker.run(first['id'])
    clock.add(121)
    second = worker.request('waits-for-cap', 'losers'); await worker.run(second['id'])
    saved = repo._data['colonyReasoning'][second['id']]
    assert saved['status'] == 'retry_wait' and saved['attempts'] == 0
    assert saved['admission_deferrals'] == 1 and not worker.status()['auto_blocked']
    assert worker.status()['requests_today'] == 1 and len(provider.calls) == 1
    assert not any(e['kind'] == 'model.failed' for e in repo._data['agentEvents'].values())
    await worker.run(second['id']); assert len(provider.calls) == 1
    clock.add(saved['retry_at_epoch']-clock())
    await worker.run(second['id'])
    assert repo._data['colonyReasoning'][second['id']]['status'] == 'completed'
    assert len(provider.calls) == len(colonies.applied) == 2


@pytest.mark.asyncio
async def test_pending_queue_rejection_is_admission_deferral_without_provider_retry(fixture):
    repo, colonies, provider, clock, worker = fixture
    class FullQueue(ProviderQueue):
        async def run(self, *args, **kwargs):
            self._reject_local('local_queue_full', 'No request was sent.', 5)
    worker.queue = FullQueue(clock=clock)
    run = worker.request('queue-full', 'winners'); await worker.run(run['id'])
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'retry_wait' and saved['attempts'] == 0
    assert worker.status()['requests_today'] == 0 and not provider.calls
    assert not worker.status()['auto_blocked']
    clock.add(5); worker.queue = ProviderQueue(clock=clock)
    await worker.run(run['id'])
    assert len(provider.calls) == len(colonies.applied) == 1


async def restart_paused(repo, colonies, provider, clock, worker):
    clone = MemoryRepository(repo.settings)
    clone._data = deepcopy(repo._data)
    restarted = ColonyPlanner(clone, colonies, replace(worker.settings, ai_paused=True),
                              client=provider, clock=clock)
    await restarted.start(); await restarted.close()
    return clone, restarted


@pytest.mark.asyncio
async def test_waiting_for_slow_pace_survives_crash_and_graceful_stop_without_uncertainty(fixture):
    repo, colonies, provider, clock, worker = fixture
    waiting = asyncio.Event()
    async def sleep(_seconds):
        waiting.set(); await asyncio.Event().wait()
    queue = worker.queue = ProviderQueue(clock=clock, sleep=sleep)
    queue.set_pacing('slow')
    async def previous(): return None
    await queue.run('previous-fixture', previous)
    run = worker.request('queued-crash', 'winners')
    task = asyncio.create_task(worker.run(run['id'])); await waiting.wait()
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'queue_wait' and saved['attempts'] == 0
    assert worker.status()['requests_today'] == 0 and not provider.calls
    cloned, restarted = await restart_paused(repo, colonies, provider, clock, worker)
    assert cloned._data['colonyReasoning'][run['id']]['status'] == 'queued'
    assert not restarted.status()['auto_blocked']
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert repo._data['colonyReasoning'][run['id']]['status'] == 'queued'
    assert worker.status()['active_run']['id'] == run['id'] and not worker.status()['auto_blocked']
    worker.queue = ProviderQueue(clock=clock)
    await worker.run(run['id'])
    assert len(provider.calls) == len(colonies.applied) == 1


@pytest.mark.asyncio
async def test_dispatched_turn_stays_uncertain_on_crash_and_cancellation(fixture):
    repo, colonies, provider, clock, worker = fixture
    sent = asyncio.Event()
    async def stalled(**kwargs):
        provider.calls.append(kwargs); sent.set(); await asyncio.Event().wait()
    provider.aio.interactions.create = stalled
    run = worker.request('sent-crash', 'winners')
    task = asyncio.create_task(worker.run(run['id'])); await sent.wait()
    assert repo._data['colonyReasoning'][run['id']]['status'] == 'dispatching'
    cloned, restarted = await restart_paused(repo, colonies, provider, clock, worker)
    assert cloned._data['colonyReasoning'][run['id']]['status'] == 'uncertain'
    assert restarted.status()['auto_blocked']
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert repo._data['colonyReasoning'][run['id']]['status'] == 'uncertain'
    assert worker.status()['auto_blocked'] and len(provider.calls) == 1 and not colonies.applied


@pytest.mark.asyncio
@pytest.mark.parametrize('valid', [True, False])
async def test_saved_response_recovery_never_buys_another_response(fixture, valid):
    repo, colonies, provider, clock, worker = fixture
    run = worker.request('response-crash', 'winners')
    def seed(tx):
        row = tx.get('colonyReasoning', run['id'])
        row.update(status='response_received', received_at='2026-10-24T10:00:00+00:00',
                   proposal_text=json.dumps({'action': 'carry', 'reason': 'Use saved response.'}) if valid else '{}')
        tx.put('colonyReasoning', row)
    repo.transaction(seed)
    worker._interrupted(run['id'])
    assert repo._data['colonyReasoning'][run['id']]['status'] == 'response_received'
    await worker.run(run['id'])
    assert not provider.calls
    assert repo._data['colonyReasoning'][run['id']]['status'] == ('completed' if valid else 'rejected')
    assert not worker.status()['auto_blocked']
    assert len(colonies.applied) == int(valid)


@pytest.mark.asyncio
@pytest.mark.parametrize('category', ['local_daily_cap', 'invalid_report_evidence', 'unknown_outcome'])
async def test_restart_migrates_only_proven_recoverable_legacy_blocks(fixture, category):
    repo, colonies, provider, clock, worker = fixture
    run = worker.request('old-block', 'winners')
    message = 'Old known failure.'
    def seed(tx):
        row = tx.get('colonyReasoning', run['id'])
        row.update(status='rejected' if category == 'invalid_report_evidence' else 'failed',
                   error=message, completed_at=row['created_at'])
        if category == 'invalid_report_evidence': row['validation_code'] = category
        else: row['provider_diagnostic'] = ProviderDiagnostic(category, message, retry_after_seconds=5).public()
        state = worker._state(tx, True)
        state.update(pending_run_id=None, active_session_id=None, auto_blocked=True, error=message)
        session = tx.get('colonyCouncilSessions', run['session_id']); session['status'] = row['status']
        tx.put('colonyReasoning', row); tx.put('colonyPlanner', state); tx.put('colonyCouncilSessions', session)
    repo.transaction(seed)
    _, restarted = await restart_paused(repo, colonies, provider, clock, worker)
    assert restarted.status()['auto_blocked'] == (category == 'unknown_outcome')
    if category == 'local_daily_cap': assert restarted.status()['active_run']['status'] == 'retry_wait'
    if category == 'invalid_report_evidence': assert restarted.status()['validation_backoff']['winners']
    assert not provider.calls and not colonies.applied
