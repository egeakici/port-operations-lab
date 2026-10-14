# Step 6 closure diagnostics — DEVELOPMENT_ONLY

These are reanalyses of existing F1/F2 records, not F3 results or validation.
All predictions: `UNCALIBRATED_SYNTHETIC_FORECAST`.
Machine evidence: `experiments/step6_closure/phase_a/history_981f78c74152.json`.

## WAIT and prediction audit

Low: A2 9 decisions/1 WAIT, B2 and B2-T each 9/1. Medium: A2 17/1;
B2 and B2-T each 20/4. Historical A2 stores these aggregates, not the full
decision sequence, so its WAIT time/branches cannot be recovered without replay.
Every historical B2/B2-T prediction decision is retained in the new report.

| Medium B2 decision | Time min | Until next actual berth decision min | WAIT branches | Selected prediction minus same-cohort realized turnaround |
| --- | ---: | ---: | ---: | ---: |
| 10 | 1825.155 | 42.588 | 6 | -865.857 |
| 11 | 1867.744 | 64.069 | 6 | -143.334 |
| 14 | 2653.502 | 171.061 | 14 | +32.840 |
| 16 | 2824.564 | 263.016 | 8 | -92.969 |

Decision 10 precedes V016's announcement, and the next actual decision coincides
with that announcement. V016 is absent from that projection. Decisions 11, 14
and 16 have no later unannounced vessel in this episode, yet prediction errors
remain, including opposite signs. Hidden new vessels therefore cannot uniquely
explain the errors. Omitted landside requests and other model/branch semantics
remain hypotheses. The elapsed WAIT intervals are not a causal decomposition of
the 2,647 vessel-minute Medium difference from A2; trajectories are unmatched.
Historical records omit resource snapshots and inner next-decision times, so
berth-release benefits and detailed crane/yard congestion are not asserted.

Mean signed errors reproduce -189.4 vessel-min (Low) and -320.5 (Medium).
The reporter uses exactly the stored cohort and compares realized turnaround
censored at last cohort arrival plus drain extension. Quantiles are stored.
All these chosen leaves and realized cohorts complete without censoring.
Predicted cargo U and actual complete-scenario U are zero on Low/Medium;
cohort and complete-scenario denominators remain distinct.

## Cargo pivotal evidence

Across 29 unique B2 decisions (9 Low + 20 Medium), zero candidate sets have
any predicted cargo difference; zero cargo-pivotal selections, and zero
one-container pivotal selections. B2-T's corresponding 29 records agree in
candidate evidence and prediction digests. Full immutable view bytes were not
archived, so this is prediction-record equality, not a claim of archived input
byte equality. Heavy/Bottleneck pivotal coverage is **NOT_RUN** until F3.
The existing pure-selector test still permits one container to override an
8,000-minute turnaround cost; that is a design property, not an observed effect.

## Ledger-grounded cargo summaries

| Existing family/arms | N_out | Loaded | U | D17 rolled over | Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Low, all six arms | 2430 | 2430 | 0 | 0 | 0 |
| Medium, all six arms | 4376 | 4376 | 0 | 0 | 0 |
| Heavy, A1 | 6989 | 6989 | 0 | 0 | 0 |
| Heavy, A1n/B1 | 6989 | 6897 | 92 | 92 | 1.3164% |
| Bottleneck, A1 | 4850 | 4850 | 0 | 0 | 0 |
| Bottleneck, A1n/B1 | 4850 | 4595 | 255 | 255 | 5.2577% |

The reporter verifies N_out = loaded + U and the recorded ledger/status
reconciliations, retains by-flow/by-vessel counts, loaded-not-departed,
vessel-present unfinished obligations, and unfinished moves. Departures do not
substitute for LOAD_COMPLETED. Stored classifications show the listed shortfalls
as D17 rollover from departed vessels; loaded-not-departed is zero.

Handling-cause minutes are runtime accounting with precedence, not mutually
exclusive container-level causes. Without underlying event-level cargo evidence,
unique primary attribution remains `UNKNOWN_OR_MULTIPLE_CONSTRAINTS`.
No claim is made that all losses were exports not gated in, or that WAIT caused
the rollovers. No future information enters a policy from this ex-post reporter.

No forecast calibration, cargo tolerance, policy ranking, CARGO-NI conclusion,
training, validation, profile adjustment or algorithm retuning was performed.

## F3 completed diagnostics — 2026-10-14

The earlier Heavy/Bottleneck NOT_RUN statements describe Phase A and are now
superseded by the authorized F3 extension: **12/12 completed, 320 berth decisions,
68 selected WAITs**. See the single consolidated
[final owner report](step6_closure_final_report.md) and its immutable machine
evidence `experiments/step6_closure/6401af0e2a01/reports/f3_b745793420a7.json`.

There are 226 integrated decisions / 222 distinct complete canonical inputs;
87 inputs contain predicted cargo variation and 11 are cargo-pivotal. There is
no observed one-container pivotal case. Maximum predicted turnaround sacrifice
at a pivotal input is 2665.945 minutes. Only four complete cross-arm inputs
match exactly after excluding construction wall time; entire outer trajectories
are not treated as shared evaluation sequences. Eight fixed F3 input-replay
probes reproduce every candidate prediction byte; no new outer episode ran.

B2 has U=0 in all four scenarios; B2-T has U=84 in Bottleneck seed 10000000 and
zero elsewhere. A2's Heavy U values are 119/70 and Bottleneck values 180/130.
Every observed shortfall is a D17 rollover with transshipment cargo still
ABOARD_ARRIVED_VESSEL at its causally ordered timeout. This supports the
availability-stage diagnosis, while upstream attribution remains
UNKNOWN_OR_MULTIPLE_CONSTRAINTS. All cargo/status/TEU/move invariants reconcile.

Mean signed same-cohort turnaround errors (prediction minus realized) are
Heavy B2 -484.392, Heavy B2-T -370.826, Bottleneck B2 -1249.460, Bottleneck B2-T
-1367.906 vessel-min. A2 future-queue scores are analyzed separately. Exact
archived projection horizons and explicit cargo denominators are used. All
predictions retain UNCALIBRATED_SYNTHETIC_FORECAST; no calibration or tuning.

WAIT branch/epoch/event reconstructions, actual resource changes, hidden-arrival
time windows and full per-decision evidence are retained. The four historical
Medium autopsies remain unchanged and are reproduced in the final report.
No causal WAIT-only performance decomposition or inferential ranking is claimed.
