/** Server-owned island state. Rendering interpolates tasks but never advances the simulation. */
export type IslandPoint = { x: number; z: number }
export type IslandTaskKind = 'forage' | 'carry' | 'water' | 'plan' | 'measure' | 'charge' | 'signal' | 'tend' | 'build' | 'rest' | 'explore'
export type IslandTask = {
  id: string
  kind: IslandTaskKind
  title: string
  started_at: string
  ends_at: string
  duration_seconds: number
  from: IslandPoint
  to: IslandPoint
  resource?: string | null
  project_id?: string | null
  gain: Partial<Record<'materials' | 'water' | 'ideas' | 'energy', number>>
  progress_gain: number
  scheduling_reason?: string
  requested_action?: string | null
  requested_decision_id?: string | null
  action_switched?: boolean
  decision_origin?: string
  decision_id?: string | null
  council_id?: string | null
}
export type IslandProject = {
  id: string
  kind: 'garden' | 'workshop' | 'beacon' | 'boardwalk' | 'assembly'
  name: string
  position: IslandPoint
  progress: number
  required_progress: number
  status: 'planned' | 'building' | 'complete'
  description: string
  level: number
  max_level: number
  completed_at?: string | null
  cost_per_action: Partial<Record<'materials' | 'water' | 'ideas' | 'energy', number>>
  reward: string
  blueprint_id?: string
  assembly?: {
    family: 'hold' | 'contain' | 'support' | 'reflect'
    parts: IslandAssemblyPart[]
    context: Record<string, number>
  }
  benefit?: { kind: 'task_yield_bonus'; resource: string; eligible_actions: string[]; amount: number }
}

export type IslandAssemblyPart = {
  kind: 'beam' | 'panel' | 'vessel' | 'connector'
  resident_id: string
  position: { x: number; y: number; z: number }
  rotation: 0 | 90
  geometry: { width: number; height: number; depth: number; length: number }
  material_assumption: string
}
export type IslandMemory = { id: string; at: string; text: string; kind: string }
export type IslandAgent = {
  id: string
  character_id: string
  display_name: string
  object_type: string
  persona: { name: string; role: string; temperament: string; motto: string; goal: string; preferred_action: string; lesson: string; basis_event_ids: string[] }
  capabilities: string[]
  allowed_actions: string[]
  xp: number
  level: number
  assignment: string
  available_assignments: { id: string; label: string }[]
  task: IslandTask | null
  position: IslandPoint
  memory: IslandMemory[]
  completed_actions: number
  persona_provenance: Record<string, unknown>
}
export type IslandResources = Record<'materials' | 'water' | 'ideas' | 'energy', number>
export type IslandEvent = {
  id: string; at: string; kind: string; character_id?: string; title: string; description: string
  resource_delta: Partial<IslandResources>; project_id?: string; progress_delta?: number
  receipt_version?: string; action_id?: string; actor_id?: string; actor_name?: string
  decision_origin?: string; decision_id?: string | null; decision_run_id?: string | null; decision_evidence?: string
  reserved_cost?: Partial<IslandResources>; execution_origin?: string
  council_id?: string | null
  scheduling_reason?: string; requested_action?: string | null; requested_decision_id?: string | null; action_switched?: boolean
}
export type IslandSimulation = {
  enabled: boolean
  world_id: string
  persistence: 'mongodb' | 'development_memory'
  server_time: string
  revision: number
  paused: boolean
  paused_at: string | null
  last_tick_at: string | null
  active_project_id: string | null
  growth_level: number
  resources: IslandResources
  projects: IslandProject[]
  agents: IslandAgent[]
  events: IslandEvent[]
  limits: { max_active_agents: number; offline_catchup_seconds: number; resource_capacity?: number }
  catch_up: { simulated_seconds: number; discarded_seconds: number }
  expeditions: number
  discoveries: { id: string; at: string; title: string; character_id: string }[]
}

const bounded = (value: number, min: number, max: number) => Math.max(min, Math.min(max, Number.isFinite(value) ? value : min))
const smooth = (value: number) => value * value * (3 - 2 * value)

/** A recipe reveals whole rigid parts as actual work lands; it never stretches them. */
export function assemblyPartPresentation(part: IslandAssemblyPart, index: number, count: number, progress: number) {
  const geometry = part.geometry ?? { width: .6, height: .4, depth: .4, length: .6 }
  return {
    width: bounded(geometry.width, .04, 3), height: bounded(geometry.height, .04, 3),
    depth: bounded(geometry.depth, .04, 3), length: bounded(geometry.length, .04, 3),
    solid: bounded(progress, 0, 1) >= (index + 1) / Math.max(1, count),
    position: { x: bounded(part.position?.x ?? 0, -3, 3), y: bounded(part.position?.y ?? 0, 0, 3), z: bounded(part.position?.z ?? 0, -3, 3) },
  }
}

/** Positions are bounded even if a stale or malformed snapshot reaches the renderer. */
export function safeIslandPoint(point: IslandPoint): IslandPoint {
  const x = bounded(point.x, -5.5, 5.5)
  const z = bounded(point.z, -5.5, 5.5)
  const radius = Math.hypot(x, z)
  return radius > 5.5 ? { x: x * 5.5 / radius, z: z * 5.5 / radius } : { x, z }
}

export function computeTaskPose(task: IslandTask | null | undefined, position: IslandPoint, timeMs: number) {
  if (!task) return { ...safeIslandPoint(position), progress: 0, travelling: false, working: false, heading: 0 }
  const from = safeIslandPoint(task.from)
  const to = safeIslandPoint(task.to)
  const started = Date.parse(task.started_at)
  const ended = Date.parse(task.ends_at)
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended <= started || !Number.isFinite(timeMs)) {
    return { ...from, progress: 0, travelling: false, working: false, heading: 0 }
  }
  const progress = bounded((timeMs - started) / (ended - started), 0, 1)
  const travel = smooth(Math.min(1, progress / .45))
  const distance = Math.hypot(to.x - from.x, to.z - from.z)
  return {
    x: from.x + (to.x - from.x) * travel,
    z: from.z + (to.z - from.z) * travel,
    progress,
    travelling: progress > 0 && progress < .45 && distance > .05,
    working: progress >= .45 && progress < 1 && task.kind !== 'rest',
    heading: distance > .05 ? Math.atan2(to.x - from.x, to.z - from.z) : 0,
  }
}
