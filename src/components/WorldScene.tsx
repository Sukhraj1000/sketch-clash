import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Line, OrbitControls } from '@react-three/drei'
import { CanvasTexture, Group, Mesh, OrthographicCamera, SRGBColorSpace, Texture, TextureLoader, Vector3 } from 'three'
import type { MeshBasicMaterial } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { safeIslandPoint } from '../lib/island'
import type { IslandAgent, IslandSimulation, IslandTaskKind } from '../lib/island'
import IslandStructure from './IslandStructures'
import { projectBenefit } from '../lib/projectBenefits'
import FactoryEnvironment from './FactoryEnvironment'
import { WORLD_MAP_SURFACE_SCALE, WORLD_PATHS, WORLD_STATIONS, WORLD_STATION_BACKSETS, WORLD_TREES, WORLD_WAYFINDER, worldGroundDetails, worldGroundShape, worldRimDecor } from './worldMap'
import FactoryLighting from './FactoryLighting'
import FactoryWorkProp from './FactoryWorkProp'
import RobotShape from './RobotShape'
import AgentTaskBadge from './AgentTaskBadge'
import { advanceRobotWheels, approachResidentPosition, residentAmbientMotion, robotWorkPose } from './robotMotion'
import type { RobotWheelState } from './robotMotion'
import ObjectShapes from './ObjectShapes'
import VesselShape from './VesselShape'
import { vesselPresentation } from './vesselPresentation'
import { furniturePresentation } from './furniturePresentation'
import { ObjectArms as Arms, ObjectFace as Face, ObjectFeet as Feet } from './ObjectRig'
import { objectSilhouette } from './objectIdentity'
import { objectPose } from './objectMotion'
import { characterDisplayScale, displayIslandPoint, residentDisplayPose, residentDisplaySlots } from './objectPresentation'
import type { ObjectActivity, ObjectWork } from './objectMotion'
import type { Object3D } from 'three'
import type { ThreeEvent } from '@react-three/fiber'
import type { WorldCharacter } from './WorldView'

type SceneProps = { presentation?: 'island' | 'factory'; characters: WorldCharacter[]; layoutSeed: number; selectedId: string | null; onSelect: (id: string) => void; active: boolean; reducedMotion: boolean; arrivalIds: string[]; onArrived: (id: string) => void; onFailure: () => void; simulation?: IslandSimulation; selectedProjectId?: string | null; onProjectSelect?: (id: string) => void; cameraResetKey?: number; followSelected?: boolean }
type WorldClock = { serverMs: number; receivedAt: number; paused: boolean }
const worldTime = (clock: WorldClock) => clock.serverMs + (clock.paused ? 0 : performance.now() - clock.receivedAt)
const INK = '#1E1C29'
const PAPER = '#FFF9EB'
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, Number.isFinite(value) ? value : 1))
const seedValue = (seed: number, offset = 0) => Math.abs(Math.sin(seed * .01713 + offset * 13.123) * 43758.5453) % 1

function Material({ color }: { color: string }) { return <meshStandardMaterial color={color} roughness={.82} flatShading /> }

/** Only a durable, same-origin media reference becomes a texture; it is never executable model output. */
function PhotoBadge({ image, onAssetState }: { image: string; onAssetState?: (state: 'ready' | 'failed') => void }) {
  const [texture, setTexture] = useState<Texture | null>(null)
  const [ratio, setRatio] = useState(1)
  const invalidate = useThree(state => state.invalidate)
  useEffect(() => {
    if (!/^\/api\/media\/[a-f0-9]{64}$/.test(image)) { onAssetState?.('failed'); return }
    let alive = true
    let owned: Texture | null = null
    const loader = new TextureLoader()
    loader.load(image, loaded => {
      if (!alive) { loaded.dispose(); return }
      owned = loaded
      loaded.colorSpace = SRGBColorSpace
      const source = loaded.image as { width?: number; height?: number }
      setRatio(clamp((source.width || 1) / (source.height || 1), .25, 4))
      setTexture(loaded)
      onAssetState?.('ready')
      invalidate()
    }, undefined, () => { if (alive) { onAssetState?.('failed'); invalidate() } })
    return () => { alive = false; owned?.dispose() }
  }, [image, invalidate, onAssetState])
  const width = Math.min(.65, .62 * ratio)
  const height = width / ratio
  return <group position={[0, .68, .302]}><mesh><planeGeometry args={[.74, .73]} /><meshBasicMaterial color={PAPER} /></mesh>{texture && <mesh position={[0, 0, .004]}><planeGeometry args={[width, height]} /><meshBasicMaterial map={texture} toneMapped={false} /></mesh>}</group>
}

export type CharacterVisual = Pick<WorldCharacter, 'visual_spec' | 'image_ref'> & Partial<Pick<WorldCharacter, 'display_name' | 'object_type' | 'canonical_type_id' | 'observed_object'>>

