import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent, useReducedMotion, useTransform, type MotionValue } from 'motion/react';
import { ArrowRight, ArrowUpRight, Globe2, Pencil, Play, RotateCcw, SlidersHorizontal, Sparkles, X } from 'lucide-react';
import type { Fighter, Phase } from './types';
import { PRESET_FIGHTERS } from './game/fixtures';
import { useTimeline } from './game/director';
import { CaptureStudio, type CaptureInput, type CaptureResponse } from './components/CaptureStudio';
import { api, post, asFighter, asPair, type BattleRecord, type Health, type PendingFighter, type FeedbackInput, type CorrectionInput } from './lib/api';
import './LiveFlow.css';
const WorldView = lazy(()=>import('./components/WorldView'));
const ColoniesView = lazy(()=>import('./components/ColoniesView'));
const QualityConsole = lazy(()=>import('./components/QualityConsole'));
import BattleArena from './components/BattleArena';

const spring = { type: 'spring' as const, stiffness: 320, damping: 21 };
const PHASE_LABEL: Record<Phase, string> = { HOME: 'THE SKETCHBOOK ARCADE', THEME: 'ROUND 01 · THE BRIEF', DRAW_P1: 'ROUND 01 · CAMERAS READY', DRAW_P2: 'ROUND 01 · CAMERAS READY', REVEAL: 'ROUND 01 · MEET THE FIGHTERS', BATTLE: 'ROUND 01 · THE SHOWDOWN', RESULTS: 'ROUND 01 · THAT’S A WRAP', WORLD:'THE TALE OF TWO ISLANDS', QUALITY:'RECOGNITION & WORLD QUALITY' };

