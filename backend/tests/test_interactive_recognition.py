"""Fast camera pipeline and truthful progress with synthetic local providers only."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.catalog import CharacterCatalog
from app.config import Settings
from app.pipeline import BASELINE_CONFIG, FAST_LIVE_CONFIG, FAST_LIVE_VERSION, validate_pipeline_config
from app.recognition import RecognitionService
from test_recognition import FakeClient, FakeEvidence, proposal, recognize


def test_fast_profile_does_not_change_legacy_defaults_or_pinned_configuration():
    old = {key: value for key, value in BASELINE_CONFIG.items() if key != 'catalog_mode'}
    before = deepcopy(old)
    normalized = validate_pipeline_config(old)
    assert old == before
    assert normalized['model'] == 'gemini-4-argon'
    assert normalized['thinking_level'] == 'medium' and normalized['catalog_mode'] == 'hybrid'
    assert validate_pipeline_config(FAST_LIVE_CONFIG)['model'] == 'gemini-3.8-flash'
    assert FAST_LIVE_CONFIG['thinking_level'] == 'low'


@pytest.mark.asyncio
async def test_fast_unknown_kind_keeps_identity_without_optional_paid_semantic_search():
    class ForbiddenSearch:
        async def search(self, _description):
            pytest.fail('Fast capture must not spend an optional embedding request.')
    value = proposal(proposed_label='microphone', canonical_type_candidate='microphone')
    value['visual_spec']['template_id'] = 'generic'
    client = FakeClient([value])
    catalog = CharacterCatalog(retriever=ForbiddenSearch())
    service = RecognitionService(Settings(), client=client, evidence_runner=FakeEvidence(), catalog=catalog)
    observed = await recognize(service, pipeline_config=FAST_LIVE_CONFIG, pipeline_version_id=FAST_LIVE_VERSION)
    assert observed.status == 'recognized'
    assert observed.pending_fighter.canonical_type_id == 'microphone'
    assert observed.pending_fighter.pipeline_version_id == FAST_LIVE_VERSION
    assert observed.evidence['retrieval']['status'] == 'skipped'
    assert observed.evidence['gemini']['retrieval_reviewed'] is False
    assert len(client.calls) == 1
    assert client.calls[0]['model'] == observed.evidence['gemini']['model'] == 'gemini-3.8-flash'
    assert client.calls[0]['generation_config']['thinking_level'] == 'low'
    alias = await catalog.resolve_character_type('coffee mug', semantic_search=False)
    assert alias['record']['canonical_type_id'] == 'mug'


@pytest.mark.asyncio
async def test_progress_and_timings_distinguish_queue_from_actual_provider_time(monkeypatch):
    import app.recognition as module
    clock = [100.]
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    progress = []
    async def on_progress(value):
        progress.append(value)
    class Client(FakeClient):
        async def create(self, **kwargs):
            assert progress[-1]['stage'] == 'gemini_recognition'
            clock[0] += 2
            return await super().create(**kwargs)
    class Queue:
        def require_enabled(self): pass
        async def run(self, model, operation, category, *, prepare, priority):
            assert progress[-1]['stage'] == 'queued'
            assert category == 'recognition' and priority == 'foreground'
            clock[0] += 60
            return await operation()
    service = RecognitionService(Settings(), client=Client([proposal()]), evidence_runner=FakeEvidence())
    service.provider_queue = Queue()
    observed = await recognize(service, pipeline_config=FAST_LIVE_CONFIG, on_progress=on_progress)
    assert [row['stage'] for row in progress] == ['local_detection', 'local_ocr', 'queued', 'gemini_recognition', 'validation']
    assert all(set(row) <= {'stage', 'model', 'attempt'} for row in progress)
    assert all(row['model'] == 'gemini-3.8-flash' for row in progress)
    assert observed.evidence['timings']['queue_ms'] == 60000
    assert observed.evidence['timings']['provider_ms'] == 2000
    assert observed.evidence['timings']['requests'] == [{'attempt': 1, 'queue_ms': 60000, 'provider_ms': 2000}]
    assert observed.evidence['gemini']['duration_ms'] == 2000
    assert observed.evidence['gemini']['queue_duration_ms'] == 60000


@pytest.mark.asyncio
async def test_real_validation_errors_still_repair_on_fast_profile():
    bad = proposal(stats={'health': 100, 'attack': 999, 'defense': 1, 'speed': 1})
    client = FakeClient([bad, proposal()])
    progress = []
    async def on_progress(value): progress.append(value)
    service = RecognitionService(Settings(), client=client, evidence_runner=FakeEvidence())
    observed = await recognize(service, pipeline_config=FAST_LIVE_CONFIG, on_progress=on_progress)
    assert observed.status == 'recognized' and len(client.calls) == 2
    assert {'stage': 'repair', 'model': 'gemini-3.8-flash', 'attempt': 2} in progress
    assert all(row['model'] == 'gemini-3.8-flash' for row in client.calls)


@pytest.mark.asyncio
async def test_evaluation_calls_keep_background_priority():
    class Budget:
        async def check(self): pass
        async def reserve(self, **_kwargs): return {'id': 'fixture'}
        async def complete(self, *_args): pass
    class Queue:
        def require_enabled(self): pass
        async def run(self, model, operation, category, *, prepare, priority):
            assert category == 'evaluation_recognition' and priority == 'background'
            await prepare()
            return await operation()
    service = RecognitionService(Settings(), client=FakeClient([proposal()]), evidence_runner=FakeEvidence())
    service.provider_queue = Queue()
    await service._request([], request_budget=Budget())
