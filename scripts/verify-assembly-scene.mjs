import assert from 'node:assert/strict';
import { assemblyPartPresentation } from '../src/lib/island.ts';

const part = { kind: 'beam', resident_id: 'fixture-resident', position: { x: -.2, y: 0, z: 0 }, rotation: 0,
  geometry: { width: .8, height: .12, depth: .4, length: 1.8 }, material_assumption: 'wood' };
const original = structuredClone(part);
for (let index = 0; index < 3; index++) {
  for (let progress = 0; progress <= 1; progress += .025) {
    const shape = assemblyPartPresentation(part, index, 3, progress);
    assert.deepEqual([shape.width, shape.height, shape.depth, shape.length], [.8, .12, .4, 1.8],
      'Progress reveals a rigid tested part without distorting its geometry');
    assert.equal(shape.solid, progress >= (index + 1) / 3);
  }
  assert.equal(assemblyPartPresentation(part, index, 3, 1).solid, true, 'Completed recipes reveal all real parts');
}
const malformed = assemblyPartPresentation({ ...part, geometry: { width: NaN, height: Infinity, depth: -.5, length: 100 },
  position: { x: NaN, y: -100, z: Infinity } }, 0, 1, Infinity);
assert.ok([malformed.width, malformed.height, malformed.depth, malformed.length, ...Object.values(malformed.position)].every(Number.isFinite));
assert.deepEqual(part, original, 'Render preparation never modifies a server-owned blueprint');
console.log('Assembly presentation checks passed: server geometry, rigid construction steps, completed parts and finite bounded fallback.');
