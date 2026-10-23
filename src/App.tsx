import { useCallback, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent, useReducedMotion, useTransform, type MotionValue } from 'motion/react';
import { ArrowRight, ArrowUpRight, ChevronLeft, Pencil, Play, RotateCcw, Sparkles, X } from 'lucide-react';
import type { Fighter, Phase } from './types';
import { PRESET_FIGHTERS } from './game/fixtures';
import { useTimeline } from './game/director';
import SketchCanvas from './components/SketchCanvas';
import BattleArena from './components/BattleArena';

const spring = { type: 'spring' as const, stiffness: 320, damping: 21 };
const PHASE_LABEL: Record<Phase, string> = { HOME: 'THE SKETCHBOOK ARCADE', THEME: 'ROUND 01 · THE BRIEF', DRAW_P1: 'ROUND 01 · PENCILS UP', DRAW_P2: 'ROUND 01 · PENCILS UP', REVEAL: 'ROUND 01 · MEET THE FIGHTERS', BATTLE: 'ROUND 01 · THE SHOWDOWN', RESULTS: 'ROUND 01 · THAT’S A WRAP' };

function Star({ className = '', color = 'currentColor' }: { className?: string; color?: string }) {
  return <svg className={className} viewBox="0 0 100 100" fill={color} aria-hidden="true"><path d="M51 3 62 35 96 31 73 54 89 88 54 72 25 96 28 61 2 43 37 36Z" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" /></svg>;
}
function Burst({ className = '' }: {className?: string}) {
  return <svg className={className} viewBox="0 0 500 500" aria-hidden="true"><path d="M247 9 276 107 340 39 335 136 437 99 384 188 490 207 396 252 478 320 374 320 408 421 320 366 300 487 244 391 174 478 171 375 69 417 119 321 9 302 109 248 24 180 127 179 94 74 184 128Z" fill="currentColor" /></svg>;
}
function Crown({ className = '' }: { className?: string }) {
  return <svg className={className} viewBox="0 0 200 130" aria-hidden="true"><path d="m21 100-9-72 53 30 37-49 30 54 54-28-21 74Z" fill="#FFD166" stroke="#1E1C29" strokeWidth="6" strokeLinejoin="round"/><path d="m25 113 138 7M44 32 34 13m116 10 12-16M98 3V0" stroke="#1E1C29" strokeWidth="5" strokeLinecap="round"/><path d="m47 87 94 5" stroke="#1E1C29" strokeWidth="4" strokeLinecap="round"/></svg>;
}
function ActionButton({children,onClick,className='',label}:{children:React.ReactNode;onClick:()=>void;className?:string;label?:string}) {
  return <motion.button type="button" className={`arcade-button ${className}`} onClick={onClick} aria-label={label} whileHover={{y:-3,rotate:-1}} whileTap={{y:4,x:3,boxShadow:'0px 0px 0px var(--ink)'}} transition={spring}>{children}</motion.button>;
}

