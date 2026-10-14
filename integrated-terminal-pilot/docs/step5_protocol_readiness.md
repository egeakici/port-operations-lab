# Step 5 Protocol Readiness

Status of the scientific protocol at the end of Step 5 (2026-10-13). This document approves
nothing. It lists what is approved, what is pending, what the user must review before any
validation comparison, and what follows from proceeding with provisional values.

```text
STEP5_IMPLEMENTATION       = COMPLETE (adapters, gates, tests, development smoke; see step5_independent_benchmark.md)
POLICY_COMPATIBILITY       = A1 PASS, A2 PASS, A3 train-seed 11/23/37 PASS (medium/heavy checkpoints);
                             tiny checkpoints BLOCK (no eligible Project I family)
SCIENTIFIC_PROTOCOL_LOCK   = BLOCKED  (29 register records PROPOSED_PENDING_REVIEW, AM-01 pending,
                                       cargo-compliance criterion pending)
VALIDATION AUTHORIZED      = NO (requires explicit user approval of the items in section 3)
```

The lock state is computed from the repository at run time
(`integrated_terminal_pilot.benchmark.profiles.approval_state()`) and is written into every Step 5
run manifest as `scientific_protocol_lock`.

## 00. Update 2026-10-14 — Step 6 implemented (current state)

```text
STEP6_IMPLEMENTATION      = COMPLETE (B1, B2, B2-T, A1n; gates G6-01..G6-17 tested)
K5_FIXED_BUDGET           = PROPOSED_NEEDS_OWNER_REVIEW (B2 mean 15.3 s > 2.0 s PROPOSED trigger)
SCIENTIFIC_PROTOCOL_LOCK  = BLOCKED ; VALIDATION_AUTHORIZED = NO ; STEP7_STARTED = NO
```

Step 6 status and outcomes:

- **Arms.** Step 6 added the B arms (B1, B2, B2-T) and the A1n control on the primary profile
  ([step6_integrated_coordination.md](step6_integrated_coordination.md)). It changed no approval:
  24 FROZEN / 28 PROPOSED_PENDING_REVIEW, as before.
- **Owner decisions needed before Step 7, in addition to the 28 records and the formal lock:**
  - Q6-1: B1 estimator;
  - Q6-2: forward-model landside rule;
  - Q6-3: K5 budget or cohort cap;
  - Q6-4: B2 inner prediction definitions.

  See [step6_compute_budget_profile.md](step6_compute_budget_profile.md) and
  [step6_development_diagnostics.md](step6_development_diagnostics.md).
- **Step 7 readiness:** not ready.

## 0. Update 2026-10-13 — pre-Step 6 decision package

The owner approved AM-01 … AM-09 and S2-075 on 2026-10-13
([protocol_amendments.md](protocol_amendments.md), [pre_step6_design_decisions.md](pre_step6_design_decisions.md)).
Sections 1–7 below record the state at the **end of Step 5** and are kept for history. Where they
say "pending" for AM-01, D15, D17, R5, the cargo rule or the fleet, this section supersedes them.

```text
STEP5_IMPLEMENTATION          = COMPLETE
PRE_STEP6_IMPLEMENTATION      = COMPLETE (research profile, cargo metric, CARGO-NI helper, control register)
POLICY_COMPATIBILITY          = unchanged (A1, A2, A3-11/23/37 PASS; tiny BLOCK)
STEP6 TECHNICAL READINESS     = READY TO START (after owner review); Step 6 not authorized by this package
SCIENTIFIC_PROTOCOL_LOCK      = BLOCKED
LOCK_REVIEW_READINESS         = NOT_READY (28 register records pending)
VALIDATION AUTHORIZED         = NO
```

### 0.1 Approved now

| Item | Record | Status |
| --- | --- | --- |
| Common balanced P_y for all A/B arms (first fit = diagnostic `P_y_ff`) | AM-01 (+ P3-PY-FF superseded) | APPROVED_IN_EFFECT |
| Eight-crane primary research profile `itp_primary_balanced_qc8_v1`; 4 QC stays the historical v1 reference (S2-019 unchanged); 4/6 QC sensitivity | AM-02 | APPROVED_IN_EFFECT |
| D15 = 10, D17 = 240 min (D17 120/480 sensitivity only) | AM-03 / S2-075 FROZEN | APPROVED_IN_EFFECT |
| R5 execution rule | AM-04 | APPROVED_IN_EFFECT |
| `assigned` efficiency basis | AM-05 | APPROVED_IN_EFFECT |
| CARGO-NI rule (1 pp margin, one-sided 95 % upper bound, nested A3, reference map) | AM-06 | APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED |
| B2 cargo-first lexicographic objective | AM-07 | APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED |
| B2-T matched ablation | AM-08 | APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED |
| 17 PREFIX exact cases accepted (separate from 383 FULL) | AM-09 | APPROVED_IN_EFFECT |

The decision register now holds 24 FROZEN and 28 PROPOSED_PENDING_REVIEW records. The pending
records are listed row by row in
[pre_step6_synthetic_parameter_approval_matrix.md](pre_step6_synthetic_parameter_approval_matrix.md).
None of them was approved.

