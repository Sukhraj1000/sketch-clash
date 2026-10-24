import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

from google.genai._gaos.types.interactions import Interaction
import pytest

from backend.app.retailer_lookup import lookup_retailer_prices


URL = 'https://www.ikea.com/gb/en/p/faergklar-mug-matt-green-40478189/'


def entry():
    return {'category': 'mug', 'scope': 'Plain ceramic mug', 'listings': [{
        'item_id': 'ikea-40478189', 'title': 'FÄRGKLAR Mug, matt green, 37 cl',
        'retailer': 'IKEA UK', 'url': URL, 'currency': 'GBP', 'condition': 'New',
        'amount_gbp': 999.99, 'price_evidence': 'old starter price £999.99',
    }]}


def row(**changes):
    return {'url': URL, 'amount_gbp': 2, 'currency': 'GBP', 'unit_quantity': 1,
            'price_kind': 'current_single_item', 'price_evidence': 'FÄRGKLAR Mug £2', **changes}


def response(rows=None, *, retrieval_status='success', retrieved_url=URL, status='completed', is_error=False):
    # Use the installed official SDK's current steps schema, not a guessed legacy
    # url_context_metadata or candidate format.
    return Interaction.model_validate({
        'status': status,
        'steps': [
            {'type': 'url_context_call', 'id': 'fetch-1', 'arguments': {'urls': [URL]}},
            {'type': 'url_context_result', 'call_id': 'fetch-1', 'is_error': is_error,
             'result': [{'url': retrieved_url, 'status': retrieval_status}]},
            {'type': 'thought', 'signature': 'private-test-signature',
             'summary': [{'type': 'text', 'text': 'private reasoning'}]},
            {'type': 'model_output', 'content': [{'type': 'text',
             'text': json.dumps({'prices': [row()] if rows is None else rows})}]},
        ],
    })


class Client:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else response()
        self.error = error
        self.calls = []
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class Queue:
    def __init__(self):
        self.calls = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return await kwargs['operation']()


@pytest.mark.asyncio
async def test_extracts_only_current_permitted_url_with_official_schema_and_foreground_queue():
    client, queue = Client(), Queue()
    original = entry()
    frozen = deepcopy(original)
    got = await lookup_retailer_prices(original, client, queue)
    assert len(got) == 1
    assert got[0]['amount_gbp'] == 2
    assert got[0]['url'] == URL
    assert got[0]['item_id'] == original['listings'][0]['item_id']
    assert got[0]['title'] == original['listings'][0]['title']
    assert got[0]['retailer'] == 'IKEA UK'
    assert got[0]['retrieval_status'] == 'success'
    assert got[0]['retrieval_method'] == 'gemini_url_context'
    assert got[0]['checked_at'].endswith('+00:00')
    assert original == frozen
    assert 'private reasoning' not in json.dumps(got)
    assert 'signature' not in json.dumps(got)
    assert queue.calls[0]['category'] == 'pricing'
    assert queue.calls[0]['priority'] == 'foreground'
    call = client.calls[0]
    assert call['model'] == 'gemini-3.8-flash'
    assert call['tools'] == [{'type': 'url_context'}]
    assert call['store'] is False
    assert call['response_format']['mime_type'] == 'application/json'
    assert call['generation_config']['thinking_level'] == 'low'
    assert call['timeout'] == 8
    assert '999.99' not in call['input']
    assert 'temperature' not in call['generation_config']


@pytest.mark.parametrize('changes', [
    {'currency': 'USD'}, {'amount_gbp': None}, {'amount_gbp': True}, {'amount_gbp': 0},
    {'amount_gbp': float('nan')}, {'amount_gbp': float('inf')}, {'amount_gbp': 2.001},
    {'amount_gbp': 1_000_001}, {'amount_gbp': '2'}, {'unit_quantity': 2}, {'unit_quantity': True},
    {'unit_quantity': 1.0},
    {'price_kind': 'unknown'}, {'price_evidence': 'There are 2 mugs'},
    {'price_evidence': 'Mug £20'}, {'price_evidence': 'Was £5, now £2'},
    {'price_evidence': 'Mug £2.001'}, {'price_evidence': 'Mug £2,00'},
    {'price_evidence': 'x ' * 21 + '£2'},
    {'url': 'https://www.ikea.com/gb/en/p/a-different-product/'},
    {'url': URL + '?tracking=1'},
])
@pytest.mark.asyncio
async def test_unverifiable_or_non_single_product_values_are_neutral(changes):
    assert await lookup_retailer_prices(entry(), Client(response([row(**changes)]))) == []


