import { api } from './api'

export type AgentEvent = {
  id: string; world_id: string; sequence: number; kind: string; created_at: string
  island_id: string | null; actor_id: string | null; actor_name: string | null; session_id: string | null
  message: string; data: Record<string, unknown>; trace_id: string | null; span_id: string | null; committed: boolean
}
export type EventBatch = { events: AgentEvent[]; cursor: number; persistence: string; transport: string; stream_error: string | null; resync_required: boolean; server_time: string }
export type AgentSpan = { trace_id: string; span_id: string; parent_span_id: string | null; name: string; created_at: string; duration_ms: number; status: string; attributes: Record<string, unknown>; links?: {trace_id:string;span_id:string}[] }
export type TraceDetail = { trace_id: string; spans: AgentSpan[]; note: string }
export type ObservatoryMetrics = { window_minutes: number; totals: {count: number; errors: number; mean_duration_ms: number; input_tokens: number; output_tokens: number; total_tokens?: number}; event_counts: Record<string, number>; exported_spans: number; dropped_spans: number; export_failures: number; event_counts_sampled: boolean }
export type CouncilSession = { id: string; island_id?: string; colony_id?: string; status: string; created_at: string; last_event_at?: string; event_count?: number }
export type RequestPaceMode = 'slow' | 'steady' | 'fast'
export type RequestPacing = {
  mode: RequestPaceMode
  options: { mode: RequestPaceMode; label: string; requests_per_minute: number; min_dispatch_interval_seconds: number }[]
  effective_requests_per_minute: number; paused: boolean; persistence: string
  hard_limit_requests_per_minute: number; updated_at: string | null; revision: number
}
export type ActionReceipt = {
  id: string; action: string; at: string; actor_id: string | null; actor_name: string | null; island_id: string
  resource_delta: Record<string, number>; resource_cost: Record<string, number> | null
  progress_delta: number; project_id: string | null; decision_origin: string | null
  decision_id: string | null; provenance_status: string
  provenance: {status: string; attribution: 'model' | 'executor' | 'unattributed'; reason: string}
  resources_before?: Record<string, number>; resources_after?: Record<string, number>
  resources_before_reservation?: Record<string, number>; resources_after_reservation?: Record<string, number>
  capability_evidence?: unknown; capability_basis?: unknown; source_snapshot?: unknown; effect_note?: string; source?: unknown
  project_before?: unknown; project_after?: unknown
}
export type EventEvidence = {
  event_id: string | null; status: 'verified' | 'missing' | 'not_applicable' | 'historical'; reason: string
  receipts: ActionReceipt[]; board_message?: Record<string, unknown> | null; decision?: Record<string, unknown> | null
}
export type ActorContributions = {
  id: string; name: string; actions: number; productive_actions: number; no_gain_actions: number; resource_gains: Record<string, number>; resource_costs: Record<string, number>
  project_work: number; model_actions: number; executor_actions: number; unattributed_actions: number
  last_receipt_at: string | null; costs_complete: boolean; historical_actions: number
  last_receipt_id: string | null
}
export type IslandContributions = {
  id: string; actions: number; productive_actions: number; no_gain_actions: number; resource_gains: Record<string, number>; resource_costs: Record<string, number>
  project_work: number; actors: ActorContributions[]; costs_complete: boolean; historical_actions: number
}
export type Contributions = {
  window_minutes: number; from: string; to: string; receipt_count: number; receipt_sample_limit: number; sampled: boolean
  islands: IslandContributions[]
}
export const observatory = {
  pacing: (signal?: AbortSignal) => api<RequestPacing>('/observatory/pacing', {signal}),
  setPacing: (mode: RequestPaceMode) => api<RequestPacing>('/observatory/pacing', {method: 'POST', body: JSON.stringify({mode})}),
  evidence: (id: string, signal?: AbortSignal) => api<EventEvidence>(`/observatory/events/${encodeURIComponent(id)}/evidence`, {signal}),
  receiptEvidence: (id: string, signal?: AbortSignal) => api<EventEvidence>(`/observatory/receipts/${encodeURIComponent(id)}/evidence`, {signal}),
  contributions: (signal?: AbortSignal) => api<Contributions>('/observatory/contributions?window=60', {signal}),
  events: (signal?: AbortSignal) => api<EventBatch>('/observatory/events?limit=300', {signal}),
  sessionEvents: (id: string, signal?: AbortSignal) => api<EventBatch>(`/observatory/events?session_id=${encodeURIComponent(id)}&limit=500`, {signal}),
  metrics: (island: string, signal?: AbortSignal) => api<ObservatoryMetrics>(`/observatory/metrics?window=60${island === 'all' ? '' : `&island=${island}`}`, {signal}),
  sessions: (signal?: AbortSignal) => api<{sessions: CouncilSession[]}>('/observatory/sessions', {signal}),
  trace: (id: string, signal?: AbortSignal) => api<TraceDetail>(`/observatory/traces/${encodeURIComponent(id)}`, {signal}),
}
export function eventCategory(event: AgentEvent) {
  if (/model|gemini|provider/.test(event.kind)) return 'model'
  if (/experiment|research|learning|finding|memory|blueprint|capabilit|resident.arrived/.test(event.kind)) return 'learning'
  if (/council|board|message|decision/.test(event.kind)) return 'discussion'
  return 'work'
}
export function eventLabel(kind: string) { return kind.replace(/[._]/g, ' ').replace(/^\w/, s => s.toUpperCase()) }
export function mergeEvents(current: AgentEvent[], incoming: AgentEvent[]) {
  const unique = new Map(current.map(event => [event.id, event]))
  incoming.forEach(event => unique.set(event.id, event))
  return [...unique.values()].sort((a, b) => a.sequence - b.sequence).slice(-600)
}
