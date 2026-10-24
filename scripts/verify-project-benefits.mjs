import assert from 'node:assert/strict';
import { projectBenefit } from '../src/lib/projectBenefits.ts';

// Saved API-shaped fixtures only. Compare the presentation with the executor's
// per-resource base levels and its single Boolean assembly bonus; no provider calls.
const base = (kind, level, patch = {}) => ({
  id: kind, kind, name: `${kind} fixture`, position: { x: 0, z: 0 },
  progress: 0, required_progress: 12, status: level === 3 ? 'complete' : 'planned',
  level, max_level: 3, description: 'Saved fixture', reward: 'Recorded construction reward',
  completed_at: level ? '2026-10-24T16:00:00Z' : null,
  cost_per_action: { materials: 2 }, ...patch,
});
const assembly = (id, resource, eligibleActions, patch = {}) => ({
  ...base('assembly', 1), id, name: id, status: 'complete', max_level: 1,
  benefit: { kind: 'task_yield_bonus', resource, eligible_actions: eligibleActions, amount: 1 },
  ...patch,
});
const resident = (id, actions) => ({ id, display_name: id, allowed_actions: actions });
const freeze = value => {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
};
const checks = [];
const check = (name, run) => checks.push({ name, run });

for (const [kind, resource, actions] of [
  ['garden', 'water', ['water']],
  ['workshop', 'materials', ['forage', 'carry', 'explore', 'tend']],
  ['beacon', 'ideas', ['plan', 'measure', 'signal']],
  ['boardwalk', 'energy', ['charge']],
]) {
  for (const level of [1, 2, 3]) check(`${kind} level ${level} matches its saved resource bonus`, () => {
    const project = freeze(base(kind, level));
    const crew = freeze(actions.map(action => resident(`${action}-worker`, [action, 'rest'])));
    const result = projectBenefit(project, [project], crew);
    assert.equal(result.status, 'active');
    assert.equal(result.resource, resource);
    assert.equal(result.amount, level, 'Base yield bonus equals completed levels, not upgrade progress');
    assert.deepEqual(result.eligibleActions, actions);
    assert.deepEqual(result.crew, crew.map(agent => agent.display_name));
    assert.match(result.label, new RegExp(`\\+${level} ${resource}`));
    assert.match(result.description, /completed tasks.*storage has room/i,
      'A building is a delivery multiplier, not automatic stock or proof of output');
  });
  check(`${kind} first blueprint does not claim an unlocked bonus`, () => {
    const project = freeze(base(kind, 0, { progress: 11, status: 'building' }));
    const result = projectBenefit(project, [project], [resident('eligible', actions)]);
    assert.equal(result.status, 'planned');
    assert.equal(result.amount, 0, 'Reserved or partial work cannot unlock a bonus');
    assert.match(result.label, /unlocks/i);
    assert.match(result.description, /not.*complete|not.*unlocked/i);
  });
  check(`${kind} pending upgrade retains its already-built benefit`, () => {
    const project = freeze(base(kind, 1, { progress: 8, status: 'building' }));
    const result = projectBenefit(project, [project], [resident('eligible', actions)]);
    assert.equal(result.status, 'active');
    assert.equal(result.amount, 1, 'Building level two must not erase level one or award level two early');
    assert.doesNotMatch(result.description, /not.*unlocked/i);
  });
}

check('a tested assembly unlocks exactly one bonus only at completion', () => {
  const crew = [resident('carrier', ['carry', 'forage'])];
  const pending = freeze(assembly('support', 'materials', ['carry', 'forage'], {
    level: 0, progress: 3, required_progress: 4, status: 'building', completed_at: null,
  }));
  assert.equal(projectBenefit(pending, [pending], crew).status, 'planned');
  assert.equal(projectBenefit(pending, [pending], crew).amount, 0);
  const complete = freeze({ ...pending, level: 1, status: 'complete', progress: 0 });
  const result = projectBenefit(complete, [complete], crew);
  assert.equal(result.status, 'active');
  assert.equal(result.amount, 1);
  assert.match(result.description, /capped at \+1/i);
});

check('historical identical assemblies share the single capped bonus in either input order', () => {
  const first = freeze(assembly('first', 'materials', ['carry', 'forage']));
  const later = freeze(assembly('later', 'materials', ['carry', 'forage'], { completed_at: '2026-10-24T16:05:00Z' }));
  const crew = [resident('carrier', ['carry'])];
  for (const projects of [[first, later], [later, first]]) {
    assert.equal(projectBenefit(first, projects, crew).status, 'active');
    const duplicate = projectBenefit(later, projects, crew);
    assert.equal(duplicate.status, 'redundant');
    assert.equal(duplicate.amount, 0, 'A second copy cannot claim another +1');
    assert.match(duplicate.label, /no extra yield/i);
  }
});

