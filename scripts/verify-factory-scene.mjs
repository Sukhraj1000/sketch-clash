import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { transformSync } from 'rolldown/utils';
import * as THREE from 'three';

// Inspect the components' actual JSX geometry without a GPU, live world or API.
// Hooks are inert only for the existing structure wrapper's animation lifecycle;
// construction progress, recipe geometry and selection handlers remain real code.
const require = createRequire(import.meta.url);
const sourceUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
const jsxRuntime = pathToFileURL(require.resolve('react/jsx-runtime')).href;
function componentModule(filename, replacements = {}, source = readFileSync(new URL(filename, import.meta.url), 'utf8')) {
  const result = transformSync(filename, source, {
    lang: 'tsx', sourceType: 'module', jsx: { runtime: 'automatic' },
  });
  assert.equal(result.errors.length, 0, `${filename} compiles for inspection`);
  let code = result.code;
  for (const [from, to] of Object.entries({ 'react/jsx-runtime': jsxRuntime, three: import.meta.resolve('three'), ...replacements })) {
    code = code.replaceAll(JSON.stringify(from), JSON.stringify(to)).replaceAll(`'${from}'`, JSON.stringify(to));
  }
  return sourceUrl(code);
}
const primitives = componentModule('../src/components/FactoryPrimitives.tsx');
const equipmentUrl = new URL('../src/components/robotEquipment.ts', import.meta.url).href;
const { robotEquipment } = await import(equipmentUrl);
const { default: RobotShape } = await import(componentModule('../src/components/RobotShape.tsx', { './FactoryPrimitives': primitives, './robotEquipment': equipmentUrl }));
const structuresUrl = componentModule('../src/components/FactoryStructures.tsx', { './FactoryPrimitives': primitives });
const { FactoryStructureVisual } = await import(structuresUrl);
const worldMapUrl = new URL('../src/components/worldMap.ts', import.meta.url).href;
const assemblyLayoutUrl = new URL('../src/components/assemblyLayout.ts', import.meta.url).href;
const { assemblySiteScale } = await import(assemblyLayoutUrl);
const { WORLD_STATIONS, WORLD_PATHS } = await import(worldMapUrl);
const { default: FactoryEnvironment } = await import(componentModule('../src/components/FactoryEnvironment.tsx', { './FactoryPrimitives': primitives, './worldMap': worldMapUrl }));
const { default: IslandStructure } = await import(componentModule('../src/components/IslandStructures.tsx', {
  './FactoryStructures': structuresUrl,
  '../lib/island': new URL('../src/lib/island.ts', import.meta.url).href,
  '../lib/projectBenefits': new URL('../src/lib/projectBenefits.ts', import.meta.url).href,
  './ProjectMapLabel': sourceUrl('export default () => null;'),
  './assemblyLayout': assemblyLayoutUrl,
  react: sourceUrl('export const useRef = value => ({ current: value }); export const useEffect = () => {}; export const useState = value => [value, () => {}];'),
  '@react-three/fiber': sourceUrl('export const useFrame = () => {};'),
  three: import.meta.resolve('three'),
}));

