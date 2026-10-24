"""Shared Gemini admission and sanitized provider diagnostics.

Credits are not request throughput. This queue honours provider cooldowns without
inventing a daily spending allowance or retrying an ambiguous transport outcome.
"""
from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
import math
import random
import json
import re
import time

AI_PAUSE_REASON = 'AI requests are paused for local development during the Gemini credit outage. Saved island work and Atlas persistence continue.'


def require_ai_enabled(settings, queue=None):
    """Reject before intake, budget reservation or provider dispatch."""
    if getattr(settings, 'ai_paused', False) or getattr(queue, 'paused', False):
        from .repository import StoreError
        raise StoreError(AI_PAUSE_REASON, 503, 'ai_paused')


@dataclass(frozen=True)
class ProviderDiagnostic:
    category: str
    message: str
    status_code: int | None = None
    retryable: bool = False
    retry_after_seconds: float | None = None
    request_id: str | None = None
    quota_metric: str | None = None
    outcome_known: bool = True
    quota_id: str | None = None
    quota_value: int | None = None
    provider_reason: str | None = None
    provider_message: str | None = None
    provider_error_details: list[dict] | None = None
    provider_body_source: str | None = None
    http_endpoint: str | None = None
    http_method: str | None = None
    http_status_source: str | None = None
    observed_at_utc: str | None = None

    def public(self):
        return {key: value for key, value in asdict(self).items() if value is not None}


class ProviderFailure(Exception):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


_KEY_PATTERN = re.compile(r'AIza[A-Za-z0-9_-]{20,}|\bBearer\s+[^\s,;]+', re.I)


def _safe_id(value):
    text = str(value or '')
    return text[:160] if re.fullmatch(r'[A-Za-z0-9._:/ -]{1,160}', text) and not _KEY_PATTERN.search(text) else None


def _safe_endpoint(value):
    """Retain the requested HTTP origin/path, never credentials or query strings."""
    try:
        url = urlsplit(str(value or ''))
        if url.scheme not in ('http', 'https') or not url.hostname: return None
        host = url.hostname
        if ':' in host: host = '[' + host + ']'
        if url.port: host += ':' + str(url.port)
        path = _KEY_PATTERN.sub('[redacted]', url.path)
        return urlunsplit((url.scheme, host, path, '', ''))[:512]
    except (TypeError, ValueError): return None


def _redact_message(value):
    if not isinstance(value, str): return None
    text = value[:8192]
    text = re.sub(r'https?://[^\s<>"\']+', lambda match: _safe_endpoint(match.group()) or '[redacted URL]', text)
    text = _KEY_PATTERN.sub('[redacted]', text)
    text = re.sub(r'(?i)\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret)\s*[:=]\s*["\']?[^\s,;"\']+',
                  '[redacted credential]', text)
    text = re.sub(r'(?i)\bproject(?:\s+(?:id|number))?\s*[:=]?\s+(?:[0-9]{6,}|[A-Za-z0-9_-]*[_-][A-Za-z0-9_-]*)',
                  'project [redacted]', text)
    return text[:1200]


def _delay_seconds(value):
    try:
        delay = float(value.get('seconds', 0)) + float(value.get('nanos', 0)) / 1e9 if isinstance(value, dict) else float(str(value).rstrip('s'))
        return max(0., delay) if math.isfinite(delay) else None
    except (ValueError, TypeError, OverflowError): return None


def _response_body(exc, response):
    if response is not None:
        try:
            body = response.json()
            if isinstance(body, dict): return body, 'response.json'
        except (AttributeError, TypeError, ValueError, RuntimeError): pass
    for name in ('body', 'response_json'):
        body = getattr(exc, name, None)
        if isinstance(body, (str, bytes)):
            try: body = json.loads(body)
            except (TypeError, ValueError): continue
        if isinstance(body, dict): return body, 'sdk.' + name
    return {}, None


