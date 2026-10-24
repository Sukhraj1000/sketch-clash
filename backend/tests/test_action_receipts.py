"""Receipts describe committed executor effects, not invented discoveries or AI claims."""
from copy import deepcopy

import pytest

from app.colonies import ColoniesStore
from app.config import Settings
from app.island import MAX_RESOURCE, RESOURCE_KEYS
from app.repository import MemoryRepository
from backend.tests.test_colonies import Clock, actor, battle, command


def setup_colony():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='receipt-fixture'), clock)
    battle(repo, 'one', 'pencil', 'phone')
    battle(repo, 'two', 'bottle', 'box')
    battle(repo, 'three', 'mug', 'battery')
    store = ColoniesStore(repo)
    store.initialize()
    return repo, store, clock


def receipts(repo):
    return [row for row in repo._data.get('islandEvents', {}).values() if 'sequence' in row]


def test_completed_actions_have_atomic_links_and_reconcilable_stock_and_project_evidence():
    repo, store, clock = setup_colony()
    clock.advance(120)
    store.advance()
    rows = receipts(repo)
    assert rows and any(row['reserved_cost'] for row in rows)
    completions = [event for event in repo._data['agentEvents'].values() if event['kind'] == 'task.completed']
    assert len(completions) == len(rows)
    assert {event['data']['receipt_id'] for event in completions} == {row['id'] for row in rows}
    for receipt in rows:
        assert receipt['receipt_version'] == 'island-action-v2'
        assert receipt['execution_origin'] == 'local_executor'
        assert receipt['decision_origin'] == 'deterministic'
        assert receipt['decision_id'] is None
        assert receipt['decision_evidence'] == 'not_applicable'
        assert receipt['reservation_evidence'] == 'recorded'
        assert receipt['capability_basis']['allowed_action']
        for resource in RESOURCE_KEYS:
            assert receipt['resources_after'][resource] - receipt['resources_before'][resource] == receipt['resource_delta'].get(resource, 0)
            assert receipt['resources_before_reservation'][resource] - receipt['resources_after_reservation'][resource] == receipt['reserved_cost'].get(resource, 0)
            assert receipt['resource_net_delta'].get(resource, 0) == receipt['resource_delta'].get(resource, 0) - receipt['reserved_cost'].get(resource, 0)
        if receipt['project_before']:
            before, after = receipt['project_before'], receipt['project_after']
            assert after['reserved_progress'] == before['reserved_progress'] - receipt['progress_delta']
            if after['level'] == before['level']:
                assert after['progress'] - before['progress'] == receipt['progress_delta']
            else:
                assert after['level'] == before['level'] + 1 and after['progress'] == 0
                assert before['progress'] + receipt['progress_delta'] == before['required_progress']
        event = next(event for event in completions if event['data']['receipt_id'] == receipt['id'])
        assert event['actor_id'] == receipt['actor_id']
        assert event['created_at'] == receipt['at']
        assert event['data']['execution_origin'] == 'local_executor'
        assert event['data']['resource_delta'] == receipt['resource_delta']
    before = deepcopy(repo._data)
    store.advance()
    assert repo._data == before


def test_exploration_describes_actual_yield_and_zero_at_capacity_without_invented_discoveries():
    repo, store, clock = setup_colony()
    pencil = actor(store, 'pencil')
    command(store, 'assign', 'explore-with-evidence', character_id=pencil['character_id'], assignment='explore')
    clock.advance(40)
    store.advance()
    surveys = [row for row in receipts(repo) if row['kind'] == 'explore' and row['character_id'] == pencil['character_id']]
    assert surveys
    for row in surveys:
        assert row['decision_origin'] == 'player'
        assert row['resource_delta']['materials'] > 0
        assert f"{row['resource_delta']['materials']} materials" in row['description']
        assert 'found ' not in row['description'] and 'pebble' not in row['description']

    island = store.islands['winners']
    def fill(tx):
        state = tx.get('islandState', island.state_id)
        state['resources']['materials'] = MAX_RESOURCE
        tx.put('islandState', state)
        for agent in island._agents(tx):
            agent['assignment'] = 'explore'
            agent['assignment_origin'] = 'player'
            tx.put('islandAgents', agent)
    repo.transaction(fill)
    clock.advance(20)
    store.advance()
    capped = [row for row in receipts(repo) if row['kind'] == 'explore' and row['resource_delta'].get('materials') == 0]
    assert capped and all('full storage prevented a resource gain' in row['description'] for row in capped)
    state = repo._data['islandState'][island.state_id]
    for survey in state['discoveries']:
        receipt = repo._data['islandEvents'][survey['receipt_id']]
        assert survey['resource_delta'] == receipt['resource_delta']
        assert survey['origin'] == 'local_executor'


