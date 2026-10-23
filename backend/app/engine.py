"""Deterministic integer combat v1. Cosmetic language is independent of outcomes."""
from hashlib import sha256
from typing import Any
from pydantic import ValidationError
from .contracts import CombatStats, PendingFighter, VisualSpec

ENGINE_VERSION = 'clash-integer-1'
PRESETS = {
    'Quick': {'health': 100, 'attack': 16, 'defense': 2, 'speed': 3},
    'Power': {'health': 100, 'attack': 24, 'defense': 1, 'speed': 1},
    'Guard': {'health': 100, 'attack': 18, 'defense': 7, 'speed': 2},
}
DURATIONS = {'normal': 12800, 'reduced': 12800, 'quick': 6400}

def validate_fighter_config(config: dict[str, Any]) -> dict[str, Any]:
    errors = []
    archetype = config.get('archetype')
    if archetype not in PRESETS:
        errors.append('archetype must be Quick, Power or Guard')
    try:
        stats = CombatStats.model_validate(config.get('stats', {})).model_dump()
        if archetype in PRESETS and stats != PRESETS[archetype]:
            errors.append('stats must exactly match the approved archetype preset')
    except ValidationError as exc:
        errors.extend(str(e['msg']) for e in exc.errors())
    return {'valid': not errors, 'errors': errors}

def validate_visual_spec(spec: dict[str, Any]) -> dict[str, Any]:
    try:
        VisualSpec.model_validate(spec)
        return {'valid': True, 'errors': []}
    except ValidationError as exc:
        return {'valid': False, 'errors': [str(e['msg']) for e in exc.errors()]}

def _roll(seed: int, turn: int, purpose: str) -> int:
    return int.from_bytes(sha256(f'{ENGINE_VERSION}:{seed}:{turn}:{purpose}'.encode()).digest()[:4], 'big')

def simulate_match(fighters: list[dict[str, Any]], seed: int, playback_mode: str = 'normal') -> dict[str, Any]:
    if len(fighters) != 2 or playback_mode not in DURATIONS:
        raise ValueError('A match requires two fighters and a supported playback mode.')
    stats = []
    for fighter in fighters:
        check = validate_fighter_config(fighter)
        if not check['valid']:
            raise ValueError('; '.join(check['errors']))
        stats.append(fighter['stats'])
    health = [100, 100]
    events = []
    first = 0 if stats[0]['speed'] > stats[1]['speed'] else 1 if stats[1]['speed'] > stats[0]['speed'] else seed % 2
    for turn in range(10):
        attacker = (first + turn) % 2
        target = 1 - attacker
        # Integer cinematic multiplier keeps even defensive mirrors inside the short authored arena.
        raw_damage = stats[attacker]['attack'] - stats[target]['defense'] + _roll(seed, turn, 'damage') % 7 - 3
        damage = min(38, max(16, raw_damage * 2))
        damage = min(health[target], damage)
        health[target] -= damage
        knockout = health[target] == 0
        events.append({'id': f'hit-{turn+1}', 'at': 0, 'attacker': attacker, 'damage': damage,
                       'kind': 'finisher' if knockout else 'heavy' if damage >= 21 else 'swipe',
                       'word': 'K.O.!' if knockout else ('WHAM!', 'POW!', 'THWACK!', 'SWISH!')[turn % 4]})
        if knockout:
            winner = attacker
            break
    else:
        # Documented termination rule: remaining health, then seeded tiebreak; decisive final hit.
        winner = 0 if health[0] > health[1] else 1 if health[1] > health[0] else seed % 2
        target = 1 - winner
        events.append({'id': 'decision', 'at': 0, 'attacker': winner, 'damage': health[target], 'kind': 'finisher', 'word': 'K.O.!'})
        health[target] = 0
    duration = DURATIONS[playback_mode]
    for index, event in enumerate(events):
        event['at'] = round((1600 + index * 8300 / max(1, len(events) - 1)) * duration / 12800)
    return {'events': events, 'winner_slot': winner, 'final_health': health, 'duration_ms': duration,
            'engine_version': ENGINE_VERSION, 'seed': seed, 'playback_mode': playback_mode}

def simulate_match_preview(config: dict[str, Any]) -> dict[str, Any]:
    check = validate_fighter_config(config)
    if not check['valid']:
        return check
    result = simulate_match([config, {'archetype': 'Guard', 'stats': PRESETS['Guard']}], 42)
    return {'valid': len(result['events']) <= 11 and 0 in result['final_health'], 'errors': [],
            'duration_ms': result['duration_ms'], 'event_count': len(result['events'])}
