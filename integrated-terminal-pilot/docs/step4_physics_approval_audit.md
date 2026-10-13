# Step 4 — Physics Approval Audit

**SYNTHETIC — NOT CALIBRATED TO A REAL TERMINAL.**

This audit records which physical values and rules the Step 4 kernel executes, where each one
comes from, which equation uses it, and whether it is approved. Approval of ten reference values
(below) does **not** mean that all physics are approved: 29 decision records remain
`PROPOSED_PENDING_REVIEW`, and several Step 4 execution rules (§4) are interpretations of the frozen
Step 1 text that need explicit user review before any validation comparison.

Register after Step 4: **23 FROZEN, 29 PROPOSED_PENDING_REVIEW, 0 BLOCKED, 0 DEFERRED** (52 records;
before Step 4: 13 / 38 / 0 / 0 over 51 records). The generator parameter values are unchanged, so
the generator-config fingerprint (`f5789d8c91…e9ca179e`), every scenario file and every scenario
fingerprint are unchanged.

## 1. User-approved v1 reference values (Step 4 brief §6)

Approval provenance is stored in the register as an `approval` block on each record
(`approved_by: user`, `approval_source: Project I Step 4 brief, section 6`, `approval_date:
2026-10-09`, `approved_value`, `scope`). The loader now accepts `FROZEN` only for Step 1 FROZEN
values, Step 2 brief process rules, or records with such an approval block
(`scenarios/config.py`); an approved record that is not `FROZEN`, or an incomplete approval, is
rejected (tests `test_approval_record_must_be_complete_and_frozen`,
`test_stabilization_values_are_not_silently_frozen`).

| Approved value (brief name) | Register record / config path | Value | Kernel equation |
| --- | --- | --- | --- |
| quay_crane_count | S2-019 `families.*.terminal.quay_crane_count` | 4 | crane pool size |
| quay_crane_nominal_moves_per_hour | S2-020 `families.*.terminal.quay_crane_moves_per_hour` | 30 moves/h | `crane_rate = nominal × eff(n) × 1.0` |
| max_cranes_per_vessel | S2-021 `families.*.terminal.max_cranes_per_vessel` | 2 | validator `MAX_CRANES_EXCEEDED`, INV03 |
| two_crane_efficiency | **S2-071A** (split from S2-071) `physics_profiles.standard_v1.crane.efficiency.two` | 0.92 | `eff(2)`; two working cranes give 2 × 30 × 0.92 = 55.2 moves/h |
| yard_block_count | S2-022 `families.*.yard.block_count` | 12 | yard layout |
| total_yard_operating_capacity_teu | S2-022 × S2-023 (`families.*.yard.capacity_teu` = 2200) | 26,400 TEU | TEU gate `capacity − occupied − reserved − blocked ≥ batch_teu` |
| normal_yard_block_handling_moves_per_hour | S2-031 | 60 moves/h | `μ_b` of Coupling C |
| bottleneck_yard_block_handling_moves_per_hour | S2-033 | 30 moves/h | `μ_b` (bottleneck family) |
| normal_initial_yard_occupancy_target | S2-032 | 0.50 | generator target (initial inventory) |
| bottleneck_initial_yard_occupancy_target | S2-034 | 0.70 | generator target (bottleneck family) |

No duplicate configuration key was created: every approved value maps to its existing path. The
12-block three-line geometry, 2200 TEU per block, supported sizes (20/40 ft) and the four-crane
baseline are preserved. Six cranes remains a sensitivity option. The ten values stay synthetic.

S2-071 was split because one record covered all four efficiency factors and only the two-crane
factor was approved. The remaining factors (one = 1.0, three = 0.82, four_plus = 0.72) stay
`PROPOSED_PENDING_REVIEW`. With `max_cranes_per_vessel = 2` the three and four-plus factors are
unreachable in the v1 reference configuration.

## 2. Already frozen by Step 1 (unchanged)

| Record | Value | Use in the kernel |
| --- | --- | --- |
| S2-017 / S2-018 (D04) | quay 1200 m, clearance 20 m | Project 03 geometry functions |
| S2-070 (D20, D21) | ServiceConfig(30, 0.5, 20) | nominal service (input only); berthing preparation 30 min and departure preparation 20 min (physical) |
| S2-072 (D19) | productivity 1.0 | Coupling A |
| S2-076 (D18) | H = 240 min | announcement at `max(0, arrival − 240)` for arrivals > 0 (Project 03 rule) |
| S2-080 | degenerate profile | equivalence test |

