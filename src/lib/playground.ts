import type { IslandAgent, IslandPoint, IslandProject, IslandResources, IslandSimulation, IslandTask, IslandTaskKind } from './island'
import type { WorldCharacter } from '../components/WorldView'

/** A deliberately separate, browser-memory game. No live residents, model output or database IDs. */
export type ObjectKind = 'mug' | 'ruler' | 'battery' | 'spoon' | 'book' | 'pitcher'
export type Resource = keyof IslandResources
export type Capability = 'water' | 'measure' | 'charge' | 'salvage'
export type PlaygroundObject = {
  kind: ObjectKind; label: string; role: string; detail: string; color: string
  resource: Resource; yield: number; action: IslandTaskKind; capability: Capability
}
export const OBJECTS: readonly PlaygroundObject[] = [
  { kind: 'mug', label: 'Mug', role: 'Water carrier', detail: 'Holds water from the well. Supplies garden irrigation.', color: '#F58273', resource: 'water', yield: 2, action: 'water', capability: 'water' },
  { kind: 'ruler', label: 'Ruler', role: 'Surveyor', detail: 'Measures joints and plots. Produces usable construction plans.', color: '#FFD166', resource: 'ideas', yield: 2, action: 'measure', capability: 'measure' },
  { kind: 'battery', label: 'Battery', role: 'Energy carrier', detail: 'Charges at the solar pad, then carries energy to a build.', color: '#70BF9A', resource: 'energy', yield: 3, action: 'charge', capability: 'charge' },
  { kind: 'spoon', label: 'Spoon', role: 'Digger', detail: 'Scoops loose material from the salvage pile and digs beds.', color: '#B2C6DD', resource: 'materials', yield: 3, action: 'forage', capability: 'salvage' },
  { kind: 'book', label: 'Book', role: 'Plan keeper', detail: 'An illustrated construction guide. Supplies measured plans.', color: '#AD92CB', resource: 'ideas', yield: 3, action: 'plan', capability: 'measure' },
  { kind: 'pitcher', label: 'Pitcher', role: 'Water carrier', detail: 'Carries a larger load from the well. Same role as a mug.', color: '#70D3CE', resource: 'water', yield: 3, action: 'water', capability: 'water' },
]
export const objectDefinition = (kind: ObjectKind) => OBJECTS.find(object => object.kind === kind)!
export const RESOURCE_ORDER: Resource[] = ['materials', 'water', 'ideas', 'energy']
export const CAPABILITY_LABELS: Record<Capability, string> = { water: 'water carrier', measure: 'measured plans', charge: 'energy carrier', salvage: 'digger' }
export const MAX_CREW = 6
export const STORAGE_LIMIT = 40
const EPOCH = Date.parse('2026-01-01T00:00:00Z')
const at = (seconds: number) => new Date(EPOCH + seconds * 1000).toISOString()
const secondsAt = (timestamp: string) => (Date.parse(timestamp) - EPOCH) / 1000
const SOURCES: Record<Resource, IslandPoint> = { materials: { x: -3.45, z: .5 }, water: { x: -.25, z: -3.5 }, ideas: { x: .2, z: .1 }, energy: { x: 3.7, z: .55 } }

type Blueprint = { id: IslandProject['kind']; name: string; cost: Partial<IslandResources>; needs: Capability[]; reward: string; value: number; position: IslandPoint; requires?: IslandProject['kind'] }
// Priority is explicit game design, not a learned model policy. Feasibility precedes priority.
export const BLUEPRINTS: readonly Blueprint[] = [
  { id: 'beacon', name: 'Signal beacon', cost: { materials: 12, ideas: 6, energy: 9 }, needs: ['salvage', 'measure', 'charge'], requires: 'workshop', reward: 'A working signal. +12 island value.', value: 12, position: { x: 0, z: 2.8 } },
  { id: 'workshop', name: 'Tiny workshop', cost: { materials: 8, ideas: 4, energy: 3 }, needs: ['salvage', 'measure', 'charge'], reward: 'Better tools: each salvage trip brings 1 extra material.', value: 8, position: { x: 2.1, z: -1.5 } },
  { id: 'garden', name: 'Community garden', cost: { materials: 6, water: 6 }, needs: ['salvage', 'water'], reward: 'A planted, irrigated garden. +6 island value.', value: 6, position: { x: -2.1, z: -1.7 } },
  { id: 'boardwalk', name: 'Little boardwalk', cost: { materials: 6, ideas: 2 }, needs: ['salvage', 'measure'], reward: 'Safer paths: future work trips take 25% less time.', value: 4, position: { x: 0, z: -2.7 } },
]
export type PlaygroundResident = { id: string; kind: ObjectKind; position: IslandPoint; task: IslandTask | null; actions: number; delivered: number; built: number }
export type PlaygroundNote = { id: number; at: number; actor: string; text: string; kind: 'decision' | 'arrival' | 'work' | 'complete' }
export type PlaygroundIsland = {
  id: 'sunrise' | 'driftwood'; name: string; color: string; residents: PlaygroundResident[]
  resources: IslandResources; projects: IslandProject[]; activeProject: string | null
  notes: PlaygroundNote[]; nextNote: number; nextTask: number; arrivals: number
}
export type PlaygroundState = { seconds: number; paused: boolean; islands: PlaygroundIsland[] }

