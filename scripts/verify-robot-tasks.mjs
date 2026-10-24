import assert from 'node:assert/strict';
import { robotTaskState, robotWorkPose, robotWheelAngle, advanceRobotWheels } from '../src/components/robotMotion.ts';
import { displayIslandPoint, residentDisplaySlots } from '../src/components/objectPresentation.ts';

// Saved API-shaped fixtures only: no backend, mutable world or paid model calls.
const started = Date.parse('2026-10-24T16:00:00Z');
const duration = 20_000;
const arrival = started + duration * .45;
const frozen = value => {
  if (value && typeof value === 'object') { Object.values(value).forEach(frozen); Object.freeze(value); }
  return value;
};
const task = frozen({
  id: 'local-build-task', kind: 'build', title: 'Build the shared workshop',
  started_at: new Date(started).toISOString(), ends_at: new Date(started + duration).toISOString(), duration_seconds: 20,
  from: { x: -3.25, z: 1.2 }, to: { x: 2.1, z: -1.5 },
  resource: null, project_id: 'workshop', gain: {}, progress_gain: 3,
  scheduling_reason: 'The crew has enough materials for the approved workshop.',
  requested_action: 'build', requested_decision_id: 'local-approved-decision', action_switched: false,
});
const original = JSON.stringify(task);
const location = state => ({ x: state.x, z: state.z });

for (const time of [started - 10_000, started]) {
  const state = robotTaskState(task, task.from, time);
  assert.equal(state.phase, 'scheduled', 'A future task cannot become an active job early');
  assert.equal(state.label, 'Preparing');
  assert.equal(state.working, false);
  assert.equal(state.travelling, false);
  assert.deepEqual(location(state), task.from);
  assert.equal(robotWheelAngle(task, task.from, time), 0, 'Wheels remain still until actual travel begins');
}
let previous = robotTaskState(task, task.from, started);
let previousWheel = 0;
let samples = 0;
for (let time = started + 50; time < arrival; time += 50) {
  const state = robotTaskState(task, task.from, time);
  const wheel = robotWheelAngle(task, task.from, time);
  assert.equal(state.phase, 'travelling');
  assert.equal(state.label, 'To build site');
  assert.equal(state.working, false, 'Robots cannot build while travelling to their station');
  assert.ok(state.progress > previous.progress);
  assert.ok(Math.hypot(state.x - previous.x, state.z - previous.z) < .06, 'Travel is continuous');
  assert.ok(wheel > previousWheel, 'Wheels roll only as the robot travels');
  previous = state; previousWheel = wheel; samples++;
}
const working = robotTaskState(task, task.from, arrival);
assert.equal(working.phase, 'working');
assert.equal(working.label, 'Assembling');
assert.equal(working.travelling, false);
assert.ok(Math.hypot(working.x - task.to.x, working.z - task.to.z) < 1e-10, 'Work begins only at the saved destination');
const wheelAtStation = robotWheelAngle(task, task.from, arrival);
assert.ok(wheelAtStation > 0);
let wheels = advanceRobotWheels({ distanceAngle: 0, angle: 0 }, task.id, wheelAtStation);
assert.equal(wheels.angle, wheelAtStation);
wheels = advanceRobotWheels(wheels, 'next-task', 0);
assert.equal(wheels.angle, wheelAtStation, 'A newly scheduled job cannot snap wheels back to their starting orientation');
wheels = advanceRobotWheels(wheels, 'next-task', .8);
assert.equal(wheels.angle, wheelAtStation + .8, 'A new journey continues the existing wheel rotation');
assert.deepEqual(advanceRobotWheels(wheels, 'next-task', .8), wheels, 'Repeated and paused snapshots do not spin wheels');
const slots = residentDisplaySlots(['one', 'two', 'three', 'four']);
for (const slot of slots.values()) for (const point of [{ x: -.25, z: -2.9 }, { x: 3.65, z: .55 }, { x: 2.1, z: -.5 }]) {
  const displayed = displayIslandPoint(point, slot);
  assert.ok(Math.hypot(displayed.x - point.x, displayed.z - point.z) < .7, 'Workers stay beside the actual station instead of retaining the wide standby spread');
}
for (const time of [arrival + 100, started + duration - 1, started + duration, started + 180_000]) {
  assert.equal(robotWheelAngle(task, task.from, time), wheelAtStation, 'Stationary wheels cannot keep rotating during or after work');
}
for (const time of [started + duration, started + 180_000]) {
  const state = robotTaskState(task, task.from, time);
  assert.equal(state.phase, 'settling');
  assert.equal(state.label, 'Awaiting receipt', 'An expired local timer is not evidence of a committed contribution');
  assert.equal(state.working, false, 'A stale task stops its work gesture while awaiting the server');
  assert.equal(state.travelling, false);
  assert.ok(Math.hypot(state.x - task.to.x, state.z - task.to.z) < 1e-10);
  assert.equal(Object.hasOwn(state, 'gain'), false, 'Task display cannot present planned yield as recorded output');
  assert.equal(Object.hasOwn(state, 'receipt_id'), false, 'A visual timeline cannot invent a receipt');
}

