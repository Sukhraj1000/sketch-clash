"""Controlled engineering fixtures; no recognition-quality or preference claim."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from app.config import Settings
from app.contracts import Observation
from app.engine import PRESETS
from app.pipeline import BASELINE_CONFIG, BASELINE_VERSION, LEGACY_VERSION, active_key, version_key, validate_pipeline_config
from app.repository import MemoryRepository, StoreError
from app.service import BattleService
from app.recognition import RecognitionService


def photo():
    out = BytesIO()
    Image.new('RGB', (120, 90), 'red').save(out, 'JPEG')
    return out.getvalue()


def visual(template='mug'):
    return dict(template_id=template, palette=['#FF0000'], scale=1, proportions={'width': 1, 'height': 1},
                accessories=['eyes'], animation_style='calm', schema_version='1', appearance_seed=1)


class ControlledRecognizer:
    def __init__(self):
        self.calls = []

    async def recognize_capture(self, data, **kw):
        self.calls.append(deepcopy(kw))
        # Deliberately tries to change identity and strength in every style retry.
        corrected = kw.get('correction_context')
        kind, archetype = ('bottle', 'Power') if corrected else ('mug', 'Quick')
        fighter = dict(battle_id=kw['battle_id'], player_slot=kw['player_slot'], capture_id=kw['capture_id'],
            image_hash=kw['image_hash'], image_ref=kw['image_ref'], canonical_type_id=kind, object_type=kind,
            display_name='Fixture fighter', archetype=archetype, stats=PRESETS[archetype], visual_spec=visual(kind))
        return Observation(**{key: kw[key] for key in ['capture_id', 'source', 'image_ref', 'image_hash', 'width', 'height', 'crop']},
            status='recognized', proposed_label=kind, pending_fighter=fighter, visible_features=['round body'])


@pytest.fixture
def setup():
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    model = ControlledRecognizer()
    return repo, BattleService(settings, repo, model), model


async def prepare(repo, service, request='round', slot=0):
    battle = repo.create_battle(request)
    result = await service.submit_capture(battle['id'], f'capture-{slot}', slot, 'upload', photo(), 'image/jpeg')
    return battle, result


def feedback(obs, **extra):
    return dict(idempotency_key='feedback-1', output_id=obs['output_id'], pipeline_version_id=obs['pipeline_version_id'],
                recognition_verdict='correct', creative_verdict='skipped', **extra)


def correction(obs, kind='style', key='revision-1', **extra):
    return dict(idempotency_key=key, output_id=obs['output_id'], pipeline_version_id=obs['pipeline_version_id'],
                kind=kind, details='Make the colour closer to the photo.', **extra)


def test_pipeline_baseline_initialization_is_atomic_and_existing_pointer_is_not_reset(setup):
    repo, _, _ = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: repo.initialize_pipeline(), range(20)))
    assert len(repo._data['pipelineVersions']) == 1
    baseline = deepcopy(repo.get_pipeline(BASELINE_VERSION))
    first = repo.create_battle('before-change')
    def fixture_activation(tx):
        tx.put('pipelineVersions', {'_id': version_key(repo.world_id, 'fixture-candidate'), 'id': 'fixture-candidate',
            'world_id': repo.world_id, 'config': {**BASELINE_CONFIG, 'clarification_mode': 'conservative'}})
        pointer = tx.get('qualityState', active_key(repo.world_id))
        pointer['active_version_id'] = 'fixture-candidate'
        tx.put('qualityState', pointer)
    repo.transaction(fixture_activation)
    repo.initialize_pipeline()
    second = repo.create_battle('after-change')
    assert repo.get_battle(first['id'])['pipeline_version_id'] == BASELINE_VERSION
    assert second['pipeline_version_id'] == 'fixture-candidate'
    assert repo.get_pipeline(BASELINE_VERSION) == baseline


def test_pipeline_allowlist_cannot_modify_model_or_game_configuration():
    for value in [{'model': 'another-model'}, {'stats': {'attack': 999}}, {'reference_limit': 4},
                  {'recognition_guidance': 'x'*1201}, {'thinking_level': 'high'}]:
        with pytest.raises(ValidationError):
            validate_pipeline_config(value)


@pytest.mark.asyncio
async def test_exact_proposal_feedback_is_immutable_and_distinguishes_skips(setup):
    repo, service, _ = setup
    battle, obs = await prepare(repo, service)
    before = deepcopy(repo.world())
    body = feedback(obs)
    saved = repo.submit_feedback(battle['id'], obs['capture_id'], body)
    assert saved['creative_verdict'] == 'skipped'
    assert saved['recognition_verdict'] == 'correct'
    assert saved['shared_consent'] is False
    assert saved['review_status'] == 'unreviewed'
    assert repo.submit_feedback(battle['id'], obs['capture_id'], body) == saved
    with pytest.raises(StoreError, match='different review'):
        repo.submit_feedback(battle['id'], obs['capture_id'], {**body, 'creative_verdict': 'change'})
    with pytest.raises(StoreError, match='exact proposal'):
        repo.submit_feedback(battle['id'], obs['capture_id'], {**body, 'idempotency_key': 'other', 'output_id': 'wrong'})
    assert repo.world() == before
    repo.confirm_capture(battle['id'], 0, obs['capture_id'])
    assert repo.submit_feedback(battle['id'], obs['capture_id'], body) == saved
    with pytest.raises(StoreError, match='before this fighter'):
        repo.submit_feedback(battle['id'], obs['capture_id'], {**body, 'idempotency_key': 'late'})


@pytest.mark.asyncio
async def test_style_correction_lineage_is_bounded_and_never_rerolls_identity_or_stats(setup):
    repo, service, model = setup
    battle, original = await prepare(repo, service)
    request = correction(original)
    changed = await service.correct_capture(battle['id'], original['capture_id'], request)
    assert changed['output_id'] != original['output_id']
    assert changed['capture_id'] != original['capture_id']
    assert changed['parent_output_id'] == original['output_id']
    assert repo.get_capture(battle['id'], original['capture_id'])['observation'] == original
    for key in ('canonical_type_id', 'archetype', 'stats', 'observed_object'):
        assert changed['pending_fighter'][key] == original['pending_fighter'][key]
    assert changed['pending_fighter']['visual_spec']['template_id'] == 'mug'
    assert changed['observed_object'] == original['observed_object']
    assert await service.correct_capture(battle['id'], original['capture_id'], request) == changed
    assert len(model.calls) == 2
    twice = await service.correct_capture(battle['id'], changed['capture_id'], correction(changed, key='revision-2'))
    with pytest.raises(StoreError, match='Two corrections'):
        await service.correct_capture(battle['id'], twice['capture_id'], correction(twice, key='revision-3'))
    assert repo.world()['characters'] == []


@pytest.mark.asyncio
async def test_factual_correction_uses_recognizer_and_locked_fighter_rejects_changes(setup):
    repo, service, model = setup
    battle, original = await prepare(repo, service)
    request = correction(original, kind='factual', canonical_label='water bottle')
    corrected = await service.correct_capture(battle['id'], original['capture_id'], request)
    assert model.calls[-1]['correction_context']['request']['canonical_label'] == 'water bottle'
    assert corrected['pending_fighter']['canonical_type_id'] == 'bottle'
    repo.confirm_capture(battle['id'], 0, corrected['capture_id'])
    with pytest.raises(StoreError, match='confirmed fighter'):
        await service.correct_capture(battle['id'], corrected['capture_id'], correction(corrected, key='locked'))


@pytest.mark.asyncio
async def test_legacy_recovery_preserves_accepted_fighter_and_marks_unknown_provenance(setup):
    repo, service, _ = setup
    battle, original = await prepare(repo, service)
    repo.confirm_capture(battle['id'], 0, original['capture_id'])
    stored = repo._data['battles'][battle['id']]
    stored.pop('pipeline_version_id')
    for key in ('output_id', 'pipeline_version_id', 'parent_output_id', 'observed_object'):
        stored['pending_fighters'][0].pop(key, None)
    before_fighter = deepcopy(stored['pending_fighters'][0])
    recovered = repo.get_battle(battle['id'])
    assert recovered['pipeline_version_id'] == LEGACY_VERSION
    assert recovered['pending_fighters'][0] == before_fighter
    assert repo.get_pipeline(LEGACY_VERSION)['config'] == BASELINE_CONFIG
    assert repo.confirm_capture(battle['id'], 0, original['capture_id'])['pending_fighters'][0] == before_fighter


class Evidence:
    async def detect(self, _): return {'status': 'empty', 'detections': []}
    async def read_text(self, _): return {'status': 'empty', 'text': []}
    def close(self): pass


class Client:
    def __init__(self):
        self.calls = []
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self.create))
    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(steps=[{'type': 'function_call', 'id': 'proposal', 'name': 'prepare_fighter',
            'arguments': {'status': 'recognized', 'proposed_label': 'mug', 'canonical_type_candidate': 'mug',
                'visible_features': ['handle'], 'uncertainty': [], 'display_name': 'Fixture mug', 'archetype': 'Quick',
                'stats': PRESETS['Quick'], 'visual_spec': visual()}}], usage={'total_tokens': 22}, model_version='fixture-version')


class Budget:
    def __init__(self): self.reserved, self.completed = [], []
    async def reserve(self, **kwargs):
        self.reserved.append(kwargs)
        return len(self.reserved)
    async def complete(self, reservation, response): self.completed.append(reservation)


@pytest.mark.asyncio
async def test_isolated_evaluation_uses_pinned_configuration_budget_and_never_persists_catalog():
    client, budget = Client(), Budget()
    service = RecognitionService(Settings(), evidence_runner=Evidence(), client=client)
    writes = []
    async def forbidden(record): writes.append(record)
    service.catalog.ensure_type = forbidden
    observed = await service.recognize_capture(photo(), battle_id='isolated-evaluation', player_slot=0, capture_id='opaque-id',
        image_hash='a'*64, image_ref='/api/media/'+'a'*64, width=120, height=90,
        pipeline_config={**BASELINE_CONFIG, 'recognition_guidance': 'Look carefully for a handle.'},
        pipeline_version_id='fixture-v2', persist_catalog=False, request_budget=budget)
    assert observed.pipeline_version_id == 'fixture-v2'
    assert observed.pending_fighter.pipeline_version_id == 'fixture-v2'
    assert writes == []
    assert len(budget.reserved) == len(budget.completed) == 1
    assert budget.reserved[0]['output_tokens'] == 4096
    assert client.calls[0]['generation_config']['max_output_tokens'] == 4096
    assert 'Look carefully for a handle.' in client.calls[0]['system_instruction']
    assert client.calls[0]['store'] is False
    assert observed.evidence['provider_requests'][0]['model_version'] == 'fixture-version'
    assert observed.evidence['provider_requests'][0]['usage']['total_tokens'] == 22


@pytest.mark.asyncio
async def test_saved_resident_preview_is_original_and_never_another_players_proposal(setup):
    from app.repository import key_for
    repo, service, _ = setup
    resident = {'_id': key_for(repo.world_id, 'mug')[:32], 'id': 'saved-mug', 'world_id': repo.world_id,
        'canonical_type_id': 'mug', 'object_type': 'mug', 'display_name': 'Original resident',
        'image_ref': '/api/media/'+'b'*64, 'visual_spec': visual(), 'archetype': 'Guard',
        'home_position': {'x': 1, 'y': 0, 'z': 2}, 'distinct_battle_count': 4}
    repo.transaction(lambda tx: tx.put('worldCharacters', resident))
    before = deepcopy(repo.world())
    battle, first = await prepare(repo, service)
    second = await service.submit_capture(battle['id'], 'capture-1', 1, 'upload', photo(), 'image/jpeg')
    assert second['saved_resident_preview']['display_name'] == 'Original resident'
    assert second['saved_resident_preview']['image_ref'] == '/api/media/'+'b'*64
    assert second['saved_resident_preview']['image_ref'] != first['image_ref']
    assert 'pending_fighters' not in second
    assert repo.world() == before


@pytest.mark.asyncio
async def test_factual_suggestion_is_not_a_blind_label_override():
    repo = MemoryRepository(Settings(repository='memory'))
    client = Client()  # Always sees a mug even if the player suggests bottle.
    recognizer = RecognitionService(Settings(), evidence_runner=Evidence(), client=client)
    service = BattleService(Settings(), repo, recognizer)
    battle, original = await prepare(repo, service)
    revised = await service.correct_capture(battle['id'], original['capture_id'],
        correction(original, kind='factual', canonical_label='bottle'))
    assert revised['pending_fighter']['canonical_type_id'] == 'mug'
    assert revised['observed_object']['canonical_type_id'] == 'mug'
    assert 'bottle' in client.calls[-1]['input'][0]['content'][0]['text']
