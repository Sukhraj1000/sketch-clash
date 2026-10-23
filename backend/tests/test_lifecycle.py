"""Controlled fixtures exercise state invariants; these are not live model/Atlas tests."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.contracts import Crop, Observation
from backend.app.engine import PRESETS, DURATIONS, simulate_match, validate_fighter_config, validate_visual_spec
from backend.app.images import ImageError, ProcessedImage, normalize_image, crop_image
from backend.app.repository import MemoryRepository, StoreError, create_repository
from backend.app.service import BattleService

class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 23, tzinfo=timezone.utc)
    def __call__(self):
        return self.value.isoformat()
    def advance(self, ms=13000):
        self.value += timedelta(milliseconds=ms)

@pytest.fixture
def state():
    clock = Clock()
    settings = Settings(repository='memory', gemini_api_key='fixture-not-a-secret')
    return settings, MemoryRepository(settings, clock), clock

def photo(colour='red', size=(120, 90), format='PNG'):
    buffer = BytesIO()
    Image.new('RGB', size, colour).save(buffer, format=format)
    return buffer.getvalue()

def fighter(battle_id, slot, capture_id, image, type_id='mug', colour='#FF596E'):
    return {'battle_id': battle_id, 'player_slot': slot, 'capture_id': capture_id,
            'image_hash': image.image_hash, 'canonical_type_id': type_id, 'object_type': type_id,
            'display_name': f'{type_id}-{colour}', 'image_ref': image.image_ref, 'archetype': 'Quick',
            'stats': PRESETS['Quick'], 'visual_spec': {'template_id': type_id if type_id in ('mug', 'bottle') else 'generic',
            'palette': [colour], 'scale': 1, 'proportions': {'width': 1, 'height': 1}, 'accessories': ['eyes'],
            'animation_style': 'bouncy', 'schema_version': '1', 'appearance_seed': slot + 1},
            'validation': [{'tool': 'fixture', 'valid': True}], 'config_versions': {'fixture': '1'}}

def ready(repo, settings, request='test', types=('mug', 'bottle'), colours=('#FF596E', '#66E0D4')):
    battle = repo.create_battle(request)
    for slot in (0, 1):
        image = normalize_image(photo('red' if slot == 0 else 'blue'), 'image/png', settings)
        repo.save_media(image)
        cid = f'{request}-{slot}'
        capture = {'capture_id': cid, 'player_slot': slot, 'source': 'upload', 'image_hash': image.image_hash,
                   'image_ref': image.image_ref, 'canonical_media_id': image.image_hash,
                   'width': image.width, 'height': image.height, 'crop': None}
        repo.begin_capture(battle['id'], capture)
        observation = {'capture_id': cid, 'source': 'upload', 'image_hash': image.image_hash,
                       'image_ref': image.image_ref, 'width': image.width, 'height': image.height, 'crop': None,
                       'status': 'recognized', 'pending_fighter': fighter(battle['id'], slot, cid, image, types[slot], colours[slot])}
        repo.finish_capture(battle['id'], cid, Observation.model_validate(observation).model_dump())
        repo.confirm_capture(battle['id'], slot, cid)
    return repo.get_battle(battle['id'])

def complete(repo, clock, battle):
    started = repo.start_battle(battle['id'], 'normal')
    clock.advance()
    return repo.finalize_battle(started['id'])

def test_creation_is_idempotent_and_world_is_read_only(state):
    settings, repo, _ = state
    first = repo.create_battle('same')
    assert first == repo.create_battle('same')
    before = deepcopy(repo._data)
    assert repo.world()['characters'] == []
    assert repo._data == before
    assert first['persistence'] == 'development_memory'
    with pytest.raises(StoreError, match='not configured'):
        create_repository(Settings())

def test_pending_and_cancelled_battles_never_unlock(state):
    settings, repo, clock = state
    battle = ready(repo, settings)
    assert repo.world()['characters'] == []
    repo.start_battle(battle['id'], 'normal')
    repo.cancel_battle(battle['id'])
    clock.advance()
    with pytest.raises(StoreError):
        repo.finalize_battle(battle['id'])
    assert repo.world()['characters'] == []

def test_start_is_immutable_and_playback_modes_gate_finalization(state):
    settings, repo, clock = state
    for mode in DURATIONS:
        battle = ready(repo, settings, mode)
        first = repo.start_battle(battle['id'], mode)
        assert first == repo.start_battle(battle['id'], 'quick')
        assert first['duration_ms'] == DURATIONS[mode]
        with pytest.raises(StoreError) as early:
            repo.finalize_battle(battle['id'])
        assert early.value.code == 'playback_pending'
        clock.advance(DURATIONS[mode])
        saved = repo.finalize_battle(battle['id'])
        assert saved['status'] == 'completed'
        assert saved['events'] == first['events']
        assert saved['fighters'] == first['fighters']
        assert repo.start_battle(battle['id'], 'normal') == saved
        assert repo.finalize_battle(battle['id']) == saved
    assert all(c['distinct_battle_count'] == 3 for c in repo.world()['characters'])

def test_simultaneous_finalization_applies_effects_once(state):
    settings, repo, clock = state
    battle = ready(repo, settings)
    repo.start_battle(battle['id'], 'normal')
    clock.advance()
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: repo.finalize_battle(battle['id']), range(30)))
    assert all(r == results[0] for r in results)
    assert len(repo.world()['characters']) == 2
    assert all(c['distinct_battle_count'] == 1 for c in repo.world()['characters'])
    assert len(repo._data['encounters']) == 2

def test_duplicate_type_uses_lower_slot_and_counts_distinct_battle_once(state):
    settings, repo, clock = state
    battle = ready(repo, settings, types=('mug', 'mug'))
    complete(repo, clock, battle)
    resident = repo.world()['characters'][0]
    assert len(repo.world()['characters']) == 1
    assert resident['visual_spec']['palette'] == ['#FF596E']
    assert resident['distinct_battle_count'] == 1
    history = repo.history(resident['id'])
    assert len(history['encounters']) == 1
    assert len(history['encounters'][0]['slots']) == 2
    assert sorted(slot['won'] for slot in history['encounters'][0]['slots']) == [False, True]

def test_repeat_encounter_preserves_appearance_and_first_battle(state):
    settings, repo, clock = state
    first = ready(repo, settings, 'first')
    complete(repo, clock, first)
    old = {c['canonical_type_id']: c for c in repo.world()['characters']}
    second = ready(repo, settings, 'second', colours=('#000000', '#FFFFFF'))
    complete(repo, clock, second)
    for resident in repo.world()['characters']:
        original = old[resident['canonical_type_id']]
        for key in ('display_name', 'image_ref', 'visual_spec', 'first_battle_id', 'home_position'):
            assert resident[key] == original[key]
        assert resident['distinct_battle_count'] == 2
    # A lost HTTP response can reread/retry without recognition or any extra effects.
    before = deepcopy(repo._data)
    assert repo.get_battle(second['id']) == repo.finalize_battle(second['id'])
    assert repo._data == before

def test_simultaneous_same_type_first_insert_wins(state):
    settings, repo, clock = state
    battles = [ready(repo, settings, f'race-{i}', ('mug', 'mug'), (colour, colour)) for i, colour in enumerate(('#FF0000', '#0000FF'))]
    for battle in battles:
        repo.start_battle(battle['id'], 'normal')
    clock.advance()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda battle: repo.finalize_battle(battle['id']), battles))
    residents = repo.world()['characters']
    assert len(residents) == 1
    assert residents[0]['distinct_battle_count'] == 2
    assert sum(bool(result['completion']['new_resident_ids']) for result in results) == 1
    original = next(b for b in battles if b['id'] == residents[0]['first_battle_id'])
    assert residents[0]['visual_spec'] == original['pending_fighters'][0]['visual_spec']

def test_superseded_capture_cannot_overwrite_current_fighter(state):
    settings, repo, _ = state
    battle = ready(repo, settings)
    old = repo.get_capture(battle['id'], 'test-0')
    changed = {k: old[k] for k in ('player_slot', 'source', 'image_hash', 'image_ref', 'canonical_media_id', 'width', 'height', 'crop')}
    changed['capture_id'] = 'replacement'
    repo.begin_capture(battle['id'], changed)
    stale = repo.finish_capture(battle['id'], 'test-0', old['observation'])
    assert stale['stale']
    assert repo.get_battle(battle['id'])['pending_fighters'][0] is None
    assert repo.get_battle(battle['id'])['active_capture_ids'][0] == 'replacement'
    with pytest.raises(StoreError) as mismatch:
        repo.begin_capture(battle['id'], {**changed, 'image_hash': 'a' * 64})
    assert mismatch.value.code == 'capture_mismatch'


def test_engine_replay_and_validated_presets():
    for a in PRESETS:
        for b in PRESETS:
            inputs = [{'archetype': a, 'stats': PRESETS[a]}, {'archetype': b, 'stats': PRESETS[b]}]
            for seed in range(20):
                result = simulate_match(inputs, seed)
                assert result == simulate_match(inputs, seed)
                health = [100, 100]
                previous_time = -1
                for event in result['events']:
                    assert event['at'] > previous_time
                    previous_time = event['at']
                    health[1 - event['attacker']] -= event['damage']
                    assert all(0 <= value <= 100 for value in health)
                assert health == result['final_health']
                assert health[1 - result['winner_slot']] == 0
                assert len(result['events']) <= 11
                assert result['events'][-1]['kind'] == 'finisher'
                assert result['events'][-1]['at'] < result['duration_ms']
    assert not validate_fighter_config({'archetype': 'Quick', 'stats': {**PRESETS['Quick'], 'attack': 24}})['valid']
    assert not validate_visual_spec({'template_id': 'javascript:evil'})['valid']


def test_image_normalization_limits_orientation_and_crop():
    settings = Settings(inference_max_edge=1600)
    raw = photo(size=(3200, 1800))
    normalized = normalize_image(raw, 'image/png', settings)
    assert (normalized.width, normalized.height) == (1600, 900)
    assert normalized.image_hash == sha256(normalized.data).hexdigest()
    with Image.open(BytesIO(normalized.data)) as decoded:
        assert not decoded.getexif()
    selected = crop_image(normalized, Crop(x=100, y=100, width=200, height=300))
    assert (selected.width, selected.height) == (200, 300)
    with pytest.raises(ImageError):
        crop_image(normalized, Crop(x=1500, y=0, width=200, height=100))
    for invalid, mime in [(b'not an image', 'image/jpeg'), (raw, 'image/heic')]:
        with pytest.raises(ImageError):
            normalize_image(invalid, mime, settings)
    with pytest.raises(ImageError):
        normalize_image(raw, 'image/png', Settings(max_image_pixels=100))
    with pytest.raises(ImageError):
        normalize_image(raw, 'image/png', Settings(max_upload_bytes=10))

class ControlledRecognizer:
    def __init__(self):
        self.calls = 0
    async def recognize_capture(self, image_bytes, **kwargs):
        self.calls += 1
        await asyncio.sleep(.01)
        image = ProcessedImage(image_bytes, kwargs['width'], kwargs['height'])
        pending = fighter(kwargs['battle_id'], kwargs['player_slot'], kwargs['capture_id'], image)
        pending['image_ref'], pending['image_hash'] = kwargs['image_ref'], kwargs['image_hash']
        return Observation(capture_id=kwargs['capture_id'], source=kwargs['source'], image_ref=kwargs['image_ref'],
                           image_hash=kwargs['image_hash'], width=kwargs['width'], height=kwargs['height'], crop=kwargs['crop'],
                           status='recognized', pending_fighter=pending,
                           evidence={'fixture': 'controlled test recognizer; no live model called'})

def test_duplicate_async_capture_recovers_once_and_selected_media_is_durable(state):
    settings, repo, _ = state
    model = ControlledRecognizer()
    service = BattleService(settings, repo, model)
    battle = repo.create_battle('async')
    async def flow():
        return await asyncio.gather(*[service.submit_capture(battle['id'], 'capture', 0, 'upload', photo(), 'image/png') for _ in range(4)])
    results = asyncio.run(flow())
    assert model.calls == 1
    assert all(result == results[0] for result in results)
    selected = asyncio.run(service.select_capture(battle['id'], 'capture', Crop(x=10, y=10, width=40, height=40)))
    assert selected['capture_id'] != 'capture'
    again = asyncio.run(service.select_capture(battle['id'], 'capture', Crop(x=10, y=10, width=40, height=40)))
    assert again == selected
    assert model.calls == 2
    media = repo.get_media(selected['image_ref'].rsplit('/', 1)[1])
    assert (media['width'], media['height']) == (40, 40)
    assert repo.world()['characters'] == []

def test_api_full_controlled_upload_flow_and_authority(state):
    from backend.app.main import create_app
    settings, repo, clock = state
    model = ControlledRecognizer()
    with TestClient(create_app(settings, repo, model)) as client:
        assert client.get('/api/health').json()['persistence'] == 'development_memory'
        battle = client.post('/api/battles', json={'request_id': 'http'}).json()
        assert client.post('/api/battles', json={'request_id': 'http', 'world_id': 'unauthorized'}).status_code == 422
        for slot in (0, 1):
            response = client.post(f"/api/battles/{battle['id']}/captures", data={'capture_id': f'http-{slot}', 'slot': slot, 'source': 'upload'}, files={'image': ('test.png', photo(), 'image/png')})
            assert response.status_code == 200, response.text
            assert response.json()['pending_fighter']['image_ref'].startswith('/api/media/')
            confirmed = client.post(f"/api/battles/{battle['id']}/confirm", json={'player_slot': slot, 'capture_id': f'http-{slot}'})
            assert confirmed.status_code == 200, confirmed.text
        started = client.post(f"/api/battles/{battle['id']}/start", json={'playback_mode': 'quick'})
        assert started.status_code == 200, started.text
        assert client.post(f"/api/battles/{battle['id']}/finalize", json={}).status_code == 409
        clock.advance(6400)
        done = client.post(f"/api/battles/{battle['id']}/finalize", json={'winner_slot': 1-started.json()['winner_slot']})
        assert done.status_code == 200
        assert done.json()['winner_slot'] == started.json()['winner_slot']
        world = client.get('/api/world').json()
        assert len(world['characters']) == 1
        assert world['characters'][0]['distinct_battle_count'] == 1
        before_calls = model.calls
        assert client.get('/api/world').json() == world
        assert model.calls == before_calls
        resident = world['characters'][0]
        assert client.get(resident['image_ref']).headers['content-type'] == 'image/jpeg'
        assert client.patch(f"/api/world/characters/{resident['id']}", json={'activity': 'rest'}).json()['state']['activity'] == 'rest'
        assert client.get('/api/world').json()['characters'][0]['state']['activity'] == 'rest'


def test_recognition_requires_explicit_confirmation_and_retake_invalidates_it(state):
    settings, repo, _ = state
    battle = ready(repo, settings, 'confirmation')
    original = repo.get_capture(battle['id'], 'confirmation-0')
    replacement = {key: original[key] for key in ('player_slot', 'source', 'image_hash', 'image_ref', 'canonical_media_id', 'width', 'height', 'crop')}
    replacement['capture_id'] = 'new-capture'
    repo.begin_capture(battle['id'], replacement)
    observation = deepcopy(original['observation'])
    observation['capture_id'] = 'new-capture'
    observation['pending_fighter']['capture_id'] = 'new-capture'
    repo.finish_capture(battle['id'], 'new-capture', observation)
    checked = repo.get_battle(battle['id'])
    assert checked['pending_fighters'][0] is not None
    assert checked['confirmed_capture_ids'][0] is None
    assert checked['status'] == 'draft'
    with pytest.raises(StoreError):
        repo.start_battle(battle['id'], 'normal')
    with pytest.raises(StoreError) as old:
        repo.confirm_capture(battle['id'], 0, 'confirmation-0')
    assert old.value.code == 'stale_capture'
    confirmed = repo.confirm_capture(battle['id'], 0, 'new-capture')
    assert confirmed['status'] == 'ready'
    assert repo.confirm_capture(battle['id'], 0, 'new-capture') == confirmed
    assert repo.world()['characters'] == []


def test_selection_cannot_replace_a_newer_capture_between_read_and_transaction(state):
    settings, repo, _ = state
    battle = ready(repo, settings, 'selection-race')
    old = repo.get_capture(battle['id'], 'selection-race-0')
    replacement = {key: old[key] for key in ('player_slot', 'source', 'image_hash', 'image_ref', 'canonical_media_id', 'width', 'height', 'crop')}
    replacement['capture_id'] = 'newer-retake'
    repo.begin_capture(battle['id'], replacement)
    with pytest.raises(StoreError) as stale:
        repo.begin_capture(battle['id'], {**replacement, 'capture_id': 'old-selection'}, expected_capture_id='selection-race-0')
    assert stale.value.code == 'stale_capture'
    assert repo.get_battle(battle['id'])['active_capture_ids'][0] == 'newer-retake'


def test_service_failure_can_retry_same_capture_and_releases_locks(state):
    settings, repo, _ = state
    class RetryRecognizer(ControlledRecognizer):
        async def recognize_capture(self, image_bytes, **kwargs):
            if self.calls == 0:
                self.calls += 1
                return Observation(capture_id=kwargs['capture_id'], source=kwargs['source'], image_ref=kwargs['image_ref'],
                    image_hash=kwargs['image_hash'], width=kwargs['width'], height=kwargs['height'], status='needs_recapture',
                    evidence={'gemini': {'status': 'failed', 'error_category': 'TimeoutError'}})
            return await super().recognize_capture(image_bytes, **kwargs)
    model = RetryRecognizer()
    service = BattleService(settings, repo, model)
    battle = repo.create_battle('retry-service')
    async def flow():
        failed = await service.submit_capture(battle['id'], 'same', 0, 'upload', photo(), 'image/png')
        recovered = await service.submit_capture(battle['id'], 'same', 0, 'upload', photo(), 'image/png')
        return failed, recovered
    failed, recovered = asyncio.run(flow())
    assert failed['status'] == 'needs_recapture'
    assert recovered['status'] == 'recognized'
    assert model.calls == 2
    assert service._locks == {}


def test_rejected_post_start_upload_does_not_store_an_orphan_image(state):
    settings, repo, _ = state
    battle = ready(repo, settings, 'sealed')
    repo.start_battle(battle['id'], 'normal')
    before_media = deepcopy(repo._data['media'])
    service = BattleService(settings, repo, ControlledRecognizer())
    with pytest.raises(StoreError):
        asyncio.run(service.submit_capture(battle['id'], 'late', 0, 'upload', photo('green'), 'image/png'))
    assert repo._data['media'] == before_media


def test_declared_mime_must_match_decoded_format():
    with pytest.raises(ImageError, match='do not match'):
        normalize_image(photo(format='JPEG'), 'image/png', Settings())


def test_slow_old_upload_normalization_cannot_displace_newer_retake(state, monkeypatch):
    import time
    import threading
    import backend.app.service as service_module
    settings, repo, _ = state
    old_bytes, new_bytes = photo('red'), photo('blue')
    original_normalize = service_module.normalize_image
    normalizing = threading.Event()
    def slow_normalize(data, mime, config):
        if data == old_bytes:
            normalizing.set()
            time.sleep(.08)
        return original_normalize(data, mime, config)
    monkeypatch.setattr(service_module, 'normalize_image', slow_normalize)
    class SlowOldRecognizer(ControlledRecognizer):
        async def recognize_capture(self, data, **kwargs):
            if kwargs['capture_id'] == 'old':
                await asyncio.sleep(.08)
            return await super().recognize_capture(data, **kwargs)
    service = BattleService(settings, repo, SlowOldRecognizer())
    battle = repo.create_battle('normalization-race')
    async def flow():
        old = asyncio.create_task(service.submit_capture(battle['id'], 'old', 0, 'upload', old_bytes, 'image/png'))
        await asyncio.to_thread(normalizing.wait, 1)
        new = asyncio.create_task(service.submit_capture(battle['id'], 'new', 0, 'upload', new_bytes, 'image/png'))
        return await asyncio.gather(old, new, return_exceptions=True)
    old, new = asyncio.run(flow())
    assert repo.get_battle(battle['id'])['active_capture_ids'][0] == 'new'
    assert repo.get_battle(battle['id'])['pending_fighters'][0]['capture_id'] == 'new'
    assert new['status'] == 'recognized'
    assert isinstance(old, StoreError) or old['stale'] is True
    assert service._locks == {}


def test_world_scoped_keys_are_unambiguous_for_colon_request_ids():
    from backend.app.repository import key_for
    assert key_for('a', 'b:c') != key_for('a:b', 'c')


def test_cross_origin_mutations_are_rejected_before_writing(state):
    from backend.app.main import create_app
    settings, repo, _ = state
    with TestClient(create_app(settings, repo, ControlledRecognizer())) as client:
        blocked = client.post('/api/battles', json={'request_id': 'blocked'}, headers={'Origin': 'https://unrelated.example'})
        assert blocked.status_code == 403
        assert repo._data.get('battles', {}) == {}
        allowed = client.post('/api/battles', json={'request_id': 'allowed'}, headers={'Origin': 'http://127.0.0.1:5173'})
        assert allowed.status_code == 200
