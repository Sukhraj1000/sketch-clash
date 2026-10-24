"""Legacy evidence repair preserves receipts and only grants tested game uses."""
from copy import deepcopy

import pytest

from app.colonies import colony_world_id
from app.colony_experiments import (DOSSIER_EVIDENCE_VERSION, RULE_VERSION, canonical_digest, cavity_model,
                                    physical_properties, physical_property_fingerprint, simulate_experiment)
from app.colony_learning import (DOSSIERS, DOSSIER_REVISIONS, EXPERIMENTS, FINDINGS, RESEARCH,
                                 ColonyLearningStore)
from app.config import Settings
from app.repository import MemoryRepository, StoreError, key_for


def world(features=None, capabilities=None, *, label='mug'):
    repo = MemoryRepository(Settings(repository='memory', world_id='cavity-repair-fixture'),
                            lambda: '2026-10-24T19:00:00+00:00')
    store = ColonyLearningStore(repo)
    scope = colony_world_id(repo.world_id, 'winners')
    resident = {'_id': 'object', 'id': 'object', 'world_id': scope, 'display_name': label,
                'object_type': label, 'canonical_type_id': label, 'first_battle_id': 'first-battle',
                'observed_object': {'visible_features': features or []},
                'visual_spec': {'template_id': 'mug', 'proportions': {'width': 1, 'height': 1}}}
    def seed(tx):
        tx.put('colonyResidents', resident)
        tx.put('islandAgents', {'_id': 'agent', 'id': 'agent', 'world_id': scope, 'character_id': 'object',
                               'display_name': label, 'capabilities': capabilities or [],
                               'allowed_actions': ['build', 'water'] if capabilities else ['build']})
        tx.put('islandState', {'_id': key_for(scope, 'island-state'), 'world_id': scope, 'revision': 0,
                              'resources': {'materials': 30, 'water': 20, 'ideas': 20, 'energy': 0}, 'projects': []})
        store.initialize_resident(tx, resident, {**resident, 'capture_id': 'real-capture'}, 'real-placement')
        store.refresh_arrivals(tx, scope, 'winners', [resident])
    repo.transaction(seed)
    return repo, store, scope, resident


def spec():
    return {'family': 'contain', 'subject_ids': ['object'], 'hypothesis': 'Test the simulated vessel against the normal transport workload.',
            'expected_success': True, 'context': {'volume': .3, 'distance': 2}}


@pytest.mark.parametrize('label', ['mug', 'pitcher', 'water reservoir', 'solid rock'])
def test_missing_photo_and_template_or_name_alone_do_not_establish_a_cavity(label):
    repo, store, scope, _ = world(label=label)
    dossier = store.snapshot(scope)['dossiers'][0]
    assert dossier['observed_evidence']['visible_features'] == []
    assert dossier['simulation_properties']['apparent_cavity'] is None
    assert dossier['simulation_properties']['cavity_model']['status'] == 'unknown'
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        store.run_experiment(scope, 'agent', spec(), 'unsupported')
    assert exc.value.code == 'containment_evidence_missing'
    assert repo._data == before  # No cost, false negative, work or resource grant.


@pytest.mark.parametrize('capability', ['store_water', 'contain_water'])
def test_declared_capability_is_a_separate_testable_game_proxy(capability):
    repo, store, scope, _ = world(capabilities=[capability])
    dossier = store.snapshot(scope)['dossiers'][0]
    properties = dossier['simulation_properties']
    assert properties['apparent_cavity'] is None
    assert properties['cavity_model']['status'] == 'declared_simulation_cavity'
    assert properties['cavity_model']['authority'] == 'declared_game_capability'
    assert dossier['observed_evidence']['status'] == 'historical_features_unavailable'
    assert dossier['observed_evidence']['visible_features'] == []
    assert dossier['tested_capabilities'] == []
    stored = repo._data[DOSSIERS][dossier['id']]
    assert stored['_physical_properties']['provenance'] == 'authored_simulation_proxy_from_declared_game_capability'
    test = store.run_experiment(scope, 'agent', spec(), 'supported-retest')
    assert test['result']['success'] and test['result']['production_validation']['eligible']
    assert test['dossier_revisions'][0]['cavity_model']['authority'] == 'declared_game_capability'
    assert test['evidence_version'] == DOSSIER_EVIDENCE_VERSION
    assert repo._data['islandState'][key_for(scope, 'island-state')]['resources'] == {
        'materials': 30, 'water': 20, 'ideas': 19, 'energy': 0}
    assert store.snapshot(scope)['dossiers'][0]['tested_capabilities'][0]['authority'] == 'tested_simulation_only'
    proposal = {'name': 'Useful water vessel', 'purpose': 'Improve existing water transport using a tested vessel design.',
                'family': 'contain', 'experiment_id': test['id'], 'parts': [{'kind': 'vessel', 'resident_id': 'object'}],
                'position': {'x': 0, 'z': 0}}
    blueprint = store.propose_blueprint(scope, 'agent', proposal, 'vessel-blueprint')
    assert blueprint['benefit']['resource'] == 'water'
    assert blueprint['status'] == 'proposed'  # Crew agreement and work still required.
    assert repo._data['islandState'][key_for(scope, 'island-state')]['projects'] == []


def test_explicit_absence_and_conflicts_are_not_overridden_by_game_capabilities():
    solid = physical_properties(['no cavity', 'solid metal body'], capabilities=['store_water'])
    assert solid['_cavity_status'] == 'observed_absence'
    assert simulate_experiment('contain', [solid], {})['success'] is False
    assert cavity_model(['no visible opening'])['status'] == 'unknown'
    assert cavity_model(['not a container'])['status'] == 'unknown'
    assert cavity_model(['not hollow'])['status'] == 'observed_absence'
    conflicting = physical_properties(['hollow body', 'no cavity'], capabilities=['store_water'])
    with pytest.raises(StoreError) as exc:
        simulate_experiment('contain', [conflicting], {})
    assert exc.value.code == 'containment_evidence_missing'


