import { useState } from 'react'
import { ArrowDown, ArrowRight, Camera, CheckCheck, Database, MessageSquare, Network, ShieldCheck, Sparkles, Swords, Wrench } from 'lucide-react'
import './ArchitectureGuide.css'

const stages = [
  { title: 'Capture & confirm', icon: Camera, text: 'Photo → object evidence → Gemini recognition → your identity check.', detail: 'The local API combines available detector/OCR evidence, catalogue retrieval and Gemini. You review the identity before the fighter is accepted. The current camera flow uses your browser camera or an uploaded image.' },
  { title: 'Battle & route', icon: Swords, text: 'The server resolves combat and records each accepted fighter’s destination.', detail: 'The recorded winner goes to Winner Island and the other fighter to Loser Island. Placement records are idempotent. Repeat appearances retain one resident per canonical object type on each shore. Price does not determine placement.' },
  { title: 'Two separate crews', icon: Network, text: 'Each shore has its own residents, resources, projects, board and memories.', detail: 'Both islands share building rules and starting resources. An actor sees only its own island. The original collection is retained separately. Different crews and player interventions mean this is an experiment, not proof that one price group is better.' },
]
const loop = [
  { title: 'Observe', icon: Network, text: 'Own abilities, stock, projects, board and memories.' },
  { title: 'Discuss', icon: MessageSquare, text: 'Propose a project, support it, or object with a reason.' },
  { title: 'Validate', icon: ShieldCheck, text: 'Check scope, abilities and the cost of a whole upgrade.' },
  { title: 'Work', icon: Wrench, text: 'Queue permitted tasks; finish existing commitments.' },
  { title: 'Remember', icon: Database, text: 'Commit the effect, receipt and board update to Atlas.' },
]
const example = [
  { actor: 'Crew council', title: 'Spot the blocker', text: 'The beacon needs energy. Stock is empty and nobody in this crew can collect energy. Waiting will not solve it.', board: 'Objection · beacon · missing capability: energy', state: 'Beacon remains unfinished; no energy is invented.' },
  { actor: 'Pencil + mug', title: 'Find work we can do', text: 'The crew checks the other unfinished buildings. A garden needs materials and water; the mug can collect water and every resident can gather basic materials.', board: 'Proposal / support · garden · available crew can supply its inputs', state: 'The council compares feasible upgrades, not just the next construction action.' },
  { actor: 'Council validator', title: 'Commit a shared goal', text: 'If the garden is the best feasible candidate, the council chooses it and records why. Existing work and reserved supplies remain accounted for.', board: 'Decision · garden · crew control · next council after cooldown', state: 'The project changes without the player choosing a priority.' },
  { actor: 'Builder → board → mug', title: 'Ask and claim', text: 'When water is needed, a builder posts a request. A capable mug claims it. Another resident cannot also claim that same request.', board: 'Request water → offer from mug → exclusive commitment', state: 'An offer reserves responsibility; it is not a completed delivery.' },
  { actor: 'Local executor → Atlas', title: 'Prove the contribution', text: 'The water task finishes. One transaction credits shared water, records the receipt and updates the request. The builders can use that stock.', board: 'Verified report · supplied water · linked task receipt', state: 'Only the committed resource delta counts. The next observation sees it.' },
]

