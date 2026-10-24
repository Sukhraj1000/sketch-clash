"""Capability-aware work admission fixtures; no provider calls or real saves."""
from copy import deepcopy

from app.colonies import ColoniesStore, IDLE_CHECK_SECONDS
from app.config import Settings
from app.island import MAX_RESOURCE
from app.repository import MemoryRepository
from test_colonies import Clock, actor, battle, side


def prepared(resources=None):
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='useful-work-fixture'), clock)
    for i, kind in enumerate(('pencil', 'bottle', 'microwave')):
        battle(repo, f'object-{i}', kind, f'other-{i}')
    store = ColoniesStore(repo)
    store.initialize()
    island = store.islands['winners']
    def set_state(tx):
        state = tx.get('islandState', island.state_id)
        state['resources'] = resources or {'materials': 1000, 'water': 44, 'ideas': 42, 'energy': 0}
        for project in state['projects']:
            project.update(level=0 if project['id'] == 'beacon' else project['max_level'],
                           progress=0, reserved_progress=0, workers=[])
        state.update(active_project_id='beacon', planning={'mode': 'crew', 'decision_authority': 'model',
                     'selected_project_id': 'beacon', 'target_level': 1})
        for agent in island._agents(tx):
            agent.update(assignment='auto', assignment_origin='deterministic', active_commitment=None)
            island._schedule(state, agent, clock.value)
            tx.put('islandAgents', agent)
        tx.put('islandState', state)
    island.repo.transaction(set_state)
    return repo, store, clock, island


def test_full_materials_switch_to_a_declared_useful_specialty_and_never_invent_energy():
    _, store, _, island = prepared({'materials': MAX_RESOURCE, 'water': 44, 'ideas': 0, 'energy': 0})
    pencil = actor(store, 'pencil')
    assert pencil['task']['kind'] == 'plan' and pencil['task']['gain']['ideas'] > 0
    assert actor(store, 'microwave')['task']['kind'] == 'rest'
    observation = store.observation('winners', pencil['id'])
    options = observation['work_options']
    assert options['full_resources'] == ['materials']
    assert 'plan' in options['useful_actions']
    assert options['action_yields']['explore'] == {'materials': 0}
    assert 'charge' not in options['available_actions']
    assert any(row['action'] == 'explore' and 'storage is full' in row['reason'] for row in options['blocked_actions'])
    assert 'energy' in next(row['reason'] for row in options['blocked_actions'] if row['action'] == 'build')


def test_admission_prefers_funded_construction_and_preserves_valid_model_choices():
    _, store, _, island = prepared()
    state = island.repo.read(lambda tx: tx.get('islandState', island.state_id))
    state['resources']['energy'] = 20
    project = island._choose_project(state)
    pencil = actor(store, 'pencil')
    assert island._choose_action(state, pencil, project) == 'build'
    pencil.update(assignment='plan', assignment_origin='model')
    assert island._choose_action(state, pencil, project) == 'plan'
    bottle = actor(store, 'bottle')
    bottle.update(assignment='water', assignment_origin='model')
    assert island._choose_action(state, bottle, project) == 'water'


def test_stale_model_choice_cannot_farm_full_storage_or_relabel_fallback_as_model_work():
    repo, store, clock, island = prepared({'materials': MAX_RESOURCE, 'water': 44, 'ideas': 0, 'energy': 0})
    def schedule(tx):
        state = tx.get('islandState', island.state_id)
        pencil = next(a for a in island._agents(tx) if a['object_type'] == 'pencil')
        pencil.update(assignment='explore', assignment_origin='model', pending_decision_action='explore',
                      pending_decision_id='stale-model-choice')
        island._schedule(state, pencil, clock.value)
        tx.put('islandAgents', pencil)
        tx.put('islandState', state)
    island.repo.transaction(schedule)
    pencil = actor(store, 'pencil')
    task = pencil['task']
    assert task['kind'] == 'plan' and task['action_switched']
    assert task['requested_action'] == 'explore' and task['requested_decision_id'] == 'stale-model-choice'
    assert task['decision_id'] is None and task['decision_origin'] == 'deterministic'
    assert 'storage is full' in task['scheduling_reason']
    assert pencil['assignment'] == 'auto' and 'pending_decision_action' not in pencil
    clock.advance(20); store.advance()
    receipt = repo._data['islandEvents'][task['id']]
    assert receipt['resource_delta']['ideas'] > 0 and receipt['requested_decision_id'] == 'stale-model-choice'
    assert receipt['decision_origin'] == 'deterministic'
    report = next(row for row in side(store)['board'] if row.get('receipt_ids') == [receipt['id']])
    assert report['origin'] == 'executor' and report['verified']


