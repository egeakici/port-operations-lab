# Container and Yard Foundation

Canonical schemas for containers, container groups, yard blocks, slot
addresses, container lifecycle and the movement ledger. Schema version
`itp_container_yard_v1`.

**Principle:** high-fidelity data contracts now; complex 3D stacking
optimization later. Project I simulates the yard at block level (G0). Every
container is still an individually identified, lifecycle-tracked object, and
the geometry can represent slot-level (G1) yards. Project 05 (Container Yard
Puzzle) can therefore reuse these contracts without breaking changes (§10).

## 1. Relationship to Project 01

| Project 01 concept | Project I use |
| --- | --- |
| `ContainerSize` (`20_ft`, `40_ft`), `ContainerFlow`, `ContainerLoadState`, `YardCapability` | Reused verbatim as field vocabularies |
| `ContainerGroup` (frozen, homogeneous, `quantity`, flow/vessel rules) | Reused as the grouping layer; every container belongs to exactly one group |
| `YardBlock` (TEU per group, reservation → commit) | Reservation semantics reused. Block identity, capacity and capabilities projected for audit. Geometry and handling are new (`YardBlockRecord`) |
| `TaskLocationType` (VESSEL, YARD_BLOCK, GATE) | Reused. Project I adds `TRANSFER` and `EXTERNAL_LANDSIDE` as location kinds for containers only (§4.2), mapped back for audit (data contract §12) |
| No individual container entity exists | `ContainerRecord` is new and adapts all names to Project 01 vocabulary (`container_size`, `load_state`, `flow` values) |

No duplicate container-group model is introduced. Project 01 is not modified.

## 2. ContainerRecord (immutable scenario input)

One record per physical container, created by the Step 2 generator. Field
classes: **Req** required · **Opt** optional · **Der** derived (materialized
and validated) · **Imm** immutable · **Obs** observable to online
decision-makers (and from when) · **Hid** hidden future information.

| Field | Type | Class | Observability | Rule |
| --- | --- | --- | --- | --- |
| `container_id` | str `CNT-\d{6}` | Req, Imm | Obs when its vessel is announced, or at gate-in for an export not linked to an announced vessel, or at t=0 if present | Unique within scenario. Global key `(scenario_id, container_id)`. Never reused, renamed or split |
| `container_group_id` | str | Req, Imm | same as id | Exactly one group (DQ04) |
| `container_size` | `20_ft` \| `40_ft` | Req, Imm | Obs | Only sizes supported by Project 01 (DQ02) |
| `size_teu` | float | Der, Imm | Obs | 1.0 for 20 ft, 2.0 for 40 ft (= `ContainerGroup.teu_per_container`) |
| `load_state` | `laden` \| `empty` | Req, Imm | Obs | Empty ⇒ not reefer, not hazardous (Project 01 rule) |
| `is_reefer`, `is_hazardous` | bool | Req, Imm | Obs | Determine required yard capabilities via the group |
| `gross_weight_kg` | int | Opt, Imm | Obs | Synthetic, within per-size generator bounds; recorded but **not used by v1 physics** (stacking weight rules are DEFERRED to Project 05) |
| `cargo_flow` | `import` \| `export` \| `transshipment` | Req, Imm | Obs | §2.1 |
| `origin_vessel_id` | str or null | Req-if (import, transshipment), else null | Obs | Never a fictional vessel |
| `destination_vessel_id` | str or null | Req-if (export, transshipment), else null | Obs | Different from origin |
| `terminal_entry_mode` | `VESSEL` \| `LANDSIDE` | Der, Imm | Obs | import/transshipment → VESSEL; export → LANDSIDE |
| `terminal_exit_mode` | `VESSEL` \| `LANDSIDE` | Der, Imm | Obs | import → LANDSIDE; export/transshipment → VESSEL |
| `present_at_episode_start` | bool | Req, Imm | Obs at t=0 if true | True only for initial yard inventory |
| `scheduled_gate_in_time_min` | float or null | Req-if (export and not present at start), else null; Imm, exogenous | **Hid** until `GATE_IN_ARRIVAL` | ≥ 0 and ≤ destination vessel arrival − `export_cutoff_min` (Step 2 parameter) |
| `scheduled_pickup_time_min` | float or null | Req-if import, else null; Imm, exogenous | **Hid** until `PICKUP_DUE` | This is the requested `expected_release_time_min`. ≥ origin vessel arrival (or ≥ 0 if present at start) |
| `source_scenario_id` | str | Req, Imm | never in observations | Equals the scenario's `scenario_id` |

`handling_history` is deliberately **not** a stored field. The ledger (§8) is the
single source of handling history, and per-container history is a ledger
query. Actual times (`terminal_entry_time_min`, `actual_release_time_min`) are
mutable state (§4).

### 2.1 Flow rules (DQ03)

| Flow | `origin_vessel_id` | `destination_vessel_id` | Enters by | Leaves by | Initial status options |
| --- | --- | --- | --- | --- | --- |
| IMPORT | required | **null** | vessel discharge | landside pickup | `EXPECTED_BY_VESSEL`, or `IN_YARD` if present at start (then origin vessel is a vessel *outside* the scenario: see below) |
| EXPORT | **null** | required | gate-in | vessel load | `EXPECTED_BY_LANDSIDE`, or `IN_YARD` if present at start |
| TRANSSHIPMENT | required | required, ≠ origin | vessel discharge | vessel load | `EXPECTED_BY_VESSEL`, or `IN_YARD` if present at start |

Initial inventory whose inbound vessel visited **before** the episode is
represented with `present_at_episode_start = true`. For such import and
transshipment containers the origin vessel lies outside the simulated vessel
list. To keep Project 01's flow rule (import needs a source vessel) without
inventing a fictional vessel *visit*, the generator uses the reserved
sentinel id `PRE_EPISODE` for `origin_vessel_id`. `PRE_EPISODE` is not a vessel
record, is not projected to Project 03, and is rejected anywhere a
vessel record is looked up. This is the only allowed sentinel (FROZEN).
Validators treat any other unknown vessel id as `UNKNOWN_REFERENCE`.

## 3. Container groups and reconciliation

A `ContainerGroup` (Project 01 class, unchanged) groups containers sharing
`container_size`, `cargo_flow`, `load_state`, `is_reefer`, `is_hazardous`,
`origin_vessel_id`, `destination_vessel_id`. The generator creates one group
per distinct combination, so groups are maximal and homogeneous (FROZEN).

