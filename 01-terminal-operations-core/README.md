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

## Interactive Frontend

The Streamlit control center is the manual operations UI for this domain core.
It is not a scheduler, simulator, or optimizer. It lets you build a terminal,
issue public `Terminal` commands from forms, inspect `TerminalState`, and export
the scenario you created.

Run it from this project directory:

```bash
python -m pip install -r requirements-demo.txt
python -m streamlit run app/streamlit_app.py
```

The app opens with two top-level tabs:

- `Interactive Sandbox`: the main workspace for manually creating and operating
  a terminal.
- `Reference Scenario`: a read-only checkpoint viewer for the deterministic
  integration scenario.

Inside `Interactive Sandbox`, use:

- `Control Center` to advance terminal time, see overview metrics, and run
  vessel arrive/berth/depart commands.
- `Terminal Setup` to register berths, vessels, quay cranes, and yard blocks.
- `Cargo & Tasks` to register container groups, initialize physical cargo
  locations such as export gate inventory, create operation tasks, reserve yard
  capacity, manage yard status, manage task lifecycle, and operate cranes.
- `Terminal Map` to inspect a read-only bird's-eye schematic of the current
  terminal.
- `Live State` to inspect current berth layout, vessels, cranes, yards, cargo
  locations, tasks, and raw `TerminalState` JSON.
- `Events & History` to inspect the domain event timeline separately from
  app-level command history and saved checkpoints.
- `Import / Export` to download/upload the current Terminal JSON or a full
  sandbox scenario package.

Every form command is routed through `app.command_service.execute_terminal_command`.
That service captures a before snapshot, calls only public `Terminal` APIs,
records new domain events, stores success/failure command history, and verifies
rollback safety on domain errors. The app does not mutate private Terminal
registries or create domain events manually.

Named checkpoints store restoreable Terminal JSON plus an immutable
`TerminalState` snapshot. Restoring a checkpoint validates the JSON with
`Terminal.from_dict()` before replacing the session terminal.

## Bird's-Eye Terminal View

The Streamlit app includes a read-only SVG terminal map generated from the
current `TerminalState`. The same renderer is used by the Interactive Sandbox
and the Reference Scenario checkpoint viewer.

The view is schematic, not GIS or geospatial. Berth, berthed vessel, and quay
crane placement uses the Core's real meter data where available:
`Berth.length_m`, vessel berth `start_position_m`, `Vessel.length_m`, and
`QuayCrane.position_m`. Yard blocks and gate areas have no physical x/y fields
in the Core, so the app lays them out deterministically as presentation-only UI
positions.

Cargo badges reflect actual Core inventory from `TerminalState.group_locations`.
Task progress is shown separately as logical operation arrows. The map never
partially moves cargo just because a task has progress; physical cargo locations
change only after Terminal commands update inventory. Operation arrows represent
logical cargo flow, not vehicle paths or simulated transport routes.

The visualization does not mutate `Terminal`, does not add visual coordinates to
domain entities, and does not run an animation loop. It redraws on normal
Streamlit reruns after commands update the sandbox state.

## Frontend Tests

```bash
python -m pytest tests/test_app_command_service.py -v
python -m pytest tests/test_app_presenters.py -v
python -m pytest tests/test_app_session_store.py -v
python -m pytest tests/test_streamlit_app.py -v
python -m pytest tests/test_visual_layout.py -v
python -m pytest tests/test_visual_presenter.py -v
python -m pytest tests/test_terminal_map.py -v
```

## Architecture Boundaries

- Integration uses only public `Terminal` commands and queries.
- Integration does not mutate private Terminal registries.
- Integration does not create events manually.
- Integration does not duplicate `TerminalState` validation rules.
- Checkpoints are immutable `TerminalState` snapshots.
- Physical inventory is moved only by Terminal commands.
- The Streamlit app depends on `terminal_core`; `terminal_core` does not depend
  on Streamlit.
- The app uses only public Terminal commands and queries for mutation and
  inspection.

## Intentionally Out Of Scope

- React, FastAPI, Flask, REST API, database, or authentication.
- Event queue, async execution, automatic clock, or arrival generator.
- Randomness, FCFS, scheduler, dispatcher, optimizer, OR-Tools, or RL.
- SimPy, AIS, animation, or charting.

## Next Project: MiniPortSim

With Terminal Operations Core complete, MiniPortSim can build a time-progressing
simulation layer on top of these domain entities, events, snapshots, and the
deterministic integration scenario.
