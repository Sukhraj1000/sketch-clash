"""World-scoped storage and transactional lifecycle invariants.

MongoDB is the default. MemoryRepository is an explicitly labelled, process-local
contract-test/development adapter; it is never an automatic persistence fallback.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from math import cos, sin, tau
from threading import RLock
from typing import Any, Callable
import secrets
import json

from .config import Settings
from .engine import simulate_match
from .contracts import FeedbackSubmission
from .pipeline import (BASELINE_VERSION, LEGACY_VERSION, BASELINE_CONFIG, BASE_PROMPT_HASH,
                       BASE_SYSTEM_INSTRUCTION, active_key, version_key)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def key_for(*parts: str) -> str:
    # Unambiguous framing preserves world scoping even when user request IDs contain ':'.
    return sha256(json.dumps(parts, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

from .provider_errors import LocalProviderControlError


class StoreError(LocalProviderControlError):
    def __init__(self, message: str, status: int = 409, code: str = 'invalid_transition'):
        super().__init__(message)
        self.status, self.code = status, code

class MemoryTransaction:
    def __init__(self, data: dict[str, dict]):
        self.data = data
    def get(self, collection: str, key: str) -> dict | None:
        value = self.data.setdefault(collection, {}).get(key)
        return deepcopy(value) if value is not None else None
    def put(self, collection: str, value: dict) -> None:
        self.data.setdefault(collection, {})[value['_id']] = deepcopy(value)
    def find(self, collection: str, query: dict, sort: str | None = None, limit: int = 501) -> list[dict]:
        values = [deepcopy(v) for v in self.data.setdefault(collection, {}).values() if all(v.get(k) == x for k, x in query.items())]
        if sort:
            values.sort(key=lambda v: v[sort], reverse=True)
        return values[:limit]

class MongoTransaction:
    def __init__(self, database, session=None):
        self.database, self.session = database, session
    def get(self, collection: str, key: str) -> dict | None:
        return self.database[collection].find_one({'_id': key}, session=self.session)
    def put(self, collection: str, value: dict) -> None:
        self.database[collection].replace_one({'_id': value['_id']}, value, upsert=True, session=self.session)
    def find(self, collection: str, query: dict, sort: str | None = None, limit: int = 501) -> list[dict]:
        cursor = self.database[collection].find(query, session=self.session)
        if sort:
            cursor = cursor.sort(sort, -1)
        return list(cursor.limit(limit))

class Repository:
    persistence = 'mongodb'
    def __init__(self, settings: Settings, clock: Callable[[], str] = now_iso):
        self.settings, self.clock = settings, clock
        self.world_id = settings.world_id

    def transaction(self, operation: Callable) -> Any:
        raise NotImplementedError

    def read(self, operation: Callable) -> Any:
        raise NotImplementedError

    def _battle(self, tx, battle_id: str) -> dict:
        battle = tx.get('battles', battle_id)
        if not battle or battle['world_id'] != self.world_id:
            raise StoreError('Battle not found in this world.', 404, 'not_found')
        battle.setdefault('confirmed_capture_ids', [None, None])
        # Historical accepted fighters remain unchanged; only their provenance is unknown.
        battle.setdefault('pipeline_version_id', LEGACY_VERSION)
        return battle

    def initialize_pipeline(self) -> None:
        def operation(tx):
            baseline_key = version_key(self.world_id, BASELINE_VERSION)
            if not tx.get('pipelineVersions', baseline_key):
                tx.put('pipelineVersions', {'_id': baseline_key, 'id': BASELINE_VERSION, 'world_id': self.world_id,
                    'config': deepcopy(BASELINE_CONFIG), 'parent_id': None, 'created_at': self.clock(),
                    'immutable': True, 'system_instruction': BASE_SYSTEM_INSTRUCTION,
                    'base_prompt_hash': BASE_PROMPT_HASH, 'provenance': 'Inspected existing recognition baseline'})
            pointer_key = active_key(self.world_id)
            if not tx.get('qualityState', pointer_key):
                tx.put('qualityState', {'_id': pointer_key, 'id': 'active-pipeline', 'world_id': self.world_id,
                    'active_version_id': BASELINE_VERSION, 'revision': 1, 'updated_at': self.clock()})
        self.transaction(operation)

    def get_pipeline(self, version_id: str) -> dict:
        # Legacy rounds can finish with the inspected baseline, without relabelling old outputs.
        actual = BASELINE_VERSION if version_id == LEGACY_VERSION else version_id
        version = self.read(lambda tx: tx.get('pipelineVersions', version_key(self.world_id, actual)))
        if not version:
            raise StoreError('The round’s pinned pipeline is unavailable.', 503, 'pipeline_unavailable')
        return public(version)

    def create_battle(self, request_id: str) -> dict:
        battle_id = key_for(self.world_id, request_id)[:32]
        def operation(tx):
            existing = tx.get('battles', battle_id)
            if existing:
                return existing
            timestamp = self.clock()
            pointer = tx.get('qualityState', active_key(self.world_id))
            if not pointer or not tx.get('pipelineVersions', version_key(self.world_id, pointer['active_version_id'])):
                raise StoreError('The active recognition pipeline is unavailable.', 503, 'pipeline_unavailable')
            battle = {'_id': battle_id, 'id': battle_id, 'request_id': request_id, 'world_id': self.world_id,
                      'pipeline_version_id': pointer['active_version_id'],
                      'status': 'draft', 'created_at': timestamp, 'updated_at': timestamp,
                      'active_capture_ids': [None, None], 'confirmed_capture_ids': [None, None], 'pending_fighters': [None, None],
                      'fighters': [], 'events': [], 'seed': None, 'engine_version': None,
                      'winner_slot': None, 'final_health': None, 'playback_mode': None,
                      'duration_ms': None, 'started_at': None, 'eligible_at': None,
                      'completed_at': None, 'completion': None, 'persistence': self.persistence,
                      'capture_count': 0}
            tx.put('battles', battle)
            return battle
        return public_battle(self.transaction(operation))

    def get_battle(self, battle_id: str) -> dict:
        return public_battle(self.read(lambda tx: self._battle(tx, battle_id)))

    def save_media(self, image) -> None:
        def operation(tx):
            if not tx.get('media', image.image_hash):
                tx.put('media', {'_id': image.image_hash, 'data': image.data, 'mime_type': image.mime_type,
                                 'width': image.width, 'height': image.height, 'created_at': self.clock()})
        self.transaction(operation)

    def get_media(self, media_id: str) -> dict:
        value = self.read(lambda tx: tx.get('media', media_id))
        if not value:
            raise StoreError('Image not found.', 404, 'not_found')
        return value

    def begin_capture(self, battle_id: str, capture: dict, expected_capture_id: str | None = None) -> dict:
        capture_key = key_for(battle_id, capture['capture_id'])
        def operation(tx):
            battle = self._battle(tx, battle_id)
            existing = tx.get('captures', capture_key)
            if existing:
                immutable_fields = ('image_hash', 'source', 'player_slot', 'crop', 'canonical_media_id', 'width', 'height', 'parent_output_id', 'correction')
                if any(existing.get(k) != capture.get(k) for k in immutable_fields):
                    raise StoreError('This capture ID is already locked to a different image or selection.', 409, 'capture_mismatch')
                if (existing.get('status') == 'failed' and not existing.get('observation')
                        and battle['status'] in ('draft', 'ready')
                        and battle['active_capture_ids'][capture['player_slot']] == capture['capture_id']):
                    existing.update(status='processing', error=None)
                    tx.put('captures', existing)
                return existing
            if battle['status'] not in ('draft', 'ready'):
                raise StoreError('New captures are allowed only before the battle starts.')
            if expected_capture_id is not None and battle['active_capture_ids'][capture['player_slot']] != expected_capture_id:
                raise StoreError('The photograph was replaced before this selection arrived.', 409, 'stale_capture')
            if capture.get('correction'):
                previous = tx.get('captures', key_for(battle_id, expected_capture_id or ''))
                if not previous or previous.get('correction_count', 0) >= 2:
                    raise StoreError('Two corrections have already been tried. Select or retake the photo.', 409, 'correction_limit')
                if battle['confirmed_capture_ids'][capture['player_slot']] is not None:
                    raise StoreError('A confirmed fighter cannot be revised.', 409, 'fighter_locked')
                capture['correction_count'] = previous.get('correction_count', 0) + 1
            if battle['capture_count'] >= 20:
                raise StoreError('This battle has reached its retake limit. Start a new round.', 409, 'capture_limit')
            capture_doc = {'_id': capture_key, **capture, 'battle_id': battle_id, 'world_id': self.world_id,
                           'pipeline_version_id': battle['pipeline_version_id'],
                           'status': 'processing', 'created_at': self.clock(), 'observation': None,
                           'error': None}
            slot = capture['player_slot']
            battle['active_capture_ids'][slot] = capture['capture_id']
            battle['pending_fighters'][slot] = None
            battle['confirmed_capture_ids'][slot] = None
            battle['status'] = 'draft'
            battle['capture_count'] += 1
            battle['updated_at'] = self.clock()
            tx.put('captures', capture_doc)
            tx.put('battles', battle)
            return capture_doc
        return self.transaction(operation)

    def get_capture(self, battle_id: str, capture_id: str) -> dict:
        def operation(tx):
            self._battle(tx, battle_id)
            value = tx.get('captures', key_for(battle_id, capture_id))
            if not value:
                raise StoreError('Capture not found.', 404, 'not_found')
            return value
        return self.read(operation)

    def finish_capture(self, battle_id: str, capture_id: str, observation: dict) -> dict:
        def operation(tx):
            battle = self._battle(tx, battle_id)
            capture = tx.get('captures', key_for(battle_id, capture_id))
            if not capture:
                raise StoreError('Capture not found.', 404, 'not_found')
            slot = capture['player_slot']
            active = battle['status'] in ('draft', 'ready') and battle['active_capture_ids'][slot] == capture_id
            observation = deepcopy(observation_data)
            observation['stale'] = not active
            # Persist the first successful result, including ambiguity; duplicate calls recover it.
            if capture.get('observation'):
                existing = deepcopy(capture['observation'])
                existing['stale'] = not active
                return existing
            capture.update({'status': 'done', 'observation': observation, 'error': None})
            tx.put('captures', capture)
            if active:
                battle['pending_fighters'][slot] = observation.get('pending_fighter') if observation['status'] == 'recognized' else None
                battle['status'] = 'ready' if all(battle['pending_fighters']) and battle['confirmed_capture_ids'] == battle['active_capture_ids'] else 'draft'
                battle['updated_at'] = self.clock()
                tx.put('battles', battle)
            return observation
        observation_data = observation
        return self.transaction(operation)

    def fail_capture(self, battle_id: str, capture_id: str, code: str) -> None:
        def operation(tx):
            self._battle(tx, battle_id)
            capture = tx.get('captures', key_for(battle_id, capture_id))
            if capture and not capture.get('observation'):
                capture.update({'status': 'failed', 'error': code})
                tx.put('captures', capture)
        self.transaction(operation)

    def submit_feedback(self, battle_id: str, capture_id: str, body: dict) -> dict:
        data = FeedbackSubmission.model_validate(body).model_dump()
        feedback_id = key_for(self.world_id, battle_id, data['idempotency_key'])[:32]
        def operation(tx):
            battle = self._battle(tx, battle_id)
            previous = tx.get('qualityFeedback', feedback_id)
            if previous:
                if previous['capture_id'] != capture_id or previous['submission'] != data:
                    raise StoreError('This feedback request already refers to a different review.', 409, 'feedback_mismatch')
                return public(previous)
            capture = tx.get('captures', key_for(battle_id, capture_id))
            if not capture or not capture.get('observation'):
                raise StoreError('A prepared proposal is required for feedback.', 409, 'proposal_missing')
            observation = capture['observation']
            slot = capture['player_slot']
            if battle['status'] not in ('draft', 'ready') or battle['active_capture_ids'][slot] != capture_id:
                raise StoreError('Feedback must be recorded on the current proposal before battle.', 409, 'feedback_closed')
            if battle['confirmed_capture_ids'][slot] is not None:
                raise StoreError('Feedback must be recorded before this fighter is confirmed.', 409, 'fighter_locked')
            if observation.get('output_id') != data['output_id'] or observation.get('pipeline_version_id') != data['pipeline_version_id']:
                raise StoreError('The feedback does not match the exact proposal shown.', 409, 'proposal_mismatch')
            if data['recognition_verdict'] == 'corrected' and not (data['correction_label'] or data['selected_target']):
                raise StoreError('A correction needs an object label or selected target.', 422, 'correction_missing')
            value = {'_id': feedback_id, 'id': feedback_id, 'world_id': self.world_id, 'battle_id': battle_id,
                     'capture_id': capture_id, 'player_slot': slot, **data, 'submission': data,
                     'image_ref': observation['image_ref'], 'image_hash': observation['image_hash'],
                     'parent_output_id': observation.get('parent_output_id'), 'created_at': self.clock(),
                     'review_status': 'unreviewed', 'provenance': {'kind': 'player', 'session_id': battle_id},
                     'interaction_scope': 'corrected_retry' if observation.get('parent_output_id') else 'first_preview',
                     'shared_use': 'consented_pending_review' if data['shared_consent'] else 'private'}
            tx.put('qualityFeedback', value)
            return public(value)
        return self.transaction(operation)

    def saved_resident_preview(self, canonical_type_id: str) -> dict | None:
        resident = self.read(lambda tx: tx.get('worldCharacters', key_for(self.world_id, canonical_type_id)[:32]))
        if not resident:
            return None
        # The public island's already saved resident only, never another player's pending capture.
        return {key: deepcopy(resident.get(key)) for key in
                ('id', 'canonical_type_id', 'object_type', 'display_name', 'image_ref', 'visual_spec', 'archetype')}

    def confirm_capture(self, battle_id: str, slot: int, capture_id: str) -> dict:
        def operation(tx):
            battle = self._battle(tx, battle_id)
            if slot not in (0, 1):
                raise StoreError('Invalid player slot.', 422, 'invalid_request')
            if battle['active_capture_ids'][slot] != capture_id:
                raise StoreError('This photograph was replaced. Confirm the current fighter.', 409, 'stale_capture')
            fighter = battle['pending_fighters'][slot]
            if not fighter or fighter['capture_id'] != capture_id:
                raise StoreError('This capture does not have a valid checked fighter.', 409, 'fighter_not_ready')
            if battle['confirmed_capture_ids'][slot] == capture_id and battle['status'] in ('draft', 'ready', 'running', 'completed'):
                return battle
            if battle['status'] not in ('draft', 'ready'):
                raise StoreError('Only a battle being prepared can accept fighter confirmations.')
            battle['confirmed_capture_ids'][slot] = capture_id
            battle['status'] = 'ready' if all(battle['pending_fighters']) and battle['confirmed_capture_ids'] == battle['active_capture_ids'] else 'draft'
            battle['updated_at'] = self.clock()
            tx.put('battles', battle)
            return battle
        return public_battle(self.transaction(operation))

    def start_battle(self, battle_id: str, playback_mode: str) -> dict:
        # No LLM, media conversion or unbounded simulation is performed in this transaction.
        # A maximum of 11 integer steps is cheaper than an additional race-prone pre-read.
        chosen_seed = secrets.randbelow(2**31)
        def operation(tx):
            battle = self._battle(tx, battle_id)
            if battle['status'] in ('running', 'completed'):
                return battle
            if battle['status'] != 'ready' or not all(battle['pending_fighters']) or battle['confirmed_capture_ids'] != battle['active_capture_ids']:
                raise StoreError('Both players need a confirmed, checked object before starting.')
            fighters = deepcopy(battle['pending_fighters'])
            for slot, fighter in enumerate(fighters):
                if fighter['capture_id'] != battle['active_capture_ids'][slot]:
                    raise StoreError('A fighter was replaced. Confirm the current capture first.')
                media_id = fighter['image_ref'].rsplit('/', 1)[-1]
                if not tx.get('media', media_id):
                    raise StoreError('A fighter image has not been saved.', 409, 'media_missing')
            result = simulate_match(fighters, chosen_seed, playback_mode)
            started = datetime.fromisoformat(self.clock())
            from datetime import timedelta
            battle.update(result)
            battle.update({'status': 'running', 'fighters': fighters, 'started_at': started.isoformat(),
                           'eligible_at': (started + timedelta(milliseconds=result['duration_ms'])).isoformat(),
                           'updated_at': started.isoformat()})
            tx.put('battles', battle)
            return battle
        return public_battle(self.transaction(operation))

    def cancel_battle(self, battle_id: str) -> dict:
        def operation(tx):
            battle = self._battle(tx, battle_id)
            if battle['status'] == 'completed':
                raise StoreError('A completed battle cannot be cancelled.')
            if battle['status'] != 'cancelled':
                battle['status'], battle['updated_at'] = 'cancelled', self.clock()
                tx.put('battles', battle)
            return battle
        return public_battle(self.transaction(operation))

    def finalize_battle(self, battle_id: str) -> dict:
        def operation(tx):
            battle = self._battle(tx, battle_id)
            if battle['status'] == 'completed':
                return battle
            if battle['status'] != 'running':
                raise StoreError('Only a running battle can be completed.')
            if datetime.fromisoformat(self.clock()) < datetime.fromisoformat(battle['eligible_at']):
                raise StoreError('The accepted battle playback has not finished yet.', 409, 'playback_pending')
            timestamp = self.clock()
            resident_ids, new_ids = [], []
            # Sorting establishes the required lower-slot appearance for a same-type first unlock.
            unique = {}
            for fighter in sorted(battle['fighters'], key=lambda f: f['player_slot']):
                unique.setdefault(fighter['canonical_type_id'], fighter)
            for type_id, fighter in unique.items():
                resident_id = key_for(self.world_id, type_id)[:32]
                resident = tx.get('worldCharacters', resident_id)
                if not resident:
                    position_seed = int(key_for(self.world_id, type_id)[0:8], 16)
                    angle, radius = (position_seed % 360) * tau / 360, 1.0 + ((position_seed // 360) % 220) / 100
                    resident = {'_id': resident_id, 'id': resident_id, 'world_id': self.world_id,
                                'canonical_type_id': type_id, 'object_type': fighter['object_type'],
                                'display_name': fighter['display_name'], 'image_ref': fighter['image_ref'],
                                'visual_spec': deepcopy(fighter['visual_spec']), 'archetype': fighter['archetype'],
                                'first_battle_id': battle_id, 'unlocked_at': timestamp,
                                'home_position': {'x': round(cos(angle) * radius, 3), 'y': 0, 'z': round(sin(angle) * radius, 3)},
                                'state': {'activity': 'wander', 'mood': 'curious'}, 'distinct_battle_count': 0}
                    new_ids.append(resident_id)
                encounter_id = key_for(self.world_id, resident_id, battle_id)
                if not tx.get('encounters', encounter_id):
                    slots = [{'player_slot': f['player_slot'], 'won': f['player_slot'] == battle['winner_slot'],
                              'image_ref': f['image_ref'], 'display_name': f['display_name']}
                             for f in battle['fighters'] if f['canonical_type_id'] == type_id]
                    tx.put('encounters', {'_id': encounter_id, 'world_id': self.world_id,
                                         'character_id': resident_id, 'battle_id': battle_id,
                                         'completed_at': timestamp, 'winner_slot': battle['winner_slot'], 'slots': slots})
                    resident['distinct_battle_count'] += 1
                    resident['last_battle_at'] = timestamp
                    tx.put('worldCharacters', resident)
                resident_ids.append(resident_id)
            battle.update({'status': 'completed', 'completed_at': timestamp, 'updated_at': timestamp,
                           'completion': {'resident_ids': resident_ids, 'new_resident_ids': new_ids,
                                          'effects_applied': True, 'durable': self.persistence == 'mongodb'}})
            # Route the exact accepted fighters atomically without changing legacy residents.
            from .colonies import route_completed_battle
            route_completed_battle(tx, battle, self.world_id)
            tx.put('battles', battle)
            return battle
        return public_battle(self.transaction(operation))

    def world(self) -> dict:
        # Read-only: deliberately no upserts, recognition, embeddings or character creation.
        def operation(tx):
            world = tx.get('worlds', self.world_id)
            if not world:
                raise StoreError('The configured world has not been initialized.', 503, 'world_unavailable')
            characters = tx.find('worldCharacters', {'world_id': self.world_id})
            return {'world': public(world), 'characters': [public(c) for c in characters[:500]],
                    'has_more': len(characters) > 500, 'persistence': self.persistence}
        return self.read(operation)

    def history(self, character_id: str) -> dict:
        def operation(tx):
            character = tx.get('worldCharacters', character_id)
            if not character or character['world_id'] != self.world_id:
                raise StoreError('Character not found.', 404, 'not_found')
            encounters = tx.find('encounters', {'world_id': self.world_id, 'character_id': character_id}, sort='completed_at', limit=20)
            return {'character_id': character_id, 'encounters': [public(e) for e in encounters[:20]],
                    'distinct_battle_count': character['distinct_battle_count']}
        return self.read(operation)

    def update_character(self, character_id: str, activity: str) -> dict:
        if activity not in ('wander', 'rest'):
            raise StoreError('Activity must be wander or rest.', 422, 'invalid_state')
        def operation(tx):
            character = tx.get('worldCharacters', character_id)
            if not character or character['world_id'] != self.world_id:
                raise StoreError('Character not found.', 404, 'not_found')
            character['state']['activity'] = activity
            tx.put('worldCharacters', character)
            return public(character)
        return self.transaction(operation)

    def initialize_world(self) -> None:
        def operation(tx):
            if not tx.get('worlds', self.world_id):
                tx.put('worlds', {'_id': self.world_id, 'id': self.world_id, 'name': 'Sketch Island',
                                 'layout_seed': 4127, 'version': '1', 'created_at': self.clock()})
        self.transaction(operation)

    def close(self) -> None:
        pass

class MemoryRepository(Repository):
    persistence = 'development_memory'
    def __init__(self, settings: Settings, clock: Callable[[], str] = now_iso):
        super().__init__(settings, clock)
        self._data: dict[str, dict] = {}
        self._lock = RLock()
        self.initialize_world()
        self.initialize_pipeline()
    def transaction(self, operation: Callable) -> Any:
        with self._lock:
            staged = deepcopy(self._data)
            result = operation(MemoryTransaction(staged))
            self._data = staged
            return deepcopy(result)
    def read(self, operation: Callable) -> Any:
        with self._lock:
            return deepcopy(operation(MemoryTransaction(deepcopy(self._data))))

class MongoRepository(Repository):
    def __init__(self, settings: Settings, clock: Callable[[], str] = now_iso):
        super().__init__(settings, clock)
        from pymongo import MongoClient, ASCENDING
        from pymongo.errors import PyMongoError
        try:
            self.client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
                                      socketTimeoutMS=15000, timeoutMS=20000, retryWrites=True, appname='sketch-clash')
            self.db = self.client[settings.mongodb_database]
        except (PyMongoError, ValueError):
            raise StoreError('MongoDB configuration is invalid. Check the local URI and database name.', 503, 'mongodb_configuration') from None
        try:
            hello = self.client.admin.command('hello')
            if not hello.get('setName') and hello.get('msg') != 'isdbgrid':
                raise StoreError('MongoDB transactions require Atlas or a replica set.', 503, 'transactions_unavailable')
            self.db.battles.create_index([('world_id', ASCENDING), ('request_id', ASCENDING)], unique=True)
            self.db.worldCharacters.create_index([('world_id', ASCENDING), ('canonical_type_id', ASCENDING)], unique=True)
            self.db.characterTypes.create_index('canonical_key', unique=True)
            self.db.captures.create_index([('battle_id', ASCENDING), ('capture_id', ASCENDING)], unique=True)
            self.db.encounters.create_index([('world_id', ASCENDING), ('character_id', ASCENDING), ('battle_id', ASCENDING)], unique=True)
            self.db.encounters.create_index([('world_id', ASCENDING), ('character_id', ASCENDING), ('completed_at', -1)])
            self.db.pipelineVersions.create_index([('world_id', ASCENDING), ('id', ASCENDING)], unique=True)
            self.db.qualityFeedback.create_index([('world_id', ASCENDING), ('battle_id', ASCENDING), ('idempotency_key', ASCENDING)], unique=True)
            self.db.qualityFeedback.create_index([('world_id', ASCENDING), ('created_at', -1)])
            self.initialize_world()
            self.initialize_pipeline()
        except StoreError:
            self.client.close()
            raise
        except PyMongoError as exc:
            self.client.close()
            raise StoreError('MongoDB could not connect or create required indexes. Check the URI, Atlas network access and database permissions.', 503, 'mongodb_unavailable') from exc

    def transaction(self, operation: Callable) -> Any:
        from pymongo import timeout
        from pymongo.errors import PyMongoError, DuplicateKeyError
        from pymongo.read_concern import ReadConcern
        from pymongo.write_concern import WriteConcern
        # Callback may be repeated by the driver; all values that must be stable are allocated outside it.
        for attempt in range(3):
            try:
                with timeout(20), self.client.start_session() as session:
                    return session.with_transaction(lambda current: operation(MongoTransaction(self.db, current)),
                                                    read_concern=ReadConcern('snapshot'), write_concern=WriteConcern('majority'),
                                                    max_commit_time_ms=5000)
            except DuplicateKeyError:
                if attempt == 2:
                    raise StoreError('Concurrent save needs a retry. The battle ID remains recoverable.', 503, 'write_retry')
            except PyMongoError as exc:
                raise StoreError('The database save could not be confirmed. Retry using the same battle ID.', 503, 'write_unconfirmed') from exc
        raise AssertionError('unreachable')

    def read(self, operation: Callable) -> Any:
        from pymongo.errors import PyMongoError
        try:
            return operation(MongoTransaction(self.db))
        except PyMongoError as exc:
            raise StoreError('The database is temporarily unavailable. Retry shortly.', 503, 'mongodb_unavailable') from exc

    def close(self) -> None:
        self.client.close()


def public(value: dict) -> dict:
    return {k: deepcopy(v) for k, v in value.items() if not k.startswith('_')}

def public_battle(value: dict) -> dict:
    return {k: v for k, v in public(value).items() if k != 'capture_count'}

def create_repository(settings: Settings) -> Repository:
    if settings.repository == 'memory':
        return MemoryRepository(settings)
    if settings.repository != 'mongodb':
        raise StoreError('SKETCH_REPOSITORY must be mongodb or explicit development memory.', 503, 'configuration')
    if not settings.mongodb_uri:
        raise StoreError('MongoDB is not configured. Add MONGODB_URI to .env.local and restart the backend. Development-only memory mode is available explicitly.', 503, 'mongodb_not_configured')
    return MongoRepository(settings)
