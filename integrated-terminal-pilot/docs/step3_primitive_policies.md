# Step 3 — Primitive Crane & Yard Policies

Package `integrated_terminal_pilot.policies`. Built on the Step 2 stabilization commit
`c42d64c`.

**What this step is:** decision logic only. Policies read an immutable observation and
return a declarative action. They do not mutate state, advance time, reserve capacity,
move containers or create events.

**What it does not do:**
- No kernel, validator, simulation or experimental arm exists or was run.
- Nothing here measures terminal performance. A correct decision is not evidence of
  terminal-wide efficiency.

```text
Step 2 immutable scenario ─┐
Step 4 kernel state ───────┴─> decision-time observation ─> P_c / P_y ─> declarative action
                                                                            │
                                    Step 4 PhysicalActionValidator (authoritative) <─┘
```

## 1. Package

| Module | Content |
| --- | --- |
| `observations.py` | `CraneObservation`, `CraneVesselView`, `CraneView`, `YardObservation`, `YardRequest`, `YardContainerView`, `YardBlockView`, `ObservationError` |
| `actions.py` | `CraneAction`, `CraneAssignment`, `YardAction`, outcome classes, no-action reasons |
| `crane.py` | `GreedyBerthOrderCranePolicy` (P_c) |
| `yard.py` | `FirstFitYardPolicy` (P_y), `OccupancyBalancingYardPolicy` (diagnostic), `eligible_blocks` |
| `registry.py` | `CranePolicy` / `YardPolicy` protocols, `POLICY_REGISTRY`, `create_policy` |

**Dependencies:** the Python standard library only. The package carries a copy of two
`itp_scenario_v1` tables (id patterns, TEU per size); a test pins them equal to
`scenarios.models`. Importing `integrated_terminal_pilot.scenarios` would load the generator
and, through it, SimPy and gymnasium. A test asserts that importing the policies loads none
of Project 01–03, SimPy, Streamlit, gymnasium or PyTorch, and no GPU is used. It imports no kernel
code; `CranePolicy` and `YardPolicy` are structural protocols.

| Policy id | Protocol name | Role | Version |
| --- | --- | --- | --- |
| `primitive_crane_greedy_v1` | P_c | Primitive; identical in every arm (protocol §3, FROZEN). Default crane policy | 1 |
| `yard_first_fit_v1` | P_y | Primitive; identical in every arm (protocol §3, FROZEN). Default yard policy | 1 |
| `yard_occupancy_balance_v1` | — | **Diagnostic**, yard-only. Not P_y and used by no arm | 1 |

`create_policy(policy_id)` rejects unknown ids; it never substitutes another policy.

**BerthPolicy.** The roadmap lists a `BerthPolicy` interface among the Step 3 outputs. It
was deliberately not created here. Its observation contract is the frozen Project 03
`dynamic_obs_v1` adapter, which belongs to Step 5. An interface without that contract would
be an empty placeholder.

## 2. Observations (`itp_crane_obs_v1`, `itp_yard_obs_v1`)

All records are frozen dataclasses of primitives and tuples:
- Lists passed in are copied to tuples.
- Records are sorted by their stable id (`vessel_id`, `crane_id`, `block_id`,
  `container_id`) at construction. Two observations with the same meaning therefore compare
  equal, whatever their input order.
- Construction validates the observation. A malformed observation raises
  `ObservationError` (code `INVALID_INPUT`), so a policy never receives it.

### 2.1 Crane observation

| Record | Fields | Validated |
| --- | --- | --- |
| `CraneObservation` | `time_min`, `vessels`, `cranes`, `decision_id`, `schema_version` | unique ids; a crane assigned to a vessel must be in `vessels`, compatible with it, and agree with the vessel's `assigned_crane_ids` (single owner, spec §4) |
| `CraneVesselView` | `vessel_id`, `phase` (data contract §8 vocabulary), `length_m`, `berth_position_m`, `berth_start_time_min`, `max_cranes`, `remaining_moves`, `assigned_crane_ids`, `priority` | berthed phases need position and start time, and only berthed phases have them; cranes held only in BERTHING_PREP/HANDLING; held ≤ `max_cranes` |
| `CraneView` | `crane_id`, `status` (Project 01 `CraneStatus` values), `assigned_vessel_id`, `nominal_moves_per_hour`, `compatible_vessel_ids` (None = all), `activity` (IDLE/PRODUCTIVE/BLOCKED) | assigned/operating ⇔ vessel set; available/failed/maintenance hold no vessel; unassigned cranes are IDLE |

### 2.2 Yard observation

