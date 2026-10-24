import assert from 'node:assert/strict';
import { computeTaskPose, safeIslandPoint } from '../src/lib/island.ts';
import { objectSilhouette } from '../src/components/objectIdentity.ts';
import { furniturePresentation } from '../src/components/furniturePresentation.ts';
import { vesselPresentation } from '../src/components/vesselPresentation.ts';
import { objectPose } from '../src/components/objectMotion.ts';
import { characterDisplayScale, displayIslandPoint, residentDisplayPose, residentDisplaySlots } from '../src/components/objectPresentation.ts';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { transformSync } from 'rolldown/utils';
import * as THREE from 'three';

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
for (const label of ['table','wooden table','rectangular wooden dining table','wooden table displayed on smartphone screen','a brown wooden table shown on a phone screen','table in a photograph']) {
  assert.equal(objectSilhouette('generic',label),'table',`${label} keeps the furniture subject rather than its capture context`);
}
for (const label of ['chair','wooden chair','dining chair','a white wooden chair pictured in a photo']) {
  assert.equal(objectSilhouette('generic',label),'chair',`${label} gets a seat, back and four legs`);
}
for (const label of ['table football','chair cushion','tablecloth','coffee table book','smartphone displaying a table','person beside a wooden chair','wooden table with a chair','not a chair','possibly a table','Timber Table Hero']) {
  assert.equal(objectSilhouette('generic',label),null,`${label} cannot invent furniture from an incidental word`);
}
assert.equal(objectSilhouette('generic','table lamp'),'lamp','A table lamp stays a lamp');
assert.equal(objectSilhouette('generic','table lamp','table'),null,'Known noun conflicts are not resolved by the furniture shortcut');
assert.equal(objectSilhouette('generic','wooden table displayed on smartphone screen','phone'),null,'Contradictory accepted phone identity still prevents a furniture upgrade');
assert.equal(objectSilhouette('generic','smartphone','table'),null,'An actual phone does not become a table through conflicting canonical data');
assert.equal(objectSilhouette('book','dining chair','chair'),'chair','Saved furniture upgrades coarse historical templates without record migration');
const workKinds = [undefined,'forage','carry','water','plan','measure','charge','signal','tend','build','rest','explore'];
let poses = 0;
for (const style of ['calm','bouncy','wobbly']) for (const activity of ['idle','rest','wander']) for (const work of workKinds) {
  for (let milliseconds = 0; milliseconds <= 30000; milliseconds += 50) {
    const pose = objectPose(style,activity,milliseconds/1000,.6,false,work);
    assert.ok(Object.values(pose).every(Number.isFinite),'Every body and limb transform remains finite');
    assert.ok(Math.abs(pose.y)<.15 && Math.abs(pose.roll)<.15 && Math.abs(pose.pitch)<.3,'Body movement stays bounded');
    assert.ok(pose.scaleY>.9 && pose.scaleY<=1.02 && pose.blink>=.08 && pose.blink<=1,'Characters and eyes never invert or disappear');
    assert.equal(pose.scaleY,1,'Rigid objects never squash or stretch during any task');
    assert.ok(Math.abs(pose.leftArmZ)<=2.2 && Math.abs(pose.rightArmZ)<=2.2,'Arm gestures stay inside the supported rig');
    poses++;
  }
  assert.deepEqual(objectPose(style,activity,0,.6,true,work),objectPose(style,activity,100,.6,true,work),'Reduced motion/paused poses do not drift or blink');
}
assert.deepEqual(objectPose('calm','idle',NaN,Infinity),objectPose('calm','idle',0,0),'Invalid clocks cannot poison scene transforms');
assert.notDeepEqual(objectPose('calm','idle',1,0,false,'plan'),objectPose('calm','idle',1,0,false,'measure'),'Different jobs produce distinct gestures');
console.log(`Object presentation checks passed: supported and conservative identity mapping; ${poses} finite bounded limb/blink/work poses; motion-disabled stability.`);

