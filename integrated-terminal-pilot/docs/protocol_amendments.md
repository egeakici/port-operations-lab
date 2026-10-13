# Protocol Amendment Register (`itp_protocol_v1`)

Append-only register of proposed and approved amendments to
[scientific_experiment_protocol.md](scientific_experiment_protocol.md). The frozen protocol text is
never edited in place: an amendment records what changes, why, and its approval state. A superseded
rule stays documented; it is marked superseded by a later record, never deleted.

Amendments may be approved only **before** any validation result is read (protocol §9).

---

## AM-01 — Common yard baseline: occupancy balancing for every arm

- **Status:** PROPOSED / PENDING USER APPROVAL
  - *Pointer (2026-10-13):* approved; see "AM-01 APPROVED" below. This 2026-10-12 record is kept as written.
- **Proposed:** 2026-10-12 (Step 4 closure)
- **Affects:** protocol §3 (definition of the common primitive P_y). Physics is unchanged.
- **Approved:** no. Until it is approved, the frozen protocol §3 P_y (`yard_first_fit_v1`) remains the
  experimental default everywhere, including `default_policies()` and
  `simulator.diagnostics.REFERENCE_YARD_POLICY_ID`.

### Proposed text

> For all primary arms A1, A2, A3, B1, B2 and the optional B3, the common yard primitive P_y is the
> Step 3 policy `yard_occupancy_balance_v1`, applied identically in every arm. Among the blocks
> that pass the unchanged Step 3 eligibility tests (OPEN status, size, capabilities, TEU test
> `capacity − occupied − reserved − blocked ≥ required`), it chooses the lowest projected
> occupancy `(occupied_teu + reserved_teu + required_teu) / capacity_teu`; ties go to the lower
> `block_id`. The former P_y, `yard_first_fit_v1`, is retained unchanged as the diagnostic
> reference `P_y_ff`.

### Rationale and limits

- **Same primitive in every arm.** AM-01 changes the *common* operational primitive. It gives no
  arm additional yard knowledge, so it does not create an A/B information difference. Coordination
  still changes berth decisions only.
- **Why.** Step 4 development runs showed that first fit sends every discharge and gate receipt to
  the lowest-id block with free TEU. That block's handling share then caps the whole terminal's
  discharge throughput and makes berth-position effects depend on B01 alone. A common primitive
  with such a pathology could mask real differences between arms.
- **Information.** The balancing rule reads only fields of the Step 3 `YardObservation`: block
  status, capabilities, sizes, capacity, occupied, reserved and blocked TEU, and the request's cargo
  identity and flow. It does not read berth positions, crane state, transport distance, handling
  rates, future gate or pickup truth, or any future terminal state (tested).
- **Not an optimum.** Balancing is a design-motivated pre-validation candidate, not an empirically
  established best rule and not a calibrated terminal yard planner. It may have its own
  shortcomings. For example, it ignores transfer distance and spreads landside work over many blocks.
- **Implementations unchanged.** Both Step 3 policies keep their ids and decision logic; the switch
  is a configuration choice.

### Approval checklist (to be completed by the user)

1. [ ] Review the closure diagnostics ([step4_closure_diagnostics.md](step4_closure_diagnostics.md))
   for C1 (balanced vs first fit).
2. [ ] Confirm that a common balanced P_y is wanted for every arm (A1/A2/A3/B1/B2/B3).
3. [ ] Confirm that first fit is kept as the diagnostic reference `P_y_ff`.
4. [ ] Record the approval below (date, approver, scope).

**After approval (one-line switch, no physics change):** set
`REFERENCE_YARD_POLICY_ID = "yard_occupancy_balance_v1"` in
`src/integrated_terminal_pilot/simulator/diagnostics.py`, and set the `default_policies()` yard
policy to the same id. Then append a record "AM-01 APPROVED" and a record "Protocol §3 P_y
(`yard_first_fit_v1`) SUPERSEDED by AM-01" to this register. Update the Step 3 registry role of
`yard_occupancy_balance_v1` from `diagnostic` to `primitive`, and the role of `yard_first_fit_v1`
to `diagnostic_reference`.

### Approval record

_(none — pending)_

---

# Pre-Step 6 decision package (2026-10-13)

