import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { Group, OrthographicCamera, SRGBColorSpace, Texture, TextureLoader } from 'three'
import type { ThreeEvent } from '@react-three/fiber'
import type { WorldCharacter } from './WorldView'

type SceneProps = { characters: WorldCharacter[]; layoutSeed: number; selectedId: string | null; onSelect: (id: string) => void; active: boolean; reducedMotion: boolean; arrivalIds: string[]; onArrived: (id: string) => void; onFailure: () => void }
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

function Resident({ character, selected, onSelect, active, reducedMotion, arriving, onArrived }: { character: WorldCharacter; selected: boolean; onSelect: (id: string) => void; active: boolean; reducedMotion: boolean; arriving: boolean; onArrived: (id: string) => void }) {
  const root = useRef<Group>(null)
  const body = useRef<Group>(null)
  const elapsed = useRef(0)
  const arrivalReported = useRef(false)
  const spec = character.visual_spec
  const seed = Number.isFinite(spec.appearance_seed) ? spec.appearance_seed : 0
  const phase = seedValue(seed) * Math.PI * 2
  const homeX = clamp(character.home_position.x, -4, 4)
  const homeZ = clamp(character.home_position.z, -4, 4)
  const radius = Math.hypot(homeX, homeZ)
  const safeHomeX = radius > 4 ? homeX * 4 / radius : homeX
  const safeHomeZ = radius > 4 ? homeZ * 4 / radius : homeZ
  const scale = clamp(spec.scale, .7, 1.4) * .75
  const width = clamp(spec.proportions.width, .7, 1.4)
  const height = clamp(spec.proportions.height, .7, 1.4)

  useFrame((_, delta) => {
    if (!root.current || !body.current || !active) return
    if (reducedMotion) {
      root.current.position.set(safeHomeX, 0, safeHomeZ)
      body.current.position.y = 0
      body.current.rotation.z = 0
      body.current.scale.set(1, 1, 1)
      if (arriving && !arrivalReported.current) { arrivalReported.current = true; onArrived(character.id) }
      return
    }
    elapsed.current += Math.min(delta, .05)
    const time = elapsed.current
    const wander = character.state.activity === 'wander'
    root.current.position.x = safeHomeX + (wander ? Math.sin(time * .2 + phase) * .36 : 0)
    root.current.position.z = safeHomeZ + (wander ? Math.cos(time * .17 + phase) * .36 : 0)
    // Follow the local path with short, soft turns; saved home positions stay unchanged.
    const heading = wander ? Math.atan2(Math.cos(time * .2 + phase) * .2, -Math.sin(time * .17 + phase) * .17) : .15
    const angleDelta = Math.atan2(Math.sin(heading - root.current.rotation.y), Math.cos(heading - root.current.rotation.y))
    root.current.rotation.y += angleDelta * Math.min(1, delta * 1.5)
    const arrival = arriving ? Math.min(1, time / 1.15) : 1
    if (arriving && arrival === 1 && !arrivalReported.current) { arrivalReported.current = true; onArrived(character.id) }
    const lift = (1 - arrival) * .75
    animateCharacterBody(body.current, spec.animation_style, wander ? 'wander' : 'rest', time, phase)
    body.current.position.y += lift
    body.current.scale.multiplyScalar(.92 + arrival * .08)
  })

  const choose = (event: ThreeEvent<MouseEvent>) => { event.stopPropagation(); onSelect(character.id) }
  return <group ref={root} position={[safeHomeX, 0, safeHomeZ]} onClick={choose}>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .012, 0]}><circleGeometry args={[selected ? .68 : .48, 18]} /><meshBasicMaterial color={selected ? '#FFD166' : '#1E1C29'} transparent opacity={selected ? .8 : .1} depthWrite={false} /></mesh>
    {selected && <mesh position={[0, 1.85 * scale * height, 0]} rotation={[0, 0, Math.PI]}><coneGeometry args={[.12, .2, 4]} /><Material color="#FF596E" /></mesh>}
    <group scale={[scale * width, scale * height, scale * width]}><group ref={body}><CharacterShape character={character} /></group></group>
  </group>
}

