# Sketch Clash

**Making AI’s view of the physical world more reliable through human feedback and interactive play.**

Sketch Clash is a local two-player object battle game with two persistent 3D colonies. Photograph an everyday object, review its identity and fictional character, challenge a friend, then send the winner to Winner Island and the other fighter to Loser Island. Residents gather, build, gain experience and remember their contributions. A separate creator lab investigates recognition failures and requires human approval before adopting pipeline changes.

The research question is **“Can human feedback help AI create more reliable and useful digital representations of real-world objects?”** Storing feedback changes neither Gemini’s weights nor the active pipeline automatically. Intended benefits remain things to measure, not demonstrated improvements.

**Local only.** React/Vite and Python/FastAPI bind to `127.0.0.1`. Your selected photographs and supporting evidence are sent by the backend to Gemini; game records and compact images are stored in MongoDB Atlas. There is no public deployment or public account system.

## Start on this computer

Dependencies, vision weights and backend credentials are already configured. Preserve the ignored `.env.local`.

```sh
cd /Users/sukhrajkalon/Documents/Codex/2026-10-23/i-w/outputs/sketch-clash
npm run dev
```

Open [http://127.0.0.1:5173/](http://127.0.0.1:5173/). The API listens on port 8000. Use the existing server if those ports are already occupied. `npm run dev:frontend` and `npm run dev:api` start the services separately.

The MacBook can use the same URL through the existing SSH tunnel over Tailscale. Open it in the **MacBook’s own browser** to use its camera. Atlas connections originate from the home Mac, so the home connection’s public egress IP belongs in the Atlas allowlist; the remote MacBook’s IP and Tailscale address do not replace it.

The default repository is MongoDB and fails clearly if unavailable. `npm run dev:demo` explicitly selects temporary memory for development, labelled in the UI; its island disappears on backend restart. It is not a persistence demonstration.

## Build and demonstrate during the Gemini outage

```sh
npm run dev:offline
```

This starts the normal local services with `SKETCH_AI_PAUSED=true`. Atlas still saves the real islands and the local executor still completes valid work. New Gemini recognition, councils, reflections and embeddings are blocked before provider dispatch. Camera battles stay visible with a pause explanation, and **ORIGINAL DEMO** still runs the preset showdown; **PLAY OBJECT BATTLE** opens the new attribute-based fixture arena. The interface shows **Gemini paused**; the separately saved evaluation pause stays in place. This command does not change billing, credentials or model selection.

Open **[Island Playground](http://127.0.0.1:5173/#/playground)** for a separate practice simulation. Add a useful object, inspect its job, watch supplies become construction and compare the two example crews. The board explains rule-based choices and completed contributions. Pause, speed up or reset the practice world. Its state lives only in browser memory: these are example residents, not actual battle outcomes, Gemini discussions or saved Atlas records. The playground also works with the API server stopped while Vite is running.

The live islands now show shared supply shortages, productive tasks and the gains expected when each job completes. The Observatory distinguishes a public plan, a validated action and the saved receipt proving its effect. After the provider recovers, restart without `--offline` to remove the startup pause; the evaluation pause and existing provider-failure records are not automatically cleared. Resume and validate those deliberately before claiming new model-authored conversations.

## Object battles while Gemini is paused

Choose **PLAY OBJECT BATTLE** on the home page or open [the object arena](http://127.0.0.1:5173/#/battles). Choose two of twelve illustrated fixtures, inspect their attributes, limitations and conditional matchup effects, then start a battle. These are authored game profiles and **illustrative GBP prices**, not recognized photos or live market appraisals. The new arena requires the local API and configured storage, but no Gemini calls.

All objects start at 100 HP with a 20-point budget across impact, resilience, agility and control. Reusable interactions cover brittle surfaces, cushioning, reach, close grip, rolling, traction, limited water, flexible recovery, precise placement, redirecting a roll, bracing and hooking. Only the strongest positive and strongest negative applicable rules count on a hit, with a combined ±20% bound. Price has one logarithmic damage bonus capped at 1%; it does not increase health or grant abilities. Missing prices disable price bonuses for both fighters.

Both objects commit an action each round, so being animated first cannot steal a turn. Results distinguish knockouts, points decisions and tiebreaks. Equal health compares total impact before the remaining-health cap; only equal impact points use the saved random seed. Each hit carries its stat calculation, applicable rules, price contribution, randomness, rounding and health receipt. **Why this won** shows the recorded result and same-seed comparisons with price or interaction modifiers removed; it does not invent a model explanation.

Atlas saves these immutable practice matches in `arenaBattles`, including complete profiles, rules, price snapshots, seed, receipts and a snapshot digest. The match URL contains its saved ID for refresh/replay. Repeating a request returns the same result, and changing fighters under that request ID is rejected. Fixture battles never enter the real camera-battle collection or unlock island residents. Existing camera battles keep their original v1 rules, saved outcomes and island placements. Recognition integration and live comparable-price retrieval remain future work after the provider outage.

The checked-in [balance audit](docs/combat-balance-v2.json) covers 342,000 local simulations with 1,000 seeds per pairing or price comparison. Against a uniform mix of the other eleven fixtures, win rates range from 40.04% to 56.75%. Raising only an object’s sample price from £0 to the full £250 cap increased its win rate by at most 4.80 percentage points. These measurements apply to this authored roster, not every possible object. Run `npm run test:combat-v2` for integrity checks or `npm run check:combat-balance` to repeat the longer audit.

## Play and give feedback

1. Choose **NEW CAMERA BATTLE**. The current brief is **Everyday Objects**; this does not implement rotating themes or theme disqualification.
2. Pass the device privately to each player. Use camera or upload, select one object and crop or retake if needed. JPEG, PNG and WebP are supported; input limits remain 5 MiB and 24 megapixels, with a 1,600-pixel normalized image. Convert HEIC first.
3. Review the **source photograph beside the actual procedural 3D preview**. Answer **Correct**, **Correct it**, or **Not sure**. Factual corrections re-examine the photograph; they are suggestions, not unquestioned ground truth.
4. Optionally choose **Keep** or **Change details**, with reasons and a short comment. Skipping creative feedback is not a negative rating. Style revisions preserve the identity, class and fixed combat stats. The original proposal and correction lineage remain recorded.
5. Optionally opt in to reviewed evaluation/reference use of this object photo and feedback. This checkbox starts **off**. Declining does not affect gameplay. Player consent alone does not approve a dataset case.
6. **Lock in my fighter**, then pass the device. Feedback is tied to the exact output and pipeline version before the winner is known. Failed feedback saves are labelled honestly; a valid fighter can continue without a false saved claim.
7. Watch the recorded battle and enter the islands after completion is confirmed. The winner joins Winner Island and the other fighter joins Loser Island. Each side retains one resident per canonical object type; repeated appearances preserve that side’s original identity and history. The original shared collection is also preserved.

Normal capture time is 60 seconds per player; Quick Clash uses 20. Permission, normalization, recognition and saving pause active timing. Expiry never submits automatically. The camera stops when leaving capture. Refresh recovery includes a private handoff before showing the recovered photograph.

Quick, Power and Guard still have fixed presets and 100 HP. The server owns attacks, damage and winner; replay shows the same recorded outcome without extra unlocks. Normal/reduced battles last 12.8 seconds; Quick Clash lasts 6.4 seconds. **ORIGINAL DEMO** is the original scripted cinematic, with no recognition or island progression.

## Two islands, one rivalry

Choose **ENTER THE ISLANDS**, then **START BOTH ISLANDS** once. Existing completed battles are enrolled using their recorded outcomes; future completed battles route both fighters atomically. The original island remains accessible through **Original island**.

- Switch between Winner Island and Loser Island. Each has its own crew, resources, projects, board and history. Set a building priority, select an object in the 3D scene or roster, follow it, or assign an allowed job.
- Objects contribute through declared game capabilities: containers move supplies, suitable vessels collect water, stationery plans or measures, electronics observe signals, and batteries collect energy at a charging dock. All animated residents can move, gather basic materials and assist construction. A missing specialist creates a visible capability gap.
- Same-island agents post requests, accept commitments and produce resources. The board links each verified contribution to an actual completed action receipt. A message alone cannot create resources or claim success.
- **Under the hood** shows observation → memory → public intent → validation → task → receipt, plus real board connections. Rules, AI proposals and verified executor results are labelled separately. This displays public decisions, not private model reasoning.
- Compare building levels, work, cooperation and resource gaps. Optional GBP values are **your estimates**, with coverage displayed; they never alter capabilities, combat or rewards. Winning does not imply being more expensive, and this comparison is not a controlled experiment.
- Recognizable supported object silhouettes have blinking faces, moving limbs and work animation. Unsupported or conflicting identities preserve their source-photo card. These are procedural models, not arbitrary photo-to-3D reconstruction.

The **local Python backend runs the agents**; MongoDB stores durable state. The islands keep working with the browser closed while the Mac and backend stay awake. Restart catch-up is bounded to 120 seconds. Up to 40 residents work per island; additional residents remain in the collection. Resources are an abstract shared ledger; there is no physical cargo or collision/pathfinding simulation.

Routine work needs no model calls. Strategy now uses durable councils: up to three separately invoked residents exchange up to six turns, with `gemini-4-argon` proposing and `gemini-3.8-flash` replying. They read actual earlier messages and need explicit agreement on a feasible project. New arrivals change the capability fingerprint, reopen relevant research and invalidate stale proposals; accepted work remains intact. Each resident has an evidence dossier and can test holding, containing or supporting before proposing a bounded construction with real costs and benefits.

A shared provider queue coordinates Gemini work. `COLONY_REQUESTS_PER_DAY=0` removes the old local daily ceiling; periodic councils default to 120 seconds and relevant arrivals/completions can wake them sooner. Provider quotas and billing caps still apply. Definite throttles get bounded retries, account caps pause reasoning, and ambiguous transport outcomes are not replayed automatically. Configured models and actual provider usage are visible in AI settings.

Open **[Observatory](http://127.0.0.1:5173/#/observatory)** for live committed activity, saved session replay, linked OpenTelemetry traces and Atlas metrics. **Discussion** shows model-authored conversations and the island laboratory. No successful conversation is claimed when the provider is blocked. See [the current runtime architecture](docs/architecture/agent-observatory.md) for the system diagram, evidence boundaries and verification.

Starting the two-island mode switches off the original island’s persona-only reflection to avoid competing planners. Its existing residents, saved appearance and history stay intact. The legacy view retains its own 12-request limit within the same usage counter.

See [COLONIES_IMPLEMENTATION.md](COLONIES_IMPLEMENTATION.md) for the implemented architecture, SDK and validation boundaries. [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md) remains the earlier audit/design draft; the bounded analytical testbed is implemented as described in the current runtime architecture. [ISLAND_PLAN.md](ISLAND_PLAN.md) describes the preserved original island.

## Recognition & World Quality

Choose **QUALITY LAB** from the home screen. This entry is absent during a round. To unlock it, run this yourself in a private terminal on the home Mac after starting the backend:

```sh
npm run operator:token
```

Paste the displayed local operator key into the lab. Do not put it in chat, screenshots or source. The key is generated into ignored, owner-only `backend/data/operator-token`; it is never bundled into the frontend. The server checks an expiring HTTP-only, SameSite cookie for review, jobs, render reports, exports, activation and rollback. Failed key attempts are rate-limited. This is a local operator gate, not a public authentication system.

The lab contains:

- **Review queue:** completed/closed rounds only, original evidence, proposal, player feedback and actual rendered preview. Record your own reviewer name, reason and factual/creative judgement; acceptance alone is not human-reviewed truth.
- **Baseline and dataset readiness:** separate reference, development and reserved-final roles, case revisions, physical-object/session grouping, consent and ambiguity. Unreviewed or disputed cases are ineligible.
- **Evaluation jobs:** fixed baseline runs and one-candidate improvement jobs, with estimates, progress, cancellation, usage and failures. No usable reviewed data produces **Needs human review**, without spending on a purported evaluation.
- **Comparison:** independent factual counts, technical checks and blinded A/B creative review. Ties, neither acceptable and pending review are valid outcomes. Load the actual scene to record render checks; fallback images are not a pass.
- **Active version and rollback:** inspect the configuration diff and gate reasons. Only the operator can activate a passing candidate. Rollback selects the baseline or a previously active version. Existing rounds keep their pinned version; saved residents are not redesigned.

Current baseline: `baseline-v1`. Its visual-reference limit starts at zero to preserve the inspected configuration. **There are currently no approved evaluation/reference cases and no supported improvement claim.** The 21 catalogue descriptions used for type search are not a human-reviewed photo dataset. The full policy, scoring and implementation limits are in [Design.md](Design.md); actual evidence and pending checks are in [HANDOVER.md](HANDOVER.md).

## Budgets and human authority

Each operator-triggered improvement job may propose **one** candidate. Policy ceilings are 60 provider requests, 600,000 aggregate reserved tokens, 48,000 input tokens and 4,096 output tokens per request, and a 10-minute deadline. The current durable worker processes requests sequentially, below the concurrency ceiling of two. These are limits, not targets; the UI can select a smaller request budget.

Requests, repairs and embeddings count against budgets. Unknown request outcomes remain conservatively reserved and are not blindly resubmitted after interruption. A failed, cancelled, interrupted, incomplete or over-budget comparison cannot activate anything. Current orchestration uses bounded synchronous Interactions requests; it does not require an external agent framework, managed sandbox or background generation service.

The fixed adoption policy requires at least three reviewed development cases and three fresh reserved cases from three independent groups, complete matching results, valid combat/schema and actual render checks, no increase in wrong accepted identities, no coverage drop, no increase in unnecessary clarification and bounded latency. Recognition candidates need independent improvement; appearance candidates need supporting human comparison. Passing remains provisional and still requires an explicit human activation.

## Autonomous island crews

Open **The islands**. **Island** shows the crew’s current goal and actual construction/supply contributions. **Discussion** shows capability-based project opinions, the validated choice, and request → offer → receipt threads. **Architecture** shows the complete capture-to-island system and an illustrative communication sequence; live model records sit in a separate disclosure.

Model councils discuss feasible projects and alternatives, with the backend checking the whole next upgrade before accepting agreement. Routine tasks gather resources using the selected goal and approved capabilities. Manual overrides have a **Return control to crew** action. Provider failure remains visible; the executor supplies no artificial model votes. Execution remains local, with Atlas persistence.

## Atlas retrieval and persistence

The existing collections hold battles, captures, content-hashed media, residents, worlds and encounters. Island collections add `islandState`, `islandAgents`, `islandEvents`, `islandPlanner` and `islandReasoning`: transactional economy/buildings, durable tasks and personas, append-only action/command journals, daily budgets and recoverable plans. Quality collections hold exact-output feedback, human reviews, case revisions, frozen jobs/results/comparisons, immutable pipeline versions, an atomic active pointer and activation history. Evaluation paths cannot create battles, rewards or residents, and do not write to the live type catalogue.

Colony collections add `colonyModes`, `colonyResidents`, `colonyPlacements`, `colonyBoard`, `colonyProjectOpinions`, `colonyCommitments`, `colonyDecisions`, `colonyContributions`, `colonyEstimates`, `colonyPlanner` and `colonyReasoning`. Scoped `islandState`, `islandAgents` and `islandEvents` hold each side’s simulation. Placement, action effects, commitments and idempotency are checked transactionally; model calls run outside transactions. The decision loop uses indexed queries plus conditioned findings retrieval through Atlas Vector Search when embeddings and the index are available; otherwise it labels exact retrieval as a fallback. New collections retain dossiers, experiments, findings, blueprints, council sessions, transactional events, sanitized spans and minute metrics. MongoDB stores these records; Python runs the agents.

Two retrieval systems are deliberately separate:

1. **Type catalogue:** exact names/aliases first, then genuine Atlas Vector Search over approved descriptions. The historical live setup has 21 Gemini Embedding 2 vectors, 768 dimensions, in `character_types_vector`. To deliberately set up a fresh catalogue, configure the embedding settings and run `npm run setup:retrieval`; verify with `npm run verify:retrieval`.
2. **Reviewed visual references:** eligible object photos use a separate `qualityReferenceVectors` collection and `quality_references_vector` index. In the lab, create/check that index explicitly, then prepare selected approved reference cases using a bounded durable job. No gameplay photo is automatically enrolled. Index creation/permission failures remain visible; a fallback is never called Vector Search. Live similarity queries enforce world, review, consent, role and embedding provenance, exclude the same image and held-out groups, and recheck current case revisions after search. Frozen evaluations use their own eligible reference snapshot, not the mutable live index.

No paid visual-reference query runs when references are disabled, absent, not enrolled or the separate index is unavailable. Similarity supplies evidence; it neither establishes identity nor merges residents. The Atlas coupon’s redemption, expiry, balance and cluster tier require the owner’s check.

## Fresh setup and configuration

Use Node 22.18+ and Python 3.12. JavaScript and Python dependencies are locked in `package-lock.json` and `backend/requirements.lock.txt`.

```sh
npm ci
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r backend/requirements.lock.txt
npm run setup:vision
npm run setup:gemini
npm run setup:mongodb
npm run dev
```

Without `uv`, create `.venv` using Python 3.12 and install the same Python lockfile with its pip. Vision setup downloads official YOLO11n and English EasyOCR weights to ignored `backend/models/`; runtime does not download them automatically. The secure Gemini/Atlas prompts preserve unrelated settings. Restart the backend after changing local settings.

Supported environment names, with defaults documented in `.env.example`: `COLONY_REQUESTS_PER_DAY`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS`, `MONGODB_URI`, `MONGODB_DATABASE`, `SKETCH_WORLD_ID`, `SKETCH_REPOSITORY`, `FRONTEND_ORIGIN`, `MAX_UPLOAD_BYTES`, `MAX_IMAGE_PIXELS`, `INFERENCE_MAX_EDGE`, `RECOGNITION_CONCURRENCY`, `EVIDENCE_TIMEOUT_SECONDS`, `YOLO_MODEL`, `YOLO_ENABLED`, `OCR_ENABLED`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `MONGODB_VECTOR_INDEX`. The operator gate also accepts an optional `SKETCH_OPERATOR_TOKEN` override; normal local use needs no override and uses the generated file. `operator:token` displays that generated file, not an environment override.

Keep `.env.local` at mode `0600`, ignored by Git. Never prefix secrets with `VITE_`. Private captures, model weights, generated builds, caches and the operator token are excluded from commits.

## Local Gemini safeguards

All Gemini services in the running backend share one admission queue: recognition, council turns, original-island reflection, embeddings and quality evaluation. Defaults are **four requests per minute**, at least **15 seconds between dispatches**, **one request in flight**, **eight waiting requests**, and **200 dispatched requests in a rolling 24-hour window**. Failed requests still count. A full waiting queue or exhausted local daily guard rejects the request before contacting Google. Provider `Retry-After` cooldowns also apply.

Configure these with `GEMINI_REQUESTS_PER_MINUTE`, `GEMINI_PROVIDER_CONCURRENCY`, `GEMINI_MAX_PENDING` and `GEMINI_REQUESTS_PER_DAY` in the server environment or `.env.local`, then restart. Values are local safety limits, not Google's reported quotas or a spending budget. Counters reset on backend restart and do not cover other processes, scripts or applications using the Google project. Google also applies model-specific token and project-wide quotas; this limiter does not measure remaining Google quota. Check the new project's actual limits in [AI Studio](https://ai.google.dev/gemini-api/docs/rate-limits) before raising the defaults.

SDK automatic retries are disabled for both Interactions and embeddings, so each queue admission permits one HTTP attempt. Application-level retries, when allowed, must pass through the queue again; ambiguous timeouts remain uncertain. Recognition output is capped at 4,096 tokens, council/reflection and improvement turns at 2,048. Image/context bounds and existing evaluation budgets still apply. `SKETCH_AI_PAUSED=true` and the durable evaluation pause independently prevent new automatic work; changing the API key does not clear those pauses or old provider-error history.

The Observatory's **Gemini request pace** control changes actual dispatch spacing: Slow, Steady and Fast use 25%, 50% and 100% of the configured request ceiling (by default 1, 2 and 4 requests/minute). Fast preserves the previous default. Selection is saved in the world-scoped `providerControls` collection and restored before workers start. Updates wake queued callers to recalculate their wait; they do not cancel in-flight calls, reset counters, bypass provider cooldowns or unpause AI/evaluations. This is a maximum admission rate, not a promise of that many calls: new decisions still depend on planner readiness and useful work. Replay speed only changes playback.

The contribution ledger totals completed `islandEvents` action receipts over the last hour, grouped by island and character. It shows actual stock added, construction work and costs reserved at task start. It reads at most 1,000 recent receipts per island and declares when totals are sampled. New receipts retain resource, project and actor before/after snapshots plus capability and decision provenance. The executor applies abstract simulation yields; a shoreline survey is not a real-world discovery or an unrecorded Gemini thought. Full storage produces an explicit zero-gain result. Proposals and model calls have no action receipt until work completes, and are labelled accordingly. Historical receipts retain their original text and explicitly disclose missing evidence; they are never backfilled with invented snapshots. Claimed Gemini actions require a matching accepted decision, completed provider turn and council session before they count as model-attributed contributions.

## Model-use note

- **Gemini 4 Argon**, official Python `google-genai==2.33.0`, Interactions API, medium thinking: live recognition/character proposals and the bounded improvement reasoning/tool loop. Provider/version metadata is retained when returned. Feedback influences validated configuration and approved context, not model weights.
- **Gemini Embedding 2**, official embedding API: existing catalogue description vectors and the explicitly prepared visual-reference adapter, both with versioned 768-dimensional provenance. No claim that visual references have been enrolled when the dataset is empty.
- **YOLO11n** (`ultralytics==8.4.184`) and **EasyOCR** (`easyocr==1.7.2`): local still-image evidence. Their scores are distinct from Gemini uncertainty and are not calibrated identity confidence.
- **Gemini 4 Argon / Gemini 3.8 Flash**, official SDK and Interactions API: separate proposal/reply turns in persistent island councils, with structured capability checks, contextual memory and experiments. Actual usage and public decisions are persisted. **Gemini 3.5 Flash-Lite** remains in the preserved original island’s persona reflection. Routine animation and work do not call models.
- React 19.3.1, Motion, Three 0.186.1, React Three Fiber 9.8.2 and Drei 10.7.9: local rendering, including the shared preview/verification harness. It uses supported procedural templates and parameters, not generated meshes or photo-to-3D reconstruction.

## Verification, export and backup

```sh
npm run test:combat
npm run test:images
npm run test:island-scene
npm run test:backend
npm run build
```

`npm run preview` serves the build locally and proxies `/api` to the separate backend. See HANDOVER for test dates, service/fixture distinctions and any unfinished final checks.

Use the lab’s **Export approved evidence** control for reviewed, consented case metadata, immutable configurations and policy. From a selected job, export its run/result records as well. The JSON deliberately excludes raw media bytes, private gameplay feedback, embeddings, credentials and opaque model steps. Image references in that export require a separate private backup of the corresponding Atlas `media` collection to remain usable.

Before hackathon resources expire, take an authorized database backup/export of the application collections **including `media`, all island collections and all quality collections**, and store it privately with access controls. Retain downloaded approved-only JSON exports for portable analysis. Keep secret configuration separately from source archives. The private [GitHub repository](https://github.com/Sukhraj1000/sketch-clash) backs up source and commit history; it does not back up Atlas data. Preserve regular focused commits and existing history.

The physical MacBook camera remains unverified until the device owner checks it. AR, rotating themes, eBay pricing, online multiplayer/accounts, arbitrary mesh generation and a hosted always-on worker are outside this increment. Any pre-existing prototype should be disclosed according to the organisers’ rules; history must not be rewritten to hide it.

Candidate decisions and dataset transitions remain human actions: the comparison screen can record an explicit rejection with a reviewer/reason, and the data screen can move an exposed reserved group into development as one atomic transition. Rejection prevents adoption; retirement preserves case history and does not make used final cases independent again. Fresh reserved groups are required for a later claim.
