"""Analytical experiments and durable learning: isolated worlds, no provider calls."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.colonies import colony_world_id
from app.colony_experiments import (BlueprintProposal, ExperimentSpec, RULE_VERSION,
                                    physical_properties, simulate_experiment)
from app.colony_learning import (BLUEPRINTS, DOSSIERS, EXPERIMENTS, FINDINGS, RESEARCH,
                                ColonyLearningStore, finding_index_definition)
from app.config import Settings
from app.repository import MemoryRepository, StoreError, key_for


@pytest.fixture
def research():
    repo = MemoryRepository(Settings(repository='memory', world_id='learning-fixture'), lambda: '2026-10-24T12:00:00+00:00')
    learning = ColonyLearningStore(repo)
    scope = colony_world_id(repo.world_id, 'winners')
    def initialize(tx):
        tx.put('islandState', {'_id': key_for(scope, 'island-state'), 'world_id': scope, 'revision': 0,
                              'resources': {'materials': 30, 'water': 8, 'ideas': 30, 'energy': 5}, 'projects': []})
        residents = []
        for identifier, label, features in (
                ('beam', 'ruler', ['flat elongated wooden strip']),
                ('support', 'mug', ['ceramic body', 'open top', 'broad base']),
                ('tank', 'pitcher', ['hollow plastic body', 'open top', 'tall']),
                ('weight', 'paperweight', ['solid metal rectangular body'])):
            resident = {'_id': identifier, 'id': identifier, 'world_id': scope, 'colony_id': 'winners',
                        'display_name': label.title(), 'object_type': label, 'canonical_type_id': label,
                        'first_battle_id': 'test-' + identifier, 'observed_object': {'visible_features': features}}
            tx.put('colonyResidents', resident)
            tx.put('islandAgents', {'_id': 'agent-' + identifier, 'id': 'agent-' + identifier,
                                  'world_id': scope, 'character_id': identifier, 'display_name': label.title(),
                                  'allowed_actions': ['forage', 'build'], 'capabilities': ['gather_materials']})
            learning.initialize_resident(tx, resident, {**resident, 'capture_id': 'capture-' + identifier,
                                                        'output_id': 'output-' + identifier}, 'placement-' + identifier)
            residents.append(resident)
        learning.refresh_arrivals(tx, scope, 'winners', residents)
    repo.transaction(initialize)
    return repo, learning, scope


def experiment(family='hold', subjects=None, **context):
    return {'family': family, 'subject_ids': subjects or ['weight'],
            'hypothesis': 'The tested arrangement can perform useful work in these conditions.',
            'expected_success': True, 'context': context}


def proposal(test, subjects=None, **overrides):
    ids = subjects or test['subject_ids']
    parts = [{'kind': {'hold': 'panel', 'contain': 'vessel', 'support': 'beam'}[test['family']],
              'resident_id': identifier} for identifier in ids]
    return {'name': 'Useful island structure', 'purpose': 'Help residents perform their normal island work.',
            'family': test['family'], 'parts': parts, 'experiment_id': test['id'], 'position': {'x': 0, 'z': 0}, **overrides}


def test_physics_is_label_invariant_and_replayable():
    properties = physical_properties(['solid metal rectangular body'])
    renamed = {**properties, 'label': 'banana', 'price': 1000000}
    first = simulate_experiment('hold', [properties], {'wind_force': 1})
    assert first['success']
    assert simulate_experiment('hold', [renamed], {'wind_force': 1}) == first
    assert simulate_experiment('hold', [properties], {'wind_force': 1}) == first
    assert first['authority'] == 'deterministic_simulation'


def test_stronger_wind_and_changed_load_can_refute_transfer():
    p = physical_properties(['flat wooden strip'])
    assert simulate_experiment('hold', [p], {'wind_force': .1})['success']
    assert not simulate_experiment('hold', [p], {'wind_force': 20})['success']
    assert simulate_experiment('support', [p], {'span': .2, 'load': .1})['success']
    assert not simulate_experiment('support', [p], {'span': 1.8, 'load': 10})['success']


def test_actual_second_object_changes_support_outcome():
    beam = physical_properties(['flat wooden strip'])
    support = physical_properties(['solid metal rectangular body'])
    assert not simulate_experiment('support', [beam], {'span': .6, 'load': .2})['success']
    assert simulate_experiment('support', [beam, support], {'span': .6, 'load': .2, 'support_count': 3})['success']
    with pytest.raises(StoreError, match='additional physical participants'):
        simulate_experiment('support', [beam], {'span': .6, 'support_count': 3})


def test_container_capacity_tilt_and_leakage_have_measurable_effects():
    container = physical_properties(['hollow plastic body', 'open top', 'tall'])
    solid = physical_properties(['solid metal rectangular body'])
    assert simulate_experiment('contain', [container], {'volume': .3})['success']
    assert not simulate_experiment('contain', [container], {'volume': .3, 'tilt_degrees': 70})['success']
    assert not simulate_experiment('contain', [solid], {'volume': .3})['success']
    porous = {**container, 'leak_rate': .3}
    assert not simulate_experiment('contain', [porous], {'volume': .3, 'distance': 5})['success']


@pytest.mark.parametrize('field,value', [('mass', float('inf')), ('friction', float('nan')), ('capacity', -1), ('stiffness', True)])
def test_nonphysical_input_cannot_produce_results(field, value):
    with pytest.raises(StoreError):
        simulate_experiment('hold', [{**physical_properties([]), field: value}], {})


def test_dossier_keeps_capture_evidence_and_hides_assumed_unknowns(research):
    repo, learning, scope = research
    public = next(row for row in learning.snapshot(scope)['dossiers'] if row['resident_id'] == 'tank')
    assert public['observed_evidence']['capture_id'] == 'capture-tank'
    assert public['observed_evidence']['placement_id'] == 'placement-tank'
    assert public['observed_evidence']['visible_features'] == ['hollow plastic body', 'open top', 'tall']
    assert '_physical_properties' not in public
    assert 'mass' not in public['simulation_properties']['geometry']
    assert 'mass' in public['simulation_properties']['unknowns']
    assert 'authored' in public['simulation_properties']['authority']
    stored = repo._data[DOSSIERS][public['id']]
    assert stored['_physical_properties']['capacity'] > 0


def test_experiment_consumes_one_idea_once_and_journals_actual_result(research):
    repo, learning, scope = research
    before = repo._data['islandState'][key_for(scope, 'island-state')]['resources']['ideas']
    first = learning.run_experiment(scope, 'agent-weight', experiment(), 'test-1')
    after = deepcopy(repo._data)
    second = learning.run_experiment(scope, 'agent-weight', experiment(), 'test-1')
    assert first == second and repo._data == after
    assert first['status'] == 'completed' and first['result']['success']
    assert repo._data['islandState'][key_for(scope, 'island-state')]['resources']['ideas'] == before - 1
    finding = repo._data[FINDINGS][first['finding_id']]
    assert finding['supporting_experiment_ids'] == [first['id']]
    assert finding['context']['wind_force'] == 1
    assert any(row['kind'] == 'experiment.completed' for row in repo._data['agentEvents'].values())
    with pytest.raises(StoreError) as exc:
        learning.run_experiment(scope, 'agent-weight', experiment(wind_force=2), 'test-1')
    assert exc.value.code == 'research_request_mismatch'


def test_repetition_links_evidence_without_making_new_capabilities(research):
    repo, learning, scope = research
    a = learning.run_experiment(scope, 'agent-weight', experiment(), 'repeat-a')
    b = learning.run_experiment(scope, 'agent-weight', experiment(), 'repeat-b')
    assert a['finding_id'] == b['finding_id']
    dossier = repo._data[DOSSIERS][key_for(scope, 'object-dossier', 'weight')]
    assert len(dossier['tested_capabilities']) == 1
    assert 'confidence' not in repo._data[FINDINGS][a['finding_id']]


def test_changed_context_preserves_old_boundary_and_records_failure(research):
    repo, learning, scope = research
    passed = learning.run_experiment(scope, 'agent-beam', experiment('hold', ['beam'], wind_force=.1), 'calm')
    failed = learning.run_experiment(scope, 'agent-beam', {**experiment('hold', ['beam'], wind_force=20),
                                                        'reply_to_finding_id': passed['finding_id']}, 'storm')
    assert passed['result']['success'] and not failed['result']['success']
    assert failed['prediction_correct'] is False
    old = repo._data[FINDINGS][passed['finding_id']]
    assert old['success'] is True and old['boundary_evidence_ids'] == [failed['id']]
    assert old['context'] != failed['context']
    assert passed['finding_id'] != failed['finding_id']


def test_cross_island_and_nonparticipant_research_is_denied_without_changes(research):
    repo, learning, scope = research
    before = deepcopy(repo._data)
    for wrong_scope, actor, subjects in ((colony_world_id(repo.world_id, 'losers'), 'agent-weight', ['weight']),
                                         (scope, 'agent-weight', ['tank']), (scope, 'agent-weight', ['weight', 'foreign'])):
        with pytest.raises(StoreError):
            learning.run_experiment(wrong_scope, actor, experiment(subjects=subjects), 'denied')
        assert repo._data == before


def test_idea_shortage_creates_blocked_research_not_fake_evidence(research):
    repo, learning, scope = research
    repo.transaction(lambda tx: tx.put('islandState', {**tx.get('islandState', key_for(scope, 'island-state')),
                                                       'resources': {'ideas': 0}}))
    result = learning.run_experiment(scope, 'agent-weight', experiment(), 'no-ideas')
    assert result['status'] == 'blocked' and result['result'] is None
    assert not repo._data.get(FINDINGS)
    assert next(iter(repo._data[RESEARCH].values()))['status'] == 'blocked'


def test_new_object_reopens_research_and_changes_fingerprint_without_rewriting_old_dossier(research):
    repo, learning, scope = research
    repo.transaction(lambda tx: learning.remember_blocked_tx(tx, scope, 'agent-beam', 'Add a support to bridge the wider gap.', ['support'], 'wide-bridge'))
    old = learning.snapshot(scope)
    old_dossiers = deepcopy(repo._data[DOSSIERS])
    def arrive(tx):
        new = {'_id': 'new-support', 'id': 'new-support', 'world_id': scope, 'display_name': 'New support',
               'observed_object': {'visible_features': ['solid metal broad base']}}
        tx.put('colonyResidents', new)
        tx.put('islandAgents', {'_id': 'new-agent', 'id': 'new-agent', 'world_id': scope,
                               'character_id': new['id'], 'allowed_actions': ['carry'], 'capabilities': ['carry_materials']})
        return learning.refresh_arrivals(tx, scope, 'winners', tx.find('colonyResidents', {'world_id': scope}))
    result = repo.transaction(arrive)
    assert result['changed'] and result['new_resident_ids'] == ['new-support'] and len(result['reopened']) == 1
    assert result['fingerprint'] != old['capability_fingerprint']
    assert next(iter(repo._data[RESEARCH].values()))['status'] == 'needs_reassessment'
    for identifier, dossier in old_dossiers.items():
        assert repo._data[DOSSIERS][identifier] == dossier
    before = deepcopy(repo._data)
    repeated = repo.transaction(lambda tx: learning.refresh_arrivals(tx, scope, 'winners', tx.find('colonyResidents', {'world_id': scope})))
    assert not repeated['changed'] and repo._data == before


def test_blueprint_uses_server_costs_and_has_no_instant_resource_reward(research):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'stable')
    resources = deepcopy(repo._data['islandState'][key_for(scope, 'island-state')]['resources'])
    blueprint = learning.propose_blueprint(scope, 'agent-weight', proposal(test), 'desk')
    assert blueprint['status'] == 'proposed' and blueprint['project']['level'] == 0
    assert blueprint['project']['kind'] == 'assembly'
    assert blueprint['cost_per_action']['materials'] >= 1
    assert blueprint['benefit']['amount'] == 1
    assert repo._data['islandState'][key_for(scope, 'island-state')]['resources'] == resources
    assert repo.read(lambda tx: learning.structure_bonus(tx, scope, 'plan')) == {}
    before = deepcopy(repo._data)
    assert learning.propose_blueprint(scope, 'agent-weight', proposal(test), 'desk') == blueprint
    assert repo._data == before


def test_invalid_blueprint_cost_reward_unearned_evidence_and_physics_are_rejected(research):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'stable')
    for patch in ({'cost_per_action': {'materials': 0}}, {'benefit': {'amount': 999}},
                  {'experiment_id': 'not-evidence'}, {'position': {'x': 3, 'z': 3}},
                  {'parts': [{'kind': 'panel', 'resident_id': 'weight', 'position': {'y': 1}}]}):
        before = deepcopy(repo._data)
        with pytest.raises(StoreError):
            learning.propose_blueprint(scope, 'agent-weight', proposal(test, **patch), 'bad-blueprint')
        assert repo._data == before


def test_failed_experiment_cannot_unlock_a_construction(research):
    _, learning, scope = research
    test = learning.run_experiment(scope, 'agent-beam', experiment('hold', ['beam'], wind_force=20), 'failed')
    with pytest.raises(StoreError) as exc:
        learning.propose_blueprint(scope, 'agent-beam', proposal(test), 'invalid')
    assert exc.value.code == 'blueprint_evidence_mismatch'


def test_completed_build_activates_only_matching_task_bonus_and_is_idempotent(research):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'stable')
    bp = learning.propose_blueprint(scope, 'agent-weight', proposal(test), 'desk')
    assert repo.transaction(lambda tx: learning.complete_blueprint_tx(tx, scope, bp['project'])) is None
    project = {**bp['project'], 'level': 1, 'status': 'complete'}
    complete = repo.transaction(lambda tx: learning.complete_blueprint_tx(tx, scope, project))
    before = deepcopy(repo._data)
    assert repo.transaction(lambda tx: learning.complete_blueprint_tx(tx, scope, project)) == complete
    assert repo._data == before
    assert repo.read(lambda tx: learning.structure_bonus(tx, scope, 'plan')) == {'ideas': 1}
    assert repo.read(lambda tx: learning.structure_bonus(tx, scope, 'water')) == {}


def test_schema_prevents_duplicate_objects_unbounded_assemblies_and_nonfinite_context():
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(experiment(subjects=['weight', 'weight']))
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(experiment(wind_force=float('nan')))
    with pytest.raises(ValidationError):
        BlueprintProposal.model_validate({'name': 'Too much', 'purpose': 'An excessive construction', 'family': 'hold',
                                           'experiment_id': 'real', 'parts': [{'kind': 'panel', 'resident_id': str(i)} for i in range(13)]})


def test_memory_retrieval_never_returns_other_island_or_other_rules(research):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'test')
    original = deepcopy(repo._data[FINDINGS][test['finding_id']])
    repo.transaction(lambda tx: tx.put(FINDINGS, {**original, '_id': 'foreign', 'id': 'foreign',
                                                 'world_id': colony_world_id(repo.world_id, 'losers')}))
    repo.transaction(lambda tx: tx.put(FINDINGS, {**original, '_id': 'old', 'id': 'old', 'rule_version': 'old-rules'}))
    result = learning.knowledge(scope, 'stable wind')
    assert result['status'] == 'exact_only'
    assert [row['id'] for row in result['findings']] == [test['finding_id']]
    definition = finding_index_definition()
    assert {'world_id', 'rule_version', 'status'} <= {row['path'] for row in definition['fields'] if row['type'] == 'filter'}


@pytest.mark.asyncio
async def test_memory_adapter_exposes_exact_fallback_without_embedding_calls(research):
    _, learning, scope = research
    class NeverEmbed:
        async def embed(self, *args, **kwargs):
            raise AssertionError('Memory fallback must not spend provider calls.')
    result = await learning.retrieve(scope, 'water carrier', NeverEmbed())
    assert result['status'] == 'exact_only'
    assert (await learning.prepare_embeddings(scope, NeverEmbed()))['status'] == 'exact_only'


def test_label_change_with_same_accepted_evidence_does_not_change_dossier_properties(research):
    repo, learning, scope = research
    original = deepcopy(repo._data['colonyResidents']['weight'])
    def add(tx):
        return learning.initialize_resident(tx, {**original, '_id': 'renamed', 'id': 'renamed',
                                                  'object_type': 'banana', 'canonical_type_id': 'banana', 'display_name': 'Banana'})
    renamed = repo.transaction(add)
    old = repo._data[DOSSIERS][key_for(scope, 'object-dossier', 'weight')]
    assert renamed['property_fingerprint'] == old['property_fingerprint']


def test_matched_memory_evaluation_preserves_outcomes_and_retests_new_conditions():
    from backend.scripts.evaluate_colony_memory import evaluate
    report = evaluate()
    assert report['model_calls'] == 0 and report['live_database_writes'] == 0
    assert report['all_outcomes_agree']
    assert report['totals']['memory_off']['experiments_run'] == 4
    assert report['totals']['memory_on']['experiments_run'] == 2
    assert report['totals']['memory_on']['known_failures_avoided'] == 1
    for row in report['scenarios'][-2:]:
        assert row['memory_on']['action'] == 'run_new_experiment'
    assert report['scenarios'][-1]['memory_on']['success']
