import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Line, OrbitControls } from '@react-three/drei'
import { Group, Mesh, OrthographicCamera, Shape, SRGBColorSpace, Texture, TextureLoader, Vector3 } from 'three'
import type { MeshBasicMaterial } from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { computeTaskPose, safeIslandPoint } from '../lib/island'
import type { IslandAgent, IslandSimulation, IslandTaskKind } from '../lib/island'
import IslandStructure from './IslandStructures'
import type { ThreeEvent } from '@react-three/fiber'
import type { WorldCharacter } from './WorldView'

type SceneProps = { characters: WorldCharacter[]; layoutSeed: number; selectedId: string | null; onSelect: (id: string) => void; active: boolean; reducedMotion: boolean; arrivalIds: string[]; onArrived: (id: string) => void; onFailure: () => void; simulation?: IslandSimulation; selectedProjectId?: string | null; onProjectSelect?: (id: string) => void; cameraResetKey?: number; followSelected?: boolean }
type WorldClock = { serverMs: number; receivedAt: number; paused: boolean }
const worldTime = (clock: WorldClock) => clock.serverMs + (clock.paused ? 0 : performance.now() - clock.receivedAt)
const INK = '#1E1C29'
const PAPER = '#FFF9EB'
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, Number.isFinite(value) ? value : 1))
const seedValue = (seed: number, offset = 0) => Math.abs(Math.sin(seed * .01713 + offset * 13.123) * 43758.5453) % 1

function Material({ color }: { color: string }) { return <meshStandardMaterial color={color} roughness={.82} flatShading /> }

function Face({ y = .93, z = .44, width = .14 }: { y?: number; z?: number; width?: number }) {
  return <group>
    {[-1, 1].map(side => <group key={side} position={[side * width, y, z]}><mesh><sphereGeometry args={[.073, 8, 6]} /><meshBasicMaterial color={PAPER} /></mesh><mesh position={[.01, 0, .055]}><sphereGeometry args={[.033, 8, 6]} /><meshBasicMaterial color={INK} /></mesh></group>)}
    <mesh position={[0, y - .16, z + .01]} rotation={[0, 0, Math.PI]}><torusGeometry args={[.075, .018, 4, 10, Math.PI]} /><meshBasicMaterial color={INK} /></mesh>
  </group>
}

function Feet() {
  return <group>{[-1, 1].map(side => <mesh key={side} position={[side * .22, .105, .11]} scale={[1, .6, 1.5]} castShadow><sphereGeometry args={[.13, 8, 5]} /><Material color={INK} /></mesh>)}</group>
}

function Arms({ color, width = .52 }: { color: string; width?: number }) {
  return <group>{[-1, 1].map(side => <mesh key={side} position={[side * width, .66, 0]} rotation={[0, 0, side * .45]} castShadow><capsuleGeometry args={[.055, .31, 3, 6]} /><Material color={color} /></mesh>)}</group>
}

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

export type CharacterVisual = Pick<WorldCharacter, 'visual_spec' | 'image_ref'> & Partial<Pick<WorldCharacter, 'display_name' | 'object_type'>>

