import assert from 'node:assert/strict';
import {
  addPlaygroundObject, advancePlayground, BLUEPRINTS, createPlayground, islandValue,
  MAX_CREW, OBJECTS, objectDefinition, playgroundCharacters, playgroundScene, projectGaps,
  RESOURCE_ORDER, STORAGE_LIMIT,
} from '../src/lib/playground.ts';
import { objectSilhouette } from '../src/components/objectIdentity.ts';

const initial = createPlayground();
const initialCopy = structuredClone(initial);
assert.equal(initial.islands[0].activeProject, 'boardwalk', 'Without water or energy carriers, choose a useful build the crew can finish');
assert.equal(initial.islands[1].activeProject, 'garden', 'A different crew chooses a different feasible build');
assert.deepEqual(projectGaps(initial.islands[0], 'garden').capabilities, ['water']);

const paused = { ...initial, paused: true };
assert.equal(advancePlayground(paused, 30), paused, 'Paused simulation does no work');
const pausedArrival = addPlaygroundObject(paused, 'sunrise', 'battery');
assert.equal(pausedArrival.islands[0].activeProject, 'workshop', 'Arrival re-evaluates available skills even while paused');
assert.equal(pausedArrival.seconds, 0);
assert.deepEqual(pausedArrival.islands.map(island => island.resources), paused.islands.map(island => island.resources), 'Arrival while paused cannot spend or generate resources');
assert.equal(pausedArrival.islands[0].residents.at(-1).task, null, 'A paused arrival does not start work');

let funds = advancePlayground(initial, 16);
const funded = funds.islands[0];
assert.equal(funded.projects.find(project => project.id === 'boardwalk').status, 'building');
assert.equal(funded.resources.materials, 0, 'Six gathered materials pay the six-material foundation exactly once');
assert.equal(funded.resources.ideas, 2, 'Four gathered plans minus the two-plan cost leaves two');
const arrivesDuringBuild = addPlaygroundObject(funds, 'sunrise', 'battery');
assert.equal(arrivesDuringBuild.islands[0].activeProject, 'boardwalk', 'Do not abandon a funded project and lose its reserved resources');
assert.ok(arrivesDuringBuild.islands[0].notes.at(-1).text.includes('Finish the funded build'));
const paid = structuredClone(funded.resources);
funds = advancePlayground(funds, 8);
assert.deepEqual(funds.islands[0].resources, paid, 'Further build actions do not charge the project again');

let defaultRun = initial;
for (let tick = 0; tick < 240; tick++) defaultRun = advancePlayground(defaultRun, 1);
assert.equal(defaultRun.islands[0].projects.filter(project => project.status === 'complete').length, 1, 'Missing roles cannot be invented after waiting');
assert.equal(defaultRun.islands[1].projects.filter(project => project.status === 'complete').length, 1);
assert.equal(defaultRun.islands[0].activeProject, null);
assert.equal(defaultRun.islands[1].activeProject, null);
assert.equal(defaultRun.islands[0].resources.energy, 0, 'Only a battery can supply energy');
assert.equal(defaultRun.islands[0].resources.water, 0, 'Only a water carrier can supply water');

let full = initial;
for (const island of initial.islands) for (const object of OBJECTS) full = addPlaygroundObject(full, island.id, object.kind);
for (const island of full.islands) assert.equal(island.residents.length, MAX_CREW);
assert.equal(addPlaygroundObject(full, 'sunrise', 'mug'), full, 'Duplicate object clicks do not create more residents');
assert.equal(addPlaygroundObject(full, 'unknown', 'mug'), full);
let stepped = full;
let trajectorySamples = 0;
for (let tick = 0; tick < 1200; tick++) {
  stepped = advancePlayground(stepped, .25);
  for (const island of stepped.islands) {
    for (const resource of RESOURCE_ORDER) assert.ok(island.resources[resource] >= 0 && island.resources[resource] <= STORAGE_LIMIT, 'Resource spending and storage remain bounded');
    for (const project of island.projects) {
      assert.ok(project.progress >= 0 && project.progress <= project.required_progress);
      if (project.status === 'building' || project.status === 'complete') assert.deepEqual(projectGaps(island, project.id).capabilities, [], 'Every funded project has the necessary object roles');
    }
    for (const resident of island.residents) if (resident.task) {
      const object = objectDefinition(resident.kind);
      assert.equal(resident.task.kind, object.action, 'An object only performs its own supported action');
      if (resident.task.project_id) assert.ok(BLUEPRINTS.find(project => project.id === resident.task.project_id).needs.includes(object.capability), 'Build contributions require a useful role');
      else assert.deepEqual(Object.keys(resident.task.gain), [object.resource], 'Gatherers only produce their supported resource');
    }
    assert.ok(island.notes.length <= 60, 'The in-memory board is bounded');
  }
  trajectorySamples++;
}
let chunked = full;
for (let chunk = 0; chunk < 5; chunk++) chunked = advancePlayground(chunked, 60);
assert.deepEqual(chunked, stepped, 'Fixed elapsed time produces identical outcomes independent of render tick size');
for (const island of stepped.islands) {
  assert.equal(island.projects.filter(project => project.status === 'complete').length, 4, 'A complete crew can finish all four projects');
  assert.equal(islandValue(island), 30, 'Value is earned by actual completed useful builds');
}
assert.deepEqual(initial, initialCopy, 'Every transition preserves its input');
assert.equal(advancePlayground(initial, NaN), initial);
assert.equal(advancePlayground(initial, -1), initial);
assert.ok(advancePlayground(initial, 1000).seconds <= 60, 'A suspended timer cannot trigger unbounded catch-up');

const rendering = playgroundScene({ ...full, paused: true }, full.islands[0], 4, Date.parse('2026-10-24T15:00:00Z'));
assert.equal(rendering.paused, true);
assert.equal(rendering.paused_at, rendering.server_time);
for (const agent of rendering.agents) {
  if (agent.task) assert.equal(Date.parse(agent.task.ends_at) - Date.parse(agent.task.started_at), agent.task.duration_seconds * 1000, 'The renderer uses the selected speed without altering simulation work');
  assert.equal(agent.persona_provenance.origin, 'practice_game_rules');
}
for (const character of playgroundCharacters(full.islands[0])) {
  assert.equal(character.image_ref, '', 'Example characters never load real object photos');
  assert.ok(character.visual_spec.template_id !== 'generic' || objectSilhouette(character.visual_spec.template_id, character.object_type, character.canonical_type_id), 'Every example has a recognizable supported rig, never a blank photo-card substitute');
  assert.equal(character.distinct_battle_count, 0, 'Practice objects never claim battle provenance');
}
console.log(`Playground checks passed: ${trajectorySamples} bounded transition samples; capability-gated alternatives, arrivals, pauses, one-time spending, deterministic timing, complete crews, bounded history and supported object rigs.`);
