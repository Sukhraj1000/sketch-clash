"""Deterministic cartoon object combat. No network calls and no model-selected winner."""
from copy import deepcopy
from hashlib import sha256
from math import isfinite, log1p
from typing import Any

ENGINE_VERSION = 'object-combat-2'
STAT_NAMES = ('impact', 'resilience', 'agility', 'control')
PRICE_POLICY = {
    'kind': 'sample_comparables', 'max_bonus_percent': 1,
    'saturation_gbp': 250, 'currency': 'GBP',
    'description': 'An illustrative game premium, capped at 1% damage. It does not establish physical quality. If either price is missing, both premiums are disabled.',
}
RULES = [
    {'id': 'hard-on-brittle', 'name': 'Brittle surface', 'attacker_trait': 'rigid_hard', 'defender_trait': 'brittle', 'percent': 8, 'description': 'A rigid bump challenges a brittle surface.'},
    {'id': 'cushion-impact', 'name': 'Cushioned impact', 'attacker_trait': 'rigid_hard', 'defender_trait': 'cushioned', 'percent': -8, 'description': 'Soft padding spreads a hard impact.'},
    {'id': 'early-reach', 'name': 'Opening reach', 'attacker_trait': 'long_reach', 'defender_trait': 'close_grip', 'percent': 10, 'max_round': 2, 'description': 'Reach helps before the objects close the gap.'},
    {'id': 'close-control', 'name': 'Close control', 'attacker_trait': 'close_grip', 'defender_trait': 'long_reach', 'percent': 5, 'min_round': 3, 'description': 'A secure short grip becomes useful once the gap closes.'},
    {'id': 'rolling-bump', 'name': 'Rolling bump', 'attacker_trait': 'round_roll', 'defender_trait': 'flat_contact', 'percent': 8, 'description': 'A rolling body can get underneath a flat contact edge.'},
    {'id': 'grip-stops-roll', 'name': 'Traction slows roll', 'attacker_trait': 'round_roll', 'defender_trait': 'grippy', 'percent': -8, 'description': 'A grippy surface absorbs rolling momentum.'},
    {'id': 'splash-absorbent', 'name': 'Water load', 'attacker_trait': 'water_splash', 'defender_trait': 'absorbent', 'percent': 18, 'max_round': 2, 'description': 'Stored water adds a load to an absorbent material. Only two splashes are available.'},
    {'id': 'splash-resistant', 'name': 'Water-resistant surface', 'attacker_trait': 'water_splash', 'defender_trait': 'water_resistant', 'percent': -12, 'max_round': 2, 'description': 'A water-resistant surface sheds this small splash.'},
    {'id': 'yield-to-precision', 'name': 'Flexible recovery', 'attacker_trait': 'precision', 'defender_trait': 'flexible_recovery', 'percent': -3, 'description': 'A flexible body yields to a precise poke and regains its shape.'},
    {'id': 'redirect-roll', 'name': 'Redirect the roll', 'attacker_trait': 'precision', 'defender_trait': 'round_roll', 'percent': 6, 'description': 'A well-placed tap redirects a predictable rolling path.'},
    {'id': 'precision-on-bulk', 'name': 'Precise placement', 'attacker_trait': 'precision', 'defender_trait': 'unwieldy', 'percent': 10, 'description': 'A controlled tap finds an opening around a bulky body.'},
    {'id': 'brace-reach', 'name': 'Braced base', 'attacker_trait': 'long_reach', 'defender_trait': 'stable_base', 'percent': -2, 'description': 'A broad braced base resists a distant tap.'},
    {'id': 'hook-a-loop', 'name': 'Handle caught', 'attacker_trait': 'hooking', 'defender_trait': 'looped', 'percent': 8, 'description': 'A loose rope loop can catch an exposed handle or loop.'},
    {'id': 'smooth-escape', 'name': 'Smooth escape', 'attacker_trait': 'hooking', 'defender_trait': 'smooth', 'percent': -6, 'description': 'A loose hook slips off a smooth surface.'},
]
KNOWN_TRAITS = {r[key] for r in RULES for key in ('attacker_trait', 'defender_trait')}