export function CharacterShape({ character, onAssetState }: { character: CharacterVisual; onAssetState?: (state: 'ready' | 'failed') => void }) {
  const spec = character.visual_spec
  const palette = spec.palette.filter(color => /^#[0-9A-Fa-f]{6}$/.test(color))
  const color = palette[0] ?? '#66E0D4'
  const accent = palette[1] ?? '#FFD166'
  const feet = spec.accessories.includes('feet')
  const eyes = spec.accessories.includes('eyes')
  const arms = spec.accessories.includes('arms')
  const template = spec.template_id
  const silhouette = objectSilhouette(template, character.object_type, character.canonical_type_id)
  const furniture = silhouette === 'table' || silhouette === 'chair' ? furniturePresentation(silhouette, character.observed_object) : undefined
  const vessel = silhouette ? null : vesselPresentation(character)
  useEffect(() => { if (silhouette || template !== 'generic') onAssetState?.('ready') }, [silhouette, template, onAssetState])
  return <group name="sc-character" userData={{ rigKey: `${template}:${silhouette ?? vessel?.kind ?? 'photo'}:${vessel?.handle}:${vessel?.lid}:${furniture?.stretchers}:${furniture?.taperedLegs}:${spec.accessories.join(',')}` }}>
    {feet && !silhouette && !vessel && <Feet />}
    {silhouette ? <ObjectShapes kind={silhouette} color={color} accent={accent} feet={feet} eyes={eyes} arms={arms} furnitureFeatures={furniture} /> : vessel ? <VesselShape shape={vessel} color={color} accent={accent} feet={feet} eyes={eyes} arms={arms} /> : template === 'mug' ? <group>
      <mesh position={[0, .67, 0]} castShadow><cylinderGeometry args={[.48, .43, .96, 12]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.154, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.37, 12]} /><Material color="#6D5142" /></mesh>
      <mesh position={[0, 1.15, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[.427, .055, 5, 12]} /><Material color={accent} /></mesh>
      <mesh position={[.52, .7, 0]} castShadow><torusGeometry args={[.285, .085, 6, 12]} /><Material color={color} /></mesh>
      {eyes && <Face y={.82} z={.44} />}{arms && <Arms color={accent} width={.49} />}
    </group> : template === 'bottle' ? <group>
      <mesh position={[0, .76, 0]} castShadow><cylinderGeometry args={[.32, .36, 1.13, 10]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.38, 0]} castShadow><cylinderGeometry args={[.16, .32, .22, 10]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.58, 0]} castShadow><cylinderGeometry args={[.16, .16, .24, 10]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.74, 0]} castShadow><cylinderGeometry args={[.195, .195, .12, 10]} /><Material color={accent} /></mesh>
      <mesh position={[0, .65, 0]}><cylinderGeometry args={[.327, .348, .35, 10]} /><Material color={accent} /></mesh>
      {eyes && <Face y={1.03} z={.31} width={.12} />}{arms && <Arms color={accent} width={.36} />}
    </group> : template === 'plant' ? <group>
      <mesh position={[0, .54, 0]} castShadow><cylinderGeometry args={[.45, .3, .7, 8]} /><Material color={color} /></mesh>
      <mesh position={[0, .91, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.4, 8]} /><Material color="#5D4636" /></mesh>
      <mesh position={[0, 1.23, 0]}><cylinderGeometry args={[.04, .055, .65, 5]} /><Material color="#4E8061" /></mesh>
      {[-1, 1].map((side, index) => <mesh key={side} position={[side * .2, 1.35 + index * .15, 0]} rotation={[0, 0, side * -.65]} scale={[.55, 1, .35]} castShadow><octahedronGeometry args={[.38]} /><Material color={accent} /></mesh>)}
      {eyes && <Face y={.65} z={.4} />}
    </group> : template === 'book' ? <group>
      <mesh position={[0, .84, 0]} castShadow><boxGeometry args={[.91, 1.25, .42]} /><Material color={color} /></mesh>
      <mesh position={[.045, .84, .015]}><boxGeometry args={[.78, 1.13, .435]} /><Material color={PAPER} /></mesh>
      <mesh position={[0, .84, .25]} castShadow><boxGeometry args={[.94, 1.27, .07]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.18, .291]}><boxGeometry args={[.53, .06, .015]} /><Material color={accent} /></mesh>
      {eyes && <Face y={.93} z={.31} />}{arms && <Arms color={accent} width={.49} />}
    </group> : template === 'ball' ? <group>
      <mesh position={[0, .76, 0]} castShadow><icosahedronGeometry args={[.62, 1]} /><Material color={color} /></mesh>
      <mesh position={[0, .76, 0]} rotation={[.3, 0, .3]}><torusGeometry args={[.605, .035, 4, 14]} /><Material color={accent} /></mesh>
      {eyes && <Face y={.93} z={.56} />}{arms && <Arms color={accent} width={.66} />}
    </group> : <group>
      <mesh position={[0, .83, 0]} castShadow><boxGeometry args={[.93, 1.3, .6]} /><Material color={color} /></mesh>
      <PhotoBadge image={character.image_ref} onAssetState={onAssetState} />
      {eyes && <Face y={1.29} z={.31} />}{arms && <Arms color={accent} width={.50} />}
    </group>}
  </group>
}

export type CharacterActivity = ObjectActivity

type RigBindings = { root: Object3D | undefined; key: string; eyes?: Object3D; leftArm?: Object3D; rightArm?: Object3D; leftFoot?: Object3D; rightFoot?: Object3D; backLeftFoot?: Object3D; backRightFoot?: Object3D; tail?: Object3D; detail?: Object3D; detailLeft?: Object3D; detailRight?: Object3D; wheels: (Object3D | undefined)[] }
const rigs = new WeakMap<Group, RigBindings>()
function characterRig(body: Group) {
  const root = body.getObjectByName('sc-character')
  const key = String(root?.userData.rigKey ?? '')
  const previous = rigs.get(body)
  if (previous && previous.root === root && previous.key === key) return previous
  const find = (name: string) => root?.getObjectByName(name)
  const rig = { root, key, eyes: find('sc-eyes'), leftArm: find('sc-arm-left'), rightArm: find('sc-arm-right'), leftFoot: find('sc-foot-left'), rightFoot: find('sc-foot-right'), backLeftFoot: find('sc-foot-back-left'), backRightFoot: find('sc-foot-back-right'), tail: find('sc-tail'), detail: find('sc-detail'), detailLeft: find('sc-detail-left'), detailRight: find('sc-detail-right'), wheels: [-1, 1].flatMap(side => [-1, 1].map(axle => find(`robot-wheel-${side}-${axle}`))) }
  rigs.set(body, rig)
  return rig
}