| Record | Fields | Validated |
| --- | --- | --- |
| `YardObservation` | `time_min`, `request`, `blocks`, `decision_id`, `schema_version` | at least one block, unique ids |
| `YardRequest` | `work_order_id` (`WO-nnnnnn`), `operation_type` (`DISCHARGE` / `GATE_IN` only), `source_location_id`, `containers` | see the rules below |
| `YardContainerView` | `container_id`, `container_group_id`, `container_size`, `size_teu`, `cargo_flow`, `load_state`, `is_reefer`, `is_hazardous`, `origin_vessel_id`, `destination_vessel_id`, `status` | `size_teu` matches the size (20 ft = 1, 40 ft = 2); flow/vessel-link rules of foundation §2.1; `PRE_EPISODE` is not a vessel |
| `YardBlockView` | `block_id`, `status` (open/closed/maintenance), `capabilities`, `allowed_sizes`, `capacity_teu` (operating), `occupied_teu`, `reserved_teu`, `blocked_teu`, `handling_capacity_moves_per_hour`, transfer point | `occupied + reserved + blocked ≤ capacity` (DQ07) |

**`YardRequest` rules:**
- **Containers:** 1 or more, unique ids, one homogeneous group (D15): the same group, size,
  flow, load state, reefer/hazard flags and vessel links.
- **Allowed flows:** DISCHARGE carries import or transshipment cargo from its origin vessel,
  in status `ABOARD_ARRIVED_VESSEL`. GATE_IN carries export cargo in status `AT_GATE`.

Three capacity notions are kept apart:
- **Geometric capacity:** slots. It is not in the observation; Step 2 validated it.
- **Operating storage capacity:** `capacity_teu`.
- **Handling capacity:** `handling_capacity_moves_per_hour`. It is informational only; no
  policy uses it as a storage criterion.

A container listed in a request has not reached the yard. Its status says where it is,
and no destination field exists.

### 2.3 Scenario helpers

`CraneView.from_scenario_crane`, `YardBlockView.from_scenario_block` and
`YardContainerView.from_scenario_container` copy only the allowed static fields of Step 2
records. Status, assignment, occupancy and reservations must be supplied by the caller: the
Step 4 kernel, or the tests' hand-built snapshots.

## 3. Actions (`itp_crane_action_v1`, `itp_yard_action_v1`)

| Action | Fields | Contract |
| --- | --- | --- |
| `CraneAction` | `policy_id`, `time_min`, `action_type` (`ASSIGN_CRANES` / `NO_ACTION`), `assignments` (one `CraneAssignment(vessel_id, crane_ids)` per vessel, in visit order), `releases`, `no_action_reason`, `decision_id` | No crane appears twice. A no-op carries exactly one reason. `releases` exists because spec §7 allows releases at a CRANE decision; P_c never releases |
| `YardAction` | `policy_id`, `time_min`, `work_order_id`, `action_type` (`ALLOCATE_BLOCK` / `NO_ACTION`), `container_ids` (exact members, sorted), `required_teu`, `block_id`, `no_action_reason`, `decision_id`; property `container_count` | No bay, row, tier or slot field exists (G0). A no-op still names the request's containers, so nothing is silently dropped |

**Outcome classes:**

| Class | Meaning |
| --- | --- |
| `VALID_NO_ACTION` | A no-op action with a reason |
| `INVALID_INPUT` | `ObservationError`; no action is produced |
| `PHYSICAL_ACTION_REJECTION` | Reserved for the Step 4 validator; no policy produces it |

Retrying after a resource release is Step 4's responsibility.

**No-action reasons.** Each set is checked in fixed precedence order.
- **Crane:** `NO_ELIGIBLE_VESSEL` → `MAX_CRANES_REACHED` → `NO_AVAILABLE_CRANE` →
  `NO_COMPATIBLE_CRANE`.
- **Yard:** `NO_OPEN_BLOCK` → `NO_SIZE_COMPATIBLE_BLOCK` → `NO_CAPABLE_BLOCK` →
  `INSUFFICIENT_CAPACITY`. The reason names the first filter that leaves no block.

## 4. P_c — greedy by berth order

Protocol §3 (FROZEN): *berthed vessels with remaining work are visited in
`(berth_start_time_min, vessel_id)` order. Each receives available cranes in `crane_id` order
up to `max_cranes`.*

1. **Eligible vessels:** phase BERTHING_PREP or HANDLING, `remaining_moves > 0`, and fewer
   than `max_cranes` cranes (data contract §5 "Allocation").
2. **Free cranes:** status `available`, in `crane_id` order.
3. **Assignment:** for each eligible vessel in visit order, take the free, not yet claimed
   cranes that may serve it (`compatible_vessel_ids` is None or contains the vessel), up to
   `max_cranes − already assigned`.
4. **Result:** the assignments, or `NO_ACTION` with a reason.

