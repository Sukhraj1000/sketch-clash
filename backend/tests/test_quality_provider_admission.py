"""Per-job services use the same provider admission as normal gameplay."""
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import Settings
from app.provider_queue import ProviderQueue
from app.quality import QualityStore
from app.quality_jobs import JobBudget, QualityWorker
from app.recognition import RecognitionService
from app.repository import MemoryRepository
from test_quality import create_job, seed_case
from test_recognition import FakeClient, FakeEvidence, proposal


@pytest.mark.asyncio
async def test_evaluation_recognizer_catalog_and_reference_share_worker_queue(monkeypatch):
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    store = QualityStore(repo)
    case = seed_case(repo, 'evaluation-queue-case')
    seed_case(repo, 'evaluation-queue-reference', 'reference', seed=2)
    job = store.job(create_job(store)['id'])
    worker = QualityWorker(store, settings)
    queue = worker.provider_queue = ProviderQueue()
    provider = FakeClient([proposal()])
    provider.aio.aclose = AsyncMock()
    provider.close = Mock()
    service = RecognitionService(settings, client=provider, evidence_runner=FakeEvidence())
    monkeypatch.setattr('app.recognition.RecognitionService', lambda _settings: service)
    references = []

    class ReferenceAdapter:
        available = True

        def __init__(self, *_args):
            self.provider_queue = None
            references.append(self)

        async def retrieve(self, *_args, **_kwargs):
            assert self.provider_queue is queue
            return []

        async def close(self):
            pass

    monkeypatch.setattr('app.quality_references.ApprovedReferences', ReferenceAdapter)
    await worker.evaluate(job['id'], case, 'baseline', job['baseline_id'],
        {**job['baseline_config'], 'reference_limit': 1}, JobBudget(store, job['id']))
    assert service.provider_queue is queue
    assert service.catalog.retriever.provider_queue is queue
    assert len(references) == 1 and references[0].provider_queue is queue
    assert len(provider.calls) == 1
    assert queue.status()['completed'] == 1
    assert provider.calls[0]['generation_config']['max_output_tokens'] == 4096


@pytest.mark.asyncio
async def test_reference_preparation_inherits_worker_queue(monkeypatch):
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    store = QualityStore(repo)
    seed_case(repo, 'development-case')
    reference = seed_case(repo, 'reference-preparation', 'reference', seed=2)
    job = store.job(create_job(store)['id'])
    worker = QualityWorker(store, settings)
    queue = worker.provider_queue = ProviderQueue()
    prepared = []

    class ReferenceAdapter:
        def __init__(self, *_args):
            self.provider_queue = None

        async def prepare_reference(self, identifier, budget):
            assert self.provider_queue is queue
            prepared.append(identifier)

        async def close(self):
            pass

    monkeypatch.setattr('app.quality_references.ApprovedReferences', ReferenceAdapter)
    await worker.prepare_references(job, JobBudget(store, job['id']))
    assert prepared == [reference['id']]
    assert reference['id'] in store.job(job['id'])['checkpoints']