function Star({ className = '', color = 'currentColor' }: { className?: string; color?: string }) {
  return <svg className={className} viewBox="0 0 100 100" fill={color} aria-hidden="true"><path d="M51 3 62 35 96 31 73 54 89 88 54 72 25 96 28 61 2 43 37 36Z" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" /></svg>;
}
function Burst({ className = '' }: {className?: string}) {
  return <svg className={className} viewBox="0 0 500 500" aria-hidden="true"><path d="M247 9 276 107 340 39 335 136 437 99 384 188 490 207 396 252 478 320 374 320 408 421 320 366 300 487 244 391 174 478 171 375 69 417 119 321 9 302 109 248 24 180 127 179 94 74 184 128Z" fill="currentColor" /></svg>;
}
function Crown({ className = '' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 200 130" aria-hidden="true"><path d="m21 100-9-72 53 30 37-49 30 54 54-28-21 74Z" fill="#FFD166" stroke="#1E1C29" strokeWidth="6" strokeLinejoin="round"/><path d="m25 113 138 7M44 32 34 13m116 10 12-16M98 3V0" stroke="#1E1C29" strokeWidth="5" strokeLinecap="round"/><path d="m47 87 94 5" stroke="#1E1C29" strokeWidth="4" strokeLinecap="round"/></svg>;
}
function ActionButton({children,onClick,className='',label,disabled=false}:{children:React.ReactNode;onClick:()=>void;className?:string;label?:string;disabled?:boolean}) {
  return <motion.button type="button" className={`arcade-button ${className}`} onClick={onClick} aria-label={label} disabled={disabled} whileHover={{y:-3,rotate:-1}} whileTap={{y:4,x:3,boxShadow:'0px 0px 0px var(--ink)'}} transition={spring}>{children}</motion.button>;
}

function LandingScreen({onPlay,onDemo,onIsland,quick,setQuick}:{onPlay:()=>void;onDemo:()=>void;onIsland:()=>void;quick:boolean;setQuick:(value:boolean)=>void}) {
  const reduced=useReducedMotion();
  return <motion.main className="landing" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0,y:-22}}>
    <div className="landing-note note-left">a little imagination.<br/>a lot of chaos.<svg viewBox="0 0 100 70" aria-hidden="true"><path d="M5 8q66-4 65 45m-13-9 13 15 13-17"/></svg></div>
    <div className="landing-note note-right">one wins the clash.<br/>both get a new chapter.<Star /></div>
    <div className="hero-eyebrow"><span className="tiny-star">✳</span> ORDINARY OBJECTS. EXTRAORDINARY GRUDGES. <span className="tiny-star">✳</span></div>
    <div className="hero-grid">
      <motion.div className="hero-fighter hero-fighter-left" initial={{x:-60,opacity:0,rotate:-14}} animate={{x:0,opacity:1,rotate:-8}} transition={{...spring,delay:.18}}>
        <div className="fighter-paper coral-paper"><span className="tape tape-top"/><div className="paper-grid"/>
          <motion.img src={PRESET_FIGHTERS[0].image} alt="Scratch, a mischievous hand-drawn cat" animate={reduced?{}:{y:[0,-8,0],rotate:[-3,1,-3]}} transition={{duration:4,repeat:Infinity,ease:'easeInOut'}} draggable={false}/>
          <div className="mini-player">P1 <span>SCRATCH</span></div><div className="paper-caption">HAS CLAWS. WILL DOODLE.</div>
        </div><Star className="fighter-star star-one" color="var(--yellow)"/>
      </motion.div>
      <div className="hero-center">
        <h1 className="hero-logo" aria-label="Sketch Clash"><motion.span className="logo-sketch" initial={{y:-50,rotate:-9,opacity:0}} animate={{y:0,rotate:-4,opacity:1}} transition={{...spring,delay:.05}}>SKETCH</motion.span><motion.span className="logo-clash" initial={{scale:.6,rotate:8,opacity:0}} animate={{scale:1,rotate:-5,opacity:1}} transition={{...spring,delay:.2}}>CLASH<span className="logo-period">!</span></motion.span></h1>
        <motion.p className="hero-tagline" initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{delay:.4}}>SNAP. CLASH. PICK A SHORE.</motion.p>
        <p className="hero-description">Winners get an island. So do the losers.<br/>Whose little crew will build something great?</p>
        <div className="hero-actions"><ActionButton onClick={onPlay}>LET’S PLAY <ArrowRight size={27}/></ActionButton><motion.button className="demo-button" onClick={onDemo} whileHover={{x:3}} whileTap={{scale:.97}}><Play size={15} fill="currentColor"/> WATCH THE SHOWDOWN <ArrowUpRight size={15}/></motion.button></div>
        <label className="quick-toggle"><input type="checkbox" checked={quick} onChange={e=>setQuick(e.target.checked)}/><span className="toggle-track"><span/></span> QUICK CLASH <span className="toggle-seconds">{quick?'20':'60'} SEC / PLAYER</span></label>
        <button className="home-colonies-entry" onClick={onIsland}><Globe2 size={16}/><span>ENTER THE ISLANDS<small>TWO CREWS. PLENTY TO PROVE.</small></span><ArrowUpRight size={17}/></button>
      </div>
      <motion.div className="hero-fighter hero-fighter-right" initial={{x:60,opacity:0,rotate:13}} animate={{x:0,opacity:1,rotate:7}} transition={{...spring,delay:.28}}>
        <div className="fighter-paper mint-paper"><span className="tape tape-top"/><div className="paper-grid"/>
          <motion.img src={PRESET_FIGHTERS[1].image} alt="Chomps, a goofy hand-drawn dinosaur" animate={reduced?{}:{y:[-5,3,-5],rotate:[2,-2,2]}} transition={{duration:4.6,repeat:Infinity,ease:'easeInOut'}} draggable={false}/>
          <div className="mini-player">P2 <span>CHOMPS</span></div><div className="paper-caption">SMALL ARMS. BIG ENERGY.</div>
        </div><Star className="fighter-star star-two" color="var(--coral)"/>
      </motion.div>
    </div>
    <button className="no-skills-stamp island-stamp" onClick={onIsland}>ONE WINNER.<br/><b>TWO NEW CHAPTERS.</b><span>VISIT THE RIVAL ISLANDS <ArrowUpRight size={11}/></span></button>
    <div className="how-strip"><div><span className="step-number">01</span><p><b>FIND AN OBJECT</b><span>A mug. A bottle. Your everyday champion.</span></p></div><div><span className="step-number">02</span><p><b>SNAP. THEN CLASH.</b><span>Two players. Camera or photo upload.</span></p></div><div><span className="step-number">03</span><p><b>TWO CREWS. ONE RIVALRY.</b><span>They talk, share work and build their shores.</span></p></div></div>
  </motion.main>;
}

