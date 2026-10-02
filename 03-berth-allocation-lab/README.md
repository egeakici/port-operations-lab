# Berth Allocation Lab

Project 03 is the berth-allocation optimization laboratory for the Port
Operations Lab roadmap.

Current status: Step 9 / Static Maskable PPO.

Completed:

- Step 1: problem specification
- Step 2: experiment and data contract
- Step 3: package/configuration scaffold
- Step 4: synthetic scenario schema and generator
- Step 5: continuous BAP geometry, feasibility, scheduling, candidates, and
  objectives
- Step 6: static FCFS and Greedy Rollout policies, common KPIs, and run records
- Step 7: tiny fixed-order candidate-space exact reference and certified gaps
- Step 8: StaticBAP Gymnasium environment with candidate-index actions,
  action masks and FCFS/Rollout/exact-reference replay validation
- Step 9: Static Maskable PPO training, split-disjoint scenario mixtures,
  validation-only checkpoint selection and paired evaluation against FCFS,
  Greedy Rollout and certified tiny Exact

Completed: Steps 1-9. Current: Step 9 - Static Maskable PPO.
Next: Step 10 - DynamicBAP Environment.

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
`StaticBAPEnv` exposes the same fixed-order candidate decisions to RL agents.
Step 9 trains MaskablePPO policies on it; see the Step 9 note for the measured
pilot results, which are short-budget pilots, not established performance.
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

Read the Step 8 environment definition:

- [docs/static_bap_environment.md](docs/static_bap_environment.md)

Read the Step 9 training/evaluation definition and pilot results:

- [docs/static_maskable_ppo.md](docs/static_maskable_ppo.md)

## Package Structure

- `src/berth_allocation_lab/core`: shared continuous BAP placement, geometry,
  feasibility, scheduling, candidate, and objective functions.
- `src/berth_allocation_lab/policies`: static FCFS and Greedy Rollout.
- `src/berth_allocation_lab/solvers`: tiny candidate-space enumeration.
- `src/berth_allocation_lab/envs`: `StaticBAPEnv`, split-aware synthetic and
  mixture scenario providers.
- `src/berth_allocation_lab/rl`: Static Maskable PPO configs, scenario suites,
  leakage audit, training, checkpoint inference and paired evaluation.
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

The core install has no PyTorch dependency. Step 9 reinforcement learning
(training, checkpoint inference, plots) needs the `rl` extra
(stable-baselines3 / sb3-contrib 2.8, torch, matplotlib; gymnasium < 1.3):

```bash
python -m pip install -e ".[dev,rl]"
```

Without the extra, RL test modules are skipped and the rest of the suite runs.

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

## StaticBAP Environment

```python
from berth_allocation_lab.envs import StaticBAPEnv

env = StaticBAPEnv(
    scenario=scenario,
    max_vessels=8,
)

obs, info = env.reset(seed=42)

mask = env.action_masks()
obs, reward, terminated, truncated, info = env.step(int(mask.nonzero()[0][0]))
```

Each action selects a canonical candidate berth position for the next vessel
in `(arrival_time_min, vessel_id)` order; the core sets the earliest feasible
start and the reward is the negative waiting time, so the undiscounted episode
return equals minus total waiting. Use `scenario_provider=SyntheticScenarioProvider(...)`
for reproducible generated instances with an explicit dataset split.

## Static Maskable PPO

```bash
python scripts/train_static_ppo.py --config configs/rl/static_ppo_tiny.yaml     --total-timesteps 10000 --eval-freq 2000 --output-dir experiments/rl/pilot --progress
python scripts/evaluate_static_ppo.py --config configs/rl/static_ppo_tiny.yaml     --experiment-dir experiments/rl/pilot/static_ppo_tiny_v1     --output experiments/rl/pilot_evaluations/static_ppo_tiny_v1 --progress
```

`--progress` is optional (default off). Plain tqdm bars and permanent validation
lines go to stderr; existing summary/report output remains on stdout. The display
does not enter configs/manifests or change seeds, checkpoint selection or results.

The pre-registered extended v1 campaign (300k/500k timesteps, 8 environments,
fresh 20/50-per-component validation/test suites, validation decision rule
recorded before testing) is defined in
[docs/static_maskable_ppo.md](docs/static_maskable_ppo.md#extended-v1-campaign)
with its exact commands.

Training uses `gamma = 1.0`, action masks at every decision and a fixed
training-only reward scale; checkpoints are selected on validation instances
only, and evaluation reports raw vessel-minutes paired with FCFS, Greedy
Rollout and (for tiny instances) the certified candidate-space Exact reference.
Model files stay under the Git-ignored `experiments/` directory.