Reconciliation rules (DQ04, DQ05):

```text
for each group g:
    members(g) = {c : c.container_group_id == g.group_id}
    |members(g)|                       == g.quantity
    Σ c.size_teu over members(g)       == g.total_teu  (== g.quantity × g.teu_per_container)
    every member's size/flow/load_state/reefer/hazard/vessel links == g's fields
every container belongs to exactly one existing group
```

A work order batch takes containers from one group only (D15). Batching is a
processing convenience: it never creates, loses or splits containers. A
batch's `planned_teu` equals the sum of its members' `size_teu`.

## 4. Container operational state and lifecycle

### 4.1 ContainerState (mutable, owned by the kernel)

| Field | Meaning |
| --- | --- |
| `container_id` | key |
| `status` | §4.3 vocabulary (`container_status_v1`) |
| `location` | exactly one location (§4.2); the single authoritative owner |
| `reserved_by_work_order_id` | planned claim by a work order that has not started; never changes location |
| `terminal_entry_time_min` | actual time it entered terminal custody (discharge start or gate arrival); null if not yet or present at start |
| `actual_release_time_min` | actual terminal exit (pickup completion or vessel departure); null until then |
| `rolled_over` | bool; set by rule D17. Status does not change |
| `transition_index` | count of physical transitions so far (ledger idempotency) |

### 4.2 Location kinds

| Kind | `location_id` | Slot fields | Physical meaning |
| --- | --- | --- | --- |
| `VESSEL` | vessel id | null | Aboard that vessel (not yet arrived, arrived, berthed or departed) |
| `TRANSFER` | work order id | null | In a modelled ship↔yard or gate↔yard transaction (crane + transport or yard equipment) |
| `YARD_BLOCK` | block id | `bay`, `row`, `tier` (G1) or all null (G0), plus `slot_resolution` | Stored in the yard |
| `GATE` | gate id | null | Truck at gate, awaiting yard receipt |
| `EXTERNAL_LANDSIDE` | null | null | Outside the terminal on the landside (before gate-in, after pickup) |

`slot_resolution ∈ {"BLOCK_ONLY", "SLOT"}`. In G0 every yard location is
`BLOCK_ONLY` with `bay = row = tier = null`. A container is never given a
fictional slot (DQ19).

### 4.3 Status vocabulary (FROZEN)

| Status | Location kind | Terminal? |
| --- | --- | --- |
| `EXPECTED_BY_VESSEL` | VESSEL (origin, vessel not arrived) | no |
| `ABOARD_ARRIVED_VESSEL` | VESSEL (origin, vessel arrived: waiting or berthed) | no |
| `DISCHARGING` | TRANSFER | no |
| `EXPECTED_BY_LANDSIDE` | EXTERNAL_LANDSIDE | no |
| `AT_GATE` | GATE | no |
| `RECEIVING` | TRANSFER | no |
| `IN_YARD` | YARD_BLOCK | no |
| `RETRIEVING_TO_LANDSIDE` | TRANSFER | no |
| `RELEASED_TO_LANDSIDE` | EXTERNAL_LANDSIDE | **yes** |
| `LOADING` | TRANSFER | no |
| `LOADED` | VESSEL (destination, at berth) | no |
| `DEPARTED_BY_VESSEL` | VESSEL (destination, departed) | **yes** |

Mapping to the conceptual candidates in the Step 1 brief: ANNOUNCED /
ON_INBOUND_VESSEL → `EXPECTED_BY_VESSEL`; ARRIVED_ON_VESSEL →
`ABOARD_ARRIVED_VESSEL`; DISCHARGING + IN_TERMINAL_TRANSFER / IN_TRANSFER →
`DISCHARGING` (one modelled transaction); EXPECTED_LANDSIDE →
`EXPECTED_BY_LANDSIDE`; GATE_RECEIVED → `AT_GATE`; RETRIEVING + LOADING →
`LOADING`; LOADED_ON_VESSEL / LOADED_ON_OUTBOUND_VESSEL → `LOADED`;
DEPARTED → `DEPARTED_BY_VESSEL`. **RESERVED_FOR_VESSEL is not a status.** A
reservation is a plan, and physical status and reservations must stay distinct. It is
represented by `reserved_by_work_order_id` and by `destination_vessel_id`.
Project 01 has no container status vocabulary, so none is contradicted.

### 4.4 Valid transitions

Each row is an atomic transaction boundary: the location changes exactly
once, and the yard counters change in the same step.

| # | From → To | Trigger | Source → destination location | Yard / capacity effect | Timestamp set |
| --- | --- | --- | --- | --- | --- |
| T1 | EXPECTED_BY_VESSEL → ABOARD_ARRIVED_VESSEL | `VESSEL_ARRIVAL` of origin | VESSEL → same VESSEL | none | — |
| T2 | ABOARD_ARRIVED_VESSEL → DISCHARGING | DISCHARGE work order starts (origin vessel in HANDLING) | VESSEL → TRANSFER | destination block `reserved_teu += size_teu` (reservation made at work-order start) | `terminal_entry_time_min` |
| T3 | DISCHARGING → IN_YARD | work order completes | TRANSFER → YARD_BLOCK | `reserved −= size_teu`, `occupied += size_teu`, `occupied_count += 1` | — |
| T4 | EXPECTED_BY_LANDSIDE → AT_GATE | `GATE_IN_ARRIVAL` | EXTERNAL_LANDSIDE → GATE | none | `terminal_entry_time_min` |
| T5 | AT_GATE → RECEIVING | GATE_IN work order starts | GATE → TRANSFER | `reserved += size_teu` | — |
| T6 | RECEIVING → IN_YARD | completes | TRANSFER → YARD_BLOCK | reserved → occupied | — |
| T7 | IN_YARD → RETRIEVING_TO_LANDSIDE | GATE_OUT work order starts (import, pickup due) | YARD_BLOCK → TRANSFER | `occupied −= size_teu`, `occupied_count −= 1` | — |
| T8 | RETRIEVING_TO_LANDSIDE → RELEASED_TO_LANDSIDE | completes | TRANSFER → EXTERNAL_LANDSIDE | none | `actual_release_time_min` |
| T9 | IN_YARD → LOADING | LOAD work order starts (export/transshipment; destination vessel in HANDLING) | YARD_BLOCK → TRANSFER | `occupied −=`, `occupied_count −= 1` | — |
| T10 | LOADING → LOADED | completes | TRANSFER → VESSEL (destination) | none | — |
| T11 | LOADED → DEPARTED_BY_VESSEL | `VESSEL_DEPARTED` of destination | VESSEL → same VESSEL | none | `actual_release_time_min` |