function note(island: PlaygroundIsland, seconds: number, actor: string, text: string, kind: PlaygroundNote['kind']) {
  island.notes.push({ id: island.nextNote++, at: seconds, actor, text, kind })
  island.notes = island.notes.slice(-60)
}
export function projectGaps(island: PlaygroundIsland, projectId: string) {
  const blueprint = BLUEPRINTS.find(project => project.id === projectId)!
  const available = new Set(island.residents.map(resident => objectDefinition(resident.kind).capability))
  const capabilities = blueprint.needs.filter(capability => !available.has(capability))
  const prerequisite = blueprint.requires && !island.projects.some(project => project.id === blueprint.requires && project.status === 'complete') ? blueprint.requires : null
  return { capabilities, prerequisite }
}
export function islandValue(island: PlaygroundIsland) {
  return BLUEPRINTS.reduce((total, blueprint) => total + (island.projects.find(project => project.id === blueprint.id)?.status === 'complete' ? blueprint.value : 0), 0)
}
export function costLabel(cost: Partial<IslandResources>) {
  return RESOURCE_ORDER.filter(resource => cost[resource]).map(resource => `${cost[resource]} ${resource === 'ideas' ? 'plans' : resource}`).join(' · ')
}
export function shortages(island: PlaygroundIsland, project: IslandProject): Partial<IslandResources> {
  if (project.status === 'building' || project.status === 'complete') return {}
  return Object.fromEntries(RESOURCE_ORDER.filter(resource => (project.cost_per_action[resource] ?? 0) > island.resources[resource]).map(resource => [resource, (project.cost_per_action[resource] ?? 0) - island.resources[resource]]))
}
function newResident(islandId: string, kind: ObjectKind, index: number): PlaygroundResident {
  return { id: `practice-${islandId}-${kind}-${index}`, kind, position: { x: -1 + index * .55, z: 1.3 }, task: null, actions: 0, delivered: 0, built: 0 }
}
function makeIsland(id: PlaygroundIsland['id'], name: string, color: string, crew: ObjectKind[]): PlaygroundIsland {
  return {
    id, name, color, residents: crew.map((kind, index) => newResident(id, kind, index)), resources: { materials: 0, water: 0, ideas: 0, energy: 0 }, activeProject: null,
    projects: BLUEPRINTS.map(blueprint => ({ id: blueprint.id, kind: blueprint.id, name: blueprint.name, position: blueprint.position, progress: 0, required_progress: 6, status: 'planned', description: `Requires ${blueprint.needs.map(capability => CAPABILITY_LABELS[capability]).join(', ')}.`, level: 0, max_level: 1, cost_per_action: { ...blueprint.cost }, reward: blueprint.reward })),
    notes: [], nextNote: 1, nextTask: 1, arrivals: crew.length,
  }
}
function chooseProject(island: PlaygroundIsland, seconds: number) {
  const inProgress = island.projects.find(project => project.status === 'building')
  const candidate = inProgress ?? island.projects.find(project => project.status !== 'complete' && !projectGaps(island, project.id).capabilities.length && !projectGaps(island, project.id).prerequisite)
  const previous = island.activeProject
  island.activeProject = candidate?.id ?? null
  if (previous !== island.activeProject) {
    const unavailable = island.projects.find(project => project.status === 'planned' && projectGaps(island, project.id).capabilities.length)
    const reason = unavailable ? `${unavailable.name} needs ${projectGaps(island, unavailable.id).capabilities.map(capability => CAPABILITY_LABELS[capability]).join(' + ')}. ` : ''
    note(island, seconds, 'Plan selector', candidate ? `${reason}Choose ${candidate.name}: this crew has every required role.` : island.projects.every(project => project.status === 'complete') ? 'All four projects are complete. The crew is topping up its shared supplies.' : 'No remaining project fits the crew yet. Gather useful supplies until a missing role arrives.', 'decision')
  }
  return candidate
}
function assign(island: PlaygroundIsland, seconds: number) {
  const project = chooseProject(island, seconds)
  if (project && project.status === 'planned' && !Object.keys(shortages(island, project)).length) {
    for (const resource of RESOURCE_ORDER) island.resources[resource] -= project.cost_per_action[resource] ?? 0
    project.status = 'building'
    note(island, seconds, 'Shared store', `${project.name} is funded: ${costLabel(project.cost_per_action)} reserved once. Construction can start.`, 'decision')
  }
  const required = project ? BLUEPRINTS.find(blueprint => blueprint.id === project.id)!.needs : []
  for (const resident of island.residents) {
    if (resident.task) continue
    const object = objectDefinition(resident.kind)
    const canBuild = project?.status === 'building' && required.includes(object.capability)
    const deficit = project ? shortages(island, project) : {}
    const gatheringForProject = (deficit[object.resource] ?? 0) > 0
    const canGather = island.resources[object.resource] < (gatheringForProject ? STORAGE_LIMIT : 12)
    if (!canBuild && !canGather) continue
    const duration = island.projects.find(item => item.id === 'boardwalk')?.status === 'complete' ? 6 : 8
    const gain = canBuild ? {} : { [object.resource]: object.yield + (object.resource === 'materials' && island.projects.find(item => item.id === 'workshop')?.status === 'complete' ? 1 : 0) }
    resident.task = {
      id: `${island.id}-task-${island.nextTask++}`, kind: object.action,
      title: canBuild ? `Contribute to ${project!.name}` : `${object.role}: +${gain[object.resource]} ${object.resource === 'ideas' ? 'plans' : object.resource}`,
      started_at: at(seconds), ends_at: at(seconds + duration), duration_seconds: duration,
      from: { ...resident.position }, to: { ...(canBuild ? project!.position : SOURCES[object.resource]) },
      resource: canBuild ? null : object.resource, project_id: canBuild ? project!.id : null, gain, progress_gain: canBuild ? 1 : 0,
    }
  }
}
export function createPlayground(): PlaygroundState {
  const state: PlaygroundState = { seconds: 0, paused: false, islands: [makeIsland('sunrise', 'Sunrise crew', '#F48471', ['spoon', 'ruler']), makeIsland('driftwood', 'Driftwood crew', '#63B4AB', ['mug', 'spoon'])] }
  for (const island of state.islands) {
    note(island, 0, 'Practice setup', 'Example crew. A well, salvage pile and solar charging pad supply the game. No battle results are used.', 'arrival')
    assign(island, 0)
  }
  return state
}
export function addPlaygroundObject(state: PlaygroundState, islandId: string, kind: ObjectKind): PlaygroundState {
  const original = state.islands.find(island => island.id === islandId)
  if (!original || original.residents.length >= MAX_CREW || original.residents.some(resident => resident.kind === kind) || !OBJECTS.some(object => object.kind === kind)) return state
  const next = structuredClone(state)
  const island = next.islands.find(item => item.id === islandId)!
  const object = objectDefinition(kind)
  const before = island.projects.filter(project => !projectGaps(island, project.id).capabilities.length).map(project => project.id)
  island.residents.push(newResident(islandId, kind, island.arrivals++))
  const unlocked = island.projects.filter(project => !before.includes(project.id) && !projectGaps(island, project.id).capabilities.length).map(project => project.name)
  note(island, state.seconds, object.label, `Arrived with ${CAPABILITY_LABELS[object.capability]}. ${unlocked.length ? `Crew requirements now met for ${unlocked.join(' and ')}.` : 'Adds capacity to an existing role.'}${island.projects.some(project => project.status === 'building') ? ' Finish the funded build, then reconsider.' : ''}`, 'arrival')
  // Re-evaluate immediately, including while paused; no work or spending occurs until resumed.
  chooseProject(island, next.seconds)
  if (!next.paused) assign(island, next.seconds)
  return next
}
export function advancePlayground(state: PlaygroundState, elapsedSeconds: number): PlaygroundState {
  if (state.paused || !Number.isFinite(elapsedSeconds) || elapsedSeconds <= 0) return state
  const next = structuredClone(state)
  const end = next.seconds + Math.min(60, elapsedSeconds)
  // Complete in timestamp order so a long tick cannot skip deductions or grant early work.
  while (next.seconds < end) {
    const due = next.islands.flatMap(island => island.residents.flatMap(resident => resident.task ? [secondsAt(resident.task.ends_at)] : [])).filter(time => time > next.seconds)
    next.seconds = Math.min(end, ...due)
    for (const island of next.islands) {
      for (const resident of island.residents) {
        const task = resident.task
        if (!task || secondsAt(task.ends_at) > next.seconds) continue
        resident.position = { ...task.to }; resident.task = null; resident.actions++
        const object = objectDefinition(resident.kind)
        if (task.project_id) {
          const project = island.projects.find(item => item.id === task.project_id)!
          if (project.status === 'building') {
            project.progress = Math.min(project.required_progress, project.progress + task.progress_gain)
            resident.built += task.progress_gain
            note(island, next.seconds, object.label, `${project.name}: ${project.progress}/${project.required_progress} work. Contribution: ${object.role.toLowerCase()}.`, 'work')
            if (project.progress >= project.required_progress) {
              project.status = 'complete'; project.level = 1; project.completed_at = at(next.seconds)
              note(island, next.seconds, 'Crew milestone', `${project.name} complete. ${project.reward}`, 'complete')
            }
          }
        } else {
          for (const resource of RESOURCE_ORDER) {
            const added = Math.min(STORAGE_LIMIT - island.resources[resource], task.gain[resource] ?? 0)
            island.resources[resource] += added; resident.delivered += added
            if (added) note(island, next.seconds, object.label, `Delivered ${added} ${resource === 'ideas' ? 'plans' : resource} to the shared store.`, 'work')
          }
        }
      }
      assign(island, next.seconds)
    }
  }
  return next
}