/** Shared, bounded body/limb pose code. It only changes scene nodes, never game records. */
export function animateCharacterBody(body: Group, style: WorldCharacter['visual_spec']['animation_style'], activity: CharacterActivity, time: number, phase = 0, reducedMotion = false, work?: ObjectWork) {
  const pose = objectPose(style, activity, time, phase, reducedMotion, work)
  body.position.y = pose.y
  body.rotation.set(pose.pitch, pose.yaw, pose.roll)
  body.scale.set(1, pose.scaleY, 1)
  const rig = characterRig(body)
  if (rig.eyes) rig.eyes.scale.y = pose.blink
  if (rig.leftArm) { rig.leftArm.rotation.x = pose.leftArmX; rig.leftArm.rotation.z = pose.leftArmZ }
  if (rig.rightArm) { rig.rightArm.rotation.x = pose.rightArmX; rig.rightArm.rotation.z = pose.rightArmZ }
  for (const [foot, rotation, lift] of [[rig.leftFoot, pose.leftFootX, pose.leftFootY], [rig.rightFoot, pose.rightFootX, pose.rightFootY], [rig.backLeftFoot, pose.rightFootX, pose.rightFootY], [rig.backRightFoot, pose.leftFootX, pose.leftFootY]] as const) {
    if (!foot) continue
    const stride = Number(foot.userData.strideScale ?? 1)
    foot.rotation.x = rotation * stride
    foot.position.y = Number(foot.userData.restY ?? .14) + lift * stride * Number(foot.userData.liftScale ?? 1)
  }
  if (rig.tail) rig.tail.rotation.y = pose.tail
  if (rig.detail) rig.detail.rotation.x = pose.detail
  if (rig.detailLeft) rig.detailLeft.rotation.z = Number(rig.detailLeft.userData.restZ ?? -.2) - Math.abs(pose.detail)
  if (rig.detailRight) rig.detailRight.rotation.z = Number(rig.detailRight.userData.restZ ?? .2) + Math.abs(pose.detail)
}

function WorkProp({ kind, active, reducedMotion }: { kind?: IslandTaskKind; active: boolean; reducedMotion: boolean }) {
  const effect = useRef<Group>(null)
  useFrame(({ clock }) => {
    if (!effect.current || !active || reducedMotion) return
    const time = clock.elapsedTime
    if (kind === 'water' || kind === 'tend') effect.current.children.forEach((drop, i) => {
      const phase = (time * 1.1 + i / 5) % 1
      drop.position.set(.15 + phase * .5, .65 - phase * .65, .42 + phase * .38)
      drop.scale.setScalar(Math.sin(phase * Math.PI))
    })
    else if (kind === 'build' || kind === 'measure') effect.current.rotation.z = Math.sin(time * 5) * .33
    else if (kind === 'charge' || kind === 'signal') effect.current.rotation.y = time * 1.4
    else effect.current.rotation.z = Math.sin(time * 2) * .045
  })
  if (!kind || kind === 'rest' || kind === 'explore') return null
  if (kind === 'water' || kind === 'tend') return <group ref={effect}>{Array.from({ length: 5 }, (_, i) => <mesh key={i} position={[.3, .5, .5]}><sphereGeometry args={[.055, 5, 4]} /><meshBasicMaterial color="#6FDFFF" /></mesh>)}</group>
  if (kind === 'plan') return <group ref={effect} position={[.28, .63, .55]} rotation={[-.3, 0, -.15]}><mesh><boxGeometry args={[.5, .36, .025]} /><Material color="#FFF8DB" /></mesh>{[0, 1, 2].map(i => <mesh key={i} position={[-.03, .09 - i * .08, .02]}><boxGeometry args={[.3 - i * .04, .018, .01]} /><Material color="#6D92B8" /></mesh>)}</group>
  if (kind === 'measure') return <group ref={effect} position={[.46, .5, .35]}><mesh><boxGeometry args={[.65, .08, .06]} /><Material color="#FFCF58" /></mesh>{[-.22, -.1, .02, .14, .26].map(x => <mesh key={x} position={[x, .02, .04]}><boxGeometry args={[.018, .04, .01]} /><Material color={INK} /></mesh>)}</group>
  if (kind === 'build') return <group ref={effect} position={[.5, .6, .3]}><mesh position={[0, .1, 0]}><boxGeometry args={[.06, .45, .06]} /><Material color="#9C6845" /></mesh><mesh position={[0, .34, 0]}><boxGeometry args={[.3, .14, .14]} /><Material color="#52677F" /></mesh></group>
  if (kind === 'charge' || kind === 'signal') return <group ref={effect} position={[0, 1.55, 0]}>{[0, 1, 2].map(i => <mesh key={i} position={[Math.sin(i * 2.09) * .3, 0, Math.cos(i * 2.09) * .3]}><octahedronGeometry args={[.07]} /><meshBasicMaterial color="#FFD367" /></mesh>)}</group>
  return <group ref={effect} position={[0, .5, .48]}><mesh castShadow><boxGeometry args={[.53, .4, .35]} /><Material color="#D3A16A" /></mesh>{[-.17, .17].map(x => <mesh key={x} position={[x, 0, .184]}><boxGeometry args={[.05, .41, .03]} /><Material color="#745236" /></mesh>)}<mesh position={[0, 0, .184]}><boxGeometry args={[.54, .045, .03]} /><Material color="#745236" /></mesh></group>
}

