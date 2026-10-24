import type { ActionReceipt } from './observatory'

const record = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value))

/** Missing/truncated ledgers are unknown, never an empty ledger or zero spending. */
export function receiptResources(value: unknown): Record<string, number> | null {
  if (!record(value) || Object.values(value).some(amount => typeof amount !== 'number' || !Number.isFinite(amount))) return null
  return value as Record<string, number>
}

export function receiptRows(evidence: unknown): ActionReceipt[] {
  if (!record(evidence) || !Array.isArray(evidence.receipts)) return []
  return evidence.receipts.filter((row): row is ActionReceipt => record(row) && typeof row.id === 'string' && Boolean(row.id))
}

export function receiptDecision(receipt: unknown) {
  const row = record(receipt) ? receipt : {}
  const provenance = record(row.provenance) ? row.provenance : {}
  const hasReason = typeof provenance.reason === 'string' && Boolean(provenance.reason.trim())
  const verified = provenance.status === 'verified' && hasReason && ['model', 'executor'].includes(String(provenance.attribution))
  const label = !verified ? row.decision_origin === 'model' ? 'Claimed model origin · link unverified' : 'Origin not verified'
    : provenance.attribution === 'model' ? 'Gemini decision'
      : row.decision_origin === 'player' ? 'Player direction' : 'Local simulator'
  const reason = typeof provenance.reason === 'string' && provenance.reason.trim() ? provenance.reason : 'Decision provenance was not returned. No model attribution has been verified.'
  return { label, reason, verified }
}

export function receiptEvidenceLabel(evidence: unknown) {
  if (!record(evidence)) return 'EVIDENCE UNAVAILABLE'
  if (evidence.status === 'verified') {
    const receipts = receiptRows(evidence)
    if (!receipts.length) return 'RECEIPT DETAILS UNAVAILABLE'
    return receipts.every(receipt => receiptDecision(receipt).verified) ? 'VERIFIED RECEIPT' : 'SAVED RECEIPT · ORIGIN UNVERIFIED'
  }
  return ({ missing: 'EVIDENCE MISSING', not_applicable: 'NO ACTION RECEIPT EXPECTED', historical: 'HISTORICAL RECORD' } as Record<string, string>)[String(evidence.status)] ?? 'EVIDENCE UNAVAILABLE'
}
