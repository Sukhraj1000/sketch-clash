import type { CombatProfile } from '../lib/camera-combat';

export default function MarketPriceEvidence({ price }: { price: CombatProfile['price'] }) {
  if (!price.listings?.length) return <p className="cb-price-status">{price.label}</p>;
  return <details className="cb-price-sources"><summary>See {price.listings.length} sourced asking prices</summary>
    <p>{price.label}</p><small>Retrieved {price.observed_at ? new Date(price.observed_at).toLocaleString() : 'time unavailable'} · GBP · frozen for this round</small>
    <ul>{price.listings.map(item => <li key={item.item_id}><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a><b>£{item.amount_gbp.toFixed(2)}</b><small>{item.condition}</small></li>)}</ul>
  </details>;
}
