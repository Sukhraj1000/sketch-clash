import { useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Box3, Color, Group, Mesh, MeshStandardMaterial, OrthographicCamera, Vector3 } from 'three';
import type { Object3D } from 'three';
import type { MotionValue } from 'motion/react';
import type { Fighter } from '../types';
import type { BattleEvent, BattleOutcome } from '../game/battle';
import { getImpact } from '../game/battle';
import { getBattleFighter3DPose } from '../game/battle3d';
import type { CharacterVisual } from './WorldScene';
import { characterDisplayScale } from './objectPresentation';
import BattleObjectShape from './BattleObjectShape';

type Props = {
  fighters: [Fighter, Fighter]; elapsed: MotionValue<number>; events: readonly BattleEvent[];
  reduced: boolean; winnerSlot: 0 | 1; outcome: BattleOutcome;
  onReady: () => void; onFailure: () => void;
};
const TEAM_COLORS = ['#FF596E', '#66E0D4'];

/** Old saves without a render spec get a clearly stylised solid avatar. The
 * source photograph remains in the review/result, never on the fighting mesh. */
function visualFor(fighter: Fighter): CharacterVisual {
  return fighter.characterVisual ?? {
    display_name: fighter.name, object_type: '', image_ref: '',
    visual_spec: { template_id: 'generic', palette: [TEAM_COLORS[fighter.side], '#FFD166'],
      scale: 1, proportions: { width: 1, height: 1 }, accessories: ['eyes', 'arms', 'feet'],
      animation_style: 'bouncy', appearance_seed: fighter.side, schema_version: 'battle-fallback-1' },
  };
}

function Actor({ fighter, elapsed, events, reduced, winnerSlot, outcome }: Omit<Props, 'fighters' | 'onReady' | 'onFailure'> & { fighter: Fighter }) {
  const actor = useRef<Group>(null);
  const fit = useRef<Group>(null);
  const model = useRef<Group>(null);
  const rig = useRef<Record<string, Object3D | undefined>>({});
  const corners = useRef<Vector3[]>([]);
  const sample = useMemo(() => new Vector3(), []);
  const materials = useRef<{ material: MeshStandardMaterial; intensity: number; emissive: Color }[]>([]);
  const visual = useMemo(() => visualFor(fighter), [fighter]);
  const size = useThree(state => state.size);
  const stageScale = size.width < 640 ? .65 : 1;
  useLayoutEffect(() => {
    if (!model.current || !fit.current) return;
    // Measure in model space, independent of the fighter's current stage pose
    // and of Strict Mode's repeated layout-effect setup.
    const measured = model.current.clone(true);
    measured.updateWorldMatrix(true, true);
    const box = new Box3().setFromObject(measured);
    const bounds = box.getSize(new Vector3()), center = box.getCenter(new Vector3());
    const scale = Math.min(2.25 / Math.max(.1, bounds.y), 2.2 / Math.max(.1, bounds.x), 1.7 / Math.max(.1, bounds.z));
    fit.current.scale.setScalar(scale);
    fit.current.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale);
    corners.current = [-bounds.x / 2, bounds.x / 2].flatMap(x => [0, bounds.y].flatMap(y => [-bounds.z / 2, bounds.z / 2].map(z => new Vector3(x * scale, y * scale, z * scale))));
    rig.current = Object.fromEntries(['sc-arm-left', 'sc-arm-right', 'sc-foot-left', 'sc-foot-right', 'sc-foot-back-left', 'sc-foot-back-right', 'sc-eyes'].map(name => [name, model.current?.getObjectByName(name)]));
    const unique = new Set<MeshStandardMaterial>();
    model.current.traverse(node => {
      if (!(node instanceof Mesh)) return;
      for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
        if (material instanceof MeshStandardMaterial) unique.add(material);
      }
    });
    materials.current = [...unique].map(material => ({ material, intensity: material.emissiveIntensity, emissive: material.emissive.clone() }));
  }, [visual]);
  useFrame(() => {
    if (!actor.current) return;
    const pose = getBattleFighter3DPose(elapsed.get(), fighter.side, reduced, events, winnerSlot, outcome);
    actor.current.position.set(pose.x * stageScale, pose.y, pose.z);
    actor.current.rotation.set(pose.rotationX, pose.rotationY, pose.rotationZ);
    actor.current.scale.setScalar(pose.scale);
    if (pose.action === 'defeated') {
      // A tipped-over mug or tall battery rests on the stage rather than
      // disappearing through it. Use the measured solid bounds, not its photo.
      const floor = Math.min(0, ...corners.current.map(corner => sample.copy(corner).multiplyScalar(pose.scale).applyEuler(actor.current!.rotation).y));
      actor.current.position.y -= floor;
    }
    const parts = rig.current;
    if (parts['sc-arm-left']) parts['sc-arm-left'].rotation.set(pose.armLeftX, 0, pose.armLeftZ);
    if (parts['sc-arm-right']) parts['sc-arm-right'].rotation.set(pose.armRightX, 0, pose.armRightZ);
    for (const name of ['sc-foot-left', 'sc-foot-back-right']) if (parts[name]) parts[name]!.rotation.x = pose.footLeftX;
    for (const name of ['sc-foot-right', 'sc-foot-back-left']) if (parts[name]) parts[name]!.rotation.x = pose.footRightX;
    if (parts['sc-eyes']) parts['sc-eyes'].scale.y = pose.blink;
    for (const { material, intensity, emissive } of materials.current) {
      if (pose.flash) material.emissive.set('#FFF0B0'); else material.emissive.copy(emissive);
      material.emissiveIntensity = pose.flash ? .8 : intensity;
    }
  });
  return <group ref={actor} name={`battle-fighter-${fighter.side}`} position={[(fighter.side ? 2.3 : -2.3) * stageScale, 0, 0]}>
    <group ref={fit}><group ref={model} scale={characterDisplayScale(visual)}><BattleObjectShape character={visual} /></group></group>
  </group>;
}