def diagnose_provider_error(exc, now=None):
    """Separate redacted response evidence from our human-readable classification."""
    if isinstance(exc, ProviderFailure): return exc.diagnostic
    instant = time.time() if now is None else now
    response = getattr(exc, 'response', None)
    status = None
    status_source = None
    for candidate, source in ((getattr(response, 'status_code', None), 'http_response'),
                              (getattr(exc, 'status_code', None), 'sdk_exception'),
                              (getattr(exc, 'code', None), 'sdk_exception')):
        try:
            parsed = int(candidate)
            if 100 <= parsed <= 599: status, status_source = parsed, source; break
        except (ValueError, TypeError): pass
    if status is None and 'ratelimit' in type(exc).__name__.lower(): status, status_source = 429, 'exception_class'
    headers = getattr(response, 'headers', {}) or getattr(exc, 'headers', {}) or {}
    headers = {str(key).lower(): value for key, value in headers.items()} if hasattr(headers, 'items') else {}
    retry = _delay_seconds(headers.get('retry-after'))
    if retry is None and headers.get('retry-after'):
        try: retry = max(0., parsedate_to_datetime(str(headers['retry-after'])).timestamp() - instant)
        except (ValueError, TypeError, OverflowError): pass
    body, body_source = _response_body(exc, response)
    error = body.get('error', body)
    if not isinstance(error, dict): error = {}
    metric = quota_id = quota_value = None
    raw_details = error.get('details')
    safe_details = [] if isinstance(raw_details, list) else None
    for detail in raw_details[:8] if isinstance(raw_details, list) else []:
        if not isinstance(detail, dict): continue
        safe_detail = {}
        type_id = _safe_id(detail.get('@type') or detail.get('type'))
        if type_id: safe_detail['type'] = type_id
        delay = _delay_seconds(detail.get('retryDelay', detail.get('retry_delay')))
        if delay is not None:
            safe_detail['retry_delay_seconds'] = delay
            if retry is None: retry = delay
        violations = detail.get('violations', [])
        safe_violations = []
        for violation in violations[:8] if isinstance(violations, list) else []:
            if not isinstance(violation, dict): continue
            candidate_metric = _safe_id(violation.get('quotaMetric') or violation.get('quota_metric'))
            candidate_id = _safe_id(violation.get('quotaId') or violation.get('quota_id'))
            try:
                value = int(violation.get('quotaValue', violation.get('quota_value')))
                value = value if 0 <= value <= 10**15 else None
            except (TypeError, ValueError, OverflowError): value = None
            item = {key: value for key, value in {'quota_metric': candidate_metric, 'quota_id': candidate_id, 'quota_value': value}.items() if value is not None}
            dimensions = violation.get('quotaDimensions', violation.get('quota_dimensions', {}))
            if isinstance(dimensions, dict):
                for key in ('model', 'location'):
                    dimension = _safe_id(dimensions.get(key))
                    if dimension: item[key] = dimension
            if item: safe_violations.append(item)
            if quota_value != 0:
                metric, quota_id, quota_value = candidate_metric or metric, candidate_id or quota_id, value
        if safe_violations: safe_detail['violations'] = safe_violations
        if safe_detail: safe_details.append(safe_detail)
    request_id = _safe_id(headers.get('x-request-id') or headers.get('x-goog-request-id') or getattr(exc, 'request_id', None))
    try: request = getattr(response, 'request', None)
    except (AttributeError, RuntimeError): request = None
    method = getattr(request, 'method', None)
    method = method.upper() if isinstance(method, str) and method.upper() in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS') else None
    evidence = {'request_id': request_id, 'quota_metric': metric, 'quota_id': quota_id, 'quota_value': quota_value,
                'provider_reason': _safe_id(error.get('status') or error.get('code')),
                'provider_message': _redact_message(error.get('message')),
                'provider_error_details': safe_details, 'provider_body_source': body_source,
                'http_endpoint': _safe_endpoint(getattr(request, 'url', None)), 'http_method': method,
                'http_status_source': status_source,
                'observed_at_utc': datetime.fromtimestamp(instant, timezone.utc).isoformat()}
    # Classify ONLY the explicit response body. Exception strings can include SDK
    # commentary, stale errors, headers or credentials and are never evidence.
    message = error.get('message') if isinstance(error.get('message'), str) else ''
    if status == 429:
        daily = bool(re.search(r'per.?day|daily|\brpd\b', ' '.join((metric or '', quota_id or '', message)), re.I))
        spending_cap = bool(re.search(r'(?:exceeded|reached).{0,60}(?:monthly|spend(?:ing)?).{0,30}(?:cap|limit)|'
                                      r'(?:monthly|spend(?:ing)?).{0,30}(?:cap|limit).{0,30}(?:exceeded|reached)', message, re.I))
        billing = spending_cap or bool(re.search(r'(?:billing(?: account)?).{0,30}(?:disabled|suspended)|'
            r'(?:credits?|balance).{0,30}(?:exhausted|depleted|insufficient)|'
            r'(?:spend(?:ing)?|budget).{0,20}(?:cap|limit).{0,20}(?:exceeded|reached)|'
            r'prepaid.{0,20}(?:insufficient|exhausted)|payment required|'
            r'insufficient.{0,20}(?:credits?|balance)', message, re.I))
        if quota_value == 0:
            return ProviderDiagnostic('project_quota_zero', 'Gemini reports a configured quota of zero for this project and model. Check this model’s access and quota in the project linked to the key.', status, False, **evidence)
        if billing:
            summary = ('Gemini billing account has reached its monthly spending cap. Check AI Studio billing and project credits.' if spending_cap else
                       'Gemini explicitly rejected available credit or the billing account. Check the project’s credit allocation and billing status.')
            return ProviderDiagnostic('account_quota', summary, status, False, **evidence)
        return ProviderDiagnostic('daily_quota' if daily else 'rate_limited',
            'Gemini project daily quota is exhausted; discussion is delayed.' if daily else 'Gemini throttled this project; discussion will resume after its cooldown.',
            status, True, retry if retry is not None else (3600. if daily else 15.), **evidence)
    if status in (502, 503, 504):
        return ProviderDiagnostic('provider_capacity', 'Gemini capacity is temporarily unavailable; discussion will retry.', status, True, retry or 5., **evidence)
    if status in (400, 401, 402, 403, 404):
        return ProviderDiagnostic('provider_configuration', 'Gemini rejected the configured key, model or request. Check the provider setup.', status, False, **evidence)
    return ProviderDiagnostic('unknown_outcome', 'The Gemini response outcome is unknown. This turn will not be sent again automatically.', status, False, outcome_known=False, **evidence)


