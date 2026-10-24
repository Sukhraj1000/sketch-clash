"""Deterministic simulation fixtures, separate from real player data and model calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.config import Settings
from backend.app.island import IslandStore, MAX_AGENTS, MAX_CATCH_UP_SECONDS, MAX_MEMORY, MAX_RESOURCE
from backend.app.repository import MemoryRepository, StoreError, key_for


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat()

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)
        return self.value


def seed(repo, types=('mug', 'bottle', 'pencil', 'ruler', 'phone')):
    def operation(tx):
        for index, object_type in enumerate(types):
            character_id = key_for(repo.world_id, object_type)[:32]
            tx.put('worldCharacters', {'_id': character_id, 'id': character_id, 'world_id': repo.world_id,
                'canonical_type_id': object_type, 'object_type': object_type,
                'display_name': f'Fixture {object_type.title()}', 'unlocked_at': repo.clock(),
                'home_position': {'x': (index % 3) - 1, 'y': 0, 'z': 1},
                'visual_spec': {'template_id': object_type, 'palette': ['#FF3344']},
                'state': {'activity': 'wander', 'mood': 'curious'}, 'distinct_battle_count': 2,
                'first_battle_id': 'fixture-battle'})
    repo.transaction(operation)


@pytest.fixture
def world():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='fixture-island'), clock)
    seed(repo)
    return repo, IslandStore(repo), clock


def action_events(repo):
    return [event for event in repo._data.get('islandEvents', {}).values() if 'sequence' in event]


def command(store, kind, key='fixture-command-key', **kwargs):
    return store.command({'idempotency_key': key, 'kind': kind, **kwargs})


def test_snapshot_never_initializes_or_ticks(world):
    repo, store, clock = world
    before = deepcopy(repo._data)
    assert not store.snapshot()['enabled']
    assert repo._data == before
    started = store.initialize()
    after = deepcopy(repo._data)
    clock.advance(100)
    snapshot = store.snapshot()
    assert snapshot['resources'] == started['resources']
    assert snapshot['revision'] == started['revision']
    assert repo._data == after


def test_initialize_is_idempotent_and_only_explicit_sync_adds_agents(world):
    repo, store, _ = world
    first = store.initialize()
    before = deepcopy(repo._data)
    assert first == store.initialize()
    assert repo._data == before
    seed(repo, ('plant',))
    assert len(store.snapshot()['agents']) == 5
    second = store.initialize()
    assert len(second['agents']) == 6
    old = {agent['character_id']: agent for agent in first['agents']}
    assert all(agent == old[agent['character_id']] for agent in second['agents'] if agent['character_id'] in old)


def test_affordances_tasks_and_world_history_are_preserved(world):
    repo, store, clock = world
    originals = {name: deepcopy(repo._data[name]) for name in ('worldCharacters', 'worlds', 'pipelineVersions', 'qualityState')}
    initial = store.initialize()
    expected = {'mug': 'carry', 'bottle': 'water', 'pencil': 'plan', 'ruler': 'measure', 'phone': 'signal'}
    for agent in initial['agents']:
        assert expected[agent['object_type']] in agent['allowed_actions']
        assert set(('forage', 'build', 'rest', 'explore')).issubset(agent['allowed_actions'])
        assert 14 <= agent['task']['duration_seconds'] <= 18
        assert agent['task']['kind'] in agent['allowed_actions']
    clock.advance(120)
    after = store.advance()
    assert after['completed_actions'] > 15
    assert any(project['level'] > 0 for project in after['projects'])
    for collection, original in originals.items():
        assert repo._data[collection] == original
    assert 'battles' not in repo._data and 'encounters' not in repo._data


def test_concurrent_advances_apply_each_effect_once(world):
    repo, store, clock = world
    store.initialize()
    expected_repo = MemoryRepository(repo.settings, clock)
    expected_repo._data = deepcopy(repo._data)
    clock.advance(100)
    expected = IslandStore(expected_repo).advance()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.advance(), range(20)))
    assert all(result == expected for result in results)
    events = action_events(repo)
    assert len(events) == len({event['id'] for event in events})
    assert len(events) == sum(agent['completed_actions'] for agent in results[0]['agents'])


def test_store_restart_recovers_tasks_memory_and_no_duplicate_rewards(world):
    repo, store, clock = world
    store.initialize()
    clock.advance(70)
    before = store.advance()
    restored = IslandStore(repo)
    assert restored.snapshot() == before
    assert restored.advance() == before
    assert len(action_events(repo)) == before['completed_actions']
    clock.advance(20)
    after = restored.advance()
    assert after['completed_actions'] > before['completed_actions']
    assert all(after_agent['xp'] >= before_agent['xp'] for before_agent, after_agent in zip(before['agents'], after['agents']))


def test_offline_catchup_is_bounded_and_discarded_time_cannot_be_replayed(world):
    repo, store, clock = world
    store.initialize()
    short_clock = Clock()
    short_repo = MemoryRepository(repo.settings, short_clock)
    short_repo._data = deepcopy(repo._data)
    short_clock.advance(MAX_CATCH_UP_SECONDS)
    bounded = IslandStore(short_repo).advance()
    clock.advance(86400 * 7)
    resumed = store.advance()
    assert resumed['catch_up']['simulated_seconds'] == MAX_CATCH_UP_SECONDS
    assert resumed['catch_up']['discarded_seconds'] == 86400 * 7 - MAX_CATCH_UP_SECONDS
    assert resumed['resources'] == bounded['resources']
    assert resumed['completed_actions'] == bounded['completed_actions']
    assert resumed['last_tick_at'] == clock()
    assert store.advance() == resumed
    assert len(action_events(repo)) == resumed['completed_actions']
    clock.advance(5)
    after = store.advance()
    assert after['catch_up']['discarded_seconds'] == 0
    assert after['completed_actions'] - resumed['completed_actions'] <= len(after['agents'])


def test_pause_freezes_progress_and_resume_preserves_remaining_action_time(world):
    repo, store, clock = world
    store.initialize()
    clock.advance(5)
    paused = command(store, 'pause')
    tasks = {agent['id']: deepcopy(agent['task']) for agent in paused['agents']}
    before = deepcopy(repo._data)
    clock.advance(3600)
    frozen = store.advance()
    assert repo._data == before
    assert frozen['completed_actions'] == paused['completed_actions']
    resumed = command(store, 'resume', key='fixture-resume-key')
    assert not resumed['paused']
    for agent in resumed['agents']:
        assert datetime.fromisoformat(agent['task']['ends_at']) - datetime.fromisoformat(tasks[agent['id']]['ends_at']) == timedelta(hours=1)
    clock.advance(8)
    assert store.advance()['completed_actions'] == 0
    clock.advance(10)
    assert store.advance()['completed_actions'] >= 5


def test_commands_are_idempotent_revision_checked_and_invalid_changes_roll_back(world):
    repo, store, clock = world
    started = store.initialize()
    paused = command(store, 'pause', expected_revision=started['revision'])
    before = deepcopy(repo._data)
    assert paused == command(store, 'pause', expected_revision=started['revision'])
    assert repo._data == before
    with pytest.raises(StoreError) as mismatch:
        command(store, 'resume')
    assert mismatch.value.code == 'island_command_mismatch'
    with pytest.raises(StoreError) as stale:
        command(store, 'priority', key='stale-priority', project_id='workshop', expected_revision=0)
    assert stale.value.code == 'island_revision_conflict'
    command(store, 'resume', key='fixture-resume-key')
    clock.advance(50)
    before = deepcopy(repo._data)
    with pytest.raises(StoreError):
        command(store, 'priority', key='bad-priority-key', project_id='not-a-project')
    assert repo._data == before  # Advance and validation share the same transaction.


def test_assignments_and_priority_take_effect_after_committed_current_task(world):
    _, store, clock = world
    started = store.initialize()
    mug = next(agent for agent in started['agents'] if agent['object_type'] == 'mug')
    with pytest.raises(StoreError) as wrong:
        command(store, 'assign', character_id=mug['character_id'], assignment='water')
    assert wrong.value.code == 'invalid_assignment'
    assigned = command(store, 'assign', key='valid-assignment', character_id=mug['character_id'], assignment='rest')
    assigned_mug = next(agent for agent in assigned['agents'] if agent['id'] == mug['id'])
    assert assigned_mug['task'] == mug['task']
    command(store, 'priority', key='fixture-new-priority', project_id='beacon')
    clock.advance(20)
    after = store.advance()
    assert next(agent for agent in after['agents'] if agent['id'] == mug['id'])['task']['kind'] == 'rest'
    assert after['active_project_id'] == 'beacon'


def test_project_reservations_never_overspend_or_credit_the_next_upgrade(world):
    _, store, clock = world
    store.initialize()
    for _ in range(35):
        clock.advance(30)
        snapshot = store.advance()
        for project in snapshot['projects']:
            assert 0 <= project['progress'] + project['reserved_progress'] <= project['required_progress']
            assert len(project['workers']) <= 2
            tasks = [agent['task'] for agent in snapshot['agents'] if agent['task']['project_id'] == project['id']]
            assert sum(task['progress_gain'] for task in tasks) == project['reserved_progress']
            assert all(task['project_level'] == project['level'] for task in tasks)
        assert all(0 <= value <= MAX_RESOURCE for value in snapshot['resources'].values())
    assert snapshot['growth_level'] > 4
    assert any(project['level'] > 1 for project in snapshot['projects'])
    assert all(len(agent['memory']) <= MAX_MEMORY for agent in snapshot['agents'])


def test_unknown_object_alone_can_build_without_a_required_specialist():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='fixture-generic'), clock)
    seed(repo, ('mysterious stone',))
    store = IslandStore(repo)
    store.initialize()
    for _ in range(35):
        clock.advance(120)
        snapshot = store.advance()
    assert snapshot['growth_level'] >= 5
    assert all(project['level'] >= 1 for project in snapshot['projects'])
    assert snapshot['agents'][0]['completed_actions'] > 100
    assert snapshot['agents'][0]['level'] > 1


def test_resource_capacity_is_enforced_even_for_simultaneous_deliveries(world):
    repo, store, clock = world
    snapshot = store.initialize()
    def near_capacity(tx):
        state = tx.get('islandState', store.state_id)
        state['resources'] = {key: MAX_RESOURCE for key in state['resources']}
        tx.put('islandState', state)
    repo.transaction(near_capacity)
    for index, agent in enumerate(snapshot['agents']):
        command(store, 'assign', key=f'fixture-capacity-{index}', character_id=agent['character_id'], assignment='explore')
    clock.advance(120)
    result = store.advance()
    assert all(0 <= value <= MAX_RESOURCE for value in result['resources'].values())
    assert result['expeditions'] > 0
    assert len(result['discoveries']) <= 24


def test_agent_cap_does_not_silently_replace_existing_residents():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='fixture-capped'), clock)
    seed(repo, tuple(f'object {index}' for index in range(MAX_AGENTS + 4)))
    store = IslandStore(repo)
    first = store.initialize()
    assert len(first['agents']) == MAX_AGENTS
    assert first['inactive_residents'] == 4
    ids = {agent['id'] for agent in first['agents']}
    seed(repo, ('earlier-sorting-object',))
    assert {agent['id'] for agent in store.initialize()['agents']} == ids
    assert store.snapshot()['inactive_residents'] == 5


def test_persona_plans_are_bounded_grounded_and_idempotent(world):
    repo, store, clock = world
    store.initialize()
    clock.advance(30)
    snapshot = store.advance()
    agent = snapshot['agents'][0]
    source = agent['memory'][0]['id']
    persona = {'role': 'Fixture helper', 'goal': 'Help build the next project.', 'preferred_action': 'build',
               'lesson': 'Builders need supplies before beginning work.', 'basis_event_ids': [source]}
    provenance = {'run_id': 'fixture-persona-run', 'origin': 'fixture', 'model': 'fixture-model', 'generated_at': clock()}
    original_character = deepcopy(repo._data['worldCharacters'][agent['character_id']])
    updated = store.set_persona(agent['character_id'], persona, provenance)
    assert updated['persona']['preferred_action'] == 'build'
    assert updated['allowed_actions'] == agent['allowed_actions']
    assert updated['level'] == agent['level']
    before = deepcopy(repo._data)
    assert store.set_persona(agent['character_id'], persona, provenance) == updated
    assert repo._data == before
    assert repo._data['worldCharacters'][agent['character_id']] == original_character
    with pytest.raises(StoreError):
        store.set_persona(agent['character_id'], {**persona, 'preferred_action': 'delete_world'}, {**provenance, 'run_id': 'bad-run'})
    with pytest.raises(StoreError):
        store.set_persona(agent['character_id'], {**persona, 'basis_event_ids': ['invented-event']}, {**provenance, 'run_id': 'invented-run'})
    with pytest.raises(StoreError):
        store.set_persona(agent['character_id'], {**persona, 'capabilities': ['magic']}, {**provenance, 'run_id': 'invalid-run'})


def test_old_persona_replay_does_not_revert_a_later_reflection(world):
    _, store, clock = world
    agent = store.initialize()['agents'][0]
    first = {'goal': 'First plan', 'preferred_action': 'forage', 'lesson': '', 'basis_event_ids': []}
    provenance = {'run_id': 'first-run', 'origin': 'fixture', 'generated_at': clock()}
    store.set_persona(agent['character_id'], first, provenance)
    second = store.set_persona(agent['character_id'], {**first, 'goal': 'Later plan'}, {**provenance, 'run_id': 'second-run'})
    replayed = store.set_persona(agent['character_id'], first, provenance)
    assert replayed == second


def test_world_scoping_and_synchronization_after_long_offline_period(world):
    repo, store, clock = world
    store.initialize()
    other = IslandStore(MemoryRepository(Settings(repository='memory', world_id='other-world'), clock))
    assert not other.snapshot()['enabled']
    with pytest.raises(StoreError):
        other.command({'idempotency_key': 'fixture-other-world', 'kind': 'pause'})
    clock.advance(86400)
    seed(repo, ('plant',))
    snapshot = store.initialize()
    new_agent = next(agent for agent in snapshot['agents'] if agent['object_type'] == 'plant')
    assert new_agent['task']['started_at'] == clock()
    assert (datetime.fromisoformat(new_agent['task']['ends_at']) - clock.value).total_seconds() <= 18
    before = new_agent['task']['ends_at']
    assert next(agent for agent in store.advance()['agents'] if agent['object_type'] == 'plant')['task']['ends_at'] == before


def test_finished_island_expeditions_consume_supplies_and_continue_meaningful_work():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='fixture-endgame'), clock)
    seed(repo, ('stone',))
    store = IslandStore(repo)
    store.initialize()
    def completed_island(tx):
        state = tx.get('islandState', store.state_id)
        state['resources'] = {key: 30 for key in state['resources']}
        state['active_project_id'] = None
        for project in state['projects']:
            project.update(level=3, status='complete', progress=0, reserved_progress=0, workers=[])
        for agent in store._agents(tx):
            agent['task'] = None
            tx.put('islandAgents', agent)
        tx.put('islandState', state)
    repo.transaction(completed_island)
    start = store.initialize()
    task = start['agents'][0]['task']
    assert task['kind'] == 'explore'
    assert task['cost'] == {'materials': 2, 'water': 1, 'energy': 2}
    assert start['resources']['water'] == 29
    assert start['resources']['energy'] == 28
    for _ in range(10):
        clock.advance(120)
        snapshot = store.advance()
    assert snapshot['active_project_id'] is None
    assert snapshot['expeditions'] > 20
    assert snapshot['agents'][0]['xp'] > 50
    assert all(0 <= value <= MAX_RESOURCE for value in snapshot['resources'].values())
    assert len(snapshot['discoveries']) <= 24
