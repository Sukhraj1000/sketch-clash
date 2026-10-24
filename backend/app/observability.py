"""Evidence-driven Observatory: transactional events, OpenTelemetry, and one stream.

Domain events are committed with the state they describe. Trace spans describe
attempts and never stand in for a successful transaction. Export writes suppress
instrumentation, and telemetry failure must not stop the simulation.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
from threading import RLock
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Link, SpanContext, Status, StatusCode, TraceFlags

from .repository import Repository, StoreError, key_for, now_iso

logger = logging.getLogger('sketch_clash.observatory')
OPERATION_DAYS = 7
METRIC_DAYS = 30
_PRIVATE = re.compile(r'password|secret|credential|authorization|api.?key|(^|_)token$|prompt|image|capture_bytes|raw_|statement|connection_string|mongodb_uri', re.I)
_SECRET_TEXT = re.compile(r'AIza[\w-]{20,}|mongodb(?:\+srv)?://[^\s]+|Bearer\s+[^\s]+', re.I)
_provider: TracerProvider | None = None
_exporter: AtlasSpanExporter | None = None
_init_lock = RLock()
_scope: ContextVar[dict] = ContextVar('agent_telemetry_scope', default={})


def safe(value: Any, depth: int = 0) -> Any:
    """Allow small structured diagnostics, never raw requests or credential fields."""
    if depth > 5:
        return '[depth limited]'
    if isinstance(value, dict):
        return {str(k)[:80]: safe(v, depth + 1) for k, v in list(value.items())[:40]
                if not _PRIVATE.search(str(k))}
    if isinstance(value, (list, tuple)):
        return [safe(v, depth + 1) for v in value[:30]]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return _SECRET_TEXT.sub('[redacted]', value)[:1600]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(type(value).__name__)


def _public(value: dict) -> dict:
    return {k: safe(v) for k, v in value.items() if k not in ('_id', 'expires_at')}


def record_event(tx, world_id: str, *, event_id: str, kind: str,
                 island_id: str | None = None, actor_id: str | None = None,
                 actor_name: str | None = None, session_id: str | None = None,
                 message: str = '', data: dict | None = None, at: str | None = None) -> dict:
    """Call INSIDE the mutation transaction using a stable semantic event ID."""
    identifier = key_for(world_id, 'agent-event', event_id)
    existing = tx.get('agentEvents', identifier)
    if existing:
        return _public(existing)
    timestamp = at or now_iso()
    instant = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    counter_id = key_for(world_id, 'observatory-sequence')
    counter = tx.get('observatoryCounters', counter_id) or {'_id': counter_id, 'world_id': world_id, 'sequence': 0}
    counter['sequence'] += 1
    tx.put('observatoryCounters', counter)
    context = trace.get_current_span().get_span_context()
    row = {'_id': identifier, 'id': identifier, 'world_id': world_id,
           'sequence': counter['sequence'], 'kind': kind[:80], 'created_at': timestamp,
           'island_id': island_id, 'actor_id': actor_id, 'actor_name': safe(actor_name),
           'session_id': session_id, 'message': safe(message), 'data': safe(data or {}),
           'trace_id': format(context.trace_id, '032x') if context.is_valid else None,
           'span_id': format(context.span_id, '016x') if context.is_valid else None,
           'committed': True, 'expires_at': instant + timedelta(days=OPERATION_DAYS)}
    tx.put('agentEvents', row)
    return _public(row)


@contextmanager
def agent_span(name: str, *, link_trace_id: str | None = None, link_span_id: str | None = None, **attributes):
    provider = _ensure_provider()
    clean = {f'sketch.{k}': v for k, v in safe(attributes).items()
             if isinstance(v, (str, bool, int, float))}
    links = []
    if isinstance(link_trace_id, str) and isinstance(link_span_id, str) and re.fullmatch(r'[a-fA-F0-9]{32}', link_trace_id) and re.fullmatch(r'[a-fA-F0-9]{16}', link_span_id):
        context = SpanContext(trace_id=int(link_trace_id, 16), span_id=int(link_span_id, 16),
            is_remote=False, trace_flags=TraceFlags(TraceFlags.SAMPLED))
        if context.is_valid:
            links.append(Link(context, attributes={'sketch.relationship': 'caused_by_decision'}))
    token = _scope.set({**_scope.get(), **clean})
    try:
        with provider.get_tracer('sketch-clash.agents').start_as_current_span(
                name[:100], attributes=clean, links=links, record_exception=False,
                set_status_on_exception=False) as span:
            try:
                yield span
            except BaseException as exc:
                span.set_attribute('error.type', type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR))
                raise
    finally:
        _scope.reset(token)



class AtlasSpanExporter(SpanExporter):
    """A bounded OTel batch consumer; Atlas is storage, not an OTLP collector."""
    def __init__(self):
        self.repository: Repository | None = None
        self.exported = 0
        self.dropped = 0
        self.failures = 0

    def export(self, spans):
        repo = self.repository
        if repo is None:
            return SpanExportResult.SUCCESS
        documents = []
        for span in spans:
            attrs = safe(dict(span.attributes or {}))
            # Polling the Observatory must not manufacture an infinite activity feed.
            if '/api/observatory' in str(attrs.get('http.route', '')):
                continue
            ctx = span.context
            if not ctx:
                continue
            start = datetime.fromtimestamp(span.start_time / 1e9, timezone.utc)
            duration = max(0, (span.end_time - span.start_time) / 1e6)
            doc = {'_id': key_for(repo.world_id, format(ctx.trace_id, '032x'), format(ctx.span_id, '016x')),
                   'world_id': repo.world_id, 'trace_id': format(ctx.trace_id, '032x'),
                   'span_id': format(ctx.span_id, '016x'),
                   'parent_span_id': format(span.parent.span_id, '016x') if span.parent else None,
                   'name': safe(span.name), 'kind': span.kind.name, 'created_at': start.isoformat(),
                   'duration_ms': round(duration, 3), 'status': span.status.status_code.name,
                   'attributes': attrs,
                   'links': [{'trace_id': format(link.context.trace_id, '032x'),
                              'span_id': format(link.context.span_id, '016x')} for link in span.links[:12]],
                   'expires_at': start + timedelta(days=OPERATION_DAYS)}
            documents.append(doc)
        try:
            with suppress_instrumentation():
                def save(tx):
                    if hasattr(tx, 'database') and documents:
                        # One read and two bulk writes per batch. A round trip per span
                        # cannot keep up with instrumented Atlas calls over a home link.
                        from pymongo import UpdateOne
                        ids = [doc['_id'] for doc in documents]
                        existing = {row['_id'] for row in tx.database.agentSpans.find(
                            {'_id': {'$in': ids}}, {'_id': 1}, session=tx.session)}
                        fresh = [doc for doc in documents if doc['_id'] not in existing]
                        if not fresh:
                            return
                        groups = {}
                        for doc in fresh:
                            attrs = doc['attributes']
                            minute = doc['created_at'][:16]
                            island = attrs.get('sketch.island_id', 'system')
                            operation = 'model' if 'model' in doc['name'] else ('database' if attrs.get('db.system', attrs.get('db.system.name')) == 'mongodb' else 'agent' if doc['name'].startswith(('agent.', 'council.', 'island.')) else 'http')
                            model = attrs.get('sketch.model', attrs.get('gen_ai.request.model', 'none'))
                            metric_id = key_for(repo.world_id, minute, str(island), operation, str(model))
                            group = groups.setdefault(metric_id, {
                                'metadata': {'world_id': repo.world_id, 'minute': minute, 'island_id': island,
                                    'operation': operation, 'model': model,
                                    'expires_at': datetime.fromisoformat(doc['created_at']) + timedelta(days=METRIC_DAYS)},
                                'delta': {'count': 0, 'errors': 0, 'duration_ms': 0, 'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}})
                            delta = group['delta']
                            delta['count'] += 1
                            delta['errors'] += int(doc['status'] == 'ERROR')
                            delta['duration_ms'] += doc['duration_ms']
                            inputs = int(attrs.get('gen_ai.usage.input_tokens', attrs.get('sketch.input_tokens', 0)) or 0)
                            outputs = int(attrs.get('gen_ai.usage.output_tokens', attrs.get('sketch.output_tokens', 0)) or 0)
                            delta['input_tokens'] += inputs
                            delta['output_tokens'] += outputs
                            delta['total_tokens'] += int(attrs.get('gen_ai.usage.total_tokens', inputs + outputs) or 0)
                        tx.database.agentSpans.bulk_write([UpdateOne({'_id': doc['_id']},
                            {'$setOnInsert': doc}, upsert=True) for doc in fresh], ordered=False, session=tx.session)
                        tx.database.agentMetrics.bulk_write([UpdateOne({'_id': metric_id},
                            {'$setOnInsert': group['metadata'], '$inc': group['delta']}, upsert=True)
                            for metric_id, group in groups.items()], ordered=False, session=tx.session)
                        return
                    for doc in documents:
                        if tx.get('agentSpans', doc['_id']):
                            continue
                        tx.put('agentSpans', doc)
                        minute = doc['created_at'][:16]
                        attrs = doc['attributes']
                        island = attrs.get('sketch.island_id', 'system')
                        operation = 'model' if 'model' in doc['name'] else ('database' if attrs.get('db.system') == 'mongodb' else 'agent' if doc['name'].startswith(('agent.', 'council.', 'island.')) else 'http')
                        model = attrs.get('sketch.model', attrs.get('gen_ai.request.model', 'none'))
                        metric_id = key_for(repo.world_id, minute, str(island), operation, str(model))
                        metric = tx.get('agentMetrics', metric_id) or {
                            '_id': metric_id, 'world_id': repo.world_id, 'minute': minute,
                            'island_id': island, 'operation': operation, 'model': model,
                            'count': 0, 'errors': 0, 'duration_ms': 0, 'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
                            'expires_at': datetime.fromisoformat(doc['created_at']) + timedelta(days=METRIC_DAYS)}
                        metric['count'] += 1
                        metric['errors'] += int(doc['status'] == 'ERROR')
                        metric['duration_ms'] += doc['duration_ms']
                        metric['input_tokens'] += int(attrs.get('gen_ai.usage.input_tokens', attrs.get('sketch.input_tokens', 0)) or 0)
                        metric['output_tokens'] += int(attrs.get('gen_ai.usage.output_tokens', attrs.get('sketch.output_tokens', 0)) or 0)
                        metric['total_tokens'] = metric.get('total_tokens', 0) + int(attrs.get('gen_ai.usage.total_tokens',
                            int(attrs.get('gen_ai.usage.input_tokens', 0) or 0) + int(attrs.get('gen_ai.usage.output_tokens', 0) or 0)) or 0)
                        tx.put('agentMetrics', metric)
                repo.transaction(save)
            self.exported += len(documents)
            return SpanExportResult.SUCCESS
        except Exception as exc:
            self.failures += 1
            self.dropped += len(documents)
            logger.warning('telemetry_export_failed category=%s', type(exc).__name__)
            return SpanExportResult.FAILURE

    def shutdown(self):
        self.repository = None


def _ensure_provider() -> TracerProvider:
    global _provider, _exporter
    with _init_lock:
        if _provider is None:
            _provider = TracerProvider(resource=Resource.create({'service.name': 'sketch-clash-local', 'service.version': '3'}))
            _exporter = AtlasSpanExporter()
            _provider.add_span_processor(BatchSpanProcessor(_exporter, max_queue_size=2048,
                max_export_batch_size=128, schedule_delay_millis=3000, export_timeout_millis=5000))
            # Exporting off-machine is opt-in via the standard server-side OTel variable.
            if os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT'):
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        return _provider


def instrument_app(app: FastAPI) -> None:
    """Call before creating MongoClient and before FastAPI starts."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
    provider = _ensure_provider()
    if not PymongoInstrumentor().is_instrumented_by_opentelemetry:
        def mongo_scope(span, event):
            # ContextVars propagate through asyncio.to_thread; IDs stay in spans,
            # while only island/model/operation become metric dimensions.
            for key, value in _scope.get().items():
                span.set_attribute(key, value)
        PymongoInstrumentor().instrument(tracer_provider=provider, capture_statement=False, request_hook=mongo_scope)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider,
        excluded_urls=r'.*/api/observatory/.*', exclude_spans=['receive', 'send'])


