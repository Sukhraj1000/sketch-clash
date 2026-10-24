# Sketch Clash handover — 24 October 2026

## Current increment — autonomous crews and clearer islands

Both islands now choose projects through a persisted crew council. Whole-upgrade feasibility separates missing capabilities from supplies the crew can gather; existing tasks/reservations remain intact. Rules cast capability-based actor preferences, and bounded Gemini turns can submit proposals, support and objections. One actor has one active project stance, retained up to six hours or full project completion so the next automatic actor can read it. Supply requests keep their separate five-minute expiry. Manual priority is an explicit optional override with a return-to-crew command.

The page now has **Island / Discussion / Architecture** tabs. Island focuses on the shared goal and actual build work/resource contributions. Discussion shows real council positions, the recorded choice, model-origin notes and request/offer/receipt threads. Architecture contains the entire capture/recognition/battle/routing/agent/storage flow, local-versus-cloud boundaries, an illustrative communication walkthrough, and expandable live run records. No example dialogue is labelled as a live transcript.

Deformation came from four residents sharing the exact rest coordinate and coarse saved proportions stretching precise object meshes. Known rigid objects now use uniform presentation scale, grounded feet, calmer motion and deterministic display slots. Mug/pitcher handles and the spout face correctly. Source identities, saved appearances and authoritative task positions remain unchanged. Current 4+4 residents are visually verified; a 40-resident shared station can still be crowded.

Live Atlas migration automatically moved both shores from the energy-blocked beacon to garden level 2, then to boardwalk level 2. The original world API matched the pre-restart checkpoint exactly. A real saved rule-generated supply exchange was verified: Sir Measure-a-Lot requested 2 water; Creamy Citadel Mug offered and supplied 2; the request links to the completion receipt. No fabricated battle or resident was inserted. The four-building/three-level content ceiling still applies.

Final backend suite: **189 passed, 2 optional Mongo fixture tests skipped**. Coverage includes automatic peer discussion across 0/15/30-minute turns, six-hour opinion expiry, scope/replay, full-upgrade resource admission, capability gaps, manual release and long-run construction. Browser QA covered both shores, live council data, step-through example, keyboard tabs, 390px/737px layouts without horizontal overflow and no new console errors. Production build and scene geometry/timeline/animation checks passed. Fresh screenshots are outside Git: `../sketch-clash-island-council.jpg`, `../sketch-clash-crew-discussion.jpg`, `../sketch-clash-architecture-guide.jpg`.

The final live Gemini check returned **RateLimitError**. No decision/output was applied; shared usage is 17/24 including earlier turns. The durable run remains uncertain and automatic provider calls are blocked conservatively. Local council/tasks continue and Discussion surfaces the provider error. Do not silently reset usage or repeatedly retry. A later explicit actor turn can be requested after the provider quota is available; a successful result resumes normal automatic scheduling. Model proposal/support across independent actor turns was verified with provider fixtures, not claimed as a successful live call in this increment.

## Earlier increment — two islands and useful cooperation

The default island view now compares Winner Island and Loser Island. Immutable completed battle slots route to distinct per-side residents; the original collection and original island are preserved. Each side has its own resources, tasks, projects, capability-limited agents and shared work board. A typed internal SDK accepts requests, offers, actions and evidence-backed reports; transactions enforce ownership, accepted capability, exclusive commitments and exactly-once effects. See [COLONIES_IMPLEMENTATION.md](COLONIES_IMPLEMENTATION.md) for architecture, diagrams, limits and demo steps.

The original paper arcade theme remains. Eighteen procedural object identities now improve coarse saved templates while retaining identity, palette, accessories and scale. Limbs, blinking, working poses, follow controls and a visible charging dock make the existing task state legible. The in-app **HOW THE ISLAND THINKS** diagram links actual public proposals, checks, tasks, receipts and same-island replies. Both explicit AI entries and deterministic coordination are labelled honestly.

### Verification for this increment

