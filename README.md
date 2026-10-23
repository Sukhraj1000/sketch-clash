# Sketch Clash

A local two-player camera battle game. Photograph or upload one everyday object per player, confirm Gemini's checked fighter, watch the existing paper-and-ink showdown, then visit the characters in a separate island.

**Local only.** The frontend and backend bind to `127.0.0.1`. No hosted preview, sign-in or deployment is involved. Recognition sends the selected still image and supporting evidence to Google's Gemini API; persistent mode stores game records and compact images in your MongoDB Atlas database.

## Start on this computer

Dependencies and local vision weights have already been installed. Gemini and Atlas credentials are configured in ignored, owner-only `.env.local` and are read only by the backend. The current app uses **durable MongoDB Atlas storage**, with genuine Atlas Vector Search also verified.

```sh
cd /Users/sukhrajkalon/Documents/Codex/2026-10-23/i-w/outputs/sketch-clash
npm run dev
```

Open [Sketch Clash locally](http://127.0.0.1:5173/). The configured Atlas cluster is `cluster0.hgrpk3.mongodb.net`, database `sketch_clash`, world `shared-demo`. A real uploaded mug/bottle round completed with durable unlocks for both residents. A full backend restart preserved the exact world, saved rest choice, battle, histories and photograph bytes; browser reload restored both 3D residents. Detailed verification and the remaining physical-camera check are in [HANDOVER.md](HANDOVER.md).

The owner has already entered the Atlas password through the hidden `npm run setup:mongodb` prompt. Run that helper again only when updating credentials for database user `sketch_clash_app`; it URL-encodes the password, preserves Gemini and other local settings, and selects MongoDB mode. It does not test connectivity or restart the running server. For another cluster, configure `MONGODB_URI` and `MONGODB_DATABASE` in `.env.local` directly.

Leave `SKETCH_REPOSITORY=mongodb` for durable play. Default mode never silently falls back to memory. Missing or inaccessible Atlas configuration produces a clear service error, while the preset cinematic remains available. `npm run dev:demo` is an optional **temporary memory mode** for development: its battles, images and residents disappear on backend restart, and its UI marks them as nonpersistent. Stop previous servers before switching modes. Both commands launch Vite on port 5173 and FastAPI on port 8000. `npm run dev:frontend` and `npm run dev:api` run them individually for troubleshooting.

## Fresh setup

Use Node 22.18+ and Python 3.12. The tested Python environment is pinned in `backend/requirements.lock.txt`.

```sh
npm ci
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r backend/requirements.lock.txt
npm run setup:vision
npm run setup:gemini
```

If `uv` is unavailable, create a Python 3.12 virtual environment with `python3.12 -m venv .venv` and use `.venv/bin/python -m pip install -r backend/requirements.lock.txt`. Vision setup downloads the official Ultralytics YOLO11n and English EasyOCR weights to ignored `backend/models/`; runtime does not download weights automatically.

The Gemini setup command uses a hidden terminal prompt and preserves other settings. Do not put secrets in `VITE_` variables or frontend code. `.env.local` should remain mode `0600`, ignored by Git and excluded from archives. `.env.example` documents the actual supported configuration without secrets. Model IDs, image bounds, API timeout and evidence switches are configurable.

## How to play

1. Choose **LET'S PLAY**. This milestone uses **Everyday Objects**, with one object per player; it is not the older proposed rotating-theme game.
2. Pass the device to each player. Choose camera or upload. JPEG, PNG and WebP are supported; maximum input is 5 MiB and 24 megapixels. HEIC must be converted first.
3. Capture or select one target. Multiple candidates require a box or manual crop. The preview is a framed real photograph, not a claimed transparent cutout. Review the name/type, then confirm. The camera is stopped when leaving the input screen.
4. See the reveal, seeded battle, KO and victory. The server controls health and winner. **QUICK CLASH** shortens capture time and plays the approved 6.4-second battle; normal and reduced motion use 12.8 seconds.
5. Wait for confirmed completion, then enter the island. Both valid participants qualify. Repeated types retain their original resident, appearance and home. Rest/wander changes are saved explicitly.

Capture timers pause during permission, image preparation and recognition. Expiry does not submit a blank frame. Player one's image is hidden during player two's setup. Cancelled/incomplete battles do not unlock residents. Refresh offers recovery from the same server battle. Failed completion can be retried without another model call. Replaying a completed battle grants no extra effects.

**WATCH THE SHOWDOWN** remains the original scripted preset demo. It uses no recognition and grants no unlocks. The drawing component remains in source for reference but is not the current input path.

## Actual AI and rendering stack

- Python `google-genai==2.33.0`, `gemini-4-argon`, `client.aio.interactions.create`, `thinking_level=medium`, `store=False`, manually retained interaction steps for repairs. No deprecated sampling fields. The earlier JS connectivity dependency is retained at `@google/genai==2.31.0`; it is not imported by the browser.
- Local `ultralytics==8.4.184` / YOLO11n and `easyocr==1.7.2` / English OCR. Still images only; models load once, bounded worker, CPU inference off the async event loop. Empty results are normal. Failed/unavailable components are reported separately.
- Real type resolution, fighter validation, appearance validation and deterministic simulation tools. At most two specification repairs, separately bounded transport retry. Configuration checks do not establish image accuracy or perfect combat balance.
- React 19.3.1, Motion, Three 0.186.1, React Three Fiber 9.8.2 and Drei 10.7.9. World rendering is lazy, local and independent of Gemini. A collection view supports WebGL failure.

## MongoDB and optional retrieval

Atlas must allow this computer's IP and a database user with access to the configured database. Use a replica-set/Atlas deployment supporting transactions. Startup creates required regular unique/query indexes and seeds approved character types; it does not create world residents. Completion and its unlock effects commit together, protected by state transitions and unique effects. No API key or Atlas credential reaches the browser.

Collections: `characterTypes`, `battles`, `captures`, `media`, `worlds`, `worldCharacters`, `encounters`. See [Design.md](Design.md) for responsibilities and invariants. Images are content-addressed compressed JPEG records, not repeated base64 payloads. World loading uses a bounded world-scoped query and never runs recognition.

Known types use exact/alias lookup first. Genuine Atlas semantic retrieval is configured on this computer: 21 approved catalog descriptions are embedded with `gemini-embedding-2`, 768 dimensions and schema version 1; `character_types_vector` is READY and queryable. A live query for a vessel for hot drinks returned mug, cup and bowl. For a fresh cluster or a deliberate catalog/index rebuild:

```sh
# Set EMBEDDING_MODEL=gemini-embedding-2 and EMBEDDING_DIMENSIONS=768
# in .env.local, alongside Atlas and Gemini credentials.
npm run setup:retrieval
```

The setup command embeds approved descriptions, stores model/dimension/schema provenance and creates `character_types_vector` if absent. Wait for the index to become READY in Atlas, then run `npm run verify:retrieval` for an actual query. Restart the backend after changing embedding settings before checking related discoveries in the game; settings load at startup. Querying uses matching preprocessing/model/dimensions and a small approved candidate set. Related discoveries describe similarity, never ownership. Missing configuration or index is explicitly unavailable; no fabricated vector results. Atlas credit redemption, remaining balance and cluster tier have not been inspected by the agent.

## Verification and local build

```sh
npm run test:combat
npm run test:images
npm run test:backend
npm run build
```

`npm run preview` serves `dist/` locally and proxies `/api` to the separately running backend. The production build does not publish anything. Tests use controlled model responses unless explicitly described as live in [HANDOVER.md](HANDOVER.md).

The current verification record, actual blockers, physical-camera distinction and exact demo sequence are in HANDOVER. Architecture is in Design. Key modules:

| Area | Files |
| --- | --- |
| Camera, upload, crop, handoff | `CaptureStudio.tsx`, `imageInput.ts` |
| Screen flow, recovery, completion | `App.tsx`, `lib/api.ts` |
| Motion timeline and server-event playback | `game/director.ts`, `game/battle.ts`, `BattleArena.tsx` |
| Image/vision/model/tools | `backend/app/images.py`, `evidence.py`, `recognition.py`, `catalog.py`, `retrieval.py` |
| Lifecycle and persistence | `backend/app/service.py`, `repository.py`, `main.py` |
| World/collection/detail renderer | `WorldView.tsx`, `WorldScene.tsx` |

No public authentication, networked multiplayer, pricing/eBay mechanic, generated meshes, exact arbitrary-object reconstruction or continuous offline simulation is claimed. Before hackathon resources expire, export the MongoDB database including media, preserve source/lockfiles and keep a private copy of configuration outside any shareable archive. Ask organisers how the existing pre-kickoff prototype must be disclosed; do not remove history to conceal it.
