# Sketch Clash architecture and quality policy

## Product and the two loops

Research question: **Can human feedback help AI create more reliable and useful digital representations of real-world objects?** Players should get fewer wrong fighters and representations they want to keep; the creator should gain a repeatable way to investigate and compare changes. These are intended benefits, not measured outcomes yet. Feedback storage, retrieval and prompt changes do not train Gemini’s weights.

The live path remains:

**Capture → YOLO/OCR evidence → references where enabled → Gemini proposal → application validation → player review/correction → confirmation → recorded battle → normal island persistence.**

The independent improvement path is:

**Consented feedback → operator review → grouped case revisions → frozen dataset/policy → baseline evaluation → one bounded candidate → independent final evaluation → actual render checks and human comparison → operator activation or rejection.**

The game never waits for an optimisation batch. Evaluation uses the same recognition/validation components through a service boundary that disables catalogue persistence and never calls battle, unlock, encounter or island mutation methods. The preview component has no gameplay API writes.

## Interface and the real object

The paper-and-ink identity is retained with softer mint/coral accents, consistent spacing and controls, a live illustrative landing character, a focused capture desk and a calmer island interface. The landing specimen is explicitly illustrative. Its larger presentation camera is not used for A/B verification.

Browser normalization orients once, strips metadata, flattens transparency and produces a JPEG bounded to 1,600 pixels. Backend decoding independently checks supported JPEG/PNG/WebP content, MIME, 5 MiB upload and 24 MP pixel limits. Crop coordinates address the canonical oriented image. Accepted crops are immutable content-hashed media. Late responses cannot replace a newer capture. The original selected photograph stays visible beside the character and in battle artwork.

The player sees **Correct / Correct it / Not sure**, plus separate optional **Keep / Change details** controls. Creative reasons cover resemblance, colour/proportions, name, style/accessory and rendering/animation defects. A concise factual label is validated server-side and re-examined against the image. A label correction is not ground truth. The original proposal and parent-output lineage remain recorded, with at most two correction attempts before selection/retake. Style correction preserves factual identity, approved template, archetype and fixed stats.

Feedback records reference the exact `output_id` and `pipeline_version_id` shown. Idempotency protects retries. Creative skip remains `skipped`, not a negative vote. Feedback is collected before the battle outcome. Failed persistence is visible and never called saved; the valid game can continue without feedback. Optional shared-evidence consent is unchecked by default and does not affect play.

Live and recovered review use the same private handoff. The creator entry is only on Home. Review queue access excludes open rounds. Player-one photos and feedback are not reused in player-two components. A returning object shows the regenerated battle proposal separately from the saved island resident: accepting a proposal does not replace that resident’s appearance.

## Recognition and fixed combat authority

Local YOLO11n supplies candidate boxes; EasyOCR reads the selected region. Missing/empty detector or OCR results do not automatically invalidate a photograph. Evidence availability, detector/OCR scores and model uncertainty stay distinct. OCR, player comments and reference text are untrusted data, never operational instructions.

Gemini 4 Argon uses the official Python SDK and Interactions API with medium thinking. The model proposes an observed object and separate fictional character interpretation. Resolver, schema, semantic appearance checks and deterministic simulation validate the proposal, with at most two configuration repairs. Successful validation does not prove recognition accuracy, aesthetic quality or competitive balance.

The server owns `draft → ready → running → completed`, cancellation/failure, confirmation, fixed fighter snapshots, seed, events, winner, duration and completion eligibility. The browser plays the recorded sequence. Normal/reduced modes last 12.8 seconds; quick mode lasts 6.4 seconds. Replaying a completed battle cannot grant duplicate effects. Failed completion retries the same battle rather than the model.

| Class | Health | Attack | Defence | Speed |
| --- | ---: | ---: | ---: | ---: |
| Quick | 100 | 16 | 2 | 3 |
| Power | 100 | 24 | 1 | 1 |
| Guard | 100 | 18 | 7 | 2 |