- Backend suite: **169 passed, 2 optional Mongo fixture tests skipped**. Real Atlas verification below ran separately. Coverage includes routing/replay, atomic rollback, scoped ownership, capability upgrades, truthful reports, concurrent claims, late decision causality, player priority, quota/recovery, read-only GET and optional-planner outage.
- Production build, TypeScript, scene checks (801 timeline and 64,908 bounded pose samples), combat checks and 14 image-input assertions passed. The large lazy Three.js chunk remains a build advisory; physical camera capture remains unverified.
- Live Atlas initialization enrolled **four residents per shore** from actual completed battles. Original `worldCharacters` API records matched the checkpoint exactly after initialization and again after restart. No fabricated battle or character was inserted into the shared world.
- Full local backend restart preserved both resident lists, budget and completed progress. At the checkpoint after recovery: Winner Island had 60 completed tasks, 1 building upgrade, 6 fulfilled requests; Loser Island had 61 tasks, 2 upgrades, 4 fulfilled requests. The simulation continues, so these are dated observations rather than fixed scores. SDK v2 upgraded the pitcher to water keeper and TV to observation scout without rewriting source residents.
- Three new real Flash-Lite calls: one accepted winner decision (1,896 reported tokens), one rejected structured response with no applied effects, then one accepted loser decision (3,542 reported tokens). Shared usage reached 15/24, including 12 prior original-island calls. No quota reset or refund hid failed work. The invalid response prompted bounded stored proposal diagnostics and a rejection test. Automatic scheduling remains enabled after the successful explicit turn.
- Atlas timed out once during startup index setup; a subsequent restart recovered successfully. The app remains local, backed by Atlas. Gemini and Atlas secrets were not changed or exposed.
- Browser verified restored home, both shores, selected resident detail, recognized shapes, live project progress, the shared board and the interactive evidence diagram. Switching shores revealed a nested React root cleanup error in the charging-dock HTML label; replacing it with a disposable WebGL sprite eliminated new console errors across reload and both switch directions. New screenshots are outside Git: `../sketch-clash-two-islands.png` and `../sketch-clash-agent-loop.png`. Responsive styles are implemented; new two-island mobile-width visual QA has not yet been performed.

The two-island planner uses a default 24 calls per UTC day shared with original-island usage, one automatic actor turn every 15 minutes and a 60-second manual cooldown. Local tasks keep running without model calls. Both current crews lack an energy carrier; energy-dependent construction can wait for an appropriate object or a different player-selected project. Price fields are optional **user estimates**, not market data, and cannot affect power. The economy is an abstract ledger; physical cargo conservation and a controlled causal cooperation experiment remain future work. Append-only receipts grow with actual activity; only query windows/context are bounded.

## Earlier increment — the purposeful island

The original bold **paper arcade UI is restored**. The island is now a small persistent colony: object-based residents travel, gather, build, level up and remember actual contributions. The user requested this expansion; earlier statements that autonomous island behaviour was out of scope are superseded by [ISLAND_PLAN.md](ISLAND_PLAN.md). Everything remains local, with server-side Gemini and Atlas.

Four staged structures—garden, workshop, beacon and boardwalk—each have three upgrade levels and a real production benefit. After all 12 upgrades, expeditions consume supplies and add discoveries. Residents have object-based capabilities, automatic useful-job selection, manual assignments, XP, levels, a bounded personal journal and optional AI-refined personas/plans. Use a 3D site or blueprint to set construction priority. Select a resident for task/personality/memory details, job assignment and original photo/history. Orbit, zoom, follow, reset, pause/resume and the accessible roster are available.

**The local Python backend executes agents; MongoDB stores their state.** Work continues with the browser closed while the home Mac/backend is awake. A backend interruption allows 120 seconds of bounded catch-up, once. This does not supply cloud execution while the home computer is off. Five new collections (`islandState`, `islandAgents`, `islandEvents`, `islandPlanner`, `islandReasoning`) preserve state separately from existing characters and battles. Up to 40 residents work; additional saved residents stay in the collection. Newly unlocked residents join via **WELCOME NEW RESIDENTS**.

