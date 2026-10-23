import assert from 'node:assert/strict';
// Native type stripping (Node 22.18+): no runner, browser or generated files.
import { BATTLE_DURATION, BATTLE_EVENTS, getHealth, getImpact, getFighterPose, getCameraOffset, getHitFlash } from '../src/game/battle.ts';

assert.ok(BATTLE_DURATION >= 10_000 && BATTLE_DURATION <= 15_000, 'Fight must last 10–15 seconds');
assert.ok(BATTLE_EVENTS.at(-1).at < BATTLE_DURATION, 'Final impact must leave room for the KO');
assert.deepEqual(getHealth(0), [100, 100], 'A fresh round starts at full health');
assert.deepEqual(getHealth(BATTLE_DURATION), [52, 0], 'Player 1 must win the scripted round');

let previousHealth = getHealth(0);
let checkedFrames = 0;
for (let time = 0; time <= BATTLE_DURATION; time += 5) {
  const health = getHealth(time);
  for (const side of [0, 1]) {
    assert.ok(health[side] >= 0 && health[side] <= 100, `Health is bounded at ${time}ms`);
    assert.ok(health[side] <= previousHealth[side], `Health cannot recover at ${time}ms`);
    const pose = getFighterPose(time, side);
    const reduced = getFighterPose(time, side, true);
    assert.ok(Object.values(pose).every(Number.isFinite), `All transforms are finite at ${time}ms`);
    assert.ok(Object.values(reduced).every(Number.isFinite), `Reduced-motion transforms are finite at ${time}ms`);
    assert.ok(pose.scaleX > 0 && pose.scaleY > 0, `Fighters never invert or disappear at ${time}ms`);
    assert.ok(pose.opacity >= 0 && pose.opacity <= 1, `Opacity is valid at ${time}ms`);
    assert.equal(reduced.x, 0, `Reduced motion disables lunges at ${time}ms`);
    assert.equal(reduced.y, 0, `Reduced motion disables bouncing at ${time}ms`);
    assert.equal(reduced.rotate, 0, `Reduced motion disables spinning at ${time}ms`);
    assert.equal(getHitFlash(time, side, true), false, `Reduced motion disables hit flashes at ${time}ms`);
  }
  assert.ok(Number.isFinite(getCameraOffset(time)), `Camera offset is finite at ${time}ms`);
  assert.equal(getCameraOffset(time, true), 0, `Reduced motion disables camera shake at ${time}ms`);
  previousHealth = health;
  checkedFrames++;
}

for (const event of BATTLE_EVENTS) {
  const defender = event.attacker === 0 ? 1 : 0;
  assert.equal(getImpact(event.at)?.id, event.id, `Impact starts at the contact frame: ${event.id}`);
  assert.notEqual(getImpact(event.at - 1)?.id, event.id, `Impact cannot start early: ${event.id}`);
  assert.equal(getHealth(event.at)[defender], getHealth(event.at - 1)[defender] - event.damage, `Damage lands exactly on contact: ${event.id}`);
  assert.equal(getHitFlash(event.at - 1, defender), false, 'Defender must not flash before contact');
  assert.equal(getHitFlash(event.at, defender), true, 'Defender flashes on contact');
  assert.equal(getHitFlash(event.at, event.attacker), false, 'Attacker does not receive a hit flash');
  assert.equal(getHitFlash(event.at + 105, defender), false, 'Hit flash ends with the freeze');
  for (const side of [0, 1]) {
    assert.deepEqual(getFighterPose(event.at, side), getFighterPose(event.at + 100, side), `Both drawings freeze on contact: ${event.id}`);
  }
}

// Reading a completed fight must not leak health or mutate future replays.
getHealth(BATTLE_DURATION);
const fresh = getHealth(0);
assert.deepEqual(fresh, [100, 100], 'Replay begins from fresh health');
fresh[0] = 1;
assert.deepEqual(getHealth(0), [100, 100], 'Returned snapshots cannot mutate future rounds');
assert.equal(getImpact(BATTLE_DURATION), undefined, 'All impact effects finish before the scene exits');
console.log(`Combat checks passed: ${checkedFrames} timeline samples, ${BATTLE_EVENTS.length} contacts, monotonic health, fixed winner, fresh replay, hit-stop, flashes and reduced motion.`);
