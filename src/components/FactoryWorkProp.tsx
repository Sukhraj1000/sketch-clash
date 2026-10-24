import type { IslandTaskKind } from '../lib/island'
import { FACTORY, FactoryBox as Box, FactoryPaint as Paint } from './FactoryPrimitives'

/** Mounted only while the shared executor's saved task is actually active. */
export default function FactoryWorkProp({ kind }: { kind?: IslandTaskKind }) {
  if (kind === 'carry' || kind === 'forage') return <group name="factory-work-tool" position={[0, .46, .38]} userData={{ restX: 0, restY: .46, restZ: .38 }}>
    <Box size={[.36, .045, .27]} color={FACTORY.metal} material="steel" />
    {[-1, 1].map(side => <Box key={side} position={[side * .17, .09, 0]} size={[.022, .18, .27]} color={FACTORY.metal} material="steel" />)}
    <Box position={[0, .09, -.126]} size={[.34, .18, .018]} color={FACTORY.metal} material="steel" />
  </group>
  if (kind === 'plan') return <group name="factory-work-tool" position={[0, .6, .32]} rotation={[-.45, 0, 0]} userData={{ restX: 0, restY: .6, restZ: .32, restTilt: -.45 }}>
    <Box size={[.28, .18, .022]} color={FACTORY.ink} material="rubber" />
    <Box position={[0, 0, .015]} size={[.24, .14, .006]} color="#55787D" shadow={false} material="glass" />
  </group>
  if (kind === 'build' || kind === 'measure') return <group name="factory-work-tool" position={[.24, .49, .3]} rotation={[Math.PI / 2, 0, 0]} userData={{ restX: .24, restY: .49, restZ: .3, restTilt: Math.PI / 2 }}>
    <mesh name="factory-tool-bit" castShadow><cylinderGeometry args={[.035, .04, .14, 16]} /><Paint color={FACTORY.metal} material="steel" /></mesh>
    <mesh position={[0, -.12, 0]}><cylinderGeometry args={[.008, .008, .12, 12]} /><Paint color={FACTORY.ink} material="steel" /></mesh>
    {kind === 'measure' && <Box position={[0, -.08, -.025]} size={[.3, .025, .025]} color={FACTORY.metal} material="steel" />}
  </group>
  if (kind === 'water' || kind === 'tend') return <group name="factory-work-tool" position={[.2, .46, .38]} userData={{ restX: .2, restY: .46, restZ: .38 }}>
    <mesh castShadow><cylinderGeometry args={[.028, .028, .17, 12]} /><Paint color={FACTORY.metal} material="steel" /></mesh>
    <Box position={[0, -.08, .06]} size={[.055, .045, .13]} color={FACTORY.ink} material="rubber" />
  </group>
  if (kind === 'charge' || kind === 'signal') return <group name="factory-work-tool" position={[.2, .48, .31]} userData={{ restX: .2, restY: .48, restZ: .31 }}>
    <Box size={[.065, .11, .08]} color={FACTORY.ink} material="rubber" />
    <Box position={[0, .017, .045]} size={[.042, .05, .01]} color={FACTORY.teal} material="glass" />
  </group>
  // Hardware only: no particles imply inventory or energy that hasn't been committed.
  return null
}
