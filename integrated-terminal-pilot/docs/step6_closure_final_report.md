# Project I — Step 6 Closure consolidated owner report

**DEVELOPMENT_ONLY — COMPLETE: 12/12 F3 runs.**
Post-run diagnostic status: **COMPLETE**; additional WAIT reconstructions not admitted after compute allowance: 0.
All predictions: `UNCALIBRATED_SYNTHETIC_FORECAST`. No winner or primary CARGO-NI inference.

## 1. Revision and preservation

Phase A began/ended at `76ced62b94e5419fea98933b3cb17debf1bd8a62`. The owner then committed Phase A as `dac52fd` and `38a4f5c`. F3 used `38a4f5c67b3e8c5dfa9cff7a0ce10ff6b8a55c9b`. No agent commit or staging.

All 137 approved source/config hashes, authentic P03 A2, frozen B policies, checkpoints, QC8 Balanced Yard physics and original historical artifacts are preserved. New work consists of approval provenance, reporter-only diagnostics and documentation. Projects 01–03 were not modified.

Machine evidence: `experiments\step6_closure\6401af0e2a01\reports\f3_b745793420a7.json`. It links every run and per-decision diagnostic hash.

## 2. Owner decisions and authority

Q6-1 B1 v1 estimator, Q6-2 omission of future landside requests, Q6-3 K5-A uncapped full cohort and Q6-4 cohort/horizon/censoring/FCFS/WAIT semantics are explicitly **APPROVED**. K5-A preserves every legal candidate and WAIT. Protocol section 5’s proposed 2-second reduction trigger is superseded by a compute warning for Step 6/Step 7 research (AM-10); no Step 7 start is authorized.

Approval: `configs\protocol\step6_closure_owner_approval.json`; canonical SHA `ef4dc4463d108c31e3013e6361388aabc89e7e5c7b94b9ffaef89bad01af9118`. Exact message: `configs/protocol/step6_closure_approval_history/owner_message_6401_verbatim.txt`. The owner explicitly approved the replacement plan; earlier approval/history records remain unchanged. The small line-break normalization in the initial JSON is documented by an append-only exact-message provenance artifact.

## 3. Independent contract gate

**PASS_SCOPED:** 12 FULL fixtures, 20 eligible decisions, 0 PREFIX, 5 noneligible controls, 0 demonstrated contract defects. For uncensored fixed-service branches, integrated turnaround equals authentic future queue waiting plus a candidate-independent constant. Candidate orders, ties and WAIT branches match under that predicate. Rate/distance dependence, cargo delays and censoring are preserved negative findings; no universal equivalence is claimed.

Reviewed gate SHA `7cb84b87c78f3b2a6628a59ce4a2013b90ba8d66c347230eab24d6095f18c5c2`. Phase A was not repeated.

## 4. Algorithms and observation integrity

No policy score, tie, continuation, physics, cohort cap, tolerance or checkpoint changed. The Phase A optional sanitized observation capture is unchanged. All new future-event analysis is confined to the post-run reporter. The reporter reconstructs WAIT subbranches from archived inputs; it never supplies those reconstructions or realized outcomes to a policy.

## 5. Compute costs and resource envelope

One worker; 180-minute cumulative admission allowance; 4096 MiB process-RSS admission check. Healthy episodes are allowed to finish; no inner candidate is truncated for wall time.

Episode wall sum: **63.307 min**; CPU sum: 61.089 min. Max episode-boundary RSS: 675.277 MiB; max telemetry sample: 729.203 MiB. These are sampled values, not a peak-memory claim. JSON/reporting overhead and post-run reconstruction are separated from policy/evaluator timings. Full admission checkpoints are in the machine report.

Campaign elapsed at the last recorded checkpoint: 67.848 min. Reporter analysis: 475.105 s. Episode sums exclude final result serialization/checksum overhead; the campaign admission clock includes it.

Historical A2 maxima 10.28 s and 1.86 s use different sampling frames and trajectories. The Phase A matched-state probe was repeatable but did not reconstruct the missing slowest historical state. The sparse maximum is not a global A2 bound. Projection build is outside B evaluator timing.

