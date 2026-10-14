# Project I Step 6 Closure — Phase A owner review

Development characterization only. F3 is `BLOCKED_BY_OWNER_REVIEW`.
No Q6 approval is inferred from the instruction to continue until completion.

## 1. Revision and worktree

Starting and ending HEAD: `76ced62b94e5419fea98933b3cb17debf1bd8a62`.
Already present: `48d2956` (coordination policies), `cfc93d6` (isolation tests),
`76ced62` (cost/diagnostics documentation). No automatic commit or staging.

The only modified pre-existing tracked file is
`src/integrated_terminal_pilot/benchmark/runner.py` (optional sanitized snapshots).
Added: `benchmark/closure_gate.py`, `benchmark/step6_closure.py`,
`scripts/run_step6_closure.py`, `scripts/audit_step6_closure_history.py`,
`scripts/probe_step6_closure_a2.py`, `scripts/report_step6_closure.py`,
`tests/step6_closure_support.py`, `tests/unit/test_step6_closure.py`, and the five
`docs/step6_closure_*.md` reports. Generated evidence is under the new ignored
`experiments/step6_closure/` namespace. The owner's root prompt remains untracked.

Projects 01–03, checkpoints, existing policies/configuration, original F1/F2
artifacts and the 8-crane Balanced Yard profile are preserved. The machine report
verifies all 31 historical inputs used in this audit against their captured hashes.
Authentic P03 A2 and existing B policy/view source match HEAD (Git CRLF checkout
normalization is stated explicitly where applicable).

## 2. Owner decisions

All four are `PENDING_EXPLICIT_OWNER_APPROVAL`; no signature/date/amendment has
been recorded. Exact contracts and alternatives are in
`step6_closure_owner_decisions.md`:

* Q6-1: accept the existing B1 v1 sequential-flow release estimator and tie-break.
* Q6-2: accept omission of future gate-in/pickup requests, continuing observed
  requests, with `UNCALIBRATED_SYNTHETIC_FORECAST` on predictions.
* Q6-3: K5-A full visible cohort, all legal + WAIT candidates, no cap/fallback;
  supersede the proposed 2-second reduction trigger with a reported warning.
* Q6-4: accept the existing nondeparted visible cohort, common drain horizon,
  censored turnaround, status-based unfulfilled cargo and selector-specific WAIT branches.

The requested F3 resource authorization is one worker, a 180-minute cumulative
admission budget and a 4 GiB RSS admission check. These are proposed resources,
not a peak-memory guarantee or a hard episode timeout. Healthy inner candidates
and episodes are never truncated to meet a wall-time target.

## 3. Independent contract gate

`PASS_WITH_SCOPED_CLAIMS`: 12 FULL fixtures, 0 PREFIX, 20 eligible decisions,
5 noneligible controls, 0 contract defects. The preregistered proof is
`turnaround(a) = future_wait(a) + K` for uncensored fixed-service branches, where
K is candidate independent. All candidate orders, ties, choices and WAIT
subbranches agree under these conditions. Two hand-calculated cases provide an
additional oracle. B predictions are independently simulated, never replaced
by P03 reference scores.

Crane-rate mismatch, distance-dependent service, censoring and unavailable
export/transshipment fail the applicability predicate. Censoring demonstrates
an actual action divergence: A2 assignment versus B2-T WAIT after integrated
scores tie. No performance-oriented repair was made. The full proof, negative
mechanisms and evidence hash are in `step6_closure_contract_gate.md`.

## 4. Algorithm changes

A2, B2, B2-T, B1 and physical/observation policies are unchanged. No demonstrated
existing-specification algorithm defect required repair. The runner's optional
diagnostic observer stores sanitized current resources and returns the original
policy observation. Default execution remains unchanged. Capture/plain tests
preserve action/trace/prediction digests for A2, B2 and B2-T.

## 5. Computation

Heavy A2 historical all-decision sample: n=28, p50=1.4827 s, p95=9.5016 s,
max=10.2759 s, mean=2.5595 s. Phase P sparse A1-driven sample: n=15 across four
families, p50=0.1329 s, p95=1.6943 s, max=1.8648 s, mean=0.3944 s.
The sampling frames and trajectories differ; 1.86 s is not an A2 bound.

