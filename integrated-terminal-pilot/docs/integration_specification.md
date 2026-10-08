# Integration Specification

Project I — Integrated Terminal Pilot, Step 1. Specification version
`itp_spec_v1`. Every statement below was checked against repository HEAD
`66990eba625488cd267ec194e7a8a0a900f697b5` (see
[repository_capability_audit.md](repository_capability_audit.md)).

## 1. Purpose and boundary

Project I builds one small, synthetic, deterministic container terminal in
which three decision layers act on shared physical resources:

1. **Berth** — which waiting vessel starts service now, and at which
   continuous quay position (Project 03 Dynamic BAP semantics).
2. **Quay crane allocation** — how many / which pooled quay cranes serve each
   berthed vessel (a simplified QCAP; no rail scheduling).
3. **Yard** — which yard block receives or supplies each container batch,
   under capacity, handling-rate and congestion limits.

The project measures (S1) how frozen berth-only policies behave when their
decisions are physically executed in this terminal, and (S2) whether
decisions that use crane and yard information improve terminal-wide
performance. Research questions, arms and statistics are in
[scientific_experiment_protocol.md](scientific_experiment_protocol.md).

### 1.1 Inside the boundary

- One continuous quay line; vessel arrivals; berth occupancy in space and time.
- A fixed pool of quay cranes, each assignable to one berthed vessel at a time.
- A horizontal-transport *cycle-time* abstraction between quay and yard.
- Yard blocks with geometry, TEU capacity, handling rate and congestion.
- Individually identified containers for import, export and transshipment.
- Landside gate-in (exports) and pickup (imports) as exogenous events.
- An append-only container movement ledger.

### 1.2 Outside the boundary (exclusions)

| Excluded | Status | Absorbable by v1 contracts without breaking changes? |
| --- | --- | --- |
| Rail-mounted crane routing, crane travel time, non-crossing, interference | DEFERRED to Project 04 | Yes: `QuayCraneRecord.position_m` and `rail_id` are reserved fields; kernel adds travel events. |
| Twin-lift, tandem-lift, restows, hatch-cover moves | DEFERRED | Yes: `extra_work_units` field (fixed to 0 in v1) and `lift_mode` in work orders. |
| Full 3D slot placement, relocation optimization, relocation RL | DEFERRED to Project 05 | Yes: G1 slot addresses and ledger relocation event types are specified now (see [container_yard_foundation.md](container_yard_foundation.md)). |
| Yard crane (RTG/RMG) scheduling and routing | DEFERRED | Partly: block handling capacity is an aggregate rate; equipment entities would be added as new resources. |
| Terminal tractor / AGV routing, road network | DEFERRED | Yes: transport is a cycle-time abstraction keyed by distance. |
| Vessel stowage planning, bay plans, stability | DEFERRED | Yes: container records carry no on-vessel slot; a nullable field can be added. |
| ETA uncertainty, productivity noise, crane failures | DEFERRED (disabled in v1 primary experiments) | Yes: exogenous streams are keyed by entity identity; crane failure states exist in Project 01's `CraneStatus`. |
| Multiple quays / discrete berths | DEFERRED | No for frozen PPO (single-quay training); yes for the kernel. |
| New PPO training, crane/yard RL, multi-agent RL, neural coordinator | Excluded | — |
| Commercial frontend, authentication, REST API, cloud, production TOS integration | Excluded | — |

## 2. Decision register

IDs are cited by every other document. "Confirm at" names the step that must
confirm or amend a PROPOSED item before validation results exist.