export default function ArchitectureGuide() {
  const [step, setStep] = useState(0)
  const current = example[step]
  return <section className="architecture-guide" aria-label="Complete Sketch Clash architecture">
    <header className="architecture-heading"><span className="colony-kicker"><Network size={13} /> THE WHOLE SYSTEM</span><h2>From your camera to a living crew.</h2><p>The app and workers run on your Mac. Gemini proposes; the game validates; MongoDB remembers.</p></header>

    <div className="architecture-journey" aria-label="Capture, battle, then isolated islands">
      {stages.map(({ title, icon: Icon, text, detail }, index) => <div className="architecture-stage" key={title}><span className="architecture-number">0{index + 1}</span><Icon size={22} /><h3>{title}</h3><p>{text}</p><details><summary>What happens here</summary><p>{detail}</p></details>{index < stages.length - 1 && <ArrowRight className="architecture-link" size={20} aria-hidden="true" />}</div>)}
    </div>
    <div className="architecture-flow-label"><ArrowDown size={18} /> EACH ISLAND RUNS THIS LOOP INDEPENDENTLY</div>
    <div className="architecture-loop" aria-label="Observe, discuss, validate, work, remember, then observe again">
      {loop.map(({ title, icon: Icon, text }, index) => <div key={title}><Icon size={21} /><h3>{title}</h3><p>{text}</p>{index < loop.length - 1 && <ArrowRight size={17} className="architecture-link" aria-hidden="true" />}</div>)}
    </div>
    <p className="architecture-return">↺ Saved receipts and the shared board become the next observation.</p>
    <div className="architecture-boundaries">
      <div><span className="colony-kicker"><Wrench size={13} /> LOCAL PYTHON WORKERS</span><h3>Keep the island moving</h3><p>Local workers resume durable councils and execute validated tasks. New residents, completed projects and changed conditions wake discussion. Accepted work continues between model turns and while your browser is closed.</p></div>
      <div><span className="colony-kicker"><Sparkles size={13} /> BOUNDED GEMINI TURNS</span><h3>One object, one context</h3><p>Up to three residents hold a short council using separate Gemini calls. They read real preceding messages, test hypotheses and explicitly agree on a feasible project. The executor records results and rejects unsupported actions.</p></div>
      <div><span className="colony-kicker"><Database size={13} /> MONGODB ATLAS</span><h3>The durable shared memory</h3><p>Transactions save state, conversations, commitments, experiment evidence and events. Atlas Vector Search recalls tested findings. A Change Stream feeds the Observatory; OpenTelemetry connects model calls to database operations.</p></div>
    </div>

    <section className="architecture-example" aria-label="Illustrative agent communication example">
      <header><div><span className="colony-kicker">WALK THROUGH AN EXAMPLE · ILLUSTRATIVE, NOT A LIVE TRANSCRIPT</span><h2>No energy? Build something useful.</h2></div><span>{step + 1} / {example.length}</span></header>
      <ol className="architecture-example-steps">{example.map((item, index) => <li key={item.title}><button type="button" aria-current={index === step ? 'step' : undefined} onClick={() => setStep(index)}><span>{index + 1}</span>{item.title}</button></li>)}</ol>
      <div className="architecture-example-content" aria-live="polite"><span className="colony-kicker">{current.actor}</span><h3>{current.title}</h3><p>{current.text}</p><div className="architecture-board-line"><MessageSquare size={17} /><span>{current.board}</span></div><p className="architecture-example-state"><CheckCheck size={16} />{current.state}</p></div>
      <footer><button type="button" className="colony-button" disabled={step === 0} onClick={() => setStep(step - 1)}>Previous</button><p>Actual project choices and evidence are in <strong>Discussion</strong>.</p><button type="button" className="colony-button is-yellow" disabled={step === example.length - 1} onClick={() => setStep(step + 1)}>Next <ArrowRight size={13} /></button></footer>
    </section>

    <details className="architecture-details"><summary>Storage map, recognition feedback and system boundaries</summary>
      <div className="architecture-storage"><h3>What lives where</h3><dl>
        <div><dt>Battle & placement</dt><dd><code>battles</code>, <code>colonyPlacements</code>, <code>colonyResidents</code></dd></div>
        <div><dt>Island & actor state</dt><dd><code>islandState</code>, <code>islandAgents</code>, <code>islandEvents</code> — scoped to each shore</dd></div>
        <div><dt>Council & cooperation</dt><dd><code>colonyBoard</code>, <code>colonyProjectOpinions</code>, <code>colonyCommitments</code>, <code>colonyDecisions</code>, <code>colonyContributions</code></dd></div>
        <div><dt>Model runs & councils</dt><dd><code>colonyPlanner</code>, <code>colonyReasoning</code>, <code>colonyCouncilSessions</code>, <code>colonyCouncilOutcomes</code> and shared provider usage</dd></div>
        <div><dt>Learning & observability</dt><dd>Object dossiers, experiment receipts, conditioned findings and blueprints; <code>agentEvents</code>, OpenTelemetry spans and minute metrics.</dd></div><div><dt>Recognition retrieval</dt><dd>Character catalogue + configured Atlas Vector Search. This is separate from the council’s ordinary state reads.</dd></div>
      </dl><h3>Recognition feedback has its own review loop</h3><p>Capture feedback → operator review → candidate reference / character → evaluation and render checks → explicit activation → approved recognition references. Feedback does not automatically rewrite a live fighter or grant an island capability.</p><h3>What the simulation means</h3><p>Resources are game units credited to shared stock. Motion illustrates task positions and timings; it is not a fluid, collision or physical-delivery simulation. Abilities come from accepted object identity and declared game rules. The Mac and backend must remain running for continuous work. The four original buildings remain. Agents can add tested assemblies made from supported parts. Hold, contain, support and reflection tests use authored analytical physics; their evidence applies only inside this simulation and its tested conditions. A tested optical relay can improve existing observation tasks, but cannot create energy or grant an object new powers.</p></div>
    </details>
  </section>
}
