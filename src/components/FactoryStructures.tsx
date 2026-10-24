import type { IslandProject } from '../lib/island'
import { FACTORY, FactoryBox as Box, FactoryPaint as Paint, FloorMark } from './FactoryPrimitives'

const FRAME = '#667078'
const DARK_STEEL = '#39434A'
const GROW_GREEN = '#425D3D'

/** Short tube sections keep fixtures readable without turning them into oversized toy blocks. */
function Tube({ position, length, radius = .018, rotation = [0, 0, 0], color = FRAME }: { position: [number, number, number]; length: number; radius?: number; rotation?: [number, number, number]; color?: string }) {
  return <mesh position={position} rotation={rotation} castShadow receiveShadow>
    <cylinderGeometry args={[radius, radius, length, 10]} />
    <Paint color={color} material="steel" />
  </mesh>
}

function GrowShelves({ progress }: { progress: number }) {
  return <group name="factory-grow-shelves">
    {[-.76, .76].flatMap(x => [-.4, .4].map(z => <Box key={`foot-${x}-${z}`} position={[x, .035, z]} size={[.13, .07, .13]} color={FACTORY.ink} material="rubber" />))}
    {progress > .15 && <>
      {[-.76, .76].flatMap(x => [-.4, .4].map(z => <Box key={`${x}-${z}`} position={[x, .8, z]} size={[.045, 1.5, .045]} color={FRAME} material="steel" />))}
      {[-.4, .4].map(z => <Box key={z} position={[0, 1.53, z]} size={[1.56, .045, .04]} color={FRAME} material="steel" />)}
      <Box position={[0, .8, -.415]} size={[.025, 1.6, .025]} rotation={[0, 0, .8]} color={FRAME} material="steel" />
    </>}
    {progress > .32 && [.35, .94].map(y => <group key={y} position={[0, y, 0]}>
      <Box size={[1.53, .055, .84]} color={FACTORY.metal} material="steel" />
      <Box position={[0, .07, 0]} size={[1.42, .09, .73]} color={DARK_STEEL} material="paint" />
      <Box position={[0, .12, 0]} size={[1.32, .025, .63]} color="#28322D" material="rubber" />
      {progress > .6 && <>
        <Box position={[0, .46, 0]} size={[1.32, .04, .12]} color={FACTORY.metal} material="steel" />
        <Box position={[0, .435, 0]} size={[1.2, .008, .075]} color="#B6C9BA" shadow={false} />
        {[-.48, 0, .48].map(x => <group key={x} position={[x, .16, 0]}>
          <mesh castShadow><cylinderGeometry args={[.095, .075, .1, 10]} /><Paint color="#303735" material="rubber" /></mesh>
          {progress > .82 && [-1, 1].map(side => <mesh key={side} position={[side * .05, .09, 0]} rotation={[0, side * .3, side * -.55]} scale={[.048, .15, .018]} castShadow><sphereGeometry args={[1, 8, 6]} /><Paint color={GROW_GREEN} /></mesh>)}
        </group>)}
      </>}
    </group>)}
    {progress > .6 && <>
      <Box position={[.55, .145, -.02]} size={[.32, .2, .55]} color="#7C8580" material="paint" />
      <Tube position={[.7, .8, -.36]} length={1.22} radius={.014} color="#263638" />
    </>}
  </group>
}

