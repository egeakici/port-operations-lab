# Step 6 closure compute and F3 — Phase A

`F3_BLOCKED_BY_OWNER_REVIEW`; K5-A is proposed, not approved. No F3 episode executed.

## Measured populations

Historical evidence is re-extracted by `scripts/audit_step6_closure_history.py`
into an immutable `experiments/step6_closure/phase_a/history_*.json`, with hashes
of every read historical record. No historical campaign is rerun.

| Population | n | Median seconds | P95 seconds | Maximum seconds | Mean seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pre-Step 6 A2, Heavy seed 10000000, all A2-driven decisions | 28 | 1.4827 | 9.5016 | 10.2759 | 2.5595 |
| Phase P A2, sparse A1-driven states across four families | 15 | 0.1329 | 1.6943 | 1.8648 | 0.3944 |
| Phase P shared B evaluator, same sparse states | 15 | 4.4530 | 53.9115 | 59.7490 | 15.2540 |

Pre-Step 6 records also cover all decisions in 12 primary A2 episodes, three
seeds per family; their per-run distributions are retained in the machine report.
Phase P samples ordinals 1/5/10/15/20 where present, seed 10000000 only: 2 Low,
4 Medium, 5 Heavy, 4 Bottleneck. These differ in trajectory, family/seed coverage
and sampling frame. The 1.86 s maximum is not an A2 bound. Historical A2 lacks
per-state cohort/branch records, so the exact slowest state's cause cannot be
identified. No matched-state retiming has been performed; load and warm-up
contributions remain unresolved. Pre-Step 6 P95 uses the runner's nearest-index
statistic; Phase P uses numpy's linear percentile. Do not pool these summaries
as raw observations or infer a global median from per-run medians.

Historical host: Windows 11 build 26300, Python 3.13.2, Intel64 Family 6 Model 186
Stepping 3, 12 logical CPUs, single process, uncontrolled concurrent load.
Package versions and Git provenance are in the underlying records. Imports,
checkpoint setup and trajectory driving were excluded from Phase P decision times.

**Timing clarification:** source `profile_compute` builds the projection before
calling `evaluate`; the 15.254 s evaluator mean excludes the separately timed
0.743 s mean projection build. The older “in the B2 time” wording is not supported
by those measurement boundaries. Combined mean is about 15.997 s before other
observation/selection overhead. Tracemalloc on Low also perturbs those timings;
its 6.6–10.5 MB is Python allocation peak, not total process RSS.

## Proposed campaign

### Phase A matched timing probe preregistration

Before executing this probe: Heavy development seed 10000000 only, primary QC8,
decision ordinals 1 and 5 reached independently under A1 and A2. Stop each driver
at ordinal 5; do not complete either episode. At each captured immutable BerthView,
run authentic A2 three times, recording each duration, selected action, scores,
view hash, cohort sizes and candidate counts. This is not F3 and does not run B2.
It measures repeatability on matched states; it cannot reconstruct the historical
slowest decision because that snapshot was not archived. Setup/trajectory time
is excluded and reported separately; no warm-up sample is discarded.

Heavy and yard-bottleneck × seeds 10000000/10000001 × A2/B2-T/B2 = 12 episodes.
All inputs are checksum-verified stored development scenarios, primary Balanced
Yard QC8, max two cranes/vessel, assigned efficiency, unchanged D15/D17/R5.
Historical A2 records are retained as context; fresh A2 episodes are planned
because old aggregate records do not contain every decision needed for this audit.
No historical F1/F2 plan is changed and no completed F3 run is duplicated.

Illustrative compute projection: 4 Heavy integrated episodes × 30 decisions ×
25.17 s plus 4 Bottleneck integrated episodes × 25 decisions × 22.35 s gives
about 87.6 minutes of evaluation, before projection, outer simulation, reporting
and four A2 episodes. Decision counts are assumptions, not observed F3 counts;
different outer trajectories may be much more expensive. No cross-arm cache exists.
Proposed cumulative admission allowance: 180 minutes, one worker, RSS check 4 GiB
before episodes. The controller measures CPU and RSS at episode boundaries;
it does not claim peak RSS or interrupt a healthy candidate to meet wall time.

