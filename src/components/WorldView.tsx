import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { ArrowLeft, Box, Check, ChevronRight, Globe2, Grid2X2, Moon, RefreshCw, Sparkles, X } from 'lucide-react'
import './WorldView.css'

export type WorldCharacter = {
  id: string
  world_id: string
  canonical_type_id: string
  object_type: string
  display_name: string
  image_ref: string
  visual_spec: {
    template_id: 'mug' | 'bottle' | 'generic' | 'plant' | 'book' | 'ball'
    palette: string[]
    scale: number
    proportions: { width: number; height: number }
    accessories: string[]
    animation_style: 'bouncy' | 'calm' | 'wobbly'
    schema_version: string
    appearance_seed: number
  }
  archetype: string
  first_battle_id: string
  unlocked_at: string
  home_position: { x: number; y: number; z: number }
  state: { activity: 'wander' | 'rest'; mood: string }
  distinct_battle_count: number
  last_battle_at?: string
}
export type WorldData = {
  world: { id: string; name: string; layout_seed: number; version: string; created_at: string }
  characters: WorldCharacter[]
  has_more: boolean
  persistence: 'mongodb' | 'development_memory'
}
type History = { character_id: string; distinct_battle_count: number; encounters: { battle_id: string; completed_at: string; winner_slot: number; slots: { player_slot: number; won: boolean; image_ref: string; display_name: string }[] }[] }

const WorldScene = lazy(() => import('./WorldScene'))
const CharacterPreview = lazy(() => import('./CharacterPreview'))
const MAX_ISLAND_RESIDENTS = 40

class SceneBoundary extends Component<{ children: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn('World renderer unavailable:', error.name, info.componentStack?.split('\n')[1] ?? '')
    this.props.onFailure()
  }
  render() { return this.state.failed ? null : this.props.children }
}

async function requestJSON<T>(url: string, signal: AbortSignal, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...options, signal, headers: { 'Content-Type': 'application/json', ...options.headers } })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body?.error?.message ?? body?.detail?.message ?? body?.detail ?? body?.message
    throw new Error(typeof detail === 'string' ? detail : `The world could not be reached (${response.status}).`)
  }
  return body as T
}

function dateLabel(value: string) {
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : 'Date unavailable'
}

function CharacterDetails({ character, onClose, onUpdate }: { character: WorldCharacter; onClose: () => void; onUpdate: (character: WorldCharacter) => void }) {
  const [history, setHistory] = useState<History | null>(null)
  const [historyError, setHistoryError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [historyAttempt, setHistoryAttempt] = useState(0)
  const saveAbort = useRef<AbortController | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort('timeout'), 15_000)
    setHistory(null)
    setHistoryError('')
    void requestJSON<History>(`/api/world/characters/${encodeURIComponent(character.id)}/history`, controller.signal).then(setHistory).catch(error => {
      if (!controller.signal.aborted || controller.signal.reason === 'timeout') setHistoryError(controller.signal.reason === 'timeout' ? 'Battle history timed out. Try again.' : error.message)
    }).finally(() => window.clearTimeout(timeout))
    return () => { controller.abort(); window.clearTimeout(timeout) }
  }, [character.id, historyAttempt])
  useEffect(() => () => saveAbort.current?.abort(), [])

  const updateActivity = async () => {
    if (saving) return
    const controller = new AbortController()
    saveAbort.current = controller
    const timeout = window.setTimeout(() => controller.abort('timeout'), 15_000)
    setSaving(true)
    setSaveError('')
    setSaved(false)
    try {
      const result = await requestJSON<WorldCharacter>(`/api/world/characters/${encodeURIComponent(character.id)}`, controller.signal, { method: 'PATCH', body: JSON.stringify({ activity: character.state.activity === 'rest' ? 'wander' : 'rest' }) })
      if (controller.signal.aborted) return
      onUpdate(result)
      setSaved(true)
    } catch (error) {
      if (!controller.signal.aborted || controller.signal.reason === 'timeout') setSaveError(controller.signal.reason === 'timeout' ? 'Saving timed out. Refresh the world to check whether it was saved.' : error instanceof Error ? error.message : 'The change could not be saved.')
    } finally {
      window.clearTimeout(timeout)
      if (!controller.signal.aborted || controller.signal.reason === 'timeout') setSaving(false)
    }
  }

  return <aside className="world-character-detail" aria-label={`${character.display_name} details`}>
    <div className="world-detail-topline"><span>RESIDENT FILE</span><button type="button" aria-label="Close character details" onClick={onClose}><X size={17} /></button></div>
    <div className="world-detail-model"><Suspense fallback={<span>Loading saved appearance…</span>}><CharacterPreview fighter={character} compact scope="Saved island appearance" /></Suspense></div>
    <div className="world-character-photo"><span className="world-photo-tape" aria-hidden="true" /><img src={character.image_ref} alt={`Original photograph of ${character.object_type}`} /></div>
    <span className="world-detail-type">{character.object_type} / {character.archetype}</span>
    <h2>{character.display_name}</h2>
    <p className="world-detail-description">First arrived {dateLabel(character.unlocked_at)}. This is the original accepted appearance, kept across repeat encounters.</p>
    <div className="world-detail-stats"><div><strong>{character.distinct_battle_count}</strong><span>DISTINCT {character.distinct_battle_count === 1 ? 'BATTLE' : 'BATTLES'}</span></div><div><strong>{character.state.activity === 'rest' ? 'RESTING' : 'ROAMING'}</strong><span>AT HOME ON THE ISLAND</span></div></div>
    <button className="world-activity-button" type="button" disabled={saving} onClick={() => void updateActivity()}>{character.state.activity === 'rest' ? <Sparkles size={16} /> : <Moon size={16} />}{saving ? 'SAVING…' : character.state.activity === 'rest' ? 'LET THEM WANDER' : 'TAKE A LITTLE REST'}</button>
    {saved && <p className="world-save-status" role="status"><Check size={13} /> Activity saved.</p>}
    {saveError && <p className="world-detail-error" role="alert">{saveError}</p>}
    <div className="world-history"><h3>BATTLE STORIES</h3>{!history && !historyError && <p role="status">Loading recorded battles…</p>}{historyError && <div><p role="alert">{historyError}</p><button className="world-inline-button" type="button" onClick={() => setHistoryAttempt(value => value + 1)}>Retry history</button></div>}
      {history?.encounters.length === 0 && <p>No battle history was returned for this resident.</p>}
      {history?.encounters.map(encounter => <div className="world-history-entry" key={encounter.battle_id}><span>{dateLabel(encounter.completed_at)}</span><div>{encounter.slots.map(slot => <span key={slot.player_slot}>P{slot.player_slot + 1}<b className={slot.won ? 'world-history-win' : ''}>{slot.won ? 'WON' : 'LOST'}</b></span>)}</div><small>Battle {encounter.battle_id.slice(0, 8)}</small></div>)}
      {history && history.distinct_battle_count > history.encounters.length && <p>Showing the latest {history.encounters.length} of {history.distinct_battle_count} battles.</p>}
    </div>
  </aside>
}

