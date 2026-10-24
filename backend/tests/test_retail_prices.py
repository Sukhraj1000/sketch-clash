"""Price references must fail neutral, stay scoped and freeze with the battle."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from backend.app.camera_combat import simulate_capture_battle
from backend.app.config import Settings
from backend.app.market_prices import combat_price
from backend.app.repository import MemoryRepository
from backend.app.retail_prices import RetailPrices
from backend.app.retail_quotes import catalogue, category_for, make_quote, utc, valid_retail_quote
from backend.tests.test_camera_combat import object_fighter


class Clock:
    def __init__(self):
        self.now = utc(catalogue()['checked_at']) + timedelta(seconds=10)

    def __call__(self):
        return self.now.isoformat()

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def setup(*, configured=False, paused=False):
    clock = Clock()
    settings = Settings(repository='memory', ai_paused=paused, gemini_api_key='fixture-key' if configured else '')
    repo = MemoryRepository(settings, clock)
    recognizer = SimpleNamespace(client=object() if configured else None, provider_queue=object())
    prices = RetailPrices(settings, repo, recognizer)
    return prices, repo, clock


def refreshed(entry, clock):
    listings = deepcopy(entry['listings'])
    for listing in listings:
        listing.update(checked_at=clock(), retrieval_status='success')
    return listings


@pytest.mark.asyncio
async def test_seeded_starters_use_durable_cache_and_restart_never_renews_age():
    prices, repo, clock = setup()
    prices.initialize()
    for category, amount in [('mug', 2), ('water bottle', 3), ('notebook', 2.89), ('ruler', 1.49), ('scissors', 7.49)]:
        quote = await prices.quote(object_fighter(label=category))
        assert quote['amount_gbp'] == amount and valid_retail_quote(quote)
        assert quote['cache']['hit'] is True
        assert quote['cache']['persistence'] == 'development_memory'
        assert utc(quote['cache']['expires_at']) == utc(catalogue()['checked_at']) + timedelta(days=1)
        assert quote['cache']['snapshot_id']
    unknown = await prices.quote(object_fighter(label='unknown object'))
    assert combat_price(unknown)['policy_version'] == 'retail-reference-prices-1'
    original = prices.cache.get('mug')
    clock.advance(3600)
    restarted = RetailPrices(prices.settings, repo, prices.recognizer)
    restarted.initialize()
    assert restarted.cache.get('mug') == original
    clock.advance(86400)
    restarted.initialize()
    assert restarted.cache.get('mug') is None
    quote = await restarted.quote(object_fighter(label='mug'))
    assert quote['amount_gbp'] is None and quote['status'] == 'refresh_unavailable'


@pytest.mark.parametrize('label,features', [
    ('cat', []), ('fire', []), ('mug-shaped toy', []), ('toy mug', []), ('mug holder', []),
    ('gold mug', []), ('plastic mug', []), ('steel mug', []), ('mug', ['glass body']),
    ('mug', ['wooden body']), ('water bottle', ['insulated body']), ('wine bottle', []),
    ('bottle', []), ('disposable water bottle', []), ('Apple notebook', []), ('notebook', ['keyboard and screen']),
    ('leather notebook', []), ('metal ruler', []), ('ruler', ['wooden body']),
    ('kitchen scissors', []), ('child scissors', []), ('scissors', ['heavy duty blades']),
    ('water bottle', ['2 litre reusable plastic bottle']), ('ruler', ['50 cm markings']),
    ('A3 notebook', []), ('mug', ['gold, premium collectible design']), ('scissors', ['12cm blades']),
])
@pytest.mark.asyncio
async def test_unsupported_objects_cannot_borrow_generic_starter_price(label, features):
    prices, repo, _ = setup(configured=True)
    quote = await prices.quote(object_fighter(features, label=label))
    assert quote['amount_gbp'] is None
    assert repo.read(lambda tx: tx.find('priceCache', {})) == []


@pytest.mark.asyncio
async def test_expired_reference_refresh_calls_gemini_once_then_uses_saved_snapshot(monkeypatch):
    prices, repo, clock = setup(configured=True)
    prices.initialize()
    old = prices.cache.get('mug')
    clock.advance(86400)
    calls = []
    async def lookup(entry, client, **kwargs):
        calls.append(kwargs)
        return refreshed(entry, clock)
    monkeypatch.setattr('backend.app.retailer_lookup.lookup_retailer_prices', lookup)
    new = await prices.quote(object_fighter(label='mug'))
    assert new['source'] == 'retailer_page' and valid_retail_quote(new)
    assert new['cache']['hit'] is False
    assert new['cache']['snapshot_id'] != old['cache']['snapshot_id']
    hit = await prices.quote(object_fighter(label='mug'))
    assert hit['cache']['hit'] and hit['cache']['snapshot_id'] == new['cache']['snapshot_id']
    assert len(calls) == 1 and calls[0]['timeout_seconds'] == 8
    assert calls[0]['model'] == 'gemini-3.8-flash'
    assert repo.read(lambda tx: tx.get('priceQuoteSnapshots', old['cache']['snapshot_id']))['quote']['source'] == 'curated_retail'


@pytest.mark.asyncio
async def test_concurrent_cache_miss_does_not_queue_duplicate_optional_model_calls(monkeypatch):
    prices, _, clock = setup(configured=True)
    clock.advance(86400)
    started, finish = asyncio.Event(), asyncio.Event()
    calls = []
    async def lookup(entry, *args, **kwargs):
        calls.append(entry)
        started.set()
        await finish.wait()
        return refreshed(entry, clock)
    monkeypatch.setattr('backend.app.retailer_lookup.lookup_retailer_prices', lookup)
    first = asyncio.create_task(prices.quote(object_fighter(label='mug')))
    await started.wait()
    duplicate = await prices.quote(object_fighter(label='mug'))
    assert duplicate['amount_gbp'] is None and duplicate['status'] == 'reference_refresh_in_progress'
    finish.set()
    assert (await first)['amount_gbp'] == 2 and len(calls) == 1


@pytest.mark.asyncio
async def test_failed_refresh_is_negative_cached_and_never_reuses_expired_starter(monkeypatch):
    prices, _, clock = setup(configured=True)
    prices.initialize()
    clock.advance(86400)
    calls = []
    async def lookup(*args, **kwargs):
        calls.append(1)
        return []
    monkeypatch.setattr('backend.app.retailer_lookup.lookup_retailer_prices', lookup)
    for _ in range(2):
        assert (await prices.quote(object_fighter(label='mug')))['amount_gbp'] is None
    assert len(calls) == 1
    clock.advance(301)
    await prices.quote(object_fighter(label='mug'))
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_pause_blocks_refresh_but_fresh_sourced_cache_needs_no_ai(monkeypatch):
    prices, _, clock = setup(configured=True, paused=True)
    monkeypatch.setattr('backend.app.retailer_lookup.lookup_retailer_prices', lambda *a, **k: pytest.fail('AI dispatched while paused'))
    assert (await prices.quote(object_fighter(label='mug')))['amount_gbp'] == 2
    clock.advance(86400)
    assert (await prices.quote(object_fighter(label='mug')))['status'] == 'refresh_unavailable'


@pytest.mark.asyncio
async def test_optional_cache_failure_leaves_recognition_usable(monkeypatch):
    prices, _, _ = setup()
    def broken(*args):
        raise RuntimeError('db unavailable')
    monkeypatch.setattr(prices.cache, 'get', broken)
    quote = await prices.quote(object_fighter(label='mug'))
    assert quote['amount_gbp'] is None


@pytest.mark.asyncio
async def test_optional_pricing_deadline_includes_database_latency(monkeypatch):
    import time
    prices, _, _ = setup()
    def slow(*args):
        time.sleep(.1)
        return None
    monkeypatch.setattr(prices.cache, 'get', slow)
    monkeypatch.setattr('backend.app.retail_prices.TOTAL_TIMEOUT_SECONDS', .01)
    before = time.monotonic()
    assert (await prices.quote(object_fighter(label='mug')))['amount_gbp'] is None
    assert time.monotonic() - before < .08


@pytest.mark.parametrize('issue', ['observation_expired', 'scope_changed', 'category_changed'])
@pytest.mark.asyncio
async def test_fresh_cache_does_not_override_source_freshness_or_scope(issue):
    prices, _, clock = setup()
    entry = prices.entries['mug']
    quote = make_quote(entry, entry['listings'], source='curated_retail', observed_at=clock())
    if issue == 'observation_expired':
        quote['observed_at'] = (clock.now - timedelta(days=2)).isoformat()
    elif issue == 'scope_changed':
        quote['scope'] = 'An older narrower scope'
    else:
        quote['category'] = 'notebook'
    assert prices.cache.claim('mug', 'fixture-owner')
    assert prices.cache.store('mug', 'fixture-owner', quote)
    assert (await prices.quote(object_fighter(label='mug')))['amount_gbp'] is None


@pytest.mark.asyncio
async def test_sourced_retail_combat_freezes_receipts_with_one_percent_cap_and_unknown_neutrality():
    prices, _, clock = setup()
    items = [object_fighter(label='mug'), object_fighter(label='scissors', slot=1)]
    for item in items:
        item['market_price'] = await prices.quote(item)
    battle = simulate_capture_battle(items, [{}, {}], 73, 'quick')
    assert battle['provenance']['price_sources'] == ['curated_retail', 'curated_retail']
    assert 'eBay' not in battle['explanation']['price_note']
    assert all(0 <= e['receipt']['price_percent'] <= 1 for e in battle['events'])
    snapshot = deepcopy(battle)
    items[0]['market_price']['listings'][0]['amount_gbp'] = 90000
    clock.advance(86400 * 30)
    assert battle == snapshot  # old battle keeps its own immutable reference
    assert combat_price(snapshot['fighters'][0]['price'])['amount_gbp'] == 2
    unknown = simulate_capture_battle(items, [{}, {}], 73, 'quick')
    assert all(event['receipt']['price_percent'] == 0 for event in unknown['events'])


@pytest.mark.parametrize('change', [
    lambda q: q.update(amount_gbp=9999),
    lambda q: q['listings'][0].update(url='https://www.ikea.com.evil.example/gb/en/p/fake'),
    lambda q: q['listings'][0].update(price_evidence='Height 1 cm'),
    lambda q: q['listings'][0].update(currency='USD'),
    lambda q: q['listings'][0].update(amount_gbp=True),
    lambda q: q['listings'][0].update(checked_at='2026-10-24'),
    lambda q: q.update(source='gemini_search'),
    lambda q: q['listings'].__setitem__(1, deepcopy(q['listings'][0])),
])
def test_invalid_or_unsourced_receipts_are_neutral_at_combat_boundary(change):
    entry = catalogue()['entries'][0]
    quote = make_quote(entry, entry['listings'], source='curated_retail', observed_at=catalogue()['checked_at'])
    assert valid_retail_quote(quote)
    change(quote)
    assert combat_price(quote)['amount_gbp'] is None