Hash-derived jitter is an integer from −3 to +3. Damage is `clamp((attack − defense + jitter) × 2, 16, 38)`, capped by remaining health. Higher speed starts; seed breaks equal speed. Turns alternate, with at most ten ordinary attacks and one decisive tiebreak. Creative feedback never rerolls strength or modifies an accepted battle.

Atomic completed battles unlock both valid participants, including the loser. One resident exists per world/canonical type. A repeated type updates distinct-battle history while preserving first appearance and home; same-type participants in one match count once. Scripted Watch the Showdown stays separate with no unlocks.

## Versioning and backward compatibility

`pipeline.py` registers the inspected system prompt/hash and bounded configuration as immutable `baseline-v1`. Initialization inserts the baseline and active pointer only if absent. It does not overwrite existing versions or game data. New battles pin the active version before either player prepares a fighter; retries and both players use that version.

Legacy records missing provenance read as `legacy-unknown`. Accepted fighters, events and residents remain unchanged. Legacy unfinished rounds may complete using the inspected baseline for new preparation without relabelling historical outputs. Feedback/correction requires the exact versioned proposal; historical unknown previews may continue or be retaken.

Candidate configuration is data, not executable code: fixed Argon model/medium thinking, bounded recognition and appearance guidance, balanced/conservative clarification and zero to three approved references. The initial baseline has zero visual references. Candidate changes are immutable and scoped to recognition or appearance; combat code, stats, renderer code and scoring policy are not candidate tools.

Activation compares both expected active version and pointer revision in a transaction. Stale approval cannot overwrite a newer adoption. The operator’s identity/reason and activation history are retained. Rollback is restricted to the baseline or previously active versions. Only future rounds see the changed pointer; existing battle versions and resident appearances remain stable.

## Storage responsibilities

| Collection | Responsibility |
| --- | --- |
| `characterTypes` | Stable canonical names/aliases, approved type mappings and optional catalogue description vectors. |
| `battles`, `captures` | Lifecycle, immutable captures/proposals, pinned version, correction lineage, confirmation and recorded outcomes. |
| `media` | Content-addressed normalized photographs, stored once. |
| `worlds`, `worldCharacters`, `encounters` | Shared world, unique resident/home/appearance/activity and distinct battle history. |
| `qualityFeedback` | Idempotent exact-output factual/creative feedback and shared-evidence permission. |
| `qualityReviews`, `qualityCases`, `qualityCaseRevisions` | Human provenance, expected outcomes, consent, grouping, roles, ambiguity and immutable case revisions. |
| `pipelineVersions`, `qualityState`, `qualityActivation` | Immutable configurations, active pointer and activation/rollback history. |
| `qualityJobs`, `qualityResults`, `qualityComparisons` | Frozen snapshots/policies, budgets/checkpoints, predictions/scores/render reports and separate blinded human preference. |
| `qualityReferenceVectors` | Explicitly prepared reviewed-image vectors with case revision and embedding provenance. |

Unique indexes, idempotent keys and transactions protect gameplay effects, feedback, jobs/results and version selection. Model calls and CPU vision work occur outside storage transactions. World reads are bounded, world-scoped and do not run recognition or create characters. The explicit memory adapter supports engineering tests; it is not a persistence fallback or evidence of Atlas transactions.

## Evidence, consent and splitting policy

Player acceptance, a player correction, developer review and disputed evidence are different provenance states. The operator must supply a reviewer name, timestamp/reason and explicit factual outcome: expected canonical identity, target, or insufficient evidence requiring clarification. Canonical aliases resolve through one identity function. Creative rubric fields—resemblance, visible-feature preservation, style fit and appeal—remain separate and contextual.

A case is reusable only when human approved, explicitly consented and not retired. The server refuses to manufacture photo permission where the player did not opt in. Unreviewed, disputed and reserved-final records never become live references. Conflicting reviewed labels are preserved as disputed, not silently overwritten as truth.