export function CharacterShape({ character, onAssetState }: { character: CharacterVisual; onAssetState?: (state: 'ready' | 'failed') => void }) {
  const spec = character.visual_spec
  const palette = spec.palette.filter(color => /^#[0-9A-Fa-f]{6}$/.test(color))
  const color = palette[0] ?? '#66E0D4'
  const accent = palette[1] ?? '#FFD166'
  const feet = spec.accessories.includes('feet')
  const eyes = spec.accessories.includes('eyes')
  const arms = spec.accessories.includes('arms')
  const template = spec.template_id
  return <group>
    {feet && <Feet />}
    {template === 'mug' ? <group>
      <mesh position={[0, .67, 0]} castShadow><cylinderGeometry args={[.48, .43, .96, 12]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.154, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.37, 12]} /><Material color="#6D5142" /></mesh>
      <mesh position={[0, 1.15, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[.427, .055, 5, 12]} /><Material color={accent} /></mesh>
      <mesh position={[.52, .7, 0]} rotation={[0, Math.PI / 2, 0]} castShadow><torusGeometry args={[.285, .085, 6, 12]} /><Material color={color} /></mesh>
      {eyes && <Face y={.82} z={.44} />}{arms && <Arms color={accent} width={.62} />}
    </group> : template === 'bottle' ? <group>
      <mesh position={[0, .76, 0]} castShadow><cylinderGeometry args={[.32, .36, 1.13, 10]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.38, 0]} castShadow><cylinderGeometry args={[.16, .32, .22, 10]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.58, 0]} castShadow><cylinderGeometry args={[.16, .16, .24, 10]} /><Material color={color} /></mesh>
      <mesh position={[0, 1.74, 0]} castShadow><cylinderGeometry args={[.195, .195, .12, 10]} /><Material color={accent} /></mesh>
      <mesh position={[0, .65, 0]}><cylinderGeometry args={[.327, .348, .35, 10]} /><Material color={accent} /></mesh>
      {eyes && <Face y={1.03} z={.31} width={.12} />}{arms && <Arms color={accent} width={.43} />}
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
      {eyes && <Face y={.93} z={.31} />}{arms && <Arms color={accent} width={.55} />}
    </group> : template === 'ball' ? <group>
      <mesh position={[0, .76, 0]} castShadow><icosahedronGeometry args={[.62, 1]} /><Material color={color} /></mesh>
      <mesh position={[0, .76, 0]} rotation={[.3, 0, .3]}><torusGeometry args={[.605, .035, 4, 14]} /><Material color={accent} /></mesh>
      {eyes && <Face y={.93} z={.56} />}{arms && <Arms color={accent} width={.66} />}
    </group> : <group>
      <mesh position={[0, .83, 0]} castShadow><boxGeometry args={[.93, 1.3, .6]} /><Material color={color} /></mesh>
      <PhotoBadge image={character.image_ref} onAssetState={onAssetState} />
      {eyes && <Face y={1.29} z={.31} />}{arms && <Arms color={accent} width={.58} />}
    </group>}
  </group>
}

