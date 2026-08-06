# Port Operations Lab

Port Operations Lab is a staged preparation workspace for building a reliable
container-terminal digital-twin and optimization stack.

## Eight-Project Roadmap

1. `01-terminal-operations-core`: shared terminal domain model, events, state,
   aggregate commands, integration scenario, and interactive demo.
2. `mini-port-sim`: future discrete-event terminal simulator.
3. `berth-allocation-lab`: future berth allocation baselines.
4. `rail-crane-scheduler`: future quay-crane assignment and scheduling logic.
5. `container-yard-puzzle`: future yard relocation/search core.
6. `terminal-rl-sandbox`: future Gymnasium/action-masking RL environment.
7. `ais-port-call-calibrator`: future AIS-based port-call calibration.
8. `terminal-optimization-benchmark`: future experiment and comparison engine.

Only Project 1 is implemented in this repository right now.

## Project 1 Status

`01-terminal-operations-core` is complete and includes:

- Vessel, berth, quay crane, yard block, container group, and operation task
  domain entities.
- Immutable TerminalEvent records and immutable TerminalState snapshots.
- Mutable Terminal aggregate commands with atomic rollback and inventory checks.
- Deterministic reference integration scenario.
- Interactive Streamlit Terminal Operations Control Center.

## Interactive Frontend

Run from `01-terminal-operations-core`:

```bash
python -m pip install -r requirements-demo.txt
python -m streamlit run app/streamlit_app.py
```

The frontend has an `Interactive Sandbox` for manual terminal setup and
operations, plus a read-only `Reference Scenario` checkpoint viewer.

## Tests

Run from `01-terminal-operations-core`:

```bash
python -m pytest -v
```

## Next Project

The next preparation project is MiniPortSim, which will add a time-progressing
discrete-event simulation layer on top of the Terminal Operations Core.
