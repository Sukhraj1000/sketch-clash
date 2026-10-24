"""Observability evidence, privacy and recovery without network or real saves."""
import asyncio
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.trace import Status, StatusCode

from app.config import Settings
from app.observability import (AtlasSpanExporter, Observatory, agent_span, instrument_app,
                               record_event, register_observatory_routes, safe)
from app.repository import MemoryRepository


def repository(world='observatory-fixture'):
    return MemoryRepository(Settings(repository='memory', world_id=world))


def emit(repo, identifier, **fields):
    return repo.transaction(lambda tx: record_event(tx, repo.world_id, event_id=identifier,
        kind='board.message', message='I can support the crossing.', **fields))


def test_event_is_transactional_world_scoped_and_idempotent():
    repo = repository()
    first = emit(repo, 'message-1', island_id='winners', actor_id='ruler', data={'project_id': 'crossing'})
    assert first['committed'] and first['sequence'] == 1
    assert emit(repo, 'message-1', island_id='winners') == first
    assert emit(repo, 'message-2', island_id='losers')['sequence'] == 2
    with pytest.raises(RuntimeError):
        def fail(tx):
            record_event(tx, repo.world_id, event_id='rollback', kind='task.completed')
            raise RuntimeError('transaction aborted')
        repo.transaction(fail)
    assert len(repo._data['agentEvents']) == 2
    obs = Observatory(repo)
    assert [r['sequence'] for r in obs.events(island_id='winners')['events']] == [1]
    assert [r['sequence'] for r in obs.events(after=1)['events']] == [2]
    repo.transaction(lambda tx: record_event(tx, 'other-world', event_id='foreign', kind='board.message'))
    assert len(obs.events()['events']) == 2


def test_event_payload_drops_credentials_prompts_and_raw_media():
    repo = repository()
    event = emit(repo, 'private', data={'project_id': 'bridge', 'api_key': 'SECRET',
        'raw_prompt': 'PRIVATE', 'image_bytes': 'PRIVATE', 'nested': {'password': 'PRIVATE'},
        'diagnostic': 'mongodb+srv://person:password@private.host/db', 'input_tokens': 12})
    encoded = json.dumps(event)
    assert 'SECRET' not in encoded and 'PRIVATE' not in encoded and 'password@' not in encoded
    assert event['data']['input_tokens'] == 12
    assert len(safe('a' * 10000)) == 1600
    assert len(safe(list(range(100)))) == 30


def test_otel_export_is_sanitized_idempotent_and_suppresses_recursive_db_spans():
    repo = repository()
    exporter = AtlasSpanExporter()
    exporter.repository = repo
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    original = repo.transaction
    instrumentation_states = []
    def guarded(operation):
        instrumentation_states.append(is_instrumentation_enabled())
        return original(operation)
    repo.transaction = guarded
    tracer = provider.get_tracer('fixture')
    with tracer.start_as_current_span('agent.model_turn', attributes={
        'sketch.island_id': 'winners', 'sketch.model': 'fixture-model',
        'gen_ai.usage.input_tokens': 42, 'gen_ai.usage.output_tokens': 9,
        'api_key': 'PRIVATE', 'db.statement': 'PRIVATE'}) as span:
        span.set_status(Status(StatusCode.ERROR))
    assert instrumentation_states == [False]
    rows = list(repo._data['agentSpans'].values())
    assert len(rows) == 1 and rows[0]['status'] == 'ERROR'
    assert 'PRIVATE' not in json.dumps(safe(rows))
    metric = next(iter(repo._data['agentMetrics'].values()))
    assert metric['count'] == 1 and metric['input_tokens'] == 42 and metric['output_tokens'] == 9
    assert metric['errors'] == 1
    obs = Observatory(repo)
    assert len(obs.trace_detail(rows[0]['trace_id'])['spans']) == 1
    assert obs.metrics('winners')['totals']['count'] == 1
    assert obs.metrics('losers')['totals']['count'] == 0
    provider.shutdown()


