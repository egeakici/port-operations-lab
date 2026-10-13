# Pre-Step 6 Design Decisions (2026-10-13)

Human-readable summary of the decision package the project owner approved on 2026-10-13, the four
binding safeguards, the fleet history, and what still blocks validation. The authoritative records
are append-only: [protocol_amendments.md](protocol_amendments.md) (AM-01 … AM-09),
`configs/protocol/itp_protocol_control_register_v1.yaml` (machine-readable) and the decision
register (S2-075).

```text
IMPLEMENTATION (pre-Step 6)  = COMPLETE (profile, metrics, pre-registration, characterization tooling)
STEP 6                        = NOT STARTED (not authorized by this package)
SCIENTIFIC_PROTOCOL_LOCK      = BLOCKED (28 register records pending; Step 7 lock not written)
VALIDATION                    = NOT AUTHORIZED
```

## 1. Decision matrix

| ID | Decision | Old status | New status (2026-10-13) | Where recorded | Boundary |
| --- | --- | --- | --- | --- | --- |
| AM-01 | `yard_occupancy_balance_v1` is the common P_y of every A and B arm (incl. B2/B2-T forward models) | PROPOSED | APPROVED_IN_EFFECT | amendments, control register | No extra information through P_y; first fit kept as `P_y_ff` |
| P3-PY-FF | Protocol section 3 first-fit P_y as primary | FROZEN v1 | SUPERSEDED (by AM-01) | control register | First fit stays registered and reproduces history |
| AM-02 | FLEET-8: versioned primary research profile `itp_primary_balanced_qc8_v1` | — | APPROVED_IN_EFFECT | amendments, control register, `benchmark.profiles` | S2-019 (4 QC) unchanged; 4/6 QC are sensitivity levels |
| AM-03 | D15 batch 10, D17 rollover wait 240 min | PROPOSED (S2-075) | FROZEN with approval (S2-075) | decision register | D16 unchanged; D17 120/480 sensitivity only |
| AM-04 | R5: one concurrent GATE_OUT batch per block, FIFO | execution rule, pending | APPROVED_IN_EFFECT | control register | No generator value exists; INV15 |
| AM-05 | R1: `assigned` efficiency basis | reference, pending | APPROVED_IN_EFFECT | control register | `working` stays diagnostic; S2-071 stays pending |
| AM-06 | CARGO-NI: one-sided 95 % upper bound ≤ +1 pp, paired, nested A3 | proposal | APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED | amendments, `benchmark.cargo_ni` | Analysis rule; D24 unchanged; no scalar |
| AM-07 | B2 objective: lexicographic (cargo, then turnaround) | — | APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED | amendments | Step 6 implementation only |
| AM-08 | B2-T matched turnaround-only ablation | — | APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED | amendments | Step 6 implementation only |
| AM-09 | EXACT-SCOPE: 17 PREFIX cases accepted, separate from 383 FULL | proposal | APPROVED_IN_EFFECT | amendments | PREFIX is never whole-episode equality |

Approval provenance for every row: "explicit project-owner approval in the 2026-10-13 project
conversation". No signed document or calibration source exists.

## 2. The owner's four binding safeguards

**S1 — Explicit reference arms and nesting.** Cargo non-inferiority contrasts use A1 as the
reference for A2 and for A3 (S1). S2 uses each B arm's pre-registered A comparator: B1↔A1, B2↔A2,
and B2-T↔A2 as a labelled ablation. Optional B3 is paired checkpoint by checkpoint with the same A3
training seed. For A3's training seeds 11/23/37, the results are first averaged **within each
scenario**, then paired confidence intervals are computed over **scenario seeds**. Each seed's
result is preserved, and training seeds are never treated as extra independent traffic samples.
Implemented in `benchmark.cargo_ni` (`COMPARATOR_MAP`, `scenario_rates`, `paired_differences`).

**S2 — Control for B2's altered objective.** A2↔B2 is a coordination-package comparison, not a pure
information experiment, because B2 also changes the objective. B2-T (section 4) is pre-registered
now to separate the cargo objective from the forward-model effects. It does not isolate every
modelling difference by itself.

