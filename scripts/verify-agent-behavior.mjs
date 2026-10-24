import assert from 'node:assert/strict'
import { agentBehavior, crewBlockers, messageReceiptLink } from '../src/lib/agentBehavior.ts'
import { cavityPresentation, historicalEvidence } from '../src/lib/learningPresentation.ts'

const agent = { id: 'agent-a', character_id: 'object-a', allowed_actions: ['build', 'water', 'rest'], task: { kind: 'rest', title: 'Wait for useful work' } }
const receipt = (id, at, patch = {}) => ({ id, at, actor_id: agent.id, character_id: agent.character_id, kind: 'rest', receipt_version: 'island-action-v2', action_id: id, resource_delta: {}, progress_delta: 0, ...patch })
const message = (id, at, patch = {}) => ({ id, created_at: at, actor_id: agent.id, character_id: agent.character_id, origin: 'model', receipt_ids: [], text: 'A public proposal', ...patch })
const colony = {
  island: { enabled: true, paused: false, agents: [agent], resources: { materials: 8, energy: 0, water: 1, ideas: 3 }, events: [], projects: [] },
  board: [], planning: { candidates: [] },
}
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value) }; return value }
const input = freeze({ ...colony, board: [
  message('new', '2026-10-24T15:00:00Z'), message('old', '2026-10-24T14:00:00Z'),
  message('wrong-actor', '2026-10-24T16:00:00Z', { actor_id: 'other-agent' }),
  message('executor', '2026-10-24T17:00:00Z', { origin: 'executor' }),
], island: { ...colony.island, events: [
  receipt('build', '2026-10-24T14:00:00Z', { kind: 'build', progress_delta: 3 }),
  receipt('latest', '2026-10-24T15:00:00Z'),
  receipt('narration', '2026-10-24T18:00:00Z', { receipt_version: null, action_id: null, resource_delta: { materials: 100 } }),
  receipt('wrong-actor', '2026-10-24T19:00:00Z', { actor_id: 'other-agent', progress_delta: 10 }),
] } })
const review = agentBehavior(input, agent)
assert.equal(review.message.id, 'new', 'Public model message selected by time and actor; executor reports cannot masquerade as speech')
assert.equal(review.receipt.id, 'latest', 'Unreceipted narration and another actor must not be attributed to this agent')
assert.equal(review.productive.id, 'build')
assert.equal(review.taskState, 'Waiting / resting')
assert.match(review.outcome, /not a failed action/)
assert.equal(review.linkage, 'none', 'Nearby timestamps never establish causality')
assert.equal(review.allowed, true)
assert.equal(agentBehavior({ ...colony, island: { ...colony.island, paused: true } }, agent).taskState, 'Island paused')
assert.equal(agentBehavior(colony, { ...agent, task: { kind: 'charge' } }).allowed, false)
assert.equal(agentBehavior(colony, { ...agent, task: null }).allowed, null)
assert.match(agentBehavior(colony, agent).outcome, /No action receipt/)
assert.match(agentBehavior({ ...colony, island: { ...colony.island, events: [receipt('water', '2026-10-24T14:00:00Z', { kind: 'water', resource_delta: { water: 4 } })] } }, agent).outcome, /\+4 water/)
assert.equal(messageReceiptLink(message('m', '', { receipt_ids: ['r'] }), receipt('r', '')), 'receipt')
assert.equal(messageReceiptLink(message('m', '', { run_id: 'run' }), receipt('r', '', { decision_run_id: 'run', decision_origin: 'model' })), 'decision')
assert.equal(messageReceiptLink(message('m', '', { run_id: 'run' }), receipt('r', '', { decision_run_id: 'run', decision_origin: 'deterministic' })), 'none')
assert.equal(messageReceiptLink(message('m', '', { session_id: 'council' }), receipt('r', '', { council_id: 'council' })), 'council')
assert.equal(messageReceiptLink(message('m', ''), receipt('r', '')), 'none', 'Missing identifiers do not match one another')
const candidate = (id, resources, patch = {}) => ({ project_id: id, name: id, required_resources: resources, incoming_resources: {}, gatherable_resources: ['materials', 'water'], missing_capabilities: [], feasible: true, ...patch })
const blockers = crewBlockers(freeze({ ...colony, island: { ...colony.island, projects: [{ id: 'finished', level: 3, max_level: 3 }] }, planning: { candidates: [
  candidate('finished', { water: 20 }), candidate('complete-flag', { water: 20 }, { complete: true }),
  candidate('beacon', { energy: 6 }, { feasible: false, missing_capabilities: ['energy'] }),
  candidate('garden', { water: 5 }, { incoming_resources: { water: 2 } }),
  candidate('unknown', { ideas: 4 }), candidate('funded', { materials: 4 }),
] } }))
assert.equal(blockers.length, 4, 'Completed upgrade costs cannot be presented as current shortages')
assert.deepEqual(blockers.find(row => row.id === 'beacon').missing, [{ resource: 'energy', amount: 6, kind: 'capability' }])
assert.deepEqual(blockers.find(row => row.id === 'garden').missing, [{ resource: 'water', amount: 2, kind: 'supply' }])
assert.equal(blockers.find(row => row.id === 'unknown').missing[0].kind, 'unknown')
assert.deepEqual(blockers.find(row => row.id === 'funded').missing, [])
for (const value of [null, undefined]) {
  const display = cavityPresentation({ id: 'd', simulation_properties: { apparent_cavity: value } })
  assert.match(display.label, /unknown/i)
  assert.doesNotMatch(display.label, /Solid/)
}
const authored = cavityPresentation({ id: 'd', simulation_properties: { apparent_cavity: null, cavity_model: { status: 'declared_simulation_cavity', authority: 'declared_game_capability', detail: 'An existing capability permits this simulated vessel.' } } })
assert.match(authored.label, /Visual cavity unknown/)
assert.match(authored.authority, /declared game capability/)
assert.match(cavityPresentation({ id: 'd', simulation_properties: { apparent_cavity: true, cavity_model: { status: 'conflicting_evidence' } } }).label, /Conflicting/, 'Evidence conflict takes precedence over an old boolean')
assert.equal(historicalEvidence({ id: 'finding', evidence_status: 'superseded_properties' }), true)
assert.equal(historicalEvidence({ id: 'finding', evidence_status: 'current' }), false)
console.log('Agent behavior checks passed: actor identity, public speech, receipt-only outcomes, explicit causal references, honest waiting, supported actions and resource/capability shortages. No model calls or state writes.')
