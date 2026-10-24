import { useEffect, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { ThreeEvent } from '@react-three/fiber'
import { Group } from 'three'
import { assemblyPartPresentation } from '../lib/island'
import type { IslandProject } from '../lib/island'

const INK = '#172338'
const WOOD = '#BA7950'
function Paint({ color, glow = false }: { color: string; glow?: boolean }) {
  return <meshStandardMaterial color={color} roughness={.86} flatShading emissive={glow ? color : '#000000'} emissiveIntensity={glow ? .35 : 0} />
}

function Garden({ progress, time }: { progress: number; time: React.RefObject<Group | null> }) {
  return <group>
    {[-.5, .5].flatMap((x, i) => [-.4, .4].map((z, j) => <group key={`${x}:${z}`} position={[x, .03, z]}>
      <mesh receiveShadow><boxGeometry args={[.9, .12, .68]} /><Paint color={WOOD} /></mesh>
      <mesh position={[0, .075, 0]}><boxGeometry args={[.76, .05, .55]} /><Paint color="#4C372D" /></mesh>
      {progress > .16 && <group position={[0, .1, 0]} scale={[1, Math.max(.1, progress), 1]}>
        <mesh position={[0, .25, 0]} castShadow><cylinderGeometry args={[.035, .05, .5, 5]} /><Paint color="#467B36" /></mesh>
        {[-1, 1].map(side => <mesh key={side} position={[side * .14, .33, 0]} rotation={[0, 0, side * -.6]} scale={[.7, 1, .5]} castShadow><octahedronGeometry args={[.24, 0]} /><Paint color={(i + j) % 2 ? '#A8EA58' : '#70C744'} /></mesh>)}
        {progress > .75 && <mesh position={[0, .55, 0]} castShadow><icosahedronGeometry args={[.16, 1]} /><Paint color={(i + j) % 2 ? '#FFC857' : '#FF7363'} /></mesh>}
      </group>}
    </group>))}
    {progress > .35 && <group ref={time} position={[-1.03, 0, -.7]}><mesh position={[0, .38, 0]}><cylinderGeometry args={[.035, .035, .75, 5]} /><Paint color={INK} /></mesh><mesh position={[.16, .64, 0]}><boxGeometry args={[.35, .2, .04]} /><Paint color="#FECA52" /></mesh></group>}
  </group>
}

function Workshop({ progress }: { progress: number }) {
  const roof = progress > .64
  return <group>
    <mesh position={[0, .08, 0]} receiveShadow castShadow><boxGeometry args={[1.9, .16, 1.65]} /><Paint color="#D7B582" /></mesh>
    {progress > .15 && [-.76, .76].flatMap(x => [-.62, .62].map(z => <mesh key={`${x}:${z}`} position={[x, Math.min(1, progress * 2.5) * .64 + .1, z]} scale={[1, Math.min(1, progress * 2.5), 1]} castShadow><boxGeometry args={[.14, 1.28, .14]} /><Paint color={WOOD} /></mesh>))}
    {progress > .4 && <><mesh position={[0, .65, .13]} castShadow><boxGeometry args={[1.2, .13, .64]} /><Paint color="#9D6243" /></mesh><mesh position={[-.4, .38, .13]} castShadow><boxGeometry args={[.1, .5, .44]} /><Paint color={INK} /></mesh><mesh position={[.4, .38, .13]} castShadow><boxGeometry args={[.1, .5, .44]} /><Paint color={INK} /></mesh><mesh position={[.25, .8, .15]} rotation={[0, 0, .3]} castShadow><boxGeometry args={[.28, .2, .22]} /><Paint color="#FFD05C" /></mesh></>}
    {roof && <group position={[0, 1.52, 0]}>
      {[-1, 1].map(side => <mesh key={side} position={[side * .48, 0, 0]} rotation={[0, 0, side * -.34]} castShadow><boxGeometry args={[1.13, .12, 1.95]} /><Paint color={side < 0 ? '#FF816C' : '#DA5B50'} /></mesh>)}
      <mesh position={[0, .18, 0]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[.07, .07, 2, 6]} /><Paint color={INK} /></mesh>
    </group>}
    {progress >= 1 && <group position={[-1.06, .3, -.4]}><mesh castShadow><boxGeometry args={[.34, .56, .55]} /><Paint color="#6AAED6" /></mesh><mesh position={[0, .31, 0]}><boxGeometry args={[.37, .08, .58]} /><Paint color={INK} /></mesh></group>}
  </group>
}

function Beacon({ progress, light }: { progress: number; light: React.RefObject<Group | null> }) {
  const height = Math.max(.1, progress) * 1.65
  return <group>
    <mesh position={[0, .08, 0]} castShadow receiveShadow><cylinderGeometry args={[.75, .87, .16, 8]} /><Paint color="#B2BECC" /></mesh>
    {progress > .15 && <mesh position={[0, height / 2 + .14, 0]} castShadow><cylinderGeometry args={[.31, .51, height, 8]} /><Paint color="#FFEFCC" /></mesh>}
    {progress > .45 && <mesh position={[0, height * .55, 0]}><cylinderGeometry args={[.409, .43, .22, 8]} /><Paint color="#F86E6A" /></mesh>}
    {progress > .8 && <group position={[0, height + .29, 0]}>
      <mesh castShadow><cylinderGeometry args={[.5, .5, .12, 8]} /><Paint color={INK} /></mesh>
      <mesh position={[0, .28, 0]}><cylinderGeometry args={[.32, .32, .5, 8]} /><Paint color="#FFD66C" glow /></mesh>
      <mesh position={[0, .6, 0]} castShadow><coneGeometry args={[.56, .33, 8]} /><Paint color="#F27262" /></mesh>
      {progress >= 1 && <group ref={light} position={[0, .25, 0]}>
        <mesh position={[1.1, 0, 0]} rotation={[0, 0, -Math.PI / 2]}><coneGeometry args={[.45, 2.1, 12, 1, true]} /><meshBasicMaterial color="#FFF4AE" transparent opacity={.13} depthWrite={false} /></mesh>
        <mesh position={[-1.1, 0, 0]} rotation={[0, 0, Math.PI / 2]}><coneGeometry args={[.45, 2.1, 12, 1, true]} /><meshBasicMaterial color="#FFF4AE" transparent opacity={.13} depthWrite={false} /></mesh>
      </group>}
    </group>}
  </group>
}

function Boardwalk({ progress }: { progress: number }) {
  return <group rotation={[0, -.43, 0]}>
    {Array.from({ length: Math.max(1, Math.floor(progress * 10)) }, (_, i) => <mesh key={i} position={[(i - 4) * .2, .09, 0]} castShadow receiveShadow><boxGeometry args={[.18, .12, 1.1]} /><Paint color={i % 2 ? '#DCAB74' : '#C89360'} /></mesh>)}
    {progress > .3 && [-.8, .8].flatMap(x => [-.48, .48].map(z => <mesh key={`${x}:${z}`} position={[x, -.15, z]} castShadow><cylinderGeometry args={[.07, .09, .72, 6]} /><Paint color={WOOD} /></mesh>))}
    {progress >= 1 && [-.48, .48].map(z => <group key={z}><mesh position={[.82, .35, z]}><boxGeometry args={[.06, .65, .06]} /><Paint color={INK} /></mesh><mesh position={[.82, .7, z]}><sphereGeometry args={[.11, 8, 6]} /><Paint color="#FFCF63" glow /></mesh></group>)}
  </group>
}

const MATERIAL_COLOURS: Record<string, string> = {
  metal: '#91A6B0', ceramic: '#F5E9D0', glass: '#91D2DB', wood: '#BA7950',
  plastic: '#77B7AA', paper: '#EED49B', fabric: '#D98D76', unknown: '#B8B1A0',
}

/** Render the server-approved recipe, with its real part proportions and work state. */
function Assembly({ project, progress }: { project: IslandProject; progress: number }) {
  const assembly = project.assembly
  if (!assembly?.parts.length) return null
  const parts = assembly.parts.slice(0, 12)
  const presentations = parts.map((part, index) => assemblyPartPresentation(part, index, parts.length, progress))
  const supportHeight = assembly.family === 'support' ? Math.max(.25, ...presentations.slice(1).map(part => part.height)) : 0
  const width = Math.max(1, ...presentations.map(part => Math.abs(part.position.x) * 2 + part.length))
  const scale = Math.min(.8, 2 / width)
  return <group name={`assembly-${project.blueprint_id ?? project.id}`} scale={scale}>
    {parts.map((part, index) => {
      const shape = presentations[index]
      const primarySpan = assembly.family === 'support' && index === 0
      const y = shape.position.y + shape.height / 2 + (primarySpan ? supportHeight + .05 : 0)
      const color = shape.solid ? MATERIAL_COLOURS[part.material_assumption] ?? MATERIAL_COLOURS.unknown : '#6BA9B9'
      const material = <meshStandardMaterial color={color} roughness={.78} flatShading transparent={!shape.solid} opacity={shape.solid ? 1 : .34} wireframe={!shape.solid} depthWrite={shape.solid} />
      return <group key={`${part.resident_id}-${index}`} name={`assembly-part-${part.resident_id}`} position={[shape.position.x, y, shape.position.z]} rotation={[0, part.rotation === 90 ? Math.PI / 2 : 0, 0]}>
        {part.kind === 'vessel' ? <>
          <mesh castShadow={shape.solid} receiveShadow>
            <cylinderGeometry args={[shape.width / 2, shape.width * .45, shape.height, 12, 1, true]} />{material}
          </mesh>
          <mesh position={[0, -shape.height / 2 + .025, 0]} castShadow={shape.solid}>
            <cylinderGeometry args={[shape.width * .45, shape.width * .45, .05, 12]} />{material}
          </mesh>
          <mesh position={[0, shape.height / 2, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[shape.width * .49, .025, 5, 12]} />{material}
          </mesh>
        </> : part.kind === 'connector' ? <mesh castShadow={shape.solid} receiveShadow>
          <cylinderGeometry args={[shape.width / 2, shape.width / 2, shape.height, 8]} />{material}
        </mesh> : <mesh castShadow={shape.solid} receiveShadow>
          <boxGeometry args={[shape.length, shape.height, shape.depth]} />{material}
        </mesh>}
        {shape.solid && <mesh position={[0, shape.height / 2 + .02, 0]}>
          <boxGeometry args={[Math.min(.16, shape.width * .2), .025, Math.min(.16, shape.depth * .2)]} />
          <Paint color={assembly.family === 'contain' ? '#6BAECD' : assembly.family === 'hold' ? '#FFD166' : '#8AC9AA'} />
        </mesh>}
      </group>
    })}
    {assembly.family === 'support' && [-1, 1].map(side => <mesh key={side} position={[side * (assembly.context.span ?? .6) / 2, .12, 0]}>
      <boxGeometry args={[.2, .24, .65]} /><Paint color="#A5AC9D" />
    </mesh>)}
  </group>
}

export default function IslandStructure({ project, selected, onSelect, active, reducedMotion }: { project: IslandProject; selected: boolean; onSelect?: (id: string) => void; active: boolean; reducedMotion: boolean }) {
  const upgradeProgress = project.status === 'complete' ? 1 : Math.max(0, Math.min(1, project.progress / Math.max(1, project.required_progress)))
  // Construction progress resets for the next upgrade; an existing building never disappears.
  const progress = project.level > 0 ? 1 : upgradeProgress
  const light = useRef<Group>(null)
  const flag = useRef<Group>(null)
  const burst = useRef<Group>(null)
  const previousLevel = useRef(project.level)
  const celebration = useRef(0)
  useEffect(() => { if (project.level > previousLevel.current) celebration.current = 3; previousLevel.current = project.level }, [project.level])
  useFrame(({ clock }, delta) => {
    if (!active || reducedMotion) return
    if (light.current) light.current.rotation.y += delta * .65
    if (flag.current) flag.current.rotation.z = Math.sin(clock.elapsedTime * 1.7) * .055
    if (burst.current) {
      celebration.current = Math.max(0, celebration.current - delta)
      burst.current.visible = celebration.current > 0
      burst.current.children.forEach((piece, i) => { const phase = 1 - celebration.current / 3; piece.position.set(Math.cos(i * 2.4) * phase * 1.9, 2 + Math.sin(phase * Math.PI) * 2 - phase * 2, Math.sin(i * 2.4) * phase * 1.9); piece.rotation.set(phase * 8, i, phase * 5) })
    }
  })
  const choose = (event: ThreeEvent<MouseEvent>) => { if (event.delta > 4) return; event.stopPropagation(); onSelect?.(project.id) }
  return <group position={[project.position.x, .025, project.position.z]} onClick={choose}>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -.009, 0]} receiveShadow><circleGeometry args={[project.kind === 'beacon' ? 1.05 : 1.5, 8]} /><Paint color={selected ? '#FFE17F' : project.level > 0 ? '#AAD66A' : '#D4B585'} /></mesh>
    {project.level === 0 && [-1, 1].map(side => <group key={side} position={[side * 1.12, .18, .8]}><mesh castShadow><coneGeometry args={[.11, .35, 4]} /><Paint color="#FFC951" /></mesh><mesh position={[0, -.14, 0]}><boxGeometry args={[.28, .055, .28]} /><Paint color={INK} /></mesh></group>)}
    {project.kind === 'garden' ? <Garden progress={progress} time={flag} /> : project.kind === 'workshop' ? <Workshop progress={progress} /> : project.kind === 'beacon' ? <Beacon progress={progress} light={light} /> : project.kind === 'boardwalk' ? <Boardwalk progress={progress} /> : project.kind === 'assembly' ? <Assembly project={project} progress={progress} /> : null}
    {project.level >= 2 && project.kind === 'garden' && [-.8, .8].map(x => <group key={x} position={[x, .1, -.85]}><mesh position={[0, .3, 0]}><cylinderGeometry args={[.04, .06, .6, 5]} /><Paint color={WOOD} /></mesh><mesh position={[0, .65, 0]} castShadow><icosahedronGeometry args={[.3, 0]} /><Paint color="#58B85D" /></mesh><mesh position={[.13, .7, .2]}><sphereGeometry args={[.08, 6, 5]} /><Paint color="#FF8D62" /></mesh></group>)}
    {project.level >= 2 && project.kind === 'workshop' && <group position={[.62, 1.75, -.4]}><mesh castShadow><boxGeometry args={[.2, .7, .23]} /><Paint color="#86A2AD" /></mesh><mesh position={[0, .39, 0]}><boxGeometry args={[.3, .12, .31]} /><Paint color={INK} /></mesh></group>}
    {project.level >= 2 && project.kind === 'beacon' && <mesh position={[0, 1.55, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[.55, .04, 5, 16]} /><Paint color="#7FE2D1" glow /></mesh>}
    {project.level >= 2 && project.kind === 'boardwalk' && [-.48, .48].map(z => <mesh key={z} position={[0, .56, z]} rotation={[0, -.43, 0]} castShadow><boxGeometry args={[1.8, .07, .07]} /><Paint color={WOOD} /></mesh>)}
    {project.level >= 3 && <group position={[-.9, .1, -.7]}><mesh position={[0, .6, 0]}><cylinderGeometry args={[.025, .025, 1.2, 5]} /><Paint color={INK} /></mesh><mesh position={[.17, 1.05, 0]}><boxGeometry args={[.36, .25, .04]} /><Paint color="#FFCF59" /></mesh><mesh position={[.17, 1.05, .025]}><octahedronGeometry args={[.07]} /><Paint color={INK} /></mesh></group>}
    {(selected || (upgradeProgress > 0 && project.status !== 'complete')) && <group position={[0, .12, 1.05]}><mesh><boxGeometry args={[1.24, .06, .17]} /><Paint color={INK} /></mesh><mesh position={[-.56 * (1 - upgradeProgress), .035, 0]}><boxGeometry args={[Math.max(.015, 1.12 * upgradeProgress), .04, .1]} /><Paint color="#7FE2D1" /></mesh></group>}
    {selected && <mesh position={[0, project.kind === 'beacon' ? 3.1 : 2.2, 0]} rotation={[0, 0, Math.PI]}><coneGeometry args={[.14, .22, 4]} /><Paint color="#FFD15D" /></mesh>}
    <group ref={burst} visible={false}>{Array.from({ length: 12 }, (_, i) => <mesh key={i}><boxGeometry args={[.075, .15, .025]} /><Paint color={['#FFD15D', '#FF7363', '#7FE2D1'][i % 3]} /></mesh>)}</group>
  </group>
}
