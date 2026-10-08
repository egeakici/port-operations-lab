# Repository Capability Audit

Factual inventory of Projects 01–03 for Project I integration. Everything here
was read from source at HEAD `66990eba625488cd267ec194e7a8a0a900f697b5`
("feat: add BAP interactive replay visualization"), not from historical
descriptions.

## 1. Preflight record

| Check | Result |
| --- | --- |
| `git status --short` | empty (clean worktree) |
| `git log -5 --oneline` | `66990eb` replay viz · `bae5def` finalize BAP lab · `c5cc52e` results warehouse · `bcd84b1` benchmark diagnostics · `d0cff55` benchmark core |
| `git rev-parse HEAD` | `66990eba625488cd267ec194e7a8a0a900f697b5` = expected HEAD |
| `integrated-terminal-pilot/` before Step 1 | existed, empty, untracked |
| Project 03 completion | `03-berth-allocation-lab/README.md` and `docs/project03_final_report.md` both state **PROJECT 03 COMPLETE**, Steps 1–13; final release `experiments/results/project03/project03_final_v1/` (Git-ignored) |
| Environment | Python 3.13.2; editable installs of `terminal-core 0.1.0`, `mini-port-sim 0.1.0`, `berth-allocation-lab 0.1.0`; simpy 4.1.2; gymnasium 1.2.3; numpy 2.2.3; stable_baselines3 2.8.0; sb3_contrib 2.8.0; torch 2.6.0; pytest 9.1.1 |

