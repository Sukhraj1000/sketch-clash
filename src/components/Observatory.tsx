import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Activity, ArrowLeft, ArrowRight, BrainCircuit, CheckCheck, ChevronRight, Database, FlaskConical, GitBranch, History, MessageSquare, Pause, Play, Radio, RefreshCw, ShieldCheck, SkipForward, Sparkles, Timer, WifiOff, X } from 'lucide-react'
import { coloniesRequest } from '../lib/colonies'
import type { ColoniesSnapshot } from '../lib/colonies'
import { eventCategory, eventLabel, mergeEvents, observatory } from '../lib/observatory'
import type { AgentEvent, CouncilSession, ObservatoryMetrics, TraceDetail, RequestPacing, RequestPaceMode, Contributions, EventEvidence } from '../lib/observatory'
import './Observatory.css'
import { receiptDecision, receiptEvidenceLabel, receiptResources, receiptRows } from '../lib/receiptPresentation'

const time = (value: string) => new Date(value).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})
const short = (value?: string | null) => value ? `${value.slice(0, 8)}…` : '—'
const iconFor = (event: AgentEvent) => ({model: Sparkles, learning: FlaskConical, discussion: MessageSquare, work: CheckCheck}[eventCategory(event)])
const displayValue = (value: unknown) => value == null ? 'Not recorded' : typeof value === 'string' ? value : JSON.stringify(value, null, 2)
const resourceSummary = (values: unknown, prefix = '') => { const ledger = receiptResources(values); return ledger === null ? 'Not recorded' : Object.entries(ledger).filter(([, value]) => value !== 0).map(([key, value]) => `${value < 0 ? '' : prefix}${value} ${key}`).join(' · ') || 'None' }

const count = (value?: number) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : '—'
const guardWaitLabels: Record<string, string> = {
  ai_paused: 'Gemini activity paused',
  local_dispatch_spacing: 'Spacing requests',
  local_minute_cap: 'Local minute limit reached',
  local_daily_cap: 'Local 24-hour limit reached',
  local_concurrency: 'Waiting for the active request',
  provider_cooldown: 'Honouring a provider cooldown',
}

