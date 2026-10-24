"""Capture combat integration with controlled evidence; no provider or Atlas writes."""
from copy import deepcopy

import pytest

from backend.app.camera_combat import capture_profile, simulate_capture_battle
from backend.app.combat_v2 import simulate_v2, validate_profile
from backend.app.config import Settings
from backend.app.contracts import Battle, Observation
from backend.app.engine import PRESETS, simulate_match
from backend.app.images import normalize_image
from backend.app.repository import MemoryRepository, StoreError, key_for
from backend.tests.test_lifecycle import Clock, fighter, photo, ready


def object_fighter(features=(), *, label='object', slot=0, archetype='Quick'):
    settings = Settings(repository='memory')
    image = normalize_image(photo('red' if slot == 0 else 'blue'), 'image/png', settings)
    item = fighter('capture-battle', slot, 'capture-' + str(slot), image, 'mug')
    item.update(observed_object={'label': label, 'visible_features': list(features)},
                archetype=archetype, stats=deepcopy(PRESETS[archetype]))
    return item


def test_realistic_mug_and_tumbler_use_body_evidence_not_presets_or_background():
    mug = capture_profile(object_fighter([
        'cylindrical ceramic body', 'prominent curved side handle', 'wide top circular rim opening',
        'off-white / cream glazed surface', 'resting on light brown wooden or laminate tabletop']), confirmed=True)
    bottle = capture_profile(object_fighter([
        'gradient light-to-medium blue matte finish', 'cylindrical insulated tumbler/bottle body',
        'light blue flip lid with drink spout cover', 'sturdy side carry handle'], slot=1), confirmed=True)
    assert {'rigid_hard', 'brittle', 'close_grip', 'looped', 'smooth'} <= set(mug['traits'])
    assert bottle['traits'] == ['close_grip', 'looped']
    assert mug['stats'] != bottle['stats']
    assert 'resting on light brown wooden or laminate tabletop' in mug['provenance']['omitted_features']
    for profile in (mug, bottle):
        validate_profile(profile)
        assert sum(profile['stats'].values()) == 20
        assert profile['resources']['water_charges'] == 0
        assert profile['price']['amount_gbp'] is None


@pytest.mark.parametrize('feature', [
    'not glass', 'no handle', 'without a flat base', 'could be ceramic or plastic',
    'maybe metal', 'unknown material', 'ceramic-looking finish', 'faux metal',
    'smooth wooden tabletop behind the mug', 'background rubber ball',
    'resting on a glass table', 'not water resistant', 'possibly a spherical body',
    'non-absorbent plastic surface', 'glass-free screen',
    'ceramic body ' + 'with decorative details ' * 12 + 'but possibly plastic',
])
def test_negative_uncertain_and_background_properties_do_not_award_traits(feature):
    profile = capture_profile(object_fighter([feature]), confirmed=True)
    assert profile['traits'] == []
    assert set(profile['stats'].values()) == {5}


def test_conflicting_claims_and_cosmetic_identity_cannot_award_traits_or_value():
    item = object_fighter(['glass body', 'not glass'])
    item.update(display_name='Expensive steel water blaster', object_type='water bottle',
                canonical_type_id='bottle', price={'amount_gbp': 10000})
    item['visual_spec']['accessories'] = ['handle', 'leaf']
    profile = capture_profile(item, {'evidence': {'ocr': {'text': ['metal filled with water']}}}, confirmed=True)
    assert profile['traits'] == []
    assert profile['price']['amount_gbp'] is None
    assert profile['resources']['water_charges'] == 0
    unknown = capture_profile(object_fighter([], label='water bottle'), confirmed=True)
    assert unknown['traits'] == []


def test_uncertainty_vetoes_properties_and_empty_accepted_features_stay_empty():
    item = object_fighter(['ceramic body', 'curved side handle'])
    profile = capture_profile(item, {'uncertainty': ['Material could be plastic']}, confirmed=True)
    assert profile['traits'] == ['close_grip', 'looped']
    assert profile['provenance']['uncertainty'] == ['Material could be plastic']
    empty = capture_profile(object_fighter([]), {'visible_features': ['ceramic body']}, confirmed=True)
    assert empty['traits'] == []
    depicted = capture_profile(object_fighter(['visible water printed on the label', 'open top']), confirmed=True)
    assert depicted['resources']['water_charges'] == 0
    knob = capture_profile(object_fighter(['spherical knob on a box']), confirmed=True)
    assert 'round_roll' not in knob['traits']


