import type { IslandProject } from '../lib/island'
import { FACTORY, FactoryBox as Box, FactoryPaint as Paint, FloorMark } from './FactoryPrimitives'

function GrowShelves({ progress }: { progress: number }) {
  return <group name="factory-grow-shelves">
    <Box position={[0, .05, 0]} size={[1.65, .1, 1.05]} color={FACTORY.ink} />
    {progress > .15 && [-.73, .73].flatMap(x => [-.4, .4].map(z => <Box key={`${x}-${z}`} position={[x, .46, z]} size={[.06, .82, .06]} color={FACTORY.paper} />))}
    {progress > .32 && [.23, .72].map(y => <group key={y} position={[0, y, 0]}>
      <Box size={[1.55, .055, .9]} color={FACTORY.metal} />
      {progress > .6 && [-.48, 0, .48].map(x => <group key={x} position={[x, .1, 0]}>
        <Box size={[.35, .15, .58]} color={FACTORY.paper} />
        <Box position={[0, .08, 0]} size={[.29, .02, .5]} color="#455A4C" />
        {progress > .82 && [-.15, .15].map(z => <group key={z} position={[0, .11, z]}>
          <mesh position={[0, .075, 0]} castShadow><cylinderGeometry args={[.018, .025, .15, 5]} /><Paint color="#67A56A" /></mesh>
          {[-1, 1].map(side => <mesh key={side} position={[side * .045, .12, 0]} rotation={[0, 0, side * -.65]} scale={[.7, 1, .45]} castShadow><octahedronGeometry args={[.1]} /><Paint color={FACTORY.teal} /></mesh>)}
        </group>)}
      </group>)}
    </group>)}
  </group>
}

function FabricationBench({ progress }: { progress: number }) {
  return <group name="factory-fabrication-bench">
    <Box position={[0, .045, 0]} size={[1.65, .09, 1.1]} color={FACTORY.ink} />
    {progress > .15 && [-.64, .64].map(x => <Box key={x} position={[x, .34, 0]} size={[.15, .6, .7]} color={FACTORY.paper} />)}
    {progress > .35 && <>
      <Box position={[0, .67, 0]} size={[1.65, .12, .95]} color={FACTORY.ink} />
      <Box position={[0, .74, 0]} size={[1.57, .035, .87]} color={FACTORY.paper} />
      {[-.45, .45].map(x => <Box key={x} position={[x, .42, .37]} size={[.35, .24, .04]} color={FACTORY.teal} />)}
    </>}
    {progress > .6 && <group position={[-.36, .8, 0]}>
      <Box size={[.38, .08, .3]} color={FACTORY.metal} />
      <Box position={[-.11, .095, 0]} size={[.08, .15, .3]} color={FACTORY.ink} />
      <Box position={[.11, .095, 0]} size={[.08, .15, .3]} color={FACTORY.teal} />
      <Box position={[0, .16, 0]} size={[.14, .06, .22]} color={FACTORY.yellow} />
    </group>}
    {progress > .82 && <group position={[.45, .8, .04]} rotation={[0, -.3, 0]}>
      <Box size={[.3, .045, .4]} color={FACTORY.teal} />
      <Box position={[.01, .07, 0]} size={[.045, .06, .3]} color={FACTORY.ink} />
      <Box position={[.01, .07, -.15]} size={[.2, .08, .08]} color={FACTORY.metal} />
    </group>}
  </group>
}

function CommsTerminal({ progress }: { progress: number }) {
  return <group name="factory-comms-terminal">
    <Box position={[0, .06, 0]} size={[1, .12, .85]} color={FACTORY.ink} />
    {progress > .15 && <Box position={[0, .38, 0]} size={[.58, .62, .48]} color={FACTORY.paper} />}
    {progress > .4 && <>
      <Box position={[0, .49, .253]} size={[.4, .3, .025]} color={FACTORY.ink} />
      {[-.12, 0, .12].map((x, i) => <Box key={x} position={[x, .45 + i * .045, .27]} size={[.055, .1 + i * .07, .015]} color={FACTORY.teal} shadow={false} />)}
      <Box position={[0, .75, -.08]} size={[.34, .1, .3]} color={FACTORY.metal} />
    </>}
    {progress > .7 && <group position={[0, 1.03, -.08]}>
      <mesh castShadow><cylinderGeometry args={[.045, .055, .48, 8]} /><Paint color={FACTORY.ink} /></mesh>
      <group position={[0, .15, 0]} rotation={[.6, 0, 0]}>
        <mesh castShadow><sphereGeometry args={[.34, 12, 6, 0, Math.PI * 2, 0, Math.PI / 2]} /><Paint color={FACTORY.paper} /></mesh>
        <mesh position={[0, .04, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[.32, .025, 5, 12]} /><Paint color={FACTORY.teal} /></mesh>
      </group>
      {progress >= 1 && <mesh position={[0, .39, .06]}><sphereGeometry args={[.055, 8, 6]} /><Paint color={FACTORY.yellow} glow /></mesh>}
    </group>}
  </group>
}

function ServiceWalkway({ progress }: { progress: number }) {
  return <group name="factory-service-walkway" rotation={[0, -.43, 0]}>
    {Array.from({ length: Math.max(1, Math.floor(progress * 10)) }, (_, i) => <group key={i} position={[(i - 4) * .2, .09, 0]}>
      <Box size={[.18, .12, 1.1]} color={i % 2 ? FACTORY.metal : FACTORY.paper} />
      {[-.48, .48].map(z => <Box key={z} position={[0, .065, z]} size={[.17, .015, .075]} color={i % 2 ? FACTORY.ink : FACTORY.yellow} shadow={false} />)}
    </group>)}
    {progress > .55 && [-.75, .75].map(x => <Box key={x} position={[x, .3, -.5]} size={[.045, .6, .045]} color={FACTORY.ink} />)}
    {progress >= 1 && <Box position={[0, .58, -.5]} size={[1.6, .06, .06]} color={FACTORY.yellow} />}
  </group>
}

/** Geometry only. The caller retains the same project, selection and committed progress. */
export function FactoryStructureVisual({ project, progress: rawProgress }: { project: IslandProject; progress: number }) {
  const progress = Number.isFinite(rawProgress) ? Math.max(0, Math.min(1, rawProgress)) : 0
  if (project.kind === 'assembly') return null
  return <group name={`factory-project-${project.kind}`}>
    <FloorMark width={project.kind === 'beacon' ? 1.3 : 2} depth={project.kind === 'beacon' ? 1.15 : 1.4} color={FACTORY.metal} />
    {project.kind === 'garden' ? <GrowShelves progress={progress} /> : project.kind === 'workshop' ? <FabricationBench progress={progress} /> : project.kind === 'beacon' ? <CommsTerminal progress={progress} /> : project.kind === 'boardwalk' ? <ServiceWalkway progress={progress} /> : null}
    {project.level >= 2 && <group position={[-.65, .1, .55]}>
      <Box size={[.24, .16, .15]} color={FACTORY.ink} />
      {Array.from({ length: Math.min(3, Math.max(0, project.level)) }, (_, i) => <Box key={i} position={[-.07 + i * .07, .02, .083]} size={[.035, .07, .012]} color={FACTORY.teal} shadow={false} />)}
    </group>}
  </group>
}
