"""Optional eBay Browse comparables. Never a valuation of the photographed item.

One bounded UK listing search, >=3 matching single-item offers, median asking
price excluding postage. No credential, match, or timely response means neutral.
Only server-fetched receipts cross into combat; model-supplied prices are ignored.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import math
import re
from statistics import median
import time
from urllib.parse import urlparse

import httpx

from .config import Settings

POLICY = 'ebay-gb-comparables-1'
# Broad labels such as animal, water, plant or mystery object have no comparable.
# This is a conservative market vocabulary, independent of round-theme policy.
GOODS = {
    'water bottle': ('water bottle',), 'bottle': ('water bottle',),
    'tumbler': ('tumbler',), 'mug': ('mug',), 'cup': ('cup',),
    'book': ('book',), 'notebook': ('notebook',), 'pencil': ('pencil',),
    'pen': ('pen',), 'scissors': ('scissors',), 'hammer': ('hammer',),
    'spoon': ('spoon',), 'fork': ('fork',), 'flashlight': ('torch', 'flashlight'),
    'torch': ('torch', 'flashlight'), 'sponge': ('sponge',), 'ball': ('ball',),
    'shoe': ('shoe',), 'remote control': ('remote control',), 'phone': ('phone',),
    'keyboard': ('keyboard',), 'headphones': ('headphones',), 'calculator': ('calculator',),
}
REJECT = re.compile(r'\b(replacement|spare|parts?|broken|faulty|repair|bundle|wholesale|vintage|antique|rare|collectible|miniature)\b|\b(?:pack|set|lot) of\b|\b\d+\s*(?:pcs|pieces|pack)\b|\b(?:case|cover|holder|stand|sleeve|strap|lid|straw) (?:only|for)\b', re.I)
ACCESSORY = re.compile(r'\b(case|protector|charger|charging|cable|adapter|holder|stand|sleeve|strap|replacement|refill|lid|straw)\b', re.I)


def unavailable(reason='unconfigured') -> dict:
    return {'amount_gbp': None, 'source': 'unavailable', 'label': 'No sourced comparable price; no premium',
            'confidence': 'unknown', 'observed_at': None, 'status': reason, 'policy_version': POLICY, 'listings': []}


def query_for(fighter: dict) -> tuple[str, tuple[str, ...]] | None:
    observed = fighter.get('observed_object') or {}
    label = str(observed.get('label') or fighter.get('object_type') or '').lower().replace('_', ' ').strip()
    if ACCESSORY.search(label):
        return None
    # Do not use OCR, generated character names, or model-suggested brands.
    for kind in sorted(GOODS, key=len, reverse=True):
        if re.search(r'\b' + re.escape(kind) + r's?$', label):
            if re.search(r'\b(toy|drawing|picture|photo|shaped|replica)\b', label):
                return None
            return GOODS[kind][0], GOODS[kind]
    return None


def safe_listing_url(value) -> bool:
    try:
        url = urlparse(str(value))
        return url.scheme == 'https' and url.hostname in {'www.ebay.co.uk', 'www.ebay.com', 'ebay.co.uk', 'ebay.com'} and url.path.startswith('/itm/') and not url.username and not url.password
    except ValueError:
        return False


def comparable_quote(payload: dict, query: str, terms: tuple[str, ...]) -> dict:
    listings, seen = [], set()
    items = payload.get('itemSummaries') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return unavailable('invalid_provider_response')
    for item in items[:50]:
        if not isinstance(item, dict):
            continue
        title, price = str(item.get('title', ''))[:160], item.get('price') or {}
        if not isinstance(price, dict) or not isinstance(item.get('buyingOptions'), list):
            continue
        if not any(re.search(r'\b' + re.escape(term) + r's?\b', title, re.I) for term in terms) or REJECT.search(title) or ACCESSORY.search(title):
            continue
        if price.get('currency') != 'GBP' or 'FIXED_PRICE' not in item.get('buyingOptions', []) or not safe_listing_url(item.get('itemWebUrl')):
            continue
        try:
            amount = float(price.get('value'))
        except (ValueError, TypeError):
            continue
        ident = str(item.get('itemId') or '')[:100]
        if not ident or ident in seen or not math.isfinite(amount) or not 0.01 <= round(amount, 2) <= 100000:
            continue
        seen.add(ident)
        listings.append({'item_id': ident, 'title': title, 'amount_gbp': round(amount, 2),
                         'url': item['itemWebUrl'], 'condition': str(item.get('condition') or 'Unspecified')[:60]})
        if len(listings) == 5:
            break
    if len(listings) < 3:
        return {**unavailable('insufficient_matches'), 'query': query}
    amounts = [item['amount_gbp'] for item in listings]
    # A wildly mixed category is not a defensible common price anchor.
    if max(amounts) / min(amounts) > 8:
        return {**unavailable('incomparable_spread'), 'query': query}
    return {'amount_gbp': round(median(amounts), 2), 'source': 'ebay_browse', 'status': 'available',
            'policy_version': POLICY, 'confidence': 'category_comparable', 'currency': 'GBP',
            'label': 'Median eBay UK asking price for similar objects; not this item’s value. Postage excluded.',
            'observed_at': datetime.now(timezone.utc).isoformat(), 'query': query, 'listings': listings}


def combat_price(value: dict | None) -> dict:
    """Reject incomplete receipts and arbitrary estimates at the combat boundary."""
    from .retail_quotes import POLICY as RETAIL_POLICY, neutral
    if isinstance(value, dict) and value.get('source') == 'unavailable' and value.get('policy_version') == RETAIL_POLICY:
        return neutral(value.get('status', 'unavailable'))
    if isinstance(value, dict) and value.get('source') in {'curated_retail', 'retailer_page'}:
        from .retail_quotes import valid_retail_quote
        return deepcopy(value) if valid_retail_quote(value) else unavailable('invalid_receipt')
    if not isinstance(value, dict) or value.get('source') != 'ebay_browse' or value.get('policy_version') != POLICY or value.get('status') != 'available':
        return unavailable((value or {}).get('status', 'unavailable') if isinstance(value, dict) else 'unavailable')
    try:
        amount = float(value['amount_gbp'])
        listings = value['listings']
        values = [float(item['amount_gbp']) for item in listings]
        observed = datetime.fromisoformat(value['observed_at'])
        valid = (3 <= len(listings) <= 5 and value.get('currency') == 'GBP' and observed.tzinfo is not None
                 and all(math.isfinite(v) and 0 < v <= 100000 for v in values)
                 and all(safe_listing_url(item['url']) for item in listings)
                 and len({item['item_id'] for item in listings}) == len(listings)
                 and max(values) / min(values) <= 8 and math.isfinite(amount)
                 and amount == round(median(values), 2))
    except (KeyError, TypeError, ValueError, OverflowError):
        valid = False
    return deepcopy(value) if valid else unavailable('invalid_receipt')


class MarketPrices:
    def __init__(self, settings: Settings, *, transport=None):
        self.settings, self.transport = settings, transport
        self._token, self._token_until = '', 0.0
        self._cache = {}
        self._lock = asyncio.Lock()

    @property
    def configured(self):
        return bool(self.settings.ebay_client_id and self.settings.ebay_client_secret)

    async def quote(self, fighter: dict) -> dict:
        if not self.configured:
            return unavailable()
        query = query_for(fighter)
        if not query:
            return unavailable('unsupported_category')
        try:
            # Includes lock/token/search; optional pricing cannot hold recognition up.
            return await asyncio.wait_for(self._quote(*query), timeout=6)
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, asyncio.TimeoutError):
            return unavailable('provider_unavailable')

    async def _quote(self, query, terms):
        async with self._lock:
            cached = self._cache.get(query)
            if cached and cached[0] > time.monotonic():
                return deepcopy(cached[1])
            async with httpx.AsyncClient(timeout=3, transport=self.transport, follow_redirects=False) as client:
                if self._token_until <= time.monotonic():
                    result = await client.post('https://api.ebay.com/identity/v1/oauth2/token',
                        auth=(self.settings.ebay_client_id, self.settings.ebay_client_secret),
                        data={'grant_type': 'client_credentials', 'scope': 'https://api.ebay.com/oauth/api_scope'})
                    result.raise_for_status()
                    token = result.json()
                    self._token = token['access_token']
                    self._token_until = time.monotonic() + max(1, min(int(token['expires_in']), 7200) - 60)
                result = await client.get('https://api.ebay.com/buy/browse/v1/item_summary/search',
                    headers={'Authorization': 'Bearer ' + self._token, 'X-EBAY-C-MARKETPLACE-ID': 'EBAY_GB'},
                    params={'q': query, 'limit': '30', 'filter': 'buyingOptions:{FIXED_PRICE},priceCurrency:GBP,deliveryCountry:GB'})
                result.raise_for_status()
                quote = comparable_quote(result.json(), query, terms)
                if len(self._cache) >= 100:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[query] = (time.monotonic() + (21600 if quote['amount_gbp'] else 300), deepcopy(quote))
                return quote