| ID | Decision | Status | Confirm at |
| --- | --- | --- | --- |
| D01 | Project directory `integrated-terminal-pilot/`; project id `project_i_integrated_terminal_pilot`; future Python package `integrated_terminal_pilot` under `src/` with its own `pyproject.toml`, depending on `terminal-core==0.1.0`, `mini-port-sim==0.1.0`, `berth-allocation-lab==0.1.0` | FROZEN | — |
| D02 | Simulation time is float **minutes** since episode start, field suffix `_min`. No `datetime` inside the kernel. Project 01 projections use fixed epoch `1970-01-01T00:00:00+00:00` plus minutes | FROZEN | — |
| D03 | Terminal coordinates: `x_m` along the quay, same origin and direction as Project 03 `berth_position_m`; `y_m` inland, quay line at `y_m = 0` | FROZEN | — |
| D04 | One continuous quay. Primary regime geometry `berth_length_m = 1200.0`, `min_clearance_m = 20.0` (Project 03 medium/heavy training geometry) | FROZEN | — |
| D05 | Execution engine: deterministic, cloneable event kernel (Approach B), not SimPy | FROZEN | — |
| D06 | Berth decisions start service **immediately**; execution never holds future berth reservations (Project 03 Dynamic semantics) | FROZEN | — |
| D07 | Berth decision epochs arise only from vessel arrival, vessel departure (berth release) and horizon entry, plus same-timestamp re-query after an assignment | FROZEN | — |
| D08 | Quay cranes are a pooled resource: no travel time, no rail order, exclusive to one vessel, at most `max_cranes` per vessel, non-preemptive within a work-order batch | FROZEN | — |
| D09 | Crane-to-service coupling: vessel handling rate = sum of per-crane rates with Project 02 multi-crane efficiency, recomputed whenever the vessel's crane count changes | FROZEN mechanism; coefficient values PROPOSED | Step 2 |
| D10 | Berth-position-to-yard coupling: per-crane transport cycle time from rectilinear quay–block distance caps the crane's rate | FROZEN mechanism; coefficients PROPOSED | Step 2 |
| D11 | Yard coupling: block handling capacity shared by concurrent flows, reduced by an occupancy congestion function; TEU capacity gates reservations | FROZEN mechanism; coefficients PROPOSED | Step 2 |
| D12 | Yard fidelity G0 (block-level) for execution; G1 (Bay/Row/Tier) data contracts mandatory; G1 bookkeeping disabled in primary experiments | FROZEN | — |
| D13 | Every container is an individual `ContainerRecord`; `ContainerGroup` remains a grouping layer | FROZEN | — |
| D14 | Exactly one ship-side crane move per container (single lift); `extra_work_units = 0` | FROZEN | — |
| D15 | Containers move in **work-order batches** of at most `batch_size_containers` (PROPOSED value 10) sharing one source, destination and container group | FROZEN mechanism; size PROPOSED | Step 4 |
| D16 | Per-vessel sequencing: discharge before load; a crane may start a ready load batch only when no discharge batch of that vessel can start because of yard capacity | FROZEN | — |
| D17 | Rollover (shut-out) rule: export/transshipment containers not in the yard `max_load_wait_min` (PROPOSED 240) after the vessel's last other work completes are rolled over; the vessel then proceeds to departure | FROZEN rule; value PROPOSED | Step 4 |
| D18 | No ETA noise: actual arrival = announced arrival; announcement at `arrival − H`, `H = 240` | FROZEN | — |
| D19 | Primary experiments have deterministic physics: productivity factor 1.0, crane failures disabled | FROZEN | — |
| D20 | Nominal service = Project 03 `planned_berth_occupancy_minutes` with `ServiceConfig(30.0, 0.5, 20.0)` | FROZEN | — |
| D21 | Realized berth occupancy = berthing preparation (30 min) + realized handling + departure preparation (20 min); berth released only at departure | FROZEN | — |
| D22 | Event priorities and tie-breaking of §8 | FROZEN | — |
| D23 | Seed bands and namespaced exogenous streams of the experiment protocol | FROZEN after collision audit (passed, see protocol §6) | — |
| D24 | Primary KPI: total vessel turnaround (minutes), drain-censored | FROZEN | — |
| D25 | Frozen PPO gate modes PASS-EXACT / PASS-FORECAST / BLOCK | FROZEN gate; forecaster formula PROPOSED | Step 6 |
| D26 | Information contract of §10 | FROZEN; landside forecast rules for forward models PROPOSED | Step 6 |
| D27 | Episode end: success, drain-limit truncation, deadlock, kernel failure (§9) | FROZEN | — |