`scripts/run_step6_closure.py --plan` writes an exclusive, content-addressed
plan and hash sidecar. `--dry-run` writes nothing; `--audit` is read-only.
`--run` and `--resume` refuse missing approvals before starting work; exact plan,
source/scenario digests, Q6 decisions, gate review, resource authorization and
scientific boundaries are required. Output installation is atomic and exclusive.
Completed records are checksum/metadata verified; failed or interrupted attempts
are never silently rerun. A stale worker lock or started-without-result marker
requires operator inspection. No resume has been attempted on real F3 data.

The closure runner opts into additive per-decision sanitized resource snapshots,
and retains full policy records plus reporter-only ledger/events/blocking evidence.
Three fixture regressions verify identical actions, traces and B predictions with
capture enabled. Historical records remain unchanged and lack these new fields.
Phase B must review the gate evidence and approval linkage before its first episode;
actual F3 event-grounded diagnostics cannot exist before those episodes run.

## Phase A timing result and current proposal

The preregistered matched probe is now complete; it supersedes the earlier
"No matched-state retiming" statement above. Evidence:
`experiments/step6_closure/phase_a/a2_probe_ee8e2d0685ed.json`.
Four captured states, three authentic A2 evaluations each, zero completed
episodes, zero B2 calls. Total probe wall time was 1.811 s, including drivers.
First-state hashes match across A1/A2 trajectories (2 revealed/nondeparted,
2 legal assignments plus WAIT); call times range 0.000912–0.002404 s.
Fifth-state hashes differ: A1-driven t=433.114677, A2-driven t=433.245062;
both have 15 revealed, 14 nondeparted and 6 legal assignments plus WAIT.
A2 selects action 193 on the A1-driven view and WAIT on its own trajectory.
Fifth-state call times range 0.208084–0.215197 s. Every repeat on each state
has identical scores and action. No warm-up sample was removed. Concurrent
regression load was uncontrolled; this small probe cannot identify the missing
historical 10.28-second state or attribute its runtime to a unique mechanism.

Current proposal SHA-256:
`1c97b83d5d5537bc95b6285795a521ffd01cbfdae580fcbbcd4701c811bd43bf`.
Plan: `experiments/step6_closure/1c97b83d5d55/plan.json` with file/canonical
hash sidecar. Earlier proposal directories remain historical drafts, superseded
after controller source hardening; none contains an executed F3 episode.
All 12 cells are blocked by owner review: 6 Heavy and 6 Bottleneck; each family
has seeds 10000000/10000001 and all three arms. Authorized/completed/failed/reused
F3 episodes: 0/0/0/0. F3 compute wall time: 0. No real F3 resume is needed or
authorized. Run/resume denial was exercised without creating episode artifacts.

Progress checkpoints emit coverage for each family/seed/arm, counts, timestamp,
elapsed invocation time and throughput/remaining-time estimates from the latest
three completed runs only. Before a completion the estimate is null. Checkpoints
occur at episode boundaries; there is no asynchronous in-candidate heartbeat or
peak-RSS monitor. `--report` marks interrupted attempts explicitly. Recovery
requires inspection of immutable records, checksums, worker lock and started
markers; the controller never silently repeats an incomplete/failed episode.

After explicit approval, append the owner response and amendment lineage, verify
the reviewed gate, and rerun cheap source/plan/readiness checks before execution.
If those authorized governance changes affect hashed source/configuration,
publish a new linked plan and bind the actual approval record to that plan;
never replace this proposal or pretend a different hash was approved.

Approval enforcement also binds the review to the actual immutable degenerate
gate artifact and its canonical digest, and rejects missing/tampered evidence.
The final readiness run passed 44 tests (21 closure, 23 existing coordination).
The fixture-only approval test writes to pytest temporary storage; it does not
create the real owner approval file or approve any Q6 item.

The final optional capture also archives the exact policy observation as base64
pickle bytes. B2's archive includes its existing sanitized SafeProjection; A2's
archive is the BerthView it actually receives. Current resource summaries remain
separate. Replays must use locally generated, checksum-verified trusted artifacts
with the recorded source/runtime. No live kernel or unrevealed catalog is archived
as a policy input. This enables later common-input replay without reconstructing
an approximation from resource summaries. Serialization/reporting contributes to
outer wall cost, not an inner candidate budget. The archive addition passed all
44 focused/coordination tests in 6.90 s. The previous `c216e611ab9a` proposal is
retained as a superseded draft; it has no F3 episodes.

