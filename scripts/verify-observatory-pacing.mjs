import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { transformWithOxc } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Render the actual conversation and its local imports. Effects never run in
// SSR, and this verification replaces fetch to forbid accidental API calls.
const originalFetch = globalThis.fetch
let requests = 0
globalThis.fetch = () => { requests++; throw new Error('Pacing rendering must not request an API') }
const modules = new Map()
async function sourceModule(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const { code: transformed } = await transformWithOxc(readFileSync(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })
  let code = transformed.replace(/^\s*import\s+['"][^'"]+\.css['"];?\s*$/gm, '')
  for (const match of [...code.matchAll(/\bfrom\s+(['"])([^'"]+)\1/g)]) {
    const specifier = match[2]
    if (specifier === './FighterReview') { code = code.replace(match[0], 'from '+JSON.stringify('data:text/javascript,export default function UnusedReview(){return null}')); continue }
    let resolved
    if (specifier.startsWith('.')) {
      let dependency = new URL(specifier, url)
      if (!existsSync(dependency)) dependency = ['.ts', '.tsx'].map(extension => new URL(specifier + extension, url)).find(candidate => existsSync(candidate))
      assert.ok(dependency, `Resolve local import ${specifier}`)
      resolved = await sourceModule(dependency)
    } else resolved = import.meta.resolve(specifier)
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  modules.set(url.href, result)
  return result
}
try {
  const { IslandPacingControls, GeminiSafeguards } = await import(await sourceModule(new URL('../src/components/Observatory.tsx', import.meta.url)))
  const pacing = { mode: 'slow', scope: 'background', effective_requests_per_minute: 1, hard_limit_requests_per_minute: 4, paused: false, options: [{ mode: 'slow', label: 'Slow', requests_per_minute: 1, min_dispatch_interval_seconds: 60 }] }
  const pace = renderToStaticMarkup(createElement(IslandPacingControls, { pacing, paceSaving: false, paceError: '', reasoningPaused: false, changePace() { throw new Error('SSR must not update pacing') } }))
  assert.match(pace, /ISLAND AI REQUEST PACE/)
  assert.match(pace, /Background ceiling: 1 request per minute/)
  assert.match(pace, /Camera recognition gets priority and uses the shared safety limits/)
  assert.doesNotMatch(pace, /across all workers|Admission ceiling/)
  const providerQueue = { local_limits: { requests_per_minute: 4, min_dispatch_interval_seconds: 15, background_min_dispatch_interval_seconds: 60, requests_per_day: 200, concurrency: 1, max_pending: 8 }, local_usage: { requests_last_minute: 2, requests_last_24_hours: 35, requests_remaining_day: 165 }, wait_reason: 'local_background_spacing' }
  const guard = renderToStaticMarkup(createElement(GeminiSafeguards, { providerQueue, reasoningPaused: false }))
  assert.match(guard, /SHARED REQUEST LIMIT<\/dt><dd>4/)
  assert.match(guard, /at least 15s apart/)
  assert.doesNotMatch(guard, /at least 60s apart/)
  assert.match(guard, /Island thinking pace/)
  assert.match(guard, /cover camera recognition and island AI/)
  const paused = renderToStaticMarkup(createElement(IslandPacingControls, { pacing, paceSaving: false, paceError: '', reasoningPaused: true, changePace() {} }))
  assert.match(paused, /Gemini remains paused/)
  assert.doesNotMatch(paused, /Background ceiling/)
  const { CaptureProgressPanel } = await import(await sourceModule(new URL('../src/components/CaptureStudio.tsx', import.meta.url)))
  const camera = renderToStaticMarkup(createElement(CaptureProgressPanel, { normalizing: false, unavailable: false, seconds: 20, progress: { stage: 'queued', message: 'Waiting for Gemini', queue: { dispatch_wait_seconds: 8, min_dispatch_interval_seconds: 15 } } }))
  assert.match(camera, /Shared Gemini safety spacing: at least 15 seconds/)
  assert.match(camera, /Camera checks have priority over island discussions/)
  assert.doesNotMatch(camera, /Slow|60 seconds/)
  assert.equal(requests, 0)
  console.log('Pacing SSR checks passed: island-only speed controls, separate shared safety limits, capture priority copy and paused state without API calls.')
} finally {
  globalThis.fetch = originalFetch
}