function inspect(node, parent = new THREE.Matrix4(), result = { named: new Map(), geometry: [], colors: new Set() }) {
  if (node == null || typeof node === 'boolean' || typeof node === 'string' || typeof node === 'number') return new THREE.Box3();
  if (Array.isArray(node)) return node.reduce((box, child) => box.union(inspect(child, parent, result)), new THREE.Box3());
  if (typeof node.type === 'function') return inspect(node.type(node.props), parent, result);
  const props = node.props ?? {};
  if (typeof node.type === 'string' && node.type.endsWith('Geometry')) {
    const Constructor = THREE[node.type[0].toUpperCase() + node.type.slice(1)];
    assert.equal(typeof Constructor, 'function', `${node.type} has a real Three geometry`);
    assert.ok((props.args ?? []).every(value => typeof value !== 'number' || Number.isFinite(value)), 'All geometry arguments are finite');
    const geometry = new Constructor(...(props.args ?? []));
    geometry.computeBoundingBox();
    const box = geometry.boundingBox.clone().applyMatrix4(parent);
    geometry.dispose();
    assert.ok([...box.min, ...box.max].every(Number.isFinite), 'Actual world-space geometry is finite');
    result.geometry.push({ type: node.type, args: props.args, matrix: parent.toArray(), bounds: [...box.min, ...box.max] });
    return box;
  }
  if (typeof node.type === 'string' && node.type.endsWith('Material') && props.color) result.colors.add(props.color);
  const transform = new THREE.Object3D();
  if (props.position) transform.position.fromArray(props.position);
  if (props.rotation) transform.rotation.fromArray(props.rotation);
  if (typeof props.scale === 'number') transform.scale.setScalar(props.scale);
  else if (props.scale) transform.scale.fromArray(props.scale);
  transform.updateMatrix();
  const matrix = parent.clone().multiply(transform.matrix);
  const box = inspect(props.children, matrix, result);
  if (props.name) result.named.set(props.name, { bounds: [...box.min, ...box.max], matrix: matrix.toArray(), props });
  return box;
}
function scene(node) {
  const result = { named: new Map(), geometry: [], colors: new Set() };
  return { ...result, bounds: inspect(node, new THREE.Matrix4(), result) };
}
function frozen(value) {
  if (value && typeof value === 'object') { Object.values(value).forEach(frozen); Object.freeze(value); }
  return value;
}

const character = frozen({
  id: 'saved-bottle', object_type: 'bottle', image_ref: '/api/media/fixture',
  visual_spec: { palette: ['#5577AA', '#F2BC41'], template_id: 'generic', scale: 1.6, proportions: { width: .5, height: 1.5 }, accessories: ['eyes', 'feet', 'arms'], animation_style: 'wobbly' },
});
const originalCharacter = JSON.stringify(character);
const permissions = [
  [[], 'none'], [['water'], 'water'], [['tend'], 'water'], [['plan'], 'plan'], [['measure'], 'measure'],
  [['charge'], 'charge'], [['signal'], 'signal'], [['build'], 'build'], [['carry'], 'carry'],
  [['rest', 'explore'], 'none'], [['waterproof', 'building', 'recharge', 'signal_boost'], 'none'],
];
for (const [actions, expected] of permissions) {
  frozen(actions);
  assert.equal(robotEquipment(actions).id, expected, 'Equipment follows exact saved permissions, never object-name guesses');
  const robot = scene(RobotShape({ character, allowedActions: actions }));
  const size = robot.bounds.getSize(new THREE.Vector3());
  assert.ok(robot.bounds.min.y >= -.001 && robot.bounds.min.y <= .001, 'The actual robot feet rest on the ground');
  assert.ok(size.x > .4 && size.x < .9 && size.y > .7 && size.y < 1.15 && size.z < .8, 'Every module keeps a compact, undeformed robot silhouette');
  for (const name of ['sc-character', 'sc-eyes', 'sc-arm-left', 'sc-arm-right', 'sc-foot-left', 'sc-foot-right']) {
    assert.ok(robot.named.has(name), `${expected} robot retains its shared animation rig: ${name}`);
  }
  const modules = [...robot.named.keys()].filter(name => name.startsWith('factory-module-'));
  assert.deepEqual(modules, expected === 'none' ? [] : [`factory-module-${expected}`], 'A robot shows only its permitted accessory');
  assert.match(robot.named.get('sc-character').props.userData.rigKey, /^factory-robot:/, 'Switching object geometry invalidates cached rig bindings');
  for (const name of ['sc-foot-left', 'sc-foot-right']) assert.ok(Number.isFinite(robot.named.get(name).props.userData.restY), 'Feet retain their animation rest height');
  assert.ok(robot.colors.has('#5577AA') && robot.colors.has('#F2BC41'), 'The robot preserves its object palette');
}
const oddProportions = { ...character, visual_spec: { ...character.visual_spec, scale: 50, proportions: { width: 100, height: .01 } } };
assert.deepEqual(scene(RobotShape({ character: oddProportions })).geometry, scene(RobotShape({ character })).geometry, 'Saved photographic proportions cannot distort the robot mesh');
assert.equal(JSON.stringify(character), originalCharacter, 'Rendering leaves the accepted object record untouched');

