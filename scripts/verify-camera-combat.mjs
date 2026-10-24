import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { transformWithOxc } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { cameraFighter, cameraPair, cameraPlayback, equalDamageBeforeLuck, priceComparisonTitle } from '../src/lib/camera-combat.ts'

const profile = (slot, patch = {}) => ({ id: `capture:${slot}`, name: `Accepted object ${slot + 1}`, object_type: slot ? 'mug' : 'ruler', image_ref: `/api/media/photo-${slot}`, health: 100,
  description: 'Accepted physical properties', stats: { impact: 6, resilience: 5, agility: 4, control: 5 }, traits: ['rigid_hard'], capabilities: ['Rigid surface'], limitations: ['No confirmed water'],
  price: { amount_gbp: null, source: 'unavailable', label: 'No verified price; no premium' }, profile_version: 'capture-1',
  provenance: { kind: 'accepted_capture', label: 'Player-accepted capture', capture_id: `photo-${slot}`, observed_features: ['rigid ceramic body'] }, ...patch })
const pending = slot => ({ battle_id: 'round', player_slot: slot, display_name: 'Later display name', object_type: 'later type', image_ref: '/later-image', archetype: 'Guard', combat_profile: profile(slot, { stats: { impact: 5, resilience: 5, agility: 5, control: 5 } }) })
const receipt = { round: 1, base_damage: 13, stat_adjustment: 1.1, interaction_percent: 8, interaction_damage: 1.128, interaction_rules: [{ id: 'hard-on-brittle', name: 'Brittle surface', percent: 8, reason: 'A rigid bump challenges a brittle surface.' }], price_percent: 0, price_damage: 0, luck: 1, unrounded_damage: 16.228, rounding_adjustment: -.228, damage_before_cap: 16, damage: 16, health_before: 100, health_after: 84 }
const event = { id: 'round-1-0', at: 700, attacker: 0, damage: 16, word: 'BOP!', kind: 'heavy', receipt }
const counter = (patch = {}) => ({ winner_slot: 0, final_health: [8, 0], outcome: 'knockout', changed_winner: false, ...patch })
const combat = { fighters: [profile(0), profile(1)], events: [event], winner_slot: 0, final_health: [8, 0], duration_ms: 6400, outcome: 'knockout', seed: 42, engine_version: 'object-combat-2', profile_version: 'capture-1',
  explanation: { summary: 'Accepted object 1 wins by knockout after paired rounds.', highlights: ['Both started with equal health.', 'The rigid surface challenged brittle material.'], price_note: 'Neither capture has a verified price. Both premiums are zero.' },
  price_policy: { max_bonus_percent: 1 }, counterfactual: { without_price: counter(), without_interactions: counter({ changed_winner: true, winner_slot: 1, final_health: [0, 4] }) } }
const battle = { id: 'round', status: 'completed', persistence: 'development_memory', fighters: [pending(0), pending(1)], events: [event], duration_ms: 6400, winner_slot: 0, engine_version: 'object-combat-2', seed: 42, combat }
const original = JSON.stringify(battle)
const fighters = cameraPair(battle)
assert.equal(fighters[0].name, 'Accepted object 1', 'The frozen profile wins over mutable recognition presentation')
assert.equal(fighters[0].image, '/api/media/photo-0')
assert.equal(fighters[0].combatStats.impact, 6)
assert.equal(fighters[0].archetype, undefined, 'Camera display cannot imply class presets select combat')
assert.doesNotMatch(cameraFighter(pending(0)).subtitle, /Guard|Quick|Power/)
assert.equal(cameraPlayback(battle).events[0].at, 700, 'Quick timing is not rescaled a second time')
assert.match(cameraPlayback(battle).events[0].explanation, /Brittle surface: A rigid bump/)
assert.equal(cameraPlayback({ ...battle, combat: { ...combat, outcome: 'tiebreak' } }).outcome, 'tiebreak')
assert.equal(cameraPlayback({ ...battle, combat: { ...combat, outcome: 'points' } }).outcome, 'points')
assert.match(priceComparisonTitle(combat), /Unknown prices/)
assert.match(priceComparisonTitle({ ...combat, fighters: [profile(0, { price: { amount_gbp: 12 } }), profile(1)] }), /Neutral for both/)
assert.equal(cameraPlayback({ ...battle, combat: undefined }).events[0], event, 'Historical playback has no invented receipt explanation')
assert.equal(cameraPlayback({ ...battle, duration_ms: null }), undefined)
assert.equal(JSON.stringify(battle), original, 'Rendering helpers never mutate saved evidence')
const pairedEvents = [event, { ...event, id: 'round-1-1', attacker: 1, receipt: { ...receipt, luck: -1, rounding_adjustment: .2 } }]
assert.equal(equalDamageBeforeLuck({ ...combat, events: pairedEvents }), true)
assert.equal(equalDamageBeforeLuck(combat), false, 'A single actor cannot establish an even match')
assert.equal(equalDamageBeforeLuck({ ...combat, events: [] }), false)
assert.equal(equalDamageBeforeLuck({ ...combat, events: [...pairedEvents, { ...event, id: 'incomplete', receipt: { ...receipt, price_damage: undefined } }] }), false, 'Missing receipt fields never imply zero')
assert.equal(equalDamageBeforeLuck({ ...combat, events: [...pairedEvents, { ...event, id: 'bad', receipt: { ...receipt, luck: NaN } }] }), false)
assert.equal(equalDamageBeforeLuck({ ...combat, events: [...pairedEvents, { ...event, id: 'later-rule', receipt: { ...receipt, interaction_damage: 0 } }] }), false, 'Every hit matters, including later conditional changes')