Routine decisions/movement cost no Gemini requests. The optional **Gemini 3.5 Flash-Lite** planner uses official Interactions calls, bounded batches of six, one automatic batch per 15 minutes, at most 12 requests and 84,000 conservatively reserved tokens per UTC day. Initial roles exist without AI. AI can refine personality and an allowed useful-action preference, never resources, abilities, combat or appearances. Its inputs contain object metadata and recent recorded simulation events, not photos or quality feedback. The UI labels AI plans separately from recorded actions. Quota, provider failure and explicit retry are visible; unknown/invalid responses block automatic retries. The AI toggle is separate from simulation pause.

### Current island evidence

- Final backend suite: **122 passed, 2 optional real-Mongo tests skipped**. The separate live Atlas test below did run. Animation checks passed 801 authoritative timeline samples; existing combat checks passed 2,561 samples and image checks passed 14 assertions.
- Final TypeScript/Vite production build passed. The lazy Three.js scene retains a bundle-size advisory (about 981 kB uncompressed / 260 kB gzip), plus the existing development THREE.Clock deprecation warning; no renderer errors were observed.
- Full live server restart: with the colony temporarily paused at **112 completed actions**, all agent tasks/personas/memories, resources, projects, events, revision, discovery state and planner quota matched exactly after restart. The original five-resident world response also matched exactly. The colony was then resumed. Detailed report: `work/island-restart-verification.json` in the parent workspace.
- Real shared-world start through the UI: **five residents**, an initial completed Flash-Lite reflection with **1,405 reported tokens**, working resource/task/XP/memory updates and durable personas. Original collection, appearances, homes and history references matched the pre-change snapshot exactly after the new simulation ran.
- Real WebGL checks: selectable 3D residents/sites, Follow, Reset, orbit, pause/resume, task travel/work props, and growing construction. The garden reached level 1 and remained built after reload; the workshop then reached 27% and showed construction posts. Later progress is intentionally ongoing.
- Isolated live Atlas/Gemini check: six controlled residents, 42 completed actions before reflection, a built garden, three concurrent advances with exactly-once effects, then a successful Flash-Lite response with **3,141 reported tokens**. Persona application did not alter resources. A new Atlas repository instance recovered exact agents/resources; seven days of test downtime yielded only 120 seconds once. The isolated world was removed. These are engineering fixtures, not a learning or recognition benchmark.
- An earlier isolated reflection returned an invalid structured response. It was rejected without applying a persona, retained its budget and did not automatically retry. A new explicit diagnostic run succeeded. Neither result was presented as human judgement or model training.
- Deterministic simulation checks cover concurrency, restart, pause, offline caps, resource reservations, unknown-object progression, persona source validation and four-hour operation without deadlock. Planner checks cover quotas, unknown outcomes, local recovery, missing model-version metadata and six-resident context bounds. Existing quality/combat/image checks remain in place.
- Actual 320/390-pixel browser layouts had no document overflow; the roster/inspector, quality operator gate and capture handoff were usable. A temporary empty capture round was cancelled without taking/uploading a photo or calling recognition. Physical MacBook camera capture remains unverified.

Desktop evidence outside Git: `../sketch-clash-arcade-restored.jpg`, `../sketch-clash-colony.jpg`, `../sketch-clash-colony-full.jpg` and `../sketch-clash-resident-agent.jpg`. Mobile checks are `../sketch-clash-arcade-mobile.jpg`, `../sketch-clash-island-mobile.jpg` and `../sketch-clash-capture-mobile.jpg`. Some include existing object thumbnails and are deliberately excluded from source commits. Non-secret detailed reports are `work/island-live-verification.json` and `work/island-scene-qa.json` in the parent workspace.

The quality baseline remains `baseline-v1`; no candidate was adopted and no reviewed dataset or recognition improvement claim was added. Atlas credit redemption/balance/tier were not inspected. The private GitHub repository backs up source/history, not database records or private photos. Keep the home backend running to demonstrate a living island.

## Earlier increment — recognition and quality workflow

The local game now has a **human-reviewed recognition and character-quality loop**, plus a cleaner object-studio interface. The capture → confirmation → recorded battle → persistent island path remains in place. The application still runs locally on the home Mac, accessed from the MacBook through the existing SSH/Tailscale tunnel; Atlas and Gemini remain backend integrations.

