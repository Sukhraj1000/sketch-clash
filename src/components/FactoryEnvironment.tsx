import { FACTORY, FactoryBox as Box, FactoryPaint as Paint, FloorMark } from './FactoryPrimitives'

/** These are the existing resource destinations, not a second factory simulation. */
export const FACTORY_STATIONS = {
  materials: { x: -3.25, z: 1.2 }, water: { x: -.25, z: -2.9 },
  ideas: { x: .15, z: .7 }, energy: { x: 3.65, z: .55 },
} as const

function SupplyRack() {
  return <group position={[0, 0, -.38]}>
    {[-.47, .47].map(x => <Box key={x} position={[x, .34, 0]} size={[.055, .68, .055]} color={FACTORY.ink} />)}
    {[.1, .38, .68].map(y => <Box key={y} position={[0, y, 0]} size={[1.05, .055, .4]} color={FACTORY.paper} />)}
    {[-.28, .06, .31].map((x, i) => <group key={x} position={[x, i === 1 ? .22 : .51, 0]}>
      <Box size={[i === 1 ? .44 : .24, .2, .26]} color={i === 1 ? FACTORY.teal : FACTORY.metal} />
      <Box position={[0, 0, .137]} size={[.1, .035, .012]} color={FACTORY.ink} shadow={false} />
    </group>)}
  </group>
}

function WaterStation() {
  return <group position={[0, 0, -.36]}>
    <Box position={[0, .05, 0]} size={[.75, .1, .5]} color={FACTORY.ink} />
    <mesh position={[0, .4, -.035]} castShadow><cylinderGeometry args={[.26, .26, .62, 12]} /><Paint color={FACTORY.paper} /></mesh>
    <mesh position={[0, .4, -.035]}><cylinderGeometry args={[.263, .263, .15, 12]} /><Paint color={FACTORY.blue} /></mesh>
    <mesh position={[0, .73, -.035]} castShadow><cylinderGeometry args={[.2, .2, .055, 12]} /><Paint color={FACTORY.ink} /></mesh>
    <Box position={[0, .33, .265]} size={[.07, .075, .22]} color={FACTORY.metal} />
    <Box position={[0, .305, .365]} size={[.07, .09, .06]} color={FACTORY.ink} />
  </group>
}

function DesignTerminal() {
  return <group position={[0, 0, -.4]}>
    <Box position={[0, .25, 0]} size={[.13, .5, .14]} color={FACTORY.ink} />
    <Box position={[0, .045, 0]} size={[.5, .09, .35]} color={FACTORY.metal} />
    <group position={[0, .6, 0]} rotation={[-.38, 0, 0]}>
      <Box size={[.62, .36, .09]} color={FACTORY.paper} />
      <Box position={[0, 0, .052]} size={[.53, .26, .02]} color={FACTORY.ink} />
      <Box position={[-.13, .025, .067]} size={[.12, .12, .012]} color={FACTORY.teal} shadow={false} />
      {[.06, -.03, -.1].map((y, i) => <Box key={y} position={[.08, y, .067]} size={[i === 2 ? .1 : .2, .018, .012]} color={FACTORY.paper} shadow={false} />)}
    </group>
  </group>
}

function ChargeStation() {
  return <group>
    <mesh position={[0, .035, .08]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[.3, .35, 16]} /><Paint color={FACTORY.teal} /></mesh>
    <group position={[0, 0, -.42]}>
      <Box position={[0, .34, 0]} size={[.5, .68, .24]} color={FACTORY.paper} />
      <Box position={[0, .59, .13]} size={[.36, .1, .025]} color={FACTORY.ink} />
      {[-.105, 0, .105].map(x => <Box key={x} position={[x, .59, .148]} size={[.07, .05, .012]} color={FACTORY.teal} />)}
      <Box position={[0, .33, .13]} size={[.27, .25, .025]} color={FACTORY.ink} />
      <Box position={[.045, .37, .148]} size={[.05, .17, .02]} color={FACTORY.yellow} rotation={[0, 0, -.45]} />
      <Box position={[-.025, .29, .148]} size={[.05, .17, .02]} color={FACTORY.yellow} rotation={[0, 0, -.45]} />
    </group>
  </group>
}

/** A low, open industrial set. Existing residents and task paths remain authoritative. */
export default function FactoryEnvironment() {
  return <group name="factory-environment">
    <mesh position={[0, -.68, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[120, 120]} /><Paint color="#C9D4D0" /></mesh>
    <mesh position={[0, -.39, 0]} castShadow receiveShadow><cylinderGeometry args={[5.7, 5.4, .47, 16]} /><Paint color={FACTORY.ink} /></mesh>
    <mesh position={[0, -.1, 0]} castShadow receiveShadow><cylinderGeometry args={[5.7, 5.7, .18, 16]} /><Paint color={FACTORY.floor} /></mesh>
    {Array.from({ length: 11 }, (_, i) => i - 5).flatMap(coordinate => {
      const span = 2 * Math.sqrt(5.5 ** 2 - coordinate ** 2)
      return [
        <Box key={`grid-x-${coordinate}`} position={[coordinate, -.003, 0]} size={[.014, .012, span]} color={FACTORY.seam} shadow={false} />,
        <Box key={`grid-z-${coordinate}`} position={[0, -.003, coordinate]} size={[span, .012, .014]} color={FACTORY.seam} shadow={false} />,
      ]
    })}
    {Array.from({ length: 32 }, (_, i) => {
      const angle = i * Math.PI / 16
      return <Box key={`rim-${i}`} position={[Math.cos(angle) * 5.36, .005, Math.sin(angle) * 5.36]} size={[.11, .02, .28]} color={i % 2 ? FACTORY.yellow : FACTORY.ink} rotation={[0, -angle, 0]} shadow={false} />
    })}
    {Object.entries(FACTORY_STATIONS).map(([resource, point]) => <group key={resource} name={`factory-station-${resource}`} position={[point.x, .025, point.z]}>
      <FloorMark width={resource === 'materials' ? 1.2 : 1} depth={1.05} color={resource === 'water' ? FACTORY.blue : resource === 'energy' ? FACTORY.teal : FACTORY.yellow} />
      {resource === 'materials' ? <SupplyRack /> : resource === 'water' ? <WaterStation /> : resource === 'ideas' ? <DesignTerminal /> : <ChargeStation />}
    </group>)}
    {[-1, 1].map(side => <group key={side} position={[side * 3.5, 0, -3.65]}>
      <Box position={[0, .1, 0]} size={[.23, .2, .23]} color={FACTORY.ink} />
      <mesh position={[0, .3, 0]} castShadow><cylinderGeometry args={[.065, .065, .4, 8]} /><Paint color={FACTORY.yellow} /></mesh>
      <mesh position={[0, .41, 0]}><cylinderGeometry args={[.068, .068, .08, 8]} /><Paint color={FACTORY.ink} /></mesh>
    </group>)}
    <group position={[-3.25, .03, 3.6]} rotation={[0, -.55, 0]}>
      <Box position={[0, .22, 0]} size={[.08, .44, .08]} color={FACTORY.ink} />
      <Box position={[0, .46, 0]} size={[.72, .28, .07]} color={FACTORY.paper} />
      {[0, 1, 2].map(i => <Box key={i} position={[-.2 + i * .18, .46, .045]} size={[.1, .14, .02]} color={i === 0 ? FACTORY.yellow : FACTORY.ink} />)}
    </group>
  </group>
}