**S3 — Fleet chosen before inspecting eight-crane policy rankings.** The eight-crane primary profile
is final for this protocol stage. The development recheck is characterization only. Fleet size is
not changed because a ranking changes, A3 remains out of distribution, or a policy performs poorly.
Reopening requires a separately recorded **physical invalidity** (systematic drain truncation making
the profile unexecutable, deadlock from scenario design, validator/invariant failures). It also
requires stopping and asking the owner; nothing is auto-tuned. Enforced by
`benchmark.profiles.assert_primary_profile_unchanged`.

**S4 — Cargo-first forecast is uncertain.** B2 stays strictly lexicographic for now. Step 6
development profiling must log how often the cargo forecast is **pivotal**, especially when a
one-container predicted difference overrules a large predicted turnaround cost. It must report the
frequency, the predicted cargo delta, the turnaround trade-off and the uncertainty caveats. A
tolerance may only be proposed (pre-registered) before validation and needs a new owner decision.

## 3. Fleet history: historical four-crane reference vs primary eight-crane research profile

| Profile id | Role | Cranes | P_y | Physics |
| --- | --- | --- | --- | --- |
| `itp_v1_reference_qc4_first_fit` | APPROVED_HISTORICAL_V1_4QC | 4 (S2-019, approved 2026-10-09) | `yard_first_fit_v1` | the generator's v1 source scenarios as stored |
| `itp_primary_balanced_qc8_v1` | **APPROVED_PRIMARY_RESEARCH_QC8** | 8, derived in memory | `yard_occupancy_balance_v1` | resolved-physics fingerprint distinct from 4 QC |
| `itp_sensitivity_balanced_qc4_v1` | SENSITIVITY_ONLY_QC4_QC6 | 4 | balanced | capacity sensitivity level |
| `itp_sensitivity_balanced_qc6_v1` | SENSITIVITY_ONLY_QC4_QC6 | 6, derived in memory | balanced | capacity sensitivity level |

All profiles share `primitive_crane_greedy_v1`, `max_cranes_per_vessel = 2`, two-crane efficiency
0.92, the `assigned` basis, D15 = 10, D17 = 240 min and R5. The generator configuration, the
stored development scenarios and their SHA-256 / fingerprints are unchanged. Derived fleets live
only in memory: `simulator.diagnostics.derive_fleet` copies the homogeneous source crane, assigns
unique ids `QC05…`, and the result is re-validated and re-fingerprinted with an identical exogenous
fingerprint. The historical Step 4/5 paths (`default_policies()`, `REFERENCE_YARD_POLICY_ID`, the
Step 5 `protocol_v1_first_fit` profile) are untouched, so every historical trace still reproduces.
Selection is part of a synthetic research design; it is not a real-terminal equipment
recommendation.

## 4. B2 and B2-T pre-registration (Step 6 implementation only; no code exists)

### B2 — integrated cargo-first lexicographic rollout (AM-07)

- **Information:** the permitted observable terminal state plus admissible projected future events
  only. It never uses hidden truth, the real future gate/pickup schedule or the kernel's event heap.
  It may use crane/yard state visible to a *coordinated* policy under the future Step 6 contract.
  These fields are never exposed to A policies or to the common P_y.
- **Candidates:** the legal berth actions and WAIT from the common validator and geometry.
- **Evaluation:** an integrated forward model on a policy-visible clone/projection
  (`observable_clone`) with the common P_c/P_y.
- **Score:** strictly lexicographic. First minimize **predicted** unfulfilled outbound obligations
  (`itp_outbound_obligation_v1` semantics), then predicted turnaround (exact definition fixed in the
  Step 6 design), then a deterministic stable tie-break. There are no utility weights. The forecast
  cargo loss is an estimate, and its uncertainty is tracked.
- **Budget:** candidate count, depth/horizon, rollout seeds, continuation policy and compute budget
  are fixed before Step 7. B2 never gets more lookahead or stronger physics than B2-T.

### B2-T — required matched objective ablation (AM-08)

B2-T uses the **same visible information**, integrated forward-model implementation, legal
candidates, horizon, state cloning, continuation policy, deterministic event rules, computational
budget and tie-breaking as B2. The only intended difference is the decision score:
**turnaround only**, without the cargo-first priority. Predicted cargo outcomes are logged as diagnostics and do
not rank candidates (except through the unchanged deterministic tie-break contract). Any deviation
from the matched design is recorded as a **violation**, not as a scientific finding.

