import type { WorldCharacter } from '../components/WorldView'
import type { IslandAgent, IslandSimulation } from './island'

export type ColonyId = 'winners' | 'losers'
export type ColonyCharacter = WorldCharacter & {
  market_price?: null; estimated_value_gbp?: number | null; valuation_status?: 'unknown' | 'user_estimate'
  valuation_provenance?: { kind: 'user_estimate'; currency: 'GBP'; recorded_at: string } | null
}
export type ColonyBoardEntry = {
  id: string; created_at: string; kind: 'request' | 'offer' | 'report' | 'proposal' | 'support' | 'objection' | 'decision' | 'question' | 'reflection'; text: string
  actor_id: string; character_id: string; actor_name: string
  resource?: string; quantity?: number; remaining?: number
  status: 'open' | 'claimed' | 'fulfilled' | 'recorded' | 'expired'; origin: 'deterministic' | 'model' | 'player' | 'executor'
  request_id?: string; claimed_by?: string; receipt_ids: string[]
  project_id?: string; council_id?: string; proposal_id?: string
  session_id?: string; reply_to_id?: string; model?: string; run_id?: string; turn_index?: number
  interpretation?: string | null
  request_reused?: boolean; effect?: string
}
export type ColonyAgent = IslandAgent & {
  assignment_origin?: 'player' | 'model' | 'deterministic' | 'executor'
  intent?: string; contribution?: Record<string, number>
  contributions?: { resources: Record<string, number>; work: number; cooperative_units: number }
}
export type ColonyCandidate = {
  project_id: string; name: string; target_level: number; feasible: boolean; remaining_work: number; remaining_actions: number
  required_resources: Record<string, number>; available_resources: Record<string, number>; gatherable_resources: string[]
  missing_capabilities: string[]; reason: string
}
export type ColonyOpinion = {
  agent_id: string; character_id: string; actor_name: string; project_id: string | null
  kind: 'support' | 'objection'; reason: string; contributes: string[]; origin: 'deterministic' | 'model'; message_id?: string
}
export type ColonyCouncil = {
  id: string; at: string; chosen_project_id: string | null; previous_project_id: string | null; reason: string
  origin: 'deterministic' | 'model'; participants: ColonyOpinion[]; candidates: ColonyCandidate[]; model_message_ids: string[]
}
export type ColonyMetrics = {
  resident_count?: number; active_agents?: number; completed_actions?: number; building_levels?: number
  project_levels?: number; fulfilled_requests?: number; open_requests?: number; cooperative_deliveries?: number; capability_gaps?: string[]
  estimated_total_gbp?: number | null; estimated_mean_gbp?: number | null; valued_residents?: number; unknown_value_residents?: number
  total_building_levels?: number; contribution_score?: number; active_seconds?: number; actions_per_resident?: number
  dependency_contributions?: number; resource_contributions?: Record<string, number>; score?: number
  [key: string]: unknown
}
export type Colony = {
  id: ColonyId; name: string; characters: ColonyCharacter[]
  island: Omit<IslandSimulation, 'agents'> & { agents: ColonyAgent[] }; board: ColonyBoardEntry[]; metrics: ColonyMetrics
  world?: { id: string; name: string; layout_seed: number }
  planning?: {
    mode: 'crew' | 'manual'; status: 'building' | 'gathering' | 'blocked' | 'complete' | 'waiting'
    selected_project_id: string | null; target_level?: number; reason: string; last_council_at: string | null; next_council_at: string | null
    cooldown_seconds: number; candidates: ColonyCandidate[]
  }
  council?: ColonyCouncil[]
  learning?: ColonyLearning
}
export type ColonyRun = {
  id: string; colony_id: ColonyId; agent_id?: string; agent_name?: string; status: string
  created_at: string; completed_at?: string; decision?: Record<string, unknown> | null
  usage?: Record<string, unknown> | null; receipt?: Record<string, unknown> | null; error?: string
  session_id?: string; turn_index?: number
}
export type GeminiQueueStatus = {
  paused?: boolean; active?: number; waiting?: number; completed?: number; throttled?: number
  local_limits?: {
    scope?: 'island'
    requests_per_minute?: number; requests_per_day?: number; max_pending?: number
    min_dispatch_interval_seconds?: number; background_min_dispatch_interval_seconds?: number; concurrency?: number
  }
  local_usage?: {
    scope?: 'island'; all_requests_last_24_hours?: number
    requests_last_minute?: number; requests_last_24_hours?: number
    requests_remaining_minute?: number; requests_remaining_day?: number
  }
  interactive_limits?: { concurrency?: number; min_dispatch_interval_seconds?: number; requests_per_minute?: null; requests_per_day?: null }
  scopes?: Partial<Record<'island' | 'interactive' | 'evaluation', { active?: number; waiting?: number }>>
  wait_reason?: string | null; dispatch_wait_seconds?: number
  counter_scope?: 'database_rolling_window' | 'process_lifetime'
  admission_ledger?: { historical_usage_unknown?: boolean; rolling_window_complete?: boolean; cutover_at_epoch?: number }
  admission_ledger_error?: string | null
  last_local_error?: { message?: string; category?: string } | null
}
export type ColonyPlanner = {
  enabled: boolean; configured: boolean; model?: string; requests_today: number; max_requests_per_day: number | null
  paused?: boolean; pause_reason?: string | null
  remaining_requests?: number; last_status?: string; next_turn_at?: string; active_run?: ColonyRun | null
  runs?: ColonyRun[]; error?: string; active_session_id?: string | null
  provider_queue?: GeminiQueueStatus
  sessions?: { id: string; colony_id: ColonyId; status: string; completed_turns: number; max_turns: number }[]
  limits?: { max_session_turns?: number }
  auto_blocked?: boolean
  validation_backoff?: Partial<Record<ColonyId, { until: number }>>
}
export type ColoniesSnapshot = {
  enabled: boolean; server_time: string; persistence: 'mongodb' | 'development_memory'; colonies: Colony[]
  comparison: Record<string, unknown>; planner?: ColonyPlanner
  placement_policy?: string
}

