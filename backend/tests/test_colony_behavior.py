from copy import deepcopy

import pytest

from app.colony_behavior import behavior_summary
from app.colony_experiments import BENEFITS, RULE_VERSION
from app.colony_opportunities import work_opportunities
from app.repository import StoreError
from test_colony_opportunities import observation, project
from test_colony_planner import fixture


def colony(payload):
    return {'id': 'winners', 'island': {'agents': [payload['actor'], *payload['peers']],
            'resources': payload['resources'], 'projects': payload['projects']},
            'planning': payload['planning'], 'learning': payload['learning']}


def exhausted():
    payload = observation()
    project(payload, 'finished-hold', kind='assembly', level=1, benefit=BENEFITS['hold'])
    project(payload, 'finished-support', kind='assembly', level=1, benefit=BENEFITS['support'])
    project(payload, 'beacon', feasible=False, required={'energy': 2})
    return payload


def test_exhausted_world_reports_real_gap_without_changing_stock_or_granting_energy():
    payload = exhausted()
    value = colony(payload)
    before = deepcopy(value)
    output = behavior_summary(value)
    assert output['status'] == 'waiting_for_change'
    assert output['missing_capabilities'] == ['energy']
    assert output['research_options'] == []
    assert value == before
    assert 'current evidence window' in output['reason']


def test_declared_container_opens_useful_research_not_instant_completed_work():
    payload = exhausted()
    payload['actor']['allowed_actions'].append('water')
    dossier = payload['learning']['dossiers'][0]
    dossier['simulation_properties'].update(apparent_cavity=None, cavity_model={
        'status': 'declared_simulation_cavity', 'authority': 'declared_game_capability'})
    output = behavior_summary(colony(payload))
    assert output['status'] == 'research_available'
    assert output['research_options'][0]['family'] == 'contain'
    assert output['research_options'][0]['evidence_basis'] == 'declared_game_capability'
    assert not output['funded_project_ids']
    # Observed absence, unknown and conflicting evidence cannot become positive
    # merely because a water task exists in this game.
    for status in ('observed_absence', 'unknown', 'conflicting_evidence'):
        dossier['simulation_properties']['cavity_model']['status'] = status
        assert behavior_summary(colony(payload))['status'] == 'waiting_for_change'


def test_research_does_not_repeat_failed_current_benchmark_or_spend_nonexistent_ideas():
    payload = exhausted()
    payload['actor']['allowed_actions'].append('water')
    payload['learning']['dossiers'][0]['simulation_properties']['cavity_model'] = {'status': 'observed_cavity'}
    payload['learning']['experiments'].append({'id': 'failed-contain', 'rule_version': RULE_VERSION,
        'family': 'contain', 'subject_ids': ['object-weight'], 'property_fingerprints': ['current-shape'],
        'context': {'volume': .3, 'distance': 2}, 'status': 'completed', 'result': {'success': False}})
    assert work_opportunities(payload)['research_options'] == []
    payload['learning']['dossiers'][0]['property_fingerprint'] = 'new-evidence'
    assert work_opportunities(payload)['research_options'][0]['family'] == 'contain'
    payload['resources']['ideas'] = 0
    assert work_opportunities(payload)['research_options'] == []


def test_meaningful_changes_wake_world_but_idle_receipts_xp_and_motion_do_not():
    value = colony(exhausted())
    original = behavior_summary(value)['fingerprint']
    value['island']['agents'][0].update(xp=999, position={'x': 2, 'z': 1}, task={'kind': 'rest', 'id': 'new-idle'})
    value['island']['recent_events'] = [{'id': 'idle-receipt'}]
    assert behavior_summary(value)['fingerprint'] == original
    for change in ('resources', 'capabilities', 'evidence'):
        altered = deepcopy(value)
        if change == 'resources': altered['island']['resources']['energy'] = 2
        elif change == 'capabilities': altered['island']['agents'][0]['allowed_actions'].append('charge')
        else: altered['learning']['dossiers'][0]['property_fingerprint'] = 'changed'
        assert behavior_summary(altered)['fingerprint'] != original


def test_consumed_model_assignment_is_not_a_world_change_but_player_constraints_are():
    value = colony(exhausted())
    agent = value['island']['agents'][0]
    agent.update(assignment='auto', assignment_origin='deterministic')
    original = behavior_summary(value)['fingerprint']
    agent.update(assignment='rest', assignment_origin='model', pending_decision_id='real-model-decision')
    assert behavior_summary(value)['fingerprint'] == original
    agent.update(assignment='auto', assignment_origin='deterministic')
    agent.pop('pending_decision_id')
    assert behavior_summary(value)['fingerprint'] == original

    agent.update(assignment='rest', assignment_origin='player')
    resting = behavior_summary(value)['fingerprint']
    assert resting != original
    agent['assignment'] = 'build'
    assert behavior_summary(value)['fingerprint'] not in (original, resting)
    agent['assignment'] = 'auto'
    assert behavior_summary(value)['fingerprint'] == original, 'Releasing an override removes the durable constraint'


