# Sketch Clash polish and codebase audit plan

The immediate change is a coherent object-based frontend: replace the cat and dinosaur with a pencil and mug, preserve the paper arcade theme, explain the battle-to-island journey, and verify the homepage and cinematic demo on desktop and mobile. Commit and push that work separately.

The audit then checks whether the existing game works reliably and makes truthful claims. It produces verified findings and an ordered repair plan before any broad repairs. New features, new agents, extra Gemini evaluation runs, billing changes and public deployment are outside this pass. Existing gameplay remains on Slow and evaluation batches remain paused.

## Audit sequence

1. **Establish the baseline.** Record the reviewed revision, tracked modules, runtime configuration status without secrets, test results and current build output. Run isolated fixture tests only; do not alter live islands to reproduce bugs.
2. **Check provider controls and security.** Trace key/config precedence, queue pacing, concurrency, pause enforcement, quota errors, retries, request budgets, operator authorization, upload limits and telemetry redaction. Verify what survives process restarts.
3. **Check MongoDB and recovery.** Trace battle finalization, island admission, world revisions, council state, execution receipts and indexes. Inspect atomicity, duplicate requests, crash recovery, stale writes and retained history. Distinguish in-memory test coverage from Atlas integration coverage.
4. **Check battle and recognition correctness.** Follow captures through recognition, human corrections, validation, object attributes, bounded price effects, conditional weaknesses, deterministic simulation, winner explanations and island placement. Keep fixtures distinct from live recognition and generated art.
5. **Check agent behavior and evidence.** Follow observation, discussion, proposals, experiments, agreement and execution. Verify capability limits, handling of missing resources/full storage, changes after new arrivals, learning provenance, actual contributions and receipt links. Identify contradictions between conversation and action.
6. **Check frontend usability and performance.** Review home, camera capture, object arena, islands, board, observatory, playground and quality tools. Test routing, error/loading/empty states, keyboard labels, motion, small-screen layout, polling, WebGL lifecycle and build size. Record areas that need a real camera or further device testing.
7. **Check delivery readiness.** Review dependency locks, scripts, documentation, ignored secrets, tests and demo instructions. Rank only actionable findings with evidence; do not treat every prototype shortcut as a release blocker.
8. **Scope live semantic analysis.** Assess whether existing public dialogue, structured intentions, experiments and execution receipts already support a clearer account of what agents mean and do. Prefer better presentation of existing evidence. Any extra classifier, embedding pipeline or model calls become a deferred proposal, not implementation.

## Finding standard

Each finding must state severity, a concrete trigger, observable impact, source location, and a reproduction or clearly bounded source-based proof. Separate confirmed defects from risks and unverified coverage gaps. Do not infer private model reasoning from dialogue or invent live results.

- **P0:** active data loss, credential exposure or an unusable core path requiring immediate containment.
- **P1:** reproducible correctness, persistence or spending-control defect that threatens the demo or trusted outcomes.
- **P2:** materially confusing UI, accessibility/performance issue, recovery edge case or maintainability weakness.
- **P3:** optional cleanup with limited immediate user impact.

## Repair plan deliverable

Create a consolidated report with the current architecture, coverage and limitations, prioritized findings, and sequenced repair batches. Each batch gets an acceptance check, expected effort and a focused commit boundary. Broad audit repairs wait for review of that plan; the requested frontend polish is the only implementation in this pass.

## Completion checks

- Cat/dinosaur promotional assets and demo presets are replaced; object recognition still supports legitimate animal inputs.
- The frontend builds and existing deterministic battle checks pass; desktop/mobile screenshots are inspected.
- Tests do not call paid providers or modify Atlas state; persistent evaluation pause is preserved.
- Findings are traceable to code and reproduce where practical.
- The final report explains what to fix first and what to defer, including the semantic-analysis idea.
- Frontend changes and audit documents are committed separately and pushed to the existing GitHub repository.