Abort transitions (specified for completeness; **unreachable in v1** because
crane failures are disabled, D19): DISCHARGING → ABOARD_ARRIVED_VESSEL,
RECEIVING → AT_GATE (both release the reservation), LOADING → IN_YARD,
RETRIEVING_TO_LANDSIDE → IN_YARD (both re-occupy the same block). In G1 they
also restore the same slot.

Flow lifecycles:

```text
IMPORT        EXPECTED_BY_VESSEL → ABOARD_ARRIVED_VESSEL → DISCHARGING → IN_YARD → RETRIEVING_TO_LANDSIDE → RELEASED_TO_LANDSIDE
EXPORT        EXPECTED_BY_LANDSIDE → AT_GATE → RECEIVING → IN_YARD → LOADING → LOADED → DEPARTED_BY_VESSEL
TRANSSHIPMENT EXPECTED_BY_VESSEL → ABOARD_ARRIVED_VESSEL → DISCHARGING → IN_YARD → LOADING → LOADED → DEPARTED_BY_VESSEL
(initial inventory starts at IN_YARD and follows the remainder of its flow)
```

### 4.5 Invalid transitions (non-exhaustive, all rejected with `INVALID_STATUS_TRANSITION`)

- Any transition not in T1–T11 or the abort list; skipping `TRANSFER`
  (for example ABOARD_ARRIVED_VESSEL → IN_YARD).
- EXPECTED_BY_VESSEL → DISCHARGING (vessel not arrived or not in HANDLING).
- T7 for EXPORT or TRANSSHIPMENT; T9 for IMPORT (flow rule).
- T9 when the destination vessel is not in HANDLING; T7 before
  `scheduled_pickup_time_min`.
- Any transition out of a terminal status; LOADED → IN_YARD (no restows in v1).
- A vessel entering DEPARTURE_PREP while any container with that vessel as
  origin is not past DISCHARGING (orphaned cargo, Project 01 departure rule).

### 4.6 Reservation rules

- A discharge or gate-receive batch reserves destination TEU at work-order
  start (T2/T5) and commits it at completion (T3/T6). This is Project 01
  `reserve_capacity` → `commit_reservation` semantics, keyed by
  `work_order_id`.
- Reservations never change a container's location or status, and never
  count as occupancy.
- Load work orders do not reserve vessel space (no stowage model).
  `reserved_by_work_order_id` marks yard containers claimed by a READY load
  order and prevents two orders from claiming one container.
- Uniqueness: at every instant, every container has exactly one location;
  every container claimed by an IN_PROGRESS work order is in that order's
  `TRANSFER` location; no container is claimed by two work orders.

### 4.7 Rollover (D17)

When a vessel in HANDLING has no startable work, no crane is mid-batch on it,
and some of its load list is not IN_YARD, the kernel schedules
`LOAD_WAIT_TIMEOUT` at `now + max_load_wait_min` (cancelled if the work
becomes startable). At timeout, every still-unavailable load container gets
`rolled_over = true`, and the vessel proceeds to `VESSEL_HANDLING_COMPLETED`.
Rolled-over containers keep their status and later follow no vessel path.
They are reported as residual inventory with code `ROLLED_OVER`. The rule is identical
for every arm.

## 5. Units and accounting

| Quantity | Unit | Definition | Never confused with |
| --- | --- | --- | --- |
| Physical container count | containers | number of `ContainerRecord`s | TEU, moves |
| TEU quantity | TEU | Σ `size_teu` (20 ft = 1, 40 ft = 2) | containers |
| Crane move (ship-side work unit) | moves | one lift of one container between vessel and transfer (D14) | containers per vessel visit (a transshipment container causes 2 moves at 2 vessels) |
| Vessel workload | moves | `discharge_move_count + load_move_count + extra_work_units(=0)` | TEU |
| Yard handling move | yard moves | one lift into or out of a block: T3, T6 (in), T7, T9 (out) | crane moves |
| Yard transfer count | transfers | number of completed TRANSFER transactions (T3, T6, T8, T10 completions) | — |
| Relocation move | relocations | intra-yard rehandle (DEFERRED; ledger types reserved, §8.5) | yard handling moves |
| Gross weight | kg | per container, synthetic | TEU |
| Time | min | float since episode start | — |
| Distance | m | rectilinear terminal coordinates | — |
| Crane / transport / yard rates | moves/h | — | TEU/h |

Reconciliation identities (checked in Step 2 and in post-run audit):

```text
Σ_v workload_moves(v) = |{c: origin_vessel_id ∈ V}| + |{c: destination_vessel_id ∈ V}|
                        # V = vessels of the scenario; transshipment counted twice
throughput_containers = |{c : status ∈ {RELEASED_TO_LANDSIDE, DEPARTED_BY_VESSEL}}|
completed_crane_moves = count(T3 from DISCHARGE) + count(T10)
block occupied_teu    = Σ size_teu of containers with location YARD_BLOCK == block
```

A 40 ft container consumes 2.0 TEU of yard capacity and **one** crane move
(single lift). Twin-lift of two 20 ft containers (two containers, two TEU, one
move) is DEFERRED. If ever enabled, it is represented as an explicit
`lift_mode = TWIN` on a work order with `move_count < len(container_ids)`,
never by silently changing container counts.

## 6. Yard geometry

### 6.1 YardBlockRecord (immutable)

