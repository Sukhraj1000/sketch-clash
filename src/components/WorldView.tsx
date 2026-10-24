import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { ArrowLeft, ArrowRight, Box, Check, ChevronRight, Flag, Globe2, Grid2X2, Hammer, Lightbulb, LoaderCircle, Maximize2, Pause, Play, RefreshCw, Sparkles, Target, Waves, X, Zap } from 'lucide-react'
import type { IslandAgent, IslandProject, IslandSimulation } from '../lib/island'
import type { ObservedAppearance } from './vesselPresentation'
import './WorldView.css'

export type WorldCharacter = {
  id: string
  world_id: string
  canonical_type_id: string
  object_type: string
  display_name: string
  image_ref: string
  observed_object?: ObservedAppearance
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
type Planner = { enabled: boolean; configured?: boolean; auto_blocked?: boolean; pending_run_id?: string | null; model?: string; requests_today: number; max_requests_per_day: number; next_reflection_at?: string; last_status?: string; error?: string; uncertain?: boolean }
type Simulation = IslandSimulation & { planner?: Planner }
const WorldScene = lazy(() => import('./WorldScene'))
const MAX_ISLAND_RESIDENTS = 40
const RESOURCE_LABELS: Record<string,string> = { materials:'MATERIALS',water:'WATER',ideas:'IDEAS',energy:'ENERGY' }
const RESOURCE_ICONS = { materials:Box,water:Waves,ideas:Lightbulb,energy:Zap }

class SceneBoundary extends Component<{ children: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.warn('World renderer unavailable:',error.name,info.componentStack?.split('\n')[1]??'');this.props.onFailure() }
  render() { return this.state.failed ? null : this.props.children }
}
async function requestJSON<T>(url:string, signal:AbortSignal, options:RequestInit={}):Promise<T> {
  const controller=new AbortController()
  const cancel=()=>controller.abort(signal.reason)
  if(signal.aborted)cancel();else signal.addEventListener('abort',cancel,{once:true})
  const timeout=window.setTimeout(()=>controller.abort('timeout'),15000)
  try{
    const response=await fetch(url,{...options,signal:controller.signal,headers:{'Content-Type':'application/json',...options.headers}})
    const body=await response.json().catch(()=>null)
    if(!response.ok){const detail=body?.error?.message??body?.detail?.message??body?.detail??body?.message;throw new Error(typeof detail==='string'?detail:`The island could not be reached (${response.status}).`)}
    return body as T
  }catch(error){if(controller.signal.reason==='timeout')throw new Error('The island request timed out. Check that the local server is awake, then refresh.');throw error}
  finally{window.clearTimeout(timeout);signal.removeEventListener('abort',cancel)}
}
function dateLabel(value:string){const date=new Date(value);return Number.isFinite(date.getTime())?date.toLocaleDateString(undefined,{day:'numeric',month:'short'}):'Date unavailable'}
function ageLabel(value:string,now:number){const age=Math.max(0,Math.floor((now-Date.parse(value))/1000));return !Number.isFinite(age)?'Recorded':age<60?'Just now':age<3600?`${Math.floor(age/60)}m ago`:`${Math.floor(age/3600)}h ago`}
function progressPercent(project:IslandProject){return project.status==='complete'?100:Math.min(100,Math.round(project.progress/Math.max(1,project.required_progress)*100))}
function resourceText(resources:Record<string,number>){return Object.entries(resources).filter(([,value])=>value>0).map(([key,value])=>`${value} ${key}`).join(' · ')}
function TaskProgress({agent,now,paused}:{agent:IslandAgent;now:number;paused:boolean}){
  if(!agent.task)return <p className="agent-task-empty">Choosing the next useful thing to do.</p>
  const start=Date.parse(agent.task.started_at),end=Date.parse(agent.task.ends_at)
  const progress=Math.max(0,Math.min(100,((now-start)/Math.max(1,end-start))*100))
  return <div className="agent-task"><div><Hammer size={14}/><b>{agent.task.title}</b><span>{paused?'PAUSED':`${Math.max(0,Math.ceil((end-now)/1000))}s`}</span></div><div className="island-progress-track"><span style={{width:`${progress}%`}}/></div><small>{paused?'Resume the island to continue.':agent.task.resource?`Working toward more ${agent.task.resource}.`:'One small action. A more useful island.'}</small></div>
}
function ResidentHistory({character}:{character:WorldCharacter}){
  const [history,setHistory]=useState<History|null>(null),[error,setError]=useState('')
  useEffect(()=>{const controller=new AbortController();void requestJSON<History>(`/api/world/characters/${encodeURIComponent(character.id)}/history`,controller.signal).then(setHistory).catch(error=>{if(!controller.signal.aborted)setError(error.message)});return()=>controller.abort()},[character.id])
  return <div className="resident-history"><img src={character.image_ref} alt={`Original ${character.object_type} photograph`}/><p>First arrived {dateLabel(character.unlocked_at)}. The original accepted appearance stays with this resident.</p><h4>{character.distinct_battle_count} BATTLE {character.distinct_battle_count===1?'STORY':'STORIES'}</h4>{error&&<p role="alert">{error}</p>}{!history&&!error&&<p>Loading battle stories…</p>}{history?.encounters.slice(0,5).map(encounter=><div key={encounter.battle_id}><span>{dateLabel(encounter.completed_at)}</span><span>{encounter.slots.map(slot=>`P${slot.player_slot+1} ${slot.won?'won':'lost'}`).join(' · ')}</span></div>)}</div>
}
function AgentInspector({agent,character,now,paused,busy,onAssign,onClose}:{agent:IslandAgent;character:WorldCharacter;now:number;paused:boolean;busy:boolean;onAssign:(assignment:string)=>void;onClose:()=>void}){
  const [historyOpen,setHistoryOpen]=useState(false)
  return <aside className="island-inspector agent-inspector" aria-label={`${agent.display_name} resident details`}>
    <div className="island-panel-top"><span>RESIDENT / LEVEL {agent.level}</span><button onClick={onClose} aria-label="Close resident"><X size={16}/></button></div>
    <div className="agent-identity"><img src={character.image_ref} alt={character.object_type}/><div><span>{agent.object_type}</span><h2>{agent.display_name}</h2><b>{agent.persona.role}</b><small className="agent-persona-origin">{agent.persona_provenance?.origin==='gemini'?'AI-refined role':'Object-based role'}</small></div></div>
    <p className="agent-quote">“{agent.persona.motto}”</p><p className="agent-personality">{agent.persona.temperament}</p>
    <div className="agent-capabilities">{agent.capabilities.map(capability=><span key={capability}>{capability.replaceAll('_',' ')}</span>)}</div>
    <div className="agent-xp"><span><Sparkles size={13}/>{agent.xp} XP</span><span>{agent.completed_actions} useful actions</span></div>
    <TaskProgress agent={agent} now={now} paused={paused}/>
    <label className="agent-assignment">GIVE THEM DIRECTION<select value={agent.assignment} disabled={busy} onChange={event=>onAssign(event.target.value)}>{agent.available_assignments.map(assignment=><option value={assignment.id} key={assignment.id}>{assignment.label}</option>)}</select><small>New directions apply after the current task finishes.</small></label>
    <p className="agent-goal"><Target size={14}/><span>{agent.persona.goal}</span></p>
    <div className="agent-memories"><h3>WHAT I REMEMBER</h3>{agent.memory.length?agent.memory.slice(-3).reverse().map(memory=><p key={memory.id}><span><b>{memory.kind==='reflection'?'AI PLAN':'RECORDED ACTION'}</b> · {ageLabel(memory.at,now)}</span>{memory.text}</p>):<p>My story starts with my first useful action.</p>}</div>
    <details className="resident-original" open={historyOpen} onToggle={event=>setHistoryOpen(event.currentTarget.open)}><summary>Original photo & battle stories</summary>{historyOpen&&<ResidentHistory character={character}/>}</details>
  </aside>
}
function ProjectInspector({project,active,busy,onPrioritize,onClose}:{project:IslandProject;active:boolean;busy:boolean;onPrioritize:()=>void;onClose:()=>void}){
  return <aside className="island-inspector project-inspector" aria-label={`${project.name} blueprint`}><div className="island-panel-top"><span>ISLAND BLUEPRINT</span><button onClick={onClose} aria-label="Close project"><X size={16}/></button></div><div className="project-seal"><Hammer size={36}/></div><span className="project-state">{project.status==='complete'?'BUILT TOGETHER':active?'CURRENT PRIORITY':'NEXT ON THE ISLAND'}</span><h2>{project.name}</h2><span className="project-level-label">LEVEL {project.level} / {project.max_level} · {project.level>0?'UPGRADE IN PLACE':'FOUNDATION'}</span><p>{project.description}</p><div className="project-progress-title"><b>{progressPercent(project)}%</b><span>{project.progress} / {project.required_progress} work</span></div><div className="island-progress-track"><span style={{width:`${progressPercent(project)}%`}}/></div><div className="project-cost"><span>EACH BUILD ACTION USES</span><b>{resourceText(project.cost_per_action)||'A little teamwork'}</b></div><div className="project-reward"><Flag size={17}/><div><span>WHY BUILD IT?</span><p>{typeof project.reward==='string'?project.reward:JSON.stringify(project.reward)}</p></div></div>{project.status!=='complete'&&<button className="island-primary" onClick={onPrioritize} disabled={busy||active}>{active?<Check size={16}/>:<Target size={16}/>} {active?'TEAM IS FOCUSED HERE':'MAKE THIS THE PRIORITY'}</button>}{active&&<p className="island-small-note">Autonomous residents gather what is missing, then build. Assign a resident to change their contribution.</p>}</aside>
}

