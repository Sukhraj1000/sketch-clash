import type { ReactNode } from 'react';
import { ArrowRight, ChevronDown, Coins, FileCheck2, RotateCcw, ShieldCheck, Trophy } from 'lucide-react';
import type { BattleRecord } from '../lib/api';
import type { Fighter } from '../types';
import { COMBAT_STATS, equalDamageBeforeLuck, priceComparisonTitle, type CameraCombat, type CombatProfile } from '../lib/camera-combat';
import { humanize, pounds, signed, type ArenaEvent } from '../lib/object-battles';
import './ObjectBattles.css';
import './CameraBattleReport.css';
import MarketPriceEvidence from './MarketPriceEvidence';

function FrozenProfile({ profile, slot }: { profile: CombatProfile; slot: number }) {
  return <article className={`cb-profile ob-player-${slot}`}>
    <div className="cb-profile-heading"><span>P{slot + 1}</span><div><h3>{profile.name}</h3><p>{humanize(profile.object_type)}</p></div><b>{pounds(profile.price.amount_gbp)}<small>{profile.price.amount_gbp === null ? 'NO PRICE ADVANTAGE' : 'RECORDED VALUE'}</small></b></div>
    <p>{profile.description}</p>
    <MarketPriceEvidence price={profile.price}/>
    <div className="ob-stats">{COMBAT_STATS.map(stat => <div key={stat}><small>{humanize(stat)}</small><b>{profile.stats[stat]}</b></div>)}</div>
    <div className="ob-traits">{profile.traits.map(trait => <span key={trait}>{humanize(trait)}</span>)}</div>
    <details className="ob-evidence"><summary>Inspect this frozen profile <ChevronDown size={14}/></summary><div><b>SUPPORTED ABILITIES</b><ul>{profile.capabilities.map(value => <li key={value}>{humanize(value)}</li>)}</ul><b>LIMITS & ASSUMPTIONS</b><ul>{profile.limitations.map(value => <li key={value}>{value}</li>)}</ul><p>{profile.provenance.label}</p><p>{profile.price.label}</p><p>Profile {profile.profile_version}. Attributes are balanced game values, not measurements of real-world strength.</p><details className="cb-source-evidence"><summary>Recorded source evidence</summary><pre>{JSON.stringify(profile.provenance, null, 2)}</pre></details></div></details>
  </article>;
}

function DamageReceipt({ event, combat }: { event: ArenaEvent; combat: CameraCombat }) {
  const receipt = event.receipt;
  const attacking = combat.fighters[event.attacker].stats;
  const defending = combat.fighters[1 - event.attacker].stats;
  return <li className={`ob-receipt ob-receipt-${event.attacker}`}>
    <div className="ob-receipt-heading"><span>P{event.attacker + 1}</span><div><b>{combat.fighters[event.attacker].name}</b><small>Exchange {receipt.round} · {event.word}</small></div><strong>−{event.damage}<small>HP</small></strong></div>
    <div className="ob-receipt-math"><span>Base + attributes<b>{receipt.base_damage} {signed(receipt.stat_adjustment)}</b></span><span>Matchup<b>{signed(receipt.interaction_percent, '%')}</b></span><span>Price<b>{signed(receipt.price_percent, '%')}</b></span><span>Luck roll<b>{signed(receipt.luck)}</b></span><span>Rounding<b title={String(receipt.rounding_adjustment)}>{signed(receipt.rounding_adjustment)}</b></span><span>Target health<b>{receipt.health_before} → {receipt.health_after}</b></span></div>
    <div className="ob-calculation"><span><b>Attribute comparison</b>0.6 × ({attacking.impact} impact − {defending.resilience} opponent resilience) + 0.5 × ({attacking.control} control − {defending.agility} opponent agility) = <strong>{signed(receipt.stat_adjustment)} damage</strong></span><span><b>Damage calculation</b>{receipt.base_damage} {signed(receipt.stat_adjustment)} attributes {signed(receipt.interaction_damage)} matchup {signed(receipt.price_damage)} price {signed(receipt.luck)} luck = <strong title={String(receipt.unrounded_damage)}>{Number(receipt.unrounded_damage.toFixed(2))}</strong></span><span><b>Seeded rounding</b>{signed(receipt.rounding_adjustment)} → {Math.round(receipt.unrounded_damage + receipt.rounding_adjustment)}</span><span><b>1–25 damage limit</b>{receipt.damage_before_cap}</span><span><b>Remaining-health cap</b>{receipt.damage_before_cap} → {receipt.damage} damage · {receipt.health_after} HP left</span>{(receipt.water_charges_before ?? 0) > 0 && <span><b>Water supply</b>{receipt.water_charges_before} → {receipt.water_charges_after ?? 0} splashes remaining</span>}</div>
    {receipt.interaction_rules.length ? <ul className="cb-applied-rules">{receipt.interaction_rules.map(rule => <li key={rule.id}><b>{rule.name} {signed(rule.percent, '%')}</b><span>{rule.reason}</span></li>)}</ul> : <p>No conditional weakness or resistance applied on this hit.</p>}
  </li>;
}

