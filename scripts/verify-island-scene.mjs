import assert from 'node:assert/strict';
import { computeTaskPose, safeIslandPoint } from '../src/lib/island.ts';

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