| Field | Type / unit | Status | Notes |
| --- | --- | --- | --- |
| `block_id` | str | FROZEN | `B01`… |
| `origin_x_m`, `origin_y_m` | m | FROZEN | Terminal coordinates of the block corner with smallest `x` and `y` |
| `bay_axis` | `"X"` | FROZEN v1 | Bays run along the quay direction. `"Y"` reserved |
| `bay_count`, `row_count`, `max_tiers` | int ≥ 1 | FROZEN | `bay_count` even (40 ft pairs) |
| `ground_slot_length_m`, `ground_slot_width_m` | m | PROPOSED 6.5 / 2.8 | Synthetic footprint for geometry and visuals, not calibrated |
| `geometric_slot_count` | int | Der | `bay_count × row_count × max_tiers` |
| `geometric_capacity_teu` | TEU | Der | `= geometric_slot_count` (one 20 ft slot = 1 TEU) |
| `capacity_teu` | TEU | Req | Operational limit used by G0; `≤ geometric_capacity_teu × operating_fill_limit` |
| `operating_fill_limit` | — | PROPOSED `(max_tiers − 1) / max_tiers` | Keeps one tier of working space per stack |
| `capabilities` | set of `YardCapability` | Req | Project 01 vocabulary |
| `allowed_sizes` | subset of {`20_ft`, `40_ft`} | Req | Size compatibility |
| `handling_capacity_moves_per_hour` | moves/h | Req, PROPOSED | `μ_b` of the integration specification §5.3 |
| `transfer_point_x_m`, `transfer_point_y_m` | m | Der | Middle of the block's quay-side edge: `(origin_x + bay_count × slot_len / 2, origin_y)` |

### 6.2 Indexing and axes (FROZEN, used identically by generator, kernel and Project 05)

- **Bay** — longitudinal position along `bay_axis`, integers `1…bay_count`,
  bay 1 at the block's smallest `x`.
- **Row** — transverse position, integers `1…row_count`, row 1 nearest the
  quay (smallest `y`).
- **Tier** — vertical level, integers `1…max_tiers`, tier 1 on the ground.
- All indices are **1-based positive integers**. 0 and negatives are invalid.
- Display form: `B02 / Bay 04 / Row 03 / Tier 05`. Canonical string
  `B02-04-03-05` (zero-padded 2 digits, wider if a dimension exceeds 99).
- **Stack** = `(block_id, bay, row)` for 20 ft, or `(block_id, anchor_bay, row)`
  for a 40 ft stack. Stack contents are ordered **bottom → top** (index 0 =
  tier 1). This is the single list convention required by Project 05.

### 6.3 Capacity concepts

| Concept | Unit | Definition |
| --- | --- | --- |
| Geometric capacity | slots / TEU | all slots of the grid |
| TEU capacity (operational) | TEU | `capacity_teu` |
| Occupied slots | slots | G1 only: slots covered by containers (a 40 ft covers 2) |
| Occupied TEU | TEU | Σ `size_teu` of containers located in the block |
| Reserved TEU | TEU | Σ reservations of IN_PROGRESS inbound work orders |
| Blocked TEU | TEU | capacity unavailable because of block status or explicitly blocked slots (0 in v1) |
| Available TEU | TEU | `capacity_teu − occupied − reserved − blocked` |
| Handling-rate limit | moves/h | `μ_b × g(ρ_b)`, shared (integration specification §5.3) |

### 6.4 Physical length representation and slot compatibility (G1, simplified v1 rule)

- A 20 ft container occupies one slot `(bay, row, tier)`.
- A 40 ft container occupies **two** slots `(b, row, tier)` and `(b+1, row, tier)`
  with `b` odd. It is addressed by its anchor bay `b` with `bay_span = 2`. The
  common real-world practice of labelling 40 ft positions with an even bay number
  is **not** adopted, to keep one integer grid. This is a modelling convention, not a
  claim about any terminal.
- A bay pair `(b, b+1)` at one row is a **stack position** of one length
  class at a time: either two independent 20 ft stacks or one 40 ft stack. Sizes
  never mix vertically within a stack position (no 40-on-20, no 20-on-40).
- No floating containers: a container at tier `t > 1` requires occupied
  supporting cells at tier `t − 1` covering exactly its footprint.
- Accessibility: a container is accessible iff no container occupies any
  cell of its footprint at tier `t + 1`.
- `tier ≤ max_tiers`, `bay_span` within `1…bay_count`, size ∈ `allowed_sizes`.

This grid is a simplified abstraction. It does not model ISO corner-castings,
weight-based stacking limits, reefer plug positions, hazardous segregation
distances, or equipment reach. No full ISO stacking realism is claimed.

## 7. Yard fidelity levels

| Feature | G0 (Project I execution) | G1 contract support (mandatory now) | G1 bookkeeping in Project I | Deferred to Project 05 |
| --- | --- | --- | --- | --- |
| Container identity, lifecycle, ledger | yes | yes | — | — |
| Block assignment, TEU capacity, reservations | yes | yes | — | — |
| Handling rate, congestion, distance | yes | yes | — | — |
| Bay/Row/Tier address fields | null | schema, validation | optional (`yard_fidelity = "G1"`), disabled in primary experiments (D12) | — |
| Slot-level capacity accounting | — | schema | optional | — |
| Legal slot placement (§6.4) | — | validator spec | optional, validator-checked | placement optimization |
| Stack-top accessibility | — | definition | optional (reported, not affecting time) | retrieval with relocations |
| Relocation moves and their time | — | ledger types reserved | **no** | yes |
| Stacking/relocation search, RL | — | — | no | yes |

G0 batches are processing conveniences reconciled to container ids at every
commit (§3). A G0 block assignment is never labelled or exported as a slot
placement (DQ19). If a G1 occupancy snapshot is supplied (initial state or
test fixture), every claimed position must satisfy §6.4 (DQ09, DQ10). A run
never implies that a 3D stacking trace exists when only block-level
operations were simulated: G0 ledgers carry `slot_resolution = BLOCK_ONLY`.

## 8. Container movement ledger

Append-only, one record per container per event, JSONL. Schema
`itp_ledger_v1`.

