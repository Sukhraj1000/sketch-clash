import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpen, Bot, Box, Check, ChevronRight, Factory, Flag, Globe2, Hammer, Lightbulb, LoaderCircle, Maximize2, MessageCircle, Pause, Play, RefreshCw, ShieldCheck, Sparkles, SwitchCamera, Target, Trophy, Waves, X, Zap } from 'lucide-react'
import { coloniesRequest, colonyMutation, numberMetric } from '../lib/colonies'
import type { Colony, ColonyAgent, ColonyId, ColonyPlanner, ColoniesSnapshot } from '../lib/colonies'
import type { IslandProject, IslandTask } from '../lib/island'
import { LiveConversation, ColonyResearch } from './ColonyResearch'
import { colonyActivity } from '../lib/colonyActivity'
import { CompletedWork, ReceiptEvidence } from './ColonyReceipts'
import { BoardMessageText } from './BoardMessageText'
import { robotEquipment } from './robotEquipment'
import { projectBenefit } from '../lib/projectBenefits'
import './ColoniesView.css'

const WorldScene = lazy(() => import('./WorldScene'))
const ArchitectureGuide = lazy(() => import('./ArchitectureGuide'))
type ScenePresentation = 'island' | 'factory'
const FACTORY_PROJECTS: Record<IslandProject['kind'], string> = { garden: 'Grow shelves', workshop: 'Fabrication bench', beacon: 'Communications terminal', boardwalk: 'Service walkway', assembly: 'Approved assembly fixture' }
const RESOURCE_ICONS = { materials: Box, water: Waves, ideas: Lightbulb, energy: Zap }
const RESOURCE_NAMES = ['materials', 'water', 'ideas', 'energy'] as const
const percent = (project: IslandProject) => project.status === 'complete' ? 100 : Math.min(100, Math.round(project.progress / Math.max(1, project.required_progress) * 100))
const human = (value: string) => value.replaceAll('_', ' ')
const count = (value: number) => Number.isFinite(value) ? Math.round(value).toLocaleString() : '—'
const pounds = (value: number | null | undefined) => value == null ? 'UNKNOWN' : new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 2 }).format(value)
const scalar = (value: unknown) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? String(value) : null
const AGE = (value: string) => { const date = new Date(value); return Number.isFinite(date.getTime()) ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Saved' }
const expectedYield = (task: IslandTask) => [
  ...Object.entries(task.gain).filter(([, amount]) => amount > 0).map(([resource, amount]) => `${count(amount)} ${resource}`),
  ...(task.progress_gain > 0 ? [`${count(task.progress_gain)} build work`] : []),
]
const taskTitle = (agent: ColonyAgent) => agent.task?.kind === 'rest' ? 'Waiting for useful work' : agent.task?.title ?? 'Waiting for a task'


function PlaygroundLink() {
  return <a className="colony-playground-link" href="#/playground">Try the playground <ArrowRight size={14} /></a>
}

function IslandBrief({ colony, onSelect }: { colony: Colony; onSelect: (id: string) => void }) {
  const project = colony.island.projects.find(item => item.id === colony.island.active_project_id)
  const productiveJobs = colony.island.agents.filter(agent => agent.task && agent.task.kind !== 'rest')
  const jobs = (productiveJobs.length ? productiveJobs : colony.island.agents).slice(0, 3)
  const abilities = [...new Set(colony.island.agents.flatMap(agent => agent.capabilities))]
  return <section className="colony-work-brief" aria-label="Island supplies and current work">
    <div className="colony-supply-brief"><span className="colony-kicker"><Box size={14} /> SHARED SUPPLIES</span><div className="colony-supply-list">{RESOURCE_NAMES.map(resource => {
      const Icon = RESOURCE_ICONS[resource]
      const required = project && project.status !== 'complete' ? project.cost_per_action[resource] ?? 0 : 0
      const available = colony.island.resources[resource]
      const full = colony.island.limits.resource_capacity != null && available >= colony.island.limits.resource_capacity
      return <div key={resource}><Icon size={16} /><span><b>{count(available)} <em>{resource}</em></b><small>{full ? 'Storage full · use supplies before gathering more' : required > available ? `Need ${count(required - available)} more for one build action` : required ? `${count(required)} per build action · ready` : 'Stored for the crew'}</small></span></div>
    })}</div><p><b>This crew can:</b> {abilities.length ? abilities.map(human).join(' · ') : 'No resident abilities recorded yet.'}</p></div>
    <div className="colony-next-work"><span className="colony-kicker"><Hammer size={14} /> {colony.island.paused ? 'SAVED WORK · ISLAND PAUSED' : 'CURRENT WORK · LOCAL EXECUTOR'}</span>{jobs.length ? jobs.map(agent => {
      const task = agent.task
      const expected = task && task.kind !== 'rest' ? expectedYield(task) : []
      return <button key={agent.id} onClick={() => onSelect(agent.character_id)}><span><b>{agent.display_name}</b><ArrowUpRight size={13} /></span><strong>{taskTitle(agent)}</strong>{task && task.kind !== 'rest' && <small>{expected.length ? `Planned yield: ${expected.join(' + ')}` : 'Outcome is recorded when this task completes.'}</small>}{task?.scheduling_reason ? <small className="colony-task-reason">{task.action_switched ? 'Changed job: ' : ''}{task.scheduling_reason}</small> : task?.kind === 'rest' && <small>{task.title}</small>}</button>
    }) : <p>{colony.island.agents.length ? 'No productive task is active. Inspect a resident or a project to see available work.' : 'A battle brings objects to each shore. Their abilities determine what the crew can do.'}</p>}<small className="colony-executor-note">Planned yields can change if supplies fill up. Only the saved completion receipt counts as a contribution.</small></div>
  </section>
}

class ColonySceneBoundary extends Component<{ children: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch() { this.props.onFailure() }
  render() { return this.state.failed ? null : this.props.children }
}

function ProjectPanel({ colony, project, busy, onPriority, presentation }: { colony: Colony; project: IslandProject; busy: boolean; onPriority: () => void; presentation: ScenePresentation }) {
  const active = project.id === colony.island.active_project_id
  const effect = projectBenefit(project, colony.island.projects, colony.island.agents)
  const finished = project.status === 'complete'
  const sources = [...new Set(project.assembly?.parts.map(part => colony.characters.find(character => character.id === part.resident_id)?.display_name).filter(Boolean) ?? [])]
  const contributors = [...new Set(colony.island.events.filter(event => event.project_id === project.id && (event.progress_delta ?? 0) > 0).map(event => event.actor_name).filter(Boolean))]
  return <div className="colony-project-inspect">
    <span className="colony-kicker"><Flag size={13} /> {project.level > 0 ? 'BUILT IMPROVEMENT' : active ? 'SAVED ISLAND PRIORITY' : 'ISLAND BLUEPRINT'}</span>
    <h2>{project.name}</h2>
    {presentation === 'factory' && <div className="colony-representation-note"><Factory size={16} /><div><b>{FACTORY_PROJECTS[project.kind]}</b><span>The same saved construction, in industrial form.</span></div></div>}
    <div className={`colony-build-benefit benefit-${effect.status}`}><span>HOW IT HELPS THE CREW</span><strong>{effect.label}</strong><p>{effect.description}</p></div>
    <p>{project.description}</p>
    {sources.length > 0 && <p className="colony-build-origin"><b>Design based on</b>{sources.join(' + ')}</p>}
    {contributors.length > 0 && <p className="colony-build-origin"><b>Recent construction by</b>{contributors.join(' + ')}</p>}
    <div className="colony-progress-label"><b>{finished ? 'Built' : `${percent(project)}%`}</b><span>{finished ? `LEVEL ${project.level} / ${project.max_level}` : `LEVEL ${project.level + 1} ${project.level > 0 ? 'UPGRADE' : 'CONSTRUCTION'}`}</span></div><div className="colony-progress"><i style={{ width: `${percent(project)}%` }} /></div>{project.level > 0 && !finished && <p>Level {project.level} is already built and its unlocked benefit is retained during the next upgrade.</p>}
    {finished ? <p className="colony-built-date"><Check size={14} /> Built{project.completed_at ? ` at ${AGE(project.completed_at)}` : ''} · saved in this world</p> : <div className="colony-cost"><span>ONE BUILD ACTION NEEDS</span><b>{Object.entries(project.cost_per_action).filter(([, amount]) => amount > 0).map(([resource, amount]) => `${amount} ${resource}`).join(' · ')}</b></div>}
    {!finished && <><button className="colony-button is-yellow" disabled={busy || active} onClick={onPriority}>{active ? <Check size={15} /> : <Target size={15} />}{active ? 'CREW IS FOCUSED HERE' : 'OVERRIDE WITH THIS PROJECT'}</button><small>Choosing a priority overrides the crew’s choice.</small></>}
  </div>
}

function BuiltImprovements({ colony, selectedId, onSelect }: { colony: Colony; selectedId: string | null; onSelect: (id: string) => void }) {
  const built = colony.island.projects.filter(project => project.level > 0).sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? '') || a.id.localeCompare(b.id))
  return <section className="colony-built-improvements" aria-label="Built improvements and crew benefits">
    <div><span className="colony-kicker"><Hammer size={13} /> BUILT INTO THIS WORLD</span><b>{built.length} {built.length === 1 ? 'structure' : 'structures'} · {built.reduce((sum, project) => sum + project.level, 0)} completed levels</b></div>
    <p>Select a build to find it on the map and see who it helps.</p>
    <div className="colony-built-strip">{built.map(project => {
      const effect = projectBenefit(project, colony.island.projects, colony.island.agents)
      return <button key={project.id} aria-pressed={project.id === selectedId} onClick={() => onSelect(project.id)}><span><Check size={12} /> LEVEL {project.level}<ArrowUpRight size={13} /></span><strong>{project.name}</strong><small data-benefit={effect.status}>{effect.label}</small></button>
    })}</div>
    {!built.length && <p>No finished structures yet. Outlined sites show what the crew can build.</p>}
  </section>
}