function ThemeReveal({onComplete}:{onComplete:()=>void}) {
  const reduced=useReducedMotion();
  const clock=useTimeline(4200,onComplete);
  const [beat,setBeat]=useState(0);
  useMotionValueEvent(clock,'change',t=>setBeat(t<1700?Math.floor(t/125):t<2700?20:t<3400?21:22));
  const rotate=useTransform(clock,[0,250,800,1200,1700,1950,2200],[0,-10,8,-6,5,-4,-3]);
  const scale=useTransform(clock,[0,450,1550,1750,2050],[.7,1,.95,1.12,1]);
  const names=['MUGS','BOTTLES','BOOKS','EVERYDAY OBJECTS'];
  return <main className="theme-screen"><div className="eyebrow round-ribbon">ROUND 01 <span>THE PAGE IS YOURS</span></div><p className="section-kicker">AND YOUR THEME IS…</p><div className="theme-stage"><Burst className="theme-burst"/><motion.div className="theme-card" style={reduced?{}:{rotate,scale}}><div className="theme-card-top"><Pencil size={20}/><span>THE CAMERA BRIEF</span><span>001</span></div><div className="theme-paw">✳</div><h1>{beat<20?names[beat%names.length]:'EVERYDAY OBJECTS'}</h1><p>Ordinary things. Unreasonable attitude.</p><div className="theme-rule">One visible object per player. Camera or upload.</div><span className="tape tape-top"/></motion.div><Star className="theme-star" color="var(--mint)"/></div><div className="theme-countdown" aria-live="polite">{beat<20?'SHUFFLING THE SKETCHBOOK…':beat===20?'CAMERAS READY?':beat===21?'3… 2…':'FIND YOUR CHAMPION!'}</div></main>;
}

function RevealFighter({fighter,clock}:{fighter:Fighter;clock:MotionValue<number>}) {
  const reduced=useReducedMotion(); const delay=fighter.side*600;
  const y=useTransform(clock,[0,600+delay,1000+delay,1900+delay,5400,5900,6300],[0,0,-18,-70,-70,8,0]);
  const rotate=useTransform(clock,[0,700+delay,1800+delay,5400,5900,6300],[fighter.side?-4:4,fighter.side?-4:4,fighter.side?8:-8,fighter.side?8:-8,fighter.side?-3:3,0]);
  const scale=useTransform(clock,[0,700+delay,1900+delay,5700,5900,6300],[.85,.85,1.09,1.09,1.16,1]);
  const pageRotate=useTransform(clock,[0,600+delay,1800+delay,3500],[0,0,fighter.side?14:-14,fighter.side?14:-14]);
  const pageOpacity=useTransform(clock,[0,3400,4600],[1,1,0]);
  const burstScale=useTransform(clock,[0,1100+delay,1500+delay,3000,4300],[0,0,1.2,1,0]);
  const labelOpacity=useTransform(clock,[0,1700+delay,2200+delay],[0,0,1]);
  return <div className={`reveal-fighter reveal-side-${fighter.side}`} style={{'--fighter-color':fighter.color} as React.CSSProperties}>
    <motion.div className="reveal-sheet" style={reduced?{opacity:pageOpacity}:{rotate:pageRotate,opacity:pageOpacity}}><span className="reveal-perforation"/><span className="reveal-sheet-caption">ORIGINAL MASTERPIECE · P{fighter.side+1}</span></motion.div>
    <motion.div className="reveal-inkburst" style={{scale:reduced?0:burstScale}}><Burst/></motion.div>
    <motion.img className={`reveal-drawing ${fighter.kind==='photo'?'photo-fighter':''}`} src={fighter.image} alt={`${fighter.name}, the original ${fighter.kind==='photo'?'photograph':'drawing'} lifting off the page`} style={reduced?{}:{y,rotate,scale}} draggable={false}/>
    <div className="reveal-floor-shadow"/>
    <motion.div className="reveal-name" style={{opacity:labelOpacity}}><span>PLAYER {fighter.side+1}</span><h2>{fighter.name}</h2><p>{fighter.subtitle}</p><div className="fighter-attribute"><b>{fighter.archetype??(fighter.side===0?'QUICK & SCRAPPY':'HEAVY HITTER')}</b><span>{fighter.side===0?'100':'100'} HP</span></div></motion.div>
  </div>;
}
function FighterReveal({fighters,onComplete,isDemo}:{fighters:[Fighter,Fighter];onComplete:()=>void;isDemo:boolean}) {
  const clock=useTimeline(7000,onComplete);
  const vsScale=useTransform(clock,[0,3500,3850,4100,6100,6500],[0,0,1.4,1,1,0]);
  return <main className="reveal-screen"><div className="section-heading"><span className="eyebrow">FROM THE PAGE TO THE RAGE</span><h1>IT’S ALIVE<span>!</span></h1><p>{isDemo?'Two sketchbook originals. One very personal showdown.':'Your real photographs. A whole new attitude.'}</p></div><div className="reveal-stage"><RevealFighter fighter={fighters[0]} clock={clock}/><motion.div className="reveal-vs" style={{scale:vsScale}}>VS<span>✦</span></motion.div><RevealFighter fighter={fighters[1]} clock={clock}/></div><div className="bottom-caption">{isDemo?'CINEMATIC DEMO · NO UNLOCKS':'ORIGINAL PHOTOGRAPHS'} <span>✳</span> {isDemo?'SCRIPTED SHOWDOWN':'VALIDATED FIGHTERS'}</div></main>;
}

