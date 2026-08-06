# Terminal Operations Core

Terminal Operations Core is a small Python domain core for modeling the static
rules and coordinated state changes of a container terminal. It provides domain
entities, immutable events, immutable state snapshots, a mutable Terminal
aggregate, and a deterministic integration scenario.

## Project Purpose

The project defines the shared language for later terminal simulation and
optimization work. It does not optimize the terminal, choose schedules, run a
clock, or simulate random arrivals.

## Architecture Overview

The dependency direction is intentionally simple:

```text
integration.py
    -> Terminal public API
        -> domain entities
        -> TerminalEvent
        -> TerminalState
```

`Terminal` is the aggregate root. It owns live registries, executes atomic
commands, emits events, and validates each completed command through
`TerminalState.capture()`.

`TerminalState` is an immutable snapshot. It is used for queries, JSON
round-trips, and cross-entity consistency validation.

## Modules

- `Vessel`: vessel lifecycle from approaching to departed.
- `Berth`: berth length, safe clearance, and vessel occupancies.
- `QuayCrane`: crane assignment, operation, failure, repair, maintenance, and movement.
- `YardBlock`: capacity, reservations, stored groups, and block status.
- `ContainerGroup`: immutable cargo group master data.
- `OperationTask`: task route, progress, resource assignment, blocking, completion, cancellation, and failure.
- `TerminalEvent`: immutable event records with JSON-safe payloads.
- `TerminalState`: immutable terminal snapshot and consistency validator.
- `Terminal`: mutable aggregate root for coordinated commands.
- `Integration`: deterministic reference orchestration across the public Terminal API.

## Reference Scenario

The reference scenario is `two-vessel-transshipment-v1`.

It moves one 100 TEU transshipment group from inbound vessel `V-IN` to yard
block `Y01`, then from `Y01` to outbound vessel `V-OUT`. During discharge,
primary crane `QC01` fails after 40 TEU of recorded progress. The task is
unassigned, reassigned to backup crane `QC02`, restarted, completed, and then
the cargo is loaded onto `V-OUT`.

The integration scenario is deterministic orchestration. It is not a
discrete-event simulation.

## Scenario Timeline

- `08:00`: initial terminal infrastructure and two vessels are registered.
- `08:10`: `V-IN` arrives and waits.
- `08:20-08:35`: `V-IN` berths, cargo/tasks are registered, and `Y01` is reserved.
- `08:40-09:20`: discharge task starts and records 40 TEU progress.
- `09:30`: `QC01` fails and blocks the discharge task.
- `09:35-10:20`: task is moved to `QC02`, restarted, and discharge completes.
- `10:25-10:30`: `QC01` is repaired and `V-IN` departs.
- `10:40-10:50`: `V-OUT` arrives and berths.
- `10:55-11:50`: load task runs and completes.
- `12:00`: `V-OUT` departs and the scenario reaches final state.

## Checkpoints

- `initial`
- `inbound_waiting`
- `inbound_berthed`
- `discharge_in_progress`
- `crane_failed`
- `discharge_completed`
- `inbound_departed`
- `outbound_berthed`
- `load_completed`
- `final`

## How To Run Tests

```bash
python -m pytest tests/test_terminal_integration.py -v
python -m pytest tests/test_terminal.py -v
python -m pytest tests/test_terminal_state.py -v
python -m pytest -v
```

## How To Run The Example

```bash
python examples/run_reference_scenario.py
```

The script prints the scenario ID, start/completion time, event count,
checkpoint names, final vessel/crane/task statuses, and final cargo location.

## Expected Final State

- `V-IN`: departed.
- `V-OUT`: departed.
- `B01`: empty.
- `QC01`: available.
- `QC02`: available.
- `T-DISCHARGE`: completed.
- `T-LOAD`: completed.
- `G-TRANS`: 100 TEU on `V-OUT`.
- `Y01`: no stored `G-TRANS` cargo remains.

## Architecture Boundaries

- Integration uses only public `Terminal` commands and queries.
- Integration does not mutate private Terminal registries.
- Integration does not create events manually.
- Integration does not duplicate `TerminalState` validation rules.
- Checkpoints are immutable `TerminalState` snapshots.
- Physical inventory is moved only by Terminal commands.

## Intentionally Out Of Scope

- Frontend, dashboard, Streamlit, React.
- REST API or database.
- Event queue, async execution, automatic clock, or arrival generator.
- Randomness, FCFS, scheduler, dispatcher, optimizer, OR-Tools, or RL.
- SimPy, AIS, animation, or charting.

## Next Project: MiniPortSim

With Terminal Operations Core complete, MiniPortSim can build a time-progressing
simulation layer on top of these domain entities, events, snapshots, and the
deterministic integration scenario.
