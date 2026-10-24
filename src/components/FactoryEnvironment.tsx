import { FACTORY, FactoryBox as Box, FactoryPaint as Paint, FloorMark } from './FactoryPrimitives'
import { WORLD_MAP_SURFACE_SCALE, WORLD_PATHS, WORLD_STATIONS, WORLD_STATION_BACKSETS, WORLD_TREES, WORLD_WAYFINDER, worldFloorSeams, worldGroundContour, worldGroundDetails, worldGroundShape, worldRimDecor } from './worldMap'
import type { WorldMapVertex } from './worldMap'

/** These are the existing resource destinations, not a second factory simulation. */
const FACTORY_STATIONS = WORLD_STATIONS

/** Fittings and framing use real thicknesses; the racks do not invent stored stock. */
function SupplyRack() {
  return <group position={[0, 0, -WORLD_STATION_BACKSETS.materials]}>
    {[-.49, .49].flatMap(x => [-.19, .19].map(z => <group key={`${x}:${z}`} position={[x, 0, z]}>
      <Box position={[0, .47, 0]} size={[.032, .94, .032]} color={FACTORY.metal} material="steel" />
      <Box position={[0, .025, 0]} size={[.09, .035, .085]} color={FACTORY.metal} material="steel" />
    </group>))}
    {[.12, .5, .88].map(y => <group key={y}>
      <Box position={[0, y, 0]} size={[1.04, .025, .43]} color="#849096" material="steel" />
      <Box position={[0, y - .028, .205]} size={[1.04, .04, .025]} color={FACTORY.metal} material="steel" />
      <Box position={[0, y - .028, -.205]} size={[1.04, .04, .025]} color={FACTORY.metal} material="steel" />
    </group>)}
    {[-1, 1].map(side => <Box key={side} position={[0, .48, -.21]} rotation={[0, 0, side * .89]} size={[.018, 1.12, .018]} color="#738087" material="steel" />)}
    <Box position={[.29, .846, .225]} size={[.19, .04, .008]} color="#D0D2CB" shadow={false} />
  </group>
}

function WaterStation() {
  return <group position={[0, 0, -WORLD_STATION_BACKSETS.water]}>
    <Box position={[0, .035, 0]} size={[.76, .07, .58]} color="#4B555A" material="steel" />
    {[-.2, .2].flatMap(x => [-.17, .17].map(z => <Box key={`${x}:${z}`} position={[x, .13, z]} size={[.045, .2, .045]} color={FACTORY.metal} material="steel" />))}
    <mesh position={[0, .5, -.035]} castShadow><cylinderGeometry args={[.26, .26, .59, 32]} /><Paint color="#ADB5B8" material="steel" /></mesh>
    {[.215, .785].map(y => <mesh key={y} position={[0, y, -.035]} scale={[1, .28, 1]} castShadow><sphereGeometry args={[.26, 24, 12]} /><Paint color="#ADB5B8" material="steel" /></mesh>)}
    {/* The hemispherical end caps are shallow, with visible welded retaining bands. */}
    {[.27, .73].map(y => <mesh key={y} position={[0, y, -.035]}><cylinderGeometry args={[.267, .267, .025, 32]} /><Paint color="#77838A" material="steel" /></mesh>)}
    <mesh position={[0, .9, -.035]} castShadow><cylinderGeometry args={[.055, .055, .1, 20]} /><Paint color={FACTORY.metal} material="steel" /></mesh>
    <mesh position={[0, .96, -.035]} castShadow><cylinderGeometry args={[.08, .08, .025, 20]} /><Paint color={FACTORY.metal} material="steel" /></mesh>
    <mesh position={[0, .32, .31]} rotation={[Math.PI / 2, 0, 0]} castShadow><cylinderGeometry args={[.026, .026, .23, 16]} /><Paint color={FACTORY.metal} material="steel" /></mesh>
    <mesh position={[0, .31, .44]} rotation={[0, Math.PI / 2, 0]}><torusGeometry args={[.058, .01, 8, 20]} /><Paint color="#626F72" material="steel" /></mesh>
    <mesh position={[0, .23, .41]} castShadow><cylinderGeometry args={[.025, .025, .17, 16]} /><Paint color={FACTORY.metal} material="steel" /></mesh>
    <Box position={[.07, .49, .23]} size={[.1, .16, .015]} color="#D1D5D2" shadow={false} />
    <Box position={[.07, .49, .241]} size={[.013, .12, .006]} color="#647F87" shadow={false} />
  </group>
}