for (const [identity,width,height] of [['tv',1.3,.9],['ruler',1.3,.8],['pencil',.75,1.3],['pitcher',.95,1.2],['microwave',1.3,.9],['mug',1,1.1],['bottle',1,1.25],['table',1.4,.7],['chair',.7,1.4]]) {
  const character = {object_type:identity,canonical_type_id:identity,visual_spec:{template_id:identity==='mug'||identity==='bottle'?identity:'generic',scale:1.1,proportions:{width,height}}};
  const saved = structuredClone(character);
  const scale = characterDisplayScale(character,.7);
  assert.equal(scale[0],scale[1],`${identity} preserves the modeled width/height ratio instead of double-stretching legacy proportions`);
  assert.equal(scale[1],scale[2],`${identity} preserves round eyes and circular handles`);
  assert.deepEqual(character,saved,'Presentation correction never rewrites the saved visual spec');
}
assert.deepEqual(characterDisplayScale({visual_spec:{template_id:'generic',scale:1,proportions:{width:.8,height:1.2}}}),[.8,1.2,.8],'Unknown photo badges retain their accepted aspect');
const crew = ['tv','pitcher','ruler','mug'];
const slots = residentDisplaySlots(crew);
assert.deepEqual(slots,residentDisplaySlots([...crew].reverse()),'Presentation slots do not depend on API row order');
const rest = {x:-.7,z:1.1};
const spots = crew.map(id=>displayIslandPoint(rest,slots.get(id)));
for(let i=0;i<spots.length;i++) for(let j=i+1;j<spots.length;j++) assert.ok(Math.hypot(spots[i].x-spots[j].x,spots[i].z-spots[j].z)>1.1,'Four residents sharing the actual rest point remain separately readable');
for(const slot of slots.values()) {
  assert.ok(Math.hypot(slot.x,slot.z)<1.7,'Four-resident visual separation stays near the authoritative station');
  const arriving = {...task,to:rest};
  const departing = {...task,from:rest,to:{x:3.65,z:.55},started_at:task.ends_at,ends_at:new Date(start+32000).toISOString()};
  const end = residentDisplayPose(arriving,task.from,start+16000,slot);
  const begin = residentDisplayPose(departing,rest,start+16000,slot);
  assert.ok(Math.hypot(end.x-begin.x,end.z-begin.z)<1e-10,'Display offsets are continuous across actual task boundaries');
  let last = residentDisplayPose(arriving,task.from,start,slot);
  for(let elapsed=25;elapsed<=16000;elapsed+=25){const next=residentDisplayPose(arriving,task.from,start+elapsed,slot);assert.ok(Math.hypot(next.x-last.x,next.z-last.z)<.05,'Presentation follows a continuous journey');last=next;}
}
assert.deepEqual(task,before,'Presentation routes do not mutate server tasks');
console.log('Rigid-body and separation regression checks passed: actual live identity proportions, distinct shared-rest slots, task-boundary continuity and saved-state preservation.');

// Inspect the actual JSX geometry, not a second hand-written list of expected
// dimensions. Pure shape/rig components need no browser, GPU or paid API.
const require = createRequire(import.meta.url);
const jsxRuntime = pathToFileURL(require.resolve('react/jsx-runtime')).href;
const componentModule = (filename, replacements={}) => {
  const compiled = transformSync(filename,readFileSync(new URL(filename,import.meta.url),'utf8'),{lang:'tsx',sourceType:'module',jsx:{runtime:'automatic'}});
  assert.equal(compiled.errors.length,0,'Actual shape components compile for geometry inspection');
  let source = compiled.code;
  source = source.replaceAll('"react/jsx-runtime"',JSON.stringify(jsxRuntime));
  for(const [from,to] of Object.entries(replacements)) source = source.replaceAll(JSON.stringify(from),JSON.stringify(to)).replaceAll(`'${from}'`,JSON.stringify(to));
  return 'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
};
const rigUrl = componentModule('../src/components/ObjectRig.tsx');
const furnitureUrl = componentModule('../src/components/FurnitureShape.tsx',{'./ObjectRig':rigUrl});
const {default: Shapes} = await import(componentModule('../src/components/ObjectShapes.tsx',{'./ObjectRig':rigUrl,'./FurnitureShape':furnitureUrl}));
function geometryBounds(node,parent=new THREE.Matrix4(),named=new Map()) {
  if(node==null || typeof node==='boolean') return new THREE.Box3();
  if(Array.isArray(node)) return node.reduce((box,child)=>box.union(geometryBounds(child,parent,named)),new THREE.Box3());
  if(typeof node.type==='function') return geometryBounds(node.type(node.props),parent,named);
  const props=node.props??{};
  if(typeof node.type==='string' && node.type.endsWith('Geometry')) {
    const Constructor=THREE[node.type[0].toUpperCase()+node.type.slice(1)];
    const geometry=new Constructor(...(props.args??[]));geometry.computeBoundingBox();
    const box=geometry.boundingBox.clone().applyMatrix4(parent);geometry.dispose();return box;
  }
  const transform=new THREE.Object3D();
  if(props.position) transform.position.fromArray(props.position);
  if(props.rotation) transform.rotation.fromArray(props.rotation);
  if(typeof props.scale==='number') transform.scale.setScalar(props.scale);
  else if(props.scale) transform.scale.fromArray(props.scale);
  transform.updateMatrix();
  const matrix=parent.clone().multiply(transform.matrix);
  const box=geometryBounds(props.children,matrix,named);
  if(props.name) named.set(props.name,box.clone());
  return box;
}
const dimensions={};
for(const kind of ['pencil','ruler','television','microwave','pitcher','phone','battery']) {
  const named=new Map();
  const box=geometryBounds(Shapes({kind,color:'#6699BB',accent:'#FFD166',feet:true,eyes:true,arms:true}),undefined,named);
  const size=box.getSize(new THREE.Vector3());dimensions[kind]=size;
  assert.ok(box.min.y>=-.01 && box.min.y<.03,`${kind} actual feet are grounded, not suspended below the body`);
  assert.ok(size.y>1 && size.y<2 && size.x<1.8,`${kind} actual rig stays within recognizable body proportions`);
  for(const foot of ['sc-foot-left','sc-foot-right']) assert.ok(named.get(foot).max.y>.25,`${kind} has actual ankle geometry connecting its feet to the body`);
}
assert.ok(dimensions.pencil.y/dimensions.pencil.x>2.3,'The actual pencil silhouette stays tall and narrow');
assert.ok(dimensions.ruler.y/dimensions.ruler.x>1.8,'The actual ruler silhouette stays a long straight edge');
assert.ok(dimensions.television.x/dimensions.television.y>1,'The actual TV remains a landscape display');
assert.ok(dimensions.microwave.x/dimensions.microwave.y>1.15,'The actual microwave remains a wide appliance');
console.log('Actual JSX geometry checks passed: grounded feet/ankles and recognizable pencil, ruler, TV, microwave, pitcher, phone and battery dimensions.');

