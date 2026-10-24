import assert from 'node:assert/strict'
import { colonyActivity, emptyActivityWindow } from '../src/lib/colonyActivity.ts'

const winner = {id: 'winners', island: {enabled: true, paused: false, agents: [{assignment: 'auto', assignment_origin: 'deterministic'}]}}
const planner = {enabled: true, configured: true, paused: false, limits: {max_session_turns: 6}}
const duringLoser = {...planner, active_session_id: 's1', active_run: {colony_id: 'losers', session_id: 's1', status: 'queue_wait', turn_index: 1, agent_name: 'Cup'}, sessions: [{id: 's1', colony_id: 'losers', status: 'running', completed_turns: 1, max_turns: 6}]}
const paused = {...winner, island: {...winner.island, paused: true}}
assert.equal(colonyActivity(paused, duringLoser).label, 'Island paused')
assert.equal(colonyActivity(paused, {...duringLoser, paused: true}).label, 'Island paused', 'Local pause must not be obscured by the shared provider state')
assert.equal(colonyActivity(winner, duringLoser).label, 'Waiting for Loser Island')
assert.match(colonyActivity(winner, duringLoser).detail, /turn 2 of 6/)
assert.equal(colonyActivity({...winner, id: 'losers'}, duringLoser).label, 'Gemini request queued')
assert.equal(colonyActivity({...winner, id: 'losers'}, {...duringLoser, active_run: {...duringLoser.active_run, status: 'dispatching'}}).label, 'Council in progress')
assert.equal(colonyActivity(winner, {...planner, active_session_id: 'unknown'}).label, 'Shared council in progress', 'Missing ownership must not be attributed to the selected island')
assert.equal(colonyActivity(winner, {...planner, active_run: {...duringLoser.active_run, status: 'completed'}}).label, 'Island running', 'A finished run must not keep the other island waiting')
assert.equal(colonyActivity(winner, {...planner, provider_queue: {paused: true}}).label, 'Gemini paused')
assert.equal(colonyActivity(winner, planner, true).label, 'Gemini paused')
assert.equal(colonyActivity(winner, {...planner, enabled: false}).label, 'Councils switched off')
assert.equal(colonyActivity(winner, {...planner, configured: false}).label, 'Gemini not configured')
assert.equal(colonyActivity(winner, undefined).label, 'Council state unavailable')
assert.equal(colonyActivity(undefined, planner).label, 'State unavailable')
assert.equal(colonyActivity({...winner, island: {...winner.island, agents: [{assignment: 'build', assignment_origin: 'player'}]}}, planner).label, 'Crew manually assigned')
assert.equal(colonyActivity({...winner, island: {...winner.island, agents: [{assignment: 'build', assignment_origin: 'model'}]}}, planner).label, 'Island running', 'A model assignment remains eligible')
const cooling = {...planner, validation_backoff: {winners: {until: 120}}}
assert.equal(colonyActivity(winner, cooling, false, 60_000).label, 'Council retry scheduled')
assert.equal(colonyActivity(winner, cooling, false, 120_000).label, 'Island running')
assert.equal(colonyActivity(winner, {...planner, validation_backoff: {losers: {until: 120}}}, false, 60_000).label, 'Island running')
assert.match(emptyActivityWindow(false), /loaded recent window/)
assert.match(emptyActivityWindow(true), /selected replay so far/)
assert.doesNotMatch(emptyActivityWindow(false), /recorded.*yet|never|first/)
const ownManualRetry = {...duringLoser, active_run: {...duringLoser.active_run, colony_id: 'winners'}, sessions: [], validation_backoff: {winners: {until: 120}}}
assert.equal(colonyActivity(winner, ownManualRetry, false, 60_000).label, 'Gemini request queued', 'An active manual retry takes precedence over future automatic cooldown')
const capQueue = {wait_reason: 'local_daily_cap', dispatch_wait_seconds: 2 * 3600 + 30 * 60, local_limits: {requests_per_day: 200}, local_usage: {requests_remaining_day: 0}}
assert.equal(colonyActivity(winner, {...planner, provider_queue: capQueue}).label, 'Daily AI limit reached')
assert.match(colonyActivity(winner, {...planner, provider_queue: capQueue}, false, 0).detail, /all 200 .*in about 2 h 30 min/)
assert.equal(colonyActivity(winner, {...duringLoser, provider_queue: capQueue}).label, 'Daily AI limit reached', 'A council stalled on the daily cap must not read as waiting for the other island')
assert.match(colonyActivity(winner, {...planner, provider_queue: {local_usage: {requests_remaining_day: 0}}}).detail, /oldest request is 24 hours old/)
assert.equal(colonyActivity(winner, {...planner, max_requests_per_day: 5, requests_today: 5}).label, 'Local request allowance used')
console.log('Colony activity regressions passed: pause, ownership, queue admission, cooldowns, manual assignments and bounded history.')
