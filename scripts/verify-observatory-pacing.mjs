import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { transformWithOxc } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Render the actual pacing panels and their local imports. Effects never run in
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
  const pacing = { mode: 'slow', scope: 'island', effective_requests_per_minute: 1, hard_limit_requests_per_minute: 4, paused: false, options: [{ mode: 'slow', label: 'Slow', requests_per_minute: 1, min_dispatch_interval_seconds: 60 }] }
  const pace = renderToStaticMarkup(createElement(IslandPacingControls, { pacing, paceSaving: false, paceError: '', reasoningPaused: false, changePace() { throw new Error('SSR must not update pacing') } }))
  assert.match(pace, /ISLAND AI REQUEST PACE/)
  assert.match(pace, /Island ceiling: 1 request per minute/)
  assert.match(pace, /Camera recognition runs normally and does not wait for this pace/)
  assert.doesNotMatch(pace, /across all workers|Admission ceiling/)
  const providerQueue = { active: 3, waiting: 4, scopes: { island: { active: 1, waiting: 3 }, interactive: { active: 2, waiting: 1 } }, interactive_limits: { concurrency: 2, min_dispatch_interval_seconds: 0, requests_per_minute: null, requests_per_day: null }, local_limits: { scope: 'island', requests_per_minute: 4, min_dispatch_interval_seconds: 15, background_min_dispatch_interval_seconds: 60, requests_per_day: 200, concurrency: 1, max_pending: 8 }, local_usage: { requests_last_minute: 2, requests_last_24_hours: 35, requests_remaining_day: 165 }, wait_reason: 'local_background_spacing' }
  const guard = renderToStaticMarkup(createElement(GeminiSafeguards, { providerQueue, reasoningPaused: false }))
  assert.match(guard, /ISLAND REQUEST LIMIT<\/dt><dd>4/)
  assert.match(guard, /selected pace: at least 60s apart/)
  assert.doesNotMatch(guard, /SHARED GEMINI|SHARED QUEUE/)
  assert.match(guard, /1 active · 3 waiting · 8 waiting slots/)
  assert.match(guard, /2 active · 1 waiting/)
  assert.match(guard, /Island thinking pace/)
  assert.match(guard, /apply only to island agents/)
  const paused = renderToStaticMarkup(createElement(IslandPacingControls, { pacing, paceSaving: false, paceError: '', reasoningPaused: true, changePace() {} }))
  assert.match(paused, /Gemini remains paused/)
  assert.doesNotMatch(paused, /Island ceiling/)
  const { CaptureProgressPanel } = await import(await sourceModule(new URL('../src/components/CaptureStudio.tsx', import.meta.url)))
  const camera = renderToStaticMarkup(createElement(CaptureProgressPanel, { normalizing: false, unavailable: false, seconds: 20, progress: { stage: 'queued', message: 'Waiting for Gemini', queue: { dispatch_wait_seconds: 0, min_dispatch_interval_seconds: 0 } } }))
  assert.match(camera, /Camera checks run independently of the island pace/)
  assert.doesNotMatch(camera, /Slow|60 seconds|15 seconds|priority|safety spacing/)
  assert.match(guard, /normal requests with no artificial pacing or minute\/day cap/)
  const cooling = renderToStaticMarkup(createElement(CaptureProgressPanel, { normalizing: false, unavailable: false, seconds: 20, progress: { stage: 'queued', message: 'Waiting for Gemini', queue: { wait_reason: 'provider_cooldown', dispatch_wait_seconds: 8, min_dispatch_interval_seconds: 0 } } }))
  assert.match(cooling, /Gemini is cooling down after a provider error/)
  assert.match(cooling, /not a completion estimate/)
  assert.doesNotMatch(cooling, /priority|safety spacing|island pace/)
  const busy = renderToStaticMarkup(createElement(CaptureProgressPanel, { normalizing: false, unavailable: false, seconds: 20, progress: { stage: 'queued', message: 'Waiting for Gemini', queue: { wait_reason: 'local_concurrency', min_dispatch_interval_seconds: 0 } } }))
  assert.match(busy, /Other normal Gemini requests are running/)
  assert.doesNotMatch(busy, /island discussions/)
  assert.equal(requests, 0)
  console.log('Pacing SSR checks passed: island-only speed and budget controls, independent normal camera requests, real cooldowns and paused state without API calls.')
} finally {
  globalThis.fetch = originalFetch
}