A development-only probe captured ordinals 1/5 on independent A1/A2 trajectories,
evaluated each state three times, and completed no episode. First-state hashes
match; fifth-state hashes and A2 actions differ. Repeated scores/actions match
on every captured state. Fifth-state call costs are 0.2081–0.2152 s. The absent
historical 10.28-second snapshot prevents unique runtime attribution.

Phase P B evaluator mean=15.254 s excludes projection build mean=0.743 s;
combined about 15.997 s before further overhead. The historical wording that
projection was included is qualified additively. The illustrative F3 estimate
is about 87.6 minutes of B evaluation plus projection/simulation/reporting and
four A2 episodes, with substantial unquantified trajectory uncertainty.
See `step6_closure_compute_and_f3.md` for timing boundaries, host and resources.

## 6. F3 coverage and recovery

Plan SHA-256:
`1c97b83d5d5537bc95b6285795a521ffd01cbfdae580fcbbcd4701c811bd43bf`.
Artifact: `experiments/step6_closure/1c97b83d5d55/plan.json` plus hash sidecar.

| Family | Seed | A2 | B2-T | B2 |
| --- | ---: | --- | --- | --- |
| Heavy | 10000000 | BLOCKED | BLOCKED | BLOCKED |
| Heavy | 10000001 | BLOCKED | BLOCKED | BLOCKED |
| Yard bottleneck | 10000000 | BLOCKED | BLOCKED | BLOCKED |
| Yard bottleneck | 10000001 | BLOCKED | BLOCKED | BLOCKED |

Planned=12, authorized=0, completed=0, failed=0, reused=0, blocked=12;
F3 runtime=0. Earlier drafts are retained without episodes. Run/resume paths
reject absent approval. A future run requires exact plan/source/scenario and
reviewed-gate hashes, owner provenance, scientific-boundary and resource checks.
No actual F3 recovery is pending. On interruption inspect the lock/started marker
and immutable records; never remove evidence or silently repeat an incomplete run.
Progress ETA is null until completed-run evidence exists.

## 7. WAIT, cargo and forecasts

The four historical Medium WAITs last 42.588, 64.069, 171.061 and 263.016 minutes
until the next actual decision. Their prediction errors are −865.857, −143.334,
+32.840 and −92.969 vessel-min. One precedes an unannounced vessel; the other
three show error without later hidden entrants. No unique causal explanation
or WAIT-only decomposition of the Medium performance gap follows.

Low/Medium: 29 unique B2 decisions, zero candidate sets with predicted cargo
differences, zero cargo-pivotal selections. Corresponding B2-T prediction records
match; historical full input bytes were not stored. Mean signed turnaround
prediction errors are −189.4 and −320.5 vessel-min for the documented same cohorts.
Heavy/Bottleneck pivotal/calibration evidence remains NOT_RUN pending F3.

Historic Heavy A1n/B1 shortfall=92/6989 outbound containers (1.3164%);
Bottleneck=255/4850 (5.2577%), both recorded as D17 rollover. A1 has zero shortfall
in those records. Low/Medium have zero shortfall. N_out=loaded+U reconciles.
Ledger-derived status summaries support these counts, while unique causes remain
`UNKNOWN_OR_MULTIPLE_CONSTRAINTS`. No fresh historical event replay is claimed.
Details and four WAIT autopsies are in `step6_closure_diagnostics.md`.

## 8. Scientific fairness

Each prehashed development scenario fixes source/exogenous/resolved physics,
comparison fingerprint, N_out and T_end for all three arms. The primary profile
remains QC8, max two cranes/vessel, assigned efficiency and unchanged D15/D17/R5.
Existing matched-view evaluator, hidden-future adversarial and no-live-kernel
tests are included in the 44-test readiness run. Fixture capture/repetition
digests are stable. No F3 repetition or paired outcome is asserted before runs.

F3 with two seeds/family will support descriptive development diagnostics only.
No policy winner, S2 success, primary CARGO-NI inference, forecast calibration or
outcome-driven tuning is authorized.

## 9. Tests and preserved evidence

Final readiness: 44 passed in 6.49 s (21 closure + 23 existing coordination).
Projects 01/02: 426 passed in 20.15 s / 55 passed in 0.54 s. Project 03 selected
read-only suite: 423 passed, 5 deselected in 98.82 s; training and historical
results/benchmark integration modules were excluded. This is not a full P03 pass.