const baseProject = {
  id: 'saved-project', name: 'Fixture structure', kind: 'workshop', position: { x: 2.1, z: -1.5 },
  progress: 0, required_progress: 100, status: 'building', level: 0, max_level: 3,
};
const completedShapes = new Set();
for (const kind of ['garden', 'workshop', 'beacon', 'boardwalk']) {
  const project = frozen({ ...baseProject, kind });
  const initial = scene(FactoryStructureVisual({ project, progress: 0 }));
  const complete = scene(FactoryStructureVisual({ project, progress: 1 }));
  assert.ok(complete.geometry.length > initial.geometry.length, `${kind} visibly builds from real construction progress`);
  completedShapes.add(JSON.stringify(complete.geometry));
  for (const progress of [-5, 0, .2, .5, .8, 1, 20, NaN, Infinity]) {
    const rendered = scene(FactoryStructureVisual({ project, progress }));
    const size = rendered.bounds.getSize(new THREE.Vector3());
    assert.ok(size.x < 3 && size.z < 3 && size.y < 3, `${kind} stays inside its existing worksite footprint`);
  }
  assert.deepEqual(scene(FactoryStructureVisual({ project, progress: -5 })).geometry, initial.geometry, 'Negative progress clamps to the starting structure');
  assert.deepEqual(scene(FactoryStructureVisual({ project, progress: 20 })).geometry, complete.geometry, 'Excess progress clamps to the completed structure');
  // Once built, the same wrapper keeps the entire building during its next upgrade.
  const upgraded = scene(IslandStructure({ project: { ...project, level: 1, progress: 0 }, selected: false, active: false, reducedMotion: true, presentation: 'factory' }));
  const priorComplete = scene(IslandStructure({ project: { ...project, level: 1, status: 'complete', progress: 100 }, selected: false, active: false, reducedMotion: true, presentation: 'factory' }));
  assert.deepEqual(upgraded.geometry, priorComplete.geometry, 'Starting an upgrade never removes an existing factory structure');
}
assert.equal(completedShapes.size, 4, 'Different existing project kinds have distinct factory forms');