| Family / arm | Decisions | WAIT | Policy p50 s | p95 s | Max s | >2 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| itp_heavy/A2 | 56 | 8 | 0.349 | 4.543 | 8.798 | 9 |
| itp_heavy/B2 | 59 | 11 | 9.870 | 67.874 | 118.670 | 48 |
| itp_heavy/B2-T | 59 | 11 | 10.624 | 70.397 | 120.291 | 48 |
| itp_yard_bottleneck/A2 | 38 | 2 | 0.104 | 1.410 | 1.847 | 0 |
| itp_yard_bottleneck/B2 | 52 | 16 | 6.180 | 25.868 | 29.777 | 36 |
| itp_yard_bottleneck/B2-T | 56 | 20 | 6.287 | 23.660 | 25.915 | 39 |

Percentiles use numpy linear interpolation; historical runner quantiles remain labelled separately.

## 6. F3 coverage and plan

Plan SHA: `6401af0e2a01f875d3d5d24b0db1ed25a7f2955ae8ed92645081dc1366c97f20`.

| Family | Seed | Arm | Turnaround min | N_out | Loaded | U | D17 rolled | Wall s |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| itp_heavy | 10000000 | A2 | 58,695.842 | 6989 | 6870 | 119 | 119 | 72.686 |
| itp_heavy | 10000000 | B2-T | 59,520.025 | 6989 | 6989 | 0 | 0 | 1,006.469 |
| itp_heavy | 10000000 | B2 | 59,520.025 | 6989 | 6989 | 0 | 0 | 999.463 |
| itp_heavy | 10000001 | A2 | 41,350.045 | 7023 | 6953 | 70 | 70 | 35.287 |
| itp_heavy | 10000001 | B2-T | 37,939.188 | 7023 | 7023 | 0 | 0 | 263.335 |
| itp_heavy | 10000001 | B2 | 39,807.442 | 7023 | 7023 | 0 | 0 | 251.493 |
| itp_yard_bottleneck | 10000000 | A2 | 36,899.374 | 4850 | 4670 | 180 | 180 | 29.196 |
| itp_yard_bottleneck | 10000000 | B2-T | 41,446.701 | 4850 | 4766 | 84 | 84 | 289.204 |
| itp_yard_bottleneck | 10000000 | B2 | 40,564.349 | 4850 | 4850 | 0 | 0 | 287.218 |
| itp_yard_bottleneck | 10000001 | A2 | 42,871.787 | 5973 | 5843 | 130 | 130 | 32.316 |
| itp_yard_bottleneck | 10000001 | B2-T | 42,548.103 | 5973 | 5973 | 0 | 0 | 270.419 |
| itp_yard_bottleneck | 10000001 | B2 | 43,168.470 | 5973 | 5973 | 0 | 0 | 261.304 |

### Preserved historical context (not fresh F3 runs)

| Scenario | Historical arm | Turnaround min | U containers |
| --- | --- | ---: | ---: |
| itp_heavy_development_seed10000000 | A1 | 63,629.723 | 0 |
| itp_heavy_development_seed10000000 | A1n | 62,908.046 | 92 |
| itp_heavy_development_seed10000000 | B1 | 62,709.612 | 92 |
| itp_heavy_development_seed10000001 | A1 | 41,075.233 | 110 |
| itp_yard_bottleneck_development_seed10000000 | A1 | 43,888.089 | 0 |
| itp_yard_bottleneck_development_seed10000000 | A1n | 39,213.427 | 255 |
| itp_yard_bottleneck_development_seed10000000 | B1 | 39,213.427 | 255 |
| itp_yard_bottleneck_development_seed10000001 | A1 | 44,053.601 | 0 |
| itp_heavy_development_seed10000000 | A3 mean of train 11/23/37 | 63,879.416 | 114.000 |
| itp_heavy_development_seed10000001 | A3 mean of train 11/23/37 | 41,323.643 | 233.000 |
| itp_yard_bottleneck_development_seed10000000 | A3 mean of train 11/23/37 | 37,512.547 | 185.333 |
| itp_yard_bottleneck_development_seed10000001 | A3 mean of train 11/23/37 | 43,882.106 | 44.667 |

Historical context is admitted only after fingerprint, profile/cutoff/denominator, status/audit and policy-identity checks. Every original file hash and Git/package provenance is retained. Missing, blocked or mismatched context is rejected, not repaired. A3 training seeds are averaged within a scenario only when all three exist and verify. Context is neither a new F3 run nor independent traffic replication.

