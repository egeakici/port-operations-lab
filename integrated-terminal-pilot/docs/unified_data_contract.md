# Unified Data Contract

Schema family `itp_scenario_v1` (scenario documents) and `itp_state_v1`
(kernel state). This document is canonical for vessels, cranes, gates, work
orders, physics configuration, mutable state, projections, serialization and
fingerprints. The canonical schemas for **containers, container groups, yard
blocks, slot addresses and the movement ledger** are in
[container_yard_foundation.md](container_yard_foundation.md). This document
references them and does not restate them, so there is a single source of
truth.

## 1. Conventions

| Topic | Rule | Status |
| --- | --- | --- |
| Time | float minutes since episode start, suffix `_min`, finite, ≥ 0 (D02) | FROZEN |
| Length / position | meters, suffix `_m`; `x_m` along quay, `y_m` inland (D03) | FROZEN |
| Rates | `_moves_per_hour` (crane, yard handling, transport) | FROZEN |
| Speed | `_m_per_min` | FROZEN |
| Capacity | `_teu` (float with integer values in v1) | FROZEN |
| Counts | `_count` (int); container count, move count and TEU are never interchangeable | FROZEN |
| Weight | `_kg` (int) | FROZEN |
| Identifiers | non-empty ASCII strings matching the patterns below; unique within their registry | FROZEN |
| Nullability | `null` means "does not apply" or "not yet happened", never "unknown but filled with a placeholder" | FROZEN |
| Enumerations | Serialized by `.value` of the reused Project 01 enum where one exists | FROZEN |

Identifier patterns (FROZEN for generated data):

| Entity | Pattern | Example |
| --- | --- | --- |
| Vessel | `V\d{3}` (Project 02/03 convention) | `V007` |
| Quay crane | `QC\d{2}` | `QC03` |
| Yard block | `B\d{2}` | `B02` |
| Gate | `G\d{2}` | `G01` |
| Container | `CNT-\d{6}` (synthetic; deliberately **not** an ISO 6346 code) | `CNT-000417` |
| Container group | `GRP-\d{4}` | `GRP-0012` |
| Work order | `WO-\d{6}` (assigned in creation order at run time) | `WO-000031` |
| Kernel event | `KE-\d{8}` (run-scoped) | `KE-00001234` |
| Ledger event | `LE-\d{8}` (run-scoped) | `LE-00000077` |

## 2. Scenario document

One JSON document per scenario, immutable after generation. It is loaded once
and shared by reference between kernel clones.

```text
{
  "schema_version": "itp_scenario_v1",
  "identity":        {...},   # §2.1
  "terminal":        {...},   # §3  quay, gates; yard blocks per container_yard_foundation §6
  "resources":       {...},   # §5  quay cranes
  "vessels":         [...],   # §4
  "container_groups":[...],   # container_yard_foundation §3
  "containers":      [...],   # container_yard_foundation §2
  "initial_state":   {...},   # §7
  "physics":         {...},   # §6
  "fingerprints":    {...}    # §10 (computed, excluded from its own hash)
}
```

### 2.1 Identity block

| Field | Type | Meaning |
| --- | --- | --- |
| `scenario_id` | str | `itp_{family}_{split}_seed{scenario_seed}` |
| `project_id` | str | `project_i_integrated_terminal_pilot` |
| `scenario_family` | str | e.g. `itp_medium`, `itp_heavy` (Step 2 defines) |
| `split` | str | `development` \| `validation` \| `test` \| `diagnostic` |
| `scenario_seed` | int | Seed in the split's band (protocol §6) |
| `generator_version` | str | e.g. `itp_generator_v1` |
| `data_provenance` | str | always `synthetic` |
| `yard_fidelity` | str | `G0` or `G1` (D12) |

## 3. Terminal geometry

| Field | Unit | Status | Notes |
| --- | --- | --- | --- |
| `quay.berth_length_m` | m | FROZEN 1200.0 (primary) | Continuous quay `x ∈ [0, L]` |
| `quay.min_clearance_m` | m | FROZEN 20.0 | Between hulls, not at quay ends (Project 03 geometry) |
| `quay.quay_line_y_m` | m | FROZEN 0.0 | — |
| `gates[].gate_id`, `x_m`, `y_m` | m | PROPOSED one gate | Reference location only. No landside road model |
| `yard_blocks[]` | — | see foundation §6 | Geometry, capacity, handling, transfer point |

