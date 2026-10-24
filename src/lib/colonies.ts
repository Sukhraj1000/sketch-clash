import type { WorldCharacter } from '../components/WorldView'
import type { IslandAgent, IslandSimulation } from './island'

export type ColonyId = 'winners' | 'losers'
export type ColonyCharacter = WorldCharacter & {
  market_price?: null; estimated_value_gbp?: number | null; valuation_status?: 'unknown' | 'user_estimate'
  valuation_provenance?: { kind: 'user_estimate'; currency: 'GBP'; recorded_at: string } | null
}
export type ColonyBoardEntry = {
  id: string; created_at: string; kind: 'request' | 'offer' | 'report'; text: string
  actor_id: string; character_id: string; actor_name: string
  resource?: string; quantity?: number; remaining?: number
  status: 'open' | 'claimed' | 'fulfilled' | 'recorded' | 'expired'; origin: 'deterministic' | 'model' | 'player'
  request_id?: string; claimed_by?: string; receipt_ids: string[]
}
export type ColonyAgent = IslandAgent & { intent?: string; contribution?: Record<string, number> }
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
  island: IslandSimulation & { agents: ColonyAgent[] }; board: ColonyBoardEntry[]; metrics: ColonyMetrics
  world?: { id: string; name: string; layout_seed: number }
}
export type ColonyRun = {
  id: string; colony_id: ColonyId; agent_id?: string; agent_name?: string; status: string
  created_at: string; completed_at?: string; decision?: Record<string, unknown> | null
  usage?: Record<string, unknown> | null; receipt?: Record<string, unknown> | null; error?: string
}
export type ColonyPlanner = {
  enabled: boolean; configured: boolean; model?: string; requests_today: number; max_requests_per_day: number
  remaining_requests?: number; last_status?: string; next_turn_at?: string; active_run?: ColonyRun | null
  runs?: ColonyRun[]; error?: string
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
