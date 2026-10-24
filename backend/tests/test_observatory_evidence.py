"""Durable contribution evidence, including missing and historical provenance."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.observability import Observatory, record_event, register_observatory_routes
from app.observatory_evidence import ReceiptEvidence
from app.repository import MemoryRepository, StoreError, key_for

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def fixture():
    repo = MemoryRepository(Settings(repository='memory', world_id='evidence-fixture'))
    scope = key_for(repo.world_id, 'colony-world', 'winners')[:32]
    actor_id = key_for(scope, 'island-agent', 'mug')
    repo.transaction(lambda tx: tx.put('islandAgents', {'_id': actor_id, 'id': actor_id,
        'world_id': scope, 'character_id': 'mug', 'display_name': 'Ceramic Mug'}))
    return repo, scope, actor_id


def add_receipt(repo, scope, actor, identifier='receipt-1', **changes):
    row = {'_id': identifier, 'id': identifier, 'world_id': scope, 'sequence': 1,
           'character_id': 'mug', 'actor_id': actor, 'actor_name': 'Ceramic Mug',
           'at': (NOW - timedelta(minutes=1)).isoformat(), 'kind': 'water', 'action_id': 'water',
           'resource_delta': {'water': 3}, 'reserved_cost': {'energy': 1}, 'progress_delta': 0,
           'receipt_version': 'island-action-v2', 'reservation_evidence': 'recorded',
           'execution_origin': 'local_executor', 'decision_origin': 'deterministic',
           'decision_id': None, **changes}
    repo.transaction(lambda tx: tx.put('islandEvents', row))
    return row


def add_event(repo, actor, identifier='event-1', kind='task.completed', **data):
    return repo.transaction(lambda tx: record_event(tx, repo.world_id, event_id=identifier,
        kind=kind, island_id='winners', actor_id=actor, data=data, at=NOW.isoformat()))


def add_lineage(repo, scope, actor, receipt, *, valid=True):
    receipt.update(decision_origin='model', decision_id='decision')
    def put(tx):
        tx.put('islandEvents', receipt)
        tx.put('colonyDecisions', {'_id': 'decision', 'id': 'decision', 'world_id': scope,
            'actor_id': actor, 'character_id': 'mug', 'status': 'accepted', 'run_id': 'run',
            'decision': {'action': 'water'}})
        tx.put('colonyReasoning', {'_id': 'run', 'id': 'run', 'world_id': repo.world_id,
            'colony_id': 'winners', 'agent_id': actor, 'status': 'completed', 'model': 'fixture-model',
            'received_at': NOW.isoformat(), 'receipt': {'id': 'decision'}, 'session_id': 'session'})
        tx.put('colonyCouncilSessions', {'_id': 'session', 'id': 'session', 'world_id': repo.world_id,
            'colony_id': 'winners', 'run_ids': ['run'], 'participants': [{'id': actor if valid else 'other'}]})
    repo.transaction(put)


def test_event_resolves_actual_receipt_and_null_decision_does_not_mean_missing_receipt():
    repo, scope, actor = fixture()
    row = add_receipt(repo, scope, actor)
    event = add_event(repo, actor, receipt_id=row['id'])
    before = deepcopy(repo._data)
    result = ReceiptEvidence(repo).event_evidence(event['id'])
    assert result['status'] == 'verified'
    receipt = result['receipts'][0]
    assert receipt['decision_id'] is None and receipt['id'] == row['id']
    assert receipt['resource_delta'] == {'water': 3} and receipt['resource_cost'] == {'energy': 1}
    assert receipt['provenance']['attribution'] == 'executor'
    assert repo._data == before


def test_proposal_is_not_applicable_while_missing_report_or_receipt_is_explicit():
    repo, scope, actor = fixture()
    proposal = add_event(repo, actor, 'proposal', 'board.message', message_id='proposal-board')
    repo.transaction(lambda tx: tx.put('colonyBoard', {'_id': 'proposal-board', 'id': 'proposal-board',
        'world_id': scope, 'actor_id': actor, 'kind': 'proposal', 'receipt_ids': [], 'origin': 'model'}))
    evidence = ReceiptEvidence(repo)
    assert evidence.event_evidence(proposal['id'])['status'] == 'not_applicable'
    absent = add_event(repo, actor, 'absent', receipt_id='missing')
    assert evidence.event_evidence(absent['id'])['missing_receipt_ids'] == ['missing']
    no_id = add_event(repo, actor, 'no-id')
    assert evidence.event_evidence(no_id['id'])['status'] == 'missing'
    provider = add_event(repo, actor, 'provider', 'model.completed')
    assert evidence.event_evidence(provider['id'])['status'] == 'not_applicable'


def test_board_report_resolves_deduplicated_evidence_and_never_crosses_world_or_actor():
    repo, scope, actor = fixture()
    row = add_receipt(repo, scope, actor)
    repo.transaction(lambda tx: tx.put('colonyBoard', {'_id': 'report', 'id': 'report', 'world_id': scope,
        'actor_id': actor, 'kind': 'report', 'receipt_ids': [row['id'], row['id']]}))
    event = add_event(repo, actor, kind='board.message', message_id='report', receipt_id=row['id'])
    evidence = ReceiptEvidence(repo)
    assert len(evidence.event_evidence(event['id'])['receipts']) == 1
    foreign = add_receipt(repo, 'foreign-world', actor, identifier='foreign')
    foreign_event = add_event(repo, actor, 'foreign-link', receipt_id=foreign['id'])
    assert evidence.event_evidence(foreign_event['id'])['status'] == 'missing'
    with pytest.raises(StoreError) as error:
        evidence.receipt_evidence(foreign['id'])
    assert error.value.status == 404
    wrong_actor = add_event(repo, 'another-actor', 'wrong-actor', receipt_id=row['id'])
    assert evidence.event_evidence(wrong_actor['id'])['status'] == 'missing'
    other_world_event = repo.transaction(lambda tx: record_event(tx, 'foreign', event_id='foreign', kind='task.completed'))
    with pytest.raises(StoreError):
        evidence.event_evidence(other_world_event['id'])


def test_historical_effects_are_readable_without_fabricating_costs_or_snapshots():
    repo, scope, actor = fixture()
    row = add_receipt(repo, scope, actor)
    for field in ('receipt_version', 'reserved_cost', 'reservation_evidence', 'actor_name', 'actor_id', 'decision_origin'):
        row.pop(field)
    repo.transaction(lambda tx: tx.put('islandEvents', row))
    result = ReceiptEvidence(repo).receipt_evidence(row['id'])
    assert result['status'] == 'historical'
    saved = result['receipts'][0]
    assert saved['resource_delta'] == {'water': 3} and saved['resource_cost'] is None
    assert 'resources_before' not in saved
    assert saved['actor_id'] == actor and saved['provenance']['attribution'] == 'unattributed'
    total = ReceiptEvidence(repo).contributions(now=NOW)
    winner = total['islands'][0]
    assert winner['historical_actions'] == 1 and not winner['costs_complete']
    assert winner['resource_costs'] == {} and winner['unattributed_actions'] == 1


def test_model_contribution_requires_real_provider_decision_and_session_lineage():
    repo, scope, actor = fixture()
    row = add_receipt(repo, scope, actor)
    add_lineage(repo, scope, actor, row)
    evidence = ReceiptEvidence(repo)
    assert evidence.receipt_evidence(row['id'])['receipts'][0]['provenance']['attribution'] == 'model'
    assert evidence.contributions(now=NOW)['islands'][0]['model_actions'] == 1
    repo._data['colonyCouncilSessions']['session']['participants'] = [{'id': 'someone-else'}]
    result = evidence.receipt_evidence(row['id'])['receipts'][0]
    assert result['provenance_status'] == 'missing'
    assert evidence.contributions(now=NOW)['islands'][0]['unattributed_actions'] == 1
    # A valid origin string cannot rescue a mismatched decision owner.
    repo._data['colonyDecisions']['decision']['actor_id'] = 'foreign-actor'
    assert evidence.receipt_evidence(row['id'])['receipts'][0]['provenance']['attribution'] == 'unattributed'


def test_contribution_window_counts_only_actions_costs_work_and_latest_receipt(monkeypatch):
    import app.observatory_evidence as module
    repo, scope, actor = fixture()
    add_receipt(repo, scope, actor, identifier='first', progress_delta=4, at=(NOW - timedelta(minutes=2)).isoformat())
    add_receipt(repo, scope, actor, identifier='latest', resource_delta={'wood': 2}, reserved_cost={}, progress_delta=1)
    add_receipt(repo, scope, actor, identifier='outside', at=(NOW - timedelta(hours=2)).isoformat())
    repo.transaction(lambda tx: tx.put('islandEvents', {'_id': 'milestone', 'world_id': scope, 'kind': 'milestone',
        'at': NOW.isoformat(), 'resource_delta': {'water': 100}, 'progress_delta': 999}))
    total = ReceiptEvidence(repo).contributions(window=60, now=NOW)
    assert total['receipt_count'] == 2 and not total['sampled']
    colony = total['islands'][0]
    assert colony['resource_gains'] == {'water': 3, 'wood': 2}
    assert colony['resource_costs'] == {'energy': 1} and colony['project_work'] == 5
    assert colony['actors'][0]['last_receipt_id'] == 'latest'
    assert colony['actors'][0]['executor_actions'] == 2
    assert colony['productive_actions'] == 2 and colony['no_gain_actions'] == 0
    assert colony['actors'][0]['productive_actions'] == 2
    assert total['islands'][1]['actions'] == 0
    monkeypatch.setattr(module, 'PER_ISLAND_RECEIPT_LIMIT', 1)
    limited = ReceiptEvidence(repo).contributions(window=99999, now=NOW)
    assert limited['window_minutes'] == 1440 and limited['sampled']
    assert limited['receipt_count'] == 1 and limited['receipt_sample_limit'] == 2
    with pytest.raises(StoreError):
        ReceiptEvidence(repo).contributions(island_id='foreign', now=NOW)


@pytest.mark.asyncio
async def test_read_only_evidence_routes_and_sanitized_receipt_fields():
    repo, scope, actor = fixture()
    receipt = add_receipt(repo, scope, actor, description='API key AIza' + 'x' * 30)
    event = add_event(repo, actor, receipt_id=receipt['id'])
    app = FastAPI()
    app.state.observatory = Observatory(repo)
    register_observatory_routes(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        event_result = await client.get('/api/observatory/events/' + event['id'] + '/evidence')
        assert event_result.status_code == 200 and event_result.json()['status'] == 'verified'
        assert 'AIza' not in event_result.text
        saved = await client.get('/api/observatory/receipts/' + receipt['id'] + '/evidence')
        assert saved.status_code == 200 and saved.json()['receipts'][0]['id'] == receipt['id']
        assert (await client.get('/api/observatory/contributions')).status_code == 200
    assert len(repo._data['islandEvents']) == 1 and len(repo._data['agentEvents']) == 1


@pytest.mark.asyncio
async def test_full_v2_receipt_api_preserves_provenance_and_schema_without_relaxing_redaction():
    from backend.tests.test_colonies import Clock, battle
    from app.colonies import ColoniesStore
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='full-receipt-api-fixture'), clock)
    battle(repo, 'full-receipt-battle', 'pencil', 'mug')
    colony = ColoniesStore(repo)
    colony.initialize()
    clock.advance(20)
    colony.advance()
    event = next(row for row in Observatory(repo).events()['events'] if row['kind'] == 'task.completed')
    receipt_id = event['data']['receipt_id']
    def inject_untrusted_diagnostics(tx):
        receipt = tx.get('islandEvents', receipt_id)
        receipt['description'] = 'Observed key AIza' + 'x' * 30 + ' ' + 'detail ' * 1000
        receipt['api_key'] = 'TOP_LEVEL_PRIVATE'
        receipt['capability_basis'].update(api_key='NESTED_PRIVATE',
                details=list(range(100)), nested={'a': {'b': {'c': {'d': {'e': {'f': 'too deep'}}}}}})
        tx.put('islandEvents', receipt)
    repo.transaction(inject_untrusted_diagnostics)
    expected = ReceiptEvidence(repo).receipt_evidence(receipt_id)['receipts'][0]
    assert len(expected) > 40  # Regression: the generic telemetry serializer truncated here.
    before = deepcopy(repo._data)
    app = FastAPI()
    app.state.observatory = Observatory(repo)
    register_observatory_routes(app)
    paths = [f'/api/observatory/receipts/{receipt_id}/evidence',
             f'/api/observatory/events/{event["id"]}/evidence']
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for path in paths:
            response = await client.get(path)
            assert response.status_code == 200
            saved = response.json()['receipts'][0]
            assert set(saved) == set(expected)
            assert saved['provenance'] == expected['provenance']
            assert saved['provenance']['reason'] and saved['provenance_status'] == 'verified'
            assert saved['status'] == 'verified' and saved['committed'] is True
            assert saved['decision_id'] is None and saved['scheduling_reason'] == expected['scheduling_reason']
            assert saved['resources_after'] == expected['resources_after']
            assert saved['resource_delta'] == expected['resource_delta']
            assert len(saved['description']) == 1600 and len(saved['capability_basis']['details']) == 30
            assert '[depth limited]' in response.text
            assert 'AIza' not in response.text and 'PRIVATE' not in response.text and 'api_key' not in response.text
    assert repo._data == before


def test_actual_colony_completion_resolves_new_snapshots_and_matching_contributions():
    from backend.tests.test_colonies import Clock, battle
    from app.colonies import ColoniesStore
    from app.island import ACTION_LABELS
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='real-receipt-fixture'), clock)
    battle(repo, 'evidence-battle', 'mug', 'pencil')
    colony = ColoniesStore(repo)
    colony.initialize()
    clock.advance(35)
    colony.advance()
    evidence = ReceiptEvidence(repo)
    completed = [row for row in Observatory(repo).events()['events'] if row['kind'] == 'task.completed']
    assert completed
    counts = {'winners': 0, 'losers': 0}
    gains = {'winners': {}, 'losers': {}}
    for event in completed:
        saved = evidence.event_evidence(event['id'])
        assert saved['status'] == 'verified'
        receipt = saved['receipts'][0]
        assert receipt['action'] in ACTION_LABELS
        assert receipt['action_id'] == receipt['id']
        assert receipt['provenance']['attribution'] == 'executor'
        for key, value in receipt['resource_delta'].items():
            assert receipt['resources_after'][key] - receipt['resources_before'][key] == value
            gains[event['island_id']][key] = gains[event['island_id']].get(key, 0) + value
        counts[event['island_id']] += 1
    totals = evidence.contributions(now=clock.value)
    assert totals['receipt_count'] == len(completed)
    for island in totals['islands']:
        assert island['actions'] == counts[island['id']]
        assert island['resource_gains'] == gains[island['id']]
        assert island['model_actions'] == 0


def test_productive_actions_require_actual_stock_or_work_gain_not_completion_or_xp():
    repo, scope, actor = fixture()
    add_receipt(repo, scope, actor, identifier='full-storage', resource_delta={'materials': 0},
                reserved_cost={}, progress_delta=0, xp_gain=4)
    add_receipt(repo, scope, actor, identifier='rest', kind='rest', resource_delta={},
                reserved_cost={}, progress_delta=0, xp_gain=0)
    add_receipt(repo, scope, actor, identifier='construction', kind='build', resource_delta={},
                reserved_cost={'materials': 2}, progress_delta=3, xp_gain=4)
    add_receipt(repo, scope, actor, identifier='water', resource_delta={'water': 1},
                reserved_cost={}, progress_delta=0)
    summary = ReceiptEvidence(repo).contributions(now=NOW)
    island = summary['islands'][0]
    for total in (island, island['actors'][0]):
        assert total['actions'] == 4
        assert total['productive_actions'] == 2 and total['no_gain_actions'] == 2
        assert total['productive_actions'] + total['no_gain_actions'] == total['actions']
        assert total['resource_gains'] == {'materials': 0, 'water': 1}
        assert total['project_work'] == 3
    assert summary['islands'][1]['productive_actions'] == summary['islands'][1]['no_gain_actions'] == 0
    assert 'XP' in summary['productivity_basis']
