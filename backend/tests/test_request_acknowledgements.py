"""Repeated needs share a work item, never overwrite a different speaker's history."""
from copy import deepcopy

import pytest

from test_colony_integration import colony, actor, completed_battle


@pytest.mark.asyncio
async def test_repeated_request_preserves_both_real_turns_and_shared_work_idempotently(colony):
    repo, store, provider, clock, worker = colony
    completed_battle(repo, 'second-resident', 'pencil', 'mug')
    store.initialize()
    bottle = actor(store, 'winners', 'bottle')
    pencil = actor(store, 'winners', 'pencil')
    provider.decision = {'message': {'kind': 'request', 'resource': 'water', 'quantity': 2,
                                    'project_id': 'garden', 'text': 'I need water for the garden.'}}
    first = worker.request('shared-garden-water', 'winners', bottle['id'])
    await worker.run(first['id'])
    first_run = deepcopy(repo._data['colonyReasoning'][first['id']])
    request_id = first_run['receipt']['board_ids'][0]
    original_request = deepcopy(repo._data['colonyBoard'][request_id])
    assert original_request['actor_id'] == bottle['id']
    second_id = worker.status()['active_run']['id']
    assert repo._data['colonyReasoning'][second_id]['agent_id'] == pencil['id']
    provider.decision['message']['text'] = 'I also need water; keep the shared garden request.'
    await worker.run(second_id)
    second_run = repo._data['colonyReasoning'][second_id]
    assert second_run['status'] == 'completed'
    acknowledgement = repo._data['colonyBoard'][second_run['receipt']['board_ids'][0]]
    assert acknowledgement['id'] != request_id
    assert acknowledgement['actor_id'] == pencil['id']
    assert acknowledgement['run_id'] == second_id
    assert acknowledgement['request_id'] == request_id
    assert acknowledgement['kind'] == 'reflection'
    assert acknowledgement['request_reused'] is True
    assert 'No new request, offer or delivery' in acknowledgement['effect']
    assert not acknowledgement['receipt_ids']
    assert repo._data['colonyBoard'][request_id] == original_request
    requests = [row for row in repo._data['colonyBoard'].values()
                if row['kind'] == 'request' and row['resource'] == 'water' and row.get('project_id') == 'garden']
    assert len(requests) == 1
    session = repo._data['colonyCouncilSessions'][first['session_id']]
    assert [row['actor_id'] for row in session['messages']] == [bottle['id'], pencil['id']]
    assert session['messages'][1]['text'] == provider.decision['message']['text']
    assert session['messages'][1]['request_id'] == request_id
    assert session['messages'][1]['reply_to_id'] == request_id
    assert session['messages'][1]['id'] == acknowledgement['id']
    event = next(row for row in repo._data['agentEvents'].values()
                 if row['kind'] == 'agent.message' and row['data'].get('message_id') == acknowledgement['id'])
    assert event['actor_id'] == pencil['id'] and event['data']['run_id'] == second_id
    before = deepcopy(repo._data)
    provenance = {key: second_run.get(key) for key in ('session_id', 'reply_to_id', 'seen_message_ids', 'model', 'turn_index', 'trace_id', 'span_id')}
    replay = store.apply_decision('winners', pencil['id'], second_run['decision'], second_id, provenance)
    assert replay['message_id'] == acknowledgement['id']
    await worker.run(second_id)
    assert repo._data == before and len(provider.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('historical_origin', ['model', 'deterministic'])
async def test_new_session_keeps_existing_request_and_older_transcript_unchanged(colony, historical_origin):
    repo, store, provider, clock, worker = colony
    resident = actor(store, 'winners', 'bottle')
    provider.decision = {'message': {'kind': 'request', 'resource': 'water', 'quantity': 2,
                                    'project_id': 'garden', 'text': 'The garden needs water.'}}
    first = worker.request('older-request-session', 'winners', resident['id'])
    await worker.run(first['id'])
    original = repo._data['colonyBoard'][repo._data['colonyReasoning'][first['id']]['receipt']['board_ids'][0]]
    # Historical rule-created requests may still be open after enabling model councils.
    original['origin'] = historical_origin
    saved_request = deepcopy(original)
    saved_session = deepcopy(repo._data['colonyCouncilSessions'][first['session_id']])
    clock.advance(3)
    provider.decision['message']['text'] = 'The existing water request is still relevant.'
    second = worker.request('new-request-session', 'winners', resident['id'])
    await worker.run(second['id'])
    current = repo._data['colonyCouncilSessions'][second['session_id']]
    assert second['session_id'] != first['session_id']
    assert current['messages'][0]['text'] == 'The existing water request is still relevant.'
    assert current['messages'][0]['request_id'] == original['id']
    assert current['messages'][0]['id'] != original['id']
    assert repo._data['colonyBoard'][original['id']] == saved_request
    assert repo._data['colonyCouncilSessions'][first['session_id']] == saved_session
    assert len(provider.calls) == 2