for (const kind of ['table','chair']) for (const accessories of [false,true]) {
  const named = new Map();
  const box = geometryBounds(Shapes({kind,color:'#B68C56',accent:'#E2C69B',feet:accessories,eyes:accessories,arms:accessories}),undefined,named);
  const size = box.getSize(new THREE.Vector3());
  const surface = named.get(`sc-${kind}-${kind==='table'?'top':'seat'}`);
  assert.ok(surface,`${kind} has its defining horizontal surface, not a photo cube`);
  const surfaceSize = surface.getSize(new THREE.Vector3());
  assert.ok(surfaceSize.x>surfaceSize.y*6 && surfaceSize.z>surfaceSize.y*6,`${kind} surface is thin and horizontal`);
  const legs=[...named].filter(([name])=>name.startsWith(`sc-${kind}-leg-`));
  assert.equal(legs.length,4,`${kind} always has four structural legs, independent of decorative feet`);
  for (const [name,leg] of legs) {
    assert.ok(Math.abs(leg.min.y-.025)<1e-6,`${name} is grounded`);
    assert.ok(Math.abs(leg.max.y-surface.min.y)<1e-6,`${name} connects to the underside of the surface`);
    assert.ok(Math.abs(leg.getCenter(new THREE.Vector3()).x)>.25 && Math.abs(leg.getCenter(new THREE.Vector3()).z)>.25,`${name} leaves the centre under the furniture open`);
  }
  assert.ok(box.min.y>=0 && size.x<2 && size.y<1.85,`${kind} stays bounded and fits the shared preview`);
  for (const limb of ['left','right','back-left','back-right']) assert.equal(named.has(`sc-foot-${limb}`),accessories,'All four feet bind to the shared motion rig only when requested');
  if(kind==='table') {
    assert.ok(size.x>size.y*1.4,'A table remains broader than it is tall');
    assert.ok(named.get('sc-table-apron').min.y>surface.min.y-.17,'The apron supports the top instead of filling the whole body');
  } else {
    const back=named.get('sc-chair-back');
    assert.ok(back.max.y>surface.max.y+.8 && back.max.z<0,'The chair has a tall back behind the seat');
    assert.equal([...named.keys()].filter(name=>name.startsWith('sc-chair-back-slat-')).length,3,'The chair back has distinct open slats');
    assert.ok(size.y>size.x*1.4,'A chair remains a tall seat rather than a table');
  }
}
console.log('Furniture regression checks passed: table/chair subjects, conservative capture context, four grounded structural legs, thin open surfaces, chair back, uniform scale and shared preview/island geometry.');