## 3. Remaining provisional, runtime-relevant parameters

All values are the documented Step 2 provisional values. They are used for Step 4 development and
physical correctness testing only. No validation or held-out comparison was run.

| Decision | Parameter (path) | Value, unit | Source | Equation in the kernel | Status | Effect on physics / fingerprints | Recommended v1 handling | Material ambiguity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S2-073 (D10) | transport speed `transport.speed_m_per_min` | 250 m/min | Step 1 PROPOSED | `cycle = 2 d / v + handover` | PENDING | Binds a 30 moves/h crane beyond ~750 m (4 units); physics + physics fingerprint | approve or replace before validation | no (mechanism frozen) |
| S2-073 | handover `transport.handover_min` | 2 min | Step 1 PROPOSED | as above | PENDING | as above | approve | no |
| S2-073 | units per crane `transport.units_per_crane` | 4 units | Step 1 PROPOSED | `transport_rate = units × 60 / cycle`; ship demand `= min(crane_rate, transport_rate)` | PENDING | transport shortfall measured per crane | approve | no |
| S2-074 (D11) | `yard.congestion_rho0` | 0.70 | Step 1 PROPOSED | `g(ρ) = 1` if ρ ≤ ρ0 else linear to `g_min` at ρ = 1 | PENDING | reduces `μ_b` above 70 % physical occupancy | approve | no |
| S2-074 | `yard.congestion_g_min` | 0.50 | Step 1 PROPOSED | as above | PENDING | as above | approve | no |
| S2-074 | `yard.landside_reserved_fraction` | 0.20 | Step 1 PROPOSED | landside guaranteed share of `μ_b g(ρ)` when it has demand; unused share returned | PENDING | ship-side gets 48 moves/h (60 × 0.8) when landside demand exists | approve | no |
| S2-074 | `yard.gate_flow_demand` | `block_handling_capacity` | Step 1 PROPOSED | each landside batch demands `μ_b` | PENDING | all landside batches of a block share equally | approve; see rule R5 (§4) | **yes** (concurrency, §4 R5) |
| S2-075 (D15) | `work.batch_size_containers` | 10 containers | Step 1 PROPOSED, **confirm at Step 4** | batch of ≤ 10 containers of one group, one source, one destination | PENDING | batch duration, reservation size, P_y granularity | **confirm 10** (no Step 4 evidence argues against it; must not be tuned later) | no |
| S2-075 (D17) | `work.max_load_wait_min` | 240 min | Step 1 PROPOSED, **confirm at Step 4** | rollover timer after the vessel's last other work | PENDING | resolves cargo waits and crane hold-and-wait | **confirm 240** | no |
| S2-077 (D27) | `episode.max_drain_extension_min` | 10080 min | Step 1 PROPOSED (Project 03 default) | `T_end = last arrival + 10080`; truncation; turnaround censoring | PENDING | heavy and bottleneck development runs truncate (§5); KPI censoring point | review together with §5 | **yes** (§5) |
| S2-078 (D22) | `kernel.same_timestamp_cycle_limit` | 10000 cycles | Step 1 PROPOSED | livelock guard | PENDING | guard only; never reached in valid v1 runs | approve | no |
| S2-071 | efficiency one / three / four_plus | 1.0 / 0.82 / 0.72 | Step 1 PROPOSED | `eff(n)` | PENDING | unreachable with max 2 cranes | approve with sensitivity grid | no |
| S2-079 | `landside.export_cutoff_min` | 360 min | Step 2 provisional | exogenous gate-in times only (DQ11) | PENDING | landside demand timing; exogenous fingerprint | approve (synthetic) | no |
| S2-060 | export lead, import dwell, background pickup | U[0, 2880], U[720, 4320], U[0, 2880] min | Step 2 provisional | exogenous request times | PENDING | landside load, pre-staged inventory | approve (synthetic) | no |
| S2-035, S2-040, S2-041 | block lines 3, spacing 100/40/40/100 m, slot 6.5 × 2.8 m | Step 2 provisional | transfer points → distances (Coupling B) | PENDING (geometry *preserved* per brief, not approved) | distances 100–1308 m | approve | no |
| S2-043 | capabilities `general`, sizes 20/40 ft | Step 2 provisional | yard eligibility (P_y, validator) | PENDING | none in v1 cargo | approve | no |
| S2-050 – S2-054 | cargo composition | Step 2 provisional | exogenous manifests | PENDING | workload split, TEU pressure | approve (synthetic) | no |