function AttributeMatchup({ combat }: { combat: CameraCombat }) {
  return <div className="cb-attribute-matchup" aria-label="Recorded attribute comparisons">{combat.fighters.map((profile, slot) => {
    const opponent = combat.fighters[1 - slot];
    const firstHit = combat.events.find(event => event.attacker === slot);
    return <p key={slot}><b>P{slot + 1} · {profile.name}</b><span>Impact {profile.stats.impact} vs {opponent.name}’s resilience {opponent.stats.resilience}; control {profile.stats.control} vs their agility {opponent.stats.agility}. {firstHit ? <>Recorded attribute adjustment: <strong>{signed(firstHit.receipt.stat_adjustment)} damage per hit</strong>, before matchup, price, luck and rounding.</> : 'No saved hit receipt is available for this object.'}</span></p>;
  })}</div>;
}

function Counterfactual({ combat, kind }: { combat: CameraCombat; kind: 'without_price' | 'without_interactions' }) {
  const result = combat.counterfactual[kind];
  const isPrice = kind === 'without_price';
  return <article>{isPrice ? <Coins size={23}/> : <ShieldCheck size={23}/>}<span className="ob-kicker">{isPrice ? 'DID PRICE DECIDE IT?' : 'DID THE MATCHUP MATTER?'}</span><h3>{isPrice ? priceComparisonTitle(combat) : result.changed_winner ? 'The combined counters changed the winner.' : 'Same winner without counters.'}</h3><p>{isPrice ? combat.explanation.price_note : 'Remove all conditional weaknesses and resistances, keeping the same profiles and random seed.'}</p><div><b>{isPrice ? 'Without price' : 'Without counters'}: {combat.fighters[result.winner_slot].name}</b><span>{result.final_health[0]} : {result.final_health[1]} HP</span></div>{result.outcome === 'tiebreak' && <small className="ob-counterfactual-tie">{result.impact_points ? `P1 ${result.impact_points[0]} : P2 ${result.impact_points[1]} impact points. ` : ''}{result.tiebreak_reason === 'impact_points' ? 'Higher impact before health caps wins.' : 'Equal impact: the saved seed decides.'}</small>}</article>;
}

