# Repository evidence, reuse and integration architecture

Audit date: 2026-11-09 (Europe/Istanbul). Start HEAD:
`7124fa94019fc7772b5ef0e6e6bd1487b485efd3`.
Local source takes precedence over stale root/Project I README progress text.
The machine manifest records exact reviewed paths, symbols and raw-byte SHA256s.
This is a read-only capability audit, not a fresh execution/reproduction audit.

Evidence labels: `EXISTING` means found in source, not proved anew by running it;
`ADAPTER_NEEDED` means an existing concept needs a new mapping;
`NEW_PROJECT04_REQUIRED` identifies absent QCSP capability;
`PROPOSED` is a design recommendation; `UNKNOWN` means no evidence established.

## Source-grounded inventory

Paths below are repository-relative. E IDs resolve to full paths/symbols/hashes
in `source_inventory` in the [manifest](../configs/research/step1_problem_contract_v1.json).

| Evidence | Source symbol and verified behavior | Label / Project 04 consequence |
| --- | --- | --- |
| E01 | `01-terminal-operations-core/src/terminal_core/quay_crane.py`, `QuayCrane`: `position_m`, `moves_per_hour`, status, assigned vessel; `move_to` updates position and returns distance, disallows operating/failed/maintenance motion | EXISTING; timed rail trajectory, shared-rail order and clearance validator NEW_PROJECT04_REQUIRED; do not call `move_to` as a physical travel engine |
| E02 | `.../operation_task.py`, `OperationTask`, `TaskLocation`, enums: task/group IDs, `planned_teu`, source/target entity locations, datetime release/due, predecessors, completed TEU, resource/status | ADAPTER_NEEDED: no bay-meter/job-move field; map operation type, identity and release explicitly, never TEU directly to moves |
| E03 | `.../terminal.py`, `Terminal._atomic`, `_validate_task_can_be_ready`, `assign_task_resource`, `start_task`, `complete_task`: coordinated commands/readiness/resource/TEU inventory | EXISTING: preserve ID and validation discipline; no live-state mutation by Project 04 policy |
| E04–E07 | `.../vessel.py` `Vessel` has length/workload/max cranes; `.../berth.py` `BerthOccupancy` has start/end positions; `.../terminal_event.py` `TerminalEvent` has datetime; `.../terminal_state.py` `TerminalState` snapshots/checks consistency | ADAPTER_NEEDED: global origin/units and ownership; ship bay offsets/orientation DATA_GAP |
| E08 | `02-mini-port-simulation/src/mini_port_sim/simulation.py`, `PortSimulation`: owns SimPy environment, `elapsed_minutes`, `now_datetime`; synchronized Core clock | EXISTING event/time pattern, not a second clock to embed in Project I |
| E09–E11 | `processes/crane_dispatcher.py` `crane_dispatcher_process` chooses vessel/task assignments; `policies/crane_policy.py` `GreedyCranePolicy.choose` selects READY tasks/free cranes, capped by vessel max; `processes/task_process.py` `crane_task_process`, `_remaining_duration_minutes` use SimPy timeouts and TEU ratio to moves; interruption records progress/failure | ADAPTER_NEEDED: future QCSP non-preemption differs from failure interruption; no shared-rail trajectories in these dispatch paths |
| E12–E13 | `processes/vessel_process.py` `vessel_service_process` includes berthing/operations/departure; `visualization/replay.py` `build_event_replay`, `build_state_replay` consume stored events | EXISTING separation/replay pattern; REQUIRES_ADAPTER for rail segments and job traces |
| E14 | `03-berth-allocation-lab/src/berth_allocation_lab/envs/dynamic_bap_env.py`, `DynamicBAPEnv`: minute clock/events, bounded visibility, masked vessel/position assignment plus WAIT; reward is waiting-cost increment | EXISTING pattern only; QCSP needs own state/actions/makespan reward |
| E15–E17 | `envs/dynamic_visible_state.py` `DynamicVisibleState`; `policies/dynamic_fcfs.py` `online_fcfs_action` reads public legal choices; `policies/dynamic_online_rollout.py` `_VisibleContinuation`, `online_rollout_choice` operate on visible cohort | ADAPTER_NEEDED conceptually for causal QCSP heuristic; these are berth algorithms, not crane baselines |
| E18–E21 | `rl/dynamic_checkpoint.py` `save_dynamic_checkpoint`, `load_dynamic_checkpoint` check environment, observation, action capacities, scales and architecture; `rl/dynamic_training.py` `_ValidationMonitor`; `rl/dynamic_decision.py` `dynamic_rule`; `benchmark/stats.py` `scenario_seed_means`, `paired_bootstrap` | EXISTING reproducibility/selection/nesting conventions; new Project 04 PPO implementation/checkpoints required, no checkpoint loading here |
| E22 | `integrated-terminal-pilot/src/integrated_terminal_pilot/policies/crane.py`, `GreedyBerthOrderCranePolicy.decide`, ID `primitive_crane_greedy_v1`: vessels ordered by berth start/ID; compatible available cranes by ID up to max; no releases by primitive | EXISTING QCAP-like vessel allocation primitive, not bay QCSP |
| E23–E24 | `policies/observations.py` `CraneVesselView` has berth/remaining moves/max cranes; `CraneView` has status/rate/compatibility/activity, **no live rail position**; `policies/actions.py` `CraneAssignment`, `CraneAction` have vessel/crane IDs, optional releases, decision/time/schema IDs | CONTRACT_CONFLICT with detailed bay/task/movement plans; primitive action schema cannot express them |
| E25 | `scenarios/models.py` `CRANE_KEYS` includes `rail_id`, `home_position_m`; `CONTAINER_KEYS` identities/flows; `LOCATION_KEYS` bay/row/tier fields | EXISTING reserved rail metadata and individual containers; not evidence of motion or vessel stowage |
| E26 | `scenarios/validation.py` initial-location checks: non-yard locations must have null bay/row/tier; G0 yard is block-only | EXISTING; genuine vessel bay plan DATA_GAP. Yard bay geometry is not ship bay geometry |
| E27–E28 | `simulator/state.py` `CraneState`, `WorkOrderState`: crane work/activity and batches with container indices/moves/TEU; `simulator/physics.py` `crane_rate_moves_per_hour`, `quay_transfer_x_m`: nominal × assigned-crane efficiency × productivity; transport point is mid-hull | EXISTING rate/cargo model; no live position trajectory in CraneState; detailed QCSP duration equivalence UNKNOWN |
| E29 | `simulator/kernel.py` `TerminalKernel._commit_crane_action`: assigns vessel/status immediately; `_recompute_rates` uses assigned count unless diagnostic override; `observable_clone` delegates sanitization | EXISTING immediate allocation; timed rail movement NEW_PROJECT04_REQUIRED in a separately versioned integration world |
| E30–E32 | `simulator/events.py` event queue ordered by time/priority/key/sequence, tolerance; `simulator/validator.py` `validate_crane_action` checks phase, availability, compatibility, max cranes, no release during batch; `simulator/invariants.py` `check` | EXISTING validation/event discipline; current crane validation does not enforce QCSP rail path safety |
| E33–E34 | `simulator/ledger.py` `replay_audit`; `simulator/observable.py` `build_observable_clone` removes hidden vessels/landside events, seed/fingerprints and logs | EXISTING cargo authority and causal boundary; no raw clone/event queue to future online policy |
| E35–E37 | `configs/protocol/itp_protocol_control_register_v1.yaml`, AM-02 and efficiency records; `configs/generator/itp_generator_v1_decisions.yaml`, S2-020/021 and two-crane efficiency; `benchmark/step7_inputs.py` historical source/checkpoint hashes | INHERITED_FROZEN **for Project I only**: eight-crane primary fleet, max two per vessel, assigned basis; four-crane original remains; no new Project 04 rate approval |
| E38–E42 | `docs/PROJECT_I_RESEARCH_HANDOFF.md`, `docs/PROJECT_04_TRANSITION_NOTE.md`, `docs/step8/CURRENT_FINAL_CLOSURE.json`, `PROJECT_I_SCIENTIFIC_CLOSURE.md`, current derived closure report | EXISTING authoritative handoff; historical science unchanged; exact current qualifications below |
| E43 | `docs/step8/final_closure/4b959879b7ed0606/OWNER_APPROVAL_RECORDED.md` | EXISTING explicit FC01–FC04 packet acceptance; not evidence diagnostics ran |
| E44–E47 | Project 03 final report and README, root README and PROJECT_CONTEXT | EXISTING architecture/history; root progress summaries stale; actual Project 04 directory empty at start |
| E48–E50 | Project 03 `dynamic_observation.py`, `core/numerics.py`, `tracking/records.py` | EXISTING padded tensor/normalization, `1e-9` BAP numerical convention and run-record patterns; semantics require adaptation |
| E51–E56 | Owner specification, Projects 01/02 READMEs, Project I AGENTS.md, simulator catalog and root `.gitignore` | EXISTING scope/manual-execution constraints and catalog fields; `.gitignore:27` excludes Project 04, so new documents remain local/ignored without changing root rules |

