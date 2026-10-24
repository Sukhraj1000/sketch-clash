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
export const observatory = {
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