## 3. Integrated components and reuse

Summary (the full inventory with import paths, contracts and risks is in the
audit):

| Concern | Source | Use in Project I |
| --- | --- | --- |
| Quay geometry, candidate positions, placement feasibility, schedule violations | `berth_allocation_lab.core` | DIRECT REUSE (pure functions) |
| Berth projection scenario, fingerprints | `berth_allocation_lab.data.BAPScenarioInstance`, `BAPVesselInput` | DIRECT REUSE |
| Nominal service formula | `berth_allocation_lab.scenarios.synthetic.planned_berth_occupancy_minutes` | DIRECT REUSE |
| Online FCFS / Online Rollout | `berth_allocation_lab.policies` | ADAPTER (visible-state projection) |
| Frozen Dynamic PPO | `berth_allocation_lab.rl.dynamic_checkpoint`, `envs.dynamic_observation` | ADAPTER + compatibility gate |
| Multi-crane efficiency | `mini_port_sim.scenario.ServiceConfig.crane_efficiency` | DIRECT REUSE |
| Keyed RNG derivation | `mini_port_sim.rng.RandomStreams` pattern | ADAPTER (entity-keyed streams) |
| Greedy crane, first-fit yard policies | `mini_port_sim.policies` | ADAPTER (same rules over kernel observations) |
| Enumerations: container size/flow/load state, yard capability, crane status, operation type, task status | `terminal_core` | DIRECT REUSE |
| `ContainerGroup` | `terminal_core.ContainerGroup` | DIRECT REUSE as grouping layer |
| Mutable `Terminal` aggregate | `terminal_core.Terminal` | NOT SUITABLE as kernel state; ADAPTER for audit projections |
| SimPy engine and processes | `mini_port_sim.simulation`, `processes` | NOT SUITABLE (BLOCKED BY REPOSITORY EVIDENCE for cloning) |

## 4. Shared state and ownership

One canonical logical state, `TerminalKernelState`, split into an immutable
`ScenarioDefinition` (never mutated, shared by reference between clones) and
mutable operational state. Each fact has exactly one owner; everything else
is a derived view recomputed or invariant-checked against it.

| Fact | Owner (single source of truth) | Derived views (never stored independently) |
| --- | --- | --- |
| Simulation time | `KernelClock.now_min` | — |
| Vessel phase, berth position, berth start, departure | `VesselState` | Berth occupancy list; Project 03 placements |
| Vessel visibility (HIDDEN / ANNOUNCED / visible) | `VesselState.visibility` | Observation slots |
| Crane assignment and status | `QuayCraneState.assigned_vessel_id`, `.status` | Vessel's crane set and count |
| Crane activity accounting | `QuayCraneState.activity` + time accumulators | Utilization KPIs |
| Container physical location and status | `ContainerState.location`, `.status` | Block occupied TEU / slot count, vessel on-board lists |
| Yard reservations | `YardBlockState.reservations[work_order_id]` | Reserved TEU |
| Work progress | `WorkOrderState.completed_moves`, `.status`, `.rate_moves_per_hour` | Vessel remaining moves |
| Pending future events | `EventQueue` | — |
| Event / ledger sequence counters | `KernelCounters` | — |
| Failure / termination status | `EpisodeStatus` | — |

Cached counters (for example `YardBlockState.occupied_teu`) are permitted for
speed but are asserted equal to the owner-derived value at every
post-transition invariant check in tests and at every Step 7 episode end.

