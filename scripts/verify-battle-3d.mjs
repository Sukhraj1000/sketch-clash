import assert from 'node:assert/strict';
import { BATTLE_DURATION, BATTLE_EVENTS, getFighterPose, getHealth } from '../src/game/battle.ts';
import { getBattleFighter3DPose } from '../src/game/battle3d.ts';

const immutableEvents = JSON.stringify(BATTLE_EVENTS);
const numeric = pose => Object.values(pose).filter(value => typeof value === 'number');
const presentation = ({ action, ...pose }) => pose;
let samples = 0;
for (const outcome of ['knockout', 'points', 'tiebreak']) for (const winner of [0, 1]) {
  for (const side of [0, 1]) {
    const reducedStart = presentation(getBattleFighter3DPose(0, side, true, BATTLE_EVENTS, winner, outcome));
    for (let time = 0; time <= BATTLE_DURATION; time += 5) {
      const healthBefore = getHealth(time);
      const pose = getBattleFighter3DPose(time, side, false, BATTLE_EVENTS, winner, outcome);
      assert.ok(numeric(pose).every(Number.isFinite), `Finite 3D transforms at ${time}`);
      assert.ok(pose.y >= 0, 'The rig never sinks below its rest floor');
      assert.ok(pose.scale >= .8 && pose.scale <= 1, 'Object scale is a bounded uniform scalar');
      if (pose.action !== 'defeated') assert.equal(pose.scale, 1, 'Rigid objects never squash or stretch');
      if (pose.action === 'defeated') assert.equal(outcome, 'knockout', 'Only a recorded knockout defeats a rig');
      assert.deepEqual(presentation(getBattleFighter3DPose(time, side, true, BATTLE_EVENTS, winner, outcome)),
        reducedStart, 'Reduced motion keeps all transforms, limbs, blink and flash fixed');
      assert.deepEqual(getHealth(time), healthBefore, '3D presentation cannot change recorded damage');
      samples++;
    }
  }
  const endWinner = getBattleFighter3DPose(BATTLE_DURATION, winner, false, BATTLE_EVENTS, winner, outcome);
  const endLoser = getBattleFighter3DPose(BATTLE_DURATION, 1 - winner, false, BATTLE_EVENTS, winner, outcome);
  assert.equal(endWinner.action, 'win');
  assert.equal(endWinner.scale, 1, 'Either recorded winner remains full size and visible');
  assert.equal(endLoser.action, outcome === 'knockout' ? 'defeated' : 'idle');
  if (outcome !== 'knockout') {
    assert.equal(endLoser.scale, 1);
    assert.ok(Math.abs(endLoser.rotationZ) < .04, 'A points/tiebreak runner-up remains upright');
  }
}

for (const event of BATTLE_EVENTS) {
  for (const side of [0, 1]) {
    const contact = getBattleFighter3DPose(event.at, side);
    for (const offset of [1, 50, 100, 104.999]) {
      assert.deepEqual(getBattleFighter3DPose(event.at + offset, side), contact,
        'The entire rig, including limbs, blink and flash, freezes for the full contact window');
    }
    assert.equal(contact.flash, side !== event.attacker, 'Only the struck fighter flashes');
    assert.equal(getBattleFighter3DPose(event.at + 105, side).flash, false, 'Flash ends exactly after 105ms');
    assert.notDeepEqual(getBattleFighter3DPose(event.at + 106, side), contact, 'The rig resumes after hit-stop');
    const old = getFighterPose(event.at, side);
    assert.equal(contact.x, (side === 0 ? -2.3 : 2.3) + old.x * 9.2, 'Contacts share the authored arena positions');
    assert.equal(contact.y, Math.max(0, -old.y / 140));
    assert.equal(contact.rotationZ, -old.rotate * Math.PI / 180);
  }
  assert.equal(getBattleFighter3DPose(event.at - 200, event.attacker).action, 'windup');
  assert.equal(getBattleFighter3DPose(event.at, event.attacker).action, 'attack');
  assert.equal(getBattleFighter3DPose(event.at, 1 - event.attacker).action, 'hit');
  const direction = event.attacker === 0 ? 1 : -1;
  const windup = getBattleFighter3DPose(event.at - 200, event.attacker);
  const attack = getBattleFighter3DPose(event.at, event.attacker);
  const recoil = getBattleFighter3DPose(event.at, 1 - event.attacker);
  assert.ok(windup.rotationY * direction < .55, 'Windup turns the body away before the punch');
  assert.ok(attack.rotationY * direction > 1.1, 'Either attacker visibly turns toward the opponent');
  assert.ok(recoil.rotationY * -direction < .55, 'The defender recoils away from the contact');
  const leadArm = event.attacker === 0 ? 'armRightX' : 'armLeftX';
  const guardArm = event.attacker === 0 ? 'armLeftX' : 'armRightX';
  assert.ok(windup[leadArm] > 0 && attack[leadArm] < -1.5, 'Both mirrored leading arms extend from windup into the punch');
  assert.ok(attack[leadArm] < attack[guardArm], 'The leading arm punches farther than the guarded arm');
  assert.equal(attack[event.attacker === 0 ? 'armRightZ' : 'armLeftZ'], event.attacker === 0 ? .12 : -.12);
}

// Saved fights can have closely spaced hits and either recorded winner. A new
// contact must replace an older freeze rather than suppress the second action.
const overlap = [
  { id: 'left', at: 1000, attacker: 0, damage: 12, kind: 'heavy', word: 'POW!' },
  { id: 'right', at: 1050, attacker: 1, damage: 9, kind: 'swipe', word: 'BOP!' },
];
assert.equal(getBattleFighter3DPose(1050, 1, false, overlap).action, 'attack');
assert.equal(getBattleFighter3DPose(1050, 0, false, overlap).action, 'hit');
for (const side of [0, 1]) {
  assert.deepEqual(getBattleFighter3DPose(1154.999, side, false, overlap), getBattleFighter3DPose(1050, side, false, overlap));
  assert.equal(getBattleFighter3DPose(1155, side, false, overlap).flash, false);
  for (const invalidTime of [NaN, Infinity, -100]) assert.deepEqual(getBattleFighter3DPose(invalidTime, side), getBattleFighter3DPose(0, side));
  assert.equal(getBattleFighter3DPose(BATTLE_DURATION, side, false, []).action, 'idle', 'Empty histories invent no winner choreography');
}
const doubleKO = [
  { id: 'paired-left', at: 9900, attacker: 0, damage: 100, kind: 'finisher', word: 'K.O.!' },
  { id: 'paired-right', at: 10400, attacker: 1, damage: 100, kind: 'finisher', word: 'K.O.!' },
];
assert.deepEqual(getHealth(BATTLE_DURATION, doubleKO), [0, 0]);
assert.equal(getBattleFighter3DPose(BATTLE_DURATION, 0, false, doubleKO, 0, 'tiebreak').action, 'win');
assert.equal(getBattleFighter3DPose(BATTLE_DURATION, 1, false, doubleKO, 0, 'tiebreak').action, 'idle');
assert.equal(JSON.stringify(BATTLE_EVENTS), immutableEvents, 'Pose sampling never mutates saved events');
console.log(`3D battle poses passed: ${samples} samples, rigid models, exact whole-rig hit-stop, both winners/outcomes, overlapping contacts, replay safety and reduced motion.`);