export default function WorldView({ onBack, arrivalIds = [] }: { onBack: () => void; arrivalIds?: string[] }) {
  const [data, setData] = useState<WorldData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [view, setView] = useState<'island' | 'collection'>('island')
  const [sceneFailed, setSceneFailed] = useState(false)
  const [visible, setVisible] = useState(!document.hidden)
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const arrived = useRef(new Set<string>())

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort('timeout'), 15_000)
    setLoading(true)
    setError('')
    void requestJSON<WorldData>('/api/world', controller.signal).then(result => {
      if (!result?.world || !Array.isArray(result.characters)) throw new Error('The world returned an unexpected response. Please retry.')
      if (controller.signal.aborted) return
      setData(result)
    }).catch(reason => {
      if (!controller.signal.aborted || controller.signal.reason === 'timeout') setError(controller.signal.reason === 'timeout' ? 'The world took too long to respond. Check that the local server and database are running, then retry.' : reason instanceof Error ? reason.message : 'The world could not be loaded.')
    }).finally(() => {
      window.clearTimeout(timeout)
      if (!controller.signal.aborted || controller.signal.reason === 'timeout') setLoading(false)
    })
    return () => { controller.abort(); window.clearTimeout(timeout) }
  }, [attempt])

  useEffect(() => {
    const onVisibility = () => setVisible(!document.hidden)
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMotion = () => setReducedMotion(query.matches)
    document.addEventListener('visibilitychange', onVisibility)
    query.addEventListener('change', onMotion)
    return () => { document.removeEventListener('visibilitychange', onVisibility); query.removeEventListener('change', onMotion) }
  }, [])

  const selected = data?.characters.find(character => character.id === selectedId)
  const collectionMode = view === 'collection' || sceneFailed
  const onSceneFailure = () => { setSceneFailed(true); setView('collection') }
  const updateCharacter = (character: WorldCharacter) => setData(current => current ? { ...current, characters: current.characters.map(item => item.id === character.id ? character : item) } : current)

  return <section className="world-screen" aria-label="Sketch Clash world">
    <div className="world-heading"><div><span className="world-eyebrow"><Globe2 size={13} /> BEYOND THE BATTLE</span><h1>SMALL ISLAND.<br /><em>BIG PERSONALITIES.</em></h1><p>Your real-world finds, with a little life of their own.</p></div><button className="world-back-button" onClick={onBack}><ArrowLeft size={16} /> BACK TO BATTLE</button></div>
    {data?.persistence === 'development_memory' && <p className="world-development-note" role="status"><strong>DEVELOPMENT WORLD</strong> These residents are held in temporary server memory. They are not saved in MongoDB and disappear when that server restarts.</p>}
    {loading && <div className="world-state"><span className="world-state-star" aria-hidden="true">✳</span><h2>OPENING THE SKETCHBOOK…</h2><p role="status">Loading the inhabitants already saved in this world.</p></div>}
    {!loading && error && <div className="world-state world-state-error"><Globe2 size={40} /><h2>THE ISLAND IS OUT OF REACH.</h2><p role="alert">{error}</p><button className="arcade-button" onClick={() => setAttempt(value => value + 1)}>TRY AGAIN <RefreshCw size={19} /></button><small>Your existing fighters are not changed by a failed world load.</small></div>}
    {!loading && !error && data && <>
      <div className="world-view-bar"><div><span className="world-location-dot" /><b>{data.world.name}</b><span>{data.characters.length}{data.has_more ? '+' : ''} {data.characters.length === 1 ? 'RESIDENT' : 'RESIDENTS'}</span></div><div className="world-view-buttons"><button type="button" aria-pressed={!collectionMode} disabled={sceneFailed} onClick={() => setView('island')}><Globe2 size={15} /> ISLAND</button><button type="button" aria-pressed={collectionMode} onClick={() => setView('collection')}><Grid2X2 size={15} /> COLLECTION</button><button type="button" aria-label="Refresh saved world" onClick={() => setAttempt(value => value + 1)}><RefreshCw size={15} /></button></div></div>
      {sceneFailed && <p className="world-render-note" role="status">3D is unavailable in this browser. Your saved collection and battle histories are still here.</p>}
      <div className={`world-main ${selected ? 'has-selection' : ''}`}>
        <div className="world-main-content">
          {!collectionMode && <div className="world-diorama"><span className="world-map-label" aria-hidden="true">SKETCH ISLAND<br /><b>A PLACE FOR EVERY LITTLE CHARACTER</b></span><span className="world-environment-label"><span /> {visible ? "Island awake" : "Island resting"}</span><SceneBoundary onFailure={onSceneFailure}><Suspense fallback={<div className="world-scene-loading" role="status">Opening the island…</div>}><WorldScene characters={data.characters.slice(0, MAX_ISLAND_RESIDENTS)} layoutSeed={data.world.layout_seed} selectedId={selectedId} onSelect={setSelectedId} active={visible} reducedMotion={reducedMotion} arrivalIds={arrivalIds.filter(id => !arrived.current.has(id))} onArrived={id => arrived.current.add(id)} onFailure={onSceneFailure} /></Suspense></SceneBoundary><span className="world-map-compass" aria-hidden="true">N<br />↑</span><div className="world-map-caption">DRAG TO LOOK AROUND <span>✦</span> TAP A RESIDENT TO SAY HELLO</div></div>}
          {data.characters.length === 0 && <div className="world-empty"><span aria-hidden="true">✳</span><div><h2>A LITTLE QUIET, FOR NOW.</h2><p>Finish a battle with two real objects. Both fighters can arrive here once the result is saved.</p><button className="world-inline-button" onClick={onBack}>START THEIR FIRST STORY <ChevronRight size={15} /></button></div></div>}
          {!collectionMode && data.characters.length > MAX_ISLAND_RESIDENTS && <p className="world-render-note">Showing {MAX_ISLAND_RESIDENTS} residents on the island to keep it smooth. Every loaded resident is in the collection below.</p>}
          {data.characters.length > 0 && <div className={`world-collection ${collectionMode ? 'is-full' : ''}`}><div className="world-collection-heading"><h2>THE LOCAL CHARACTERS</h2><span>ONE RESIDENT PER OBJECT TYPE</span></div><div className="world-resident-grid">{data.characters.map(character => <button className={`world-resident ${selectedId === character.id ? 'is-selected' : ''}`} key={character.id} onClick={() => setSelectedId(character.id)} aria-pressed={selectedId === character.id}><div><img src={character.image_ref} alt={character.object_type} loading="lazy" /><span aria-hidden="true">{character.state.activity === 'rest' ? '☾' : '✳'}</span></div><strong>{character.display_name}</strong><small>{character.object_type}</small><span className="world-resident-count">{character.distinct_battle_count} {character.distinct_battle_count === 1 ? 'BATTLE' : 'BATTLES'}</span></button>)}</div>{data.has_more && <p className="world-render-note">This view shows the first 500 saved residents.</p>}</div>}
        </div>
        {selected && <CharacterDetails key={selected.id} character={selected} onClose={() => setSelectedId(null)} onUpdate={updateCharacter} />}
      </div>
      <div className="world-footnote"><span><Box size={13} /> Stylised characters inspired by your objects. Original photos stay in their resident files.</span><span>{reducedMotion ? 'REDUCED MOTION' : 'MOVEMENT RUNS WHILE YOU VISIT'}</span></div>
    </>}
  </section>
}
