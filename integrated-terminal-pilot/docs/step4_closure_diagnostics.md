# Step 4 Closure — Pre-Step-5 Diagnostics

**Step 4 closure, not a new numbered roadmap step.** Built on the Step 4 commit `2b6153a`.
**Development data only. FCFS physical fixture only.** These runs are not A1 results, not S1/S2
evidence and not a Step 5 evaluation. **Nothing here selects or freezes a fleet, a family or a yard
baseline.** SYNTHETIC — NOT CALIBRATED.

## 1. Purpose and baseline history

Step 4 produced a working kernel and two open research-readiness questions:

* **A. First-fit concentration.** The frozen P_y `yard_first_fit_v1` sends all eligible work to the
  lowest-id block with free TEU. Every arm uses the same P_y, so this gives no arm an information
  advantage. It may, however, mask differences and make berth-position effects depend on one block.
* **B. Supply versus demand.** Realized service of about 5× nominal and drain-limit truncation (heavy,
  bottleneck) were seen on single seeds. Crane scarcity had not been separated from yard
  concentration, transport, arrival overload and rollover.

The closure adds measurement tools, stages amendment AM-01 as **PROPOSED**, and characterizes these
factors on the 80 stabilized development scenarios. Physics, reference values and all historical
artifacts are unchanged. Event, ledger, decision and blocking digests of fresh runs are
byte-identical to the committed Step 4 smoke runs (verified for low and heavy seed 10,000,000).

## 2. Inspection evidence

| Item | Code path |
| --- | --- |
| Yard policies (unchanged) | `policies/yard.py::FirstFitYardPolicy.decide`, `OccupancyBalancingYardPolicy.decide`, `eligible_blocks` |
| Registry (unchanged) | `policies/registry.py::POLICY_REGISTRY` (`yard_first_fit_v1` primitive, `yard_occupancy_balance_v1` diagnostic), `create_policy` |
| Reference yard id | `simulator/diagnostics.py::REFERENCE_YARD_POLICY_ID = "yard_first_fit_v1"`; `simulator/drivers.py::default_policies` |
| Crane efficiency (R1) | `simulator/kernel.py::_recompute_rates` (`assigned` reference; `working` diagnostic); `physics.py::crane_rate_moves_per_hour` |
| Release admission (R5) | `simulator/kernel.py::_start_releases`, `BlockState.active_release_wo`, `invariants.py` INV15 admission check |
| Batch rule D15 / sequencing D16 | `kernel.py::_dispatch_crane` (D16), `catalog.py::PhysicsConfig.check_supported` (D15) |
| Rollover D17 | `kernel.py::_update_load_wait_timers`, `_on_load_wait_timeout`, `_load_wait_condition` |
| Trace modes | `simulator/trace.py::emit_trace`, `write_trace`, `canonical_streams` |
| Overrides and fingerprints | `simulator/diagnostics.py::derive_fleet`, `build_condition_catalog`, `DiagnosticCondition` |
| Decomposition, compliance | `kernel.py::_handling_cause`, `_settle`; `metrics.py::_compliance_and_decomposition` |
| Campaign | `simulator/closure.py`, `scripts/run_step4_closure_campaign.py` |

No conflict with a frozen contract was found before modifying code.

## 3. Decision status

| Decision | Status | Note |
| --- | --- | --- |
| 10 reference values (4 cranes, 30 moves/h, ≤ 2/vessel, eff(2) 0.92, 12 blocks, 26,400 TEU, 60/30 moves/h, 0.50/0.70) | **APPROVED by the user** (register `approval` blocks) | unchanged |
| D15 `batch_size_containers = 10` | PROPOSED_PENDING_REVIEW (S2-075) | approval-ready entry in the physics audit §7 |
| D17 `max_load_wait_min = 240` | PROPOSED_PENDING_REVIEW (S2-075) | rollover now reported as unfulfilled cargo |
| R5 release admission | Step 4 execution rule, pending review | scope unchanged (GATE_OUT only) |
| R1 efficiency basis | `assigned` per frozen spec §5.1 | `working` is a diagnostic override only |
| AM-01 balanced common P_y | **PROPOSED / PENDING USER APPROVAL** | [protocol_amendments.md](protocol_amendments.md) |
| Remaining physics coefficients | 29 PROPOSED_PENDING_REVIEW records | [step4_physics_approval_audit.md](step4_physics_approval_audit.md) |