def test_materials_come_from_capture_not_canonical_mug_defaults():
    ceramic = capture_profile(object_fighter(['ceramic body']))
    steel = capture_profile(object_fighter(['steel body']))
    mystery = capture_profile(object_fighter([]))
    assert 'brittle' in ceramic['traits'] and 'brittle' not in steel['traits']
    assert 'water_resistant' in steel['traits']
    assert mystery['traits'] == []
    changed = object_fighter(['steel body'], archetype='Power')
    assert capture_profile(changed)['stats'] == steel['stats']


@pytest.mark.parametrize('features,confirmed,charges', [
    (['visible water inside', 'open spout'], True, 2),
    (['visible water inside', 'open spout'], False, 0),
    (['filled with water'], True, 0),
    (['open spout'], True, 0),
    (['visible water inside', 'open spout', 'closed cap'], True, 0),
    (['visible water inside', 'open spout', 'empty container'], True, 0),
    (['visible water inside', 'open spout', 'no water'], True, 0),
    (['possibly visible water', 'open spout'], True, 0),
    (['visible water frozen into ice', 'open spout'], True, 0),
])
def test_water_requires_accepted_visible_supply_and_open_access(features, confirmed, charges):
    profile = capture_profile(object_fighter(features), confirmed=confirmed)
    assert profile['resources']['water_charges'] == charges
    assert ('water_splash' in profile['traits']) == bool(charges)


def test_every_supported_trait_combination_keeps_equal_stat_budget():
    phrases = ['ceramic body', 'steel body', 'sponge body', 'foam padding', 'rubber surface',
        'long handle', 'curved side handle', 'broad base', 'flat face', 'spherical body',
        'fine point', 'loose loop', 'bulky body', 'grippy surface']
    for count in range(len(phrases) + 1):
        for rotation in range(len(phrases)):
            features = (phrases[rotation:] + phrases[:rotation])[:count]
            profile = capture_profile(object_fighter(features), confirmed=True)
            validate_profile(profile)
            assert sum(profile['stats'].values()) == 20
            assert all(1 <= value <= 8 for value in profile['stats'].values())


@pytest.mark.parametrize('mode,duration', [('normal', 12800), ('reduced', 12800), ('quick', 6400)])
def test_capture_simulation_preserves_receipts_price_neutrality_and_timing(mode, duration):
    items = [object_fighter(['ceramic body', 'curved side handle']),
             object_fighter(['steel body', 'smooth surface'], slot=1)]
    result = simulate_capture_battle(items, [{}, {}], 73, mode)
    assert result['duration_ms'] == duration
    assert result['events'][-1]['at'] < duration
    assert result['explanation']['summary']
    assert result['price_policy']['kind'] == 'unknown_capture_prices'
    assert 'illustrative' not in result['explanation']['price_note']
    assert all(event['receipt']['price_percent'] == 0 for event in result['events'])
    assert not result['counterfactual']['without_price']['changed_winner']
    assert result['counterfactual']['without_price']['final_health'] == result['final_health']
    replay = simulate_v2(result['fighters'], result['seed'])
    assert replay['winner_slot'] == result['winner_slot']
    assert replay['final_health'] == result['final_health']
    assert [e['receipt'] for e in replay['events']] == [e['receipt'] for e in result['events']]