All records below were explicitly approved by the project owner in the 2026-10-13 project conversation
(provenance for every record: "explicit project-owner approval in the 2026-10-13 project
conversation"). No signed document or external calibration source exists, and none is implied.
The machine-readable copy is [`configs/protocol/itp_protocol_control_register_v1.yaml`](../configs/protocol/itp_protocol_control_register_v1.yaml);
D15/D17 are recorded in the decision register (S2-075). These are approvals of **design decisions**.
They do not approve the remaining PROPOSED register records
([pre_step6_synthetic_parameter_approval_matrix.md](pre_step6_synthetic_parameter_approval_matrix.md)),
do not write `protocol_lock_v1.json`, and do not authorize validation, test runs, retraining or Step 6
code. `SCIENTIFIC_PROTOCOL_LOCK` stays **BLOCKED**.

## AM-01 APPROVED — common balanced yard primitive

- **Old status:** PROPOSED / PENDING USER APPROVAL (2026-10-12). **New status:** APPROVED_IN_EFFECT (2026-10-13).
- **Scope:** `yard_occupancy_balance_v1` is the common P_y of A1, A2, A3, B1, B2, B2-T and optional B3,
  including B2/B2-T internal forward models. No policy reads berth, crane, transport or future
  information through P_y; the Step 3 algorithm is unchanged.
- **Value:** P_y = `yard_occupancy_balance_v1`; diagnostic reference P_y_ff = `yard_first_fit_v1`.
- **Affects:** research profiles `itp_primary_balanced_qc8_v1`, `itp_sensitivity_balanced_qc4_v1`,
  `itp_sensitivity_balanced_qc6_v1`; Step 3 registry roles (balanced → `primitive`, first fit →
  `diagnostic_reference`).
- **Implementation note (deviation from the 2026-10-12 "one-line switch").** The original note
  proposed changing `REFERENCE_YARD_POLICY_ID` and `default_policies()`. Following the pre-Step 6
  brief section 5.6, these historical v1 defaults are **not** mutated: they keep reproducing the
  four-crane first-fit Step 4 fixtures, the 80/80 gate and the Step 5 smoke. The approved P_y is
  applied through explicit, versioned research profiles (`benchmark.profiles.RESEARCH_PROFILES`).

## SUPERSEDED_BY_AM-01 — protocol section 3 P_y = `yard_first_fit_v1`

- **Record:** P3-PY-FF. **Old status:** frozen protocol section 3 primary P_y. **New status:**
  SUPERSEDED (2026-10-13) as the *primary experimental* yard primitive only.
- The original text in [scientific_experiment_protocol.md](scientific_experiment_protocol.md) section 3
  stays readable and unedited (append-only pointer added). First fit remains registered, unchanged,
  as diagnostic reference and as the historical v1 reproduction default.

## AM-02 — FLEET-8: versioned eight-quay-crane primary synthetic research profile

- **Status:** APPROVED_IN_EFFECT (2026-10-13).
- **Profile:** `itp_primary_balanced_qc8_v1`. Eight quay cranes `QC01`–`QC08`, derived **in memory**
  from each unchanged source scenario by `simulator.diagnostics.derive_fleet` (`QC05`–`QC08` copy
  the homogeneous source crane record; home positions use the generator's even-spacing rule). The
  derived document is re-validated and re-fingerprinted; its exogenous fingerprint must equal the
  source's. `max_cranes_per_vessel` = 2 (unchanged), two-crane efficiency 0.92 (S2-071A),
  `assigned` basis (AM-05), common P_c `primitive_crane_greedy_v1` and P_y per AM-01.
- **History preserved:** S2-019 (four cranes, approved 2026-10-09) is **not** relabelled. It remains
  the approved historical v1 reference (`itp_v1_reference_qc4_first_fit`, role
  `APPROVED_HISTORICAL_V1_4QC`). The generator config, source scenarios and their fingerprints are
  unchanged.
- **Sensitivity levels:** 4 and 6 cranes (balanced P_y) are predeclared capacity sensitivity
  levels (`SENSITIVITY_ONLY_QC4_QC6`). Each has a distinct resolved-physics fingerprint. They are
  never "losing" arms and never mixed with same-physics S1/S2 contrasts.
- **Safeguard S3 (binding):** the fleet was chosen **before** any eight-crane policy result was
  viewed and is final for this protocol stage. The development recheck is characterization only.
  Fleet size must not change because an A1/A2/A3 ranking changes, because A3 remains out of
  distribution, or because a policy performs poorly. Reopening needs a separately recorded
  **physical invalidity** (systematic drain truncation making the profile unexecutable, deadlock
  from scenario design, validator/invariant failures) and a new owner decision. Code enforces this:
  `benchmark.profiles.assert_primary_profile_unchanged` refuses any automatic primary switch.
- **Not an equipment recommendation:** this is a synthetic research design, not a calibrated or
  optimal real-terminal crane count.

## AM-03 — D15 batch size 10 and D17 rollover wait 240 min

- **Status:** decision register **S2-075** PROPOSED_PENDING_REVIEW → FROZEN with an approval block
  (approval_date 2026-10-13). S2-075 holds exactly these two terms, so it is frozen atomically and
  no unrelated term is approved.
- **Values:** `batch_size_containers = 10` (one group per batch, D15); `max_load_wait_min = 240.0` (D17).
  D16 sequencing and kernel dispatch are unchanged.
- **Pre-registered D17 sensitivity:** 120 and 480 min, with explicit cargo-failure KPIs. These are
  sensitivity levels, not tuning candidates.

## AM-04 — R5 execution rule

- **Status:** APPROVED_IN_EFFECT (2026-10-13). There is no generator parameter: R5 is a kernel
  execution rule (landside release admission). It is checked by invariant INV15 and recorded in
  [step4_physics_approval_audit.md](step4_physics_approval_audit.md).
- **Rule:** at most one concurrent GATE_OUT (release) batch per YardBlock, FIFO. Receipts keep their
  atomic TEU admission. Inventory and reservation invariants are unchanged.

## AM-05 — R1 assigned crane-count efficiency basis

- **Status:** APPROVED_IN_EFFECT (2026-10-13). `assigned` is the reference basis for every profile;
  `working` stays a Step 4 closure diagnostic. No other efficiency coefficient is approved (S2-071
  stays PROPOSED; S2-071A two-crane 0.92 was approved on 2026-10-09).

## AM-06 — CARGO-NI pre-registered analysis rule

- **Status:** APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED (2026-10-13). Binding for Step 7. It
  enters a lock only when Step 7 writes it.
- **Metric:** `itp_outbound_obligation_v1` (`benchmark.cargo`). `N_out(s)` is the number of unique
  original containers committed to outbound loading (export and outbound transshipment, including
  yard-resident exports; never imports, TEU or moves). `U(a, s)` counts those not `LOAD_COMPLETED` in
  the authoritative ledger by the common cutoff `T_end(s)`. `R = U / N_out`, or `NOT_APPLICABLE`
  when `N_out = 0`. Load completion is the primary facet; loaded-but-not-departed is reported
  separately.
- **Rule:** `d_s = R(p, s) − R(c, s)`. Non-inferiority holds if the one-sided 95 % upper bound of the
  across-scenario paired mean of `d_s` is ≤ +0.01. The bound comes from a paired scenario bootstrap
  (10,000 resamples, seed 20261013, 95th percentile). Margin 0.00 is a stricter sensitivity
  analysis. Per-family results are primary; a stratified overall estimate uses equal family weight.
  There is no weighted scalar, and D24 is unchanged.
- **Safeguard S1 (binding) — reference map and nesting:** S1: A2 vs A1; A3 vs A1. S2: B1 vs A1;
  B2 vs A2; B2-T vs A2 (labelled ablation); B2 vs B2-T (objective ablation within the coordinated
  family). Optional B3 is paired checkpoint by checkpoint with the same A3 training seed. A1 is
  never compared with itself. For A3 (and B3), the three training-seed results are averaged
  **within each scenario first**, then confidence intervals are computed over **scenario seeds**.
  Per-seed results are kept and reported. Training seeds are never treated as independent traffic
  samples. A missing seed makes the scenario aggregate missing; survivors are never averaged.
  Unknown pairs fail closed (`benchmark.cargo_ni`).
- **Labels:** a turnaround gain is called cargo-non-inferior only under this rule. Otherwise it is
  `TURNAROUND_GAIN_WITH_UNPROVEN_OR_EXCESS_CARGO_LOSS`.

## AM-07 — B2-OBJECTIVE: cargo-first lexicographic B2

- **Status:** APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED (2026-10-13). Implemented in Step 6 only;
  no B2 code exists.
- **Objective:** lexicographic: (1) predicted unfulfilled outbound obligations, then (2) predicted
  turnaround; deterministic stable tie-break. Predicted cargo loss is a forecast, not observed
  future truth. No utility weights.
- **Safeguard S4 (binding):** in Step 6 development profiling, log how often the cargo term decides
  the choice. In particular, log cases where a one-container predicted cargo difference overrules
  a large predicted turnaround cost. Report the frequency, predicted cargo delta, turnaround
  trade-off and forecast-uncertainty caveats. If this reveals a pathology, propose a pre-registered
  tolerance **before validation**. None may be applied without a new owner decision.

## AM-08 — B2-T: matched turnaround-only ablation

- **Status:** APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED (2026-10-13). Implemented in Step 6 only.
- **Design:** identical to B2 in visible information, integrated forward model, legal candidates,
  horizon, state cloning, continuation policy, deterministic event rules, compute budget and
  tie-break. The **only** difference is the score: predicted turnaround only. Predicted cargo
  outcomes are logged as diagnostics and never rank candidates. Any unmatched element is recorded
  as a design violation, not a finding.
- **Safeguard S2 (binding):** A2 vs B2 is a *coordination-package* contrast (integrated model plus
  cargo-first objective), not a pure information effect. A2 vs B2-T compares the forward model and
  coordination with both arms targeting turnaround; differences in horizon, budget and model
  assumptions must still be examined. B2-T vs B2 is the effect of the cargo-first priority given
  the matched model. B2-T does not isolate every modelling difference by itself.

## AM-09 — EXACT-SCOPE: PREFIX-scoped degenerate equality

- **Status:** APPROVED_IN_EFFECT (2026-10-13).
- **Scope:** Step 5 PASS-EXACT gate, 400 attempts: 383 FULL and 17 PREFIX. A PREFIX case validates
  only decisions strictly before the first nominal-semantics divergence (a vessel berthed before its
  cargo was available: `CARGO_UNAVAILABLE`, rollover). It is never described as whole-episode
  equality. Evidence: [step5_bap_compatibility_report.md](step5_bap_compatibility_report.md) section 5
  and the `exact_gate_*` report.
