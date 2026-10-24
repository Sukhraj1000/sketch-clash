"""Local unit and statistical checks; this suite cannot call a provider."""
from copy import deepcopy

import pytest

from app.combat_fixtures import fixture_profile, get_catalog
from app.combat_v2 import RULES, _active_rules, _simulate, price_percent, simulate_v2, validate_profile


@pytest.fixture(scope='module')
def roster():
    return get_catalog()['fixtures']


def test_catalog_profiles_are_independent_validated_illustrations(roster):
    assert len(roster) == 12 and len(RULES) >= 10
    for profile in roster:
        validate_profile(profile)
        assert sum(profile['stats'].values()) == 20 and profile['health'] == 100
        assert profile['price']['source'] == 'sample_fixture'
        assert profile['provenance']['kind'] == 'curated_fixture'
    copy = fixture_profile(roster[0]['id'])
    copy['name'] = 'Changed copy'
    assert fixture_profile(roster[0]['id'])['name'] != 'Changed copy'


@pytest.mark.parametrize('field,value', [('health', 101), ('stats', {'impact': 8, 'resilience': 8, 'agility': 8, 'control': 8}), ('traits', ['electric_attack'])])
def test_unearned_capabilities_and_budgets_rejected(field, value):
    profile = fixture_profile('ceramic-mug')
    profile[field] = value
    with pytest.raises(ValueError):
        validate_profile(profile)


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True])
def test_invalid_price_rejected(value):
    profile = fixture_profile('ceramic-mug')
    profile['price']['amount_gbp'] = value
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_missing_price_is_neutral_for_both_fighters():
    profiles = [fixture_profile('ceramic-mug'), fixture_profile('smartphone')]
    profiles[0]['price']['amount_gbp'] = None
    result = simulate_v2(profiles, 42)
    assert all(e['receipt']['price_percent'] == 0 for e in result['events'])
    assert result['counterfactual']['without_price']['changed_winner'] is False


def test_outlier_price_is_capped():
    profile = fixture_profile('smartphone')
    profile['price']['amount_gbp'] = 250
    capped = price_percent(profile)
    profile['price']['amount_gbp'] = 10**12
    assert price_percent(profile) == capped == 1


@pytest.mark.parametrize('charges,evidence', [(0, 'curated_fixture'), (2, 'unknown'), (100, 'confirmed'), (True, 'confirmed')])
def test_unverified_or_infinite_water_is_rejected(charges, evidence):
    profile = fixture_profile('filled-water-jug')
    profile['resources'] = {'water_charges': charges, 'water_evidence': evidence}
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_water_depletes_and_empty_objects_never_splash():
    jug = fixture_profile('filled-water-jug')
    book = fixture_profile('hardback-book')
    result = simulate_v2([jug, book], 42)
    splashes = [e for e in result['events'] if e['attacker'] == 0 and any(r['id'] == 'splash-absorbent' for r in e['receipt']['interaction_rules'])]
    assert [e['receipt']['round'] for e in splashes] == [1, 2]
    assert [(e['receipt']['water_charges_before'], e['receipt']['water_charges_after']) for e in splashes] == [(2, 1), (1, 0)]
    neutral = simulate_v2([jug, fixture_profile('ceramic-mug')], 42)
    jug_events = [e for e in neutral['events'] if e['attacker'] == 0]
    assert [e['word'] for e in jug_events[:2]] == ['SPLASH!', 'SPLASH!']
    assert all(e['word'] != 'SPLASH!' for e in jug_events[2:])
    for identifier in ('ceramic-mug', 'steel-bottle'):
        empty = simulate_v2([fixture_profile(identifier), book], 42)
        assert all(not r['id'].startswith('splash-') for e in empty['events'] for r in e['receipt']['interaction_rules'])


@pytest.mark.parametrize('rule', RULES, ids=[r['id'] for r in RULES])
def test_every_conditional_rule_triggers_only_with_required_traits(rule):
    attacker, defender = fixture_profile('ceramic-mug'), fixture_profile('steel-bottle')
    attacker['traits'] = [rule['attacker_trait']]
    defender['traits'] = [rule['defender_trait']]
    attacker['resources'] = {'water_charges': 2, 'water_evidence': 'confirmed'}
    round_number = rule.get('min_round', 1)
    assert rule['id'] in [r['id'] for r in _active_rules(attacker, defender, round_number)]
    attacker['traits'] = []
    assert not _active_rules(attacker, defender, round_number)


def test_positive_and_negative_rules_do_not_stack():
    attacker, defender = fixture_profile('metal-whisk'), fixture_profile('ceramic-mug')
    attacker['traits'] = ['long_reach', 'precision', 'rigid_hard', 'hooking']
    defender['traits'] = ['brittle', 'looped', 'unwieldy', 'cushioned', 'stable_base', 'close_grip']
    rules = _active_rules(attacker, defender, 1)
    assert len([r for r in rules if r['percent'] > 0]) == 1
    assert len([r for r in rules if r['percent'] < 0]) == 1


def test_range_and_health_caps_are_accounted_for():
    jug, sponge = fixture_profile('filled-water-jug'), fixture_profile('kitchen-sponge')
    jug['stats'] = {'impact': 8, 'resilience': 1, 'agility': 3, 'control': 8}
    sponge['stats'] = {'impact': 6, 'resilience': 1, 'agility': 5, 'control': 8}
    jug['price']['amount_gbp'] = 250
    saw_range_cap = saw_health_cap = False
    for seed in range(50):
        result = simulate_v2([jug, sponge], seed, include_analysis=False)
        for event in result['events']:
            r = event['receipt']
            assert r['rounded_damage'] == pytest.approx(r['unrounded_damage'] + r['rounding_adjustment'])
            assert r['damage_before_health_cap'] == r['rounded_damage'] + r['damage_range_adjustment']
            assert event['damage'] == r['damage_before_health_cap'] + r['health_cap_adjustment']
            saw_range_cap |= r['damage_range_adjustment'] != 0
            saw_health_cap |= r['health_cap_adjustment'] != 0
    assert saw_range_cap and saw_health_cap


