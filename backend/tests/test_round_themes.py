"""Round eligibility uses controlled identities; no model or Atlas requests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from backend.app.config import Settings
from backend.app.contracts import Battle, Observation
from backend.app.images import normalize_image
from backend.app.repository import MemoryRepository, StoreError, key_for
from backend.app.round_themes import THEMES, theme_for_round, validate_theme
from backend.tests.test_lifecycle import Clock, fighter, photo


def judgment(theme_id, label, canonical=None, player_confirmed=False, **extra):
    theme = next(theme_for_round(i) for i, value in enumerate(THEMES) if value['id'] == theme_id)
    observation = {'status': 'recognized', 'pending_fighter': {'object_type': label,
        'canonical_type_id': canonical or label.replace(' ', '-')},
        'observed_object': {'label': label, 'canonical_type_id': canonical or label.replace(' ', '-')}}
    observation.update(extra)
    return validate_theme(theme, observation, player_confirmed=player_confirmed)


@pytest.mark.parametrize('theme,label,canonical', [
    ('kitchen', 'ceramic mug', 'mug'), ('kitchen', 'silicone ladle', 'ladle'),
    ('desk', 'computer mouse', 'mouse'), ('tools', 'metal spanner', 'spanner'),
    ('animals', 'cat', None), ('animals', 'dog', None), ('animals', 'axolotl', None),
    ('animals', 'African elephant', 'elephant'), ('animals', 'parrot', None),
    ('nature', 'pine cone', None), ('nature', 'gecko', None),
    ('play', 'plush cat', None), ('play', 'toy car', None), ('play', 'guitar', None),
    ('wearables', 'red leather boot', 'boot'), ('everyday', 'bread slicer', None),
])
def test_broad_identities_qualify_without_render_catalog_membership(theme, label, canonical):
    assert judgment(theme, label, canonical)['verdict'] == 'eligible'


@pytest.mark.parametrize('theme,label', [
    ('animals', 'mug'), ('animals', 'plush cat'), ('animals', 'cat mug'),
    ('kitchen', 'dog'), ('desk', 'elephant'), ('tools', 'mug'),
    ('nature', 'smartphone'), ('play', 'apple'), ('wearables', 'kettle'),
])
def test_known_other_category_is_rejected_with_retake_explanation(theme, label):
    result = judgment(theme, label)
    assert result['verdict'] == 'outside_theme'
    assert 'Correct a wrong label or retake' in result['reason']


@pytest.mark.parametrize('label', ['mystery gadget', 'mouse', 'possibly a cat', 'cat or dog', 'animal-like object'])
def test_unknown_or_ambiguous_identity_is_not_a_disqualification(label):
    assert judgment('animals', label)['verdict'] == 'uncertain'


def test_conflicting_identity_or_cross_category_detector_needs_review():
    assert judgment('animals', 'cat', 'mug')['verdict'] == 'uncertain'
    support = {'identity_support': {'status': 'different_labels', 'detector_labels': ['cat']}}
    assert judgment('kitchen', 'mug', evidence=support)['verdict'] == 'uncertain'
    # A broad YOLO cup versus a bottle does not change Kitchen eligibility.
    support['identity_support']['detector_labels'] = ['cup']
    assert judgment('kitchen', 'bottle', evidence=support)['verdict'] == 'eligible'
    assert judgment('animals', 'printed picture of cat', 'cat')['verdict'] == 'uncertain'
    assert judgment('animals', 'plush cat', 'cat')['verdict'] == 'uncertain'
    assert judgment('animals', 'not a cat', 'cat')['verdict'] == 'uncertain'


def test_player_confirmation_settles_detector_doubt_but_not_category_rules():
    support = {'identity_support': {'status': 'different_labels', 'detector_labels': ['teddy bear']}}
    doubtful = judgment('kitchen', 'gingerbread cookie', 'cookie', evidence=support)
    assert doubtful['verdict'] == 'uncertain'
    assert doubtful['resolution'] == 'confirm_identity'
    assert 'local detector' not in doubtful['reason']
    assert judgment('kitchen', 'gingerbread cookie', 'cookie', player_confirmed=True, evidence=support)['verdict'] == 'eligible'
    # Confirmation never turns a recognised subject from another category into a fit.
    assert judgment('kitchen', 'dog', player_confirmed=True, evidence=support)['verdict'] == 'outside_theme'
    assert judgment('animals', 'cat', 'mug', player_confirmed=True)['verdict'] == 'uncertain'


def test_fictional_name_attributes_and_background_cannot_change_theme():
    result = judgment('animals', 'mug', visible_features=['A cat in the background'],
                      evidence={'ocr': {'text': ['cat']}}, proposed_label='cat')
    assert result['verdict'] == 'outside_theme'
    assert result['evidence_labels'] == ['mug']


def test_theme_rotation_is_atomic_durable_world_scoped_and_idempotent():
    settings = Settings(repository='memory', world_id='themes-a')
    repo = MemoryRepository(settings, Clock())
    with ThreadPoolExecutor(max_workers=8) as pool:
        same = list(pool.map(repo.create_battle, ['same'] * 8))
    assert all(battle == same[0] for battle in same)
    first = same[0]
    Battle.model_validate(first)
    for index in range(1, len(THEMES) + 1):
        battle = repo.create_battle(f'round-{index}')
        assert battle['theme'] == theme_for_round(index)
        assert repo.get_battle(first['id'])['theme'] == first['theme']
    before = deepcopy(repo._data)
    assert repo.create_battle('same') == first
    assert repo._data == before
    other = MemoryRepository(Settings(repository='memory', world_id='themes-b'), Clock())
    assert other.create_battle('same')['theme'] == first['theme']


def add_capture(repo, battle, label, slot, capture_id, **extra):
    image = normalize_image(photo(), 'image/png', repo.settings)
    repo.save_media(image)
    capture = {'capture_id': capture_id, 'player_slot': slot, 'source': 'upload',
        'image_hash': image.image_hash, 'image_ref': image.image_ref,
        'canonical_media_id': image.image_hash, 'width': image.width, 'height': image.height, 'crop': None}
    repo.begin_capture(battle['id'], capture)
    observation = {key: value for key, value in capture.items() if key not in {'player_slot', 'canonical_media_id'}}
    observation.update(status='recognized', pending_fighter=fighter(battle['id'], slot, capture_id, image, label),
                       observed_object={'canonical_type_id': label, 'label': label}, **extra)
    return repo.finish_capture(battle['id'], capture_id, Observation.model_validate(observation).model_dump())


def test_correct_feedback_on_the_exact_proposal_unlocks_detector_doubt():
    repo = MemoryRepository(Settings(repository='memory'), Clock())
    repo.create_battle('first-open-round')
    battle = repo.create_battle('kitchen-round')
    support = {'identity_support': {'status': 'different_labels', 'detector_labels': ['teddy bear']}}
    doubtful = add_capture(repo, battle, 'cookie', 0, 'doubtful', evidence=support,
                           output_id='proposal-1', pipeline_version_id='pipeline-1')
    assert doubtful['theme_validation']['resolution'] == 'confirm_identity'
    # The API response contract must carry the hint, not reject it.
    assert Observation.model_validate(doubtful).theme_validation.resolution == 'confirm_identity'
    with pytest.raises(StoreError) as error:
        repo.confirm_capture(battle['id'], 0, 'doubtful')
    assert error.value.code == 'theme_uncertain'
    review = {'idempotency_key': 'vouch', 'output_id': 'proposal-1', 'pipeline_version_id': 'pipeline-1'}
    repo.submit_feedback(battle['id'], 'doubtful', {**review, 'recognition_verdict': 'unsure'})
    with pytest.raises(StoreError):
        repo.confirm_capture(battle['id'], 0, 'doubtful')
    repo.submit_feedback(battle['id'], 'doubtful', {**review, 'idempotency_key': 'vouch-2', 'recognition_verdict': 'correct'})
    assert repo.confirm_capture(battle['id'], 0, 'doubtful')['confirmed_capture_ids'][0] == 'doubtful'


def test_reject_retake_both_player_guards_and_replay_keep_saved_brief():
    clock = Clock()
    repo = MemoryRepository(Settings(repository='memory'), clock)
    repo.create_battle('first-open-round')
    battle = repo.create_battle('kitchen-round')
    original_theme = deepcopy(battle['theme'])
    bad = add_capture(repo, battle, 'dog', 0, 'wrong-theme')
    assert bad['theme_validation']['verdict'] == 'outside_theme'
    # Keep the reviewable proposal, so a factual error can be corrected.
    assert bad['pending_fighter']['object_type'] == 'dog'
    with pytest.raises(StoreError) as error:
        repo.confirm_capture(battle['id'], 0, bad['capture_id'])
    assert error.value.code == 'outside_theme'
    assert repo.world()['characters'] == []
    with pytest.raises(StoreError):
        repo.start_battle(battle['id'], 'quick')
    add_capture(repo, battle, 'mug', 0, 'retaken')
    repo.confirm_capture(battle['id'], 0, 'retaken')
    uncertain = add_capture(repo, battle, 'mystery-gadget', 1, 'uncertain')
    assert uncertain['theme_validation']['verdict'] == 'uncertain'
    with pytest.raises(StoreError) as error:
        repo.confirm_capture(battle['id'], 1, 'uncertain')
    assert error.value.code == 'theme_uncertain'
    good = add_capture(repo, battle, 'bottle', 1, 'second-retaken')
    assert good['theme_validation']['theme_id'] == bad['theme_validation']['theme_id'] == 'kitchen'
    repo.confirm_capture(battle['id'], 1, good['capture_id'])
    start = repo.start_battle(battle['id'], 'quick')
    assert start['theme'] == original_theme
    clock.advance()
    complete = repo.finalize_battle(battle['id'])
    assert complete['theme'] == original_theme
    assert repo.start_battle(battle['id'], 'normal') == complete
    assert len(repo.world()['characters']) == 2
    assert {r['object_type'] for r in repo.world()['characters']} == {'mug', 'bottle'}


def test_start_rechecks_capture_not_client_claim_or_eligibility_field():
    repo = MemoryRepository(Settings(repository='memory'), Clock())
    repo.create_battle('first')
    battle = repo.create_battle('kitchen')
    for slot, kind in enumerate(['mug', 'bottle']):
        add_capture(repo, battle, kind, slot, f'p{slot}')
        repo.confirm_capture(battle['id'], slot, f'p{slot}')
    # Simulate an invalid imported/old record: the saved verdict is not authority.
    observation = repo._data['captures'][key_for(battle['id'], 'p1')]['observation']
    observation['observed_object'] = {'label': 'dog', 'canonical_type_id': 'dog'}
    assert observation['theme_validation']['verdict'] == 'eligible'
    with pytest.raises(StoreError) as error:
        repo.start_battle(battle['id'], 'quick')
    assert error.value.code == 'outside_theme'
    assert repo.world()['characters'] == []


def test_historical_round_keeps_unrestricted_original_rules_without_migration():
    repo = MemoryRepository(Settings(repository='memory'), Clock())
    battle = repo.create_battle('old')
    del repo._data['battles'][battle['id']]['theme']
    assert repo.get_battle(battle['id'])['theme']['enforced'] is False
    for slot, kind in enumerate(['mystery-gadget', 'dog']):
        capture = add_capture(repo, battle, kind, slot, f'old-{slot}')
        assert capture['theme_validation']['verdict'] == 'eligible'
        repo.confirm_capture(battle['id'], slot, capture['capture_id'])
    assert repo.start_battle(battle['id'], 'quick')['status'] == 'running'
