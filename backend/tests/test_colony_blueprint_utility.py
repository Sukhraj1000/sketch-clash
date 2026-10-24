"""Blueprints need marginal utility, not just a different name or drawing."""
from copy import deepcopy

import pytest

from app.colony_learning import BLUEPRINTS
from app.repository import StoreError, key_for
from test_colony_learning import experiment, proposal, research


def attach_project(repo, scope, project, **changes):
    def attach(tx):
        state = tx.get('islandState', key_for(scope, 'island-state'))
        state['projects'].append({**deepcopy(project), **changes})
        tx.put('islandState', state)
    repo.transaction(attach)


@pytest.mark.parametrize('status', ['planned', 'building', 'complete'])
def test_duplicate_bonus_rejected_without_writes_or_cost_and_original_replays(research, status):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'evidence')
    body = proposal(test)
    first = learning.propose_blueprint(scope, 'agent-weight', body, 'first')
    attach_project(repo, scope, first['project'], status=status, level=int(status == 'complete'))
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        learning.propose_blueprint(scope, 'agent-weight', proposal(test,
            name='A differently named duplicate', position={'x': 2, 'z': 0}), 'duplicate')
    assert exc.value.code == 'duplicate_structure_benefit'
    assert repo._data == before  # No project, blueprint, event or resource write.
    assert learning.propose_blueprint(scope, 'agent-weight', body, 'first') == first
    assert repo._data == before


@pytest.mark.parametrize('family,subject,context', [
    ('hold', 'weight', {'wind_force': 1, 'load': 1, 'duration': 10}),
    ('contain', 'tank', {'volume': .3, 'distance': 2}),
    ('support', 'weight', {'span': .6, 'load': .2}),
])
def test_first_production_benefit_remains_allowed(research, family, subject, context):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-' + subject, experiment(family, [subject], **context), 'qualified')
    assert test['result']['success'] and test['result']['production_validation']['eligible']
    before = deepcopy(repo._data['islandState'][key_for(scope, 'island-state')]['resources'])
    design = learning.propose_blueprint(scope, 'agent-' + subject, proposal(test), 'useful')
    assert design['id'] in repo._data[BLUEPRINTS]
    assert repo._data['islandState'][key_for(scope, 'island-state')]['resources'] == before


@pytest.mark.parametrize('covered', [
    {'resource': 'water', 'eligible_actions': ['plan', 'measure']},
    {'resource': 'ideas', 'eligible_actions': ['water']},
    {'resource': 'ideas', 'eligible_actions': ['plan']},
])
def test_different_resource_action_or_partially_uncovered_benefit_remains_useful(research, covered):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'evidence')
    attach_project(repo, scope, {'id': 'existing', 'kind': 'assembly', 'status': 'complete',
        'position': {'x': -2, 'z': 0}, 'benefit': {'kind': 'task_yield_bonus', 'amount': 1, **covered}})
    design = learning.propose_blueprint(scope, 'agent-weight', proposal(test), 'new-utility')
    assert design['benefit']['resource'] == 'ideas'
    assert design['benefit']['eligible_actions'] == ['plan', 'measure']


def test_multiple_structures_collectively_cover_the_proposed_actions(research):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'evidence')
    for index, action in enumerate(['plan', 'measure']):
        attach_project(repo, scope, {'id': 'existing-' + str(index), 'kind': 'assembly', 'status': 'planned',
            'position': {'x': -2 + index, 'z': 0},
            'benefit': {'kind': 'task_yield_bonus', 'resource': 'ideas', 'amount': 1, 'eligible_actions': [action]}})
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        learning.propose_blueprint(scope, 'agent-weight', proposal(test), 'duplicate')
    assert exc.value.code == 'duplicate_structure_benefit'
    assert repo._data == before


@pytest.mark.parametrize('changes', [
    {'status': 'cancelled'}, {'kind': 'garden'},
    {'benefit': {'kind': 'task_yield_bonus', 'resource': 'ideas', 'amount': 0, 'eligible_actions': ['plan', 'measure']}},
])
def test_unavailable_or_nonproducing_structures_do_not_claim_coverage(research, changes):
    repo, learning, scope = research
    test = learning.run_experiment(scope, 'agent-weight', experiment(), 'evidence')
    attach_project(repo, scope, {'id': 'old', 'kind': 'assembly', 'status': 'complete',
        'position': {'x': -2, 'z': 0},
        'benefit': {'kind': 'task_yield_bonus', 'resource': 'ideas', 'amount': 1, 'eligible_actions': ['plan', 'measure']}}, **changes)
    assert learning.propose_blueprint(scope, 'agent-weight', proposal(test), 'new-utility')['status'] == 'proposed'