@pytest.mark.asyncio
async def test_real_waiting_council_stays_asleep_after_scheduler_consumes_model_rest():
    import json
    from types import SimpleNamespace
    from app.colony_planner import ColonyPlanner
    from test_council_integration import setup_world
    from test_colonies import side
    from test_provider_queue import queue_with_advancing_clock

    repo, store, clock, settings = setup_world()
    island = store.islands['winners']

    def exhaust_useful_work(tx):
        state = tx.get('islandState', island.state_id)
        state['resources'] = {'materials': 1000, 'water': 1000, 'ideas': 1000, 'energy': 0}
        for project in state['projects']:
            if project['id'] != 'beacon':
                project.update(level=project['max_level'], status='complete', reserved_progress=0, workers=[])
        # This controlled fixture has already built each supported task bonus.
        for index, (family, benefit) in enumerate(BENEFITS.items()):
            completed = deepcopy(state['projects'][0])
            completed.update(id='completed-' + family, kind='assembly', level=1, max_level=1,
                             status='complete', benefit=deepcopy(benefit), position={'x': index - 1, 'z': 2})
            state['projects'].append(completed)
        for agent in island._agents(tx):
            island._schedule(state, agent, clock.value)
            assert agent['task']['kind'] == 'rest'
            tx.put('islandAgents', agent)
        tx.put('islandState', state)

    island.repo.transaction(exhaust_useful_work)
    assert side(store)['behavior']['status'] == 'waiting_for_change'
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        decision = {'action': 'rest', 'reason': 'No useful work is available with our current capabilities.',
                    'message': {'kind': 'reflection', 'text': 'We need an energy-capable resident before the beacon can proceed.'}}
        return SimpleNamespace(output_text=json.dumps(decision), model_dump=lambda **kw: {'usage': {'total_tokens': 40}})

    provider = SimpleNamespace(aio=SimpleNamespace(interactions=SimpleNamespace(create=create)))
    worker = ColonyPlanner(repo, store, settings, client=provider, clock=lambda: clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda: clock.value.timestamp(), clock.advance))
    worker.request('review-exhausted-world', 'winners')
    for _ in range(6):
        await worker.run(worker.status()['active_run']['id'])
        clock.advance(3)
    assert worker.sessions('winners')[0]['status'] == 'no_agreement'
    reviewed = worker.status()['reviewed_work_fingerprints']['winners']
    assert any(a['assignment_origin'] == 'model' for a in side(store)['island']['agents'])

    clock.advance(65)
    store.advance()  # Real scheduler consumes each accepted rest choice once.
    after = side(store)
    assert all(a['assignment'] == 'auto' and a['assignment_origin'] == 'deterministic' for a in after['island']['agents'])
    assert after['behavior']['fingerprint'] == reviewed
    state = repo.read(lambda tx: worker._state(tx))
    assert 'winners' not in [c['id'] for c in worker._available_colonies(store.snapshot(), state)]
    assert len(calls) == 6

    first = after['island']['agents'][0]
    store.command({'colony_id': 'winners', 'kind': 'assign', 'assignment': 'rest',
                   'character_id': first['character_id'], 'idempotency_key': 'player-changes-constraint'})
    assert side(store)['behavior']['fingerprint'] != reviewed
    assert 'winners' in [c['id'] for c in worker._available_colonies(store.snapshot(), state)]


@pytest.mark.parametrize('context', [{'volume': 1, 'distance': 10}, {'volume': .3, 'distance': 2, 'tilt_degrees': 70}])
def test_failed_harder_workload_does_not_rule_out_normal_benchmark(context):
    payload = exhausted()
    payload['actor']['allowed_actions'].append('water')
    payload['learning']['dossiers'][0]['simulation_properties']['cavity_model'] = {'status': 'observed_cavity'}
    payload['learning']['experiments'].append({'id': 'failed-overload', 'rule_version': RULE_VERSION,
        'family': 'contain', 'subject_ids': ['object-weight'], 'property_fingerprints': ['current-shape'],
        'context': context, 'status': 'completed', 'result': {'success': False}})
    options = work_opportunities(payload)['research_options']
    assert options[0]['family'] == 'contain'
    assert options[0]['context'] == {'volume': .3, 'distance': 2}


def test_reusable_unfunded_design_keeps_gatherable_work_available():
    payload = observation()
    payload['resources']['materials'] = 0
    payload['peers'][0]['action_yields'] = {'carry': {'materials': 2}}
    output = behavior_summary(colony(payload))
    assert output['status'] == 'design_available'
    assert output['tested_design_ids'] == ['real-test']
    assert 'More supplies must be gathered' in output['reason']
    assert not output['funded_project_ids']
    # A design cannot silently invent a resource source either.
    payload['peers'][0]['action_yields'] = {}
    output = behavior_summary(colony(payload))
    assert not output['tested_design_ids']
    assert 'materials' in output['missing_capabilities']


@pytest.mark.asyncio
async def test_completed_review_sleeps_only_unchanged_automatic_councils_manual_still_works(fixture):
    repo, colonies, provider, clock, worker = fixture
    original = colonies.snapshot
    fingerprints = {'winners': 'work-v1', 'losers': 'work-v1'}
    def snapshot():
        value = original()
        for side in value['colonies']:
            side['behavior'] = {'status': 'waiting_for_change', 'fingerprint': fingerprints[side['id']]}
        return value
    colonies.snapshot = snapshot
    run = worker.request('review-once', 'winners')
    for _ in range(6):
        current = worker.status()['active_run']
        if not current: break
        await worker.run(current['id'])
        clock.add()
    state = repo.read(lambda tx: worker._state(tx))
    assert state['reviewed_work_fingerprints']['winners'] == 'work-v1'
    assert [c['id'] for c in worker._available_colonies(snapshot(), state)] == ['losers']
    assert len(worker._available_colonies(snapshot())) == 2, 'Manual council bypasses waiting guard'
    fingerprints['winners'] = 'work-v2'
    assert len(worker._available_colonies(snapshot(), state)) == 2
    fingerprints['winners'] = 'work-v1'
    clock.add(180)
    manual = worker.request('manual-review', 'winners')
    assert manual['colony_id'] == 'winners'
    assert 'winners' not in repo.read(lambda tx: worker._state(tx))['reviewed_work_fingerprints']