function Resident({ character, agent, clock, positions, slot, selected, onSelect, active, reducedMotion, arriving, onArrived, presentation, workTarget }: { presentation: 'island' | 'factory'; character: WorldCharacter; agent?: IslandAgent; clock: WorldClock; positions: Map<string, Vector3>; slot: { x: number; z: number }; selected: boolean; onSelect: (id: string) => void; active: boolean; reducedMotion: boolean; arriving: boolean; onArrived: (id: string) => void; workTarget?: { x: number; z: number } }) {
  const root = useRef<Group>(null)
  const body = useRef<Group>(null)
  const work = useRef<Group>(null)
  const elapsed = useRef(0)
  const arrivalReported = useRef(false)
  const wheels = useRef<RobotWheelState>({ distanceAngle: 0, angle: 0 })
  const displayDistance = useRef(0)
  const now = useMemo(() => () => worldTime(clock), [clock])
  const spec = character.visual_spec
  const seed = Number.isFinite(spec.appearance_seed) ? spec.appearance_seed : 0
  const phase = seedValue(seed) * Math.PI * 2
  const displaySlot = useRef({ ...slot })
  const home = safeIslandPoint({ x: character.home_position.x, z: character.home_position.z })
  const initial = agent ? residentDisplayPose(agent.task, agent.position, worldTime(clock), slot) : { ...displayIslandPoint(home, slot), heading: .6 }
  // Robot proportions are fixed; saved photo/template dimensions must not stretch the chassis.
  const factory = presentation === 'factory'
  const displayScale: [number, number, number] = factory ? [1, 1, 1] : characterDisplayScale(character, .7)
  useEffect(() => { positions.set(character.id, new Vector3(initial.x, .5, initial.z)); return () => { positions.delete(character.id) } }, [character.id, positions])
  useFrame((_, delta) => {
    if (!root.current || !body.current || !active) return
    if (!clock.paused && !reducedMotion) elapsed.current += Math.min(delta, .05)
    const time = elapsed.current
    let moving = !factory && character.state.activity === 'wander' && !agent && !clock.paused
    let working = false
    let taskVisible = false
    let taskTravelling = false
    let heading = .6
    const previousX = root.current.position.x, previousZ = root.current.position.z
    const settle = reducedMotion ? 1 : Math.min(1, delta * 2)
    displaySlot.current.x += (slot.x - displaySlot.current.x) * settle
    displaySlot.current.z += (slot.z - displaySlot.current.z) * settle
    if (agent) {
      const pose = residentDisplayPose(agent.task, agent.position, worldTime(clock), displaySlot.current)
      const ambient = residentAmbientMotion(agent.task, agent.position, worldTime(clock), time, seed, reducedMotion)
      const display = approachResidentPosition(root.current.position, { x: pose.x + ambient.x, z: pose.z + ambient.z }, delta, reducedMotion)
      if (!clock.paused) root.current.position.set(display.x, .03, display.z)
      const catchingUp = Math.hypot(display.x - pose.x, display.z - pose.z) > .12 && !ambient.ambient
      moving = (pose.travelling || ambient.moving || catchingUp) && !clock.paused
      working = pose.working && !catchingUp
      taskTravelling = pose.travelling
      taskVisible = pose.progress > 0 && pose.progress < 1
      heading = ambient.ambient ? ambient.heading : catchingUp ? Math.atan2(pose.x - display.x, pose.z - display.z) : pose.heading
      // Face the actual station/project while working, rather than keeping the travel heading.
      if (working && workTarget) heading = Math.atan2(workTarget.x - pose.x, workTarget.z - pose.z)
    } else {
      const place = displayIslandPoint(home, displaySlot.current)
      root.current.position.set(place.x + (moving && !reducedMotion ? Math.sin(time * .22 + phase) * .3 : 0), .03, place.z + (moving && !reducedMotion ? Math.cos(time * .19 + phase) * .3 : 0))
      heading = moving ? Math.atan2(Math.cos(time * .22 + phase) * .22, -Math.sin(time * .19 + phase) * .19) : .2
    }
    const angleDelta = Math.atan2(Math.sin(heading - root.current.rotation.y), Math.cos(heading - root.current.rotation.y))
    if (!clock.paused) root.current.rotation.y += reducedMotion ? angleDelta : angleDelta * Math.min(1, delta * 5)
    const taskKind = agent?.task?.kind
    const gesture = working || (taskTravelling && (taskKind === 'carry' || taskKind === 'forage')) ? taskKind : undefined
    animateCharacterBody(body.current, factory ? 'calm' : spec.animation_style, factory ? 'idle' : moving ? 'wander' : taskKind === 'rest' ? 'rest' : 'idle', time, phase, reducedMotion || clock.paused, gesture)
    // Wheels follow rendered distance, including clearly labelled between-job strolls.
    // Keeping this in the resident preserves the same motion through the reveal.
    if (!clock.paused && !reducedMotion) displayDistance.current += Math.hypot(root.current.position.x - previousX, root.current.position.z - previousZ) / .12
    wheels.current = advanceRobotWheels(wheels.current, 'resident-path', displayDistance.current)
    if (factory) {
      // A mobile industrial chassis rolls level; it never hops, stretches or blinks.
      body.current.position.y = 0
      body.current.rotation.set(0, 0, 0)
      const rig = characterRig(body.current)
      if (rig.eyes) rig.eyes.scale.y = 1
      const mechanical = robotWorkPose(taskKind, working, taskTravelling, time, reducedMotion || clock.paused)
      if (rig.leftArm) rig.leftArm.rotation.set(mechanical.leftArmX, 0, mechanical.leftArmZ)
      if (rig.rightArm) rig.rightArm.rotation.set(mechanical.rightArmX, 0, mechanical.rightArmZ)
      rig.wheels.forEach(wheel => { if (wheel) wheel.rotation.y = reducedMotion ? 0 : -wheels.current.angle })
      const tool = work.current?.getObjectByName('factory-work-tool')
      if (tool) {
        tool.position.set(Number(tool.userData.restX ?? 0) + mechanical.toolX, Number(tool.userData.restY ?? 0) + mechanical.toolY, Number(tool.userData.restZ ?? 0) + mechanical.toolZ)
        tool.rotation.x = Number(tool.userData.restTilt ?? 0) + mechanical.toolTilt
        const bit = tool.getObjectByName('factory-tool-bit')
        if (bit) bit.rotation.y = mechanical.toolSpin
      }
    }
    if (work.current) work.current.visible = !!agent?.task && taskVisible && (working || (taskTravelling && ['carry', 'forage'].includes(agent.task.kind)))
    const arrival = arriving ? reducedMotion ? 1 : Math.min(1, time / 1.15) : 1
    if (arriving && arrival === 1 && !arrivalReported.current) { arrivalReported.current = true; onArrived(character.id) }
    if (!factory) { body.current.position.y += (1 - arrival) * .75; body.current.scale.multiplyScalar(.92 + arrival * .08) }
    positions.get(character.id)?.copy(root.current.position).setY(.5)
  })
  const choose = (event: ThreeEvent<MouseEvent>) => { if (event.delta > 4) return; event.stopPropagation(); onSelect(character.id) }
  return <group ref={root} position={[initial.x, .03, initial.z]} rotation={[0, initial.heading, 0]} onClick={choose}>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .012, 0]}>{factory ? <ringGeometry args={[selected ? .39 : .3, selected ? .42 : .31, 48]} /> : <circleGeometry args={[selected ? .64 : .43, 20]} />}<meshBasicMaterial color={factory ? '#8AB2BC' : selected ? '#FFD166' : '#182B3C'} transparent opacity={factory ? selected ? .85 : 0 : selected ? .8 : .13} depthWrite={false} /></mesh>
    {selected && !factory && <mesh position={[0, 2 * displayScale[1], 0]} rotation={[0, 0, Math.PI]}><coneGeometry args={[.14, .22, 4]} /><Material color="#FF596E" /></mesh>}
    <group scale={displayScale}><group ref={body}>{factory ? <RobotShape character={character} allowedActions={agent?.allowed_actions} /> : <CharacterShape character={character} />}<group ref={work}>{factory ? <FactoryWorkProp kind={agent?.task?.kind} /> : <WorkProp kind={agent?.task?.kind} active={active && !clock.paused} reducedMotion={reducedMotion} />}</group></group></group>
    {agent && <AgentTaskBadge agent={agent} selected={selected} now={now} paused={clock.paused} reducedMotion={reducedMotion} height={factory ? 1.2 : Math.max(1.35, displayScale[1] * 1.95)} />}
  </group>
}

