/** Prevent superseded async work (even transports that ignore abort) from publishing. */
export function createLatestRequest() {
  let generation = 0
  let controller: AbortController | null = null
  const cancel = () => { generation++; controller?.abort(); controller = null }
  return {
    cancel,
    async run<T>(load: (signal: AbortSignal) => Promise<T>): Promise<{ value: T } | { error: unknown } | null> {
      cancel()
      const current = generation
      controller = new AbortController()
      const signal = controller.signal
      try {
        const value = await load(signal)
        return current === generation && !signal.aborted ? { value } : null
      } catch (error) {
        return current === generation && !signal.aborted ? { error } : null
      }
    },
  }
}

export function comparisonsPermitLabels(loaded: boolean, kind: string, pairs: { review?: unknown }[]) {
  // A baseline has no blind alternative. A candidate with zero pairs has not passed blind review.
  return loaded && (kind === 'baseline' || pairs.length > 0 && pairs.every(pair => !!pair.review))
}
