# Project04 consolidated development completion report

Date: 2026-11-10 Europe/Istanbul. HEAD `b5cdcc82d3ef8e920e8d16d490570034109d9435`, branch `main`.

**IMPLEMENTATION_PARTIAL_BLOCKED.** All fourteen specifications were processed
sequentially; safe independent fixture engineering continued past dependency and
primary-science gates as explicitly allowed by the master. No scientific closure
or owner approval was fabricated. No commit/push/stage was performed.

## Acceptance and actual evidence

| Adim | Durum | Son tam regresyonda kanit | Engel |
| --- | --- | --- | --- |
| 01 | REUSED_VERIFIED | 56 kaynak hash kontrolu | - |
| 02 | PASS | 22 passed / 0 skipped | - |
| 03 | PASS | 10 passed / 0 skipped | - |
| 04 | PASS | 12 passed / 0 skipped | - |
| 05 | PASS | 6 passed / 0 skipped | - |
| 06 | PARTIAL_BLOCKED | 3 passed / 1 skipped | ORTOOLS_DEPENDENCY_PENDING |
| 07 | PASS | 3 passed / 0 skipped | - |
| 08 | PASS | 4 passed / 0 skipped | - |
| 09 | PASS | 8 passed / 0 skipped | - |
| 10 | PASS | 3 passed / 0 skipped | - |
| 11 | PASS | 5 passed / 0 skipped | - |
| 12 | PASS | 3 passed / 0 skipped | - |
| 13 | PASS | 6 passed / 0 skipped | - |
| 14 | PARTIAL_BLOCKED | Tam paket: 89 passed / 1 skipped | FINAL_SOURCE_TESTS_PASS_WITH_ONE_DEPENDENCY_SKIP; PRIMARY_PROFILE_OWNER_APPROVAL_PENDING |

The latest final run executed `90` Project04 tests in
22.851 seconds: 89 passed, one actual OR-Tools
test skipped, zero failed/errors. Ten real module CLI commands returned zero;
solver check truthfully reports DEPENDENCY_PENDING. Step-local attempts are
immutable, including failed Windows temp setup, checker and JSON scalar attempts.
Pointer JSON files identify latest attempts. Final regression supersedes earlier
source snapshots for current-code integration verification; old receipts remain.

## Delivered engineering

- Immutable strict DTOs, canonical JSON/hashes, units/frames and explicit null physics.
- Counter-SHA256 named-stream generator, split/identity guards, bounded fixtures and separately guarded manual generation.
- Constant-speed reference-point kernel, shared legality and independent union-of-knots safety verifier; original tasks conserved.
- Four deterministic heuristic arms, independently verified metrics and JSON/CSV pairing.
- Bounded finite-event CP-SAT source plus truthful dependency/finite-subclass/optimality boundaries. OR-Tools execution NOT verified.
- Real Gymnasium API, normalized stable tensors, exact oracle masks, finite WAIT/failure handling and elapsed-time reward tests.
- New crane MaskablePPO tooling, actual untrained masked inference/save/reload, corruption/version checks, validation-only selection source and optimizer-boundary resume source. **No learn() call or research checkpoint.**
- Guarded immutable-cell evaluation/resume, scenario-first seed nesting, paired inference/multiplicity helpers and empty-evidence report generation.
- Streamlit read-only Gantt/rail slider/comparison/failure UI with actual AppTest and PNG render. The local fixture Gantt was visually inspected.
- Synthetic-only one-way adapter, stale-plan rejection and isolated execution conservation. No legacy kernel mutation/native terminal integration.

Source layout and versions: see ../ARCHITECTURE.md and FINAL_STATUS.json.
Full exact file inventory is CHANGED_FILES.json; integrity hashes are in
ARTIFACT_INTEGRITY.json. Experiments, smoke models, caches and environments are
excluded from this source handoff inventory and remain local/ignored.

## Preservation and scientific limits

All 656 protected tracked files from Projects01/02/03/I are
byte-identical to preflight. The original eight Step01 contract documents/manifest
remain byte-identical; only its README was authorizedly updated for current status.
The original root Step01 prompt is now absent, but its package copy is byte-identical
to the historical recorded hash. All 16 packaged prompt files match their manifest.
No old suite, original 1,960 campaign rerun, PPO checkpoint inference or raw held-out
archive verification was performed. This is not a fresh audit of ignored gigabytes.

Project I current pointer still says FINAL_CLOSED=NO, 1,960 Step7 episodes complete,
4,320 new diagnostic cells pending. B2 remains model-based cargo-first coordination,
not a new RL model. No real AIS/TOS/ship stowage calibration or terminal benefit.

Supported physics/actions are proposed fixture reference-point constant-speed
immediate dispatch. Joint yielding, acceleration/body envelopes, dynamic readiness,
multi-vessel QCAP and joint berth/crane/yard learning are outside implemented v1.
Detailed scientific profile, sample sizes, seeds, budgets and inference decisions
remain unapproved. Simple masks do not make unrestricted offline motion solvable.
CP finite-subclass OPTIMAL would not imply global continuous optimality.

Managed Windows AppTest/import cleanup emits a temporary-directory permission
warning after test assertions; it is retained in stderr, not excluded. The raw
Gymnasium checker requires an explicit legal reset-action sampler for a masked
invalid-action-truncation environment; step semantics/assertions were not weakened.

## Next owner actions and manual commands

Review OWNER_DECISIONS.md once (O1-O6), verify OR-Tools in an isolated approved
Python environment, then approve exact canonical source/config/cohort payloads.
Commands, guards, inputs/outputs and interruption/resume limits are fully specified
in ../MANUAL_EXECUTION.md. Long operations were **not** executed as code tests.
No exact runtime is promised. Empty evidence report states NOT_YET_RUN and cannot
claim success, model improvement or SCIENTIFICALLY_CLOSED.

Safe checks already verified:

```powershell
$env:PYTHONPATH = (Resolve-Path .\04-rail-crane-scheduler\src).Path
python -B -m rail_crane_scheduler training --mode check
python -B -m rail_crane_scheduler solver --mode check
python -B -m rail_crane_scheduler evaluation --mode status
python -B 04-rail-crane-scheduler/scripts/check_stage.py 14
```

## One owner-reviewed commit plan

Root .gitignore still excludes Project04. Existing Step01 files are already tracked;
new source/tests/docs are ignored. Do not force-add the whole directory. First
review allowing the project source while keeping its local experiments/models/
caches/environments ignored, then stage only reviewed source/docs/config/test paths.
Suggested single message: `feat: add Project 04 fixture-tested QCSP research tooling`.
No commit/push or root ignore edit was performed. See CONTINUATION.md only for
remaining owner/dependency gates; no hidden background task will finish them.
