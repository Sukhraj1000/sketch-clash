import { useEffect, useState } from 'react'
import { ArrowRight, Check, Hammer, LoaderCircle, ShieldCheck } from 'lucide-react'
import type { Colony } from '../lib/colonies'
import type { IslandEvent } from '../lib/island'
import { observatory } from '../lib/observatory'
import type { EventEvidence } from '../lib/observatory'
import { receiptDecision, receiptEvidenceLabel, receiptResources, receiptRows } from '../lib/receiptPresentation'
import './ColonyReceipts.css'

const amount = (value: number) => Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : '—'
const time = (value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const changes = (values: unknown = {}) => Object.entries(receiptResources(values) ?? {}).filter(([, value]) => typeof value === 'number' && value > 0).map(([key, value]) => `${amount(value!)} ${key}`)
export const receiptOutput = (receipt: IslandEvent) => [...changes(receipt.resource_delta), ...(receipt.progress_delta ? [`${amount(receipt.progress_delta)} build work`] : [])]
export const recentActionReceipts = (colony: Colony) => colony.island.events.filter(event => Boolean(event.action_id)).sort((a, b) => Date.parse(b.at) - Date.parse(a.at))

/** Resolve the stored receipt before calling its provenance verified. Never infer it from a model's text. */
export function ReceiptEvidence({ receiptId }: { receiptId: string }) {
  const [open, setOpen] = useState(false)
  const [evidence, setEvidence] = useState<EventEvidence | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setEvidence(null); setError('')
    observatory.receiptEvidence(receiptId, controller.signal).then(value => {
      if (!controller.signal.aborted) setEvidence(value)
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Receipt lookup failed.') })
    return () => controller.abort()
  }, [open, receiptId])
  return <details className="colony-receipt-proof" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary><ShieldCheck size={13} /> Inspect saved receipt</summary>
    {open && <div>
      {!evidence && !error && <p role="status"><LoaderCircle size={13} /> Reading the committed record…</p>}
      {error && <p role="alert">Receipt could not be checked: {error}</p>}
      {evidence && <><p className="receipt-verification"><b>{receiptEvidenceLabel(evidence)}</b> {evidence.reason}</p>{receiptRows(evidence).map(receipt => <div key={receipt.id}>
        <dl><div><dt>Added</dt><dd>{receiptResources(receipt.resource_delta) === null ? 'Resource gains not recorded' : changes(receipt.resource_delta).join(' · ') || 'No resources added'}</dd></div><div><dt>Build work</dt><dd>{amount(receipt.progress_delta)}</dd></div><div><dt>Supplies spent</dt><dd>{receiptResources(receipt.resource_cost) === null ? 'Not recorded on this historical receipt' : changes(receipt.resource_cost).join(' · ') || 'None'}</dd></div></dl>
        <p><b>Decision evidence:</b> {receiptDecision(receipt).label}. {receiptDecision(receipt).reason}</p>
        {receiptResources(receipt.resources_before) && receiptResources(receipt.resources_after) && <dl className="receipt-before-after">{Object.keys(receipt.resources_after!).filter(resource => receipt.resources_before![resource] !== receipt.resources_after![resource]).map(resource => <div key={resource}><dt>{resource} at completion</dt><dd>{amount(receipt.resources_before![resource])} <ArrowRight size={11} /> {amount(receipt.resources_after![resource])}</dd></div>)}</dl>}
        {receipt.effect_note && <p>{receipt.effect_note}</p>}
      </div>)}</>}
      <code>{receiptId}</code>
    </div>}
  </details>
}

export function ReceiptResult({ receipt, colony }: { receipt: IslandEvent; colony: Colony }) {
  const output = receiptOutput(receipt)
  const costs = changes(receipt.reserved_cost)
  const actor = receipt.actor_name ?? colony.island.agents.find(agent => agent.character_id === receipt.character_id)?.display_name ?? 'Island resident'
  const project = colony.island.projects.find(item => item.id === receipt.project_id)
  const modelLinked = receipt.decision_origin === 'model' && receipt.decision_evidence === 'accepted_decision'
  return <article className={`colony-receipt-result ${output.length ? 'has-output' : 'no-output'}`}>
    <header><b>{actor}</b><time dateTime={receipt.at}>{time(receipt.at)}</time></header>
    <strong>{output.length ? <Check size={14} /> : <Hammer size={14} />}{output.length ? output.join(' + ') : 'No shared resources or build work added'}</strong>
    <p>{receipt.description}</p>
    {receipt.scheduling_reason && <p><b>{receipt.action_switched ? 'Why the job changed:' : 'Why this job:'}</b> {receipt.scheduling_reason}</p>}
    <div className="colony-receipt-context"><span>{modelLinked ? 'MODEL DECISION LINKED' : receipt.decision_origin === 'player' ? 'PLAYER ASSIGNMENT' : receipt.decision_origin === 'model' ? 'MODEL LINK UNVERIFIED' : 'LOCAL SCHEDULER'}</span><span>Executed by simulation{project ? ` · ${project.name}` : ''}</span></div>
    {costs.length > 0 && <small>Supplies spent: {costs.join(' · ')}</small>}
    <ReceiptEvidence receiptId={receipt.id} />
  </article>
}

export function CompletedWork({ colony }: { colony: Colony }) {
  const [showAll, setShowAll] = useState(false)
  const receipts = recentActionReceipts(colony)
  const shown = (showAll ? receipts : receipts.filter(receipt => receiptOutput(receipt).length)).slice(0, 6)
  const noGain = receipts.filter(receipt => !receiptOutput(receipt).length).length
  return <section className="colony-work-results" aria-label="Actual island contributions">
    <div className="colony-section-heading"><div><span className="colony-kicker"><Hammer size={14} /> THE WORK AFTER THE WORDS</span><h2>What actually changed.</h2></div><button className="colony-text-button" aria-pressed={showAll} onClick={() => setShowAll(value => !value)}>{showAll ? 'Show useful output' : 'Include zero-output actions'}</button></div>
    <p>Completed tasks from this island’s recent saved history. Walking and proposals do not count as contributions. {noGain > 0 ? `${noGain} recent action${noGain === 1 ? '' : 's'} added no shared resources or build work.` : ''}</p>
    {shown.length ? <div className="colony-work-result-list">{shown.map(receipt => <ReceiptResult key={receipt.id} receipt={receipt} colony={colony} />)}</div> : <p className="colony-work-empty">{receipts.length ? 'No shared output in the recent receipts. The crew needs useful work before these cards show a contribution.' : 'No current-format task receipts in this snapshot yet. Contributions appear after an action finishes.'}</p>}
    <small>Shows up to six actions from the latest island history, rather than lifetime totals. Older records remain available in the Observatory.</small>
  </section>
}
