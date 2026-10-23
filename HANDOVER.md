# Sketch Clash handover — 23 October 2026

## Current state

The camera/upload → recognition → confirmed photo fighters → authoritative battle → separate 3D island flow is implemented locally. **The current app uses durable MongoDB Atlas storage and genuine Atlas Vector Search.** A real Gemini/YOLO/OCR mug-and-bottle browser round saved both residents, and a full backend restart restored the same world, rest choice, battle, histories and byte-identical source photographs. Repeated completion changed no resident or battle counts. The physical MacBook camera remains unverified; upload is the live-tested input path.

Atlas cluster: `cluster0.hgrpk3.mongodb.net`; database: `sketch_clash`; world: `shared-demo`. The owner entered the database password through the hidden local setup prompt. The ignored `.env.local` contains the credentials and verified embedding configuration with mode 0600. Live health reports ready, MongoDB persistence, `persistent: true` and configured semantic retrieval. No billing, coupon balance or cluster tier was inspected, so the $100 credit's redemption and remaining balance are not verified here.

No deployment, external account change, Git history rewrite or secret publication was performed. The earlier hosting metadata was retired locally; that does not take any previously hosted copy offline.

## What changed and what stayed

- Kept the paper-and-ink branding, landing page, typography, private player handoff, reveal cards, arena choreography, health bars, impacts, KO, victory and replay. The original preset showdown remains available and clearly grants no unlocks.
- Replaced the notebook drawing input with video-only camera, still capture, upload, retake, object selection, integer crop controls and explicit fighter confirmation. The actual accepted photograph/crop remains visible through battle. Timers pause during permission, preparation and recognition; expiry never submits automatically.
- Added decoded JPEG/PNG/WebP checks on both sides, 5 MiB / 24 MP input bounds, orientation normalization, 1,600-pixel inference bound, immutable capture/hash tracking, stale-response protection and cleanup.
- Added local YOLO11n and English EasyOCR evidence alongside Gemini, separate evidence statuses/scores, useful selection/recapture states, actual resolver/validation/simulation tools and at most two configuration repairs. Empty detector/OCR results are allowed. Printed text is untrusted evidence.
- Added server-owned confirmation, seeded events, winner/HP, duration eligibility, retryable completion and immutable replay. Mongo repositories implement unique indexes, atomic completion, one resident per world/type, first-appearance preservation and distinct-battle counting. Both valid participants qualify only after completion.
- Added a separate lazy 3D island, reusable object templates, saved appearance/home, bounded local movement, rest/wander updates, photo/history detail cards and a collection fallback. World reads do not invoke recognition or create residents.
- Added exact/alias resolution and a genuine Atlas Vector Search adapter/setup command, now configured and live-tested. Similarity never merges identity or grants ownership. Unavailable retrieval is reported honestly.

The current brief uses **Everyday Objects**. Rotating category rounds, theme disqualification, eBay pricing, networked multiplayer, generated meshes and arbitrary-object 3D reconstruction are not part of this milestone.

## Run it