No external scholarly sources or APIs were consulted; this contract is an explicit
design synthesis of the owner's specification and local source. Empirical AIS,
TOS records, real QC logs, bay/stowage plan and calibration remain UNKNOWN/DATA_GAP.
No issues service was accessed; local tracked/untracked files were inspected.

## Current scientific closure, not the older README

Project 03 final report distinguishes static waiting-time research from online
BAP and scoped candidate-space exactness; PPO does not dominate rollout. These
findings and weights are untouched and do not predict QCSP rankings.

Project I current pointer names release `e54e000a11c7097e` under plan
`4b959879b7ed0606`, manifest SHA256
`2b08d56ea825d513ca73cdd255ea4beb644141aae14023fea87ac1a1656afe7f`.
It records Step 7 `COMPLETED_1960_OF_1960`, return `VERIFIED_FULL_CANONICAL`,
primary inference `COMPLETE_WITH_POST_HOC_QUALIFICATION`, and
`PROJECT_I_FINAL_CLOSED=NO`. New diagnostics: 4,320 runnable cells pending,
0 verified, 40 aliases and 120 unsupported requirements; unsupported is never
success. FC acceptance is recorded, with diagnostics still outstanding.
These are inspected receipt claims, not independently rerun verification here.

The handoff's synthetic B2-versus-A2 evidence concerns terminal-aware model-based
berth coordination, not a trained crane policy or three-branch joint RL.
Real-terminal savings/calibration are unestablished. Final closure of Project I
is not required to draft independent P04 contracts; it remains a separate owner
workflow and does not authorize any rerun from this task.

