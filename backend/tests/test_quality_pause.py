"""A durable evaluation-only pause: no live providers or application saves."""
import asyncio
from copy import deepcopy
import time
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.quality import QualityStore
from app.quality_jobs import JobBudget, QualityWorker
from app.repository import MemoryRepository, StoreError
from test_quality import FakeRecognizer, create_job, seed_case


@pytest.fixture
def quality():
    settings = Settings(repository='memory', world_id='quality-pause-fixture')
    repo = MemoryRepository(settings)
    store = QualityStore(repo)
    seed_case(repo, 'development')
    seed_case(repo, 'reference', 'reference', seed=2)
    return repo, store, settings


def pause(store):
    return store.set_evaluation_pause(True, reviewer='fixture operator', reason='Investigate provider quota without evaluation batches.')


def test_pause_is_durable_idempotent_and_does_not_pause_or_modify_gameplay(quality):
    repo, store, _ = quality
    job = create_job(store)
    before_jobs = deepcopy(repo._data['qualityJobs'])
    before_world = deepcopy(repo.world())
    control = pause(store)
    assert control['evaluation_paused'] and control['revision'] == 1
    assert pause(store) == control
    restarted = QualityStore(repo)
    assert restarted.evaluation_control() == control
    overview = restarted.overview()
    assert overview['evaluation_paused'] is True
    assert overview['evaluation_control']['reason'] == control['reason']
    assert repo._data['qualityJobs'] == before_jobs and repo.world() == before_world
    assert restarted.job(job['id'])['status'] == 'queued'


@pytest.mark.parametrize('kind', ['baseline', 'candidate', 'references'])
def test_pause_blocks_new_batches_but_retains_existing_jobs(quality, kind):
    repo, store, _ = quality
    existing = create_job(store, key='existing')
    pause(store)
    before = deepcopy(repo._data)
    with pytest.raises(StoreError) as exc:
        if kind == 'references':
            store.create_reference_job({'idempotency_key': 'new-references', 'case_ids': ['reference']})
        else:
            create_job(store, key='new-' + kind, kind=kind)
    assert exc.value.code == 'evaluation_paused'
    assert repo._data == before
    assert create_job(store, key='existing')['id'] == existing['id']


@pytest.mark.asyncio
async def test_pause_blocks_budget_reservation_in_same_transaction_as_admission(quality, monkeypatch):
    _, store, _ = quality
    job = create_job(store)
    original = store.mutate_job
    def pause_between_precheck_and_reservation(identifier, callback, **kwargs):
        if kwargs.get('require_evaluation_enabled'):
            pause(store)
        return original(identifier, callback, **kwargs)
    monkeypatch.setattr(store, 'mutate_job', pause_between_precheck_and_reservation)
    with pytest.raises(StoreError) as exc:
        await JobBudget(store, job['id']).reserve(input_tokens=1, output_tokens=1, kind='fixture')
    assert exc.value.code == 'evaluation_paused'
    saved = store.job(job['id'])
    assert saved['budget']['requests'] == saved['budget']['reserved_tokens'] == 0
    assert saved['inflight'] is None


@pytest.mark.asyncio
async def test_already_returned_response_is_saved_but_pause_stops_next_request(quality):
    _, store, _ = quality
    job = create_job(store)
    budget = JobBudget(store, job['id'])
    reservation = await budget.reserve(input_tokens=5, output_tokens=5, kind='controlled-response')
    pause(store)
    await budget.complete(reservation, {'id': 'fixture-response', 'usage': {'total_tokens': 7}})
    saved = store.job(job['id'])
    assert saved['inflight'] is None and saved['budget']['reported_tokens'] == 7
    assert saved['provider_calls'][0]['interaction_id'] == 'fixture-response'
    with pytest.raises(StoreError) as exc:
        await budget.reserve(input_tokens=1, output_tokens=1, kind='must-not-dispatch')
    assert exc.value.code == 'evaluation_paused'
    assert store.job(job['id'])['budget']['requests'] == 1


