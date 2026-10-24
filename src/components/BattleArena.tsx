import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion, useMotionValueEvent, useReducedMotion, useTransform, type MotionValue } from 'motion/react';
import type { Fighter } from '../types';
import { BATTLE_DURATION, BATTLE_EVENTS, getCameraOffset, getFighterPose, getHealth, getHitFlash, getImpact, type BattleEvent, type BattlePlayback, type BattleOutcome } from '../game/battle';
import { useTimeline } from '../game/director';
import './BattleArena.css';

type Props = { fighters: [Fighter, Fighter]; onComplete: () => void; playback?: BattlePlayback };

function FighterSprite({ fighter, elapsed, width, reduced, events, winnerSlot, outcome, fixture }: { fighter: Fighter; elapsed: MotionValue<number>; width: number; reduced: boolean; events: readonly BattleEvent[]; winnerSlot: 0 | 1; outcome: BattleOutcome; fixture: boolean }) {
  const x = useTransform(elapsed, t => getFighterPose(t, fighter.side, reduced, events, winnerSlot, outcome).x * width);
  const y = useTransform(elapsed, t => getFighterPose(t, fighter.side, reduced, events, winnerSlot, outcome).y);
  const rotate = useTransform(elapsed, t => getFighterPose(t, fighter.side, reduced, events, winnerSlot, outcome).rotate);
  const scaleX = useTransform(elapsed, t => getFighterPose(t, fighter.side, reduced, events, winnerSlot, outcome).scaleX);
  const scaleY = useTransform(elapsed, t => getFighterPose(t, fighter.side, reduced, events, winnerSlot, outcome).scaleY);
  const opacity = useTransform(elapsed, t => getFighterPose(t, fighter.side, reduced, events, winnerSlot, outcome).opacity);
  const shadowScale = useTransform(y, value => 1 + value / 230);
  const hitFilter = useTransform(elapsed, t => getHitFlash(t, fighter.side, reduced, events) ? 'brightness(0) invert(1)' : 'none');
  return <div className={`battle-fighter-anchor battle-fighter-anchor-${fighter.side}`}>
    <motion.div className="battle-floor-shadow" style={{ x, scale: shadowScale }} />
    <motion.div className={`battle-fighter ${fighter.kind === 'photo' ? 'battle-fighter-photo' : ''}`} style={{ x, y, rotate, scaleX, scaleY, opacity }}>
      <motion.img src={fighter.image} alt={fixture ? `${fighter.name}, illustrated practice object` : `${fighter.name}, original player ${fighter.kind === 'photo' ? 'photograph' : 'drawing'}`} draggable={false} style={{ filter: hitFilter }} />
    </motion.div>
    <div className="battle-floor-marker" style={{ color: fighter.color }}>{fighter.side === 0 ? 'P1' : 'P2'}</div>
  </div>;
}

