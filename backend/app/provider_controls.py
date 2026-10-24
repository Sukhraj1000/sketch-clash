"""Durable request pace, bounded by the backend's existing safety ceilings."""
from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import Request
from pydantic import BaseModel, ConfigDict

from .repository import StoreError, key_for


class PaceSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['slow', 'steady', 'fast']


class ProviderControls:
    def __init__(self, repository, queue):
        self.repository, self.queue = repository, queue
        self.key = key_for(repository.world_id, 'gemini-request-pacing')
        self._lock = asyncio.Lock()
        self.record = None

    def load(self):
        def operation(tx):
            record = tx.get('providerControls', self.key)
            valid = record and record.get('world_id') == self.repository.world_id
            mode = record['mode'] if valid else self.queue.pacing_mode
            if self.queue.ledger:
                mode = self.queue.ledger.pacing_in_transaction(tx, mode, self.queue.clock(), only_if_unset=True)
            return record if valid else None, mode
        read = self.repository.transaction if self.queue.ledger else self.repository.read
        self.record, mode = read(operation)
        self.queue.set_pacing(mode)

    def status(self):
        return {**self.queue.pacing(), 'persistence': self.repository.persistence,
                'revision': (self.record or {}).get('revision', 0),
                'updated_at': (self.record or {}).get('updated_at')}

    def _save(self, mode):
        def operation(tx):
            prior = tx.get('providerControls', self.key) or {}
            record = {'_id': self.key, 'world_id': self.repository.world_id, 'mode': mode,
                      'revision': prior.get('revision', 0) + 1,
                      'updated_at': self.repository.clock()}
            tx.put('providerControls', record)
            if self.queue.ledger:
                self.queue.ledger.pacing_in_transaction(tx, mode, self.queue.clock())
            return record
        return self.repository.transaction(operation)

    async def update(self, mode):
        if mode not in ('slow', 'steady', 'fast'):
            raise StoreError('Choose a valid request pace.', 422, 'invalid_pace')
        async with self._lock:
            # A disconnected browser must not leave durable and active pace at
            # different values after an in-progress database commit succeeds.
            task = asyncio.create_task(asyncio.to_thread(self._save, mode))
            cancelled = False
            while True:
                try:
                    record = await asyncio.shield(task)
                    break
                except asyncio.CancelledError:
                    if task.cancelled():
                        raise
                    cancelled = True
            self.queue.set_pacing(record['mode'])
            self.record = record
            if cancelled:
                raise asyncio.CancelledError
            return self.status()


def register_provider_controls(app):
    def controls(request):
        value = getattr(request.app.state, 'provider_controls', None)
        if value is None:
            raise StoreError('Request pacing is unavailable until storage is connected.', 503, 'pacing_unavailable')
        return value

    @app.get('/api/observatory/pacing')
    async def get_pacing(request: Request):
        return controls(request).status()

    @app.post('/api/observatory/pacing')
    async def set_pacing(payload: PaceSelection, request: Request):
        return await controls(request).update(payload.mode)
