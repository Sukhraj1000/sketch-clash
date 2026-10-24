import type { IslandAgent, IslandProject } from './island'

export type ProjectBenefit = {
  label: string
  description: string
  status: 'active' | 'planned' | 'redundant' | 'unavailable'
  resource: string | null
  amount: number
  eligibleActions: string[]
  crew: string[]
}

const BASE_BENEFITS = {
  garden: { resource: 'water', actions: ['water'] },
  workshop: { resource: 'materials', actions: ['forage', 'carry', 'explore', 'tend'] },
  beacon: { resource: 'ideas', actions: ['plan', 'measure', 'signal'] },
  boardwalk: { resource: 'energy', actions: ['charge'] },
} as const
const built = (project: IslandProject) => project.kind === 'assembly'
  ? project.level >= project.max_level && project.max_level > 0 : project.level > 0
const buildOrder = (project: IslandProject) => `${project.completed_at ?? '9999'}:${project.id}`
const actionNames: Record<string, string> = { forage: 'gathering', carry: 'carrying', explore: 'exploring', tend: 'tending', water: 'water delivery', measure: 'measuring', plan: 'planning', signal: 'observing', charge: 'energy delivery' }

/** Describes saved building effects, never credits stock or invents observed output. */
export function projectBenefit(project: IslandProject, projects: IslandProject[] = [project], agents?: IslandAgent[]): ProjectBenefit {
  const base = project.kind === 'assembly' ? null : BASE_BENEFITS[project.kind]
  const resource = base?.resource ?? project.benefit?.resource ?? null
  const actions: string[] = base ? [...base.actions] : [...(project.benefit?.eligible_actions ?? [])]
  const amount = base ? Math.max(0, Math.floor(project.level)) : 1
  const ready = built(project)
  const capable = agents?.filter(agent => agent.allowed_actions.some(action => actions.includes(action)))
  const crew = capable?.map(agent => agent.display_name) ?? []
  const shared = { resource, amount: ready ? amount : 0, eligibleActions: actions, crew }
  if (!resource || !actions.length) return { ...shared, amount: 0, status: 'unavailable', label: 'No saved effect', description: project.reward || 'No operational benefit is recorded for this structure.' }
  if (!ready) return { ...shared, status: 'planned', label: `Unlocks +${base ? 1 : amount} ${resource}`, description: `Construction is not complete. Its delivery bonus has not been unlocked.` }
  // Historical duplicate structures remain visible, but a capped bonus is shown once.
  const prior = project.kind === 'assembly' ? projects.filter(other => other.id !== project.id && other.kind === 'assembly' && built(other)
    && other.benefit?.resource === resource && buildOrder(other) < buildOrder(project)) : []
  const covered = new Set(prior.flatMap(other => other.benefit?.eligible_actions ?? []))
  const uniqueActions = actions.filter(action => !covered.has(action))
  if (!uniqueActions.length) return { ...shared, amount: 0, status: 'redundant', label: 'Shared bonus · no extra yield', description: 'Another completed structure already provides this effect. The assembly bonus is capped at +1 per eligible task; these buildings do not stack.' }
  const uniqueCrew = agents?.filter(agent => agent.allowed_actions.some(action => uniqueActions.includes(action))).map(agent => agent.display_name)
  if (uniqueCrew && !uniqueCrew.length) return { ...shared, crew: [], status: 'unavailable', label: `+${amount} ${resource} · needs a role`, description: `Built and ready, but nobody in this crew can perform ${uniqueActions.map(action => actionNames[action] ?? action).join(' or ')} yet. It does not create ${resource} by itself.` }
  return { ...shared, crew: uniqueCrew ?? [], status: 'active', label: `+${amount} ${resource} / delivery`, description: `${uniqueCrew?.length ? uniqueCrew.join(', ') : 'Eligible residents'} can use this for ${uniqueActions.map(action => actionNames[action] ?? action).join(' and ')}. The bonus applies to completed tasks when storage has room.${project.kind === 'assembly' ? ' Assembly bonuses are capped at +1 per eligible task.' : ''}` }
}
