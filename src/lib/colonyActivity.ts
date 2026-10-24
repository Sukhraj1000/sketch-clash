import type { Colony, ColonyPlanner } from './colonies'

type Activity = { label: string; detail: string; tone: 'active' | 'waiting' | 'paused' | 'unavailable' }
const shoreName = (id: string) => id === 'winners' ? 'Winner Island' : 'Loser Island'
const activeStatuses = new Set(['queued', 'queue_wait', 'running', 'dispatching', 'response_received', 'applying', 'retry_wait'])

/** Current saved controls and scheduler ownership, never inferred from a quiet event window. */
export function colonyActivity(colony: Colony | undefined, planner: ColonyPlanner | undefined, aiPaused = false, now = Date.now()): Activity {
  if (!colony) return { label: 'State unavailable', detail: 'Current island state has not loaded.', tone: 'unavailable' }
  if (!colony.island.enabled) return { label: 'Island not started', detail: 'Start the islands to enable local work and discussions.', tone: 'paused' }
  if (colony.island.paused) return { label: 'Island paused', detail: 'Local work and new council turns are paused. Resume this island to continue.', tone: 'paused' }
  if (!colony.island.agents.length) return { label: 'Waiting for residents', detail: 'Objects join this crew after a battle.', tone: 'waiting' }
  if (aiPaused || planner?.paused || planner?.provider_queue?.paused) return { label: 'Gemini paused', detail: 'Local work can continue. New Gemini discussion requests are paused.', tone: 'paused' }
  if (!planner) return { label: 'Council state unavailable', detail: 'The island is running; its current discussion status has not loaded.', tone: 'unavailable' }
  if (!planner.configured) return { label: 'Gemini not configured', detail: 'Local work can continue, but no Gemini provider is configured.', tone: 'paused' }
  if (!planner.enabled) return { label: 'Councils switched off', detail: 'Local work can continue. Enable agent councils for new discussions.', tone: 'paused' }
  if (planner.auto_blocked) return { label: 'Councils blocked', detail: planner.error || 'The saved planner state blocks new automatic councils.', tone: 'paused' }
  if (!colony.island.agents.some(a => a.assignment_origin !== 'player' || a.assignment === 'auto')) return { label: 'Crew manually assigned', detail: 'Return a resident to automatic work to include them in councils.', tone: 'waiting' }
  const run = planner.active_run && activeStatuses.has(planner.active_run.status) ? planner.active_run : undefined
  const session = planner.sessions?.find(s => s.id === planner.active_session_id)
  const owner = session?.colony_id ?? run?.colony_id
  const maxTurns = session?.max_turns ?? planner.limits?.max_session_turns
  const turn = run?.turn_index != null ? run.turn_index + 1 : session ? session.completed_turns + 1 : undefined
  const progress = turn && maxTurns ? ` · turn ${Math.min(turn, maxTurns)} of ${maxTurns}` : ''
  if (owner === colony.id) {
    if (run?.status === 'queue_wait' || run?.status === 'queued' || run?.status === 'retry_wait') return { label: 'Gemini request queued', detail: `${run.agent_name || 'A resident'} is waiting for provider admission${progress}. Request spacing and safeguards still apply.`, tone: 'waiting' }
    return { label: 'Council in progress', detail: `${run?.agent_name || 'This crew'}${run?.status === 'applying' || run?.status === 'response_received' ? ' is validating a response' : ' has the current council turn'}${progress}. Only saved replies appear on the board.`, tone: 'active' }
  }
  const until = planner.validation_backoff?.[colony.id]?.until
  if (until && until * 1000 > now) return { label: 'Council retry scheduled', detail: `This crew is cooling down after a rejected turn. Retry eligibility in about ${Math.ceil((until * 1000 - now) / 60000)} minutes; local work continues.`, tone: 'waiting' }
  if (owner && owner !== colony.id) return { label: `Waiting for ${shoreName(owner)}`, detail: `The shared council is with ${shoreName(owner)}${progress}. Local work continues while it waits for a later council.`, tone: 'waiting' }
  if (planner.active_session_id) return { label: 'Shared council in progress', detail: 'Council ownership is not loaded yet. This island remains running.', tone: 'waiting' }
  if (planner.provider_queue?.admission_ledger_error) return { label: 'Request budget unavailable', detail: 'New Gemini dispatch is blocked until saved budget storage recovers. Local work continues.', tone: 'waiting' }
  if (planner.provider_queue?.local_usage?.requests_remaining_day === 0 || (planner.max_requests_per_day && planner.requests_today >= planner.max_requests_per_day)) return { label: 'Local request allowance used', detail: 'New Gemini requests must wait for the application budget to become available. Local work continues.', tone: 'waiting' }
  return { label: 'Island running', detail: 'Eligible for an automatic council. Local workers carry out saved tasks between discussions.', tone: 'active' }
}

export function emptyActivityWindow(replay: boolean) {
  return replay ? 'No event for this crew in the selected replay so far.' : 'No event for this crew in the loaded recent window. Earlier saved activity may exist.'
}
