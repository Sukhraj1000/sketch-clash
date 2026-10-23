"""Local operator gate and narrowly scoped quality endpoints."""
from __future__ import annotations
import asyncio
import base64
from hashlib import sha256
import hmac
import os
from pathlib import Path
import secrets
import time
from typing import Literal
from fastapi import Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from .config import PROJECT_ROOT
from .repository import StoreError
from .quality import TERMINAL

class OperatorGate:
    def __init__(self, token=None, path=None):
        path = Path(path or PROJECT_ROOT / 'backend/data/operator-token')
        self.token = token or os.getenv('SKETCH_OPERATOR_TOKEN', '')
        if not self.token:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as f: f.write(secrets.token_urlsafe(32))
            except FileExistsError: pass
            if path.is_symlink(): raise ValueError('Operator token file cannot be a symlink.')
            os.chmod(path, 0o600)
            self.token = path.read_text().strip()
        if len(self.token) < 24: raise ValueError('Operator token must contain at least 24 characters.')
        self.attempts = {}

    def login(self, supplied, address):
        now = time.time()
        recent = [t for t in self.attempts.get(address, []) if now-t < 60]
        if len(recent) >= 5: raise StoreError('Wait a minute before trying the operator key again.', 429, 'operator_rate_limit')
        if not hmac.compare_digest(supplied, self.token):
            self.attempts[address] = recent + [now]
            raise StoreError('Operator key was not accepted.', 401, 'operator_required')
        self.attempts.pop(address, None)
        payload = f'{int(now)+8*3600}:{secrets.token_urlsafe(16)}'
        signature = hmac.new(self.token.encode(), payload.encode(), sha256).hexdigest()
        return base64.urlsafe_b64encode(f'{payload}:{signature}'.encode()).decode()

    def check(self, cookie):
        try:
            expiry, nonce, signature = base64.urlsafe_b64decode(cookie or '').decode().split(':')
            expected = hmac.new(self.token.encode(), f'{expiry}:{nonce}'.encode(), sha256).hexdigest()
            return int(expiry) > time.time() and hmac.compare_digest(signature, expected)
        except (ValueError, TypeError, UnicodeError): return False

class Body(BaseModel): model_config = ConfigDict(extra='forbid')
class SessionBody(Body): token: str = Field(min_length=1, max_length=256)
class CreativeRubric(Body):
    resemblance: int | None = Field(default=None, ge=1, le=5)
    feature_preservation: int | None = Field(default=None, ge=1, le=5)
    style_fit: int | None = Field(default=None, ge=1, le=5)
    appeal: int | None = Field(default=None, ge=1, le=5)
    context: str = Field(default='', max_length=600)
class ReviewBody(Body):
    feedback_id: str = Field(min_length=1, max_length=100)
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=600)
    decision: Literal['approved', 'disputed', 'insufficient']
    expected_identity: str | None = Field(default=None, max_length=80)
    clarification_required: bool = False
    group_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_:-]+$')
    role: Literal['reference', 'development', 'reserved']
    shared_consent: bool = False
    visible_attributes: list[str] = Field(default_factory=list, max_length=12)
    creative: CreativeRubric = Field(default_factory=CreativeRubric)
    expected_revision: int = Field(default=0, ge=0)
class JobBody(Body):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_:-]+$')
    kind: Literal['baseline', 'candidate']
    scope: Literal['recognition', 'appearance'] = 'recognition'
    max_requests: int = Field(default=24, ge=1, le=60)
    case_ids: list[str] | None = Field(default=None, max_length=12)
class ReferenceBody(Body):
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_:-]+$')
    case_ids: list[str] = Field(min_length=1, max_length=12)
class RenderBody(Body):
    status: Literal['passed', 'failed', 'unavailable']
    bounds_ok: bool = False
    visible: bool = False
    states: list[Literal['idle', 'rest', 'wander']] = Field(default_factory=list, max_length=3)
    errors: list[str] = Field(default_factory=list, max_length=10)
    view_version: Literal['quality-v1'] = 'quality-v1'
class ComparisonBody(Body):
    reviewer: str = Field(min_length=1, max_length=80)
    preference: Literal['left', 'right', 'tie', 'neither']
    reason: str = Field(min_length=1, max_length=600)