Items of the brief §7 that have **no parameter** in the frozen contracts (none was invented):

| Topic | Frozen rule | Kernel behaviour |
| --- | --- | --- |
| Crane setup / travel time | D08: no travel, no setup | none |
| Transfer buffers | spec §5.3: v1 has no quay apron buffer (FROZEN) | a discharge batch starts only with a destination reservation; otherwise the crane is `BLOCKED(YARD_CAPACITY)`; transport is a rate cap, never a storage space |
| Zero-duration events | spec §8.3 | batches ≥ 1 move and rate > 0; preparation 30/20; a forecast that is not > now is a kernel error (G17) |
| Deadlock timeout | spec §8.3 / D27 | no timeout: deadlock = unresolved work, empty valid queue, no startable action |
| Handling-resource sharing | spec §5.3 (FROZEN mechanism) | §4 R5, R7 |

## 4. Step 4 execution rules that interpret frozen text (review requested)

| ID | Rule | Basis | Why it was needed | Material? |
| --- | --- | --- | --- | --- |
| R1 | `eff(n)` uses the number of cranes **assigned** to the vessel; an assigned crane without work contributes no capacity | spec §5.1 ("n_v cranes currently assigned"), D09 | brief §19 asked to verify | yes — a vessel holding two cranes with one startable batch works it at 27.6 moves/h |
| R2 | D16 at batch-start level: a load batch may start when every discharge batch of the vessel has started, or when the unstarted ones are blocked by yard capacity | D16 text | "no discharge batch can start" is ambiguous when the last discharge batch is in progress on another crane | minor (tail of discharge, multi-crane only) |
| R3 | Batch membership: discharge groups in group-id order, containers in id order; loads by (group, source block); releases FIFO per block; gate receipts FIFO per group | D15 (one group/source/destination) | D15 fixes size, not order | no |
| R4 | Dispatch order within a timestamp: landside releases → ship-side (vessels by berth start, cranes by id) → gate receipts | spec §7 (order not stated) | determinism; releases free TEU first | minor |
| R5 | **Release admission:** at most one GATE_OUT batch in progress per block; further due imports wait IN_YARD (FIFO) and keep occupying storage. Gate receipts are not limited (they reserve destination TEU at start) | spec §7.3 "start when block capacity allows"; §5.4 a landside batch demands the whole `μ_b`; T7 frees storage at release *start* | with unbounded concurrent releases, hundreds of containers were "being retrieved" from one block while new cargo took their storage — Project 01's validator rejected the state (7,859 TEU attributed to a 2,200 TEU block) | **yes** |
| R6 | `yard.constraints_enabled = false` switches off Coupling C rate effects (every flow gets its demand); the TEU storage gate stays active | spec §5 (couplings individually disableable) | storage conservation is not a rate coupling | no (degenerate test only) |
| R7 | Landside processor sharing is computed exactly with a per-block virtual clock (equal per-flow rates) | spec §5.3 proportional sharing with equal demands | performance; exact, not an approximation (`allocate_block` ≡ `share_block_capacity`, tested) | no |
| R8 | Rollover timer starts when the vessel's last *other* work completes (all discharge done, nothing in progress, no load in the yard) and restarts after each newly available load | D17 + foundation §4.7 | the two texts differ when discharge is yard-blocked | minor |
| R9 | A landside receipt/release of a non-head batch carries no queued completion event (only the next-to-finish batch of a block does) | §8.4 | performance; exact | no |

## 5. Observed physical consequences that need a decision before Step 5

These are Step 4 measurements on development seeds (FCFS fixture + P_c + P_y, standard physics);
they are not experimental results.