No completed outer episode was duplicated or silently retried. Safe resume verifies stored hashes and pairing metadata; incomplete attempts/worker locks require inspection. A budget stop requires further resource authorization before additional admission; no cap or fallback substitutes for it.

## 7. WAIT, pivotal cargo, rollover and forecast diagnostics

Integrated decisions: 226; unique canonical integrated inputs: 222; inputs with any predicted cargo variation: 87; cargo-pivotal inputs: 11; one-container pivotal inputs: 0.

CARGO_PRIORITY_CHANGED_ROOT_ACTIONS: report predicted cargo/turnaround tradeoffs; realized alternative trajectories are not observed counterfactuals.

Maximum observed predicted turnaround sacrifice among pivotal inputs: 2,665.945 min. The preserved pure-selector test documents that one container can override an 8,000-minute predicted cost; observed frequencies and tradeoffs above are kept separate from that permitted design property.

Both selectors are compared on exactly the same stored candidate predictions at each state. Actual subsequent outcomes belong to the executed outer trajectory, not an unobserved counterfactual. Full per-decision cohort, legal actions, resources, selected branches, horizon/censoring and realized same-cohort outcomes are retained. A2 future queue scores and errors are separate from B turnaround forecasts; A2 does not predict cargo. P03’s scalar-return WAIT implementation does not retain a unique subbranch identity on ties, so the reporter records all tied minima.

| Integrated family / arm | Mean TA error | Median | P95 | Mean absolute | Mean known-cargo U error |
| --- | ---: | ---: | ---: | ---: | ---: |
| itp_heavy/B2 | -484.392 | -55.422 | 1,081.796 | 857.853 | 0.237 |
| itp_heavy/B2-T | -370.826 | -42.011 | 1,081.796 | 757.070 | 3.254 |
| itp_yard_bottleneck/B2 | -1,249.460 | -761.624 | -102.973 | 1,265.491 | 0.000 |
| itp_yard_bottleneck/B2-T | -1,367.906 | -898.659 | -93.851 | 1,367.983 | -7.250 |

Signed error = predicted minus realized outcome for the same cohort at the common inner horizon. Known forecast obligations and full-cohort obligations have separate denominators and explicit equality flags. No calibration or posterior forecast correction was applied.

### WAIT illustrations

Four preserved historical Medium B2 autopsies (not F3):

| Decision | Time min | WAIT to next actual decision min | Branches | TA prediction error min |
| --- | ---: | ---: | ---: | ---: |
| 10 | 1825.155 | 42.588 | 6 | -865.857 |
| 11 | 1867.744 | 64.069 | 6 | -143.334 |
| 14 | 2653.502 | 171.061 | 14 | +32.840 |
| 16 | 2824.564 | 263.016 | 8 | -92.969 |

Only decision 10 precedes V016’s announcement. Errors persist without later hidden entrants in the other three cases; hidden arrivals cannot uniquely explain the historical Medium gap. These are preserved source-record autopsies, not newly executed Medium episodes.

One additional F3 illustration is selected descriptively by largest absolute integrated TA error among the retained examples. All F3 WAITs remain available in per-decision diagnostics:

- itp_yard_bottleneck / 10000000 / B2-T, decision 6 at t=1,421.146: WAIT elapsed 1.400 min; departures []; new announcements ['V017']; TA error -4,588.417.

These time windows do not establish a causal WAIT benefit or loss. The four historical Medium autopsies and Low/Medium forecast errors remain preserved in `docs/step6_closure_diagnostics.md`. No new F3 result proves a WAIT-only explanation of the historical Medium gap.

### Cargo evidence

