import { Shape } from 'three'

export type WorldMapPoint = { x: number; z: number }
export type WorldMapVertex = [number, number, number]

/** One map in two materials. None of these presentation helpers changes a task. */
export const WORLD_MAP_SURFACE_SCALE = .95
export const WORLD_STATIONS = {
  materials: { x: -3.25, z: 1.2 }, water: { x: -.25, z: -2.9 },
  ideas: { x: .15, z: .7 }, energy: { x: 3.65, z: .55 },
} as const

// The saved destination is the service position in front of the fixture.
export const WORLD_STATION_BACKSETS = { materials: .38, water: .6, ideas: .65, energy: .67 } as const

export const WORLD_TREES = [
  { x: -3.7, z: .4, size: 1.05, color: '#4B9D47' },
  { x: -4.35, z: 1.15, size: .8, color: '#4A9854' },
  { x: -3.7, z: 1.65, size: .64, color: '#4B9D47' },
  { x: -1.4, z: -4.2, size: .8, color: '#4B9D47' },
  { x: -.7, z: -4.65, size: .64, color: '#478F57' },
] as const
export const WORLD_WAYFINDER = { x: -2.7, z: 3.3, rotation: -.5 } as const

const projectPoints: WorldMapPoint[] = [{ x: -2.1, z: -1.7 }, { x: 2.1, z: -1.5 }, { x: 0, z: 2.5 }, { x: 3.3, z: 1.6 }]
export const WORLD_PATHS: WorldMapVertex[][] = [...Object.values(WORLD_STATIONS), ...projectPoints].map(({ x, z }, index) => [
  [0, .02, 0], [x * .5 + (index % 2 ? -.2 : .2), .02, z * .5], [x, .02, z],
])

const contour = Array.from({ length: 40 }, (_, index) => {
  const angle = index / 40 * Math.PI * 2
  const radius = 5.45 + Math.sin(angle * 3 + .4) * .3 + Math.cos(angle * 5) * .19
  return { x: Math.cos(angle) * radius, z: Math.sin(angle) * radius }
})
const shape = new Shape()
contour.forEach(({ x, z }, index) => index ? shape.lineTo(x, z) : shape.moveTo(x, z))
shape.closePath()
export const worldGroundShape = () => shape

/** World-space boundary after the shared horizontal-plane rotation. */
export const worldGroundContour = (scale = WORLD_MAP_SURFACE_SCALE): WorldMapPoint[] => contour.map(({ x, z }) => ({ x: x * scale, z: -z * scale }))

const seedValue = (seed: number, offset = 0) => Math.abs(Math.sin(seed * .01713 + offset * 13.123) * 43758.5453) % 1
export const worldRimDecor = (seed: number) => Array.from({ length: 12 }, (_, index) => {
  const angle = index / 12 * Math.PI * 2 + .2
  const radius = 5.15 + seedValue(seed, index) * .15
  return { x: Math.cos(angle) * radius, z: Math.sin(angle) * radius, size: .13 + seedValue(seed, index + 8) * .2 }
})
export const worldGroundDetails = (seed: number) => Array.from({ length: 18 }, (_, index) => {
  const angle = index * 2.399
  const radius = 3.7 + seedValue(seed, index + 60) * 1.1
  return { x: Math.cos(angle) * radius, z: Math.sin(angle) * radius, angle }
})

/** Concrete joints stop at the same coastline rather than implying a larger map. */
export function worldFloorSeams(): WorldMapVertex[][] {
  const points = worldGroundContour(.94)
  const lines: WorldMapVertex[][] = []
  for (const axis of ['x', 'z'] as const) for (const coordinate of [-4, -2, 0, 2, 4]) {
    const other = axis === 'x' ? 'z' : 'x'
    const intersections: number[] = []
    points.forEach((point, index) => {
      const next = points[(index + 1) % points.length]
      if ((point[axis] <= coordinate && next[axis] > coordinate) || (next[axis] <= coordinate && point[axis] > coordinate)) {
        const progress = (coordinate - point[axis]) / (next[axis] - point[axis])
        intersections.push(point[other] + progress * (next[other] - point[other]))
      }
    })
    intersections.sort((a, b) => a - b)
    for (let index = 0; index + 1 < intersections.length; index += 2) {
      const [from, to] = [intersections[index], intersections[index + 1]]
      lines.push(axis === 'x' ? [[coordinate, .003, from], [coordinate, .003, to]] : [[from, .003, coordinate], [to, .003, coordinate]])
    }
  }
  return lines
}