**Current active baseline: `baseline-v1`; no candidate has been activated.** Approved reference/development/reserved dataset counts are currently **0 / 0 / 0**. There is no independent recognition improvement, creative preference result or candidate regression rate to claim. The isolated engineering smoke below records actual latency/usage, but it is not a reviewed benchmark. The 21 earlier catalogue description embeddings are not reviewed photograph cases. Storing feedback does not train Gemini’s weights.

Atlas remains configured for `sketch_clash`, world `shared-demo`. The most recent UI check showed **five saved residents**. Existing source photographs, resident appearance and history must remain intact. The physical MacBook camera is still unverified. Atlas coupon redemption, expiry, balance and cluster tier have not been inspected.

## What changed

- **Home, capture, battle and island:** a calmer paper/ink design, coherent mint/coral palette, better spacing and responsive controls, live illustrative 3D landing specimen and more focused island presentation.
- **Fighter review:** source photo beside the actual procedural 3D character; separate Correct / Correct it / Not sure and optional Keep / Change details. Feedback is saved against the exact output/version before battle. Creative skipping is neutral. Factual/style corrections preserve original evidence and lineage; style cannot change fixed combat power.
- **Privacy and permission:** recovered captures pass through the private handoff too. The creator lab is entered from Home, and its queue only exposes completed/closed rounds. Optional image/feedback reuse permission starts off. Failed saves show the real state, with a way to continue a valid round without claiming saved feedback.
- **Version continuity:** inspected immutable baseline, atomic active pointer, per-round version pinning, explicit unknown historical provenance and compatible legacy recovery. Adoption/rollback never rewrites a resident or accepted battle.
- **Recognition & World Quality:** local operator gate; review provenance; grouped, consented, revised cases; separate dataset roles/readiness; durable evaluation jobs; deterministic factual/technical results; actual rendered previews; blinded human comparisons; guarded activation and rollback.
- **Bounded improvement agent:** one validated candidate per operator job, limited configuration tools and independent final evaluation. No access to labels/roles/scoring-policy mutation, arbitrary code, human approval or activation. All outcomes remain reviewable.
- **Two retrieval paths:** the existing catalogue search and a separate approved visual-reference adapter/index. The latter has explicit index/preparation controls, budgeted durable embedding jobs and server-enforced isolation. Empty or unapproved data never becomes a fake visual dataset.
- **Portable records:** approved-evidence/configuration exports and selected job results, with raw/secret/private fields excluded. Media still needs a separate private database backup.

Fixed Quick/Power/Guard presets, 100 HP, server-owned winner/events, 12.8-second normal/reduced and 6.4-second quick battles, identical replay, duplicate-reward protection, both-player unlocks and first resident appearance/home are preserved. Watch the Showdown is still a scripted demo without progression. Current gameplay remains Everyday Objects; no rotating themes, eBay values, online multiplayer, AR or arbitrary mesh generation was added.

## Run and review

```sh
cd /Users/sukhrajkalon/Documents/Codex/2026-10-23/i-w/outputs/sketch-clash
npm run dev
```

