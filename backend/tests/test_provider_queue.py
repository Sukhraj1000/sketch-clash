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
    assert calls == ['failure', 'success'] and waits == [15]
    assert queue.status()['local_usage']['requests_last_24_hours'] == 2
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
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1


def test_generic_google_429_billing_boilerplate_is_not_account_failure():
    error=HttpError(429, {'error': {'code':429, 'status':'RESOURCE_EXHAUSTED',
        'message':'You exceeded your current quota, please check your plan and billing details. Retry in 23s.',
        'details':[{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'23s'}]}})
    diagnostic=diagnose_provider_error(error)
    assert diagnostic.category=='rate_limited' and diagnostic.retryable
    assert diagnostic.retry_after_seconds==23 and diagnostic.provider_reason=='RESOURCE_EXHAUSTED'


def test_interactions_http_response_json_retains_quota_fields_without_raw_body():
    class RateLimitError(Exception):
        status_code=429
        body='not parsed here'
        response=SimpleNamespace(status_code=429,headers={},json=lambda:{'error':{
            'message':'You exceeded your current quota; check your plan and billing details. Secret project ID SECRET_PROJECT',
            'details':[{'violations':[{'quotaMetric':'generativelanguage.googleapis.com/generate_content_free_tier_input_token_count',
                'quotaId':'GenerateContentInputTokensPerModelPerMinute-FreeTier','quotaValue':'250000'}]},
                {'retryDelay':{'seconds':31,'nanos':500000000}}]}})
    diagnostic=diagnose_provider_error(RateLimitError('https://api.invalid/?key=SECRET_KEY'))
    assert diagnostic.category=='rate_limited' and diagnostic.retryable
    assert diagnostic.quota_value==250000 and diagnostic.quota_id.endswith('FreeTier')
    assert diagnostic.retry_after_seconds==31.5
    assert 'SECRET' not in str(diagnostic.public())


def test_only_explicit_zero_quota_is_configuration_problem():
    absent=diagnose_provider_error(HttpError(429, {'error':{'details':[{'violations':[{'quotaMetric':'requests_per_minute'}]}]}}))
    assert absent.retryable and absent.quota_value is None
    zero=diagnose_provider_error(HttpError(429, {'error':{'details':[{'violations':[{'quotaMetric':'requests_per_minute','quotaValue':'0'}]}]}}))
    assert zero.category=='project_quota_zero' and zero.quota_value==0 and not zero.retryable


def test_observed_monthly_spending_cap_is_precise_nonretryable_account_failure():
    class RateLimitError(Exception):
        status_code=429
        response=SimpleNamespace(headers={},json=lambda:{'message':
            'Your billing account has exceeded its monthly spending cap. Please go to AI Studio at https://ai.studio/billing to manage your billing. Learn more at https://ai.google.dev/gemini-api/docs/rate-limits#tier-spend-caps.',
            'code':'too_many_requests'})
    diagnostic=diagnose_provider_error(RateLimitError())
    assert diagnostic.category=='account_quota' and not diagnostic.retryable
    assert diagnostic.message=='Gemini billing account has reached its monthly spending cap. Check AI Studio billing and project credits.'
    assert diagnostic.provider_reason=='too_many_requests'