function FabricationBench({ progress }: { progress: number }) {
  return <group name="factory-fabrication-bench">
    {[-.72, .72].flatMap(x => [-.38, .38].map(z => <Box key={`foot-${x}-${z}`} position={[x, .035, z]} size={[.14, .07, .14]} color={FACTORY.ink} material="rubber" />))}
    {progress > .15 && <>
      {[-.72, .72].flatMap(x => [-.38, .38].map(z => <Box key={`${x}-${z}`} position={[x, .43, z]} size={[.055, .8, .055]} color={DARK_STEEL} material="steel" />))}
      <Box position={[0, .23, -.38]} size={[1.45, .055, .055]} color={DARK_STEEL} material="steel" />
    </>}
    {progress > .35 && <>
      <Box position={[0, .85, 0]} size={[1.76, .08, 1.02]} color={FRAME} material="steel" />
      <Box position={[0, .898, 0]} size={[1.71, .016, .97]} color="#A3AAAC" material="steel" />
      {[-.52, -.26, 0, .26, .52].map(x => <Box key={x} position={[x, .909, 0]} size={[.015, .003, .82]} color={DARK_STEEL} material="rubber" shadow={false} />)}
      <Box position={[-.46, .57, 0]} size={[.44, .45, .7]} color="#5E6C6C" material="paint" />
      {[.46, .65].map(y => <group key={y}>
        <Box position={[-.46, y, .36]} size={[.4, .16, .025]} color="#718080" material="paint" />
        <Tube position={[-.46, y + .025, .388]} length={.22} radius={.012} rotation={[0, 0, Math.PI / 2]} />
      </group>)}
      <Box position={[.48, .29, 0]} size={[.49, .035, .68]} color={FRAME} material="steel" />
    </>}
    {progress > .6 && <group position={[-.39, .96, .17]}>
      <Box size={[.36, .09, .28]} color={DARK_STEEL} material="steel" />
      <Box position={[-.11, .1, 0]} size={[.075, .16, .28]} color="#5B6B71" material="paint" />
      <Box position={[.09, .1, 0]} size={[.075, .16, .28]} color="#5B6B71" material="paint" />
      {[-.065, .045].map(x => <Box key={x} position={[x, .145, 0]} size={[.025, .065, .26]} color={FACTORY.metal} material="steel" />)}
      <Tube position={[.25, .055, 0]} length={.22} radius={.016} rotation={[0, 0, Math.PI / 2]} />
      <Tube position={[.36, .055, 0]} length={.19} radius={.012} />
    </group>}
    {progress > .82 && <group position={[.48, .94, -.16]}>
      <Box size={[.37, .055, .4]} color={DARK_STEEL} material="steel" />
      <Tube position={[0, .3, -.12]} length={.6} radius={.03} />
      <Box position={[0, .57, -.02]} size={[.22, .16, .34]} color="#6A7A7B" material="paint" />
      <Box position={[0, .24, .03]} size={[.3, .035, .26]} color={FRAME} material="steel" />
      <Tube position={[0, .39, .1]} length={.19} radius={.013} />
      <Tube position={[.18, .52, -.02]} length={.25} radius={.013} rotation={[0, 0, .8]} />
    </group>}
  </group>
}