function Water({ active }: { active: boolean }) {
  const ripples = useRef<Group>(null)
  const waves = useRef<Group>(null)
  useFrame(({ clock }) => {
    if (!active) return
    if (ripples.current) ripples.current.children.forEach((ring, index) => {
      const phase = (clock.elapsedTime * .035 + index / 3) % 1
      ring.scale.set(1 + phase * .3, 1 + phase * .3, 1)
      const material = (ring as Mesh).material as MeshBasicMaterial
      material.opacity = (1 - phase) * .18
    })
    if (waves.current) waves.current.children.forEach((wave, i) => { wave.position.y = Math.sin(clock.elapsedTime * .8 + i) * .035; wave.rotation.y = Math.sin(clock.elapsedTime * .11 + i) * .05 })
  })
  return <group position={[0, -.7, 0]}>
    <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[120, 120]} /><meshStandardMaterial color="#49B5E0" roughness={.65} metalness={.06} /></mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .014, 0]}><circleGeometry args={[7.4, 40]} /><meshBasicMaterial color="#6CDEDC" transparent opacity={.55} depthWrite={false} /></mesh>
    <group ref={ripples}>{[0, 1, 2].map(index => <mesh key={index} rotation={[-Math.PI / 2, 0, 0]} position={[0, .028 + index * .002, 0]}><ringGeometry args={[5.8 + index * .5, 5.86 + index * .5, 64]} /><meshBasicMaterial color="#F1FFF7" transparent opacity={.16} depthWrite={false} /></mesh>)}</group>
    <group ref={waves}>{Array.from({ length: 13 }, (_, i) => { const angle = i * 2.4; const radius = 7.9 + i % 4 * 1.3; return <group key={i}><group position={[Math.cos(angle) * radius, .045, Math.sin(angle) * radius]} rotation={[0, angle, 0]}><Line points={[[-.4, 0, .05], [-.15, .012, -.03], [.13, 0, -.05], [.36, 0, .015]]} color="#B4F0F6" lineWidth={2} transparent opacity={.65} /></group></group> })}</group>
  </group>
}

function Tree({ x, z, size = 1, color = '#4B9D47' }: { x: number; z: number; size?: number; color?: string }) {
  return <group position={[x, 0, z]} scale={size}>
    <mesh position={[0, .5, 0]} castShadow><cylinderGeometry args={[.09, .14, 1, 6]} /><Material color="#925E3B" /></mesh>
    <mesh position={[0, 1.15, 0]} castShadow><icosahedronGeometry args={[.63, 0]} /><Material color={color} /></mesh>
    <mesh position={[.26, 1.39, -.05]} scale={[.8, .9, .8]} castShadow><icosahedronGeometry args={[.43, 0]} /><Material color="#82C84C" /></mesh>
    <mesh position={[-.3, 1.27, .1]} scale={[.7, .9, .8]} castShadow><icosahedronGeometry args={[.4, 0]} /><Material color="#69B74A" /></mesh>
  </group>
}

function ChargingDockLabel() {
  const [texture, setTexture] = useState<CanvasTexture | null>(null)
  const invalidate = useThree(state => state.invalidate)
  useEffect(() => {
    // The label stays inside the WebGL scene. A DOM portal would create a second
    // React root whose synchronous cleanup can race scene unmounts in React 19.
    const canvas = document.createElement('canvas')
    canvas.width = 512; canvas.height = 160
    const context = canvas.getContext('2d')
    if (!context) return
    context.fillStyle = PAPER; context.fillRect(0, 0, 512, 160)
    context.strokeStyle = INK; context.lineWidth = 10; context.strokeRect(5, 5, 502, 150)
    context.fillStyle = INK; context.textAlign = 'center'; context.textBaseline = 'middle'
    context.font = '800 39px sans-serif'; context.fillText('SOLAR', 256, 49)
    context.font = '800 49px sans-serif'; context.fillText('CHARGING DOCK', 256, 110)
    const owned = new CanvasTexture(canvas)
    owned.colorSpace = SRGBColorSpace
    setTexture(owned)
    invalidate()
    return () => owned.dispose()
  }, [invalidate])
  return texture ? <sprite name="solar-charging-dock-label" position={[0, 1.65, -.18]} scale={[2.05, .64, 1]} raycast={() => {}}>
    <spriteMaterial map={texture} toneMapped={false} depthWrite={false} />
  </sprite> : null
}

