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

## 1. What is approved

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