Project I full opt-in run and current-source non-slow run are still RUNNING at
this report's initial write. No full-suite PASS is claimed at this point.
The initial sandbox denied two pytest temporary fixtures; normal-access retries
are logged separately. Full opt-in run intentionally includes the 80-case Step 4
and 400-case Step 5 gates. Its final outcome will be appended without repeating
successful expensive cases. Historical reports independently retain 80/80 and
400/400 (383 FULL, 17 PREFIX); those historical counts are not substituted for
the running regression result.

Commands/logs live in `experiments/step6_closure/phase_a/`; pytest cache and bytecode
writes were disabled. `git diff --check` passes. The read-only audit reports all
six checkpoint hashes unchanged and 28 parameter records still pending.

## 10. Current scientific status

```text
STEP6_CLOSURE_CODE              = PHASE_A_IMPLEMENTED; FINAL_REGRESSION_PENDING
OWNER_Q6_DECISIONS              = PROPOSED_NEEDS_OWNER_APPROVAL
A2_B2T_DEGENERATE_CONTRACT_GATE = PASS_SCOPED
K5_FIXED_BUDGET                 = PROPOSED_FULL_COHORT_NEEDS_OWNER_REVIEW
F3_DEVELOPMENT                  = BLOCKED_BY_OWNER_REVIEW (0/12)
HIDDEN_FUTURE_GATE              = PASS (readiness tests)
PENDING_PARAMETER_RECORDS       = 28
SCIENTIFIC_PROTOCOL_LOCK        = BLOCKED
VALIDATION_AUTHORIZED           = NO
STEP7_STARTED                   = NO
```

## 11. Owner follow-up

Explicitly approve or revise Q6-1 through Q6-4 and the identified bounded F3
proposal. This approval is required by the owner's closure prompt, sections
10–11 and 19; the instruction to continue work does not supply those decisions.
After approval, append actual provenance and complete readiness checks before
starting F3. The 28 pending records and formal Step 7 lock remain separate
scientific blockers. No validation, held-out access, PPO retraining or Step 7
authorization is included in this request.

## Reproduction commands and test exclusions

From the repository root (all Python commands used
`PYTHONDONTWRITEBYTECODE=1`; pytest also used `-p no:cacheprovider`):

```powershell
$env:ITP_RUN_SLOW='1'
python -m pytest integrated-terminal-pilot/tests -q -p no:cacheprovider --basetemp=integrated-terminal-pilot/experiments/step6_closure/phase_a/pytest_tmp
# Separate current-source retry, normal temporary-file access:
python -m pytest integrated-terminal-pilot/tests -q -m 'not slow' -p no:cacheprovider
python -m pytest integrated-terminal-pilot/tests/unit/test_step6_closure.py integrated-terminal-pilot/tests/unit/test_step6_coordination.py -q -p no:cacheprovider
python integrated-terminal-pilot/scripts/run_step6_closure.py --report --plan-file integrated-terminal-pilot/experiments/step6_closure/1c97b83d5d55/plan.json
python integrated-terminal-pilot/scripts/report_step6_closure.py --plan-file integrated-terminal-pilot/experiments/step6_closure/1c97b83d5d55/plan.json
```

Projects 01/02 used `python -m pytest tests -q -p no:cacheprovider` in each
project directory. Project 03 used:

```powershell
python -m pytest tests -q -m 'not slow' -p no:cacheprovider --ignore=tests/integration/test_dynamic_ppo_integration.py --ignore=tests/integration/test_static_ppo_integration.py --ignore=tests/integration/test_static_ppo_v2_integration.py --ignore=tests/integration/test_project03_results_release.py --ignore=tests/unit/test_project03_results.py --ignore=tests/integration/test_scientific_benchmark_integration.py --ignore=tests/integration/test_benchmark_diagnostics_integration.py
```

These exclusions preserve the owner's no-training/no-held-out boundary; the
unexecuted tests are not counted as passed. Sandbox temporary-directory failures
are retained in original logs; the retry results are reported separately.

## Regression update — current-source fast suite complete

Project I non-slow retry: **472 passed, 9 deselected in 752.12 s**. No failure.
The 9 opt-in slow tests are executing in the original long campaign, not counted
as passed here. The fast suite collected 19 closure tests before the last two
focused approval/progress tests were added; the final 44-test readiness run
includes all 21 closure tests plus all 23 existing coordination tests.
This update supersedes the initial fast-suite RUNNING status in section 9.
The full opt-in campaign remains RUNNING; successful expensive cases will not
be repeated merely to remove the separate sandbox temporary-fixture errors.