### 0.2 Machine lock semantics

`benchmark.profiles.approval_state()` computes, at run time:

- the register counts and pending ids (decision register);
- the status of every required control record AM-01 … AM-09 (`configs/protocol/itp_protocol_control_register_v1.yaml`;
  missing or wrong-status records are reported as `control_record_gaps`);
- whether the Step 7 formal lock `protocol_lock_v1.json` exists (it does not, and nothing before Step 7
  writes it).

`lock_review_readiness` becomes `READY_FOR_LOCK_REVIEW` only when no register record is pending and
no control record is missing. `scientific_protocol_lock` stays `BLOCKED` while any blocker exists,
including the absent Step 7 lock. `validation_authorized` is always `false` in code. The Step 7 lock
event is a separate, owner-run procedure (protocol §9).

### 0.3 Comparator map and B2-T (pre-registered)

S1 uses A2 vs A1 and A3 vs A1, with A3 averaged over training seeds within each scenario first and
confidence intervals over scenario seeds. S2 uses B1 vs A1, B2 vs A2, B2-T vs A2 (ablation) and B2 vs
B2-T. Optional B3 is paired with A3 seed by seed. B2-T matches B2 in everything but the score
(turnaround only). A2 vs B2 is a coordination-package contrast. Full text:
[pre_step6_design_decisions.md](pre_step6_design_decisions.md) sections 2 and 4.

### 0.4 Step 6 technical readiness vs Step 7 scientific lock

Step 6 can technically start after owner review. It has the shared adapter, the validator, the
eight-crane profile, the cargo metric and the pre-registered B2/B2-T contract and diagnostics.
Step 7 is blocked by the 28 pending records, by the Step 6 arms and their measured compute budget,
and by the formal lock.

---

## 1. What is approved (state at the end of Step 5)

| Item | Source | Status |
| --- | --- | --- |
| 23 decision-register records | `configs/generator/itp_generator_v1_decisions.yaml` | FROZEN |
| 10 of them user-approved in Step 4 (each with an `approval` block): S2-019, S2-020, S2-021, S2-022, S2-023, S2-031, S2-032, S2-033, S2-034, S2-071A | Step 4 brief section 6; `step4_physics_approval_audit.md` section 1 | FROZEN (unchanged by Step 5) |
| Four quay cranes as the **currently approved v1 reference fleet** (S2-019) | user approval, Step 4 | FROZEN as the reference; not re-selected by any Step 4/5 result |
| Two-crane efficiency 0.92 (S2-071A), `assigned` basis | user approval, Step 4 | FROZEN; the `working` basis remains a closure diagnostic |
| Frozen protocol section 3 P_y = `yard_first_fit_v1` | `scientific_experiment_protocol.md` section 3 | FROZEN default, used by every Step 5 primary development run |
| Primary KPI D24: T_end-censored total turnaround over all vessels | protocol section 7.1 | FROZEN |
| BAP compatibility contract (gates G01-G21, PASS-EXACT / PASS-FORECAST / BLOCK) | `bap_compatibility_contract.md` | FROZEN (Step 1); implemented unchanged in Step 5 |

## 2. What is pending (not approved; exercised only as provisional development values)

| ID | Item | Current execution | Where |
| --- | --- | --- | --- |
| AM-01 | `yard_occupancy_balance_v1` as the common P_y of every arm | **not applied**: `protocol_v1_first_fit` is the default profile; Balanced runs only as the labelled `am01_balanced_diagnostic` profile | `protocol_amendments.md` (approval record: none) |
| D15 | batch size 10 containers of one group | 10 | register S2-075 (PROPOSED) |
| D17 | maximum load / rollover wait 240 min | 240 min | register S2-075 (PROPOSED) |
| R5 | at most one concurrent GATE_OUT batch per block, FIFO | on | `step4_physics_approval_audit.md` section 4 / 7 |
| Physics | multi-crane efficiency for 1, 3, 4+ cranes (S2-071), transport coupling (S2-073), yard coupling (S2-074), drain extension (S2-077), cycle limit (S2-078), export cutoff (S2-079) | as configured | register (PROPOSED) |
| Scenario design | family traffic (S2-010..013), roles (S2-014/015), yard grid and layout (S2-026..028, S2-035, S2-040, S2-041, S2-043), cargo mix and landside timing (S2-050..054, S2-060), seed bands and batch sizes (S2-005, S2-007, S2-008) | as configured | register (PROPOSED) |
| CARGO-RULE | cargo-compliance criterion for arm comparisons (section 4) | metrics reported separately; no criterion applied | this document |
| FLEET | whether the four-crane reference stays the **primary scientific** fleet after the Step 4 closure C2 diagnostics (rollover is significant at four cranes) | four cranes | user decision |

Total: 29 register records PROPOSED_PENDING_REVIEW plus AM-01, R5, CARGO-RULE and FLEET.

## 3. Lock checklist (user review required before any validation comparison)

1. Approve or amend AM-01. If approved, append the approval record to `protocol_amendments.md`
   and switch the default Step 5 profile; the Step 5 code needs no change (profiles are named).
