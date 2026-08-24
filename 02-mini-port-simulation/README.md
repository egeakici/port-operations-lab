# Mini Port Simulation

MiniPortSim is the time-progressing simulation layer that runs on top of
Terminal Operations Core.

Project boundary:

- Core owns the domain entities and validation rules.
- MiniPortSim owns simulation time, scenarios, processes, policies, metrics,
  and replay artifacts.
- MiniPortSim must not copy Core classes.

Implemented modules:

- Module 01: Architecture + Core Integration
- Module 02: Simulation Engine
- Module 03: Scenario + RNG
- Module 04: Vessel Arrival Generator
- Module 05: FCFS Berth Allocation
- Module 06: Vessel Service Lifecycle
- Module 07: Quay Crane Resource System
- Module 08: ContainerGroup + OperationTask + YardBlock Flow
- Module 09: Stochasticity + Disruptions
- Module 10: Metrics + Event Logging
- Module 11: Visualization + Scenario Replay
- Module 12: Experiments + Final Tests

Current engine contract:

- `PortSimulation` owns a SimPy environment.
- `env.now` is the authoritative simulation clock in minutes.
- `Terminal.current_time` is synchronized from `env.now`.
- Simulation processes are registered through `add_process(...)`.
- `run(until_minutes=...)` uses inclusive horizon semantics, so events
  scheduled exactly at the horizon are processed.

Current scenario contract:

- Scenario inputs are represented by `ScenarioConfig`.
- Terminal and traffic assumptions live in nested config objects.
- Scenario JSON files can be loaded from `scenarios/`.
- `RandomStreams` derives independent RNG streams from one master seed.
- `PortSimulation` owns one `RandomStreams` manager for each seeded run.
- Consuming one stream, such as `arrival`, does not advance another stream,
  such as `failure`.
- Arrival timing, vessel attributes, workload, failures, and productivity use
  separate RNG streams.

Current operations contract:

- `VesselArrivalGenerator` creates deterministic vessel arrival plans from a
  scenario and the simulation-owned RNG manager.
- `vessel_arrival_process(...)` registers vessels in Core and moves them to
  waiting at their scheduled simulation time.
- `FCFSLeftmostPolicy` chooses the first waiting feasible vessel and the
  leftmost safe continuous-berth position.
- `berth_dispatcher_process(...)` commits berth placement to Core before
  starting vessel service processes, so same-tick dispatch decisions see
  current berth occupancy.
- `vessel_service_process(...)` models berthing preparation, simplified
  service time, operation completion, departure preparation, and Core
  departure.
- When quay cranes and yard blocks exist, vessel service uses Core
  `ContainerGroup`, `OperationTask`, `YardBlock`, and `QuayCrane` objects
  instead of the simplified service duration.
- `GreedyCranePolicy` assigns available cranes to ready vessel tasks up to the
  vessel's `max_cranes` limit.
- `FirstFitYardPolicy` creates reservation-based yard bottlenecks before
  discharge tasks can become ready.
- Productivity variation, ETA variation, and crane failure/repair processes
  are driven from independent scenario RNG streams.
- `PortSimulation.start_basic_operations()` wires the arrival and berth
  dispatcher processes for the baseline flow, plus crane failures when enabled
  by the scenario.

Current measurement and experiment contract:

- `collect_metrics(simulation)` turns Core events and simulation lifecycle
  records into vessel KPIs, queue metrics, throughput, utilization, and
  downtime.
- `build_event_replay(simulation)` produces JSON-safe replay frames from the
  domain event log.
- `build_berth_timeline(...)` and `build_crane_timeline(...)` produce
  timeline segments for visualization.
- `run_scenario_experiment(...)` builds a terminal from a scenario, runs it,
  and returns metrics plus replay/timeline artifacts.
- `run_multi_seed_experiment(...)` supports reproducible stochastic
  experiment batches.

## Development Setup

Install Terminal Operations Core first, then install MiniPortSim:

```bash
python -m pip install -e ../01-terminal-operations-core
python -m pip install -e .
```

Then verify the package boundary:

```bash
python -c "from terminal_core import Terminal, Vessel, Berth; from mini_port_sim import PortSimulation"
python -m pytest
```