Roles are assigned before evaluation:

- **Reference:** approved examples available to inference when the pipeline enables them.
- **Development:** failures the optimiser may inspect to propose a change.
- **Reserved final:** independent evidence hidden from the optimiser until a frozen candidate is evaluated by a separate service.

All views of one physical object and capture session must use the same group and role. Exact hashes, shared sessions and perceptual near-duplicate checks flag conflicting grouping. Group uncertain cases conservatively; automatic similarity is a review signal, not proof of physical identity. A previously enrolled individual-object experiment is distinct from generalisation to unfamiliar objects and must be labelled accordingly.

Each job freezes case revisions, membership, references, baseline/configuration and policy. Its inference payload includes only image reference/hash/dimensions; expected identity, human correction, comments, filename and prior outputs are excluded. Each case gets an isolated model interaction. The optimiser sees development failures only. Reserved cases are claimed to a comparison; later revisions need fresh reserved groups rather than reuse disclosed final answers. Correcting the original photo is tracked as interaction repair, not independent generalisation.

## Two genuine retrieval boundaries

The existing catalogue keeps exact names/aliases first. Optional semantic catalogue search uses `gemini-embedding-2` description vectors with matching model, 768 dimensions and schema version. Similarity retrieves related types but cannot merge identity or establish ownership. The historical 21 description vectors are not a reviewed image evaluation corpus.

`ApprovedReferences` is a separate live visual adapter. Reference-image embedding is an explicit operator job, never a side effect of gameplay or opening the island. The official embedding API receives image bytes only; reference labels are returned later as explicitly approved context. Its separate index filters world, reference role, approval, consent and embedding provenance. Query logic excludes the current hash, excluded groups and every development/reserved group; authoritative current case/revision/media checks reject stale, withdrawn or disputed index rows after retrieval.

The adapter reports missing/not-ready/incompatible indexes, empty eligible sets and unavailable services explicitly. Empty/disabled/not-enrolled reference sets and missing indexes trigger no paid query embedding. The baseline’s reference limit remains zero until a reviewed passing change is activated. Frozen evaluations use their own approved snapshot rather than a mutable live-index lookup. Their selected reference IDs are logged.

## Bounded worker and improvement tool boundary

`quality_jobs.py` is one durable local worker; it currently runs requests sequentially. No broker or large framework is introduced. The policy’s concurrency ceiling is two, with actual concurrency one. Operator-triggered jobs support baseline evaluation, one-candidate improvement, and explicit reference preparation. Ineligible data yields Needs human review before paid evaluation.

Comparison ceilings: 60 total provider requests, 600,000 aggregate conservatively reserved tokens, 48,000 input and 4,096 output tokens per request, 600 seconds, at most 12 evaluation cases and three reference inputs. Smaller request budgets are supported. Reference preparation reserves one image request and 8,192 input tokens per selected case. Every retry, repair, embedding and agent call counts; uncertain or unfinished calls are not refunded.

The improvement agent can list reviewed development failures, retrieve approved reference metadata, propose a validated configuration, evaluate development inputs, compare those results and submit its single candidate. It cannot change reviewed labels, dataset roles, policy/thresholds, game code, arbitrary rendering code, approvals or the active pointer. Separate service logic freezes/submits the candidate and evaluates reserved cases.

Current requests are synchronous Interactions calls with `store=False`, fixed bounded output and medium thinking. The worker stores job progress, per-request usage/model metadata when available, checkpoints and unknown-outcome markers. A known unfinished checkpoint can resume; an interrupted external request with uncertain outcome is surfaced and is never blindly resubmitted. Cancellation stops scheduling; in-flight transport outcomes may remain uncertain and conservative reservations remain. Failed/cancelled/interrupted/over-budget jobs cannot activate a candidate. There is no claim of exact financial cost without verified price calculations.

## Independent scores and fixed adoption gate

`quality-policy-v1` is frozen into each job before inference. Results show actual counts and missing data; no combined unexplained “AI quality” score exists.