- itp_heavy / 10000000 / A2: overlapping tags {'D17_ROLLOVER': 119, 'TRANSSHIPMENT_NOT_DISCHARGED_TO_YARD_AT_D17': 119}; D17 status counts {'ABOARD_ARRIVED_VESSEL': 119}.
- itp_heavy / 10000001 / A2: overlapping tags {'D17_ROLLOVER': 70, 'TRANSSHIPMENT_NOT_DISCHARGED_TO_YARD_AT_D17': 70}; D17 status counts {'ABOARD_ARRIVED_VESSEL': 70}.
- itp_yard_bottleneck / 10000000 / A2: overlapping tags {'D17_ROLLOVER': 180, 'TRANSSHIPMENT_NOT_DISCHARGED_TO_YARD_AT_D17': 180}; D17 status counts {'ABOARD_ARRIVED_VESSEL': 180}.
- itp_yard_bottleneck / 10000000 / B2-T: overlapping tags {'D17_ROLLOVER': 84, 'TRANSSHIPMENT_NOT_DISCHARGED_TO_YARD_AT_D17': 84}; D17 status counts {'ABOARD_ARRIVED_VESSEL': 84}.
- itp_yard_bottleneck / 10000001 / A2: overlapping tags {'D17_ROLLOVER': 130, 'TRANSSHIPMENT_NOT_DISCHARGED_TO_YARD_AT_D17': 130}; D17 status counts {'ABOARD_ARRIVED_VESSEL': 130}.

N_out=loaded+U, ledger/final-status and per-vessel move reconciliations pass. Each D17 loss links to a timeout event and exact container status, source connection, eventual yard-ready time and overlapping WAIT windows. Evidence tags can overlap; upstream primary attribution remains `UNKNOWN_OR_MULTIPLE_CONSTRAINTS`. Departure never substitutes for LOAD_COMPLETED. Loaded-but-not-departed, vessel-present incomplete obligations and unfinished moves are reported separately by run/flow/vessel.

## 8. Pairing, hidden-future boundary and determinism

Common scenario/exogenous/physical fingerprints, QC8, max two cranes/vessel, assigned efficiency, D15/D17/R5, T_end and N_out verify across arms. Run hashes and original ledger/event/blocking digests are independently checked. Actual archived integrated inputs are checked for redacted identity, absent hidden vessel catalog entries and future gate/pickup events, normalized event sequences, and absent ledger/event logs.

Matched integrated canonical inputs with identical candidate predictions: 4. Canonical input bytes exclude projection construction wall time; the report separately records whether raw pickle bytes match. Whole episodes are not claimed to share states after divergence. Matched A2/B2-T observed contexts still have model/objective differences. Existing Phase A determinism/full-summary parity tests are preserved; no completed outer episode was repeated. New F3 probes use fixed B2-T ordinals 1 and 5 per scenario on the exact archived inputs; private event logging measures processed-event counts while requiring every candidate prediction byte to reproduce.

New F3 determinism probes passed: 8/8. These are inner-input diagnostics, not additional outer runs.

## 9. Regression evidence

Phase A retained: Project I fast 472 passed / 9 deselected; final focused 47 passed. The original opt-in command lost its summary to pytest WinError 5 cleanup; exact progress reconstruction records 443 passes / 19 errors / 0 failures / 0 skips. A clean retry covers all affected non-slow nodes. All nine slow tests passed, including 80/80 Step 4 and 400/400 Step 5. Historical scope counts are 383 FULL / 17 PREFIX; the existing pytest wrapper did not retain new scope counters. This is not mislabelled as one clean full-suite command.

Projects 01/02: 426/55 passed; selected Project 03 suite: 423 passed, 5 deselected. Training and historical-results/benchmark integration exclusions are documented in Phase A. No old tests were repeated. New reporter arithmetic tests: 5 passed in 0.27 s; a separate same-timestamp causal-sequence test also passed. A reporter-only timestamp field mismatch was repaired by deriving actual times from authoritative assignment records and departure events; real-record shape/integrity checks then passed. No policy or result was altered.

## 10. Status and remaining scientific blockers

```text
STEP6_CLOSURE_F3          = COMPLETE (12/12)
OWNER_Q6_DECISIONS        = APPROVED
K5_FIXED_BUDGET           = APPROVED_FULL_COHORT
DEGENERATE_GATE           = PASS_SCOPED
PENDING_PARAMETER_RECORDS = 28
SCIENTIFIC_PROTOCOL_LOCK  = BLOCKED
VALIDATION_AUTHORIZED     = NO
STEP7_STARTED            = NO
```

Remaining scientific blockers: 28 pending synthetic parameter records and a separate formal Step 7 lock procedure; uncalibrated/omitted landside forecasts; conditional model/horizon comparability; n=2 scenarios/family; incomplete causal attribution of WAIT and cargo losses; the missing historical slowest A2 state; sampled memory rather than peak RSS; and frozen PPO forecast-substitution domain shift / unestablished equality with the original GPU training runtime. Negative/null/mixed findings are preserved. No winner, S2 success, primary CARGO-NI conclusion or validation readiness is declared.