Existing assignments are never touched, and a crane is claimed at most once. Ties use
`vessel_id`, then `crane_id`, and no randomness exists. Rail order, travel and collision
avoidance are Project 04 concerns and are not modelled. `home_position_m` is not a
compatibility rule in v1.

**Worked example** (computed by the implementation). At t = 120:

| Vessel | Phase | Berth start | max_cranes | Already holds |
| --- | --- | ---: | ---: | --- |
| V001 | HANDLING | 40 | 3 | QC02 |
| V002 | BERTHING_PREP | 15 | 2 | — |

QC01, QC03 and QC04 are available.
- The visit order is V002 (15) before V001 (40).
- V002 has 2 free places and takes QC01 and QC03.
- V001 has 3 − 1 = 2 free places, but only QC04 remains.
- Result: `ASSIGN_CRANES [(V002, QC01 QC03), (V001, QC04)]`.

## 5. P_y — first fit

Protocol §3 (FROZEN): *the first OPEN block in `block_id` order that supports the batch's
capabilities and size and passes the TEU test.* The TEU test (spec §5.3) is:

```text
capacity_teu − occupied_teu − reserved_teu − blocked_teu ≥ Σ size_teu of the batch   (1e-9 tolerance)
```

**Required capabilities** follow Project 01 `ContainerGroup.required_yard_capabilities`:
- empty containers need `{empty}`;
- otherwise `{general}`, plus `reefer_power` or `hazardous` as flagged.

**One destination per batch.** The batch is never split (spec §6). If no block can take
the whole batch, the result is `NO_ACTION/INSUFFICIENT_CAPACITY`, never a partial
allocation. Step 1 defines no splitting rule, so no splitting algorithm was invented.

**Worked example** (computed by the implementation). Request WO-000017 holds one 40 ft
import, `CNT-001201` (2.0 TEU).

| Block | Capacity | Occupied | Reserved | Available | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| B01 | 2,200 | 2,150 | 49 | 1.0 TEU | rejected: 1.0 < 2.0 (a 20 ft container would fit) |
| B02 | 2,200 | 1,100 | 0 | 1,100 TEU | **chosen** |

Result: `ALLOCATE_BLOCK B02, container_ids (CNT-001201,), required_teu 2.0`.

### 5.1 Diagnostic heuristic (not P_y)

`OccupancyBalancingYardPolicy` (`yard_occupancy_balance_v1`):
- **Candidates:** the same as P_y.
- **Choice:** the lowest `(occupied + reserved + required) / capacity_teu`; ties go to the
  lower `block_id`. `blocked_teu` (0.0 in v1) enters only through eligibility.
- **Status:** a yard-only alternative for diagnostics. It is never the experimental default,
  and it is not an integrated coordinator.

## 6. Storage versus handling

P_y answers one question: *which block can store this batch now?* Handling capacity
(60 moves/h per block; 30 in the bottleneck family) is not a storage admission rule in the
frozen contract. Queuing, rate sharing, congestion and crane blocking are Step 4 physics.

The integration test `test_bottleneck_handling_capacity_does_not_change_storage_choice`
confirms that P_y gives the same choice at 30 or 60 moves/h. No claim is made that the
bottleneck family blocks cranes; Step 4 must measure that.

## 7. Containers, TEU and flows

- **Container identity:** every yard decision names its exact `container_id`s. The batch is
  a processing convenience over those ids (group, count and TEU are derived from the
  members); there are no anonymous counts.
- **TEU:** `required_teu = Σ size_teu`. Tests check that 20 ft = 1 TEU and 40 ft = 2 TEU,
  that container count ≠ TEU, and that a 40 ft container is rejected where only 1 TEU is free.
- **Flows:**
  - *Import and transshipment* reach P_y as DISCHARGE requests from their origin vessel.
    Transshipment keeps both vessel links.
  - *Export* reaches P_y only as a GATE_IN request with status `AT_GATE`. An export that
    is still `EXPECTED_BY_LANDSIDE` cannot form a request (`INVALID_INPUT`), so it can
    never be allocated as if it were already in the terminal.
  - *Loads and landside releases* are never yard decisions, because their source block is
    the container's location (spec §6).
- **G0 fidelity:** the action selects a block only. No bay, row or tier is produced,
  relocations are not modelled, and full yard optimization is not claimed. Project 05 can
  add a slot-level action that refers to the same container ids.

## 8. Information visibility (spec §10)

The view types have **no attribute** for hidden information:
- arrival and announce times, nominal service, workload;
- gate-in and pickup times, weights;
- unavailability windows;
- scenario id, seed and fingerprints.

The brief asked for "source scenario identity" in observations. Frozen spec §10 says scenario
id, seed, split and fingerprints are *never* in observations, so that rule was followed. A
`decision_id` field carries request identity instead.