function CommsTerminal({ progress }: { progress: number }) {
  return <group name="factory-comms-terminal">
    <Box position={[0, .055, 0]} size={[.88, .11, .76]} color={DARK_STEEL} material="steel" />
    {progress > .15 && <>
      <Box position={[0, .6, 0]} size={[.68, 1.04, .55]} color="#778385" material="paint" />
      <Box position={[0, .51, .285]} size={[.6, .8, .024]} color="#6A777B" material="paint" />
      <Box position={[.23, .59, .315]} size={[.018, .13, .022]} color={FACTORY.ink} material="rubber" />
      {[.28, .32, .36, .4].map(y => <Box key={y} position={[-.03, y, .301]} size={[.36, .012, .007]} color={DARK_STEEL} shadow={false} />)}
    </>}
    {progress > .4 && <>
      <Box position={[0, .93, .317]} size={[.5, .34, .07]} color={FACTORY.ink} material="rubber" />
      <Box position={[0, .94, .356]} size={[.44, .25, .012]} color="#173337" material="glass" shadow={false} />
      {[-.055, .015, .085].map((y, i) => <Box key={y} position={[-.045, .94 + y, .364]} size={[.19 + i * .035, .012, .002]} color="#70998E" shadow={false} />)}
      <Box position={[0, .71, .39]} size={[.56, .035, .25]} rotation={[.16, 0, 0]} color={FRAME} material="steel" />
      <Box position={[-.03, .738, .4]} size={[.35, .012, .13]} rotation={[.16, 0, 0]} color="#253037" material="rubber" />
      <mesh position={[.2, .78, .323]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[.015, .015, .012, 10]} /><Paint color={FACTORY.teal} glow /></mesh>
    </>}
    {progress > .7 && <>
      <Box position={[-.2, 1.17, -.07]} size={[.2, .1, .25]} color={DARK_STEEL} material="steel" />
      <Tube position={[-.2, 1.46, -.07]} length={.51} radius={.018} />
      <Box position={[-.2, 1.73, -.07]} size={[.16, .23, .11]} color="#A7AEAD" material="paint" />
      <Tube position={[.2, 1.4, -.1]} length={.56} radius={.009} color={DARK_STEEL} />
      <Tube position={[.3, 1.3, -.1]} length={.36} radius={.009} color={DARK_STEEL} />
      <Tube position={[-.37, .68, -.17]} length={1.06} radius={.015} color="#293236" />
      {progress >= 1 && <Box position={[.23, 1.16, .08]} size={[.07, .025, .07]} color={FACTORY.teal} material="glass" />}
    </>}
  </group>
}

function ServiceWalkway({ progress }: { progress: number }) {
  return <group name="factory-service-walkway" rotation={[0, -.43, 0]}>
    {[-.48, .48].map(z => <Box key={z} position={[0, .12, z]} size={[1.9, .16, .045]} color={DARK_STEEL} material="steel" />)}
    {Array.from({ length: Math.max(1, Math.floor(progress * 10)) }, (_, i) => <group key={i} position={[(i - 4.5) * .185, .205, 0]}>
      <Box size={[.14, .035, .98]} color="#818C91" material="steel" />
      <Box position={[0, .02, 0]} size={[.025, .007, .85]} color={DARK_STEEL} material="steel" shadow={false} />
    </group>)}
    {progress > .55 && <>
      {[-.78, .78].map(x => <group key={x}>
        <Box position={[x, .035, -.48]} size={[.14, .07, .17]} color={FRAME} material="steel" />
        <Tube position={[x, .52, -.48]} length={.84} radius={.022} color="#8A8D72" />
      </group>)}
      <Box position={[-.97, .09, 0]} size={[.15, .08, .88]} color={DARK_STEEL} material="steel" />
      <Box position={[.97, .09, 0]} size={[.15, .08, .88]} color={DARK_STEEL} material="steel" />
    </>}
    {progress >= 1 && <>
      {[.6, .93].map(y => <Tube key={y} position={[0, y, -.48]} length={1.62} radius={.022} rotation={[0, 0, Math.PI / 2]} color="#8A8D72" />)}
      {[-.97, .97].map(x => <Box key={x} position={[x, .135, 0]} size={[.04, .007, .88]} color={FACTORY.yellow} shadow={false} />)}
    </>}
  </group>
}

