# Sketch Clash repair record — 24 October 2026

This pass implements the approved audit repairs and investigates the reported object-recognition failures. It preserves local hosting, Slow gameplay Gemini, the durable evaluation pause and each island's separate pause setting. No new semantic classifier, agents, paid evaluation batch or billing change is part of this work.

## Agent evidence and discussion

- **A1 — Board claims:** executor receipt facts are the primary text for completed-work reports. Model interpretation is separately labelled **Unverified model commentary**. Historical Observatory events are normalized when read, including replay and live stream publication. Missing or foreign evidence cannot inherit a verified contribution claim. Stored historical records are preserved.
- **A2 — Attribution:** one shared resource request remains owned by its original speaker. Later speakers publish their own immutable acknowledgements referencing that request. The acknowledgement creates no resources and does not claim another agent's work. Replay remains idempotent.
- **A3 — Rejected discussions:** validation still rejects unsupported actions without applying effects. Recoverable validation failures now create bounded, per-island backoff instead of indefinitely blocking every council. Repeated failures progressively wait longer, up to 30 minutes. Unknown external outcomes and integrity failures retain conservative handling.
- **B3 — Local admission:** a full request queue, exhausted local daily allowance or unavailable admission ledger becomes a saved deferral with a retry time. These local conditions are distinct from Google errors.
- **B4 — Restart recovery:** council turns persist queue-wait, dispatching, response-received and applying boundaries. Undispatched work can recover; a saved response is reused; a genuinely uncertain dispatch is not automatically purchased again.

Live diagnosis also found a council stopped by **The bounded council context is full**. The accumulated observation was about 46,000 characters before recalled evidence, leaving insufficient room under the 48,000-character guard. A read-only check of that same current island produced 34,683 characters after repair, retaining all four conversation messages and leaving 13,317 characters under the maximum. Context compaction now removes duplicated metadata and optional older history while preserving action constraints, tool schemas and real conversation. Omitted context is disclosed; it does not delete island memory or promote unsupported findings. The same bound is applied after recall and immediately before dispatch.

## Provider controls

- **B1 — Evaluation pause:** recognition evaluation, improvement and reference/embedding paths recheck pause, cancellation and deadlines after waiting for admission. A pause during a queue wait prevents the fake SDK invocation in regression tests. Local guard errors are not labelled Google failures. A second pause check also closes the race while an admission transaction is in flight.
- **B2 — Durable request budget:** the shared `providerAdmission` record stores atomic reservations across models and request categories. Restart does not replenish the rolling allowance. Failed or uncertain requests remain conservatively charged. Storage uncertainty prevents new dispatch. The UI distinguishes saved application limits from Google quotas. The saved request pace is checked inside admission, so a stale worker cannot bypass Slow.
- The first migration can only preserve known prior usage. Known process usage is carried forward conservatively; unrecorded history remains explicitly unknown until a complete 24-hour window has elapsed. This ledger does not observe other applications using the Google account.

## Recognition diagnosis and repair

Two recent microphone captures completed on the backend after approximately **268 and 337 seconds**. The old browser stopped waiting after **125 seconds**. This explains those apparent failures; it is not a claim that every reported recognition error had that cause.

YOLO and OCR were already enabled and loaded. The installed YOLO11n detector has 80 classes and does **not** include microphone. A local bundled bus-image smoke test detected bus and people without a Gemini call.

The evidence path is:

1. YOLO offers local detections for its supported vocabulary; OCR reads visible text.
2. YOLO, OCR and Gemini inspect the same selected image region.
3. Gemini interprets broader identity and attributes using the image and supporting evidence. Detector disagreement remains visible; no detector score becomes a verified identity claim.
4. Human confirmation or correction remains the final gate before accepting a fighter.

The review now shows compatible labels, differing labels, multiple candidates, no detection, or unavailable evidence, together with class-coverage limits. Capture requests wait for a bounded ten minutes and show elapsed time. On connection failure, one read-only GET checks the same capture; the browser does not automatically repeat the paid POST. Known failed captures are distinguished from queued work. An explicit retry of an eligible failed capture returns it to processing. Standalone recognition no longer automatically retries an uncertain timeout or gateway outcome.

## Frontend repairs

| Finding | Result |
| --- | --- |
| F1 — Late review response | Superseded job requests are cancelled and generation-checked. Matching detail and comparisons publish together. Same-job polling preserves the review form and preview instance. Mutations are guarded against a mismatched selection. |
| F2 — Blinded labels | Candidate labels stay hidden until valid comparison data has loaded and required pairs are reviewed. An empty candidate pair list does not count as a completed review. |
| F3 — Navigation | Islands, original island and Quality Lab have stable hash routes. Reload, Back, Forward and closing the view agree with the displayed page. Outstanding round callbacks cannot overwrite a newer route. |
| F4 — Observatory freshness | Metrics are tied to the selected island. Failed requests clear unavailable data and show a warning. The event-stream status no longer claims every data source is healthy; load timestamps are separate. |
| F5 — Reduced motion | The global motion preference is respected, with decorative battle rings, particles, swipes, crown travel and hit-word transforms suppressed or simplified. |
| F6 — Evaluation visibility | Quality Lab shows the saved evaluation pause and disables provider-backed batch/preparation controls while paused or unavailable. Gameplay has separate controls. |

