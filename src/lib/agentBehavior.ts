import type { Colony, ColonyAgent, ColonyBoardEntry } from './colonies'
import type { IslandEvent } from './island'

const numeric = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : 0
const newest = <T,>(rows: T[], date: (row: T) => string) => [...rows].sort((a, b) => (Date.parse(date(b)) || 0) - (Date.parse(date(a)) || 0))[0] ?? null
const owns = (row: { actor_id?: string; character_id?: string }, agent: ColonyAgent) => row.actor_id ? row.actor_id === agent.id : row.character_id === agent.character_id

/** A recent record is not proof of a causal relationship. Require saved IDs. */
export function messageReceiptLink(message: ColonyBoardEntry | null, receipt: IslandEvent | null) {
  if (!message || !receipt) return 'none' as const
  if (message.receipt_ids?.includes(receipt.id)) return 'receipt' as const
  if (message.run_id && receipt.decision_run_id === message.run_id && receipt.decision_origin === 'model') return 'decision' as const
  if (receipt.council_id && [message.council_id, message.session_id].includes(receipt.council_id)) return 'council' as const
  return 'none' as const
}

/** Read only summaries of public state; resting is never treated as a failure. */
export function agentBehavior(colony: Colony, agent: ColonyAgent) {
  const messages = colony.board.filter(row => owns(row, agent) && row.origin === 'model')
  const message = newest(messages, row => row.created_at)
  const receipts = colony.island.events.filter(row => owns(row, agent) && Boolean(row.receipt_version && row.action_id))
  const receipt = newest(receipts, row => row.at)
  const positiveGain = (row: IslandEvent) => numeric(row.progress_delta) > 0 || Object.values(row.resource_delta || {}).some(value => numeric(value) > 0)
  const productive = newest(receipts.filter(positiveGain), row => row.at)
  const task = agent.task
  const taskState = colony.island.paused ? 'Island paused' : !colony.island.enabled ? 'Island not started' : !task ? 'No task recorded' : task.kind === 'rest' ? 'Waiting / resting' : 'Task assigned'
  const allowed = task ? agent.allowed_actions.includes(task.kind) : null
  const outcome = !receipt ? 'No action receipt in the loaded recent history.'
    : positiveGain(receipt) ? [
      ...Object.entries(receipt.resource_delta || {}).filter(([, value]) => numeric(value) > 0).map(([key, value]) => `+${value} ${key}`),
      ...(numeric(receipt.progress_delta) > 0 ? [`${receipt.progress_delta} construction work`] : []),
    ].join(' · ')
      : receipt.kind === 'rest' ? 'Rest recorded; no supplies or work added. Waiting is not a failed action.'
        : 'No stock or construction gain in this receipt. Inspect its evidence before judging usefulness.'
  return { message, receipt, productive, task, taskState, allowed, outcome, linkage: messageReceiptLink(message, receipt) }
}

export function crewBlockers(colony: Colony) {
  const projects = new Map(colony.island.projects.map(project => [project.id, project]))
  return (colony.planning?.candidates || []).filter(candidate => {
    const project = projects.get(candidate.project_id)
    return !candidate.complete && (!project || project.level < project.max_level)
  }).map(candidate => {
    const missing = Object.entries(candidate.required_resources || {}).flatMap(([resource, amount]) => {
      const stored = numeric(colony.island.resources[resource as keyof typeof colony.island.resources])
      const incoming = numeric(candidate.incoming_resources?.[resource])
      const gap = Math.max(0, numeric(amount) - stored - incoming)
      return gap > 0 ? [{ resource, amount: gap, kind: candidate.missing_capabilities.includes(resource) ? 'capability' as const : candidate.gatherable_resources.includes(resource) ? 'supply' as const : 'unknown' as const }] : []
    })
    return { id: candidate.project_id, name: candidate.name, feasible: candidate.feasible, missing, reason: candidate.reason }
  })
}

export const behaviorStatusLabel = {
  work_in_progress: 'Useful work in progress', funded_work: 'Funded work available',
  gathering_work: 'Gather supplies for a useful project', design_available: 'Tested design ready to discuss',
  research_available: 'Useful research available', waiting_for_change: 'Waiting for a meaningful change', no_residents: 'Waiting for residents',
} as const
