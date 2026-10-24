export const FACTORY = {
  ink: '#252B36', floor: '#515D65', seam: '#647178', paper: '#FFF4D9',
  metal: '#A9BABD', yellow: '#FFD15D', teal: '#73D5C5', blue: '#7EBED6',
} as const

export function FactoryPaint({ color, glow = false }: { color: string; glow?: boolean }) {
  return <meshStandardMaterial color={color} roughness={.78} flatShading emissive={glow ? color : '#000000'} emissiveIntensity={glow ? .16 : 0} />
}

export function FactoryBox({ position = [0, 0, 0], size, color, rotation = [0, 0, 0], shadow = true }: { position?: [number, number, number]; size: [number, number, number]; color: string; rotation?: [number, number, number]; shadow?: boolean }) {
  return <mesh position={position} rotation={rotation} castShadow={shadow} receiveShadow><boxGeometry args={size} /><FactoryPaint color={color} /></mesh>
}

export function FloorMark({ width = 1.1, depth = .8, color = FACTORY.yellow }: { width?: number; depth?: number; color?: string }) {
  return <group name="factory-floor-mark">
    {[-1, 1].flatMap(side => [
      <FactoryBox key={`x-${side}`} position={[side * width / 2, .018, 0]} size={[.025, .012, depth]} color={color} shadow={false} />,
      <FactoryBox key={`z-${side}`} position={[0, .018, side * depth / 2]} size={[width, .012, .025]} color={color} shadow={false} />,
    ])}
  </group>
}
