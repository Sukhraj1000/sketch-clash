from copy import deepcopy
import json

import pytest

from app.colony_context import bounded_council_context
from app.colony_planner import SYSTEM
from app.repository import StoreError


def observation():
    return {'actor': {'character_id': 'own', 'allowed_actions': ['carry', 'build'],
                     'capabilities': ['hold'], 'memory': [{'text': 'Earlier work. '*50} for _ in range(4)]},
            'work_options': {'useful_actions': ['build'], 'full_resources': ['materials']},
            'known_capability_gaps': ['energy'], 'resources': {'materials': 1000},
            'projects': [{'id': 'assembly-1', 'position': {'x': 1, 'z': 2}}],
            'council_session': {'conversation': [{'id': 'message-1', 'actor_id': 'peer',
                'text': 'Materials are full. Build the tested anchor.', 'reply_to_id': None,
                'seen_message_ids': ['old-message']*80}]},
            'learning': {'tools': {'production_benchmarks': {'hold': {'wind_force': 1, 'load': 1}},
                                  'truth_boundary': 'Simulation test only.'},
                'dossiers': [{'id': 'dossier-'+str(i), 'resident_id': 'own' if i == 0 else 'peer-'+str(i),
                    'observed_evidence': {'visible_features': ['Observed material. '*60]},
                    'simulation_properties': {'authority': 'authored_assumption'}} for i in range(10)],
                'experiments': [{'id': 'experiment-'+str(i), 'context': {'wind_force': i+1},
                    'result': {'success': True, 'measurements': {'load': 1}, 'production_validation': {'eligible': True}},
                    'hypothesis': 'Recorded hypothesis. '*50} for i in range(6)],
                'findings': [{'id': 'finding-'+str(i), 'rule_version': 'fixture', 'context': {'load': 1},
                             'description': 'Actual evidence. '*75} for i in range(8)],
                'blueprints': [{'id': 'blueprint-'+str(i), 'project': {'id': 'assembly-1', 'redundant': 'x'*2000},
                                'evidence': 'Keep exact evidence. '*30} for i in range(8)]},
            'project_discussion': [], 'board': [], 'last_receipts': [], 'recent_validation_feedback': []}


def test_bounding_reserves_recall_room_without_rewriting_tools_capabilities_or_dialogue():
    payload = observation(); original = deepcopy(payload)
    encoded = bounded_council_context(payload, len(SYSTEM))
    assert len(encoded)+len(SYSTEM) <= 36000
    assert payload['learning']['tools'] == original['learning']['tools']
    assert payload['actor']['allowed_actions'] == original['actor']['allowed_actions']
    assert payload['work_options'] == original['work_options']
    message = payload['council_session']['conversation'][0]
    assert message['text'] == original['council_session']['conversation'][0]['text']
    assert 'seen_message_ids' not in message
    assert payload['learning']['dossiers'][0]['resident_id'] == 'own'
    assert payload['context_window']['omitted_records']
    assert all('project' not in row for row in payload['learning']['blueprints'])
    assert original['learning']['blueprints'][0]['project']['redundant']


def test_recall_is_bounded_again_and_supplied_evidence_stays_self_contained():
    payload = observation()
    bounded_council_context(payload, len(SYSTEM))
    retained = deepcopy(payload['learning']['findings'])
    payload['learning']['retrieved_memory'] = {'status': 'exact_only', 'findings': retained}
    encoded = bounded_council_context(payload, len(SYSTEM), target=40000)
    assert len(encoded)+len(SYSTEM) <= 40000
    recall = payload['learning']['retrieved_memory']
    assert recall['status'] == 'exact_only' and recall['findings']
    assert all(row in retained for row in recall['findings'])
    assert 'finding_ids_in_learning' not in recall
    assert json.loads(encoded)['learning']['tools'] == payload['learning']['tools']