## 4. Vessel record (immutable scenario input)

| Field | Type / unit | Class | Observable from |
| --- | --- | --- | --- |
| `vessel_id` | str | required, immutable | announcement |
| `arrival_time_min` | float min | required, immutable exogenous | announcement (exact, D18) |
| `announce_time_min` | float min | derived: `max(0, arrival − H)` | — (the kernel uses it) |
| `length_m` | float m, ≤ quay | required, immutable | announcement |
| `max_cranes` | int ≥ 1 | required, immutable (Project 01 `Vessel.max_cranes`) | announcement |
| `priority` | int 1–3 | optional (default 2; not used by v1 objectives) | announcement |
| `discharge_move_count` | int ≥ 0 | derived, materialized: containers with `origin_vessel_id == vessel_id` | announcement |
| `load_move_count` | int ≥ 0 | derived, materialized: containers with `destination_vessel_id == vessel_id` | announcement |
| `extra_work_units` | int | FROZEN 0 (D14) | announcement |
| `workload_moves` | int | derived: discharge + load + extra (DQ06) | announcement |
| `discharge_teu`, `load_teu` | float TEU | derived, materialized | announcement |
| `nominal_service_time_min` | float min | derived: D20 formula of `workload_moves` | announcement |

Materialized derived fields exist so that the vessel record alone can be
fingerprinted and projected. A generator or loader that finds any mismatch
with the container records rejects the scenario (`WORKLOAD_RECONCILIATION_FAILURE`).

A vessel must satisfy `workload_moves ≥ 1` in generated Project I scenarios.
Vessels without cargo appear only in hand-written test fixtures.

## 5. Quay crane record

| Field | Type / unit | Class | v1 value |
| --- | --- | --- | --- |
| `crane_id` | str | required, immutable | `QC01…` |
| `nominal_moves_per_hour` | float > 0 | required, immutable (Project 01 `moves_per_hour`) | PROPOSED 30.0 (Project 02 default) |
| `rail_id` | str | reserved for Project 04 | `R1` (single rail, unused) |
| `home_position_m` | float m | reserved for Project 04 | evenly spaced, unused by v1 physics |
| `compatible_vessel_ids` | list or null | optional; `null` = all vessels | `null` |
| `unavailability_windows` | list of `[start_min, end_min)` | optional; must be `[]` in v1 (D19) | `[]` |

Crane semantics (D08):

| Rule | Definition |
| --- | --- |
| Exclusivity | A crane has at most one `assigned_vessel_id` |
| Allocation | Only to a vessel in phase `BERTHING_PREP` or `HANDLING` with remaining ship-side work, and only if the vessel has fewer than `max_cranes` cranes |
| Minimum per vessel | 0. A berthed vessel may have no crane; it then accrues waiting-for-crane time |
| Release | Automatic at `VESSEL_HANDLING_COMPLETED`; voluntary release only at a CRANE decision and only when the crane is not in a batch (non-preemptive) |
| Preemption | None inside a batch; reassignment between batches allowed at CRANE decisions |
| Sharing | No crane sharing between vessels; cranes on one vessel split its batches (each crane works one batch at a time) |
| Multi-crane efficiency | `eff(n_v)` of D09 applied to every crane on the vessel |
| Idle time | `status == AVAILABLE` |
| Productive time | Assigned and working a batch with rate > 0 |
| Blocked time | Assigned, not working, reason ∈ {`VESSEL_NOT_READY`, `YARD_CAPACITY`, `CARGO_UNAVAILABLE`, `NO_REMAINING_WORK`} |
| Physically assigned but yard-blocked | Counted as blocked (`YARD_CAPACITY`), not idle and not productive; it remains unavailable to other vessels unless the crane policy releases it |

## 6. Physics configuration (immutable per scenario)