@pytest.mark.asyncio
async def test_paused_worker_does_not_dispatch_or_cancel_queued_job(quality):
    _, store, settings = quality
    job = create_job(store)
    pause(store)
    FakeRecognizer.calls = []
    worker = QualityWorker(store, settings, recognizer_factory=FakeRecognizer)
    await worker.run(job['id'])
    saved = store.job(job['id'])
    assert saved['status'] == 'queued' and not saved['cancel_requested']
    assert saved['budget'] == job['budget'] and saved['checkpoints'] == job['checkpoints']
    assert FakeRecognizer.calls == []


@pytest.mark.asyncio
async def test_pause_between_cases_preserves_completed_checkpoint(quality):
    repo, store, settings = quality
    seed_case(repo, 'another-development', seed=3)
    job = create_job(store)
    class PauseAfterResponse(FakeRecognizer):
        calls = []
        async def recognize_capture(self, *args, **kwargs):
            result = await super().recognize_capture(*args, **kwargs)
            pause(store)
            return result
    worker = QualityWorker(store, settings, recognizer_factory=PauseAfterResponse)
    await worker.run(job['id'])
    saved = store.job(job['id'])
    assert saved['status'] == 'queued' and saved['progress']['completed'] == 1
    assert len(saved['checkpoints']) == len(store.results(job['id'])) == 1
    assert len(PauseAfterResponse.calls) == 1
    assert not saved['cancel_requested'] and saved['remaining_deadline_seconds'] > 0


@pytest.mark.asyncio
async def test_restart_keeps_pause_checkpoints_and_uncertain_requests(quality):
    _, store, settings = quality
    clean, unknown = create_job(store, key='clean'), create_job(store, key='unknown')
    store.mutate_job(clean['id'], lambda job: job.update(status='running', deadline_at=time.time()+100,
                                                         checkpoints=['saved-case'], progress={'completed': 1, 'total': 2}))
    await JobBudget(store, unknown['id']).reserve(input_tokens=1, output_tokens=1, kind='unknown')
    store.mutate_job(unknown['id'], lambda job: job.update(status='running'))
    pause(store)
    FakeRecognizer.calls = []
    worker = QualityWorker(QualityStore(store.repo), settings, recognizer_factory=FakeRecognizer)
    await worker.start()
    await worker.close()
    assert store.evaluation_control()['evaluation_paused']
    assert store.job(clean['id'])['status'] == 'queued'
    assert store.job(clean['id'])['checkpoints'] == ['saved-case']
    assert 0 < store.job(clean['id'])['remaining_deadline_seconds'] <= 100
    assert store.job(unknown['id'])['status'] == 'interrupted'
    assert store.job(unknown['id'])['inflight'] and store.job(unknown['id'])['budget']['requests'] == 1
    assert FakeRecognizer.calls == []


def test_operator_authentication_protects_durable_pause_control(quality):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from app.quality_api import OperatorGate, register_quality_routes
    _, store, _ = quality
    app = FastAPI()
    app.state.operator_gate = OperatorGate(token='fixture-quality-control-token-123')
    app.state.quality = store
    app.state.quality_worker = SimpleNamespace(wake=asyncio.Event())
    @app.exception_handler(StoreError)
    async def handle(request: Request, exc: StoreError):
        return JSONResponse({'detail': str(exc), 'code': exc.code}, status_code=exc.status)
    register_quality_routes(app)
    body = {'evaluation_paused': True, 'reviewer': 'fixture operator', 'reason': 'Stop evaluation batches.'}
    with TestClient(app) as client:
        assert client.post('/api/quality/control', json=body).status_code == 401
        client.post('/api/quality/session', json={'token': 'fixture-quality-control-token-123'})
        response = client.post('/api/quality/control', json=body)
        assert response.status_code == 200 and response.json()['evaluation_paused']
        assert client.get('/api/quality/overview').json()['evaluation_paused']
        assert client.post('/api/quality/jobs', json={'idempotency_key': 'blocked', 'kind': 'baseline'}).json()['code'] == 'evaluation_paused'
        assert client.post('/api/quality/control', json={**body, 'evaluation_paused': 'false'}).status_code == 422
    assert store.evaluation_control()['evaluation_paused']
