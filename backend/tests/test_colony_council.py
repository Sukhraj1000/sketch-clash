"""Crew council facts and scheduling are deterministic fixtures, never paid model calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta

import pytest

from app.agent_sdk import AgentDecision
from app.colonies import ColoniesStore, COUNCIL_SECONDS, COUNCIL_HISTORY_LIMIT
from app.config import Settings
from app.repository import MemoryRepository, StoreError
from test_colonies import Clock, battle, side, actor, command


def create(types=('pitcher', 'ruler', 'mug', 'TV')):
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='fixture-council'), clock)
    for index, kind in enumerate(types):
        battle(repo, f'fixture-council-{index}', kind, f'ordinary-object-{index}')
    return repo, ColoniesStore(repo), clock


def candidate(store, project, colony_id='winners'):
    return next(row for row in side(store, colony_id)['planning']['candidates'] if row['project_id'] == project)


def test_read_only_default_and_full_upgrade_feasibility_prevent_partial_trap():
    repo, store, _ = create(('pencil',))
    before = deepcopy(repo._data)
    assert side(store)['planning']['mode'] == 'crew'
    assert not side(store)['council'] and repo._data == before
    store.initialize()
    garden = candidate(store, 'garden')
    assert garden['required_resources']['water'] == 9
    assert garden['available_resources']['water'] == 4
    assert garden['missing_capabilities'] == ['water'] and not garden['feasible']
    assert candidate(store, 'workshop')['feasible']
    assert side(store)['planning']['selected_project_id'] == 'workshop'
    assert not any(p['reserved_progress'] or p['progress'] for p in side(store)['island']['projects'] if p['id'] == 'garden')
    assert all(row['origin'] == 'deterministic' for row in side(store)['board'])
    assert side(store)['council'][-1]['participants'][0]['agent_id'] == actor(store, 'pencil')['id']


def test_temporary_shortage_is_gatherable_and_keeps_agreed_upgrade():
    repo, store, clock = create(('bottle', 'pencil'))
    store.initialize()
    chosen = side(store)['planning']['selected_project_id']
    island = store.islands['winners']
    def empty_stock(tx):
        state = tx.get('islandState', island.state_id)
        state['resources'] = dict.fromkeys(state['resources'], 0)
        tx.put('islandState', state)
    island.repo.transaction(empty_stock)
    assert candidate(store, chosen)['feasible']
    assert candidate(store, chosen)['gathering_needed']
    clock.advance(COUNCIL_SECONDS); store.advance()
    assert side(store)['planning']['selected_project_id'] == chosen
    assert side(store)['planning']['status'] in ('gathering', 'building')
    assert 'temporary shortages' in side(store)['planning']['reason']
    assert any(row['kind'] == 'request' for row in side(store)['board'])


def test_council_budget_accounts_for_existing_paid_reservations_and_incoming_stock():
    repo, store, _ = create(('pencil',))
    store.initialize()
    island = store.islands['winners']
    def nearly_finished(tx):
        state = tx.get('islandState', island.state_id)
        garden = next(p for p in state['projects'] if p['id'] == 'garden')
        garden.update(progress=12, reserved_progress=4, workers=['fixture-reserved-a', 'fixture-reserved-b'])
        state['resources']['water'] = 1
        tx.put('islandState', state)
    island.repo.transaction(nearly_finished)
    assessed = candidate(store, 'garden')
    assert assessed['remaining_work'] == 2 and assessed['remaining_actions'] == 1
    assert assessed['reserved_work'] == 4 and assessed['required_resources']['water'] == 1
    assert assessed['feasible']  # Previously reserved work was already paid for.


def test_full_upgrade_guard_switches_missing_capability_after_cooldown_and_preserves_tasks():
    repo, store, clock = create()
    store.initialize()
    command(store, 'priority', 'manual-beacon', project_id='beacon')
    assert side(store)['planning']['mode'] == 'manual'
    assert side(store)['planning']['status'] == 'blocked'
    tasks = {a['id']: deepcopy(a['task']) for a in side(store)['island']['agents']}
    command(store, 'council', 'give-crew-control', mode='crew')
    assert side(store)['planning']['mode'] == 'crew'
    assert side(store)['planning']['selected_project_id'] != 'beacon'
    assert 'energy' in candidate(store, 'beacon')['missing_capabilities']
    assert {a['id']: a['task'] for a in side(store)['island']['agents']} == tasks
    before = deepcopy(repo._data)
    command(store, 'council', 'give-crew-control', mode='crew')
    assert repo._data == before
    selection = side(store)['planning']['selected_project_id']
    history_count = len(side(store)['council'])
    for _ in range(8):
        clock.advance(5); store.advance()
    assert side(store)['planning']['selected_project_id'] == selection
    assert len(side(store)['council']) == history_count


def test_model_preferences_are_single_actor_votes_and_can_change_feasible_selection():
    repo, store, clock = create(('mug', 'bottle', 'pencil'))
    store.initialize()
    assert side(store)['planning']['selected_project_id'] == 'garden'
    bottle, pencil = actor(store, 'bottle'), actor(store, 'pencil')
    proposal_decision = {'message': {'kind': 'proposal', 'project_id': 'workshop', 'text': 'Workshop first will improve our materials.'}}
    first = store.apply_decision('winners', bottle['id'], proposal_decision, 'first-proposal')['decision']
    proposal_id = first['board_ids'][0]
    support = {'message': {'kind': 'support', 'project_id': 'workshop', 'proposal_id': proposal_id}}
    store.apply_decision('winners', pencil['id'], support, 'second-vote')
    assert side(store)['planning']['selected_project_id'] == 'garden'  # No immediate authority bypass.
    assert len([row for row in repo._data['colonyProjectOpinions'].values() if row['world_id'] == store.islands['winners'].world_id]) == 2
    clock.advance(COUNCIL_SECONDS); store.advance()
    council = side(store)['council'][-1]
    assert council['chosen_project_id'] == 'workshop'
    assert 'majority' in council['reason']
    assert set(council['model_message_ids']) == {proposal_id, next(row['message_id'] for row in repo._data['colonyProjectOpinions'].values() if row['actor_id'] == pencil['id'])}
    assert sum(p['origin'] == 'model' for p in council['participants']) == 2
    assert council['origin'] == 'deterministic'
    before = deepcopy(repo._data)
    store.apply_decision('winners', bottle['character_id'], AgentDecision.model_validate(proposal_decision), 'first-proposal')
    assert repo._data == before


def test_infeasible_model_proposal_is_visible_but_cannot_grant_missing_abilities():
    repo, store, clock = create(('bottle', 'pencil'))
    store.initialize()
    for kind in ('bottle', 'pencil'):
        store.apply_decision('winners', actor(store, kind)['id'], {'message': {'kind': 'proposal', 'project_id': 'beacon', 'text': 'Pretend that we have free power.'}}, 'unsupported-' + kind)
    before = deepcopy(side(store)['island']['resources'])
    clock.advance(COUNCIL_SECONDS); store.advance()
    assert side(store)['planning']['selected_project_id'] != 'beacon'
    assert not candidate(store, 'beacon')['feasible']
    assert side(store)['island']['resources']['energy'] == before['energy']
    assert all('charge' not in a['allowed_actions'] for a in side(store)['island']['agents'])
    assert any('did not pass feasibility' in p['reason'] for p in side(store)['council'][-1]['participants'])


def test_project_support_is_scoped_and_objections_do_not_forge_a_different_actor():
    repo, store, _ = create(('bottle', 'pencil'))
    store.initialize()
    bottle = actor(store, 'bottle')
    proposal = store.apply_decision('winners', bottle['id'], {'message': {'kind': 'proposal', 'project_id': 'garden'}}, 'local-proposal')['decision']['board_ids'][0]
    other = side(store, 'losers')['island']['agents'][0]
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        store.apply_decision('losers', other['id'], {'message': {'kind': 'support', 'project_id': 'garden', 'proposal_id': proposal}}, 'foreign-support')
    assert exc.value.code == 'invalid_proposal_evidence' and repo._data == before
    with pytest.raises(StoreError):
        store.apply_decision('losers', other['id'], {'message': {'kind': 'objection', 'project_id': 'garden', 'actor_id': bottle['id']}}, 'forged-speaker')
    with pytest.raises(StoreError):
        store.apply_decision('losers', other['id'], {'message': {'kind': 'proposal'}}, 'missing-project')


def test_manual_priority_remains_until_explicit_release():
    repo, store, clock = create()
    store.initialize()
    command(store, 'priority', 'manual-beacon-again', project_id='beacon')
    for _ in range(4):
        clock.advance(COUNCIL_SECONDS); store.advance()
    assert side(store)['planning']['mode'] == 'manual'
    assert side(store)['planning']['selected_project_id'] == 'beacon'
    command(store, 'council', 'crew-again', mode='crew')
    assert side(store)['planning']['selected_project_id'] != 'beacon'
    assert side(store, 'losers')['planning']['mode'] == 'crew'


def test_long_run_builds_every_feasible_project_without_energy_and_history_stays_bounded():
    repo, store, clock = create()
    store.initialize()
    for _ in range(80):
        clock.advance(30); store.advance()
    projects = {p['id']: p for p in side(store)['island']['projects']}
    assert projects['beacon']['level'] == projects['beacon']['progress'] == projects['beacon']['reserved_progress'] == 0
    assert all(projects[name]['level'] == 3 for name in ('garden', 'workshop', 'boardwalk'))
    assert len(side(store)['council']) <= COUNCIL_HISTORY_LIMIT
    assert side(store)['metrics']['fulfilled_requests'] > 0
    assert all(0 <= n <= 1000 for n in side(store)['island']['resources'].values())
    before = deepcopy(repo._data)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: store.advance(), range(6)))
    assert repo._data == before
    assert not repo._data.get('colonyDecisions')
    assert all(p['reserved_progress'] == 0 and not p['workers'] for p in projects.values())


def test_observation_exposes_real_same_colony_proposal_text_and_reference_ids():
    repo, store, _ = create(('bottle', 'pencil'))
    store.initialize()
    bottle, pencil = actor(store, 'bottle'), actor(store, 'pencil')
    text = 'A workshop would improve the materials we both need.'
    record = store.apply_decision('winners', bottle['id'], {'message': {'kind': 'proposal', 'project_id': 'workshop', 'text': text}}, 'readable-proposal')['decision']
    context = store.observation('winners', pencil['id'])
    discussion = context['project_discussion']
    assert len(discussion) == 1
    assert discussion[0]['id'] == record['board_ids'][0] and discussion[0]['text'] == text
    assert discussion[0]['actor_id'] == bottle['id'] and discussion[0]['origin'] == 'model'
    assert 'participants' not in context['council'][0] and 'candidates' not in context['council'][0]
    foreign = side(store, 'losers')['island']['agents'][0]
    assert store.observation('losers', foreign['id'])['project_discussion'] == []
    support = store.apply_decision('winners', pencil['id'], {'message': {'kind': 'support', 'project_id': 'workshop', 'proposal_id': discussion[0]['id']}}, 'read-and-support')
    assert support['decision']['status'] == 'accepted'


def test_old_sdk_turn_replays_after_optional_project_field_is_added():
    from hashlib import sha256
    import json
    repo, store, _ = create(('bottle',))
    store.initialize()
    bottle = actor(store, 'bottle')
    value = {'message': {'kind': 'request', 'resource': 'water', 'quantity': 1}}
    accepted = store.apply_decision('winners', bottle['id'], value, 'prior-sdk-turn')['decision']
    def old_format(tx):
        row = tx.get('colonyDecisions', accepted['id'])
        row['decision']['message'].pop('proposal_id')
        row['fingerprint'] = sha256(json.dumps(row['decision'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        tx.put('colonyDecisions', row)
    repo.transaction(old_format)
    before = deepcopy(repo._data)
    assert store.apply_decision('winners', bottle['id'], value, 'prior-sdk-turn')['decision']['id'] == accepted['id']
    assert repo._data == before


def test_repeated_blocked_deliberation_is_quiet_and_concurrent_tick_is_idempotent():
    repo, store, clock = create(('ordinary-object',))
    store.initialize()
    assert side(store)['planning']['status'] == 'blocked'
    original = len(side(store)['council'])
    clock.advance(COUNCIL_SECONDS)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: store.advance(), range(6)))
    assert len(side(store)['council']) == original
    assert len([row for row in side(store)['board'] if row['kind'] == 'decision']) == original
    assert side(store)['planning']['next_council_at'] > clock()


def test_legacy_blocked_project_migrates_without_losing_partial_progress():
    repo, store, clock = create()
    store.initialize()
    island = store.islands['winners']
    def legacy_state(tx):
        state = tx.get('islandState', island.state_id)
        state.pop('planning'); state.pop('council')
        state['active_project_id'] = 'beacon'
        next(p for p in state['projects'] if p['id'] == 'beacon')['progress'] = 6
        state['resources']['energy'] = 0
        tx.put('islandState', state)
    island.repo.transaction(legacy_state)
    clock.advance(5); store.advance()
    assert side(store)['planning']['mode'] == 'crew'
    assert side(store)['planning']['selected_project_id'] != 'beacon'
    beacon = next(p for p in side(store)['island']['projects'] if p['id'] == 'beacon')
    assert beacon['progress'] == 6 and beacon['level'] == 0
