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
