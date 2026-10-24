"""Optical relay contracts: no provider traffic or mutation of a saved world.

The connected case uses actual council/executor code with explicit scripted
provider replies; the optical measurements are authored analytical simulation.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.colonies import ColoniesStore
from app.colony_experiments import (RULE_VERSION, physical_properties, physical_property_fingerprint,
                                   reflection_model, simulate_experiment)
from app.colony_learning import DOSSIERS, EXPERIMENTS, annotated_evidence
from app.colony_planner import ColonyPlanner
from app.config import Settings
from app.repository import MemoryRepository, StoreError, key_for
from test_colonies import Clock, battle, side
from test_colony_learning import research
from test_demo_end_to_end import seed_mature_condition
from test_provider_queue import queue_with_advancing_clock


def reflect_test(subject, **context):
    return {'family': 'reflect', 'subject_ids': [subject], 'hypothesis':
            'My accepted reflective surface can redirect the test light over the normal signal route.',
            'expected_success': True, 'context': {'distance': 2, 'load': 1, 'tilt_degrees': 0, **context}}


def reflect_design(experiment, **changes):
    return {'name': 'Tested signal relay', 'purpose': 'Improve existing observation work using a tested reflective panel.',
            'family': 'reflect', 'experiment_id': experiment['id'],
            'parts': [{'kind': 'panel', 'resident_id': experiment['subject_ids'][0]}],
            'position': {'x': 0, 'z': 0}, **changes}


def reflective_resident(repo, learning, scope, *, observer=True, features=None):
    def update(tx):
        resident = tx.get('colonyResidents', 'weight')
        resident['observed_object'] = {'visible_features': features or ['flat polished metal surface']}
        tx.put('colonyResidents', resident)
        if observer:
            agent = tx.get('islandAgents', 'agent-weight')
            agent.update(allowed_actions=['forage', 'build', 'signal'], action_yields={'signal': {'ideas': 3}})
            tx.put('islandAgents', agent)
        return learning.initialize_resident(tx, resident, resident)
    return repo.transaction(update)


@pytest.mark.parametrize('features,status', [
    ([], 'unknown'), (['metal body'], 'unknown'), (['glass screen'], 'unknown'),
    (['matte surface'], 'observed_diffuse_surface'),
    (['not reflective'], 'observed_diffuse_surface'),
    (['non-shiny surface'], 'observed_diffuse_surface'),
    (['possibly polished glass'], 'unknown'),
    (['may be reflective'], 'unknown'),
    (['shiny frame', 'matte coating'], 'conflicting_evidence'),
])
def test_no_optical_evidence_cannot_be_a_physical_failure_or_free_capability(features, status):
    assert reflection_model(features)['status'] == status
    props = physical_properties(features)
    with pytest.raises(StoreError) as exc:
        simulate_experiment('reflect', [props], {})
    assert exc.value.code == 'reflection_evidence_missing'


def test_optical_measurements_are_replayable_and_conditions_can_refute_transfer():
    props = physical_properties(['flat polished metal surface'])
    result = simulate_experiment('reflect', [props], {'distance': 2, 'load': 1})
    assert result['success'] and result['production_validation']['eligible']
    assert result['authority'] == 'deterministic_simulation'
    assert simulate_experiment('reflect', [{**props, 'label': 'cat', 'price': 100000}], result['context']) == result
    assert not simulate_experiment('reflect', [props], {'distance': 10, 'load': 1})['success']
    assert not simulate_experiment('reflect', [props], {'distance': 2, 'load': 10})['success']
    assert not simulate_experiment('reflect', [props], {'distance': 2, 'load': 1, 'tilt_degrees': 45})['success']
    assert not simulate_experiment('reflect', [props], {'distance': 2, 'load': 1, 'tilt_degrees': 70})['success']
    small = {**props, 'width': .3, 'length': .3}
    assert not simulate_experiment('reflect', [small], {'distance': 2, 'load': 1})['success']
    assert simulate_experiment('reflect', [small] * 6, {'distance': 2, 'load': 1})['success']
    for value in (float('inf'), float('nan'), -.1, 1.1, True):
        with pytest.raises(StoreError):
            simulate_experiment('reflect', [{**props, '_reflectivity': value}], {})


def test_missing_evidence_rolls_back_without_cost_finding_or_dossier_change(research):
    repo, learning, scope = research
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        learning.run_experiment(scope, 'agent-weight', reflect_test('weight'), 'no-surface')
    assert exc.value.code == 'reflection_evidence_missing'
    assert repo._data == before


def test_research_options_require_optical_evidence_and_an_existing_signal_action(research):
    from app.colony_opportunities import work_opportunities
    repo, learning, scope = research
    def options(dossier, actions):
        return work_opportunities({'actor': {'character_id': 'weight', 'allowed_actions': actions},
            'resources': {'ideas': 20, 'materials': 30}, 'projects': [], 'peers': [],
            'learning': {'dossiers': [dossier], 'experiments': [], 'blueprints': []}})
    unknown = next(d for d in learning.snapshot(scope)['dossiers'] if d['resident_id'] == 'weight')
    assert not any(r['family'] == 'reflect' for r in options(unknown, ['signal'])['research_options'])
    recorded = reflective_resident(repo, learning, scope)
    assert not any(r['family'] == 'reflect' for r in options(recorded, ['forage'])['research_options'])
    research_options = options(recorded, ['signal'])['research_options']
    assert len(research_options) == 1 and research_options[0]['family'] == 'reflect'
    assert research_options[0]['evidence_basis'] == 'accepted_visible_features'
    assert recorded['simulation_properties']['reflection_model']['status'] == 'observed_reflective_surface'
    assert 'reflectance' in recorded['simulation_properties']['unknowns']
    assert '_physical_properties' not in recorded
    assert 'reflect' in learning.snapshot(scope)['tools']['experiment']['families']


def test_relay_requires_benchmark_real_evidence_and_an_existing_observer(research):
    repo, learning, scope = research
    reflective_resident(repo, learning, scope, observer=False)
    easy = learning.run_experiment(scope, 'agent-weight', reflect_test('weight', distance=.1, load=.1), 'easy')
    assert easy['result']['success'] and not easy['result']['production_validation']['eligible']
    with pytest.raises(StoreError) as exc:
        learning.propose_blueprint(scope, 'agent-weight', reflect_design(easy), 'too-easy')
    assert exc.value.code == 'production_benchmark_not_met'
    tested = learning.run_experiment(scope, 'agent-weight', reflect_test('weight'), 'qualified')
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        learning.propose_blueprint(scope, 'agent-weight', reflect_design(tested), 'no-observer')
    assert exc.value.code == 'blueprint_beneficiary_missing'
    assert repo._data == before
    reflective_resident(repo, learning, scope)
    design = learning.propose_blueprint(scope, 'agent-weight', reflect_design(tested), 'useful')
    assert design['benefit']['resource'] == 'ideas'
    assert design['benefit']['eligible_actions'] == ['signal']
    assert design['benefit']['amount'] == 1
    assert repo.read(lambda tx: learning.structure_bonus(tx, scope, 'signal')) == {}
    # A changed reflective proxy cannot reuse a previously successful receipt.
    original = deepcopy(repo._data[EXPERIMENTS][tested['id']])
    current = reflective_resident(repo, learning, scope, features=['matte metal surface'])
    assert annotated_evidence(original, {'weight': current})['evidence_status'] != 'current'
    with pytest.raises(StoreError) as exc:
        learning.propose_blueprint(scope, 'agent-weight', reflect_design(tested), 'stale-reflection')
    assert exc.value.code in {'blueprint_evidence_stale', 'reflection_evidence_missing'}
    assert repo._data[EXPERIMENTS][tested['id']] == original


def test_additive_optical_proxy_preserves_unchanged_v1_properties_and_receipts(research):
    repo, learning, scope = research
    from test_colony_learning import experiment
    original = learning.run_experiment(scope, 'agent-weight', experiment(), 'old-hold')
    dossier_id = key_for(scope, 'object-dossier', 'weight')
    def legacy(tx):
        dossier = tx.get(DOSSIERS, dossier_id)
        dossier['evidence_fingerprint'] = 'historical-v2-fingerprint'
        dossier.pop('family_property_fingerprints', None)
        dossier['simulation_properties'].pop('reflection_model', None)
        dossier['_physical_properties'].pop('_reflection_status', None)
        dossier['_physical_properties'].pop('_reflectivity', None)
        tx.put(DOSSIERS, dossier)
    repo.transaction(legacy)
    previous = deepcopy(repo._data[DOSSIERS][dossier_id])
    resident = repo._data['colonyResidents']['weight']
    refreshed = repo.transaction(lambda tx: learning.initialize_resident(tx, resident, resident))
    assert refreshed['property_fingerprint'] == previous['property_fingerprint']
    assert physical_property_fingerprint(previous['_physical_properties']) == physical_property_fingerprint(
        repo._data[DOSSIERS][dossier_id]['_physical_properties'])
    assert refreshed['tested_capabilities'] == previous['tested_capabilities']
    assert annotated_evidence(original, {'weight': refreshed})['evidence_status'] == 'current'
    assert repo._data[EXPERIMENTS][original['id']]['result'] == original['result']


class RelayCouncil:
    """An explicit fixture reading real supplied IDs and previous dialogue."""
    def __init__(self):
        self.calls = []
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        payload = json.loads(kwargs['input'])
        self.calls.append(payload)
        options = payload['work_opportunities']
        actor = payload['actor']
        project = next((p for p in payload['projects'] if p.get('assembly', {}).get('family') == 'reflect'
                        and p['level'] < p['max_level']), None)
        designs = [d for d in options['tested_designs'] if d['family'] == 'reflect']
        research = [d for d in options['research_options'] if d['family'] == 'reflect']
        if project:
            kind = 'support' if any(m.get('project_id') == project['id']
                                   for m in payload['council_session']['conversation']) else 'proposal'
            response = {'message': {'kind': kind, 'project_id': project['id'],
                'text': 'Build this tested signal relay: our existing observer can use it for clearer reports.'}}
        elif designs:
            design = designs[0]
            response = {'message': {'kind': 'reflection', 'text': 'The light test passed. Here is its costed relay design for crew agreement.'},
                'blueprint': {'name': 'Crew optical relay', 'purpose': 'Improve our existing observation station with the tested reflective panel.',
                    'family': 'reflect', 'parts': design['tested_parts'], 'experiment_id': design['experiment_id'],
                    'position': options['free_sites'][0]}}
        elif research:
            response = {'message': {'kind': 'reflection', 'text': 'I will test whether my recorded shiny surface can redirect a useful signal.'},
                'experiment': reflect_test(actor['character_id'], **research[0]['context'])}
        else:
            response = {'message': {'kind': 'question', 'text': 'Can our reflective resident test the light before we commit materials?'}}
        return SimpleNamespace(output_text=json.dumps(response), model_dump=lambda **kw: {
            'usage': {'total_tokens': 40}, 'model_version': 'controlled-offline-relay-fixture'})


@pytest.mark.asyncio
async def test_council_test_design_agreement_actual_build_and_capped_signal_receipt():
    clock = Clock()
    settings = Settings(repository='memory', world_id='relay-offline-integration', gemini_api_key='fixture-only')
    repo = MemoryRepository(settings, clock)
    first = battle(repo, 'reflective-observer', winner_type='phone', loser_type='mug')
    first['fighters'][0]['observed_object'] = {'visible_features': ['flat shiny glass screen']}
    repo.transaction(lambda tx: tx.put('battles', first))
    battle(repo, 'planner-peer', winner_type='pencil', loser_type='bottle')
    store = ColoniesStore(repo)
    store.initialize()
    seed_mature_condition(store, clock)
    # Fixture-only stock setup: leave room for the actual post-build delivery,
    # while remaining well above the automatic collection reserve.
    def delivery_room(tx):
        state = tx.get('islandState', store.islands['winners'].state_id)
        state['resources']['ideas'] = 990
        tx.put('islandState', state)
    repo.transaction(delivery_room)
    observer = next(a for a in side(store)['island']['agents'] if a['object_type'] == 'phone')
    actor_before = deepcopy(observer)
    provider = RelayCouncil()
    worker = ColonyPlanner(repo, store, settings, client=provider, clock=lambda: clock.value.timestamp(),
        provider_queue=queue_with_advancing_clock(lambda: clock.value.timestamp(), clock.advance))
    for index in range(3):
        worker.request('relay-council-' + str(index), 'winners', observer['id'])
        for _ in range(6):
            run = worker.status()['active_run']
            if not run:
                break
            await worker.run(run['id'])
            assert repo._data['colonyReasoning'][run['id']]['status'] == 'completed'
            clock.advance(3)
        if side(store)['planning']['selected_project_id']:
            break
    crew = side(store)
    test = next(e for e in crew['learning']['experiments'] if e['family'] == 'reflect')
    blueprint = next(b for b in crew['learning']['blueprints'] if b['family'] == 'reflect')
    project_id = blueprint['project']['id']
    assert test['result']['production_validation']['eligible'] and test['evidence_status'] == 'current'
    assert blueprint['experiment_id'] == test['id'] and blueprint['rule_version'] == RULE_VERSION
    assert crew['planning']['selected_project_id'] == project_id
    assert any(s['status'] == 'agreed' and s['project_id'] == project_id for s in worker.sessions('winners'))
    for _ in range(20):
        clock.advance(20)
        store.advance()
        project = next(p for p in side(store)['island']['projects'] if p['id'] == project_id)
        if project['status'] == 'complete':
            break
    assert project['status'] == 'complete'
    receipts = [r for r in repo._data['islandEvents'].values() if r.get('project_id') == project_id and r.get('progress_delta', 0) > 0]
    assert sum(r['progress_delta'] for r in receipts) == blueprint['work_required']
    crew = side(store)
    observer = next(a for a in crew['island']['agents'] if a['id'] == observer['id'])
    assert observer['allowed_actions'] == actor_before['allowed_actions']
    assert crew['island']['resources']['energy'] == 0
    island = store.islands['winners']
    state = repo.read(lambda tx: tx.get('islandState', island.state_id))
    gained, active = island._production_yield(state, observer, 'signal')
    without = deepcopy(state)
    without['projects'] = [p for p in without['projects'] if p['id'] != project_id]
    base, _ = island._production_yield(without, observer, 'signal')
    assert active and gained['ideas'] == base['ideas'] + 1
    duplicate = deepcopy(state)
    duplicate['projects'].append(deepcopy(project))
    assert island._production_yield(duplicate, observer, 'signal') == (gained, active)
    full = deepcopy(state)
    full['resources']['ideas'] = 1000
    assert island._production_yield(full, observer, 'signal')[0] == {'ideas': 0}
    assert 'signal' not in island._work_options(full, observer, None)['available_actions']
    plan_before = next(a for a in crew['island']['agents'] if a['object_type'] == 'pencil')
    assert island._production_yield(state, plan_before, 'plan') == island._production_yield(without, plan_before, 'plan')
    decision = store.apply_decision('winners', observer['id'], {'action': 'signal',
        'reason': 'Use the completed relay for one actual observation task.'}, 'verify-signal-output')['decision']
    clock.advance(100)
    store.advance()
    delivery = [r for r in repo._data['islandEvents'].values() if r.get('decision_id') == decision['id']]
    assert len(delivery) == 1 and delivery[0]['resource_delta']['ideas'] == gained['ideas']
    assert delivery[0]['decision_origin'] == 'model' and delivery[0]['execution_origin'] == 'local_executor'
    reports = [m for m in side(store)['board'] if delivery[0]['id'] in m.get('receipt_ids', [])]
    assert reports and all(r['verified'] and r['kind'] == 'report' for r in reports)
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        store.learning.propose_blueprint(island.world_id, observer['id'],
            reflect_design(test, position={'x': 2, 'z': 1}), 'duplicate-relay')
    assert exc.value.code == 'duplicate_structure_benefit' and repo._data == before
    assert len(provider.calls) >= 4
    assert any(p['council_session']['conversation'] for p in provider.calls)
    assert all(m['id'] in repo._data['colonyBoard'] for p in provider.calls
               for m in p['council_session']['conversation'])