| Field | Unit | Status | Default |
| --- | --- | --- | --- |
| `service.berthing_preparation_minutes` | min | FROZEN (D20/D21) | 30.0 |
| `service.service_minutes_per_move` | min | FROZEN (nominal only) | 0.5 |
| `service.departure_preparation_minutes` | min | FROZEN | 20.0 |
| `crane.efficiency` | factors | FROZEN mechanism, PROPOSED values | 1.0 / 0.92 / 0.82 / 0.72 |
| `crane.productivity_factor` | — | FROZEN (D19) | 1.0 |
| `transport.enabled` | bool | — | true |
| `transport.speed_m_per_min` | m/min | PROPOSED | 250.0 |
| `transport.handover_min` | min | PROPOSED | 2.0 |
| `transport.units_per_crane` | int | PROPOSED | 4 |
| `yard.constraints_enabled` | bool | — | true |
| `yard.congestion_rho0` | — | PROPOSED | 0.70 |
| `yard.congestion_g_min` | — | PROPOSED | 0.50 |
| `yard.landside_reserved_fraction` | — | PROPOSED | 0.20 |
| `work.batch_size_containers` | int | PROPOSED (D15) | 10 |
| `work.max_load_wait_min` | min | PROPOSED (D17) | 240.0 |
| `visibility.future_horizon_min` | min | FROZEN (D18) | 240.0 |
| `episode.max_drain_extension_min` | min | PROPOSED | 10080.0 (Project 03 dynamic default) |
| `kernel.same_timestamp_cycle_limit` | count | PROPOSED | 10000 |

Example transport arithmetic (illustrative): `d = 600 m` gives a cycle of
`2·600/250 + 2 = 6.8 min`, so 4 units give `4·60/6.8 ≈ 35.3` moves/h, which
does not bind a 30 moves/h crane. `d = 1500 m` gives `14 min` and `≈ 17.1` moves/h,
which binds.

The **degenerate profile** used by the equivalence test is a physics block
with `transport.enabled = false`, `yard.constraints_enabled = false`, every
crane `nominal_moves_per_hour = 120.0`, every vessel `max_cranes = 1`, and at
least as many cranes as the maximum number of concurrently berthed vessels.
Handling then lasts exactly `0.5 × workload_moves` minutes. This profile is a
test fixture, not an experimental condition.

## 7. Initial state block

| Field | Meaning |
| --- | --- |
| `initial_state.time_min` | always 0.0 |
| `initial_state.container_locations` | for each container: initial status and location (foundation §4). Must be lifecycle-consistent with its flow |
| `initial_state.block_status` | OPEN / CLOSED / MAINTENANCE per block (v1: all OPEN) |
| `initial_state.slot_occupancy` | only when `yard_fidelity == "G1"`; otherwise absent |

## 8. Mutable operational state (`itp_state_v1`)

All mutable state is plain data: dicts, lists and tuples of primitives, or
frozen dataclasses of primitives. No generators, closures, file handles,
`MappingProxyType`, policy objects or models.

| Record | Fields |
| --- | --- |
| `KernelClock` | `now_min` |
| `VesselState` | `vessel_id`, `visibility` (HIDDEN / ANNOUNCED / ARRIVED), `phase` (NOT_ARRIVED, WAITING, BERTHING_PREP, HANDLING, DEPARTURE_PREP, DEPARTED), `slot_index` (int or null; allocated at first reveal, never reused), `berth_position_m`, `berth_start_time_min`, `handling_start_time_min`, `handling_end_time_min`, `departure_time_min`, `load_wait_deadline_min`, `rolled_over_container_ids` |
| `QuayCraneState` | `crane_id`, `status` (`CraneStatus`), `assigned_vessel_id`, `activity` (IDLE / PRODUCTIVE / BLOCKED), `blocked_reason`, `current_work_order_id`, `rate_moves_per_hour`, accumulators `idle_min`, `productive_min`, `blocked_min_by_reason{}`, `moves_completed`, `rate_shortfall_moves` |
| `YardBlockState` | `block_id`, `status` (`YardBlockStatus`), `reservations{work_order_id: teu}`, cached `occupied_teu`, `occupied_container_count`, `blocked_teu` (0.0 in v1), `slot_occupancy` (G1 only), accumulator `teu_minutes` (for mean occupancy), `peak_occupied_teu` |
| `ContainerState` | foundation §4 |
| `WorkOrderState` | §9 |
| `EventQueue` | heap of `(time_min, priority, stable_key, sequence, event_type, payload_tuple, generation)` |
| `KernelCounters` | `next_kernel_event_seq`, `next_ledger_seq`, `next_work_order_seq` |
| `KpiAccumulators` | waiting queue integrals, transfer waiting, decision timing (§ protocol 7) |
| `EpisodeStatus` | `RUNNING` / `COMPLETED` / `TRUNCATED_DRAIN_LIMIT` / `DEADLOCK` / `FAILED`, `reason`, `unresolved_ids` |
| `Ledger` | append-only list of ledger events (foundation §8), or `None` in forward-model clones |