def test_no_capable_useful_work_idles_without_rewards_and_does_not_flood_the_board():
    repo, store, clock, _ = prepared()
    initial = actor(store, 'microwave')
    assert initial['task']['kind'] == 'rest'
    assert initial['task']['duration_seconds'] == IDLE_CHECK_SECONDS
    assert initial['task']['gain'] == {} and initial['task']['xp_gain'] == 0
    assert 'energy' in initial['task']['scheduling_reason']
    assert all(a['task']['kind'] == 'rest' for a in side(store)['island']['agents'])
    for _ in range(3):
        clock.advance(IDLE_CHECK_SECONDS); store.advance()
    current = actor(store, 'microwave')
    assert current['xp'] == initial['xp']
    rows = [r for r in repo._data['islandEvents'].values() if r.get('actor_id') == current['id']]
    assert len(rows) == 3 and all(r['resource_delta'] == {} and r['progress_delta'] == 0 for r in rows)
    reports = [r for r in side(store)['board'] if r['actor_id'] == current['id'] and r['origin'] == 'executor']
    assert len(reports) == 1 and reports[0]['receipt_ids']
    assert side(store)['island']['resources'] == {'materials': 1000, 'water': 44, 'ideas': 42, 'energy': 0}


def test_model_contribution_receipt_and_executor_report_preserve_the_accepted_decision():
    repo, store, clock, _ = prepared()
    pencil = actor(store, 'pencil')
    accepted = store.apply_decision('winners', pencil['id'],
        {'action': 'plan', 'reason': 'Draw plans for a possible supported experiment.'}, 'fixture-real-decision')['decision']
    clock.advance(IDLE_CHECK_SECONDS + 20); store.advance()
    receipt = next(r for r in repo._data['islandEvents'].values() if r.get('decision_id') == accepted['id'])
    assert receipt['decision_origin'] == 'model' and receipt['resource_delta']['ideas'] > 0
    report = next(r for r in side(store)['board'] if r.get('receipt_ids') == [receipt['id']])
    assert report['origin'] == 'executor' and report['text'] == receipt['description']
    assert report['decision_id'] == accepted['id']


def test_observation_is_read_only_and_identifies_admissible_but_unneeded_stock():
    repo, store, _, _ = prepared()
    pencil = actor(store, 'pencil')
    before = deepcopy(repo._data)
    options = store.observation('winners', pencil['id'])['work_options']
    assert options['available_actions'] == ['rest', 'plan']
    assert options['useful_actions'] == []
    assert options['action_yields']['plan']['ideas'] > 0
    assert options['automatic_buffer_target'] == 40
    assert repo._data == before


def test_full_storage_cancels_stale_offer_without_faking_delivery_or_trapping_actor():
    repo, store, clock, island = prepared()
    pencil, bottle = actor(store, 'pencil'), actor(store, 'bottle')
    request = store.apply_decision('winners', pencil['id'],
        {'message': {'kind': 'request', 'resource': 'water', 'quantity': 3}}, 'request-water')['decision']['board_ids'][0]
    store.apply_decision('winners', bottle['id'], {'action': 'water', 'claim_request_id': request}, 'offer-water')
    commitment_id = actor(store, 'bottle')['active_commitment']['id']
    def fill(tx):
        state = tx.get('islandState', island.state_id)
        state['resources']['water'] = MAX_RESOURCE
        tx.put('islandState', state)
    island.repo.transaction(fill)
    clock.advance(1); store.advance()
    assert repo._data['colonyBoard'][request]['status'] == 'superseded'
    commitment = repo._data['colonyCommitments'][commitment_id]
    assert commitment['status'] == 'cancelled' and commitment['receipt_ids'] == []
    assert commitment['remaining'] == 3
    assert actor(store, 'bottle')['active_commitment'] is None
    assert actor(store, 'bottle')['assignment'] == 'auto'
    assert not [r for r in repo._data.get('colonyContributions', {}).values() if r['request_id'] == request]


