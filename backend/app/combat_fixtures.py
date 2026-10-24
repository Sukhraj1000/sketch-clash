"""Curated, explicitly illustrative arena fixtures. These are not camera observations."""
from copy import deepcopy
from typing import Any

PROFILE_VERSION = 'object-fixtures-1'


def _fixture(identifier, name, object_type, description, stats, traits, capabilities, limitations, price):
    return {
        'id': identifier, 'name': name, 'object_type': object_type, 'description': description,
        'image_ref': f'/fixtures/{identifier}.svg', 'health': 100,
        'stats': dict(zip(('impact', 'resilience', 'agility', 'control'), stats)),
        'traits': traits, 'capabilities': capabilities, 'limitations': limitations,
        'resources': {'water_charges': 2 if 'water_splash' in traits else 0,
                      'water_evidence': 'curated_fixture' if 'water_splash' in traits else 'none'},
        'price': {'amount_gbp': price, 'source': 'sample_fixture',
                  'label': 'Illustrative typical-item price; not a live marketplace quote',
                  'observed_at': None, 'confidence': 'illustrative'},
        'provenance': {'kind': 'curated_fixture', 'label': 'Authored example, not AI recognition',
                       'profile_version': PROFILE_VERSION},
        'profile_version': PROFILE_VERSION,
    }


_FIXTURES = [
    _fixture('ceramic-mug', 'Ceramic Mug', 'mug', 'An empty ceramic mug with a handle.',
             (6, 5, 3, 6), ['rigid_hard', 'brittle', 'close_grip', 'stable_base', 'looped'],
             ['Brace on a flat base', 'Use its handle for close control'],
             ['Empty: cannot splash water', 'Ceramic can chip under a hard impact'], 8),
    _fixture('steel-bottle', 'Steel Bottle', 'bottle', 'An empty steel bottle, with a closed cap.',
             (6, 7, 3, 4), ['rigid_hard', 'smooth', 'water_resistant', 'unwieldy'],
             ['Resist splashes', 'Deliver a firm body bump'],
             ['Empty and capped: no water attack', 'Bulk reduces agility'], 28),
    _fixture('kitchen-sponge', 'Kitchen Sponge', 'sponge', 'A dry, soft kitchen sponge.',
             (2, 6, 7, 5), ['cushioned', 'absorbent', 'flexible_recovery', 'grippy'],
             ['Soften hard impacts', 'Regain its shape after a squeeze'],
             ['Little striking power', 'Absorbed water adds a load'], 1.5),
    _fixture('wooden-ruler', 'Wooden Ruler', 'ruler', 'A lightweight, straight wooden ruler.',
             (5, 4, 6, 5), ['long_reach', 'precision', 'flat_contact'],
             ['Keep an opponent at a distance', 'Place a precise tap'],
             ['Close contact removes its reach advantage', 'Narrow profile offers little padding'], 2),
    _fixture('rubber-ball', 'Rubber Ball', 'ball', 'A bouncy rubber play ball.',
             (6, 5, 7, 2), ['round_roll', 'flexible_recovery', 'water_resistant'],
             ['Roll into flat objects', 'Recover its shape after contact'],
             ['Hard to place a precise hit', 'Grippy surfaces slow its roll'], 4),
    _fixture('hardback-book', 'Hardback Book', 'book', 'A closed paper book with a stiff cover.',
             (5, 6, 2, 7), ['flat_contact', 'absorbent', 'stable_base', 'close_grip'],
             ['Brace behind a broad cover', 'Control short-range contact'],
             ['Paper is vulnerable to water', 'Broad shape moves slowly'], 12),
    _fixture('filled-water-jug', 'Filled Water Jug', 'pitcher', 'A plastic jug with visible water and an open spout.',
             (6, 5, 3, 6), ['water_splash', 'water_resistant', 'unwieldy', 'looped'],
             ['Splash its stored water during the first two rounds', 'Use its handle to guide a bump'],
             ['Water supply lasts only two splashes', 'No heat, ice or infinite water'], 6),
    _fixture('wooden-spoon', 'Wooden Spoon', 'spoon', 'A compact wooden cooking spoon.',
             (4, 5, 6, 5), ['long_reach', 'precision', 'close_grip'],
             ['Guide a precise tap', 'Keep control at close range'],
             ['Cannot create food, heat or water', 'Limited striking mass'], 3),
    _fixture('coiled-rope', 'Coiled Rope', 'rope', 'A soft length of rope with a loose hooking loop.',
             (3, 5, 5, 7), ['hooking', 'flexible_recovery', 'grippy', 'absorbent'],
             ['Catch a handle or open loop', 'Yield under a precise poke'],
             ['Slips off smooth surfaces', 'No rigid striking edge'], 7),
    _fixture('smartphone', 'Smartphone', 'phone', 'A phone in a slim rigid case, with a glass screen.',
             (3, 4, 6, 7), ['precision', 'brittle', 'flat_contact', 'smooth'],
             ['Place an accurate short tap', 'Slide out of a loose hook'],
             ['Glass is vulnerable to hard impact', 'A battery inside does not grant electric attacks'], 650),
    _fixture('foam-block', 'Foam Block', 'foam', 'A dry, soft foam block with a broad base.',
             (2, 7, 6, 5), ['cushioned', 'flexible_recovery', 'stable_base', 'absorbent'],
             ['Cushion a hard bump', 'Brace against long reach'],
             ['Very little striking power', 'Absorbed water adds a load'], 3),
    _fixture('metal-whisk', 'Metal Whisk', 'whisk', 'A lightweight whisk with springy metal loops.',
             (4, 5, 6, 5), ['long_reach', 'looped', 'precision', 'water_resistant'],
             ['Deliver a controlled long-range tap', 'Ignore a small water splash'],
             ['Loops can be caught by rope', 'No heating or electrical power'], 5),
]


def fixture_profile(identifier: str) -> dict[str, Any]:
    from .combat_v2 import validate_profile
    for profile in _FIXTURES:
        if profile['id'] == identifier:
            result = deepcopy(profile)
            validate_profile(result)
            return result
    raise ValueError(f'Unknown arena fixture: {identifier}')


def get_catalog() -> dict[str, Any]:
    from .combat_v2 import ENGINE_VERSION, PRICE_POLICY, RULES, preview_matchup
    fixtures = [fixture_profile(item['id']) for item in _FIXTURES]
    return {
        'engine_version': ENGINE_VERSION, 'profile_version': PROFILE_VERSION,
        'fixtures': fixtures, 'rules': deepcopy(RULES), 'price_policy': deepcopy(PRICE_POLICY),
        'matchup_previews': {f"{a['id']}:{b['id']}": preview_matchup([a, b]) for a in fixtures for b in fixtures},
        'disclaimer': 'Curated cartoon fixtures and illustrative prices. No Gemini recognition or live marketplace lookup. All fighters share a 20-point base budget.',
    }
