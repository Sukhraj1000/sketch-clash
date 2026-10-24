"""Report presentation regressions: fake model output, real isolated executor receipts."""
from copy import deepcopy

import pytest

from app.observability import Observatory
from test_colony_integration import colony, actor


async def accepted_report(fixture):
    repo, store, provider, clock, worker = fixture
    clock.advance(20)
    store.advance()
    resident = actor(store, 'winners', 'bottle')
    receipt = next(row for row in repo._data['islandEvents'].values()
                   if row.get('sequence') and row.get('character_id') == resident['character_id'])
    provider.decision = {'message': {'kind': 'report', 'receipt_id': receipt['id'],
                                    'text': 'I generated 999 energy.'}}
    run = worker.request('contradictory-report', 'winners', resident['id'])
    await worker.run(run['id'])
    saved = repo._data['colonyReasoning'][run['id']]
    assert saved['status'] == 'completed'
    board = repo._data['colonyBoard'][saved['receipt']['board_ids'][0]]
    events = [row for row in repo._data['agentEvents'].values()
              if (row.get('data') or {}).get('message_id') == board['id']]
    return repo, worker, saved, board, receipt, events


@pytest.mark.asyncio
async def test_report_event_and_council_use_facts_with_commentary_explicitly_unverified(colony):
    repo, worker, run, board, receipt, events = await accepted_report(colony)
    assert board['text'] == receipt['description']
    assert board['interpretation'] == 'I generated 999 energy.'
    assert receipt['resource_delta'].get('energy', 0) == 0
    assert {event['kind'] for event in events} == {'board.message', 'agent.message'}
    for event in events:
        assert event['message'] == receipt['description']
        assert event['data']['unverified_model_commentary'] == board['interpretation']
    session = repo._data['colonyCouncilSessions'][run['session_id']]
    assert session['messages'][0]['text'] == receipt['description']
    assert session['messages'][0]['content_basis'] == 'validated_receipt'
    assert len(colony[2].calls) == 1


@pytest.mark.asyncio
async def test_historical_event_projection_and_stream_backfill_do_not_rewrite_records(colony):
    repo, _, _, board, receipt, events = await accepted_report(colony)
    # Old builds published interpretation as the apparent verified report text.
    for event in events:
        event['message'] = board['interpretation']
        event['data'].pop('unverified_model_commentary', None)
        event['data'].pop('message_kind', None)
    before = deepcopy(repo._data)
    obs = Observatory(repo)
    projected = [row for row in obs.events()['events'] if row['id'] in {event['id'] for event in events}]
    assert len(projected) == 2
    for row in projected:
        assert row['message'] == receipt['description']
        assert row['data']['report_text_basis'] == 'executor_receipt'
        assert row['data']['unverified_model_commentary'] == board['interpretation']
    class Request:
        async def is_disconnected(self):
            return False
    stream = obs.subscribe(Request(), events[0]['sequence'] - 1, 'winners')
    item = await anext(stream)
    assert receipt['description'] in item
    assert 'unverified_model_commentary' in item
    await stream.aclose()
    assert repo._data == before


@pytest.mark.asyncio
async def test_historical_report_cannot_borrow_missing_or_foreign_evidence(colony):
    repo, _, _, board, receipt, events = await accepted_report(colony)
    foreign = next(row for row in repo._data['islandEvents'].values()
                   if row.get('sequence') and row.get('world_id') != receipt['world_id'])
    for refs in (['missing-receipt'], [foreign['id']]):
        board['receipt_ids'] = refs
        before = deepcopy(repo._data)
        rows = [row for row in Observatory(repo).events()['events'] if row['id'] in {event['id'] for event in events}]
        for row in rows:
            assert row['data']['report_text_basis'] == 'evidence_unavailable'
            assert row['message'] == 'Report evidence unavailable. No contribution can be verified from this event.'
            assert foreign['description'] not in row['message']
        assert repo._data == before