function AgentPanel({ agent, colony, busy, now, onAssign, onThink, canThink, onValue, presentation }: { agent: ColonyAgent; colony: Colony; busy: boolean; now: number; onAssign: (assignment: string) => void; onThink: () => void; canThink: boolean; onValue: (value: number) => void; presentation: ScenePresentation }) {
  const character = colony.characters.find(item => item.id === agent.character_id)
  const [estimate, setEstimate] = useState(character?.estimated_value_gbp?.toString() ?? '')
  useEffect(() => setEstimate(character?.estimated_value_gbp?.toString() ?? ''), [character?.id, character?.estimated_value_gbp])
  const task = agent.task
  const taskEnd = task ? Date.parse(task.ends_at) : 0
  const taskStart = task ? Date.parse(task.started_at) : 0
  const progress = task ? Math.max(0, Math.min(100, (now - taskStart) / Math.max(1, taskEnd - taskStart) * 100)) : 0
  const work = agent.contributions?.work ?? 0
  const delivered = agent.contributions?.cooperative_units ?? 0
  const expected = task && task.kind !== 'rest' ? expectedYield(task) : []
  const output = Object.entries(agent.contributions?.resources ?? {}).filter(([, amount]) => amount > 0).map(([resource, amount]) => `${count(amount)} ${resource}`)
  return <div className="colony-agent-inspect">
    <div className="colony-agent-identity">{character && <img src={character.image_ref} alt={character.object_type} />}<div><span>LEVEL {agent.level} · {agent.xp} XP</span><h2>{agent.display_name}</h2><b>{agent.persona.role}</b></div></div>
    {presentation === 'factory' && <div className="colony-representation-note"><Bot size={17} /><div><b>Original object: {human(agent.object_type)}</b><span>Robot representation · {robotEquipment(agent.allowed_actions).label}</span><small>Allowed work: {agent.allowed_actions.length ? agent.allowed_actions.map(human).join(' · ') : 'No actions recorded yet'}</small></div></div>}
    <p className="colony-motto">“{agent.persona.motto}”</p><div className="colony-abilities">{agent.capabilities.map(capability => <span key={capability}>{human(capability)}</span>)}</div>
    <p className="colony-intent"><Target size={15} /><span>{agent.intent || agent.persona.goal}</span></p>
    <div className="colony-current-task"><span>SAVED TASK · LOCAL EXECUTOR <b>{colony.island.paused ? 'PAUSED' : !task || task.kind === 'rest' ? 'WAITING' : taskEnd <= now ? 'SETTLING' : `${Math.max(0, Math.ceil((taskEnd - now) / 1000))}s`}</b></span><strong>{taskTitle(agent)}</strong>{task && task.kind !== 'rest' && <div className="colony-progress"><i style={{ width: `${progress}%` }} /></div>}{task?.scheduling_reason ? <p>{task.action_switched ? 'Changed job: ' : ''}{task.scheduling_reason}</p> : task?.kind === 'rest' && <p>{task.title}</p>}{expected.length > 0 && <small>Expected on completion: {expected.join(' + ')}. Not credited yet.</small>}</div>
    <label className="colony-assignment">GIVE THEM DIRECTION<select value={agent.assignment} disabled={busy} onChange={event => onAssign(event.target.value)}>{agent.available_assignments.map(assignment => <option key={assignment.id} value={assignment.id}>{assignment.label}</option>)}</select><small>Takes effect after the current job.</small></label>
    <div className="colony-agent-totals" aria-label="Committed contribution totals"><span><b>{count(work)}</b>BUILD WORK COMMITTED</span><span><b>{count(delivered)}</b>CREW REQUEST UNITS DELIVERED</span>{output.length > 0 && <small>Recorded resource output: {output.join(' · ')}</small>}</div>
    <details className="colony-agent-advanced"><summary>AI planning</summary><button className="colony-button" disabled={busy || !canThink} onClick={onThink}><MessageCircle size={15} /> ASK FOR A PLAN</button><small className="colony-ai-note">Starts a council with separate resident turns. Proposals are checked before they affect work.</small></details>
    <details className="colony-memory"><summary>Recent memories</summary>{agent.memory.length ? agent.memory.slice(-3).reverse().map(memory => <p key={memory.id}><span>{memory.kind === 'reflection' ? 'AI INTERPRETATION' : 'RECORDED EVENT'} · {AGE(memory.at)}</span>{memory.text}</p>) : <p>The first completed job starts this resident’s story.</p>}</details>
    <details className="colony-value-editor"><summary>YOUR VALUE ESTIMATE <b>{pounds(character?.estimated_value_gbp)}</b></summary><p>A rough user estimate, not a verified market price. It never changes abilities or rewards.</p><form onSubmit={event => { event.preventDefault(); const amount = Number(estimate); if (estimate.trim() && Number.isFinite(amount) && amount >= 0 && amount <= 1000000) onValue(amount) }}><label>ESTIMATED VALUE (GBP)<input type="number" min="0" max="1000000" step="0.01" required inputMode="decimal" value={estimate} onChange={event => setEstimate(event.target.value)} placeholder="e.g. 12.50" /></label><button className="colony-button" disabled={busy || !estimate.trim() || !Number.isFinite(Number(estimate)) || Number(estimate) < 0 || Number(estimate) > 1000000}>SAVE ESTIMATE</button></form></details>
  </div>
}

