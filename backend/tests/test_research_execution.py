"""Research crosses the same authoritative SDK, resource ledger and build lifecycle."""
from copy import deepcopy
from app.colonies import ColoniesStore
from app.config import Settings
from app.repository import MemoryRepository
from test_colonies import Clock, battle, actor, side, command


def test_experiment_cost_blueprint_build_and_new_arrival_preserve_evidence():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='research-sdk', gemini_api_key='fixture-only'), clock)
    saved = battle(repo, 'first', 'pencil', 'mug')
    saved['fighters'][0]['observed_object'] = {'visible_features': ['solid metal rectangular body', 'broad base']}
    repo.transaction(lambda tx: tx.put('battles', saved))
    store = ColoniesStore(repo); store.initialize()
    scientist = actor(store, 'pencil')
    initial = side(store)['island']['resources']['ideas']
    proposal = {'experiment': {'family': 'hold', 'subject_ids': [scientist['character_id']],
                              'hypothesis': 'A broad base holds the work surface steady in a light wind.',
                              'expected_success': True, 'context': {'wind_force': 1, 'load': 1, 'duration': 10}},
                'message': {'kind': 'reflection', 'text': 'I will test my broad base before recommending a work surface.'}}
    result = store.apply_decision('winners', scientist['id'], proposal, 'test-hold')['decision']['learning_results']['experiment']
    assert result['result']['success']
    assert side(store)['island']['resources']['ideas'] == initial - 1
    store.apply_decision('winners', scientist['id'], proposal, 'test-hold')
    assert side(store)['island']['resources']['ideas'] == initial - 1
    clock.advance(3)
    design = {'blueprint': {'name': 'Stable planning bench', 'purpose': 'Help the island draw plans in wind.',
                           'family': 'hold', 'parts': [{'kind': 'panel', 'resident_id': scientist['character_id']}],
                           'experiment_id': result['id'], 'position': {'x': 0, 'z': 0}}}
    blueprint = store.apply_decision('winners', scientist['id'], design, 'test-design')['decision']['learning_results']['blueprint']
    project_id = blueprint['project']['id']
    pending = next(p for p in side(store)['island']['projects'] if p['id'] == project_id)
    assert pending['level'] == 0 and side(store)['island']['active_project_id'] is None
    # An explicit user override is also validated, and must tolerate an unselected council target.
    command(store, 'priority', 'choose-tested-bench', project_id=project_id)
    for _ in range(12):
        clock.advance(15); store.advance()
        if next(p for p in side(store)['island']['projects'] if p['id'] == project_id)['status'] == 'complete':
            break
    finished = next(p for p in side(store)['island']['projects'] if p['id'] == project_id)
    assert finished['status'] == 'complete'
    scope = store.islands['winners'].world_id
    assert repo.read(lambda tx: store.learning.structure_bonus(tx, scope, 'plan')) == {'ideas': 1}
    evidence = deepcopy(side(store)['learning']['findings'])
    saved = battle(repo, 'arrival', 'bottle', 'battery')
    from app.colonies import route_completed_battle
    repo.transaction(lambda tx: route_completed_battle(tx, saved, repo.world_id)); store.advance()
    assert side(store)['learning']['findings'] == evidence
    assert len(side(store)['learning']['dossiers']) == 2


def test_tool_only_research_does_not_invent_model_dialogue():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='silent-research', gemini_api_key='fixture-only'), clock)
    battle(repo, 'first', 'pencil', 'mug')
    store = ColoniesStore(repo); store.initialize()
    scientist = actor(store, 'pencil')
    result = store.apply_decision('winners', scientist['id'], {'experiment': {
        'family': 'hold', 'subject_ids': [scientist['character_id']],
        'hypothesis': 'This object can hold steady in a breeze.', 'expected_success': True,
        'context': {'wind_force': .01}}}, 'silent-turn')
    message = next(m for m in side(store)['board'] if m['id'] == result['message_id'])
    assert message['origin'] == 'executor'
    assert 'executor' in message['text']
    assert message['evidence']['experiment']['status'] == 'completed'
