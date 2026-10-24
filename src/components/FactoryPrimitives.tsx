import { Shape } from 'three'

export const FACTORY = {
  ink: '#242A2D', floor: '#696F70', seam: '#555C5D', paper: '#BBC0BC',
  metal: '#87979D', yellow: '#C7A64D', teal: '#3E817A', blue: '#527C8D',
} as const

type Surface = 'paint' | 'steel' | 'rubber' | 'concrete' | 'glass'
const SURFACES = {
  paint: { roughness: .42, metalness: .28 },
  steel: { roughness: .3, metalness: .82 },
  rubber: { roughness: .92, metalness: .02 },
  concrete: { roughness: .94, metalness: 0 },
  glass: { roughness: .12, metalness: .35 },
} as const
export function FactoryPaint({ color, glow = false, material = 'paint' }: { color: string; glow?: boolean; material?: Surface }) {
  return <meshStandardMaterial color={color} {...SURFACES[material]} emissive={glow ? color : '#000000'} emissiveIntensity={glow ? .28 : 0} />
}

// Cache CPU-only outlines/parameters. Real meshes still own their GPU geometry,
// and identical box dimensions do not rebuild it on every world snapshot.
const outlines = new Map<string, [Shape, { depth: number; bevelEnabled: boolean; bevelSegments: number; steps: number; bevelSize: number; bevelThickness: number; curveSegments: number }]>()
function beveledBox(size: [number, number, number]) {
  const key = size.join(':')
  const previous = outlines.get(key)
  if (previous) return previous
  const [width, height, depth] = size
  const radius = Math.min(.018, Math.min(...size) * .15)
  const x = width / 2 - radius, y = height / 2 - radius
  const shape = new Shape().moveTo(-x, -y).lineTo(x, -y).lineTo(x, y).lineTo(-x, y).closePath()
  const args: [Shape, { depth: number; bevelEnabled: boolean; bevelSegments: number; steps: number; bevelSize: number; bevelThickness: number; curveSegments: number }] = [shape, { depth: depth - radius * 2, bevelEnabled: true, bevelSegments: 2, steps: 1, bevelSize: radius, bevelThickness: radius, curveSegments: 1 }]
  outlines.set(key, args)
  return args
}

export function FactoryBox({ position = [0, 0, 0], size, color, rotation = [0, 0, 0], shadow = true, material = 'paint' }: { position?: [number, number, number]; size: [number, number, number]; color: string; rotation?: [number, number, number]; shadow?: boolean; material?: Surface }) {
  const radius = Math.min(.018, Math.min(...size) * .15)
  // Flat markings remain simple planes/boxes; machinery edges catch real light.
  const bevel = shadow && Math.min(...size) > .025
  return <group position={position} rotation={rotation}><mesh position={[0, 0, bevel ? -size[2] / 2 + radius : 0]} castShadow={shadow} receiveShadow>
    {bevel ? <extrudeGeometry args={beveledBox(size)} /> : <boxGeometry args={size} />}
    <FactoryPaint color={color} material={material} />
  </mesh></group>
}

export function FloorMark({ width = 1.1, depth = .8, color = FACTORY.yellow }: { width?: number; depth?: number; color?: string }) {
  return <group name="factory-floor-mark">
    {[-1, 1].flatMap(side => [
      <FactoryBox key={`x-${side}`} position={[side * width / 2, .018, 0]} size={[.025, .012, depth]} color={color} shadow={false} />,
      <FactoryBox key={`z-${side}`} position={[0, .018, side * depth / 2]} size={[width, .012, .025]} color={color} shadow={false} />,
    ])}
  </group>
}
