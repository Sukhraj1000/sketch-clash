"""Real provider failures remain diagnosable without leaking response secrets."""
import asyncio
from types import SimpleNamespace
import pytest
from app.provider_queue import ProviderQueue, ProviderFailure, diagnose_provider_error


class HttpError(Exception):
    def __init__(self, status, body=None, headers=None):
        super().__init__('https://provider.invalid?key=SECRET_QUERY')
        self.status_code = status
        self.body = body or {}
        self.response = SimpleNamespace(headers=headers or {}, status_code=status)


def test_rate_limit_details_are_safe_and_known():
    error = HttpError(429, {'error': {'message': 'limit for project SECRET_PROJECT', 'details': [
        {'retryDelay': '22s'}, {'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_requests_per_minute'}]}]}},
        {'x-request-id': 'req-123', 'authorization': 'SECRET_HEADER'})
    detail = diagnose_provider_error(error)
    assert detail.status_code == 429 and detail.retryable and detail.outcome_known
    assert detail.retry_after_seconds == 22 and detail.request_id == 'req-123'
    assert detail.quota_metric.endswith('per_minute')
    assert 'SECRET' not in str(detail.public())


def test_billing_configuration_and_timeout_have_different_failure_modes():
    billing = diagnose_provider_error(HttpError(429, {'error': {'message': 'Billing credit exhausted'}}))
    auth = diagnose_provider_error(HttpError(403))
    timeout = diagnose_provider_error(TimeoutError())
    assert billing.category == 'account_quota' and not billing.retryable
    assert auth.category == 'provider_configuration' and auth.outcome_known
    assert timeout.category == 'unknown_outcome' and not timeout.outcome_known


def test_retry_after_header_precedes_body_and_daily_quota_is_classified():
    detail = diagnose_provider_error(HttpError(429, {'error': {'message': 'Daily quota exceeded', 'details': [{'retryDelay': '3s'}]}}, {'retry-after': '17'}))
    assert detail.category == 'daily_quota' and detail.retry_after_seconds == 17


@pytest.mark.asyncio
async def test_queue_honours_shared_cooldown_without_hidden_retry():
    now = [100.]
    waits = []
    async def sleep(seconds): waits.append(seconds); now[0] += seconds
    queue = ProviderQueue(clock=lambda: now[0], sleep=sleep)
    calls = []
    async def fail():
        calls.append('failure')
        raise HttpError(429, headers={'retry-after': '12'})
    with pytest.raises(ProviderFailure): await queue.run('model-a', fail, 'recognition')
    async def succeed(): calls.append('success'); return 'response'
    assert await queue.run('model-b', succeed, 'council') == 'response'
    assert calls == ['failure', 'success'] and waits == [12]
    assert queue.status()['active'] == queue.status()['waiting'] == 0


@pytest.mark.asyncio
async def test_queue_cancellation_releases_admission_slot():
    queue = ProviderQueue(concurrency=1)
    entered = asyncio.Event()
    async def block(): entered.set(); await asyncio.Event().wait()
    task = asyncio.create_task(queue.run('model', block))
    await entered.wait(); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert queue.status()['active'] == queue.status()['waiting'] == 0