const assembly = frozen({ ...baseProject, kind: 'assembly', progress: 60, blueprint_id: 'approved-fixture', assembly: {
  family: 'support', context: { span: .6 }, parts: [
    { kind: 'beam', resident_id: 'ruler', position: { x: 0, y: .1, z: 0 }, rotation: 90, geometry: { width: .8, height: .12, depth: .4, length: 1.8 }, material_assumption: 'wood' },
    { kind: 'vessel', resident_id: 'mug', position: { x: -.5, y: 0, z: .2 }, rotation: 0, geometry: { width: .6, height: .7, depth: .6, length: .6 }, material_assumption: 'ceramic' },
    { kind: 'connector', resident_id: 'clip', position: { x: .5, y: 0, z: -.1 }, rotation: 0, geometry: { width: .3, height: .4, depth: .3, length: .3 }, material_assumption: 'metal' },
  ],
} });
const assemblySites = new Set();
for (const family of ['support', 'hold', 'contain']) {
  const project = { ...assembly, assembly: { ...assembly.assembly, family } };
  const initial = scene(FactoryStructureVisual({ project, progress: 0 }));
  const finished = scene(FactoryStructureVisual({ project, progress: 1 }));
  assert.ok(finished.geometry.length > initial.geometry.length, 'The installed fixture appears only as actual construction progresses');
  assert.ok(finished.named.has(`factory-fixture-${family}`), 'Each approved family gains a readable fitted worksite');
  const size = finished.bounds.getSize(new THREE.Vector3());
  assert.ok(size.x < 2 && size.z < 1.5 && size.y < .6, 'Worksite fittings stay within the existing saved site and below the real object recipe');
  assert.ok(![...finished.named.keys()].some(name => name.startsWith('assembly-part-')), 'Factory site fittings do not invent or replace source-object parts');
  assemblySites.add(JSON.stringify(finished.geometry));
}
assert.equal(assemblySites.size, 3, 'Support, holding and containment have distinct fixtures');
const assemblySnapshot = JSON.stringify(assembly);
const assemblyViews = [];
for (const presentation of ['island', 'factory']) {
  const selectedIds = [];
  const node = IslandStructure({ project: assembly, selected: false, onSelect: id => selectedIds.push(id), active: false, reducedMotion: true, presentation });
  node.props.onClick({ delta: 0, stopPropagation() {} });
  node.props.onClick({ delta: 10, stopPropagation() { assert.fail('Camera drags must not become project selection'); } });
  assert.deepEqual(selectedIds, [assembly.id], 'Both appearances select the same saved project, and ignore drag gestures');
  const rendered = scene(node);
  assemblyViews.push([...rendered.named.entries()].filter(([name]) => name.startsWith('assembly')).map(([name, detail]) => [name, detail.bounds, detail.matrix]));
}
assert.equal(assemblyViews[0].length, 4, 'The approved assembly and all three attributed recipe parts remain visible');
assert.deepEqual(assemblyViews[1], assemblyViews[0], 'Factory view preserves exact approved part geometry, proportions, positions and construction state');
assert.equal(JSON.stringify(assembly), assemblySnapshot, 'Both appearances leave the persisted blueprint untouched');

const denseProjects = frozen(Array.from({ length: 7 }, (_, index) => ({ ...assembly, id: `dense-${index}`, position: { x: index - 3, z: 0 }, level: 1, max_level: 1, status: 'complete' })));
const denseSnapshot = JSON.stringify(denseProjects);
assert.equal(assemblySiteScale(denseProjects[0]), 1, 'An isolated assembly remains full size');
assert.equal(assemblySiteScale(denseProjects[0], [denseProjects[0], { ...baseProject, id: 'near-base', position: { x: -2, z: 0 } }]), .45, 'An assembly also fits near an existing base building');
assert.equal(assemblySiteScale(denseProjects[0], [denseProjects[0], { ...baseProject, id: 'far-base', position: { x: 0, z: 0 } }]), 1, 'A generously spaced site retains its full presentation');
assert.equal(assemblySiteScale(denseProjects[0], [denseProjects[0], { ...baseProject, id: 'coincident', position: denseProjects[0].position }]), .28, 'Coincident historical sites remain finite and selectable');
const denseViews = [];
for (const presentation of ['island', 'factory']) {
  const rendered = denseProjects.map(project => {
    const props = { project, selected: false, active: false, reducedMotion: true, presentation };
    const compact = scene(IslandStructure({ ...props, projects: denseProjects }));
    const isolated = scene(IslandStructure(props));
    const visual = compact.named.get(`project-visual-${project.id}`);
    const matrix = new THREE.Matrix4().fromArray(visual.matrix);
    const position = new THREE.Vector3().setFromMatrixPosition(matrix);
    assert.deepEqual([position.x, position.y, position.z], [project.position.x, .025, project.position.z], 'Adaptive display keeps the exact saved site anchor');
    const scale = new THREE.Vector3().setFromMatrixScale(matrix);
    assert.deepEqual(scale.toArray(), [.45, .45, .45], 'Fixture, recipe and selection footprint share one uniform scale');
    for (const [name, detail] of compact.named) if (name.startsWith('assembly')) {
      const expected = new THREE.Matrix4().makeTranslation(position.x, position.y, position.z)
        .scale(scale).multiply(new THREE.Matrix4().makeTranslation(-position.x, -position.y, -position.z))
        .multiply(new THREE.Matrix4().fromArray(isolated.named.get(name).matrix));
      assert.ok(expected.toArray().every((value, index) => Math.abs(value - detail.matrix[index]) < 1e-9), 'Every approved part retains its relative proportions and orientation inside the uniformly scaled site');
    }
    return compact;
  });
  for (let index = 1; index < rendered.length; index++) {
    const previous = rendered[index - 1].named.get(`project-visual-dense-${index - 1}`).bounds;
    const next = rendered[index].named.get(`project-visual-dense-${index}`).bounds;
    assert.ok(previous[3] < next[0], 'A dense row of saved builds has visible space between complete sites instead of a solid wall');
  }
  denseViews.push(rendered.map(view => [...view.named.entries()].filter(([name]) => name.startsWith('assembly')).map(([name, detail]) => [name, detail.matrix])));
}
assert.deepEqual(denseViews[0], denseViews[1], 'Crowded recipes stay identical in island and factory representations');
assert.equal(JSON.stringify(denseProjects), denseSnapshot, 'Adaptive presentation never rewrites saved projects or their recipes');