function Water({ active }: { active: boolean }) {
  const ripples = useRef<Group>(null)
  useFrame(({ clock }) => {
    if (!ripples.current || !active) return
    ripples.current.children.forEach((ring, index) => {
      const phase = (clock.elapsedTime * .07 + index / 3) % 1
      ring.scale.setScalar(1 + phase * .2)
      const material = (ring as import('three').Mesh).material as import('three').MeshBasicMaterial
      material.opacity = (1 - phase) * .2
    })
  })
  return <group position={[0, -.83, 0]}>
    <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow><circleGeometry args={[45, 64]} /><meshStandardMaterial color="#B4DCD4" roughness={.65} metalness={.08} /></mesh>
    <group ref={ripples}>{[0, 1, 2].map(index => <mesh key={index} rotation={[-Math.PI / 2, 0, 0]} position={[0, .018 + index * .002, 0]}><ringGeometry args={[5.5 + index * .4, 5.54 + index * .4, 64]} /><meshBasicMaterial color="#F8FFF5" transparent opacity={.16} depthWrite={false} /></mesh>)}</group>
  </group>
}

function Island({ seed }: { seed: number }) {
  const decorations = useMemo(() => Array.from({ length: 13 }, (_, index) => {
    const angle = index / 13 * Math.PI * 2 + seedValue(seed, index) * .15
    return { x: Math.cos(angle) * (4.55 + seedValue(seed, index + 20) * .25), z: Math.sin(angle) * (4.55 + seedValue(seed, index + 20) * .25), scale: .16 + seedValue(seed, index + 40) * .18, angle }
  }), [seed])
  return <group>
    <mesh position={[0, -.27, 0]} receiveShadow><cylinderGeometry args={[5.42, 5.18, .25, 48]} /><Material color="#F0DAB1" /></mesh>
    <mesh position={[0, -.48, 0]} receiveShadow castShadow><cylinderGeometry args={[5.18, 4.65, .8, 12]} /><Material color="#C9B69A" /></mesh>
    <mesh position={[0, -.095, 0]} receiveShadow><cylinderGeometry args={[5.25, 5.18, .19, 48]} /><Material color="#CFE7C4" /></mesh>
    <mesh position={[0, -.96, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[6.12, 36]} /><meshBasicMaterial color="#66E0D4" transparent opacity={.22} /></mesh>
    <mesh position={[0, .009, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[1.25, 1.7, 32]} /><Material color="#E9DCC2" /></mesh>
    <mesh position={[0, .01, 0]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[.7, 14]} /><Material color="#E9DCC2" /></mesh>
    {decorations.map((item, index) => <group key={index} position={[item.x, 0, item.z]} rotation={[0, item.angle, 0]}>{index % 3 === 0 ? <><mesh position={[0, .23, 0]} castShadow><cylinderGeometry args={[.035, .045, .46, 5]} /><Material color="#6C6B52" /></mesh><mesh position={[.08, .36, 0]} rotation={[0, 0, -.5]} scale={[.8, 1, .25]} castShadow><octahedronGeometry args={[.22]} /><Material color="#79AA89" /></mesh><mesh position={[-.07, .24, 0]} rotation={[0, 0, .5]} scale={[.8, 1, .25]} castShadow><octahedronGeometry args={[.17]} /><Material color="#66B3A0" /></mesh></> : <mesh position={[0, item.scale * .4, 0]} scale={[1.4, .6, 1]} castShadow><icosahedronGeometry args={[item.scale, 0]} /><Material color={index % 2 === 0 ? '#B7C4B0' : '#DFD8C3'} /></mesh>}</group>)}
    <group position={[4.3, -.08, 1.5]} rotation={[0, -.3, 0]}>
      {Array.from({ length: 6 }, (_, index) => <mesh key={index} position={[index * .2, 0, 0]} castShadow receiveShadow><boxGeometry args={[.18, .1, .8]} /><Material color={index % 2 ? '#B59B76' : '#C5AC87'} /></mesh>)}
      {[-.32, .32].map(z => <mesh key={z} position={[.82, -.25, z]}><cylinderGeometry args={[.055, .07, .6, 6]} /><Material color="#847050" /></mesh>)}
    </group>
    {Array.from({ length: 28 }, (_, index) => { const angle = index * 2.399; const radius = 2.1 + seedValue(seed, index + 60) * 2.7; return <group key={`grass-${index}`} position={[Math.cos(angle) * radius, .03, Math.sin(angle) * radius]} rotation={[0, angle, 0]}>{[-1, 1].map(side => <mesh key={side} position={[side * .035, .075, 0]} rotation={[0, 0, side * -.3]}><coneGeometry args={[.025, .17, 3]} /><Material color={index % 3 ? '#83B18C' : '#A8C58B'} /></mesh>)}</group> })}
    <group position={[-3.6, 0, -2.2]} rotation={[0, .25, 0]}><mesh position={[0, .55, 0]} castShadow><cylinderGeometry args={[.045, .06, 1.1, 6]} /><Material color={INK} /></mesh><mesh position={[.3, .94, 0]}><boxGeometry args={[.65, .33, .04]} /><Material color="#FF596E" /></mesh><mesh position={[0, 1.14, 0]}><sphereGeometry args={[.08, 8, 6]} /><Material color="#FFD166" /></mesh></group>
  </group>
}

function CameraAndContext({ onFailure }: { onFailure: () => void }) {
  const { camera, size, gl, invalidate } = useThree()
  useEffect(() => {
    if (camera instanceof OrthographicCamera) { camera.zoom = Math.max(12, Math.min(size.width / 13, size.height / 9)); camera.updateProjectionMatrix(); invalidate() }
  }, [camera, size.width, size.height, invalidate])
  useEffect(() => {
    const failure = (event: Event) => { event.preventDefault(); onFailure() }
    gl.domElement.addEventListener('webglcontextlost', failure)
    return () => gl.domElement.removeEventListener('webglcontextlost', failure)
  }, [gl, onFailure])
  return null
}

export default function WorldScene({ characters, layoutSeed, selectedId, onSelect, active, reducedMotion, arrivalIds, onArrived, onFailure }: SceneProps) {
  // R3F renders fallback as HTML canvas children even when WebGL works. It must have no effects.
  return <Canvas orthographic camera={{ position: [8, 9, 11], zoom: 45, near: .1, far: 60 }} shadows="percentage" dpr={[1, 1.5]} frameloop={active && !reducedMotion ? 'always' : 'demand'} gl={{ antialias: true, alpha: true, powerPreference: 'low-power' }} fallback={<span>Saved object characters. Use Collection for accessible resident details.</span>} aria-label="3D island with saved object characters">
    <CameraAndContext onFailure={onFailure} />
    <ambientLight intensity={.65} />
    <fog attach="fog" args={['#D9ECE6', 22, 47]} />
    <hemisphereLight args={['#FFF9EB', '#759E87', 1.15]} />
    <directionalLight position={[-3, 8, 5]} intensity={2.1} castShadow shadow-mapSize={[1024, 1024]} shadow-camera-left={-7} shadow-camera-right={7} shadow-camera-top={7} shadow-camera-bottom={-7} shadow-normalBias={.035} />
    <Water active={active && !reducedMotion} /><Island seed={layoutSeed} />
    {characters.map(character => <Resident key={character.id} character={character} selected={selectedId === character.id} onSelect={onSelect} active={active} reducedMotion={reducedMotion} arriving={arrivalIds.includes(character.id)} onArrived={onArrived} />)}
    <OrbitControls makeDefault target={[0, .1, 0]} enabled={active} enablePan={false} enableZoom minZoom={12} maxZoom={90} minPolarAngle={.45} maxPolarAngle={1.22} enableDamping={!reducedMotion && active} dampingFactor={.08} />
  </Canvas>
}
