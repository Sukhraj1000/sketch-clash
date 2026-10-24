import { ObjectArms, ObjectFace, ObjectMaterial as Paint } from './ObjectRig'
import type { FurnitureFeatures } from './furniturePresentation'

type Props = { kind: 'table' | 'chair'; color: string; accent: string; feet: boolean; eyes: boolean; arms: boolean; features?: FurnitureFeatures }

/** Furniture legs belong to the object, even when decorative feet are absent.
 * Their pivots attach to the underside, so a walking pose never detaches them.
 * No geometry or animation grants an agent a new capability. */
function Legs({ kind, color, moving, tapered }: { kind: Props['kind']; color: string; moving: boolean; tapered?: boolean }) {
  const table = kind === 'table'
  const x = table ? .65 : .32, z = table ? .38 : .31
  const top = table ? .94 : .71, bottom = .025, width = table ? .12 : .1
  return <group>{[-1, 1].flatMap(side => [-1, 1].map(depth => {
    const limb = `${depth < 0 ? 'back-' : ''}${side < 0 ? 'left' : 'right'}`
    return <group key={limb} name={moving ? `sc-foot-${limb}` : undefined} position={[side * x, top, depth * z]} userData={{ restY: top, strideScale: .55, liftScale: 0 }}>
      <mesh name={`sc-${kind}-leg-${limb}`} position={[0, -(top - bottom) / 2, 0]} rotation={[0, tapered ? Math.PI / 4 : 0, 0]} castShadow receiveShadow>{tapered ? <cylinderGeometry args={[width / Math.SQRT2, width * .72 / Math.SQRT2, top - bottom, 4]} /> : <boxGeometry args={[width, top - bottom, width]} />}<Paint color={color} /></mesh>
    </group>
  }))}</group>
}

function Stretchers({ kind, color }: { kind: Props['kind']; color: string }) {
  const x = kind === 'table' ? .65 : .32, z = kind === 'table' ? .38 : .31
  return <group name={`sc-${kind}-stretchers`}>
    {[-1, 1].map(side => <mesh key={side} position={[side * x, .29, 0]} castShadow><boxGeometry args={[.065, .075, z * 2]} /><Paint color={color} /></mesh>)}
    <mesh position={[0, .29, 0]} castShadow><boxGeometry args={[x * 2, .075, .065]} /><Paint color={color} /></mesh>
  </group>
}

export default function FurnitureShape({ kind, color, accent, feet, eyes, arms, features }: Props) {
  // Braced legs form one rigid frame. Whole-body travel still follows the real
  // task; individual leg swings would detach the observed horizontal stretchers.
  const moving = feet && !features?.stretchers
  if (kind === 'table') return <group name="sc-table">
    <mesh name="sc-table-top" position={[0, 1, 0]} castShadow receiveShadow><boxGeometry args={[1.62, .12, 1.04]} /><Paint color={color} /></mesh>
    <group name="sc-table-apron">
      {[-1, 1].map(side => <mesh key={`long-${side}`} position={[0, .87, side * .39]} castShadow><boxGeometry args={[1.4, .16, .08]} /><Paint color={color} /></mesh>)}
      {[-1, 1].map(side => <mesh key={`short-${side}`} position={[side * .65, .87, 0]} castShadow><boxGeometry args={[.08, .16, .78]} /><Paint color={color} /></mesh>)}
    </group>
    <Legs kind={kind} color={color} moving={moving} tapered={features?.taperedLegs} />
    {features?.stretchers && <Stretchers kind={kind} color={color} />}
    {eyes && <ObjectFace y={.91} z={.435} width={.12} size={.54} />}
    {arms && <ObjectArms color={accent} width={.82} y={.92} size={.65} />}
  </group>

  return <group name="sc-chair">
    <mesh name="sc-chair-seat" position={[0, .76, .015]} castShadow receiveShadow><boxGeometry args={[.86, .1, .86]} /><Paint color={color} /></mesh>
    <Legs kind={kind} color={color} moving={moving} tapered={features?.taperedLegs} />
    {features?.stretchers && <Stretchers kind={kind} color={color} />}
    {features?.cushion && <mesh name="sc-chair-cushion" position={[0, .845, .025]} castShadow receiveShadow><boxGeometry args={[.75, .07, .73]} /><Paint color={features.cushionColor ?? accent} /></mesh>}
    <group name="sc-chair-back">
      {[-1, 1].map(side => <mesh key={side} name={`sc-chair-back-post-${side}`} position={[side * .32, 1.19, -.31]} castShadow><boxGeometry args={[.1, .98, .1]} /><Paint color={color} /></mesh>)}
      <mesh name="sc-chair-back-rail" position={[0, 1.59, -.31]} castShadow><boxGeometry args={[.75, .22, .12]} /><Paint color={color} /></mesh>
      {[-.17, 0, .17].map(x => <mesh key={x} name={`sc-chair-back-slat-${x}`} position={[x, 1.14, -.31]} castShadow><boxGeometry args={[.06, .7, .075]} /><Paint color={color} /></mesh>)}
    </group>
    {eyes && <ObjectFace y={1.63} z={-.242} width={.12} size={.52} />}
    {arms && <ObjectArms color={accent} width={.46} y={.87} size={.65} />}
  </group>
}
