"""Orchestrates bounded recognition outside storage transactions and the event loop."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Any
from .config import Settings
from .contracts import Crop, Observation, PendingFighter
from .engine import validate_fighter_config, validate_visual_spec
from .images import ProcessedImage, normalize_image, crop_image
from .repository import Repository, StoreError

class BattleService:
    def __init__(self, settings: Settings, repository: Repository, recognizer: Any):
        self.settings, self.repository, self.recognizer = settings, repository, recognizer
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def _capture_lock(self, key: str):
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        self._locks[key] = (lock, users + 1)
        try:
            async with lock:
                yield
        finally:
            remaining = self._locks[key][1] - 1
            if remaining:
                self._locks[key] = (lock, remaining)
            else:
                del self._locks[key]

    async def submit_capture(self, battle_id: str, capture_id: str, slot: int, source: str,
                             data: bytes, mime_type: str, crop: Crop | None = None) -> dict:
        # Serialize short intake work in arrival order, not model inference: an older large
        # photo cannot finish CPU normalization after a newer retake and claim the slot back.
        async with self._capture_lock(f'intake:{battle_id}:{slot}'):
            await asyncio.to_thread(self.repository.get_battle, battle_id)
            canonical = await asyncio.to_thread(normalize_image, data, mime_type, self.settings)
            selected, capture = await self._register_capture(battle_id, capture_id, slot, source, canonical, crop)
        return await self._recognize_registered(battle_id, capture_id, slot, source, canonical, selected, capture, crop)

    async def select_capture(self, battle_id: str, capture_id: str, crop: Crop) -> dict:
        capture = await asyncio.to_thread(self.repository.get_capture, battle_id, capture_id)
        battle = await asyncio.to_thread(self.repository.get_battle, battle_id)
        revision = sha256(f'{capture_id}:{crop.model_dump_json()}'.encode()).hexdigest()[:32]
        if battle['active_capture_ids'][capture['player_slot']] not in (capture_id, revision):
            raise StoreError('This photograph has been replaced. Select the current photograph.', 409, 'stale_capture')
        media = await asyncio.to_thread(self.repository.get_media, capture['canonical_media_id'])
        canonical = ProcessedImage(media['data'], media['width'], media['height'], media['mime_type'])
        # A selection is a new immutable capture revision. Repeating the exact selection recovers the same ID.
        return await self._process(battle_id, revision, capture['player_slot'], capture['source'], canonical, crop,
                                   expected_capture_id=capture_id)

    async def _process(self, battle_id: str, capture_id: str, slot: int, source: str,
                       canonical: ProcessedImage, crop: Crop | None, expected_capture_id: str | None = None) -> dict:
        selected, capture = await self._register_capture(battle_id, capture_id, slot, source, canonical, crop, expected_capture_id)
        return await self._recognize_registered(battle_id, capture_id, slot, source, canonical, selected, capture, crop)

    async def _register_capture(self, battle_id: str, capture_id: str, slot: int, source: str,
                               canonical: ProcessedImage, crop: Crop | None,
                               expected_capture_id: str | None = None) -> tuple[ProcessedImage, dict]:
        selected = await asyncio.to_thread(crop_image, canonical, crop) if crop else canonical
        capture = {'capture_id': capture_id, 'player_slot': slot, 'source': source,
                   'image_hash': selected.image_hash, 'image_ref': selected.image_ref,
                   'canonical_media_id': canonical.image_hash, 'width': canonical.width, 'height': canonical.height,
                   'crop': crop.model_dump() if crop else None}
        await asyncio.to_thread(self.repository.begin_capture, battle_id, capture, expected_capture_id)
        return selected, capture

    async def _recognize_registered(self, battle_id: str, capture_id: str, slot: int, source: str,
                                    canonical: ProcessedImage, selected: ProcessedImage,
                                    capture: dict, crop: Crop | None) -> dict:
        lock_key = f'{battle_id}:{capture_id}'
        async with self._capture_lock(lock_key):
            existing = await asyncio.to_thread(self.repository.get_capture, battle_id, capture_id)
            if existing.get('observation'):
                return await self._recover_observation(battle_id, existing)
            battle = await asyncio.to_thread(self.repository.get_battle, battle_id)
            if battle['active_capture_ids'][slot] != capture_id or battle['status'] not in ('draft', 'ready'):
                raise StoreError('This capture has been superseded or its battle was closed.', 409, 'stale_capture')
            try:
                await asyncio.to_thread(self.repository.save_media, canonical)
                if selected.image_hash != canonical.image_hash:
                    await asyncio.to_thread(self.repository.save_media, selected)
                result = await self.recognizer.recognize_capture(
                    canonical.data, battle_id=battle_id, player_slot=slot, capture_id=capture_id,
                    image_hash=selected.image_hash, image_ref=selected.image_ref,
                    width=canonical.width, height=canonical.height, source=source, crop=crop)
                observation = Observation.model_validate(result).model_dump()
                self._validate_identity(observation, capture, battle_id)
                component = observation.get('evidence', {}).get('gemini', {})
                if component.get('status') in ('failed', 'unavailable'):
                    # Do not permanently memoize transport/configuration failures as image judgments.
                    await asyncio.to_thread(self.repository.fail_capture, battle_id, capture_id, 'recognition_retryable')
                    current = await asyncio.to_thread(self.repository.get_battle, battle_id)
                    observation['stale'] = current['active_capture_ids'][slot] != capture_id or current['status'] not in ('draft', 'ready')
                    return observation
                return await asyncio.to_thread(self.repository.finish_capture, battle_id, capture_id, observation)
            except BaseException as exc:
                # A transport failure is recoverable using the same ID. Cancellation never unlocks anything.
                await asyncio.shield(asyncio.to_thread(self.repository.fail_capture, battle_id, capture_id, type(exc).__name__))
                raise

    async def _recover_observation(self, battle_id: str, capture: dict) -> dict:
        battle = await asyncio.to_thread(self.repository.get_battle, battle_id)
        observation = dict(capture['observation'])
        observation['stale'] = battle['active_capture_ids'][capture['player_slot']] != capture['capture_id'] or battle['status'] in ('cancelled', 'failed')
        return observation

    @staticmethod
    def _validate_identity(observation: dict, capture: dict, battle_id: str) -> None:
        for key in ('capture_id', 'image_hash', 'image_ref', 'source', 'width', 'height', 'crop'):
            if observation.get(key) != capture.get(key):
                raise StoreError('Recognition returned mismatched image identity.', 502, 'recognition_contract')
        fighter = observation.get('pending_fighter')
        if observation['status'] == 'recognized' and not fighter:
            raise StoreError('Recognition did not produce a checked fighter.', 502, 'recognition_contract')
        if fighter:
            expected = {'battle_id': battle_id, 'player_slot': capture['player_slot'],
                        'capture_id': capture['capture_id'], 'image_hash': capture['image_hash'], 'image_ref': capture['image_ref']}
            if any(fighter.get(k) != v for k, v in expected.items()):
                raise StoreError('Fighter identity does not match the confirmed photograph.', 502, 'recognition_contract')
            if not validate_fighter_config(fighter)['valid'] or not validate_visual_spec(fighter['visual_spec'])['valid']:
                raise StoreError('Fighter configuration failed final server validation.', 502, 'recognition_contract')