class ActivationBody(Body):
    version_id: str = Field(min_length=1, max_length=100)
    expected_active_version_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=600)

def register_quality_routes(app):
    async def operator(request: Request):
        if not app.state.operator_gate.check(request.cookies.get('sketch_operator')):
            raise StoreError('Unlock Recognition & World Quality with the local operator key.', 401, 'operator_required')
        if not getattr(app.state, 'quality', None):
            raise StoreError('Quality services are unavailable; live gameplay remains separate.', 503, 'quality_unavailable')
        return app.state.quality

    @app.post('/api/quality/session')
    async def login(body: SessionBody, request: Request, response: Response):
        cookie = app.state.operator_gate.login(body.token, request.client.host if request.client else 'local')
        response.set_cookie('sketch_operator', cookie, httponly=True, samesite='strict', max_age=8*3600, path='/api/quality')
        return {'authenticated': True, 'expires_in': 8*3600}

    @app.delete('/api/quality/session')
    async def logout(response: Response):
        response.delete_cookie('sketch_operator', path='/api/quality')
        return {'authenticated': False}

    @app.get('/api/quality/overview')
    async def overview(store=Depends(operator)):
        result = await asyncio.to_thread(store.overview)
        adapter = getattr(app.state, 'references', None)
        if adapter: result['reference_retrieval']['adapter'] = adapter.status
        return result

    @app.post('/api/quality/reviews')
    async def review(body: ReviewBody, store=Depends(operator)):
        data = body.model_dump(exclude_none=True)
        if any(len(x) > 160 for x in data['visible_attributes']):
            raise StoreError('Keep reviewed visible attributes concise.', 422, 'invalid_attributes')
        return await asyncio.to_thread(store.review, data)

    @app.post('/api/quality/jobs')
    async def create_job(body: JobBody, store=Depends(operator)):
        result = await asyncio.to_thread(store.create_job, body.model_dump())
        app.state.quality_worker.wake.set()
        return result

    @app.post('/api/quality/references/index')
    async def reference_index(store=Depends(operator)):
        adapter = getattr(app.state, 'references', None)
        if adapter is None: raise StoreError('Visual reference service unavailable.', 503, 'reference_unavailable')
        return await adapter.ensure_index()

    @app.post('/api/quality/references/prepare')
    async def prepare_references(body: ReferenceBody, store=Depends(operator)):
        result = await asyncio.to_thread(store.create_reference_job, body.model_dump())
        app.state.quality_worker.wake.set()
        return result

    @app.get('/api/quality/jobs/{identifier}')
    async def job(identifier: str, store=Depends(operator)):
        result = await asyncio.to_thread(store.job, identifier)
        return {'job': store.public_job(result), 'results': await asyncio.to_thread(store.results, identifier),
                'gate': await asyncio.to_thread(store.gates, identifier)}

    @app.post('/api/quality/jobs/{identifier}/cancel')
    async def cancel(identifier: str, store=Depends(operator)):
        def change(job):
            if job['status'] in TERMINAL: return
            job['cancel_requested'] = True
            if job['status'] == 'queued': job['status'] = 'cancelled'
        result = await asyncio.to_thread(store.mutate_job, identifier, change)
        return store.public_job(result)

    @app.post('/api/quality/results/{identifier}/render')
    async def render(identifier: str, body: RenderBody, store=Depends(operator)):
        return await asyncio.to_thread(store.render, identifier, body.model_dump())

    @app.get('/api/quality/jobs/{identifier}/comparison')
    async def comparison(identifier: str, store=Depends(operator)):
        return await asyncio.to_thread(store.comparison, identifier)

    @app.post('/api/quality/comparisons/{identifier}')
    async def comparison_review(identifier: str, body: ComparisonBody, store=Depends(operator)):
        return await asyncio.to_thread(store.compare_review, identifier, body.model_dump())

    @app.post('/api/quality/activate')
    async def activate(body: ActivationBody, store=Depends(operator)):
        return await asyncio.to_thread(store.activate, body.model_dump())

    @app.post('/api/quality/rollback')
    async def rollback(body: ActivationBody, store=Depends(operator)):
        return await asyncio.to_thread(store.activate, body.model_dump(), True)

    @app.get('/api/quality/export')
    async def export(job_id: str | None = None, store=Depends(operator)):
        return await asyncio.to_thread(store.export, job_id)