class ProviderQueue:
    """Shared process-local admission limits, independent of Google's quotas.

    Every dispatch counts, including failed or subsequently cancelled requests.
    Counters use rolling windows and reset when this backend process restarts.
    Admission is claimed only after a concurrency slot becomes available.
    """
    def __init__(self, concurrency=1, clock=time.time, sleep=asyncio.sleep, *, paused=False,
                 requests_per_minute=4, requests_per_day=200, max_pending=8):
        self.clock, self.sleep = clock, sleep
        self.paused = bool(paused)
        self.concurrency = max(1, int(concurrency))
        self.requests_per_minute = max(1, int(requests_per_minute))
        self.requests_per_day = max(1, int(requests_per_day))
        self.max_pending = max(1, int(max_pending))
        self.pacing_mode = 'fast'
        self.min_dispatch_interval_seconds = 60. / self.requests_per_minute
        self._pacing_changed = asyncio.Event()
        self.semaphore = asyncio.Semaphore(self.concurrency)
        self._admission_lock = asyncio.Lock()
        self._minute_dispatches = deque()
        self._day_dispatches = deque()
        self._last_dispatch = None
        self.cooldown_until = 0.
        # waiting retains its original meaning internally: active + pending.
        self.waiting = self.active = self.completed = self.throttled = 0
        self.local_rejected = 0
        self.last_error = self.last_local_error = None

    def pacing(self):
        options = [{'mode': mode, 'label': mode.title(),
                    'requests_per_minute': self.requests_per_minute * fraction,
                    'min_dispatch_interval_seconds': 60. / (self.requests_per_minute * fraction)}
                   for mode, fraction in (('slow', .25), ('steady', .5), ('fast', 1.))]
        selected = next(option for option in options if option['mode'] == self.pacing_mode)
        return {'mode': self.pacing_mode, 'options': options, 'paused': self.paused,
                'effective_requests_per_minute': selected['requests_per_minute'],
                'hard_limit_requests_per_minute': self.requests_per_minute}

    def set_pacing(self, mode):
        if mode not in ('slow', 'steady', 'fast'):
            raise ValueError('Unknown request pace.')
        if mode == self.pacing_mode:
            return
        self.pacing_mode = mode
        self.min_dispatch_interval_seconds = 60. / self.pacing()['effective_requests_per_minute']
        # Each waiter owns the old event, so a change wakes all of them without
        # an event.clear race. In-flight operations and quota history stay intact.
        changed, self._pacing_changed = self._pacing_changed, asyncio.Event()
        changed.set()

    async def _wait_for_pacing(self, delay, changed):
        sleeper = asyncio.create_task(self.sleep(delay))
        updater = asyncio.create_task(changed.wait())
        try:
            await asyncio.wait((sleeper, updater), return_when=asyncio.FIRST_COMPLETED)
            if sleeper.done():
                sleeper.result()
        finally:
            for task in (sleeper, updater):
                if not task.done(): task.cancel()
            await asyncio.gather(sleeper, updater, return_exceptions=True)

    def _prune(self, now):
        while self._minute_dispatches and self._minute_dispatches[0] <= now - 60.:
            self._minute_dispatches.popleft()
        while self._day_dispatches and self._day_dispatches[0] <= now - 86400.:
            self._day_dispatches.popleft()

    def _reject_local(self, category, message, retry_after_seconds=None):
        diagnostic = ProviderDiagnostic(category, message, retryable=False,
                                        retry_after_seconds=retry_after_seconds)
        self.local_rejected += 1
        self.last_local_error = diagnostic.public()
        raise ProviderFailure(diagnostic)

    def _require_daily_allowance(self, now):
        if len(self._day_dispatches) >= self.requests_per_day:
            self._reject_local('local_daily_cap',
                'The local Gemini safety cap for the last 24 hours is reached. No request was sent to Google.',
                max(0., self._day_dispatches[0] + 86400. - now))

    def _wait_condition(self, now):
        candidates = [(max(0., self.cooldown_until - now), 'provider_cooldown')]
        if self._last_dispatch is not None:
            candidates.append((max(0., self._last_dispatch + self.min_dispatch_interval_seconds - now),
                               'local_dispatch_spacing'))
        if len(self._minute_dispatches) >= self.requests_per_minute:
            candidates.append((max(0., self._minute_dispatches[0] + 60. - now), 'local_minute_cap'))
        delay, reason = max(candidates, key=lambda item: item[0])
        return delay, reason if delay > 0 else None

    async def _admit(self):
        while True:
            self.require_enabled()
            # Never hold this lock across sleep or a provider call. A second
            # task must recheck the same shared windows after every wake-up.
            async with self._admission_lock:
                now = self.clock()
                self._prune(now)
                self._require_daily_allowance(now)
                delay, _ = self._wait_condition(now)
                changed = self._pacing_changed
                if delay <= 0:
                    self._minute_dispatches.append(now)
                    self._day_dispatches.append(now)
                    self._last_dispatch = now
                    return
            await self._wait_for_pacing(delay, changed)
            self.require_enabled()

    async def run(self, model, operation, category='agent'):
        self.require_enabled()
        now = self.clock()
        self._prune(now)
        self._require_daily_allowance(now)
        # No await between testing and incrementing: the pending bound is
        # atomic on this event loop, including callers waiting on a semaphore.
        if self.waiting - self.active >= self.max_pending:
            self._reject_local('local_queue_full',
                'The local Gemini waiting queue is full. No request was sent to Google; try again after pending work completes.')
        self.waiting += 1
        try:
            async with self.semaphore:
                await self._admit()
                self.active += 1
                try:
                    result = await operation()
                    self.completed += 1
                    return result
                except asyncio.CancelledError: raise
                except Exception as exc:
                    diagnostic = diagnose_provider_error(exc, self.clock())
                    self.last_error = diagnostic.public()
                    if diagnostic.retryable:
                        self.throttled += 1
                        self.cooldown_until = max(self.cooldown_until, self.clock() + (diagnostic.retry_after_seconds or 5))
                    raise ProviderFailure(diagnostic) from None
                finally: self.active -= 1
        finally: self.waiting -= 1

    def status(self):
        now = self.clock()
        self._prune(now)
        delay, reason = self._wait_condition(now)
        if self.paused:
            reason, delay = 'ai_paused', 0.
        elif len(self._day_dispatches) >= self.requests_per_day:
            reason = 'local_daily_cap'
            delay = max(0., self._day_dispatches[0] + 86400. - now)
        elif not reason and self.active >= self.concurrency:
            reason = 'local_concurrency'
        return {'waiting': max(0, self.waiting - self.active), 'active': self.active,
                'paused': self.paused, 'pause_reason': AI_PAUSE_REASON if self.paused else None,
                'completed': self.completed, 'throttled': self.throttled,
                'retry_after_seconds': max(0, round(self.cooldown_until - now, 2)),
                'last_error': self.last_error,
                'last_local_error': self.last_local_error, 'local_rejected': self.local_rejected,
                'counter_scope': 'process_lifetime',
                'pacing': self.pacing(),
                'local_limits': {'requests_per_minute': self.requests_per_minute,
                    'requests_per_day': self.requests_per_day, 'max_pending': self.max_pending,
                    'min_dispatch_interval_seconds': self.min_dispatch_interval_seconds,
                    'concurrency': self.concurrency},
                'local_usage': {'requests_last_minute': len(self._minute_dispatches),
                    'requests_last_24_hours': len(self._day_dispatches),
                    'requests_remaining_minute': max(0, self.requests_per_minute - len(self._minute_dispatches)),
                    'requests_remaining_day': max(0, self.requests_per_day - len(self._day_dispatches))},
                'wait_reason': reason, 'dispatch_wait_seconds': round(delay, 2)}

    def require_enabled(self):
        if self.paused:
            raise ProviderFailure(ProviderDiagnostic('ai_paused', AI_PAUSE_REASON, retryable=False))

    @staticmethod
    def retry_delay(diagnostic, attempt):
        return max(diagnostic.retry_after_seconds or 0, min(300, 5 * 2 ** max(0, attempt - 1))) + random.uniform(0, 1)
