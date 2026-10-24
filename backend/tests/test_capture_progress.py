"""Read-only progress and explicit live-profile upgrades; no provider requests."""
from copy import deepcopy
import asyncio

import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repository import MemoryRepository, StoreError, key_for
from backend.app.pipeline import BASELINE_VERSION, active_key
from backend.tests.test_lifecycle import photo
from backend.app.images import normalize_image
from backend.app.service import BattleService
from backend.app.contracts import Observation


def fixture():
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    battle = repo.create_battle('capture-stage-test')
    image = normalize_image(photo(), 'image/png', settings)
    capture = {'capture_id': 'photo-1', 'player_slot': 0, 'source': 'upload',
        'image_hash': image.image_hash, 'image_ref': image.image_ref, 'canonical_media_id': image.image_hash,
        'width': image.width, 'height': image.height, 'crop': None}
    repo.begin_capture(battle['id'], capture)
    return settings, repo, battle['id'], capture


def test_progress_is_read_only_safe_and_terminal_state_cannot_regress():
    _, repo, battle, capture = fixture()
    cid = capture['capture_id']
    repo.update_capture_progress(battle, cid, {'stage': 'queued', 'model': 'gemini-3.8-flash', 'attempt': 1,
                                             'message': 'untrusted stage text', 'api_key': 'not-public'})
    before = deepcopy(repo._data)
    progress = repo.capture_progress(battle, cid)
    assert repo._data == before
    assert progress['stage'] == 'queued' and progress['attempt'] == 1
    assert 'priority' in progress['message']
    assert 'untrusted' not in str(progress) and 'api_key' not in progress
    repo.fail_capture(battle, cid, 'fixture_failure')
    repo.update_capture_progress(battle, cid, {'stage': 'gemini_recognition'})
    assert repo.capture_progress(battle, cid)['status'] == 'failed'
    repo.begin_capture(battle, capture)
    assert repo.capture_progress(battle, cid)['stage'] == 'registered'
    repo.finish_capture(battle, cid, {'status': 'needs_recapture'})
    repo.update_capture_progress(battle, cid, {'stage': 'queued'})
    assert repo.capture_progress(battle, cid)['status'] == 'complete'


def test_progress_route_returns_stage_without_starting_recognition():
    settings, repo, battle, capture = fixture()
    class NoRecognition:
        async def recognize_capture(self, *args, **kwargs):
            raise AssertionError('Progress reads cannot perform recognition')
    with TestClient(create_app(settings, repository=repo, recognizer=NoRecognition())) as client:
        repo.update_capture_progress(battle, capture['capture_id'], {'stage': 'queued'})
        response = client.get(f'/api/battles/{battle}/captures/{capture["capture_id"]}/progress')
        assert response.status_code == 200
        assert response.json()['stage'] == 'queued'
        assert 'min_dispatch_interval_seconds' in response.json()['queue']
        assert client.get(f'/api/battles/missing/captures/{capture["capture_id"]}/progress').status_code == 404
        assert client.get(f'/api/battles/{battle}/captures/missing/progress').status_code == 404


@pytest.mark.asyncio
async def test_inflight_progress_is_saved_and_duplicate_capture_recovers_without_repeating_work():
    settings, repo, battle, _ = fixture()
    entered, release = asyncio.Event(), asyncio.Event()
    class FakeRecognition:
        calls = 0
        async def recognize_capture(self, data, **kwargs):
            self.calls += 1
            await kwargs['on_progress']({'stage': 'queued', 'model': 'gemini-3.8-flash', 'attempt': 1})
            entered.set()
            await release.wait()
            await kwargs['on_progress']({'stage': 'gemini_recognition', 'model': 'gemini-3.8-flash'})
            return Observation(**{k: kwargs[k] for k in ['capture_id', 'source', 'image_ref', 'image_hash', 'width', 'height']}, status='needs_recapture')
    recognizer = FakeRecognition()
    service = BattleService(settings, repo, recognizer)
    task = asyncio.create_task(service.submit_capture(battle, 'new-photo', 0, 'upload', photo(), 'image/png'))
    await asyncio.wait_for(entered.wait(), 2)
    assert repo.capture_progress(battle, 'new-photo')['stage'] == 'queued'
    release.set()
    result = await task
    assert repo.capture_progress(battle, 'new-photo')['status'] == 'complete'
    assert await service.submit_capture(battle, 'new-photo', 0, 'upload', photo(), 'image/png') == result
    assert recognizer.calls == 1


def test_fast_profile_upgrade_is_explicit_idempotent_and_preserves_pinned_rounds():
    from backend.app.pipeline import FAST_LIVE_VERSION, FAST_LIVE_CONFIG
    _, repo, old, _ = fixture()
    baseline = deepcopy(repo.get_pipeline(BASELINE_VERSION))
    first = repo.enable_fast_live_pipeline()
    assert first['active_version_id'] == FAST_LIVE_VERSION
    assert repo.enable_fast_live_pipeline() == first
    assert repo.get_pipeline(BASELINE_VERSION) == baseline
    assert repo.get_pipeline(FAST_LIVE_VERSION)['config'] == FAST_LIVE_CONFIG
    assert repo.get_battle(old)['pipeline_version_id'] == BASELINE_VERSION
    assert repo.create_battle('new-round')['pipeline_version_id'] == FAST_LIVE_VERSION
    assert len(repo._data['pipelineChanges']) == 1


def test_fast_profile_does_not_replace_a_custom_active_candidate():
    _, repo, _, _ = fixture()
    def custom(tx):
        value = tx.get('qualityState', active_key(repo.world_id))
        value['active_version_id'] = 'reviewed-custom'
        tx.put('qualityState', value)
    repo.transaction(custom)
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as error:
        repo.enable_fast_live_pipeline()
    assert error.value.code == 'pipeline_conflict'
    assert repo._data == before