export type CharacterActivity = 'idle' | 'rest' | 'wander'
/** Shared, bounded pose code. This only changes the local scene graph, never game records. */
export function animateCharacterBody(body: Group, style: WorldCharacter['visual_spec']['animation_style'], activity: CharacterActivity, time: number, phase = 0, reducedMotion = false) {
  const moving = activity === 'wander' && !reducedMotion
  const breathing = reducedMotion ? 0 : Math.sin(time * 1.4 + phase) * .009
  const step = Math.sin(time * 5.2 + phase)
  body.position.y = moving ? (style === 'bouncy' ? Math.abs(step) * .055 : Math.abs(step) * .025) : breathing
  body.rotation.z = moving ? step * (style === 'wobbly' ? .065 : .022) : 0
  body.rotation.x = activity === 'rest' ? -.07 : 0
  body.scale.set(1, activity === 'rest' ? .96 + breathing : 1, 1)
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

function Resident({ character, agent, clock, positions, selected, onSelect, active, reducedMotion, arriving, onArrived }: { character: WorldCharacter; agent?: IslandAgent; clock: WorldClock; positions: Map<string, Vector3>; selected: boolean; onSelect: (id: string) => void; active: boolean; reducedMotion: boolean; arriving: boolean; onArrived: (id: string) => void }) {
  const root = useRef<Group>(null)
  const body = useRef<Group>(null)
  const work = useRef<Group>(null)
  const elapsed = useRef(0)
  const arrivalReported = useRef(false)
  const spec = character.visual_spec
  const seed = Number.isFinite(spec.appearance_seed) ? spec.appearance_seed : 0
  const phase = seedValue(seed) * Math.PI * 2
  const home = safeIslandPoint({ x: character.home_position.x, z: character.home_position.z })
  const initial = agent ? computeTaskPose(agent.task, agent.position, worldTime(clock)) : { ...home, heading: .2 }
  const scale = clamp(spec.scale, .7, 1.4) * .7
  const width = clamp(spec.proportions.width, .7, 1.4)
  const height = clamp(spec.proportions.height, .7, 1.4)
  useEffect(() => { positions.set(character.id, new Vector3(initial.x, .5, initial.z)); return () => { positions.delete(character.id) } }, [character.id, positions])
  useFrame((_, delta) => {
    if (!root.current || !body.current || !active) return
    if (!clock.paused && !reducedMotion) elapsed.current += Math.min(delta, .05)
    const time = elapsed.current
    let moving = character.state.activity === 'wander' && !agent && !clock.paused
    let working = false
    let heading = .2
    if (agent) {
      const pose = computeTaskPose(agent.task, agent.position, worldTime(clock))
      root.current.position.set(pose.x, .03, pose.z)
      moving = pose.travelling && !clock.paused
      working = pose.working && !clock.paused
      heading = pose.heading
    } else {
      root.current.position.set(home.x + (moving && !reducedMotion ? Math.sin(time * .22 + phase) * .3 : 0), .03, home.z + (moving && !reducedMotion ? Math.cos(time * .19 + phase) * .3 : 0))
      heading = moving ? Math.atan2(Math.cos(time * .22 + phase) * .22, -Math.sin(time * .19 + phase) * .19) : .2
    }
    const angleDelta = Math.atan2(Math.sin(heading - root.current.rotation.y), Math.cos(heading - root.current.rotation.y))
    root.current.rotation.y += reducedMotion ? angleDelta : angleDelta * Math.min(1, delta * 5)
    animateCharacterBody(body.current, spec.animation_style, moving ? 'wander' : agent?.task?.kind === 'rest' ? 'rest' : 'idle', time, phase, reducedMotion || clock.paused)
    if (working && !reducedMotion) {
      body.current.rotation.z = Math.sin(time * (agent?.task?.kind === 'build' ? 5 : 2.4) + phase) * .055
      body.current.rotation.x = agent?.task?.kind === 'plan' || agent?.task?.kind === 'measure' ? .13 : Math.sin(time * 2) * .04
      body.current.position.y += Math.max(0, Math.sin(time * 3 + phase)) * .018
    }
    if (work.current) work.current.visible = !!agent?.task && (working || moving) && agent.task.kind !== 'rest'
    const arrival = arriving ? reducedMotion ? 1 : Math.min(1, time / 1.15) : 1
    if (arriving && arrival === 1 && !arrivalReported.current) { arrivalReported.current = true; onArrived(character.id) }
    body.current.position.y += (1 - arrival) * .75
    body.current.scale.multiplyScalar(.92 + arrival * .08)
    positions.get(character.id)?.copy(root.current.position).setY(.5)
  })
  const choose = (event: ThreeEvent<MouseEvent>) => { if (event.delta > 4) return; event.stopPropagation(); onSelect(character.id) }
  return <group ref={root} position={[initial.x, .03, initial.z]} rotation={[0, initial.heading, 0]} onClick={choose}>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .012, 0]}><circleGeometry args={[selected ? .64 : .43, 20]} /><meshBasicMaterial color={selected ? '#FFD166' : '#182B3C'} transparent opacity={selected ? .8 : .13} depthWrite={false} /></mesh>
    {selected && <mesh position={[0, 2 * scale * height, 0]} rotation={[0, 0, Math.PI]}><coneGeometry args={[.14, .22, 4]} /><Material color="#FF596E" /></mesh>}
    <group scale={[scale * width, scale * height, scale * width]}><group ref={body}><CharacterShape character={character} /><group ref={work}><WorkProp kind={agent?.task?.kind} active={active && !clock.paused} reducedMotion={reducedMotion} /></group></group></group>
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

