import type { IslandTaskKind } from '../lib/island'
import { FACTORY, FactoryBox as Box, FactoryPaint as Paint } from './FactoryPrimitives'

/** Mounted only while the shared executor's saved task is actually active. */
export default function FactoryWorkProp({ kind }: { kind?: IslandTaskKind }) {
  if (kind === 'carry' || kind === 'forage') return <group position={[0, .46, .38]}>
    <Box size={[.36, .045, .27]} color={FACTORY.metal} material="steel" />
    {[-1, 1].map(side => <Box key={side} position={[side * .17, .09, 0]} size={[.022, .18, .27]} color={FACTORY.metal} material="steel" />)}
    <Box position={[0, .09, -.126]} size={[.34, .18, .018]} color={FACTORY.metal} material="steel" />
  </group>
  if (kind === 'plan') return <group position={[0, .6, .32]} rotation={[-.45, 0, 0]}>
    <Box size={[.28, .18, .022]} color={FACTORY.ink} material="rubber" />
    <Box position={[0, 0, .015]} size={[.24, .14, .006]} color="#55787D" shadow={false} material="glass" />
  </group>
  if (kind === 'build' || kind === 'measure') return <group position={[.24, .49, .3]} rotation={[Math.PI / 2, 0, 0]}>
    <mesh castShadow><cylinderGeometry args={[.035, .04, .14, 16]} /><Paint color={FACTORY.metal} material="steel" /></mesh>
    <mesh position={[0, -.12, 0]}><cylinderGeometry args={[.008, .008, .12, 12]} /><Paint color={FACTORY.ink} material="steel" /></mesh>
  </group>
  // The permanent permitted module shows watering/charging/signalling hardware;
  // no floating particles imply unrecorded activity or simulated output.
  return null
}
