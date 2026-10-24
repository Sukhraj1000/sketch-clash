import assert from 'node:assert/strict';
import { computeTaskPose, safeIslandPoint } from '../src/lib/island.ts';
import { objectSilhouette } from '../src/components/objectIdentity.ts';
import { objectPose } from '../src/components/objectMotion.ts';

const start = Date.parse('2026-10-24T10:00:00Z');
const task = { id: 'fixture-task', kind: 'build', title: 'Build the garden', started_at: new Date(start).toISOString(), ends_at: new Date(start + 16000).toISOString(), duration_seconds: 16, from: { x: -3.25, z: 1.2 }, to: { x: -2.1, z: -.7 }, gain: {}, progress_gain: 1 };
const before = structuredClone(task);
let previous = computeTaskPose(task, task.from, start - 1000);
assert.equal(previous.progress, 0);
assert.deepEqual({ x: previous.x, z: previous.z }, task.from, 'A task cannot start before the authoritative start time');
let samples = 0;
for (let t = start; t <= start + 20000; t += 25) {
  const pose = computeTaskPose(task, task.from, t);
  assert.ok([pose.x, pose.z, pose.progress, pose.heading].every(Number.isFinite));
  assert.ok(Math.hypot(pose.x, pose.z) <= 5.5, 'All positions stay on the island');
  assert.ok(pose.progress >= previous.progress && pose.progress <= 1);
  assert.ok(Math.hypot(pose.x - previous.x, pose.z - previous.z) < .04, 'Travel remains continuous across frames');
  if (pose.working) assert.deepEqual({ x: pose.x, z: pose.z }, task.to, 'Work starts only after reaching the server workspot');
  previous = pose;
  samples++;
}
assert.equal(previous.working, false, 'A finished task does not invent further work while waiting for the server');
assert.equal(previous.travelling, false);
assert.deepEqual(task, before, 'Animation reads cannot mutate authoritative task state');
const frozen = computeTaskPose(task, task.from, start + 5000);
assert.deepEqual(frozen, computeTaskPose(task, task.from, start + 5000), 'Paused server time produces the same pose on every render');
assert.deepEqual(computeTaskPose({ ...task, ends_at: 'invalid' }, task.from, start), { ...task.from, progress: 0, travelling: false, working: false, heading: 0 });
for (const point of [{ x: 100, z: -100 }, { x: NaN, z: Infinity }, { x: 0, z: 0 }]) {
  const safe = safeIslandPoint(point);
  assert.ok(Number.isFinite(safe.x) && Number.isFinite(safe.z));
  assert.ok(Math.hypot(safe.x, safe.z) <= 5.5000001);
}
console.log(`Island scene checks passed: ${samples} authoritative timeline samples, continuous bounded travel, no early work, paused time, malformed input and immutable state.`);

for (const [label, expected] of [['pencil','pencil'],['ballpoint pen','pen'],['metal ruler','ruler'],['smartphone','phone'],['desk lamp','lamp'],['AA battery','battery'],['running shoe','shoe'],['pair of scissors','scissors'],['teaspoon','spoon'],['house key','keys'],['water pitcher','pitcher'],['kitten','cat'],['puppy','dog'],['toy rabbit','rabbit'],['teddy bear','bear'],['rubber duck','duck']]) {
  assert.equal(objectSilhouette('generic', label), expected, `Accepted ${label} identity has a recognizable silhouette`);
}
for (const label of ['animal','toy','pencil case','phone charger','not a cat','mystery object','coin cell','Sir Pencil Hero']) {
  assert.equal(objectSilhouette('generic',label),null, `Ambiguous/unsupported ${label} remains an honest photo card`);
}
assert.equal(objectSilhouette('book','TV','television'),'television','Accepted TV identity upgrades a coarse legacy book template');
assert.equal(objectSilhouette('generic','computer monitor'),'television','A monitor has a display and stand');
assert.equal(objectSilhouette('book','microwave','microwave oven'),'microwave','Accepted microwave identity upgrades coarse legacy geometry');
assert.equal(objectSilhouette('bottle','water pitcher','pitcher'),'pitcher','A pitcher gains its spout and handle despite an old bottle template');
assert.equal(objectSilhouette('mug','pencil','pencil'),'pencil','Exact accepted identity can upgrade any coarse supported template');
assert.equal(objectSilhouette('book','book','book'),null,'A genuine book retains its original book template');
assert.equal(objectSilhouette('book','mystery object'),null,'Unknown identity does not override an existing template');
assert.equal(objectSilhouette('book','TV','book'),null,'Conflicting known legacy and new identities keep the existing presentation');
assert.equal(objectSilhouette('generic','TV remote'),null,'Related objects are not inferred from substrings');
assert.equal(objectSilhouette('generic','Lord Television'),null,'Creative nicknames cannot invent an accepted identity');
assert.equal(objectSilhouette('generic','ruler','phone'),null,'Conflicting accepted identities cannot pick a convenient silhouette');
assert.equal(objectSilhouette('generic',undefined,'wooden-pencil'),'pencil','Known canonical identities can supply a missing display label');
const workKinds = [undefined,'forage','carry','water','plan','measure','charge','signal','tend','build','rest','explore'];
let poses = 0;
for (const style of ['calm','bouncy','wobbly']) for (const activity of ['idle','rest','wander']) for (const work of workKinds) {
  for (let milliseconds = 0; milliseconds <= 30000; milliseconds += 50) {
    const pose = objectPose(style,activity,milliseconds/1000,.6,false,work);
    assert.ok(Object.values(pose).every(Number.isFinite),'Every body and limb transform remains finite');
    assert.ok(Math.abs(pose.y)<.15 && Math.abs(pose.roll)<.15 && Math.abs(pose.pitch)<.3,'Body movement stays bounded');
    assert.ok(pose.scaleY>.9 && pose.scaleY<=1.02 && pose.blink>=.08 && pose.blink<=1,'Characters and eyes never invert or disappear');
    assert.ok(Math.abs(pose.leftArmZ)<=2.2 && Math.abs(pose.rightArmZ)<=2.2,'Arm gestures stay inside the supported rig');
    poses++;
  }
  assert.deepEqual(objectPose(style,activity,0,.6,true,work),objectPose(style,activity,100,.6,true,work),'Reduced motion/paused poses do not drift or blink');
}
assert.deepEqual(objectPose('calm','idle',NaN,Infinity),objectPose('calm','idle',0,0),'Invalid clocks cannot poison scene transforms');
assert.notDeepEqual(objectPose('calm','idle',1,0,false,'plan'),objectPose('calm','idle',1,0,false,'measure'),'Different jobs produce distinct gestures');
console.log(`Object presentation checks passed: supported and conservative identity mapping; ${poses} finite bounded limb/blink/work poses; motion-disabled stability.`);
