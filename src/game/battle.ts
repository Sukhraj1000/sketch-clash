export type HitKind = 'swipe' | 'heavy' | 'finisher';
export type BattleEvent = { id: string; at: number; attacker: 0 | 1; damage: number; kind: HitKind; word: string; explanation?: string };
export type BattleOutcome = 'knockout' | 'points' | 'tiebreak';
export type BattlePlayback = { events: readonly BattleEvent[]; duration_ms: number; winner_slot: 0 | 1; outcome?: BattleOutcome; source_label?: string };
export const BATTLE_DURATION = 12800;
export const BATTLE_EVENTS: readonly BattleEvent[] = [
  { id: 'first-strike', at: 2300, attacker: 0, damage: 18, kind: 'swipe', word: 'SWISH!' },
  { id: 'counter', at: 4050, attacker: 1, damage: 22, kind: 'heavy', word: 'WHAM!' },
  { id: 'double-down', at: 5950, attacker: 0, damage: 25, kind: 'heavy', word: 'POW!' },
  { id: 'comeback', at: 7800, attacker: 1, damage: 26, kind: 'swipe', word: 'THWACK!' },
  { id: 'the-finisher', at: 9900, attacker: 0, damage: 57, kind: 'finisher', word: 'K.O.!' },
];

const clamp = (n: number) => Math.max(0, Math.min(1, n));
const easeOut = (n: number) => 1 - Math.pow(1 - clamp(n), 3);

export function getHealth(elapsed: number, events: readonly BattleEvent[] = BATTLE_EVENTS): [number, number] {
  const health: [number, number] = [100, 100];
  for (const event of events) if (elapsed >= event.at) health[event.attacker === 0 ? 1 : 0] -= event.damage;
  return [Math.max(0, health[0]), Math.max(0, health[1])];
}

export function getImpact(elapsed: number, events: readonly BattleEvent[] = BATTLE_EVENTS): BattleEvent | undefined {
  // Closely spaced server events must show the most recent contact.
  return [...events].reverse().find(event => elapsed >= event.at && elapsed < event.at + (event.kind === 'finisher' ? 1550 : 650));
}

export function getHitFlash(elapsed: number, side: 0 | 1, reducedMotion = false, events: readonly BattleEvent[] = BATTLE_EVENTS): boolean {
  if (reducedMotion) return false;
  return events.some(event => event.attacker !== side && elapsed >= event.at && elapsed < event.at + 105);
}

export type FighterPose = { x: number; y: number; rotate: number; scaleX: number; scaleY: number; opacity: number };

/** Positions are normalised to arena width; hit-stop is authored into the timeline. */
export function getFighterPose(elapsed: number, side: 0 | 1, reducedMotion = false, events: readonly BattleEvent[] = BATTLE_EVENTS, winnerSlot: 0 | 1 = 0, outcome: BattleOutcome = 'knockout'): FighterPose {
  const dir = side === 0 ? 1 : -1;
  const pose: FighterPose = {
    x: 0, y: reducedMotion ? 0 : Math.sin(elapsed / 190 + side) * 4,
    rotate: reducedMotion ? 0 : Math.sin(elapsed / 380 + side) * 1.8,
    scaleX: 1, scaleY: 1, opacity: 1,
  };
  const finalTime = events[events.length - 1]?.at ?? BATTLE_DURATION;
  if (elapsed > finalTime + 160) {
    const progress = clamp((elapsed - finalTime - 160) / 850);
    if (side !== winnerSlot && outcome === 'knockout') {
      pose.x = reducedMotion ? 0 : -dir * 0.1 * easeOut(progress);
      pose.y = reducedMotion ? 0 : 60 * easeOut(progress);
      pose.rotate = reducedMotion ? 0 : -dir * 105 * easeOut(progress);
      pose.scaleX = 1 - progress * .66;
      pose.scaleY = 1 - progress * .78;
      pose.opacity = 1 - progress * .3;
    } else if (side === winnerSlot && !reducedMotion) {
      const jump = Math.max(0, Math.sin((elapsed - finalTime - 350) / 210));
      pose.y = -jump * 55;
      pose.rotate = Math.sin((elapsed - finalTime) / 260) * 5;
      pose.scaleY = 1 + jump * .06;
    }
    return pose;
  }
  for (const event of [...events].reverse()) {
    const relative = elapsed - event.at;
    if (relative < -440 || relative > 720) continue;
    if (event.attacker === side) {
      if (reducedMotion) {
        pose.scaleX = relative >= 0 && relative < 140 ? 1.035 : 1;
        return pose;
      }
      if (relative < -170) {
        const p = clamp((relative + 440) / 270);
        pose.x = -dir * .027 * p;
        pose.y = 5 * p;
        pose.rotate = -dir * 9 * p;
        pose.scaleX = 1 + .11 * p;
        pose.scaleY = 1 - .13 * p;
      } else if (relative < 0) {
        const p = easeOut((relative + 170) / 170);
        pose.x = dir * (-.027 + .362 * p);
        pose.y = -Math.sin(p * Math.PI) * (event.kind === 'finisher' ? 65 : 30);
        pose.rotate = dir * (-9 + 21 * p);
        pose.scaleX = 1.1;
        pose.scaleY = .93;
      } else if (relative < 105) {
        pose.x = dir * .335; pose.y = 0; pose.rotate = dir * 12; pose.scaleX = 1.1; pose.scaleY = .93;
      } else {
        const p = easeOut((relative - 105) / 570);
        pose.x = dir * .335 * (1 - p);
        pose.rotate = dir * 12 * (1 - p);
        pose.y = -Math.sin(p * Math.PI) * 20;
        pose.scaleX = 1 + .1 * (1 - p); pose.scaleY = 1 - .07 * (1 - p);
      }
    } else if (relative >= 0) {
      const p = clamp((relative - 105) / 550);
      const power = event.kind === 'finisher' ? 1.55 : 1;
      pose.x = reducedMotion ? 0 : -dir * .047 * (1 - p) * power;
      pose.y = reducedMotion ? 0 : -Math.sin(p * Math.PI) * 24;
      pose.rotate = reducedMotion ? 0 : -dir * 16 * (1 - p) * power;
      pose.scaleX = 1 - .17 * (1 - p);
      pose.scaleY = 1 + .12 * (1 - p);
    }
    return pose;
  }
  return pose;
}

export function getCameraOffset(elapsed: number, reducedMotion = false, events: readonly BattleEvent[] = BATTLE_EVENTS) {
  if (reducedMotion) return 0;
  const event = getImpact(elapsed, events);
  if (!event || event.kind === 'swipe') return 0;
  const p = (elapsed - event.at) / 330;
  return p >= 1 ? 0 : Math.sin(p * 42) * (1 - p) * (event.kind === 'finisher' ? 10 : 5);
}