### 8.1 Clone contract

`clone()` returns a state that, run with the same policies, produces the same
future. It contains:

- the immutable `ScenarioDefinition` (shared reference, never copied);
- deep copies of every record listed above, including the clock,
  occupancies, pending work orders and their progress, reservations,
  committed container locations, scheduled future events with their
  generations, all counters and accumulators;
- the RNG contract: v1 kernels consume **no runtime randomness**, because
  every exogenous draw is materialized in the scenario (D19). Future
  stochastic physics must use stateless streams keyed by
  `(scenario_seed, entity_id, attribute, occurrence_index)`, which are
  clone-safe by construction.

Not included: ledger file sinks, loggers, policy and model objects, timing
instrumentation, UI objects. `observable_clone()` additionally removes hidden
information (integration specification §10) and sets `Ledger = None`.

## 9. Work order (batch) record

Vocabulary reuse: `operation_type` uses Project 01 `OperationType`;
`status` uses Project 01 `OperationTaskStatus`.

| Field | Type | Notes |
| --- | --- | --- |
| `work_order_id` | str | `WO-nnnnnn` |
| `operation_type` | `DISCHARGE` / `LOAD` / `GATE_IN` / `GATE_OUT` | `YARD_TRANSFER` reserved for future relocation between blocks |
| `container_group_id` | str | All containers of the batch share one group (D15) |
| `container_ids` | tuple[str] | 1..`batch_size_containers`, sorted, unique, all currently at `source` |
| `move_count` | int | `= len(container_ids)` (D14) |
| `planned_teu` | float | `= Σ size_teu` of members |
| `vessel_id` | str or null | Ship-side orders only |
| `crane_id` | str or null | Ship-side orders only |
| `source`, `destination` | location (foundation §4.2) | Destination block chosen by the yard policy for DISCHARGE / GATE_IN |
| `status` | CREATED → READY → ASSIGNED → IN_PROGRESS → COMPLETED (CANCELLED / FAILED / BLOCKED reachable only on abort paths) | Project 01 transition table |
| `completed_moves` | float | Fluid progress; container commits happen only at completion (atomic batch) |
| `rate_moves_per_hour`, `rate_generation` | float, int | §5.4 / §8.4 of the integration specification |
| `created_time_min`, `start_time_min`, `completion_time_min` | float or null | — |

## 10. Fingerprints

Canonical JSON: `json.dumps(value, sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False)`; floats use Python's shortest
round-trip `repr`; enums by `.value`; sets as sorted lists. Hash: SHA-256
hex.

| Fingerprint | Content | Excludes | Purpose |
| --- | --- | --- | --- |
| `scenario_fingerprint` | Whole scenario document | `fingerprints` block | Exact identity of the file |
| `terminal_geometry_fingerprint` | quay, gates, yard block geometry, capacities, capabilities, handling | ids of the scenario, split, seed | Geometry identity |
| `resource_fingerprint` | crane records | same | Resource identity |
| `container_manifest_fingerprint` | containers sorted by `container_id`, immutable fields only (foundation §2), plus groups | mutable state | Cargo identity (DQ16) |
| `exogenous_schedule_fingerprint` | sorted `(vessel_id, arrival)`, `(container_id, gate-in time)`, `(container_id, scheduled pickup)` | — | DQ17: identical across all arms of a scenario |
| `physics_config_fingerprint` | physics block | — | Coefficient identity |
| `physical_fingerprint` | SHA-256 of the five component fingerprints above, in that order | identity block | Detects physically duplicate scenarios across splits |
| `berth_projection_fingerprint` | Project 03 `BAPScenarioInstance.content_fingerprint` of the projection | — | Ties S1 reference runs to the scenario |
| `berth_projection_physical_fingerprint` | Project 03 `rl.suites.physical_fingerprint(projection)` | ids, split, seed | Collision audit against Project 03 suites |

