# Sketch Clash architecture

## Baseline and preservation

The original local React 19 / Vite / Motion app contained landing, theme, drawing handoff, reveal, arena and victory screens. Its preset five-contact battle was a scripted cinematic. Before changes, production build and `test:combat` passed. Baseline screenshots of landing, input, reveal, arena and results were saved under the task's `work/baseline/` directory. Existing paper textures, typography, palette, responsive layout and choreography are retained. The original preset showdown remains an explicitly labelled cinematic demo with no unlocks.

The minimum integration is camera/upload within the notebook, a photo-to-fighter adapter, server events supplied to the existing Motion timeline, then a separate lazy world. No generated fighter images or mesh generation are involved.

## Flow and authority

Browser normalization strips EXIF, applies orientation once and exports a JPEG no longer than 1,600 pixels. Backend decoding independently checks supported media, size and pixel limits. Integer crop coordinates refer to this oriented canonical image. The camera preview is not mirrored. Immutable capture IDs and image hashes distinguish original/retaken/cropped input; late responses cannot overwrite the current selection. The actual processed image becomes battle artwork.

Local YOLO proposes boxes. EasyOCR reads only the selected region. Empty detection/text is allowed; evidence availability, detector scores, OCR scores and model uncertainty remain distinct. Gemini receives the selected photo plus evidence and proposes a fictional personality and approved combat/appearance specification. Real resolver, schema/preset, appearance and deterministic simulation tools run on the backend; actual failures are returned for at most two repairs. Printed text is untrusted evidence. Validation proves configuration safety, not recognition accuracy or game balance.

The backend owns `draft → ready → running → completed`, with cancellation/failure alternatives. Capture confirmation is separate from recognition. Start persists fixed fighter snapshots, seed, engine version, events, winner, approved mode and completion eligibility before playback. The browser can only play that sequence. Normal/reduced modes are 12.8 seconds; quick mode is 6.4 seconds. Completed replay does not grant another reward. After animation the browser finalizes the same battle ID; failed saves are retryable without another photograph or model call.

Only atomically completed battles unlock residents. Both participants qualify, including the loser. Same-type slots create one resident and count one distinct battle. A later encounter updates bounded history/count state while preserving the first accepted appearance. The first slot wins an initial same-type appearance tie.

## Data and persistence

`characterTypes` holds versioned stable identity, aliases, approved archetype/template mappings and optional embeddings. Template reuse never changes canonical identity. Exact/alias resolution precedes optional semantic candidates.

`battles` holds lifecycle, pending captures, confirmed selections, immutable event sequence and completion metadata. `captures` holds independent capture revisions/results to avoid growing a battle document without bounds. `media` stores content-addressed compact JPEG bytes once. `worlds` holds shared world configuration. `worldCharacters` holds one resident per world/type, first appearance/home and intentional state. `encounters` holds bounded-query battle history rather than an unbounded array.

MongoDB unique indexes and conditional updates protect creation requests, canonical types, world/type membership and encounter effects. Multi-document completion uses a transaction, with idempotent terminal state and unique effects. Recognition and media processing are outside transactions. A single world-scoped query retrieves residents and does not create records or invoke models. All targets are restricted to the configured world.

The memory repository is an explicit development option only. It exercises the same lifecycle but loses everything on restart and marks completions `durable:false`. It never claims Atlas success. Atlas integration checks require a real replica-set/Atlas URI; local in-memory tests cannot prove transaction behavior.

## Deterministic combat

Quick: HP100, attack16, defense2, speed3. Power: HP100, attack24, defense1, speed1. Guard: HP100, attack18, defense7, speed2. Hash-derived seeded jitter is an integer from −3 to +3. Damage is `clamp((attack − defense + jitter) × 2, 16, 38)`, capped by remaining health. Higher speed acts first; equal speeds use the seed. Turns alternate. At most 10 ordinary attacks then a decisive remaining-health/seed tiebreak produces at most 11 events. The event schedule fits the existing short cinematic. This is a deliberately small baseline, not a claim of competitive balance.

## World and retrieval

A lazy React Three Fiber view uses reusable low-poly mug, bottle and image-badge templates; additional visual templates may reuse the generic renderer. Saved appearance seeds, colours, proportions and homes drive rendering. Bounded wandering and idle motion are local, paused when hidden and restrained for reduced motion. Intentional rest/wander is a bounded API write. The collection and detail/history view remain usable without WebGL. There is no world camera input or model call per frame.

Optional Atlas Vector Search embeds approved descriptions using the same configured model/dimensions at indexing and query time. Provenance is persisted and mismatches fail closed. Similarity provides related candidates, not identity or ownership. Missing embedding configuration, credentials or index is explicitly unavailable; exact resolution remains functional. Index setup is an explicit command, never a world-read side effect.

## Limits and operational choices

Local servers bind 127.0.0.1. Credentials load only in Python from ignored `.env.local`; no browser API keys. Still-image inference uses bounded concurrency, timeouts and loaded-once local weights. No continuous camera inference. Media is durable with MongoDB; local development memory is not a backup. The shared local prototype intentionally does not add authentication or support public deployment.

See README for setup and HANDOVER for the exact verification record, remaining human prerequisites and demo steps.