### Interpretation limits (all three contrasts)

- **A2 vs B2:** integrated coordination plus the modified objective. This is a *coordination-package*
  effect, **not** a pure information-sharing effect.
- **A2 vs B2-T:** the forward model and coordination, with both arms targeting turnaround.
  Differences in horizon, candidate budget and model assumptions must still be examined before
  calling it an isolated information effect.
- **B2-T vs B2:** the effect of adding the cargo-first lexicographic priority, conditional on the
  matched integrated forward model.

### Mandatory Step 6 diagnostic (safeguard S4)

For every decision, record the candidate chosen by B2 and by B2-T and whether the cargo score was
**pivotal**. Also record the number of decisions where a one-container predicted cargo delta
overruled a large predicted turnaround difference, the size of that predicted sacrifice, the
frequency by family, and an uncertainty label (calibrated or uncalibrated; deterministic synthetic
forecasts are never presented as probabilities). This is profiled on development data first. Only
an owner-approved, pre-registered tolerance may change the strict lexicographic score before
validation.

### 2×2 / computation fairness plan (protocol sections 4–5)

The frozen protocol factorizes information access (berth-only vs integrated) against search
(none vs rollout): A1n/B1 (greedy, no search) and A2/B2 (rollout). Its section 5 keeps the
structural budget equal for A2 and B2 and reports wall-clock, never ranking by it. B2-T adds a third
labelled dimension, the objective, without creating a new information level. The Step 6
implementation must label four things separately in every record: (1) information access, (2)
forward-model fidelity (nominal berth-only vs integrated kernel), (3) objective (turnaround vs
cargo-first) and (4) computational budget (candidates, depth, forward simulations, events simulated).
Before allocating a fixed budget, Step 6 must time B2/B2-T. It must record `observable_clone` and
catalog preparation time, the time of each forward evaluation, the candidate count, events
simulated, peak memory and p50/p95/max latency. A2's observed ~2 s heavy decision time
(four-crane Step 5 smoke) is a warning, not a B2 runtime; no B2 cost is claimed before it is
measured. If the protocol's PROPOSED 2.0 s trigger applies, the pre-registered cohort cap applies
to A2, B2 and B2-T alike.

## 5. Cargo rule (AM-06) in one paragraph

`R(a, s) = U(a, s) / N_out(s)` is computed from the ledger: original outbound obligations not
`LOAD_COMPLETED` by `T_end`. For each pre-registered pair, `d_s = R(p, s) − R(c, s)`, with A3/B3
aggregated within scenario first. A paired scenario bootstrap (10,000 resamples, seed 20261013)
gives the one-sided 95 % upper bound, which must be ≤ 0.01. Per-family results are primary. A
turnaround gain without this bound is labelled `TURNAROUND_GAIN_WITH_UNPROVEN_OR_EXCESS_CARGO_LOSS`.
The 0.00 margin is a stricter sensitivity analysis. Absolute rollover and unfinished-move changes are
always reported alongside. D24 is unchanged, and there is no weighted scalar.

## 6. Remaining validation blockers

1. 28 decision-register records remain PROPOSED_PENDING_REVIEW
   ([pre_step6_synthetic_parameter_approval_matrix.md](pre_step6_synthetic_parameter_approval_matrix.md)).
   None was approved by this package.
2. Step 6 (A1n, B1, B2, B2-T, optional B3) is not implemented; the B2/B2-T budget is not yet measured.
3. The Step 7 formal lock (`protocol_lock_v1.json`, clean worktree, protocol section 9) is not written.
4. Validation (11M) and test (12M) scenarios have not been generated, opened or run.

## 7. Fixed no-outcome-selection rule

No development outcome (Step 4 closure, Step 5 smoke, pre-Step 6 characterization) is used to
select A1, A2 or A3. Nor is it used to change the eight-crane primary profile, the common P_y,
D15/D17/R5, the cargo margin, the B2 objective or any checkpoint. Development results are labelled
`DEVELOPMENT_CHARACTERIZATION`. A3 out-of-distribution measurements are reported as
`OUT_OF_DISTRIBUTION_MEASURED` and change nothing.
