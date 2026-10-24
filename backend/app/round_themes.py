"""Durable round briefs and conservative, explainable eligibility rules.

Recognition proposes the object identity; this policy checks that identity against
the brief. Unknown vocabulary is not proof of a violation. No extra provider call
is made and a rejected photograph can always be corrected or replaced.
"""
from __future__ import annotations

from copy import deepcopy
import re

POLICY_VERSION = 'round-themes-1'

THEMES = [
    {'id': 'everyday', 'name': 'Everyday Objects', 'instructions': 'Choose one real object around you. Both players share this brief.',
     'examples': ['mug', 'book', 'phone', 'shoe']},
    {'id': 'kitchen', 'name': 'Kitchen Crew', 'instructions': 'Choose food, a utensil, a cooking tool or a food/drink container.',
     'examples': ['mug', 'ladle', 'apple', 'water bottle']},
    {'id': 'desk', 'name': 'Desk Companions', 'instructions': 'Choose something for a desk: writing, reading, computing or desk supplies.',
     'examples': ['pencil', 'keyboard', 'book', 'desk lamp']},
    {'id': 'tools', 'name': 'Useful Tools', 'instructions': 'Choose a tool that helps someone make, fix, measure, cut or clean.',
     'examples': ['hammer', 'scissors', 'ruler', 'brush']},
    {'id': 'animals', 'name': 'Animal Kingdom', 'instructions': 'Choose a clear photograph of an animal. Pets and wild animals both count; toys and printed pictures do not.',
     'examples': ['cat', 'dog', 'rabbit', 'parrot']},
    {'id': 'nature', 'name': 'From Nature', 'instructions': 'Choose a plant, fruit, natural material or animal. Show the subject clearly.',
     'examples': ['leaf', 'pine cone', 'rock', 'flower']},
    {'id': 'play', 'name': 'Sport & Play', 'instructions': 'Choose sports equipment, a toy, a game or a musical instrument.',
     'examples': ['ball', 'toy car', 'dice', 'guitar']},
    {'id': 'wearables', 'name': 'Ready to Wear', 'instructions': 'Choose clothing, footwear or an accessory someone can wear or carry.',
     'examples': ['shoe', 'hat', 'watch', 'backpack']},
]


def theme_for_round(index: int) -> dict:
    return {**deepcopy(THEMES[index % len(THEMES)]), 'rotation_index': index,
            'policy_version': POLICY_VERSION, 'enforced': True}


def legacy_theme() -> dict:
    return {**deepcopy(THEMES[0]), 'rotation_index': None, 'policy_version': 'legacy-unrestricted',
            'enforced': False}


