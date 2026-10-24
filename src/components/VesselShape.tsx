import { BackSide } from 'three'
import { ObjectArms, ObjectFace, ObjectFeet, ObjectMaterial } from './ObjectRig'
import type { VesselPresentation } from './vesselPresentation'

/** A recognizable procedural vessel, not a reconstruction of the photograph. */
export default function VesselShape({ shape, color, accent, feet, eyes, arms }: { shape: VesselPresentation; color: string; accent: string; feet: boolean; eyes: boolean; arms: boolean }) {
  const base = feet ? .22 : .02
  const top = base + shape.bodyHeight
  const neckTop = top + shape.neckHeight
  const mouthRadius = shape.neckHeight ? .16 : shape.radiusTop
  const handleWidth = .26
  const handleHeight = Math.min(.43, shape.bodyHeight * .37)
  return <group name={`sc-vessel-${shape.kind}`} userData={{ appearanceBasis: shape.basis }}>
    {feet && <ObjectFeet width={Math.min(.23, shape.radiusBottom * .65)} />}
    <group name="sc-vessel-body">
      <mesh position={[0, base + shape.bodyHeight / 2, 0]} castShadow receiveShadow><cylinderGeometry args={[shape.radiusTop, shape.radiusBottom, shape.bodyHeight, 28, 1, true]} /><ObjectMaterial color={color} /></mesh>
      <mesh position={[0, base + .055, 0]} castShadow><cylinderGeometry args={[shape.radiusBottom * .98, shape.radiusBottom, .11, 28]} /><ObjectMaterial color={color} /></mesh>
      {/* Inner wall and the recessed bottom leave an actual opening; no invented coffee/liquid. */}
      <mesh position={[0, base + shape.bodyHeight / 2, 0]}><cylinderGeometry args={[shape.radiusTop - .035, shape.radiusBottom - .035, shape.bodyHeight - .04, 28, 1, true]} /><meshStandardMaterial color={color} roughness={.88} side={BackSide} /></mesh>
    </group>
    {shape.neckHeight > 0 && <group name="sc-vessel-neck">
      <mesh position={[0, top + .11, 0]} castShadow><cylinderGeometry args={[.16, shape.radiusTop, .22, 28, 1, true]} /><ObjectMaterial color={color} /></mesh>
      <mesh position={[0, top + .22 + (shape.neckHeight - .22) / 2, 0]} castShadow><cylinderGeometry args={[.16, .16, shape.neckHeight - .22, 28, 1, true]} /><ObjectMaterial color={color} /></mesh>
    </group>}
    <mesh name="sc-vessel-rim" position={[0, neckTop, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[mouthRadius - .017, .025, 8, 28]} /><ObjectMaterial color={color} /></mesh>
    {shape.lid && <group name="sc-vessel-lid">
      <mesh position={[0, neckTop + .045, 0]} castShadow><cylinderGeometry args={[shape.lidRadius * .98, shape.lidRadius, .10, 28]} /><ObjectMaterial color={accent} /></mesh>
      {shape.spout && <mesh name="sc-vessel-spout" position={[0, neckTop + .12, .08]} castShadow><boxGeometry args={[.16, .07, .24]} /><ObjectMaterial color={accent} /></mesh>}
    </group>}
    {shape.handle && <group name="sc-vessel-handle" position={[shape.radiusTop + .13, base + shape.bodyHeight * .57, 0]}>
      <mesh scale={[1, handleHeight / handleWidth, 1]} castShadow><torusGeometry args={[handleWidth, .065, 8, 28]} /><ObjectMaterial color={color} /></mesh>
    </group>}
    {eyes && <ObjectFace y={base + shape.bodyHeight * .70} z={shape.radiusTop + .015} width={Math.min(.14, shape.radiusTop * .38)} size={.9} />}
    {arms && <ObjectArms color={accent} width={shape.radiusTop + .025} y={base + shape.bodyHeight * .38} size={.9} />}
  </group>
}
