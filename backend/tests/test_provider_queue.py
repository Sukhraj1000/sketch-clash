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
