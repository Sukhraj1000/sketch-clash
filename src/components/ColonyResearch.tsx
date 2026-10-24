import { useState } from 'react'
import { ArrowRight, FlaskConical, Lightbulb, MessageCircle, Sparkles } from 'lucide-react'
import type { Colony } from '../lib/colonies'
import './ColonyResearch.css'

const label = (value: string) => value.replaceAll('_', ' ')

export function LiveConversation({ colony, paused = false, canThink = true }: { colony: Colony; paused?: boolean; canThink?: boolean }) {
  const [chosen, setChosen] = useState('')
  const messages = colony.board.filter(m => m.origin === 'model' && m.session_id)
  const sessions = [...new Set(messages.slice().reverse().map(m => m.session_id!))]
  const session = sessions.includes(chosen) ? chosen : sessions[0]
  const conversation = messages.filter(m => m.session_id === session).sort((a, b) => (a.turn_index ?? 0) - (b.turn_index ?? 0))
  return <section className="research-conversation" aria-label="Actual agent conversation">
    <div className="research-heading"><div><span><MessageCircle size={14}/> SEPARATE AGENTS. ONE SHARED BOARD.</span><h2>The crew’s conversation.</h2></div><a href="#/observatory">WATCH UNDER THE HOOD <ArrowRight size={15}/></a></div>
    <p>Saved Gemini messages appear here. Each reply comes from a separate model turn that reads the earlier conversation. Completed work has its own receipt.</p>
    {sessions.length > 1 && <label className="research-select">CONVERSATION <select value={session} onChange={e => setChosen(e.target.value)}>{sessions.map((s, i) => <option key={s} value={s}>{i === 0 ? 'Latest discussion' : `Earlier discussion ${i}`}</option>)}</select></label>}
    {!conversation.length ? <div className="research-empty"><MessageCircle/><h3>{paused ? 'No Gemini discussion to show yet.' : 'Waiting for the first council.'}</h3><p>{paused ? 'New model turns are paused during the provider issue. Try gathering and building with fixed object roles in the playground.' : canThink ? 'Use “Gather the crew” to start a discussion. This board shows saved model responses only.' : 'Start the islands and enable available AI councils to request a discussion. No model response has been saved for this crew.'}</p><a className="research-playground-link" href="#/playground">Try the playground <ArrowRight size={14}/></a></div> : <div className="research-transcript">{conversation.map((m, index) => {
      const resident = colony.characters.find(c => c.id === m.character_id)
      const parent = colony.board.find(p => p.id === m.reply_to_id)
      return <article key={m.id} className={index % 2 ? 'reply-right' : ''}>
        <div className="research-speaker">{resident && <img src={resident.image_ref} alt=""/>}<div><b>{m.actor_name}</b><small>{m.model ?? 'Gemini'} · {label(m.kind)}</small></div><span>{String(index + 1).padStart(2, '0')}</span></div>
        {parent && <blockquote>Replying to {parent.actor_name}: “{(parent.interpretation || parent.text).slice(0, 100)}{(parent.interpretation || parent.text).length > 100 ? '…' : ''}”</blockquote>}
        <p>{m.interpretation || m.text}</p>
        <footer>{m.project_id ? colony.island.projects.find(p => p.id === m.project_id)?.name ?? 'Construction proposal' : 'Crew discussion'}<a href={`#/observatory`}>Inspect turn <ArrowRight size={12}/></a></footer>
      </article>
    })}</div>}
  </section>
}