# This vocabulary is independent of the render catalogue: a new recognised kind
# can use the generic renderer and still qualify. Overlapping categories are
# deliberate (a ruler is both a desk item and a tool).
GROUPS = {
    'kitchen': 'mug|cup|bottle|flask|tumbler|pitcher|jug|bowl|plate|dish|saucer|spoon|fork|knife|ladle|spatula|whisk|tongs|chopsticks|sieve|colander|grater|peeler|pan|saucepan|pot|kettle|teapot|coffee maker|toaster|blender|breadmaker|food processor|oven|microwave|fridge|refrigerator|chopping board|cutting board|can opener|corkscrew|jar|food container|lunchbox|lunch box|thermos|apple|banana|orange|pear|peach|lemon|lime|grape|strawberry|tomato|potato|carrot|onion|bread|cake|biscuit|cookie|sandwich|egg|cheese',
    'desk': 'pen|pencil|marker|highlighter|crayon|eraser|rubber|sharpener|ruler|scissors|stapler|tape dispenser|paper clip|paperclip|binder clip|notebook|notepad|paper|book|folder|binder|envelope|calendar|calculator|phone|smartphone|tablet|laptop|computer|monitor|keyboard|computer mouse|mousepad|mouse mat|headphones|headset|desk lamp|lamp|printer|mug|cup|bottle|flask|tumbler|plant|clock|charger|usb cable|power bank|battery',
    'tools': 'hammer|mallet|screwdriver|wrench|spanner|pliers|drill|saw|file|chisel|clamp|vise|vice|soldering iron|scissors|knife|ruler|tape measure|measuring tape|level|brush|paintbrush|broom|mop|sponge|duster|vacuum cleaner|watering can|shovel|spade|rake|trowel|ladle|spatula|whisk|tongs|grater|peeler|can opener|corkscrew|needle|sewing machine|pencil|pen|stapler',
    'animals': 'cat|kitten|dog|puppy|rabbit|bunny|hamster|gerbil|guinea pig|rat|chinchilla|ferret|hedgehog|parrot|parakeet|budgie|bird|pigeon|sparrow|owl|eagle|duck|goose|swan|chicken|rooster|penguin|horse|pony|donkey|cow|bull|sheep|goat|pig|llama|alpaca|deer|fox|wolf|bear|lion|tiger|leopard|cheetah|panther|elephant|giraffe|zebra|rhino|rhinoceros|hippo|hippopotamus|monkey|gorilla|chimpanzee|orangutan|koala|panda|kangaroo|squirrel|raccoon|otter|badger|skunk|bat|seal|walrus|dolphin|whale|shark|fish|goldfish|turtle|tortoise|lizard|gecko|iguana|snake|crocodile|alligator|frog|toad|salamander|axolotl|butterfly|moth|bee|ant|beetle|ladybird|ladybug|spider|snail|slug|crab|lobster|octopus|squid|jellyfish|starfish',
    'nature': 'plant|cactus|succulent|flower|rose|tulip|daisy|sunflower|orchid|fern|moss|leaf|leaves|branch|twig|stick|pine cone|pinecone|acorn|seed|nut|rock|stone|pebble|shell|seashell|sand|feather|wood|log|mushroom|apple|banana|orange|pear|peach|lemon|lime|grape|strawberry|tomato|potato|carrot|onion',
    'play': 'ball|football|basketball|volleyball|baseball|tennis ball|rugby ball|golf ball|cricket ball|tennis racket|racket|racquet|bat|cricket bat|baseball bat|hockey stick|golf club|frisbee|skateboard|skate|roller skate|bicycle|bike|scooter|dumbbell|jump rope|skipping rope|toy|plush|teddy|doll|figurine|action figure|toy car|puzzle|dice|die|board game|chess piece|chessboard|playing card|cards|game controller|controller|guitar|ukulele|violin|piano|keyboard instrument|drum|flute|recorder|trumpet|harmonica|tambourine|maraca',
    'wearables': 'shoe|trainer|sneaker|boot|sandal|slipper|sock|hat|cap|beanie|helmet|scarf|glove|mitten|shirt|t shirt|tshirt|blouse|jumper|sweater|hoodie|jacket|coat|dress|skirt|trousers|pants|jeans|shorts|belt|tie|watch|wristwatch|bracelet|necklace|ring|earring|glasses|sunglasses|backpack|rucksack|handbag|bag|purse|wallet|headphones|headset',
}
VOCAB = {category: set(words.split('|')) for category, words in GROUPS.items()}
UNCERTAIN = re.compile(r'\b(maybe|possibly|perhaps|unclear|unknown|unidentified|could be|might be|looks like|appears to be|not|without|or)\b')
REPRESENTATION = re.compile(r'\b(toy|plush|stuffed|figurine|statue|model|sculpture|printed|drawing|picture|photo|photograph|logo|shaped)\b')


def _normalise(label: str) -> str:
    return re.sub(r'[^a-z0-9 ]', ' ', label.casefold().replace('-', ' ').replace('_', ' ')).strip()