function HealthBar({ fighter, health }: { fighter: Fighter; health: number }) {
  return <div className={`battle-health battle-health-${fighter.side}`}>
    <div className="battle-health-heading"><span className="battle-player-badge" style={{ background: fighter.color }}>P{fighter.side + 1}</span><strong>{fighter.name}</strong><span className="battle-hp-number">{health}<small> HP</small></span></div>
    <div className="battle-health-track" role="progressbar" aria-label={`${fighter.name} health`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={health}>
      <motion.div className="battle-health-damage" animate={{ scaleX: health / 100 }} transition={{ duration: .65, delay: .2 }} />
      <motion.div className="battle-health-fill" style={{ background: fighter.color }} animate={{ scaleX: health / 100 }} transition={{ duration: .25, ease: [.22, 1, .36, 1] }} />
      <div className="battle-health-divisions" />
    </div>
    <div className="battle-health-subline"><span>{fighter.subtitle}</span><span>{health < 30 ? 'ON THIN PAPER' : health < 70 ? 'STILL SCRAPPING' : 'READY TO RUMBLE'}</span></div>
  </div>;
}

function ImpactEffects({ event, reduced }: { event: BattleEvent; reduced: boolean }) {
  const final = event.kind === 'finisher';
  const color = event.attacker === 0 ? 'var(--coral)' : 'var(--mint)';
  return <motion.div className={`battle-impact battle-impact-${event.kind} battle-impact-side-${event.attacker === 0 ? 1 : 0}`} initial={{ opacity: 1 }} exit={{ opacity: 0 }}>
    <motion.div className="battle-impact-burst" style={{ background: color }} initial={{ scale: .15, rotate: -15 }} animate={{ scale: final ? 1.6 : 1, rotate: 12, opacity: [1, 1, 0] }} transition={{ duration: reduced ? .1 : .48 }} />
    <motion.div className="battle-impact-ring" initial={{ scale: .2, opacity: 1 }} animate={{ scale: final ? 2 : 1.45, opacity: 0 }} transition={{ duration: .55 }} />
    {!reduced && Array.from({ length: final ? 12 : 8 }, (_, i) => {
      const angle = i / (final ? 12 : 8) * Math.PI * 2;
      return <motion.i key={i} className="battle-ink-particle" style={{ background: i % 3 ? color : 'var(--ink)', width: i % 2 ? 8 : 14, height: i % 2 ? 21 : 14 }} initial={{ x: 0, y: 0, opacity: 1, rotate: i * 29 }} animate={{ x: Math.cos(angle) * (final ? 205 : 145), y: Math.sin(angle) * (final ? 180 : 125) + 35, opacity: 0, rotate: i * 90 }} transition={{ duration: .55, ease: 'easeOut' }} />;
    })}
    {!final && <motion.div className="battle-hit-word" initial={{ scale: .3, rotate: event.attacker === 0 ? -14 : 12 }} animate={{ scale: [1.35, 1], y: -45 }} transition={{ duration: .25 }}>{event.word}<span>−{event.damage}</span></motion.div>}
    {event.kind === 'swipe' && <motion.svg className="battle-slash" viewBox="0 0 260 200" initial={{ opacity: 0, scale: .6 }} animate={{ opacity: [0, 1, 0], scale: 1.1 }} transition={{ duration: .4 }}><path d="M20 170 Q80 15 225 25 Q115 65 20 170" fill="var(--yellow)" stroke="var(--ink)" strokeWidth="3"/><path d="M60 190 Q125 70 245 65" fill="none" stroke="var(--paper)" strokeWidth="8"/></motion.svg>}
  </motion.div>;
}

export default function BattleArena({ fighters, onComplete, playback }: Props) {
  const reduced = !!useReducedMotion();
  const duration = playback?.duration_ms ?? BATTLE_DURATION;
  const winnerSlot = playback?.winner_slot ?? 0;
  const outcome = playback?.outcome ?? 'knockout';
  const fixture = Boolean(playback?.source_label);
  const outcomeLabel = outcome === 'knockout' ? 'K.O.' : outcome === 'points' ? 'POINTS' : 'TIEBREAK';
  const events = useMemo(() => playback ? playback.events.map(event => ({ ...event, at: event.at * BATTLE_DURATION / duration })) : BATTLE_EVENTS, [playback, duration]);
  const physicalElapsed = useTimeline(duration, onComplete);
  // One RAF drives both normal and quick playback; choreography retains its authored 12.8s coordinate system.
  const elapsed = useTransform(physicalElapsed, value => value * BATTLE_DURATION / duration);
  const finalTime = (events.at(-1)?.at ?? 9900) + 100;
  const photographs = fighters.some(fighter => fighter.kind === 'photo');
  const root = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  const [frame, setFrame] = useState({ health: [100, 100] as [number, number], impact: undefined as BattleEvent | undefined, intro: 'READY?', ko: false, second: 10, hits: 0 });
  const lastKey = useRef('');
  useMotionValueEvent(elapsed, 'change', t => {
    const impact = getImpact(t, events);
    const intro = t < 800 ? 'READY?' : t < 1400 ? 'CLASH!' : '';
    const ko = t >= finalTime;
    const second = Math.max(0, Math.ceil((finalTime - t) / 1000));
    const hits = events.filter(event => t >= event.at).length;
    const key = `${impact?.id ?? ''}:${intro}:${ko}:${second}:${hits}`;
    if (key !== lastKey.current) {
      lastKey.current = key;
      setFrame({ health: getHealth(t, events), impact, intro, ko, second, hits });
    }
  });
  useEffect(() => {
    if (!root.current) return;
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  const shake = useTransform(elapsed, t => getCameraOffset(t, reduced, events));
  const flash = useTransform(elapsed, t => {
    if (reduced) return 0;
    const event = getImpact(t, events);
    return event && t - event.at < 75 ? (event.kind === 'finisher' ? .7 : .28) : 0;
  });

  return <section className="battle-screen" aria-label="Sketch Clash battle arena">
    <div className="battle-topline"><span><i /> {playback?.source_label ?? 'LIVE FROM THE SKETCHBOOK'}</span><span>{photographs || fixture ? 'EVERYDAY OBJECTS' : 'ANIMALS'} · ROUND 01</span></div>
    <div className="battle-hud">
      <HealthBar fighter={fighters[0]} health={frame.health[0]} />
      <div className="battle-round-clock"><span>ROUND 01</span><strong>{frame.ko ? outcome === 'knockout' ? 'KO' : 'FT' : String(frame.second).padStart(2, '0')}</strong><small>{photographs || fixture ? 'OBJECTS IN MOTION' : 'NO ERASERS NOW'}</small></div>
      <HealthBar fighter={fighters[1]} health={frame.health[1]} />
    </div>
    <div className="battle-arena-wrap" ref={root}>
      <motion.div className="battle-arena" style={{ x: shake }}>
        <div className="battle-page-fold" /><div className="battle-paper-grid" />
        <div className="battle-arena-watermark" aria-hidden="true">MAKE A<br/>MESS.</div>
        <svg className="battle-background-scribble battle-background-scribble-left" viewBox="0 0 220 220" aria-hidden="true"><path d="M22 180L66 143 35 112 110 130 108 54 140 115 196 71 160 145 211 167 142 173 130 214 99 170 22 180Z"/><path d="M14 23Q100 100 58 31Q35 0 88 42M170 208l27-8M183 220l29-8"/></svg>
        <svg className="battle-background-scribble battle-background-scribble-right" viewBox="0 0 220 220" aria-hidden="true"><path d="M20 80Q80 20 110 83T195 55M30 97Q85 45 110 100T200 75M60 150l20-22 13 21 23-10-8 29 24 13-28 7-2 30-20-25-22 15 8-29-26-8Z"/></svg>
        <div className="battle-horizon" /><div className="battle-floor-grid" />
        <div className="battle-arena-stamp"><span>SKETCH CLASH</span><small>EST. JUST NOW</small></div>
        <div className="battle-arena-corner">A LITTLE ROUGH<br/><strong>BY DESIGN.</strong></div>
        {fighters.map(fighter => <FighterSprite key={fighter.id} fighter={fighter} elapsed={elapsed} width={width} reduced={reduced} events={events} winnerSlot={winnerSlot} outcome={outcome} fixture={fixture} />)}
        <AnimatePresence>{frame.impact && <ImpactEffects key={frame.impact.id} event={frame.impact} reduced={reduced} />}</AnimatePresence>
        <AnimatePresence>{frame.intro && <motion.div key={frame.intro} className={`battle-intro ${frame.intro === 'CLASH!' ? 'battle-intro-clash' : ''}`} initial={{ scale: reduced ? 1 : .45, opacity: 0, rotate: -8 }} animate={{ scale: 1, opacity: 1, rotate: -5 }} exit={{ scale: reduced ? 1 : 1.35, opacity: 0 }} transition={{ type: 'spring', stiffness: 350, damping: 19 }}>{frame.intro}</motion.div>}</AnimatePresence>
        <AnimatePresence>{frame.ko && <motion.div className={`battle-ko ${outcome !== 'knockout' ? 'battle-decision' : ''}`} initial={{ opacity: 0, scale: reduced ? 1 : 2.5, rotate: -12 }} animate={{ opacity: 1, scale: 1, rotate: -8 }} transition={{ type: 'spring', stiffness: 280, damping: 15 }}><span>THAT’S A WRAP.</span><strong>{outcomeLabel}</strong><small>{outcome === 'knockout' ? 'INK CREDIBLE.' : 'EVERY HIT COUNTED.'}</small></motion.div>}</AnimatePresence>
        {frame.ko && <motion.svg className={`battle-winner-crown battle-winner-crown-${winnerSlot}`} viewBox="0 0 100 75" initial={{ opacity: 0, y: -25, rotate: -15 }} animate={{ opacity: 1, y: 0, rotate: -8 }} transition={{ delay: .35, type: 'spring' }} aria-label="Winner crown"><path d="M15 56 8 15 34 33 50 6 66 33 92 15 84 56Z" fill="var(--yellow)" stroke="var(--ink)" strokeWidth="5" strokeLinejoin="round"/><path d="M18 66Q50 59 81 66" fill="none" stroke="var(--ink)" strokeWidth="5" strokeLinecap="round"/></motion.svg>}
        <motion.div className="battle-contact-flash" style={{ opacity: flash }} />
      </motion.div>
      <div className="battle-arena-tape battle-arena-tape-left" /><div className="battle-arena-tape battle-arena-tape-right" />
    </div>
    <div className="battle-footer"><span><i className="battle-tiny-star">✦</i> {fixture ? 'SAMPLE OBJECTS. SAVED RESULT.' : photographs ? 'REAL OBJECTS. REAL GRUDGE.' : 'ORIGINAL DOODLES. REAL GRUDGE.'}</span><div className="battle-event-dots" aria-label={`${frame.hits} of ${events.length} attacks complete`}>{events.map((event, index) => <i key={event.id} className={index < frame.hits ? 'is-complete' : ''} />)}</div><span>{frame.ko ? 'ONE FOR THE SKETCHBOOK.' : 'LET THE INK FLY.'}</span></div>
    {fixture && <div className="battle-live-receipt" aria-live="polite"><span>{frame.ko ? 'FINAL DECISION' : frame.impact ? `HIT ${frame.hits}` : 'LOCKED & READY'}</span><p>{frame.ko ? `${fighters[winnerSlot].name} wins ${outcome === 'knockout' ? 'by knockout' : outcome === 'points' ? 'on remaining health' : 'by the recorded tiebreak'}. The full receipt follows.` : frame.impact?.explanation ?? 'Every hit is calculated by the server and saved for this replay.'}</p></div>}
    <p className="battle-sr-only" aria-live="polite">{frame.ko ? `${fighters[winnerSlot].name} wins ${outcome === 'knockout' ? 'by knockout' : outcome === 'points' ? 'on remaining health' : 'by the recorded tiebreak'}.` : frame.impact ? `${fighters[frame.impact.attacker].name} lands ${frame.impact.word} ${frame.impact.damage} damage.` : 'The battle is in progress.'}</p>
  </section>;
}