## Adapter readiness matrix

Readiness labels describe exactness of a **specific mapping**, not general code
reuse. An absent datum must fail closed or remain explicitly unsupported.

| Source → target / required data | Status | Transformation, safety/provenance and limit |
| --- | --- | --- |
| Existing string crane/vessel/task IDs → provenance references | EXACTLY_REUSABLE | Preserve byte-identical source IDs with source-project/schema/fingerprint namespace; validate uniqueness; no new entity identity inferred |
| Minutes and meter unit meanings → P04 unit labels | EXACTLY_REUSABLE | Units only; no copied clock owner, tolerance or coefficient approval |
| Core OperationTask → QCSP atomic bay job | REQUIRES_ADAPTER | Explicit operation/group link, moves/TEU conversion record, release epoch, original identities; require bay and workload source; check no splitting/phantom completion |
| BerthOccupancy.start_position_m / I CraneVesselView.berth_position_m → global hull origin | REQUIRES_ADAPTER | Validate frame origin, hull length, orientation and timestamp; apply ship-local bay transform from problem spec; preserve source snapshot |
| Vessel bay offsets/orientation/stowage → bay meter positions | DATA_GAP | No ship bay plan supplied; separate labelled synthetic P04 layout only, not inferred real source data |
| Core QuayCrane.position_m → timed current trajectory | REQUIRES_ADAPTER | Snapshot position can seed a new model only with known epoch/frame/availability; instantaneous move_to supplies no speed/path history |
| I rail_id/home_position_m → current rail position/order | DATA_GAP | Reserved home metadata is not live position; no silent home=current fallback |
| I CraneAction → bay job/reposition/wait plan | CONTRACT_CONFLICT | Vessel assignment lacks task/bay/time/path reservation; current schema cannot execute QCSP plans; new versioned physical/action support required |
| I nominal rate / efficiency → P04 effective rho | REQUIRES_ADAPTER | Carry nominal, assigned count, efficiency/productivity and transport/yard limits as provenance; prove equivalence only for bounded diagnostic cases; never declare equal throughput generally |
| I WorkOrderState.container_indices / ledger → original cargo mapping | REQUIRES_ADAPTER | Resolve indices using immutable catalog identities; reconcile type/moves/TEU and exactly-once original obligations; aggregate completion cannot author LOAD_COMPLETED |
| I validator/observable_clone → online P04 proposal boundary | REQUIRES_ADAPTER | Public immutable snapshot, visibility filter and new proposal validator; no raw internal queue/private-state mutation; no rail validator currently reusable |
| Project 03 PPO weights → P04 policy | CONTRACT_CONFLICT | Different spaces/objective/architecture semantics; new separately trained agent required |
| Real calibration / AIS / TOS → operational parameters | DATA_GAP | Need approved independent data and quality/rights/provenance process in future; AIS alone cannot supply move/bay facts |