| Field | Type | Notes |
| --- | --- | --- |
| `event_id` | str `LE-nnnnnnnn` | Run-scoped, equal to `sequence_number` formatted |
| `run_id`, `scenario_id` | str | — |
| `sequence_number` | int | Strictly increasing within a run; the total order |
| `simulation_time_min` | float | Non-decreasing in `sequence_number` |
| `event_type` | §8.1 | — |
| `event_class` | `PLAN` \| `PHYSICAL` \| `EXCEPTION` | — |
| `container_id`, `container_group_id` | str | — |
| `from_status`, `to_status` | status or null | null for PLAN events |
| `source_location`, `destination_location` | location objects (§4.2) | Equal for PLAN events |
| `quantity_teu` | float | the container's `size_teu` |
| `crane_moves` | int | 1 on the completion of a ship-side transfer, else 0 |
| `handling_resource_id` | str or null | crane id (ship-side), block id (landside), null otherwise |
| `related_vessel_id` | str or null | — |
| `related_work_order_id` | str or null | — |
| `causation_id` | str | Kernel event id (`KE-…`) or decision id that caused it (Project 01 causation convention) |
| `transition_index` | int or null | k-th physical transition of this container (PHYSICAL only) |
| `idempotency_key` | str | PHYSICAL: `"{container_id}#{transition_index}"`; PLAN/EXCEPTION: `"{event_type}#{related_work_order_id}#{container_id}"` |

### 8.1 Event types

| Event type | Class | Transition | Inventory changes? | Counts as throughput? |
| --- | --- | --- | --- | --- |
| `WORK_ORDER_PLANNED` | PLAN | — | no | no |
| `YARD_RESERVATION_CREATED`, `YARD_RESERVATION_RELEASED` | PLAN | — | no (reserved TEU only) | no |
| `VESSEL_ARRIVED_WITH_CARGO` | PHYSICAL | T1 | no location change (status) | no |
| `DISCHARGE_STARTED` / `DISCHARGE_COMPLETED` | PHYSICAL | T2 / T3 | yes | completion: crane move |
| `GATE_ARRIVED` | PHYSICAL | T4 | yes | no |
| `RECEIVE_STARTED` / `RECEIVE_COMPLETED` | PHYSICAL | T5 / T6 | yes | no |
| `RELEASE_STARTED` / `RELEASE_COMPLETED` | PHYSICAL | T7 / T8 | yes | completion: container throughput |
| `LOAD_STARTED` / `LOAD_COMPLETED` | PHYSICAL | T9 / T10 | yes | completion: crane move |
| `DEPARTED_WITH_VESSEL` | PHYSICAL | T11 | no location change (status) | container throughput |
| `TRANSFER_ABORTED` | EXCEPTION | abort rows | yes (back to source) | no (v1 unreachable) |
| `TRANSFER_REJECTED` | EXCEPTION | — | no | no |
| `ROLLED_OVER` | EXCEPTION | — | no | no |
| `YARD_RELOCATION_STARTED` / `_COMPLETED`, `YARD_SHIFT_STARTED` / `_COMPLETED` | PHYSICAL | reserved for Project 05 | yes | relocation count |

A planned move is never counted as throughput. A reservation never mutates
inventory.

### 8.2 Ordering of simultaneous events

The ledger order equals the kernel processing order (integration
specification §8). Within one kernel event that affects several containers (a
batch), records are emitted in ascending `container_id`. `sequence_number`
breaks every remaining tie.

### 8.3 Duplicate detection and conservation verification (post-run audit)

```text
1. idempotency_key values are unique                       → else INVENTORY_CONSERVATION_FAILURE
2. replay: loc = initial_state locations
   for e in PHYSICAL events by sequence_number:
       require loc[e.container_id] == e.source_location      → else UNAVAILABLE_SOURCE_INVENTORY
       require (e.from_status → e.to_status) ∈ T1..T11/abort → else INVALID_STATUS_TRANSITION
       loc[e.container_id] = e.destination_location
3. require loc == kernel final ContainerState locations      → else INVENTORY_CONSERVATION_FAILURE
4. require |loc| == |containers| (no creation, no loss)
5. recompute per-block occupied TEU / counts from loc and compare with cached counters
6. recompute KPIs (throughput, crane moves, yard moves) from the ledger and compare with accumulators
```

### 8.4 Failed transfers

A rejected attempt (for example a yard policy naming an ineligible block) is
recorded as `TRANSFER_REJECTED` with the validation error code. State is
unchanged. An aborted in-progress transfer (future failures) emits
`TRANSFER_ABORTED` and returns each container atomically to its source
location.

### 8.5 Future relocation without redefining identity

Project 05 relocations use the same ledger: `YARD_RELOCATION_STARTED` moves
the container from a `YARD_BLOCK` slot to `TRANSFER`, and `_COMPLETED` moves
it from `TRANSFER` to another slot of the same block. `YARD_SHIFT_*` does the
same between blocks, matching Project 01 `OperationType.YARD_TRANSFER`.
`container_id`, `transition_index`, `idempotency_key` and the replay audit
apply unchanged.

## 9. Data quality rules and validation taxonomy

Validators are implemented in Steps 2 (scenario), 4 (runtime and post-run).
Severity: **REJECT_SCENARIO** (generator output invalid; scenario discarded
and the reason logged), **FAIL_RUN** (run marked `FAILED`, excluded from KPIs,
counted per arm), **REPORT** (recorded, run continues). Invalid data is
never silently repaired (DQ20).

