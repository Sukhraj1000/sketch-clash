import { Component, Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ArrowLeft, ArrowRight, BatteryCharging, BookOpen, Box, Check, Coffee, Crosshair, Flag, Hammer, Lightbulb, Maximize2, Pause, Play, Plus, RotateCcw, Ruler, Sprout, Utensils, Waves, Zap } from 'lucide-react'
import { addPlaygroundObject, advancePlayground, BLUEPRINTS, CAPABILITY_LABELS, costLabel, createPlayground, islandValue, MAX_CREW, OBJECTS, objectDefinition, playgroundCharacters, playgroundScene, projectGaps, RESOURCE_ORDER, shortages } from '../lib/playground'
import type { ObjectKind, Resource } from '../lib/playground'
import './IslandPlayground.css'

const WorldScene = lazy(() => import('./WorldScene'))
const OBJECT_ICONS = { mug: Coffee, ruler: Ruler, battery: BatteryCharging, spoon: Utensils, book: BookOpen, pitcher: Waves }
const RESOURCE_ICONS = { materials: Box, water: Waves, ideas: Lightbulb, energy: Zap }
const RESOURCE_NAMES: Record<Resource, string> = { materials: 'Materials', water: 'Water', ideas: 'Plans', energy: 'Energy' }
const timeLabel = (seconds: number) => `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`
class SceneBoundary extends Component<{ children: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch() { this.props.onFailure() }
  render() { return this.state.failed ? null : this.props.children }
}
export default function IslandPlayground({ onBack }: { onBack: () => void }) {
  const [state, setState] = useState(createPlayground)
  const [islandId, setIslandId] = useState('sunrise')
  const [speed, setSpeed] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [arrivalIds, setArrivalIds] = useState<string[]>([])
  const [follow, setFollow] = useState(false)
  const [cameraReset, setCameraReset] = useState(0)
  const [sceneFailed, setSceneFailed] = useState(false)
  const [visible, setVisible] = useState(!document.hidden)
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [showWork, setShowWork] = useState(false)
  const [notice, setNotice] = useState('Try adding a Battery to Sunrise. A new capability opens a new plan.')
  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden)
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMotion = () => setReducedMotion(query.matches)
    document.addEventListener('visibilitychange', onVisibility); query.addEventListener('change', onMotion)
    return () => { document.removeEventListener('visibilitychange', onVisibility); query.removeEventListener('change', onMotion) }
  }, [])
  useEffect(() => {
    if (state.paused || !visible) return
    const timer = window.setInterval(() => setState(previous => advancePlayground(previous, .25 * speed)), 250)
    return () => window.clearInterval(timer)
  }, [state.paused, visible, speed])
  const island = state.islands.find(item => item.id === islandId)!
  const characters = useMemo(() => playgroundCharacters(island), [island.residents])
  const simulation = useMemo(() => playgroundScene({ ...state, paused: state.paused || !visible }, island, speed, Date.now()), [state, island, speed, visible])
  const project = island.projects.find(item => item.id === island.activeProject)
  const missing = project ? shortages(island, project) : {}
  const selected = island.residents.find(resident => resident.id === selectedId)
  const selectedObject = selected ? objectDefinition(selected.kind) : null
  const progress = project ? Math.round(project.progress / project.required_progress * 100) : 0
  const finished = island.projects.filter(item => item.status === 'complete').length
  const notes = island.notes.filter(note => showWork || note.kind !== 'work').slice(-8).reverse()
  const onArrived = useCallback((id: string) => setArrivalIds(previous => previous.filter(item => item !== id)), [])
  const addObject = (kind: ObjectKind) => {
    const next = addPlaygroundObject(state, islandId, kind)
    if (next === state) return
    const newId = next.islands.find(item => item.id === islandId)!.residents.at(-1)!.id
    setState(next); setSelectedId(newId); setArrivalIds(previous => [...previous, newId])
    setNotice(`${objectDefinition(kind).label} joined ${island.name}. The rule engine has reconsidered the crew’s capabilities.`)
  }
  const reset = () => {
    setState(createPlayground()); setIslandId('sunrise'); setSelectedId(null); setArrivalIds([]); setFollow(false); setCameraReset(key => key + 1)
    setNotice('Practice reset. Both example crews start with the same empty store. Your saved islands are untouched.')
  }
  return <main className="playground-screen">
    <div className="pg-topline"><button className="pg-text-button" onClick={onBack}><ArrowLeft size={15} /> Back to Sketch Clash</button><span className="pg-stamp">PRACTICE / NO AI CALLS</span></div>
    <header className="pg-heading"><div><span className="pg-eyebrow">THE ISLAND PLAYGROUND</span><h1>Small objects.<br /><em>Big plans.</em></h1><p>Drop in a useful object. Watch the crew gather, build and change its plan.</p></div><div className="pg-intro-note"><span>THE EXPERIMENT</span><b>What makes a crew thrive?</b><p>Two example islands. Different skills. Give them a missing role and see what becomes possible.</p><small>Browser memory only · not saved to Atlas</small></div></header>
    <div className="pg-island-tabs" role="group" aria-label="Choose an example island">{state.islands.map(item => <button key={item.id} aria-pressed={islandId === item.id} onClick={() => { setIslandId(item.id); setSelectedId(null); setFollow(false); setCameraReset(key => key + 1) }}><span className="pg-crew-dot" style={{ background: item.color }} /><span><small>EXAMPLE {item.id === 'sunrise' ? 'A' : 'B'}</small><b>{item.name}</b><em>{item.residents.length} objects · {item.projects.filter(project => project.status === 'complete').length}/4 builds</em></span><strong>{islandValue(item)}<small>VALUE</small></strong></button>)}</div>
    <div className="pg-controls"><div><span className={`pg-running-dot ${state.paused ? 'is-paused' : ''}`} /><b>{state.paused ? 'Practice paused' : 'Practice running'}</b><span className="pg-clock">{timeLabel(state.seconds)}</span></div><div><button onClick={() => setState(previous => ({ ...previous, paused: !previous.paused }))}>{state.paused ? <Play size={15} /> : <Pause size={15} />}{state.paused ? 'Resume' : 'Pause'}</button><label><span className="pg-sr-only">Simulation speed</span><select aria-label="Simulation speed" value={speed} onChange={event => setSpeed(Number(event.target.value))}><option value={1}>1× speed</option><option value={2}>2× speed</option><option value={4}>4× speed</option></select></label><button onClick={reset}><RotateCcw size={14} /> Reset practice</button></div></div>
    <section className="pg-stage-layout" aria-label="Practice island and current plan">
      <div className="pg-scene-shell"><div className="pg-scene-label"><span style={{ background: island.color }} />{island.name}<small>EXAMPLE CREW</small></div><div className="pg-scene">
        {sceneFailed ? <div className="pg-scene-fallback"><Sprout size={42} /><h2>The crew list is ready.</h2><p>3D isn’t available in this browser. Follow every contribution in the crew list and board below.</p></div> : <SceneBoundary key={islandId} onFailure={() => setSceneFailed(true)}><Suspense fallback={<div className="pg-scene-fallback">Setting up the island…</div>}><WorldScene characters={characters} layoutSeed={islandId === 'sunrise' ? 241 : 412} selectedId={selectedId} onSelect={setSelectedId} active={visible} reducedMotion={reducedMotion} arrivalIds={arrivalIds} onArrived={onArrived} onFailure={() => setSceneFailed(true)} simulation={simulation} selectedProjectId={project?.id} cameraResetKey={cameraReset} followSelected={follow} /></Suspense></SceneBoundary>}
      </div><div className="pg-camera-tools"><span>Drag to orbit · pinch or Ctrl + scroll to zoom · click an object</span><button onClick={() => { setCameraReset(key => key + 1); setFollow(false) }} aria-label="Reset island camera"><Maximize2 size={15} /></button><button disabled={!selected} aria-pressed={follow} onClick={() => setFollow(value => !value)} title={selected ? 'Follow selected object' : 'Select an object to follow it'}><Crosshair size={15} /> Follow</button></div>
        <div className="pg-resource-strip">{RESOURCE_ORDER.map(resource => { const Icon = RESOURCE_ICONS[resource]; return <div key={resource}><Icon size={17} /><span><strong>{island.resources[resource]}</strong><small>{RESOURCE_NAMES[resource]}</small></span>{(missing[resource] ?? 0) > 0 && <em>need {missing[resource]} more</em>}</div> })}</div>
      </div>
      <aside className="pg-plan-panel"><div className="pg-panel-kicker"><span>THE CREW’S NEXT MOVE</span><span>GAME RULES</span></div><h2>{project?.name ?? (finished === 4 ? 'Island complete!' : 'A new role, please.')}</h2><p>{project ? project.status === 'building' ? 'Supplies are reserved. Every eligible object contributes its own skill.' : Object.keys(missing).length ? `Gather ${costLabel(missing)}. The crew chose a build it has the skills to finish.` : 'Supplies are ready. Resume practice to fund construction.' : finished === 4 ? 'All four builds are working. Compare the other crew or reset to try another combination.' : 'The crew is stocking supplies. Add a missing capability to unlock another build.'}</p><div className="pg-plan-progress"><span><b>{project?.status === 'building' ? `${progress}% built` : project ? 'Gathering supplies' : `${finished}/4 built`}</b><small>{project?.status === 'building' ? `${project.progress}/${project.required_progress} work` : `${islandValue(island)} island value`}</small></span><div role="progressbar" aria-label={project ? `${project.name} construction` : 'Island projects'} aria-valuemin={0} aria-valuemax={100} aria-valuenow={project ? progress : finished * 25}><i style={{ width: `${project ? progress : finished * 25}%` }} /></div></div>
        <div className="pg-crew-heading"><b>WHO DOES WHAT</b><span>{island.residents.length}/{MAX_CREW}</span></div><div className="pg-crew-list">{island.residents.map(resident => { const object = objectDefinition(resident.kind), Icon = OBJECT_ICONS[resident.kind]; return <button key={resident.id} aria-pressed={selectedId === resident.id} onClick={() => setSelectedId(resident.id)}><i style={{ background: object.color }}><Icon size={18} /></i><span><b>{object.label}</b><small>{resident.task?.title ?? 'Supplies stocked · ready to help'}</small></span><ArrowRight size={14} /></button> })}</div>
        {selected && selectedObject && <div className="pg-selected-detail"><b>{selectedObject.label} · {selectedObject.role}</b><p>{selectedObject.detail}</p><span>{selected.delivered} resources delivered · {selected.built} build contributions</span></div>}
      </aside>
    </section>
    <section className="pg-object-section" aria-label="Add an object"><div className="pg-section-title"><div><span className="pg-eyebrow">CHANGE THE CREW. CHANGE THE PLAN.</span><h2>Who’s coming ashore?</h2></div><p>Choose an object for <b>{island.name}</b>. New skills unlock new builds; duplicate roles add capacity.</p></div><div className="pg-object-palette">{OBJECTS.map(object => { const Icon = OBJECT_ICONS[object.kind], present = island.residents.some(resident => resident.kind === object.kind), full = island.residents.length >= MAX_CREW; return <button key={object.kind} disabled={present || full} onClick={() => addObject(object.kind)}><span className="pg-object-doodle" style={{ background: object.color }}><Icon strokeWidth={1.6} size={35} /></span><b>{object.label}</b><small>{object.role}</small><span className="pg-object-yield">+{object.yield} {RESOURCE_NAMES[object.resource].toLowerCase()} / trip</span><span className="pg-add-label">{present ? <Check size={13} /> : <Plus size={13} />}{present ? 'On this island' : full ? 'Crew is full' : 'Add to crew'}</span></button> })}</div><p className="pg-feedback" role="status"><Flag size={15} />{notice}</p></section>
    <section className="pg-blueprints" aria-label="Project requirements"><div className="pg-section-title"><div><span className="pg-eyebrow">USEFUL THINGS, BUILT TOGETHER</span><h2>The island’s to-do list.</h2></div><p>Materials are paid once when construction starts. Missing skills come first; then the rule engine selects the highest-priority feasible build.</p></div><div className="pg-blueprint-grid">{[...island.projects].reverse().map(item => { const gaps = projectGaps(island, item.id), blueprint = BLUEPRINTS.find(blueprint => blueprint.id === item.id)!, status = item.status === 'complete' ? 'COMPLETE' : item.status === 'building' ? 'BUILDING' : gaps.capabilities.length ? 'MISSING A ROLE' : gaps.prerequisite ? 'NEEDS WORKSHOP' : 'CREW READY'; return <article key={item.id} className={`${item.status === 'complete' ? 'is-complete' : ''} ${item.id === island.activeProject ? 'is-active' : ''}`}><div><Hammer size={15} /><span>{status}</span>{item.status === 'complete' && <Check size={15} />}</div><h3>{item.name}</h3><p className="pg-blueprint-cost">{costLabel(item.cost_per_action)}</p><div className="pg-role-chips">{blueprint.needs.map(capability => <span key={capability} className={gaps.capabilities.includes(capability) ? 'is-missing' : ''}>{gaps.capabilities.includes(capability) ? <Plus size={11} /> : <Check size={11} />}{CAPABILITY_LABELS[capability]}</span>)}</div><p>{item.reward}</p></article> })}</div></section>
    <section className="pg-board" aria-label="Practice rules board"><div className="pg-section-title"><div><span className="pg-eyebrow">THE REASONS ARE ON THE BOARD</span><h2>From new arrival to new plan.</h2></div><label><input type="checkbox" checked={showWork} onChange={event => setShowWork(event.target.checked)} /> Include individual work</label></div><p className="pg-board-disclosure">These are explanations of deterministic game rules and completed actions. No Gemini discussion, learning or model reasoning is being simulated.</p><ol className="pg-board-notes">{notes.map(note => <li key={note.id} className={`pg-note-${note.kind}`}><div><span>{note.kind === 'decision' ? 'PLAN RULE' : note.kind === 'arrival' ? 'ARRIVAL' : note.kind === 'complete' ? 'BUILT TOGETHER' : 'WORK DONE'}</span><time>{timeLabel(note.at)}</time></div><b>{note.actor}</b><p>{note.text}</p></li>)}</ol></section>
    <footer className="pg-footer"><span>LOCAL PRACTICE · FIXED GAME RULES · EXAMPLE OBJECTS</span><p>No model calls. No Atlas writes. Refreshing or leaving this page clears the practice session. Both crews advance together while this page is visible.</p><button className="pg-text-button" onClick={onBack}>Back to your saved world <ArrowRight size={15} /></button></footer>
  </main>
}