function Island({ seed }: { seed: number }) {
  const shape = useMemo(() => {
    const result = new Shape()
    const points = Array.from({ length: 40 }, (_, i) => { const angle = i / 40 * Math.PI * 2; const radius = 5.45 + Math.sin(angle * 3 + .4) * .3 + Math.cos(angle * 5) * .19; return [Math.cos(angle) * radius, Math.sin(angle) * radius] })
    points.forEach(([x, z], i) => i ? result.lineTo(x, z) : result.moveTo(x, z)); result.closePath(); return result
  }, [])
  const rim = useMemo(() => Array.from({ length: 12 }, (_, i) => { const angle = i / 12 * Math.PI * 2 + .2; return { x: Math.cos(angle) * (5.15 + seedValue(seed, i) * .15), z: Math.sin(angle) * (5.15 + seedValue(seed, i) * .15), size: .13 + seedValue(seed, i + 8) * .2 } }), [seed])
  return <group>
    <mesh position={[0, -.69, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow castShadow><extrudeGeometry args={[shape, { depth: .48, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .22, bevelThickness: .1 }]} /><Material color="#C79961" /></mesh>
    <mesh position={[0, -.14, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[1.04, 1.04, 1]} receiveShadow><shapeGeometry args={[shape]} /><Material color="#F5D394" /></mesh>
    <mesh position={[0, -.08, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[.95, .95, 1]} receiveShadow><extrudeGeometry args={[shape, { depth: .08, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .04, bevelThickness: .02 }]} /><Material color="#8CCB56" /></mesh>
    <mesh position={[0, .012, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.82, 8]} /><Material color="#E7C690" /></mesh>
    {[[0, 0, -3.5], [-2.1, 0, -1.7], [2.1, 0, -1.5], [0, 0, 2.5], [-3.7, 0, .7], [3.8, 0, .1]].map(([x, , z], i) => <Line key={i} points={[[0, .02, 0], [x * .5 + (i % 2 ? -.2 : .2), .02, z * .5], [x, .02, z]]} color="#E7C690" lineWidth={17} />)}
    <Tree x={-3.7} z={.4} size={1.05} /><Tree x={-4.35} z={1.15} size={.8} color="#4A9854" /><Tree x={-3.7} z={1.65} size={.64} />
    <Tree x={-1.4} z={-4.2} size={.8} /><Tree x={-.7} z={-4.65} size={.64} color="#478F57" />
    <group position={[3.85, 0, .1]}>{[0, 1, 2, 3].map(i => <mesh key={i} position={[Math.cos(i * 2.3) * .32, .17 + i % 2 * .1, Math.sin(i * 2.3) * .33]} scale={[1, .75, .8]} rotation={[0, i, .1]} castShadow><dodecahedronGeometry args={[.3 + i % 2 * .1, 0]} /><Material color={i % 2 ? '#7F9CA9' : '#B7CFCD'} /></mesh>)}</group>
    <group position={[-.25, .02, -3.5]}>
      <mesh position={[0, .18, 0]} castShadow><cylinderGeometry args={[.52, .56, .34, 10]} /><Material color="#9FBBB8" /></mesh>
      <mesh position={[0, .36, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.39, 12]} /><meshStandardMaterial color="#46BADD" roughness={.2} /></mesh>
      {[-.46, .46].map(x => <mesh key={x} position={[x, .66, 0]} castShadow><boxGeometry args={[.08, 1, .08]} /><Material color="#966A43" /></mesh>)}
      <mesh position={[0, 1.17, 0]} castShadow><boxGeometry args={[1.08, .1, .15]} /><Material color="#966A43" /></mesh>
      <mesh position={[0, .85, 0]}><cylinderGeometry args={[.012, .012, .55, 4]} /><Material color="#EBD9A3" /></mesh>
    </group>
    <group position={[.15, .02, .05]} rotation={[0, -.3, 0]}>
      <mesh position={[0, .2, 0]} castShadow><cylinderGeometry args={[.3, .32, .4, 8]} /><Material color="#AA8055" /></mesh>
      <mesh position={[0, .41, 0]}><cylinderGeometry args={[.3, .3, .025, 8]} /><Material color="#E8BD81" /></mesh>
      <mesh position={[.4, .22, -.2]} rotation={[0, 0, Math.PI / 2]} castShadow><cylinderGeometry args={[.12, .12, .64, 7]} /><Material color="#98663F" /></mesh>
    </group>
    {rim.map((item, index) => <mesh key={index} position={[item.x, -.01, item.z]} scale={[1.4, .65, 1]} rotation={[0, index, 0]} castShadow><icosahedronGeometry args={[item.size, 0]} /><Material color={index % 2 ? '#E9CA93' : '#A3B5A0'} /></mesh>)}
    {Array.from({ length: 18 }, (_, i) => { const angle = i * 2.399; const radius = 3.7 + seedValue(seed, i + 60) * 1.1; return <group key={`grass-${i}`} position={[Math.cos(angle) * radius, .035, Math.sin(angle) * radius]} rotation={[0, angle, 0]}>{[-1, 1].map(side => <mesh key={side} position={[side * .045, .1, 0]} rotation={[0, 0, side * -.3]}><coneGeometry args={[.04, .23, 3]} /><Material color={i % 3 ? '#5EAD46' : '#B4DA60'} /></mesh>)}{i % 4 === 0 && <mesh position={[0, .18, .03]}><icosahedronGeometry args={[.07]} /><Material color={i % 8 ? '#FFCE5C' : '#FFF6CE'} /></mesh>}</group> })}
    <group position={[-2.7, 0, 3.3]} rotation={[0, -.5, 0]}><mesh position={[0, .46, 0]} castShadow><boxGeometry args={[.06, .93, .06]} /><Material color={INK} /></mesh><mesh position={[.09, .74, 0]} castShadow><boxGeometry args={[.64, .28, .08]} /><Material color="#FFCF59" /></mesh><mesh position={[.08, .75, .046]}><boxGeometry args={[.27, .035, .01]} /><Material color={INK} /></mesh></group>
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

function CameraAndContext({ onFailure, resetKey, followSelected, selectedId, positions, active, reducedMotion }: { onFailure: () => void; resetKey: number; followSelected: boolean; selectedId: string | null; positions: Map<string, Vector3>; active: boolean; reducedMotion: boolean }) {
  const { camera, size, gl, invalidate } = useThree()
  const orbit = useRef<OrbitControlsImpl>(null)
  const previousTarget = useRef(new Vector3())
  useEffect(() => {
    if (camera instanceof OrthographicCamera) { camera.zoom = Math.max(12, Math.min(size.width / 14.2, size.height / 10.8)); camera.updateProjectionMatrix(); invalidate() }
  }, [camera, size.width, size.height, invalidate])
  useEffect(() => {
    camera.position.set(9, 11, 13)
    if (camera instanceof OrthographicCamera) { camera.zoom = Math.max(12, Math.min(size.width / 14.2, size.height / 10.8)); camera.updateProjectionMatrix() }
    orbit.current?.target.set(0, .25, 0); orbit.current?.update(); invalidate()
  }, [resetKey, camera, invalidate])
  useEffect(() => {
    const failure = (event: Event) => { event.preventDefault(); onFailure() }
    gl.domElement.addEventListener('webglcontextlost', failure)
    return () => gl.domElement.removeEventListener('webglcontextlost', failure)
  }, [gl, onFailure])
  useFrame((_, delta) => {
    const target = selectedId ? positions.get(selectedId) : null
    if (!active || !followSelected || !target || !orbit.current) return
    previousTarget.current.copy(orbit.current.target)
    orbit.current.target.lerp(target, reducedMotion ? 1 : Math.min(1, delta * 3))
    previousTarget.current.sub(orbit.current.target)
    camera.position.sub(previousTarget.current)
    orbit.current.update()
  })
  return <OrbitControls ref={orbit} makeDefault target={[0, .25, 0]} enabled={active} enablePan enableZoom minZoom={12} maxZoom={115} minPolarAngle={.42} maxPolarAngle={1.25} enableDamping={!reducedMotion && active} dampingFactor={.09} />
}

export default function WorldScene({ characters, layoutSeed, selectedId, onSelect, active, reducedMotion, arrivalIds, onArrived, onFailure, simulation, selectedProjectId, onProjectSelect, cameraResetKey = 0, followSelected = false }: SceneProps) {
  const positions = useRef(new Map<string, Vector3>())
  const agents = useMemo(() => new Map((simulation?.agents ?? []).map(agent => [agent.character_id, agent])), [simulation?.agents])
  const clock = useMemo<WorldClock>(() => {
    const paused = simulation?.paused ?? false
    const timestamp = Date.parse(paused ? simulation?.paused_at ?? simulation?.server_time ?? '' : simulation?.server_time ?? '')
    return { serverMs: Number.isFinite(timestamp) ? timestamp : Date.now(), receivedAt: performance.now(), paused }
  }, [simulation?.server_time, simulation?.paused, simulation?.paused_at])
  const selectedAgent = selectedId ? agents.get(selectedId) : undefined
  // Server time drives task paths; frame callbacks only animate meshes and never write progress.
  return <Canvas orthographic camera={{ position: [9, 11, 13], zoom: 45, near: .1, far: 100 }} shadows="percentage" dpr={[1, 1.5]} frameloop={active && !reducedMotion ? 'always' : 'demand'} gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }} fallback={<span>Saved island residents and projects. Use the collection and project controls for accessible details.</span>} aria-label="Interactive 3D island: drag to orbit, scroll to zoom, click a resident or building">
    <color attach="background" args={['#82CDE8']} />
    <CameraAndContext onFailure={onFailure} resetKey={cameraResetKey} followSelected={followSelected} selectedId={selectedId} positions={positions.current} active={active} reducedMotion={reducedMotion} />
    <ambientLight intensity={.55} />
    <fog attach="fog" args={['#9DDDEF', 25, 60]} />
    <hemisphereLight args={['#FFF9DC', '#83AA67', 1.4]} />
    <directionalLight position={[-5, 10, 7]} intensity={2.4} castShadow shadow-mapSize={[1024, 1024]} shadow-camera-left={-8} shadow-camera-right={8} shadow-camera-top={8} shadow-camera-bottom={-8} shadow-normalBias={.04} />
    <Water active={active && !reducedMotion} /><Island seed={layoutSeed} /><Atmosphere active={active} reducedMotion={reducedMotion} />
    {simulation?.projects.map(project => <IslandStructure key={project.id} project={project} selected={project.id === selectedProjectId} onSelect={onProjectSelect} active={active && !clock.paused} reducedMotion={reducedMotion} />)}
    {selectedAgent?.task && <Line points={[[selectedAgent.task.from.x, .055, selectedAgent.task.from.z], [selectedAgent.task.to.x, .055, selectedAgent.task.to.z]]} color="#FFF2AF" lineWidth={2} dashed dashSize={.14} gapSize={.09} />}
    {characters.slice(0, 40).map(character => <Resident key={character.id} character={character} agent={agents.get(character.id)} clock={clock} positions={positions.current} selected={selectedId === character.id} onSelect={onSelect} active={active} reducedMotion={reducedMotion} arriving={arrivalIds.includes(character.id)} onArrived={onArrived} />)}
  </Canvas>
}