/** A fitted worksite supports the approved object recipe; its parts stay in the shared renderer. */
function AssemblyFixture({ project, progress }: { project: IslandProject; progress: number }) {
  const family = project.assembly?.family
  return <group name={`factory-fixture-${family ?? 'unknown'}`}>
    <FloorMark width={1.8} depth={1.35} color={progress >= 1 ? '#85AC98' : FACTORY.yellow} />
    {progress > 0 && <>
      <Box position={[0, .055, 0]} size={[1.65, .11, 1.18]} color={DARK_STEEL} material="steel" />
      <Box position={[0, .12, 0]} size={[1.59, .025, 1.12]} color="#9AA5A7" material="steel" />
      {[-.72, .72].flatMap(x => [-.47, .47].map(z => <mesh key={`${x}:${z}`} position={[x, .14, z]}><cylinderGeometry args={[.028, .028, .025, 6]} /><Paint color={DARK_STEEL} material="steel" /></mesh>))}
    </>}
    {progress > .45 && family === 'support' && [-.65, .65].map(x => <group key={x}>
      <Box position={[x, .25, 0]} size={[.14, .22, 1]} color={FRAME} material="steel" />
      <Box position={[x, .37, 0]} size={[.24, .045, 1.08]} color="#9BA7AA" material="steel" />
      <Tube position={[x, .26, 0]} length={.86} radius={.018} rotation={[Math.PI / 2 - .22, 0, 0]} />
    </group>)}
    {progress > .45 && family === 'hold' && [-1, 1].flatMap(side => [-1, 1].map(front => <group key={`${side}:${front}`} position={[side * .66, .19, front * .43]}>
      <Box size={[.12, .1, .12]} color="#728176" material="paint" />
      <Tube position={[0, .07, 0]} length={.12} radius={.019} color={DARK_STEEL} />
      <Box position={[side * -.08, .13, 0]} size={[.24, .035, .065]} color={FRAME} material="steel" />
    </group>))}
    {progress > .45 && family === 'contain' && [-1, 1].map(side => <group key={side}>
      <Box position={[side * .69, .24, 0]} size={[.06, .24, .92]} color={FRAME} material="steel" />
      <Box position={[0, .24, side * .49]} size={[1.4, .24, .04]} color="#718B92" material="steel" />
    </group>)}
    {progress > .45 && family === 'reflect' && <group name="factory-optical-relay-mount">
      {[-.62, .62].map(x => <group key={x}>
        <Box position={[x, .34, 0]} size={[.08, .44, .82]} color={FRAME} material="steel" />
        <Tube position={[x, .32, .34]} length={.3} radius={.018} color={DARK_STEEL} />
      </group>)}
      <Box position={[0, .46, -.46]} size={[1.42, .06, .07]} color={DARK_STEEL} material="steel" />
      {progress >= 1 && <group position={[.68, .48, -.4]}>
        <Box size={[.12, .18, .08]} color={DARK_STEEL} material="paint" />
        <mesh position={[0, 0, .046]}><circleGeometry args={[.034, 12]} /><Paint color="#C8E7EF" material="glass" /></mesh>
      </group>}
    </group>}
    {progress >= 1 && <group position={[.73, .3, .5]}>
      <Box size={[.18, .3, .08]} color={DARK_STEEL} material="paint" />
      <Box position={[0, .075, .046]} size={[.1, .07, .012]} color="#91B8A1" material="glass" />
    </group>}
  </group>
}

/** Geometry only. The caller retains the same project, selection and committed progress. */
export function FactoryStructureVisual({ project, progress: rawProgress }: { project: IslandProject; progress: number }) {
  const progress = Number.isFinite(rawProgress) ? Math.max(0, Math.min(1, rawProgress)) : 0
  if (project.kind === 'assembly') return <AssemblyFixture project={project} progress={progress} />
  return <group name={`factory-project-${project.kind}`}>
    <FloorMark width={project.kind === 'beacon' ? 1.3 : 2} depth={project.kind === 'beacon' ? 1.15 : 1.4} color={FACTORY.metal} />
    {project.kind === 'garden' ? <GrowShelves progress={progress} /> : project.kind === 'workshop' ? <FabricationBench progress={progress} /> : project.kind === 'beacon' ? <CommsTerminal progress={progress} /> : project.kind === 'boardwalk' ? <ServiceWalkway progress={progress} /> : null}
    {project.level >= 2 && <group position={[-.65, .1, .55]}>
      <Box size={[.24, .16, .15]} color={FACTORY.ink} material="paint" />
      {Array.from({ length: Math.min(3, Math.max(0, project.level)) }, (_, i) => <Box key={i} position={[-.07 + i * .07, .02, .083]} size={[.035, .07, .012]} color={FACTORY.teal} shadow={false} />)}
    </group>}
  </group>
}
