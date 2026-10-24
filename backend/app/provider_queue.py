"""Shared Gemini admission and sanitized provider diagnostics.

Credits are not request throughput. This queue honours provider cooldowns without
inventing a daily spending allowance or retrying an ambiguous transport outcome.
"""
from __future__ import annotations
import asyncio
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
    """One local admission queue shared by every Gemini-using service."""
    def __init__(self, concurrency=2, clock=time.time, sleep=asyncio.sleep, *, paused=False):
        self.clock, self.sleep = clock, sleep
        self.paused = bool(paused)
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.cooldown_until = 0.
        self.waiting = self.active = self.completed = self.throttled = 0
        self.last_error = None

    async def run(self, model, operation, category='agent'):
        self.require_enabled()
        self.waiting += 1
        try:
            async with self.semaphore:
                self.require_enabled()
                while self.cooldown_until > self.clock():
                    await self.sleep(self.cooldown_until - self.clock())
                    self.require_enabled()
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
        return {'waiting': max(0, self.waiting - self.active), 'active': self.active,
                'paused': self.paused, 'pause_reason': AI_PAUSE_REASON if self.paused else None,
                'completed': self.completed, 'throttled': self.throttled,
                'retry_after_seconds': max(0, round(self.cooldown_until - self.clock(), 2)),
                'last_error': self.last_error}

    def require_enabled(self):
        if self.paused:
            raise ProviderFailure(ProviderDiagnostic('ai_paused', AI_PAUSE_REASON, retryable=False))

    @staticmethod
    def retry_delay(diagnostic, attempt):
        return max(diagnostic.retry_after_seconds or 0, min(300, 5 * 2 ** max(0, attempt - 1))) + random.uniform(0, 1)