**Leakage tests:**
- Perturbing hidden fields of a generated scenario (gate-in and pickup times, weights,
  future arrivals) leaves the observations and decisions identical.
- Passing a scenario document to a policy raises `INVALID_INPUT`.
- Policies never mutate the scenario.

`compatible_vessel_ids` is a static scenario field. In v1 it is always null. Step 4 should
restrict it to visible vessels if it is ever populated.

## 9. Project 02 equivalence

Source inspected:
- `mini_port_sim/policies/crane_policy.py`, `yard_policy.py`;
- `processes/crane_dispatcher.py`, `processes/task_process.py`;
- `terminal_core` `Terminal`, `QuayCrane`, `YardBlock`, `ContainerGroup`, `Vessel`.

| Aspect | Project 02 | Project I |
| --- | --- | --- |
| Crane granularity | one crane per READY task: `min(ready tasks, available cranes, max_cranes − current)` | cranes to the vessel up to `max_cranes − current`; batches dispatched by the kernel (D16). **Not capped by ready tasks** |
| Crane candidates | status `AVAILABLE`, `crane_id` (sorted) order | same, plus `compatible_vessel_ids` (absent in Project 01) |
| Vessel order | dispatcher loop over vessels in berthing order, applying each result | `(berth_start_time_min, vessel_id)`; claims are tracked inside one call |
| Mutation | the policy is pure; the dispatcher mutates `Terminal` | the policy is pure; Step 4 executes |
| Yard order and status | `yard_block_ids` (sorted), OPEN only | same |
| Yard capacity | `capacity − occupied − reserved − planned` | `capacity − occupied − reserved − blocked` (planned = Project I reservations) |
| Size | not restricted per block; TEU from the group's size (simulation groups default to 20 ft, so 1 move = 1 TEU there) | `allowed_sizes` per block; actual 20/40 ft TEU per container |
| Identity | anonymous group quantity | exact container ids |

**Equivalence tests** (`tests/integration/test_step3_project02_equivalence.py`):
- Real Project 01 terminals are built through the public API. The unchanged Project 02
  rules run on them, and P_c/P_y run on equivalent observations.
- **Crane:** 6 states agree (single vessel, failed crane, maintenance crane, berth order with
  an existing assignment, scarce cranes across 3 vessels, vessel at max).
- **Yard:** 8 states agree (20/40 ft, occupancy, reservations, exact boundary,
  closed/maintenance, reefer capability, id-versus-insertion order, nothing fits).
- **Documented differences**, tested separately: the ready-task cap, crane compatibility,
  per-block size restriction, blocked TEU, and exact container ids.
- Project 02 was not modified.

## 10. Performance (engineering timings, Windows, CPU, single process; not an SLA)

| Operation | Median |
| --- | ---: |
| P_c decision (4 vessels, 4 cranes) | about 31 µs |
| P_y decision (12 blocks, 10-container batch) | about 55 µs |
| Balancing decision (12 blocks) | about 64 µs |
| Building a yard observation (12 blocks + 7-container batch) from the 16,369-container heavy scenario | about 0.44 ms |

Cost depends on the number of blocks and request members, not on scenario size. Only
decision-relevant records are copied.

## 11. Step 4 integration notes

1. **Building observations:** build them from kernel state, never from the full scenario.
   `remaining_moves` = vessel workload minus completed moves; occupancy, reservations and
   `blocked_teu` come from `YardBlockState`.
2. **CRANE decision:** call P_c once per CRANE decision (spec §7). Apply the
   `CraneAssignment`s only after `PhysicalActionValidator` accepts the whole action.
3. **Yard decision:** call P_y per DISCHARGE / GATE_IN work order at dispatch. On
   `ALLOCATE_BLOCK`, the kernel reserves `required_teu` and starts the batch. On `NO_ACTION`,
   the crane becomes `BLOCKED(YARD_CAPACITY)` or the gate container waits `AT_GATE`, and is
   retried at the next capacity-freeing event (spec §5.3).
4. **Validation:** the validator must re-check everything the policy checked. A well-formed
   action is not a guarantee of legality.

## 12. Limitations

- P_c follows the frozen text. It can give a vessel more cranes than it has startable
  batches (Project 02 would not). Whether that idles cranes is a Step 4 observation.
- No batch splitting exists. A batch larger than any block's free TEU waits.
- Policies cover crane assignment and yard destination only. Berth policies arrive with the
  Step 5 adapter.
- All physical parameters remain PROPOSED (Step 2 decision register: 13 FROZEN, 38 PROPOSED,
  0 BLOCKED). They must be approved before Step 4 freezes physics.
