"""Local boundary for the two persistent colonies and their independent actor turns."""
from __future__ import annotations
import asyncio
from typing import Literal
from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from .repository import StoreError

class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Command(Body):
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_:-]+$')
    colony_id: Literal['winners', 'losers']
    kind: Literal['pause', 'resume', 'priority', 'assign', 'value', 'council']
    mode: Literal['crew', 'manual'] | None = None
    project_id: str | None = Field(default=None, max_length=60)
    character_id: str | None = Field(default=None, max_length=100)
    assignment: str | None = Field(default=None, max_length=30)
    expected_revision: int | None = Field(default=None, ge=0)
    estimated_value_gbp: float | None = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)

class Turn(Body):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_:-]+$')
    colony_id: Literal['winners', 'losers']
    agent_id: str | None = Field(default=None, max_length=100)

class Switch(Body):
    enabled: bool


def register_colony_routes(app):
    def colonies():
        store = getattr(app.state, 'colonies', None)
        if store is None: raise StoreError('The two-island engine is unavailable. Existing saves remain intact.', 503, 'colonies_unavailable')
        return store

    def planner():
        worker = getattr(app.state, 'colony_planner', None)
        if worker is None: raise StoreError('Agent decisions are unavailable. Local work continues.', 503, 'planner_unavailable')
        return worker

    async def snapshot(store):
        result = await asyncio.to_thread(store.snapshot)
        worker = getattr(app.state, 'colony_planner', None)
        result['planner'] = await asyncio.to_thread(worker.status) if worker else {'enabled': False, 'configured': False, 'last_status': 'unavailable'}
        result['runtime'] = {'mode': 'local_backend', 'worker_active': bool(getattr(app.state, 'colony_runtime', None)),
                             'description': 'Local workers run the agents; MongoDB stores state, boards and receipts.'}
        return result

    @app.get('/api/colonies')
    async def get_colonies(store=Depends(colonies)):
        return await snapshot(store)

    @app.post('/api/colonies/start')
    async def start_colonies(store=Depends(colonies)):
        await asyncio.to_thread(store.initialize)
        # Switch the old persona-only planner off when the new cooperative mode starts.
        # Its existing budget remains shared; original colony data is preserved.
        legacy = getattr(app.state, 'island_planner', None)
        if legacy: await asyncio.to_thread(legacy.toggle, False)
        worker = getattr(app.state, 'colony_planner', None)
        if worker:
            await asyncio.to_thread(worker.ensure_state)
            worker.wake.set()
        return await snapshot(store)

    @app.post('/api/colonies/command')
    async def command(body: Command, store=Depends(colonies)):
        await asyncio.to_thread(store.command, body.model_dump(exclude_none=True))
        return await snapshot(store)

    @app.post('/api/colonies/think', status_code=202)
    async def think(body: Turn, store=Depends(colonies), worker=Depends(planner)):
        run = await asyncio.to_thread(worker.request, body.idempotency_key, body.colony_id, body.agent_id)
        return {'run': run, 'planner': await asyncio.to_thread(worker.status)}

    @app.post('/api/colonies/planner')
    async def planner_switch(body: Switch, store=Depends(colonies), worker=Depends(planner)):
        await asyncio.to_thread(worker.toggle, body.enabled)
        return await snapshot(store)
