"""Exercise the pinned SDK against an in-memory HTTP transport, never Google."""
import httpx
import pytest
from google import genai

from app.gemini_client import create_gemini_client


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [429, 503])
async def test_sdk_admission_sends_one_http_attempt_for_each_transport(monkeypatch, status):
    calls = []

    def fail(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(status, json={'error': {
            'code': status, 'status': 'RESOURCE_EXHAUSTED' if status == 429 else 'UNAVAILABLE',
            'message': 'Synthetic provider failure for transport verification.',
        }})

    transport = httpx.MockTransport(fail)
    original = genai.Client

    def local_client(**kwargs):
        kwargs['http_options']['httpx_client'] = httpx.Client(transport=transport)
        kwargs['http_options']['httpx_async_client'] = httpx.AsyncClient(transport=transport)
        return original(**kwargs)

    monkeypatch.setattr(genai, 'Client', local_client)
    client = create_gemini_client('synthetic-key-never-sent-over-network', timeout_ms=1000)
    assert client.interactions.sdk_configuration.retry_config is None
    assert client.aio.interactions.sdk_configuration.retry_config is None
    try:
        with pytest.raises(Exception):
            client.interactions.create(model='gemini-3.8-flash', input='OK', store=False)
        assert len(calls) == 1
        with pytest.raises(Exception):
            await client.aio.interactions.create(model='gemini-3.8-flash', input='OK', store=False)
        assert len(calls) == 2
        with pytest.raises(Exception):
            client.models.embed_content(model='gemini-embedding-2', contents='test')
        assert len(calls) == 3
        with pytest.raises(Exception):
            await client.aio.models.embed_content(model='gemini-embedding-2', contents='test')
        assert len(calls) == 4
        assert all(method == 'POST' for method, _ in calls)
    finally:
        await client.aio.aclose()
        client.close()