function LandingScreen({onPlay,onDemo,quick,setQuick}:{onPlay:()=>void;onDemo:()=>void;quick:boolean;setQuick:(value:boolean)=>void}) {
  const reduced=useReducedMotion();
  return <motion.main className="landing" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0,y:-22}}>
    <div className="landing-note note-left">a little imagination.<br/>a lot of chaos.<svg viewBox="0 0 100 70" aria-hidden="true"><path d="M5 8q66-4 65 45m-13-9 13 15 13-17"/></svg></div>
    <div className="landing-note note-right">your doodle<br/>could be a legend.<Star /></div>
    <div className="hero-eyebrow"><span className="tiny-star">✳</span> THE PEN IS MIGHTIER. PERIOD. <span className="tiny-star">✳</span></div>
    <div className="hero-grid">
      <motion.div className="hero-fighter hero-fighter-left" initial={{x:-60,opacity:0,rotate:-14}} animate={{x:0,opacity:1,rotate:-8}} transition={{...spring,delay:.18}}>
        <div className="fighter-paper coral-paper"><span className="tape tape-top"/><div className="paper-grid"/>
          <motion.img src={PRESET_FIGHTERS[0].image} alt="Scratch, a mischievous hand-drawn cat" animate={reduced?{}:{y:[0,-8,0],rotate:[-3,1,-3]}} transition={{duration:4,repeat:Infinity,ease:'easeInOut'}} draggable={false}/>
          <div className="mini-player">P1 <span>SCRATCH</span></div><div className="paper-caption">HAS CLAWS. WILL DOODLE.</div>
        </div><Star className="fighter-star star-one" color="var(--yellow)"/>
      </motion.div>
      <div className="hero-center">
        <h1 className="hero-logo" aria-label="Sketch Clash"><motion.span className="logo-sketch" initial={{y:-50,rotate:-9,opacity:0}} animate={{y:0,rotate:-4,opacity:1}} transition={{...spring,delay:.05}}>SKETCH</motion.span><motion.span className="logo-clash" initial={{scale:.6,rotate:8,opacity:0}} animate={{scale:1,rotate:-5,opacity:1}} transition={{...spring,delay:.2}}>CLASH<span className="logo-period">!</span></motion.span></h1>
        <motion.p className="hero-tagline" initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{delay:.4}}>DRAW IT. DEFEND IT. BATTLE IT.</motion.p>
        <p className="hero-description">Your imagination. Their problem.<br/>Turn your doodles into arcade legends.</p>
        <div className="hero-actions"><ActionButton onClick={onPlay}>LET’S PLAY <ArrowRight size={27}/></ActionButton><motion.button className="demo-button" onClick={onDemo} whileHover={{x:3}} whileTap={{scale:.97}}><Play size={15} fill="currentColor"/> WATCH THE SHOWDOWN <ArrowUpRight size={15}/></motion.button></div>
        <label className="quick-toggle"><input type="checkbox" checked={quick} onChange={e=>setQuick(e.target.checked)}/><span className="toggle-track"><span/></span> QUICK DRAW <span className="toggle-seconds">{quick?'20':'60'} SEC / PLAYER</span></label>
      </div>
      <motion.div className="hero-fighter hero-fighter-right" initial={{x:60,opacity:0,rotate:13}} animate={{x:0,opacity:1,rotate:7}} transition={{...spring,delay:.28}}>
        <div className="fighter-paper mint-paper"><span className="tape tape-top"/><div className="paper-grid"/>
          <motion.img src={PRESET_FIGHTERS[1].image} alt="Chomps, a goofy hand-drawn dinosaur" animate={reduced?{}:{y:[-5,3,-5],rotate:[2,-2,2]}} transition={{duration:4.6,repeat:Infinity,ease:'easeInOut'}} draggable={false}/>
          <div className="mini-player">P2 <span>CHOMPS</span></div><div className="paper-caption">SMALL ARMS. BIG ENERGY.</div>
        </div><Star className="fighter-star star-two" color="var(--coral)"/>
      </motion.div>
    </div>
    <div className="no-skills-stamp">ZERO ART SKILLS<br/><b>REQUIRED</b><span>JUST BRING THE ATTITUDE</span></div>
    <div className="how-strip"><div><span className="step-number">01</span><p><b>GET A THEME</b><span>One brief. Endless possibilities.</span></p></div><div><span className="step-number">02</span><p><b>MAKE YOUR MARK</b><span>Two players. Two very bad drawings.</span></p></div><div><span className="step-number">03</span><p><b>LET ’EM CLASH</b><span>Your exact doodles. Fully unleashed.</span></p></div></div>
  </motion.main>;
}

