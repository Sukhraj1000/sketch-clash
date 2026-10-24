import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { transformWithOxc } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// Render the actual conversation and its local imports. Effects never run in
// SSR, and this verification replaces fetch to forbid accidental API calls.
const originalFetch = globalThis.fetch
let requests = 0
globalThis.fetch = () => { requests++; throw new Error('Conversation rendering must not request an API') }
const modules = new Map()
async function sourceModule(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const { code: transformed } = await transformWithOxc(readFileSync(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })
  let code = transformed.replace(/^\s*import\s+['"][^'"]+\.css['"];?\s*$/gm, '')
  for (const match of [...code.matchAll(/\bfrom\s+(['"])([^'"]+)\1/g)]) {
    const specifier = match[2]
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
  const { LiveConversation, ColonyResearch } = await import(await sourceModule(new URL('../src/components/ColonyResearch.tsx', import.meta.url)))
  const colony = {
    id: 'winners', name: 'Winner Island', characters: [], metrics: {}, board: [],
    island: { enabled: true, paused: false, agents: [{ id: 'pencil', assignment: 'auto', assignment_origin: 'executor' }], events: [], projects: [] },
  }
  const planner = { configured: true, enabled: true, requests_today: 0, max_requests_per_day: null, runs: [] }
  const render = (crew = colony, state = planner, extra = {}) => renderToStaticMarkup(createElement(LiveConversation, { colony: crew, planner: state, canThink: false, ...extra }))
  const emptyText = 'No saved model messages are loaded for this island.'
  const localPause = render({ ...colony, island: { ...colony.island, paused: true } })
  assert.match(localPause, /Island paused\./)
  assert.match(localPause, /Resume this island to continue\./)
  assert.ok(localPause.includes(emptyText))
  assert.doesNotMatch(localPause, /Waiting for the first|Gemini is paused|Gemini paused\./)

  const globalPause = render(colony, { ...planner, paused: true }, { paused: true })
  assert.match(globalPause, /Gemini paused\./)
  assert.match(globalPause, /Local work can continue/)
  assert.doesNotMatch(globalPause, /Waiting for the first council/)

  const otherCouncil = {
    ...planner, active_session_id: 'loser-session',
    active_run: { id: 'turn-3', colony_id: 'losers', status: 'running', agent_name: 'Mug', turn_index: 2 },
    sessions: [{ id: 'loser-session', colony_id: 'losers', status: 'running', completed_turns: 2, max_turns: 6 }],
  }
  const waiting = render(colony, otherCouncil)
  assert.match(waiting, /Waiting for Loser Island\./)
  assert.match(waiting, /The shared council is with Loser Island · turn 3 of 6/)
  assert.doesNotMatch(waiting, /Council in progress\.|This crew has the current council turn/)

  const separateRates = render(colony, { ...planner, provider_queue: { local_limits: { min_dispatch_interval_seconds: 15, background_min_dispatch_interval_seconds: 60 } } })
  assert.match(separateRates, /Island AI requests are spaced at least 60 seconds apart/)
  assert.doesNotMatch(separateRates, /spaced at least 15 seconds apart/, 'The shared camera safeguard must not be shown as the island discussion pace')
  const legacyRate = render(colony, { ...planner, provider_queue: { local_limits: { min_dispatch_interval_seconds: 60 } } })
  assert.match(legacyRate, /Island AI requests are spaced at least 60 seconds apart/)

  const message = { id: 'saved-message', kind: 'reflection', origin: 'model', text: 'Saved thought', interpretation: 'I can support the garden with a stable surface.', session_id: 'saved-session', run_id: 'saved-run', turn_index: 0, actor_name: 'Pencil', status: 'open', created_at: '2026-10-24T12:00:00Z' }
  const saved = render({ ...colony, board: [message], island: { ...colony.island, paused: true } }, { ...planner, paused: true }, { paused: true })
  assert.match(saved, /Island paused\./)
  assert.match(saved, /I can support the garden with a stable surface\./)
  assert.match(saved, /Message: saved-message/)
  assert.doesNotMatch(saved, /No saved model messages are loaded/)
  const knowledge = { rule_version: 'fixture', dossiers: [{ id: 'd', resident_id: 'mug', display_name: 'Mug', revision: 2, simulation_properties: { apparent_cavity: null, cavity_model: { status: 'declared_simulation_cavity', authority: 'declared_game_capability', detail: 'Photograph evidence is still unavailable.' } } }], experiments: [{ id: 'old', family: 'contain', status: 'completed', evidence_status: 'superseded_properties', hypothesis: 'Historical test', result: { success: true, production_validation: { eligible: true } } }], findings: [{ id: 'current', claim: 'A current supported claim', evidence_status: 'current', status: 'supported' }], historical_findings: [{ id: 'history', claim: 'An earlier unsupported claim', evidence_status: 'superseded_properties' }], research: [] }
  const lab = renderToStaticMarkup(createElement(ColonyResearch, { colony: { ...colony, learning: knowledge } }))
  assert.match(lab, /Visual cavity unknown/)
  assert.match(lab, /DECLARED GAME CAPABILITY/)
  assert.match(lab, /HISTORICAL TEST/)
  assert.match(lab, /Earlier findings · preserved history/)
  assert.match(lab, /1 CURRENT FINDINGS/)
  assert.doesNotMatch(lab, /Solid proxy|Tested for the normal island workload|>SUPPORTED</, 'Old test cannot claim current capability or production readiness')
  assert.equal(requests, 0)
  console.log('Conversation SSR checks passed: local/Gemini pauses, other-island ownership, accurate empty history and saved messages preserved without API calls.')
} finally {
  globalThis.fetch = originalFetch
}
