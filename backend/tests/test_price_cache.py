"""Durable cache/lease contracts; no provider requests or Atlas credentials."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from app.config import Settings
from app.price_cache import PriceCache, POLICY, COLLECTION, SNAPSHOT_COLLECTION, canonical_category
from app.repository import MemoryRepository


@pytest.fixture
def setup():
    current = [datetime(2026, 10, 24, 12, tzinfo=timezone.utc)]
    repo = MemoryRepository(Settings(repository='memory', world_id='price-tests'), clock=lambda: current[0].isoformat())
    return repo, current, PriceCache(repo)


def quote(amount=8.0):
    return {'amount_gbp': amount, 'currency': 'GBP', 'source': 'curated_retail', 'status': 'available',
            'policy_version': POLICY, 'confidence': 'category_comparable', 'category': 'mug',
            'label': 'Independent retail category reference', 'observed_at': '2026-10-24T12:00:00+00:00',
            'listings': [{'title': 'Ceramic mug', 'amount_gbp': amount, 'url': 'https://retailer.example/mug'}]}


def publish(cache, category='mug', owner='a', value=None, ttl_seconds=86400):
    assert cache.claim(category, owner)
    return cache.store(category, owner, quote() if value is None else value, ttl_seconds=ttl_seconds)


def test_cache_is_world_category_market_policy_scoped_and_canonical(setup):
    repo, _, cache = setup
    saved = publish(cache, '  Water_Bottle ')
    assert canonical_category('water-bottle') == 'water bottle'
    assert cache.get('WATER BOTTLE')['amount_gbp'] == 8
    assert cache.get('mug') is None
    row = next(iter(repo._data[COLLECTION].values()))
    assert {field: row[field] for field in ('world_id', 'category', 'currency', 'market', 'policy_version')} == {
        'world_id': 'price-tests', 'category': 'water bottle', 'currency': 'GBP', 'market': 'GB', 'policy_version': POLICY}
    class OtherScope:
        world_id = 'another-world'
        clock = staticmethod(repo.clock)
        read = repo.read
        transaction = repo.transaction
    other = PriceCache(OtherScope())
    assert other.get('water bottle') is None
    publish(other, 'water bottle', value=quote(6))
    assert cache.get('water bottle')['amount_gbp'] == 8
    assert other.get('water bottle')['amount_gbp'] == 6
    assert saved['cache']['snapshot_id'] != other.get('water bottle')['cache']['snapshot_id']
    assert saved['cache']['persistence'] == 'development_memory'


def test_expiry_boundary_returns_no_stale_price_and_keeps_immutable_history(setup):
    repo, current, cache = setup
    first = publish(cache, ttl_seconds=10)
    first_snapshot = deepcopy(repo._data[SNAPSHOT_COLLECTION][first['cache']['snapshot_id']])
    current[0] += timedelta(seconds=9)
    assert cache.get('mug')['amount_gbp'] == 8
    assert not cache.claim('mug', 'blocked')
    current[0] += timedelta(seconds=1)
    assert cache.get('mug') is None
    second = publish(cache, owner='b', value=quote(10), ttl_seconds=10)
    assert first['cache']['snapshot_id'] != second['cache']['snapshot_id']
    assert len(repo._data[SNAPSHOT_COLLECTION]) == 2
    assert repo._data[SNAPSHOT_COLLECTION][first['cache']['snapshot_id']] == first_snapshot


def test_second_cache_instance_recovers_published_quote_and_durable_lease(setup):
    repo, _, first = setup
    assert first.claim('mug', 'first')
    restarted = PriceCache(repo)
    assert not restarted.claim('mug', 'second')
    assert first.store('mug', 'first', quote())
    assert restarted.get('mug')['amount_gbp'] == 8
    assert restarted.get('mug')['cache']['hit'] is True


def test_concurrent_process_style_claims_allow_only_one_provider_lookup(setup):
    repo, _, _ = setup
    gate = Barrier(8)
    def attempt(owner):
        gate.wait(timeout=5)
        return PriceCache(repo).claim('mug', owner)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, [f'worker-{i}' for i in range(8)]))
    assert sum(results) == 1
    assert len(repo._data[COLLECTION]) == 1


def test_expired_owner_cannot_publish_or_clear_a_new_workers_lease(setup):
    _, current, cache = setup
    assert cache.claim('mug', 'old', lease_seconds=5)
    assert not cache.claim('mug', 'old', lease_seconds=5)
    current[0] += timedelta(seconds=5)
    assert cache.store('mug', 'old', quote()) is None
    assert not cache.fail('mug', 'old', 'provider_unavailable')
    assert cache.claim('mug', 'new', lease_seconds=5)
    assert cache.store('mug', 'old', quote()) is None
    assert not cache.fail('mug', 'old', 'provider_unavailable')
    assert cache.store('mug', 'new', quote(12))['amount_gbp'] == 12
    assert cache.store('mug', 'old', quote(7)) is None
    assert not cache.fail('mug', 'old', 'provider_unavailable')
    assert cache.get('mug')['amount_gbp'] == 12


def test_negative_cache_blocks_repeat_searches_then_expires(setup):
    repo, current, cache = setup
    assert cache.claim('mug', 'first')
    assert cache.fail('mug', 'first', 'insufficient_sources', ttl_seconds=30)
    negative = PriceCache(repo).get('mug')
    assert negative['amount_gbp'] is None
    assert negative['status'] == 'insufficient_sources'
    assert negative['source'] == 'unavailable'
    assert negative['cache']['snapshot_id'] is None
    assert not cache.claim('mug', 'second')
    current[0] += timedelta(seconds=30)
    assert cache.get('mug') is None
    assert cache.claim('mug', 'second')
    assert cache.store('mug', 'second', quote())['amount_gbp'] == 8


def test_failed_refresh_does_not_resurrect_expired_positive_or_erase_audit_receipt(setup):
    repo, current, cache = setup
    first = publish(cache, ttl_seconds=1)
    original = deepcopy(repo._data[SNAPSHOT_COLLECTION])
    current[0] += timedelta(seconds=1)
    assert cache.claim('mug', 'new')
    assert cache.get('mug') is None
    assert cache.fail('mug', 'new', 'no_matches')
    assert cache.get('mug')['amount_gbp'] is None
    assert cache.get('mug')['cache']['snapshot_id'] is None
    assert repo._data[SNAPSHOT_COLLECTION] == original
    assert first['amount_gbp'] == 8


def test_input_results_and_snapshot_are_not_shared_mutable_references(setup):
    repo, _, cache = setup
    value = quote()
    saved = publish(cache, value=value)
    snapshot_id = saved['cache']['snapshot_id']
    value['listings'][0]['amount_gbp'] = 99
    saved['listings'][0]['amount_gbp'] = 100
    retrieved = cache.get('mug')
    retrieved['listings'].clear()
    assert cache.get('mug')['listings'][0]['amount_gbp'] == 8
    assert repo._data[SNAPSHOT_COLLECTION][snapshot_id]['quote']['listings'][0]['amount_gbp'] == 8


def test_explicit_now_accepts_timezone_and_normalizes_to_utc(setup):
    repo, _, cache = setup
    at = '2026-10-24T14:00:00+02:00'
    assert cache.claim('mug', 'a', now=at)
    saved = cache.store('mug', 'a', quote(), ttl_seconds=5, now=at)
    assert saved['cache']['stored_at'] == '2026-10-24T12:00:00+00:00'
    assert PriceCache(repo).get('mug', now='2026-10-24T12:00:05Z') is None


@pytest.mark.parametrize('value', ['', ' ', '\x00', 'a' * 81, None, 42])
def test_invalid_categories_fail_before_accessing_storage(setup, value):
    repo, _, cache = setup
    with pytest.raises(ValueError):
        cache.claim(value, 'a')
    assert COLLECTION not in repo._data


@pytest.mark.parametrize('seconds', [0, -1, float('inf'), float('nan'), True, '10'])
def test_invalid_ttl_or_lease_cannot_make_an_immortal_price(setup, seconds):
    _, _, cache = setup
    with pytest.raises(ValueError):
        cache.claim('mug', 'a', lease_seconds=seconds)
    assert cache.claim('mug', 'a')
    with pytest.raises(ValueError):
        cache.store('mug', 'a', quote(), ttl_seconds=seconds)
    with pytest.raises(ValueError):
        cache.fail('mug', 'a', 'no_matches', ttl_seconds=seconds)


@pytest.mark.parametrize('changes', [
    {'amount_gbp': None}, {'amount_gbp': 0}, {'amount_gbp': float('nan')}, {'amount_gbp': True},
    {'currency': 'USD'}, {'status': 'unknown'}, {'policy_version': 'old-policy'},
    {'observed_at': '2026-10-24T12:00:00'}, {'source': ''}, {'raw_response': {'sensitive': True}},
    {'listings': [{'api_key': 'do-not-persist'}]}, {'listings': [{'nested': object()}]},
])
def test_cache_rejects_invalid_or_raw_receipts(setup, changes):
    repo, _, cache = setup
    assert cache.claim('mug', 'a')
    with pytest.raises(ValueError):
        cache.store('mug', 'a', {**quote(), **changes})
    assert SNAPSHOT_COLLECTION not in repo._data


def test_failure_body_is_not_saved_as_diagnostic_text(setup):
    repo, _, cache = setup
    assert cache.claim('mug', 'a')
    assert cache.fail('mug', 'a', '429 request had api_key=do-not-persist')
    assert cache.get('mug')['status'] == 'provider_unavailable'
    assert 'do-not-persist' not in str(repo._data[COLLECTION])


@pytest.mark.parametrize('source', ['gemini_search', 'google_search', 'search_grounding', 'ebay_browse'])
def test_search_and_unapproved_provider_sources_cannot_be_persisted(setup, source):
    repo, _, cache = setup
    assert cache.claim('mug', 'a')
    with pytest.raises(ValueError):
        cache.store('mug', 'a', {**quote(), 'source': source})
    assert SNAPSHOT_COLLECTION not in repo._data


@pytest.mark.parametrize('field', [
    'grounding', 'grounding_metadata', 'groundingMetadata', 'groundingChunks',
    'search_suggestions', 'searchSuggestions', 'search_queries', 'webSearchQueries',
    'searchEntryPoint', 'citations', 'google_search',
])
def test_search_grounding_fields_rejected_even_inside_retail_receipts(setup, field):
    repo, _, cache = setup
    assert cache.claim('mug', 'a')
    with pytest.raises(ValueError):
        cache.store('mug', 'a', {**quote(), 'listings': [{field: 'must not persist'}]})
    assert SNAPSHOT_COLLECTION not in repo._data


def test_direct_retailer_receipts_and_persistence_metadata(setup):
    repo, _, cache = setup
    repo.db = object()  # Exercise metadata only; no database or network operation.
    value = {**quote(), 'source': 'retailer_page'}
    saved = publish(cache, value=value)
    assert saved['source'] == 'retailer_page'
    assert saved['cache']['persistence'] == 'mongodb'
    assert saved['cache']['policy_version'] == 'retail-reference-prices-1'
    assert cache.get('mug')['cache']['persistence'] == 'mongodb'


def test_index_setup_is_explicit_and_has_no_ttl_deletion(setup):
    repo, _, cache = setup
    cache.ensure_indexes()  # Memory adapters require no fake database APIs.
    calls = []
    class Collection:
        def create_index(self, fields, **options):
            calls.append((fields, options))
    class Database:
        def __getitem__(self, name):
            assert name in {COLLECTION, SNAPSHOT_COLLECTION}
            return Collection()
    repo.db = Database()
    cache.ensure_indexes()
    assert len(calls) == 2
    assert all(options['unique'] and 'expireAfterSeconds' not in options for _, options in calls)