## Exact-input archive readiness update

The final capture additionally stores the actual immutable policy observation
(base64 pickle), preserving the sanitized B2 projection for common-input replay.
It records the observer's original return value and never changes policy inputs.
All 44 focused/coordination tests pass after this addition (6.90 s), including
input/view-digest linkage and sanitized-catalog/ledger checks. Actions, traces and
prediction digests remain identical with capture enabled. This additive reporter
change supersedes the earlier plan with the current hash in section 6. Earlier
plans remain intact. The full-suite default capture remains disabled.

## Persistent evidence verification update

Final focused run: **47 passed in 11.68 s** (24 closure + 23 existing
coordination). Three additional tests run the controller on tiny hand-written
A2/B2-T/B2 fixtures in pytest temporary storage, then reload/verify the JSON,
ledger, events and original policy-input archive. Stored trace hashes match
plain fixture execution. These are test-only mocked approval gates and do not
create the real approval file, run a stored development scenario, or count as F3.
This supersedes earlier focused-test totals; it changes no production source or
plan hash. No further test expansion is needed unless a failure appears.

## Final Phase A regression closure — 2026-10-14

The authorized Phase A work is complete. The original opt-in command reached
100% but exited 1 because pytest's session-finish cleanup raised
`PermissionError: [WinError 5]` on the designated basetemp. It did not produce
a normal pytest result summary and is **not labelled a clean full-suite pass**.

The archived progress symbols map exactly to all 462 original collected tests:
**443 pass indicators, 19 error indicators, 0 failure indicators, 0 skips**.
The reconstruction excludes only the subsequently added closure test module;
pre-existing test files were not changed. All 19 error nodes are non-slow and
were covered by the clean 472-pass retry. Their individual setup tracebacks
were not emitted after session-finish aborted, so the report does not invent
19 independent error traces. The explicit teardown evidence is WinError 5;
the temporary-file failures disappear with normal-access pytest execution.

All **9 slow tests have pass indicators**, including all four Step 4 family
gates (**80/80 scenarios**) and all four Step 5 family/arm gates (**400/400
cases**), plus the existing B2/B2-T development integration test. These gates
were intentionally executed once and not repeated. The wrapper does not retain
per-case scope counts: **383 FULL / 17 PREFIX** is verified from the preserved
historical 400-row report, rather than misrepresented as a newly recorded counter.

Original command duration is approximately **4923.27 s (82.05 min)** from the
log's creation/last-write timestamps; this is not a missing pytest stopwatch
summary. The separate fast retry took 752.12 s, and final focused verification
took 11.68 s. These overlapping commands must not be summed as elapsed project
time. F3 campaign runtime remains zero.

Immutable reconstruction:
`experiments/step6_closure/phase_a/full_progress_e0b6a4a307fc.json`.
Final machine-readable closure report:
`experiments/step6_closure/phase_a/closure_report_638ac8c0fa9f.json`.
It records 137 source/config hashes, all 31 preserved historical input hashes,
the actual HEAD/worktree, raw test-log hashes, the original collection order,
all nine slow-test results, all 19 recovered error node IDs, and the owner/F3
blocks. The final plan directory contains only `plan.json` and its hash sidecar;
no episode, started marker or worker lock exists there.

This final update supersedes every earlier RUNNING/regression-pending status in
this document. Current status:

```text
AUTHORIZED_PHASE_A              = COMPLETE
STEP6_CLOSURE                   = PARTIAL_F3_REQUIRES_OWNER_APPROVAL
OWNER_Q6_DECISIONS              = PROPOSED_NEEDS_OWNER_APPROVAL (all four)
A2_B2T_DEGENERATE_CONTRACT_GATE = PASS_SCOPED
K5_FIXED_BUDGET                 = PROPOSED_FULL_COHORT_NEEDS_OWNER_REVIEW
F3_DEVELOPMENT                  = BLOCKED_BY_OWNER_REVIEW (0/12)
HIDDEN_FUTURE_GATE              = PASS
PENDING_PARAMETER_RECORDS       = 28
SCIENTIFIC_PROTOCOL_LOCK        = BLOCKED
VALIDATION_AUTHORIZED           = NO
STEP7_STARTED                   = NO
```

No owner approval, validation access, training, source-policy modification,
protocol lock or commit was performed. Owner follow-up remains section 11.
