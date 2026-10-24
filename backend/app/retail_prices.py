"""Cache-first references with optional, bounded Gemini retailer-page refreshes."""
import asyncio
from copy import deepcopy
import logging
from uuid import uuid4

from .price_cache import PriceCache
from .retail_quotes import catalogue, category_for, make_quote, neutral, utc, valid_retail_quote, MAX_AGE_SECONDS

logger = logging.getLogger('sketch.prices')
TOTAL_TIMEOUT_SECONDS = 10


class RetailPrices:
    def __init__(self, settings, repository, recognizer):
        self.settings, self.repo, self.recognizer = settings, repository, recognizer
        self.cache = PriceCache(repository)
        self.data = catalogue()
        self.entries = {entry['category']: entry for entry in self.data['entries']}

    def status(self):
        return {'configured': True, 'provider': 'curated_retail_with_gemini_url_context',
                'starter_categories': sorted(self.entries), 'cache': self.repo.persistence,
                'refresh_configured': bool(getattr(self.recognizer, 'client', None) and self.settings.gemini_api_key),
                'refresh_model': self.settings.price_lookup_model,
                'basis': 'UK retail category references; unknown stays neutral; not an appraisal',
                'search_grounding': False}

    def _starter(self, entry):
        age = (utc(self.repo.clock()) - utc(self.data['checked_at'])).total_seconds()
        if not 0 <= age < MAX_AGE_SECONDS:
            return None, 0
        return make_quote(entry, entry['listings'], source='curated_retail',
                          observed_at=self.data['checked_at'], version=self.data['version']), MAX_AGE_SECONDS - age

    def initialize(self):
        """Seed only fresh reviewed data; a restart never extends its useful life."""
        self.cache.ensure_indexes()
        for category, entry in self.entries.items():
            quote, ttl = self._starter(entry)
            if quote and valid_retail_quote(quote):
                owner = uuid4().hex
                if self.cache.claim(category, owner):
                    self.cache.store(category, owner, quote, ttl_seconds=ttl)

    async def quote(self, fighter):
        category = category_for(fighter)
        if category not in self.entries:
            return neutral()
        try:
            # Includes optional database reads/writes as well as provider waits.
            # An in-flight DB thread may finish a safe leased store after this
            # caller stops waiting; it cannot overwrite another lease owner.
            return await asyncio.wait_for(self._quote(category), timeout=TOTAL_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Optional price/storage failure cannot discard paid recognition.
            logger.warning('price_reference_unavailable category=%s', type(exc).__name__)
            return neutral('reference_unavailable')

    def _usable(self, quote, category):
        if not valid_retail_quote(quote) or quote.get('category') != category or quote.get('scope') != self.entries[category]['scope']:
            return False
        # Storage latency/restarts must not extend a source's freshness horizon.
        age = (utc(self.repo.clock()) - utc(quote['observed_at'])).total_seconds()
        return 0 <= age < MAX_AGE_SECONDS

    async def _quote(self, category):
        cached = await asyncio.to_thread(self.cache.get, category)
        if cached is not None:
            return cached if cached.get('amount_gbp') is None or self._usable(cached, category) else neutral('invalid_cached_reference')
        entry = self.entries[category]
        owner = uuid4().hex
        if not await asyncio.to_thread(self.cache.claim, category, owner):
            # Another capture owns the lookup. Do not queue duplicate paid work.
            cached = await asyncio.to_thread(self.cache.get, category)
            return cached if cached and self._usable(cached, category) else neutral('reference_refresh_in_progress')
        quote, ttl = self._starter(entry)
        if not quote:
            if self.settings.ai_paused or not self.settings.gemini_api_key or not getattr(self.recognizer, 'client', None):
                await asyncio.to_thread(self.cache.fail, category, owner, 'refresh_unavailable')
                return neutral('refresh_unavailable')
            from .retailer_lookup import lookup_retailer_prices
            listings = await lookup_retailer_prices(deepcopy(entry), self.recognizer.client,
                provider_queue=getattr(self.recognizer, 'provider_queue', None),
                model=self.settings.price_lookup_model, timeout_seconds=8)
            quote = make_quote(entry, listings, source='retailer_page', observed_at=self.repo.clock())
            ttl = MAX_AGE_SECONDS
        if not valid_retail_quote(quote):
            await asyncio.to_thread(self.cache.fail, category, owner, 'no_verified_reference')
            return neutral('no_verified_reference')
        saved = await asyncio.to_thread(self.cache.store, category, owner, quote, ttl_seconds=ttl)
        return saved if saved and self._usable(saved, category) else neutral('reference_lease_expired')
