import json
from dataclasses import replace
from types import SimpleNamespace
import pytest

from test_colony_planner import fixture
from test_colony_recovery import restart_paused


@pytest.mark.asyncio
async def test_long_hypothesis_repaired_once_in_same_council_with_normal_admission(fixture):
    repo, colonies, provider, clock, worker = fixture
    async def respond(**kwargs):
        provider.calls.append(kwargs)
        value = {'action': 'rest', 'reason': 'State the limitation briefly.'}
        if len(provider.calls) == 1:
            value['experiment'] = {'family': 'hold', 'subject_ids': ['winners-character'],
                'hypothesis': 'A' * 401, 'expected_success': True}
        return SimpleNamespace(output_text=json.dumps(value), model_dump=lambda **kw: {'usage': {'total_tokens': 10}})
    provider.aio.interactions.create = respond
    run = worker.request('long-hypothesis', 'winners')
    await worker.run(run['id'])
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'queued' and not colonies.applied
    assert worker.status()['active_session_id'] == run['session_id']
    assert repo._data['colonyCouncilSessions'][run['session_id']]['completed_turns'] == 0
    before = clock()
    await worker.run(run['id'])
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'completed' and saved['attempts'] == 2
    assert worker.status()['requests_today'] == 2
    assert len(colonies.applied) == 1
    assert clock() > before, 'Normal queue spacing still applies to the correction'
    correction = json.loads(provider.calls[1]['input'])
    assert correction['response_repair']['errors'][0]['field'] == 'experiment.hypothesis'
    assert json.loads(saved['rejected_responses'][0]['proposal_text'])['experiment']['hypothesis'] == 'A' * 401


@pytest.mark.asyncio
async def test_non_text_schema_error_is_not_automatically_repaired(fixture):
    repo, colonies, provider, clock, worker = fixture
    async def invalid(**kwargs):
        provider.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps({'action': 'invent_energy', 'reason': 'x' * 601}),
                               model_dump=lambda **kw: {'usage': {}})
    provider.aio.interactions.create = invalid
    run = worker.request('invalid-capability-and-text', 'winners')
    await worker.run(run['id'])
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'rejected' and 'text_repair_count' not in saved
    assert len(provider.calls) == 1 and not colonies.applied


@pytest.mark.asyncio
async def test_restart_preserves_long_response_for_normal_bounded_repair(fixture):
    repo, colonies, provider, clock, worker = fixture
    run = worker.request('long-response-crash', 'winners')
    def seed(tx):
        row = tx.get('colonyReasoning', run['id'])
        row.update(status='response_received', received_at='2026-10-24T10:00:00+00:00',
                   proposal_text=json.dumps({'action': 'rest', 'reason': 'x' * 601}))
        tx.put('colonyReasoning', row)
    repo.transaction(seed)
    clone, restarted = await restart_paused(repo, colonies, provider, clock, worker)
    assert restarted.status()['active_session_id'] == run['session_id']
    restarted.settings = replace(restarted.settings, ai_paused=False)
    restarted.queue.paused = False
    await restarted.run(run['id'])
    saved = clone._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'queued' and saved['text_repair_count'] == 1
    assert saved['rejected_responses'][0]['proposal_text'] == json.dumps({'action': 'rest', 'reason': 'x' * 601})
    assert not provider.calls and not colonies.applied
