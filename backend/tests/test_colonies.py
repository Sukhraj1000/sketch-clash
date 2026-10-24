"""Controlled colony fixtures: no real saves, network calls, or model spending."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from app.agent_sdk import capability_profile
from app.colonies import ColoniesStore, colony_world_id, route_completed_battle
from app.config import Settings
from app.repository import MemoryRepository, StoreError


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    def __call__(self):
        return self.value.isoformat()
    def advance(self, seconds=13):
        self.value += timedelta(seconds=seconds)
        return self.value


def battle(repo, identifier, winner_type='pencil', loser_type='bottle', winner_slot=0, color='#123456'):
    fighters = []
    for slot, kind in enumerate((winner_type, loser_type)):
        fighters.append({'player_slot': slot, 'canonical_type_id': kind, 'object_type': kind,
            'display_name': f'{kind} from {identifier}', 'image_ref': f'/api/media/{identifier}-{slot}',
            'archetype': 'Quick', 'visual_spec': {'template_id': kind, 'palette': [color], 'appearance_seed': slot + 1}})
    value = {'_id': identifier, 'id': identifier, 'world_id': repo.world_id, 'status': 'completed',
             'winner_slot': winner_slot, 'completed_at': repo.clock(), 'fighters': fighters}
    repo.transaction(lambda tx: tx.put('battles', value))
    return value


def side(store, side_id='winners'):
    return next(row for row in store.snapshot()['colonies'] if row['id'] == side_id)


def actor(store, kind, side_id='winners'):
    return next(row for row in side(store, side_id)['island']['agents'] if row['object_type'] == kind)


def command(store, kind, key, side_id='winners', **fields):
    return store.command({'colony_id': side_id, 'kind': kind, 'idempotency_key': key, **fields})


@pytest.fixture
def colony():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory', world_id='colony-fixture'), clock)
    battle(repo, 'a', 'pencil', 'phone')
    battle(repo, 'b', 'bottle', 'box')
    battle(repo, 'c', 'mug', 'battery')
    return repo, ColoniesStore(repo), clock


def test_read_is_inert_and_backfill_preserves_actual_metadata_and_legacy(colony):
    repo, store, _ = colony
    before = deepcopy(repo._data)
    assert not store.snapshot()['enabled']
    assert not store.advance()['enabled']
    assert repo._data == before
    first = store.initialize()
    assert first['persistence'] == repo.persistence
    after = deepcopy(repo._data)
    assert store.initialize() == first and repo._data == after
    for name, values in before.items():
        assert repo._data[name] == values
    assert len(repo._data['colonyPlacements']) == 6
    assert len(repo._data['colonyResidents']) == 6
    pencil = side(store)['characters'][0]
    for character in side(store)['characters']:
        original = repo._data['battles'][character['first_battle_id']]['fighters'][0]
        assert character['visual_spec'] == original['visual_spec']
        assert character['image_ref'] == original['image_ref']
        assert character['market_price'] is None and character['estimated_value_gbp'] is None


def test_same_type_can_exist_on_both_sides_without_moving_or_replacing_first_appearance(colony):
    repo, store, clock = colony
    store.initialize()
    old = deepcopy(side(store)['characters'])
    clock.advance()
    second = battle(repo, 'same-type', 'pencil', 'pencil', winner_slot=1, color='#ABCDEF')
    repo.transaction(lambda tx: route_completed_battle(tx, second, repo.world_id))
    store.advance()
    winner = next(c for c in side(store)['characters'] if c['object_type'] == 'pencil')
    loser = next(c for c in side(store, 'losers')['characters'] if c['object_type'] == 'pencil')
    original = next(c for c in old if c['object_type'] == 'pencil')
    assert winner['id'] == original['id'] and winner['visual_spec'] == original['visual_spec']
    assert winner['distinct_battle_count'] == 2
    assert loser['id'] != winner['id'] and loser['visual_spec']['palette'] == ['#ABCDEF']
    assert loser['first_player_slot'] == 0 and winner['first_player_slot'] == 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: repo.transaction(lambda tx: route_completed_battle(tx, second, repo.world_id)), range(12)))
    assert winner == next(c for c in side(store)['characters'] if c['id'] == winner['id'])
    altered = deepcopy(second); altered['winner_slot'] = 0
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        repo.transaction(lambda tx: route_completed_battle(tx, altered, repo.world_id))
    assert exc.value.code == 'placement_conflict' and repo._data == before


def test_live_finalization_routes_both_participants_in_the_same_transaction(colony, monkeypatch):
    from backend.tests.test_lifecycle import ready
    import app.colonies as module
    repo, store, clock = colony
    store.initialize()
    prepared = ready(repo, repo.settings, request='new-real-round', types=('plant', 'ruler'))
    started = repo.start_battle(prepared['id'], 'normal')
    clock.advance()
    original_route = module.route_completed_battle
    def broken(tx, result, world_id):
        original_route(tx, result, world_id)
        raise RuntimeError('Controlled routing write failure')
    monkeypatch.setattr(module, 'route_completed_battle', broken)
    before = deepcopy(repo._data)
    with pytest.raises(RuntimeError):
        repo.finalize_battle(started['id'])
    assert repo._data == before
    monkeypatch.setattr(module, 'route_completed_battle', original_route)
    result = repo.finalize_battle(started['id'])
    assert result['status'] == 'completed'
    placements = [p for p in repo._data['colonyPlacements'].values() if p['battle_id'] == result['id']]
    assert len(placements) == 2 and {p['colony_id'] for p in placements} == {'winners', 'losers'}
    expected = result['fighters'][result['winner_slot']]['object_type']
    store.advance()
    assert actor(store, expected)['object_type'] == expected
    assert len(repo.world()['characters']) == 2


@pytest.mark.parametrize('kind,allowed,denied', [
    ('bag', 'carry', 'water'), ('box', 'carry', 'water'), ('basket', 'carry', 'water'),
    ('mug', 'water', 'charge'), ('bottle', 'water', 'plan'), ('phone', 'signal', 'charge'),
    ('lamp', 'signal', 'charge'), ('power bank', 'charge', 'signal'), ('pencil', 'plan', 'water'),
    ('pitcher', 'water', 'charge'), ('jug', 'water', 'charge'), ('kettle', 'water', 'charge'),
    ('watering can', 'water', 'charge'), ('TV', 'signal', 'charge'), ('television', 'signal', 'charge'),
    ('monitor', 'signal', 'charge'), ('microwave', 'forage', 'charge')])
def test_capabilities_have_physical_sources_and_never_promote_generic_actions(kind, allowed, denied):
    profile = capability_profile({'object_type': kind, 'canonical_type_id': kind})
    assert allowed in profile['allowed_actions'] and denied not in profile['allowed_actions']
    assert profile['action_yields']['forage'] == {'materials': 1}
    assert profile['action_yields']['explore'] == {'materials': 1}
    if kind == 'lamp':
        assert 'store_energy' not in profile['capabilities'] and profile['role'] == 'Lookout light'
    if kind == 'power bank':
        assert profile['action_yields']['charge'] == {'energy': 3}
        assert 'dock' in profile['goal']


def test_capability_denial_sender_binding_and_cross_colony_references_roll_back(colony):
    repo, store, _ = colony
    store.initialize()
    pencil, bottle = actor(store, 'pencil'), actor(store, 'bottle')
    bad = [({'action': 'water'}, 'capability_denied'),
           ({'action': 'plan', 'resources': {'water': 99}}, 'invalid_agent_decision'),
           ({'message': {'kind': 'request', 'resource': 'water', 'quantity': 2, 'actor_id': bottle['id']}}, 'invalid_agent_decision')]
    for decision, expected in bad:
        before = deepcopy(repo._data)
        with pytest.raises(StoreError) as exc:
            store.apply_decision('winners', pencil['id'], decision, 'invalid')
        assert exc.value.code == expected and repo._data == before
    with pytest.raises(StoreError) as exc:
        store.apply_decision('losers', pencil['id'], {'action': 'plan'}, 'wrong-side')
    assert exc.value.code == 'actor_not_found'
    request = store.apply_decision('winners', pencil['id'], {'message': {'kind': 'request', 'resource': 'water', 'quantity': 3}}, 'water-request')
    request_id = request['decision']['board_ids'][0]
    phone = actor(store, 'phone', 'losers')
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        store.apply_decision('losers', phone['id'], {'action': 'signal', 'claim_request_id': request_id}, 'cross-side')
    assert exc.value.code == 'request_not_found' and repo._data == before


def test_model_claim_controls_next_work_and_real_receipts_fulfill_request_once(colony):
    repo, store, clock = colony
    store.initialize()
    pencil, bottle = actor(store, 'pencil'), actor(store, 'bottle')
    request = store.apply_decision('winners', pencil['id'], {'message': {'kind': 'request', 'resource': 'water', 'quantity': 3}}, 'need-water')['decision']
    request_id = request['board_ids'][0]
    current = deepcopy(bottle['task'])
    decision = {'action': 'water', 'claim_request_id': request_id, 'reason': 'My bottle can supply the pencil.'}
    accepted = store.apply_decision('winners', bottle['id'], decision, 'supply-water')
    assert actor(store, 'bottle')['task'] == current
    assert actor(store, 'bottle')['assignment'] == 'water'
    assert actor(store, 'bottle')['active_commitment']['request_id'] == request_id
    before = deepcopy(repo._data)
    assert store.apply_decision('winners', bottle['character_id'], decision, 'supply-water') == accepted
    assert repo._data == before
    with pytest.raises(StoreError) as exc:
        store.apply_decision('winners', bottle['id'], {'action': 'rest'}, 'supply-water')
    assert exc.value.code == 'decision_conflict'
    with pytest.raises(StoreError) as exc:
        command(store, 'assign', 'manual-conflict', character_id=bottle['character_id'], assignment='rest')
    assert exc.value.code == 'commitment_busy'
    clock.advance(40); store.advance()
    fulfilled = repo._data['colonyBoard'][request_id]
    assert fulfilled['status'] == 'fulfilled' and fulfilled['remaining'] == 0
    links = [r for r in repo._data['colonyContributions'].values() if r['request_id'] == request_id]
    assert sum(link['quantity'] for link in links) == 3
    for link in links:
        receipt = repo._data['islandEvents'][link['receipt_id']]
        assert receipt['decision_id'] == accepted['decision']['id']
        assert receipt['resource_delta']['water'] >= link['quantity']
        assert receipt['world_id'] == colony_world_id(repo.world_id, 'winners')
    reports = [r for r in side(store)['board'] if r['kind'] == 'report' and r.get('request_id') == request_id]
    assert reports and all(r['verified'] and r['receipt_ids'] for r in reports)
    assert side(store)['metrics']['fulfilled_requests'] >= 1
    before = deepcopy(repo._data)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: ColoniesStore(repo).advance(), range(12)))
    assert repo._data == before


def test_competing_claims_have_one_owner_and_no_duplicate_commitment(colony):
    repo, store, _ = colony
    store.initialize()
    pencil = actor(store, 'pencil')
    request_id = store.apply_decision('winners', pencil['id'], {'message': {'kind': 'request', 'resource': 'water', 'quantity': 2}}, 'one-request')['decision']['board_ids'][0]
    def claim(kind):
        try:
            return store.apply_decision('winners', actor(store, kind)['id'], {'action': 'water', 'claim_request_id': request_id}, 'claim-' + kind)
        except StoreError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, ('bottle', 'mug')))
    assert sum(isinstance(result, dict) for result in outcomes) == 1
    assert 'request_unavailable' in outcomes
    assert len([r for r in repo._data['colonyCommitments'].values() if r['request_id'] == request_id]) == 1


def test_reports_require_actor_owned_executor_evidence_and_do_not_trust_model_prose(colony):
    repo, store, clock = colony
    store.initialize(); clock.advance(20); store.advance()
    pencil, bottle = actor(store, 'pencil'), actor(store, 'bottle')
    own = next(r for r in repo._data['islandEvents'].values() if r.get('sequence') and r.get('character_id') == pencil['character_id'])
    other = next(r for r in repo._data['islandEvents'].values() if r.get('sequence') and r.get('character_id') == bottle['character_id'])
    for invalid in ('invented-receipt', other['id']):
        before = deepcopy(repo._data)
        with pytest.raises(StoreError) as exc:
            store.apply_decision('winners', pencil['id'], {'message': {'kind': 'report', 'receipt_id': invalid}}, 'fake-report')
        assert exc.value.code == 'invalid_report_evidence' and repo._data == before
    accepted = store.apply_decision('winners', pencil['id'], {'message': {'kind': 'report', 'receipt_id': own['id'], 'text': 'I invented unlimited water.'}}, 'real-report')['decision']
    report = repo._data['colonyBoard'][accepted['board_ids'][0]]
    assert report['text'] == own['description'] and report['verified']
    assert report['interpretation'] == 'I invented unlimited water.'


def test_manual_price_estimate_is_descriptive_idempotent_and_isolated(colony):
    repo, store, _ = colony
    store.initialize()
    selected = actor(store, 'pencil')
    before_islands = deepcopy(repo._data['islandState'])
    before_agents = deepcopy(repo._data['islandAgents'])
    before_placements = deepcopy(repo._data['colonyPlacements'])
    assert side(store)['metrics']['estimated_total_gbp'] is None
    command(store, 'value', 'price-estimate', character_id=selected['character_id'], estimated_value_gbp=12.345)
    command(store, 'value', 'price-estimate', character_id=selected['character_id'], estimated_value_gbp=12.345)
    metrics = side(store)['metrics']
    assert metrics['estimated_total_gbp'] == metrics['estimated_mean_gbp'] == 12.35
    assert metrics['valued_residents'] == 1 and metrics['unknown_value_residents'] == 2
    assert metrics['market_value'] is None and side(store, 'losers')['metrics']['estimated_total_gbp'] is None
    assert repo._data['islandState'] == before_islands and repo._data['islandAgents'] == before_agents
    assert repo._data['colonyPlacements'] == before_placements
    resident = repo._data['colonyResidents'][selected['character_id']]
    assert resident['valuation_provenance']['kind'] == 'user_estimate' and resident['market_price'] is None
    with pytest.raises(StoreError):
        command(store, 'value', 'price-estimate', character_id=selected['character_id'], estimated_value_gbp=100)


def test_capability_gaps_do_not_turn_into_magical_resources_and_pause_is_isolated(colony):
    repo, store, clock = colony
    store.initialize()
    # Winner crew has no battery; loser crew has no water container.
    assert 'energy' in side(store)['metrics']['capability_gaps']
    assert 'water' in side(store, 'losers')['metrics']['capability_gaps']
    command(store, 'pause', 'pause-winners')
    frozen = deepcopy(side(store)['island'])
    for _ in range(30):
        clock.advance(20); store.advance()
    after = side(store)['island']
    assert after['completed_actions'] == frozen['completed_actions']
    assert after['resources'] == frozen['resources']
    assert side(store, 'losers')['island']['completed_actions'] > 10
    scope = colony_world_id(repo.world_id, 'losers')
    assert not any(r.get('resource_delta', {}).get('water', 0) for r in repo._data['islandEvents'].values() if r.get('world_id') == scope)
    before = deepcopy(repo._data)
    assert ColoniesStore(repo).snapshot() == store.snapshot() and repo._data == before


def test_deterministic_cooperation_produces_receipts_and_bounded_progress(colony):
    repo, store, clock = colony
    store.initialize()
    for _ in range(20):
        clock.advance(20); store.advance()
    metrics = side(store)['metrics']
    assert metrics['fulfilled_requests'] > 0 and metrics['cooperative_deliveries'] > 0
    assert metrics['project_levels'] > 0
    assert not repo._data.get('colonyDecisions')
    for row in repo._data['colonyContributions'].values():
        receipt = repo._data['islandEvents'][row['receipt_id']]
        assert 0 < row['quantity'] <= receipt['resource_delta'][row['resource']]
        assert row['world_id'] == receipt['world_id']
    for colony in store.snapshot()['colonies']:
        assert all(0 <= value <= 1000 for value in colony['island']['resources'].values())
        assert all(0 <= project['progress'] + project['reserved_progress'] <= project['required_progress'] for project in colony['island']['projects'])


def test_active_requests_expire_even_when_recent_board_is_full(colony):
    repo, store, clock = colony
    store.initialize()
    pencil = actor(store, 'pencil')
    request_id = store.apply_decision('winners', pencil['id'], {'message': {'kind': 'request', 'resource': 'energy', 'quantity': 4}}, 'no-energy')['decision']['board_ids'][0]
    island = store.islands['winners']
    # A busy board cannot hide an older still-open commitment from authority queries.
    def fill(tx):
        saved_actor = tx.get('islandAgents', pencil['id'])
        for index in range(300):
            island._new_board(tx, saved_actor, 'report', clock.value + timedelta(seconds=1), f'fixture-report-{index}', text='Fixture history.')
    island.repo.transaction(fill)
    assert request_id in {r['id'] for r in store.observation('winners', pencil['id'])['board']}
    clock.advance(301); store.advance()
    assert repo._data['colonyBoard'][request_id]['status'] == 'expired'
    assert len(side(store)['board']) <= 80


def test_player_assignment_cannot_be_overwritten_by_model_and_can_be_released(colony):
    repo, store, _ = colony
    store.initialize()
    pencil = actor(store, 'pencil')
    command(store, 'assign', 'manual-work', character_id=pencil['character_id'], assignment='rest')
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        store.apply_decision('winners', pencil['id'], {'action': 'plan'}, 'model-override')
    assert exc.value.code == 'player_assignment' and repo._data == before
    command(store, 'assign', 'manual-release', character_id=pencil['character_id'], assignment='auto')
    store.apply_decision('winners', pencil['id'], {'action': 'plan'}, 'model-override')
    assert actor(store, 'pencil')['assignment'] == 'plan'


def test_profile_upgrade_adds_real_identity_synonyms_once_without_resetting_life(colony):
    from app.agent_sdk import SDK_VERSION
    repo, store, clock = colony
    battle(repo, 'new-live-identities', 'pitcher', 'TV')
    store.initialize()
    pitcher, television = actor(store, 'pitcher'), actor(store, 'TV', 'losers')
    def old_version(tx):
        for current in (pitcher, television):
            old = tx.get('islandAgents', current['id'])
            old['sdk_version'] = 'colony-capabilities-v1'
            old['allowed_actions'] = ['forage', 'build', 'rest', 'explore']
            old['action_yields'] = {'forage': {'materials': 1}, 'explore': {'materials': 1}}
            old['persona'].update(role='Resource scout', preferred_action='explore')
            old['xp'] = 96
            old['display_name'] = 'A nickname without source-identity clues'
            tx.put('islandAgents', old)
    repo.transaction(old_version)
    before = deepcopy(repo._data)
    assert actor(store, 'pitcher')['sdk_version'] == 'colony-capabilities-v1'  # GET cannot migrate.
    store.advance()
    updated_pitcher, updated_tv = actor(store, 'pitcher'), actor(store, 'TV', 'losers')
    assert updated_pitcher['sdk_version'] == updated_tv['sdk_version'] == SDK_VERSION
    assert updated_pitcher['persona']['role'] == 'Water keeper' and 'water' in updated_pitcher['allowed_actions']
    assert updated_tv['persona']['role'] == 'Observation scout' and updated_tv['action_yields']['signal'] == {'ideas': 3}
    for updated, original in ((updated_pitcher, pitcher), (updated_tv, television)):
        assert updated['id'] == original['id'] and updated['character_id'] == original['character_id']
        assert updated['task'] == original['task'] and updated['xp'] == 96
    for name in ('battles', 'colonyResidents', 'colonyPlacements', 'worlds'):
        assert repo._data[name] == before[name]
    migrated = deepcopy(repo._data)
    store.advance(); store.initialize()
    assert repo._data == migrated
    migrations = [r for r in repo._data['islandEvents'].values() if r['kind'] == 'capability_profile']
    assert len(migrations) == 2