The full field list and clone contract are in
[unified_data_contract.md](unified_data_contract.md#8-mutable-operational-state-itp_state_v1)
and [simulator_architecture_decision.md](simulator_architecture_decision.md).

## 5. Physical couplings (K3)

All three couplings are explicit functions of state, configurable, and
individually disableable (`*_enabled` flags) so that the degenerate
equivalence test can switch each off. All coefficients are synthetic,
non-calibrated and must be frozen before any validation result is read
(protocol §9).

### 5.1 Coupling A — crane allocation → realized service time

For crane `c` assigned to vessel `v`, with `n_v` cranes currently assigned to
`v`:

```text
crane_rate_c = nominal_moves_per_hour_c × eff(n_v) × productivity_factor
eff(1)=1.0, eff(2)=two_crane_efficiency, eff(3)=three_crane_efficiency,
eff(n≥4)=four_plus_crane_efficiency           # ServiceConfig.crane_efficiency
productivity_factor = 1.0                      # D19
```

`eff` is called through `mini_port_sim.scenario.ServiceConfig.crane_efficiency`
(direct reuse). Unlike Project 02, which fixes the factor when a task is
assigned (`processes/task_process.py::_effective_crane_moves_per_hour`), the
kernel recomputes it for every crane of `v` whenever `n_v` changes. This is a
documented, intentional divergence.

The vessel's handling phase ends when all of its ship-side moves are
complete; realized berth occupancy then follows D21. Service time is therefore
a *consequence* of crane allocation, not an input.

### 5.2 Coupling B — berth position → transfer burden

```text
quay transfer point of vessel v:  x_v = berth_position_m + length_m / 2,  y = 0
block transfer point of block b:  (transfer_point_x_m, transfer_point_y_m)
distance_m(v, b) = |x_v − transfer_point_x_m| + transfer_point_y_m      # rectilinear
cycle_min(d)     = 2 × d / transport_speed_m_per_min + handover_min
transport_rate_moves_per_hour(d) = transport_units_per_crane × 60 / cycle_min(d)
```

The transport rate caps the rate of every crane working a batch between `v`
and `b` (§5.4). Mechanism: each crane is served by a fixed gang of transport
units that must complete a round trip per move. This is a cycle-time
abstraction, not a road network and not a calibrated travel model. It is the
*only* way distance affects service. No undocumented distance multiplier
on crane productivity is permitted.

Gate trips consume block handling capacity (§5.3) only. Landside road travel is
not modelled.

### 5.3 Coupling C — yard occupancy and handling capacity → processing speed

Block `b` has a nominal handling capacity `μ_b` (moves per hour, all yard-side
equipment of the block aggregated) and a congestion factor based on
**physical** occupancy (reservations excluded):

```text
ρ_b = occupied_teu_b / capacity_teu_b
g(ρ) = 1                                              if ρ ≤ ρ0
g(ρ) = 1 − (1 − g_min) × (ρ − ρ0) / (1 − ρ0)          if ρ > ρ0
effective_capacity_b = μ_b × g(ρ_b)
```

`ρ0` and `g_min` are PROPOSED synthetic values (0.70 and 0.50). `g_min = 1.0`
disables congestion. Rationale: denser blocks need more internal
rehandling per useful move; this proxy stands in for relocations that G0 does
not simulate (Project 05 will).

**Capacity sharing.** Active flows at block `b` are partitioned into
ship-side (discharge, load) and landside (gate receive, gate release) flows.
Landside flows are guaranteed a share `landside_reserved_fraction` (PROPOSED
0.2) of `effective_capacity_b` when they have demand. Within each class, if
total demand exceeds the available capacity, each flow receives a share
proportional to its demand (deterministic proportional sharing). Unused
landside share is returned to ship-side flows, and vice versa.

**TEU capacity gate.** A discharge or gate-receive batch can start only if a
destination block passes the reservation test
`available_teu_b = capacity_teu_b − occupied_teu_b − reserved_teu_b − blocked_teu_b ≥ batch_teu`.

**Complete-block behaviour, buffering and blocking.** v1 has no quay apron
buffer (FROZEN). If no eligible block passes the test, the batch cannot start
and the crane enters `BLOCKED(YARD_CAPACITY)`. Gate-in containers that cannot
be received wait at `GATE` (status `AT_GATE`). There is no gate rejection in v1.

**Recovery.** Every event that frees yard TEU (load start, release start,
reservation cancellation) or changes handling capacity triggers a dispatch
decision at the same timestamp, so blocked work restarts without delay when
capacity exists.

### 5.4 Combined work rate

A ship-side batch `w` worked by crane `c` between vessel `v` and block `b`
requests

```text
demand_w = min(crane_rate_c, transport_rate(distance_m(v, b)))
```

and receives `rate_w = allocated_share_w ≤ demand_w` from §5.3. A landside
batch requests `gate_flow_demand_moves_per_hour` (PROPOSED: equal to `μ_b`, so
landside flows take whatever share they are allocated). All rates are
piecewise constant between kernel timestamps. Progress is settled exactly
(`Δmoves = rate × Δt / 60`) before any state change, and completion events
are rescheduled whenever a rate changes (§8.4).

Crane time accounting while assigned: `PRODUCTIVE` if working a batch with
`rate > 0`; `BLOCKED(reason)` otherwise, where reason ∈ {`VESSEL_NOT_READY`
(berthing preparation), `YARD_CAPACITY`, `CARGO_UNAVAILABLE`,
`NO_REMAINING_WORK`}. Rate loss from transport or yard sharing is measured
separately as `crane_rate_shortfall_moves = ∫ (crane_rate_c − rate_w) dt / 60`.

## 6. Operational ownership of decisions

| Layer | Decides | Never decides |
| --- | --- | --- |
| Berth policy | WAIT, or (waiting vessel, legal quay position) starting now | Cranes, blocks, timing of service completion |
| Crane policy | Assignment / release of available cranes to berthed vessels | Which batch a crane works (kernel dispatch rule D16), quay positions |
| Yard policy | Destination block for each discharge / gate-receive batch; G1 slot only if G1 active | Load source block (fixed by container location), timing |
| Coordinator (B arms) | Selects the berth action using permitted extra information or a forward model | Physical legality (the validator does) |
| Kernel | Physics, legality, dispatch order, inventory, events | Any choice delegated to policies |

All policies and coordinators submit actions to one `PhysicalActionValidator`
that is identical across arms. An illegal action raises before any state
mutation (Project 03 `DynamicBAPEnv._validate_action` convention). It is never
silently repaired.

## 7. Decision points

At each timestamp, after all events at that timestamp are processed (§8), the
kernel runs the decision phase in fixed order:

1. **BERTH** — if at least one vessel is WAITING and at least one legal
   immediate (vessel, position) exists, the berth policy is queried
   repeatedly until it returns WAIT or no legal assignment remains (same-time
   consecutive assignments are legal, as in Project 03). WAIT is legal only
   under the Project 03 rule: some *visible* future event exists, meaning an
   ANNOUNCED vessel with a later arrival, or an occupying vessel whose
   forecast release is later than now.
2. **CRANE** — queried once if any crane is AVAILABLE and any berthed vessel
   has fewer than `max_cranes` cranes and remaining work, or if the policy
   requested release opportunities. Output: a set of assignments/releases or
   no-op.
3. **DISPATCH** — kernel-driven. Every assigned, idle crane takes the next
   startable batch of its vessel by rule D16. For each discharge or
   gate-receive batch the yard policy chooses a destination block among
   blocks passing §5.3, then the kernel reserves TEU and starts the batch.
   Landside release and receive batches start when block capacity allows.

Berth epochs follow D07. Crane and yard events (batch completions,
preparation ends) do not create berth epochs. This preserves Project 03 decision
semantics for frozen berth policies.

## 8. Event contract and deterministic ordering

### 8.1 Event types and priorities (D22)

Events at the same timestamp are processed in ascending priority. Ties break
by stable entity key (lexicographic string), then by the monotonic scheduling
sequence number.

| Priority | Event | Effect |
| --- | --- | --- |
| 10 | `WORK_ORDER_COMPLETED` | Commit inventory of the batch (ledger `*_COMPLETED`); free crane for dispatch |
| 20 | `VESSEL_HANDLING_COMPLETED` | Scheduled at the timestamp of the vessel's last batch completion or rollover; release all cranes of the vessel; start departure preparation |
| 30 | `VESSEL_DEPARTED` | Berth released; on-board loaded containers → `DEPARTED_BY_VESSEL` |
| 40 | `BERTHING_PREP_COMPLETED` | Vessel becomes workable by its cranes |
| 50 | `LOAD_WAIT_TIMEOUT` | Apply rollover rule D17 |
| 60 | `GATE_IN_ARRIVAL` | Export container moves EXTERNAL_LANDSIDE → GATE |
| 65 | `PICKUP_DUE` | Import container becomes eligible for release |
| 70 | `VESSEL_ARRIVAL` | Vessel visible and WAITING; its inbound cargo `ABOARD_ARRIVED_VESSEL` |
| 80 | `HORIZON_ENTRY` | Vessel ANNOUNCED |

Releases precede acquisitions. The relative order of departure (30),
arrival (70) and horizon entry (80) matches Project 03
`_EVENT_PRIORITY = {SERVICE_COMPLETION: 0, VESSEL_ARRIVAL: 1, HORIZON_ENTRY: 2}`.
Same-timestamp grouping uses `berth_allocation_lab.core.numerics.is_close`
(absolute tolerance `1e-9` minutes).

### 8.2 Kernel cycle at a timestamp

```text
1. pop t = earliest valid event time;  require t ≥ now − 1e-9, else KernelTimeError
2. settle progress of all active work orders over [now, t]; accrue KPIs; now = t
3. process every valid event with time ≈ t in (priority, key, sequence) order
4. decision phase BERTH → CRANE → DISPATCH (§7)
5. recompute all rates; reschedule completion events whose rate changed
6. run invariant checks (tests and audit mode: all; production runs: cheap subset)
```

### 8.3 Protections

| Hazard | Rule |
| --- | --- |
| Negative / backward time | Scheduling at `t < now` raises `KernelTimeError` |
| Duplicated completion | Every scheduled completion carries the work order's `rate_generation`; stale generations are discarded on pop; a completion for a non-`IN_PROGRESS` order raises |
| Infinite same-timestamp loops | Each decision layer runs at most once per timestamp, except BERTH, which ends on WAIT or no legal assignment. Each assignment strictly reduces waiting vessels. A hard limit of `same_timestamp_cycle_limit` (PROPOSED 10,000) raises `KernelLivelockError` → episode `FAILED` |
| Hidden zero-duration resource use | A work order has ≥ 1 move and starts only with rate > 0. Preparation durations are ≥ 0 and explicit. No resource is held by an event with zero modelled duration except by declared preparation phases |
| Deadlock | Unresolved work with an empty valid event queue and no startable action → `DEADLOCK` (§9) |
| Orphaned cargo | Post-run audit: every container ends in a lifecycle-consistent status; containers on a departed inbound vessel are a fatal error |
| Invalid transitions | Container, vessel, crane and work-order transitions are validated against the declared tables; violation → `INVALID_STATUS_TRANSITION`, run `FAILED` |

### 8.4 Rate changes

Completion time of an in-progress batch is `now + 60 × remaining_moves / rate`.
When `rate` changes, `rate_generation` is incremented and a new completion
event is scheduled; the old event becomes stale. If the rate drops to zero
(only possible if a block's capacity drops to zero, which is not reachable in
v1), the batch stays `IN_PROGRESS` with no completion event, and the episode
can become a deadlock.

### 8.5 Minimal hand-worked trace (illustrative values)

Configuration: quay 600 m, clearance 20 m, `H = 240`; one crane `QC01` at 30
moves/h; transport and yard couplings disabled (non-binding);
`batch_size_containers = 2`; nominal service per D20.

| Vessel | Arrival | Length | Discharge | Load | Moves | Nominal service |
| --- | --- | --- | --- | --- | --- | --- |
| V001 | 0 | 200 m | C-000001 (20 ft), C-000002 (40 ft) | C-000101, C-000102 (20 ft, in block B01) | 4 | 30 + 0.5×4 + 20 = 52 min |
| V002 | 10 | 400 m | — | — | 0 | 50 min |

| t (min) | Priority / phase | Event or decision | State change |
| --- | --- | --- | --- |
| 0 | 70 | `VESSEL_ARRIVAL` V001 | V001 WAITING; C-000001/2 `ABOARD_ARRIVED_VESSEL` |
| 0 | 80 | `HORIZON_ENTRY` V002 (10 − 240 < 0 → 0) | V002 ANNOUNCED |
| 0 | BERTH | FCFS: V001 @ 0.0 m | V001 BERTHED [0, 200]; `BERTHING_PREP_COMPLETED` @ 30 |
| 0 | CRANE | QC01 → V001 | QC01 `BLOCKED(VESSEL_NOT_READY)` |
| 10 | 70 | `VESSEL_ARRIVAL` V002 | V002 WAITING; no legal position (needs 200+20+400 = 620 > 600) |
| 30 | 40 | `BERTHING_PREP_COMPLETED` V001 | V001 workable |
| 30 | DISPATCH | QC01 starts WO-000001 discharge {C-000001, C-000002} → B01, reserve 3 TEU | Containers VESSEL → TRANSFER; rate 30 → completes @ 34 |
| 34 | 10 | `WORK_ORDER_COMPLETED` WO-000001 | TRANSFER → YARD B01; reserved 3 → occupied 3 TEU |
| 34 | DISPATCH | QC01 starts WO-000002 load {C-000101, C-000102} from B01 | YARD → TRANSFER; B01 occupied −2 TEU; completes @ 38 |
| 38 | 10, 20 | WO-000002 completed; `VESSEL_HANDLING_COMPLETED` V001 | C-000101/2 `LOADED`; QC01 AVAILABLE; departure @ 58 |
| 58 | 30 | `VESSEL_DEPARTED` V001 | Quay free; C-000101/2 `DEPARTED_BY_VESSEL` |
| 58 | BERTH | FCFS: V002 @ 0.0 m | V002 waiting = 58 − 10 = 48 min |

A berth-only nominal model expects V001 to leave at 52 and V002 to wait
42 minutes. Physically, V001 occupies the quay until 58 (realized handling
8 min at 30 moves/h versus 2 min nominal at 0.5 min/move). Between 52 and 58,
the physical validator reports no legal position for V002. Nothing is moved,
overlapped or teleported.

## 9. Episode termination (D27)

| Outcome | Condition | Reported as |
| --- | --- | --- |
| `COMPLETED` | All vessels departed; all landside events processed; post-run audit clean | Valid episode |
| `TRUNCATED_DRAIN_LIMIT` | Next event later than `drain_limit_min = last_arrival_min + max_drain_extension_min` | Incomplete; unresolved vessels and containers listed |
| `DEADLOCK` | Unresolved work, no valid future event, no startable action | Incomplete; evidence snapshot saved |
| `FAILED` | Invariant, transition, livelock or validation error | Invalid run; excluded from KPIs; counted and reported |

Landside pickups of imports scheduled after the last vessel departure are
processed until the queue is empty or the drain limit is reached. Turnaround
censoring is defined in protocol §7.

## 10. Information contract (D26)

| Information | Generator | Kernel | Online policies | Forward models (A2, B2) |
| --- | --- | --- | --- | --- |
| Vessel arrival time, length, nominal service, move counts, container manifest | known | known | from HORIZON_ENTRY (`arrival − 240`) | same as online |
| Vessels not yet announced | known | known (queue) | **hidden**: no slot, count or bit | hidden |
| Realized progress, current rates, crane assignments, yard occupancy, reservations | — | known | observable (B arms); not consumed by frozen berth-only policies | B2: observable; A2: not modelled |
| Forecast berth release of occupying vessels | — | computed (§11) | observable | observable |
| Export gate-in times | known | queue | **hidden** until `GATE_IN_ARRIVAL` | public forecast only (PROPOSED: not simulated) |
| Import pickup times | known | queue | **hidden** until `PICKUP_DUE` | public forecast only (PROPOSED: not simulated) |
| Scenario id, seed, split, fingerprints | known | known | never in observations; only in `info`/records | never |

A forward model is the **same kernel code** run on an `ObservableClone`.
That clone is built by removing every hidden vessel and every hidden landside
event from the queue. It is never a raw deep copy of the full state.
Counterfactual leakage tests are specified in
[implementation_roadmap.md](implementation_roadmap.md#step-6--integrated-coordination-policies).

## 11. Service-time semantics (K4)

| Quantity | Definition | Nature | Who may read it |
| --- | --- | --- | --- |
| `nominal_service_time_min` | D20 formula from `workload_moves` | Immutable scenario input | All policies after announcement |
| `estimated_remaining_berth_time_min` | `ServiceForecaster` output (below) | Kernel-computed prediction | Policies, at decision time |
| `realized_service_progress` | `completed_moves / workload_moves` plus phase | Mutable kernel truth | Observable to B arms and forecaster |
| `realized_berth_release_time_min` | Timestamp of `VESSEL_DEPARTED` | Policy-dependent outcome | KPI only, after it happens |

`ServiceForecaster v1` (PROPOSED; frozen at Step 6 before validation), for a
vessel occupying the quay at `now`:

```text
remaining_prep  = time left in berthing preparation (0 if finished)
rate_now        = current total handling rate of the vessel (moves/h)
handling_left   = 60 × remaining_moves / rate_now    if rate_now > 0
                = 0.5 × remaining_moves              otherwise (D20 nominal minutes per move)
departure_left  = 20 if departure preparation not started, else its time left
estimated_release = now + remaining_prep + handling_left + departure_left   (> now, asserted)
```

The forecaster never reads the future event queue. Physical release happens only
at `VESSEL_DEPARTED`. How the forecast enters the frozen PPO observation is
governed by [bap_compatibility_contract.md](bap_compatibility_contract.md).

**Overrun resolution (single deterministic rule).** Because execution only
commits immediate starts on physically free quay (D06), an overrunning vessel
keeps its occupancy. Every candidate start that would overlap it is illegal
until its real departure, and a policy that "expected" the space waits. No
existing occupancy is moved, shortened or overlapped. The rule is identical
for every arm.

**Reservation vs. occupancy.** A `BerthReservation` (data contract only) is
a planned future rectangle owned by a policy or forward model; it never
blocks the physical quay in execution and is discarded at each decision. An
occupancy is a `VesselState` in phases `BERTHING_PREP`, `HANDLING`, or
`DEPARTURE_PREP`, and it blocks the quay until `VESSEL_DEPARTED`.

## 12. Terminology

| Term | Meaning |
| --- | --- |
| Container | One physical unit with one `container_id` |
| TEU | Capacity unit; 20 ft = 1.0, 40 ft = 2.0 |
| Move (crane move, work unit) | One ship-side crane lift of one container (D14) |
| Yard handling move | One yard-side lift into or out of a block (one per container per transaction) |
| Work order | A batch of 1..`batch_size_containers` containers with one source, destination and group |
| Berth projection | The Project 03 `BAPScenarioInstance` derived from a Project I scenario (nominal service) |
| Realized projection | Post-hoc rectangles with realized occupancy, for audit only |
| Visible cohort | Vessels ANNOUNCED, WAITING or occupying the quay at decision time |