const chairObservation={canonical_type_id:'chair',label:'wooden outdoor chair',visible_features:['wooden outdoor chair','vertical slat backrest','square cream seat cushion','four wooden legs with horizontal stretchers']};
const chairObservationBefore=structuredClone(chairObservation);
const chairFeatures=furniturePresentation('chair',chairObservation);
assert.deepEqual(chairFeatures,{cushion:true,cushionColor:'#EEE3C8',stretchers:true,taperedLegs:false},'Saved chair evidence adds its cream seat cushion and leg braces');
assert.deepEqual(chairObservation,chairObservationBefore,'Appearance refinement does not mutate source evidence');
const featureNames=new Map();
geometryBounds(Shapes({kind:'chair',color:'#B68C56',accent:'#E2C69B',feet:true,eyes:true,arms:true,furnitureFeatures:chairFeatures}),undefined,featureNames);
assert.ok(featureNames.has('sc-chair-cushion')&&featureNames.has('sc-chair-stretchers'),'Evidence-backed details exist in actual rendered geometry');
assert.ok(!featureNames.has('sc-foot-left')&&!featureNames.has('sc-foot-back-left'),'Braced frame stays rigid so independent leg animations cannot tear it apart');
assert.ok(Math.abs(featureNames.get('sc-chair-cushion').min.y-featureNames.get('sc-chair-seat').max.y)<1e-6,'Cushion sits on the actual seat instead of floating');
assert.equal(furniturePresentation('chair',{canonical_type_id:'chair',visible_features:['possibly a seat cushion','no horizontal stretchers']}).cushion,false,'Uncertain cushion evidence is not rendered');
assert.equal(furniturePresentation('chair',{canonical_type_id:'chair',visible_features:['cream seat cushion','no seat cushion']}).cushion,false,'Negative cushion evidence wins over conflicting positive evidence');
assert.equal(furniturePresentation('chair',{...chairObservation,canonical_type_id:'phone'}).cushion,false,'Conflicting observation identity cannot add furniture details');
assert.equal(furniturePresentation('chair',{...chairObservation,label:'table'}).stretchers,false,'Conflicting observation label cannot add furniture details');
assert.equal(furniturePresentation('table',{canonical_type_id:'table',visible_features:['four tapered wooden legs']}).taperedLegs,true,'Observed table leg taper is retained');
assert.equal(furniturePresentation('chair',undefined).cushion,false,'Missing historical evidence does not invent a cushion');
console.log('Saved furniture evidence checks passed: cream cushion, rigid leg stretchers, conservative absence/conflict handling and tapered table legs.');