@pytest.mark.parametrize('metadata', [
    {'retrieval_status': 'error'}, {'retrieval_status': 'unsafe'}, {'retrieval_status': 'paywall'},
    {'retrieval_status': None}, {'retrieved_url': URL + 'other'}, {'status': 'incomplete'}, {'is_error': True},
])
@pytest.mark.asyncio
async def test_provider_retrieval_success_is_required(metadata):
    assert await lookup_retailer_prices(entry(), Client(response(**metadata))) == []


@pytest.mark.asyncio
async def test_no_retrieval_steps_duplicate_rows_and_invalid_json_are_neutral():
    no_steps = response()
    no_steps.steps = []
    assert await lookup_retailer_prices(entry(), Client(no_steps)) == []
    assert await lookup_retailer_prices(entry(), Client(response([row(), row()]))) == []
    malformed = response()
    malformed.steps[-1].content[0].text = 'invalid JSON private-output'
    malformed.output_text = 'invalid JSON private-output'
    assert await lookup_retailer_prices(entry(), Client(malformed)) == []


@pytest.mark.parametrize('url', [
    'http://www.ikea.com/gb/en/p/mug/', 'https://127.0.0.1/private',
    'https://www.ikea.com@evil.test/p/mug/', 'https://www.ikea.com.evil.test/p/mug/',
    'https://www.ikea.com:443/p/mug/', 'https://www.ikea.com/gb/en/p/mug/#fragment',
    'https://www.ikea.com/', 'not a URL',
])
@pytest.mark.asyncio
async def test_unapproved_urls_never_dispatch(url):
    product = entry()
    product['listings'][0]['url'] = url
    client = Client()
    assert await lookup_retailer_prices(product, client) == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_wait_timeout_includes_admission_and_does_not_retry_or_send_late():
    client = Client()
    cancelled = False

    class WaitingQueue:
        async def run(self, **kwargs):
            nonlocal cancelled
            try:
                await asyncio.sleep(1)
                return await kwargs['operation']()
            finally:
                cancelled = True

    assert await lookup_retailer_prices(entry(), client, WaitingQueue(), timeout_seconds=0.01) == []
    assert cancelled
    assert client.calls == []


@pytest.mark.asyncio
async def test_provider_failure_is_neutral_and_never_logs_raw_response(capsys):
    client = Client(error=RuntimeError('private-provider-message-and-key'))
    assert await lookup_retailer_prices(entry(), client) == []
    assert len(client.calls) == 1
    assert capsys.readouterr() == ('', '')


@pytest.mark.asyncio
async def test_cancellation_propagates_and_timeout_cannot_exceed_eight_seconds():
    client = Client(error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await lookup_retailer_prices(entry(), client)
    client = Client()
    assert await lookup_retailer_prices(entry(), client, timeout_seconds=600)
    assert client.calls[0]['timeout'] == 8


@pytest.mark.asyncio
async def test_partial_retrieval_keeps_only_evidenced_product_and_preserves_source_identity():
    product = entry()
    second = deepcopy(product['listings'][0])
    second.update(item_id='ikea-other', url='https://www.ikea.com/gb/en/p/other-mug/')
    product['listings'].append(second)
    got = await lookup_retailer_prices(product, Client(response([row(), row(url=second['url'])])))
    assert [listing['url'] for listing in got] == [URL]


@pytest.mark.asyncio
async def test_gbp_evidence_can_include_pence_and_thousands_separator():
    got = await lookup_retailer_prices(entry(), Client(response([
        row(amount_gbp=1234.5, price_evidence='Mug GBP 1,234.50'),
    ])))
    assert got[0]['amount_gbp'] == 1234.5