## 11. Owner review

Review this consolidated Step 6 Closure report. Completion of this development characterization does not approve parameters, create the scientific lock, authorize held-out use, retrain PPO or start Step 7.

## 12. Descriptive owner readout and pivotal-state audit

This append-only readout is derived from the unchanged machine report above.

All **320 berth decisions and 68 selected WAITs** are covered. B2 loaded every outbound obligation in all four selected scenarios. A2 had D17 losses of 119/70 containers in Heavy and 180/130 in Yard Bottleneck. B2-T had 84 losses in Bottleneck seed 10000000 and zero in the other three cases.

Turnaround findings are mixed: **B2 is slower than A2 in three of four scenarios** despite its cargo fulfillment. B2-T is slower than A2 in two scenarios and faster in two. Relative to B2-T, B2 is equal on Heavy seed 10000000, slower on Heavy seed 10000001 and Bottleneck seed 10000001, and faster with 84 fewer lost obligations on Bottleneck seed 10000000. These are descriptive scenario contrasts; no statistical winner or primary CARGO-NI conclusion follows.

Every observed F3 shortfall has direct D17 evidence with transshipment cargo still `ABOARD_ARRIVED_VESSEL` at the deadline. This establishes that the inbound cargo had not been discharged to a loadable yard location. It does not uniquely assign the upstream reason to berthing, crane/yard congestion or WAIT; those mechanisms remain coupled.

### All cargo-pivotal unique inputs

Each row applies both pure selectors to one identical candidate evaluation set. The row arm identifies the actually executed trajectory; alternate realized outcomes are not invented.

| Family / seed / trajectory | Decision | Time min | B2 action | B2-T action | Predicted cargo advantage containers | Predicted TA sacrifice min |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| itp_heavy / 10000001 / B2-T | 14 | 2461.609 | 721 (ASSIGN) | 433 (ASSIGN) | 27 | 2665.945 |
| itp_heavy / 10000001 / B2-T | 16 | 2762.735 | 0 (WAIT) | 482 (ASSIGN) | 110 | 1889.261 |
| itp_heavy / 10000001 / B2 | 14 | 2461.609 | 721 (ASSIGN) | 433 (ASSIGN) | 27 | 2665.945 |
| itp_yard_bottleneck / 10000000 / B2-T | 14 | 2661.011 | 433 (ASSIGN) | 0 (WAIT) | 85 | 6.553 |
| itp_yard_bottleneck / 10000000 / B2-T | 15 | 2809.378 | 578 (ASSIGN) | 818 (ASSIGN) | 84 | 235.448 |
| itp_yard_bottleneck / 10000000 / B2-T | 17 | 3053.333 | 385 (ASSIGN) | 769 (ASSIGN) | 58 | 396.778 |
| itp_yard_bottleneck / 10000000 / B2 | 14 | 2661.011 | 433 (ASSIGN) | 0 (WAIT) | 85 | 6.553 |
| itp_yard_bottleneck / 10000000 / B2 | 15 | 2820.437 | 241 (ASSIGN) | 770 (ASSIGN) | 85 | 871.550 |
| itp_yard_bottleneck / 10000001 / B2-T | 19 | 3414.945 | 626 (ASSIGN) | 0 (WAIT) | 48 | 714.238 |
| itp_yard_bottleneck / 10000001 / B2-T | 22 | 4025.397 | 481 (ASSIGN) | 0 (WAIT) | 12 | 141.975 |
| itp_yard_bottleneck / 10000001 / B2 | 19 | 3414.945 | 626 (ASSIGN) | 0 (WAIT) | 48 | 714.238 |

The 11 pivotal unique inputs have no observed one-container pivotal case. The maximum predicted turnaround sacrifice is 2665.945 minutes. The primary model objective remains unchanged; these observations do not authorize a tolerance, recalibration or policy rescue.

Final integrity: all 137 approved source/config hashes match; all six checkpoint hashes match; all 31 historical inputs used in Phase A match their captured SHA-256 values. No outer episode was repeated, no incomplete attempt or worker lock remains, and no automatic commit was made.

Final review manifest: `experiments/step6_closure/6401af0e2a01/reports/final_review_manifest.json`.