export function ColonyResearch({ colony, residentId }: { colony: Colony; residentId?: string }) {
  const knowledge = colony.learning
  if (!knowledge) return null
  const dossiers = knowledge.dossiers.filter(d => !residentId || d.resident_id === residentId)
  const experiments = knowledge.experiments.filter(e => !residentId || e.subject_ids?.includes(residentId)).slice(0, 8)
  const findings = knowledge.findings.filter(f => !residentId || f.subject_ids?.includes(residentId)).slice(0, 6)
  return <section className="research-notebook" aria-label="Island experiments and object knowledge">
    <div className="research-heading"><div><span><FlaskConical size={14}/> IDEAS NEED EVIDENCE.</span><h2>{residentId ? 'What I am learning.' : 'The island laboratory.'}</h2></div><span className="research-count">{knowledge.findings.length} TESTED FINDINGS</span></div>
    {!residentId && <p>Objects bring shapes and recorded attributes. Model proposals can suggest new uses; the simulation tests them and saves the outcome. These are findings inside this world.</p>}
    <div className="research-dossiers">{dossiers.map(d => <details key={d.id}><summary><Sparkles size={15}/><b>{d.display_name}</b><span>{d.tested_capabilities?.length ?? 0} tested uses</span></summary><div><small>ACCEPTED VISUAL EVIDENCE</small><p>{d.observed_evidence?.visible_features?.join(' · ') || 'This historical resident has no recorded visual features.'}</p><small>SIMULATION ASSUMPTIONS</small><p>{d.simulation_properties?.material_assumption ?? 'Unmeasured material'} · {d.simulation_properties?.apparent_cavity ? 'Possible container' : 'Solid proxy'}</p><small>QUESTIONS TO TEST</small><p>{d.simulation_properties?.unknowns?.map(label).join(', ')}</p><p className="research-muted">Properties are game assumptions. Tests establish uses inside this simulation.</p></div></details>)}</div>
    {experiments.length ? <div className="research-experiments">{experiments.map(e => <article key={e.id} className={e.status === 'blocked' ? 'test-blocked' : e.result?.success ? 'test-pass' : 'test-fail'}><div><FlaskConical size={16}/><b>{label(e.family)} test</b><span>{e.status === 'blocked' ? 'NEEDS SUPPLIES' : e.result?.success ? 'SUPPORTED' : 'DID NOT WORK'}</span></div><h3>{e.hypothesis}</h3><p>{e.reason || e.result?.summary || e.result?.interpretation || (e.result?.success ? 'The tested arrangement met its success condition.' : 'The crew has new evidence to revise this idea.')}</p><dl>{Object.entries(e.result?.measurements ?? {}).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{typeof value === 'number' ? value.toFixed(2) : String(value)}</dd></div>)}</dl>{e.result?.production_validation && <p className="research-muted">{e.result.production_validation.eligible ? 'Tested for the normal island workload.' : `Prototype only. Retest: ${(e.result.production_validation.unmet_requirements ?? []).map((r: { field: string; required_minimum: number }) => `${label(r.field)} ≥ ${r.required_minimum}`).join(' · ') || 'the arrangement must also succeed'}.`}</p>}<small>{e.actor_name ?? 'Island resident'} · {e.status === 'completed' ? e.prediction_correct ? 'Prediction matched the result' : 'Prediction challenged by the result' : 'No result claimed'}</small><details><summary>Test conditions & evidence</summary><pre>{JSON.stringify({conditions: e.context, receipt: e.id, rule_version: e.rule_version}, null, 2)}</pre></details></article>)}</div> : <div className="research-empty"><FlaskConical/><h3>No experiments recorded yet.</h3><p>The island can test holding against wind, containing water and supporting a load when a test is proposed. The playground offers a separate exercise in gathering and building with fixed object roles.</p><a className="research-playground-link" href="#/playground">Try the playground <ArrowRight size={14}/></a></div>}
    {!!findings.length && <div className="research-findings">{findings.map(f => <div key={f.id}><Lightbulb size={16}/><div><b>{f.claim}</b><p>{label(f.status)} · {f.supporting_experiment_ids?.length ?? f.evidence_ids?.length ?? f.receipt_ids?.length ?? 1} evidence record(s)</p><small>Valid for the tested conditions, not every possible use.</small></div></div>)}</div>}
    {!!knowledge.research.length && <details className="research-open"><summary>Open research · {knowledge.research.length} ideas to revisit</summary>{knowledge.research.slice(0, 8).map(r => <p key={r.id}><b>{r.goal}</b><br/>{label(r.status)}{r.reassessment_reason ? ` · ${r.reassessment_reason}` : ''}</p>)}</details>}
  </section>
}