export default function WorldView({onBack,arrivalIds=[]}:{onBack:()=>void;arrivalIds?:string[]}){
  const [data,setData]=useState<WorldData|null>(null),[simulation,setSimulation]=useState<Simulation|null>(null)
  const [loading,setLoading]=useState(true),[error,setError]=useState(''),[simError,setSimError]=useState(''),[commandError,setCommandError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(''),[attempt,setAttempt]=useState(0)
  const [selectedId,setSelectedId]=useState<string|null>(null),[selectedProjectId,setSelectedProjectId]=useState<string|null>(null),[view,setView]=useState<'island'|'collection'>('island'),[sceneFailed,setSceneFailed]=useState(false)
  const [visible,setVisible]=useState(!document.hidden),[reducedMotion,setReducedMotion]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches),[cameraResetKey,setCameraResetKey]=useState(0),[followSelected,setFollowSelected]=useState(false),[now,setNow]=useState(Date.now())
  const arrived=useRef(new Set<string>()),commandAbort=useRef<AbortController|null>(null),clockOffset=useRef(0),personaKey=useRef<string|null>(null),busyRef=useRef(false)
  useEffect(()=>{const controller=new AbortController();const timeout=window.setTimeout(()=>controller.abort('timeout'),15000);setLoading(true);setError('');void requestJSON<WorldData>('/api/world',controller.signal).then(result=>{if(!result?.world||!Array.isArray(result.characters))throw new Error('The world returned an unexpected response.');if(!controller.signal.aborted)setData(result)}).catch(reason=>{if(!controller.signal.aborted||controller.signal.reason==='timeout')setError(controller.signal.reason==='timeout'?'The local server took too long to respond. Check that it is running, then retry.':reason.message)}).finally(()=>{window.clearTimeout(timeout);if(!controller.signal.aborted||controller.signal.reason==='timeout')setLoading(false)});return()=>{controller.abort();window.clearTimeout(timeout)}},[attempt])
  useEffect(()=>{const onVisibility=()=>setVisible(!document.hidden);const query=window.matchMedia('(prefers-reduced-motion: reduce)');const onMotion=()=>setReducedMotion(query.matches);document.addEventListener('visibilitychange',onVisibility);query.addEventListener('change',onMotion);return()=>{document.removeEventListener('visibilitychange',onVisibility);query.removeEventListener('change',onMotion)}},[])
  useEffect(()=>{if(!visible||!data)return;const controller=new AbortController();let timer:number|undefined;const poll=async()=>{try{const result=await requestJSON<Simulation>('/api/island',controller.signal);if(!controller.signal.aborted){setSimulation(result);setSimError('');if(result.server_time)clockOffset.current=Date.parse(result.server_time)-Date.now()}}catch(reason){if(!controller.signal.aborted)setSimError(reason instanceof Error?reason.message:'The simulation could not be reached.')}finally{if(!controller.signal.aborted)timer=window.setTimeout(()=>void poll(),3000)}};void poll();return()=>{controller.abort();window.clearTimeout(timer)}},[visible,data?.world.id,attempt])
  useEffect(()=>{if(!visible)return;const timer=window.setInterval(()=>setNow(Date.now()+clockOffset.current),1000);return()=>window.clearInterval(timer)},[visible])
  useEffect(()=>()=>commandAbort.current?.abort(),[])
  const act=async(kind:string,body:Record<string,unknown>={})=>{
    if(busyRef.current)return;busyRef.current=true;setBusy(kind);setCommandError('');setNotice('');const controller=new AbortController();commandAbort.current=controller;const timeout=window.setTimeout(()=>controller.abort('timeout'),20000)
    try{const endpoint=kind==='start'?'/api/island/start':kind==='personas'?'/api/island/personas':kind==='planner'?'/api/island/planner':'/api/island/command';if(kind==='personas'&&!personaKey.current)personaKey.current=crypto.randomUUID();const payload=kind==='start'?{}:kind==='personas'?{idempotency_key:personaKey.current}:kind==='planner'?body:{idempotency_key:crypto.randomUUID(),kind,...body};await requestJSON<unknown>(endpoint,controller.signal,{method:'POST',body:JSON.stringify(payload)});if(kind==='personas'){personaKey.current=null;setNotice('A bounded AI reflection was requested. Residents keep working while it runs.')}const result=await requestJSON<Simulation>('/api/island',controller.signal);if(!controller.signal.aborted){setSimulation(result);if(result.server_time)clockOffset.current=Date.parse(result.server_time)-Date.now()}}
    catch(reason){if(!controller.signal.aborted||controller.signal.reason==='timeout')setCommandError(controller.signal.reason==='timeout'?'The request timed out. Refresh to check whether it was saved.':reason instanceof Error?reason.message:'The change could not be saved.')}
    finally{window.clearTimeout(timeout);busyRef.current=false;if(!controller.signal.aborted||controller.signal.reason==='timeout')setBusy('')}
  }
  const enabled=Boolean(simulation?.enabled),collectionMode=view==='collection'||sceneFailed
  const agents=simulation?.agents??[],projects=simulation?.projects??[],events=simulation?.events??[]
  const selected=data?.characters.find(character=>character.id===selectedId),selectedAgent=agents.find(agent=>agent.character_id===selectedId)
  const activeProject=projects.find(project=>project.id===simulation?.active_project_id),project=projects.find(item=>item.id===selectedProjectId)
  const newcomers=data?.characters.filter(character=>!agents.some(agent=>agent.character_id===character.id))??[]
  const activeLimit=simulation?.limits?.max_active_agents??MAX_ISLAND_RESIDENTS
  const plannerBusy=Boolean(simulation?.planner?.pending_run_id)||['queued','running','applying'].includes(simulation?.planner?.last_status??'')
  const plannerRetry=Boolean(simulation?.planner?.uncertain||simulation?.planner?.auto_blocked)
  const completedProjects=projects.filter(item=>item.level>0).length
  const projectUpgrades=projects.reduce((total,item)=>total+item.level,0)
  const selectResident=(id:string)=>{setSelectedId(id);setSelectedProjectId(null)}
  const selectProject=(id:string)=>{setSelectedProjectId(id);setSelectedId(null);setFollowSelected(false)}
  const onSceneFailure=()=>{setSceneFailed(true);setView('collection')}
  const simNow=simulation?.paused&&simulation.paused_at?Date.parse(simulation.paused_at):now

  return <section className="world-screen" aria-label="Sketch Clash island">
    <div className="island-heading"><div><span className="world-eyebrow"><Globe2 size={13}/> AFTER THE CLASH</span><h1>SMALL OBJECTS.<em>BIG PLANS.</em></h1></div><button className="world-back-button" onClick={onBack}><ArrowLeft size={16}/> BACK TO THE ARCADE</button></div>
    {data?.persistence==='development_memory'&&<p className="world-development-note" role="status"><strong>TEMPORARY WORLD</strong> MongoDB is not connected. This island disappears when the local server restarts.</p>}
    {loading&&<div className="world-state"><span className="world-state-star">✳</span><h2>ROUNDING UP THE RESIDENTS…</h2><p role="status">Opening their saved island.</p></div>}
    {!loading&&error&&<div className="world-state"><Globe2 size={40}/><h2>THE ISLAND IS OUT OF REACH.</h2><p role="alert">{error}</p><button className="arcade-button" onClick={()=>setAttempt(value=>value+1)}>TRY AGAIN <RefreshCw size={19}/></button></div>}
    {!loading&&!error&&data&&<>
      <div className="island-status-bar"><div className="island-world-name"><span className={`island-status-dot ${simulation?.paused?'is-paused':''}`}/><b>{data.world.name}</b><span>{enabled?`LEVEL ${simulation?.growth_level??1}`:'READY TO GROW'}</span></div><div className="island-resources">{Object.entries(RESOURCE_ICONS).map(([resource,Icon])=><div key={resource} title={resource}><Icon size={16}/><strong>{Math.floor(simulation?.resources?.[resource as keyof typeof RESOURCE_ICONS]??0)}</strong><span>{RESOURCE_LABELS[resource]}</span></div>)}</div></div>
      {(commandError||simError)&&<p className="island-message is-error" role="alert">{commandError||simError}<button onClick={()=>{setCommandError('');setAttempt(value=>value+1)}}>REFRESH</button></p>}{notice&&<p className="island-message" role="status">{notice}</p>}
      {enabled&&newcomers.length>0&&<div className="island-welcome"><p><b>{newcomers.length} {newcomers.length===1?'RESIDENT IS':'RESIDENTS ARE'} READY FOR A ROLE.</b><span>{agents.length<activeLimit?'Bring your new arrivals into the crew. Their appearance and battle history stay the same.':`Your ${activeLimit}-resident active crew is full. Extra residents stay safely in the collection.`}</span></p>{agents.length<activeLimit&&<button disabled={Boolean(busy)} onClick={()=>void act('start')}><Sparkles size={14}/>{busy==='start'?'WELCOMING…':'WELCOME NEW RESIDENTS'}</button>}</div>}
      <div className="island-toolbar"><div><span>{data.characters.length} RESIDENTS</span><span>{completedProjects} / {projects.length||'—'} PROJECTS BUILT</span>{(simulation?.expeditions??0)>0&&<span>{simulation?.expeditions} EXPEDITIONS</span>}</div><div>{enabled&&<button disabled={Boolean(busy)} onClick={()=>void act(simulation?.paused?'resume':'pause')}>{simulation?.paused?<Play size={13}/>:<Pause size={13}/>} {simulation?.paused?'RESUME ISLAND':'PAUSE ISLAND'}</button>}<button aria-pressed={!collectionMode} onClick={()=>setView('island')} disabled={sceneFailed}><Globe2 size={14}/> ISLAND</button><button aria-pressed={collectionMode} onClick={()=>setView('collection')}><Grid2X2 size={14}/> ROSTER</button></div></div>
      <div className="island-workspace">
        <div className="island-stage-column">
          {!collectionMode?<div className="world-diorama"><div className="island-scene-label"><span className="scene-live-dot"/> {enabled?(simulation?.paused?'ON A LITTLE BREAK':'LITTLE JOBS. REAL PROGRESS.'):'YOUR NEXT CHAPTER STARTS HERE'}</div><SceneBoundary onFailure={onSceneFailure}><Suspense fallback={<div className="world-scene-loading" role="status">Opening the island…</div>}><WorldScene characters={data.characters.slice(0,MAX_ISLAND_RESIDENTS)} layoutSeed={data.world.layout_seed} selectedId={selectedId} onSelect={selectResident} active={visible} reducedMotion={reducedMotion} arrivalIds={arrivalIds.filter(id=>!arrived.current.has(id))} onArrived={id=>arrived.current.add(id)} onFailure={onSceneFailure} simulation={simulation??undefined} selectedProjectId={selectedProjectId} onProjectSelect={selectProject} cameraResetKey={cameraResetKey} followSelected={followSelected}/></Suspense></SceneBoundary><div className="island-camera-controls">{selectedId&&<button aria-pressed={followSelected} onClick={()=>setFollowSelected(value=>!value)}><Target size={15}/>{followSelected?'FOLLOWING':'FOLLOW'}</button>}<button onClick={()=>{setCameraResetKey(value=>value+1);setFollowSelected(false)}}><Maximize2 size={15}/> RESET VIEW</button></div><div className="world-map-caption">DRAG TO ORBIT <span>✦</span> SCROLL TO ZOOM <span>✦</span> SELECT A RESIDENT OR BUILD SITE</div></div>:<div className="island-roster-view">{sceneFailed&&<p className="world-render-note">3D is unavailable here. Your saved residents and island controls still work.</p>}<h2>THE UNLIKELY WORKFORCE</h2><div className="world-resident-grid">{data.characters.map(character=>{const agent=agents.find(item=>item.character_id===character.id);return <button className={`world-resident ${selectedId===character.id?'is-selected':''}`} key={character.id} onClick={()=>selectResident(character.id)} aria-pressed={selectedId===character.id}><img src={character.image_ref} alt={character.object_type}/><strong>{character.display_name}</strong><small>{agent?.persona.role??character.object_type}</small><span>{agent?`LEVEL ${agent.level} · ${agent.xp} XP`:`${character.distinct_battle_count} BATTLES`}</span></button>})}</div></div>}
          {data.characters.length>0&&!collectionMode&&<div className="island-resident-dock"><span>YOUR CREW</span>{data.characters.slice(0,MAX_ISLAND_RESIDENTS).map(character=>{const agent=agents.find(item=>item.character_id===character.id);return <button key={character.id} className={selectedId===character.id?'is-selected':''} onClick={()=>selectResident(character.id)} title={`${character.display_name} · ${agent?.persona.role??character.object_type}`} aria-label={`Inspect ${character.display_name}`} aria-pressed={selectedId===character.id}><img src={character.image_ref} alt=""/><span>{agent?.level??1}</span></button>})}<button className="island-add-resident" onClick={onBack} title="Play a battle to add more residents">+<small>CLASH</small></button></div>}
        </div>
        {selected&&selectedAgent?<AgentInspector key={selected.id} agent={selectedAgent} character={selected} now={simNow} paused={Boolean(simulation?.paused)} busy={Boolean(busy)} onAssign={assignment=>void act('assign',{character_id:selected.id,assignment})} onClose={()=>{setSelectedId(null);setFollowSelected(false)}}/>:selected?<aside className="island-inspector"><div className="island-panel-top"><span>RESIDENT FILE</span><button onClick={()=>setSelectedId(null)} aria-label="Close resident"><X size={16}/></button></div><h2>{selected.display_name}</h2><p>{enabled?'This resident is saved in your collection. Up to 40 residents can work on the island at once.':'Start the island to give this resident a role, useful tasks and a memory of what they build.'}</p><ResidentHistory character={selected}/></aside>:project?<ProjectInspector project={project} active={project.id===simulation?.active_project_id} busy={Boolean(busy)} onPrioritize={()=>void act('priority',{project_id:project.id})} onClose={()=>setSelectedProjectId(null)}/>:<aside className="island-inspector island-mission"><div className="island-panel-top"><span>THE NEXT BIG LITTLE THING</span><Flag size={16}/></div><div className="mission-number">{enabled?String(projectUpgrades+1).padStart(2,'0'):'GO'}<StarMark/></div><h2>{!data.characters.length?'EVERY WORLD NEEDS A FIRST HERO.':!enabled?'GIVE YOUR OBJECTS A PURPOSE.':activeProject?.name??'A PLACE BUILT TOGETHER.'}</h2><p>{!data.characters.length?'Finish a real-object battle to bring two residents home.':!enabled?'A mug carries water. A pencil turns ideas into plans. Your residents use what makes them useful to build this island.':activeProject?.description??'Your crew keeps gathering, growing and remembering the work they do.'}</p>{activeProject&&enabled&&<><div className="project-progress-title"><b>{progressPercent(activeProject)}%</b><span>BUILT TOGETHER</span></div><div className="island-progress-track"><span style={{width:`${progressPercent(activeProject)}%`}}/></div></>}{!data.characters.length?<button className="island-primary" onClick={onBack}>FIND YOUR FIRST FIGHTERS <ArrowRight size={16}/></button>:!enabled?<button className="island-primary" disabled={Boolean(busy)||!simulation} onClick={()=>void act('start')}>{busy==='start'?<LoaderCircle className="island-spinner" size={16}/>:<Play size={16}/>}START BUILDING</button>:activeProject?<button className="island-primary" onClick={()=>selectProject(activeProject.id)}>OPEN THE BLUEPRINT <ChevronRight size={17}/></button>:<span className="island-complete-stamp">ALL PROJECTS COMPLETE <Check size={16}/></span>}{!enabled&&data.characters.length>0&&<p className="island-start-note">{simulation?.planner?.configured?'Starting enables occasional AI plans: up to 12 bounded requests a day. Switch AI off anytime; everyday tasks run without model calls.':'Object-based roles and everyday work run without model calls. AI planning is available when the local server has a configured provider.'}</p>}<div className="mission-instruction"><span>01</span><p>Set the next project.<br/><b>Give the crew something worth building.</b></p></div><div className="mission-instruction"><span>02</span><p>Tap a resident.<br/><b>Read their memories. Change their job.</b></p></div><div className="mission-instruction"><span>03</span><p>Watch your island grow.<br/><b>Resources become places. Work earns XP.</b></p></div></aside>}
      </div>
      {enabled&&<><div className="island-section-heading"><h2>BUILD SOMETHING THAT STAYS.</h2><span>SELECT A BLUEPRINT TO CHANGE THE CREW’S PRIORITY</span></div><div className="island-projects">{projects.map(item=><button className={`island-project-card ${item.id===simulation?.active_project_id?'is-active':''} ${item.status==='complete'?'is-complete':''} ${selectedProjectId===item.id?'is-selected':''}`} key={item.id} onClick={()=>selectProject(item.id)} aria-pressed={selectedProjectId===item.id}><div><span>{item.status==='complete'?<Check size={15}/>:<Hammer size={15}/>}</span><small>{item.status==='complete'?'COMPLETE':item.id===simulation?.active_project_id?'CREW PRIORITY':'BLUEPRINT'}</small><b>{progressPercent(item)}%</b></div><h3>{item.name}</h3><span className="project-level-label">LEVEL {item.level} / {item.max_level}</span><p>{item.description}</p><div className="island-progress-track"><span style={{width:`${progressPercent(item)}%`}}/></div></button>)}</div><div className="island-bottom-grid"><section className="island-ledger"><div className="island-section-heading"><h2>THE ISLAND IS GETTING ON WITH IT.</h2><span>LIVE WORK LOG</span></div>{events.length?events.slice(-6).reverse().map(event=><div className="island-event" key={event.id}><span className={`event-mark event-${event.kind}`}>{event.kind==='reflection'?<Sparkles size={13}/>:event.kind.includes('complet')?<Check size={13}/>:<Hammer size={13}/>}</span><p><b>{event.title}</b><span>{event.description}</span></p><small>{ageLabel(event.at,now)}</small></div>):<p className="island-empty-log">The first job is underway. Completed work appears here.</p>}</section><aside className="island-runtime"><span className="world-eyebrow"><Sparkles size={13}/> SMALL BRAINS. LASTING MEMORIES.</span><h3>PERSONALITY WITH A PURPOSE.</h3><p>Residents remember completed jobs and use their object’s abilities. AI reflections can shape their next plans; the local simulation handles everyday work.</p>{simulation?.planner&&<><div className="planner-budget"><span>AI REFLECTIONS TODAY</span><b>{simulation.planner.requests_today??'—'} / {simulation.planner.max_requests_per_day??'—'}</b></div><label className="planner-switch"><input type="checkbox" checked={simulation.planner.enabled} disabled={Boolean(busy)||simulation.planner.configured!==true} onChange={event=>void act('planner',{enabled:event.target.checked})}/><span>OCCASIONAL AI PLANNING</span><b>{simulation.planner.enabled?'ON':'OFF'}</b></label><p className="planner-status">{simulation.planner.uncertain?'The last provider result is uncertain. It may have used quota. You can request one explicit retry after the server cooldown.':simulation.planner.auto_blocked?'AI planning paused after a provider issue. The previous call may have used quota; an explicit retry is available after the server cooldown.':simulation.planner.enabled?`Planner: ${(simulation.planner.last_status??'ready').replaceAll('_',' ')}`:'AI planning is off. Object-based roles keep the island running.'}</p><button className="world-inline-button" disabled={Boolean(busy)||!simulation.planner.enabled||simulation.planner.configured!==true||simulation.paused||plannerBusy||simulation.planner.requests_today>=simulation.planner.max_requests_per_day} onClick={()=>void act('personas')}><RefreshCw size={13}/> {busy==='personas'?'REQUESTING…':plannerBusy?'AI IS REFLECTING…':plannerRetry?'RETRY AI ONCE':'REFRESH PLANS'}</button></>}<p className="island-runtime-note">Saved in {data.persistence==='mongodb'?'MongoDB Atlas':'temporary server memory'}. Work runs while your local backend is awake. Returning after a stop simulates up to 2 minutes, not unlimited offline gains.</p>{simulation&&simulation.catch_up?.discarded_seconds>0&&<p className="island-runtime-note">Last return: {Math.round(simulation.catch_up.simulated_seconds)}s simulated. Longer time away was capped.</p>}</aside></div></>}
      <div className="world-footnote"><span><Box size={13}/> One resident per object type. Their original accepted appearance stays with them.</span><span>{reducedMotion?'REDUCED MOTION':'STATE SAVES. STORIES CONTINUE.'}</span></div>
    </>}
  </section>
}
function StarMark(){return <svg viewBox="0 0 100 100" aria-hidden="true"><path d="m50 2 12 27 29-7-13 28 20 22-31 2-13 25-12-28-30 5 16-27L8 26l30 4Z"/></svg>}