| Dimension | Recorded evidence |
| --- | --- |
| Recognition | Correct identity, wrong accepted identity, appropriate clarification, unnecessary clarification, answered/total coverage, latency and usage. |
| Creative | First-preview keep/change/skip and reasons; human contextual rubric; blinded random-order A/B preference, ties, neither and missing reviews. |
| Technical/game | Schema/semantic validity, fixed class/stats, supported visual parameters, actual rendered bounds/visibility/animation/load checks and persistence invariants. |

Activation requires a complete candidate comparison with at least three approved development cases, three fresh reserved cases and three reserved groups. Required factual/technical results must exist for both variants, actual fighter render reports must pass, all budgets/deadline checks must hold, and no unknown request/cancellation may remain. Wrong accepted identities and unnecessary clarification may not increase; coverage may not fall. Candidate aggregate latency may be at most twice baseline.

Recognition scope requires an increase in independently correct identities plus appropriate clarification. Appearance scope requires reviewed comparisons for all included cases, more candidate than baseline preferences and no neither-acceptable results. Ties remain valid records. Pending review or insufficient samples blocks activation. Even a passing small sample is marked provisional and requires a separate authorised human action. Thresholds are not adjusted to rescue a candidate.

## Shared renderer as a technical tool

`CharacterPreview` uses `CharacterShape` and the same supported animation functions as the island. It validates finite/ranged parameters, loads supported assets, checks actual scene bounds, mesh visibility and renderer draw activity, and exercises idle/rest/wander. Matching studio cameras and lighting support A/B review and standard-view captures. The landing hero has a distinct illustrative framing and never supplies evaluation evidence.

Procedural mug, bottle, plant, book, ball and generic photo-badge templates preserve supported palette, proportions and accessories. No generated executable code, external mesh service or arbitrary 3D reconstruction is involved. Actual browser execution establishes bounded technical validity, not resemblance or taste. Humans judge those. WebGL failure is recorded as unavailable; the collection fallback preserves usability without falsely passing verification.

## Local security, export and limitations

The server enforces a minimal operator gate for reviews, paid jobs, export, render reports and version actions. The default private token file has owner-only permissions and is ignored by Git; an optional environment override is available. The browser gets an eight-hour HTTP-only SameSite session cookie. A hidden link is not the gate. This local prototype is not designed for public hosting or multi-user accounts.

Keys and Atlas credentials stay in ignored local configuration. Operational records use IDs, stages, versions, error categories, timings and usage; no secrets, raw image bodies or opaque thought content belong in routine logs. Approved evidence stays in controlled media storage.

The operator export contains approved consented metadata, configuration/policy and selected run results, with sensitive/raw fields excluded. It omits raw media bytes and private gameplay feedback. A separate private Atlas backup including media and quality collections is required for full restoration; GitHub source history alone is not a data backup.

No human-reviewed dataset is currently sufficient to claim improvement. Education, accessibility, industrial and AR applications remain future possibilities requiring their own evaluations. Physical camera coverage, subjective creative reviews, final human activation and Atlas credit/billing checks require the owner. See HANDOVER for exact test scope and demo steps.

## Frozen retrieval during comparisons

Each comparison freezes the exact catalogue records/aliases and a digest of compatible embedding provenance and vectors. Its isolated recognizers cannot write catalogue records. When semantic lookup is needed, they execute the real Atlas Vector Search algorithm with a counted query embedding, and verify the vector corpus before and after the query. Corpus drift fails the comparison instead of silently changing its baseline. Reviewed visual references use their separately frozen case revisions and real filtered Atlas query; new enrolments are excluded and changed eligibility blocks the run.

An explicit human rejection is stored separately from immutable candidate configuration and blocks activation or rollback to that candidate. A group-level reserved-to-development transition preserves each case's labels and consent while recording new revisions and one immutable operator audit. Used final-group identities cannot return to reserved testing; ongoing jobs must finish or be cancelled before retirement.
