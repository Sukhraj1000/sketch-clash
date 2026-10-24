import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Box, Check, ChevronRight, Flag, Globe2, Hammer, Lightbulb, LoaderCircle, Maximize2, MessageCircle, Pause, Play, RefreshCw, ShieldCheck, Sparkles, Target, Trophy, Waves, X, Zap } from 'lucide-react'
import { coloniesRequest, colonyMutation, numberMetric } from '../lib/colonies'
import type { Colony, ColonyAgent, ColonyId, ColonyPlanner, ColoniesSnapshot } from '../lib/colonies'
import type { IslandProject } from '../lib/island'
import './ColoniesView.css'

const WorldScene = lazy(() => import('./WorldScene'))
const RESOURCE_ICONS = { materials: Box, water: Waves, ideas: Lightbulb, energy: Zap }
const RESOURCE_NAMES = ['materials', 'water', 'ideas', 'energy'] as const
const percent = (project: IslandProject) => project.status === 'complete' ? 100 : Math.min(100, Math.round(project.progress / Math.max(1, project.required_progress) * 100))
const human = (value: string) => value.replaceAll('_', ' ')
const count = (value: number) => Number.isFinite(value) ? Math.round(value).toLocaleString() : '—'
const pounds = (value: number | null | undefined) => value == null ? 'UNKNOWN' : new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 2 }).format(value)
const scalar = (value: unknown) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? String(value) : null
const textField = (record: Record<string, unknown> | null | undefined, keys: string[]) => keys.map(key => scalar(record?.[key])).find(Boolean) ?? ''
const AGE = (value: string) => { const date = new Date(value); return Number.isFinite(date.getTime()) ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Saved' }

class ColonySceneBoundary extends Component<{ children: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch() { this.props.onFailure() }
  render() { return this.state.failed ? null : this.props.children }
}

function IslandStamp({ side, built }: { side: ColonyId; built: number }) {
  return <svg className="colony-stamp" viewBox="0 0 180 95" aria-hidden="true">
    <ellipse cx="90" cy="76" rx="78" ry="13" fill="#83CDDB" />
    <path d="M25 52q65-32 130 0l-14 25q-50 24-102-2Z" fill="#C88E5B" stroke="currentColor" strokeWidth="2" />
    <ellipse cx="90" cy="52" rx="65" ry="22" fill={side === 'winners' ? '#A8DFC0' : '#B2D8A2'} stroke="currentColor" strokeWidth="2" />
    <path d="M46 48v-20m-11 10 11-17 12 17Z" fill="#48A77C" stroke="currentColor" strokeWidth="2" />
    <path d="M122 45V13m0 1h24l-5 8 5 8h-24" fill={side === 'winners' ? '#FFD166' : '#FF7C76'} stroke="currentColor" strokeWidth="2" />
    {built > 0 && <><path d="M72 51V35h28v16Z" fill="#FFE5A3" stroke="currentColor" strokeWidth="2" /><path d="m68 35 18-14 19 14Z" fill="#EE8274" stroke="currentColor" strokeWidth="2" /><path d="M82 51V42h8v9" fill="#B97853" stroke="currentColor" strokeWidth="2" /></>}
    <path d="m25 86 12-2m116-4 12-2M8 70l9-2" stroke="#407F9D" strokeWidth="2" strokeLinecap="round" />
  </svg>
}

function ColonyCard({ colony, selected, onSelect }: { colony: Colony; selected: boolean; onSelect: () => void }) {
  const levels = numberMetric(colony.metrics, ['project_levels'], colony.island.projects.reduce((sum, p) => sum + p.level, 0))
  const actions = numberMetric(colony.metrics, ['completed_actions'], colony.island.agents.reduce((sum, agent) => sum + agent.completed_actions, 0))
  const residents = numberMetric(colony.metrics, ['resident_count'], colony.characters.length)
  return <button className={`colony-card colony-${colony.id} ${selected ? 'is-selected' : ''}`} onClick={onSelect} aria-pressed={selected} aria-label={`Visit ${colony.name}`}>
    <IslandStamp side={colony.id} built={levels} />
    <div className="colony-card-heading"><span>{colony.id === 'winners' ? 'THE VICTORY CREW' : 'THE COMEBACK CREW'}</span><h2>{colony.name}</h2><p>{colony.id === 'winners' ? 'Won the fight. Now make it count.' : 'Lost the fight. Still building something great.'}</p></div>
    <div className="colony-card-scores"><span><b>{count(levels)}</b>BUILD LEVELS</span><span><b>{count(residents)}</b>RESIDENTS</span><span><b>{residents ? (actions / residents).toFixed(1) : '—'}</b>TASKS / RESIDENT</span></div>
    <div className="colony-card-footer"><span><i className={colony.island.paused ? 'paused' : ''} />{!colony.island.enabled ? 'READY TO START' : colony.island.paused ? 'PAUSED' : 'GETTING ON WITH IT'}</span><b>{selected ? 'YOU ARE HERE' : 'VISIT ISLAND'} <ArrowUpRight size={14} /></b></div>
  </button>
}

function ProjectPanel({ colony, project, busy, onPriority }: { colony: Colony; project: IslandProject; busy: boolean; onPriority: () => void }) {
  const active = project.id === colony.island.active_project_id
  return <div className="colony-project-inspect"><span className="colony-kicker"><Flag size={13} /> {active ? 'THE CREW’S PRIORITY' : 'ISLAND BLUEPRINT'}</span><h2>{project.name}</h2><p>{project.description}</p><div className="colony-progress-label"><b>{percent(project)}%</b><span>LEVEL {project.level} / {project.max_level}</span></div><div className="colony-progress"><i style={{ width: `${percent(project)}%` }} /></div><div className="colony-cost"><span>ONE BUILD ACTION NEEDS</span><b>{Object.entries(project.cost_per_action).filter(([, amount]) => amount > 0).map(([resource, amount]) => `${amount} ${resource}`).join(' · ')}</b></div><p className="colony-reward"><Sparkles size={15} />{project.reward}</p><button className="colony-button is-yellow" disabled={busy || active || project.status === 'complete'} onClick={onPriority}>{active ? <Check size={15} /> : <Target size={15} />}{project.status === 'complete' ? 'FULLY BUILT' : active ? 'CREW IS FOCUSED HERE' : 'MAKE THIS THE PRIORITY'}</button><small>Residents collect missing supplies before building. Project levels count completed upgrades.</small></div>
}

function AgentPanel({ agent, colony, busy, now, onAssign, onThink, canThink, onValue }: { agent: ColonyAgent; colony: Colony; busy: boolean; now: number; onAssign: (assignment: string) => void; onThink: () => void; canThink: boolean; onValue: (value: number) => void }) {
  const character = colony.characters.find(item => item.id === agent.character_id)
  const [estimate, setEstimate] = useState(character?.estimated_value_gbp?.toString() ?? '')
  useEffect(() => setEstimate(character?.estimated_value_gbp?.toString() ?? ''), [character?.id, character?.estimated_value_gbp])
  const task = agent.task
  const taskEnd = task ? Date.parse(task.ends_at) : 0
  const taskStart = task ? Date.parse(task.started_at) : 0
  const progress = task ? Math.max(0, Math.min(100, (now - taskStart) / Math.max(1, taskEnd - taskStart) * 100)) : 0
  const contributions = colony.board.filter(entry => entry.character_id === agent.character_id && entry.kind === 'report' && entry.receipt_ids.length)
  return <div className="colony-agent-inspect">
    <div className="colony-agent-identity">{character && <img src={character.image_ref} alt={character.object_type} />}<div><span>LEVEL {agent.level} · {agent.xp} XP</span><h2>{agent.display_name}</h2><b>{agent.persona.role}</b></div></div>
    <p className="colony-motto">“{agent.persona.motto}”</p><div className="colony-abilities">{agent.capabilities.map(capability => <span key={capability}>{human(capability)}</span>)}</div>
    <p className="colony-intent"><Target size={15} /><span>{agent.intent || agent.persona.goal}</span></p>
    <div className="colony-current-task"><span>CURRENT JOB <b>{colony.island.paused ? 'PAUSED' : task ? `${Math.max(0, Math.ceil((taskEnd - now) / 1000))}s` : 'READY'}</b></span><strong>{task?.title ?? 'Looking for a useful job.'}</strong><div className="colony-progress"><i style={{ width: `${progress}%` }} /></div></div>
    <label className="colony-assignment">GIVE THEM DIRECTION<select value={agent.assignment} disabled={busy} onChange={event => onAssign(event.target.value)}>{agent.available_assignments.map(assignment => <option key={assignment.id} value={assignment.id}>{assignment.label}</option>)}</select><small>Takes effect after the current job.</small></label>
    <div className="colony-agent-totals"><span><b>{agent.completed_actions}</b>COMPLETED TASKS</span><span><b>{contributions.length}</b>RECENT RECEIPTED REPORTS</span></div>
    <button className="colony-button" disabled={busy || !canThink} onClick={onThink}><MessageCircle size={15} /> ASK FOR A PLAN</button><small className="colony-ai-note">One bounded AI turn. A proposal must pass the same game rules.</small>
    <div className="colony-memory"><h3><BookOpen size={14} /> MEMORY, WITH RECEIPTS</h3>{agent.memory.length ? agent.memory.slice(-3).reverse().map(memory => <p key={memory.id}><span>{memory.kind === 'reflection' ? 'AI INTERPRETATION' : 'RECORDED EVENT'} · {AGE(memory.at)}</span>{memory.text}</p>) : <p>The first completed job starts this resident’s story.</p>}</div>
    <details className="colony-value-editor"><summary>YOUR VALUE ESTIMATE <b>{pounds(character?.estimated_value_gbp)}</b></summary><p>A rough user estimate, not a verified market price. It never changes abilities or rewards.</p><form onSubmit={event => { event.preventDefault(); const amount = Number(estimate); if (estimate.trim() && Number.isFinite(amount) && amount >= 0 && amount <= 1000000) onValue(amount) }}><label>ESTIMATED VALUE (GBP)<input type="number" min="0" max="1000000" step="0.01" required inputMode="decimal" value={estimate} onChange={event => setEstimate(event.target.value)} placeholder="e.g. 12.50" /></label><button className="colony-button" disabled={busy || !estimate.trim() || !Number.isFinite(Number(estimate)) || Number(estimate) < 0 || Number(estimate) > 1000000}>SAVE ESTIMATE</button></form></details>
  </div>
}

function SharedBoard({ colony, selected, onSelect }: { colony: Colony; selected: string | null; onSelect: (id: string) => void }) {
  const [filter, setFilter] = useState<'all' | 'request' | 'offer' | 'report'>('all')
  const ordered = [...colony.board].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  const entries = ordered.filter(entry => filter === 'all' || entry.kind === filter).slice(0, 12)
  return <section className="colony-board" aria-label={`${colony.name} shared whiteboard`}><div className="colony-section-heading"><div><span className="colony-kicker"><MessageCircle size={13} /> SAME ISLAND. SHARED PLAN.</span><h2>THE WORK BOARD.</h2></div><span className="colony-paper-pin" aria-hidden="true">✳</span></div><div className="colony-board-filters" aria-label="Filter board messages">{(['all', 'request', 'offer', 'report'] as const).map(kind => <button key={kind} onClick={() => setFilter(kind)} aria-pressed={filter === kind}>{kind === 'all' ? 'EVERYTHING' : `${kind.toUpperCase()}S`}</button>)}</div><div className="colony-board-entries">{entries.length ? entries.map(entry => <button className={`colony-board-note note-${entry.kind} ${selected === entry.id ? 'is-selected' : ''}`} key={entry.id} onClick={() => onSelect(entry.id)} aria-pressed={selected === entry.id}><div><span>{entry.kind.toUpperCase()} <i>{entry.origin === 'model' ? 'AI' : entry.origin === 'player' ? 'PLAYER' : 'GAME RULE'}</i></span><time>{AGE(entry.created_at)}</time></div><strong>{entry.actor_name}</strong><p>{entry.text}</p><footer><span>{human(entry.status)}{entry.remaining !== undefined && entry.status !== 'fulfilled' ? ` · ${entry.remaining} remaining` : ''}</span><b>{entry.receipt_ids.length ? `${entry.receipt_ids.length} RECEIPT${entry.receipt_ids.length === 1 ? '' : 'S'}` : 'VIEW THREAD'} <ChevronRight size={12} /></b></footer></button>) : <div className="colony-empty-board"><MessageCircle size={27} /><h3>GOOD WORK STARTS WITH A NEED.</h3><p>{colony.island.enabled ? 'Requests, offers and reports appear as this crew works. No messages are invented for the display.' : 'Start the islands to open the crew’s shared work board.'}</p></div>}</div><p className="colony-small-note">A message is a request or proposal. Only a completed, validated action changes the island.</p></section>
}

type LoopNode = 'observe' | 'remember' | 'decide' | 'validate' | 'act' | 'record'
const LOOP_NODES: { id: LoopNode; title: string; description: string; icon: typeof Box }[] = [
  { id: 'observe', title: 'NOTICE', description: 'Read the island', icon: Globe2 },
  { id: 'remember', title: 'REMEMBER', description: 'Bring evidence', icon: BookOpen },
  { id: 'decide', title: 'PROPOSE', description: 'Choose a useful job', icon: Lightbulb },
  { id: 'validate', title: 'CHECK', description: 'Rules get the last word', icon: ShieldCheck },
  { id: 'act', title: 'DO', description: 'Spend time, do work', icon: Hammer },
  { id: 'record', title: 'REMEMBER AGAIN', description: 'Save what happened', icon: Check },
]

function EvidenceFields({ record }: { record: Record<string, unknown> | null | undefined }) {
  const fields = Object.entries(record ?? {}).filter(([, value]) => value !== null && value !== undefined).slice(0, 12)
  if (!fields.length) return <p className="colony-small-note">No saved record for this step yet.</p>
  return <dl className="colony-evidence-fields">{fields.map(([key, value]) => <div key={key}><dt>{human(key)}</dt><dd>{scalar(value) ?? (Array.isArray(value) ? value.map(item => scalar(item) ?? JSON.stringify(item)).join(', ') : JSON.stringify(value))}</dd></div>)}</dl>
}

function UnderTheHood({ colony, planner, selectedEntry, onEntrySelect }: { colony: Colony; planner?: ColonyPlanner; selectedEntry: string | null; onEntrySelect: (id: string | null) => void }) {
  const [node, setNode] = useState<LoopNode>('observe')
  const [runId, setRunId] = useState<string>('')
  const runs = (planner?.runs ?? []).filter(run => run.colony_id === colony.id).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  const run = runs.find(item => item.id === runId) ?? runs[0]
  const entry = colony.board.find(item => item.id === selectedEntry)
  const request = entry?.request_id ? colony.board.find(item => item.id === entry.request_id) : entry?.kind === 'request' ? entry : undefined
  const thread = request ? colony.board.filter(item => item.id === request.id || item.request_id === request.id).sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at)) : entry ? [entry] : []
  const selectedAgent = colony.island.agents.find(agent => agent.id === run?.agent_id || agent.character_id === run?.agent_id)
  const connections = colony.board.filter(item => item.request_id && colony.board.some(request => request.id === item.request_id && request.actor_id !== item.actor_id)).slice(-6)
  const evidenceStatus: Record<LoopNode, string> = {
    observe: `STATE REVISION ${colony.island.revision}`,
    remember: selectedAgent ? `${selectedAgent.memory.length} CURRENT MEMORIES` : 'SELECT A SAVED TURN',
    decide: run?.decision ? 'PROPOSAL SAVED' : run ? human(run.status).toUpperCase() : 'NO AI TURN YET',
    validate: run?.receipt ? 'VALIDATOR RECEIPT' : 'NO RECEIPT YET',
    act: `${colony.island.agents.filter(agent => agent.task).length} ACTIVE JOBS`,
    record: `${colony.island.events.length} RECENT EVENTS`,
  }
  return <section className="colony-machine" aria-label="Under the hood"><div className="colony-section-heading"><div><span className="colony-kicker"><Zap size={13} /> LITTLE BRAINS. VISIBLE CONSEQUENCES.</span><h2>HOW THE ISLAND THINKS.</h2></div><span className="colony-live-label">SAVED EVIDENCE</span></div><p className="colony-machine-intro">Select a step. Follow a real proposal through the rules and back into memory. Everyday movement runs locally; AI is called for bounded decisions.</p>
    <div className="colony-loop" aria-label="Decision and action loop">{LOOP_NODES.map(({ id, title, description, icon: Icon }, index) => <div key={id} className="colony-loop-step"><button onClick={() => { setNode(id); onEntrySelect(null) }} aria-pressed={!entry && node === id}><span>{String(index + 1).padStart(2, '0')}<Icon size={18} /></span><b>{title}</b><small>{description}</small><em className="colony-loop-evidence">{evidenceStatus[id]}</em></button>{index < LOOP_NODES.length - 1 && <ArrowRight className="colony-loop-arrow" size={16} aria-hidden="true" />}</div>)}</div><div className="colony-loop-return" aria-hidden="true"><span>↳ NEW EVIDENCE CHANGES THE NEXT PLAN ↲</span></div>
    <div className="colony-machine-content"><div className="colony-run-evidence"><div className="colony-evidence-heading"><h3>{entry ? 'A REAL CONVERSATION' : LOOP_NODES.find(item => item.id === node)?.title}</h3>{entry && <button onClick={() => onEntrySelect(null)} aria-label="Close board receipt"><X size={15} /></button>}</div>
      {entry ? <><p className="colony-small-note">{request ? 'This thread links a need to its responses. Receipts distinguish delivered work from promises.' : 'A persisted report from the work board.'}</p>{thread.map(item => <div className="colony-thread-entry" key={item.id}><span>{item.actor_name} · {item.kind.toUpperCase()} · {item.origin === 'model' ? 'AI' : 'GAME RULE'}</span><p>{item.text}</p><small>{human(item.status)}{item.receipt_ids.length ? ` · receipts: ${item.receipt_ids.join(', ')}` : ' · no completion receipt yet'}</small></div>)}</> : <>
        {node === 'observe' && <><p>Authoritative state that a worker can inspect. The browser visualises it; the server changes it.</p><EvidenceFields record={{ island: colony.name, revision: colony.island.revision, active_project: colony.island.active_project_id ?? 'none', resources: colony.island.resources, open_requests: numberMetric(colony.metrics, ['open_requests']), server_time: colony.island.server_time }} /></>}
        {node === 'remember' && <><p>{selectedAgent ? `${selectedAgent.display_name}’s saved memory. Reflections are interpretations; recorded events are observations.` : 'Choose a saved AI turn to inspect its resident’s current memory. Retrieval details are shown only when present in the saved run.'}</p>{selectedAgent?.memory.slice(-3).map(memory => <div className="colony-thread-entry" key={memory.id}><span>{memory.kind === 'reflection' ? 'AI INTERPRETATION' : 'RECORDED EVENT'}</span><p>{memory.text}</p><small>{memory.id}</small></div>)}</>}
        {node === 'decide' && <><p>{run ? `Saved turn for ${run.agent_name ?? 'one resident'}: ${human(run.status)}. This is its structured proposal, not private model reasoning.` : 'No AI decision has been saved for this island yet. Rule-based work can continue without a model call.'}</p><EvidenceFields record={run?.decision} /></>}
        {node === 'validate' && <><p>The server checks proposals against legal actions and current state. A proposal is not evidence that a job finished.</p><EvidenceFields record={run?.receipt} /></>}
        {node === 'act' && <><p>These are the crew’s current server-owned jobs. The scene follows the same task positions and timing.</p>{colony.island.agents.slice(0, 6).map(agent => <div className="colony-thread-entry" key={agent.id}><span>{agent.display_name}</span><p>{agent.task?.title ?? 'No active job'}</p><small>{agent.task ? `Task ${agent.task.id}` : 'Waiting for the next job'}</small></div>)}</>}
        {node === 'record' && <><p>Completed work has a durable event. The next plan can use these results.</p>{colony.island.events.slice(-4).reverse().map(event => <div className="colony-thread-entry" key={event.id}><span>{event.title}</span><p>{event.description}</p><small>Receipt {event.id}</small></div>)}{!colony.island.events.length && <p className="colony-small-note">No completed work recorded yet.</p>}</>}
      </>}
      {runs.length > 0 && <label className="colony-run-selector">SAVED AI TURN<select value={run?.id ?? ''} onChange={event => setRunId(event.target.value)}>{runs.slice(0, 20).map(item => <option key={item.id} value={item.id}>{item.agent_name ?? 'Resident'} · {human(item.status)} · {AGE(item.created_at)}</option>)}</select></label>}
    </div><aside className="colony-connections"><h3><MessageCircle size={15} /> WHO IS HELPING WHO?</h3><p>Connections come from actual work-board replies on this island.</p>{connections.length ? connections.map(item => { const request = colony.board.find(request => request.id === item.request_id)!; return <button key={item.id} onClick={() => onEntrySelect(item.id)}><span>{item.actor_name}</span><div><ArrowRight size={17} /><b>{item.kind === 'offer' ? 'OFFERED HELP' : 'REPORTED BACK'}</b></div><span>{request.actor_name}</span><small>{item.resource ? human(item.resource) : 'Shared task'} · {human(item.status)}</small></button> }) : <div className="colony-no-links"><span aria-hidden="true">○ · · · ○</span><p>No linked replies yet. This diagram stays empty until residents actually exchange work.</p></div>}<p className="colony-small-note">Conversation volume is not a productivity score.</p></aside></div>
  </section>
}

