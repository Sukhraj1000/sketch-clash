"""Conservative capture-to-combat adapter. No provider calls; frozen price receipts only.

Accepted descriptions are evidence for a declared cartoon rule, not a measured
material test. Unknown properties stay neutral; cosmetic names and accessories,
OCR text, object-class presets and the practice catalog never supply attributes.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re

from .combat_v2 import RULES, STAT_NAMES, simulate_v2, validate_profile
from .market_prices import combat_price

PROFILE_VERSION = 'accepted-capture-1'
DURATIONS = {'normal': 12800, 'reduced': 12800, 'quick': 6400}

# Reject the whole clause when its subject/polarity is uncertain. Conservatively
# omitting a true property is preferable to awarding a guessed capability.
UNCERTAIN = re.compile(r"\b(no|not|without|lack\w*|absent|unknown|uncertain|unclear|unconfirmed|maybe|perhaps|possibly|possible|might|may|could|seems?|appears?|looks?|looking|resembl\w*|likely|suspected|imitat\w*|faux|fake)\b|\b(?:or|and/or)\b|\bnon[- ]|\b\w+[- ]free\b", re.I)
BACKGROUND = re.compile(r'\b(background|tabletop|table|countertop|floor|wall|behind|beside|underneath)\b|\b(?:resting|sitting|placed|standing) on\b', re.I)
DEPICTION = re.compile(r'\b(print\w*|picture|image|logo|graphic|pattern|depict\w*|drawing|photo\w*|illustration|label|sticker)\b', re.I)
MATERIAL = re.compile(r'\b(material|composition|ceramic|porcelain|glass|steel|metal|aluminium|aluminum|iron|hardwood|rubber|plastic|foam|sponge|cotton|fabric|paper|cardboard)\b', re.I)
MATERIAL_TRAITS = {'rigid_hard', 'brittle', 'water_resistant', 'cushioned', 'absorbent', 'flexible_recovery'}

# Every inferred trait records the exact accepted phrase and an explicit rule.
# No identity-only defaults: a mug can be metal, ceramic, plastic or unknown.
TRAIT_RULES = (
    ('rigid_hard', r'\b(ceramic|porcelain|glass|steel|metal|aluminium|aluminum|iron|hardwood|rigid|hard shell)\b', 'A stated hard material supports a rigid cartoon impact.'),
    ('brittle', r'\b(ceramic|porcelain|glass|brittle)\b', 'A stated brittle material can chip under a hard impact.'),
    ('water_resistant', r'\b(steel|metal|aluminium|aluminum|plastic|rubber|glass|water[- ]resistant|waterproof)\b', 'This stated surface sheds a small cartoon splash; no electronics attack is granted.'),
    ('cushioned', r'\b(foam|sponge|padded|padding|cushioned)\b', 'Stated soft padding spreads a hard impact.'),
    ('absorbent', r'\b(paper|cardboard|cotton|absorbent|sponge|foam|fabric)\b', 'The stated absorbent material can take on a water load.'),
    ('flexible_recovery', r'\b(rubber|sponge|foam|springy|elastic|flexible)\b', 'Stated flexibility permits a cartoon recovery after contact.'),
    ('smooth', r'\b(smooth|glazed|polished)\b', 'A stated smooth finish can slip out of a loose hook.'),
    ('grippy', r'\b(grippy|rubber grip|textured grip|rough gripping surface)\b', 'An explicitly described gripping surface resists rolling.'),
    ('long_reach', r'\b(long|elongated|extended) (?:\w+ ){0,2}(handle|shaft|body|rod|stick)\b|\bslender (rod|shaft)\b', 'A described long shape can reach before close contact.'),
    ('close_grip', r'\b(handle|handgrip|short grip|compact body)\b', 'A described handhold supports close control.'),
    ('looped', r'\b(?:curved|loop|looped|closed|side|carry) (?:\w+ ){0,2}handle\b|\bexposed loop\b', 'A visible handle loop can be caught by a loose hook.'),
    ('stable_base', r'\b(flat|broad|wide|stable) (?:\w+ ){0,1}base\b', 'A described supporting base permits bracing.'),
    ('flat_contact', r'\b(flat|broad) (face|surface|cover|panel)\b', 'A described flat face presents a contact edge.'),
    ('round_roll', r'\b(spherical|ball[- ]shaped) (body|shape|object|form)\b|^(?:\w+ ){0,2}ball$', 'An explicitly spherical body supports rolling.'),
    ('precision', r'\b(fine point|narrow tip|pointed tip|precision tip)\b', 'A described narrow contact tip permits a placed tap.'),
    ('hooking', r'\b(loose loop|hook[- ]shaped|curved hook|hooked end)\b', 'A described loose loop or hook can catch an exposed handle.'),
    ('unwieldy', r'\b(bulky|unwieldy|large body|heavy body)\b', 'Explicit bulk trades agility for a firm bump.'),
)

# Transfers preserve the identical 20-point budget; each is clamped as a pair.
STAT_TRANSFERS = (
    ('rigid_hard', 'impact', 'agility'), ('brittle', 'control', 'resilience'),
    ('cushioned', 'resilience', 'impact'), ('flexible_recovery', 'agility', 'impact'),
    ('long_reach', 'impact', 'resilience'), ('close_grip', 'control', 'agility'),
    ('round_roll', 'agility', 'control'), ('grippy', 'control', 'agility'),
    ('precision', 'control', 'impact'), ('unwieldy', 'impact', 'agility'),
    ('stable_base', 'resilience', 'agility'), ('flat_contact', 'resilience', 'control'),
)


def capture_profile(fighter: dict, observation: dict | None = None, *, confirmed: bool = False) -> dict:
    observation = observation or {}
    observed = fighter.get('observed_object')
    if observed is None:
        observed = observation.get('observed_object')
    # An explicitly empty accepted list remains empty during cosmetic revisions.
    features = observed.get('visible_features', []) if observed is not None else observation.get('visible_features', [])
    label = observed.get('label') if observed is not None else observation.get('proposed_label')
    raw = ([label] if isinstance(label, str) else []) + [item for item in features if isinstance(item, str)]
    overlong = {item.strip()[:200] for item in raw[:25] if len(item.strip()) > 200}
    raw = list(dict.fromkeys(item.strip()[:200] for item in raw[:25] if item.strip()))
    usable = [item for item in raw if item not in overlong and not UNCERTAIN.search(item) and not BACKGROUND.search(item) and not DEPICTION.search(item)]
    uncertainties = [str(item)[:200] for item in observation.get('uncertainty', [])[:16]]
    vetoes = uncertainties + [item for item in raw if UNCERTAIN.search(item) and not BACKGROUND.search(item)]
    material_unknown = any(MATERIAL.search(item) for item in vetoes)
    trait_evidence = []
    for trait, pattern, rule in TRAIT_RULES:
        supporting = [item for item in usable if re.search(pattern, item, re.I)]
        if (trait in MATERIAL_TRAITS and material_unknown) or any(re.search(pattern, item, re.I) for item in vetoes):
            supporting = []
        if trait == 'round_roll':
            supporting = [item for item in supporting if not re.search(r'\b(knob|bead|button|decoration|ornament)\b', item, re.I)]
        if supporting:
            trait_evidence.append({'trait': trait, 'features': supporting, 'rule': rule,
                                   'basis': 'declared_game_inference_from_capture'})
    traits = [entry['trait'] for entry in trait_evidence]
    # A container class, fictional name or a blue surface never implies water.
    # The player must accept explicit visible water AND an open pouring path.
    water = [item for item in usable if re.search(r'\b(?:visible water|water visible|filled with water|contains water|water inside)\b', item, re.I)]
    opening = [item for item in usable if re.search(r'\bopen (?:\w+ ){0,1}(spout|mouth|top|opening|rim)\b|\buncovered spout\b', item, re.I)]
    blocked = any(re.search(r'\b(empty|dry|closed|sealed|capped|lid|cover|frozen|ice)\b', item, re.I)
                  or (UNCERTAIN.search(item) and re.search(r'\bwater\b', item, re.I)) for item in raw)
    blocked = blocked or any(re.search(r'\b(water|liquid|contents|opening|spout|access)\b', item, re.I) for item in uncertainties)
    eligible_water = bool(water and opening and not blocked)
    charges = 2 if confirmed and eligible_water else 0
    if charges:
        traits.append('water_splash')
        trait_evidence.append({'trait': 'water_splash', 'features': list(dict.fromkeys(water + opening)),
            'rule': 'Player-accepted visible water and open pouring access grant two finite cartoon splashes.',
            'basis': 'accepted_visible_supply'})
    stats = dict.fromkeys(STAT_NAMES, 5)
    transfers = []
    for trait, gain, cost in STAT_TRANSFERS:
        if trait in traits and stats[gain] < 8 and stats[cost] > 1:
            stats[gain] += 1
            stats[cost] -= 1
            transfers.append({'trait': trait, 'gain': gain, 'cost': cost, 'points': 1})
    price = combat_price(fighter.get('market_price'))
    limitations = ['Attributes are bounded game interpretations of the selected photograph, not measured physical properties.',
                   price['label'],
                   'Unstated, negated, uncertain and background properties are omitted.']
    if eligible_water and not confirmed:
        limitations.append('Two splashes become available when you confirm the visible water and open pouring access.')
    elif not charges:
        limitations.append('No confirmed open water supply: no splash attack.')
    if not traits:
        limitations.append('No supported combat properties: neutral 5/5/5/5 stats.')
    profile = {
        'id': 'capture:' + fighter['image_hash'], 'name': fighter['display_name'],
        'object_type': fighter['object_type'], 'description': '; '.join(raw) or 'No supported physical properties recorded.',
        'image_ref': fighter['image_ref'], 'health': 100, 'stats': stats, 'traits': traits,
        'capabilities': [entry['rule'] for entry in trait_evidence], 'limitations': limitations,
        'resources': {'water_charges': charges, 'water_evidence': 'confirmed' if charges else 'none'},
        'price': price,
        'provenance': {'kind': 'accepted_capture' if confirmed else 'capture_preview',
            'label': 'Player-accepted capture; deterministic game rules' if confirmed else 'Capture evidence preview; awaiting player acceptance',
            'profile_version': PROFILE_VERSION, 'capture_id': fighter['capture_id'],
            'output_id': fighter.get('output_id'), 'pipeline_version_id': fighter.get('pipeline_version_id'),
            'image_hash': fighter['image_hash'], 'observed_features': raw,
            'uncertainty': uncertainties,
            'omitted_features': [item for item in raw if item not in usable], 'trait_evidence': trait_evidence,
            'feature_policy': 'Only concise clauses of at most 200 characters are eligible; longer clauses are omitted, never truncated into an assertion.',
            'stat_transfers': transfers,
            'stat_policy': 'Start at 5 in each stat; supported traits transfer points within 1–8, preserving 20 total.',
            'excluded_sources': ['archetype presets', 'fictional display name', 'visual accessories', 'OCR text', 'practice fixture prices']},
        'profile_version': PROFILE_VERSION,
    }
    validate_profile(profile)
    return profile


def simulate_capture_battle(fighters: list[dict], observations: list[dict], seed: int, playback_mode: str) -> dict:
    if playback_mode not in DURATIONS:
        raise ValueError('Unsupported battle playback mode.')
    profiles = [capture_profile(f, obs, confirmed=True) for f, obs in zip(fighters, observations)]
    result = simulate_v2(profiles, seed)
    duration = DURATIONS[playback_mode]
    for event in result['events']:
        event['at'] = round(event['at'] * duration / 12800)
    result.update(duration_ms=duration, playback_mode=playback_mode)
    priced = all(p['price']['amount_gbp'] is not None for p in profiles)
    price_note = ('Frozen medians of similar eBay UK asking prices, excluding postage; not appraisals or sold prices. '
                  'The logarithmic price premium is capped at 1% damage.' if priced else
                  'At least one capture lacks a sourced comparable price. Both price premiums are zero; removing price cannot change this winner.')
    result['price_policy'] = {**result['price_policy'], 'kind': 'sourced_comparables' if priced else 'unknown_capture_prices',
        'description': price_note}
    result['explanation']['price_note'] = price_note
    result['explanation']['highlights'].append('Combat attributes come from the accepted photographs. Quick, Power and Guard labels do not select stats or the winner.')
    result['provenance'] = {'kind': 'accepted_capture', 'profile_version': PROFILE_VERSION,
        'resolution': 'Deterministic local simulation; no model selects the winner.',
        'frozen_at': 'battle_start', 'price_source': 'ebay_browse' if priced else 'unavailable'}
    result['rules_snapshot'] = deepcopy(RULES)
    result['rules_hash'] = sha256(json.dumps(RULES, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    result['immutable'] = True
    result['snapshot_sha256'] = sha256(json.dumps({'profiles': profiles, 'rules': result['rules_snapshot'],
        'price_policy': result['price_policy'], 'profile_version': PROFILE_VERSION},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return deepcopy(result)
