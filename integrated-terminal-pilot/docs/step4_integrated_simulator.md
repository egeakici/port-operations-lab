# Step 4 — Cloneable Integrated Terminal Simulator

Package `integrated_terminal_pilot.simulator`, kernel version `itp_kernel_v1`, state schema
`itp_state_v1`, ledger `itp_ledger_v1`, trace `itp_trace_v1`. Built on Step 3 commit `cc508ef`.

**SYNTHETIC — NOT CALIBRATED.** Step 4 establishes one correct, shared physical execution
environment. It does **not** answer S1 or S2, compares no policies, runs no experimental arm, loads
no PPO checkpoint and trains nothing. The berth decisions in every Step 4 run come from a labelled
**physical integration fixture** (Project 03 online FCFS over the kernel's legal set); it is not the
Step 5 berth adapter. Physics approval status: [step4_physics_approval_audit.md](step4_physics_approval_audit.md).

## 1. Architecture

One deterministic, cloneable, discrete-event kernel (D05, ADR ITP-ADR-001), not SimPy. Berth,
cranes, transport, yard storage and handling, landside requests and individual containers share one
clock and one event queue. The same transition code serves forward execution, deterministic
continuation from a copied state (`clone`, `snapshot`/`from_snapshot`) and, in Step 6, forward
models on an `observable_clone()`.

```text
Step 2 scenario (immutable) ──► ScenarioCatalog (shared by clones)
                                       │
            KernelState (mutable, plain data; cloned) ◄── TerminalKernel (one transition model)
                                       │
     decision-time observations ──► P_c / P_y (Step 3, unchanged) / FCFS fixture ──► actions
                                       │
                         PhysicalActionValidator (identical for every arm) ──► atomic commit
```

## 2. Module map

| Module | Content |
| --- | --- |
| `catalog.py` | `ScenarioCatalog` (immutable, indexed containers, vessels, cranes, blocks, physics), `PhysicsConfig`, observable redaction |
| `state.py` | `KernelState` and its records (`VesselState`, `CraneState`, `BlockState`, `WorkOrderState`, `PendingDecision`), explicit `clone()`, `to_dict`/`from_dict` |
| `events.py` | D22 priorities, queue entry layout, scheduling guard |
| `physics.py` | Couplings A/B/C, capacity sharing (`share_block_capacity`, closed form `allocate_block`), `ServiceForecaster v1` |
| `kernel.py` | `TerminalKernel`: cycle, event handlers, decisions, D16 dispatch, rates, timers, termination |
| `validator.py` | `PhysicalActionValidator` functions, `BerthAction`, rejection codes |
| `observations.py` | `BerthView` (fixture view), Step 3 `CraneObservation` / `YardObservation` builders |
| `observable.py` | `observable_clone()` |
| `ledger.py` | ledger records, transition table T1–T11, foundation §8.3 replay audit |
| `invariants.py` | INV01–INV20 (cheap and full sets), `shared_mutable_objects` |
| `metrics.py` | result, KPIs, per-vessel service explanation, post-run audits |
| `audit.py` | realized-schedule audit (Project 03), Project 01 `TerminalState` projection |
| `drivers.py` | `FcfsBerthIntegrationDriver` (fixture), `run_episode`, `default_policies` |
| `equivalence.py` | degenerate equivalence against Project 03 |
| `trace.py` | canonical trace export, digest, standalone validation |
| `cli.py` | developer commands (smoke, validate/replay, equivalence, measure) |

Scripts: `run_integrated_smoke.py`, `validate_integrated_trace.py`, `run_degenerate_equivalence.py`,
`measure_step4_performance.py`. New dependencies: none (standard library, NumPy for P95, the
already declared Projects 01–03).

## 3. Public API

| Call | Semantics |
| --- | --- |
| `TerminalKernel.from_scenario(doc, validate=True, invariant_mode="cheap")` | Step 2 validation, catalog, initial state, initial events |
| `kernel.advance(until_min=None, max_cycles=None)` | Run kernel cycles until a decision is needed (`DecisionRequest`), the episode ends (`EpisodeEnd`) or a limit is hit (`Paused`). Never loops forever: every cycle consumes an event, and same-time cycles are capped |
| `kernel.apply_berth_action / apply_crane_action / apply_yard_action` | **One decision application**, validated atomically against the pending decision |
| `kernel.step_event()` | **One event step**: process exactly the next timestamp group (all events within 1e-9 min); the decision phase of that timestamp stays pending |
| `kernel.peek_next_event()` | The next valid queue entry. Kernel truth, including hidden future events: the truth kernel is never given to a policy |
| `run_episode(kernel, berth_policy=…, crane_policy=…, yard_policy=…, until_min=…, max_cycles=…, max_decisions=…)` | **Run until termination** or a limit; validator rejections are recorded, never repaired (run `FAILED`) |
| `kernel.berth_view() / crane_observation() / yard_observation()` | decision-time observations (§8) |
| `kernel.clone()`, `kernel.observable_clone()`, `kernel.snapshot()`, `TerminalKernel.from_snapshot(catalog, snapshot)` | §7 |
| `kernel.validate_invariants(full=True)`, `kernel.result()` | §13, §14 |
| `kernel.forecast_release(vessel_id)` | `ServiceForecaster v1` (current state only) |

"Advance to next event" is `advance()` when no decision is pending; "advance until timestamp" is
`advance(until_min=t)` or `run_episode(..., until_min=t)`.

## 4. Kernel cycle and events

```text
EVENTS    pop earliest valid time t (≥ now − 1e-9); settle progress and KPI integrals on [now, t];
          process all events with time ≤ t + 1e-9 in (priority, entity key, sequence) order
BERTH     only if a D07 epoch event (arrival, departure, horizon entry) occurred: query until WAIT or
          no legal immediate assignment remains (re-query after each start)
CRANE     once, if a crane is available and a berthed vessel is below max_cranes with remaining work
DISPATCH  releases → ship-side batches (D16) → gate receipts; the yard policy chooses every
          discharge/receipt destination
FINALIZE  rollover timers, crane activity, rate recomputation, invariant checks
```

Event types and D22 priorities (lower first at equal time): `WORK_ORDER_COMPLETED` 10,
`VESSEL_HANDLING_COMPLETED` 20, `VESSEL_DEPARTED` 30, `BERTHING_PREP_COMPLETED` 40,
`LOAD_WAIT_TIMEOUT` 50, `GATE_IN_ARRIVAL` 60, `PICKUP_DUE` 65, `VESSEL_ARRIVAL` 70, `HORIZON_ENTRY` 80.
Releases precede acquisitions; departure < arrival < horizon entry matches Project 03.
Decision requests and retries are **phases**, not queue entries (spec §7, §8.2).

* Ordering key `(time, priority, entity key, sequence)`; event id `KE-nnnnnnnn` = sequence.
* Tolerance: Project 03 `is_close`, absolute 1e-9 min, one constant everywhere.
* An event scheduled at the current timestamp while a group is processed joins the rest of that
  group (no priority regression; it is never processed before an already processed event).
* Duplicate completions: each completion carries the work order's `rate_generation`; stale entries
  are discarded on pop; a completion for a non-`IN_PROGRESS` order raises.
* Cancellation: rollover timers carry a per-vessel generation.
* Scheduling before the clock or at a non-finite time raises `KernelTimeError`.
* Same-time guard: more than `same_timestamp_cycle_limit` cycles at one timestamp raise
  `KernelLivelockError` (run `FAILED`).

## 5. Canonical runtime state (`itp_state_v1`)

Immutable `ScenarioCatalog`: identity and fingerprints, quay, gate, blocks, cranes, vessels with
their discharge groups and load lists, containers (indexed 0..N−1 by id), initial locations,
physics, drain limit. Mutable `KernelState` (one owner per fact):

| Fact | Owner |
| --- | --- |
| clock, cycle phase, counters (`KE`, `LE`, `WO`, `DEC`) | `KernelState` scalars |
| event queue | `events` (heap of immutable tuples) |
| vessel phase, visibility, slot, berth position/start, handling and departure times, rollover | `VesselState` |
| crane assignment, status, activity, blocked reason, accumulators | `CraneState` (vessel crane sets are derived) |
| block occupancy cache, reservations (per work order), landside virtual clock | `BlockState` |
| container status, location kind/id, claim, transition index, times, rollover, pickup due | flat per-container lists |
| active work orders (members, progress, rate, generation) | `work_orders` |
| dispatch indexes (load-ready, release queue, gate queue, blocked yard requests) | dicts of lists, re-derived and checked by the full invariants |
| pending decision, episode status, KPI integrals, logs (ledger, events, decisions, blocking) | `KernelState` |

There is no runtime randomness (all exogenous draws are materialized in the scenario).

## 6. Physical rules

**Berth (Project 03 geometry, D06).** A berth action starts a WAITING vessel now at a continuous
position. Legal iff inside `[0, L]` and separated by `min_clearance_m` from every vessel that has not
departed (`are_spatially_separated`). Occupancy is released only by `VESSEL_DEPARTED`; a forecast
or nominal end never frees quay. Candidates offered to the fixture come from Project 03
`candidate_positions`; the validator accepts any legal continuous position. WAIT is legal only with
a legal assignment and a visible future event (Project 03 rule).

**Cranes (D08, D09).** Pooled, exclusive, ≤ `max_cranes` per vessel, assignable in
`BERTHING_PREP`/`HANDLING` with remaining work, released at handling completion (P_c never releases;
voluntary release only outside a batch). Rate of a working crane:
`nominal × eff(n_assigned) × 1.0` with Project 02 `ServiceConfig.crane_efficiency`. Assigned cranes
without a startable batch are `BLOCKED` with a reason (`VESSEL_NOT_READY`, `YARD_CAPACITY`,
`CARGO_UNAVAILABLE`, `NO_REMAINING_WORK`) and produce nothing. Status: `available` (idle),
`assigned` (blocked), `operating` (productive).

**Batches (D15, D16).** ≤ `batch_size_containers` (10) containers of one group, one source, one
destination, with exact member ids. Discharge before load; a load batch starts when all discharge
batches have started or the unstarted ones are blocked by yard capacity (rule R2). A work-order id
is committed only when the batch starts, so a yard `NO_ACTION` creates no phantom order.

**Yard (D11, Coupling C).** Storage gate `capacity − occupied − reserved − blocked ≥ batch_teu`.
Discharge/receipt batches reserve TEU at start (T2/T5) and commit it at completion (T3/T6);
load/release batches free TEU at start (T7/T9). Handling: `E_b = μ_b × g(ρ_b)` on physical
occupancy; landside flows get a guaranteed 20 % when they have demand; proportional sharing within
each class; unused share returned. Release admission: one release batch per block (rule R5). The
handling rate of a work order is `min(crane rate, transport rate)` capped by its block share.

**Transport (D10, Coupling B).** `d = |x_v − x_b| + y_b` (vessel hull centre to block transfer
point), `cycle = 2 d / 250 + 2`, `rate = 4 × 60 / cycle`. It caps the crane's batch rate; it is the
only way distance enters physics. No buffer exists (FROZEN): containers stay in `TRANSFER` only
inside a running batch.

**Pipeline.** Crane lift, transport and yard handling of one batch run concurrently at one rate
(the minimum of the stage limits after sharing); stage durations are never added. Progress is
fluid inside a batch (`Δmoves = rate × Δt / 60`), container commits are atomic at batch completion,
so each lift is discrete and counted once.

**Cargo lifecycles (foundation §4.4).** Import: `EXPECTED_BY_VESSEL → ABOARD_ARRIVED_VESSEL →
DISCHARGING → IN_YARD → RETRIEVING_TO_LANDSIDE → RELEASED_TO_LANDSIDE`; a pickup request before
availability waits and is served when the container reaches the yard. Export:
`EXPECTED_BY_LANDSIDE → AT_GATE → RECEIVING → IN_YARD → LOADING → LOADED → DEPARTED_BY_VESSEL`
(or from initial inventory). Transshipment: discharge at the inbound vessel, load at the outbound
vessel, one identity, two crane moves.

**Blocking and wakeup.** Retries are capacity driven: a yard `NO_ACTION` is remembered with the
yard capacity version; the request is asked again only after a TEU-freeing event (load or release
start) — never polled. Crane blocking episodes are recorded (crane, vessel, reason, start, end).

**Rollover (D17).** When a HANDLING vessel's only remaining work is load cargo that is not in the
yard, a `LOAD_WAIT_TIMEOUT` is scheduled 240 min later; cargo arriving cancels it; at timeout the
missing containers are `rolled_over` (ledger `ROLLED_OVER`) and the vessel completes handling. This
also resolves a crane held by a vessel that waits for cargo another vessel cannot discharge.

**Service (D20/D21).** Nominal service (input) and realized occupancy
`30 + realized handling + 20` (outcome) are kept separately per vessel, with
`estimated_release` from `ServiceForecaster v1` and a per-vessel explanation of the difference
(no-crane time, blocked crane time by reason, multi-crane efficiency loss, transport and yard
shortfall, rollovers).

## 7. Cloning

* `clone()` — truth-preserving copy for replay, regression and continuation. The catalog is shared;
  every mutable record and list is copied (C-level list copies for per-container arrays; immutable
  ledger/event tuples are shared by reference). `shared_mutable_objects` proves no mutable object
  is shared (INV20). **Not a legal oracle** for a policy: it contains the full future queue.
* `observable_clone()` — same kernel code, hidden information removed (§8). For Step 6 forward
  models.
* `snapshot()` / `from_snapshot()` — JSON round trip of the full state; continuation is identical.

## 8. Observations and the hidden-information boundary

Policies receive only immutable observations: `CraneObservation`, `YardObservation` (Step 3
contracts, built from current state) and the fixture `BerthView` (revealed vessels, legal choices,
WAIT bit, current forecasts). None contains future arrivals, gate-in or pickup times, completion
times, weights, scenario identity, seed or fingerprints. Tests perturb hidden future data (later
arrival of an unannounced vessel, pickup and gate-in times) and assert identical observations,
decisions and observable clones.

`observable_clone()` removes unannounced vessels (records, events, state), cargo that is neither in
the terminal nor on a visible vessel's manifest, every future `GATE_IN_ARRIVAL` / `PICKUP_DUE`, the
corresponding scheduled times, identity, fingerprints, ledger and event log, and replaces the drain
limit by the last *visible* arrival + extension. A kept container record may still reference the
id of an unannounced vessel (an observable container field, foundation §2); no record, arrival or
event of that vessel exists in the clone. Landside forecast rules for forward models remain a
Step 6 decision (D26).

## 9. Termination (D27)

| Status | Condition |
| --- | --- |
| `COMPLETED` | valid queue empty, all vessels departed, no active batch, nobody at the gate or due for release (rolled-over containers remain as reported residual inventory) |
| `TRUNCATED_DRAIN_LIMIT` | next valid event after `last arrival + max_drain_extension_min` (brief: DRAIN_LIMIT_REACHED) |
| `DEADLOCK` | valid queue empty and unresolved work; diagnostics list vessels, remaining work, blocked cranes, gate and release queues, blocked yard requests, block occupancy |
| `FAILED` | invariant, transition, livelock, forecast or validation error (brief: INVALID_PHYSICAL_STATE); the runner marks a validator rejection `FAILED` too |
| `Paused` (not an end) | `until_min` / `max_cycles` limit (brief: TIME_LIMIT_REACHED) |
| load-time `UnsupportedScenario` | G1 fidelity, non-default gate demand mode, productivity ≠ 1, unavailability windows, Step 2 validation failure (brief: UNSUPPORTED_SCENARIO) |

## 10. Invariants and audits

INV01–INV20 of the brief are implemented in `invariants.py` (cheap set every cycle; full O(N) set
in `invariant_mode="full"`, at construction and in `result()`). Post-run audits: full invariants,
foundation §8.3 ledger replay (duplicates, source/status replay, final locations, per-block TEU,
crane moves, yard moves, throughput), realized schedule via Project 03
`find_schedule_violations`, and the Project 01 `TerminalState` projection (data contract §12; lossy:
reservations and `PRE_EPISODE` groups are not projected because Project 01 cannot represent them).

Hand-worked Step 1 traces: §8.5 times and statuses are reproduced; it batches a 20 ft with a 40 ft
container (violating D15) and omits the initial 2 TEU of B01 in its counters, so the kernel runs two
batches with identical times and reports physical counters. Foundation §11.3 is reproduced exactly
(times, statuses, B01/B02 occupied and reserved TEU at every row) when its receipt is placed in
B02; frozen P_y first fit chooses B01 with identical times.

## 11. Trace schema

`events.jsonl`, `decisions.jsonl`, `ledger.jsonl`, `blocking.jsonl`, `rejections.jsonl`,
`final_state.json`, `result.json` — canonical (no wall clock), hashed in `manifest.json`
(`trace_sha256`); `engineering.json` holds timings. Ledger fields follow foundation §8
(`event_id`, `sequence_number`, `simulation_time_min`, `event_type`, `event_class`, container and
group ids, statuses, source/destination locations with null bay/row/tier and `BLOCK_ONLY`,
`quantity_teu`, `crane_moves`, `handling_resource_id`, vessel, work order, `causation_id` linking to
a `KE-` event or `DEC-` decision, `transition_index`, `idempotency_key`). `validate_trace_dir`
replays the ledger from the scenario's initial locations and checks hashes, order, causal links,
TEU and final state.

## 12. Metric definitions (all vessels included; unfinished censored at `T_end`)

| KPI | Unit / denominator |
| --- | --- |
| total / mean turnaround | vessel-min; `min(departure, T_end) − arrival`, all vessels |
| berth waiting (total, mean, P95) | min; `(berth start or T_end) − arrival` |
| realized occupancy, handling duration | min; departed / handled vessels |
| crane productive / idle / blocked by reason | crane-min over the episode |
| crane utilization | productive crane-min / (cranes × makespan) |
| crane rate shortfall (transport, yard) | moves of crane capacity not realized |
| peak and mean yard occupancy, peak block fraction | TEU, fraction of capacity |
| gate waiting | container-min at `AT_GATE` |
| pickup delay (mean, P95) | min; release completion − scheduled pickup, released imports |
| container / TEU throughput | containers / TEU reaching a terminal status (a transshipment counts once) |
| crane moves, yard moves | ledger counts (a transshipment container gives two crane moves) |
| unfinished workload, rolled-over containers | moves; containers and TEU |
| peak concurrent landside batches per block | batches |
| makespan, status, invalid actions | min; category; runner rejections |

## 13. Results (development data only; correctness checks, not policy results)

**Degenerate equivalence (gate).** 80/80 development scenarios pass (30 medium, 30 heavy, 10 low,
10 bottleneck; contiguous seeds from 10,000,000; 4–5 cranes at 120 moves/h). Against the real
Project 03 `DynamicBAPEnv` + `online_fcfs_action` on each berth projection: identical allocation
order; max position error 0.0 m; max start error 1.1e-13 min; realized occupancy = nominal within
4.5e-13 min; total waiting within 3.6e-12; total turnaround within 9.1e-13; realized schedules
valid. No cargo, crane or yard delay occurred, so no projection workaround was needed. This
establishes agreement of the berth layer only.

**Smoke runs** (FCFS fixture + P_c + P_y, standard physics, stored stabilized development files,
seed 10,000,000; every run repeated with an identical canonical trace digest, standalone trace
validation passed, all four post-run audits passed, no validator rejection):

| Family | Status | Departed | Containers | Crane moves | Unfinished moves | Mean realized occupancy | Crane capacity lost to yard share | Busiest block busy | Mean pickup delay | Run time |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| itp_low | COMPLETED | 8/8 | 10,888 | 4,796 | 0 | 1,460 min | 3,959 moves | 93 % (B01) | 284 min | 1.3 s |
| itp_medium | COMPLETED | 16/16 | 13,634 | 8,762 | 0 | 1,830 min | 8,061 moves | 100 % (B01) | 1,365 min | 1.8 s |
| itp_heavy | TRUNCATED_DRAIN_LIMIT | 19/24 | 16,369 | 12,153 | 2,514 | 1,709 min | 7,814 moves | 72 % (B02) | 2,287 min | 1.6 s |
| itp_yard_bottleneck | TRUNCATED_DRAIN_LIMIT | 10/18 | 17,254 | 6,352 | 3,495 | 3,765 min | 15,176 moves | 100 % (B01) | 1,001 min | 2.1 s |

Incomplete runs: heavy leaves V017, V020 in HANDLING and V022–V024 WAITING at `T_end` = 11,163.5;
bottleneck leaves V008, V009, V013, V015 in HANDLING and V014, V016–V018 WAITING at 11,977.0. Cause:
realized handling is several times nominal (four cranes, ≤ 2 per vessel, transport and yard
limits) and P_y first fit concentrates discharge on one block whose ship-side handling share
(48 / 24 moves/h) is below a two-crane vessel's 55.2 moves/h. No deadlock occurred.

**Yard bottleneck reality check (§44).** In the bottleneck family the yard binds through
*handling rate*, not storage: B01 is busy 100 % of the episode, cranes lose 15,176 moves of
capacity to the yard share (about twice the reference families), while no crane was ever blocked
by TEU capacity (`YARD_CAPACITY` 0 crane-min) and no truck waited at the gate. Hand-worked case J
reproduces a yard-limited delay exactly (16 moves/h ship-side, 37.5 and 39.0 min).

**Engineering measurements** (Windows, CPU, single process; not an SLA):

| Quantity | itp_heavy | itp_medium |
| --- | ---: | ---: |
| scenario file / load | 15.3 MB / 0.065 s | 12.8 MB / 0.055 s |
| catalog build (with Step 2 validation) | 0.044 s (0.32 s) | 0.034 s (0.26 s) |
| kernel init | 0.019 s | 0.014 s |
| clone at t ≈ 1500 (mean of 20) | 1.3 ms | 1.5 ms |
| clone traced allocation | 1.7 MB | 1.5 MB |
| observable clone | 65 ms | 51 ms |
| one yard action application | 30 µs | 40 µs |
| mean kernel cycle | 0.30 ms | 0.26 ms |
| result + full audits | 2.3 s | 1.9 s |
| canonical trace (ledger / total) | 53 MB / 74 MB | 46 MB / 67 MB |

The 6.8 MB container catalog is shared by every clone; per-container mutable facts are flat lists
copied at C speed. The ledger dominates trace size.

## 14. Known limitations

* All non-approved coefficients are synthetic and PROPOSED; several execution rules (audit §4) need
  review; R5 changes landside timing relative to a literal unbounded processor-sharing reading.
* P_y first fit concentrates yard work on one block; heavy and bottleneck development seeds truncate
  at the drain limit (audit §5).
* G0 only: no slots, stacking, accessibility or relocations (Project 05 can replace the storage
  component; the ledger already reserves relocation types).
* Single gate, no road network, no crane travel, no failures, no stochastic physics.
* Trace files are large (the ledger of a heavy run is tens of MB).

## 15. Step 5 integration requirements

1. Implement the `BerthViewAdapter` on top of `berth_view()`, `legal_berth_choices()`,
   `berth_wait_legal()` and `forecast_release()`; assert mask = physical legal set (G08).
2. Use `run_episode` with the same validator; any rejection fails the run.
3. Resolve the review items of the physics audit (§3, §4, §5) before any validation comparison.
4. Keep P_c / P_y identical in every arm; do not change kernel physics per arm.