## Validation and activation

- Full backend suite: **426 passed, 2 skipped**, 110.51 seconds. The two opt-in Mongo integration tests remain skipped; eight existing dependency/deprecation warnings remain.
- Frontend: TypeScript/Vite production build passed. The separately loaded 3D scene still produces the existing approximately 1 MB raw chunk-size advisory.
- Combat, island scene/geometry, playground, receipt, image-input and new polish regressions passed. The new tests cover contradictory reports, request ownership, restarted/paused admissions, late review responses, blinded-label gates, capture recovery and independent polling. A separate isolated React browser regression verified that polling retains unfinished review input and does not duplicate render writes.
- Browser checks: Quality Lab reload, close, Back and Forward; island reload; discussion and Observatory rendering. This is not a physical webcam test.
- Backend activated on localhost after a graceful stop with no active/waiting provider requests. The prior process's **22 known requests** were conservatively seeded in Atlas before the new process started; the remaining daily allowance was **178 of 200** at the first read.
- Post-restart check: Atlas ready; Gemini gameplay enabled; **Slow, one request/minute**; **evaluation batches paused, zero evaluation jobs**; planner enabled and `auto_blocked=false`. Winner Island remained paused and Loser Island active, with four residents on each island. The old context-limit record remains in history; recovery applies the bounded cooldown before the next council.
- Automatic recovery was observed at **15:24:34 UTC**: a new Loser Island council started without a manual command. Frosty Gulp Jug reached `queue_wait` under Slow, with `auto_blocked=false` and no current planner/provider error. This confirms scheduling resumed; it is not a claim that a new contribution had already completed.
- YOLO and OCR remain enabled with local weights present. Their models load lazily for the next capture after restart.
- No explicit paid probe or evaluation batch was run for verification. Normal authorized gameplay may send subsequent requests on Slow.

## Remaining boundaries

These repairs do not establish accuracy on every photographed object. The physical MacBook camera and arbitrary new photos still require user-side checks. YOLO's class vocabulary remains finite; no new detector was trained or downloaded.

The camera battle still uses its existing v1 combat and persistent island placement. The fixture arena uses v2 attributes, sample prices and conditional weaknesses but does not admit practice fighters to live islands. The cinematic demo is scripted. Those product boundaries remain explicit.

The worker processes run on the local Mac; MongoDB stores durable state and coordinates reservations. In-memory regression tests do not substitute for a fresh Atlas failover or multi-process load test.

## Winner Island inactivity follow-up

The reported absence of Winner Island discussion had a saved-state cause: Winner Island was enabled but paused, with four residents. Paused islands are intentionally excluded from automatic councils. The island was resumed through the existing idempotent command API; all four residents have automatic assignments. Both islands are now enabled and unpaused. Gemini remains on Slow and evaluation batches remain paused (zero evaluation jobs).

A focused scheduler regression proves that resuming Winner Island does not interrupt the current six-turn Loser council, and the next automatic selection includes Winner Island while retaining at least 60 seconds between dispatches. The planner/recovery suites passed 37 tests. No scheduler behavior change or extra model probe was needed.

The UI now distinguishes island pause, Gemini pause, another island's council, provider admission, retry cooldown and unavailable state. The Discussion view exposes the existing island Resume action. A bounded event window no longer claims that a crew has never recorded activity; displayed event summaries have timestamps. Current control state is explicitly separate from replayed events.

Read-only verification at 15:31 UTC found Winner Island ticking and saving rest receipts. Its supplies were stocked and no unfinished project had yet been agreed. These receipts correctly record zero resource or construction gain. The Loser council was on its third turn; this check establishes resumed local execution and council eligibility, not a completed new Winner conversation.

The already-open Observatory tab also showed stale history despite a connected label. A reload recovered current records. Independent probes verified both backend and Vite streams replayed the correct retained events and delivered new events; no backend stream fault was reproduced. Browser event recovery is addressed separately from the island's saved pause.

Browser recovery now reconciles saved events every 15 seconds from its latest cursor without overlapping reads. A stream is labelled live only after an actual event or status heartbeat; 30 seconds of silence triggers one reconnect attempt per silent period while HTTP catch-up continues. Duplicate events are merged, stale callbacks are ignored and requests are cancelled when leaving the view. Fake-clock tests cover silent streams, racing cursor updates, failed reads and cleanup. Browser verification observed new Winner receipts arrive without another reload and the connection return to live.

Validation for this follow-up: 37 planner/recovery tests, all seven `test:polish` scripts (including actual conversation component rendering and event-feed recovery), and the TypeScript/Vite build passed. The existing 3D bundle-size advisory remains. No provider settings, evaluation controls, billing settings or credentials were changed.
