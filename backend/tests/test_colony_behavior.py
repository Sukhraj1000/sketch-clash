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