export default function Observatory({ onBack, aiPaused=false }: { onBack?: () => void; aiPaused?: boolean }) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [sessionEvents, setSessionEvents] = useState<AgentEvent[]>([])
  const [snapshot, setSnapshot] = useState<ColoniesSnapshot | null>(null)
  const [pacing, setPacing] = useState<RequestPacing | null>(null)
  const [paceSaving, setPaceSaving] = useState(false)
  const [paceError, setPaceError] = useState('')
  const paceRevision = useRef(0)
  const [contributions, setContributions] = useState<Contributions | null>(null)
  const [contributionError, setContributionError] = useState('')
  const [evidence, setEvidence] = useState<EventEvidence | null>(null)
  const [evidenceError, setEvidenceError] = useState('')
  const [receiptId, setReceiptId] = useState<string | null>(null)
  const inspectorRef = useRef<HTMLElement>(null)
  const [metrics, setMetrics] = useState<ObservatoryMetrics | null>(null)
  const [sessions, setSessions] = useState<CouncilSession[]>([])
  const [island, setIsland] = useState('all')
  const [session, setSession] = useState('all')
  const [category, setCategory] = useState('all')
  const [connection, setConnection] = useState('connecting')
  const [transport, setTransport] = useState('connecting')
  const [persistence, setPersistence] = useState('')
  const [error, setError] = useState('')
  const [mode, setMode] = useState<'live' | 'replay'>('live')
  const [paused, setPaused] = useState(false)
  const [position, setPosition] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [selected, setSelected] = useState<AgentEvent | null>(null)
  const [trace, setTrace] = useState<TraceDetail | null>(null)
  const [traceError, setTraceError] = useState('')
  const traceGeneration = useRef(0)
  const [pulse, setPulse] = useState<AgentEvent | null>(null)
  const [retry, setRetry] = useState(0)
  const cursor = useRef(0)
  const seen = useRef(new Set<string>())
  const modeRef = useRef(mode)
  const pausedRef = useRef(paused)
  const reduceMotion = useReducedMotion()
  modeRef.current = mode
  pausedRef.current = paused

  useEffect(() => {
    const controller = new AbortController()
    let source: EventSource | null = null
    let cancelled = false
    async function connect() {
      setConnection('connecting')
      try {
        const batch = await observatory.events(controller.signal)
        if (cancelled) return
        setEvents(batch.events)
        cursor.current = batch.cursor
        seen.current = new Set(batch.events.map(e => e.id))
        setTransport(batch.transport)
        setPersistence(batch.persistence)
        setError(batch.stream_error || '')
        source = new EventSource(`/api/observatory/stream?after=${batch.cursor}`)
        source.onopen = () => setConnection('connected')
        source.onerror = () => setConnection('reconnecting')
        source.addEventListener('agent', message => {
          const event = JSON.parse((message as MessageEvent).data) as AgentEvent
          cursor.current = Math.max(cursor.current, event.sequence)
          if (seen.current.has(event.id)) return
          seen.current.add(event.id)
          if (seen.current.size > 1200) seen.current = new Set([...seen.current].slice(-600))
          setEvents(current => mergeEvents(current, [event]))
          if (modeRef.current === 'live' && !pausedRef.current) setPulse(event)
        })
        source.addEventListener('status', message => {
          const status = JSON.parse((message as MessageEvent).data)
          setTransport(status.transport)
          setError(status.stream_error || '')
        })
        source.addEventListener('resync', () => {
          source?.close()
          setError('Reconnecting at the saved event boundary…')
          setRetry(value => value + 1)
        })
      } catch (problem) {
        if (!cancelled) { setConnection('disconnected'); setError(problem instanceof Error ? problem.message : 'The local Observatory is unavailable.') }
      }
    }
    void connect()
    return () => { cancelled = true; controller.abort(); source?.close() }
  }, [retry])

  useEffect(() => {
    const controller = new AbortController()
    let busy = false
    const refresh = async () => {
      if (busy) return
      busy = true
      const revision = paceRevision.current
      const result = await Promise.allSettled([
        coloniesRequest<ColoniesSnapshot>('', {}, controller.signal),
        observatory.metrics(island, controller.signal), observatory.sessions(controller.signal),
        observatory.pacing(controller.signal), observatory.contributions(controller.signal),
      ])
      if (!controller.signal.aborted) {
        if (result[0].status === 'fulfilled') setSnapshot(result[0].value)
        if (result[1].status === 'fulfilled') setMetrics(result[1].value)
        if (result[2].status === 'fulfilled') setSessions(result[2].value.sessions)
        if (revision === paceRevision.current) {
          if (result[3].status === 'fulfilled') {setPacing(result[3].value); setPaceError('')}
          else setPaceError('Request pace is unavailable. The existing backend limits remain in force.')
        }
        if (result[4].status === 'fulfilled') {setContributions(result[4].value); setContributionError('')}
        else setContributionError('Saved contribution totals are unavailable. Last loaded totals may be out of date.')
      }
      busy = false
    }
    void refresh()
    const interval = window.setInterval(refresh, 8000)
    return () => { controller.abort(); window.clearInterval(interval) }
  }, [island, retry])

  useEffect(() => {
    setSessionEvents([])
    if (session === 'all') return
    const controller = new AbortController()
    void observatory.sessionEvents(session, controller.signal).then(batch => {
      if (!controller.signal.aborted) setSessionEvents(batch.events)
    }).catch(problem => {
      if (!controller.signal.aborted) setError(problem instanceof Error ? problem.message : 'Saved session events are unavailable.')
    })
    return () => controller.abort()
  }, [session])
  const filtered = useMemo(() => {
    const source = session === 'all' ? events : mergeEvents(sessionEvents, events.filter(event => event.session_id === session))
    return source.filter(event => (island === 'all' || event.island_id === island) && (category === 'all' || eventCategory(event) === category))
  }, [events, sessionEvents, island, session, category])
  const pendingActors = useMemo(() => {
    const pending = new Map<string, AgentEvent>()
    for (const event of events) {
      const runId = String(event.data.run_id || `${event.session_id}:${event.actor_id}`)
      if (event.kind === 'model.requested') pending.set(runId, event)
      else if (/^model\.(completed|failed|throttled)$/.test(event.kind)) pending.delete(runId)
    }
    return [...pending.values()].filter(event => Date.now() - Date.parse(event.created_at) < 180000)
  }, [events, snapshot])
  const replayEvent = filtered[Math.min(position, Math.max(0, filtered.length - 1))]
  const active = mode === 'replay' ? replayEvent : pulse
  const recent = mode === 'replay' ? filtered.slice(0, position + 1).slice(-40).reverse() : filtered.slice(-40).reverse()

  useEffect(() => { setPosition(0); setPulse(null) }, [island, session, category])
  useEffect(() => {
    if (mode !== 'replay' || paused || filtered.length === 0) return
    const interval = window.setInterval(() => setPosition(current => {
      if (current >= filtered.length - 1) { setPaused(true); return current }
      return current + 1
    }), 1800 / speed)
    return () => window.clearInterval(interval)
  }, [mode, paused, speed, filtered.length])
  useEffect(() => {
    if (!pulse) return
    const timer = window.setTimeout(() => setPulse(null), 5000)
    return () => window.clearTimeout(timer)
  }, [pulse])
  useEffect(() => {
    const generation = ++traceGeneration.current
    setTrace(null); setTraceError('')
    if (!selected?.trace_id) return
    const controller = new AbortController()
    let attempts = 0
    let timer: number | undefined
    const read = () => {
      if (generation !== traceGeneration.current) return
      void observatory.trace(selected.trace_id!, controller.signal).then(result => {
      if (controller.signal.aborted || generation !== traceGeneration.current) return
      setTrace(result)
      // The domain event commits first; OTel exports asynchronously afterwards.
      if (!result.spans.length && ++attempts < 24) timer = window.setTimeout(read, 5000)
    }).catch(problem => {
      if (!controller.signal.aborted && generation === traceGeneration.current) setTraceError(problem instanceof Error ? problem.message : 'Trace unavailable')
    })
    }
    read()
    return () => {controller.abort(); window.clearTimeout(timer)}
  }, [selected])

  useEffect(() => {
    setEvidence(null); setEvidenceError('')
    if (!selected && !receiptId) return
    const controller = new AbortController()
    const request = receiptId ? observatory.receiptEvidence(receiptId, controller.signal) : observatory.evidence(selected!.id, controller.signal)
    void request.then(result => {if (!controller.signal.aborted) setEvidence(result)}).catch(problem => {
      if (!controller.signal.aborted) setEvidenceError(problem instanceof Error ? problem.message : 'Saved evidence is unavailable.')
    })
    return () => controller.abort()
  }, [selected, receiptId])

  const inspectEvent = (event: AgentEvent) => {traceGeneration.current += 1; setEvidence(null); setReceiptId(null); setSelected(event)}
  const inspectReceipt = (id: string) => {
    traceGeneration.current += 1; setEvidence(null); setSelected(null); setReceiptId(id)
    window.requestAnimationFrame(() => inspectorRef.current?.scrollIntoView({behavior: reduceMotion ? 'auto' : 'smooth', block: 'start'}))
  }
  const closeInspector = () => {traceGeneration.current += 1; setSelected(null); setReceiptId(null)}
  const followTrace = (id: string) => {
    const generation = ++traceGeneration.current
    setTraceError('')
    void observatory.trace(id).then(result => {if (generation === traceGeneration.current) setTrace(result)}).catch(problem => {
      if (generation === traceGeneration.current) setTraceError(problem instanceof Error ? problem.message : 'Trace unavailable')
    })
  }
  const changePace = async (next: RequestPaceMode) => {
    if (paceSaving || next === pacing?.mode) return
    paceRevision.current += 1; setPaceSaving(true); setPaceError('')
    try {setPacing(await observatory.setPacing(next))}
    catch (problem) {setPaceError(problem instanceof Error ? problem.message : 'Could not save request pace.')}
    finally {paceRevision.current += 1; setPaceSaving(false)}
  }

  const selectMode = useCallback((next: 'live' | 'replay') => {
    setMode(next); setPaused(next === 'replay'); setPulse(null); setPosition(0)
  }, [])
  const current = active && (island === 'all' || active.island_id === island) && (session === 'all' || active.session_id === session) && (category === 'all' || eventCategory(active) === category) ? active : null
  const reasoningPaused = aiPaused || Boolean(snapshot?.planner?.paused)
  const reasoningIssue = snapshot?.planner?.error
  const providerQueue = snapshot?.planner?.provider_queue
  const localLimits = providerQueue?.local_limits
  const localUsage = providerQueue?.local_usage
  const guardPaused = reasoningPaused || providerQueue?.paused
  const guardWait = providerQueue?.wait_reason
  const guardStatus = guardPaused ? 'Gemini activity paused' : guardWait ? (guardWaitLabels[guardWait] || 'Waiting before dispatch') : 'Ready within local limits'
  const totalTokens = metrics?.totals.total_tokens || (metrics?.totals.input_tokens || 0) + (metrics?.totals.output_tokens || 0)
  const modelRequests = Object.entries(metrics?.event_counts || {}).filter(([key]) => /model.requested/.test(key)).reduce((sum, [, count]) => sum + count, 0)
  const experiments = Object.entries(metrics?.event_counts || {}).filter(([key]) => /experiment.completed/.test(key)).reduce((sum, [, count]) => sum + count, 0)
  const packetSide = current?.island_id === 'losers' ? 1 : -1
  const packetPath = current?.kind === 'model.requested'
    ? {x: [packetSide * 270, packetSide * 140, 0], y: [-25, -95, -150]}
    : current?.kind === 'model.completed'
      ? {x: [0, 0, 0], y: [-150, -65, 18]}
      : current?.kind === 'task.completed' || current?.kind === 'experiment.completed'
        ? {x: [0, 0, 0], y: [110, 60, 18]}
        : {x: [packetSide * 270, packetSide * 140, 0], y: [-25, 10, 18]}
  const traceDuration = trace?.spans.length ? Math.max(...trace.spans.map(span => Date.parse(span.created_at) + span.duration_ms)) - Math.min(...trace.spans.map(span => Date.parse(span.created_at))) : 1
  const selectedReceipt = receiptRows(evidence)[0]
  const contributionIslands = contributions?.islands.filter(item => island === 'all' || item.id === island) || []
  const traceStart = trace?.spans.length ? Math.min(...trace.spans.map(span => Date.parse(span.created_at))) : 0

  return <main className="observatory">
    <header className="obs-heading">
      <div><button className="obs-back" onClick={() => onBack ? onBack() : window.location.assign('/')}><ArrowLeft size={14}/> BACK TO THE ISLANDS</button><div className="obs-eyebrow"><span/> LOCAL ENGINE / LIVE EVIDENCE</div><h1>THE OBSERVATORY<span>Inside the little minds.</span></h1><p>Follow a public plan through a checked action to a saved result. Every pulse comes from a recorded event.</p></div>
      <div className="obs-engine-status"><span className={`obs-status-dot ${connection === 'connected' ? 'is-on' : ''}`}/><div><strong>{connection === 'connected' ? 'ENGINE CONNECTED' : connection.toUpperCase()}</strong><small>{persistence === 'development_memory' ? 'Development memory · resets on restart' : transport === 'atlas_change_stream' ? 'MongoDB Atlas · Change Stream' : transport === 'atlas_polling' ? 'MongoDB Atlas · committed-event polling' : 'Connecting to persistent events'}</small></div><Database size={23}/></div>
    </header>

    <section className="obs-controls" aria-label="Observatory controls">
      <div className="obs-mode"><button aria-pressed={mode === 'live'} onClick={() => selectMode('live')}><Radio size={14}/> LIVE</button><button aria-pressed={mode === 'replay'} onClick={() => selectMode('replay')}><History size={14}/> REPLAY</button></div>
      <label><span>ISLAND</span><select value={island} onChange={e => {setIsland(e.target.value);setSession('all')}}><option value="all">Both shores</option><option value="winners">Winner Island</option><option value="losers">Loser Island</option></select></label>
      <label className="obs-session-select"><span>COUNCIL</span><select value={session} onChange={e => setSession(e.target.value)}><option value="all">Every discussion</option>{sessions.filter(item => island === 'all' || (item.island_id || item.colony_id) === island).map(item => <option key={item.id} value={item.id}>{time(item.created_at)} · {item.status} · {short(item.id)}</option>)}</select></label>
      <div className="obs-playback"><button onClick={() => setPaused(value => !value)} aria-label={paused ? 'Resume visualization' : 'Pause visualization'}>{paused ? <Play size={16}/> : <Pause size={16}/>}</button>{mode === 'replay' && <><button disabled={position >= filtered.length - 1} onClick={() => {setPaused(true);setPosition(value => Math.min(filtered.length - 1, value + 1))}} aria-label="Next recorded event"><SkipForward size={16}/></button><select aria-label="Playback speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value={0.5}>½×</option><option value={1}>1×</option><option value={2}>2×</option></select></>}<span>{mode === 'replay' ? `${Math.min(position + 1, filtered.length)} / ${filtered.length} saved events` : paused ? 'Motion paused · engine still runs' : 'Only real events animate'}</span></div>
    </section>
    {error && <div className="obs-notice" role="status"><WifiOff size={15}/><span>{error}</span><button onClick={() => setRetry(value => value + 1)}><RefreshCw size={13}/> Reconnect</button></div>}

    {reasoningIssue && !reasoningPaused && <div className="obs-notice obs-model-notice" role="status"><Sparkles size={15}/><span><strong>Last recorded provider issue.</strong> {reasoningIssue}</span><button onClick={() => setCategory('model')}>Inspect model events <ArrowRight size={13}/></button></div>}

    <section className="obs-pace" aria-label="Gemini request pace">
      <div className="obs-pace-intro"><span className="obs-eyebrow"><Timer size={13}/> ACTUAL API REQUEST PACE</span><h2>SET THE THINKING TEMPO</h2><p>Spaces out real Gemini requests across all workers. Local actions finish at their own pace.</p></div>
      <div className="obs-pace-options" aria-label="Choose request pace">{pacing?.options.map(option => <button key={option.mode} aria-pressed={pacing.mode === option.mode} disabled={paceSaving} onClick={() => void changePace(option.mode)}><strong>{option.label}</strong><span>Up to {option.requests_per_minute} / minute</span><small>At least {option.min_dispatch_interval_seconds}s apart</small></button>)}{!pacing && <p>Reading the saved request pace…</p>}</div>
      <div className="obs-pace-state" role="status">{paceSaving ? 'Saving the request pace…' : paceError ? paceError : pacing ? <><b>{pacing.paused || reasoningPaused ? 'Gemini remains paused.' : `Admission ceiling: ${pacing.effective_requests_per_minute} requests per minute.`}</b> {pacing.paused || reasoningPaused ? 'The selected pace will apply when Gemini is resumed.' : 'This sets a maximum; work demand and safety limits may send fewer requests.'} <span>Daily request cap, concurrency limits and provider cooldowns still apply. This does not change replay speed.</span></> : 'Existing safety limits remain in force.'}</div>
    </section>

    {localLimits && <section className="obs-guardrails" aria-label="Current local Gemini safeguards">
      <header><span><ShieldCheck size={14}/> GEMINI SAFEGUARDS</span><small>Current backend state · also shown during replay</small></header>
      <dl>
        <div><dt>REQUEST PACE</dt><dd>{count(pacing?.effective_requests_per_minute ?? localLimits.requests_per_minute)}<span> / minute</span></dd><small>{count(localUsage?.requests_last_minute)} dispatched in the last minute · at least {count(pacing?.options.find(option => option.mode === pacing.mode)?.min_dispatch_interval_seconds ?? localLimits.min_dispatch_interval_seconds)}s apart</small></div>
        <div><dt>ROLLING 24 HOURS</dt><dd>{count(localUsage?.requests_last_24_hours)}<span> / {count(localLimits.requests_per_day)} requests</span></dd><small>{count(localUsage?.requests_remaining_day)} local requests remaining</small></div>
        <div><dt>SHARED QUEUE</dt><dd>{count(localLimits.concurrency)}<span> at a time</span></dd><small>{count(providerQueue?.active)} active · {count(providerQueue?.waiting)} waiting · {count(localLimits.max_pending)} waiting slots</small></div>
      </dl>
      <p className="obs-guard-status"><span className={`obs-status-dot ${!guardPaused && !guardWait ? 'is-on' : ''}`}/><strong>{guardStatus}</strong>{!guardPaused && (providerQueue?.dispatch_wait_seconds || 0) > 0 && <span>Next admission check in about {count(Math.ceil(providerQueue!.dispatch_wait_seconds!))}s</span>}</p>
      <p className="obs-guard-note">These are application safety limits, not Google quotas. Usage counters reset when the backend restarts.</p>
      {providerQueue?.last_local_error?.message && <p className="obs-guard-note"><b>Last local limit event:</b> {providerQueue.last_local_error.message}</p>}
    </section>}

    <section className="obs-reading-guide" aria-label="What the activity means">
      <div><span>01</span><p><b>THE PLAN</b><small>{reasoningPaused?'Gemini paused. Existing discussions remain readable.':'Resident messages are proposals, not completed work.'}</small></p></div>
      <div><span>02</span><p><b>THE ACTION</b><small>Local rules check abilities and spend available resources.</small></p></div>
      <div><span>03</span><p><b>THE PROOF</b><small>A receipt records the result; Atlas saves the memory.</small></p></div>
      <a href="#/playground">TRY IT IN THE PLAYGROUND <ArrowRight size={14}/></a>
    </section>
    <section className={`obs-machine ${mode === 'replay' ? 'is-replay' : ''}`} aria-label="Live agent and MongoDB activity">
      <div className="obs-machine-top"><span><Activity size={12}/> {mode === 'replay' ? 'RECORDED PLAYBACK' : 'THE LIVING SYSTEM'}</span><span>{current ? time(current.created_at) : 'Waiting for the next committed event'}</span></div>
      <div className="obs-system-grid" aria-hidden="true"/>
      <svg className="obs-wires" viewBox="0 0 1100 440" preserveAspectRatio="none" aria-hidden="true"><path d="M210 210 C340 210 350 260 475 260 M890 210 C760 210 750 260 625 260"/><path d="M550 85 L550 200 M550 310 L550 380"/></svg>
      <div className={`obs-model-node ${(!reasoningPaused || mode === 'replay') && ((current && eventCategory(current) === 'model') || (mode === 'live' && pendingActors.length)) ? 'is-active' : ''}`}><Sparkles size={18}/><div><b>GEMINI</b><span>{mode === 'live' && reasoningPaused ? 'Paused · local work continues' : mode === 'live' && pendingActors.length ? `${pendingActors.length} model ${pendingActors.length === 1 ? 'turn' : 'turns'} queued / processing` : current && eventCategory(current) === 'model' ? eventLabel(current.kind) : reasoningIssue ? 'Last provider issue recorded' : 'Proposes · discusses · reflects'}</span></div><i className={(!reasoningPaused || mode === 'replay') && ((current && eventCategory(current) === 'model') || (mode === 'live' && pendingActors.length)) ? 'is-on' : ''}/></div>
      <div className="obs-islands">
        {(['winners', 'losers'] as const).map(side => {
          const colony = snapshot?.colonies.find(item => item.id === side)
          const visibleEvents = mode === 'replay' ? filtered.slice(0, position + 1) : events
          const last = [...visibleEvents].reverse().find(item => item.island_id === side)
          return <section className={`obs-shore obs-shore-${side} ${island !== 'all' && island !== side ? 'is-dim' : ''}`} key={side}><header><span>{side === 'winners' ? '01' : '02'}</span><div><h2>{side === 'winners' ? 'WINNER ISLAND' : 'LOSER ISLAND'}</h2><p>{colony?.characters.length || 0} {mode === 'replay' ? 'current residents · replaying events' : 'residents · separate memories'}</p></div></header><div className="obs-agent-roster">{colony?.characters.slice(0, 6).map(character => {
            const agent = colony.island.agents.find(item => item.character_id === character.id)
            const speaking = Boolean(current && (current.actor_id === agent?.id || current.actor_id === character.id)) || (mode === 'live' && pendingActors.some(item => item.actor_id === agent?.id || item.actor_id === character.id))
            return <button className={`obs-resident ${speaking ? 'is-speaking' : ''}`} key={character.id} onClick={() => { const event = [...events].reverse().find(item => item.actor_id === agent?.id || item.actor_id === character.id); if (event) inspectEvent(event) }} title={character.display_name}><div><img src={character.image_ref} alt={character.object_type}/>{speaking && <MessageSquare size={13}/>}</div><b>{character.object_type}</b><small>{agent?.persona.role || 'Resident'}</small></button>
          })}{!colony?.characters.length && <p className="obs-empty-crew">New objects arrive here after a battle. Their attributes change what the crew can attempt.</p>}</div><div className="obs-shore-base"><span/><span/><span/></div><footer><BrainCircuit size={14}/><p>{last?.message || 'No committed activity recorded for this crew yet.'}</p></footer></section>
        })}
      </div>
      <button className={`obs-memory-core ${current ? 'is-active' : ''}`} onClick={() => current && inspectEvent(current)} aria-label="Inspect the current committed event"><div className="obs-memory-disc"><Database size={34}/><span>ATLAS</span></div><div className="obs-memory-shelf"/><div className="obs-memory-shelf"/><strong>SHARED MEMORY</strong><small>State · discussion · evidence</small><span className="obs-commit-label"><CheckCheck size={12}/> {current ? 'EVENT COMMITTED' : 'DURABLE WHEN SAVED'}</span></button>
      <div className="obs-validator"><ShieldCheck size={17}/><span>LOCAL SIMULATOR</span><small>Validates abilities, costs and outcomes</small></div>
      <AnimatePresence>{current && !paused && <motion.div key={`${mode}-${current.id}`} className={`obs-packet obs-packet-${eventCategory(current)}`} initial={reduceMotion ? {opacity:0} : {x:packetPath.x[0], y:packetPath.y[0], opacity:0, scale:.7}} animate={reduceMotion ? {opacity:1} : {x:packetPath.x, y:packetPath.y, opacity:[0,1,1,0], scale:[.7,1,1]}} transition={{duration:reduceMotion ? .1 : 2.1}} exit={{opacity:0}}><CheckCheck size={13}/><span>{eventLabel(current.kind)}</span></motion.div>}</AnimatePresence>
      <div className="obs-machine-caption"><GitBranch size={13}/><span>Gemini proposes when enabled. Local workers validate and execute. Atlas preserves the evidence.</span></div>
    </section>

    <section className="obs-metrics" aria-label="Measured activity over the last hour"><div><span><Sparkles size={13}/> MODEL REQUESTS</span><strong>{metrics ? modelRequests : '—'}</strong><small>Recorded in the last hour{metrics?.event_counts_sampled ? ' · sampled' : ''}</small></div><div><span><BrainCircuit size={13}/> MODEL TOKENS</span><strong>{metrics ? totalTokens.toLocaleString() : '—'}</strong><small>Provider-reported token usage</small></div><div><span><FlaskConical size={13}/> EXPERIMENTS</span><strong>{metrics ? experiments : '—'}</strong><small>Completed with recorded evidence</small></div><div><span><Timer size={13}/> TRACE LATENCY</span><strong>{metrics ? `${metrics.totals.mean_duration_ms.toLocaleString()} ms` : '—'}</strong><small>Mean across instrumented operations</small></div><div><span><Database size={13}/> STORED SPANS</span><strong>{metrics ? metrics.totals.count.toLocaleString() : '—'}</strong><small>{metrics?.totals.errors || 0} error spans · {metrics?.dropped_spans || 0} export drops</small></div></section>

    <section className="obs-contributions" aria-label="Character contributions from saved receipts">
      <header><div><span className="obs-eyebrow">MEASURED ISLAND EFFECTS</span><h2>WHO CHANGED THE ISLAND?</h2><p>Completed actions in the last {contributions?.window_minutes || 60} minutes, counted from saved receipts. A completed action only counts as useful here if it adds stock or project work.</p></div><span className="obs-contribution-window">{contributions ? `${contributions.receipt_count} receipts · through ${time(contributions.to)}` : 'Reading saved receipts…'}<small>Current state · also shown during replay</small></span></header>
      {contributionError && <p className="obs-contribution-notice" role="status">{contributionError}</p>}
      {contributions?.sampled && <p className="obs-contribution-notice">This busy window is limited to {contributions.receipt_sample_limit.toLocaleString()} receipts. Totals are a sample.</p>}
      <div className="obs-contribution-islands">{contributionIslands.map(shore => <article key={shore.id} className={`obs-contribution-shore is-${shore.id}`}><header><h3>{shore.id === 'winners' ? 'WINNER ISLAND' : 'LOSER ISLAND'}</h3><a href="#/islands">Visit islands <ArrowRight size={12}/></a></header><div className="obs-contribution-totals"><div><b>{shore.productive_actions}</b><span>useful contributions</span></div><div><b>{shore.project_work}</b><span>project work units</span></div></div><p className="obs-action-efficiency">{shore.actions} completed actions · <b>{shore.no_gain_actions} with no stock or work gain</b></p><dl className="obs-resource-ledger"><div><dt>Resources gained</dt><dd>{resourceSummary(shore.resource_gains, '+')}</dd></div><div><dt>Resources spent</dt><dd>{resourceSummary(shore.resource_costs, '−')}</dd></div></dl>{shore.costs_complete === false && <p className="obs-contribution-note">Some historical receipts did not record resource costs. Recorded spending is incomplete.</p>}<div className="obs-contributor-list">{shore.actors.map(actor => <div className="obs-contributor" key={actor.id}><div><strong>{actor.name}</strong><span>{actor.productive_actions} useful contributions · {actor.project_work} work units</span><span>{actor.actions} actions completed · {actor.no_gain_actions} with no stock or work gain</span><p>{resourceSummary(actor.resource_gains, '+')}</p><small>{actor.model_actions} Gemini-directed · {actor.executor_actions} local simulator{actor.unattributed_actions ? ` · ${actor.unattributed_actions} origin not recorded` : ''}</small></div><button disabled={!actor.last_receipt_id} onClick={() => actor.last_receipt_id && inspectReceipt(actor.last_receipt_id)} title="Inspect this character’s latest saved action">Receipt <ChevronRight size={12}/></button></div>)}{shore.actors.length === 0 && <p className="obs-contribution-empty">No completed actions in this window. Waiting and discussion are not counted as contributions.</p>}</div></article>)}</div>
      <p className="obs-contribution-note">Costs shown were reserved when these actions started; gains arrived when they finished. A faster request pace creates more opportunities to plan; it does not guarantee more useful work. Zero stock or work gain is shown as zero, including when storage is full. These actions may still earn character XP; they are not counted as island growth. Compare the receipts, resources spent and project progress.</p>
    </section>

    <div className="obs-evidence-layout">
      <section className="obs-event-log"><header><div><span className="obs-eyebrow">THE EVIDENCE TRAIL</span><h2>WHAT JUST HAPPENED?</h2></div><select aria-label="Filter event type" value={category} onChange={e => setCategory(e.target.value)}><option value="all">All activity</option><option value="discussion">Conversations</option><option value="model">Gemini calls</option><option value="learning">Learning & experiments</option><option value="work">Contributions</option></select></header>{recent.length === 0 ? <div className="obs-empty"><MessageSquare size={30}/><h3>A quiet board is honest.</h3><p>{events.length ? 'No events match these filters.' : 'Events will appear when the crew acts. Earlier gameplay is not presented as freshly observed telemetry.'}</p></div> : <ol>{recent.map(event => { const Icon = iconFor(event); return <li key={event.id}><button className={selected?.id === event.id ? 'is-selected' : ''} onClick={() => inspectEvent(event)}><span className={`obs-event-icon is-${eventCategory(event)}`}><Icon size={17}/></span><div><span className="obs-event-meta">{event.actor_name || 'Local engine'} <i>·</i> {event.island_id === 'winners' ? 'Winner Island' : event.island_id === 'losers' ? 'Loser Island' : 'System'} <i>·</i> {time(event.created_at)}</span><strong>{eventLabel(event.kind)}</strong><p>{event.message || 'Open this event to inspect its recorded evidence.'}</p></div><ChevronRight size={15}/></button></li> })}</ol>}</section>
      <aside ref={inspectorRef} className="obs-inspector" aria-label="Selected event evidence"><header><span><Database size={14}/> RECORD INSPECTOR</span>{(selected || receiptId) && <button onClick={closeInspector} aria-label="Close event"><X size={15}/></button>}</header>{selected || receiptId ? <>
        <div className="obs-inspector-title"><span className="obs-proof"><CheckCheck size={12}/> {selected ? `COMMITTED EVENT #${selected.sequence}` : 'SAVED ACTION RECEIPT'}</span><h2>{selected ? eventLabel(selected.kind) : selectedReceipt ? eventLabel(selectedReceipt.action || 'Action not recorded') : 'ACTION EVIDENCE'}</h2>{selected && <p>{selected.message}</p>}</div>
        <dl className="obs-record-fields"><div><dt>Resident</dt><dd>{selected?.actor_name || selectedReceipt?.actor_name || 'System'}</dd></div><div><dt>Time</dt><dd>{selected ? time(selected.created_at) : selectedReceipt ? time(selectedReceipt.at) : 'Loading…'}</dd></div><div><dt>Session</dt><dd title={selected?.session_id || ''}>{selected?.session_id ? short(selected.session_id) : 'No council session linked'}</dd></div><div><dt>Trace</dt><dd title={selected?.trace_id || ''}>{selected?.trace_id ? short(selected.trace_id) : 'No trace linked'}</dd></div><div><dt>Storage</dt><dd>{persistence === 'mongodb' ? 'MongoDB Atlas' : 'Development memory'}</dd></div></dl>
        <div className="obs-receipt-evidence"><h3><ShieldCheck size={14}/> RECEIPT CHECK</h3>{evidenceError ? <p role="status">{evidenceError}</p> : !evidence ? <p>Resolving linked evidence from storage…</p> : <><span className={`obs-evidence-status is-${evidence.status}`}>{receiptEvidenceLabel(evidence)}</span><p>{evidence.reason}</p>{receiptRows(evidence).map(receipt => <div className="obs-action-receipt" key={receipt.id}><code title={receipt.id}>{receipt.id}</code><dl><div><dt>Action</dt><dd>{eventLabel(receipt.action || 'Action not recorded')}</dd></div><div><dt>Decision source</dt><dd>{receiptDecision(receipt).label}<small>{receiptDecision(receipt).reason}</small></dd></div><div><dt>Resources gained</dt><dd>{resourceSummary(receipt.resource_delta, '+')}</dd></div><div><dt>Resources spent</dt><dd>{resourceSummary(receipt.resource_cost, '−')}</dd></div><div><dt>Project work</dt><dd>{count(receipt.progress_delta)} units{receipt.project_id ? ` · ${eventLabel(receipt.project_id)}` : ''}</dd></div><div><dt>Recorded decision reference</dt><dd>{receipt.decision_id ? <code>{receipt.decision_id}</code> : receipt.decision_origin === 'model' ? 'Missing decision reference' : 'No model decision linked'}</dd></div></dl>{receipt.effect_note && <p className="obs-receipt-note">{receipt.effect_note}</p>}{Boolean(receipt.resources_before || receipt.resources_before_reservation || receipt.capability_evidence || receipt.capability_basis || receipt.source_snapshot || receipt.project_before || receipt.project_after) && <details className="obs-receipt-snapshot"><summary>Before / after and capability evidence</summary>{Object.entries({ 'Resources before reservation': receipt.resources_before_reservation, 'Resources after reservation': receipt.resources_after_reservation, 'Resources before completion': receipt.resources_before, 'Resources after completion': receipt.resources_after, 'Project before': receipt.project_before, 'Project after': receipt.project_after, 'Capability evidence': receipt.capability_basis || receipt.capability_evidence, 'Resource source': receipt.source_snapshot || receipt.source }).filter(([, value]) => value != null).map(([label, value]) => <div key={label}><b>{label}</b><pre>{displayValue(value)}</pre></div>)}</details>}</div>)}</>}</div>
        {selected && Object.keys(selected.data).length > 0 && <details className="obs-raw-data"><summary>Recorded event fields</summary><div className="obs-payload">{Object.entries(selected.data).map(([key, value]) => <div key={key}><b>{eventLabel(key)}</b><pre>{displayValue(value)}</pre></div>)}</div></details>}
        <div className="obs-trace"><h3><GitBranch size={15}/> {trace && trace.trace_id !== selected?.trace_id ? 'LINKED DECISION TRACE' : 'OPERATION TRACE'}</h3>{trace && trace.trace_id !== selected?.trace_id && selected?.trace_id && <button className="obs-trace-link" onClick={() => followTrace(selected!.trace_id!)}>← Back to this event’s trace</button>}{traceError && <p>{traceError}</p>}{!selected?.trace_id && <p>No trace is linked to this selection. Its saved evidence remains available.</p>}{selected?.trace_id && !trace && !traceError && <p>Reading stored spans…</p>}{trace?.spans.length === 0 && <p>Spans are still exporting or are outside the retention window.</p>}{trace?.spans.map(span => <div className="obs-span" key={span.span_id}><div><span>{span.name}</span><b>{Math.round(span.duration_ms)} ms</b></div><div className="obs-span-track"><span className={span.status === 'ERROR' ? 'is-error' : ''} style={{marginLeft:`${((Date.parse(span.created_at)-traceStart)/Math.max(1,traceDuration))*80}%`,width:`${Math.max(2,span.duration_ms/Math.max(1,traceDuration)*80)}%`}}/></div><small>{span.status}{span.attributes['db.mongodb.collection'] ? ` · ${span.attributes['db.mongodb.collection']}` : ''}{span.attributes['sketch.model'] ? ` · ${span.attributes['sketch.model']}` : ''}</small>{span.links?.map(link => <button className="obs-trace-link" key={link.trace_id + link.span_id} onClick={() => followTrace(link.trace_id)}>Follow the decision that caused this ↗</button>)}</div>)}<p className="obs-trace-note">Traces show attempts. Committed events prove changes. Private prompts and credentials are excluded.</p></div></> : <div className="obs-inspector-empty"><ArrowRight size={28}/><h3>Follow a thought to its consequence.</h3><p>Select a message or contribution to inspect its saved evidence and the operations behind it.</p><div><span>01</span> An agent proposes an action</div><div><span>02</span> The simulator checks it</div><div><span>03</span> Atlas commits the result</div><div><span>04</span> The crew remembers what happened</div></div>}</aside>
    </div>
    <footer className="obs-footer"><span><ShieldCheck size={13}/> OBSERVED EVENTS, NEVER DECORATIVE TRAFFIC</span><span>OpenTelemetry · {persistence === 'development_memory' ? 'Development storage' : 'MongoDB Atlas'} · Local Python workers</span></footer>
  </main>
}
