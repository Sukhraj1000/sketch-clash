# Sketch Clash

**Making AI’s view of the physical world more reliable through human feedback and interactive play.**

Sketch Clash is a local two-player object battle game with a persistent 3D colony. Photograph an everyday object, review its identity and fictional character, challenge a friend, then give both fighters useful work on their island. Residents gather, build, gain experience and remember their contributions. A separate creator lab investigates recognition failures and requires human approval before adopting pipeline changes.

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

## Play and give feedback

1. Choose **LET’S PLAY**. The current brief is **Everyday Objects**; this does not implement rotating themes or theme disqualification.
2. Pass the device privately to each player. Use camera or upload, select one object and crop or retake if needed. JPEG, PNG and WebP are supported; input limits remain 5 MiB and 24 megapixels, with a 1,600-pixel normalized image. Convert HEIC first.
3. Review the **source photograph beside the actual procedural 3D preview**. Answer **Correct**, **Correct it**, or **Not sure**. Factual corrections re-examine the photograph; they are suggestions, not unquestioned ground truth.
4. Optionally choose **Keep** or **Change details**, with reasons and a short comment. Skipping creative feedback is not a negative rating. Style revisions preserve the identity, class and fixed combat stats. The original proposal and correction lineage remain recorded.
5. Optionally opt in to reviewed evaluation/reference use of this object photo and feedback. This checkbox starts **off**. Declining does not affect gameplay. Player consent alone does not approve a dataset case.
6. **Lock in my fighter**, then pass the device. Feedback is tied to the exact output and pipeline version before the winner is known. Failed feedback saves are labelled honestly; a valid fighter can continue without a false saved claim.
7. Watch the recorded battle and enter the island after completion is confirmed. Both valid participants qualify, including the loser. Returning object types retain their original appearance, home and history. The review screen labels a distinct battle proposal and lets you inspect the saved resident separately.

Normal capture time is 60 seconds per player; Quick Clash uses 20. Permission, normalization, recognition and saving pause active timing. Expiry never submits automatically. The camera stops when leaving capture. Refresh recovery includes a private handoff before showing the recovered photograph.

Quick, Power and Guard still have fixed presets and 100 HP. The server owns attacks, damage and winner; replay shows the same recorded outcome without extra unlocks. Normal/reduced battles last 12.8 seconds; Quick Clash lasts 6.4 seconds. **WATCH THE SHOWDOWN** is the original scripted cinematic, with no recognition or island progression.

## Give the island a purpose

Open **MY ISLAND** or **BUILD YOUR ISLAND** on the restored paper arcade home. Choose **START BUILDING** once to give existing residents persistent roles. New arrivals can join with **WELCOME NEW RESIDENTS**; up to 40 residents work at once, with the rest retained in the collection.

- Choose a blueprint or click its 3D building site to set the crew's priority. The garden, workshop, beacon and boardwalk each have three levels and improve resource production.
- Select a resident in the scene or crew dock. Read its persona, current task, XP and memories; assign a job or return it to automatic useful work. Directions apply after its current task finishes.
- Watch residents travel, carry supplies, water, plan, survey and construct. Buildings appear in stages. Orbit, zoom, follow a resident and reset the view; the roster provides a non-3D control path.
- Earn permanent building upgrades and resident levels. After construction, expeditions consume supplies and add discoveries. A five-resident test crew reaches its first building in roughly two minutes; timing depends on roles and assignments.
- Pause/resume the settlement separately from **OCCASIONAL AI PLANNING**. State, tasks, memories, resources and progress persist in Atlas. Original appearances, battle stats and histories are unchanged.

The **local Python backend runs the agents**; MongoDB stores their durable state. They continue with the browser closed while the Mac and backend remain awake. After a backend stop, at most 120 seconds are simulated once. This is not a remotely hosted worker or unlimited offline progress.

Routine tasks use local simulation with no model request per action. Optional `gemini-3.5-flash-lite` reflection batches propose coherent personas and an allowed useful-job preference. At most six residents enter a batch, one automatic batch runs per 15 minutes, and the world has a hard ceiling of **12 provider requests / 84,000 reserved tokens per UTC day**. Each request has bounded input/output and no transport retry. Starting enables this planner; switching it off keeps local simulation running. An unknown or invalid result blocks automatic reflection until an explicit retry; its reserved budget remains spent. AI plans cannot grant resources, add powers, execute code or rewrite saved appearances. Prose is model-authored; event references are checked, not a proof of every sentence.

See [ISLAND_PLAN.md](ISLAND_PLAN.md) for the implemented plan and [Design.md](Design.md) for persistence details.

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

## Atlas retrieval and persistence

The existing collections hold battles, captures, content-hashed media, residents, worlds and encounters. Island collections add `islandState`, `islandAgents`, `islandEvents`, `islandPlanner` and `islandReasoning`: transactional economy/buildings, durable tasks and personas, append-only action/command journals, daily budgets and recoverable plans. Quality collections hold exact-output feedback, human reviews, case revisions, frozen jobs/results/comparisons, immutable pipeline versions, an atomic active pointer and activation history. Evaluation paths cannot create battles, rewards or residents, and do not write to the live type catalogue.

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

Supported environment names, with defaults documented in `.env.example`: `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS`, `MONGODB_URI`, `MONGODB_DATABASE`, `SKETCH_WORLD_ID`, `SKETCH_REPOSITORY`, `FRONTEND_ORIGIN`, `MAX_UPLOAD_BYTES`, `MAX_IMAGE_PIXELS`, `INFERENCE_MAX_EDGE`, `RECOGNITION_CONCURRENCY`, `EVIDENCE_TIMEOUT_SECONDS`, `YOLO_MODEL`, `YOLO_ENABLED`, `OCR_ENABLED`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `MONGODB_VECTOR_INDEX`. The operator gate also accepts an optional `SKETCH_OPERATOR_TOKEN` override; normal local use needs no override and uses the generated file. `operator:token` displays that generated file, not an environment override.

Keep `.env.local` at mode `0600`, ignored by Git. Never prefix secrets with `VITE_`. Private captures, model weights, generated builds, caches and the operator token are excluded from commits.

## Model-use note

- **Gemini 4 Argon**, official Python `google-genai==2.33.0`, Interactions API, medium thinking: live recognition/character proposals and the bounded improvement reasoning/tool loop. Provider/version metadata is retained when returned. Feedback influences validated configuration and approved context, not model weights.
- **Gemini Embedding 2**, official embedding API: existing catalogue description vectors and the explicitly prepared visual-reference adapter, both with versioned 768-dimensional provenance. No claim that visual references have been enrolled when the dataset is empty.
- **YOLO11n** (`ultralytics==8.4.184`) and **EasyOCR** (`easyocr==1.7.2`): local still-image evidence. Their scores are distinct from Gemini uncertainty and are not calibrated identity confidence.
- **Gemini 3.5 Flash-Lite**, the same official SDK and Interactions API, low thinking: optional island persona and useful-job reflection. Metadata and actual usage are persisted; routine colony tasks do not call it. It receives object metadata and recent simulation events, not photographs or player feedback.
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