function DesignTerminal() {
  return <group position={[0, 0, -WORLD_STATION_BACKSETS.ideas]}>
    <Box position={[0, .04, 0]} size={[.4, .065, .32]} color="#5B6569" material="steel" />
    <Box position={[0, .34, -.035]} size={[.075, .6, .075]} color={FACTORY.metal} material="steel" />
    <Box position={[0, .5, .12]} size={[.43, .024, .25]} color="#626E73" material="steel" />
    <Box position={[0, .517, .135]} size={[.28, .012, .11]} color="#343B3D" material="rubber" />
    <group position={[0, .76, -.025]} rotation={[-.18, 0, 0]}>
      <Box size={[.6, .36, .045]} color="#465158" material="steel" />
      <Box position={[0, 0, .026]} size={[.54, .29, .009]} color="#1B292D" material="glass" />
      <Box position={[-.17, .03, .033]} size={[.11, .18, .003]} color="#50676B" shadow={false} />
      {[.075, .025, -.025, -.075].map((y, i) => <Box key={y} position={[.07, y, .033]} size={[i === 3 ? .14 : .23, .008, .003]} color="#8A9C9C" shadow={false} />)}
      <mesh position={[.26, -.153, .028]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[.006, .006, .005, 10]} /><Paint color="#86A597" glow /></mesh>
    </group>
    <Box position={[-.045, .3, -.08]} size={[.012, .42, .012]} color="#30373A" material="rubber" />
  </group>
}

function ChargeStation() {
  return <group>
    <Box position={[0, .025, .05]} size={[.62, .04, .48]} color="#656F72" material="steel" />
    {[-.18, .18].map(x => <Box key={x} position={[x, .049, .05]} size={[.035, .012, .26]} color="#B0A272" material="steel" />)}
    <group position={[0, 0, -WORLD_STATION_BACKSETS.energy]}>
      <Box position={[0, .41, 0]} size={[.49, .82, .26]} color="#89918F" />
      <Box position={[0, .41, .137]} size={[.44, .75, .015]} color="#9DA3A0" />
      <Box position={[0, .64, .151]} size={[.26, .12, .012]} color="#25343A" material="glass" />
      <Box position={[-.055, .645, .16]} size={[.12, .013, .004]} color="#9AB2A6" shadow={false} />
      <Box position={[.185, .39, .16]} size={[.018, .12, .022]} color={FACTORY.ink} material="rubber" />
      {[.14, .19, .24, .29].map(y => <Box key={y} position={[0, y, .152]} size={[.27, .012, .009]} color="#5D686B" shadow={false} />)}
      <Box position={[-.165, .44, .155]} size={[.055, .08, .008]} color="#B6A475" shadow={false} />
      <mesh position={[.27, .4, .04]} rotation={[0, Math.PI / 2, 0]} castShadow><torusGeometry args={[.17, .015, 8, 24, Math.PI * 1.65]} /><Paint color="#30383B" material="rubber" /></mesh>
      <Box position={[.3, .51, .155]} size={[.06, .13, .05]} rotation={[0, 0, -.22]} color="#3F494D" material="rubber" />
    </group>
  </group>
}

/** A painted route follows the same map polyline as its island footpath. */
function FloorRoute({ points, width = .025, color = FACTORY.yellow }: { points: WorldMapVertex[]; width?: number; color?: string }) {
  return <group>{points.slice(1).map((to, index) => {
    const from = points[index]
    const dx = to[0] - from[0], dz = to[2] - from[2]
    return <Box key={index} position={[(from[0] + to[0]) / 2, from[1], (from[2] + to[2]) / 2]} rotation={[0, Math.atan2(dx, dz), 0]} size={[width, .006, Math.hypot(dx, dz)]} color={color} shadow={false} />
  })}</group>
}

/** Tree locations become utility fittings, never extra workstations or inventory. */
function UtilityFitting({ index }: { index: number }) {
  return <group>
    <Box position={[0, .035, 0]} size={[.48, .07, .44]} color="#5D696D" material="steel" />
    <Box position={[0, .4, 0]} size={[.41, .68, .32]} color="#8A9597" />
    <Box position={[0, .4, .17]} size={[.35, .61, .014]} color="#A6AEAB" />
    <Box position={[.12, .41, .187]} size={[.016, .12, .018]} color="#364346" material="rubber" />
    {[-.18, -.13, -.08].map(y => <Box key={y} position={[0, .4 + y, .18]} size={[.22, .012, .008]} color="#647176" shadow={false} />)}
    <Box position={[-.09, .59, .184]} size={[.08, .08, .006]} color="#C3B07A" shadow={false} />
    <Box position={[0, 1.09, -.09]} size={[.045, .66, .045]} color="#74828A" material="steel" />
    <group position={[0, 1.42, -.09]} rotation={[0, index * .5, 0]}>
      <Box size={[.52, .06, .15]} color="#AEB6B3" material="steel" />
      <Box position={[0, -.035, 0]} size={[.43, .012, .1]} color="#E0E3D6" shadow={false} />
    </group>
  </group>
}

