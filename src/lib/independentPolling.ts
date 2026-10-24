/** Each source refreshes independently; a slow response cannot hold up its peers. */
export function startIndependentPoll<T>(load: () => Promise<T>, success: (value: T) => void,
  failure: (error: unknown) => void, signal: AbortSignal, intervalMs = 8000) {
  let busy = false
  let stopped = false
  const refresh = async () => {
    if (busy || stopped || signal.aborted) return
    busy = true
    try { const value = await load(); if (!stopped && !signal.aborted) success(value) }
    catch (error) { if (!stopped && !signal.aborted) failure(error) }
    finally { busy = false }
  }
  void refresh()
  const timer = window.setInterval(() => void refresh(), intervalMs)
  return () => { stopped = true; window.clearInterval(timer) }
}