class Observatory:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.world_id = repository.world_id
        self.task: asyncio.Task | None = None
        self.running = False
        self.subscribers: set[asyncio.Queue] = set()
        self.last_sequence = 0
        self.transport = 'development_memory' if repository.persistence != 'mongodb' else 'connecting'
        self.stream_error: str | None = None
        self.stream = None
        self._resume_token = None

    def ensure_indexes(self):
        if not hasattr(self.repository, 'db'):
            return
        with suppress_instrumentation():
            db = self.repository.db
            db.agentEvents.create_index([('world_id', 1), ('sequence', 1)], unique=True)
            db.agentEvents.create_index([('world_id', 1), ('session_id', 1), ('sequence', 1)])
            db.agentSpans.create_index([('world_id', 1), ('trace_id', 1)])
            db.agentMetrics.create_index([('world_id', 1), ('minute', -1)])
            for name in ('agentEvents', 'agentSpans', 'agentMetrics'):
                db[name].create_index('expires_at', expireAfterSeconds=0)

    async def start(self):
        _ensure_provider()
        try:
            await asyncio.to_thread(self.ensure_indexes)
        except Exception as exc:
            self.stream_error = f'Indexes unavailable ({type(exc).__name__})'
        if _exporter:
            _exporter.repository = self.repository
        # Historic events remain available for replay; only new arrivals fan out live.
        try:
            self.last_sequence = (await asyncio.to_thread(self.events, limit=1))['cursor']
        except Exception:
            self.last_sequence = 0
        self.running = True
        self.task = asyncio.create_task(self._run(), name='observatory-events')

    async def close(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.stream:
            try:
                await asyncio.to_thread(self.stream.close)
            except Exception:
                pass
        if _provider:
            await asyncio.to_thread(_provider.force_flush, 5000)
        if _exporter and _exporter.repository is self.repository:
            _exporter.repository = None

    def _rows(self, collection, query, sort=None, limit=500):
        with suppress_instrumentation():
            return self.repository.read(lambda tx: tx.find(collection, {'world_id': self.world_id, **query}, sort, limit))

    def events(self, *, after: int | None = None, island_id: str | None = None,
               session_id: str | None = None, limit: int = 200) -> dict:
        limit = min(500, max(1, limit))
        query = {}
        if island_id:
            query['island_id'] = island_id
        if session_id:
            query['session_id'] = session_id
        if hasattr(self.repository, 'db'):
            with suppress_instrumentation():
                mongo_query = {'world_id': self.world_id, **query}
                if after is not None:
                    mongo_query['sequence'] = {'$gt': after}
                    rows = list(self.repository.db.agentEvents.find(mongo_query).sort('sequence', 1).limit(limit))
                else:
                    rows = list(self.repository.db.agentEvents.find(mongo_query).sort('sequence', -1).limit(limit))
                    rows.reverse()
                first = self.repository.db.agentEvents.find_one({'world_id': self.world_id}, sort=[('sequence', 1)])
        else:
            rows = sorted(self._rows('agentEvents', query, 'sequence', 10000), key=lambda r: r['sequence'])
            first = next(iter(rows), None)
            rows = [r for r in rows if after is None or r['sequence'] > after]
            rows = rows[-limit:] if after is None else rows[:limit]
        expired = bool(after and first and after < first['sequence'] - 1)
        return {'events': [_public(r) for r in rows], 'cursor': rows[-1]['sequence'] if rows else after or 0,
                'resync_required': expired, 'persistence': self.repository.persistence,
                'transport': self.transport, 'stream_error': self.stream_error,
                'server_time': now_iso()}

    def sessions(self):
        # Read the real persisted council sessions; event-only sessions remain discoverable.
        direct = self._rows('colonyCouncilSessions', {}, None, 200)
        sessions = {row.get('id', row.get('_id')): _public(row) for row in direct}
        for row in self.events(limit=500)['events']:
            session_id = row.get('session_id')
            if not session_id:
                continue
            entry = sessions.setdefault(session_id, {'id': session_id, 'island_id': row.get('island_id'),
                'created_at': row['created_at'], 'status': 'recorded', 'event_count': 0})
            entry['last_event_at'] = row['created_at']
            entry['event_count'] = entry.get('event_count', 0) + 1
        return {'sessions': sorted(sessions.values(), key=lambda r: r.get('last_event_at', r.get('created_at', '')), reverse=True)[:100]}

    def trace_detail(self, trace_id):
        rows = self._rows('agentSpans', {'trace_id': trace_id}, 'created_at', 300)
        return {'trace_id': trace_id, 'spans': [_public(r) for r in reversed(rows)],
                'note': 'Spans record attempted operations. Committed domain events prove state changes.'}

    def metrics(self, island_id=None, window=60):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=min(1440, max(1, window)))).isoformat()[:16]
        query = {'island_id': island_id} if island_id else {}
        rows = [r for r in self._rows('agentMetrics', query, 'minute', 3000) if r['minute'] >= cutoff]
        totals = {key: sum(r.get(key, 0) for r in rows) for key in ('count', 'errors', 'duration_ms', 'input_tokens', 'output_tokens', 'total_tokens')}
        totals['mean_duration_ms'] = round(totals['duration_ms'] / max(1, totals['count']), 1)
        events = [r for r in self.events(island_id=island_id, limit=500)['events'] if r['created_at'][:16] >= cutoff]
        counts: dict[str, int] = defaultdict(int)
        for row in events:
            counts[row['kind']] += 1
        return {'window_minutes': window, 'totals': totals, 'event_counts': dict(counts),
                'series': [_public(r) for r in reversed(rows)], 'persistence': self.repository.persistence,
                'events_sample_limit': 500, 'event_counts_sampled': len(events) >= 500,
                'exported_spans': _exporter.exported if _exporter else 0,
                'dropped_spans': _exporter.dropped if _exporter else 0,
                'export_failures': _exporter.failures if _exporter else 0}

    def _publish(self, row):
        if row['sequence'] <= self.last_sequence:
            return
        self.last_sequence = row['sequence']
        for queue in tuple(self.subscribers):
            if queue.full():
                # A slow browser gets an explicit replay boundary, never silent loss.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({'resync': True})
            else:
                queue.put_nowait(row)

    def _open_stream(self):
        with suppress_instrumentation():
            db = self.repository.db
            cursor_id = key_for(self.world_id, 'observatory-resume')
            cursor = db.observatoryCursors.find_one({'_id': cursor_id})
            options = {'max_await_time_ms': 1000, 'full_document': 'updateLookup'}
            if cursor and cursor.get('resume_token'):
                options['resume_after'] = cursor['resume_token']
            self.stream = db.agentEvents.watch([
                {'$match': {'operationType': 'insert', 'fullDocument.world_id': self.world_id}}
            ], **options)
            return self.stream

    def _next_change(self):
        with suppress_instrumentation():
            change = self.stream.try_next()
            token = self.stream.resume_token
            if token and token != self._resume_token:
                self.repository.db.observatoryCursors.update_one(
                    {'_id': key_for(self.world_id, 'observatory-resume')},
                    {'$set': {'world_id': self.world_id, 'resume_token': token, 'updated_at': now_iso()}}, upsert=True)
                self._resume_token = token
            return change

    async def _run(self):
        while self.running:
            try:
                if hasattr(self.repository, 'db') and self.stream is None:
                    try:
                        await asyncio.to_thread(self._open_stream)
                        self.transport, self.stream_error = 'atlas_change_stream', None
                    except Exception as exc:
                        self.transport = 'atlas_polling'
                        self.stream_error = f'Change Stream unavailable ({type(exc).__name__}); committed-event polling active.'
                        # An invalid/expired resume token must not block subsequent stream attempts.
                        if getattr(exc, 'code', None) in (136, 237, 260, 280, 286):
                            def clear():
                                with suppress_instrumentation():
                                    self.repository.db.observatoryCursors.delete_one({'_id': key_for(self.world_id, 'observatory-resume')})
                            await asyncio.to_thread(clear)
                # Catch up in sequence order, including writes during reconnects.
                batch = await asyncio.to_thread(self.events, after=self.last_sequence, limit=500)
                for event in batch['events']:
                    self._publish(event)
                if len(batch['events']) >= 500:
                    continue
                if self.stream:
                    try:
                        change = await asyncio.to_thread(self._next_change)
                        if change:
                            # Do not publish directly: sequence catch-up also handles ordering.
                            continue
                    except Exception as exc:
                        self.stream_error = f'Stream reconnecting ({type(exc).__name__})'
                        try:
                            await asyncio.to_thread(self.stream.close)
                        except Exception:
                            pass
                        self.stream = None
                await asyncio.sleep(0.25 if self.stream else 2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.stream_error = f'Event reads delayed ({type(exc).__name__})'
                await asyncio.sleep(3)

    async def subscribe(self, request: Request, after: int = 0, island_id=None, session_id=None):
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self.subscribers.add(queue)
        cursor = after
        try:
            # Register first, then backfill, then deduplicate queued events.
            while True:
                batch = await asyncio.to_thread(self.events, after=cursor, island_id=island_id, session_id=session_id, limit=500)
                if batch['resync_required']:
                    yield f'event: resync\ndata: {json.dumps({"reason": "retention_boundary", "cursor": cursor})}\n\n'
                for row in batch['events']:
                    cursor = row['sequence']
                    yield f'id: {cursor}\nevent: agent\ndata: {json.dumps(row)}\n\n'
                if len(batch['events']) < 500:
                    break
            while self.running and not await request.is_disconnected():
                try:
                    row = await asyncio.wait_for(queue.get(), 12)
                except asyncio.TimeoutError:
                    yield f'event: status\ndata: {json.dumps({"transport": self.transport, "stream_error": self.stream_error})}\n\n'
                    continue
                if row.get('resync'):
                    yield 'event: resync\ndata: {"reason":"slow_consumer"}\n\n'
                    break
                if row['sequence'] <= cursor:
                    continue
                cursor = row['sequence']
                if island_id and row.get('island_id') != island_id:
                    continue
                if session_id and row.get('session_id') != session_id:
                    continue
                yield f'id: {cursor}\nevent: agent\ndata: {json.dumps(row)}\n\n'
        finally:
            self.subscribers.discard(queue)


def register_observatory_routes(app: FastAPI):
    def service(request):
        obs = getattr(request.app.state, 'observatory', None)
        if obs is None:
            raise StoreError('The Observatory is waiting for the local database connection.', 503, 'observatory_unavailable')
        return obs

    @app.get('/api/observatory/events')
    async def events(request: Request, after: int | None = None, island: str | None = None,
                     session_id: str | None = None, limit: int = 200):
        return await asyncio.to_thread(service(request).events, after=after, island_id=island, session_id=session_id, limit=limit)

    @app.get('/api/observatory/sessions')
    async def sessions(request: Request):
        return await asyncio.to_thread(service(request).sessions)

    @app.get('/api/observatory/traces/{trace_id}')
    async def trace_detail(request: Request, trace_id: str):
        if not re.fullmatch('[a-f0-9]{32}', trace_id):
            return JSONResponse({'error': {'message': 'Invalid trace identifier.'}}, status_code=400)
        return await asyncio.to_thread(service(request).trace_detail, trace_id)

    @app.get('/api/observatory/metrics')
    async def metrics(request: Request, island: str | None = None, window: int = 60):
        return await asyncio.to_thread(service(request).metrics, island, window)

    @app.get('/api/observatory/stream')
    async def stream(request: Request, after: int = 0, island: str | None = None, session_id: str | None = None):
        raw = request.headers.get('last-event-id', str(after))
        cursor = int(raw) if raw.isdigit() else after
        return StreamingResponse(service(request).subscribe(request, cursor, island, session_id),
            media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