Persistent fixture verification subsequently passed 47 focused/coordination
tests in 11.68 s, including three real controller write/reload tests on hand-made
fixtures. This verifies JSON serialization of ledger/events/input archives;
it is not execution of the F3 plan and introduces no production source change.

The original opt-in Project I regression command completed after approximately
4923.27 s measured by log-file lifetime. Pytest teardown lost its normal summary
to WinError 5. Exact progress reconstruction records 443 passes, 19 errors,
0 failed assertions and 0 skips; all 9 slow tests passed, including the 80/400
gates. All affected non-slow nodes pass in the separate normal-access retry.
The main Phase A report documents this limitation and recovery; the original
command is not called a clean full-suite pass. These costs are regression costs,
not F3 campaign execution. F3 remains 0/12 with zero campaign runtime.

## Explicit owner approval and revision preflight — 2026-10-14

The owner has explicitly approved all four Q6 decisions, K5-A and the stated
12-run/one-worker/180-minute/4-GiB admission scope. This supersedes earlier
Q6-pending statements. Verbatim immutable provenance and AM-10 are linked from
`step6_closure_owner_decisions.md`.

Execution stopped before admission because the approved plan hash
`1c97b83d5d5537bc95b6285795a521ffd01cbfdae580fcbbcd4701c811bd43bf`
binds HEAD `76ced62`, while current HEAD is `38a4f5c` after the owner's Phase A
commits. The only changed plan field is `git_head`; all 137 source/config hashes,
scenario and physics fingerprints, packages, resources and gate evidence match.
The read-only checkpoint/boundary audit passes with 28 pending parameters.

Replacement plan SHA-256, **not yet approved**:
`6401af0e2a01f875d3d5d24b0db1ed25a7f2955ae8ed92645081dc1366c97f20`.
Plan: `experiments/step6_closure/6401af0e2a01/plan.json`.
Linked comparison: `experiments/step6_closure/6401af0e2a01/review_b63512293001.json`.
No automatic approval transfer, run/resume, episode admission or new F3
diagnostic computation occurred. Current status is `F3_BLOCKED_REVISION_REVIEW`,
0/12 started or completed, zero campaign runtime. Only approval of the replacement
SHA is requested; the recorded Q6 decisions and resource scope need not be repeated.

## Replacement-plan execution update — 2026-10-14

The owner explicitly approved `6401af0e2a01...`; the earlier revision-review
block is superseded. Active approval canonical SHA is
`ef4dc4463d108c31e3013e6361388aabc89e7e5c7b94b9ffaef89bad01af9118`.
Preflight passed all source/config/scenario/gate/checkpoint and scientific
boundary checks. F3 is RUNNING, one worker, 180-minute admission budget, 4096 MiB
RSS admission check. Live checkpoints, exclusive run records and roughly
45-second process-RSS telemetry are under
`experiments/step6_closure/6401af0e2a01/`. Telemetry is sampled memory, not peak RSS.
No completed outer run or Phase A test will be repeated without a demonstrated
failure. New reporter arithmetic tests (5 passed) and real-record integrity
checks are separate from the preserved Phase A regression campaign.

## F3 completed — final resource accounting, 2026-10-14

**12/12 completed; 0 failed, reused, missing or duplicated outer episodes.**
Campaign elapsed at the final checkpoint: **67.848 min**. Episode wrapper-wall
sum: 63.307 min; CPU sum: 61.089 min. Result serialization/checksum overhead
accounts for the distinction from the admission clock. Post-run diagnostic
analysis took 475.105 s (7.918 min), including eight new selected-input probes.
Both phases remained within the approved allowance; no budget extension,
healthy-episode interruption, cohort cap, timeout fallback or policy substitution.

Maximum episode-boundary RSS was 675.277 MiB; maximum roughly 45-second telemetry
sample was 729.203 MiB. These are not peak-memory measurements. One worker was
used; the outer worker finished before any private-model diagnostic replay.
No worker lock or started-without-result attempt remains. All records and sidecars
verify; resume would skip verified completions rather than rerun them.

Authoritative owner report: [step6_closure_final_report.md](step6_closure_final_report.md).
Machine report canonical SHA:
`b745793420a7f48db7a9ebec1100ee7e1a401e24811451c1021b3ae8f1a5a9b9`.
Final review provenance: `experiments/step6_closure/6401af0e2a01/reports/final_review_manifest.json`.
The prior F1/F2 campaign, drafts, approvals and Phase A results remain unchanged.