/** The island's exact contour, station anchors and routes, with industrial materials. */
export default function FactoryEnvironment({ seed = 4127 }: { seed?: number } = {}) {
  const shape = worldGroundShape()
  const boundary = worldGroundContour(.925)
  const edge: WorldMapVertex[] = [...boundary, boundary[0]].map(({ x, z }) => [x, .017, z])
  return <group name="factory-environment">
    <mesh position={[0, -.72, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[120, 120]} /><Paint color="#59656B" material="concrete" /></mesh>
    <mesh name="factory-map-foundation" position={[0, -.69, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow castShadow><extrudeGeometry args={[shape, { depth: .48, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .22, bevelThickness: .1 }]} /><Paint color="#5B6669" material="concrete" /></mesh>
    <mesh name="factory-map-shoulder" position={[0, -.14, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[1.04, 1.04, 1]} receiveShadow><shapeGeometry args={[shape]} /><Paint color="#90968E" material="concrete" /></mesh>
    <mesh name="factory-map-surface" position={[0, -.08, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[WORLD_MAP_SURFACE_SCALE, WORLD_MAP_SURFACE_SCALE, 1]} receiveShadow><extrudeGeometry args={[shape, { depth: .08, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .04, bevelThickness: .02 }]} /><Paint color={FACTORY.floor} material="concrete" /></mesh>
    <group name="factory-floor-joints">{worldFloorSeams().map((points, index) => <FloorRoute key={index} points={points} width={.014} color={FACTORY.seam} />)}</group>
    <FloorRoute points={edge} width={.035} color="#B0AB91" />
    <mesh name="factory-map-hub" position={[0, .012, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow><circleGeometry args={[.82, 8]} /><Paint color="#778181" material="concrete" /></mesh>
    <group name="factory-map-routes">{WORLD_PATHS.map((points, index) => <group key={index} name={`factory-map-route-${index}`} userData={{ mapPoints: points }}>
      <FloorRoute points={points} width={.22} color="#858E87" />
      <FloorRoute points={points.map(([x, , z]) => [x, .025, z])} width={.025} color="#AFAA8B" />
    </group>)}</group>
    {Object.entries(FACTORY_STATIONS).map(([resource, point]) => <group key={resource} name={`factory-station-${resource}`} position={[point.x, .025, point.z]}>
      <FloorMark width={resource === 'materials' ? 1.2 : 1} depth={1.05} color="#B8AE8D" />
      {resource === 'materials' ? <SupplyRack /> : resource === 'water' ? <WaterStation /> : resource === 'ideas' ? <DesignTerminal /> : <ChargeStation />}
    </group>)}
    {WORLD_TREES.map((tree, index) => <group key={index} name={`factory-map-utility-${index}`} position={[tree.x, 0, tree.z]} scale={tree.size}><UtilityFitting index={index} /></group>)}
    {worldRimDecor(seed).map((point, index) => <group key={index} name={`factory-map-edge-${index}`} position={[point.x, -.01, point.z]} rotation={[0, index, 0]}>
      <Box position={[0, point.size * .22, 0]} size={[point.size * 2.2, point.size * .44, point.size * 1.35]} color="#738086" material="steel" />
      <Box position={[0, point.size * .45, 0]} size={[point.size * 1.65, .014, point.size * .7]} color={index % 2 ? '#ACAD97' : '#929D9B'} shadow={false} />
    </group>)}
    {worldGroundDetails(seed).map((point, index) => <group key={index} name={`factory-map-detail-${index}`} position={[point.x, .024, point.z]} rotation={[0, point.angle, 0]}>
      <Box size={[.2, .018, .12]} color="#687477" material="steel" />
      {[-.06, 0, .06].map(x => <Box key={x} position={[x, .012, 0]} size={[.018, .004, .08]} color="#4E5A60" shadow={false} />)}
    </group>)}
    <group name="factory-map-wayfinder" position={[WORLD_WAYFINDER.x, 0, WORLD_WAYFINDER.z]} rotation={[0, WORLD_WAYFINDER.rotation, 0]}>
      <Box position={[0, .46, 0]} size={[.06, .93, .06]} color="#738187" material="steel" />
      <Box position={[.09, .74, 0]} size={[.64, .28, .04]} color="#B5AE8D" material="steel" />
      <Box position={[.08, .75, .024]} size={[.27, .035, .006]} color="#38464B" shadow={false} />
    </group>
  </group>
}