Installed dependencies, local model weights and backend-only Gemini/Atlas credentials are already present on this computer. The local servers were left running at [127.0.0.1:5173](http://127.0.0.1:5173/) and port 8000 in **MongoDB mode**.

```sh
cd /Users/sukhrajkalon/Documents/Codex/2026-10-23/i-w/outputs/sketch-clash
npm run dev
```

If those ports are already occupied by this preview, use it or stop its terminal before starting another copy. Default mode fails clearly when MongoDB is unavailable; it never silently substitutes memory. `npm run dev:demo` remains an optional development mode with explicitly temporary memory storage; do not use it to demonstrate Atlas persistence.

Fresh-machine setup and all supported environment settings are in [README.md](README.md) and `.env.example`. Do not overwrite the existing `.env.local` with a blank example. Keys and database credentials belong only in that ignored local file, never in chat, source, frontend `VITE_` variables or a shareable archive.

## Verification record

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

## Setup status and remaining human actions

### 1. Atlas access — complete; billing remains the owner's check

Atlas access is configured and verified. The backend connects from the home Mac, so Atlas must continue to allow that machine's public internet egress IP. A remote MacBook using an SSH tunnel over Tailscale does not connect directly to Atlas and does not need its own Atlas IP entry. Update the Atlas allowlist if the home connection's public IP changes.

The owner entered the `sketch_clash_app` password on the home Mac through `npm run setup:mongodb`. The helper URL-encodes it and atomically saves owner-only local settings while preserving Gemini and the world ID. Controlled file tests and interactive terminal checks passed, including no password echo and Ctrl-C cancellation without a write. Re-run it only if updating that user's password; the helper itself does not restart the app or test connectivity. No credentials need to be sent in chat.

To inspect the already-running backend:

```sh
curl --fail http://127.0.0.1:8000/api/health
```

Verified result: ready, MongoDB persistence, `persistent: true`, configured semantic retrieval and no configuration error. A real round and full backend restart have already verified resident, appearance, history and photo persistence; a duplicate completion left counts and residents unchanged. Check the Atlas billing page yourself to confirm the $100 coupon was applied, its expiry and remaining balance. No billing or tier verification is claimed by this handover.

Optional real transaction regression:

```sh
SKETCH_RUN_MONGO_TESTS=1 .venv/bin/python -m pytest backend/tests/test_mongo_integration.py -q
```

This suite creates and deletes its own random `sketch_test_*` database; use a database user permitted to do that, or a dedicated test replica set through `SKETCH_TEST_MONGODB_URI`. It never targets the application database for deletion.

### 2. Genuine semantic retrieval — complete

The local settings now contain `EMBEDDING_MODEL=gemini-embedding-2`, `EMBEDDING_DIMENSIONS=768` and `MONGODB_VECTOR_INDEX=character_types_vector`, saved atomically at mode 0600 while preserving credentials. All 21 approved types have real embeddings and the Atlas index is READY/queryable. The backend was restarted to load these settings. To repeat the live query:

```sh
npm run verify:retrieval
```

Actual candidates and matching embedding provenance were verified. `npm run setup:retrieval` is available for a fresh cluster or deliberate catalog/index rebuild; it is not needed for each game launch. Failure remains an explicit unavailable/degraded status and exact known types still work. Additional unfamiliar-object examples can demonstrate semantic matching; similarity alone never grants an island resident.

### 3. Exercise the physical MacBook camera

In the MacBook's own browser, open the app at `http://127.0.0.1:5173/` through the existing SSH tunnel over Tailscale. Use the MacBook browser rather than a browser inside the home Mac's remote desktop, so the MacBook's camera is available. Choose LET'S PLAY → I'M READY → Camera, grant video access, frame one object, Capture, Retake, capture again and confirm. Verify the accepted still/crop is the battle photo, the timer pauses during recognition and the camera indicator goes off after leaving capture. Also deny permission once and verify Upload remains usable. Microphone access must not be requested. This needs the device owner and remains pending.

## Demo and continuation

Use a mug and bottle on uncluttered backgrounds. Show the preparation details, confirm each fighter, let the battle finish, then enter the island. Refresh/restart now demonstrates verified real Atlas persistence. A repeated mug demonstrates identity preservation. The current app runs locally with cloud database storage; the optional `dev:demo` mode is still temporary and must be labelled accordingly.

The actual model is `gemini-4-argon`; Python SDK `google-genai==2.33.0`, Interactions API, medium thinking, `store=False`. Detector is official Ultralytics YOLO11n (`ultralytics==8.4.184`); OCR is English EasyOCR (`easyocr==1.7.2`). Architecture and combat rules are in [Design.md](Design.md). Dependencies are pinned in `package-lock.json` and `backend/requirements.lock.txt`.

Public QA photo sources: [white mug, Antonio Izquierdo García-Gallardo](https://commons.wikimedia.org/wiki/File:Taza_Blanca.jpg), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/); [blue water bottle, Byoung82](https://commons.wikimedia.org/wiki/File:Blue_Water_Bottle.jpg), [CC0](https://creativecommons.org/publicdomain/zero/1.0/). They appear in the verification screenshots, not as generated fighter art. Private captures were not collected.

Historical memory-mode visual evidence in the parent `outputs/` folder: `sketch-clash-island.png`, `sketch-clash-mobile-island.png`, `sketch-clash-mobile-details.png`, `sketch-clash-crop-evidence.png`, `sketch-clash-photo-battle.png` and `sketch-clash-photo-victory.png`. Those screenshots show earlier recorded battles and are not evidence of Atlas storage. Separate battles can have different generated names, appearance and winners. Current Atlas proof is recorded in the live browser battle and restart results above.

The project already contained a prototype before this implementation milestone. Confirm with organisers how any code preceding the Friday 17:00 kickoff must be disclosed or treated under the code-after-kickoff rule. Existing work/history was preserved. Before hackathon services expire, export MongoDB collections including `media`, preserve source and lockfiles, and keep secrets separately in a private backup.

Resume instruction: **“Atlas persistence, restart recovery and live Vector Search are verified. Read HANDOVER.md, finish the physical MacBook camera check through the existing SSH tunnel, and fix any resulting defects without rebuilding completed features.”**
