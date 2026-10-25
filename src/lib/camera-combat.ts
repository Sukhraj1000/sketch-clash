import type { BattleRecord, PendingFighter } from './api';
import type { ArenaBattle, ArenaFixture, ArenaEvent } from './object-battles';
import type { BattlePlayback } from '../game/battle';
import type { Fighter } from '../types';

export type CombatProfile = Omit<ArenaFixture, 'provenance'> & {
  image_ref?: string;
  provenance: { kind: string; label: string; profile_version?: string; [key: string]: unknown };
  resources?: { water_charges?: number; water_evidence?: string };
};
export type CameraCombat = Omit<Pick<ArenaBattle, 'events' | 'winner_slot' | 'duration_ms' | 'final_health' | 'engine_version' | 'profile_version' | 'seed' | 'outcome' | 'tiebreak_reason' | 'impact_points' | 'explanation' | 'counterfactual'>, 'events'> & {
  fighters: [CombatProfile, CombatProfile];
  events: ArenaEvent[];
  price_policy?: { max_bonus_percent: number; description?: string; kind?: string };
};
export const COMBAT_STATS = ['impact', 'resilience', 'agility', 'control'] as const;

/** Keep the accepted appearance separate from combat attributes and detach it
 * from the saved record before the renderer animates it. Older rounds may not
 * contain a usable visual specification; they retain their source image. */
function acceptedCharacterVisual(fighter: PendingFighter): Fighter['characterVisual'] {
  const spec = fighter.visual_spec;
  const proportions = spec?.proportions as { width?: unknown; height?: unknown } | undefined;
  if (!spec || !['mug', 'bottle', 'plant', 'book', 'ball', 'generic'].includes(String(spec.template_id))
    || !Array.isArray(spec.palette) || spec.palette.length === 0 || !spec.palette.every(color => typeof color === 'string' && /^#[a-f\d]{6}$/i.test(color))
    || !Array.isArray(spec.accessories) || !spec.accessories.every(value => ['eyes', 'arms', 'feet', 'leaf', 'handle', 'cap'].includes(value))
    || !['bouncy', 'calm', 'wobbly'].includes(String(spec.animation_style))
    || ![spec.scale, proportions?.width, proportions?.height].every(value => typeof value === 'number' && Number.isFinite(value) && value >= .7 && value <= 1.4)
    || typeof spec.appearance_seed !== 'number' || !Number.isFinite(spec.appearance_seed)) return undefined;
  return structuredClone({
    visual_spec: spec,
    image_ref: fighter.image_ref,
    display_name: fighter.display_name,
    object_type: fighter.object_type,
    canonical_type_id: fighter.canonical_type_id,
    observed_object: fighter.observed_object,
  }) as NonNullable<Fighter['characterVisual']>;
}

/** Rendering follows the immutable battle snapshot, never today's recognition profile. */
export function cameraFighter(fighter: PendingFighter, profile = fighter.combat_profile): Fighter {
  return {
    id: `${fighter.battle_id}-${fighter.player_slot}`, name: profile?.name ?? fighter.display_name,
    image: profile?.image_ref ?? fighter.image_ref,
    subtitle: `${(profile?.object_type ?? fighter.object_type).toUpperCase()} · ${profile ? 'ATTRIBUTE PROFILE' : 'CAMERA OBJECT'}`,
    side: fighter.player_slot, color: fighter.player_slot === 0 ? 'var(--coral)' : 'var(--mint)', kind: 'photo',
    combatStats: profile?.stats,
    characterVisual: acceptedCharacterVisual(fighter),
  };
}
export function cameraPair(record: BattleRecord): [Fighter, Fighter] {
  return [cameraFighter(record.fighters[0], record.combat?.fighters[0]), cameraFighter(record.fighters[1], record.combat?.fighters[1])];
}
export function cameraPlayback(record: BattleRecord): BattlePlayback | undefined {
  if (!record.duration_ms || record.winner_slot === null) return undefined;
  const combat = record.combat;
  return {
    duration_ms: record.duration_ms, winner_slot: record.winner_slot,
    // Historical rounds retain their recorded timing and class-engine outcome.
    ...(combat ? { outcome: combat.outcome, source_label: 'CAMERA OBJECTS · SAVED ATTRIBUTE BATTLE' } : {}),
    events: record.events.map(event => {
      const receipt = combat?.events.find(item => item.id === event.id)?.receipt;
      if (!receipt || !combat) return event;
      return { ...event, explanation: `${combat.fighters[event.attacker].name}: ${event.damage} damage. ${receipt.interaction_rules.map(rule => `${rule.name}: ${rule.reason}`).join(' ') || 'No conditional weakness or resistance applied.'}` };
    }),
  };
}

export function priceComparisonTitle(combat: CameraCombat): string {
  if (combat.fighters.some(profile => profile.price.amount_gbp === null)) return 'Unknown prices. Neutral for both.';
  return combat.counterfactual.without_price.changed_winner ? 'Price swung this close fight.' : 'Same winner without price.';
}

/** Only assert equal pre-luck damage when every recorded hit can be checked. */
export function equalDamageBeforeLuck(combat: CameraCombat): boolean {
  const completeFields = ['base_damage', 'stat_adjustment', 'interaction_damage', 'price_damage', 'luck', 'rounding_adjustment', 'unrounded_damage', 'damage_before_cap', 'damage', 'health_before', 'health_after'] as const;
  const actors = new Set<number>();
  let reference: number | undefined;
  for (const event of combat.events) {
    const receipt = event.receipt;
    if (!receipt || !completeFields.every(key => typeof receipt[key] === 'number' && Number.isFinite(receipt[key]))) return false;
    if (event.attacker !== 0 && event.attacker !== 1) return false;
    actors.add(event.attacker);
    const amount = receipt.base_damage + receipt.stat_adjustment + receipt.interaction_damage + receipt.price_damage;
    if (reference === undefined) reference = amount;
    else if (Math.abs(amount - reference) > 0.000001) return false;
  }
  return actors.size === 2;
}