def test_response_provenance_preserves_public_fields_and_redacts_credentials():
    key='AIza'+'A'*35
    error=HttpError(429, {'error': {'status':'RESOURCE_EXHAUSTED',
        'message':f'Quota exceeded. API key: {key} Password=SECRET_PASSWORD. See https://SECRET_USER:SECRET_PASS@api.example/v1beta/interactions?key=SECRET_QUERY#token=SECRET_FRAGMENT Bearer SECRET_BEARER',
        'details':[{'@type':'type.googleapis.com/google.rpc.QuotaFailure',
            'metadata':{'authorization':'SECRET_METADATA'},
            'violations':[{'quotaMetric':'requests_per_minute','quotaId':'RequestsPerMinute',
                'quotaValue':'20','description':'SECRET_DESCRIPTION',
                'quotaDimensions':{'model':'gemini-3.8-flash','location':'global','project':'SECRET_PROJECT'}}]},
            {'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'18s'}]}},
        {'authorization':'SECRET_HEADER','x-request-id':'public-request-123'})
    error.response.request=SimpleNamespace(method='POST',url='https://SECRET_USER:SECRET_PASS@api.example/v1beta/interactions?key=SECRET_QUERY#secret')
    diagnostic=diagnose_provider_error(error,now=1792844042.746)
    assert diagnostic.observed_at_utc=='2026-10-24T12:14:02.746000+00:00'
    assert diagnostic.http_endpoint=='https://api.example/v1beta/interactions'
    assert diagnostic.http_method=='POST' and diagnostic.http_status_source=='http_response'
    assert diagnostic.provider_body_source=='sdk.body'
    assert diagnostic.provider_message.startswith('Quota exceeded.')
    assert diagnostic.message != diagnostic.provider_message
    assert diagnostic.provider_error_details==[
        {'type':'type.googleapis.com/google.rpc.QuotaFailure','violations':[{
            'quota_metric':'requests_per_minute','quota_id':'RequestsPerMinute','quota_value':20,
            'model':'gemini-3.8-flash','location':'global'}]},
        {'type':'type.googleapis.com/google.rpc.RetryInfo','retry_delay_seconds':18}]
    assert 'SECRET' not in str(diagnostic.public()) and key not in str(diagnostic.public())


def test_billing_classification_cannot_be_inferred_from_exception_string():
    class RateLimitError(Exception):
        status_code=429
        response=SimpleNamespace(status_code=429,headers={},json=lambda:{'message':
            'You exceeded the request limit. Please check your plan and billing details.'})
    diagnostic=diagnose_provider_error(RateLimitError('Your billing account has exceeded its monthly spending cap. SECRET_WRAPPER'))
    assert diagnostic.category=='rate_limited' and diagnostic.retryable
    assert 'monthly' not in diagnostic.provider_message and 'SECRET_WRAPPER' not in str(diagnostic.public())
    assert diagnostic.provider_body_source=='response.json'


def test_missing_response_body_is_explicitly_missing_and_captured_fields_are_bounded():
    class RateLimitError(Exception): status_code=429
    missing=diagnose_provider_error(RateLimitError('Monthly spending cap exceeded'),now=0)
    assert missing.category=='rate_limited' and missing.provider_message is None
    assert missing.provider_error_details is None and missing.http_endpoint is None
    assert missing.observed_at_utc=='1970-01-01T00:00:00+00:00'
    large=diagnose_provider_error(HttpError(429, {'message':'x'*4000,'details':[
        {'violations':[{'quotaMetric':'requests_per_minute','quotaValue':'2'} for _ in range(30)]} for _ in range(30)]}))
    assert len(large.provider_message)==1200 and len(large.provider_error_details)==8
    assert all(len(detail['violations'])==8 for detail in large.provider_error_details)


class ManualClock:
    """Advance queue time without waiting on a wall clock or calling Google."""
    def __init__(self):
        self.now = 100.
        self.sleepers = []

    def __call__(self): return self.now

    async def sleep(self, seconds):
        future = asyncio.get_running_loop().create_future()
        self.sleepers.append((self.now + seconds, future))
        await future

    async def advance(self, seconds):
        self.now += seconds
        for wake_at, future in self.sleepers:
            if wake_at <= self.now and not future.done(): future.set_result(None)
        await drain_tasks()


async def drain_tasks():
    for _ in range(5): await asyncio.sleep(0)


def test_default_caps_are_explicitly_local_and_restart_scoped():
    status = ProviderQueue().status()
    assert status['local_limits'] == {
        'requests_per_minute': 4, 'requests_per_day': 200, 'max_pending': 8,
        'min_dispatch_interval_seconds': 15., 'concurrency': 1}
    assert status['counter_scope'] == 'process_lifetime'
    assert status['last_error'] is status['last_local_error'] is None
    assert status['local_usage']['requests_remaining_day'] == 200


@pytest.mark.asyncio
async def test_mixed_models_and_services_share_spacing_and_strict_rolling_window():
    now = [100.]
    dispatched = []
    async def sleep(seconds):
        now[0] += seconds
        await asyncio.sleep(0)
    queue = ProviderQueue(clock=lambda: now[0], sleep=sleep)
    async def call(): dispatched.append(now[0]); return 'ok'
    for index in range(16):
        assert await queue.run('flash' if index % 2 else 'argon', call,
                               'recognition' if index % 3 else 'agent') == 'ok'
    assert dispatched == [100. + 15. * index for index in range(16)]
    for instant in dispatched:
        assert sum(instant - 60. < sent <= instant for sent in dispatched) <= 4
    assert queue.status()['local_usage'] == {
        'requests_last_minute': 4, 'requests_last_24_hours': 16,
        'requests_remaining_minute': 0, 'requests_remaining_day': 184}
    now[0] = dispatched[-1] + 60.
    assert queue.status()['local_usage']['requests_last_minute'] == 0
    assert queue.status()['wait_reason'] is None


@pytest.mark.asyncio
async def test_concurrent_calls_are_spaced_without_holding_admission_lock_during_network():
    clock = ManualClock()
    queue = ProviderQueue(concurrency=2, clock=clock, sleep=clock.sleep)
    releases = [asyncio.Event(), asyncio.Event(), asyncio.Event()]
    calls = []
    async def call(index):
        calls.append((index, clock.now))
        await releases[index].wait()
        return index
    tasks = [asyncio.create_task(queue.run(str(index), lambda i=index: call(i))) for index in range(3)]
    await drain_tasks()
    assert calls == [(0, 100.)]
    assert queue.status()['active'] == 1 and queue.status()['waiting'] == 2
    await clock.advance(15.)
    assert calls == [(0, 100.), (1, 115.)]
    assert queue.status()['active'] == 2
    # The third task has no reservation while it waits for a semaphore slot.
    assert queue.status()['local_usage']['requests_last_24_hours'] == 2
    releases[0].set()
    await drain_tasks()
    await clock.advance(15.)
    assert calls == [(0, 100.), (1, 115.), (2, 130.)]
    releases[1].set(); releases[2].set()
    assert await asyncio.gather(*tasks) == [0, 1, 2]
    assert queue.status()['active'] == queue.status()['waiting'] == 0


@pytest.mark.asyncio
async def test_queue_bound_rejects_without_dispatch_and_cancelled_waiter_frees_space():
    clock = ManualClock()
    queue = ProviderQueue(clock=clock, sleep=clock.sleep, max_pending=1)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def block(): calls.append('active'); entered.set(); await release.wait()
    async def forbidden(): calls.append('unexpected')
    active = asyncio.create_task(queue.run('first', block))
    await entered.wait()
    waiting = asyncio.create_task(queue.run('second', forbidden))
    await drain_tasks()
    with pytest.raises(ProviderFailure) as exc: await queue.run('third', forbidden)
    assert exc.value.diagnostic.category == 'local_queue_full'
    assert not exc.value.diagnostic.retryable and exc.value.diagnostic.status_code is None
    assert queue.status()['last_error'] is None
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError): await waiting
    assert queue.status()['waiting'] == 0
    replacement = asyncio.create_task(queue.run('replacement', forbidden))
    await drain_tasks()
    replacement.cancel()
    with pytest.raises(asyncio.CancelledError): await replacement
    release.set(); await active
    assert calls == ['active']
    assert queue.status()['active'] == queue.status()['waiting'] == 0
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1


@pytest.mark.asyncio
async def test_cancellation_during_admission_sleep_never_spends_a_dispatch():
    clock = ManualClock()
    queue = ProviderQueue(clock=clock, sleep=clock.sleep)
    calls = []
    async def call(): calls.append(clock.now)
    await queue.run('first', call)
    cancelled = asyncio.create_task(queue.run('cancelled', call))
    await drain_tasks()
    assert queue.status()['wait_reason'] == 'local_dispatch_spacing'
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError): await cancelled
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    replacement = asyncio.create_task(queue.run('replacement', call))
    await drain_tasks(); await clock.advance(15.)
    await replacement
    assert calls == [100., 115.]
    assert queue.status()['active'] == queue.status()['waiting'] == 0


@pytest.mark.asyncio
async def test_pause_after_admission_sleep_blocks_dispatch_and_resume_still_works():
    clock = ManualClock()
    queue = ProviderQueue(clock=clock, sleep=clock.sleep)
    calls = []
    async def call(): calls.append(clock.now)
    await queue.run('first', call)
    pending = asyncio.create_task(queue.run('second', call))
    await drain_tasks()
    queue.paused = True
    await clock.advance(15.)
    with pytest.raises(ProviderFailure) as exc: await pending
    assert exc.value.diagnostic.category == 'ai_paused'
    assert queue.status()['local_usage']['requests_last_24_hours'] == 1
    assert queue.status()['active'] == queue.status()['waiting'] == 0
    queue.paused = False
    await queue.run('resumed', call)
    assert calls == [100., 115.]


@pytest.mark.asyncio
async def test_failures_count_toward_daily_cap_and_exact_rolling_boundary_reopens():
    now = [100.]
    calls, waits = [], []
    async def sleep(seconds): waits.append(seconds); now[0] += seconds
    queue = ProviderQueue(clock=lambda: now[0], sleep=sleep, requests_per_day=2)
    async def fail(): calls.append('failure'); raise HttpError(403)
    async def succeed(): calls.append('success'); return 'ok'
    with pytest.raises(ProviderFailure): await queue.run('first', fail)
    await queue.run('second', succeed)
    original_provider_error = queue.status()['last_error']
    with pytest.raises(ProviderFailure) as exc: await queue.run('third', succeed)
    assert exc.value.diagnostic.category == 'local_daily_cap'
    assert not exc.value.diagnostic.retryable and exc.value.diagnostic.status_code is None
    assert calls == ['failure', 'success'] and waits == [15.]
    assert queue.status()['last_error'] == original_provider_error
    assert queue.status()['wait_reason'] == 'local_daily_cap'
    assert queue.status()['local_usage']['requests_remaining_day'] == 0
    assert queue.status()['active'] == queue.status()['waiting'] == 0
    now[0] = 100. + 86400.
    assert await queue.run('next-day', succeed) == 'ok'
    assert queue.status()['local_usage']['requests_last_24_hours'] == 2


@pytest.mark.asyncio
async def test_daily_cap_rejects_immediately_even_while_all_slots_are_busy():
    clock = ManualClock()
    queue = ProviderQueue(clock=clock, sleep=clock.sleep, requests_per_day=1)
    started, release = asyncio.Event(), asyncio.Event()
    async def block(): started.set(); await release.wait()
    async def forbidden(): raise AssertionError('must never send')
    active = asyncio.create_task(queue.run('first', block))
    await started.wait()
    with pytest.raises(ProviderFailure) as exc: await queue.run('second', forbidden)
    assert exc.value.diagnostic.category == 'local_daily_cap'
    assert queue.status()['waiting'] == 0 and not clock.sleepers
    release.set(); await active


@pytest.mark.asyncio
async def test_provider_cooldown_can_exceed_local_spacing_without_automatic_retries():
    now = [100.]
    waits, calls = [], []
    async def sleep(seconds): waits.append(seconds); now[0] += seconds
    queue = ProviderQueue(clock=lambda: now[0], sleep=sleep)
    async def fail(): calls.append('failed'); raise HttpError(429, headers={'retry-after': '45'})
    async def succeed(): calls.append('ok')
    with pytest.raises(ProviderFailure): await queue.run('first', fail)
    assert queue.status()['wait_reason'] == 'provider_cooldown'
    await queue.run('second', succeed)
    assert waits == [45.] and calls == ['failed', 'ok']
    assert queue.status()['throttled'] == 1


def queue_with_advancing_clock(clock, advance):
    """Planner fixtures share one logical clock for admission and world time."""
    async def sleep(seconds):
        advance(seconds)
        await asyncio.sleep(0)
    return ProviderQueue(clock=clock, sleep=sleep)
