"""Isolated, authoritative fixture battles. No recognition or island unlocks."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import secrets
from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from .repository import Repository, StoreError, key_for, public


class ArenaBattleRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_:-]+$')
    fighter_ids: tuple[Annotated[str, Field(min_length=1, max_length=80)], Annotated[str, Field(min_length=1, max_length=80)]]


class ArenaStore:
    def __init__(self, repository: Repository):
        self.repo = repository

    def ensure_indexes(self):
        if hasattr(self.repo, 'db'):
            self.repo.db.arenaBattles.create_index([('world_id', 1), ('request_id', 1)], unique=True)
            self.repo.db.arenaBattles.create_index([('world_id', 1), ('created_at', -1)])

    def _check_request(self, record: dict, fighter_ids: list[str]) -> dict:
        if record['fighter_ids'] != list(fighter_ids):
            raise StoreError('This request already belongs to a different matchup. Start a new battle.', 409, 'arena_request_conflict')
        return public(record)

    def get(self, battle_id: str) -> dict:
        record = self.repo.read(lambda tx: tx.get('arenaBattles', battle_id))
        if not record or record.get('world_id') != self.repo.world_id:
            raise StoreError('Practice battle not found in this world.', 404, 'not_found')
        return public(record)

    def recent(self, limit: int = 10) -> dict:
        records = self.repo.read(lambda tx: tx.find('arenaBattles', {'world_id': self.repo.world_id}, sort='created_at', limit=limit))
        fields = ('id', 'created_at', 'fighter_ids', 'winner_slot', 'outcome', 'engine_version', 'persistence')
        return {'battles': [{**{key: record[key] for key in fields}, 'fighter_names': [f['name'] for f in record['fighters']]} for record in records]}

    def create(self, request_id: str, fighter_ids: list[str]) -> dict:
        battle_id = key_for(self.repo.world_id, 'arena', request_id)[:32]
        existing = self.repo.read(lambda tx: tx.get('arenaBattles', battle_id))
        if existing:
            return self._check_request(existing, fighter_ids)
        from .combat_fixtures import fixture_profile, get_catalog
        from .combat_v2 import simulate_v2
        try:
            profiles = [fixture_profile(fixture_id) for fixture_id in fighter_ids]
        except (KeyError, ValueError):
            raise StoreError('Choose two objects from the practice catalogue.', 422, 'unknown_fixture') from None
        catalog = get_catalog()
        # Randomness, arithmetic and time are allocated once outside retryable DB callbacks.
        seed = secrets.randbelow(2**31)
        result = simulate_v2(profiles, seed)
        snapshot = {key: deepcopy(catalog[key]) for key in ('engine_version', 'profile_version', 'rules', 'price_policy', 'disclaimer')}
        digest = sha256(json.dumps({'profiles': profiles, 'rules': snapshot}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        record = {**result, '_id': battle_id, 'id': battle_id, 'request_id': request_id,
                  'world_id': self.repo.world_id, 'fighter_ids': list(fighter_ids), 'created_at': self.repo.clock(),
                  'persistence': self.repo.persistence, 'source': 'local_fixture', 'island_rewards': False,
                  'immutable': True, 'catalog_snapshot': snapshot, 'snapshot_sha256': digest}

        def save(tx):
            saved = tx.get('arenaBattles', battle_id)
            if saved:
                self._check_request(saved, fighter_ids)
                return saved
            tx.put('arenaBattles', record)
            return record
        return public(self.repo.transaction(save))


def register_arena_routes(app: FastAPI):
    def store() -> ArenaStore:
        value = getattr(app.state, 'arena', None)
        if value is None:
            raise StoreError('Practice battle storage is unavailable. Start the local backend with Atlas connected.', 503, 'arena_unavailable')
        return value

    @app.get('/api/arena/catalog')
    async def catalogue():
        from .combat_fixtures import get_catalog
        result = get_catalog()
        repo = getattr(app.state, 'repository', None)
        return {**result, 'persistence': repo.persistence if repo else 'unavailable',
                'storage_available': getattr(app.state, 'arena', None) is not None}

    @app.post('/api/arena/battles')
    async def create(body: ArenaBattleRequest):
        return await asyncio.to_thread(store().create, body.request_id, list(body.fighter_ids))

    @app.get('/api/arena/battles')
    async def recent(limit: int = Query(default=10, ge=1, le=25)):
        return await asyncio.to_thread(store().recent, limit)

    @app.get('/api/arena/battles/{battle_id}')
    async def saved(battle_id: str):
        return await asyncio.to_thread(store().get, battle_id)