def test_seeded_replay_arithmetic_receipts_and_counterfactuals(roster):
    for seed in range(30):
        profiles = [roster[seed % 12], roster[(seed * 7 + 3) % 12]]
        frozen = deepcopy(profiles)
        result = simulate_v2(profiles, seed)
        assert result == simulate_v2(profiles, seed)
        assert profiles == frozen
        health = [100, 100]
        for event in result['events']:
            r = event['receipt']
            assert r['unrounded_damage'] == pytest.approx(r['base_damage'] + r['stat_adjustment'] + r['interaction_damage'] + r['price_damage'] + r['luck'])
            assert r['damage_before_cap'] == pytest.approx(r['unrounded_damage'] + r['rounding_adjustment'])
            target = 1 - event['attacker']
            assert r['health_before'] == health[target]
            health[target] -= event['damage']
            assert health[target] == r['health_after']
            assert 1 <= event['damage'] <= 25
            assert abs(r['interaction_percent']) <= 20
            assert 0 <= r['price_percent'] <= 1
            assert -3 <= r['luck'] <= 3
        assert health == result['final_health']
        assert len(result['events']) % 2 == 0
        for key, prices, interactions in [('without_price', False, True), ('without_interactions', True, False)]:
            replay = _simulate(profiles, seed, with_price=prices, with_interactions=interactions)
            assert result['counterfactual'][key]['winner_slot'] == replay['winner_slot']
            assert result['counterfactual'][key]['changed_winner'] == (result['winner_slot'] != replay['winner_slot'])


def test_swapping_slots_preserves_identity_randomness(roster):
    for seed in range(300):
        a, b = roster[seed % 12], roster[(seed + 5) % 12]
        normal = _simulate([a, b], seed, with_price=True, with_interactions=True)
        swapped = _simulate([b, a], seed, with_price=True, with_interactions=True)
        assert normal['winner_slot'] == 1 - swapped['winner_slot']
        assert normal['final_health'] == list(reversed(swapped['final_health']))
        assert [e['damage'] for e in normal['events']] == [e['damage'] for e in swapped['events']]


def test_mirror_fairness_over_thousands_of_seeds():
    fixture = fixture_profile('rubber-ball')
    wins = sum(_simulate([fixture, fixture], seed, with_price=True, with_interactions=True)['winner_slot'] == 0 for seed in range(10000))
    assert .48 <= wins / 10000 <= .52


def test_inexpensive_material_counter_survives_maximum_opponent_price():
    sponge, bottle = fixture_profile('kitchen-sponge'), fixture_profile('steel-bottle')
    sponge['price']['amount_gbp'] = 0
    bottle['price']['amount_gbp'] = 250
    wins = sum(_simulate([sponge, bottle], seed, with_price=True, with_interactions=True)['winner_slot'] == 0 for seed in range(1000))
    assert .60 <= wins / 1000 <= .80


def test_price_only_uplift_stays_small_against_reference_roster(roster):
    low, high = fixture_profile('foam-block'), fixture_profile('foam-block')
    low['price']['amount_gbp'], high['price']['amount_gbp'] = 0, 250
    improvement = 0
    comparisons = 0
    for opponent in roster:
        if opponent['id'] == low['id']:
            continue
        for seed in range(500):
            before = _simulate([low, opponent], seed, with_price=True, with_interactions=True)['winner_slot']
            after = _simulate([high, opponent], seed, with_price=True, with_interactions=True)['winner_slot']
            improvement += int(after == 0) - int(before == 0)
            comparisons += 1
    assert 0 <= improvement / comparisons <= .05


def test_points_and_simultaneous_ties_do_not_fabricate_final_hits():
    profiles = [fixture_profile('kitchen-sponge'), fixture_profile('foam-block')]
    results = [_simulate(profiles, seed, with_price=True, with_interactions=True) for seed in range(100)]
    points = [r for r in results if r['outcome'] == 'points']
    assert points
    assert all(min(r['final_health']) > 0 and len(r['events']) == 20 for r in points)
    assert all(not any(e['id'] == 'decision' for e in r['events']) for r in results)


def test_double_knockout_uses_recorded_impact_points_before_seed():
    profiles = [fixture_profile('wooden-spoon'), fixture_profile('wooden-ruler')]
    saw_points_tiebreak = saw_seed_tiebreak = False
    for seed in range(300):
        result = simulate_v2(profiles, seed, include_analysis=False)
        assert result['impact_points'] == [sum(e['receipt']['damage_before_health_cap'] for e in result['events'] if e['attacker'] == slot) for slot in (0, 1)]
        if result['tiebreak_reason'] == 'impact_points':
            saw_points_tiebreak = True
            assert result['final_health'] == [0, 0]
            assert result['impact_points'][result['winner_slot']] > result['impact_points'][1 - result['winner_slot']]
            assert 'impact points' in result['explanation']['summary']
        elif result['tiebreak_reason'] == 'seed':
            saw_seed_tiebreak = True
            assert result['impact_points'][0] == result['impact_points'][1]
    assert saw_points_tiebreak and saw_seed_tiebreak
