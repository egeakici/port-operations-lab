# Step 6 — Integrated Coordination Policies

Step 6 implements the coordinated berth decision rules B1, B2 and B2-T, plus the berth-only greedy
control A1n that the frozen 2×2 design needs. All of them run in the same Step 4 kernel, on the
approved primary research profile `itp_primary_balanced_qc8_v1`. Development only: no validation or
test data, no training, no Step 7.

```text
STEP6_IMPLEMENTATION      = COMPLETE (code, gates, tests); final B1/B2 details await owner approval (Q6-1..Q6-4)
B1_COORDINATION           = PASS
B2_SAFE_FORWARD_MODEL     = PASS (observable clone + Step 6 sanitisation; adversarial gate passes)
B2_T_MATCHED_ABLATION     = PASS (one evaluator, byte-identical predictions, selector-only difference)
HIDDEN_FUTURE_GATE        = PASS (5 hidden-truth perturbations; malicious inputs refused)
K5_COMPUTE_PROFILE        = MEASURED (15 predeclared development states)
K5_FIXED_BUDGET           = PROPOSED_NEEDS_OWNER_REVIEW (B2 mean 15.3 s > protocol 5 PROPOSED 2.0 s trigger)
SCIENTIFIC_PROTOCOL_LOCK  = BLOCKED ; VALIDATION_AUTHORIZED = NO ; STEP7_STARTED = NO
```

## 1. What the protocol already specified (source of truth)