function VictoryScreen({fighters,onAgain,onReplay,winner=0}:{fighters:[Fighter,Fighter];onAgain:()=>void;onReplay:()=>void;winner?:0|1}) {
  const reduced=useReducedMotion();
  return <motion.main className="victory-screen" initial={{opacity:0}} animate={{opacity:1}}><div className="victory-rays"/><div className="victory-topline"><span>THE INK HAS SETTLED</span><span>PLAYER 0{winner+1} WINS</span></div><motion.div className="victory-title" initial={reduced?{}:{scale:1.6,rotate:-7}} animate={{scale:1,rotate:-4}} transition={spring}>VICTORY<span>!</span></motion.div><div className="victory-stage"><Burst className="victory-burst"/><motion.div className={`victory-hero ${fighters[winner].kind==='photo'?'photo-winner':''}`} initial={{y:40,opacity:0}} animate={reduced?{y:0,opacity:1}:{y:[0,-15,0],opacity:1,rotate:[-3,3,-3]}} transition={{y:{duration:1.9,repeat:Infinity,ease:'easeInOut'},rotate:{duration:1.9,repeat:Infinity,ease:'easeInOut'},opacity:{duration:.3}}}><Crown className="winner-crown"/><img src={fighters[winner].image} alt={`${fighters[winner].name}, the winning original fighter`}/></motion.div><div className={`victory-loser ${fighters[1-winner].kind==='photo'?'photo-loser':''}`}><img src={fighters[1-winner].image} alt="The defeated fighter folded into a paper ball"/><span>…rematch?</span></div>{Array.from({length:16},(_,i)=><motion.div key={i} className={`confetti confetti-${i%3}`} style={{left:`${10+(i*37)%80}%`,top:`${10+(i*23)%70}%`,rotate:i*31}} initial={{scale:0}} animate={reduced?{scale:1}:{scale:[0,1,1],y:[-25,0,30],rotate:[i*31,i*31+80]}} transition={{duration:2.5,delay:(i%5)*.12,repeat:reduced?0:Infinity,repeatType:'reverse'}}>{i%3===0?'✦':''}</motion.div>)}</div><div className="victory-name"><span>THE UNDISPUTED SKETCHBOOK CHAMPION</span><h2>{fighters[winner].name}</h2><p>A masterpiece? Debatable. A winner? Absolutely.</p></div><div className="victory-actions"><ActionButton onClick={onAgain}>PLAY AGAIN <Pencil size={23}/></ActionButton><button className="text-button" onClick={onReplay}><RotateCcw size={16}/> RUN IT BACK</button></div><div className="bottom-caption">ALL GLORY. NO ERASER.</div></motion.main>;
}