const world = readFileSync(new URL('../src/components/WorldScene.tsx', import.meta.url), 'utf8');
// Render the actual island component tree. Only its browser label and Drei line
// infrastructure are inert; all island geometry and transforms remain real.
const islandSource = world.slice(world.indexOf('function Tree('), world.indexOf('function Atmosphere('));
assert.ok(islandSource.includes('function Island('), 'The actual island component is available for geometry inspection');
const { Island } = await import(componentModule('../src/components/WorldScene.tsx', {}, `
  import { WORLD_MAP_SURFACE_SCALE, WORLD_PATHS, WORLD_STATIONS, WORLD_STATION_BACKSETS, WORLD_TREES, WORLD_WAYFINDER, worldGroundDetails, worldGroundShape, worldRimDecor } from ${JSON.stringify(worldMapUrl)};
  const useMemo = fn => fn();
  const useState = value => [value, () => {}];
  const useEffect = () => {};
  const useThree = () => ({ invalidate() {} });
  const INK = '#1E1C29', PAPER = '#FFF9EB';
  function Material({color}) { return <meshStandardMaterial color={color} />; }
  function Line({points}) { return <group userData={{points}} />; }
  ${islandSource}
  export { Island };
`));
const environment = scene(FactoryEnvironment({ seed: 4127 }));
assert.ok(environment.geometry.length > 0, 'The factory environment contains real scene geometry');
for (const [resource, x, z] of [['materials', -3.25, 1.2], ['water', -.25, -2.9], ['ideas', .15, .7], ['energy', 3.65, .55]]) {
  const station = environment.named.get(`factory-station-${resource}`);
  assert.ok(station, `The ${resource} station remains identifiable`);
  const position = new THREE.Vector3().setFromMatrixPosition(new THREE.Matrix4().fromArray(station.matrix));
  assert.deepEqual([position.x, position.z], [x, z], 'Factory stations retain existing authoritative resource positions');
}

const backendIsland = readFileSync(new URL('../backend/app/island.py', import.meta.url), 'utf8');
const backendLocations = backendIsland.match(/RESOURCE_LOCATIONS = \{([\s\S]*?)\n\}/)?.[1] ?? '';
const resourcePattern = /'([a-z]+)':\s*\{'x':\s*([-\d.]+),\s*'z':\s*([-\d.]+)\}/g;
const serverStations = Object.fromEntries([...backendLocations.matchAll(resourcePattern)].map(([, key, x, z]) => [key, { x: Number(x), z: Number(z) }]));
assert.equal(Object.keys(serverStations).length, 4, 'Read all authoritative resource anchors without running a backend or model call');
assert.deepEqual(WORLD_STATIONS, serverStations, 'The shared scene map agrees with actual server resource destinations');
const serverProjects = backendIsland.match(/PROJECT_DEFINITIONS = \(([\s\S]*?)\n\)/)?.[1] ?? '';
const projectPoints = [...serverProjects.matchAll(/'position':\s*\{'x':\s*([-\d.]+),\s*'z':\s*([-\d.]+)\}/g)].map(([, x, z]) => ({ x: Number(x), z: Number(z) }));
assert.equal(projectPoints.length, 4, 'Read all four authoritative project destinations');
const routeEnds = WORLD_PATHS.map(points => ({ x: points.at(-1)[0], z: points.at(-1)[2] }));
for (const destination of [...Object.values(serverStations), ...projectPoints]) {
  assert.ok(routeEnds.some(point => point.x === destination.x && point.z === destination.z), 'Both map styles have a route reaching each actual station and project');
}