def validate_profile(profile: dict[str, Any]) -> None:
    if not isinstance(profile, dict) or not isinstance(profile.get('id'), str) or not profile['id']:
        raise ValueError('An object profile needs a stable id')
    if profile.get('health') != 100:
        raise ValueError('Every arena object starts with exactly 100 health')
    stats = profile.get('stats', {})
    if set(stats) != set(STAT_NAMES) or any(type(stats.get(k)) is not int or not 1 <= stats[k] <= 8 for k in STAT_NAMES):
        raise ValueError('Object stats must be integer impact/resilience/agility/control values from 1 to 8')
    if sum(stats.values()) != 20:
        raise ValueError('Every object must share the same 20-point base budget')
    traits = profile.get('traits', [])
    if not isinstance(traits, list) or len(traits) != len(set(traits)) or not set(traits) <= KNOWN_TRAITS:
        raise ValueError('Object traits must be unique approved capabilities and material properties')
    amount = profile.get('price', {}).get('amount_gbp')
    if amount is not None and (isinstance(amount, bool) or not isinstance(amount, (int, float)) or not isfinite(amount) or amount < 0):
        raise ValueError('Price must be a finite non-negative GBP amount, or unknown')
    resources = profile.get('resources', {})
    charges = resources.get('water_charges', 0)
    if type(charges) is not int or not 0 <= charges <= 2:
        raise ValueError('A stored water supply must have zero, one or two charges')
    if 'water_splash' in traits and (charges == 0 or resources.get('water_evidence') not in ('curated_fixture', 'confirmed')):
        raise ValueError('Water capability requires a confirmed finite water supply')


def price_percent(profile: dict[str, Any]) -> float:
    value = profile.get('price', {}).get('amount_gbp')
    if value is None:
        return 0.0
    return round(PRICE_POLICY['max_bonus_percent'] * min(1, log1p(value) / log1p(PRICE_POLICY['saturation_gbp'])), 6)


def _active_rules(attacker: dict, defender: dict, round_number: int) -> list[dict]:
    matches = [r for r in RULES if r['attacker_trait'] in attacker['traits']
               and r['defender_trait'] in defender['traits']
               and (r['attacker_trait'] != 'water_splash' or round_number <= attacker.get('resources', {}).get('water_charges', 0))
               and r.get('min_round', 1) <= round_number <= r.get('max_round', 10)]
    # A pile of similar labels cannot accumulate free combat power.
    chosen = []
    positive = [r for r in matches if r['percent'] > 0]
    negative = [r for r in matches if r['percent'] < 0]
    if positive:
        chosen.append(sorted(positive, key=lambda r: (-r['percent'], r['id']))[0])
    if negative:
        chosen.append(sorted(negative, key=lambda r: (r['percent'], r['id']))[0])
    return [{'id': r['id'], 'name': r['name'], 'percent': r['percent'], 'reason': r['description']} for r in chosen]


def preview_matchup(profiles: list[dict]) -> list[dict]:
    result = []
    for attacker in (0, 1):
        seen = set()
        for round_number in (1, 3):
            for rule in _active_rules(profiles[attacker], profiles[1 - attacker], round_number):
                if rule['id'] not in seen:
                    source = next(r for r in RULES if r['id'] == rule['id'])
                    result.append({'attacker': attacker, **rule, 'timing': 'Rounds 1–2' if source.get('max_round') == 2 else 'Round 3 onwards' if source.get('min_round') == 3 else 'Every round'})
                    seen.add(rule['id'])
    return result


def _roll(seed: int, actor: str, round_number: int, purpose: str) -> int:
    return int.from_bytes(sha256(f'{ENGINE_VERSION}:{seed}:{actor}:{round_number}:{purpose}'.encode()).digest()[:4], 'big')