const rest = frozen({ ...task, id: 'local-standby-task', kind: 'rest', title: 'Wait for a useful crew request',
  to: { x: -.7, z: 1.1 }, project_id: null, progress_gain: 0,
  scheduling_reason: 'Storage is full and the crew has no pending build.' });
const returning = robotTaskState(rest, rest.from, started + 4_000);
assert.equal(returning.phase, 'travelling');
assert.equal(returning.label, 'Returning to standby');
assert.equal(returning.working, false, 'Returning to a rest point is transport, not productive work');
for (const time of [arrival, started + duration, started + 180_000]) {
  const state = robotTaskState(rest, rest.from, time);
  assert.equal(state.phase, 'waiting');
  assert.equal(state.label, 'Waiting for work');
  assert.equal(state.working, false);
}
for (const absent of [null, undefined]) for (const time of [started, started + 180_000]) {
  const state = robotTaskState(absent, task.from, time);
  assert.equal(state.phase, 'waiting');
  assert.deepEqual(location(state), task.from, 'No saved task means no invented patrol');
  assert.equal(state.working, false);
  assert.equal(state.travelling, false);
  assert.equal(robotWheelAngle(absent, task.from, time), 0);
}

// Pausing freezes the existing server clock; it must not relabel work as completed.
const frozenTime = started + 12_000;
const paused = robotTaskState(task, task.from, frozenTime, true);
assert.equal(paused.phase, 'paused');
assert.equal(paused.label, 'Paused');
for (let frame = 0; frame < 100; frame++) {
  assert.deepEqual(robotTaskState(task, task.from, frozenTime, true), paused, 'A frozen authoritative time gives a stable paused pose');
  assert.equal(robotWheelAngle(task, task.from, frozenTime), wheelAtStation);
}
assert.equal(robotTaskState(task, task.from, frozenTime, false).phase, 'working', 'Resuming the same saved job retains its phase');

const kinds = ['carry', 'forage', 'water', 'tend', 'plan', 'measure', 'charge', 'signal', 'build', 'explore', 'rest'];
const idle = robotWorkPose(undefined, false, false, 0);
let mechanicalSamples = 0;
for (const kind of kinds) {
  assert.deepEqual(robotWorkPose(kind, false, false, 100), idle, 'An inactive task cannot keep its arms working');
  if (!['carry', 'forage'].includes(kind)) {
    assert.deepEqual(robotWorkPose(kind, false, true, 100), idle, `${kind} tools are stowed during travel`);
  } else {
    assert.notDeepEqual(robotWorkPose(kind, false, true, 100), idle, 'A carrier holds its tray while actually travelling');
    assert.deepEqual(robotWorkPose(kind, false, true, 0), robotWorkPose(kind, false, true, 100), 'Travel carries the tray steadily instead of pantomiming output');
  }
  for (let seconds = 0; seconds <= 120; seconds += .25) {
    const pose = robotWorkPose(kind, true, false, seconds);
    assert.ok(Object.values(pose).every(Number.isFinite), 'All mechanical transforms remain finite');
    assert.ok(Math.abs(pose.leftArmX) <= 1.2 && Math.abs(pose.rightArmX) <= 1.2, 'Arms stay within the manipulator range');
    assert.ok(Math.abs(pose.toolX) < .1 && Math.abs(pose.toolY) < .1 && Math.abs(pose.toolZ) < .1, 'Work gestures stay at the station instead of inventing travel');
    mechanicalSamples++;
  }
  assert.deepEqual(robotWorkPose(kind, true, false, 0, true), robotWorkPose(kind, true, false, 120, true), 'Reduced-motion work poses remain stable across time');
  assert.deepEqual(robotWorkPose(kind, true, false, NaN), robotWorkPose(kind, true, false, 0), 'An invalid animation clock cannot corrupt a robot');
  assert.deepEqual(robotWorkPose(kind, true, false, Infinity), robotWorkPose(kind, true, false, 0));
}
const drill = robotWorkPose('build', true, false, 1);
const scan = robotWorkPose('measure', true, false, 1);
const plan = robotWorkPose('plan', true, false, 1);
const nozzle = robotWorkPose('water', true, false, 1);
assert.ok(drill.toolSpin > 0 && scan.toolSpin === 0 && nozzle.toolTilt < 0, 'Drilling, measuring and watering use their actual distinct tools');
assert.notDeepEqual(scan, plan, 'Planning and measuring are visibly different jobs');
assert.notDeepEqual(drill, nozzle, 'Building cannot be displayed as watering');
assert.deepEqual(robotWorkPose('rest', false, false, 2), idle);
assert.deepEqual(robotWorkPose(undefined, false, false, 2), idle);
assert.equal(JSON.stringify(task), original, 'Animation and labels cannot mutate saved task data');
console.log(`Robot task checks passed: ${samples} travel samples, authoritative work/standby/receipt phases, stationary wheels, paused clocks and ${mechanicalSamples} bounded task-specific mechanical poses.`);