def test_newly_useful_work_supersedes_model_rest_but_preserves_player_rest():
    _, store, _, island = prepared()
    state = island.repo.read(lambda tx: tx.get('islandState', island.state_id))
    state['resources']['energy'] = 20
    project = island._choose_project(state)
    pencil = actor(store, 'pencil')
    pencil.update(assignment='rest', assignment_origin='model')
    assert island._choose_action(state, pencil, project) == 'build'
    pencil['assignment_origin'] = 'player'
    assert island._choose_action(state, pencil, project) == 'rest'


def test_council_wake_reserves_once_without_completing_idle_or_overriding_busy_work():
    repo, store, clock, island = prepared()
    before = {a['id']: deepcopy(a) for a in side(store)['island']['agents']}
    journal_before = deepcopy(repo._data.get('islandEvents', {}))
    def wake(tx):
        state = tx.get('islandState', island.state_id)
        state['resources']['energy'] = 20
        agents = island._agents(tx)
        for agent in agents:
            agent.update(assignment='rest', assignment_origin='model', pending_decision_action='rest',
                         pending_decision_id='earlier-idle-decision')
        started = island._wake_idle_workers(tx, state, agents, clock.value, 'accepted-council-outcome')
        tx.put('islandState', state)
        return started
    started = island.repo.transaction(wake)
    assert len(started) == 2  # Only the two real construction places are admitted.
    assert all(task['status'] == 'scheduled' and task['kind'] == 'build' for task in started)
    snapshot = side(store)['island']
    for item in started:
        current = next(a for a in snapshot['agents'] if a['id'] == item['actor_id'])
        previous = before[current['id']]
        assert current['task']['id'] == previous['task']['id']
        assert current['xp'] == previous['xp'] and current['completed_actions'] == previous['completed_actions']
        assert current['task']['council_id'] == 'accepted-council-outcome'
        assert current['task']['decision_origin'] == 'deterministic' and current['task']['decision_id'] is None
        assert current['task']['requested_decision_id'] == 'earlier-idle-decision'
        assert current['task']['requested_action'] == 'rest' and current['task']['action_switched']
        assert current['assignment'] == 'auto'
    assert repo._data.get('islandEvents', {}) == journal_before
    state_before = deepcopy(repo._data)
    def repeat(tx):
        state = tx.get('islandState', island.state_id)
        assert island._wake_idle_workers(tx, state, island._agents(tx), clock.value, 'accepted-council-outcome') == []
    island.repo.transaction(repeat)
    assert repo._data == state_before
    clock.advance(20); store.advance()
    receipts = [repo._data['islandEvents'][item['task_id']] for item in started]
    assert all(row['progress_delta'] > 0 and row['council_id'] == 'accepted-council-outcome' for row in receipts)
    assert all(row['kind'] == 'build' and row['decision_origin'] == 'deterministic' for row in receipts)


def test_council_wake_preserves_player_rest_and_active_commitments():
    repo, store, clock, island = prepared()
    def wake(tx):
        state = tx.get('islandState', island.state_id)
        state['resources']['energy'] = 20
        agents = island._agents(tx)
        agents[0].update(assignment='rest', assignment_origin='player')
        agents[1]['active_commitment'] = {'id': 'still-promised', 'action': 'rest'}
        agents[2]['task']['kind'] = 'plan'
        before = deepcopy(agents)
        assert island._wake_idle_workers(tx, state, agents, clock.value, 'accepted-council') == []
        assert agents == before and state['resources']['energy'] == 20
    island.repo.transaction(wake)