/** Requests stay on the local backend. No credentials or model calls run in the browser. */
export async function coloniesRequest<T>(path = '', options: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController()
  const cancel = () => controller.abort(signal?.reason)
  if (signal?.aborted) cancel()
  else signal?.addEventListener('abort', cancel, { once: true })
  const timeout = window.setTimeout(() => controller.abort('timeout'), 15000)
  try {
    const response = await fetch(`/api/colonies${path}`, { ...options, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...options.headers } })
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = body?.error?.message ?? body?.detail?.message ?? body?.detail ?? body?.message
      throw new Error(typeof detail === 'string' ? detail : `The islands could not be reached (${response.status}).`)
    }
    return body as T
  } catch (error) {
    if (controller.signal.reason === 'timeout') throw new Error('The request timed out. Refresh to check its saved result before trying again.')
    throw error
  } finally {
    window.clearTimeout(timeout)
    signal?.removeEventListener('abort', cancel)
  }
}

export const colonyMutation = <T,>(path: string, body: Record<string, unknown>, signal?: AbortSignal) => coloniesRequest<T>(path, { method: 'POST', body: JSON.stringify(body) }, signal)
export function numberMetric(metrics: ColonyMetrics, keys: string[], fallback = 0): number {
  for (const key of keys) if (typeof metrics[key] === 'number' && Number.isFinite(metrics[key])) return metrics[key] as number
  return fallback
}

export type LearningRecord = { id: string; [key: string]: any }
export type ColonyLearning = { rule_version: string; capability_fingerprint?: string; last_change?: { new_resident_ids?: string[]; reopened_research_ids?: string[] }; retrieval?: {status: string; detail?: string}; dossiers: LearningRecord[]; findings: LearningRecord[]; experiments: LearningRecord[]; blueprints: LearningRecord[]; research: LearningRecord[] }
