import type { EventBatch } from './observatory'

type FeedClock = { now: () => number; every: (callback: () => void, milliseconds: number) => () => void }
type FeedOptions = {
  getCursor: () => number
  loadAfter: (cursor: number, signal: AbortSignal) => Promise<EventBatch>
  /** Merge events and advance the shared cursor with Math.max: SSE may have advanced it meanwhile. */
  onBatch: (batch: EventBatch) => void
  onConnection: (state: 'connected' | 'polling') => void
  onError: (error: unknown) => void
  /** Reopen the stream once per silent period; polling continues if reconnecting fails. */
  onStale?: () => void
  signal?: AbortSignal
  intervalMs?: number
  staleAfterMs?: number
  clock?: FeedClock
}

/** Reconcile durable events independently of SSE, without inventing stream liveness. */
export function startEventReconciliation(options: FeedOptions) {
  const clock = options.clock ?? {
    now: () => Date.now(),
    every: (callback: () => void, milliseconds: number) => {
      const timer = globalThis.setInterval(callback, milliseconds)
      return () => globalThis.clearInterval(timer)
    },
  }
  const controller = new AbortController()
  let lastLive = clock.now()
  let stopped = false
  let busy = false
  let stale = false
  let clearInterval = () => {}
  const setConnection = (next: 'connected' | 'polling') => {
    if (!stopped) options.onConnection(next)
  }
  const checkFreshness = () => {
    if (stopped || stale || clock.now() - lastLive < (options.staleAfterMs ?? 30_000)) return
    stale = true
    setConnection('polling')
    try { options.onStale?.() } catch (error) { options.onError(error) }
  }
  const reconcile = async () => {
    if (stopped || busy) return
    busy = true
    try {
      const batch = await options.loadAfter(options.getCursor(), controller.signal)
      if (!stopped && !controller.signal.aborted) options.onBatch(batch)
    } catch (error) {
      if (!stopped && !controller.signal.aborted) options.onError(error)
    } finally {
      busy = false
    }
  }
  const stop = () => {
    if (stopped) return
    stopped = true
    controller.abort()
    clearInterval()
    options.signal?.removeEventListener('abort', stop)
  }
  // Call on a parsed SSE agent/status message, including duplicates. An open
  // socket or successful HTTP reconciliation alone is not a live heartbeat.
  const markLive = () => {
    if (stopped) return
    lastLive = clock.now()
    stale = false
    // The stream adapter may have reported reconnecting since the last frame.
    // Publish each heartbeat so that an externally changed status can recover.
    setConnection('connected')
  }
  if (options.signal?.aborted) stop()
  else {
    options.signal?.addEventListener('abort', stop, { once: true })
    clearInterval = clock.every(() => { checkFreshness(); void reconcile() }, options.intervalMs ?? 15_000)
  }
  return { markLive, reconcile, stop }
}