def _categories(label: str) -> set[str]:
    label = re.sub(r'\s+', ' ', _normalise(label))
    if UNCERTAIN.search(label) or label in {'mouse', 'bat', 'cap', 'pot', 'rubber', 'file', 'ring', 'die'}:
        return set()  # Polysemous labels need a clearer identity, never a guessed DQ.
    # Match the whole kind or its noun phrase at the end, not a background word
    # or an animal printed on a container ("cat mug" remains a mug).
    found = {category for category, words in VOCAB.items()
             if any(label == word or label.endswith(' ' + word) for word in words)}
    if REPRESENTATION.search(label):
        found.discard('animals')
        found.discard('nature')
        if re.search(r'\b(toy|plush|stuffed|figurine|doll|teddy)\b', label):
            found.add('play')
    if 'animals' in found:
        found.add('nature')
    return found


def validate_theme(theme: dict | None, observation: dict) -> dict:
    theme = theme or legacy_theme()
    fighter = observation.get('pending_fighter') or {}
    observed = observation.get('observed_object') or fighter.get('observed_object') or {}
    primary = observed.get('label') or observation.get('proposed_label') or fighter.get('object_type')
    canonical = observed.get('canonical_type_id') or fighter.get('canonical_type_id')
    labels = list(dict.fromkeys(str(item)[:100] for item in (primary, canonical) if item))[:2]
    result = {'theme_id': theme['id'], 'theme_name': theme['name'], 'policy_version': theme['policy_version'],
              'evidence_labels': labels, 'basis': 'recognition_identity_rules'}
    def verdict(value, reason):
        return {**result, 'verdict': value, 'reason': reason}
    if not theme.get('enforced'):
        return verdict('eligible', 'This older round keeps its original unrestricted brief.')
    if observation.get('status') != 'recognized' or not fighter or not labels:
        return verdict('uncertain', 'Identify one clear subject before checking the round theme.')
    if any(UNCERTAIN.search(_normalise(label)) for label in labels):
        return verdict('uncertain', 'The subject identity is uncertain. Correct it or use a clearer photograph; this is not a disqualification.')
    support = observation.get('evidence', {}).get('identity_support', {})
    if support.get('status') in {'conflict', 'disagreement', 'mismatch'}:
        return verdict('uncertain', 'The recognition checks disagree. Correct the object identity or retake before judging the theme.')
    if theme['id'] == 'everyday':
        return verdict('eligible', f'{primary} fits this open everyday-object round.')
    groups = [_categories(label) for label in labels]
    known = [categories for categories in groups if categories]
    if theme['id'] in {'animals', 'nature'} and REPRESENTATION.search(_normalise(primary or '')) and not groups[0]:
        return verdict('uncertain', 'The label may describe a depiction rather than the subject itself. Use a clearer photograph or correct the identity; no disqualification is applied.')
    if support.get('status') in {'different_labels', 'multiple_candidates'}:
        detector_groups = [_categories(label) for label in support.get('detector_labels', [])]
        if any(categories and ((theme['id'] in categories) != any(theme['id'] in group for group in known))
               for categories in detector_groups):
            return verdict('uncertain', 'The local detector and recognised subject disagree about this theme. Correct the identity or crop one clear subject; no disqualification is applied.')
    if not known:
        return verdict('uncertain', f'We cannot confidently place {primary} in {theme["name"]}. Correct the label or choose a clearer example; it is not disqualified.')
    if len(known) > 1 and not set.intersection(*known):
        return verdict('uncertain', 'The recognised label and object kind conflict. Correct the identity before checking eligibility.')
    if theme['id'] in known[0] and all(theme['id'] in categories for categories in known):
        return verdict('eligible', f'{primary} belongs in {theme["name"]}. Both players use the same saved brief.')
    # Missing vocabulary never establishes a violation. A specific, recognised
    # kind in another category does; reject this capture, not the player's account.
    return verdict('outside_theme', f'{primary} is outside {theme["name"]}. This photograph cannot enter the battle or earn an island resident. Correct a wrong label or retake with a matching subject.')