1. **First-fit concentration.** P_y (FROZEN, protocol §3) sends every discharge and gate receipt
   to the lowest-id block with free TEU. That block's handling capacity (60 moves/h, 48 ship-side
   with landside demand; 30/24 in the bottleneck family) then caps terminal-wide discharge,
   regardless of the crane fleet. Crane capacity lost to the yard share: 4.0k (low), 8.1k
   (medium), 7.8k (heavy), 15.2k (bottleneck) moves per episode.
2. **Drain truncation.** With realized service about 5× nominal, `itp_heavy` and
   `itp_yard_bottleneck` seed 10,000,000 end `TRUNCATED_DRAIN_LIMIT` (19/24 and 10/18 vessels
   departed; 2,514 and 3,495 ship-side moves unfinished). Every vessel is still included in KPIs, censored at `T_end` (D24).
3. Neither is a kernel defect. Both follow from FROZEN primitives and FROZEN mechanisms with
   PROPOSED coefficients. Whether the primary families should run with these settings (or whether
   `max_drain_extension_min`, the landside rule R5 or the coefficients of S2-073/S2-074 need
   revision) is a user decision **before** validation.

## 6. Decisions changed and preserved

* Changed: statuses of S2-019, S2-020, S2-021, S2-022, S2-023, S2-031, S2-032, S2-033, S2-034
  (→ FROZEN with user approval); S2-071 split into S2-071 (pending) and S2-071A (approved). The
  config loader accepts the optional `approval` field. No parameter value changed.
* Preserved: every other record, every Step 1 decision, the scenario schema, the generator and all
  existing scenario artifacts.

## 7. Step 4 closure update (2026-10-12) — approval-ready entries, still PENDING

The ten values of §1 remain the **only** user-approved physics. Nothing below is approved. Each
entry is written so that a later explicit user approval can be recorded without changing physics
or code behaviour (the kernel already executes exactly these rules).

| Item | Current behaviour (unchanged) | Status | Evidence (closure) | What approval would record |
| --- | --- | --- | --- | --- |
| D15 batch size | `work.batch_size_containers = 10` (S2-075) | PROPOSED_PENDING_REVIEW | no evidence for tuning; must never be tuned for coordination | S2-075 batch part FROZEN with an approval block |
| D17 rollover wait | `work.max_load_wait_min = 240` (S2-075) | PROPOSED_PENDING_REVIEW | rollover now reported as **unfulfilled cargo**, separate from departure (closure §6.5) | S2-075 rollover part FROZEN with an approval block |
| R5 release admission | ≤ 1 GATE_OUT batch per block, FIFO; receipts limited only by atomic TEU reservation | Step 4 execution rule, PENDING review | without it, the Project 01 projection audit rejected a heavy development state (7,859 TEU attributed to a 2,200 TEU block); INV15 now enforces the rule every cycle; pickup delay grows when a block's release stream is busy | record as a frozen v1 execution rule (scope unchanged) |
| R1 efficiency basis | `assigned` (spec §5.1) in the reference | FROZEN by spec text; `working` exists only as a closure diagnostic override | C3 diagnostics compare both | none needed unless the user wants `working` (that would be a spec amendment) |
| AM-01 yard baseline | reference P_y stays `yard_first_fit_v1` | PROPOSED / PENDING USER APPROVAL | C1 diagnostics | [protocol_amendments.md](protocol_amendments.md) checklist |
| Reference crane fleet | 4 cranes (user-approved) | APPROVED; 6 and 8 are development sensitivity only | C2 diagnostics | any change would be an explicit pre-validation physics amendment with a new resolved-physics fingerprint |

D15/D16 labels were audited (closure §5): no Project I file attributes the batch-size rule to D16;
four imprecise "batches dispatched by D16" phrasings were clarified (batches are formed under D15
and sequenced under D16). No dispatch behaviour changed.

## 8. Pre-Step 6 update (2026-10-13) - pointer

The owner approved D15 = 10 and D17 = 240 min (S2-075 FROZEN, AM-03), the R5 execution rule (AM-04)
and the `assigned` efficiency basis (AM-05). The four-crane fleet (S2-019) remains the approved
historical v1 reference. The primary synthetic research profile is the derived eight-crane
`itp_primary_balanced_qc8_v1` (AM-02). Sections 1-7 above are unchanged history. The remaining
provisional parameters are audited row by row in
[pre_step6_synthetic_parameter_approval_matrix.md](pre_step6_synthetic_parameter_approval_matrix.md)
and are still pending.
