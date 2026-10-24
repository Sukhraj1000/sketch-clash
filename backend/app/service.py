"""Orchestrates bounded recognition outside storage transactions and the event loop."""
from __future__ import annotations
import asyncio
import inspect
import json
import re
import logging
from copy import deepcopy
from uuid import uuid4
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Any
from .config import Settings
from .contracts import Crop, Observation, PendingFighter, CorrectionRequest
from .engine import validate_fighter_config, validate_visual_spec
from .images import ProcessedImage, normalize_image, crop_image
from .repository import Repository, StoreError
from .provider_queue import require_ai_enabled
from .retail_prices import RetailPrices

logger = logging.getLogger('sketch.capture')

class BattleService:
    def __init__(self, settings: Settings, repository: Repository, recognizer: Any):
        self.settings, self.repository, self.recognizer = settings, repository, recognizer
        self.reference_provider = None
        self.market_prices = RetailPrices(settings, repository, recognizer)
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
        require_ai_enabled(self.settings)
        # Serialize short intake work in arrival order, not model inference: an older large
        # photo cannot finish CPU normalization after a newer retake and claim the slot back.
        async with self._capture_lock(f'intake:{battle_id}:{slot}'):
            await asyncio.to_thread(self.repository.get_battle, battle_id)
            canonical = await asyncio.to_thread(normalize_image, data, mime_type, self.settings)
            selected, capture = await self._register_capture(battle_id, capture_id, slot, source, canonical, crop)
        return await self._recognize_registered(battle_id, capture_id, slot, source, canonical, selected, capture, crop)

    async def select_capture(self, battle_id: str, capture_id: str, crop: Crop) -> dict:
        require_ai_enabled(self.settings)
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

    async def correct_capture(self, battle_id: str, capture_id: str, body: dict) -> dict:
        require_ai_enabled(self.settings)
        request = CorrectionRequest.model_validate(body).model_dump()
        if request['kind'] == 'factual' and (not request['canonical_label'] or not re.fullmatch(r"[\w \-']{1,80}", request['canonical_label'])):
            raise StoreError('Use a concise object label, such as mug or water bottle.', 422, 'invalid_correction')
        capture = await asyncio.to_thread(self.repository.get_capture, battle_id, capture_id)
        observation = capture.get('observation') or {}
        if observation.get('output_id') != request['output_id'] or observation.get('pipeline_version_id') != request['pipeline_version_id']:
            raise StoreError('The correction does not match the proposal shown.', 409, 'proposal_mismatch')
        if request['kind'] == 'style' and not observation.get('pending_fighter'):
            raise StoreError('Prepare a recognised fighter before changing its details.', 409, 'fighter_not_ready')
        revision = sha256(json.dumps([battle_id, capture_id, request], sort_keys=True).encode()).hexdigest()[:32]
        media = await asyncio.to_thread(self.repository.get_media, capture['canonical_media_id'])
        canonical = ProcessedImage(media['data'], media['width'], media['height'], media['mime_type'])
        crop = Crop.model_validate(capture['crop']) if capture.get('crop') else None
        correction = {'request': request, 'parent_capture_id': capture_id, 'parent_output_id': observation['output_id'],
                      'original_fighter': observation.get('pending_fighter'), 'original_observed_object': observation.get('observed_object'),
                      'original_visible_features': observation.get('visible_features', []),
                      'original_uncertainty': observation.get('uncertainty', [])}
        return await self._process(battle_id, revision, capture['player_slot'], capture['source'], canonical, crop,
                                   expected_capture_id=capture_id, correction=correction)

    async def _process(self, battle_id: str, capture_id: str, slot: int, source: str,
                       canonical: ProcessedImage, crop: Crop | None, expected_capture_id: str | None = None,
                       correction: dict | None = None) -> dict:
        selected, capture = await self._register_capture(battle_id, capture_id, slot, source, canonical, crop, expected_capture_id, correction)
        return await self._recognize_registered(battle_id, capture_id, slot, source, canonical, selected, capture, crop)

    async def _register_capture(self, battle_id: str, capture_id: str, slot: int, source: str,
                               canonical: ProcessedImage, crop: Crop | None,
                               expected_capture_id: str | None = None, correction: dict | None = None) -> tuple[ProcessedImage, dict]:
        selected = await asyncio.to_thread(crop_image, canonical, crop) if crop else canonical
        capture = {'capture_id': capture_id, 'player_slot': slot, 'source': source,
                   'image_hash': selected.image_hash, 'image_ref': selected.image_ref,
                   'canonical_media_id': canonical.image_hash, 'width': canonical.width, 'height': canonical.height,
                   'crop': crop.model_dump() if crop else None}
        if correction:
            capture.update(correction=correction, parent_output_id=correction['parent_output_id'])
        elif expected_capture_id:
            previous = await asyncio.to_thread(self.repository.get_capture, battle_id, expected_capture_id)
            capture.update(parent_capture_id=expected_capture_id,
                           parent_output_id=(previous.get('observation') or {}).get('output_id'),
                           correction_count=previous.get('correction_count', 0))
        capture = await asyncio.to_thread(self.repository.begin_capture, battle_id, capture, expected_capture_id)
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
                pipeline = await asyncio.to_thread(self.repository.get_pipeline, battle['pipeline_version_id'])
                async def on_progress(progress):
                    try:
                        await asyncio.to_thread(self.repository.update_capture_progress, battle_id, capture_id, progress)
                    except Exception as exc:
                        # Optional stage reporting must not repeat or discard a paid result.
                        logger.warning('capture_progress_unavailable category=%s', type(exc).__name__)
                kwargs = dict(battle_id=battle_id, player_slot=slot, capture_id=capture_id,
                    image_hash=selected.image_hash, image_ref=selected.image_ref,
                    width=canonical.width, height=canonical.height, source=source, crop=crop,
                    pipeline_config=pipeline['config'], pipeline_version_id=battle['pipeline_version_id'],
                    correction_context=capture.get('correction'), reference_provider=self.reference_provider,
                    on_progress=on_progress)
                # Keep the existing injected engineering fixtures compatible with the richer live API.
                signature = inspect.signature(self.recognizer.recognize_capture)
                if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
                    kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
                result = await self.recognizer.recognize_capture(canonical.data, **kwargs)
                await on_progress({'stage': 'saving'})
                observation = Observation.model_validate(result).model_dump()
                observation['output_id'] = observation.get('output_id') or uuid4().hex
                observation['pipeline_version_id'] = battle['pipeline_version_id']
                observation['parent_output_id'] = capture.get('parent_output_id')
                fighter = observation.get('pending_fighter')
                if fighter:
                    original = (capture.get('correction') or {}).get('original_fighter')
                    if original and capture['correction']['request']['kind'] == 'style':
                        # Style is never a route to reroll combat power or factual identity.
                        for key in ('archetype', 'stats', 'canonical_type_id', 'object_type', 'observed_object'):
                            fighter[key] = deepcopy(original.get(key))
                        fighter['visual_spec']['template_id'] = original['visual_spec']['template_id']
                        observation['observed_object'] = deepcopy(capture['correction'].get('original_observed_object'))
                        observation['visible_features'] = deepcopy(capture['correction'].get('original_visible_features', []))
                        observation['uncertainty'] = deepcopy(capture['correction'].get('original_uncertainty', []))
                        observation['proposed_label'] = original['object_type']
                        observation['canonical_type_candidate'] = original['canonical_type_id']
                    observation['observed_object'] = observation.get('observed_object') or {
                        'canonical_type_id': fighter['canonical_type_id'], 'label': observation.get('proposed_label') or fighter['object_type'],
                        'visible_features': observation.get('visible_features', [])}
                    fighter.update(output_id=observation['output_id'], pipeline_version_id=battle['pipeline_version_id'],
                                   parent_output_id=observation['parent_output_id'], observed_object=observation['observed_object'])
                    observation['saved_resident_preview'] = await asyncio.to_thread(
                        self.repository.saved_resident_preview, fighter['canonical_type_id'])
                self._validate_identity(observation, capture, battle_id)
                if fighter:
                    # Ignore anything the model emits as a price. Only our optional
                    # server-side market connector can attach a sourced snapshot.
                    original = (capture.get('correction') or {}).get('original_fighter')
                    if original and capture['correction']['request']['kind'] == 'style':
                        fighter['market_price'] = deepcopy(original.get('market_price'))
                    else:
                        fighter['market_price'] = await self.market_prices.quote(fighter)
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