**D15/D16 audit.** No Project I file labelled the batch-size rule D16. Four phrasings said batches
are "dispatched/chosen by D16"; they now say batches are formed under D15 and sequenced under D16:
`policies/crane.py` (module docstring), `docs/step3_primitive_policies.md` §9 table,
`tests/integration/test_step3_project02_equivalence.py` (docstring), `tests/unit/test_policy_crane.py`
(docstring). No behaviour changed. A test guards the distinction.

## 4. AM-01 (PROPOSED)

Full text, rationale, limits and the approval checklist are in
[protocol_amendments.md](protocol_amendments.md). In short: all arms (A1/A2/A3/B1/B2, optional B3)
would use the same `yard_occupancy_balance_v1` as P_y; `yard_first_fit_v1` stays as diagnostic
`P_y_ff`. The balancing rule reads only yard-local `YardObservation` fields (tested). First fit is
kept because it is the frozen protocol rule and the historical Step 4 baseline. Balancing is proposed
because a common primitive that funnels all yard work into one block can mask berth effects; it is a
design-motivated candidate, not a proven optimum. The reference default is **unchanged** until
explicit approval.

## 5. Engineering additions

**Trace modes.** `full` writes all canonical files. `summary` writes only `blocking.jsonl`,
`rejections.jsonl` and `result.json`, but computes every per-file digest by streaming exactly the
same bytes in the same order. Per-file digests and `trace_sha256` are identical in both modes
(tested on the golden fixture and on `itp_low` seed 10,000,000). A summary run is
**digest-verifiable** only: it can be verified by re-running with the same scenario, physics,
policies and code version, not independently replayed from its own files. **Savings are disk only.**
The kernel keeps its ledger and event log in memory for the audits, and the final-state snapshot is
materialized transiently (12–18 MB) while it is hashed. In-memory use is the same in both modes.