Actual project directories: `01-terminal-operations-core`,
`02-mini-port-simulation`, `03-berth-allocation-lab`. The directories
`04-rail-crane-scheduler` through `08-benchmark-system` exist locally but are
Git-ignored placeholders (`.gitignore`: "Planned projects are kept local until
they are ready"). The root `README.md` still lists Project 03 as "NEXT". This is
stale documentation and is not modified by Step 1.

## 2. Baseline tests (run during Step 1, no code changed)

| Project | Command (from project dir) | Result |
| --- | --- | --- |
| 01 | `python -m pytest -q -p no:cacheprovider` | **426 passed**, 0 failed, 0 skipped (28.4 s) |
| 02 | `python -m pytest -q -p no:cacheprovider` | **55 passed**, 0 failed, 0 skipped (1.7 s) |
| 03 | `python -m pytest -q -m "not slow" -p no:cacheprovider` | **463 passed**, 8 deselected (`slow` marker), 0 failed (293.6 s) |

Project 03 `slow` tests (multi-seed invariants, multi-run training) were not
run. No training, held-out evaluation or release rebuild was performed.

## 3. Project 01 — `terminal_core`

Path `01-terminal-operations-core/src/terminal_core/`; import `terminal_core`.

| Component | Public API (verified) | Contract / assumptions | Integration risk | Decision |
| --- | --- | --- | --- | --- |
| `Vessel` (`vessel.py`) | fields `vessel_id, length_m, eta: datetime, workload_moves: int, priority (1–3), max_cranes ≥ 1, status`; `transition_to`, `to_dict/from_dict` | `VesselStatus`: APPROACHING→WAITING→BERTHED→OPERATING→READY_TO_DEPART→DEPARTED, strictly linear | `eta` is a `datetime` (Project I uses minutes, D02); no ANNOUNCED/HIDDEN; no berthing-prep phase | ADAPTER REQUIRED (projection only); vocabulary mapped in data contract |
| `Berth`, `BerthOccupancy` (`berth.py`) | `place_vessel`, `remove_vessel`, `has_safe_clearance`, `min_clearance_m` default 20.0 | Spatial only (no time dimension); quay starts at 0 | Cannot express space–time schedules; Project 03 core does | ADAPTER REQUIRED (audit projection); physics uses Project 03 core |
| `QuayCrane` (`quay_crane.py`) | `crane_id, position_m, moves_per_hour`; `assign_to_vessel`, `release_from_vessel`, `start_operation`, `stop_operation`, `mark_failed`, `repair`, maintenance | `CraneStatus` AVAILABLE/ASSIGNED/OPERATING/FAILED/MAINTENANCE; one vessel at a time | None for vocabulary; class itself is mutable and per-task-assigned in `Terminal` | DIRECT REUSE of `CraneStatus`; record fields mirrored |
| `YardBlock` (`yard_block.py`) | `block_id, capacity_teu, capabilities: set[YardCapability], status`; `reserve_capacity`, `commit_reservation`, `cancel_reservation`, `store_group`, `release_group`; `occupied_teu`, `reserved_teu`, `available_teu`, `occupancy_ratio` | Stores **TEU per group id** (`stored_groups: dict[str, float]`); no geometry, no coordinates, no slots, no handling rate, no individual containers | Cannot hold container identity or Bay/Row/Tier; reservation semantics (reserve → commit) are sound and adopted | ADAPTER REQUIRED; reservation semantics reused; geometry added by Project I (see §6) |
| `YardCapability`, `YardBlockStatus` | enums GENERAL/REEFER_POWER/HAZARDOUS/EMPTY; OPEN/CLOSED/MAINTENANCE | — | — | DIRECT REUSE |
| `ContainerGroup` (`container_group.py`) | frozen; `group_id, container_size: ContainerSize, quantity: int > 0, flow, load_state, is_reefer, is_hazardous, source_vessel_id, target_vessel_id`; `teu_per_container`, `total_teu`, `required_yard_capabilities` | Homogeneous group. Flow rules: IMPORT needs source and forbids target; EXPORT forbids source and needs target; TRANSSHIPMENT needs both, distinct. Empty ⇒ not reefer, not hazardous | Group-level only, no member ids | DIRECT REUSE as grouping layer (D13) |
| `ContainerSize`, `ContainerFlow`, `ContainerLoadState` | `20_ft`, `40_ft`; `import`, `export`, `transshipment`; `laden`, `empty` | 20 ft = 1.0 TEU, 40 ft = 2.0 TEU | — | DIRECT REUSE |
| `OperationTask`, `TaskLocation` (`operation_task.py`) | `task_type: OperationType` (DISCHARGE, LOAD, YARD_TRANSFER, GATE_IN, GATE_OUT), `planned_teu`, `source/target: TaskLocation(VESSEL/YARD_BLOCK/GATE, id)`, status machine CREATED→READY→ASSIGNED→IN_PROGRESS→(BLOCKED)→COMPLETED/CANCELLED/FAILED, `record_progress` in TEU | Progress measured in **TEU**, not moves; routes fixed per type | TEU progress ≠ move progress | DIRECT REUSE of `OperationType`, `OperationTaskStatus`, `TaskLocationType` vocabularies; work orders are Project I records |
| `TerminalEvent` (`terminal_event.py`) | frozen; `event_id "EVT-nnnnnn", event_type, occurred_at: datetime, entity_type, entity_id, payload (MappingProxy), correlation_id, causation_id` | Entity-level events; payload frozen via `MappingProxyType` | Not container-level; **not deep-copyable** (probe §7) | NOT SUITABLE as ledger; its `causation_id`/`correlation_id` convention is adopted |
| `TerminalState` (`terminal_state.py`) | immutable snapshot, `capture(...)`, `to_dict/from_dict`, `ContainerGroupLocation(group_id, location, teu)`, extensive cross-entity validation, `TERMINAL_STATE_SCHEMA_VERSION = 1` | Inventory = TEU per (group, location type, location id) | Useful independent validator for projections | ADAPTER REQUIRED (projection target for audits) |
| `Terminal` aggregate (`terminal.py`) | `create`, `register_*`, `arrive_vessel`, `berth_vessel`, `assign_task_resource`, `start_task`, `record_task_progress`, `complete_task`, `depart_vessel`, `snapshot`, `to_dict/from_dict` | Every command runs `_atomic()`: full `to_dict()` before, `snapshot()` validation after, full restore on error. Inventory moves atomically **at task completion** (`_complete_inventory_transfer`). Departure requires no assigned cranes, no active ship-side tasks, and no remaining source cargo | Cost grows with event log (probe §7); deep copy fails; datetime-based; ship-side crane assignment is **per task** | NOT SUITABLE as kernel mutable state (BLOCKED BY REPOSITORY EVIDENCE, see architecture decision); ADAPTER for audit projections |
| `integration.py` | `build_reference_terminal`, `run_reference_scenario` | Deterministic reference scenario | — | DEFERRED (regression reference only) |
| Streamlit `app/` | UI | — | Not reusable inside the kernel | NOT SUITABLE (UI only) |

Physical/domain invariants worth preserving in Project I (each has an analogue
in the data contract): departure preconditions; non-negative inventory;
reservation and stored TEU never exceed capacity; crane assigned ⇒ vessel
berthed; vessel `max_cranes` limit; flow/vessel link rules; task route
types.

## 4. Project 02 — `mini_port_sim`

Path `02-mini-port-simulation/src/mini_port_sim/`; import `mini_port_sim`.

| Component | Verified behaviour | Integration risk | Decision |
| --- | --- | --- | --- |
| `PortSimulation` (`simulation.py`) | Wraps a Project 01 `Terminal` and a `simpy.Environment`; processes are Python generators registered with `env.process`; dispatch via one-shot `simpy.Event`s re-created after trigger; `run`, `run_scenario` (horizon or drain mode with `SimulationDrainTimeoutError`) | Generators cannot be copied or pickled (probe §7). Continuation state lives in generator frames | NOT SUITABLE as execution engine (BLOCKED BY REPOSITORY EVIDENCE for cloning) |
| `RandomStreams` (`rng.py`) | Named streams; seed = first 8 bytes of `sha256(f"{master_seed}:{stream_name}")`; streams created lazily | Deterministic per name, but **consumption order** is policy-dependent: the `productivity` stream is drawn once per crane dispatch in `crane_dispatcher.py::_productivity_factor` | ADAPTER REQUIRED: keep the hashing pattern; key streams by entity identity |
| `ScenarioConfig` and sub-configs (`scenario.py`) | `TerminalConfig(berth_length_m=1200, min_clearance_m=20, quay_crane_count=4, quay_crane_moves_per_hour=30, yard_block_count=3, yard_block_capacity_teu=2000)`, `TrafficConfig`, `ServiceConfig(30, 0.5, 20, 0.92, 0.82, 0.72)`, `DisruptionConfig` | Shared with Project 03 generator | DIRECT REUSE of `ServiceConfig` (formula and efficiency); other configs referenced as defaults |
| `ServiceConfig.crane_efficiency(n)` | 1.0 / 0.92 / 0.82 / 0.72 for n = 1 / 2 / 3 / ≥ 4 | Pure | DIRECT REUSE (D09) |
| `FCFSLeftmostPolicy` (`policies/berth_policy.py`) | First waiting vessel with any leftmost feasible gap on a Project 01 `Berth` | Spatial-only; not the Project 03 online FCFS (which also orders candidates by position) | DEFERRED (Project 03 online FCFS is the reference) |
| `GreedyCranePolicy` (`policies/crane_policy.py`) | For one vessel: assigns `min(ready tasks, available cranes, spare max_cranes)` cranes in crane-id order | Operates on Project 01 `Terminal` tasks | ADAPTER REQUIRED: same rule re-expressed over kernel observations (Step 3), with equivalence tests |
| `FirstFitYardPolicy` (`policies/yard_policy.py`) | First OPEN block in id order supporting capabilities with `available_teu − planned ≥ group TEU` | Operates on Project 01 `Terminal` | ADAPTER REQUIRED (Step 3), equivalence-tested |
| Detailed operations (`processes/task_process.py`, `vessel_process.py`) | Creates **IMPORT-only** 20 ft groups with `quantity = workload_moves`, so 1 move = 1 container = 1 TEU implicitly. Splits into `min(max_cranes, crane_count)` chunks; reserves yard for the whole vessel at once; stored cargo never leaves the yard; crane efficiency fixed at assignment | Conflates moves/containers/TEU; no export/transshipment/landside flow; yard fills monotonically | NOT SUITABLE as integrated physics; documented as the origin of a unit conflation that Project I must not inherit |
| `VesselArrivalGenerator` (`arrivals/vessel_generator.py`) | Vessels `V001…`, exponential inter-arrivals, `priority=2`, `max_cranes=2`, optional ETA noise | Generates `Vessel` with datetime ETA | DEFERRED (Project 03 generator is the berth reference) |
| `crane_failure_process` | Per-crane stream `failure:{crane_id}` (identity-keyed) | Pattern adopted for future failures | DEFERRED (D19) |
| Metrics (`metrics/collector.py`) | Vessel lifecycle metrics, berth/crane/yard utilization, queue length | Bound to `PortSimulation` | DEFERRED (definitions consulted for KPI naming) |
| Scenarios JSON (`scenarios/*.json`) | e.g. `yard_bottleneck`: 2 blocks × 800 TEU, seed 42 | — | Reference only |

## 5. Project 03 — `berth_allocation_lab`

Path `03-berth-allocation-lab/src/berth_allocation_lab/`; import
`berth_allocation_lab`.

| Component | Verified contract | Integration risk | Decision |
| --- | --- | --- | --- |
| `data.BAPVesselInput` | frozen `vessel_id, arrival_time_min ≥ 0, length_m > 0, service_time_min > 0, workload_moves: int \| None` | — | DIRECT REUSE (berth projection) |
| `data.BAPScenarioInstance` | frozen; `formulation` static/dynamic; `split` ∈ {train, validation, test}; `data_provenance == "synthetic"`; vessels ordered by arrival; dynamic ⇒ `termination_mode="drain"`, default `max_drain_extension_min=10080`; `content_fingerprint` = sha256 of sorted JSON | Split vocabulary is {train, validation, test}; no "development" | DIRECT REUSE. Projection `split` mapping is fixed: development → `"train"`, validation → `"validation"`, test → `"test"`. The authoritative split is always the Project I record (data contract §11) |
| `scenarios.synthetic.planned_berth_occupancy_minutes` | `berthing_prep + workload × service_minutes_per_move + departure_prep` = 30 + 0.5·W + 20 | Equals 120 moves/h handling. Project 02 physics with `max_cranes=2` at 30 moves/h × 0.92 gives 55.2 moves/h | DIRECT REUSE as **nominal** service (D20); the calibration gap is a central S1 mechanism, documented in the compatibility contract |
| `core.types.BAPPlacement` | `vessel_id, berth_position_m, berth_start_time_min, length_m, service_time_min`; half-open `[start, end)` | — | DIRECT REUSE |
| `core.geometry`, `core.candidates.candidate_positions`, `core.feasibility.is_placement_feasible`, `find_schedule_violations` | Pure functions; clearance between hulls, not at quay ends; tolerance `1e-9` | `is_placement_feasible` builds the proposed rectangle from `vessel.service_time_min`; `find_schedule_violations` reports `VESSEL_MISMATCH` unless `placement.service_time_min == vessel.service_time_min` | DIRECT REUSE for legality; realized schedules are audited through a separate **realized projection** (ADAPTER) |
| `core.objectives` | `waiting_time`, `turnaround_time = service_end − arrival`, `total_waiting_time` | Same pinning as above | DIRECT REUSE on matching projection |
| `envs.DynamicBAPEnv` (`dynamic_bap_env_v1`) | Statuses HIDDEN→ANNOUNCED→WAITING→IN_SERVICE→COMPLETED; heap events `(time, priority, vessel_id, kind)` with priorities SERVICE_COMPLETION 0 < VESSEL_ARRIVAL 1 < HORIZON_ENTRY 2; action `0 = WAIT`, `1 + slot·P + candidate`, `P = 2M`; slots allocated at first reveal, never reused; assignments start at `current_time_min` only; WAIT legal only with a visible future event; `_service_duration_min(vessel)` hook returns nominal | Fixed nominal duration; private fields read by the observation encoder | DIRECT REUSE as **berth-only reference evaluator** on projections (S1) and as checkpoint-loading host; ADAPTER for integrated execution |
| `envs.dynamic_observation` (`dynamic_obs_v1`) | See §5.1 | Encoder reads private env attributes | ADAPTER (duck-typed source) — gate in compatibility contract |
| `envs.DynamicVisibleState` | `current_time_min, berth_length_m, min_clearance_m, future_horizon_min, vessels_by_slot, statuses_by_slot, active_placements, legal_choices, wait_legal` | Public, causal | ADAPTER target for FCFS/Rollout |
| `policies.dynamic_fcfs.online_fcfs_action(env)` | min over `legal_choices` by `(arrival, vessel_id, position)`; never WAITs | Needs an object exposing `legal_choices` | ADAPTER REQUIRED (trivial) |
| `policies.dynamic_online_rollout.online_rollout_choice(visible)` | Evaluates WAIT (if legal) and every legal action by a visible-cohort continuation with nominal service and FCFS completion; tie-break by action index; uses `copy.deepcopy` of a plain-data continuation | Berth-only nominal model by construction | DIRECT REUSE on adapter-built `DynamicVisibleState` (arm A2) |
| `rl.dynamic_checkpoint.load_dynamic_checkpoint(path, env, allow_cross_horizon=False)` | Requires sidecar `*.metadata.json`; checks policy id/architecture, env/obs versions, `max_vessels`, `action_capacity`, scales, reward scale, `horizon_min == env.future_horizon_min`, candidate capacity, spaces and architecture; loads on **CPU** | Needs a `DynamicBAPEnv` instance (attributes set at `reset`) | DIRECT REUSE with a projection-backed `DynamicBAPEnv` used only as a compatibility host |
| `rl.dynamic_joint_scoring.DynamicJointMaskablePolicy` | Shared vessel encoder over `vessel_features ⊕ status ⊕ placement_features` (10 inputs), context, WAIT head, assignment scorer | Consumes exactly `dynamic_obs_v1` | DIRECT REUSE (frozen weights) |
| `rl.dynamic_config` | `POLICY_ID = dynamic_maskable_ppo_v1`, `REWARD_SCALE = 1/1440`, training seeds must be `(11, 23, 37)`; validation ≥ 5M, test ≥ 6M, diagnostics ≥ 7M | — | Provenance constants |
| Static BAP, static PPO, candidate-space exact | Static formulation | Not the principal environment (K2) | DEFERRED (reference only) |
| `results/`, `benchmark/`, `replay/` | Frozen release tooling | Must not be rebuilt | NOT SUITABLE for modification; read-only |
| `integration/__init__.py` | Docstring only: "Adapters for using Project 01 and Project 02 without copying them." | Empty package | Not used (Project I adapters live in Project I) |

### 5.1 Dynamic PPO observation fields (`dynamic_obs_v1`, verified in `envs/dynamic_observation.py`)

`M = max_vessels`, `P = 2M`, `N = 1 + M·P`, `scale = 1440 min`,
`length_scale = 1000 m`, `quay = berth_length_m`.

| Key | Shape | Exact value per slot / row | Space bounds |
| --- | --- | --- | --- |
| `current_time` | (1,) | `now / 1440` | [0, f32max] |
| `horizon` | (1,) | `H / 1440` | [0, f32max] |
| `terminal_features` | (2,) | `quay / 1000`, `min_clearance_m / quay` | [0, f32max] |
| `vessel_features` | (M,3) | `(arrival − now)/1440`, `length/quay`, `service_time_min/1440` | ±f32max |
| `visible_mask` | (M,) | 1 if slot allocated | binary |
| `status_features` | (M,4) | one-hot ANNOUNCED, WAITING, IN_SERVICE, COMPLETED | binary |
| `placement_features` | (M,3) | if IN_SERVICE: `position/quay`, `(start − now)/1440`, `(end − now)/1440`; else zeros | ±f32max |
| `candidate_features` | (N,2) | per legal action: `position/quay`, `(now − arrival)/1440` | [0, f32max] |
| `action_mask` | (N,) | legal actions incl. WAIT bit | binary |

In Project 03, `end − now > 0` for every IN_SERVICE vessel at a decision,
because completions are processed before decisions at their exact nominal
time. Crane and yard state have no field.

### 5.2 Frozen checkpoint provenance (read-only)

Location: `03-berth-allocation-lab/experiments/rl/dynamic_extended_cuda/`
(Git-ignored). Hashes computed in Step 1 match
`validation_decision.json` (`dynamic_rule_1`, H = 240, `uses_test_results:
false`, source commit `1b71b5d4…`, file SHA-256 `f2f91234…3423`, equal to its
`.sha256` sidecar).

| Regime | Seed | `max_vessels` | Actions | Checkpoint SHA-256 |
| --- | --- | --- | --- | --- |
| tiny | 11 | 8 | 129 | `35a1a0ba0b8d231fb26b2aa2ecfebad49e9b3ab9a949c2ea306054dbe1a7f46d` |
| tiny | 23 | 8 | 129 | `4773a36832f02179e27bd00e4308829ae9a4eb00612ad8528b6975b88628c874` |
| tiny | 37 | 8 | 129 | `7a3138ce37f3ef18c7c1b74df7e20f7a977f552a2e69e21dea828c79a9cd956a` |
| medium_heavy | 11 | 24 | 1153 | `3373e06060a6f14cae422d7041d863cf18001bed285d1b896bffbe4dfae32018` |
| medium_heavy | 23 | 24 | 1153 | `a2a105108d9b030cec8e26538012cbe1c2c2bc872f992e1a11ac0cd428ffd625` |
| medium_heavy | 37 | 24 | 1153 | `8318b49712fbbd04c6adbf1b357e2c5916fae539306b50272ded7464d002a3a6` |

Every sidecar: `horizon_min 240`, `time_scale_min 1440.0`,
`length_scale_m 1000.0`, `observation_version dynamic_obs_v1`,
`environment_version dynamic_bap_env_v1`,
`policy_architecture dynamic_joint_action_scoring_v1`, candidate capacity
`2M`. Training geometry: tiny quay 600 m, medium/heavy quay 1200 m, both
clearance 20 m; vessel length U[200, 360] m; workload U{250…900} moves;
medium 16 vessels / mean inter-arrival 190 min; heavy 24 / 120 min. Training
seeds were sampled from all train-split generation seeds
(`seed % 3 == 0`, below `2**31 − 1`) of the Project 03 generator.

## 6. Current YardBlock data limitations (for Project 05 readiness)

1. No container identity: `stored_groups` maps group id → TEU.
2. No geometry: no bays, rows, tiers, coordinates, orientation, or transfer point.
3. No handling capacity or congestion.
4. Partial release by TEU (`release_group(group_id, teu)`) can create
   fractional-container states that a container model forbids.
5. Capabilities are block-level; there is no size compatibility (20/40 ft) per slot.
6. Reservations are per group id, not per work order.

Project I therefore defines `YardBlockRecord` (geometry and handling) and
`ContainerRecord` (identity and location). It projects to `YardBlock`
(`capacity_teu`, `capabilities`, status, TEU per group) only for audit.
Project 01 is not modified.

## 7. Empirical probes (scratch scripts outside the repository)

| Probe | Observation |
| --- | --- |
| `copy.deepcopy(PortSimulation)` after 300 simulated minutes of `scenarios/smoke.json` | `TypeError: cannot pickle 'mappingproxy' object` |
| `pickle.dumps(PortSimulation)` | same error |
| `copy.deepcopy(sim.env)`, of one `Process`, of its `_generator` | `TypeError: cannot pickle 'generator' object` (all three) |
| `copy.deepcopy(Terminal)` | `TypeError: cannot pickle 'mappingproxy' object` (frozen event payloads) |
| `Terminal.from_dict(Terminal.to_dict())` | Works: 5.6 ms at 42 events, 17.8 ms at 180 events (grows with log length; every `Terminal` command performs this round-trip inside `_atomic`) |

## 8. Known compatibility risks

| ID | Risk | Mitigation |
| --- | --- | --- |
| R1 | Nominal service (120 moves/h) far exceeds Project 02-like crane physics | Treated as an S1 mechanism, not hidden. The degenerate profile reproduces nominal exactly. Coefficients frozen before validation |
| R2 | PPO `end − now` field exact in training, forecast in integrated physics | PASS-FORECAST mode labelled as distribution shift; PASS-EXACT verified in degenerate profile |
| R3 | Observation encoder reads private `DynamicBAPEnv` attributes | Adapter pinned to `dynamic_obs_v1` and `berth-allocation-lab==0.1.0`; bit-equality test against a real `DynamicBAPEnv` on projections |
| R4 | CPU/CUDA action parity unknown (Project 03 report) | CPU-only inference, identical to Project 03 evaluation loader; repeated-inference determinism test |
| R5 | Project 03 training seeds span the whole train-split range | Project I uses namespaced generation (no Project 03 generator call with a raw Project I seed) plus fingerprint audit (protocol §6) |
| R6 | Max vessels per episode bounded by `M` (24 / 8) | Scenario families sized ≤ 24 vessels; gate BLOCKs otherwise |
| R7 | Rollout continuation cost multiplies with integrated physics | Report computation separately; batch size and cohort-limited forward models |
| R8 | Project 01 `TerminalState` validation semantics differ (TEU progress, per-task crane assignment) | Projection is audit-only; mapping rules in data contract §12 |

## 9. Regressions that must be protected

- Project 01, 02 and 03 test suites must stay green with unchanged counts
  (426 / 55 / 463 fast) at every Project I step. Project I tests run in their
  own directory.
- No file under `01-…`, `02-…`, `03-…` may change. Step gates check
  `git diff --stat -- 01-terminal-operations-core 02-mini-port-simulation 03-berth-allocation-lab`
  is empty.
- Frozen checkpoint and decision hashes in §5.2 must re-verify before any
  Project I run that loads a checkpoint.
- `python scripts/verify_project03_release.py` (Project 03) remains the
  release integrity check. Project I does not rebuild the release.