| Item | Source | What it says | Step 6 implementation |
| --- | --- | --- | --- |
| A1n | `scientific_experiment_protocol.md` §3 | Greedy minimum *estimated release time* over all legal (vessel, position); ties by FCFS key; estimates from **nominal** service; berth-only; never WAITs; secondary control | `coordination_policies.A1nNominalGreedyPolicy`: estimated release = now + nominal service; key (release, arrival, vessel_id, position) |
| B1 | §3 | Same greedy rule as A1n, with estimates from the **integrated one-step estimator** (crane availability, multi-crane efficiency, transport distance from the candidate position to the vessel's load and preview-discharge blocks, current yard congestion); never WAITs | `B1IntegratedGreedyPolicy` + `B1_ESTIMATOR` (**PROPOSED_STEP6_DETAIL_NEEDS_OWNER_APPROVAL**: §3 delegates the details to Step 6) |
| B2 | §3 | Same candidate set as A2 (all legal + WAIT if legal); each candidate scored by an `observable_clone()` kernel run of the visible cohort to completion with FCFS berth continuation and P_c/P_y; score = visible-cohort total turnaround; tie-break by action index | `SharedRolloutEvaluator` + selector `B2` |
| B2 objective | AM-07 (2026-10-13) | Lexicographic: predicted unfulfilled outbound obligations, then predicted turnaround, then stable tie-break | selector `B2`: key (U, turnaround, action) |
| B2-T | AM-08 | Exactly B2's model, candidates and budget; turnaround-only score | selector `B2-T`: key (turnaround, action). This is the original §3 B2 score |
| WAIT in rollouts | roadmap Step 6 | Same "next revealed decision" semantics as Project 03 `finish_after_wait` | WAIT branch advances to the next berth decision and rolls out every legal assignment there; each selector uses its own key on those branches |
| Information | spec §10 (D26) | Forward model = same kernel on an ObservableClone (hidden vessels and hidden landside events removed); landside forecast rule "PROPOSED: not simulated" | `coordination_view.build_projection` (§3 below); the PROPOSED rule is applied as written (Q6-2) |
| Budget | protocol §5 | Structural budget FROZEN: A2 and B2 evaluate the same candidate set and roll out the same visible cohort to completion under the same continuation rule. If B2's mean decision time exceeds 2.0 s (PROPOSED), a pre-registered cohort cap applies to both A2 and B2 | full-cohort rollout implemented; the cap is **not** applied (owner decision Q6-3) |
| B3 | §3 | Optional, exploratory | not implemented (not required) |

**Conflict with the original text, resolved by amendment.** Protocol §3 gives B2 a
turnaround-only score. AM-07 (dated, approved) changes B2 to cargo-first, and AM-08 keeps the
original score as B2-T. The original rule is therefore preserved as B2-T. The §3 table is not
edited.

## 2. Architecture

```text
TerminalKernel (Step 4, unchanged physics; primary profile: 8 QC, balanced P_y, D15/D17/R5)
  │ advance() → DecisionRequest(BERTH)
  ▼
run_episode(..., berth_observer=coordination_observer(...))       ← additive, optional hook (Step 4 driver)
  │   trusted builder: build_coordination_view(kernel)
  ▼
CoordinationView (frozen dataclasses: BerthView + cranes + visible cargo + blocks + public physics
                  [+ SafeProjection bytes for B2/B2-T])                    — no kernel reference
  │
  ├── B1: adapt_berth_view (G08/G09/G10/G17) → integrated one-step estimate → argmin (release, FCFS key)
  │
  └── B2 / B2-T: SharedRolloutEvaluator.evaluate(view)
          for each candidate (WAIT if legal, then legal assignments, action order):
              fork = projection.fork()     (pickled sanitised state → private kernel)
              apply candidate; continue with FCFS berth + P_c + P_y to visible-cohort completion
              → LeafPrediction(U_pred, turnaround_pred, censored, status, cycles)
          → EvaluationRecord (prediction digest, budget fingerprint)
          selector B2:   min (U_pred, turnaround_pred, action)
          selector B2-T: min (turnaround_pred, action)
  ▼
BerthAction → kernel.apply_berth_action → Step 4 PhysicalActionValidator (identical for every arm)
```

A1n reads only the Step 5 `BerthView`. B1, B2 and B2-T read only the `CoordinationView`. Every
returned action is validated by the unchanged Step 4 validator. A WAIT that is not legal, or any
action outside the legal set, fails the run (gate G19); nothing is repaired and there is no
fallback.

## 3. Shared physics and comparison identity

- Every A and B arm on a scenario runs the same derived eight-crane catalog, the same P_c
  (`primitive_crane_greedy_v1`), the same P_y (`yard_occupancy_balance_v1`), the same D15/D17/R5
  and the same kernel, validator and `T_end`.
- **Comparison fingerprint:** `runner.comparison_fingerprint` contains no arm identity and is
  identical across A1, A1n, B1, A2, B2 and B2-T (tested).
- **Profile guard:** B arms refuse any profile other than the primary profile (tested).
- **Algorithm vs budget fingerprints:** B2 and B2-T have distinct policy ids. They share one
  evaluator version and one budget fingerprint (candidate rule, horizon, WAIT semantics,
  continuation, forecast assumptions, replication count, engineering guard).

## 4. Factor labels (every run record, `step6.factor_labels`)

| Arm | Information | Forward model | Objective | Search budget |
| --- | --- | --- | --- | --- |
| A1 | berth only | none | FCFS rule | none |
| A1n | berth only | nominal one-step estimate | min estimated release | none |
| B1 | integrated current state | integrated one-step estimate | min estimated release | none |
| A2 | berth only | nominal berth rollout (Project 03) | visible-cohort waiting (monotone in turnaround) | full visible cohort |
| B2-T | integrated current state | integrated kernel rollout | predicted turnaround | full visible cohort (protocol §5) |
| B2 | integrated current state | integrated kernel rollout | lexicographic (predicted unfulfilled outbound, predicted turnaround) | identical to B2-T |

## 5. Interpretation (estimands, not results)

- **C1 = B1 − A1:** the information-aware greedy rule versus FCFS. Both the rule and the information differ.
- **C1b = B1 − A1n:** the value of integrated information within a fixed greedy rule. This is a
  protocol primary contrast. It depends on the B1 estimator detail (Q6-1).
- **A2 vs B2:** a *coordination package*: integrated model plus cargo-first objective. It is never a
  pure information-sharing effect (safeguard S2).
- **A2 vs B2-T:** both arms target turnaround, but they still differ in forward-model fidelity and
  in wall-clock compute; protocol §5 fixes only the structural budget.
- **B2 vs B2-T:** the objective effect, conditional on identical candidate evaluations and budget.
- **Cargo comparators (AM-06, unchanged):** B1↔A1, B2↔A2, B2-T↔A2 (ablation), B2↔B2-T.

## 6. Owner decisions required before any locked comparison

| ID | Question | Why it matters |
| --- | --- | --- |
| Q6-1 | Approve `B1_ESTIMATOR` (crane delay rule, preview block = AM-01 balanced order, flow-wise rate = min(crane, transport, congested block share), D16 sequential flows) | Protocol §3 delegates it to Step 6; it defines B1 and contrast C1b |
| Q6-2 | Freeze the spec §10 PROPOSED forward landside rule "not simulated" | Defines what B2/B2-T may assume about future gate-ins and pickups |
| Q6-3 | K5: keep the frozen full-cohort budget (B2 mean 15.3 s, p95 53.9 s on development states) **or** approve a cohort cap for A2, B2 and B2-T alike | Protocol §5 PROPOSED trigger exceeded; heavy/bottleneck B2 campaigns are deferred until decided |
| Q6-4 | Approve the inner prediction definitions (cohort, censoring at inner T_end, unfulfilled = not LOADED/DEPARTED at inner stop, WAIT semantics) | They define B2's predicted cargo and turnaround |

## 7. Limitations

- Predictions are deterministic, single-replication model outputs (`UNCALIBRATED_SYNTHETIC_FORECAST`).
  The model omits future landside requests, so it under-predicts yard pressure from future
  gate-ins and over-holds imports, which are never picked up in the model. Predicted-vs-realized
  errors are reported in [step6_development_diagnostics.md](step6_development_diagnostics.md).
- B2's predicted cargo counts only the known outbound obligations of the visible cohort. It is not
  the full-scenario `R`, which is an end-of-run outcome reported separately.
- Development results are characterization only (no winner, no CI, no CARGO-NI verdict).