const originLabel = (origin: string) => origin === 'model' ? 'GEMINI MESSAGE' : origin === 'player' ? 'PLAYER' : origin === 'executor' ? 'EXECUTOR' : 'GAME RULES'
const messageOrder: Record<string, number> = { request: 0, proposal: 0, offer: 1, support: 1, objection: 1, decision: 2, report: 3 }
function GoalSummary({ colony, busy, aiPaused, onDiscussion, onCrew }: { colony: Colony; busy: boolean; aiPaused: boolean; onDiscussion: () => void; onCrew: () => void }) {
  const plan = colony.planning
  const project = colony.island.projects.find(item => item.id === (plan ? plan.selected_project_id : colony.island.active_project_id))
  const candidate = plan?.candidates.find(item => item.project_id === project?.id)
  const goalComplete = Boolean(project && (project.status === 'complete' || plan?.target_level != null && project.level >= plan.target_level))
  const missing = project ? Object.entries(project.cost_per_action).filter(([resource, amount]) => amount > (colony.island.resources[resource as keyof typeof colony.island.resources] ?? 0)).map(([resource, amount]) => `${amount - (colony.island.resources[resource as keyof typeof colony.island.resources] ?? 0)} ${resource}`) : []
  const reason = plan?.reason || (project ? 'This saved goal guides the local workers. Its proposal and results are recorded on the board.' : aiPaused ? 'Gemini councils are paused. You can inspect available projects or try gathering and building with fixed object roles in the playground.' : 'No project choice has been recorded yet.')
  return <section className="colony-current-goal" aria-label="Current island goal"><div className="colony-goal-title"><span className="colony-kicker"><Flag size={14} />{plan?.mode === 'manual' ? 'YOUR PROJECT OVERRIDE' : 'SAVED ISLAND GOAL'}</span><h2>{project ? `${project.name} · Level ${plan?.target_level ?? Math.min(project.max_level, project.level + 1)}` : plan?.status === 'complete' ? 'All projects complete' : 'No project chosen'}</h2><p>{reason}</p><div className="colony-goal-actions"><button className="colony-text-button" onClick={onDiscussion}>See plan & work history <ArrowRight size={13} /></button>{plan?.mode === 'manual' && <button className="colony-button is-yellow" disabled={busy} onClick={onCrew}>LET THE CREW CHOOSE</button>}</div></div><div className="colony-goal-progress">{project && <><span><b>{goalComplete ? 100 : percent(project)}%</b><small>{goalComplete ? 'COMPLETE' : 'CURRENT BUILD'}</small></span><div className="colony-progress"><i style={{ width: `${goalComplete ? 100 : percent(project)}%` }} /></div></>}<p><b>{colony.island.paused ? 'Paused' : plan?.status === 'complete' ? 'Everything is built' : goalComplete || plan?.status === 'waiting' ? 'Waiting for the next review' : plan?.status === 'blocked' ? 'Needs another ability' : plan?.status === 'gathering' || missing.length ? 'Gathering supplies' : project ? 'Building together' : 'Waiting for the crew'}</b>{colony.island.paused ? 'Resume to continue the work.' : goalComplete ? aiPaused ? 'This goal is finished. New AI reviews are paused.' : 'This goal is finished and ready for a new review.' : candidate?.missing_capabilities.length ? `Missing: ${candidate.missing_capabilities.map(human).join(', ')}.` : missing.length ? `${missing.join(' and ')} needed for the next build action.` : project ? 'The next build action has the supplies it needs.' : plan?.status === 'complete' ? 'All available upgrades are complete.' : 'No project has been chosen yet.'}</p></div></section>
}