function ArenaRig({ fighters, elapsed, events, reduced, winnerSlot, outcome, onReady, onFailure }: Props) {
  const { camera, size, gl } = useThree();
  const readyFrames = useRef(0);
  const impact = useRef<Group>(null);
  const sparks = useRef<(Mesh | null)[]>([]);
  const stageScale = size.width < 640 ? .65 : 1;
  useEffect(() => {
    const lost = (event: Event) => { event.preventDefault(); onFailure(); };
    const previousShaderHandler = gl.debug.onShaderError;
    gl.debug.onShaderError = () => onFailure();
    gl.domElement.addEventListener('webglcontextlost', lost);
    return () => { gl.domElement.removeEventListener('webglcontextlost', lost); gl.debug.onShaderError = previousShaderHandler; };
  }, [gl, onFailure]);
  useFrame(() => {
    const t = elapsed.get();
    const hit = getImpact(t, events);
    const age = hit ? t - hit.at : 1000;
    if (camera instanceof OrthographicCamera) {
      const push = !reduced && hit?.kind === 'finisher' && age < 600 ? .045 * Math.sin(Math.PI * age / 600) : 0;
      camera.zoom = size.width / (size.width < 640 ? 6.8 : 10.4) * (1 + push);
      camera.position.set(0, 5, 12);
      camera.lookAt(0, 1.05, 0);
      camera.updateProjectionMatrix();
    }
    if (impact.current) {
      impact.current.visible = !reduced && !!hit && age < 520;
      if (hit) {
        const defender = hit.attacker === 0 ? 1 : 0;
        const pose = getBattleFighter3DPose(t, defender, reduced, events, winnerSlot, outcome);
        impact.current.position.set(pose.x * stageScale, 1.1, .45);
        const p = Math.max(0, age - 80) / 440;
        sparks.current.forEach((spark, index) => {
          if (!spark) return;
          const angle = index * Math.PI * 2 / 10;
          spark.position.set(Math.cos(angle) * p * 1.5, Math.sin(angle) * p * 1.25 - p * p * .65, Math.sin(index * 7) * p * .7);
          spark.rotation.set(p * 6, index, p * 5);
          spark.scale.setScalar(Math.max(.01, 1 - p));
        });
      }
    }
    // Keep the authoritative playback at zero until the arena has rendered.
    if (++readyFrames.current === 3) onReady();
  });
  return <>
    <ambientLight intensity={.75} />
    <hemisphereLight args={['#FFFAEC', '#958C94', 1.6]} />
    <directionalLight position={[-4, 8, 5]} intensity={2.6} castShadow shadow-mapSize={[1024, 1024]} shadow-camera-left={-7} shadow-camera-right={7} shadow-camera-top={5} shadow-camera-bottom={-4} shadow-normalBias={.035} />
    <directionalLight position={[5, 3, -4]} intensity={1.5} color="#90E7DA" />
    <group scale={[stageScale, 1, 1]}>
      <mesh position={[0, -.19, 0]} receiveShadow><cylinderGeometry args={[5.05, 5.15, .36, 64]} /><meshStandardMaterial color="#E5D4B5" roughness={.9} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .001, 0]} receiveShadow><circleGeometry args={[5.05, 64]} /><meshStandardMaterial color="#F5EBD5" roughness={.9} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .012, 0]}><ringGeometry args={[4.86, 4.9, 64]} /><meshBasicMaterial color="#B5A58C" /></mesh>
      {[-2.3, 2.3].map((x, index) => <mesh key={x} rotation={[-Math.PI / 2, 0, 0]} position={[x, .02, 0]}><ringGeometry args={[.78, .83, 48]} /><meshBasicMaterial color={TEAM_COLORS[index]} transparent opacity={.45} /></mesh>)}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .025, 0]}><planeGeometry args={[.025, 5]} /><meshBasicMaterial color="#C6B596" /></mesh>
    </group>
    {fighters.map(fighter => <Actor key={fighter.id} fighter={fighter} elapsed={elapsed} events={events} reduced={reduced} winnerSlot={winnerSlot} outcome={outcome} />)}
    <group ref={impact} visible={false}>{Array.from({ length: 10 }, (_, index) => <mesh key={index} ref={node => { sparks.current[index] = node; }}><octahedronGeometry args={[index % 2 ? .08 : .13]} /><meshBasicMaterial color={index % 3 ? '#FFD166' : '#FF596E'} /></mesh>)}</group>
  </>;
}

export default function BattleScene(props: Props) {
  return <div className="battle-scene" role="img" aria-label={`Animated 3D battle: ${props.fighters[0].name} versus ${props.fighters[1].name}`}>
    <Canvas orthographic shadows="percentage" dpr={[1, 1.5]} camera={{ position: [0, 5, 12], zoom: 90, near: .1, far: 60 }} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}>
      <ArenaRig {...props} />
    </Canvas>
  </div>;
}