| Rule | Requirement | Error code | Stage | Severity |
| --- | --- | --- | --- | --- |
| DQ01 | Container ids unique, pattern-valid | `DUPLICATE_CONTAINER_ID`, `INVALID_CONTAINER_ID` | scenario | REJECT_SCENARIO |
| DQ02 | Size ∈ {20_ft, 40_ft}; `size_teu` matches size; weight within bounds | `INVALID_CONTAINER_SIZE`, `TEU_SIZE_MISMATCH`, `INVALID_WEIGHT` | scenario | REJECT_SCENARIO |
| DQ03 | Flow consistent with vessel links (§2.1); referenced vessels exist (or `PRE_EPISODE` for initial inventory) | `INVALID_CARGO_FLOW`, `UNKNOWN_REFERENCE` | scenario | REJECT_SCENARIO |
| DQ04 | Every container in exactly one existing, field-consistent group | `GROUP_MEMBERSHIP_ERROR` | scenario | REJECT_SCENARIO |
| DQ05 | Group quantity and TEU equal member totals | `GROUP_TEU_MISMATCH` | scenario | REJECT_SCENARIO |
| DQ06 | Vessel `workload_moves`, move counts and TEU equal container-derived values | `WORKLOAD_RECONCILIATION_FAILURE` | scenario, post-run | REJECT_SCENARIO / FAIL_RUN |
| DQ07 | `occupied + reserved + blocked ≤ capacity_teu` per block at every instant; initial occupancy ≤ capacity | `YARD_CAPACITY_EXCEEDED` | scenario, runtime | REJECT_SCENARIO / FAIL_RUN |
| DQ08 | A container has exactly one location; a slot holds at most one container | `DUPLICATE_PHYSICAL_LOCATION` | runtime, post-run | FAIL_RUN |
| DQ09 | Bay/Row/Tier within bounds, 1-based, size allowed, 40 ft anchor odd | `INVALID_STACK_POSITION`, `SLOT_SIZE_CONFLICT` | scenario (G1 snapshot), runtime (G1) | REJECT_SCENARIO / FAIL_RUN |
| DQ10 | No floating occupancy in slot-resolved mode | `FLOATING_STACK` | scenario, runtime (G1) | REJECT_SCENARIO / FAIL_RUN |
| DQ11 | Times causal: gate-in ≤ destination arrival − cutoff; pickup ≥ origin arrival; actual times monotone along the lifecycle | `CAUSALITY_VIOLATION` | scenario, post-run | REJECT_SCENARIO / FAIL_RUN |
| DQ12 | Transfers preserve inventory (ledger replay) | `INVENTORY_CONSERVATION_FAILURE` | post-run | FAIL_RUN |
| DQ13 | Loads and releases only take containers present at the source | `UNAVAILABLE_SOURCE_INVENTORY` | runtime | FAIL_RUN (validator raises before mutation) |
| DQ14 | Discharge and receive start only with a valid destination reservation | `MISSING_DESTINATION_CAPACITY` | runtime | FAIL_RUN (validator raises before mutation) |
| DQ15 | Status transitions follow §4.4 | `INVALID_STATUS_TRANSITION` | runtime, post-run | FAIL_RUN |
| DQ16 | Fingerprints cover all immutable cargo and geometry fields and recompute identically | `FINGERPRINT_INCOMPLETE`, `FINGERPRINT_MISMATCH` | scenario load | REJECT_SCENARIO |
| DQ17 | Exogenous identities, arrivals, quantities, attributes identical across arms of one scenario | `EXOGENOUS_INPUT_DRIFT` | run comparison | FAIL_RUN (all arms of the scenario quarantined) |
| DQ18 | No hidden future information in observations or forward models without contract | `FUTURE_INFORMATION_LEAK` | tests (Step 4, 6) | blocks the step gate |
| DQ19 | G0 block assignment never reported as G1 slot | `FIDELITY_MISLABEL` | runtime, export | FAIL_RUN |
| DQ20 | Unsupported assumptions reported, not repaired (missing required fields, unsupported sizes, unknown enums, defaults for required fields) | `UNSUPPORTED_ASSUMPTION` | all | REJECT_SCENARIO / FAIL_RUN |

## 10. Project 05 extension points

| Project 05 need | Provided now | Breaking change needed later? |
| --- | --- | --- |
| Individual containers with stable ids, size, weight, flow | `ContainerRecord` | No |
| Retrieval order | Derivable: imports by `scheduled_pickup_time_min`; exports/transshipment by destination vessel order | No |
| Stack geometry and one list convention | §6.2 (1-based, bottom → top) | No |
| Legal placement rules | §6.4 validator spec | Additional rules (weight, reefer) are additive |
| Relocation and retrieval moves | Ledger types §8.5, `TRANSFER` location | No |
| Hashable state | Canonical slot occupancy: tuple of stacks, each a bottom→top tuple of container ids | No |
| Initial snapshots from Project I | Any G0 state + a G1 placement produced by Project 05 itself (never inferred from G0) | No |

## 11. Worked example (illustrative values; not empirical terminal data)

Two vessels, five containers, two blocks, one crane at 30 moves/h. Transport
and yard limits are assumed non-binding so the arithmetic stays visible.

### 11.1 Scenario excerpt (parseable)