Every run record stores all fingerprints of its scenario, the policy id and
version, checkpoint SHA-256 (if any), git commit and dirty flag (Project 03
experiment data contract convention).

## 11. Berth projection and realized projection

**Berth projection** (policy-facing, immutable): a Project 03
`BAPScenarioInstance` with

| Field | Value |
| --- | --- |
| `scenario_id` | Project I `scenario_id` + `__berth_projection` |
| `scenario_family` | Project I family |
| `formulation` | `dynamic` |
| `data_provenance` | `synthetic` |
| `split` | development → `train`, validation → `validation`, test → `test`, diagnostic → `test` with family suffix `_diagnostic` (label mapping only; Project I records are authoritative) |
| `seed` | Project I `scenario_seed` |
| `generator_version` | `itp_berth_projection_v1` |
| `berth_length_m`, `min_clearance_m` | quay values |
| `vessels` | `BAPVesselInput(vessel_id, arrival_time_min, length_m, service_time_min = nominal_service_time_min, workload_moves)` ordered by `(arrival, vessel_id)` |
| `future_horizon_min` | 240.0 |
| `termination_mode`, `max_drain_extension_min` | `drain`, physics value |
| `nominal_duration_min`, `arrival_generation_end_min` | last arrival time |

**Realized projection** (audit-only, never shown to a policy): the same, but
`service_time_min = departure_time_min − berth_start_time_min` per vessel. It is
used with `find_schedule_violations` to prove that the realized space–time
schedule has no overlap or clearance violation. It exists only after a
`COMPLETED` episode.

## 12. Project 01 audit projection

At chosen checkpoints, Step 4 can project kernel state into a Project 01
`TerminalState` (via `Terminal.create(...).snapshot()`) to reuse Project 01's
cross-entity validator. Mapping:

| Project I | Project 01 |
| --- | --- |
| time `t_min` | `datetime(1970,1,1,tzinfo=UTC) + timedelta(minutes=t)` |
| Vessel phase NOT_ARRIVED / WAITING / BERTHING_PREP / HANDLING / DEPARTURE_PREP / DEPARTED | `VesselStatus` APPROACHING / WAITING / BERTHED / OPERATING / READY_TO_DEPART / DEPARTED |
| Occupying vessel | `BerthOccupancy` on one `Berth("QUAY", berth_length_m, min_clearance_m)` |
| Crane PRODUCTIVE / BLOCKED / IDLE | `CraneStatus` OPERATING / ASSIGNED / AVAILABLE |
| Container locations | `ContainerGroupLocation` TEU per (group, location); containers in TRANSFER are counted at their **source** (Project 01 moves inventory at task completion); EXTERNAL locations are omitted |
| Yard block | `YardBlock(block_id, capacity_teu, capabilities)` with `stored_groups` TEU per group and `reservations` keyed by group id (a group's open work orders summed) |
| Work orders | not projected (Project 01 tasks measure TEU progress and assign cranes per task) |

The projection is lossy by design. It never feeds back into the kernel.

## 13. Serialization

| Artifact | Format | Notes |
| --- | --- | --- |
| Scenario | `{scenario_id}.scenario.json`, UTF-8, `indent=2`, `sort_keys=True` | Immutable; fingerprints recomputed on load and must match |
| Run manifest | JSON | Fingerprints, policy, checkpoint hash, config hash, git commit/dirty, status |
| Ledger | JSONL, one ledger event per line, ordered by `sequence_number` | foundation §8 |
| Kernel event log | JSONL | Kernel events with priority and generation |
| State snapshot | JSON of `itp_state_v1` | For debugging and deadlock evidence |

Loading rejects unknown top-level keys, missing required fields and schema
version mismatches. It never fills defaults for absent required fields
(`UNSUPPORTED_ASSUMPTION`, DQ20).
