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

// Recorded server fights can be denser than the five-hit demo and either slot can win.
for (const count of [7, 11, 15]) {
  const events = Array.from({ length: count }, (_, index) => ({
    id: `recorded-${index}`, at: 1600 + Math.round(index * 8300 / (count - 1)),
    attacker: index === count - 1 ? 1 : index % 2,
    damage: index === count - 1 ? 100 - Math.floor((count - 1) / 2) * 9 : 9,
    kind: index === count - 1 ? 'finisher' : 'swipe', word: index === count - 1 ? 'K.O.!' : 'POW!',
  }));
  const health = [100, 100];
  for (const event of events) {
    health[1 - event.attacker] -= event.damage;
    assert.deepEqual(getHealth(event.at, events), health, `Recorded damage matches contact for ${count} hits`);
    assert.equal(getImpact(event.at, events)?.id, event.id, 'The latest contact takes priority over an older impact');
  }
  assert.deepEqual(getHealth(BATTLE_DURATION, events), health);
  assert.equal(health[0], 0, 'Player 2 can win an authoritative battle');
  assert.ok(health[1] > 0, 'The recorded winner retains health');
  assert.ok(getFighterPose(BATTLE_DURATION, 0, false, events, 1).opacity < 1, 'Player 1 receives the loser choreography');
  assert.equal(getFighterPose(BATTLE_DURATION, 1, false, events, 1).opacity, 1, 'Player 2 retains the winning pose');
  for (let t = 0; t <= BATTLE_DURATION; t += 20) {
    for (const slot of [0, 1]) {
      assert.ok(Object.values(getFighterPose(t, slot, false, events, 1)).every(Number.isFinite));
      const reduced = getFighterPose(t, slot, true, events, 1);
      assert.equal(reduced.x, 0); assert.equal(reduced.y, 0); assert.equal(reduced.rotate, 0);
    }
  }
  const quickEvents = events.map(event => ({ ...event, at: event.at / 2 }));
  for (const event of quickEvents) {
    assert.deepEqual(getHealth(event.at, quickEvents), getHealth(event.at * 2, events), 'Quick and normal playback agree on contact health');
  }
}
console.log('Authoritative replay checks passed: 7/11/15 hits, either winner, exact contact health, quick playback and reduced motion.');

const { startTimeline } = await import('../src/game/director.ts');
const queuedFrames = new Map();
let frameId = 0, hidden = false, visibilityListener, completions = 0;
const sampledTimes = [];
const environment = {
  requestFrame: callback => { queuedFrames.set(++frameId, callback); return frameId; },
  cancelFrame: id => queuedFrames.delete(id),
  isHidden: () => hidden,
  subscribeVisibility: callback => { visibilityListener = callback; return () => { visibilityListener = undefined; }; },
};
const flushFrame = now => { const callbacks = [...queuedFrames.values()]; queuedFrames.clear(); callbacks.forEach(callback => callback(now)); };
const dispose = startTimeline(1000, time => sampledTimes.push(time), () => completions++, environment);
flushFrame(100); flushFrame(500);
assert.equal(sampledTimes.at(-1), 400);
hidden = true; visibilityListener();
assert.equal(queuedFrames.size, 0, 'Hidden scenes cancel RAF rather than run in the background');
flushFrame(10500);
assert.equal(completions, 0, 'Hidden time cannot complete a fight or trigger finalization');
hidden = false; visibilityListener();
flushFrame(11000); flushFrame(11500);
assert.equal(sampledTimes.at(-1), 900, 'Resume excludes all hidden time');
flushFrame(11600); flushFrame(20000);
assert.equal(completions, 1, 'The scene completes once after enough visible playback');
dispose();
assert.equal(visibilityListener, undefined, 'Unmount cleans up visibility listeners');
const cancel = startTimeline(1000, () => {}, () => completions++, environment);
flushFrame(22000); cancel(); flushFrame(24000);
assert.equal(completions, 1, 'An exited or replayed scene cannot fire a stale completion');
assert.equal(queuedFrames.size, 0);
console.log('Timeline checks passed: hidden-page pause, visible-time resume, exactly-once completion and cancellation cleanup.');