```json
{
  "schema_version": "itp_scenario_v1",
  "identity": {"scenario_id": "itp_example_development_seed10000000", "project_id": "project_i_integrated_terminal_pilot", "scenario_family": "itp_example", "split": "development", "scenario_seed": 10000000, "generator_version": "hand_written_example", "data_provenance": "synthetic", "yard_fidelity": "G0"},
  "vessels": [
    {"vessel_id": "V001", "arrival_time_min": 0.0, "length_m": 250.0, "max_cranes": 1, "priority": 2, "discharge_move_count": 3, "load_move_count": 0, "extra_work_units": 0, "workload_moves": 3, "discharge_teu": 5.0, "load_teu": 0.0, "nominal_service_time_min": 51.5},
    {"vessel_id": "V002", "arrival_time_min": 600.0, "length_m": 220.0, "max_cranes": 1, "priority": 2, "discharge_move_count": 0, "load_move_count": 3, "extra_work_units": 0, "workload_moves": 3, "discharge_teu": 0.0, "load_teu": 4.0, "nominal_service_time_min": 51.5}
  ],
  "yard_blocks": [
    {"block_id": "B01", "origin_x_m": 100.0, "origin_y_m": 150.0, "bay_axis": "X", "bay_count": 8, "row_count": 4, "max_tiers": 4, "ground_slot_length_m": 6.5, "ground_slot_width_m": 2.8, "capacity_teu": 96.0, "capabilities": ["general"], "allowed_sizes": ["20_ft", "40_ft"], "handling_capacity_moves_per_hour": 40.0},
    {"block_id": "B02", "origin_x_m": 400.0, "origin_y_m": 150.0, "bay_axis": "X", "bay_count": 8, "row_count": 4, "max_tiers": 4, "ground_slot_length_m": 6.5, "ground_slot_width_m": 2.8, "capacity_teu": 96.0, "capabilities": ["general"], "allowed_sizes": ["20_ft", "40_ft"], "handling_capacity_moves_per_hour": 40.0}
  ],
  "container_groups": [
    {"group_id": "GRP-0001", "container_size": "20_ft", "quantity": 1, "flow": "import", "load_state": "laden", "is_reefer": false, "is_hazardous": false, "source_vessel_id": "V001", "target_vessel_id": null},
    {"group_id": "GRP-0002", "container_size": "40_ft", "quantity": 1, "flow": "import", "load_state": "laden", "is_reefer": false, "is_hazardous": false, "source_vessel_id": "V001", "target_vessel_id": null},
    {"group_id": "GRP-0003", "container_size": "40_ft", "quantity": 1, "flow": "transshipment", "load_state": "laden", "is_reefer": false, "is_hazardous": false, "source_vessel_id": "V001", "target_vessel_id": "V002"},
    {"group_id": "GRP-0004", "container_size": "20_ft", "quantity": 2, "flow": "export", "load_state": "laden", "is_reefer": false, "is_hazardous": false, "source_vessel_id": null, "target_vessel_id": "V002"}
  ],
  "containers": [
    {"container_id": "CNT-000001", "container_group_id": "GRP-0001", "container_size": "20_ft", "size_teu": 1.0, "load_state": "laden", "is_reefer": false, "is_hazardous": false, "gross_weight_kg": 18000, "cargo_flow": "import", "origin_vessel_id": "V001", "destination_vessel_id": null, "terminal_entry_mode": "VESSEL", "terminal_exit_mode": "LANDSIDE", "present_at_episode_start": false, "scheduled_gate_in_time_min": null, "scheduled_pickup_time_min": 300.0, "source_scenario_id": "itp_example_development_seed10000000"},
    {"container_id": "CNT-000002", "container_group_id": "GRP-0002", "container_size": "40_ft", "size_teu": 2.0, "load_state": "laden", "is_reefer": false, "is_hazardous": false, "gross_weight_kg": 26500, "cargo_flow": "import", "origin_vessel_id": "V001", "destination_vessel_id": null, "terminal_entry_mode": "VESSEL", "terminal_exit_mode": "LANDSIDE", "present_at_episode_start": false, "scheduled_gate_in_time_min": null, "scheduled_pickup_time_min": 420.0, "source_scenario_id": "itp_example_development_seed10000000"},
    {"container_id": "CNT-000003", "container_group_id": "GRP-0003", "container_size": "40_ft", "size_teu": 2.0, "load_state": "laden", "is_reefer": false, "is_hazardous": false, "gross_weight_kg": 21000, "cargo_flow": "transshipment", "origin_vessel_id": "V001", "destination_vessel_id": "V002", "terminal_entry_mode": "VESSEL", "terminal_exit_mode": "VESSEL", "present_at_episode_start": false, "scheduled_gate_in_time_min": null, "scheduled_pickup_time_min": null, "source_scenario_id": "itp_example_development_seed10000000"},
    {"container_id": "CNT-000004", "container_group_id": "GRP-0004", "container_size": "20_ft", "size_teu": 1.0, "load_state": "laden", "is_reefer": false, "is_hazardous": false, "gross_weight_kg": 15200, "cargo_flow": "export", "origin_vessel_id": null, "destination_vessel_id": "V002", "terminal_entry_mode": "LANDSIDE", "terminal_exit_mode": "VESSEL", "present_at_episode_start": false, "scheduled_gate_in_time_min": 120.0, "scheduled_pickup_time_min": null, "source_scenario_id": "itp_example_development_seed10000000"},
    {"container_id": "CNT-000005", "container_group_id": "GRP-0004", "container_size": "20_ft", "size_teu": 1.0, "load_state": "laden", "is_reefer": false, "is_hazardous": false, "gross_weight_kg": 12400, "cargo_flow": "export", "origin_vessel_id": null, "destination_vessel_id": "V002", "terminal_entry_mode": "LANDSIDE", "terminal_exit_mode": "VESSEL", "present_at_episode_start": true, "scheduled_gate_in_time_min": null, "scheduled_pickup_time_min": null, "source_scenario_id": "itp_example_development_seed10000000"}
  ],
  "initial_state": {
    "time_min": 0.0,
    "container_locations": [
      {"container_id": "CNT-000001", "status": "EXPECTED_BY_VESSEL", "location": {"kind": "VESSEL", "location_id": "V001", "bay": null, "row": null, "tier": null, "slot_resolution": null}},
      {"container_id": "CNT-000002", "status": "EXPECTED_BY_VESSEL", "location": {"kind": "VESSEL", "location_id": "V001", "bay": null, "row": null, "tier": null, "slot_resolution": null}},
      {"container_id": "CNT-000003", "status": "EXPECTED_BY_VESSEL", "location": {"kind": "VESSEL", "location_id": "V001", "bay": null, "row": null, "tier": null, "slot_resolution": null}},
      {"container_id": "CNT-000004", "status": "EXPECTED_BY_LANDSIDE", "location": {"kind": "EXTERNAL_LANDSIDE", "location_id": null, "bay": null, "row": null, "tier": null, "slot_resolution": null}},
      {"container_id": "CNT-000005", "status": "IN_YARD", "location": {"kind": "YARD_BLOCK", "location_id": "B02", "bay": null, "row": null, "tier": null, "slot_resolution": "BLOCK_ONLY"}}
    ]
  }
}
```

Nominal service: `30 + 0.5 × 3 + 20 = 51.5` min for each vessel.
Block transfer points: B01 `(100 + 8 × 6.5 / 2, 150) = (126, 150)`; B02 `(426, 150)`.

### 11.2 TEU, move and count reconciliation

| Group | Quantity | Members | Member TEU | `total_teu` | Check |
| --- | --- | --- | --- | --- | --- |
| GRP-0001 import 20 ft | 1 | CNT-000001 | 1.0 | 1 × 1.0 = 1.0 | ✓ |
| GRP-0002 import 40 ft | 1 | CNT-000002 | 2.0 | 1 × 2.0 = 2.0 | ✓ |
| GRP-0003 transshipment 40 ft | 1 | CNT-000003 | 2.0 | 2.0 | ✓ |
| GRP-0004 export 20 ft | 2 | CNT-000004, CNT-000005 | 1.0 + 1.0 | 2 × 1.0 = 2.0 | ✓ |
| **Total** | 5 containers | | **7.0 TEU** | | |

| Vessel | Discharge (moves / TEU) | Load (moves / TEU) | `workload_moves` |
| --- | --- | --- | --- |
| V001 | CNT-1, 2, 3 → 3 / 5.0 | 0 / 0 | 3 |
| V002 | 0 / 0 | CNT-3, 4, 5 → 3 / 4.0 | 3 |

Crane moves total 6 for 5 containers, because the transshipment container is
lifted twice. Yard handling moves total 9: CNT-1, 2, 3 and 4 each enter and leave
(8), and CNT-5 only leaves (1). TEU (7.0), containers (5), crane moves (6)
and yard moves (9) are four different numbers.