def test_failure_after_action_receipt_rolls_back_effects_and_completion_event(monkeypatch):
    import app.colonies as module
    repo, store, clock = setup_colony()
    original = module.record_event
    def fail_completion(*args, **kwargs):
        if kwargs['kind'] == 'task.completed':
            raise RuntimeError('controlled event-write failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(module, 'record_event', fail_completion)
    clock.advance(20)
    before = deepcopy(repo._data)
    with pytest.raises(RuntimeError, match='controlled event-write failure'):
        store.advance()
    assert repo._data == before
    monkeypatch.setattr(module, 'record_event', original)
    store.advance()
    assert receipts(repo)


def test_inflight_legacy_tasks_keep_history_and_mark_unavailable_reservation_evidence():
    repo, store, clock = setup_colony()
    pencil = actor(store, 'pencil')
    task_id = pencil['task']['id']
    old = {'_id': 'old-exploration', 'id': 'old-exploration', 'world_id': pencil['world_id'],
           'kind': 'explore', 'description': 'Graphite Dart found a smooth pebble trail and brought back supplies.',
           'at': clock(), 'character_id': pencil['character_id']}
    def legacy(tx):
        agent = tx.get('islandAgents', pencil['id'])
        for name in ('resources_before_reservation', 'resources_after_reservation', 'capability_basis'):
            agent['task'].pop(name, None)
        tx.put('islandAgents', agent)
        tx.put('islandEvents', old)
    repo.transaction(legacy)
    clock.advance(20)
    store.advance()
    row = repo._data['islandEvents'][task_id]
    assert row['reservation_evidence'] == 'legacy_task'
    assert row['resources_before_reservation'] is None and row['resources_after_reservation'] is None
    assert row['capability_basis'] is None
    assert repo._data['islandEvents']['old-exploration'] == old
    assert row['resources_before'] and row['resources_after']


def test_accepted_decision_links_work_without_claiming_a_google_provider_call():
    repo, store, clock = setup_colony()
    pencil = actor(store, 'pencil')
    accepted = store.apply_decision('winners', pencil['id'], {'action': 'plan', 'reason': 'Fixture decision'}, 'controlled-fixture-run')['decision']
    clock.advance(40)
    store.advance()
    modeled = [row for row in receipts(repo) if row.get('decision_id') == accepted['id']]
    assert modeled
    assert all(row['decision_origin'] == 'model' and row['execution_origin'] == 'local_executor' for row in modeled)
    assert all(row['decision_run_id'] == 'controlled-fixture-run' and row['decision_evidence'] == 'accepted_decision' for row in modeled)
    assert all('model' not in row and 'provider' not in row for row in modeled)
    assert repo._data.get('colonyReasoning', {}) == {}
    report = store.apply_decision('winners', pencil['id'],
        {'message': {'kind': 'report', 'receipt_id': modeled[0]['id']}}, 'fixture-report')['decision']
    publication = next(event for event in repo._data['agentEvents'].values()
                       if event['kind'] == 'board.message' and event['data']['message_id'] == report['board_ids'][0])
    assert publication['data']['receipt_ids'] == [modeled[0]['id']]
    assert publication['data']['evidence_kind'] == 'execution_report'