Open [http://127.0.0.1:5173/](http://127.0.0.1:5173/). The API is local port 8000. Reuse an already running instance rather than starting a second one on those ports. Leave MongoDB mode enabled; `npm run dev:demo` is temporary memory only.

For the creator area, select **QUALITY LAB** on Home. In your own private terminal, run:

```sh
npm run operator:token
```

Paste the displayed key into the lab and keep it private. The server generates the ignored `backend/data/operator-token` at mode 0600; the token is not shipped in frontend code. The operator session expires after eight hours. The command is deliberately interactive-terminal-only; do not ask an agent to print the key into logs or chat. An optional `SKETCH_OPERATOR_TOKEN` environment override exists, but the helper displays the generated file rather than an override.

Keep existing Gemini/Atlas settings in ignored `.env.local` and never overwrite it with a blank example. Secure setup commands remain `npm run setup:gemini` and `npm run setup:mongodb`; neither requires sending secrets in chat. README lists supported environment names, runtime setup and backup boundaries.

## Earlier quality verification

| Check | Actual scope/status |
| --- | --- |
| Backend suite | **91 passed, 2 optional real-Mongo tests skipped** on the final revision, including 9 rejection/group-retirement tests. Controlled providers verify lifecycle, isolation, budgets and gates; they do not establish recognition quality. |
| Production build | TypeScript and Vite build passed. The lazy Three.js scene retains the existing bundle-size advisory (about 942 kB uncompressed). |
| Combat and image checks | Passed 2,561 combat timeline samples, authoritative replay/health/winner, hidden-page pause and exactly-once completion; all 14 image-input checks passed. |
| Current Atlas restart | The complete shared-world response, including all five residents and their saved appearance/state/history references, matched exactly before and after backend restart. |
| Real Gemini evaluation smoke | One isolated public mug-photo case ran the actual versioned evaluator with Argon, local evidence and frozen catalogue metadata. Completed with one generation request, 2,621 reported tokens, a valid ceramic-mug fighter and 31,277 ms end-to-end case latency. This includes local evidence work and is not a latency benchmark. The result survived an Atlas repository reconnect. |
| Real correction smoke | A separate isolated live preparation saved private exact-output feedback, then generated a new style/name proposal. Identity, class and stats stayed fixed; original proposal and parent-output lineage remained intact. No residents were created. Only the generated test-world records were removed. |
| Actual browser render → Atlas | A temporary, explicitly labelled engineering fixture used an existing saved mug appearance. The real browser rendered and checked idle, rest and wander separately, then persisted a passed report with valid bounds/visibility and no errors. An independent Atlas read confirmed it. The exact temporary job/result were removed; no human comparison was invented. |
| Operator and empty-data browser UX | Real login/logout and approved export worked; unauthenticated overview returned 401. Review queue/readiness, job, comparison and version screens worked. With zero approved data, paid runs, reference preparation and adoption remained disabled. Export contained zero cases and one baseline version. |
| Responsive/browser renderer | Desktop and 390 × 844 screens fit without horizontal overflow. Actual island residents and saved-appearance previews rendered. The procedural landing specimen, water/coastline and refined controls were inspected visually. |
| Secrets and privacy | Source scan found no current Gemini key or Atlas URI. `.env.local` and the operator-token file are ignored with permissions 0600. Ordinary logs and browser bundles contain neither secret. |
| Human evidence and activation | No approved cases, no independent baseline/candidate dataset, no human creative comparison and no activation. The shared world remains unchanged with five residents. Physical MacBook camera verification remains pending. |

The bounded agent tool loop, final-case isolation, request uncertainty, activation and rollback are covered by controlled engineering tests. A live reviewed agent comparison was not run because there is no human-reviewed dataset. No new visual-reference vectors or index were populated without approved images. The existing catalogue contained 23 approved records in the live snapshot, including the earlier 21 embedded descriptions; these are not a reviewed image dataset.

Current screenshots are in the parent `outputs/` folder: `sketch-clash-refined-home.png`, `sketch-clash-refined-island-full.png`, `sketch-clash-refined-island-mobile.png`, `sketch-clash-quality-readiness.png`, `sketch-clash-quality-mobile.png`, and `sketch-clash-engineering-render-check.png`. The last explicitly shows an engineering fixture, not a human judgement.

Non-secret detailed reports are in the workspace `work/quality-live-smoke.json` and `work/quality-render-browser-check.json`. These contain scope and measured outcomes, not credentials or private photo bytes.

## Fixed policy and experiment boundaries

Policy `quality-policy-v1` is frozen into each comparison. At least **three approved development cases plus three fresh reserved cases from three independent groups** are needed for the minimum gate; such a small passing sample remains provisional. Actual recognition numerators/denominators, coverage, clarification, latency and usage remain separate from creative preference and technical validity.

Wrong accepted identities and unnecessary clarification cannot increase; answered coverage cannot fall. Candidate latency is limited to twice baseline. All required outputs and actual render checks must pass. Recognition scope needs independent factual/clarification improvement. Appearance scope needs complete human A/B review with supporting preferences; ties are allowed records, neither acceptable blocks appearance adoption, and missing review stays pending. An authorised human must still activate the passing candidate. Stale pointer/revision checks prevent an old approval overwriting newer state. Explicit candidate rejection records an immutable reviewer/reason decision and prevents later adoption. After a reserved group has been used, the operator can move the whole group into development atomically; case revisions and frozen run snapshots stay intact, and a fresh final group is required.

An operator job has at most **one candidate, 60 provider requests, 600,000 reserved tokens, 48,000 input / 4,096 output tokens per request and ten minutes**. The implemented worker runs sequentially (one active request, within the ceiling of two). Repairs and embeddings count; estimates and usage are persisted. An uncertain provider outcome is not automatically retried. Cancelled, failed, interrupted, incomplete and over-budget jobs cannot activate anything. No precise monetary cost is claimed without verified pricing.

Each case has a role assigned before the run: approved reference, development or reserved final. Same physical-object/session views remain one group, with exact/near-duplicate checks and conservative uncertain grouping. Expected answers, player corrections and answer-bearing filenames do not enter prediction requests. The optimiser sees development failures only. A correction of the same photo is successful interaction repair, not evidence of unfamiliar-object generalisation. Frozen final cases cannot be reused to claim independence after they inform another revision.

Actual scene parameter/bounds/visibility/animation checks establish technical execution. They do not prove aesthetic resemblance. A WebGL fallback is unavailable verification, never a pass. Preview/evaluation does not create residents, battles, rewards or encounters.

## Approved visual references

The separate `qualityReferenceVectors` collection and `quality_references_vector` index are for reviewed object photos, not the existing type-description catalogue. Use the creator lab’s index check/create control, then explicitly prepare selected approved, consented reference cases. Those preparation jobs persist progress and conservative budgets. The baseline has `reference_limit: 0`; enrolment alone does not change gameplay configuration or adopt a candidate.

Only eligible reference-role cases can be prepared/retrieved. Live search excludes the same hash and held-out groups, filters provenance on the server, and rechecks case revision/consent after eventual-consistency index results. Missing access/index/data remains visible; there is no fabricated vector fallback. No newly enrolled live visual references or performance claims are recorded at this point.

## Honest three-minute demo

Prepare uncluttered real object photos and a completed/closed round with an **actual** issue or a genuine human preference. If there is no issue to demonstrate, show the correct result and explain the available correction path; do not manufacture a failure and call it real. Keep the new capture’s source photo visible.

| Time | What to show |
| --- | --- |
| 0:00–0:20 | Research question and the benefit being tested: a game where people can check and improve AI’s representation of their objects. |
| 0:20–0:55 | Fresh real capture or clearly identified recent real proposal, source photo beside 3D, factual versus creative feedback and explicit optional photo consent. The human chooses their own verdict. |
| 0:55–1:25 | Close/finish the round before opening the creator queue. Show the exact output/version, reviewer provenance and grouped roles. A correction is labelled current-attempt repair. |
| 1:25–2:10 | If suitable human-reviewed evidence exists, open a **labelled precomputed** baseline/candidate job with date, inputs and versions. Show counts, missing data/regressions, real render reports, blind preference and budget. If it does not exist—as currently—show **Needs human review** and the blocked gate honestly. Do not fake an instantaneous optimisation run. |
| 2:10–2:30 | Show the human’s actual approve/reject decision or the reason activation remains unavailable. A rejected candidate is a valid demonstration. Never click human approval on someone’s behalf. |
| 2:30–3:00 | Continue a prepared real round through Quick Clash and the persistent island, or briefly show a completed real round and make a fresh spot-check. Clearly distinguish a replay from fresh inference. |

To demonstrate a real independent improvement rather than readiness, first collect enough consented human-reviewed development and fresh reserved groups, run baseline, prepare a bounded candidate, inspect rendered comparisons and obtain human judgement. Precompute only the expensive batch, retaining its timestamps/configuration; perform a fresh spot-check live. If recognition takes longer than the demo window, show the genuine running state and a labelled saved run instead of claiming instantaneous results.

## Human actions needed

1. **Unlock and review:** use your local operator key; give consent only for object-focused photos you permit to be reused. Supply factual labels/grouping and creative judgements yourself. Create reference/development/fresh reserved cases before expecting meaningful comparisons.
2. **Adoption:** inspect any completed candidate’s independent scores, actual previews, usage and regressions, then explicitly approve or reject it. The active baseline stays unchanged until valid evidence and human action exist.
3. **MacBook camera:** through the existing local SSH URL, grant camera access in the MacBook’s own browser; test Capture, Retake, crop, review and handoff, then check the camera stops. Deny permission once and verify upload still works. No microphone permission should be requested.
4. **Resources and backups:** check the Atlas coupon/balance/expiry. Export approved metadata/results from the lab and privately back up Atlas media and game/quality collections before temporary resources expire. GitHub contains source/history, not live data.

## Exports and operational continuity

The lab’s approved-evidence export includes reusable consented case metadata, immutable versions and fixed policy; selected-job export adds its results. It deliberately omits raw media bytes, unapproved private gameplay feedback, embeddings, credentials and opaque model steps. Keep corresponding media in a separate authorised private Atlas backup if those image references must survive service expiry. Do not put such a database backup or `.env.local` into the Git repository.

The private remote is [Sukhraj1000/sketch-clash](https://github.com/Sukhraj1000/sketch-clash). Existing history and the regular focused-commit workflow are preserved. Do not change repository visibility or rewrite timestamps/history. Current source backup is separate from database restoration.

Actual model stack: `gemini-4-argon` for recognition and bounded improvement reasoning, official Python `google-genai==2.33.0`, Interactions API, medium thinking, bounded output and `store=False`; `gemini-embedding-2` for description vectors and explicit reviewed-image embedding; local YOLO11n/Ultralytics 8.4.184 and EasyOCR 1.7.2. No managed Antigravity, deep-research agent, image-generation model or weight-training service was added.

## Historical verification — earlier camera/island milestone, 23 October

The following records are preserved as historical evidence. They do **not** claim that the later human-feedback increment was already covered by those checks.

| Check | Result and scope |
| --- | --- |
| `npm run build` | Passed TypeScript and production build. The separately loaded Three.js scene produces a bundle-size advisory, not a build failure. |
| `npm run test:combat` | Passed 2,561 baseline timeline samples, fixed contacts/winner, replay, hit-stop and reduced motion; authoritative 7/11/15-event playback, either winner, exact contact health and quick playback; hidden-page pause/resume and exactly-once completion. |
| `npm run test:images` | Passed 14 assertions: supported signatures, mismatched MIME, size, cancellation, crop bounds/minimum and camera-denial messaging. This is not physical-camera coverage. |
| `npm run test:backend` | 36 passed; 2 opt-in Mongo integration tests skipped by default. Controlled model responses cover real validation/repair paths, ambiguity, crop-only OCR, unavailable evidence, stale races, explicit confirmation, retries, cancellation, immutable replay, duplicate types/effects, media, world isolation and cross-origin mutation rejection. |
| Original local MongoDB transaction tests | Both opt-in tests passed against a temporary **real MongoDB 8.2.9 local replica set**, then that test process was stopped. Includes 12 concurrent creates, 20 concurrent finalizations, same-type count-once, concurrent first-appearance preservation, durable media and repository reconnect/read restoration. |
| Live Atlas repository checks | Scoped transaction/concurrency checks passed against the actual configured Atlas database. Cleanup removed only the isolated test world, preserving the application's shared world. Non-secret report: `work/atlas-repository-checks.json` in the workspace root. |
| Real AI checks | Real public mug and bottle photographs passed local YOLO/EasyOCR plus `gemini-4-argon` via the official SDK/Interactions API. Mug detection returned a cup box; the bottle had empty detector/OCR results and still reached Gemini successfully. Actual resolver, fighter, visual and simulation checks passed. These are smoke tests, not a recognition-accuracy benchmark. |
| Historical normal browser flow (memory mode) | Passed upload → explicit confirmation → private handoff → reveal → 12.8-second recorded battle → completion → two residents. Visible HP at the fifth contact matched the saved events (40/52); the displayed winner matched the server. Pending world was empty. Memory completion was labelled nonpersistent. |
| Browser recovery and invalid input | Refresh restored a pending fighter for confirmation; a malformed image was rejected with usable upload recovery. Detailed preparation statuses and original photos were visible. |
| Historical crop / quick / replay browser check (memory mode) | A manual mug crop passed the live pipeline with its own immutable capture. A refresh preserved player one's confirmation and restored private player-two setup. A second real bottle upload completed a recorded **6,400 ms quick battle**, winner slot 0, final HP 10/0, with the matching victory. Replay and refresh restored that outcome; both residents remained at one distinct battle. |
| Live Atlas browser battle | Battle `ebd78ac9f73f24df875811c0bc549d0c`: real mug/bottle uploads, explicit confirmations, **6,400 ms quick battle**, winner slot 0 (mug), final HP **6/0**, two residents and `durable: true`. The mug's rest choice was saved through the island UI. |
| Full backend restart and duplicate completion | Exact world/state, saved rest choice, entire battle/events/outcome, both encounter histories and both byte-identical photographs survived a complete server restart. Repeated finalization returned the identical battle, with unchanged world, counts and residents. Browser reload restored both 3D residents; mug details showed RESTING, one distinct battle and WON history for the recorded battle. Non-secret report: `work/atlas-ui-restart-check.json` in the workspace root. |
| 3D and collection | Actual mug/bottle geometry rendered in Chrome and the in-app browser. Detail cards, source photos, encounter history and rest/wander updates worked. The original fallback bug was fixed; Atlas now preserves the saved state across backend restarts as verified above. |
| Responsive browser check | The final 3D island also rendered in the in-app browser at 390 × 844. Island, collection, resident details and history were usable; document width and scroll width both measured 390 px before and after opening details. Temporary viewport override was reset. |
| Secret boundary | Ignored `.env.local` remained mode 0600. Source/build literal-key scan found no exposed key. The browser calls only the local backend for AI. |
| Live Atlas Vector Search | 21 real catalog embeddings stored using `gemini-embedding-2`, 768 dimensions and schema version 1. `character_types_vector` is READY/queryable. An actual hot-drink-vessel query returned mug (0.91744), cup (0.90005), bowl (0.85757), with matching provenance. These scores express similarity, not recognition confidence. Non-secret report: `work/live-atlas-retrieval-check.json` in the workspace root. The earlier explicit-unavailable result is historical, before configuration. |

Automated model tests use controlled responses. Only the explicitly described photograph checks used live Gemini and local learned models. Browser uploads were automated through the browser tooling; no deterministic fake webcam or physical camera was used. Repository transaction tests used real MongoDB but controlled fighter data; the separately recorded Atlas browser battle used actual photograph recognition. Current island data is durable Atlas evidence; earlier memory screenshots remain historical UI evidence.


## Historical assets and continuation

Public QA photo sources: [white mug, Antonio Izquierdo García-Gallardo](https://commons.wikimedia.org/wiki/File:Taza_Blanca.jpg), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/); [blue water bottle, Byoung82](https://commons.wikimedia.org/wiki/File:Blue_Water_Bottle.jpg), [CC0](https://creativecommons.org/publicdomain/zero/1.0/). These are real public test photographs, not generated fighter art or a reviewed evaluation dataset.

Historical memory-mode screenshots in the parent outputs folder include `sketch-clash-island.png`, `sketch-clash-mobile-island.png`, `sketch-clash-mobile-details.png`, `sketch-clash-crop-evidence.png`, `sketch-clash-photo-battle.png` and `sketch-clash-photo-victory.png`. They are not Atlas persistence proof. The separately recorded Atlas battle/restart checks above establish that earlier milestone. Different rounds may have different generated names, appearances and seeded winners.

The pre-existing prototype and its history should be disclosed under the organisers’ applicable rules. This increment neither deploys a public app nor removes an earlier hosted copy by retiring local hosting metadata.

Resume instruction: **“Read the current increment in HANDOVER.md and ISLAND_PLAN.md. Preserve the live colony, original residents, quality baseline, private handoff and existing Git history. Routine island work runs locally and persists to Atlas; optional model reflection remains bounded. Continue only the next requested improvement. Never fabricate human evidence or activate a quality candidate on the owner's behalf.”**
