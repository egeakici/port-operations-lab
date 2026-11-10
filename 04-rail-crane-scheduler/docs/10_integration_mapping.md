# Source-to-contract mapping (Step 02)

The Step 01 evidence inventory and `development_run/PREFLIGHT.json` source hashes
remain authoritative. All source paths below are repository-relative.

| Source :: symbol | Meaning/unit -> P04 field | Status / gap |
| --- | --- | --- |
| 01-terminal-operations-core/src/terminal_core/quay_crane.py :: QuayCrane.position_m, moves_per_hour | m, nominal moves/h -> initial_position_m and rate provenance | ADAPTER_REQUIRED; move_to is instantaneous, not a timed path |
| 01-terminal-operations-core/src/terminal_core/operation_task.py :: OperationTask | group TEU and entity source/target -> source_task_ids, operation_kind | ADAPTER_REQUIRED; DATA_GAP for job bay and moves; TEU cannot be converted without source facts |
| 01-terminal-operations-core/src/terminal_core/berth.py :: BerthOccupancy | hull start/length m -> VesselContext | LOSSLESS_CONVERSION only with explicit origin/orientation |
| 02-mini-port-simulation/src/mini_port_sim/simulation.py :: PortSimulation.elapsed_minutes, now_datetime | SimPy clock -> elapsed planning_start_min and epoch | DIRECTLY_COMPATIBLE units; ADAPTER_REQUIRED for clock ownership |
| 02-mini-port-simulation/src/mini_port_sim/processes/task_process.py :: TaskWorkPlan, crane_task_process | moves/TEU and timed task work -> workload/source references | ADAPTER_REQUIRED; PHYSICS_CONFLICT for omitted rail travel/failure preemption |
| 03-berth-allocation-lab/src/berth_allocation_lab/rl/dynamic_checkpoint.py :: load_dynamic_checkpoint | BAP spaces/checkpoint -> provenance practice only | PHYSICS_CONFLICT for weight/action reuse; no checkpoint loaded |
| integrated-terminal-pilot/src/integrated_terminal_pilot/policies/crane.py :: GreedyBerthOrderCranePolicy | vessel-level allocation -> future specialist request | ADAPTER_REQUIRED; max two is not shared-rail legality |
| integrated-terminal-pilot/src/integrated_terminal_pilot/policies/observations.py :: CraneView | availability/rate/compatibility -> CraneDefinition subset | DATA_GAP: no current rail coordinate, ship bay or speed |
| integrated-terminal-pilot/src/integrated_terminal_pilot/policies/actions.py :: CraneAction | ASSIGN_CRANES vessel/crane IDs -> future proposal envelope | PHYSICS_CONFLICT: no timed bay task/path action |
| integrated-terminal-pilot/src/integrated_terminal_pilot/simulator/state.py :: WorkOrderState | original indices/moves/TEU -> explicit source identity mapping | ADAPTER_REQUIRED; requires immutable catalog, no fabricated container IDs |
| integrated-terminal-pilot/src/integrated_terminal_pilot/simulator/observable.py :: build_observable_clone | visible state only -> CraneObservation principle | ADAPTER_REQUIRED; never expose hidden queue/seed |

Future flow: immutable source snapshot -> explicit mapping -> QCSPProblem ->
scheduler -> candidate CraneSchedule -> independent validator -> versioned
proposal -> future successor kernel. Native legacy execution cannot consume
continuous rail plans; Step 13 must refuse missing data or use an isolated labelled
synthetic harness. The authoritative terminal kernel owns resource locks, actual
clock and cargo ledger. Plan validity expires on state/decision/hash change;
replan requests are new proposals, not v1 task preemption. No live adapter exists
in Step 02 and no legacy physics or historical results are changed.