const mapPosition = (detail) => {
  const point = new THREE.Vector3().setFromMatrixPosition(new THREE.Matrix4().fromArray(detail.matrix));
  return [point.x, point.z];
};
for (const seed of [4127, 9071]) {
  const island = scene(Island({ seed }));
  const factory = scene(FactoryEnvironment({ seed }));
  for (const layer of ['foundation', 'shoulder', 'surface', 'hub']) {
    const natural = island.named.get(`island-map-${layer}`);
    const industrial = factory.named.get(`factory-map-${layer}`);
    assert.ok(natural && industrial, 'Both appearances expose their real map geometry');
    assert.deepEqual(industrial.bounds, natural.bounds, `${layer}: factory and island have identical actual geometry bounds`);
    assert.deepEqual(industrial.matrix, natural.matrix, `${layer}: no map translation, rotation or rescaling during the toggle`);
  }
  for (const resource of Object.keys(serverStations)) {
    assert.deepEqual(mapPosition(factory.named.get(`factory-station-${resource}`)), mapPosition(island.named.get(`island-station-${resource}`)), `${resource}: a robot and an object use the same service anchor`);
  }
  for (const [name, detail] of island.named) {
    if (/^island-map-(utility|edge|detail|wayfinder)/.test(name)) {
      const counterpart = factory.named.get(name.replace(/^island-/, 'factory-'));
      assert.ok(counterpart, 'Every natural decoration has its industrial counterpart');
      assert.deepEqual(mapPosition(counterpart), mapPosition(detail), 'Tree, rim, ground detail and sign replacements keep their exact seeded positions');
    }
    if (name.startsWith('island-map-route-')) {
      const counterpart = factory.named.get(name.replace(/^island-/, 'factory-'));
      assert.deepEqual(counterpart.props.userData.mapPoints, detail.props.userData.mapPoints, 'Industrial markings follow the exact island path, including bends');
    }
  }
}

// Narrow integration checks protect React identity and the shared authoritative
// motion path. Camera/selection continuity is also exercised in browser review.
assert.match(world, /presentation\s*=\s*'island'/, 'Other scene callers keep their island appearance by default');
assert.match(world, /<Resident\s+key=\{character\.id\}/, 'Appearance changes cannot remount resident animation clocks or arrival state');
assert.match(world, /<IslandStructure\s+key=\{project\.id\}/, 'Appearance changes cannot remount saved project effects');
assert.doesNotMatch(world.match(/<Canvas\b[^>]+>/)?.[0] ?? '', /\bkey=/, 'The camera and renderer survive a presentation switch');
assert.match(world, /factory\s*\?\s*\[1,\s*1,\s*1\]\s*:\s*characterDisplayScale/, 'The robot has a uniform outer scale independent of accepted photo proportions');
assert.match(world, /residentDisplayPose\(agent\.task,\s*agent\.position,\s*worldTime\(clock\),\s*displaySlot\.current\)/, 'Robot and object movement use the same server task, time and position');
assert.match(world, /<RobotShape\s+character=\{character\}\s+allowedActions=\{agent\?\.allowed_actions\}/, 'Robot equipment reads saved agent permissions');
console.log('Factory scene checks passed: exact-permission robot modules, grounded rigid geometry, original palettes, staged workstations, upgrade continuity, approved assembly conservation, stable IDs and shared task motion.');