function ThemeReveal({onComplete}:{onComplete:()=>void}) {
  const reduced=useReducedMotion();
  const clock=useTimeline(4200,onComplete);
  const [beat,setBeat]=useState(0);
  useMotionValueEvent(clock,'change',t=>setBeat(t<1700?Math.floor(t/125):t<2700?20:t<3400?21:22));
  const rotate=useTransform(clock,[0,250,800,1200,1700,1950,2200],[0,-10,8,-6,5,-4,-3]);
  const scale=useTransform(clock,[0,450,1550,1750,2050],[.7,1,.95,1.12,1]);
  const names=['ANIMALS','CREATURES','ANIMALS','WILD THINGS'];
  return <main className="theme-screen"><div className="eyebrow round-ribbon">ROUND 01 <span>THE PAGE IS YOURS</span></div><p className="section-kicker">AND YOUR THEME IS…</p><div className="theme-stage"><Burst className="theme-burst"/><motion.div className="theme-card" style={reduced?{}:{rotate,scale}}><div className="theme-card-top"><Pencil size={20}/><span>THE DRAWING BRIEF</span><span>001</span></div><div className="theme-paw">✳</div><h1>{beat<20?names[beat%names.length]:'ANIMALS'}</h1><p>Wild, weird, or wonderfully made up.</p><div className="theme-rule">One creature. All your imagination.</div><span className="tape tape-top"/></motion.div><Star className="theme-star" color="var(--mint)"/></div><div className="theme-countdown" aria-live="polite">{beat<20?'SHUFFLING THE SKETCHBOOK…':beat===20?'PENCILS READY?':beat===21?'3… 2…':'MAKE YOUR MARK!'}</div></main>;
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
    <motion.img className="reveal-drawing" src={fighter.image} alt={`${fighter.name}, the original drawing lifting off the page`} style={reduced?{}:{y,rotate,scale}} draggable={false}/>
    <div className="reveal-floor-shadow"/>
    <motion.div className="reveal-name" style={{opacity:labelOpacity}}><span>PLAYER {fighter.side+1}</span><h2>{fighter.name}</h2><p>{fighter.subtitle}</p><div className="fighter-attribute"><b>{fighter.side===0?'QUICK & SCRAPPY':'HEAVY HITTER'}</b><span>{fighter.side===0?'100':'100'} HP</span></div></motion.div>
  </div>;
}
function FighterReveal({fighters,onComplete,isDemo}:{fighters:[Fighter,Fighter];onComplete:()=>void;isDemo:boolean}) {
  const clock=useTimeline(7000,onComplete);
  const vsScale=useTransform(clock,[0,3500,3850,4100,6100,6500],[0,0,1.4,1,1,0]);
  return <main className="reveal-screen"><div className="section-heading"><span className="eyebrow">FROM THE PAGE TO THE RAGE</span><h1>IT’S ALIVE<span>!</span></h1><p>{isDemo?'Two sketchbook originals. One very personal showdown.':'Your original drawings. A whole new attitude.'}</p></div><div className="reveal-stage"><RevealFighter fighter={fighters[0]} clock={clock}/><motion.div className="reveal-vs" style={{scale:vsScale}}>VS<span>✦</span></motion.div><RevealFighter fighter={fighters[1]} clock={clock}/></div><div className="bottom-caption">{isDemo?'PRESET FIGHTERS':'ORIGINAL SKETCHES'} <span>✳</span> SCRIPTED SHOWDOWN</div></main>;
}

function VictoryScreen({fighters,onAgain,onReplay}:{fighters:[Fighter,Fighter];onAgain:()=>void;onReplay:()=>void}) {
  const reduced=useReducedMotion();
  return <motion.main className="victory-screen" initial={{opacity:0}} animate={{opacity:1}}><div className="victory-rays"/><div className="victory-topline"><span>THE INK HAS SETTLED</span><span>PLAYER 01 WINS</span></div><motion.div className="victory-title" initial={reduced?{}:{scale:1.6,rotate:-7}} animate={{scale:1,rotate:-4}} transition={spring}>VICTORY<span>!</span></motion.div><div className="victory-stage"><Burst className="victory-burst"/><motion.div className="victory-hero" initial={{y:40,opacity:0}} animate={reduced?{y:0,opacity:1}:{y:[0,-15,0],opacity:1,rotate:[-3,3,-3]}} transition={{y:{duration:1.9,repeat:Infinity,ease:'easeInOut'},rotate:{duration:1.9,repeat:Infinity,ease:'easeInOut'},opacity:{duration:.3}}}><Crown className="winner-crown"/><img src={fighters[0].image} alt={`${fighters[0].name}, the winning original drawing`}/></motion.div><div className="victory-loser"><img src={fighters[1].image} alt="The defeated drawing crumpled into a paper ball"/><span>…rematch?</span></div>{Array.from({length:16},(_,i)=><motion.div key={i} className={`confetti confetti-${i%3}`} style={{left:`${10+(i*37)%80}%`,top:`${10+(i*23)%70}%`,rotate:i*31}} initial={{scale:0}} animate={reduced?{scale:1}:{scale:[0,1,1],y:[-25,0,30],rotate:[i*31,i*31+80]}} transition={{duration:2.5,delay:(i%5)*.12,repeat:reduced?0:Infinity,repeatType:'reverse'}}>{i%3===0?'✦':''}</motion.div>)}</div><div className="victory-name"><span>THE UNDISPUTED DOODLE CHAMPION</span><h2>{fighters[0].name}</h2><p>A masterpiece? Debatable. A winner? Absolutely.</p></div><div className="victory-actions"><ActionButton onClick={onAgain}>PLAY AGAIN <Pencil size={23}/></ActionButton><button className="text-button" onClick={onReplay}><RotateCcw size={16}/> RUN IT BACK</button></div><div className="bottom-caption">ALL GLORY. NO ERASER.</div></motion.main>;
}