// Render actual report and arena components. This is not a browser or network test.
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
      assert.ok(dependency, `Resolve ${specifier}`)
      resolved = await sourceModule(dependency)
    } else resolved = import.meta.resolve(specifier)
    code = code.replace(match[0], `from ${JSON.stringify(resolved)}`)
  }
  const result = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  modules.set(url.href, result)
  return result
}
const originalFetch = globalThis.fetch
globalThis.fetch = () => { throw new Error('Rendering must never make provider or persistence requests') }
try {
  const { default: Report } = await import(await sourceModule(new URL('../src/components/CameraBattleReport.tsx', import.meta.url)))
  const render = value => renderToStaticMarkup(createElement(Report, { battle: value, fighters: cameraPair(value), onReplay() {}, onAgain() {} }, createElement('button', {}, 'ENTER THE ISLANDS')))
  const html = render(battle)
  assert.match(html, /BY KNOCKOUT/)
  assert.doesNotMatch(html, /Both fighters had the same damage before luck/, 'Incomplete actor coverage cannot produce a luck-only explanation')
  const equalMatch = render({ ...battle, combat: { ...combat, events: pairedEvents } })
  assert.match(equalMatch, /Both fighters had the same damage before luck\. Saved luck rolls, rounding and any recorded tiebreak separated this match\./)
  assert.match(html, /Why Accepted object 1 won/)
  assert.match(html, /Unknown prices\. Neutral for both/)
  const referencedPrice = { amount_gbp: 12, source: 'curated_retail', label: 'Checked UK retail comparison.', observed_at: '2026-10-24T20:00:00Z', confidence: 'retail_reference', cache: { hit: false, persistence: 'mongodb' }, listings: [{ item_id: 'mug', title: 'Ceramic mug reference', amount_gbp: 12, url: 'https://shop.example/mug', condition: 'New' }] }
  const withReference = render({ ...battle, combat: { ...combat, fighters: [profile(0, { price: referencedPrice }), profile(1)] } })
  assert.match(withReference, /REFERENCE PRICE/)
  assert.match(withReference, /Checked retail reference/)
  assert.match(withReference, /Sourced starter · MongoDB Atlas/)
  assert.match(withReference, /href="https:\/\/shop\.example\/mug"/)
  assert.match(withReference, /Unknown prices\. Neutral for both/, 'One sourced fighter still leaves the price comparison neutral')
  assert.match(withReference, /Any price premium is capped at 1%; if either value is unknown, both premiums are zero/)
  assert.match(html, /The combined counters changed the winner/)
  assert.match(html, /Without counters: Accepted object 2/)
  assert.match(html, /Target health/)
  assert.match(html, /100 → 84/)
  assert.match(html, /Brittle surface \+8%/)
  assert.match(html, /Impact 6 vs Accepted object 2’s resilience 5; control 5 vs their agility 4/)
  assert.match(html, /Recorded attribute adjustment: <strong>\+1\.1 damage per hit/)
  assert.match(html, /0\.6 × \(6 impact − 5 opponent resilience\) \+ 0\.5 × \(5 control − 4 opponent agility\) = <strong>\+1\.1 damage/)
  assert.match(html, /No saved hit receipt is available for this object/, 'No P2 receipt cannot be invented from a formula')
  assert.match(html, /Recorded source evidence/)
  assert.match(html, /photo-0/)
  assert.match(html, /ENTER THE ISLANDS/)
  assert.doesNotMatch(html, /NO ISLAND REWARDS|CURATED PROFILE|SAMPLE VALUE/)
  assert.ok(html.indexOf('ENTER THE ISLANDS') < html.indexOf('Every hit, accounted for'), 'Island access is above detailed evidence')
  assert.ok(!/<details[^>]*open/.test(html), 'Long profiles and receipts begin collapsed')
  const secondHit = { ...event, id: 'round-1-1', attacker: 1, receipt: { ...receipt, stat_adjustment: -.1 } }
  const unequal = render({ ...battle, combat: { ...combat, fighters: [profile(0), profile(1, { stats: { impact: 4, resilience: 5, agility: 6, control: 5 } })], events: [{ ...event, receipt: { ...receipt, stat_adjustment: .1 } }, secondHit] } })
  assert.doesNotMatch(unequal, /Both fighters had the same damage before luck/, 'Unequal attributes cannot be called luck-only')
  assert.match(unequal, /Impact 4 vs Accepted object 1’s resilience 5; control 5 vs their agility 4/)
  assert.match(unequal, /Recorded attribute adjustment: <strong>−0\.1 damage per hit/, 'P2 uses its own first saved receipt')
  assert.match(unequal, /0\.6 × \(4 impact − 5 opponent resilience\) \+ 0\.5 × \(5 control − 4 opponent agility\) = <strong>−0\.1 damage/)
  const historical = render({ ...battle, combat: null, engine_version: 'legacy-1' })
  assert.match(historical, /HISTORICAL CLASS BATTLE/)
  assert.match(historical, /Attribute profiles and damage explanations were not recorded/)
  assert.doesNotMatch(historical, /Why Accepted object 1 won|DID PRICE DECIDE IT|Brittle surface/)
  const tie = render({ ...battle, combat: { ...combat, outcome: 'tiebreak', final_health: [0, 0], impact_points: [103, 101], tiebreak_reason: 'impact_points' } })
  assert.match(tie, /BY RECORDED TIEBREAK/)
  assert.match(tie, /P1: 103 impact points/)
  assert.doesNotMatch(tie, /THE RESULT IS IN · BY KNOCKOUT/)
  const { default: Arena } = await import(await sourceModule(new URL('../src/components/BattleArena.tsx', import.meta.url)))
  const arenaHtml = renderToStaticMarkup(createElement(Arena, { fighters, playback: cameraPlayback(battle), onComplete() {} }))
  assert.match(arenaHtml, /original player photograph/)
  assert.match(arenaHtml, /CAMERA OBJECTS · SAVED ATTRIBUTE BATTLE/)
  assert.doesNotMatch(arenaHtml, /illustrated practice object|SAMPLE OBJECTS/)
  const quickPlayback = { ...cameraPlayback(battle), events: [{ ...event, at: 5350 }] }
  const quickArena = renderToStaticMarkup(createElement(Arena, { fighters, playback: quickPlayback, onComplete() {} }))
  assert.match(quickArena, /battle-round-clock[^>]*><span>ROUND 01<\/span><strong>06<\/strong>/, 'Quick countdown shows physical seconds rather than the 12.8-second choreography coordinate')
  const normalArena = renderToStaticMarkup(createElement(Arena, { fighters, playback: { ...quickPlayback, duration_ms: 12800, events: [{ ...event, at: 10700 }] }, onComplete() {} }))
  assert.match(normalArena, /battle-round-clock[^>]*><span>ROUND 01<\/span><strong>11<\/strong>/)
} finally { globalThis.fetch = originalFetch }
console.log('Camera combat presentation passed: immutable profiles, quick replay timing, outcomes, neutral unknown prices, conditional receipts, counterfactuals, legacy fallback and real-photo attribution. No network calls or state writes.')