function ContributionPanel({ colony, onSelect }: { colony: Colony; onSelect: (id: string) => void }) {
  return <div className="colony-contribution-panel"><h2>Everyone brings something.</h2><p>Only completed work counts here. Select a resident to see their abilities and current task.</p>{colony.island.agents.length ? colony.island.agents.slice(0, 6).map(agent => {
    const resources = Object.entries(agent.contributions?.resources ?? {}).filter(([resource, amount]) => resource !== 'energy' && amount > 0).map(([resource, amount]) => `${count(amount)} ${resource}`)
    const work = agent.contributions?.work ?? 0
    const delivered = agent.contributions?.cooperative_units ?? 0
    return <button key={agent.id} onClick={() => onSelect(agent.character_id)}><span><b>{agent.display_name}</b><ChevronRight size={14} /></span><p>{work || resources.length ? [...(work ? [`${count(work)} build work`] : []), ...resources].join(' · ') : 'First contribution still ahead.'}</p>{delivered > 0 && <small>{count(delivered)} supplies delivered to a crew request</small>}<em>{taskTitle(agent)}</em></button>
  }) : <div className="colony-empty-crew"><p>A real-object battle adds residents to both shores.</p><PlaygroundLink /></div>}<small>Supplies are cumulative output. Build work is committed project progress.</small></div>
}

function CouncilDiscussion({ colony }: { colony: Colony }) {
  const [selected, setSelected] = useState('')
  const councils = [...(colony.council ?? [])].reverse()
  const council = councils.find(item => item.id === selected) ?? councils[0]
  const projectName = (id: string | null) => colony.island.projects.find(item => item.id === id)?.name ?? 'No project'
  return <section className="colony-council" aria-label="Crew project discussion"><div className="colony-section-heading"><div><span className="colony-kicker"><MessageCircle size={14} /> WHAT SHOULD WE BUILD NEXT?</span><h2>The crew’s discussion.</h2></div>{council && <span className="colony-council-source">{council.origin === 'model' ? 'GEMINI COUNCIL' : 'HISTORICAL RULE REVIEW'} · {AGE(council.at)}</span>}</div><p className="colony-discussion-intro">The executor records explicit agreement and checks whether the crew can complete the project. Historical rule reviews retain their original label.</p>{!council ? <div className="colony-empty-council"><MessageCircle size={28} /><h3>No crew review recorded yet.</h3><p>Project reviews appear here once recorded. No council result has been saved for this island.</p><PlaygroundLink /></div> : <><div className="colony-council-opinions">{council.participants.map((opinion, index) => <article className={`council-opinion ${opinion.kind}`} key={`${opinion.agent_id}-${index}`}><div><b>{opinion.actor_name}</b><span>{originLabel(opinion.origin)}</span></div><strong>{opinion.kind === 'objection' ? 'Raises a concern' : `Supports ${projectName(opinion.project_id)}`}</strong><p>{opinion.reason}</p>{opinion.contributes.length > 0 && <small>Can contribute: {opinion.contributes.map(human).join(', ')}</small>}</article>)}</div><div className="colony-council-choice"><Check size={21} /><div><span>RECORDED CHOICE</span><h3>{projectName(council.chosen_project_id)}</h3><p>{council.reason}</p><small>{council.model_message_ids.length ? `${council.model_message_ids.length} published Gemini messages linked to this decision.` : 'This review used game rules. It did not call an AI model.'}</small></div></div><details className="colony-council-alternatives"><summary>Other projects the crew considered</summary>{council.candidates.map(candidate => <div key={candidate.project_id}><b>{candidate.name} · Level {candidate.target_level}</b><span>{candidate.feasible ? 'Within this crew’s abilities' : 'Missing an ability'}</span><p>{candidate.reason}</p></div>)}</details>{councils.length > 1 && <label className="colony-run-selector">EARLIER CREW REVIEWS<select value={council.id} onChange={event => setSelected(event.target.value)}>{councils.map(item => <option key={item.id} value={item.id}>{AGE(item.at)} · {projectName(item.chosen_project_id)}</option>)}</select></label>}</>}</section>
}

function BoardThread({ colony, selected, onClose }: { colony: Colony; selected: string | null; onClose: () => void }) {
  const entry = colony.board.find(item => item.id === selected)
  if (!entry) return null
  const requestId = entry.request_id ?? (entry.kind === 'request' ? entry.id : null)
  const entries = requestId ? colony.board.filter(item => item.id === requestId || item.request_id === requestId) : entry.council_id ? colony.board.filter(item => item.council_id === entry.council_id) : [entry]
  entries.sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || (messageOrder[a.kind] ?? 0) - (messageOrder[b.kind] ?? 0))
  return <section className="colony-board-thread" aria-label="Selected discussion thread"><div className="colony-evidence-heading"><h3>{requestId ? 'A need → a promise → a result' : 'Recorded discussion'}</h3><button onClick={onClose} aria-label="Close discussion thread"><X size={17} /></button></div>{entries.map(item => <article key={item.id}><div><b>{item.actor_name}</b><span>{item.kind.toUpperCase()} · {originLabel(item.origin)}</span></div><BoardMessageText entry={item} /><small>{human(item.status)}{item.receipt_ids.length ? ` · ${item.receipt_ids.length} saved completion receipt${item.receipt_ids.length === 1 ? '' : 's'}` : ' · no completed work claimed'}</small>{item.receipt_ids.map(receiptId => <ReceiptEvidence key={receiptId} receiptId={receiptId} />)}</article>)}</section>
}

