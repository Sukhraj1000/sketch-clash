"""World-scoped, leased retail-reference cache with immutable quote receipts.

Repository transactions make a category claim atomic across API processes. A
quote may be published only by its current, unexpired lease owner. Expiry is
checked here instead of using MongoDB TTL deletion, so old source receipts remain
available to explain frozen battles without making stale prices reusable.

Callers validate and sanitize provider output before passing a quote to ``store``.
Only independently sourced retail references are permitted; Google Search
grounding output, suggestions, queries, and citations must never be stored here.
This module intentionally imports neither Repository nor provider code.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import re
import unicodedata


POLICY = 'retail-reference-prices-1'
COLLECTION = 'priceCache'
SNAPSHOT_COLLECTION = 'priceQuoteSnapshots'
CURRENCY = 'GBP'
MARKET = 'GB'


def canonical_category(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('A price category must be text.')
    result = re.sub(r'[\s_-]+', ' ', unicodedata.normalize('NFKC', value).casefold()).strip()
    if not result or len(result) > 80 or any(unicodedata.category(char).startswith('C') for char in result):
        raise ValueError('A price category must contain 1 to 80 readable characters.')
    return result


def _key(*parts) -> str:
    return sha256(json.dumps(parts, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _utc(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Price cache timestamps must have a timezone.')
    return value.astimezone(timezone.utc)


def _future(value, now) -> bool:
    try:
        return _utc(value) > now
    except (TypeError, ValueError, OverflowError):
        return False


def _duration(value) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Cache and lease durations must be positive finite seconds.')
    return timedelta(seconds=value)


def _owner(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError('Each price lookup needs a unique, nonempty lease owner.')
    return value


def _valid_quote(value: dict) -> dict:
    """Minimal persistence contract; source-specific validation belongs upstream."""
    if not isinstance(value, dict) or value.get('status') != 'available' or value.get('currency') != CURRENCY:
        raise ValueError('Only validated, available GBP quotes can be cached.')
    amount = value.get('amount_gbp')
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 0 < amount <= 100000:
        raise ValueError('A cached quote needs a finite positive price.')
    if value.get('policy_version') != POLICY or value.get('source') not in {'curated_retail', 'retailer_page'}:
        raise ValueError('Only independently sourced retail references may enter this cache.')
    _utc(value.get('observed_at'))
    quote = deepcopy(value)
    quote.pop('cache', None)
    # Prevent accidental persistence of an SDK object, credentials, or an entire
    # raw provider response; only the explicit quote receipt belongs in storage.
    forbidden = {'apikey', 'credentials', 'authorization', 'raw', 'rawresponse', 'providerresponse',
                 'searchsuggestions', 'searchqueries', 'websearchqueries', 'searchentrypoint',
                 'citations', 'googlesearch', 'groundedresult', 'groundedresults'}
    def inspect(node):
        if isinstance(node, dict):
            keys = (re.sub(r'[^a-z0-9]', '', str(key).casefold()) for key in node)
            if any(key in forbidden or key.startswith('grounding') for key in keys):
                raise ValueError('Grounded search output, raw provider data, and credentials cannot enter the price cache.')
            for item in node.values():
                inspect(item)
        elif isinstance(node, list):
            for item in node:
                inspect(item)
        elif not isinstance(node, (str, bool, int, float, type(None))):
            raise ValueError('A cached quote must be a sanitized JSON receipt.')
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError('A cached quote must contain finite values.')
    inspect(quote)
    if len(json.dumps(quote, separators=(',', ':'), ensure_ascii=False).encode()) > 64000:
        raise ValueError('A cached quote receipt is too large.')
    return quote


class PriceCache:
    def __init__(self, repo, *, clock=None):
        self.repo = repo
        self.world_id = repo.world_id
        self.clock = clock or repo.clock

    def _now(self, value=None):
        return _utc(self.clock() if value is None else value)

    def _identity(self, category):
        category = canonical_category(category)
        return category, _key(self.world_id, POLICY, category, CURRENCY, MARKET)

    def ensure_indexes(self):
        """Optional explicit startup step; never expires or removes audit rows."""
        db = getattr(self.repo, 'db', None)
        if db is None:
            return
        db[COLLECTION].create_index(
            [('world_id', 1), ('policy_version', 1), ('category', 1), ('currency', 1), ('market', 1)],
            unique=True, name='price_category_scope')
        db[SNAPSHOT_COLLECTION].create_index(
            [('world_id', 1), ('cache_key', 1), ('revision', 1)],
            unique=True, name='price_quote_revision')

    def _fresh(self, record, now):
        return bool(record and record.get('status') in {'available', 'unavailable'}
                    and isinstance(record.get('quote'), dict) and _future(record.get('expires_at'), now))

    def _result(self, record, *, hit):
        quote = deepcopy(record['quote'])
        quote['cache'] = {'hit': hit, 'category': record['category'], 'policy_version': POLICY,
                          'stored_at': record['stored_at'], 'expires_at': record['expires_at'],
                          'snapshot_id': record.get('snapshot_id'),
                          'persistence': 'mongodb' if getattr(self.repo, 'db', None) is not None else 'development_memory'}
        return quote

    def get(self, category: str, *, now=None) -> dict | None:
        """Return a fresh positive/negative quote; expired receipts never leak."""
        _, key = self._identity(category)
        current = self._now(now)
        def read(tx):
            record = tx.get(COLLECTION, key)
            return self._result(record, hit=True) if self._fresh(record, current) else None
        return self.repo.read(read)

    def claim(self, category: str, owner: str, lease_seconds=40, *, now=None) -> bool:
        """Claim one category lookup, using a new owner ID for every attempt."""
        category, key = self._identity(category)
        owner = _owner(owner)
        current = self._now(now)
        until = (current + _duration(lease_seconds)).isoformat()
        def claim(tx):
            record = tx.get(COLLECTION, key)
            if self._fresh(record, current) or (record and _future(record.get('lease_until'), current)):
                return False
            record = record or {'_id': key, 'world_id': self.world_id, 'policy_version': POLICY,
                                'category': category, 'currency': CURRENCY, 'market': MARKET, 'revision': 0}
            record.update(lease_owner=owner, lease_until=until, claimed_at=current.isoformat())
            tx.put(COLLECTION, record)
            return True
        return self.repo.transaction(claim)

    @staticmethod
    def _owns(record, owner, current):
        return bool(record and record.get('lease_owner') == owner and _future(record.get('lease_until'), current))

    def store(self, category: str, owner: str, quote: dict, ttl_seconds=86400, *, now=None) -> dict | None:
        """Publish a sanitized quote and immutable snapshot, or reject a lost lease."""
        _, key = self._identity(category)
        owner = _owner(owner)
        quote = _valid_quote(quote)
        current = self._now(now)
        expires = (current + _duration(ttl_seconds)).isoformat()
        def store(tx):
            record = tx.get(COLLECTION, key)
            if not self._owns(record, owner, current):
                return None
            revision = record.get('revision', 0) + 1
            snapshot_id = _key(key, 'quote', revision)
            snapshot = {'_id': snapshot_id, 'id': snapshot_id, 'world_id': self.world_id,
                        'cache_key': key, 'category': record['category'], 'policy_version': POLICY,
                        'currency': CURRENCY, 'market': MARKET, 'revision': revision,
                        'quote': quote, 'stored_at': current.isoformat(), 'expires_at': expires}
            # This branch should be unreachable under transactional writers. Fail
            # closed rather than replace an existing immutable audit receipt.
            if tx.get(SNAPSHOT_COLLECTION, snapshot_id) is not None:
                raise ValueError('Price quote revision already exists.')
            tx.put(SNAPSHOT_COLLECTION, snapshot)
            record.update(status='available', quote=quote, revision=revision, snapshot_id=snapshot_id,
                          stored_at=current.isoformat(), expires_at=expires, lease_owner=None, lease_until=None)
            tx.put(COLLECTION, record)
            return self._result(record, hit=False)
        return self.repo.transaction(store)

    def fail(self, category: str, owner: str, reason: str, ttl_seconds=300, *, now=None) -> bool:
        """Cache a bounded reason code; late failures cannot clear another lease."""
        _, key = self._identity(category)
        owner = _owner(owner)
        # Provider error bodies may contain request data. Accept stable codes only.
        reason = reason if isinstance(reason, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', reason) else 'provider_unavailable'
        current = self._now(now)
        expires = (current + _duration(ttl_seconds)).isoformat()
        def fail(tx):
            record = tx.get(COLLECTION, key)
            if not self._owns(record, owner, current):
                return False
            quote = {'amount_gbp': None, 'currency': CURRENCY, 'source': 'unavailable', 'confidence': 'unknown',
                     'status': reason, 'label': 'No sourced comparable price; no premium',
                     'policy_version': POLICY, 'observed_at': None, 'listings': []}
            record.update(status='unavailable', quote=quote, stored_at=current.isoformat(), expires_at=expires,
                          snapshot_id=None, lease_owner=None, lease_until=None)
            tx.put(COLLECTION, record)
            return True
        return self.repo.transaction(fail)
