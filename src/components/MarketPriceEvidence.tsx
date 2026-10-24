import type { MarketPrice } from '../lib/object-battles';

/** Source data is untrusted. Never pass provider HTML or an unsafe URL to the page. */
export function safePriceSourceUrl(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password) return undefined;
    return url.href;
  } catch { return undefined; }
}

function dateLabel(value?: string | null): string {
  if (!value) return 'time unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'time unavailable' : date.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
}

function sourceLabel(source: string): string {
  if (source === 'curated_retail') return 'Checked retail reference';
  if (source === 'retailer_page') return 'Retailer page reference';
  if (source === 'ebay_browse') return 'Saved marketplace asking prices';
  return 'Saved price reference';
}

function cacheLabel(price: MarketPrice): string | undefined {
  if (!price.cache) return undefined;
  const location = price.cache.persistence === 'mongodb' ? 'MongoDB Atlas'
    : price.cache.persistence === 'development_memory' ? 'temporary cache' : 'saved cache';
  if (price.cache.hit) return `Cache hit · ${location}`;
  if (price.source === 'curated_retail') return `Sourced starter · ${location}`;
  return `New reference · ${location}`;
}

export default function MarketPriceEvidence({ price }: { price: MarketPrice }) {
  if (price.amount_gbp === null || !Number.isFinite(price.amount_gbp) || price.amount_gbp <= 0) {
    return <div className="cb-price-status"><b>No sourced price · neutral</b><p>{price.label}</p><small>If either object has no price, both price bonuses are zero.</small></div>;
  }
  const listings = (price.listings ?? []).filter(item => Number.isFinite(item.amount_gbp) && item.amount_gbp > 0);
  const label = sourceLabel(price.source);
  const cached = cacheLabel(price);
  return <details className="cb-price-sources">
    <summary>{label}<span>£{price.amount_gbp.toFixed(2)}</span></summary>
    <p>{price.label}</p>
    <p className="cb-price-context">Category comparison, not an appraisal of your object. Price adds at most 1% to damage; unknown prices are neutral.</p>
    <div className="cb-price-meta"><small>Checked {dateLabel(price.observed_at)} · GBP · frozen for this round</small>{cached && <small>{cached}{price.cache?.stored_at ? ` · saved ${dateLabel(price.cache.stored_at)}` : ''}</small>}{price.cache?.expires_at && <small>Cache refresh due {dateLabel(price.cache.expires_at)}</small>}</div>
    {listings.length > 0 && <><h4>{listings.length} saved price {listings.length === 1 ? 'reference' : 'references'}</h4><ul>{listings.map((item, index) => {
      const url = safePriceSourceUrl(item.url);
      return <li key={`${item.item_id}:${index}`}><div>{url ? <a href={url} target="_blank" rel="noopener noreferrer">{item.title}</a> : <span>{item.title}</span>}<small>{[item.retailer, item.condition].filter(Boolean).join(' · ')}{item.checked_at ? ` · checked ${dateLabel(item.checked_at)}` : ''}</small></div><b>£{item.amount_gbp.toFixed(2)}</b></li>;
    })}</ul></>}
  </details>;
}
