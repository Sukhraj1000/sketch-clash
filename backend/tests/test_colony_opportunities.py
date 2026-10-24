"""Useful-work context is honest, bounded and never mutates the observed world."""
from copy import deepcopy
import math

from app.colony_experiments import BENEFITS, RULE_VERSION, physical_properties, simulate_experiment
from app.colony_opportunities import work_opportunities


def observation():
    props = physical_properties(['solid metal rectangular body'])
    dossier = {'resident_id': 'object-weight', 'property_fingerprint': 'current-shape',
               'simulation_properties': {'geometry': {key: props[key] for key in ('width', 'height', 'depth', 'length')},
                                         'material_assumption': props['material_assumption']}}
    result = simulate_experiment('hold', [props], {})
    assert result['success']
    experiment = {'id': 'real-test', 'actor_id': 'agent-weight', 'family': 'hold', 'subject_ids': ['object-weight'],
                  'finding_id': 'real-finding', 'rule_version': RULE_VERSION, 'property_fingerprints': ['current-shape'],
                  'context': result['context'], 'result': result}
    return {'actor': {'id': 'agent-weight', 'character_id': 'object-weight', 'allowed_actions': ['plan', 'build']},
            'peers': [{'id': 'agent-cart', 'character_id': 'object-cart', 'allowed_actions': ['carry', 'build']}],
            'resources': {'materials': 100, 'ideas': 100, 'water': 100, 'energy': 0},
            'projects': [], 'planning': {'candidates': []},
            'learning': {'dossiers': [dossier], 'experiments': [experiment], 'blueprints': []}}


def project(payload, identifier, *, kind='garden', level=0, max_level=1, required=None, feasible=True, benefit=None):
    row = {'id': identifier, 'name': identifier, 'kind': kind, 'level': level, 'max_level': max_level,
           'position': {'x': 0, 'z': 0}, 'reward': 'A real garden improvement', 'status': 'complete' if level == max_level else 'planned'}
    if benefit:
        row['benefit'] = deepcopy(benefit)
    payload['projects'].append(row)
    payload['planning']['candidates'].append({'project_id': identifier, 'name': identifier, 'target_level': 1,
        'complete': level >= max_level, 'feasible': feasible, 'remaining_work': 4, 'remaining_actions': 2,
        'required_resources': required or {'materials': 2, 'ideas': 1}, 'reason': 'Executor assessed this candidate.',
        'missing_capabilities': [] if feasible else ['energy']})
    return row


def test_full_storage_exposes_real_funded_work_and_evidence_without_mutation():
    payload = observation()
    project(payload, 'actual-garden')
    before = deepcopy(payload)
    output = work_opportunities(payload)
    assert payload == before
    assert output['funded_projects'][0]['project_id'] == 'actual-garden'
    assert output['funded_projects'][0]['required_resources'] == {'materials': 2, 'ideas': 1}
    design = output['tested_designs'][0]
    assert design['experiment_id'] == 'real-test'
    assert design['finding_id'] == 'real-finding'
    assert design['subject_ids'] == ['object-weight']
    assert design['tested_parts'][0]['resident_id'] == 'object-weight'
    assert design['funded_from_current_stock'] is True
    assert design['benefit']['eligible_actions'] == ['plan', 'measure']
    assert 'selected_project_id' not in output


def test_missing_energy_is_not_fabricated_and_incoming_is_not_stored_funding():
    payload = observation()
    project(payload, 'blocked-beacon', feasible=False, required={'energy': 2})
    project(payload, 'needs-materials', required={'materials': 101})
    payload['planning']['candidates'][-1]['available_resources'] = {'materials': 200}
    output = work_opportunities(payload)
    assert output['funded_projects'] == []
    assert output['blocked_projects'][0]['project_id'] == 'blocked-beacon'
    assert output['blocked_projects'][0]['missing_capabilities'] == ['energy']
    assert output['projects_needing_supplies'][0]['project_id'] == 'needs-materials'


def test_completed_bonus_makes_matching_structures_zero_marginal_but_preserves_new_benefit():
    payload = observation()
    project(payload, 'finished-hold', kind='assembly', level=1, benefit=BENEFITS['hold'])
    project(payload, 'duplicate-hold', kind='assembly', benefit=BENEFITS['hold'])
    project(payload, 'useful-support', kind='assembly', benefit=BENEFITS['support'])
    output = work_opportunities(payload)
    assert [row['project_id'] for row in output['funded_projects']] == ['useful-support']
    assert output['no_additional_benefit_projects'][0]['project_id'] == 'duplicate-hold'
    assert output['tested_designs'] == []
    hold = next(row for row in output['bonus_coverage'] if row['family'] == 'hold')
    assert hold['already_provided_actions'] == ['measure', 'plan']
    assert hold['amount_cap_per_task'] == 1