function ChargingDock() {
  return <group name="island-station-energy" position={[WORLD_STATIONS.energy.x, .02, WORLD_STATIONS.energy.z]}><group position={[0, 0, -WORLD_STATION_BACKSETS.energy]}>
    <mesh position={[0, .065, .2]} receiveShadow castShadow><boxGeometry args={[1.22, .13, 1.08]} /><Material color="#D6AB70" /></mesh>
    {[-.42, -.14, .14, .42].map(x => <mesh key={x} position={[x, .14, .2]}><boxGeometry args={[.24, .025, 1.03]} /><Material color="#EDC78B" /></mesh>)}
    <mesh position={[0, .5, -.12]} castShadow><boxGeometry args={[.09, .8, .09]} /><Material color={INK} /></mesh>
    <group position={[0, .99, -.16]} rotation={[-.55, 0, 0]}>
      <mesh castShadow><boxGeometry args={[1.04, .67, .07]} /><Material color={INK} /></mesh>
      <mesh position={[0, 0, .042]}><boxGeometry args={[.92, .55, .025]} /><meshStandardMaterial color="#3678AE" roughness={.28} metalness={.25} /></mesh>
      {[-.31, 0, .31].map(x => <mesh key={x} position={[x, 0, .06]}><boxGeometry args={[.014, .54, .008]} /><Material color="#9DCEE2" /></mesh>)}
      {[-.09, .09].map(y => <mesh key={y} position={[0, y, .06]}><boxGeometry args={[.9, .014, .008]} /><Material color="#9DCEE2" /></mesh>)}
    </group>
    <group position={[-.34, .4, .18]}>
      <mesh castShadow><boxGeometry args={[.3, .43, .29]} /><Material color={INK} /></mesh>
      <mesh position={[0, .235, 0]}><boxGeometry args={[.13, .05, .16]} /><Material color="#FFCF59" /></mesh>
      {[0, 1, 2].map(i => <mesh key={i} position={[0, -.12 + i * .12, .151]}><boxGeometry args={[.21, .08, .012]} /><Material color={i === 2 ? '#FFCF59' : '#B0D965'} /></mesh>)}
    </group>
    <mesh position={[.22, .16, .48]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.27, 12]} /><Material color={INK} /></mesh>
    <mesh position={[.22, .174, .48]} rotation={[-Math.PI / 2, 0, 0]}><torusGeometry args={[.19, .025, 4, 12]} /><Material color="#FFCF59" /></mesh>
    <Line points={[[-.23, .3, .33], [-.11, .18, .58], [.03, .18, .61], [.16, .18, .5]]} color={INK} lineWidth={3} />
    <ChargingDockLabel />
  </group></group>
}

