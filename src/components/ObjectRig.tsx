const INK = '#1E1C29'
const PAPER = '#FFF9EB'
export function ObjectMaterial({ color }: { color: string }) { return <meshStandardMaterial color={color} roughness={.82} flatShading /> }

export function ObjectFace({ y = .93, z = .44, width = .14, size = 1 }: { y?: number; z?: number; width?: number; size?: number }) {
  return <group position={[0, y, z]} scale={size}>
    <group name="sc-eyes">{[-1, 1].map(side => <group key={side} position={[side * width, 0, 0]}><mesh><sphereGeometry args={[.073, 8, 6]} /><meshBasicMaterial color={PAPER} /></mesh><mesh position={[.01, 0, .055]}><sphereGeometry args={[.033, 8, 6]} /><meshBasicMaterial color={INK} /></mesh></group>)}</group>
    <mesh position={[0, -.16, .01]} rotation={[0, 0, Math.PI]}><torusGeometry args={[.075, .018, 4, 10, Math.PI]} /><meshBasicMaterial color={INK} /></mesh>
  </group>
}

export function ObjectFeet({ width = .22, y = .14, size = 1 }: { width?: number; y?: number; size?: number }) {
  return <group>{[-1, 1].map(side => <group key={side} name={side < 0 ? 'sc-foot-left' : 'sc-foot-right'} position={[side * width, y, .02]} userData={{ restY: y }} scale={size}><mesh position={[0, -.035, .09]} scale={[1, .6, 1.5]} castShadow><sphereGeometry args={[.13, 8, 5]} /><ObjectMaterial color={INK} /></mesh></group>)}</group>
}

export function ObjectArms({ color, width = .52, y = .84, size = 1 }: { color: string; width?: number; y?: number; size?: number }) {
  return <group>{[-1, 1].map(side => <group key={side} name={side < 0 ? 'sc-arm-left' : 'sc-arm-right'} position={[side * width, y, 0]} rotation={[0, 0, side * .38]} scale={size}><mesh position={[0, -.18, 0]} castShadow><capsuleGeometry args={[.055, .31, 3, 6]} /><ObjectMaterial color={color} /></mesh><mesh position={[0, -.37, 0]}><sphereGeometry args={[.07, 6, 5]} /><ObjectMaterial color={color} /></mesh></group>)}</group>
}