def legacy_records(repo, scope, *, features=None):
    """Reproduce the old zero-capacity proxy and a receipt it actually produced."""
    identifier = key_for(scope, 'object-dossier', 'object')
    current = repo._data[DOSSIERS][identifier]
    props = {key: value for key, value in physical_properties(features or []).items() if not key.startswith('_')}
    props['provenance'] = 'authored_simulation_parameters_from_accepted_visible_features'
    legacy = {key: deepcopy(value) for key, value in current.items()
              if key not in ('evidence_version', 'evidence_fingerprint', 'revision', 'updated_at')}
    legacy['simulation_properties'].pop('cavity_model')
    legacy['simulation_properties']['apparent_cavity'] = props['capacity'] > 0
    legacy.update(property_fingerprint=canonical_digest(props), _physical_properties=props)
    result = simulate_experiment('contain', [props], {})
    record = {'_id': 'old-test', 'id': 'old-test', 'world_id': scope, 'family': 'contain',
              'subject_ids': ['object'], 'rule_version': RULE_VERSION, 'result': result,
              'status': 'completed', 'created_at': repo.clock(), 'property_fingerprints': [legacy['property_fingerprint']]}
    finding = {'_id': 'old-finding', 'id': 'old-finding', 'world_id': scope, 'family': 'contain',
               'subject_ids': ['object'], 'rule_version': RULE_VERSION, 'success': result['success'],
               'status': 'tested_in_sim', 'context': result['context'], 'claim': result['summary'],
               'measurements': result['measurements'], 'updated_at': repo.clock(),
               'property_fingerprints': [legacy['property_fingerprint']], 'supporting_experiment_ids': ['old-test']}
    def seed(tx):
        tx.put(DOSSIERS, legacy)
        tx.put(EXPERIMENTS, record)
        tx.put(FINDINGS, finding)
    repo.transaction(seed)
    return legacy, record, finding


def test_legacy_false_negative_is_archived_not_rewritten_and_supported_retest_is_new_evidence():
    repo, store, scope, resident = world(capabilities=['contain_water'])
    old_dossier, old_test, old_finding = legacy_records(repo, scope)
    assert old_test['result']['success'] is False
    # A blocked research question must be reopened when evidence changes.
    repo.transaction(lambda tx: store.remember_blocked_tx(tx, scope, 'agent', 'Try containment', ['cavity'], 'blocked'))
    # Reproduce the old capability fingerprint rather than the initial v2 fixture.
    state_id = key_for(scope, 'learning-state')
    repo._data['colonyLearningState'][state_id]['capability_fingerprint'] = 'legacy'
    for question in repo._data[RESEARCH].values():
        question['capability_fingerprint'] = 'legacy'
    update = repo.transaction(lambda tx: store.refresh_arrivals(tx, scope, 'winners', [resident]))
    assert update['changed'] and update['reopened']
    assert repo._data[EXPERIMENTS]['old-test'] == old_test
    assert repo._data[FINDINGS]['old-finding'] == old_finding
    archived = list(repo._data[DOSSIER_REVISIONS].values())
    assert len(archived) == 1
    assert archived[0]['_physical_properties'] == old_dossier['_physical_properties']
    assert archived[0]['simulation_properties'] == old_dossier['simulation_properties']
    snapshot = store.snapshot(scope)
    assert snapshot['findings'] == []
    assert snapshot['historical_findings'][0]['evidence_status'] == 'superseded_properties'
    assert store.knowledge(scope, 'cavity')['findings'] == []
    before = deepcopy(repo._data)
    assert not repo.transaction(lambda tx: store.refresh_arrivals(tx, scope, 'winners', [resident]))['changed']
    assert repo._data == before  # No repeated migration/history churn.
    fresh = store.run_experiment(scope, 'agent', spec(), 'new-test')
    assert fresh['id'] != old_test['id'] and fresh['result']['success'] is True
    assert repo._data[EXPERIMENTS]['old-test'] == old_test
    assert [row['id'] for row in store.knowledge(scope, 'cavity')['findings']] == [fresh['finding_id']]


def test_legacy_unknown_stays_unknown_and_original_valid_photo_test_stays_current():
    repo, store, scope, resident = world()
    _, old_test, _ = legacy_records(repo, scope)
    repo.transaction(lambda tx: store.refresh_arrivals(tx, scope, 'winners', [resident]))
    assert store.snapshot(scope)['historical_findings'][0]['evidence_status'] == 'missing_cavity_evidence'
    assert repo._data[EXPERIMENTS]['old-test'] == old_test
    repo, store, scope, resident = world(['hollow plastic body', 'open top'])
    _, old_test, old_finding = legacy_records(repo, scope, features=['hollow plastic body', 'open top'])
    assert old_test['result']['success']
    repo.transaction(lambda tx: store.refresh_arrivals(tx, scope, 'winners', [resident]))
    assert store.knowledge(scope, 'cavity')['findings'][0]['id'] == 'old-finding'
    assert repo._data[FINDINGS]['old-finding'] == old_finding
    dossier = store.snapshot(scope)['dossiers'][0]
    assert dossier['observed_evidence']['capture_id'] == 'real-capture'
    assert dossier['observed_evidence']['placement_id'] == 'real-placement'
    assert dossier['simulation_properties']['apparent_cavity'] is True
