# Mini Port Simulation

MiniPortSim is the time-progressing simulation layer that runs on top of
Terminal Operations Core.

Project boundary:

- Core owns the domain entities and validation rules.
- MiniPortSim owns simulation time, scenarios, processes, policies, metrics,
  and replay artifacts.
- MiniPortSim must not copy Core classes.

Step 1 status:

- The package skeleton exists.
- `terminal_core` is consumed as a dependency.
- A small `PortSimulation` shell anchors the authoritative simulation clock
  contract.

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