def _actors(profiles: list[dict]) -> list[str]:
    # Stable object identities make swapping UI slots preserve each object's random draws.
    if profiles[0]['id'] != profiles[1]['id']:
        return [p['id'] for p in profiles]
    return [f"{profiles[0]['id']}:copy-0", f"{profiles[1]['id']}:copy-1"]


def _simulate(profiles: list[dict], seed: int, *, with_price: bool, with_interactions: bool) -> dict:
    health = [100, 100]
    impact_points = [0, 0]
    events = []
    actors = _actors(profiles)
    order = sorted((0, 1), key=lambda slot: actors[slot])
    for round_number in range(1, 11):
        # Both actions are committed from the same start-of-round state. Animation order gives no free hit.
        round_events = []
        for attacker in order:
            target = 1 - attacker
            fighter, defender = profiles[attacker], profiles[target]
            stats, opposing = fighter['stats'], defender['stats']
            base = 13.0
            stat = round(.60 * (stats['impact'] - opposing['resilience']) + .50 * (stats['control'] - opposing['agility']), 6)
            rules = _active_rules(fighter, defender, round_number) if with_interactions else []
            interaction = max(-20, min(20, sum(r['percent'] for r in rules)))
            interaction_damage = round((base + stat) * interaction / 100, 6)
            # Unknown pricing is neutral for the entire pairing, never a penalty to one object.
            prices_known = all(p.get('price', {}).get('amount_gbp') is not None for p in profiles)
            premium = price_percent(fighter) if with_price and prices_known else 0.0
            price_damage = round((base + stat + interaction_damage) * premium / 100, 6)
            luck = _roll(seed, actors[attacker], round_number, 'luck') % 7 - 3
            unrounded = round(base + stat + interaction_damage + price_damage + luck, 6)
            floor_damage = int(unrounded)
            # Seeded stochastic rounding avoids turning a tiny premium into a whole guaranteed damage point.
            rounded = floor_damage + int(_roll(seed, actors[attacker], round_number, 'rounding') % 1000000 < (unrounded - floor_damage) * 1000000)
            uncapped = max(1, min(25, rounded))
            damage = min(health[target], uncapped)
            after = health[target] - damage
            round_events.append({
                'id': f'round-{round_number}-{attacker}', 'at': 0, 'attacker': attacker,
                'damage': damage, 'kind': 'finisher' if after == 0 else 'heavy' if damage >= 16 else 'swipe',
                'word': 'K.O.!' if after == 0 else 'SPLASH!' if 'water_splash' in fighter['traits'] and round_number <= fighter.get('resources', {}).get('water_charges', 0) else ('BOP!', 'THWACK!', 'BOUNCE!')[round_number % 3],
                'receipt': {'round': round_number, 'base_damage': base, 'stat_adjustment': stat,
                            'interaction_percent': interaction, 'interaction_damage': interaction_damage,
                            'interaction_rules': rules, 'price_percent': premium, 'price_damage': price_damage,
                            'luck': luck, 'unrounded_damage': unrounded, 'rounding_adjustment': round(rounded - unrounded, 6),
                            'rounded_damage': rounded, 'damage_range_adjustment': uncapped - rounded,
                            'damage_before_cap': uncapped, 'damage_before_health_cap': uncapped,
                            'health_cap_adjustment': damage - uncapped, 'damage': damage,
                            'health_before': health[target], 'health_after': after, 'dodged': False,
                            'water_charges_before': max(0, fighter.get('resources', {}).get('water_charges', 0) - round_number + 1),
                            'water_charges_after': max(0, fighter.get('resources', {}).get('water_charges', 0) - round_number)},
            })
        for event in round_events:
            health[1 - event['attacker']] = event['receipt']['health_after']
            impact_points[event['attacker']] += event['receipt']['damage_before_health_cap']
            events.append(event)
        if 0 in health:
            break
    tiebreak_reason = None
    if health[0] != health[1]:
        winner = 0 if health[0] > health[1] else 1
        outcome = 'knockout' if 0 in health else 'points'
    else:
        # A simultaneous knockout first credits total contact strength. The seed is a last resort.
        if impact_points[0] != impact_points[1]:
            winner = 0 if impact_points[0] > impact_points[1] else 1
            tiebreak_reason = 'impact_points'
        else:
            winner = order[_roll(seed, 'referee', 0, 'tiebreak') % 2]
            tiebreak_reason = 'seed'
        outcome = 'tiebreak'
    duration = 12800
    for index, event in enumerate(events):
        event['at'] = round(1400 + index * 9300 / max(1, len(events) - 1))
    return {'events': events, 'winner_slot': winner, 'final_health': health, 'duration_ms': duration,
            'engine_version': ENGINE_VERSION, 'seed': seed, 'playback_mode': 'normal', 'outcome': outcome,
            'rounds': round_number, 'impact_points': impact_points, 'tiebreak_reason': tiebreak_reason,
            'resolution': 'Both actions resolve in each round. Equal health compares total impact points before the remaining-health cap, then a saved seeded tiebreak.'}


