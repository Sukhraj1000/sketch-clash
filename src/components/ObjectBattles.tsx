import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, ChevronDown, Coins, FileCheck2, FlaskConical, Info, RotateCcw, ShieldCheck, Sparkles, Swords, Trophy } from 'lucide-react';
import BattleArena from './BattleArena';
import { arenaFighters, arenaPlayback, battleIdFromHash, createArenaBattle, fixtureImage, humanize, loadArenaBattle, loadArenaCatalog, pounds, signed } from '../lib/object-battles';
import type { ArenaBattle, ArenaCatalog, ArenaFixture, ArenaEvent } from '../lib/object-battles';
import './ObjectBattles.css';

type PendingRequest = { id: string; fighters: [string, string] };
const PENDING_KEY = 'sketch-clash:practice-request';
const STATS = ['impact', 'resilience', 'agility', 'control'] as const;
const PRESETS = [
  { label: 'The budget upset?', ids: ['kitchen-sponge', 'smartphone'] },
  { label: 'Reach vs resilience', ids: ['wooden-ruler', 'ceramic-mug'] },
  { label: 'A soggy situation', ids: ['filled-water-jug', 'hardback-book'] },
];
function readPending(): PendingRequest | null {
  try { const value = JSON.parse(sessionStorage.getItem(PENDING_KEY) ?? 'null'); return typeof value?.id === 'string' && Array.isArray(value.fighters) && value.fighters.length === 2 && value.fighters.every((item: unknown) => typeof item === 'string') ? value : null; } catch { return null; }
}
function storePending(value: PendingRequest | null) {
  try { if (value) sessionStorage.setItem(PENDING_KEY, JSON.stringify(value)); else sessionStorage.removeItem(PENDING_KEY); } catch { /* Retry still retains its request ID in memory when browser storage is disabled. */ }
}
const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'The local arena could not complete this request.';
function CounterfactualTiebreak({ result }: { result: ArenaBattle['counterfactual']['without_price'] }) {
  if (result.outcome !== 'tiebreak') return null;
  return <small className="ob-counterfactual-tie">{result.impact_points ? `P1 ${result.impact_points[0]} : P2 ${result.impact_points[1]} impact points. ` : ''}{result.tiebreak_reason === 'impact_points' ? 'Higher impact before health caps wins.' : result.tiebreak_reason === 'seed' ? 'Equal impact: saved seed decides.' : 'Winner determined by the recorded tiebreak.'}</small>;
}
function FixtureArt({ fixture }: { fixture: ArenaFixture }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [fixture.id]);
  return failed ? <span className="ob-art-fallback"><FlaskConical size={46} /><small>{humanize(fixture.object_type)}</small></span> : <img src={fixtureImage(fixture)} alt={`Illustration of ${fixture.name}`} onError={() => setFailed(true)} draggable={false} />;
}
function FighterCard({ fixture, slot, catalog, disabled, onSelect }: { fixture: ArenaFixture; slot: 0 | 1; catalog: ArenaCatalog; disabled: boolean; onSelect: (id: string) => void }) {
  return <article className={`ob-fighter-card ob-player-${slot}`}>
    <div className="ob-card-top"><b>PLAYER {slot + 1}</b><span><Check size={12} /> CURATED PROFILE</span></div>
    <div className="ob-object-art"><span className="ob-art-ring" /><FixtureArt fixture={fixture} /><div className="ob-price-tag"><small>SAMPLE VALUE</small><b>{pounds(fixture.price.amount_gbp)}</b></div></div>
    <label className="ob-object-select"><span className="ob-sr-only">Player {slot + 1} object</span><select aria-label={`Player ${slot + 1} object`} disabled={disabled} value={fixture.id} onChange={event => onSelect(event.target.value)}>{catalog.fixtures.map(item => <option key={item.id} value={item.id}>{item.name} · {pounds(item.price.amount_gbp)}</option>)}</select><ChevronDown size={20} /></label>
    <p className="ob-object-description">{fixture.description}</p>
    <div className="ob-stats">{STATS.map(stat => <div key={stat}><small>{humanize(stat)}</small><b>{fixture.stats[stat]}</b></div>)}</div>
    <div className="ob-traits">{fixture.traits.slice(0, 5).map(trait => <span key={trait}>{humanize(trait)}</span>)}</div>
    <details className="ob-evidence"><summary>What can this object actually do? <ChevronDown size={14} /></summary><div><b>ALLOWED ABILITIES</b><ul>{fixture.capabilities.map(capability => <li key={capability}>{humanize(capability)}</li>)}</ul><b>LIMITS & ASSUMPTIONS</b><ul>{fixture.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul><p>{fixture.provenance.label} {fixture.price.label} These are practice profiles, not claims from a photograph.</p></div></details>
  </article>;
}
function Receipt({ event, match, index }: { event: ArenaEvent; match: ArenaBattle; index: number }) {
  const receipt = event.receipt;
  return <li className={`ob-receipt ob-receipt-${event.attacker}`}><div className="ob-receipt-heading"><span>{String(index + 1).padStart(2, '0')}</span><div><b>{match.fighters[event.attacker].name}</b><small>Exchange {receipt.round} · {event.word}</small></div><strong>−{event.damage}<small>HP</small></strong></div><div className="ob-receipt-math"><span>Base + stats<b>{receipt.base_damage} {signed(receipt.stat_adjustment)}</b></span><span>Matchup<b>{signed(receipt.interaction_percent, '%')}</b></span><span>Price<b>{signed(receipt.price_percent, '%')}</b></span><span>Luck roll<b>{signed(receipt.luck)}</b></span><span>Rounding<b title={String(receipt.rounding_adjustment)}>{signed(receipt.rounding_adjustment)}</b></span><span>Target health<b>{receipt.health_before} → {receipt.health_after}</b></span></div><div className="ob-calculation"><span title={`Base ${receipt.base_damage}; attributes ${receipt.stat_adjustment}; interaction damage ${receipt.interaction_damage}; price damage ${receipt.price_damage}; luck ${receipt.luck}`}><b>Damage calculation</b>{receipt.base_damage} {signed(receipt.stat_adjustment)} attributes {signed(receipt.interaction_damage)} matchup {signed(receipt.price_damage)} price {signed(receipt.luck)} luck = <strong title={String(receipt.unrounded_damage)}>{Number(receipt.unrounded_damage.toFixed(2))}</strong></span><span><b>Seeded rounding</b>{signed(receipt.rounding_adjustment)} → {Math.round(receipt.unrounded_damage + receipt.rounding_adjustment)}</span><span><b>1–25 damage limit</b>{receipt.damage_before_cap}</span><span><b>Remaining-health cap</b>{receipt.damage_before_cap} → {receipt.damage} damage · {receipt.health_after} HP left</span>{(receipt.water_charges_before ?? 0) > 0 && <span><b>Water supply</b>{receipt.water_charges_before} → {receipt.water_charges_after ?? 0} splashes remaining</span>}</div><p>{receipt.interaction_rules.length ? receipt.interaction_rules.map(rule => `${rule.name}: ${rule.reason}`).join(' ') : 'No conditional weakness or resistance applied on this hit.'}</p></li>;
}
function Result({ match, onReplay, onAgain }: { match: ArenaBattle; onReplay: () => void; onAgain: () => void }) {
  const winner = match.fighters[match.winner_slot];
  const priceCheck = match.counterfactual.without_price;
  const interactionCheck = match.counterfactual.without_interactions;
  const outcome = match.outcome === 'knockout' ? 'BY KNOCKOUT' : match.outcome === 'points' ? 'ON REMAINING HEALTH' : 'BY TIEBREAK';
  return <div className="ob-result">
    <header className="ob-result-hero"><div className="ob-result-art"><Trophy size={34} /><FixtureArt fixture={winner} /></div><div><span className="ob-kicker">THE RESULT IS IN · {outcome}</span><h1>{winner.name}<br /><em>takes the round.</em></h1><p>{match.explanation.summary}</p><div className="ob-result-actions"><button className="ob-primary" onClick={onAgain}>Pick another matchup <ArrowRight size={19} /></button><button className="ob-secondary" onClick={onReplay}><RotateCcw size={15} /> Replay this battle</button></div></div></header>
    <div className="ob-final-score" aria-label="Final health">{match.fighters.map((fighter, slot) => <div key={slot}><span>P{slot + 1} · {fighter.name}</span><strong>{match.final_health[slot]}<small>HP LEFT</small></strong><b>{slot === match.winner_slot ? 'WINNER' : 'RUNNER-UP'}</b></div>)}</div>
    {match.outcome === 'tiebreak' && match.impact_points && <div className="ob-tiebreak-note"><b>RECORDED TIEBREAK</b><p>{match.tiebreak_reason === 'impact_points' ? 'Total impact before the remaining-health cap decides this tie.' : 'The recorded impact scores are equal; the saved random seed decides this tie.'}</p><span>P1: {match.impact_points[0]} impact points · P2: {match.impact_points[1]} impact points</span></div>}
    <section className="ob-why"><div className="ob-section-heading"><div><span className="ob-kicker">A RESULT YOU CAN EXPLAIN</span><h2>Why {winner.name} won.</h2></div><FileCheck2 size={29} /></div><ol>{match.explanation.highlights.map((highlight, index) => <li key={index}><span>{index + 1}</span><p>{highlight}</p></li>)}</ol><p className="ob-receipt-note">These reasons come from the recorded calculation. The model does not pick the winner.</p></section>
    <section className="ob-counterfactuals" aria-label="What changed the result"><article><Coins size={23} /><span className="ob-kicker">DID PRICE DECIDE IT?</span><h3>{priceCheck.changed_winner ? 'This close fight swung.' : 'Still wins without price.'}</h3><p>{match.explanation.price_note}</p><div><b>Without price: {match.fighters[priceCheck.winner_slot].name}</b><span>{priceCheck.final_health[0]} : {priceCheck.final_health[1]} HP</span></div><CounterfactualTiebreak result={priceCheck} /></article><article><ShieldCheck size={23} /><span className="ob-kicker">DID THE MATCHUP MATTER?</span><h3>{interactionCheck.changed_winner ? 'Combined matchup rules changed the winner.' : 'Still wins without counters.'}</h3><p>Remove conditional weaknesses and resistances, keeping the same profiles and random seed.</p><div><b>Without counters: {match.fighters[interactionCheck.winner_slot].name}</b><span>{interactionCheck.final_health[0]} : {interactionCheck.final_health[1]} HP</span></div><CounterfactualTiebreak result={interactionCheck} /></article></section>
    <p className="ob-counterfactual-note">Each comparison replays this particular seed with one modifier removed. It is not an overall win probability.</p>
    <details className="ob-receipt-list"><summary><div><span className="ob-kicker">THE FULL DAMAGE RECEIPT</span><h2>Every hit, accounted for.</h2></div><span>{match.events.length} hits <ChevronDown size={20} /></span></summary><p>Base damage and attributes are adjusted by the applicable matchup and capped price bonus, then the bounded luck roll. Damage uses seeded rounding, is limited to 1–25 and capped at remaining health. Displayed modifiers are rounded to two decimals. Both actions in an exchange are committed together, so the animation order gives no advantage.</p><ol>{match.events.map((event, index) => <Receipt key={event.id} event={event} match={match} index={index} />)}</ol></details>
    <div className="ob-save-receipt"><FileCheck2 size={19} /><div><b>{match.persistence === 'mongodb' ? 'Saved in MongoDB Atlas' : 'Saved in temporary backend memory'}</b><p>Immutable practice result · {match.engine_version} · Seed {match.seed}</p><small>Battle {match.id} · {new Date(match.created_at).toLocaleString('en-GB')}</small></div><span>NO ISLAND REWARDS</span></div>
  </div>;
}

export default function ObjectBattles({ onBack }: { onBack: () => void }) {
  const [catalog, setCatalog] = useState<ArenaCatalog | null>(null);
  const [selected, setSelected] = useState<[string, string]>(['kitchen-sponge', 'smartphone']);
  const [match, setMatch] = useState<ArenaBattle | null>(null);
  const [phase, setPhase] = useState<'setup' | 'playing' | 'result'>('setup');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [playKey, setPlayKey] = useState(0);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const pending = useRef<PendingRequest | null>(readPending());
  const currentMatch = useRef<ArenaBattle | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current++; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    loadArenaCatalog(controller.signal).then(value => {
      setCatalog(value);
      if (value.fixtures.length < 2) throw new Error('The object catalogue needs at least two practice fighters.');
      const stored = pending.current?.fighters;
      setSelected(previous => {
        const candidate = stored ?? previous;
        return candidate.every(id => value.fixtures.some(item => item.id === id)) ? candidate : [value.fixtures[0].id, value.fixtures[1].id];
      });
    }).catch(cause => { if (!isAbort(cause)) setError(errorMessage(cause)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    let controller: AbortController | undefined;
    const readRoute = () => {
      controller?.abort();
      const id = battleIdFromHash();
      if (id === currentMatch.current?.id) return;
      generation.current++;
      if (!id) { currentMatch.current = null; setMatch(null); setPhase('setup'); setBusy(false); return; }
      currentMatch.current = null; setMatch(null); setPhase('setup');
      controller = new AbortController();
      const signal = controller.signal;
      setBusy(true); setError('');
      loadArenaBattle(id, signal).then(saved => { if (signal.aborted) return; currentMatch.current = saved; setMatch(saved); setSelected([saved.fighters[0].id, saved.fighters[1].id]); setPhase('result'); }).catch(cause => { if (!isAbort(cause)) setError(errorMessage(cause)); }).finally(() => { if (!signal.aborted) setBusy(false); });
    };
    readRoute(); window.addEventListener('hashchange', readRoute);
    return () => { controller?.abort(); window.removeEventListener('hashchange', readRoute); };
  }, [reload]);
  const fighters = useMemo(() => selected.map(id => catalog?.fixtures.find(item => item.id === id)) as [ArenaFixture | undefined, ArenaFixture | undefined], [catalog, selected]);
  const frozenFighters = useMemo(() => match ? arenaFighters(match) : null, [match]);
  const playback = useMemo(() => match ? arenaPlayback(match) : null, [match]);
  const select = (pair: [string, string]) => { if (inFlight.current || busy) return; setSelected(pair); pending.current = null; storePending(null); setError(''); };
  const start = async () => {
    if (inFlight.current || busy || !catalog?.storage_available || fighters.some(item => !item)) return;
    inFlight.current = true; setBusy(true); setError('');
    const request = pending.current?.fighters.every((id, index) => id === selected[index]) ? pending.current : { id: crypto.randomUUID(), fighters: [...selected] as [string, string] };
    pending.current = request; storePending(request);
    const currentGeneration = generation.current;
    try {
      const saved = await createArenaBattle(request.id, request.fighters);
      if (!mounted.current || currentGeneration !== generation.current) return;
      currentMatch.current = saved; setMatch(saved); setPlayKey(key => key + 1); setPhase('playing');
      history.replaceState(null, '', `#/battles?id=${encodeURIComponent(saved.id)}`);
      pending.current = null; storePending(null); window.scrollTo({ top: 0, behavior: 'instant' });
    } catch (cause) { if (mounted.current && currentGeneration === generation.current) setError(`${errorMessage(cause)} Retry uses the same request, so it will not create a duplicate result.`); }
    finally { inFlight.current = false; if (mounted.current && currentGeneration === generation.current) setBusy(false); }
  };
  const again = () => { generation.current++; currentMatch.current = null; setMatch(null); setPhase('setup'); setError(''); pending.current = null; storePending(null); history.replaceState(null, '', '#/battles'); window.scrollTo({ top: 0, behavior: 'instant' }); };
  const completed = useCallback(() => { setPhase('result'); window.scrollTo({ top: 0, behavior: 'instant' }); }, []);
  const previews = catalog?.matchup_previews?.[selected.join(':')] ?? [];
  return <main className="object-battles">
    <div className="ob-topline"><button className="ob-link" onClick={onBack}><ArrowLeft size={15} /> Back to Sketch Clash</button><span><FlaskConical size={14} /> OBJECT LAB · NO AI CALLS</span></div>
    {phase === 'playing' && match && frozenFighters && playback ? <><div className="ob-playback-caption"><span><FileCheck2 size={14} /> Saved server result. Both actions commit each exchange; animation order gives no advantage.</span><button className="ob-link" onClick={completed}>Skip to the receipts <ArrowRight size={14} /></button></div><BattleArena key={`${match.id}:${playKey}`} fighters={frozenFighters} playback={playback} onComplete={completed} /></> : phase === 'result' && match ? <Result match={match} onAgain={again} onReplay={() => { setPlayKey(key => key + 1); setPhase('playing'); window.scrollTo({ top: 0, behavior: 'instant' }); }} /> : <>
      <header className="ob-heading"><div><span className="ob-kicker">BIG PRICE TAG. SMALL ADVANTAGE.</span><h1>It’s what you’re<br /><em>made of.</em></h1><p>Pick two everyday objects. Their attributes and sensible counters shape the fight. Then inspect exactly why one won.</p></div><div className="ob-house-rules"><Swords size={30} /><b>100 HP EACH.<br />NOT ALL HITS ARE EQUAL.</b><p>Strengths come with limits. {catalog ? `Sample price adds at most ${catalog.price_policy.max_bonus_percent}% to damage.` : 'Sample price gives a small, capped damage bonus.'}</p><span>SERVER RULES · SEEDED REPLAY</span></div></header>
      {error && <div className="ob-error" role="alert"><Info size={19} /><p>{error}</p><button onClick={() => catalog && !battleIdFromHash() ? void start() : setReload(value => value + 1)} disabled={busy}>{busy ? 'Working…' : 'Retry'}</button></div>}
      {loading || busy && !catalog ? <div className="ob-loading"><FlaskConical size={34} /><h2>Opening the object lab…</h2><p>Loading the reviewed profiles from your local backend.</p></div> : catalog && fighters[0] && fighters[1] ? <>
        <div className="ob-preset-strip"><span>TRY A MATCHUP</span>{PRESETS.filter(preset => preset.ids.every(id => catalog.fixtures.some(fixture => fixture.id === id))).map(preset => <button key={preset.label} disabled={busy} onClick={() => select(preset.ids as [string, string])} aria-pressed={preset.ids.every((id, index) => selected[index] === id)}>{preset.label} <ArrowRight size={12} /></button>)}</div>
        <section className="ob-fighter-grid" aria-label="Choose your two practice objects"><FighterCard fixture={fighters[0]} slot={0} catalog={catalog} disabled={busy} onSelect={id => select([id, selected[1]])} /><span className="ob-vs" aria-hidden="true">VS</span><FighterCard fixture={fighters[1]} slot={1} catalog={catalog} disabled={busy} onSelect={id => select([selected[0], id])} /></section>
        <section className="ob-matchup"><div className="ob-section-heading"><div><span className="ob-kicker">BEFORE YOU LOCK IN</span><h2>The conditions that matter.</h2></div><Sparkles size={25} /></div>{previews.length ? <ul>{previews.map((effect, index) => <li key={`${effect.attacker}:${effect.id}:${index}`}><span className={`ob-effect-player ob-player-${effect.attacker}`}>P{effect.attacker + 1}</span><div><b>{effect.name}</b><small className="ob-effect-timing">{effect.timing}</small><p>{effect.reason}</p></div><strong>{signed(effect.percent, '%')}</strong></li>)}</ul> : <p className="ob-neutral-matchup">No special weakness or resistance applies to this pairing. Attributes, the bounded price bonus and small seeded luck rolls still count.</p>}<p className="ob-matchup-note"><Info size={14} /> Conditions apply only to supported abilities. A container does not get a water attack unless it actually contains water in its profile.</p></section>
        <div className="ob-lock-in"><div><b>Ready to test the matchup?</b><p>Every object has the same 20-point attribute budget. Profiles and prices freeze at the start.</p></div><button className="ob-primary" disabled={busy || !catalog.storage_available} onClick={() => void start()}><Swords size={20} />{busy ? battleIdFromHash() ? 'Loading saved battle…' : 'Saving the battle…' : !catalog.storage_available ? 'Battle storage unavailable' : 'Lock in & clash'}<ArrowRight size={20} /></button></div>
        <div className="ob-source-note"><FlaskConical size={19} /><p><b>This is the object battle lab.</b> Curated sample objects, authored attributes and illustrative GBP prices. No camera recognition or live marketplace prices. {catalog.persistence === 'mongodb' ? 'Battles save to Atlas separately from your real islands.' : catalog.persistence === 'development_memory' ? 'Battles use temporary backend memory, separate from your real islands.' : 'Battle storage is unavailable; connect the local backend to save and start a match.'} No residents or rewards are created.</p></div>
      </> : !error ? <div className="ob-loading"><h2>The object lab needs its backend.</h2><p>Start the local server, then reload this page.</p><button className="ob-secondary" onClick={() => setReload(value => value + 1)}>Try again</button></div> : null}
    </>}
    <footer className="ob-footer"><span>EVERYDAY OBJECTS. EXPLAINABLE BATTLES.</span><p>Game rules inspired by object properties. Not a physical safety test.</p><a href="#/playground">Visit the island playground <ArrowRight size={13} /></a></footer>
  </main>;
}
