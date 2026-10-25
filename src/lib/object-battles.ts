import { api, post } from './api';
import type { BattleEvent, BattleOutcome, BattlePlayback } from '../game/battle';
import type { Fighter } from '../types';

export type MarketPrice = {
  amount_gbp: number | null;
  source: string;
  label: string;
  observed_at: string | null;
  confidence: string;
  policy_version?: string;
  listings?: {
    item_id: string; title: string; amount_gbp: number; url: string; condition: string;
    retailer?: string; checked_at?: string;
  }[];
  cache?: {
    hit: boolean; snapshot_id?: string; stored_at?: string; expires_at?: string;
    policy_version?: string; category?: string; persistence?: 'mongodb' | 'development_memory';
  };
};

export type ArenaFixture = {
  id: string; name: string; object_type: string; description: string;
  stats: { impact: number; resilience: number; agility: number; control: number };
  health: 100; traits: string[]; capabilities: string[]; limitations: string[];
  price: MarketPrice;
  provenance: { kind: string; label: string; profile_version: string }; profile_version: string;
};
export type ArenaRule = { id: string; name: string; description: string };
export type MatchupEffect = { attacker: 0 | 1; id: string; name: string; percent: number; reason: string; timing: string };
export type ArenaCatalog = {
  engine_version: string; profile_version: string; fixtures: ArenaFixture[]; rules: ArenaRule[];
  price_policy: { max_bonus_percent: number; kind: string }; disclaimer: string; persistence: string; storage_available: boolean;
  matchup_previews?: Record<string, MatchupEffect[]>;
};
export type HitReceipt = {
  base_damage: number; stat_adjustment: number; interaction_percent: number;
  interaction_rules: { id: string; name: string; percent: number; reason: string }[];
  price_percent: number; price_damage: number; interaction_damage: number; luck: number; unrounded_damage: number; rounding_adjustment: number; damage_before_cap: number; damage: number;
  health_before: number; health_after: number; dodged: boolean; round: number;
  water_charges_before?: number; water_charges_after?: number;
};
export type ArenaEvent = BattleEvent & { receipt: HitReceipt };
type CounterfactualResult = { winner_slot: 0 | 1; final_health: [number, number]; outcome: BattleOutcome; changed_winner: boolean; impact_points?: [number, number]; tiebreak_reason?: 'impact_points' | 'seed' | null };
export type ArenaBattle = {
  id: string; request_id: string; created_at: string; persistence: string; source: 'local_fixture';
  island_rewards: false; immutable: true; fighters: [ArenaFixture, ArenaFixture]; events: ArenaEvent[];
  winner_slot: 0 | 1; duration_ms: number; final_health: [number, number]; engine_version: string;
  profile_version: string; seed: number; playback_mode: 'normal'; outcome: BattleOutcome;
  tiebreak_reason?: 'impact_points' | 'seed' | null; impact_points?: [number, number];
  explanation: { summary: string; highlights: string[]; price_note: string };
  counterfactual: { without_price: CounterfactualResult; without_interactions: CounterfactualResult };
};
export const loadArenaCatalog = (signal?: AbortSignal) => api<ArenaCatalog>('/arena/catalog', { signal });
export const loadArenaBattle = (id: string, signal?: AbortSignal) => api<ArenaBattle>(`/arena/battles/${encodeURIComponent(id)}`, { signal });
export const createArenaBattle = (requestId: string, fighterIds: [string, string]) => post<ArenaBattle>('/arena/battles', { request_id: requestId, fighter_ids: fighterIds });
export const fixtureImage = (fixture: ArenaFixture) => `/fixtures/${fixture.id}.svg`;
export const humanize = (value: string) => value.replaceAll('_', ' ').replaceAll('-', ' ');
export const pounds = (amount: number | null) => amount === null ? 'Unknown' : new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: amount % 1 ? 2 : 0 }).format(amount);
export const signed = (value: number, suffix = '') => `${value > 0 ? '+' : value < 0 ? '−' : ''}${Number(Math.abs(value).toFixed(2))}${suffix}`;

type FixtureAppearance = { template: NonNullable<Fighter['characterVisual']>['visual_spec']['template_id']; palette: [string, string]; accessories?: string[] };
const FIXTURE_APPEARANCES: Record<string, FixtureAppearance> = {
  'ceramic-mug': { template: 'mug', palette: ['#F4A196', '#FFD166'], accessories: ['handle'] },
  'steel-bottle': { template: 'bottle', palette: ['#A7BEC7', '#426078'], accessories: ['cap'] },
  'kitchen-sponge': { template: 'generic', palette: ['#FFD166', '#5B9671'] },
  'wooden-ruler': { template: 'generic', palette: ['#DEAF71', '#7C4E32'] },
  'rubber-ball': { template: 'ball', palette: ['#FF596E', '#FFD166'] },
  'hardback-book': { template: 'book', palette: ['#6C92C5', '#FFD166'] },
  'filled-water-jug': { template: 'generic', palette: ['#A7DCD8', '#438CAF'], accessories: ['handle'] },
  'wooden-spoon': { template: 'generic', palette: ['#C58C56', '#E6BD86'] },
  'coiled-rope': { template: 'generic', palette: ['#C9A676', '#795B3D'] },
  'smartphone': { template: 'generic', palette: ['#4E6175', '#83D9D4'] },
  'foam-block': { template: 'generic', palette: ['#AA9DD8', '#C9C0EA'] },
  'metal-whisk': { template: 'generic', palette: ['#A7BEC7', '#556A7C'] },
};

/** Authored practice presentation, never a camera observation or game profile. */
export function fixtureCharacterVisual(fixture: ArenaFixture): NonNullable<Fighter['characterVisual']> {
  const appearance = FIXTURE_APPEARANCES[fixture.id] ?? { template: 'generic', palette: ['#66E0D4', '#FFD166'] };
  return {
    image_ref: fixtureImage(fixture), display_name: fixture.name, object_type: fixture.object_type, canonical_type_id: fixture.object_type,
    visual_spec: {
      template_id: appearance.template, palette: [...appearance.palette], scale: 1, proportions: { width: 1, height: 1 },
      accessories: ['eyes', 'arms', 'feet', ...(appearance.accessories ?? [])], animation_style: 'bouncy',
      schema_version: 'authored-arena-1', appearance_seed: [...fixture.id].reduce((seed, char) => (seed * 31 + char.charCodeAt(0)) >>> 0, 0),
    },
  };
}

export const arenaFighters = (match: ArenaBattle): [Fighter, Fighter] => match.fighters.map((fixture, slot) => ({
  id: `${match.id}:${slot}`, name: fixture.name, image: fixtureImage(fixture),
  subtitle: `${humanize(fixture.object_type)} · sample object`, side: slot as 0 | 1,
  color: slot === 0 ? 'var(--coral)' : 'var(--mint)',
  combatStats: { ...fixture.stats }, characterVisual: fixtureCharacterVisual(fixture),
})) as [Fighter, Fighter];
export const arenaPlayback = (match: ArenaBattle): BattlePlayback => ({
  duration_ms: match.duration_ms, winner_slot: match.winner_slot, outcome: match.outcome, source_label: 'OBJECT LAB · SAVED REPLAY',
  events: match.events.map(event => ({ ...event, explanation: `${match.fighters[event.attacker].name}: ${event.damage} damage. ${event.receipt.interaction_rules.map(rule => rule.reason).join(' ') || 'No conditional weakness applied.'}` })),
});
export function battleIdFromHash() {
  const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
  const id = params.get('id');
  return id && /^[A-Za-z0-9_-]{1,100}$/.test(id) ? id : null;
}
