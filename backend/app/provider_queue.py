"""Shared Gemini admission and sanitized provider diagnostics.

Credits are not request throughput. This queue honours provider cooldowns without
inventing a daily spending allowance or retrying an ambiguous transport outcome.
"""
from __future__ import annotations
import asyncio
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
import random
import json
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
    quota_id: str | None = None
    quota_value: int | None = None
    provider_reason: str | None = None

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
    body = getattr(exc, 'body', None) or getattr(exc, 'response_json', None)
    if isinstance(body, (str, bytes)):
        try: body = json.loads(body)
        except (TypeError, ValueError): body = None
    if not isinstance(body, dict) and response is not None:
        # Interactions uses an HTTPX response; its rich quota details often live
        # only in response.json(), rather than the exception's string body.
        try: body = response.json()
        except (AttributeError, TypeError, ValueError): body = None
    if not isinstance(body, dict): body = {}
    error = body.get('error', body)
    if not isinstance(error, dict): error = {}
    metric = quota_id = quota_value = None
    for detail in error.get('details', []) or []:
        if not isinstance(detail, dict): continue
        delay = detail.get('retryDelay') or detail.get('retry_delay')
        if delay and retry is None:
            try: retry = max(0., float(delay.get('seconds', 0)) + float(delay.get('nanos', 0)) / 1e9) if isinstance(delay, dict) else max(0., float(str(delay).rstrip('s')))
            except (ValueError, TypeError): pass
        for violation in detail.get('violations', []) or []:
            if isinstance(violation, dict):
                candidate_metric = _safe_id(violation.get('quotaMetric') or violation.get('quota_metric'))
                candidate_id = _safe_id(violation.get('quotaId') or violation.get('quota_id'))
                try:
                    value = int(violation.get('quotaValue', violation.get('quota_value')))
                    value = value if 0 <= value <= 10**15 else None
                except (TypeError, ValueError): value = None
                # Prefer an explicitly zero configured quota over other violated
                # metrics. Missing values must never be interpreted as zero.
                if quota_value != 0:
                    metric, quota_id, quota_value = candidate_metric or metric, candidate_id or quota_id, value
    request_id = _safe_id(headers.get('x-request-id') or headers.get('x-goog-request-id') or getattr(exc, 'request_id', None))
    # Used for classification only. Never return or log the provider's raw message.
    message = str(error.get('message', '')) + ' ' + str(exc)
    if status == 429:
        daily = bool(re.search(r'per.?day|daily|\brpd\b', ' '.join((metric or '', quota_id or '', message)), re.I))
        details = {'request_id': request_id, 'quota_metric': metric, 'quota_id': quota_id, 'quota_value': quota_value,
                   'provider_reason': _safe_id(error.get('status') or error.get('code'))}
        # Google's standard throughput error says "check your plan and billing
        # details". That boilerplate is NOT evidence of a billing failure.
        spending_cap = bool(re.search(r'(?:exceeded|reached).{0,60}(?:monthly|spend(?:ing)?).{0,30}(?:cap|limit)|'
                                      r'(?:monthly|spend(?:ing)?).{0,30}(?:cap|limit).{0,30}(?:exceeded|reached)', message, re.I))
        billing = spending_cap or bool(re.search(r'(?:billing(?: account)?).{0,30}(?:disabled|suspended)|'
            r'(?:credits?|balance).{0,30}(?:exhausted|depleted|insufficient)|'
            r'(?:spend(?:ing)?|budget).{0,20}(?:cap|limit).{0,20}(?:exceeded|reached)|'
            r'prepaid.{0,20}(?:insufficient|exhausted)|payment required|'
            r'insufficient.{0,20}(?:credits?|balance)', message, re.I))
        if quota_value == 0:
            return ProviderDiagnostic('project_quota_zero', 'Gemini reports a configured quota of zero for this project and model. Check this model’s access and quota in the project linked to the key.', status, False, **details)
        if billing:
            message = ('Gemini billing account has reached its monthly spending cap. Check AI Studio billing and project credits.' if spending_cap else
                       'Gemini explicitly rejected available credit or the billing account. Check the project’s credit allocation and billing status.')
            return ProviderDiagnostic('account_quota', message, status, False, **details)
        return ProviderDiagnostic('daily_quota' if daily else 'rate_limited',
            'Gemini project daily quota is exhausted; discussion is delayed.' if daily else 'Gemini throttled this project; discussion will resume after its cooldown.',
            status, True, retry if retry is not None else (3600. if daily else 15.), **details)
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