def simulate_v2(profiles: list[dict[str, Any]], seed: int, include_analysis: bool = True) -> dict[str, Any]:
    if len(profiles) != 2 or type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError('A battle requires two profiles and a non-negative 31-bit integer seed')
    for profile in profiles:
        validate_profile(profile)
    frozen = deepcopy(profiles)
    result = _simulate(frozen, seed, with_price=True, with_interactions=True)
    result['fighters'] = frozen
    result['profile_version'] = frozen[0]['profile_version']
    result['price_policy'] = deepcopy(PRICE_POLICY)
    winner = result['winner_slot']
    name = frozen[winner]['name']
    if result['outcome'] == 'tiebreak' and result['tiebreak_reason'] == 'impact_points':
        summary = f'Both objects were knocked out. {name} wins on impact points: {result["impact_points"][winner]} to {result["impact_points"][1 - winner]}, counted before the final health cap.'
    elif result['outcome'] == 'tiebreak':
        summary = f'{name} wins the saved seeded tiebreak after equal health and impact points. Neither object earned an advantage on those measures.'
    elif result['outcome'] == 'points':
        summary = f'{name} wins on remaining health after ten paired rounds. There was no knockout.'
    else:
        summary = f'{name} wins by knockout after {result["rounds"]} paired rounds.'
    highlights = ['Both fighters started with 100 health and the same 20-point base stat budget.',
                  'Each round commits both actions before either lands; acting first in the animation gives no advantage.']
    highlights.insert(0, f'{name} dealt {100 - result["final_health"][1 - winner]} health damage and received {100 - result["final_health"][winner]}. Its pre-health-cap impact points were {result["impact_points"][winner]} versus {result["impact_points"][1 - winner]}.')
    active_names = list(dict.fromkeys(r['name'] for event in result['events'] for r in event['receipt']['interaction_rules']))
    if active_names:
        highlights.append('Applied matchup rules: ' + ', '.join(active_names) + '.')
    counterfactual = {}
    if include_analysis:
        for key, use_price, use_interactions in [('without_price', False, True), ('without_interactions', True, False)]:
            alternative = _simulate(frozen, seed, with_price=use_price, with_interactions=use_interactions)
            counterfactual[key] = {field: alternative[field] for field in ('winner_slot', 'final_health', 'outcome', 'impact_points', 'tiebreak_reason')}
            counterfactual[key]['changed_winner'] = alternative['winner_slot'] != winner
        price_note = ('Removing the price premium changes the winner for this seed.' if counterfactual['without_price']['changed_winner']
                      else 'Removing the price premium does not change the winner for this seed.')
        highlights.append('Removing all matchup interactions ' + ('changes' if counterfactual['without_interactions']['changed_winner'] else 'does not change') + ' the winner for this seed. This checks the rules together, not any one rule alone.')
    else:
        price_note = 'Price premium is capped at 1%; this run did not calculate counterfactual replays.'
    result['explanation'] = {'summary': summary, 'highlights': highlights,
                             'price_note': price_note + ' Prices are illustrative samples, not live quotes.'}
    result['counterfactual'] = counterfactual
    return result
