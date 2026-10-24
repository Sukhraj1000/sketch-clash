import { objectSilhouette } from './objectIdentity.ts'
import { computeTaskPose } from '../lib/island.ts'
import type { IslandTask } from '../lib/island.ts'

type Visual = { visual_spec: { template_id: string; scale: number; proportions: { width: number; height: number } }; object_type?: string; canonical_type_id?: string }
type Point = { x: number; z: number }
const bound = (value: number, min: number, max: number) => Math.max(min, Math.min(max, Number.isFinite(value) ? value : 1))

/** Saved proportions describe coarse templates. Applying them again to an exact
 * object mesh stretches its screen, handle, eyes and limbs. Keep its relative
 * size, but size known rigid objects uniformly. No saved appearance is changed. */
export function characterDisplayScale(character: Visual, multiplier = 1): [number, number, number] {
  const spec = character.visual_spec
  const scale = bound(spec.scale, .7, 1.4) * multiplier
  const width = bound(spec.proportions.width, .7, 1.4)
  const height = bound(spec.proportions.height, .7, 1.4)
  if (spec.template_id !== 'generic' || objectSilhouette(spec.template_id, character.object_type, character.canonical_type_id)) {
    const uniform = scale * Math.sqrt(width * height)
    return [uniform, uniform, uniform]
  }
  return [scale * width, scale * height, scale * width]
}

/** Small deterministic presentation slots separate residents who share one
 * abstract work/rest coordinate. Every endpoint uses the same resident slot,
 * so a new task never teleports the body. These are not collision physics. */
export function residentDisplaySlots(ids: readonly string[]): Map<string, Point> {
  const sorted = [...new Set(ids)].sort()
  const columns = sorted.length <= 4 ? Math.max(1, sorted.length) : Math.ceil(Math.sqrt(sorted.length * 1.5))
  const rows = Math.ceil(sorted.length / columns)
  const spacing = Math.min(1.12, 3.36 / Math.max(1, columns - 1), 2.4 / Math.max(1, rows - 1))
  return new Map(sorted.map((id, index) => {
    const countInRow = Math.min(columns, sorted.length - Math.floor(index / columns) * columns)
    const lateral = (index % columns - (countInRow - 1) / 2) * spacing
    const depth = (Math.floor(index / columns) - (rows - 1) / 2) * spacing
    return [id, { x: lateral * .823 + depth * .568, z: -lateral * .568 + depth * .823 }]
  }))
}

export function displayIslandPoint(point: Point, slot: Point): Point {
  const x = point.x + slot.x, z = point.z + slot.z
  const radius = Math.hypot(x, z)
  return radius > 5.25 ? { x: x * 5.25 / radius, z: z * 5.25 / radius } : { x, z }
}

export function residentDisplayPose(task: IslandTask | null | undefined, position: Point, time: number, slot: Point) {
  const displayTask = task ? { ...task, from: displayIslandPoint(task.from, slot), to: displayIslandPoint(task.to, slot) } : task
  return computeTaskPose(displayTask, displayIslandPoint(position, slot), time)
}
