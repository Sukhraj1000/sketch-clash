"""Conservative UK retail references, independent of Google Search grounding.

Only the reviewed product catalogue is eligible. Receipts are category examples,
not exact-item appraisals; unknown identities never acquire a made-up price.
Historical snapshots remain self-contained when the starter catalogue changes.
"""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from statistics import median
from urllib.parse import urlparse

from .price_cache import POLICY

STARTERS = Path(__file__).resolve().parents[1] / 'data' / 'starter_prices.json'
RETAIL_HOSTS = {'www.ikea.com', 'www.wilko.com', 'www.ryman.co.uk'}
MAX_AGE_SECONDS = 86400
UNSUITABLE = re.compile(r'\b(toy|drawing|picture|photo|replica|shaped|case|cover|holder|replacement|spare|broken|faulty|antique|vintage|collectible|luxury|premium|gold|silver|set|pack|bundle)\b', re.I)


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('A reference price needs a timezone-aware date.')
    return value.astimezone(timezone.utc)


def neutral(reason='unsupported_category'):
    return {'amount_gbp': None, 'currency': 'GBP', 'source': 'unavailable', 'status': reason,
            'label': 'No sourced comparable price; no premium', 'confidence': 'unknown',
            'policy_version': POLICY, 'observed_at': None, 'listings': []}


def safe_retail_url(value):
    try:
        url = urlparse(value)
        return (url.scheme == 'https' and url.hostname in RETAIL_HOSTS
                and url.port in (None, 443) and not url.username and not url.password
                and not url.query and not url.fragment and len(url.path) > 10
                and (url.hostname != 'www.ikea.com' or url.path.startswith('/gb/en/p/')))
    except (TypeError, ValueError, AttributeError):
        return False


def evidence_matches(text, amount):
    """A number elsewhere (e.g. size) is not a displayed GBP price."""
    if not isinstance(text, str) or not 1 <= len(text) <= 300:
        return False
    values = re.findall(r'(?:£|GBP\s*)(\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d.])', text)
    return any(float(value.replace(',', '')) == amount for value in values)


@lru_cache(maxsize=1)
def catalogue():
    data = json.loads(STARTERS.read_text())
    return data


def category_for(fighter):
    observed = fighter.get('observed_object') or {}
    label = str(observed.get('label') or fighter.get('object_type') or '').casefold().replace('_', ' ').strip()
    if UNSUITABLE.search(label):
        return None
    features = ' '.join(str(x) for x in observed.get('visible_features', [])
                        if not re.search(r'\b(background|behind|tabletop|resting on|sitting on)\b', str(x), re.I))
    text = label + ' ' + features
    if UNSUITABLE.search(text):
        return None
    lengths = [float(number) for number in re.findall(r'\b(\d+(?:\.\d+)?)\s*cm\b', text, re.I)]
    if re.search(r'\bmugs?$', label) and not re.search(r'\b(steel|metal|plastic|glass|travel|insulated|thermal|copper|enamel|wood|wooden|silicone|paper)\b', text, re.I):
        return 'mug'
    if re.search(r'\bwater bottles?$', label) and not re.search(r'\b(insulated|vacuum|thermal|disposable|tumbler|flask|stanley|yeti)\b', text, re.I):
        volumes = [(float(number), unit.lower()) for number, unit in re.findall(r'\b(\d+(?:\.\d+)?)\s*(ml|cl|litres?|liters?|l)\b', text, re.I)]
        if any(number * (1 if unit == 'ml' else 10 if unit == 'cl' else 1000) != 500 for number, unit in volumes):
            return None
        return 'water_bottle'
    if re.search(r'\bnotebooks?$', label) and not re.search(r'\b(computer|laptop|electronic|digital|screen|keyboard|apple|macbook|leather|a4|a6)\b', text, re.I):
        if any(size != '5' for size in re.findall(r'\ba([0-9])\b', text, re.I)):
            return None
        return 'notebook'
    if re.search(r'\brulers?$', label) and not re.search(r'\b(steel|metal|wood|wooden|electronic|cutting|15cm|15 cm)\b', text, re.I):
        if any(length != 30 for length in lengths):
            return None
        return 'ruler'
    if re.search(r'\bscissors$', label) and not re.search(r'\b(surgical|medical|heavy|child|children|kids|safety|garden|hair|hairdressing|fabric|kitchen)\b', text, re.I):
        if any(not 17 <= length <= 21 for length in lengths):
            return None
        return 'scissors'
    return None


def valid_retail_quote(value):
    """Self-contained historical validation; does not reprice saved battles."""
    if not isinstance(value, dict):
        return False
    try:
        listings = value['listings']
        amount = value['amount_gbp']
        source = value['source']
        if (value['policy_version'] != POLICY or source not in {'curated_retail', 'retailer_page'}
                or value['status'] != 'available' or value['currency'] != 'GBP'
                or not isinstance(listings, list) or not 2 <= len(listings) <= 5
                or isinstance(amount, bool) or not isinstance(amount, (float, int))
                or not isinstance(value.get('category'), str) or not value.get('scope')):
            return False
        utc(value['observed_at'])
        prices = []
        for item in listings:
            price = item['amount_gbp']
            if (isinstance(price, bool) or not isinstance(price, (int, float))
                    or not math.isfinite(price) or not .01 <= price <= 100000 or round(price, 2) != price
                    or item['currency'] != 'GBP' or item['condition'] != 'New'
                    or not safe_retail_url(item['url']) or not item['item_id'] or not item['title']
                    or not item['retailer'] or not evidence_matches(item['price_evidence'], price)):
                return False
            utc(item['checked_at'])
            if source == 'retailer_page' and item.get('retrieval_status') != 'success':
                return False
            prices.append(price)
        return (len({item['item_id'] for item in listings}) == len(listings)
                and len({item['url'] for item in listings}) == len(listings)
                and max(prices) / min(prices) <= 8 and math.isfinite(amount)
                and amount == round(median(prices), 2)
                and (source != 'retailer_page' or value.get('verification') == 'gemini_url_context'))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def make_quote(entry, listings, *, source, observed_at, version=None):
    if not listings:
        return neutral('insufficient_references')
    quote = {'amount_gbp': round(median(item['amount_gbp'] for item in listings), 2),
             'currency': 'GBP', 'source': source, 'status': 'available', 'policy_version': POLICY,
             'confidence': 'category_reference', 'category': entry['category'], 'scope': entry['scope'],
             'observed_at': observed_at, 'query': entry['query'], 'listings': deepcopy(listings),
             'label': 'Median of checked UK retail examples; not this object’s value. Delivery excluded. Source pages may be cached; stock and checkout prices are not guaranteed.'}
    if source == 'curated_retail':
        quote['catalogue_version'] = version
    else:
        quote['verification'] = 'gemini_url_context'
    return quote if valid_retail_quote(quote) else neutral('invalid_reference')