def test_new_camera_start_freezes_profiles_receipts_and_routes_actual_winner_once(monkeypatch):
    settings = Settings(repository='memory', world_id='capture-combat-test')
    clock = Clock()
    repo = MemoryRepository(settings, clock)
    battle = ready(repo, settings)
    # Controlled accepted evidence, as provided by RecognitionService in production.
    def add_evidence(tx):
        saved = tx.get('battles', battle['id'])
        for slot, features in enumerate((['ceramic body', 'curved side handle'], ['steel body', 'smooth surface'])):
            saved['pending_fighters'][slot]['observed_object'] = {'label': 'object', 'visible_features': features}
        tx.put('battles', saved)
    repo.transaction(add_evidence)
    monkeypatch.setattr('backend.app.repository.secrets.randbelow', lambda _: 73)
    started = repo.start_battle(battle['id'], 'quick')
    Battle.model_validate(started)
    assert started['engine_version'] == 'object-combat-2'
    assert started['combat']['events'] == started['events']
    assert started['combat']['winner_slot'] == started['winner_slot']
    assert started['fighters'][0]['canonical_type_id'] == 'mug'
    assert started['fighters'][1]['canonical_type_id'] == 'bottle'
    assert started['fighters'][0]['combat_profile'] == started['combat']['fighters'][0]
    frozen = deepcopy(started)
    started['combat']['fighters'][0]['traits'].clear()
    assert repo.get_battle(battle['id']) == frozen
    monkeypatch.setattr('backend.app.repository.simulate_capture_battle', lambda *_: pytest.fail('saved battle was recalculated'))
    assert repo.start_battle(battle['id'], 'normal') == frozen
    with pytest.raises(StoreError, match='playback'):
        repo.finalize_battle(battle['id'])
    clock.advance(6400)
    completed = repo.finalize_battle(battle['id'])
    assert completed['combat'] == frozen['combat']
    before = deepcopy(repo._data)
    assert repo.finalize_battle(battle['id']) == completed
    assert repo._data == before
    residents = list(repo._data['colonyResidents'].values())
    assert len(residents) == 2
    winner = frozen['fighters'][frozen['winner_slot']]['canonical_type_id']
    assert next(row for row in residents if row['colony_id'] == 'winners')['canonical_type_id'] == winner


def test_old_running_and_completed_battles_keep_their_original_engine_and_placements(monkeypatch):
    settings = Settings(repository='memory', world_id='legacy-capture-test')
    clock = Clock()
    repo = MemoryRepository(settings, clock)
    battle = ready(repo, settings)
    def store_legacy(tx):
        saved = tx.get('battles', battle['id'])
        fighters = deepcopy(saved['pending_fighters'])
        saved.update(simulate_match(fighters, 42, 'quick'))
        saved.update(status='running', fighters=fighters, started_at=clock(), eligible_at=clock())
        saved.pop('combat', None)
        tx.put('battles', saved)
    repo.transaction(store_legacy)
    old = repo.get_battle(battle['id'])
    monkeypatch.setattr('backend.app.repository.simulate_capture_battle', lambda *_: pytest.fail('legacy battle was recalculated'))
    assert repo.start_battle(battle['id'], 'normal') == old
    completed = repo.finalize_battle(battle['id'])
    assert completed['engine_version'] == 'clash-integer-1'
    assert completed['events'] == old['events']
    assert 'combat' not in completed
    assert repo.start_battle(battle['id'], 'quick') == completed
    assert repo.finalize_battle(battle['id']) == completed


def test_saved_recognition_returns_capture_preview_without_using_provider():
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    battle = repo.create_battle('preview')
    item = object_fighter(['ceramic body', 'curved side handle'])
    item['battle_id'] = battle['id']
    capture = {'capture_id': item['capture_id'], 'player_slot': 0, 'source': 'upload',
        'image_hash': item['image_hash'], 'width': 120, 'height': 90, 'crop': None}
    repo.begin_capture(battle['id'], capture)
    observation = Observation.model_validate({**{k: v for k, v in capture.items() if k != 'player_slot'}, 'image_ref': item['image_ref'],
        'status': 'recognized', 'pending_fighter': item}).model_dump()
    saved = repo.finish_capture(battle['id'], item['capture_id'], observation)
    assert saved['pending_fighter']['combat_profile']['provenance']['kind'] == 'capture_preview'
    assert 'brittle' in saved['pending_fighter']['combat_profile']['traits']
    assert repo.finish_capture(battle['id'], item['capture_id'], observation) == saved
    assert repo.get_capture(battle['id'], item['capture_id'])['observation'] == saved
