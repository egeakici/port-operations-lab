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

Current engine contract:

- `PortSimulation` owns a SimPy environment.
- `env.now` is the authoritative simulation clock in minutes.
- `Terminal.current_time` is synchronized from `env.now`.
- Simulation processes are registered through `add_process(...)`.

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
