import { FACTORY, FactoryBox as Box, FactoryPaint as Paint, FloorMark } from './FactoryPrimitives'

/** These are the existing resource destinations, not a second factory simulation. */
export const FACTORY_STATIONS = {
  materials: { x: -3.25, z: 1.2 }, water: { x: -.25, z: -2.9 },
  ideas: { x: .15, z: .7 }, energy: { x: 3.65, z: .55 },
} as const

/** Fittings and framing use real thicknesses; the racks do not invent stored stock. */
function SupplyRack() {
  return <group position={[0, 0, -.38]}>
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
  return <group position={[0, 0, -.36]}>
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
  return <group position={[0, 0, -.4]}>
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
    <group position={[0, 0, -.42]}>
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

function ServiceWall() {
  return <group name="factory-service-wall">
    <Box position={[0, .47, -5.38]} size={[12, .94, .14]} color="#979B96" material="concrete" />
    <Box position={[0, .97, -5.38]} size={[12, .045, .18]} color="#606B70" material="steel" />
    <Box position={[0, .12, -5.285]} size={[12, .22, .045]} color="#666F70" />
    {[-5.75, -2.9, 2.9, 5.75].map(x => <group key={x} position={[x, 0, -5.3]}>
      <Box position={[0, .9, 0]} size={[.12, 1.8, .14]} color="#626D72" material="steel" />
      <Box position={[0, .035, 0]} size={[.26, .055, .25]} color="#7E898D" material="steel" />
    </group>)}
    <Box position={[0, 1.77, -5.3]} size={[11.65, .12, .14]} color="#717C81" material="steel" />
    {[-4.25, 0, 4.25].map(x => <group key={x} position={[x, 1.65, -5.15]}>
      <Box size={[1.1, .055, .12]} color="#C4C8C3" material="steel" />
      <Box position={[0, -.033, 0]} size={[1.03, .012, .09]} color="#E4E6D9" shadow={false} />
    </group>)}
    <group position={[-4.5, 0, -4.94]}>
      <Box position={[0, .51, 0]} size={[1.25, 1.02, .42]} color="#7E898B" />
      {[-.31, .31].map(x => <group key={x} position={[x, .52, .22]}>
        <Box size={[.59, .92, .018]} color="#929B9A" />
        <Box position={[x < 0 ? .2 : -.2, 0, .025]} size={[.025, .15, .025]} color="#3D464A" material="rubber" />
        {[-.25, -.3, -.35].map(y => <Box key={y} position={[0, y, .012]} size={[.39, .014, .008]} color="#687477" shadow={false} />)}
      </group>)}
      <Box position={[-.31, .8, .236]} size={[.11, .08, .008]} color="#B6A678" shadow={false} />
    </group>
    <Box position={[.3, .71, -5.27]} size={[5.8, .025, .035]} color="#778185" material="steel" />
    <Box position={[3.2, .42, -5.27]} size={[.025, .59, .035]} color="#778185" material="steel" />
    <Box position={[3.2, .22, -5.22]} size={[.15, .2, .08]} color="#ABB0AA" />
  </group>
}

/** An open industrial floor; all residents still follow their saved island paths. */
export default function FactoryEnvironment() {
  return <group name="factory-environment">
    <mesh position={[0, -.14, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[120, 120]} /><Paint color="#59656B" material="concrete" /></mesh>
    <Box position={[0, -.065, 0]} size={[12, .13, 11]} color={FACTORY.floor} material="concrete" />
    {[-4, -2, 0, 2, 4].map(coordinate => <group key={coordinate}>
      <Box position={[coordinate, .002, 0]} size={[.014, .003, 11]} color={FACTORY.seam} shadow={false} />
      <Box position={[0, .002, coordinate]} size={[12, .003, .014]} color={FACTORY.seam} shadow={false} />
    </group>)}
    {/* Fine scuff lines break up the floor without representing simulated events. */}
    {Array.from({ length: 17 }, (_, i) => <Box key={`scuff-${i}`} position={[-5.1 + (i * 1.79) % 10.2, .004, -4.7 + (i * 2.31) % 9.3]} size={[.1 + (i % 4) * .1, .002, .006]} color={i % 2 ? '#818B88' : '#89928F'} rotation={[0, .24 + (i % 5) * .31, 0]} shadow={false} />)}
    {[-1, 1].map(side => <group key={side}>
      <Box position={[side * 5.45, .008, .15]} size={[.045, .008, 10.05]} color="#BBBAB0" shadow={false} />
      <Box position={[0, .008, side * 4.7]} size={[10.9, .008, .045]} color="#BBBAB0" shadow={false} />
    </group>)}
    <group name="factory-service-aisle">
      {[-1, 1].map(side => <Box key={side} position={[0, .01, 3.45 + side * .48]} size={[10.85, .008, .045]} color={FACTORY.yellow} shadow={false} />)}
      {Array.from({ length: 9 }, (_, i) => <Box key={i} position={[-4.6 + i * 1.15, .011, 3.45]} size={[.42, .007, .028]} color="#B6B6A5" shadow={false} />)}
    </group>
    <ServiceWall />
    {Object.entries(FACTORY_STATIONS).map(([resource, point]) => <group key={resource} name={`factory-station-${resource}`} position={[point.x, .025, point.z]}>
      <FloorMark width={resource === 'materials' ? 1.2 : 1} depth={1.05} color="#B8AE8D" />
      {resource === 'materials' ? <SupplyRack /> : resource === 'water' ? <WaterStation /> : resource === 'ideas' ? <DesignTerminal /> : <ChargeStation />}
    </group>)}
    {[-5.38, 5.38].map(x => <group key={x} position={[x, 0, -4.4]}>
      <Box position={[0, .025, 0]} size={[.21, .05, .21]} color="#666F71" material="steel" />
      <mesh position={[0, .33, 0]} castShadow><cylinderGeometry args={[.055, .055, .6, 20]} /><Paint color={FACTORY.yellow} material="paint" /></mesh>
      <mesh position={[0, .45, 0]}><cylinderGeometry args={[.056, .056, .12, 20]} /><Paint color="#4B5457" /></mesh>
    </group>)}
  </group>
}
