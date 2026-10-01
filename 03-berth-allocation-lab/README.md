# Berth Allocation Lab

Project 03 is the berth-allocation optimization laboratory for the Port
Operations Lab roadmap.

Current status: Step 7 / tiny candidate-space enumeration and exact reference.

Completed:

- Step 1: problem specification
- Step 2: experiment and data contract
- Step 3: package/configuration scaffold
- Step 4: synthetic scenario schema and generator
- Step 5: continuous BAP geometry, feasibility, scheduling, candidates, and
  objectives
- Step 6: static FCFS and Greedy Rollout policies, common KPIs, and run records
- Step 7: tiny fixed-order candidate-space exact reference and certified gaps

Completed: Steps 1-7. Next: Step 8 - StaticBAP Environment.

The project scope is continuous berth allocation with two branches:

- Static Continuous BAP, where all vessel information is known before schedule
  construction.
- Dynamic Continuous BAP, where vessels appear over event-driven simulation time
  and future information is limited by a configurable visibility horizon.

The v1 primary objective is to minimize total vessel waiting time. Quay-crane,
yard, truck, and equipment scheduling policies are treated as fixed or
exogenous behavior in Project 03 v1.

Current methods are static FCFS, static Greedy Rollout, and tiny candidate-space
enumeration. The reference is exact only within fixed-order, finite candidate
decisions with earliest service starts, not unrestricted continuous BAP.
Planned methods include continuous optimization, rolling-horizon references,
Maskable PPO, and later DQN-family experiments.

Read the frozen Step 1 specification:

- [docs/problem_specification.md](docs/problem_specification.md)

Read the frozen Step 2 experiment/data contract:

- [docs/experiment_data_contract.md](docs/experiment_data_contract.md)

Read the Step 4 synthetic scenario note:

- [docs/synthetic_scenarios.md](docs/synthetic_scenarios.md)

Read the Step 5 continuous core note:

- [docs/continuous_bap_core.md](docs/continuous_bap_core.md)

Read the Step 6 baseline and recording note:

- [docs/static_baselines.md](docs/static_baselines.md)

Read the Step 7 reference definition and measured audit:

- [docs/candidate_space_reference.md](docs/candidate_space_reference.md)
- [docs/step7_validation.md](docs/step7_validation.md)

## Package Structure

- `src/berth_allocation_lab/core`: shared continuous BAP placement, geometry,
  feasibility, scheduling, candidate, and objective functions.
- `src/berth_allocation_lab/policies`: static FCFS and Greedy Rollout.
- `src/berth_allocation_lab/solvers`: tiny candidate-space enumeration.
- `src/berth_allocation_lab/evaluation`: shared KPIs and static runner.
- `src/berth_allocation_lab/tracking`: scientific records and local artifacts.
- `src/berth_allocation_lab/config`: scaffold-level YAML config loading.
- `src/berth_allocation_lab/integration`: future adapters to Project 01 and
  Project 02.
- `configs/`: scaffold example configs for scenarios, experiments, training,
  and benchmarks.
- `tests/unit` and `tests/integration`: scaffold tests.

## Development

Install upstream projects first, then Project 03:

```bash
python -m pip install -e ../01-terminal-operations-core
python -m pip install -e ../02-mini-port-simulation
python -m pip install -e ".[dev]"
```

Run Project 03 tests:

```bash
python -m pytest
```

Validate an example config:

```bash
berth-allocation-lab --validate-config configs/scenarios/synthetic_low.yaml
```

Generate a synthetic BAP instance:

```bash
berth-allocation-lab \
  --generate-scenario configs/scenarios/synthetic_low.yaml \
  --output experiments/examples/synthetic_low.json
```

Compare baselines on one generated static instance:

```bash
berth-allocation-lab --compare-baselines configs/scenarios/synthetic_low.yaml
```

Use `--static-twin` with the medium/heavy YAML presets, which are dynamic by
default. Per-run artifacts are written to `experiments/runs`.

Run the tiny reference on the dedicated congested static preset:

```bash
berth-allocation-lab --run-candidate-reference configs/scenarios/synthetic_tiny_congested.yaml
```

Defaults are 6 vessels and 250000 search nodes. Explicit `--max-vessels 8`
allows larger tiny inputs; `--time-limit-seconds` is optional. Limits never
truncate inputs or turn feasible incumbents into certified optima.