def test_export_failure_is_contained_without_touching_game_state():
    repo = repository()
    exporter = AtlasSpanExporter()
    exporter.repository = repo
    def failure(_):
        raise RuntimeError('offline')
    repo.transaction = failure
    assert exporter.export([]) == SpanExportResult.FAILURE
    assert exporter.failures == 1


def test_event_records_trace_context_and_retention_boundary():
    repo = repository()
    with agent_span('agent.validate', island_id='winners') as span:
        event = emit(repo, 'linked', island_id='winners')
        assert event['trace_id'] == format(span.get_span_context().trace_id, '032x')
    for index in range(1, 4):
        emit(repo, str(index))
    # Simulate expiry of the earliest operational events (durable game data is elsewhere).
    repo._data['agentEvents'] = {k:v for k,v in repo._data['agentEvents'].items() if v['sequence'] >= 4}
    assert Observatory(repo).events(after=1)['resync_required']


def test_subscriber_overflow_requests_explicit_resync_and_deduplicates():
    obs = Observatory(repository())
    queue = asyncio.Queue(maxsize=1)
    obs.subscribers.add(queue)
    obs._publish({'sequence': 1})
    obs._publish({'sequence': 1})
    assert queue.qsize() == 1
    obs._publish({'sequence': 2})
    assert queue.get_nowait() == {'resync': True}


@pytest.mark.asyncio
async def test_sse_backfill_deduplicates_newly_queued_events_and_stays_world_scoped():
    repo = repository()
    event = emit(repo, 'first', island_id='winners')
    obs = Observatory(repo)
    obs.running = True
    class Request:
        async def is_disconnected(self):
            return False
    stream = obs.subscribe(Request(), 0, 'winners')
    first = await anext(stream)
    assert 'id: 1\n' in first and event['id'] in first
    # The stream registered before reading, so the same event can legitimately be queued.
    obs._publish(event)
    next_event = emit(repo, 'second', island_id='winners')
    obs._publish(next_event)
    second = await asyncio.wait_for(anext(stream), 1)
    assert 'id: 2\n' in second and next_event['id'] in second
    await stream.aclose()
    assert not obs.subscribers


@pytest.mark.asyncio
async def test_read_only_routes_and_trace_id_validation():
    repo = repository()
    event = emit(repo, 'route', session_id='council-1', island_id='winners')
    app = FastAPI()
    instrument_app(app)
    app.state.observatory = Observatory(repo)
    register_observatory_routes(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/observatory/events')
        assert response.status_code == 200
        assert response.json()['events'][0]['id'] == event['id']
        assert response.json()['persistence'] == 'development_memory'
        sessions = (await client.get('/api/observatory/sessions')).json()['sessions']
        assert sessions[0]['id'] == 'council-1'
        assert (await client.get('/api/observatory/traces/invalid')).status_code == 400
        assert (await client.get('/api/observatory/metrics')).status_code == 200
    assert len(repo._data['agentEvents']) == 1


def test_main_lifespan_integrates_observatory_without_live_models_or_external_storage():
    from fastapi.testclient import TestClient
    from backend.app.config import Settings as RuntimeSettings
    from backend.app.main import create_app
    from backend.app.repository import MemoryRepository as RuntimeRepository
    from backend.app.observability import record_event as runtime_event
    settings = RuntimeSettings(repository='memory', world_id='observatory-main-fixture')
    repo = RuntimeRepository(settings)
    repo.transaction(lambda tx: runtime_event(tx, repo.world_id, event_id='integration',
        kind='capabilities.changed', island_id='winners', message='A new vessel expands the crew’s options.'))
    with TestClient(create_app(settings, repo, object())) as client:
        response = client.get('/api/observatory/events')
        assert response.status_code == 200
        assert response.json()['events'][0]['kind'] == 'capabilities.changed'
        assert response.json()['transport'] == 'development_memory'
        assert client.get('/api/observatory/sessions').status_code == 200
        assert client.get('/api/observatory/metrics').status_code == 200
        assert client.app.state.observatory.task is not None
    assert client.app.state.observatory.task is None