check('multiple earlier assemblies jointly cover a later assembly without stacking', () => {
  const plan = freeze(assembly('plan', 'ideas', ['plan']));
  const measure = freeze(assembly('measure', 'ideas', ['measure']));
  const duplicate = freeze(assembly('both', 'ideas', ['plan', 'measure'], { completed_at: '2026-10-24T17:00:00Z' }));
  const result = projectBenefit(duplicate, [duplicate, plan, measure], [resident('planner', ['plan', 'measure'])]);
  assert.equal(result.status, 'redundant');
  assert.equal(result.amount, 0);
});

check('an unfinished predecessor cannot consume the completed assembly bonus', () => {
  const pending = freeze(assembly('pending', 'water', ['water'], { level: 0, status: 'building' }));
  const complete = freeze(assembly('complete', 'water', ['water'], { completed_at: '2026-10-24T17:00:00Z' }));
  const result = projectBenefit(complete, [pending, complete], [resident('jug', ['water'])]);
  assert.equal(result.status, 'active');
  assert.equal(result.amount, 1);
});

check('partially overlapping assemblies credit only residents able to use the added action', () => {
  const first = freeze(assembly('plan-first', 'ideas', ['plan']));
  const second = freeze(assembly('measure-second', 'ideas', ['plan', 'measure'], { completed_at: '2026-10-24T17:00:00Z' }));
  const crew = [resident('pencil', ['plan']), resident('ruler', ['measure'])];
  const result = projectBenefit(second, [first, second], crew);
  assert.equal(result.status, 'active');
  assert.deepEqual(result.crew, ['ruler'], 'The pencil cannot receive credit for a measuring benefit it cannot perform');
  assert.match(result.description, /measuring/i);
  assert.doesNotMatch(result.description, /pencil/);
  const nobodyCanUseAddedAction = projectBenefit(second, [first, second], [crew[0]]);
  assert.equal(nobodyCanUseAddedAction.status, 'unavailable', 'An already-covered action does not activate a new role');
});

check('base improvements and tested assemblies are separate bonuses', () => {
  const workshop = freeze(base('workshop', 3));
  const support = freeze(assembly('support', 'materials', ['carry', 'forage']));
  const crew = [resident('carrier', ['carry'])];
  assert.equal(projectBenefit(workshop, [workshop, support], crew).amount, 3);
  assert.equal(projectBenefit(support, [workshop, support], crew).amount, 1,
    'The backend adds its one assembly bonus on top of base completed levels');
  assert.equal(projectBenefit(support, [workshop, support], crew).status, 'active');
});

check('built effects need a declared crew role and never create resources by themselves', () => {
  const beacon = freeze(base('beacon', 1));
  const result = projectBenefit(beacon, [beacon], [resident('rock', ['forage', 'build', 'rest'])]);
  assert.equal(result.status, 'unavailable');
  assert.deepEqual(result.crew, []);
  assert.match(result.label, /needs a role/i);
  assert.match(result.description, /does not create ideas by itself/i);
  assert.equal(projectBenefit(beacon, [beacon], []).status, 'unavailable', 'An empty crew is not an unknown crew');
  const unknownCrew = projectBenefit(beacon, [beacon]);
  assert.match(unknownCrew.description, /eligible residents/i);
  assert.deepEqual(unknownCrew.crew, [], 'Absent crew data cannot invent named beneficiaries');
});

check('a missing or empty saved assembly effect cannot claim a resource increment', () => {
  for (const benefit of [undefined, { kind: 'task_yield_bonus', resource: 'ideas', eligible_actions: [], amount: 1 }]) {
    const project = freeze(assembly('no-effect', 'ideas', ['plan'], { benefit }));
    const result = projectBenefit(project, [project], [resident('pencil', ['plan'])]);
    assert.equal(result.status, 'unavailable');
    assert.equal(result.amount, 0, 'No operational effect means no bonus to present');
    assert.match(result.label, /no saved effect/i);
  }
});

let failed = 0;
for (const { name, run } of checks) {
  try { run(); } catch (error) { failed++; console.error(`FAIL: ${name}\n${error.stack}`); }
}
if (failed) process.exitCode = 1;
else console.log(`Project benefit checks passed: ${checks.length} saved-level, upgrade, capped assembly, crew-role and no-effect cases.`);