2. Approve or amend D15 = 10, D17 = 240 min and R5. A changed value changes the physics
   fingerprint, so every Step 5 development result produced under the old value is superseded.
3. Approve or amend the remaining PROPOSED physics and scenario-design records (section 2).
4. Confirm the four-crane reference as the primary scientific fleet, or record a pre-validation
   physics amendment naming the new fleet (six/eight-crane runs are different physics, never mixed
   with A-arm contrasts).
5. Approve a cargo-compliance criterion (section 4) **before** validation results are viewed.
6. Confirm the PASS-EXACT scope rule of `step5_bap_compatibility_report.md` section 5 (comparison up
   to the first nominal-semantics divergence) as the operational reading of contract section 5.1.
7. Then (Step 7 start) write `protocol_lock_v1.json` exclusively from a clean worktree, as
   protocol section 9 prescribes.

## 4. Proposed cargo-compliance rule (PENDING USER APPROVAL)

The frozen primary KPI (D24) charges unfinished vessels up to `T_end`, so leaving vessels at the
quay cannot win. It does **not** charge cargo that left without being loaded: a vessel rolled over
by D17 departs and stops accruing turnaround. A berth policy could therefore shorten turnaround by
causing rollover. Step 5 reports, next to every turnaround figure, `vessels_departed`,
`vessels_cargo_fulfilled`, `rolled_over_containers` (and moves), `unfinished_ship_moves_at_stop`,
`cargo_completion_ratio`, completed-only turnaround with its denominator, and the restricted
observed turnaround with its horizon.

Proposed rule (no weighted scalar, no post-hoc threshold):

- **R-CARGO-1.** Every paired turnaround contrast (arm − comparator) is reported together with the
  paired contrasts of `rolled_over_containers` and `unfinished_ship_moves_at_stop` on the same
  scenarios.
- **R-CARGO-2.** A turnaround improvement is called an improvement only if the paired mean change in
  rolled-over containers is not positive with 95 % paired-bootstrap confidence; otherwise it is
  labelled "turnaround gain with cargo loss" and not ranked.
- **R-CARGO-3.** Departure counts are never reported without cargo-fulfillment counts.

If the user prefers a different rule, it must be recorded before validation is generated.

## 5. Consequences of proceeding with the provisional profile

- All Step 5 runs are labelled `development_diagnostic`, carry the exact yard profile, physics
  fingerprint and the approval state at run time, and select nothing.
- Any later change to a pending physics value or to the common P_y supersedes the development
  results; they must not be carried into validation.
- First fit funnels discharge to the lowest-id block (Step 4 closure), which can mask berth-policy
  differences; this is why AM-01 exists. Step 5 does not resolve it and does not choose the yard
  baseline from A-arm outcomes.
- The four-crane reference shows substantial rollover in heavy scenarios (Step 4 closure). With
  the cargo rule pending, A-arm turnaround numbers must not be read as rankings.

## 6. Step 6 / Step 7 readiness

- Step 6 (A1n/B1/B2/B3) can start technically: the shared adapter, the gates and the timing
  profile it needs exist. It must reuse the same `BerthView`, validator and run record.
- Step 7 is **not ready**: it needs every item of section 3. No validation (11M) or test (12M)
  scenario has been generated or read.

## 7. Sources of unresolved uncertainty

- Pending physics coefficients (section 2) directly set realized service and rollover.
- First-fit yard pathology (AM-01).
- Frozen PPO under forecast-substituted occupancy is a distribution shift (contract section 2.1);
  Step 5 measures it in development runs (`ppo_support` diagnostics) but does not validate it.
- PyTorch at inference (2.6.0 CPU) differs from the training environment recorded in the
  checkpoint sidecars (2.14.1+cu130, CUDA). Deterministic CPU inference is repeatable and matches
  Project 03's own `DynamicBAPEnv` inference in this environment bit for bit (PASS-EXACT), but
  equality with the original CUDA training-time inference is not established.

## Step 6 Closure owner approval update — 2026-10-14

Q6-1–Q6-4 and uncapped K5-A are now explicitly approved for the documented
research semantics (AM-10). Provenance and the owner's bounded F3 authorization:
[step6_closure_owner_decisions.md](step6_closure_owner_decisions.md).
F3 has not started: the plan approved at HEAD `76ced62` must be explicitly
relinked to current HEAD `38a4f5c` after review. Source/config and gate hashes
match; no approval transfer is inferred. This resolves the four Q6 owner
questions, not the 28 pending parameter records or formal lock. Validation,
held-out experiments, training and Step 7 remain unauthorized.

The replacement plan `6401af0e2a01...` was subsequently explicitly approved and
F3 started after exact preflight verification. No additional owner confirmation
is needed for unchanged-source administrative steps. The 28 pending parameters,
formal lock, validation and Step 7 boundaries above are unchanged.

The authorized F3 extension completed 12/12 within its resource scope. See
[Step 6 Closure final report](step6_closure_final_report.md) for mixed descriptive
results and all remaining scientific blockers. No validation readiness, primary
CARGO-NI conclusion or Step 7 authorization is inferred from this completion.
