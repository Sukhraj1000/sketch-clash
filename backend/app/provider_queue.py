"""Shared Gemini admission and sanitized provider diagnostics.

Credits are not request throughput. This queue honours provider cooldowns without
inventing a daily spending allowance or retrying an ambiguous transport outcome.
"""
from __future__ import annotations
import asyncio
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
import random
import re
import time


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

    def public(self):
        return {key: value for key, value in asdict(self).items() if value is not None}


class ProviderFailure(Exception):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


def _safe_id(value):
    text = str(value or '')
    return text[:160] if re.fullmatch(r'[A-Za-z0-9._:/ -]{1,160}', text) else None


def diagnose_provider_error(exc, now=None):
    """Only whitelisted fields leave this function; exception text can contain URLs/keys."""
    if isinstance(exc, ProviderFailure): return exc.diagnostic
    response = getattr(exc, 'response', None)
    status = getattr(exc, 'status_code', None) or getattr(exc, 'code', None) or getattr(response, 'status_code', None)
    try: status = int(status)
    except (ValueError, TypeError): status = None
    if status is None and 'ratelimit' in type(exc).__name__.lower(): status = 429
    headers = getattr(response, 'headers', {}) or getattr(exc, 'headers', {}) or {}
    headers = {str(key).lower(): value for key, value in headers.items()} if hasattr(headers, 'items') else {}
    retry = headers.get('retry-after')
    try: retry = max(0., float(retry))
    except (ValueError, TypeError):
        try: retry = max(0., parsedate_to_datetime(str(retry)).timestamp() - (now or time.time()))
        except (ValueError, TypeError, OverflowError): retry = None
    body = getattr(exc, 'body', None) or getattr(exc, 'response_json', None) or {}
    if not isinstance(body, dict): body = {}
    error = body.get('error', body)
    if not isinstance(error, dict): error = {}
    metric = None
    for detail in error.get('details', []) or []:
        if not isinstance(detail, dict): continue
        delay = detail.get('retryDelay') or detail.get('retry_delay')
        if delay and retry is None:
            try: retry = max(0., float(str(delay).rstrip('s')))
            except (ValueError, TypeError): pass
        for violation in detail.get('violations', []) or []:
            if isinstance(violation, dict): metric = _safe_id(violation.get('quotaMetric') or violation.get('quota_metric')) or metric
    request_id = _safe_id(headers.get('x-request-id') or headers.get('x-goog-request-id') or getattr(exc, 'request_id', None))
    # Used for classification only. Never return or log the provider's raw message.
    message = str(error.get('message', '')) + ' ' + str(exc)
    if status == 429:
        daily = bool(re.search(r'per.?day|daily|\brpd\b', (metric or '') + ' ' + message, re.I))
        billing = bool(re.search(r'billing|spend.?cap|prepaid|payment|credit.*exhaust', message, re.I))
        if billing:
            return ProviderDiagnostic('account_quota', 'Gemini rejected the project allowance. Check credits and billing for this key’s project.', status, False, request_id=request_id, quota_metric=metric)
        return ProviderDiagnostic('daily_quota' if daily else 'rate_limited',
            'Gemini project daily quota is exhausted; discussion is delayed.' if daily else 'Gemini throttled this project; discussion will resume after its cooldown.',
            status, True, retry if retry is not None else (3600. if daily else 15.), request_id, metric)
    if status in (502, 503, 504):
        return ProviderDiagnostic('provider_capacity', 'Gemini capacity is temporarily unavailable; discussion will retry.', status, True, retry or 5., request_id)
    if status in (400, 401, 402, 403, 404):
        return ProviderDiagnostic('provider_configuration', 'Gemini rejected the configured key, model or request. Check the provider setup.', status, False, request_id=request_id)
    return ProviderDiagnostic('unknown_outcome', 'The Gemini response outcome is unknown. This turn will not be sent again automatically.', status, False, request_id=request_id, outcome_known=False)


class ProviderQueue:
    """One local admission queue shared by every Gemini-using service."""
    def __init__(self, concurrency=2, clock=time.time, sleep=asyncio.sleep):
        self.clock, self.sleep = clock, sleep
        self.semaphore = asyncio.Semaphore(max(1, concurrency))
        self.cooldown_until = 0.
        self.waiting = self.active = self.completed = self.throttled = 0
        self.last_error = None

    async def run(self, model, operation, category='agent'):
        self.waiting += 1
        try:
            async with self.semaphore:
                while self.cooldown_until > self.clock():
                    await self.sleep(self.cooldown_until - self.clock())
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
                'completed': self.completed, 'throttled': self.throttled,
                'retry_after_seconds': max(0, round(self.cooldown_until - self.clock(), 2)),
                'last_error': self.last_error}

    @staticmethod
    def retry_delay(diagnostic, attempt):
        return max(diagnostic.retry_after_seconds or 0, min(300, 5 * 2 ** max(0, attempt - 1))) + random.uniform(0, 1)