export function playgroundCharacters(island: PlaygroundIsland): WorldCharacter[] {
  return island.residents.map((resident, index) => {
    const object = objectDefinition(resident.kind)
    return { id: resident.id, world_id: `practice-${island.id}`, canonical_type_id: resident.kind, object_type: resident.kind, display_name: object.label, image_ref: '', archetype: object.role, first_battle_id: '', unlocked_at: at(0), home_position: { ...resident.position, y: 0 }, state: { activity: 'wander', mood: 'helpful' }, distinct_battle_count: 0, visual_spec: { template_id: resident.kind === 'mug' || resident.kind === 'book' ? resident.kind : 'generic', palette: [object.color, '#FFF1B3'], scale: 1.1, proportions: { width: 1, height: 1 }, accessories: ['feet', 'eyes', 'arms'], animation_style: 'calm', schema_version: 'practice-1', appearance_seed: index + 60 } }
  })
}
/** Adapts local game time for the existing renderer; it is never sent to the server. */
export function playgroundScene(state: PlaygroundState, island: PlaygroundIsland, speed: number, wallTime: number): IslandSimulation {
  const rate = speed === 2 || speed === 4 ? speed : 1
  const displayTime = (value: string) => new Date(wallTime + (secondsAt(value) - state.seconds) * 1000 / rate).toISOString()
  const agents: IslandAgent[] = island.residents.map(resident => {
    const object = objectDefinition(resident.kind)
    return { id: resident.id, character_id: resident.id, display_name: object.label, object_type: resident.kind,
      persona: { name: object.label, role: object.role, temperament: 'Practice game role', motto: '', goal: '', preferred_action: object.action, lesson: '', basis_event_ids: [] },
      capabilities: [object.capability], allowed_actions: [object.action], xp: resident.actions, level: 1, assignment: 'practice', available_assignments: [], task: resident.task ? { ...resident.task, started_at: displayTime(resident.task.started_at), ends_at: displayTime(resident.task.ends_at), duration_seconds: resident.task.duration_seconds / rate } : null,
      position: resident.position, memory: [], completed_actions: resident.actions, persona_provenance: { origin: 'practice_game_rules' },
    }
  })
  return { enabled: true, world_id: `practice-${island.id}`, persistence: 'development_memory', server_time: new Date(wallTime).toISOString(), revision: Math.floor(state.seconds * 4), paused: state.paused, paused_at: state.paused ? new Date(wallTime).toISOString() : null, last_tick_at: null, active_project_id: island.activeProject, growth_level: islandValue(island), resources: island.resources, projects: island.projects, agents, events: [], limits: { max_active_agents: MAX_CREW, offline_catchup_seconds: 0 }, catch_up: { simulated_seconds: 0, discarded_seconds: 0 }, expeditions: 0, discoveries: [] }
}