**Diagnostic overrides** (`--crane-count`, `--yard-policy`, `--efficiency-basis`, and the
campaign conditions). Added cranes `QC05`… are copies of the homogeneous reference crane record (the
generator's own construction). The derived document is re-validated by the Step 2 validator and
re-fingerprinted in memory; the source file is never written. A heterogeneous source fleet is
refused. Fingerprints:

* `base_scenario_fingerprint` / `base_exogenous_schedule_fingerprint` — of the immutable source,
  identical across matched conditions (asserted);
* `resolved_physics_fingerprint` — crane fleet, physics block and efficiency basis;
* `condition_fingerprint` — resolved physics plus berth, crane and yard policy ids.

6 and 8 cranes compare **different physical fleets** on the same exogenous traffic; they are not
same-physics S1/S2 contrasts.

**Efficiency basis.** `assigned` (reference): `eff(n)` with `n` assigned cranes; one working crane
on a two-crane vessel runs at 27.6 moves/h. `working` (diagnostic): `n` = cranes working a batch, so
the same crane runs at 30. When the working count changes, rates are recomputed at the end of that
kernel cycle and the affected completion events are rescheduled through the existing
rate-generation mechanism (deterministic, tested).

**Vessel-time decomposition.** For every arrived vessel, observed time `min(departure, run stop) −
arrival` is partitioned into berth wait, berthing preparation, handling and departure preparation
(elapsed parts only; nothing is extrapolated). An unfinished vessel's total is labelled
*restricted/censored*. Handling minutes are partitioned by an exclusive bookkeeping precedence:
`CRANE_SHORTAGE` (no crane assigned) → idle-crane runtime reason (`YARD_STORAGE_FULL`,
`CARGO_UNAVAILABLE`, `SEQUENCING_ASSIGNED_IDLE`) → binding rate caps of the working batches
(`YARD_HANDLING_CONSTRAINED`, `TRANSPORT_CONSTRAINED`, `MULTIPLE_CONSTRAINTS`, otherwise
`AT_CRANE_RATE`) → `UNATTRIBUTED`. This is an accounting convention, not identification of a unique
causal bottleneck when constraints overlap. Productive-capacity-equivalent minutes integrate the
modelled vessel rate relative to `r_ref = max_cranes × 30 × eff(max_cranes)` (55.2 moves/h); they
are a model-equivalent quantity, not causal proof. Reconciliation is exact to ~1e-11 min.

**Service compliance.** Every result reports departed vessels, cargo-fulfilled vessels (departed
with every original move done; rollover = unfulfilled), rolled-over containers and moves,
unfinished ship-side moves, `cargo_completion_ratio`, `cargo_fulfillment_complete`, completed-only
mean turnaround (conditional) and restricted observed turnaround. The Step 4 termination vocabulary
is unchanged.

**Engineering measurements.** Per-run cost in the campaign (summary mode, Step 2 validation,
full post-run audits, streamed digests): 11–78 s mean per family × condition under 8-way parallel
execution on 12 logical cores. Digest computation became about 3× faster after switching the
final-state digest to the C JSON encoder (identical bytes, verified). Summary mode wrote about 11 MB
for all 380 runs (one result JSON per run), against roughly 45–74 MB of canonical trace per run in
full mode (heavy: ledger 53 MB, final state 18 MB). The closure leaves clone cost unchanged (Step 4:
1.3 ms at a heavy t ≈ 1500 state).

## 6. Load and capacity arithmetic (inputs only, no simulation)

Mean over the declared development seeds. Ratios are offered ship-side moves per hour divided by
the optimistic crane bound. **Optimistic bounds** assume every crane works on a vessel with at most
two cranes (`N × 30 × 0.92` for even `N`: 110.4 / 165.6 / 220.8 moves/h). They are necessary, not
sufficient, conditions: quay geometry, vessel mix, missing cargo, handling and transport can only
lower them. The geometry-aware bound caps usable cranes at `2 × k`, where `k` is the most vessels
(shortest first) that fit on the quay together. It never binds at 4–8 cranes, except for low at 8
(k = 3, bound 165.6). Windows: (a) first-to-last arrival; (b) (a) plus mean nominal service. Both are
finite-window averages, not stationary arrival rates.

| Family | Vessels | Arrival window (min) | Ship moves (incl. both transshipment lifts) | Offered (a) | Offered (b) | Ratio (a) 4 / 6 / 8 cranes | Ratio (b) 4 / 6 / 8 cranes |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| itp_low | 8 | 2,093 | 4,694 | 141.1 | 119.7 | 1.28 / 0.85 / 0.64 | 1.08 / 0.72 / 0.54 |
| itp_medium | 16 | 2,907 | 9,263 | 204.8 | 180.6 | 1.86 / 1.24 / 0.93 | 1.64 / 1.09 / 0.82 |
| itp_heavy | 24 | 2,789 | 13,879 | 323.6 | 282.6 | 2.93 / 1.95 / 1.47 | 2.56 / 1.71 / 1.28 |
| itp_yard_bottleneck | 18 | 2,941 | 10,785 | 228.1 | 202.4 | 2.07 / 1.38 / 1.03 | 1.83 / 1.22 / 0.92 |

Per-seed ranges are wide; for example heavy (a) at 4 cranes runs from 1.75 to 7.36. The yard has
12 blocks of 2,200 TEU (26,400 TEU). Handling is 60 moves/h per block (720 total), or 30 (360 total)
in the bottleneck family; with landside demand the ship-side share is 48 (24) moves/h per block.
Initial yard occupancy is 13,196 TEU (reference) and 18,472 TEU (bottleneck). Cumulative episode TEU
is not simultaneous occupancy: the observed peak block occupancy stayed ≤ 0.58 under balanced yard
(≤ 0.71 in the bottleneck family) and reached 1.0 under first fit.

## 7. Pre-run plan

Plan `experiments/step4_closure/dafac445c345/plan.json`, SHA-256
`dafac445c345458d55a2662d00c871e8b00666bb409786d1f49169d47bafd624`. It was written by `--plan`
before any result existed and records:

* source run `dev_f5789d8c91_1ee66026` (manifest SHA-256);
* every scenario file's SHA-256 and physical fingerprint;
* the five conditions and the immutable reference values;
* the pending choices, measures and definitions;
* the comparison approach (paired percentile bootstrap, 10,000 resamples, seed 20261012);
* the decision-support criteria.

No plan deviation occurred (`plan_history.jsonl` has one entry). Planned unique runs: **380**,
counted programmatically (first_fit/4 = 80, balanced/4 = 80, balanced/6 = 80, balanced/8 = 80,
balanced/4/working = 60).

## 8. Coverage and results (development only; FCFS fixture; nothing selected)

**Coverage: 380 / 380 runs executed.**

* Every run passed all post-run audits (invariants, ledger replay, realized schedule, Project 01
  projection).
* 0 validator rejections, 0 FAILED, 0 DEADLOCK, 0 storage-capacity violations.
* One distinct trace digest per run.
* Every source file matched its recorded SHA-256 and physical fingerprint.
* Base exogenous fingerprints are identical across the conditions of each scenario;
  resolved-physics fingerprints differ per fleet and efficiency basis.
* Phase reconciliation error ≤ 1.8e-12 min; handling-cause reconciliation error ≤ 1.5e-11 min.

Immutable report: `experiments/step4_closure/dafac445c345/reports/report_e8e00de772d9.json` (+ `.md`).

**Comparison horizon.** Every condition uses the same per-scenario `T_end` (last arrival + 10,080 min),
the same drain rule and the same FCFS fixture. Departure counts and fulfilled cargo are the primary
interpretive constraints. Mean turnaround is never ranked across conditions whose departures or
rollover differ without saying so.

### 8.1 Family × condition

| Family | Condition | Status | Departed | Cargo-fulfilled | Rolled over (containers) | Unfinished ship moves | Completion ratio | D24 T_end-censored mean turnaround (min) | Mean / P95 berth wait (min) | Realized/nominal median (P90) | Crane productive | Busiest-block ship share | Busiest block busy |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | --- |
| low | first_fit/4 | 10 COMPLETED | 80/80 | 80/80 | 0 | 0 | 1.000 | 1,953 | 318 / 1,302 | 4.60 (7.55) | 0.73 | 0.49 | B01 0.94 |
| low | balanced/4 | 10 COMPLETED | 80/80 | 80/80 | 0 | 0 | 1.000 | 976 | 79 / 485 | 2.26 (3.64) | 0.43 | 0.09 | 0.23 |
| low | balanced/6 | 10 COMPLETED | 80/80 | 80/80 | 0 | 0 | 1.000 | 805 | 46 / 300 | 2.16 (2.36) | 0.29 | 0.09 | 0.22 |
| low | balanced/8 | 10 COMPLETED | 80/80 | 80/80 | 0 | 0 | 1.000 | 795 | 45 / 299 | 2.14 (2.34) | 0.22 | 0.09 | 0.22 |
| medium | first_fit/4 | 28 COMPLETED, 2 TRUNCATED (landside backlog only) | 480/480 | 466/480 | 401 | 0 | 0.999 | 3,874 | 1,917 / 5,803 | 5.66 (8.89) | 0.87 | 0.45 | B01 1.00 |
| medium | balanced/4 | 30 COMPLETED | 480/480 | 466/480 | 322 | 0 | 0.999 | 1,844 | 764 / 2,585 | 3.03 (4.73) | 0.75 | 0.09 | 0.32 |
| medium | balanced/4/working | 30 COMPLETED | 480/480 | 466/480 | 322 | 0 | 0.999 | 1,845 | 764 / 2,582 | 3.04 (4.74) | 0.75 | 0.09 | 0.32 |
| medium | balanced/6 | 30 COMPLETED | 480/480 | 478/480 | 117 | 0 | 1.000 | 1,268 | 446 / 1,521 | 2.24 (3.10) | 0.53 | 0.09 | 0.30 |
| medium | balanced/8 | 30 COMPLETED | 480/480 | 479/480 | 77 | 0 | 1.000 | 1,149 | 378 / 1,298 | 2.20 (2.50) | 0.40 | 0.09 | 0.30 |
| heavy | first_fit/4 | 30 TRUNCATED (28 ship work unfinished, 2 landside only) | 617/720 | 570/720 | 1,842 | 46,503 | 0.887 | 5,849 | 4,021 / 9,893 | 5.90 (8.54) | 0.97 | 0.40 | B01 0.99 |
| heavy | balanced/4 | 30 COMPLETED | 720/720 | 682/720 | 1,567 | 0 | 0.996 | 3,196 | 2,045 / 5,035 | 3.37 (4.94) | 0.93 | 0.11 | 0.36 |
| heavy | balanced/4/working | 30 COMPLETED | 720/720 | 681/720 | 1,603 | 0 | 0.996 | 3,198 | 2,047 / 5,003 | 3.40 (4.98) | 0.93 | 0.11 | 0.36 |
| heavy | balanced/6 | 30 COMPLETED | 720/720 | 695/720 | 795 | 0 | 0.998 | 2,098 | 1,243 / 3,168 | 2.30 (3.32) | 0.78 | 0.09 | 0.40 |
| heavy | balanced/8 | 30 COMPLETED | 720/720 | 709/720 | 327 | 0 | 0.999 | 1,819 | 1,042 / 2,801 | 2.25 (2.49) | 0.61 | 0.09 | 0.40 |
| bottleneck | first_fit/4 | 10 TRUNCATED (ship work unfinished) | 112/180 | 108/180 | 205 | 36,310 | 0.662 | 7,642 | 5,018 / 10,659 | 10.36 (14.42) | 0.98 | 0.32 | B01 1.00 |
| bottleneck | balanced/4 | 10 COMPLETED | 180/180 | 173/180 | 248 | 0 | 0.998 | 3,426 | 1,856 / 4,812 | 4.58 (6.45) | 0.93 | 0.11 | 0.54 |
| bottleneck | balanced/6 | 10 COMPLETED | 180/180 | 178/180 | 47 | 0 | 1.000 | 2,667 | 1,390 / 3,572 | 3.41 (4.87) | 0.86 | 0.10 | 0.61 |
| bottleneck | balanced/8 | 10 COMPLETED | 180/180 | 180/180 | 0 | 0 | 1.000 | 2,400 | 1,225 / 3,003 | 3.27 (3.89) | 0.69 | 0.09 | 0.61 |

Column conventions:

* Berth waiting of a never-berthed vessel is counted until the run stop (restricted).
* Realized/nominal uses departed vessels only.
* Crane productive = productive crane-minutes / (cranes × run length).
* The completed-only mean turnaround (conditional on departure) is in the report JSON; it is not
  used to rank conditions with different departure counts.

### 8.2 Handling-time bookkeeping shares (exclusive precedence; UNATTRIBUTED = 0 everywhere)

Order of each cell: first_fit/4 → balanced/4 → balanced/6 → balanced/8.

| Family | Crane shortage | Yard handling constrained |
| --- | --- | --- |
| low | 0.24 → 0.18 → 0.01 → 0.00 | 0.58 → 0.18 → 0.26 → 0.26 |
| medium | 0.36 → 0.34 → 0.08 → 0.00 | 0.45 → 0.12 → 0.27 → 0.32 |
| heavy | 0.41 → 0.38 → 0.12 → 0.00 | 0.41 → 0.09 → 0.25 → 0.34 |
| bottleneck | 0.45 → 0.40 → 0.14 → 0.00 | 0.43 → 0.35 → 0.56 → 0.66 |

The full share vectors (transport, multiple constraints, at crane rate, idle-crane reasons) per
family × condition are in the report JSON.

### 8.3 Paired contrasts (per-seed differences; mean [95 % percentile paired bootstrap])

| Contrast | Family (seeds) | Departed | Cargo-fulfilled | Unfinished moves | D24 total turnaround (min) | Berth wait total (min) | Busiest-block share |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 balanced − first fit (4 cranes) | low (10)* | 0 | 0 | 0 | −7,812 [−8,630, −7,132] | −1,910 [−2,267, −1,546] | −0.40 [−0.42, −0.38] |
| | medium (30) | 0 | 0.00 [−0.23, 0.23] | 0 | −32,473 [−34,043, −30,980] | −18,449 [−19,718, −17,235] | −0.36 [−0.37, −0.35] |
| | heavy (30) | +3.43 [2.87, 4.00] | +3.73 [3.07, 4.43] | −1,550 [−1,822, −1,275] | −63,680 [−65,725, −61,650] | −47,440 [−49,182, −45,713] | −0.28 [−0.30, −0.27] |
| | bottleneck (10)* | +6.80 [6.10, 7.50] | +6.50 [5.80, 7.30] | −3,631 [−3,963, −3,292] | −75,889 [−78,987, −72,726] | −56,914 [−59,923, −53,858] | −0.21 [−0.22, −0.20] |
| C2 balanced 6 − 4 cranes (different fleet) | low (10)* | 0 | 0 | 0 | −1,370 [−1,864, −872] | −269 [−552, −64] | 0.00 |
| | medium (30) | 0 | +0.40 [0.13, 0.73] | 0 | −9,218 [−10,264, −8,110] | −5,083 [−5,837, −4,307] | 0.00 |
| | heavy (30) | 0 | +0.43 [−0.10, 0.97] | 0 | −26,342 [−27,803, −24,769] | −19,243 [−20,439, −17,928] | −0.02 |
| | bottleneck (10)* | 0 | +0.50 [0.00, 1.10] | 0 | −13,668 [−15,160, −12,122] | −8,383 [−9,801, −6,945] | −0.01 |
| C2 balanced 8 − 4 cranes (different fleet) | low (10)* | 0 | 0 | 0 | −1,449 [−1,995, −902] | −271 [−554, −66] | 0.00 |
| | medium (30) | 0 | +0.43 [0.17, 0.77] | 0 | −11,130 [−12,595, −9,642] | −6,171 [−7,216, −5,139] | 0.00 |
| | heavy (30) | 0 | +0.90 [0.27, 1.57] | 0 | −33,037 [−35,109, −30,793] | −24,069 [−25,691, −22,295] | −0.02 |
| | bottleneck (10)* | 0 | +0.70 [0.20, 1.30] | 0 | −18,469 [−21,221, −15,457] | −11,362 [−13,576, −8,912] | −0.01 |
| C3 working − assigned (4 cranes) | medium (30) | 0 | 0 | 0 | +12 [−66, 89] | +4 [−47, 54] | 0.00 |
| | heavy (30) | 0 | −0.03 [−0.10, 0.00] | 0 | +54 [−133, 258] | +46 [−88, 193] | 0.00 |

\* 10-seed families: intervals are exploratory/unstable. All intervals are development-only and
conditional on the FCFS fixture. None is a significance claim. C2 varies physical infrastructure, not
berth coordination.

## 9. Interpretation (development diagnosis only)

1. **Does busy-block concentration diminish under balancing?** Yes.
   * The busiest block's share of ship-side moves falls from 0.32–0.49 under first fit to 0.09–0.11
     (perfectly even over 12 blocks would be 0.083).
   * The busiest block's busy fraction falls from 0.94–1.00 to 0.23–0.61.
2. **First fit is the main cause of the Step 4 truncations.**
   * At 4 cranes, every heavy and bottleneck first-fit run truncated: heavy 617/720 departed with
     46,503 moves unfinished; bottleneck 112/180 with 36,310.
   * Under balancing at the same 4 cranes, every run completed with all vessels departed.
   * The two medium first-fit truncations were landside-only: all vessels departed, and the release
     backlog at the concentrated block ran past `T_end`.
3. **Crane scarcity remains under balancing at 4 cranes.**
   * The offered load exceeds the optimistic 4-crane bound in every family (ratios 1.08–2.93 on mean
     windows).
   * Realized service stays 2.3–4.6× nominal (median).
   * Crane-shortage time is 18–40 % of handling time, and crane productive utilization is 0.75–0.93
     in medium, heavy and bottleneck.
   * Departures complete, but **cargo is not always fulfilled**. In heavy, 1,567 containers rolled
     over and 682/720 vessels were fulfilled; in medium 322 rolled over; in the bottleneck family 248.
   * The rolled-over containers are load cargo that was still unavailable 240 min after the outbound
     vessel's other work ended, typically because its inbound vessel was still queued.
4. **The yard-bottleneck family is a genuine handling bottleneck, distinct from the crane fleet.**
   * As cranes increase, its yard-handling-constrained share rises (0.35 → 0.56 → 0.66) while crane
     shortage vanishes.
   * Its busiest block is busy 0.54–0.61 of the time, against 0.30–0.40 for heavy, and its
     realized/nominal ratio stays the highest of any family.
   * Storage never blocked a crane in any balanced run.
   * Under first fit, its constraint is dominated by concentration.
5. **4 / 6 / 8 cranes (different fleets).**
   * More cranes reduce waiting, turnaround and rollover: heavy rollover falls 1,567 → 795 → 327 and
     bottleneck rollover 248 → 47 → 0.
   * Crane utilization falls accordingly (heavy 0.93 → 0.78 → 0.61).
   * The checklist's offered-load criterion (< 0.9) holds only for low at 6 and 8 cranes and medium at
     8 (window b).
   * Every balanced run completed at every fleet size.
6. **Efficiency basis (C3).** `working` versus `assigned` makes no material difference: the paired
   intervals include 0. Two assigned cranes rarely sit on a vessel with only one startable batch
   under these rules.

**Limitations.**
* Only one berth rule (the FCFS fixture) was used.
* The physics is synthetic, uncalibrated and only partially approved.
* Only development seeds were used, and intervals are conditional on them.
* The handling-cause partition is bookkeeping, not causal attribution.
* Capacity bounds are optimistic.
* Nothing here measures coordination.

## 10. Decision support (reported, not chosen)

| Question | Evidence | Decision owner |
| --- | --- | --- |
| Approve AM-01 (common balanced P_y)? | C1: removes all truncations at 4 cranes, even yard use; same primitive for every arm | user |
| Keep 4 cranes as the reference fleet? | 4 cranes: every balanced run completes, but offered load exceeds the optimistic bound in every family and up to 1,567 containers roll over (heavy). 6/8 cranes reduce rollover and waiting at lower utilization | user (any change = explicit pre-validation physics amendment with a new resolved-physics fingerprint) |
| Approve D15 = 10 and D17 = 240? | no evidence against; D17 drives the rollover counts above | user |
| Approve R5 release admission? | needed for physically valid release inventory; explains the landside-only truncations under first fit | user |
| Is rollover of this size acceptable for primary families? | heavy balanced/4: 0.996 cargo completion, 38/720 vessels unfulfilled | user (may affect how S1/S2 KPIs must report cargo fulfilment) |
| Remaining 29 PROPOSED coefficients | physics audit §3 | user, before validation |

## 11. Commands (PowerShell, from `integrated-terminal-pilot`)

```powershell
python scripts/run_step4_closure_campaign.py --plan
python scripts/run_step4_closure_campaign.py --dry-run
python scripts/run_step4_closure_campaign.py --progress --resume
python scripts/run_step4_closure_campaign.py --progress --resume --shard 0/8
python scripts/run_step4_closure_campaign.py --report
python scripts/run_integrated_smoke.py --family itp_heavy --yard-policy yard_occupancy_balance_v1 --crane-count 6 --trace-mode summary
```

## 12. Degenerate equivalence after the closure

Re-run on 2026-10-12 after all closure changes: **80/80 pass** (30 medium, 30 heavy, 10 low, 10
bottleneck) against Project 03 `DynamicBAPEnv` + `online_fcfs_action`. Max errors: position 0.0 m,
start time 1.1e-13 min, occupancy minus nominal 4.5e-13 min, total waiting 3.6e-12, total
turnaround 9.1e-13, identical to Step 4. The diagnostic overrides do not touch the degenerate
reference profile. Report: `experiments/step4_equivalence/eq_20261012T150636Z/report.json`.