// Reproduce the actual accepted handled-bottle description that previously
// became a narrow-neck bottle, without its private capture or saved identity.
const bottle = {canonical_type_id:'bottle',object_type:'bottle',visual_spec:{template_id:'bottle',accessories:['cap','handle'],proportions:{width:.9,height:1.2}},observed_object:{canonical_type_id:'bottle',label:'water bottle',visible_features:['cylindrical insulated tumbler/bottle body','light blue flip lid with drink spout cover','sturdy side carry handle']}};
const bottleBefore=structuredClone(bottle);
const tumbler=vesselPresentation(bottle);
assert.equal(tumbler.kind,'tumbler','Accepted tumbler evidence removes the invented narrow neck');
assert.equal(tumbler.neckHeight,0);
assert.equal(tumbler.handle,true,'The saved/observed side handle is rendered');
assert.equal(tumbler.lid,true);
assert.equal(tumbler.spout,true,'Only an explicitly observed drink spout is added');
assert.equal(tumbler.basis,'accepted_features');
assert.deepEqual(bottle,bottleBefore,'Rendering never rewrites accepted object evidence or saved appearance');
const legacy=vesselPresentation({...bottle,observed_object:null});
assert.equal(legacy.kind,'bottle','Missing historical shape evidence does not invent a tumbler');
assert.equal(legacy.handle,true,'Historical accepted handle accessories are respected even without observations');
assert.equal(legacy.spout,false,'A cap alone does not invent a drink spout');
const unhandled=vesselPresentation({...bottle,visual_spec:{...bottle.visual_spec,accessories:[]},observed_object:{visible_features:['cylindrical body','possibly a handle behind the bottle','lid is not visible']}});
assert.equal(unhandled.handle,false,'Uncertain features do not become geometry');
assert.equal(unhandled.lid,false);
assert.equal(unhandled.kind,'bottle','A cylindrical bottle alone does not imply a neckless tumbler');
const denied=vesselPresentation({...bottle,observed_object:{visible_features:['no handle','without a lid','tumbler-like body is unclear']}});
assert.equal(denied.handle,false,'Explicit absent features override decorative legacy accessories');
assert.equal(denied.lid,false);
assert.equal(denied.kind,'bottle');
assert.equal(vesselPresentation({...bottle,observed_object:{canonical_type_id:'mug',visible_features:['wide tumbler body','drink spout']}}).kind,'bottle','Conflicting observation identities cannot override the accepted object');
assert.equal(vesselPresentation({...bottle,observed_object:{canonical_type_id:'phone',visible_features:['wide tumbler body','drink spout']}}).kind,'bottle','Unrelated observations cannot add vessel features');
assert.equal(vesselPresentation({...bottle,observed_object:{canonical_type_id:'bottle',label:'coffee mug',visible_features:['wide tumbler body','drink spout']}}).kind,'bottle','A contradictory observed label cannot refine the accepted silhouette');
assert.equal(vesselPresentation({...bottle,object_type:'mug'}),null,'Conflicting known object identities get no vessel refinement');
assert.equal(vesselPresentation({...bottle,visual_spec:{...bottle.visual_spec,template_id:'generic'}}),null,'Unsupported generic objects keep their existing photo fallback');
const mug=vesselPresentation({object_type:'mug',canonical_type_id:'mug',visual_spec:{template_id:'mug',accessories:['handle'],proportions:{width:1.1,height:1}},observed_object:{canonical_type_id:'mug',visible_features:['ceramic body','curved side handle','open top']}});
assert.equal(mug.kind,'mug');assert.equal(mug.lid,false);assert.equal(mug.neckHeight,0);
for(const width of [.7,1,1.4,NaN]) for(const height of [.7,1,1.4,Infinity]) {
  const shape=vesselPresentation({...bottle,visual_spec:{...bottle.visual_spec,proportions:{width,height}}});
  assert.ok([shape.bodyHeight,shape.radiusTop,shape.radiusBottom,shape.neckHeight,shape.lidRadius].every(Number.isFinite),'Malformed proportions cannot poison the rig');
  assert.ok(shape.bodyHeight>=1 && shape.bodyHeight<1.5 && shape.radiusTop>.4 && shape.radiusTop<.5,'Saved ratios refine the body within conservative bounds');
}
const {default:VesselShape}=await import(componentModule('../src/components/VesselShape.tsx',{'./ObjectRig':rigUrl,three:import.meta.resolve('three')}));
const vesselBounds={};
for(const [kind,shape] of [['tumbler',tumbler],['legacy',legacy],['mug',mug],['unhandled',unhandled]]) {
  const named=new Map();
  const tree=VesselShape({shape,color:'#5BCBF5',accent:'#8BE3F8',feet:true,eyes:true,arms:true});
  const box=geometryBounds(tree,undefined,named);const size=box.getSize(new THREE.Vector3());
  assert.ok(size.x<1.6 && size.y<2.1 && size.z<1.3,`${kind} remains bounded and recognizable`);
  assert.ok(box.min.y>-.01 && box.min.y<.03,`${kind} actual feet remain grounded`);
  assert.equal(named.has('sc-vessel-handle'),shape.handle);
  assert.equal(named.has('sc-vessel-lid'),shape.lid);
  assert.equal(named.has('sc-vessel-neck'),shape.neckHeight>0);
  if(shape.handle) {
    const handle=named.get('sc-vessel-handle'),body=named.get('sc-vessel-body');
    assert.ok(handle.max.x>body.max.x+.25,'Actual side handle extends beyond the body');
    assert.ok(handle.min.x<body.max.x && handle.min.y>body.min.y && handle.max.y<body.max.y+.1,'The handle intersects the body securely rather than floating');
  }
  vesselBounds[kind]=named.get('sc-vessel-body').getSize(new THREE.Vector3());
}
assert.ok(vesselBounds.tumbler.x>vesselBounds.unhandled.x*1.25,'Actual tumbler body is visibly broader than an ordinary bottle');
assert.ok(vesselBounds.mug.x/vesselBounds.mug.y>.85,'Actual mug remains a broad cup, not a thin bottle');
console.log('Evidence-backed vessel checks passed: actual handled tumbler, capped bottle and open mug geometry; conservative uncertainty/conflict handling; bounded proportions; immutable observations; same shared island and preview renderer.');