function SharedBoard({ colony, selected, onSelect }: { colony: Colony; selected: string | null; onSelect: (id: string) => void }) {
  const [filter, setFilter] = useState<'all' | 'plans' | 'requests' | 'results'>('all')
  const ordered = colony.board.filter(entry => entry.status !== 'expired').sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  const entries = ordered.filter(entry => filter === 'all' || filter === 'plans' && ['proposal', 'support', 'objection', 'decision'].includes(entry.kind) || filter === 'requests' && ['request', 'offer'].includes(entry.kind) || filter === 'results' && entry.kind === 'report').slice(0, 16)
  return <section className="colony-board" aria-label={`${colony.name} shared whiteboard`}><div className="colony-section-heading"><div><span className="colony-kicker"><MessageCircle size={13} /> PLANS TURN INTO WORK</span><h2>Requests, help & results.</h2></div><span className="colony-paper-pin" aria-hidden="true">✳</span></div><div className="colony-board-filters" aria-label="Filter board messages">{(['all', 'plans', 'requests', 'results'] as const).map(kind => <button key={kind} onClick={() => setFilter(kind)} aria-pressed={filter === kind}>{kind === 'all' ? 'Everything' : kind === 'requests' ? 'Requests & offers' : kind === 'plans' ? 'Project plans' : 'Results'}</button>)}</div><div className="colony-board-entries">{entries.length ? entries.map(entry => <button className={`colony-board-note note-${entry.kind} ${selected === entry.id ? 'is-selected' : ''}`} key={entry.id} onClick={() => onSelect(entry.id)} aria-pressed={selected === entry.id}><div><span>{entry.kind.toUpperCase()} <i>{originLabel(entry.origin)}</i></span><time>{AGE(entry.created_at)}</time></div><strong>{entry.actor_name}</strong><BoardMessageText entry={entry} /><footer><span>{human(entry.status)}{entry.remaining !== undefined && entry.status !== 'fulfilled' ? ` · ${entry.remaining} remaining` : ''}</span><b>{entry.receipt_ids.length ? `${entry.receipt_ids.length} RECEIPT${entry.receipt_ids.length === 1 ? '' : 'S'}` : entry.origin === 'model' ? 'MODEL MESSAGE' : entry.status === 'recorded' ? 'SAVED NOTE' : 'OPEN THREAD'} <ChevronRight size={12} /></b></footer></button>) : <div className="colony-empty-board"><MessageCircle size={27} /><h3>No messages here yet.</h3><p>{colony.island.enabled ? 'Saved plans, requests and completed work will appear here.' : 'Start the islands to open the crew’s shared board.'}</p></div>}</div><p className="colony-small-note">Current requests and recent results. Promises are offers; results link to completed work.</p></section>
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
    <div className="colony-machine-content"><div className="colony-run-evidence"><div className="colony-evidence-heading"><h3>{entry ? 'SAVED BOARD THREAD' : LOOP_NODES.find(item => item.id === node)?.title}</h3>{entry && <button onClick={() => onEntrySelect(null)} aria-label="Close board receipt"><X size={15} /></button>}</div>
      {entry ? <><p className="colony-small-note">{request ? 'This thread links a need to its responses. Receipts distinguish delivered work from promises.' : 'A persisted report from the work board.'}</p>{thread.map(item => <div className="colony-thread-entry" key={item.id}><span>{item.actor_name} · {item.kind.toUpperCase()} · {originLabel(item.origin)}</span><BoardMessageText entry={item} /><small>{human(item.status)}{item.receipt_ids.length ? ` · receipts: ${item.receipt_ids.join(', ')}` : ' · no completion receipt yet'}</small></div>)}</> : <>
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
  const [view, setView] = useState<'island' | 'discussion' | 'architecture'>('island')
  const [presentation, setPresentation] = useState<ScenePresentation>('island')
  const [sceneTransition, setSceneTransition] = useState(0)
  const transitionSequence = useRef(0)
  const [side, setSide] = useState<ColonyId>('winners'), [selectedId, setSelectedId] = useState<string | null>(null), [projectId, setProjectId] = useState<string | null>(null), [entryId, setEntryId] = useState<string | null>(null)
  const [sceneFailed, setSceneFailed] = useState(false), [resetKey, setResetKey] = useState(0), [follow, setFollow] = useState(false), [now, setNow] = useState(Date.now()), [visible, setVisible] = useState(!document.hidden), [reduced, setReduced] = useState(false)
  const controller = useRef<AbortController | null>(null), locked = useRef(false), mutationEpoch = useRef(0)
  const threadRef = useRef<HTMLDivElement>(null), tabsRef = useRef<HTMLDivElement>(null)
  const receivedAt = useRef(Date.now())
  const knownResidents = useRef<Set<string> | null>(null)
  const [arrivals, setArrivals] = useState<string[]>([])
  const saveSnapshot = (value: ColoniesSnapshot) => { const ids = new Set(value.colonies.flatMap(c => c.characters.map(a => a.id))); if(knownResidents.current){const fresh=[...ids].filter(id=>!knownResidents.current!.has(id)); if(fresh.length)setArrivals(current=>[...new Set([...current,...fresh])])} knownResidents.current=ids; receivedAt.current = Date.now(); setSnapshot(value) }
  useEffect(() => { const media = matchMedia('(prefers-reduced-motion: reduce)'); const update = () => setReduced(media.matches); const visibility = () => setVisible(!document.hidden); update(); media.addEventListener('change', update); document.addEventListener('visibilitychange', visibility); return () => { media.removeEventListener('change', update); document.removeEventListener('visibilitychange', visibility) } }, [])
  useEffect(() => { const timer = window.setInterval(() => { if (!document.hidden) setNow(Date.now()) }, 1000); return () => window.clearInterval(timer) }, [])
  useEffect(() => {
    if (!sceneTransition) return
    const timer = window.setTimeout(() => setSceneTransition(0), 450)
    return () => window.clearTimeout(timer)
  }, [sceneTransition])
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
      if (kind === 'think') { await colonyMutation('/think', { idempotency_key: key, colony_id: side, ...fields }, signal); setNotice('Council requested. Each resident will read and answer the others on the Discussion board.') }
      else if (kind === 'planner') saveSnapshot(await colonyMutation<ColoniesSnapshot>('/planner', fields, signal))
      else saveSnapshot(await colonyMutation<ColoniesSnapshot>(kind === 'start' ? '/start' : '/command', kind === 'start' ? {} : { idempotency_key: key, colony_id: side, kind, ...fields }, signal))
      if (kind === 'think') saveSnapshot(await coloniesRequest<ColoniesSnapshot>('', {}, signal))
    } catch (error) { if (!signal?.aborted) setActionError((error as Error).message) }
    finally { locked.current = false; if (!signal?.aborted) setBusy('') }
  }
  const colony = snapshot?.colonies.find(item => item.id === side) ?? snapshot?.colonies[0]
  const simulation = colony?.island
  const agent = simulation?.agents.find(item => item.character_id === selectedId)
  const project = simulation?.projects.find(item => item.id === projectId)
  const planner = snapshot?.planner
  const activeRun = planner?.active_run
  const plannerWorking = Boolean(planner?.active_session_id || (activeRun && ['queued', 'running', 'applying', 'retry_wait'].includes(activeRun.status)))
  const aiPaused = Boolean(planner?.paused || planner?.provider_queue?.paused)
  const activity = colonyActivity(colony, planner, aiPaused, now)
  const canThink = Boolean(!aiPaused && snapshot?.enabled && planner?.enabled && planner.configured && !simulation?.paused && !plannerWorking && (!planner.max_requests_per_day || planner.requests_today < planner.max_requests_per_day))
  const simulationNow = simulation?.paused && simulation.paused_at ? Date.parse(simulation.paused_at) : Date.parse(simulation?.server_time ?? '') + (now - receivedAt.current)
  function changePresentation(next: ScenePresentation) {
    if (next === presentation) return
    setPresentation(next)
    setSceneTransition(reduced ? 0 : ++transitionSequence.current)
  }
  function chooseSide(id: ColonyId) { setSide(id); setSelectedId(null); setProjectId(null); setEntryId(null); setFollow(false); setResetKey(value => value + 1) }
  function changeView(next: 'island' | 'discussion' | 'architecture') { setView(next); setEntryId(null); tabsRef.current?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'start' }) }
  function chooseAgent(id: string) { setSelectedId(id); setProjectId(null) }
  function chooseProject(id: string) { setProjectId(id); setSelectedId(null); setFollow(false) }

  return <section className="colonies-screen colonies-focused" aria-label="Sketch Clash twin islands">
    <div className="colonies-heading"><div><span className="colony-kicker"><Globe2 size={13} /> AFTER THE CLASH, BUILD TOGETHER.</span><h1>YOUR ISLAND.<em>THEIR NEXT MOVE.</em></h1></div><button className="colony-button" onClick={onBack}><ArrowLeft size={14} /> BACK TO THE ARCADE</button></div>
    {snapshot && <div className="colony-shore-switch" aria-label="Choose an island">{snapshot.colonies.map(item => <button key={item.id} className={`shore-${item.id}`} onClick={() => chooseSide(item.id)} aria-pressed={item.id === colony?.id}><span className="colony-side-dot" /><b>{item.name}</b><small>{item.characters.length} residents · {numberMetric(item.metrics, ['project_levels'])} build levels</small><Check size={15} className="shore-selected-mark" /></button>)}</div>}
    <nav className="colony-tools-nav" aria-label="More island views"><a className="colony-observatory-link" href="#/observatory"><Sparkles size={16}/> Open the live observatory <ArrowUpRight size={15}/></a><PlaygroundLink /></nav><div className="colony-page-tabs" ref={tabsRef} role="tablist" aria-label="Island views">{(['island', 'discussion', 'architecture'] as const).map((tab, index, tabs) => { const Icon = tab === 'island' ? Globe2 : tab === 'discussion' ? MessageCircle : BookOpen; return <button key={tab} id={`colony-tab-${tab}`} role="tab" aria-selected={view === tab} aria-controls={`colony-view-${tab}`} tabIndex={view === tab ? 0 : -1} onClick={() => changeView(tab)} onKeyDown={event => { let next = index; if (event.key === 'ArrowRight') next = (index + 1) % tabs.length; else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length; else if (event.key === 'Home') next = 0; else if (event.key === 'End') next = tabs.length - 1; else return; event.preventDefault(); setView(tabs[next]); document.getElementById(`colony-tab-${tabs[next]}`)?.focus() }}><Icon size={16} /><span>{tab === 'island' ? 'Island' : tab === 'discussion' ? 'Discussion' : 'Architecture'}</span></button> })}</div>
    <div role="tabpanel" id={`colony-view-${view}`} aria-labelledby={`colony-tab-${view}`} className="colony-page-panel">
      {view === 'architecture' ? <><Suspense fallback={<div className="flow-message">Opening the architecture…</div>}><ArchitectureGuide /></Suspense>{colony && <details className="colony-advanced live-evidence-disclosure"><summary><ShieldCheck size={16} /><span>Inspect live run records<small>Saved state, AI proposals, validation and receipts for {colony.name}</small></span></summary><UnderTheHood key={side} colony={colony} planner={planner} selectedEntry={entryId} onEntrySelect={setEntryId} /></details>}</> : <>
        {loading && !snapshot && <div className="colonies-state" role="status"><span>✳</span><h2>OPENING THE ISLANDS…</h2><p>Loading the crews and their saved work.</p><PlaygroundLink /></div>}
        {!snapshot && !loading && <div className="colonies-state"><Globe2 size={40} /><h2>THE ISLANDS ARE OUT OF REACH.</h2><p role="alert">{error || 'No island data was returned.'}</p><button className="colony-button is-yellow" onClick={() => { setLoading(true); setRetry(value => value + 1) }}><RefreshCw size={15} /> TRY AGAIN</button><button className="colony-text-button" onClick={onLegacy}>OPEN THE ORIGINAL ISLAND <ArrowUpRight size={13} /></button><PlaygroundLink /></div>}
        {snapshot && <>
          {(aiPaused || planner?.error) && <aside className="colony-provider-notice" aria-label="AI availability"><Pause size={19} /><div><b>{aiPaused ? 'Gemini discussions are paused.' : 'The last agent turn did not complete.'}</b><p>{aiPaused ? 'New model conversations are paused by the operator. Saved plans and local simulation work remain available.' : 'The board keeps its saved conversations and work. Residents can stroll between jobs; only labelled tasks add contributions.'}</p><PlaygroundLink /></div></aside>}
          {snapshot.persistence === 'development_memory' && <p className="colony-alert">TEMPORARY PREVIEW · State is lost when the local backend restarts.</p>}
          {(error || actionError) && <p className="colony-alert is-error" role="alert">{actionError || error}<button onClick={() => { setActionError(''); setRetry(value => value + 1) }}>REFRESH</button></p>}
          {notice && <p className="colony-alert" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss island message"><X size={14} /></button></p>}
          {colony && simulation && (view === 'discussion' ? <div className="colony-discussion-view"><div className="colony-discussion-actions"><button className="colony-button is-yellow" disabled={Boolean(busy) || !canThink} onClick={() => void act('think')}>{busy === 'think' ? <LoaderCircle className="colony-spin" size={15} /> : <MessageCircle size={15} />}{busy === 'think' ? 'REQUESTING COUNCIL…' : canThink ? 'GATHER THE CREW' : activity.label.toUpperCase()}</button>{snapshot.enabled && simulation.paused && <button className="colony-button" disabled={Boolean(busy)} onClick={() => void act('resume')}><Play size={15} />{busy === 'resume' ? 'RESUMING…' : 'RESUME ISLAND'}</button>}<span role="status"><b>{activity.label}.</b> {activity.detail}</span></div><LiveConversation key={side} colony={colony} planner={planner} paused={aiPaused} canThink={canThink} /><CompletedWork key={`work-${side}`} colony={colony} /><ColonyResearch colony={colony} /><details className="colony-advanced"><summary>Recorded council decisions & historical reviews</summary><CouncilDiscussion key={side} colony={colony} /></details><SharedBoard key={`board-${side}`} colony={colony} selected={entryId} onSelect={id => { setEntryId(id); window.requestAnimationFrame(() => threadRef.current?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'center' })) }} /><div ref={threadRef}><BoardThread colony={colony} selected={entryId} onClose={() => setEntryId(null)} /></div><div className="colony-discussion-explainer"><Lightbulb size={17} /><div><b>Want a concrete example?</b><p>The Architecture view shows a labelled example from a request for supplies to a completed building.</p><button className="colony-text-button" onClick={() => changeView('architecture')}>See the full explanation <ArrowRight size={13} /></button></div></div></div> : <>
            {!snapshot.enabled && <div className="colony-start-banner"><div><h2>A CREW NEEDS SOMETHING TO BUILD.</h2><p>Start both islands to let residents carry out useful work with their recorded abilities.</p><small>{aiPaused ? 'Gemini discussions are paused. Local task execution remains available.' : planner?.configured ? 'Gemini councils propose projects and experiments. Accepted work runs locally between conversations.' : 'Everyday work uses simulation rules. AI councils are optional.'}</small></div><button className="colony-button is-coral" disabled={Boolean(busy)} onClick={() => void act('start')}>{busy === 'start' ? <LoaderCircle size={17} className="colony-spin" /> : <Play size={17} />} START BOTH ISLANDS</button></div>}
            <div className="colony-toolbar"><p><span className={`colony-side-dot ${side}`} />{simulation.paused ? 'Island simulation is paused.' : colony.planning?.mode === 'manual' ? 'Local workers follow your project choice.' : 'Local workers carry out saved island tasks.'}</p>{snapshot.enabled && <button className="colony-button" disabled={Boolean(busy)} onClick={() => void act(simulation.paused ? 'resume' : 'pause')}>{simulation.paused ? <Play size={13} /> : <Pause size={13} />}{simulation.paused ? 'RESUME' : 'PAUSE'}</button>}</div>
            <div className="colony-game-layout"><div className="colony-scene-column"><div className="colony-presentation-bar"><span>YOUR WORLD</span><button type="button" className="colony-perspective-toggle" role="switch" aria-checked={presentation === 'factory'} aria-label="Show industrial representation" title="Same world. Another perspective." onClick={() => changePresentation(presentation === 'island' ? 'factory' : 'island')}><SwitchCamera size={15} aria-hidden="true" /><span>{presentation === 'factory' ? 'Alternate view' : 'Another perspective'}</span><i className="colony-switch-track" aria-hidden="true"><i /></i></button></div><div className={`colony-scene presentation-${presentation}`} data-presentation={presentation}><div className="colony-scene-tag"><i />{simulation.paused ? 'TAKING A BREATHER' : reduced ? 'REDUCED MOTION · SAVED POSITIONS' : simulation.agents.some(agent => agent.task && agent.task.kind !== 'rest') ? 'CREW AT WORK · SELECT TO FOLLOW' : 'BETWEEN JOBS · CREW STROLLING'}</div>{sceneFailed ? <div className="colony-scene-fallback"><Globe2 size={38} /><h3>THE CREW IS STILL HERE.</h3><p>3D is unavailable on this device. The roster, board and project controls below still work.</p></div> : <ColonySceneBoundary onFailure={() => setSceneFailed(true)}><Suspense fallback={<div className="colony-scene-fallback" role="status">{presentation === 'factory' ? 'Opening the factory…' : 'Opening this shore…'}</div>}><WorldScene key={side} presentation={presentation} characters={colony.characters} layoutSeed={colony.world?.layout_seed ?? 4127} selectedId={selectedId} onSelect={chooseAgent} active={visible} reducedMotion={reduced} arrivalIds={arrivals} onArrived={id => setArrivals(current => current.filter(item => item !== id))} onFailure={() => setSceneFailed(true)} simulation={simulation} selectedProjectId={projectId} onProjectSelect={chooseProject} cameraResetKey={resetKey} followSelected={follow} /></Suspense></ColonySceneBoundary>}{sceneTransition > 0 && !reduced && <div key={sceneTransition} className="colony-scene-transition" aria-hidden="true" onAnimationEnd={() => setSceneTransition(0)} />}<div className="colony-camera-controls">{selectedId && <button onClick={() => setFollow(value => !value)} aria-pressed={follow} aria-label={follow ? 'Stop following resident' : presentation === 'factory' ? 'Follow selected robot' : 'Follow selected resident'}><Target size={15} /></button>}<button onClick={() => { setResetKey(value => value + 1); setFollow(false) }} aria-label={presentation === 'factory' ? 'Reset factory camera' : 'Reset island camera'}><Maximize2 size={15} /></button></div><p className="colony-map-caption">DRAG TO ORBIT · SCROLL TO ZOOM · SELECT A {presentation === 'factory' ? 'ROBOT OR WORKSTATION' : 'RESIDENT OR BUILD SITE'}</p></div>
          <p className="colony-motion-note">{simulation.paused ? 'Simulation paused · movement is stopped.' : reduced ? 'Reduced motion is on · positions update without continuous animation.' : 'Between jobs, residents stroll around the shared square. Task labels show real work; strolling adds no supplies.'}</p><BuiltImprovements colony={colony} selectedId={projectId} onSelect={chooseProject} />
          <div className="colony-crew"><span>THE CREW</span>{colony.characters.map(character => { const resident = simulation.agents.find(agent => agent.character_id === character.id); return <button key={character.id} onClick={() => chooseAgent(character.id)} aria-pressed={selectedId === character.id} aria-label={`Inspect ${character.display_name}`} title={resident?.task?.scheduling_reason || resident?.task?.title || character.object_type}><img src={character.image_ref} alt="" /><span>{character.display_name}</span><small className="colony-crew-task" data-working={Boolean(resident?.task && resident.task.kind !== 'rest' && !simulation.paused)}>{simulation.paused ? 'Paused' : resident ? taskTitle(resident) : 'Waiting for a task'}</small></button> })}{!colony.characters.length && <div className="colony-empty-crew"><p>No residents on this shore yet. Complete a real-object battle to give both sides a first hero.</p><PlaygroundLink /></div>}</div>
        </div><aside className="colony-inspector" aria-label={agent ? `${agent.display_name} colony details` : project ? 'Island project details' : 'Crew contributions'}><div className="colony-inspector-top"><span>{agent ? 'RESIDENT FIELD NOTES' : project ? 'PROJECT DETAILS' : 'WHAT THE CREW HAS DONE'}</span>{selectedId || projectId ? <button onClick={() => { setSelectedId(null); setProjectId(null); setFollow(false) }} aria-label="Close selected resident or project"><X size={16} /></button> : <Flag size={15} />}</div>{agent ? <AgentPanel presentation={presentation} agent={agent} colony={colony} busy={Boolean(busy)} now={Number.isFinite(simulationNow) ? simulationNow : now} onAssign={assignment => void act('assign', { character_id: agent.character_id, assignment })} onThink={() => void act('think', { agent_id: agent.id })} canThink={canThink} onValue={estimated_value_gbp => void act('value', { character_id: agent.character_id, estimated_value_gbp })} /> : project ? <ProjectPanel presentation={presentation} colony={colony} project={project} busy={Boolean(busy) || !snapshot.enabled} onPriority={() => void act('priority', { project_id: project.id })} /> : <ContributionPanel colony={colony} onSelect={chooseAgent} />}</aside></div>

            <details className="colony-advanced colony-supplies-details"><summary><Box size={16} /><span>Current goal, supplies & tasks<small>See the crew’s saved plan and what each job needs</small></span></summary><GoalSummary colony={colony} busy={Boolean(busy)} aiPaused={aiPaused} onDiscussion={() => changeView('discussion')} onCrew={() => void act('council', { mode: 'crew' })} /><IslandBrief colony={colony} onSelect={chooseAgent} /></details>
            <div className="colony-project-heading"><h3>All builds & blueprints</h3><span>Tap one to inspect it. Overriding the crew is optional.</span></div><div className="colony-project-grid">{simulation.projects.map(item => <button key={item.id} onClick={() => chooseProject(item.id)} aria-pressed={projectId === item.id} className={item.id === simulation.active_project_id ? 'is-priority' : ''}><div><Hammer size={15} /><span>{item.id === simulation.active_project_id ? 'CURRENT GOAL' : item.status === 'complete' ? 'COMPLETE' : 'PROJECT'}</span><b>{item.level > 0 && item.status !== 'complete' ? 'UPGRADE ' : ''}{percent(item)}%</b></div><h3>{item.name}</h3><span>LEVEL {item.level} / {item.max_level}</span><div className="colony-progress"><i style={{ width: `${percent(item)}%` }} /></div></button>)}</div>
            <details className="colony-advanced"><summary><Sparkles size={16} /><span>AI settings & value estimates<small>Optional controls and comparison details</small></span></summary><div className="colony-advanced-content"><section className="colony-ai-settings"><h3>Let the crew think together</h3><p>When enabled, Gemini councils propose useful work. New objects change the abilities available to the next discussion.</p>{planner ? <><label className="colony-planner-toggle"><input type="checkbox" checked={planner.enabled} disabled={Boolean(busy) || !planner.configured || aiPaused} onChange={event => void act('planner', { enabled: event.target.checked })} /><span>AGENT COUNCILS</span><b>{aiPaused ? 'PAUSED' : planner.enabled ? 'ON' : 'OFF'}</b></label><p className="colony-planner-status" role="status">{activity.label}. {activity.detail} · {planner.requests_today} turns today{planner.max_requests_per_day ? ` · ${planner.max_requests_per_day} configured limit` : ' · provider quota applies'}.</p>{planner.error && <details className="colony-provider-detail"><summary>Last saved provider error</summary><p className="colony-planner-error">{planner.error}</p></details>}<button className="colony-button is-yellow" disabled={Boolean(busy) || !canThink} onClick={() => void act('think')}>{busy === 'think' ? <LoaderCircle className="colony-spin" size={15} /> : <MessageCircle size={15} />}{busy === 'think' ? 'REQUESTING COUNCIL…' : canThink ? 'GATHER THE CREW' : activity.label.toUpperCase()}</button></> : <p>AI status is unavailable.</p>}<small>A failed call may still use provider quota. No calls are made for walking or rendering.</small></section><section className="colony-estimates"><h3>User estimates, not market prices</h3><p>Select a resident to add a rough GBP estimate. Estimates never change abilities or rewards.</p><div className="colony-estimate-pair">{snapshot.colonies.map(item => <div key={item.id}><b>{item.name}</b><strong>{pounds(item.metrics.estimated_total_gbp)}</strong><small>{item.metrics.valued_residents ?? 0} / {item.characters.length} residents valued · known estimates total</small><p>Mean: {pounds(item.metrics.estimated_mean_gbp)}</p><p>Sourced comparables: <b>{pounds(item.metrics.comparable_total_gbp)}</b></p><small>{item.metrics.comparable_residents ?? 0} / {item.characters.length} residents with saved eBay asking-price receipts. Category comparisons, not appraisals; kept separate from your estimates.</small></div>)}</div><small>Crews differ in size, abilities and active time. This is a game comparison, not a controlled experiment.</small></section></div></details>
          </>)}
        </>}
      </>}
    </div>
    <footer className="colonies-footnote"><span>{snapshot?.persistence === 'mongodb' ? 'Saved in MongoDB Atlas.' : snapshot ? 'Temporary server memory.' : 'Local game.'} Agents work while the local backend is awake.</span><button onClick={onLegacy}>Open the original island <ArrowUpRight size={12} /></button></footer>
  </section>
}
