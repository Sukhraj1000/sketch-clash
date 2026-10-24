"""No provider calls: paused development keeps durable local work available."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.colony_planner import ColonyPlanner
from app.island_planner import IslandPlanner
from app.main import create_app
from app.provider_queue import ProviderFailure, ProviderQueue
from app.quality import QualityStore
from app.quality_jobs import JobBudget, QualityWorker
from app.quality_references import ApprovedReferences
from app.recognition import RecognitionService
from app.repository import MemoryRepository, StoreError
from app.retrieval import AtlasRetriever
from test_colony_planner import Colonies, Provider as CouncilProvider
from test_island_planner import Island, Provider as ReflectionProvider
from test_quality import create_job, seed_case
from test_recognition import FakeClient, FakeEvidence, recognize


class Budget:
    def __init__(self): self.reservations = []
    async def reserve(self, **kwargs): self.reservations.append(kwargs)


@pytest.mark.asyncio
async def test_shared_queue_pause_never_calls_provider_or_records_throttle():
    queue = ProviderQueue(paused=True)
    calls = []
    async def forbidden(): calls.append('sent')
    for category in ('recognition', 'agent', 'reflection', 'embedding', 'quality'):
        with pytest.raises(ProviderFailure) as exc:
            await queue.run('fixture', forbidden, category)
        assert exc.value.diagnostic.category == 'ai_paused'
        assert exc.value.diagnostic.outcome_known and not exc.value.diagnostic.retryable
    assert not calls
    status = queue.status()
    assert status['paused'] and status['pause_reason']
    assert status['active'] == status['waiting'] == status['completed'] == status['throttled'] == 0
    assert status['last_error'] is None  # A local pause is not a Google error.


@pytest.mark.asyncio
async def test_queue_rechecks_pause_after_waiting_for_a_slot():
    queue = ProviderQueue(concurrency=1)
    started, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def first():
        calls.append('first'); started.set(); await release.wait()
    async def second(): calls.append('second')
    active = asyncio.create_task(queue.run('fixture', first))
    await started.wait()
    waiting = asyncio.create_task(queue.run('fixture', second))
    await asyncio.sleep(0)
    queue.paused = True; release.set()
    await active
    with pytest.raises(ProviderFailure): await waiting
    assert calls == ['first'] and queue.status()['completed'] == 1


@pytest.mark.asyncio
async def test_recognition_pause_is_explicit_before_evidence_or_budget():
    provider, budget = FakeClient([]), Budget()
    service = RecognitionService(Settings(ai_paused=True), client=provider, evidence_runner=FakeEvidence())
    with pytest.raises(StoreError) as exc: await recognize(service, request_budget=budget)
    assert exc.value.code == 'ai_paused'
    with pytest.raises(StoreError): await service._request([], request_budget=budget)
    assert provider.calls == budget.reservations == []


@pytest.mark.asyncio
async def test_all_embedding_adapters_stop_before_budget_or_provider():
    calls, budget = [], Budget()
    async def forbidden(**kwargs): calls.append(kwargs); raise AssertionError('must not dispatch')
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(embed_content=forbidden)))
    settings = Settings(repository='memory', ai_paused=True)
    repo = MemoryRepository(settings)
    retriever = AtlasRetriever(client=client, settings=settings)
    with pytest.raises(StoreError): await retriever.embed('a useful water container')
    assert (await retriever.search('water'))['status'] == 'ai_paused'
    references = ApprovedReferences(repo, settings, client=client)
    with pytest.raises(StoreError): await references._embed({'data': b'not-read'}, budget)
    assert await references.retrieve('not-read') == []
    assert references.status['status'] == 'ai_paused'
    assert calls == budget.reservations == []


@pytest.mark.asyncio
@pytest.mark.parametrize('planner_type', ['council', 'reflection'])
async def test_queued_plans_survive_pause_without_call_or_budget_change(planner_type):
    settings = Settings(repository='memory', gemini_api_key='fixture-only')
    repo = MemoryRepository(settings)
    provider = CouncilProvider() if planner_type == 'council' else ReflectionProvider()
    store = Colonies() if planner_type == 'council' else Island()
    cls = ColonyPlanner if planner_type == 'council' else IslandPlanner
    worker = cls(repo, store, settings, client=provider)
    run = worker.request('queued-before-outage')
    worker.settings = replace(settings, ai_paused=True)
    before = deepcopy(repo._data)
    await worker.run(run['id'])
    with pytest.raises(StoreError) as exc: worker.request('during-outage')
    assert exc.value.code == 'ai_paused'
    with pytest.raises(StoreError): worker.toggle(True)
    assert worker.status()['paused'] and worker.status()['requests_today'] == 0
    assert repo._data == before and not provider.calls


@pytest.mark.asyncio
async def test_quality_pause_keeps_durable_control_checkpoints_and_budgets():
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    store = QualityStore(repo)
    seed_case(repo, 'development')
    job = create_job(store)
    store.set_evaluation_pause(True, reviewer='fixture', reason='Keep batches paused.')
    before = deepcopy(repo._data)
    worker = QualityWorker(store, replace(settings, ai_paused=True))
    await worker.run(job['id'])
    with pytest.raises(StoreError) as exc:
        await JobBudget(store, job['id']).reserve(input_tokens=1, output_tokens=1, kind='fixture')
    assert exc.value.code == 'ai_paused'
    with pytest.raises(StoreError): create_job(store, key='must-not-queue')
    assert repo._data == before
    assert store.evaluation_control()['evaluation_paused']
    assert store.job(job['id'])['budget']['requests'] == 0


def test_http_pause_is_honest_but_world_and_local_simulation_stay_available():
    settings = Settings(repository='memory', ai_paused=True, world_id='paused-http')
    repo = MemoryRepository(settings)
    store = QualityStore(repo)
    control = store.set_evaluation_pause(True, reviewer='fixture', reason='Provider outage.')
    with TestClient(create_app(settings, repo, object())) as client:
        health = client.get('/api/health').json()
        assert health['status'] == 'ready' and health['ai_paused'] and health['ai_status'] == 'paused'
        assert health['gemini']['paused'] and health['ai_pause_reason']
        assert 'fixture-only' not in str(health)
        assert client.get('/api/world').status_code == 200
        island = client.post('/api/island/start', json={})
        assert island.status_code == 200 and island.json()['enabled']
        assert island.json()['runtime']['worker_active']
        assert client.post('/api/island/personas', json={'idempotency_key': 'blocked'}).json()['error']['code'] == 'ai_paused'
        assert client.post('/api/island/planner', json={'enabled': True}).status_code == 503
        battle = client.post('/api/battles', json={'request_id': 'offline-round'}).json()
        upload = client.post('/api/battles/'+battle['id']+'/captures',
            data={'capture_id': 'paused-upload', 'slot': '0', 'source': 'upload'},
            files={'image': ('fixture.png', b'must not be processed', 'image/png')})
        assert upload.status_code == 503 and upload.json()['error']['code'] == 'ai_paused'
        assert store.evaluation_control() == control
        assert not repo._data.get('captures')


def test_pause_setting_defaults_off_and_honors_environment(monkeypatch):
    monkeypatch.setattr('app.config.load_dotenv', lambda *args, **kwargs: None)
    monkeypatch.delenv('SKETCH_AI_PAUSED', raising=False)
    assert Settings.load().ai_paused is False
    monkeypatch.setenv('SKETCH_AI_PAUSED', 'true')
    assert Settings.load().ai_paused is True
    monkeypatch.setenv('SKETCH_AI_PAUSED', 'false')
    assert Settings.load().ai_paused is False