export default function CameraBattleReport({ battle, fighters, onReplay, onAgain, children }: { battle: BattleRecord; fighters: [Fighter, Fighter]; onReplay: () => void; onAgain: () => void; children?: ReactNode }) {
  const combat = battle.combat;
  const winnerSlot = battle.winner_slot ?? 0;
  const winner = fighters[winnerSlot];
  const outcome = combat ? combat.outcome === 'knockout' ? 'BY KNOCKOUT' : combat.outcome === 'points' ? 'ON REMAINING HEALTH' : 'BY RECORDED TIEBREAK' : 'HISTORICAL CLASS BATTLE';
  return <main className="object-battles camera-battle-report">
    <header className="ob-result-hero"><div className="ob-result-art cb-winner-art"><Trophy size={34}/><img src={winner.image} alt={`${winner.name}, the winning photographed object`}/></div><div><span className="ob-kicker">THE RESULT IS IN · {outcome}</span><h1>{winner.name}<br/><em>takes the round.</em></h1><p>{combat?.explanation.summary ?? 'This saved round used the earlier class-based rules. Attribute profiles and damage explanations were not recorded for it.'}</p><div className="ob-result-actions"><button className="ob-secondary" onClick={onReplay}><RotateCcw size={15}/> Replay this battle</button><button className="ob-link" onClick={onAgain}>Start another round <ArrowRight size={16}/></button></div></div></header>
    {(combat?.final_health ?? battle.final_health) && <div className="ob-final-score" aria-label="Final health">{fighters.map((fighter, slot) => <div key={fighter.id}><span>P{slot + 1} · {fighter.name}</span><strong>{(combat?.final_health ?? battle.final_health)![slot]}<small>HP LEFT</small></strong><b>{slot === winnerSlot ? 'WINNER ISLAND' : 'LOSER ISLAND'}</b></div>)}</div>}
    {children}
    {combat ? <>
      <section className="ob-why"><div className="ob-section-heading"><div><span className="ob-kicker">FROM THE SAVED CALCULATION</span><h2>Why {winner.name} won.</h2></div><FileCheck2 size={29}/></div><ol>{combat.explanation.highlights.map((highlight, index) => <li key={index}><span>{index + 1}</span><p>{highlight}</p></li>)}</ol>{equalDamageBeforeLuck(combat)&&<p className="cb-even-match">Both fighters had the same damage before luck. Saved luck rolls, rounding and any recorded tiebreak separated this match.</p>}<AttributeMatchup combat={combat}/><p className="ob-receipt-note">Gemini helps recognise the object. The server applies the saved profiles and rules to decide this battle.</p></section>
      {combat.outcome === 'tiebreak' && combat.impact_points && <div className="ob-tiebreak-note"><b>RECORDED TIEBREAK</b><p>{combat.tiebreak_reason === 'impact_points' ? 'Equal final health: impact points before the remaining-health cap decide this tie.' : 'Equal final health and impact points: the saved seed decides this tie.'}</p><span>P1: {combat.impact_points[0]} impact points · P2: {combat.impact_points[1]} impact points</span></div>}
      <section className="ob-counterfactuals" aria-label="What changed the result"><Counterfactual combat={combat} kind="without_price"/><Counterfactual combat={combat} kind="without_interactions"/></section>
      <p className="ob-counterfactual-note">These comparisons replay this particular seed with one modifier removed. They are not overall win probabilities. Any price premium is capped at {combat.price_policy?.max_bonus_percent ?? 1}%; if either value is unknown, both premiums are zero.</p>
      <section className="cb-profiles" aria-label="Frozen object attributes"><div className="ob-section-heading"><div><span className="ob-kicker">LOCKED WHEN THE BATTLE STARTED</span><h2>Your objects. Their attributes.</h2></div></div><p>100 HP each. The same 20-point attribute budget. Conditions need supporting evidence; an empty vessel cannot splash water.</p><div className="cb-profile-grid">{combat.fighters.map((profile, slot) => <FrozenProfile key={`${profile.id}:${slot}`} profile={profile} slot={slot}/>)}</div></section>
      <details className="ob-receipt-list"><summary><div><span className="ob-kicker">THE FULL DAMAGE RECEIPT</span><h2>Every hit, accounted for.</h2></div><span>{combat.events.length} hits <ChevronDown size={20}/></span></summary><p>Each exchange commits both actions together. The animation order gives no advantage. Modifiers display to two decimals; the stored calculation uses full precision.</p><ol>{combat.events.map(event => <DamageReceipt key={event.id} event={event} combat={combat}/>)}</ol></details>
    </> : <div className="cb-legacy-note"><b>Historical result preserved.</b><p>Start a new camera battle to use attributes and conditional weaknesses. This older result has not been recalculated or given invented explanations.</p></div>}
    <div className="ob-save-receipt"><FileCheck2 size={19}/><div><b>{battle.persistence === 'mongodb' ? 'Battle saved in MongoDB Atlas' : 'Battle saved in temporary backend memory'}</b><p>{battle.engine_version ?? 'Historical engine'} · Seed {battle.seed ?? 'not recorded'} · Battle {battle.id}</p></div></div>
  </main>;
}