### 11.3 Movement timeline (illustrative, G0)

Batches are per group (D15); `batch_size_containers = 10`.

| t (min) | Event | Containers | Status / location after | B01 occ / res TEU | B02 occ / res TEU |
| --- | --- | --- | --- | --- | --- |
| 0 | V001 arrival; berth at 0.0 m | CNT-1, 2, 3 | ABOARD_ARRIVED_VESSEL / V001 | 0 / 0 | 1 / 0 |
| 30 | WO-000001 DISCHARGE GRP-0001 → B01 starts | CNT-1 | DISCHARGING / TRANSFER | 0 / 1 | 1 / 0 |
| 32 | WO-000001 completes; WO-000002 (GRP-0002 → B01) starts | CNT-1; CNT-2 | IN_YARD B01; DISCHARGING | 1 / 2 | 1 / 0 |
| 34 | WO-000002 completes; WO-000003 (GRP-0003 → B01) starts | CNT-2; CNT-3 | IN_YARD B01; DISCHARGING | 3 / 2 | 1 / 0 |
| 36 | WO-000003 completes; V001 handling complete | CNT-3 | IN_YARD B01 | 5 / 0 | 1 / 0 |
| 56 | V001 departs | — | — | 5 / 0 | 1 / 0 |
| 120 | Gate arrival; WO-000004 GATE_IN → B02 starts | CNT-4 | AT_GATE → RECEIVING | 5 / 0 | 1 / 1 |
| 121.5 | WO-000004 completes (1 move at 40 moves/h) | CNT-4 | IN_YARD B02 | 5 / 0 | 2 / 0 |
| 300 | Pickup due; WO-000005 GATE_OUT starts | CNT-1 | RETRIEVING_TO_LANDSIDE | 4 / 0 | 2 / 0 |
| 301.5 | WO-000005 completes | CNT-1 | RELEASED_TO_LANDSIDE | 4 / 0 | 2 / 0 |
| 420–421.5 | WO-000006 GATE_OUT | CNT-2 | RELEASED_TO_LANDSIDE | 2 / 0 | 2 / 0 |
| 600 | V002 arrival; berth | — | — | 2 / 0 | 2 / 0 |
| 630 | WO-000007 LOAD GRP-0003 from B01 starts | CNT-3 | LOADING / TRANSFER | 0 / 0 | 2 / 0 |
| 632 | WO-000007 completes; WO-000008 LOAD GRP-0004 from B02 {CNT-4, CNT-5} starts | CNT-3; CNT-4, 5 | LOADED / V002; LOADING | 0 / 0 | 0 / 0 |
| 636 | WO-000008 completes; V002 handling complete | CNT-4, 5 | LOADED / V002 | 0 / 0 | 0 / 0 |
| 656 | V002 departs | CNT-3, 4, 5 | DEPARTED_BY_VESSEL | 0 / 0 | 0 / 0 |

Realized berth occupancy: V001 56 min and V002 56 min, against nominal 51.5 min each
(one 30 moves/h crane needs 6 min for 3 moves; nominal assumes 1.5 min).

Final accounting: 5 containers; 2 released to landside, 3 departed by vessel,
0 in yard; crane moves completed 6; yard moves 9; conservation holds.

### 11.4 Ledger excerpt for the transshipment container CNT-000003

| seq | t | event_type | class | from → to status | source → destination | resource | work order | key |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 0 | VESSEL_ARRIVED_WITH_CARGO | PHYSICAL | EXPECTED_BY_VESSEL → ABOARD_ARRIVED_VESSEL | VESSEL V001 → VESSEL V001 | — | — | CNT-000003#1 |
| 14 | 34 | YARD_RESERVATION_CREATED | PLAN | — | — | B01 | WO-000003 | YARD_RESERVATION_CREATED#WO-000003#CNT-000003 |
| 15 | 34 | DISCHARGE_STARTED | PHYSICAL | ABOARD_ARRIVED_VESSEL → DISCHARGING | VESSEL V001 → TRANSFER WO-000003 | QC01 | WO-000003 | CNT-000003#2 |
| 17 | 36 | DISCHARGE_COMPLETED | PHYSICAL | DISCHARGING → IN_YARD | TRANSFER → YARD_BLOCK B01 (BLOCK_ONLY) | QC01 | WO-000003 | CNT-000003#3 |
| 31 | 630 | LOAD_STARTED | PHYSICAL | IN_YARD → LOADING | YARD_BLOCK B01 → TRANSFER WO-000007 | QC01 | WO-000007 | CNT-000003#4 |
| 32 | 632 | LOAD_COMPLETED | PHYSICAL | LOADING → LOADED | TRANSFER → VESSEL V002 | QC01 | WO-000007 | CNT-000003#5 |
| 40 | 656 | DEPARTED_WITH_VESSEL | PHYSICAL | LOADED → DEPARTED_BY_VESSEL | VESSEL V002 → VESSEL V002 | — | — | CNT-000003#6 |

(Sequence numbers are illustrative; gaps hold other containers' records.)

### 11.5 Illustrative G1 occupancy snapshot (test fixture, not produced by the G0 run)

A hypothetical G1 snapshot of B01 at t = 36, with both 40 ft containers
stacked in one 40 ft stack position:

```json
{
  "block_id": "B01",
  "yard_fidelity": "G1",
  "slots": [
    {"container_id": "CNT-000001", "bay": 1, "row": 1, "tier": 1, "bay_span": 1},
    {"container_id": "CNT-000003", "bay": 5, "row": 2, "tier": 1, "bay_span": 2},
    {"container_id": "CNT-000002", "bay": 5, "row": 2, "tier": 2, "bay_span": 2}
  ]
}
```

Validation: all indices are 1-based and in range (bays ≤ 8, rows ≤ 4,
tiers ≤ 4). Both 40 ft anchors are odd (5) and cover bays 5–6. CNT-000002 at
tier 2 rests on CNT-000003 with an identical footprint (no floating, no size
mixing). Occupied slots: 1 + 2 + 2 = 5 = occupied TEU. Stack `(B01, 5, 2)`
bottom → top is `[CNT-000003, CNT-000002]`. CNT-000003 is **not accessible**
because CNT-000002 is above it. Retrieving it first would need one relocation.
That is a Project 05 question, and v1 G0 timing deliberately does not charge it.
