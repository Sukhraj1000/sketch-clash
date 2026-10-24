from copy import deepcopy
import httpx
import pytest

from backend.app.config import Settings
from backend.app.market_prices import MarketPrices, comparable_quote, combat_price, query_for
from backend.app.camera_combat import simulate_capture_battle
from backend.tests.test_camera_combat import object_fighter


def listing(n, amount='12.00', **values):
    return {'itemId': str(n), 'title': 'Ceramic coffee mug', 'itemWebUrl': f'https://www.ebay.co.uk/itm/{n}',
            'price': {'value': amount, 'currency': 'GBP'}, 'condition': 'New', 'buyingOptions': ['FIXED_PRICE'], **values}


def quote(amounts=('10', '12', '14')):
    return comparable_quote({'itemSummaries': [listing(i, amount) for i, amount in enumerate(amounts)]}, 'mug', ('mug',))


def test_requires_three_real_gbp_fixed_price_single_object_matches():
    payload = {'itemSummaries': [listing(1), listing(1), listing(2, title='Replacement lid for mug'),
        listing(3, price={'value': '50', 'currency': 'USD'}), listing(4, buyingOptions=['AUCTION']),
        listing(5, itemWebUrl='https://example.com/itm/5'), listing(6, title='Set of 6 mugs'),
        listing(7, amount='NaN'), listing(8, title='Mug holder stand only')]}
    assert comparable_quote(payload, 'mug', ('mug',))['amount_gbp'] is None
    got = quote()
    assert got['amount_gbp'] == 12
    assert got['confidence'] == 'category_comparable'
    assert combat_price(got) == got
    assert quote(('1', '12', '400'))['amount_gbp'] is None
    assert query_for({'observed_object': {'label': 'cat'}}) is None
    assert query_for({'observed_object': {'label': 'picture of a mug'}}) is None
    for label in ('phone case', 'water bottle lid', 'phone charging cable'):
        assert query_for({'observed_object': {'label': label}}) is None
    accessories = {'itemSummaries': [listing(i, title=t) for i, t in enumerate(['Phone Screen Protector', 'Phone Charging Cable', 'Phone Case'])]}
    assert comparable_quote(accessories, 'phone', ('phone',))['amount_gbp'] is None


@pytest.mark.parametrize('payload', [None, [], {'itemSummaries': None}, {'itemSummaries': [listing(1, price='bad')]},
    {'itemSummaries': [listing(i, amount='0.004') for i in range(3)]}])
def test_malformed_provider_data_is_neutral(payload):
    assert comparable_quote(payload, 'mug', ('mug',))['amount_gbp'] is None


@pytest.mark.asyncio
async def test_official_headers_cache_and_failure_do_not_expose_secrets():
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path.endswith('/token'):
            return httpx.Response(200, json={'access_token': 'private-test-token', 'expires_in': 7200})
        assert request.headers['x-ebay-c-marketplace-id'] == 'EBAY_GB'
        assert request.url.params['q'] == 'mug'
        return httpx.Response(200, json={'itemSummaries': [listing(i) for i in range(3)]})
    settings = Settings(ebay_client_id='test-id', ebay_client_secret='test-secret')
    provider = MarketPrices(settings, transport=httpx.MockTransport(handler))
    fighter = object_fighter(label='ceramic mug')
    got = await provider.quote(fighter)
    assert got['amount_gbp'] == 12
    assert await provider.quote(fighter) == got
    assert len(requests) == 2
    assert 'private-test-token' not in str(got) and 'test-secret' not in repr(settings)
    failing = MarketPrices(settings, transport=httpx.MockTransport(lambda _: httpx.Response(429, json={'secret': 'sensitive'})))
    failed = await failing.quote(fighter)
    assert failed['amount_gbp'] is None and 'sensitive' not in str(failed)
    assert (await MarketPrices(Settings()).quote(fighter))['status'] == 'unconfigured'


def test_combat_freezes_comparables_and_stays_neutral_if_either_missing():
    items = [object_fighter(label='mug'), object_fighter(slot=1, label='mug')]
    items[0]['market_price'] = quote(('10', '12', '14'))
    items[1]['market_price'] = quote(('1000', '1200', '1400'))
    battle = simulate_capture_battle(items, [{}, {}], 19, 'quick')
    assert battle['price_policy']['kind'] == 'sourced_comparables'
    assert all(0 <= e['receipt']['price_percent'] <= 1 for e in battle['events'])
    assert 'illustrative' not in battle['explanation']['price_note']
    frozen = deepcopy(battle)
    items[0]['market_price']['listings'].clear()
    assert battle == frozen
    neutral = simulate_capture_battle(items, [{}, {}], 19, 'quick')
    assert all(e['receipt']['price_percent'] == 0 for e in neutral['events'])
    forged = quote()
    forged['amount_gbp'] = 9999
    assert combat_price(forged)['amount_gbp'] is None


def test_island_price_coverage_never_mixes_sourced_comparables_with_user_estimates():
    from backend.app.colonies import ColoniesStore
    metrics = ColoniesStore._metrics(None, [{'market_price': quote(), 'estimated_value_gbp': 50}, {}],
        {'agents': [], 'projects': [], 'resources': {}})
    assert metrics['comparable_total_gbp'] == 12 and metrics['comparable_residents'] == 1
    assert metrics['estimated_total_gbp'] == 50 and metrics['unknown_value_residents'] == 1
    assert metrics['market_value'] is None  # Neither record is an appraisal of the actual item.


@pytest.mark.asyncio
async def test_recognition_cannot_inject_price_and_style_preserves_server_quote():
    from backend.tests.test_feedback_pipeline import ControlledRecognizer, prepare, correction
    from app.config import Settings
    from app.repository import MemoryRepository
    from app.service import BattleService
    settings = Settings(repository='memory')
    repo = MemoryRepository(settings)
    service = BattleService(settings, repo, ControlledRecognizer())
    calls = []
    class Prices:
        async def quote(self, item):
            calls.append(item['object_type'])
            return quote()
    service.market_prices = Prices()
    battle, original = await prepare(repo, service)
    changed = await service.correct_capture(battle['id'], original['capture_id'], correction(original))
    assert len(calls) == 1
    assert changed['pending_fighter']['market_price'] == original['pending_fighter']['market_price']