export default function ColoniesView({ onBack, onLegacy }: { onBack: () => void; onLegacy: () => void }) {
  const [snapshot, setSnapshot] = useState<ColoniesSnapshot | null>(null)
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [actionError, setActionError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(''), [retry, setRetry] = useState(0)
  const [side, setSide] = useState<ColonyId>('winners'), [selectedId, setSelectedId] = useState<string | null>(null), [projectId, setProjectId] = useState<string | null>(null), [entryId, setEntryId] = useState<string | null>(null)
  const [sceneFailed, setSceneFailed] = useState(false), [resetKey, setResetKey] = useState(0), [follow, setFollow] = useState(false), [now, setNow] = useState(Date.now()), [visible, setVisible] = useState(!document.hidden), [reduced, setReduced] = useState(false)
  const controller = useRef<AbortController | null>(null), locked = useRef(false), mutationEpoch = useRef(0)
  const stageRef = useRef<HTMLDivElement>(null), evidenceRef = useRef<HTMLDivElement>(null)
  const receivedAt = useRef(Date.now())
  const saveSnapshot = (value: ColoniesSnapshot) => { receivedAt.current = Date.now(); setSnapshot(value) }
  useEffect(() => { const media = matchMedia('(prefers-reduced-motion: reduce)'); const update = () => setReduced(media.matches); const visibility = () => setVisible(!document.hidden); update(); media.addEventListener('change', update); document.addEventListener('visibilitychange', visibility); return () => { media.removeEventListener('change', update); document.removeEventListener('visibilitychange', visibility) } }, [])
  useEffect(() => { const timer = window.setInterval(() => { if (!document.hidden) setNow(Date.now()) }, 1000); return () => window.clearInterval(timer) }, [])
  useEffect(() => {
    const lifetime = new AbortController(); controller.current = lifetime; let running = false
    async function poll() { if (running || document.hidden || locked.current) return; running = true; const epoch = mutationEpoch.current; try { const value = await coloniesRequest<ColoniesSnapshot>('', {}, lifetime.signal); if (!lifetime.signal.aborted && epoch === mutationEpoch.current) { saveSnapshot(value); setError(''); setLoading(false) } } catch (error) { if (!lifetime.signal.aborted) { setError((error as Error).message); setLoading(false) } } finally { running = false } }
    void poll(); const timer = window.setInterval(() => void poll(), 3000); const wake = () => { if (!document.hidden) void poll() }; document.addEventListener('visibilitychange', wake)
    return () => { lifetime.abort(); window.clearInterval(timer); document.removeEventListener('visibilitychange', wake) }
  }, [retry])
  async function act(kind: string, fields: Record<string, unknown> = {}) {
    if (locked.current) return
    locked.current = true; mutationEpoch.current += 1; setBusy(kind); setActionError(''); setNotice('')
    const signal = controller.current?.signal
    try {
      const key = crypto.randomUUID()
      if (kind === 'think') { await colonyMutation('/think', { idempotency_key: key, colony_id: side, ...fields }, signal); setNotice('One AI turn requested. Its proposal and validation result will appear under the hood.') }
      else if (kind === 'planner') saveSnapshot(await colonyMutation<ColoniesSnapshot>('/planner', fields, signal))
      else saveSnapshot(await colonyMutation<ColoniesSnapshot>(kind === 'start' ? '/start' : '/command', kind === 'start' ? {} : { idempotency_key: key, colony_id: side, kind, ...fields }, signal))
      if (kind === 'think') saveSnapshot(await coloniesRequest<ColoniesSnapshot>('', {}, signal))
    } catch (error) { if (!signal?.aborted) setActionError((error as Error).message) }
    finally { locked.current = false; if (!signal?.aborted) setBusy('') }
  }
  const colony = snapshot?.colonies.find(item => item.id === side) ?? snapshot?.colonies[0]
  const simulation = colony?.island
  const agent = simulation?.agents.find(item => item.character_id === selectedId)
  const project = simulation?.projects.find(item => item.id === projectId) ?? (!selectedId ? simulation?.projects.find(item => item.id === simulation.active_project_id) : undefined)
  const planner = snapshot?.planner
  const activeRun = planner?.active_run
  const plannerWorking = Boolean(activeRun && ['queued', 'running', 'applying'].includes(activeRun.status))
  const canThink = Boolean(snapshot?.enabled && planner?.enabled && planner.configured && !simulation?.paused && !plannerWorking && planner.requests_today < planner.max_requests_per_day)
  const simulationNow = simulation?.paused && simulation.paused_at ? Date.parse(simulation.paused_at) : Date.parse(simulation?.server_time ?? '') + (now - receivedAt.current)
  function chooseSide(id: ColonyId) { setSide(id); setSelectedId(null); setProjectId(null); setEntryId(null); setFollow(false); setResetKey(value => value + 1); stageRef.current?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'start' }) }
  function chooseAgent(id: string) { setSelectedId(id); setProjectId(null) }
  function chooseProject(id: string) { setProjectId(id); setSelectedId(null); setFollow(false) }

  return <section className="colonies-screen" aria-label="Sketch Clash twin islands">
    <div className="colonies-heading"><div><span className="colony-kicker"><Globe2 size={13} /> THE FIGHT WAS JUST THE BEGINNING.</span><h1>TWO ISLANDS.<em>ONE BIG WHAT IF?</em></h1></div><button className="colony-button" onClick={onBack}><ArrowLeft size={14} /> BACK TO THE ARCADE</button></div>
    {loading && !snapshot && <div className="colonies-state" role="status"><span>✳</span><h2>CHECKING BOTH SIDES OF THE STORY…</h2><p>Opening the saved colonies and their work boards.</p></div>}
    {!snapshot && !loading && <div className="colonies-state"><Globe2 size={40} /><h2>THE ISLANDS ARE OUT OF REACH.</h2><p role="alert">{error || 'No island data was returned.'}</p><button className="colony-button is-yellow" onClick={() => { setLoading(true); setRetry(value => value + 1) }}><RefreshCw size={15} /> TRY AGAIN</button><button className="colony-text-button" onClick={onLegacy}>OPEN THE ORIGINAL ISLAND <ArrowUpRight size={13} /></button></div>}
    {snapshot && <>
      {snapshot.persistence === 'development_memory' && <p className="colony-alert">TEMPORARY PREVIEW · MongoDB is not connected. This state is lost when the local backend restarts.</p>}
      {(error || actionError) && <p className="colony-alert is-error" role="alert">{actionError || error}<button onClick={() => { setActionError(''); setRetry(value => value + 1) }}>REFRESH</button></p>}
      {notice && <p className="colony-alert" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss island message"><X size={14} /></button></p>}
      <div className="colony-comparison">{snapshot.colonies.map(item => <ColonyCard key={item.id} colony={item} selected={item.id === colony?.id} onSelect={() => chooseSide(item.id)} />)}<span className="colony-versus" aria-hidden="true">VS</span></div>
      <div className="colony-comparison-caption"><span><Trophy size={14} /> A battle result chooses a shore. Useful work builds the island.</span><details><summary>WHAT ARE WE COMPARING?</summary><p>Build levels are completed structure upgrades. Tasks per resident divides completed tasks by current resident count; it includes maintenance and rest. Crews can have different sizes, abilities and active time, so this is a live game comparison—not evidence that winners are better agents.</p><p><b>MARKET VALUE: UNKNOWN.</b> Optional user estimates are shown separately, with coverage. No verified market feed is connected. Battle wins and island productivity do not establish price.</p></details></div>
      {!snapshot.enabled && <div className="colony-start-banner"><div><span className="colony-kicker">THE NEXT CHAPTER</span><h2>GIVE BOTH CREWS SOMETHING TO BUILD.</h2><p>Completed battles place the winner on Winner Island and the other fighter on Loser Island. Returning object types keep their first appearance on each shore.</p><small>{planner?.configured ? 'Starting permits bounded AI decisions within the daily allowance. Everyday jobs run without model calls. AI can be switched off.' : 'Rule-based jobs work without model calls. AI decisions are available when the local provider is configured.'}</small></div><button className="colony-button is-coral" disabled={Boolean(busy)} onClick={() => void act('start')}>{busy === 'start' ? <LoaderCircle size={17} className="colony-spin" /> : <Play size={17} />} START BOTH ISLANDS</button></div>}
      {colony && simulation && <>
        <div className="colony-toolbar" ref={stageRef}><div><span className={`colony-side-dot ${side}`} /><h2>{colony.name}</h2><span>LEVEL {simulation.growth_level}</span></div><div>{snapshot.enabled && <button className="colony-button" disabled={Boolean(busy)} onClick={() => void act(simulation.paused ? 'resume' : 'pause')}>{simulation.paused ? <Play size={13} /> : <Pause size={13} />}{simulation.paused ? 'RESUME' : 'PAUSE'}</button>}<button className="colony-text-button" onClick={onLegacy}>ORIGINAL ISLAND <ArrowUpRight size={12} /></button></div></div>
        <div className="colony-resources">{RESOURCE_NAMES.map(resource => { const Icon = RESOURCE_ICONS[resource]; return <div key={resource}><Icon size={17} /><b>{count(simulation.resources[resource])}</b><span>{resource.toUpperCase()}</span></div> })}<div><MessageCircle size={17} /><b>{numberMetric(colony.metrics, ['fulfilled_requests'])}</b><span>REQUESTS FULFILLED</span></div></div>
        <div className="colony-game-layout"><div className="colony-scene-column"><div className="colony-scene"><div className="colony-scene-tag"><i />{simulation.paused ? 'TAKING A BREATHER' : 'SMALL JOBS. SHARED AMBITION.'}</div>{sceneFailed ? <div className="colony-scene-fallback"><Globe2 size={38} /><h3>THE CREW IS STILL HERE.</h3><p>3D is unavailable on this device. The roster, board and project controls below still work.</p></div> : <ColonySceneBoundary onFailure={() => setSceneFailed(true)}><Suspense fallback={<div className="colony-scene-fallback" role="status">Opening this shore…</div>}><WorldScene key={side} characters={colony.characters} layoutSeed={colony.world?.layout_seed ?? 4127} selectedId={selectedId} onSelect={chooseAgent} active={visible} reducedMotion={reduced} arrivalIds={[]} onArrived={() => {}} onFailure={() => setSceneFailed(true)} simulation={simulation} selectedProjectId={projectId} onProjectSelect={chooseProject} cameraResetKey={resetKey} followSelected={follow} /></Suspense></ColonySceneBoundary>}<div className="colony-camera-controls">{selectedId && <button onClick={() => setFollow(value => !value)} aria-pressed={follow} aria-label={follow ? 'Stop following resident' : 'Follow selected resident'}><Target size={15} /></button>}<button onClick={() => { setResetKey(value => value + 1); setFollow(false) }} aria-label="Reset island camera"><Maximize2 size={15} /></button></div><p className="colony-map-caption">DRAG TO ORBIT · SCROLL TO ZOOM · SELECT A RESIDENT OR BUILD SITE</p></div>
          <div className="colony-crew"><span>THE CREW</span>{colony.characters.map(character => { const resident = simulation.agents.find(agent => agent.character_id === character.id); return <button key={character.id} onClick={() => chooseAgent(character.id)} aria-pressed={selectedId === character.id} aria-label={`Inspect ${character.display_name}`}><img src={character.image_ref} alt="" /><span>{character.display_name}</span><small>{resident?.persona.role ?? character.object_type}</small></button> })}{!colony.characters.length && <p>No residents on this shore yet. Complete a real-object battle to give both sides a first hero.</p>}</div>
        </div><aside className="colony-inspector" aria-label={agent ? `${agent.display_name} colony details` : 'Island project details'}><div className="colony-inspector-top"><span>{agent ? 'RESIDENT FIELD NOTES' : 'THE NEXT USEFUL THING'}</span>{selectedId || projectId ? <button onClick={() => { setSelectedId(null); setProjectId(null); setFollow(false) }} aria-label="Close selected resident or project"><X size={16} /></button> : <Flag size={15} />}</div>{agent ? <AgentPanel agent={agent} colony={colony} busy={Boolean(busy)} now={Number.isFinite(simulationNow) ? simulationNow : now} onAssign={assignment => void act('assign', { character_id: agent.character_id, assignment })} onThink={() => void act('think', { agent_id: agent.id })} canThink={canThink} onValue={estimated_value_gbp => void act('value', { character_id: agent.character_id, estimated_value_gbp })} /> : project ? <ProjectPanel colony={colony} project={project} busy={Boolean(busy) || !snapshot.enabled} onPriority={() => void act('priority', { project_id: project.id })} /> : <div className="colony-mission"><span>✳</span><h2>A GOOD CREW NEEDS DIFFERENT TALENTS.</h2><p>A bottle brings water. A book helps with plans. The island’s needs give their abilities a purpose.</p><button className="colony-button is-yellow" onClick={onBack}>FIND MORE FIGHTERS <ArrowRight size={15} /></button></div>}</aside></div>
        <div className="colony-project-grid">{simulation.projects.map(item => <button key={item.id} onClick={() => chooseProject(item.id)} aria-pressed={projectId === item.id} className={item.id === simulation.active_project_id ? 'is-priority' : ''}><div><Hammer size={15} /><span>{item.id === simulation.active_project_id ? 'CREW PRIORITY' : 'BLUEPRINT'}</span><b>{percent(item)}%</b></div><h3>{item.name}</h3><span>LEVEL {item.level} / {item.max_level}</span><div className="colony-progress"><i style={{ width: `${percent(item)}%` }} /></div></button>)}</div>
        {(colony.metrics.capability_gaps?.length ?? 0) > 0 && <p className="colony-capability-note"><Lightbulb size={17} /><span><b>A DIFFERENT TALENT COULD HELP.</b> This crew has gaps in {colony.metrics.capability_gaps?.map(human).join(', ')}. Play another clash to bring new object abilities into the mix.</span></p>}
      <div className="colony-value-comparison" aria-label="User-estimated object values"><div><span className="colony-kicker">WHAT’S IN EACH CREW?</span><h3>VALUE IS A QUESTION. NOT A SUPERPOWER.</h3><p>User estimates only. Unknown values stay unknown. Select a resident to add your own estimate.</p></div>{snapshot.colonies.map(item => <div key={item.id} className="colony-value-total"><span>{item.name}</span><b>{pounds(item.metrics.estimated_total_gbp)}</b><small>KNOWN ESTIMATES TOTAL · {item.metrics.valued_residents ?? 0} / {item.characters.length} VALUED</small><p>Mean among valued residents: <strong>{pounds(item.metrics.estimated_mean_gbp)}</strong></p></div>)}</div>
        <div className="colony-social-layout"><SharedBoard key={side} colony={colony} selected={entryId} onSelect={id => { setEntryId(id); evidenceRef.current?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'start' }) }} /><aside className="colony-planner-panel"><span className="colony-kicker"><Sparkles size={13} /> A LITTLE THINKING GOES A LONG WAY.</span><h2>BIG PLANS.<br />SMALL BUDGET.</h2><p>Residents can ask for help, offer a useful job and act on what happened. The shared board keeps the conversation tied to work.</p><div className="colony-budget"><span>AI TURNS TODAY</span><b>{planner?.requests_today ?? 0}<small> / {planner?.max_requests_per_day ?? '—'}</small></b></div>{planner ? <><label className="colony-planner-toggle"><input type="checkbox" checked={planner.enabled} disabled={Boolean(busy) || !planner.configured} onChange={event => void act('planner', { enabled: event.target.checked })} /><span>OCCASIONAL AI DECISIONS</span><b>{planner.enabled ? 'ON' : 'OFF'}</b></label><p className="colony-planner-status" role="status">{!planner.configured ? 'No AI provider configured. Rule-based work remains available.' : !planner.enabled ? 'AI is off. Everyday work continues.' : plannerWorking ? `${activeRun?.agent_name ?? 'A resident'} is planning…` : `Last turn: ${human(planner.last_status ?? 'not requested')}`}</p>{planner.error && <p className="colony-planner-error">{planner.error}</p>}<button className="colony-button is-yellow" disabled={Boolean(busy) || !canThink} onClick={() => void act('think')}>{busy === 'think' || plannerWorking ? <LoaderCircle className="colony-spin" size={15} /> : <MessageCircle size={15} />}{plannerWorking ? 'A RESIDENT IS THINKING…' : 'INVITE ONE RESIDENT TO PLAN'}</button></> : <p className="colony-small-note">AI planner status is unavailable. The island’s saved work remains visible.</p>}<p className="colony-small-note">A turn may use provider quota even if it fails. No model call is made for walking, rendering, polling or each simulation tick.</p><div className="colony-price-stamp"><span>PRICE CHECK</span><b>UNKNOWN.</b><p>No market feed connected.<br />A winning fighter is not a more expensive one.</p></div></aside></div>
        <div ref={evidenceRef}><UnderTheHood key={side} colony={colony} planner={planner} selectedEntry={entryId} onEntrySelect={setEntryId} /></div>
      </>}
      <footer className="colonies-footnote"><span><Box size={13} /> State & messages saved in {snapshot.persistence === 'mongodb' ? 'MongoDB Atlas' : 'temporary server memory'}.</span><span>The local backend runs the agents. Time away is capped; there are no unlimited offline gains.</span><button onClick={onLegacy}>Your original island is preserved <ArrowUpRight size={12} /></button></footer>
    </>}
  </section>
}