def test_essential_constraints_cannot_be_silently_truncated():
    payload = {'actor': {'allowed_actions': ['carry'], 'capabilities': ['x'*50000]}}
    with pytest.raises(StoreError) as exc: bounded_council_context(payload, len(SYSTEM))
    assert exc.value.code == 'planner_context_limit'
    assert payload['actor']['capabilities'] == ['x'*50000]


def mature_observation():
    """Real record shapes at the persisted dossier/project/history limits."""
    payload = observation()
    payload['projects'] = []
    payload['planning'] = {'candidates': []}
    for i in range(12):
        project = {'id': f'assembly-{i}', 'kind': 'assembly', 'name': 'Completed support',
            'level': 1, 'max_level': 1, 'status': 'complete', 'position': {'x': i*.1, 'z': 2},
            'benefit': {'resource': 'materials', 'eligible_actions': ['carry'], 'amount': 1},
            'assembly': {'family': 'support', 'context': {'span': .6, 'load': .2},
                'parts': [{'resident_id': f'peer-{j}', 'kind': 'beam', 'rotation': 0,
                    'position': {'x': j*.1, 'y': 0, 'z': 0},
                    'geometry': {'width': 1, 'height': .1, 'depth': .5, 'length': 1.8}}
                    for j in range(12)]}}
        payload['projects'].append(project)
        payload['planning']['candidates'].append({'project_id': project['id'], 'complete': True,
            'feasible': False, 'required_resources': {'materials': 20, 'ideas': 12},
            'available_resources': {'materials': 1000, 'water': 44, 'ideas': 40, 'energy': 0},
            'incoming_resources': {'materials': 0, 'water': 0, 'ideas': 0, 'energy': 0},
            'gatherable_resources': ['materials', 'water', 'ideas'], 'remaining_work': 16,
            'reason': 'All upgrades are complete.'})
    payload['projects'].append({'id': 'beacon', 'level': 0, 'max_level': 3,
        'cost_per_action': {'materials': 1, 'ideas': 1, 'energy': 1}, 'position': {'x': 0, 'z': 1}})
    payload['planning']['candidates'].append({'project_id': 'beacon', 'complete': False,
        'feasible': False, 'missing_capabilities': ['energy'], 'required_resources': {'energy': 7},
        'reason': 'No resident can supply energy.'})
    dossiers = payload['learning']['dossiers'][:4]
    for d in dossiers:
        d['observed_evidence'] = {'status': 'accepted_capture', 'visible_features': ['A long flat shape.']}
        d['tested_capabilities'] = [{'family': 'support', 'context': {'span': .6, 'load': j+.2},
            'rule_version': 'fixture', 'authority': 'tested_simulation_only', 'finding_id': f'{j:064x}'} for j in range(32)]
        d['finding_ids'] = [f'{j:064x}' for j in range(64)]
    payload['learning']['dossiers'] = dossiers
    payload['work_opportunities'] = {'authority': 'Executor facts; model chooses.',
        'tested_designs': [{'experiment_id': 'old-experiment', 'subject_ids': ['own', 'peer-3'],
            'family': 'support', 'context': {'span': .6, 'load': .2}, 'tested_parts': [],
            'evidence_status': 'current_production_validator_passed'}],
        'research_options': [{'family': 'contain', 'resident_id': 'own',
            'evidence_basis': 'Visible opening', 'context': {'volume': .3, 'distance': 2}}]}
    payload['learning']['experiments'] = [{'id': f'old-{i}', 'hypothesis': 'An old observation. '*20,
        'result': {'success': False, 'context': {'span': .6, 'load': i+1}}} for i in range(30)]
    payload['learning']['experiments'].append({'id': 'old-experiment', 'subject_ids': ['own', 'peer-3'],
        'finding_id': 'cited-finding', 'hypothesis': 'Test the shared support.',
        'result': {'success': True, 'production_validation': {'eligible': True}},
        'context': {'span': .6, 'load': .2}})
    payload['learning']['findings'] += [{'id': 'cited-finding', 'context': {'span': .6, 'load': .2},
        'claim': 'The tested support held.', 'subject_ids': ['own', 'peer-3'], 'rule_version': 'fixture'}]
    payload['council_session']['conversation'] = [{'id': f'message-{i}', 'actor_id': 'peer-3',
        'text': 'Please reuse old-experiment and cited-finding; do not claim it supplies energy. ' * 4,
        'reply_to_id': f'message-{i-1}' if i else None, 'receipt_ids': ['real-receipt'],
        'seen_message_ids': [f'message-{j}' for j in range(i)]} for i in range(6)]
    return payload