export default function App() {
  const [phase,setPhase]=useState<Phase>('HOME');
  const [quick,setQuick]=useState(false);
  const [isDemo,setIsDemo]=useState(false);
  const [fighters,setFighters]=useState<[Fighter,Fighter]>(PRESET_FIGHTERS);
  const [roundKey,setRoundKey]=useState(0);
  const home=useCallback(()=>{setPhase('HOME');setIsDemo(false);setFighters(PRESET_FIGHTERS);setRoundKey(k=>k+1);},[]);
  const play=()=>{setIsDemo(false);setFighters(PRESET_FIGHTERS);setRoundKey(k=>k+1);setPhase('THEME');};
  const demo=()=>{setIsDemo(true);setFighters(PRESET_FIGHTERS);setRoundKey(k=>k+1);setPhase('REVEAL');};
  const themeComplete=useCallback(()=>setPhase(current=>current==='THEME'?'DRAW_P1':current),[]);
  const revealComplete=useCallback(()=>setPhase(current=>current==='REVEAL'?'BATTLE':current),[]);
  const battleComplete=useCallback(()=>setPhase(current=>current==='BATTLE'?'RESULTS':current),[]);
  function submit(player:1|2,image:string){setFighters(prev=>{const next:[Fighter,Fighter]=[...prev];next[player-1]={...prev[player-1],image,name:player===1?'SCRIBBLE ONE':'DOODLE TWO',subtitle:player===1?'ORIGINAL INK. ORIGINAL ATTITUDE.':'FRESH OFF THE SKETCHBOOK.'};return next;});setPhase(player===1?'DRAW_P2':'REVEAL');}
  const stage=phase==='DRAW_P1'||phase==='DRAW_P2'?0:phase==='REVEAL'?1:2;
  return <div className={`game-shell phase-${phase.toLowerCase()}`}><div className="paper-noise" aria-hidden="true"/>
    <header className="game-header"><button className="brand" onClick={home} aria-label="Sketch Clash home"><span className="brand-icon"><Pencil size={20}/><Pencil size={20}/></span>SKETCH<span>CLASH</span></button><span className="header-center">{PHASE_LABEL[phase]}</span><div className="header-right">{phase==='HOME'?<><span className="live-dot"/><span>2 PLAYERS · 1 SKETCHBOOK</span></>:<button className="exit-button" onClick={home} aria-label="Exit round and return home"><X size={17}/><span>EXIT ROUND</span></button>}</div></header>
    {phase!=='HOME'&&phase!=='THEME'&&phase!=='RESULTS'&&<div className="game-progress" aria-label="Round progress">{['DRAW','SUMMON','CLASH'].map((label,i)=><span key={label} className={i===stage?'current':i<stage?'complete':''}><b>0{i+1}</b>{label}{i<2&&<i/>}</span>)}</div>}
    <AnimatePresence mode="wait" initial={false}><motion.div key={`${roundKey}-${phase}`} className="screen-wrap" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:.18}}>
      {phase==='HOME'&&<LandingScreen onPlay={play} onDemo={demo} quick={quick} setQuick={setQuick}/>}
      {phase==='THEME'&&<ThemeReveal onComplete={themeComplete}/>}
      {(phase==='DRAW_P1'||phase==='DRAW_P2')&&<SketchCanvas player={phase==='DRAW_P1'?1:2} duration={quick?20:60} onSubmit={image=>submit(phase==='DRAW_P1'?1:2,image)} onCancel={home}/>}
      {phase==='REVEAL'&&<FighterReveal fighters={fighters} onComplete={revealComplete} isDemo={isDemo}/>}
      {phase==='BATTLE'&&<BattleArena fighters={fighters} onComplete={battleComplete}/>}
      {phase==='RESULTS'&&<VictoryScreen fighters={fighters} onAgain={home} onReplay={()=>{setRoundKey(k=>k+1);setPhase('BATTLE');}}/>}
    </motion.div></AnimatePresence>
    <footer className="game-footer"><span><span className="footer-asterisk">✳</span> MADE OF PAPER. BUILT FOR CHAOS.</span><span>SKETCH CLASH <i>©</i> 2026</span><span className="footer-last">A LITTLE ROUGH AROUND THE EDGES. BY DESIGN.</span></footer>
  </div>;
}
