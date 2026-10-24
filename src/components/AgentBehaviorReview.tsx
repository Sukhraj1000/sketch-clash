import { useState } from 'react'
import { ArrowRight, CheckCheck, MessageSquare, Search, ShieldCheck } from 'lucide-react'
import type { ColoniesSnapshot, Colony, ColonyAgent } from '../lib/colonies'
import { agentBehavior, behaviorStatusLabel, crewBlockers } from '../lib/agentBehavior'
import './AgentBehaviorReview.css'

const time = (value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const readable = (value: string) => value.replaceAll('_', ' ')
const origins: Record<string, string> = { model: 'Gemini direction', deterministic: 'Local simulator', executor: 'Local simulator', player: 'Player direction' }

function AgentReview({ colony, agent, inspectReceipt }: { colony: Colony; agent: ColonyAgent; inspectReceipt: (id: string) => void }) {
  const review = agentBehavior(colony, agent)
  const taskProject = colony.island.projects.find(project => project.id === review.task?.project_id)
  const lifetime = agent.contributions
  return <div className="behavior-agent-review">
    <div className="behavior-agent-title"><div><h3>{agent.display_name}</h3><p>{agent.object_type} · {agent.persona.role}</p></div><span className={`behavior-state ${review.task?.kind !== 'rest' && review.task ? 'is-active' : ''}`}>{review.taskState}</span></div>
    <div className="behavior-chain">
      <section><span className="behavior-step">01 / ROLE & ABILITIES</span><h4>{agent.persona.goal || 'No saved role objective'}</h4><p className="behavior-caption">Saved role objective · {agent.persona_provenance?.origin === 'rules' ? 'derived from object attributes' : 'recorded persona'}</p><div className="behavior-abilities">{agent.allowed_actions.filter(action => action !== 'rest').map(action => <span key={action}>{readable(action)}</span>)}</div><p>Actions must stay within these validated abilities.</p></section>
      <section><span className="behavior-step">02 / PUBLIC DISCUSSION</span>{review.message ? <><div className="behavior-message-meta"><MessageSquare size={12}/><span>{readable(review.message.kind)} · {time(review.message.created_at)}</span></div><blockquote>{review.message.text}</blockquote><p className="behavior-caption">Saved Gemini message. A statement can be revised by later evidence.</p></> : <p>No public Gemini message by this resident in the loaded board history.</p>}</section>
      <section><span className="behavior-step">03 / CURRENT EXECUTION</span><h4>{review.task?.title || 'No current task recorded'}</h4>{taskProject && <p className="behavior-project">{taskProject.name}</p>}<p>{review.task?.scheduling_reason || 'No scheduling explanation was saved.'}</p>{review.task && <div className="behavior-check"><ShieldCheck size={13}/><span>{review.allowed ? 'Action is within allowed abilities' : 'Action is outside current abilities — inspect state'}</span></div>}<p className="behavior-caption">{review.task?.decision_origin ? `${origins[review.task.decision_origin] || 'Recorded origin: ' + review.task.decision_origin} · ` : ''}Assigned work is not a completed contribution.</p>{review.task?.action_switched && <p className="behavior-switch">Switched from {readable(review.task.requested_action || 'the requested action')} to {readable(review.task.kind)}.</p>}</section>
      <section><span className="behavior-step">04 / SAVED RESULT</span><h4>{review.outcome}</h4>{review.receipt && <><p className="behavior-caption">Latest action receipt · {time(review.receipt.at)}</p><button className="behavior-proof" onClick={() => inspectReceipt(review.receipt!.id)}><CheckCheck size={13}/> Inspect receipt <ArrowRight size={12}/></button></>}<p className="behavior-linkage">{review.linkage === 'receipt' ? 'This public message explicitly references this receipt.' : review.linkage === 'decision' ? 'Message and receipt share a saved model decision run. Open the receipt to verify attribution.' : review.linkage === 'council' ? 'The message and action share a council reference. Execution is attributed separately.' : 'No direct saved link between this message and the latest action; shown side by side for review.'}</p></section>
    </div>
    {lifetime && <div className="behavior-lifetime"><span>RECORDED LIFETIME CONTRIBUTION</span><b>{lifetime.work} construction work</b>{Object.entries(lifetime.resources).filter(([, amount]) => amount > 0).map(([resource, amount]) => <b key={resource}>+{amount} {resource}</b>)}<small>Lifetime totals; receipt history above is a recent window.</small></div>}
  </div>
}

export default function AgentBehaviorReview({ snapshot, island, inspectReceipt }: { snapshot: ColoniesSnapshot | null; island: string; inspectReceipt: (id: string) => void }) {
  const [selectedAgent, setSelectedAgent] = useState('')
  const colonies = snapshot?.colonies.filter(colony => island === 'all' || colony.id === island) || []
  const crew = colonies.flatMap(colony => colony.island.agents.map(agent => ({ colony, agent })))
  const selection = crew.find(row => row.agent.id === selectedAgent) || crew[0]
  return <section className="agent-behavior" aria-label="Agent behavior analysis">
    <header><div><span className="obs-eyebrow"><Search size={13}/> BEHAVIOR REVIEW</span><h2>INTENT, ABILITY, CONSEQUENCE.</h2><p>Compare the crew’s public decisions with what the simulator actually allowed and saved.</p></div><small>Current state · also shown during replay<br/>Read only · no extra AI requests</small></header>
    {!snapshot && <p className="behavior-unavailable" role="status">Current island state is unavailable. No behavior conclusion can be made.</p>}
    <div className="behavior-crews">{colonies.map(colony => {
      const blockers = crewBlockers(colony).filter(row => row.missing.length || !row.feasible)
      const behavior = colony.behavior
      return <article key={colony.id} className={`behavior-crew is-${colony.id}`}><div className="behavior-crew-heading"><b>{colony.name}</b><span>{colony.island.agents.length} residents</span></div><h3>{behavior ? behaviorStatusLabel[behavior.status] || 'State being assessed' : 'Current project constraints'}</h3><p>{behavior?.reason || 'Project constraints are available below; the complete work assessment has not loaded.'}</p>{blockers.map(blocker => <div className="behavior-blocker" key={blocker.id}><strong>{blocker.name}</strong>{blocker.missing.length ? blocker.missing.map(gap => <p key={gap.resource}><span className={`behavior-blocker-tag is-${gap.kind}`}>{gap.kind === 'capability' ? 'ABILITY GAP' : gap.kind === 'supply' ? 'SUPPLIES NEEDED' : 'UNRESOLVED GAP'}</span>{gap.amount} {gap.resource} still needed after stored / incoming stock. {gap.kind === 'capability' ? `No current resident can supply ${gap.resource}.` : gap.kind === 'supply' ? 'The crew has an action that can gather this.' : 'A supported source is not recorded.'}</p>) : <p>{blocker.reason}</p>}</div>)}{behavior?.research_options?.length ? <p className="behavior-next"><b>Available research:</b> {[...new Set(behavior.research_options.map(option => option.family))].join(', ')} · {behavior.research_options.length} supported option{behavior.research_options.length === 1 ? '' : 's'}.</p> : null}{behavior?.wake_on?.length ? <p className="behavior-next"><b>Reassess when:</b> {behavior.wake_on.map(readable).join(' · ')}.</p> : null}</article>
    })}</div>
    {crew.length > 0 && <><div className="behavior-residents" aria-label="Choose a resident to review">{crew.map(({ colony, agent }) => <button key={agent.id} aria-pressed={selection?.agent.id === agent.id} onClick={() => setSelectedAgent(agent.id)}><strong>{agent.display_name}</strong><span>{colony.id === 'winners' ? 'Winner' : 'Loser'} Island · {agent.object_type}</span></button>)}</div>{selection && <AgentReview colony={selection.colony} agent={selection.agent} inspectReceipt={inspectReceipt}/>}</>}
    <footer>These are public records and measured effects. A quiet crew may have no useful supported job; waiting alone is not evidence of failure. Resource shortages and missing abilities are separate constraints.</footer>
  </section>
}