function captureResponse(result:any):CaptureResponse {
  return {capture_id:result.capture_id,status:result.status,image_url:result.image_ref,width:result.crop?.width??result.width,height:result.crop?.height??result.height,detections:result.candidates,fighter:result.pending_fighter??undefined,evidence:result.evidence,message:result.uncertainty?.join(' '),trace:result.pending_fighter?.validation,degraded:Object.values(result.evidence??{}).some((value:any)=>['failed','unavailable'].includes(value?.status)),output_id:result.output_id,pipeline_version_id:result.pipeline_version_id,observed_object:result.observed_object,saved_resident_preview:result.saved_resident_preview};
}

const ACTIVE_KEY='sketch-clash-active-battle';
const readActive=()=>{try{return localStorage.getItem(ACTIVE_KEY)}catch{return null}};
const saveActive=(id:string|null)=>{try{if(id)localStorage.setItem(ACTIVE_KEY,id);else localStorage.removeItem(ACTIVE_KEY)}catch{/* Server record remains the source of truth. */}};

export default function App() {
  const [phase,setPhase]=useState<Phase>('HOME');
  const [worldMode,setWorldMode]=useState<'colonies'|'legacy'>('colonies');
  const [quick,setQuick]=useState(false);
  const [isDemo,setIsDemo]=useState(false);
  const [fighters,setFighters]=useState<[Fighter,Fighter]>(PRESET_FIGHTERS);
  const [roundKey,setRoundKey]=useState(0);
  const [battle,setBattle]=useState<BattleRecord|null>(null);
  const [health,setHealth]=useState<Health|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState('');
  const [recovery,setRecovery]=useState<string|null>(readActive);
  const [reviewPending,setReviewPending]=useState<CaptureResponse|null>(null);
  const [confirming,setConfirming]=useState(false);
  const [saveState,setSaveState]=useState<'idle'|'saving'|'saved'|'error'>('idle');
  const currentBattle=useRef<BattleRecord|null>(null);
  const epoch=useRef(0);
  const createRequest=useRef<string|null>(null);
  const actionBusy=useRef(false);
  const reduced=!!useReducedMotion();
  useEffect(()=>{window.scrollTo({top:0,left:0,behavior:'instant'});},[phase]);
  const remember=useCallback((record:BattleRecord)=>{currentBattle.current=record;setBattle(record);saveActive(record.id)},[]);
  useEffect(()=>{let alive=true;api<Health>('/health').then(value=>{if(alive)setHealth(value)}).catch(()=>{});return()=>{alive=false}},[]);
  const home=useCallback(async()=>{
    if(actionBusy.current)return;
    const active=currentBattle.current;
    const generation=++epoch.current;
    actionBusy.current=true;setError('');
    try{
      if(active&&['draft','ready','running'].includes(active.status))await post(`/battles/${active.id}/cancel`);
      if(generation!==epoch.current)return;
      if(active||!readActive()){saveActive(null);setRecovery(null)}else setRecovery(readActive());currentBattle.current=null;setBattle(null);createRequest.current=null;
      setReviewPending(null);setPhase('HOME');setIsDemo(false);setFighters(PRESET_FIGHTERS);setRoundKey(k=>k+1);setSaveState('idle');
    }catch(e){setError((e as Error).message+' Your round is kept for recovery.');}
    finally{actionBusy.current=false;setBusy('')}
  },[]);
  async function play(){
    if(actionBusy.current)return;
    actionBusy.current=true;setBusy('Preparing a fresh page…');setError('');const generation=++epoch.current;
    try{
      const request=createRequest.current??crypto.randomUUID();createRequest.current=request;
      const record=await post<BattleRecord>('/battles',{request_id:request});
      if(generation!==epoch.current)return;
      remember(record);setRecovery(null);setReviewPending(null);setIsDemo(false);setFighters(PRESET_FIGHTERS);setSaveState('idle');setRoundKey(k=>k+1);setPhase('THEME');
    }catch(e){setError((e as Error).message)}finally{actionBusy.current=false;setBusy('')}
  }
  const demo=()=>{if(actionBusy.current)return;epoch.current++;setError('');setIsDemo(true);currentBattle.current=null;setBattle(null);setFighters(PRESET_FIGHTERS);setRoundKey(k=>k+1);setPhase('REVEAL')};
  const themeComplete=useCallback(()=>setPhase(current=>current==='THEME'?'DRAW_P1':current),[]);
  const prepare=useCallback(async(input:CaptureInput,signal:AbortSignal):Promise<CaptureResponse>=>{
    const record=currentBattle.current;if(!record)throw new Error('Create a round before capturing a fighter.');
    const slot=phase==='DRAW_P1'?0:1;
    const form=new FormData();form.append('image',input.file);form.append('capture_id',input.captureId);form.append('slot',String(slot));form.append('source',input.source);if(input.crop)form.append('crop',JSON.stringify(input.crop));
    const result=await api<any>(`/battles/${record.id}/captures`,{method:'POST',body:form,signal});
    if(result.stale)throw new Error('This photograph was replaced. Please use the latest capture.');
    return captureResponse(result);
  },[phase]);
  const feedback=useCallback((captureId:string,input:FeedbackInput)=>{
    const record=currentBattle.current;if(!record)throw new Error('This round is no longer active.');
    return post(`/battles/${record.id}/captures/${captureId}/feedback`,input);
  },[]);
  const correct=useCallback(async(captureId:string,input:CorrectionInput):Promise<CaptureResponse>=>{
    const record=currentBattle.current;if(!record)throw new Error('This round is no longer active.');
    return captureResponse(await post(`/battles/${record.id}/captures/${captureId}/correct`,input));
  },[]);
  async function confirm(fighter:PendingFighter){
    const active=currentBattle.current;if(!active)throw new Error('This round is no longer available. Return home and start again.');
    if(actionBusy.current)throw new Error('Another round action is finishing. Please retry.');
    actionBusy.current=true;setConfirming(true);
    const generation=epoch.current;
    try{
    const record=await post<BattleRecord>(`/battles/${active.id}/confirm`,{player_slot:fighter.player_slot,capture_id:fighter.capture_id});
    if(generation!==epoch.current)return;
    const accepted=record.pending_fighters[fighter.player_slot];
    if(!accepted||accepted.capture_id!==fighter.capture_id)throw new Error('This capture was replaced. Prepare the latest photograph again.');
    remember(record);setReviewPending(null);setFighters(previous=>{const pair:[Fighter,Fighter]=[...previous];pair[fighter.player_slot]=asFighter(accepted);return pair});
    setPhase(fighter.player_slot===0?'DRAW_P2':'REVEAL');
    }finally{actionBusy.current=false;setConfirming(false)}
  }
  const startBattle=useCallback(async()=>{
    if(actionBusy.current)return;
    if(isDemo){setPhase('BATTLE');return}
    const record=currentBattle.current;if(!record)return;
    actionBusy.current=true;setBusy('Setting the arena…');setError('');const generation=epoch.current;
    try{
      const started=await post<BattleRecord>(`/battles/${record.id}/start`,{playback_mode:quick?'quick':reduced?'reduced':'normal'});
      if(generation!==epoch.current)return;
      remember(started);setFighters(asPair(started.fighters));setPhase('BATTLE');
    }catch(e){setError((e as Error).message)}finally{actionBusy.current=false;setBusy('')}
  },[isDemo,quick,reduced,remember]);
  const finalize=useCallback(async()=>{
    const active=currentBattle.current;if(!active||actionBusy.current)return;
    if(active.status==='completed'){setSaveState('saved');return}
    actionBusy.current=true;setSaveState('saving');setError('');const generation=epoch.current;
    try{const complete=await post<BattleRecord>(`/battles/${active.id}/finalize`);if(generation!==epoch.current)return;remember(complete);setSaveState('saved');}
    catch(e){setError((e as Error).message);setSaveState('error')}
    finally{actionBusy.current=false}
  },[remember]);
  const battleComplete=useCallback(()=>{setPhase('RESULTS');if(!isDemo)void finalize()},[isDemo,finalize]);
  async function resume(){
    if(!recovery||actionBusy.current)return;
    actionBusy.current=true;setBusy('Recovering your round…');setError('');const generation=++epoch.current;
    try{const record=await api<BattleRecord>(`/battles/${recovery}`);if(generation!==epoch.current)return;
      if(['cancelled','failed'].includes(record.status)){saveActive(null);setRecovery(null);throw new Error('That round has ended. Start a fresh match.');}
      remember(record);setIsDemo(false);setRecovery(null);setRoundKey(k=>k+1);
      if(record.fighters.length===2){setFighters(asPair(record.fighters));setPhase(record.status==='completed'||(record.eligible_at&&Date.now()>=Date.parse(record.eligible_at))?'RESULTS':'BATTLE');setSaveState(record.status==='completed'?'saved':'idle')}
      else if(record.pending_fighters.every((fighter,index)=>fighter&&record.confirmed_capture_ids?.[index]===fighter.capture_id)){setFighters(asPair(record.pending_fighters as PendingFighter[]));setPhase('REVEAL')}
      else {const first=record.pending_fighters[0];const firstConfirmed=first&&record.confirmed_capture_ids?.[0]===first.capture_id;if(firstConfirmed)setFighters([asFighter(first),PRESET_FIGHTERS[1]]);const slot=firstConfirmed?1:0;const pending=record.pending_fighters[slot];let restored:CaptureResponse|null=null;if(pending){try{restored=captureResponse(await api(`/battles/${record.id}/captures/${pending.capture_id}`))}catch{restored={capture_id:pending.capture_id,status:'recognized',image_url:pending.image_ref,width:800,height:600,fighter:pending,output_id:pending.output_id,pipeline_version_id:'legacy-unknown'}}}if(generation!==epoch.current)return;setReviewPending(restored);setPhase(slot===0?'DRAW_P1':'DRAW_P2')}
    }catch(e){setError((e as Error).message)}finally{actionBusy.current=false;setBusy('')}
  }
  const stage=phase==='DRAW_P1'||phase==='DRAW_P2'?0:phase==='REVEAL'?1:2;
  const memory=battle?.persistence==='development_memory'||health?.persistence==='development_memory';
  return <div className={`game-shell phase-${phase.toLowerCase()}`}><div className="paper-noise" aria-hidden="true"/>
    <header className="game-header"><button className="brand" onClick={()=>void home()} aria-label="Sketch Clash home"><span className="brand-icon"><Pencil size={20}/><Pencil size={20}/></span>SKETCH<span>CLASH</span></button><span className="header-center">{PHASE_LABEL[phase]}</span><div className="header-right">{phase==='HOME'?<><button className="quality-entry" onClick={()=>setPhase('QUALITY')} title="Recognition & World Quality"><SlidersHorizontal size={15}/><span>QUALITY LAB</span></button><button className="text-button island-entry" onClick={()=>{setWorldMode('colonies');setPhase('WORLD')}}><Globe2 size={15}/> THE ISLANDS <ArrowUpRight size={13}/></button></>:<button className="exit-button" onClick={()=>void home()} aria-label="Exit round and return home"><X size={17}/><span>{phase==='WORLD'||phase==='QUALITY'?'BACK HOME':'EXIT ROUND'}</span></button>}</div></header>
    {memory&&<div className="service-note">LOCAL MEMORY PREVIEW · Your island disappears when the backend restarts. MongoDB is not connected.</div>}
    {!memory&&health?.status==='configuration_required'&&phase==='HOME'&&<div className="service-note">Camera battles need your Atlas connection. The cinematic demo remains available.</div>}
    {busy&&<div className="flow-message" role="status">{busy}</div>}
    {error&&<div className="flow-message flow-error" role="alert">{error}<button onClick={()=>setError('')} aria-label="Dismiss message"><X size={16}/></button>{phase==='REVEAL'&&!isDemo&&<button onClick={()=>void startBattle()}>Retry arena</button>}</div>}
    {phase==='HOME'&&recovery&&<div className="recovery-card"><b>A round is waiting in your sketchbook.</b><button onClick={()=>void resume()}>RESUME ROUND</button><button onClick={()=>{saveActive(null);setRecovery(null);createRequest.current=null}}>DISMISS RECOVERY</button></div>}
    {phase!=='HOME'&&phase!=='THEME'&&phase!=='RESULTS'&&phase!=='WORLD'&&phase!=='QUALITY'&&<div className="game-progress" aria-label="Round progress">{['CAPTURE','SUMMON','CLASH'].map((label,i)=><span key={label} className={i===stage?'current':i<stage?'complete':''}><b>0{i+1}</b>{label}{i<2&&<i/>}</span>)}</div>}
    <AnimatePresence mode="wait" initial={false}><motion.div key={`${roundKey}-${phase}`} className="screen-wrap" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:.18}}>
      {phase==='HOME'&&<LandingScreen onPlay={()=>void play()} onDemo={demo} onIsland={()=>{setWorldMode('colonies');setPhase('WORLD')}} quick={quick} setQuick={setQuick}/>}
      {phase==='THEME'&&<ThemeReveal onComplete={themeComplete}/>}
      {(phase==='DRAW_P1'||phase==='DRAW_P2')&&<CaptureStudio player={phase==='DRAW_P1'?1:2} duration={quick?20:60} initialResponse={reviewPending} onPrepare={prepare} onConfirm={confirm} onFeedback={feedback} onCorrect={correct} onCancel={()=>void home()}/>}
      {phase==='REVEAL'&&<FighterReveal fighters={fighters} onComplete={()=>void startBattle()} isDemo={isDemo}/>}
      {phase==='BATTLE'&&<BattleArena fighters={fighters} onComplete={battleComplete} playback={!isDemo&&battle?.duration_ms&&battle.winner_slot!==null?{events:battle.events,duration_ms:battle.duration_ms,winner_slot:battle.winner_slot}:undefined}/>}
      {phase==='RESULTS'&&<><VictoryScreen fighters={fighters} winner={isDemo?0:battle?.winner_slot??0} onAgain={()=>void home()} onReplay={()=>{setRoundKey(k=>k+1);setPhase('BATTLE')}}/>{isDemo?<div className="unlock-card">CINEMATIC DEMO · Preset artwork. No recognition or island unlocks.</div>:<div className="unlock-card" aria-live="polite">{saveState==='saving'?<><b>Saving the completed match…</b><p>Your island opens after the server confirms completion.</p></>:saveState==='saved'?<><b>One winner. Two new chapters. ✦</b><p>The winner joins Winner Island. The other fighter joins Loser Island. Returning types keep their first appearance on each shore.</p><ActionButton onClick={()=>{setWorldMode('colonies');setPhase('WORLD')}}>ENTER THE ISLANDS <ArrowRight size={20}/></ActionButton></>:<><b>The match finished. Its unlock is still pending.</b><button className="text-button" onClick={()=>void finalize()}>RETRY SAVE</button></>}</div>}</>}
      {phase==='QUALITY'&&<Suspense fallback={<div className="flow-message">Opening Recognition & World Quality…</div>}><QualityConsole onClose={()=>setPhase('HOME')}/></Suspense>}
      {phase==='WORLD'&&<Suspense fallback={<div className="flow-message">Opening the islands…</div>}>{worldMode==='colonies'?<ColoniesView onBack={()=>void home()} onLegacy={()=>{setWorldMode('legacy');window.scrollTo({top:0,behavior:'instant'})}}/>:<><div className="legacy-island-return"><button onClick={()=>{setWorldMode('colonies');window.scrollTo({top:0,behavior:'instant'})}}><Globe2 size={14}/> BACK TO THE TWO ISLANDS <ArrowRight size={14}/></button><span>Your original shared island and its memories are preserved.</span></div><WorldView onBack={()=>void home()} arrivalIds={battle?.status==='completed'&&battle.completion?.durable?battle.completion.new_resident_ids:[]}/></>}</Suspense>}
    </motion.div></AnimatePresence>
    <footer className="game-footer"><span><span className="footer-asterisk">✳</span> REAL OBJECTS. UNREASONABLE AMBITION.</span><span>SKETCH CLASH <i>©</i> 2026</span><span className="footer-last">CAPTURE · CLASH · BUILD · GROW</span></footer>
  </div>;
}
