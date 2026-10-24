/** Human wait for queue and budget countdowns ("about 16 h 28 min"), never raw seconds. */
export function formatWait(seconds: number) {
  if (seconds < 60) return 'under a minute'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `about ${minutes} min`
  const hours = Math.floor(minutes / 60), rest = minutes % 60
  return `about ${hours} h${rest ? ` ${rest} min` : ''}`
}

/** Local clock time when a wait ends, e.g. "16:21". */
export function resumeClock(seconds: number, now = Date.now()) {
  return new Date(now + seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
