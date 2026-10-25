import { BATTLE_DURATION, BATTLE_EVENTS, getFighterPose, getHitFlash } from './battle.ts';
import type { BattleEvent, BattleOutcome } from './battle.ts';

export type BattleFighter3DPose = {
  x: number; y: number; z: number;
  rotationX: number; rotationY: number; rotationZ: number; scale: number;
  armLeftX: number; armLeftZ: number; armRightX: number; armRightZ: number;
  footLeftX: number; footRightX: number; blink: number; flash: boolean;
  action: 'idle' | 'windup' | 'attack' | 'hit' | 'win' | 'defeated';
};

const clamp = (value: number) => Math.max(0, Math.min(1, value));

/** Presentation only. The arena's existing visible-time clock supplies the
 * authored 12.8-second coordinate; this never advances time or changes combat. */
export function getBattleFighter3DPose(elapsed: number, side: 0 | 1, reduced = false,
  events: readonly BattleEvent[] = BATTLE_EVENTS, winnerSlot: 0 | 1 = 0,
  outcome: BattleOutcome = 'knockout'): BattleFighter3DPose {
  const now = Number.isFinite(elapsed) ? Math.max(0, elapsed) : 0;
  // Freeze the whole rig, including idle gestures and blinking, for 105 ms.
  // A newer contact takes priority when recorded events overlap that window.
  const contact = [...events].reverse().find(event => now >= event.at && now < event.at + 105);
  const time = contact?.at ?? now;
  const direction = side === 0 ? 1 : -1;
  const finalTime = events.at(-1)?.at ?? BATTLE_DURATION;
  const finished = events.length > 0 && time > finalTime + 160;
  const current = contact ?? [...events].reverse().find(event => time >= event.at - 440 && time <= event.at + 720);
  const relative = current ? time - current.at : 0;
  let action: BattleFighter3DPose['action'] = 'idle';
  if (finished) action = side === winnerSlot ? 'win' : outcome === 'knockout' ? 'defeated' : 'idle';
  else if (current) {
    if (current.attacker === side) action = relative < -170 ? 'windup' : 'attack';
    else if (relative >= 0) action = 'hit';
  }
  const pose: BattleFighter3DPose = {
    x: -direction * 2.3, y: 0, z: 0,
    rotationX: 0, rotationY: direction * .55, rotationZ: 0, scale: 1,
    armLeftX: 0, armLeftZ: -.22, armRightX: 0, armRightZ: .22,
    footLeftX: 0, footRightX: 0, blink: 1, flash: false, action,
  };
  if (reduced) return pose;

  const legacy = getFighterPose(time, side, false, events, winnerSlot, outcome);
  pose.x += legacy.x * 9.2;
  pose.y = Math.max(0, -legacy.y / 140);
  pose.rotationZ = -legacy.rotate * Math.PI / 180;
  pose.flash = getHitFlash(time, side, false, events);
  const beat = Math.sin(time / 140 + side * Math.PI);
  const blinkPhase = (time / 1000 + side * .7) % 4.8;
  pose.blink = blinkPhase > 4.58 ? Math.max(.12, Math.abs(blinkPhase - 4.69) / .11) : 1;
  pose.armLeftX = -.45 + beat * .07;
  pose.armRightX = -.45 - beat * .07;
  pose.armLeftZ = -.34;
  pose.armRightZ = .34;

  if (action === 'windup') {
    const windup = clamp((relative + 440) / 270);
    pose.armLeftX = side === 0 ? -.7 : .55 * windup;
    pose.armRightX = side === 0 ? .55 * windup : -.7;
    pose.rotationX = -.08 * windup;
    pose.rotationY = direction * (.55 - .2 * windup);
    pose.footLeftX = -.2 * windup;
    pose.footRightX = .2 * windup;
  } else if (action === 'attack') {
    const extension = relative < 0 ? clamp((relative + 170) / 170)
      : 1 - clamp((relative - 105) / 570);
    pose.armLeftX = side === 0 ? -.8 : .55 - extension * 2.2;
    pose.armRightX = side === 0 ? .55 - extension * 2.2 : -.8;
    if (side === 0) pose.armRightZ = .12;
    else pose.armLeftZ = -.12;
    pose.rotationX = .12 * extension;
    pose.rotationY = direction * (.55 + .65 * extension);
    pose.footLeftX = beat * .38;
    pose.footRightX = -beat * .38;
  } else if (action === 'hit') {
    const recoil = 1 - clamp((relative - 105) / 550);
    pose.armLeftX = -1.1 * recoil;
    pose.armRightX = -1.1 * recoil;
    pose.armLeftZ = -.55;
    pose.armRightZ = .55;
    pose.rotationX = -.12 * recoil;
    pose.rotationY = direction * (.55 - .2 * recoil);
    pose.footLeftX = -.2 * recoil;
    pose.footRightX = .2 * recoil;
  } else if (action === 'win') {
    pose.armLeftZ = -2.4 + beat * .12;
    pose.armRightZ = 2.4 - beat * .12;
    pose.armLeftX = pose.armRightX = -.2;
    pose.footLeftX = beat * .18;
    pose.footRightX = -beat * .18;
  } else if (action === 'defeated') {
    pose.scale = 1 - .2 * clamp((time - finalTime - 160) / 850);
    pose.armLeftX = pose.armRightX = 0;
    pose.armLeftZ = -.4;
    pose.armRightZ = .4;
    pose.blink = .3;
  }
  return pose;
}