def test_mature_world_preserves_current_discussion_evidence_and_blockers_within_budget():
    original = mature_observation()
    payload = deepcopy(original)
    assert len(json.dumps(payload)) + len(SYSTEM) > 48000
    encoded = bounded_council_context(payload, len(SYSTEM))
    assert len(encoded) + len(SYSTEM) <= 36000
    assert payload['planning']['candidates'][-1] == original['planning']['candidates'][-1]
    assert payload['projects'][-1] == original['projects'][-1]
    assert payload['work_opportunities'] == original['work_opportunities']
    assert payload['learning']['tools'] == original['learning']['tools']
    for current, previous in zip(payload['council_session']['conversation'], original['council_session']['conversation']):
        assert current == {key: value for key, value in previous.items() if key != 'seen_message_ids'}
    assert any(row['id'] == 'old-experiment' for row in payload['learning']['experiments'])
    assert any(row['id'] == 'cited-finding' for row in payload['learning']['findings'])
    assert {row['resident_id'] for row in payload['learning']['dossiers']} >= {'own', 'peer-3'}
    assert original['projects'][0]['assembly']['parts'], 'Caller-owned projection cannot mutate saved source records'
    for current, previous in zip(payload['projects'][:12], original['projects'][:12]):
        assert current['position'] == previous['position'] and current['benefit'] == previous['benefit']
        assert current['assembly']['source_resident_ids'] == [part['resident_id'] for part in previous['assembly']['parts']]
    first = deepcopy(payload)
    assert bounded_council_context(payload, len(SYSTEM)) == encoded, 'Bounding twice must be idempotent'
    assert payload == first


def test_large_optional_dossier_indexes_are_bounded_without_changing_tested_conditions():
    payload = mature_observation()
    # Every resident is involved in this discussion, so dropping dossiers is not
    # sufficient: the optional indexes inside them must have a bounded window.
    payload['council_session']['participants'] = [{'character_id': row['resident_id']} for row in payload['learning']['dossiers']]
    before = deepcopy(payload['learning']['dossiers'])
    encoded = bounded_council_context(payload, len(SYSTEM), target=22000, maximum=30000)
    assert len(encoded) + len(SYSTEM) <= 30000
    assert payload['context_window']['omitted_records'].get('dossier.tested_capabilities', 0) > 0
    assert len(payload['learning']['dossiers']) == len(before)
    for current, old in zip(payload['learning']['dossiers'], before):
        assert current['observed_evidence'] == old['observed_evidence']
        assert current['simulation_properties'] == old['simulation_properties']
        assert all(row in old['tested_capabilities'] for row in current['tested_capabilities'])


def test_historical_findings_are_bounded_and_never_promoted_to_current_evidence():
    payload = observation()
    payload['learning']['historical_findings'] = [{'id': f'archived-{i}',
        'evidence_status': 'stale_proxy', 'claim': 'Historical test only. '*100,
        'context': {'volume': .3}, 'success': False} for i in range(40)]
    payload['council_session']['conversation'][0]['text'] = 'Does archived-39 apply to the current proxy?'
    last = deepcopy(payload['learning']['historical_findings'][-1])
    encoded = bounded_council_context(payload, len(SYSTEM))
    assert len(encoded) + len(SYSTEM) <= 36000
    assert last in payload['learning']['historical_findings']
    assert all(row['id'] != last['id'] for row in payload['learning']['findings'])
    assert payload['context_window']['omitted_records']['learning.historical_findings'] > 0