## Three integration phases and state ownership

**Phase 1: stand-alone research.** Project 04 owns its own QCSP input, one
physical clock, independent validator and immutable traces. Domain IDs/enums and
unit conventions may be referenced rather than copied into competing terminal
registries. Specialized job/path models add absent semantics. No coupling to live
Project I runtime or modified historical source is needed.

**Phase 2: read-only/versioned adapter and smoke.** A future immutable snapshot
contains source schema/fingerprint/decision/time, vessel berth frame, original
operations/cargo mapping, crane availability/positions and explicit gaps. An
adapter produces a separate QCSP request and declarative plan proposal with
target schema, original IDs, path reservations, validity window and assumptions.
The authoritative versioned integration kernel validates freshness, identities,
capacity, cargo readiness and rail physics atomically, then executes it using its
single clock and ledger. Reject stale/rejected/unsupported proposals without
mutation. Project 04 never emits authoritative cargo completion events.

Frozen Project I cannot currently execute that detailed proposal. If versioned
rail support is unavailable, a read-only translation/rejection smoke is possible;
do not call it successful physical execution. A future isolated successor world,
under new protocol approval, must provide rail state/events, motion reservations,
batch granularity alignment and policy interface versions. Never patch the frozen
kernel or translate detailed plans silently into instantaneous assignments.

**Phase 3: separate integration research.** A coordinator may combine berth,
crane and yard specialists under new fingerprints, baselines, held-out protocols
and compute/visibility rules. Reuse Project I's immutable master as historical
evidence only. Old arm identities/results remain unchanged. A passing adapter
smoke establishes interface correctness, not a performance advantage, commercial
benefit or jointly trained terminal optimizer.

Before Step 13: close DATA_GAP/CONTRACT_CONFLICT rows or explicitly restrict smoke;
approve successor execution physics and action schemas; map original cargo/batch
identity and rate basis; reconcile one clock and coordinate frame; supply observed
current positions/rail order; freeze policy/checkpoint provenance and held-out
smoke fixtures; test stale, impossible, hidden and rejected proposals plus no
mutation and cargo conservation. No integration superiority claim follows.