def test_existing_pending_design_is_work_to_agree_on_not_reason_to_retest():
    payload = observation()
    project(payload, 'awaiting-agreement', kind='assembly', benefit=BENEFITS['hold'])
    output = work_opportunities(payload)
    assert output['tested_designs'] == []
    assert output['funded_projects'][0]['project_id'] == 'awaiting-agreement'
    assert output['omitted_design_counts']['matching_project_already_awaits_work'] == 1


def test_partial_or_nonfunctional_bonuses_do_not_hide_an_uncovered_useful_action():
    payload = observation()
    payload['actor']['allowed_actions'].append('measure')
    project(payload, 'plan-only', kind='assembly', benefit={**BENEFITS['hold'], 'eligible_actions': ['plan']})
    assert work_opportunities(payload)['tested_designs'][0]['experiment_id'] == 'real-test'
    payload['projects'][0]['benefit'] = {**BENEFITS['hold'], 'amount': 0}
    assert work_opportunities(payload)['tested_designs'][0]['experiment_id'] == 'real-test'


def test_stale_evidence_easy_prototypes_and_unrelated_participants_are_never_promoted():
    for mutation in ('fingerprint', 'easy', 'rule', 'participant'):
        payload = observation()
        experiment = payload['learning']['experiments'][0]
        if mutation == 'fingerprint': experiment['property_fingerprints'] = ['old-shape']
        elif mutation == 'easy': experiment['context']['wind_force'] = .01
        elif mutation == 'rule': experiment['rule_version'] = 'old-rules'
        else: experiment['subject_ids'] = ['another-object']
        # Even a lying eligibility flag cannot override the existing validator.
        experiment['result']['production_validation']['eligible'] = True
        assert work_opportunities(payload)['tested_designs'] == [], mutation


def test_latest_tests_do_not_hide_older_actor_evidence_and_repeated_tests_do_not_multiply_it():
    payload = observation()
    own = deepcopy(payload['learning']['experiments'][0])
    payload['learning']['experiments'] = [{**deepcopy(own), 'id': f'peer-test-{i}', 'actor_id': 'another-agent',
                                         'subject_ids': ['another-object']} for i in range(10)]
    payload['learning']['experiments'].extend([own, {**deepcopy(own), 'id': 'duplicate-test'}])
    output = work_opportunities(payload)
    assert [row['experiment_id'] for row in output['tested_designs']] == ['real-test']
    assert output['omitted_design_counts']['duplicate_tested_arrangement'] == 1


def test_shared_peer_evidence_can_be_reused_by_an_actual_participant():
    payload = observation()
    payload['learning']['experiments'][0]['actor_id'] = 'peer-researcher'
    assert work_opportunities(payload)['tested_designs'][0]['experiment_id'] == 'real-test'
    payload['actor']['character_id'] = 'unrelated-object'
    assert work_opportunities(payload)['tested_designs'] == []


def test_blocked_experiments_without_a_result_do_not_break_useful_work_context():
    payload = observation()
    payload['learning']['experiments'].insert(0, {**deepcopy(payload['learning']['experiments'][0]),
                                                 'id': 'blocked-test', 'status': 'blocked', 'result': None})
    output = work_opportunities(payload)
    assert [row['experiment_id'] for row in output['tested_designs']] == ['real-test']


def test_current_capabilities_and_blueprint_references_prevent_false_new_work():
    payload = observation()
    payload['actor']['allowed_actions'] = ['build']
    assert work_opportunities(payload)['tested_designs'] == []
    payload = observation()
    payload['learning']['blueprints'] = [{'id': 'accepted-blueprint', 'experiment_id': 'real-test'}]
    output = work_opportunities(payload)
    assert output['tested_designs'] == []
    assert output['omitted_design_counts']['already_used_by_blueprint'] == 1


def test_free_sites_are_grounded_inside_boundaries_and_clear_of_all_existing_projects():
    payload = observation()
    for i, point in enumerate([(0, 0), (-.75, 0), (0, -.75), (.75, 0), (0, .75)]):
        row = project(payload, str(i))
        row['position'] = {'x': point[0], 'z': point[1]}
    sites = work_opportunities(payload)['free_sites']
    assert len(sites) == 6
    for site in sites:
        assert site['y'] == 0
        assert abs(site['x']) <= 3 and abs(site['z']) <= 3
        assert math.hypot(site['x'], site['z']) <= 3.4
        assert all(math.hypot(site['x'] - row['position']['x'], site['z'] - row['position']['z']) >= .65
                   for row in payload['projects'])


def test_construction_capacity_is_real_and_context_has_bounded_project_lists():
    payload = observation()
    for i in range(15):
        project(payload, f'assembly-{i}', kind='assembly')
    output = work_opportunities(payload)
    assert output['remaining_assembly_slots'] == 0
    assert output['tested_designs'] == []
    assert len(output['no_additional_benefit_projects']) == 6
    assert len(output['free_sites']) <= 6
