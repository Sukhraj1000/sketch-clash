import assert from 'node:assert/strict'
import { receiptDecision, receiptEvidenceLabel, receiptResources, receiptRows } from '../src/lib/receiptPresentation.ts'

// Regression: a truncated receipt response must not crash or turn absent fields into verified provenance / zero costs.
const complete = { id: 'saved-action', decision_origin: 'model', resource_cost: {}, provenance: { status: 'verified', attribution: 'model', reason: 'Completed provider turn and session verified.' } }
assert.equal(receiptDecision(complete).label, 'Gemini decision')
assert.equal(receiptEvidenceLabel({ status: 'verified', receipts: [complete] }), 'VERIFIED RECEIPT')
for (const provenance of [undefined, null, {}, [], 'truncated', { attribution: 'model' }, { status: 'verified', attribution: 'model' }]) {
  const truncated = { ...complete, provenance }
  assert.equal(receiptDecision(truncated).verified, false)
  assert.match(receiptDecision(truncated).label, /unverified/)
  assert.equal(receiptEvidenceLabel({ status: 'verified', receipts: [truncated] }), 'SAVED RECEIPT · ORIGIN UNVERIFIED')
}
for (const missingLedger of [undefined, null, [], 'missing', { ideas: '1' }, { water: NaN }]) assert.equal(receiptResources(missingLedger), null)
assert.deepEqual(receiptResources({}), {})
assert.deepEqual(receiptResources({ ideas: 1 }), { ideas: 1 })
for (const evidence of [null, undefined, {}, { receipts: null }, { receipts: {} }, { receipts: [null, 7, {}, { id: '' }] }]) assert.deepEqual(receiptRows(evidence), [])
assert.equal(receiptEvidenceLabel({ status: 'verified', receipts: null }), 'RECEIPT DETAILS UNAVAILABLE')
assert.equal(receiptEvidenceLabel({ status: 'historical', receipts: [complete] }), 'HISTORICAL RECORD')
assert.equal(receiptDecision({ decision_origin: 'deterministic', provenance: null }).label, 'Origin not verified')
assert.equal(receiptDecision({ decision_origin: 'player', provenance: { status: 'verified', attribution: 'executor', reason: 'Recorded local assignment.' } }).label, 'Player direction')
console.log('Receipt presentation regressions passed: missing provenance, unknown costs, malformed envelopes and verified records.')