function Island({ seed }: { seed: number }) {
  const shape = worldGroundShape()
  const rim = useMemo(() => worldRimDecor(seed), [seed])
  return <group>
    <mesh name="island-map-foundation" position={[0, -.69, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow castShadow><extrudeGeometry args={[shape, { depth: .48, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .22, bevelThickness: .1 }]} /><Material color="#C79961" /></mesh>
    <mesh name="island-map-shoulder" position={[0, -.14, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[1.04, 1.04, 1]} receiveShadow><shapeGeometry args={[shape]} /><Material color="#F5D394" /></mesh>
    <mesh name="island-map-surface" position={[0, -.08, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[WORLD_MAP_SURFACE_SCALE, WORLD_MAP_SURFACE_SCALE, 1]} receiveShadow><extrudeGeometry args={[shape, { depth: .08, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .04, bevelThickness: .02 }]} /><Material color="#8CCB56" /></mesh>
    <mesh name="island-map-hub" position={[0, .012, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.82, 8]} /><Material color="#E7C690" /></mesh>
    {WORLD_PATHS.map((points, index) => <group key={index} name={`island-map-route-${index}`} userData={{ mapPoints: points }}><Line points={points} color="#E7C690" lineWidth={17} /></group>)}
    {WORLD_TREES.map((tree, index) => <group key={index} name={`island-map-utility-${index}`} position={[tree.x, 0, tree.z]} scale={tree.size}><Tree x={0} z={0} color={tree.color} /></group>)}
    <group name="island-station-materials" position={[WORLD_STATIONS.materials.x, .02, WORLD_STATIONS.materials.z]} />
    <ChargingDock />
    <group name="island-station-water" position={[WORLD_STATIONS.water.x, .02, WORLD_STATIONS.water.z]}><group position={[0, 0, -WORLD_STATION_BACKSETS.water]}>
      <mesh position={[0, .18, 0]} castShadow><cylinderGeometry args={[.52, .56, .34, 10]} /><Material color="#9FBBB8" /></mesh>
      <mesh position={[0, .36, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.39, 12]} /><meshStandardMaterial color="#46BADD" roughness={.2} /></mesh>
      {[-.46, .46].map(x => <mesh key={x} position={[x, .66, 0]} castShadow><boxGeometry args={[.08, 1, .08]} /><Material color="#966A43" /></mesh>)}
      <mesh position={[0, 1.17, 0]} castShadow><boxGeometry args={[1.08, .1, .15]} /><Material color="#966A43" /></mesh>
      <mesh position={[0, .85, 0]}><cylinderGeometry args={[.012, .012, .55, 4]} /><Material color="#EBD9A3" /></mesh>
    </group></group>
    <group name="island-station-ideas" position={[WORLD_STATIONS.ideas.x, .02, WORLD_STATIONS.ideas.z]}><group position={[0, 0, -WORLD_STATION_BACKSETS.ideas]} rotation={[0, -.3, 0]}>
      <mesh position={[0, .2, 0]} castShadow><cylinderGeometry args={[.3, .32, .4, 8]} /><Material color="#AA8055" /></mesh>
      <mesh position={[0, .41, 0]}><cylinderGeometry args={[.3, .3, .025, 8]} /><Material color="#E8BD81" /></mesh>
      <mesh position={[.4, .22, -.2]} rotation={[0, 0, Math.PI / 2]} castShadow><cylinderGeometry args={[.12, .12, .64, 7]} /><Material color="#98663F" /></mesh>
    </group></group>
    {rim.map((item, index) => <group key={index} name={`island-map-edge-${index}`} position={[item.x, -.01, item.z]} rotation={[0, index, 0]}><mesh scale={[1.4, .65, 1]} castShadow><icosahedronGeometry args={[item.size, 0]} /><Material color={index % 2 ? '#E9CA93' : '#A3B5A0'} /></mesh></group>)}
    {worldGroundDetails(seed).map(({ x, z, angle }, i) => <group key={i} name={`island-map-detail-${i}`} position={[x, .035, z]} rotation={[0, angle, 0]}>{[-1, 1].map(side => <mesh key={side} position={[side * .045, .1, 0]} rotation={[0, 0, side * -.3]}><coneGeometry args={[.04, .23, 3]} /><Material color={i % 3 ? '#5EAD46' : '#B4DA60'} /></mesh>)}{i % 4 === 0 && <mesh position={[0, .18, .03]}><icosahedronGeometry args={[.07]} /><Material color={i % 8 ? '#FFCE5C' : '#FFF6CE'} /></mesh>}</group>)}
    <group name="island-map-wayfinder" position={[WORLD_WAYFINDER.x, 0, WORLD_WAYFINDER.z]} rotation={[0, WORLD_WAYFINDER.rotation, 0]}><mesh position={[0, .46, 0]} castShadow><boxGeometry args={[.06, .93, .06]} /><Material color={INK} /></mesh><mesh position={[.09, .74, 0]} castShadow><boxGeometry args={[.64, .28, .08]} /><Material color="#FFCF59" /></mesh><mesh position={[.08, .75, .046]}><boxGeometry args={[.27, .035, .01]} /><Material color={INK} /></mesh></group>
  </group>
}

function Atmosphere({ active, reducedMotion }: { active: boolean; reducedMotion: boolean }) {
  const birds = useRef<Group>(null)
  const clouds = useRef<Group>(null)
  useFrame(({ clock }) => {
    if (!active || reducedMotion) return
    if (birds.current) birds.current.children.forEach((bird, i) => { const time = clock.elapsedTime * (.075 + i * .012) + i * 2; bird.position.set(Math.sin(time) * (7 + i), 4 + Math.sin(time * 1.5) * .3, Math.cos(time) * (7 + i)); bird.rotation.y = time + Math.PI / 2; bird.children.forEach((wing, side) => { wing.rotation.z = (side ? 1 : -1) * (.25 + Math.sin(clock.elapsedTime * 4.6 + i) * .2) }) })
    if (clouds.current) clouds.current.position.x = Math.sin(clock.elapsedTime * .017) * 1.2
  })
  return <group>
    <group ref={birds}>{[0, 1, 2].map(i => <group key={i} position={[7 + i, 4, i]}>{[-1, 1].map(side => <mesh key={side} position={[side * .12, 0, 0]} rotation={[0, 0, side * .3]}><boxGeometry args={[.26, .025, .1]} /><meshBasicMaterial color="#F9F7DF" /></mesh>)}</group>)}</group>
    <group ref={clouds}>{[[-7, 5, -6], [6, 6, -8]].map(([x, y, z], i) => <group key={i} position={[x, y, z]}>{[-1, 0, 1].map(j => <mesh key={j} position={[j * .65, Math.abs(j) * -.12, 0]} scale={[1.1, .5, .65]}><icosahedronGeometry args={[.8 - Math.abs(j) * .18, 1]} /><meshBasicMaterial color="#EEFAF5" transparent opacity={.8} depthWrite={false} /></mesh>)}</group>)}</group>
  </group>
}

function CameraAndContext({ onFailure, resetKey, followSelected, selectedId, selectedProjectId, projectTarget, positions, active, reducedMotion }: { onFailure: () => void; resetKey: number; followSelected: boolean; selectedId: string | null; selectedProjectId?: string | null; projectTarget?: { x: number; z: number }; positions: Map<string, Vector3>; active: boolean; reducedMotion: boolean }) {
  const { camera, size, gl, invalidate } = useThree()
  const orbit = useRef<OrbitControlsImpl>(null)
  const previousTarget = useRef(new Vector3())
  const projectFocus = useRef<Vector3 | null>(null)
  useEffect(() => {
    if (camera instanceof OrthographicCamera) { camera.zoom = Math.max(12, Math.min(size.width / 14.2, size.height / 10.8)); camera.updateProjectionMatrix(); invalidate() }
  }, [camera, size.width, size.height, invalidate])
  useEffect(() => {
    // A plain wheel scrolls the page past the island; pinch (sent as Ctrl+wheel) or Ctrl/⌘ + scroll zooms, as embedded maps do.
    const element = gl.domElement
    const gate = (event: WheelEvent) => { if (orbit.current) orbit.current.enableZoom = event.ctrlKey || event.metaKey }
    element.addEventListener('wheel', gate, { capture: true })
    return () => element.removeEventListener('wheel', gate, { capture: true })
  }, [gl])
  useEffect(() => {
    projectFocus.current = null
    camera.position.set(9, 11, 13)
    if (camera instanceof OrthographicCamera) { camera.zoom = Math.max(12, Math.min(size.width / 14.2, size.height / 10.8)); camera.updateProjectionMatrix() }
    orbit.current?.target.set(0, .25, 0); orbit.current?.update(); invalidate()
  }, [resetKey, camera, invalidate])
  useEffect(() => {
    projectFocus.current = selectedProjectId && projectTarget ? new Vector3(projectTarget.x, .45, projectTarget.z) : null
    invalidate()
  }, [selectedProjectId, projectTarget?.x, projectTarget?.z, invalidate])
  useEffect(() => {
    const failure = (event: Event) => { event.preventDefault(); onFailure() }
    gl.domElement.addEventListener('webglcontextlost', failure)
    return () => gl.domElement.removeEventListener('webglcontextlost', failure)
  }, [gl, onFailure])
  useFrame((_, delta) => {
    const target = followSelected && selectedId ? positions.get(selectedId) : projectFocus.current
    if (!active || !target || !orbit.current) return
    previousTarget.current.copy(orbit.current.target)
    orbit.current.target.lerp(target, reducedMotion ? 1 : Math.min(1, delta * 3))
    previousTarget.current.sub(orbit.current.target)
    camera.position.sub(previousTarget.current)
    orbit.current.update()
    if (projectFocus.current && orbit.current.target.distanceTo(projectFocus.current) < .02) projectFocus.current = null
  })
  return <OrbitControls ref={orbit} makeDefault target={[0, .25, 0]} onStart={() => { projectFocus.current = null }} enabled={active} enablePan enableZoom minZoom={12} maxZoom={115} minPolarAngle={.42} maxPolarAngle={1.25} enableDamping={!reducedMotion && active} dampingFactor={.09} />
}

export default function WorldScene({ characters, layoutSeed, selectedId, onSelect, active, reducedMotion, arrivalIds, onArrived, onFailure, simulation, selectedProjectId, onProjectSelect, cameraResetKey = 0, followSelected = false, presentation = 'island' }: SceneProps) {
  const factory = presentation === 'factory'
  const positions = useRef(new Map<string, Vector3>())
  const slots = useMemo(() => residentDisplaySlots(characters.slice(0, 40).map(character => character.id)), [characters])
  const agents = useMemo(() => new Map((simulation?.agents ?? []).map(agent => [agent.character_id, agent])), [simulation?.agents])
  const clock = useMemo<WorldClock>(() => {
    const paused = simulation?.paused ?? false
    const timestamp = Date.parse(paused ? simulation?.paused_at ?? simulation?.server_time ?? '' : simulation?.server_time ?? '')
    return { serverMs: Number.isFinite(timestamp) ? timestamp : Date.now(), receivedAt: performance.now(), paused }
  }, [simulation?.server_time, simulation?.paused, simulation?.paused_at])
  const recentBuildId = useMemo(() => {
    const useful = (simulation?.projects ?? []).filter(project => project.level > 0 && projectBenefit(project, simulation?.projects, simulation?.agents).status === 'active')
    useful.sort((a, b) => Number(b.kind === 'assembly') - Number(a.kind === 'assembly') || (b.completed_at ?? '').localeCompare(a.completed_at ?? '') || a.id.localeCompare(b.id))
    return useful[0]?.id
  }, [simulation?.projects, simulation?.agents])
  const selectedAgent = selectedId ? agents.get(selectedId) : undefined
  const selectedSlot = selectedId ? slots.get(selectedId) ?? { x: 0, z: 0 } : { x: 0, z: 0 }
  const routeFrom = selectedAgent?.task ? displayIslandPoint(selectedAgent.task.from, selectedSlot) : null
  const routeTo = selectedAgent?.task ? displayIslandPoint(selectedAgent.task.to, selectedSlot) : null
  // Server time drives task paths; frame callbacks only animate meshes and never write progress.
  return <Canvas orthographic camera={{ position: [9, 11, 13], zoom: 45, near: .1, far: 100 }} shadows="percentage" dpr={[1, 1.5]} frameloop={active && !reducedMotion ? 'always' : 'demand'} gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }} fallback={<span>Saved residents and projects. Use the crew and project controls for accessible details.</span>} aria-label={factory ? "Interactive 3D factory: drag to orbit, pinch or Ctrl + scroll to zoom, click a robot or workstation" : "Interactive 3D island: drag to orbit, pinch or Ctrl + scroll to zoom, click a resident or building"}>
    <color attach="background" args={[factory ? '#333D44' : '#82CDE8']} />
    <CameraAndContext onFailure={onFailure} resetKey={cameraResetKey} followSelected={followSelected} selectedId={selectedId} selectedProjectId={selectedProjectId} projectTarget={simulation?.projects.find(project => project.id === selectedProjectId)?.position} positions={positions.current} active={active} reducedMotion={reducedMotion} />
    <ambientLight intensity={factory ? .25 : .55} />
    <fog attach="fog" args={[factory ? '#333D44' : '#9DDDEF', 25, 60]} />
    <hemisphereLight args={[factory ? '#DBE7EF' : '#FFF9DC', factory ? '#42494D' : '#83AA67', factory ? .75 : 1.4]} />
    <directionalLight position={[-5, 10, 7]} intensity={factory ? 2.1 : 2.4} color={factory ? '#F5F0E7' : '#FFFFFF'} castShadow shadow-mapSize={[1024, 1024]} shadow-camera-left={-8} shadow-camera-right={8} shadow-camera-top={8} shadow-camera-bottom={-8} shadow-normalBias={.04} />
    {factory ? <><FactoryLighting /><FactoryEnvironment seed={layoutSeed} /></> : <><Water active={active && !reducedMotion} /><Island seed={layoutSeed} /><Atmosphere active={active} reducedMotion={reducedMotion} /></>}
    {simulation?.projects.map(project => <IslandStructure key={project.id} presentation={presentation} project={project} projects={simulation.projects} agents={simulation.agents} autoLabel={!selectedProjectId && !selectedId && project.id === recentBuildId} selected={project.id === selectedProjectId} onSelect={onProjectSelect} active={active && !clock.paused} reducedMotion={reducedMotion} />)}
    {routeFrom && routeTo && <Line points={[[routeFrom.x, .055, routeFrom.z], [routeTo.x, .055, routeTo.z]]} color="#FFF2AF" lineWidth={2} dashed dashSize={.14} gapSize={.09} />}
    {characters.slice(0, 40).map(character => {
      const agent = agents.get(character.id)
      const resource = agent?.task?.resource as keyof typeof WORLD_STATIONS | undefined
      const station = resource ? WORLD_STATIONS[resource] : undefined
      const project = simulation?.projects.find(item => item.id === agent?.task?.project_id)
      const workTarget = project?.position ?? (station && resource ? { x: station.x, z: station.z - WORLD_STATION_BACKSETS[resource] } : undefined)
      return <Resident key={character.id} presentation={presentation} character={character} agent={agent} workTarget={workTarget} clock={clock} positions={positions.current} slot={slots.get(character.id) ?? { x: 0, z: 0 }} selected={selectedId ===character.id} onSelect={onSelect} active={active} reducedMotion={reducedMotion} arriving={arrivalIds.includes(character.id)} onArrived={onArrived} />
    })}
  </Canvas>
}
