"""Local gameplay routes and inexpensive persistent island ticking."""
from __future__ import annotations
import asyncio
import logging
from typing import Literal
from fastapi import Depends
from pydantic import BaseModel,ConfigDict,Field
from .repository import StoreError

log=logging.getLogger('sketch_clash.island')
class Body(BaseModel):model_config=ConfigDict(extra='forbid')
class IslandCommand(Body):
    idempotency_key:str=Field(min_length=8,max_length=100,pattern=r'^[A-Za-z0-9_:-]+$')
    kind:Literal['pause','resume','priority','assign']
    project_id:str|None=Field(default=None,max_length=60)
    character_id:str|None=Field(default=None,max_length=100)
    assignment:str|None=Field(default=None,max_length=30)
    expected_revision:int|None=Field(default=None,ge=0)
class Reflection(Body):
    idempotency_key:str=Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_:-]+$')
class PlannerSwitch(Body):enabled:bool

class IslandRuntime:
    def __init__(self,island):self.island=island;self.task=None;self.stopping=False
    async def start(self):self.task=asyncio.create_task(self.loop())
    async def close(self):
        self.stopping=True
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
    async def loop(self):
        while not self.stopping:
            try:await asyncio.to_thread(self.island.advance)
            except asyncio.CancelledError:raise
            except Exception as exc:log.warning('island_tick_failed category=%s',type(exc).__name__)
            await asyncio.sleep(5)

def register_island_routes(app):
    def island():
        store=getattr(app.state,'island',None)
        if store is None:raise StoreError('The island simulation is unavailable. Your saved collection is unchanged.',503,'island_unavailable')
        return store
    async def snapshot(store):
        result=await asyncio.to_thread(store.snapshot)
        planner=getattr(app.state,'island_planner',None)
        result['planner']=await asyncio.to_thread(planner.status) if planner else {'enabled':False,'last_status':'unavailable'}
        result['runtime']={'mode':'local_backend','worker_active':bool(getattr(app.state,'island_runtime',None)),
                           'description':'The local backend runs the simulation; MongoDB stores its state.'}
        return result
    @app.get('/api/island')
    async def get_island(store=Depends(island)):return await snapshot(store)
    @app.post('/api/island/start')
    async def start_island(store=Depends(island)):
        await asyncio.to_thread(store.initialize)
        planner=getattr(app.state,'island_planner',None)
        if planner:
            await asyncio.to_thread(planner.ensure_state);planner.wake.set()
        return await snapshot(store)
    @app.post('/api/island/command')
    async def command(body:IslandCommand,store=Depends(island)):
        await asyncio.to_thread(store.command,body.model_dump(exclude_none=True))
        planner=getattr(app.state,'island_planner',None)
        if planner:planner.wake.set()
        return await snapshot(store)
    @app.post('/api/island/personas',status_code=202)
    async def personas(body:Reflection,store=Depends(island)):
        planner=getattr(app.state,'island_planner',None)
        if planner is None:raise StoreError('AI reflection is unavailable. Local agents still work.',503,'planner_unavailable')
        run=await asyncio.to_thread(planner.request,body.idempotency_key)
        return {'run':run,'planner':await asyncio.to_thread(planner.status)}
    @app.post('/api/island/planner')
    async def planner_switch(body:PlannerSwitch,store=Depends(island)):
        planner=getattr(app.state,'island_planner',None)
        if planner is None:raise StoreError('AI reflection is unavailable.',503,'planner_unavailable')
        await asyncio.to_thread(planner.toggle,body.enabled)
        return await snapshot(store)
