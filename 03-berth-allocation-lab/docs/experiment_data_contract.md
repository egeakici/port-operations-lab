# Experiment & Data Contract

Status: frozen for Project 03 Step 2  
Scope: Project 03 - Berth Allocation Lab  
Purpose: reproducible experiment records and scientific traceability

This document defines how future Project 03 scenarios, experiment runs, vessel
results, event records, benchmark summaries, model-training runs, and artifacts
must be represented. It does not implement the synthetic generator, BAP core,
policies, solvers, environments, PPO, DQN, MLflow integration, or writers.

## Core Principle

Project 03 owns its raw scientific records.

External tools may later display, index, or mirror records, but they are not the
canonical source of truth. The intended architecture is:

```text
Simulation / Optimization
          |
          v
Project-owned scientific records
          |
          +--> event records
          +--> vessel records
          +--> run summaries
          +--> scenario definitions
          +--> manifests / configuration
          |
          v
optional adapters
          |
          +--> MLflow
          +--> future DVC / data registry
          +--> reporting tools
```

If MLflow or another tracker disappears, changes format, or is replaced, the
scientific records must remain independently usable.

## Format Strategy

Use each file format for the job it is good at:

| Format | Intended responsibility |
| --- | --- |
| YAML | human-authored scenario, benchmark, and training configs |
| JSON | immutable run manifests and small structured metadata |
| JSONL | optional streaming/debug event logs |
| Parquet | primary structured tabular scientific records |
| CSV | lightweight exports, result tables, and publication/report outputs |

CSV is not the primary storage format for large event records. Parquet is not
required for tiny hand-authored configuration.

Future principal result datasets:

```text
events.parquet   one row per relevant event/transition
vessels.parquet  one row per vessel per run
runs.parquet     one row per experiment run
```

Optional future datasets:

```text
training_metrics.parquet
benchmark_aggregates.parquet
```

No physical writer is implemented in Step 2.

## Canonical Units

Stored scientific records use canonical internal units. Reports may convert
minutes to hours for presentation, but stored records should keep canonical
units.

| Quantity | Unit / convention |
| --- | --- |
| time | minutes |
| distance | meters |
| vessel length | meters |
| `min_clearance_m` | meters |
| waiting time | minutes |
| service duration | minutes |
| turnaround time | minutes |
| berth utilization | fraction in `[0, 1]` |
| percentile metrics | same units as source metric |
| throughput | number of completed/served vessels |
| runtime / compute latency | seconds unless explicitly documented otherwise |

Persisted field names should make units obvious when ambiguity is likely:

```text
arrival_time_min
service_time_min
waiting_time_min
length_m
berth_position_m
runtime_seconds
```

Avoid ambiguous persisted names such as `waiting`, `time`, or `length`.

## Identifier Strategy

Stable identifiers must be machine-readable and must not rely on filenames
alone.

| Identifier | Meaning |
| --- | --- |
| `scenario_id` | stable scenario or generated-instance identifier |
| `scenario_version` | scenario contract/content version |
| `run_id` | unique experiment execution ID |
| `vessel_id` | vessel identifier, unique within scenario/run context |
| `policy_id` | concrete policy/model identity, e.g. `fcfs` |
| `algorithm_version` | version of algorithm implementation or model family |
| `training_run_id` | unique training execution ID |
| `model_id` | stable trained-model artifact identifier |
| `config_id` | benchmark/training config identifier |

Examples:

```text
scenario_id: synthetic_heavy_001
scenario_version: 1
policy_id: dynamic_maskppo_v1
```

`vessel_id` should not be assumed globally unique across every dataset unless a
future global identifier scheme explicitly guarantees it.

## Scenario Contract

A BAP scenario describes the terminal geometry, information setting, data
provenance, generated/declared vessel population, and termination context.

### Required Scenario Fields

| Field | Required | Notes |
| --- | --- | --- |
| `scenario_id` | yes | stable identifier, not just filename |
| `scenario_version` | yes | changes when scenario content/schema changes |
| `scenario_family` | yes | e.g. `low`, `medium`, `heavy` |
| `formulation` | yes | `static` or `dynamic` |
| `data_provenance` | yes | `synthetic`, `ais_calibrated`, `terminal_calibrated` |
| `split` | yes | `train`, `validation`, or `test` |
| `seed` | yes for generated instances | scenario/generation seed |
| `berth_length_m` | yes | maps to Project 02 `terminal.berth_length_m` |
| `min_clearance_m` | yes | canonical field name |
| `nominal_duration_min` | yes for dynamic | maps from Project 02 `duration_hours * 60` |
| `termination_mode` | yes for dynamic | compatible with Project 02 `horizon` / `drain` |
| `vessel_count` | yes | count of vessel input records |
| `vessels` | yes | collection of vessel input records |

### Conditional / Optional Scenario Fields

| Field | Condition |
| --- | --- |
| `max_drain_extension_min` | required when drain safety limit is used |
| `future_horizon_min` | meaningful for DynamicBAP, usually null/absent for StaticBAP |
| `generator_version` | required for generated synthetic scenarios |
| `generator_config_id` | recommended for generated synthetic scenarios |
| `calibration_dataset_id` | future AIS/terminal calibrated scenarios |
| `calibration_version` | future AIS/terminal calibrated scenarios |
| `test_class` | optional future values: `in_distribution`, `out_of_distribution`, `ais_calibrated` |
| `source_metadata` | optional structured provenance details |

Do not fill semantically absent fields with misleading zeros. Use null or
missing semantics where appropriate.

## Vessel Input Contract

Project 03 BAP-oriented vessel inputs use elapsed minutes and meters while
remaining compatible with Project 01/02 concepts.

### Required V1 Vessel Input Fields

| Field | Kind | Notes |
| --- | --- | --- |
| `vessel_id` | raw/input | maps to Project 01 `Vessel.vessel_id` |
| `arrival_time_min` | raw/input | scenario-relative arrival or ETA time |
| `length_m` | raw/input | maps to Project 01 `Vessel.length_m` |
| `service_time_min` | raw/input | BAP service/handling duration used by the optimizer/env |

### Optional / Future-Compatible Fields

| Field | Notes |
| --- | --- |
| `priority` | compatible with Project 01 `Vessel.priority`, not v1 objective |
| `vessel_type` | future calibration/analysis |
| `beam_m` | future geometry constraints |
| `draft_m` | future berth compatibility |
| `workload_moves` | compatible with Project 01/02 workload model |
| `announced_eta_min` | future forecast/update modeling |
| `preferred_berth_region` | future soft preference/objective extension |
| `source_metadata` | source-specific references, anonymized if needed |

Speculative fields must not become mandatory until an implementation step
requires them.

## Scenario Provenance

Every scenario must state where its parameters came from.

Canonical `data_provenance` values:

```text
synthetic
ais_calibrated
terminal_calibrated
```

For synthetic scenarios, record:

- `generator_version`,
- `seed`,
- distribution/config reference.

For AIS-calibrated scenarios, future records should include:

- `calibration_dataset_id`,
- `calibration_version`.

For terminal-calibrated scenarios, future records should include external or
restricted dataset references rather than requiring raw partner data in Git.

An AIS-calibrated scenario is still not automatically a real terminal
operational dataset. That distinction must remain explicit.

## Train / Validation / Test Split Contract

Scenarios and generated instances must support:

```text
split: train | validation | test
```

Test instances and test seeds must not be used during model training.

Training performance is not benchmark performance. Final reported RL results
must be evaluated on unseen test scenarios/seeds.

Train/validation/test allocation itself must be reproducible. A dataset or
benchmark config version should determine which instances belong to each split;
the repository must not reshuffle splits differently on every run.

Future test classes may include:

```text
in_distribution
out_of_distribution
ais_calibrated
```

They are not implemented in Step 2.

## Run Manifest Contract

Each experiment execution has one immutable run manifest.

### Required Run Manifest Fields

| Field | Notes |
| --- | --- |
| `run_id` | unique execution ID |
| `created_at` | timestamp, preferably ISO 8601 |
| `project_version` | Project 03 package/version once available |
| `git_commit_hash` | code traceability |
| `git_dirty` | optional but strongly recommended |
| `scenario_id` | scenario identity |
| `scenario_version` | scenario version |
| `scenario_seed` | scenario/generation seed |
| `formulation` | `static` or `dynamic` |
| `policy_id` | concrete policy/model identity |
| `policy_family` | e.g. `fcfs`, `greedy`, `maskable_ppo` |
| `algorithm_version` | algorithm/model implementation version |
| `data_provenance` | copied from scenario |
| `status` | `started`, `completed`, `completed_with_limit`, `invalid_unresolved_vessels`, or `failed` |

### Conditional / Optional Run Manifest Fields

| Field | Condition |
| --- | --- |
| `config_id` / `config_version` | when launched from config |
| `future_horizon_min` | DynamicBAP or horizon ablation |
| `python_version` | environment metadata |
| `package_versions` | relevant packages |
| `hardware_metadata` | optional |
| `failure_type` | failed/invalid runs |
| `failure_message` | failed/invalid runs |
| `artifact_refs` | output files, logs, figures, checkpoints |

Failed and invalid runs must remain recorded.

## Event-Level Record Contract

Event records preserve enough raw information to reconstruct system evolution
and recompute future metrics.

### Event Record Fields

| Field | Required | Notes |
| --- | --- | --- |
| `run_id` | yes | foreign key to run manifest/result |
| `scenario_id` | yes | scenario identity |
| `event_index` | yes | monotonic within run |
| `simulation_time_min` | yes | elapsed minutes |
| `event_type` | yes | Project 03 scientific event type |
| `transition_type` | yes | `agent_assignment`, `agent_wait`, `automatic_advance`, `system_event`, etc. |
| `decision_point_type` | conditional | arrival/release/announcement/update/post-assignment |
| `vessel_id` | conditional | relevant vessel |
| `queue_length` | optional | alias-compatible with waiting count when defined |
| `waiting_vessel_count` | optional | current waiting count |
| `berthed_vessel_count` | optional | current berthed count |
| `free_quay_length_m` | optional | when cheaply available |
| `selected_action_type` | conditional | `assignment`, `wait`, `none` |
| `selected_vessel_id` | conditional | assignment actions |
| `selected_candidate_index` | conditional | candidate-based actions |
| `selected_berth_position_m` | conditional | assignment actions |
| `candidate_count` | conditional | decision events |
| `candidate_positions_m` | optional | compact JSON/list artifact for debug |
| `valid_candidate_mask` | optional | compact JSON/list artifact for debug |
| `wait_selected` | conditional | true only for intentional policy WAIT |
| `reward` | optional | RL transition reward |
| `delta_time_min` | optional | transition interval |
| `cumulative_reward` | optional | RL/debug |
| `action_was_masked` | optional | invalid-action diagnostics |
| `is_valid` | optional | validation status |

Not every field is populated for every event. Null/missing should mean
semantically absent, not zero.

### Event Type Alignment

Project 01/02 have canonical terminal event names such as:

```text
vessel_arrived
vessel_waiting
vessel_berthed
vessel_operation_started
vessel_operation_completed
vessel_departed
berth_occupancy_added
berth_occupancy_removed
```

Project 03 scientific event records may use higher-level event types such as:

```text
EPISODE_START
VESSEL_ARRIVAL
BERTH_RELEASE
ANNOUNCEMENT
ETA_UPDATE
ASSIGNMENT
WAIT
AUTOMATIC_ADVANCE
EPISODE_END
```

When a Project 03 event corresponds to a Project 01/02 terminal event, preserve
the original event reference or source event type in metadata rather than
renaming destructively.

## WAIT vs Automatic Advancement

The data contract must preserve the distinction between intentional policy
`WAIT` and automatic environment time advancement.

### Intentional Policy WAIT

The agent is called only because a meaningful decision exists. `WAIT` can be
selected only when:

- at least one vessel is waiting,
- at least one feasible assignment currently exists.

Record this as policy behavior:

```text
transition_type = agent_wait
selected_action_type = wait
wait_selected = true
candidate_count > 0
feasible_assignment_count > 0
```

### Automatic Environment Advancement

If no vessel is waiting, or vessels are waiting but no feasible assignment
exists, the agent is not called. The environment advances to the next meaningful
event.

Record this as environment behavior:

```text
transition_type = automatic_advance
selected_action_type = none
wait_selected = false
```

Automatic advancement must not be recorded as if the RL policy selected `WAIT`.

## Vessel Result Contract

There is one final vessel-level result record per vessel per run.

| Field | Required | Kind |
| --- | --- | --- |
| `run_id` | yes | key |
| `scenario_id` | yes | key |
| `vessel_id` | yes | key within run/scenario |
| `arrival_time_min` | yes | input/raw |
| `berth_start_time_min` | conditional | recorded outcome |
| `berth_position_m` | conditional | recorded outcome |
| `service_time_min` | yes | input/raw or realized service duration |
| `service_end_time_min` | conditional | recorded outcome |
| `waiting_time_min` | conditional | derived |
| `turnaround_time_min` | conditional | derived |
| `completed` | yes | recorded outcome |
| `completion_status` | yes | e.g. `completed`, `unresolved`, `failed` |
| `policy_id` | yes | run policy |

Optional derived/debug fields:

- `waiting_rank`,
- `was_delayed`,
- `decision_count`,
- `reassignments`.

Equations:

```text
waiting_time_min = berth_start_time_min - arrival_time_min
turnaround_time_min = service_end_time_min - arrival_time_min
```

For unresolved vessels, derived times that require berth/service completion
should be null rather than forced to zero.

## Run-Level Result Contract

There is one summary record per run.

| Field | Required |
| --- | --- |
| `run_id` | yes |
| `scenario_id` | yes |
| `scenario_version` | yes |
| `seed` | yes |
| `formulation` | yes |
| `policy_id` | yes |
| `vessel_count_generated` | yes |
| `vessel_count_completed` | yes |
| `vessel_count_unresolved` | yes |
| `nominal_duration_min` | yes |
| `simulation_end_time_min` | yes |
| `drain_duration_min` | dynamic/drain |
| `total_waiting_time_min` | completed valid runs |
| `mean_waiting_time_min` | completed valid runs |
| `p95_waiting_time_min` | completed valid runs |
| `mean_turnaround_time_min` | completed valid runs |
| `p95_turnaround_time_min` | completed valid runs |
| `berth_utilization` | yes when computable |
| `throughput_vessels` | yes |
| `algorithm_runtime_seconds` | yes when measured |
| `wall_clock_runtime_seconds` | optional/useful |
| `episode_return` | RL runs |
| `status` | yes |
| `is_valid` | yes |
| `validation_status` | yes |
| `violation_count` | yes |

All policies must use the same metric definitions. A run with unresolved
vessels or physical invariant violations must not silently enter scientific
benchmark averages.

## KPI Definitions

Let `N` be the number of vessels in the defined evaluation scope. For clean
completed benchmark runs, this should be the number of generated vessels. If
unresolved vessels exist, the run status must make that clear before metrics are
aggregated.

### Total Waiting Time

```text
TotalWaiting = sum_i W_i
W_i = berth_start_time_min_i - arrival_time_min_i
```

### Mean Waiting

```text
MeanWaiting = (1 / N) * sum_i W_i
```

### P95 Waiting

The 95th percentile of vessel waiting times, in minutes. The exact percentile
method should be versioned when implemented.

### Mean Turnaround

```text
T_i = service_end_time_min_i - arrival_time_min_i
MeanTurnaround = (1 / N) * sum_i T_i
```

### P95 Turnaround

The 95th percentile of vessel turnaround times, in minutes.

### Throughput

Number of successfully serviced/completed vessels during the defined evaluation
scope.

### Berth Utilization

Project 03 should inherit Project 02's current conceptual definition:

```text
berth_utilization =
  occupied_length_minutes / (total_berth_length_m * evaluation_duration_min)
```

where occupied length-minutes are computed from berth occupancy intervals and
vessel lengths. Project 02 caps the result at `1.0`. If Project 03 later changes
the evaluation duration or occupancy interpretation, that must be reflected in
`metric_version`.

## Termination and Unresolved Vessels

Run records must distinguish:

- `nominal_duration_min`,
- `simulation_end_time_min`,
- `drain_duration_min`,
- `vessel_count_generated`,
- `vessel_count_completed`,
- `vessel_count_unresolved`.

Conceptual run statuses:

```text
started
completed
completed_with_limit
invalid_unresolved_vessels
failed
```

If maximum drain extension is reached and vessels remain unresolved, the run
must not look comparable to a clean completed run.

## Candidate Action Record Contract

Decision events may need to record candidate sets for debugging and paired
analysis.

Supported fields:

- `candidate_count`,
- deterministic candidate ordering,
- candidate berth positions,
- validity/mask for each candidate,
- selected candidate index,
- selected candidate berth position.

Candidate ordering must be deterministic for an identical state and
configuration.

These records are for:

- FCFS,
- Greedy,
- RL,
- action masking,
- tiny candidate enumeration,
- debugging.

They are not part of the future continuous exact optimizer contract.

## Candidate-Space Oracle vs Continuous Reference

The experiment contract must prevent academic mislabeling.

Conceptual `reference_scope` values:

```text
none
candidate_space
continuous_problem
```

A brute-force enumeration over candidate actions is a candidate-space oracle,
not a continuous optimum unless a later proof establishes equivalence.

A future mathematical solver may produce a continuous-BAP reference using berth
positions outside the finite candidate set.

## Exact / Oracle Metadata

Future exact/reference runs should support:

| Field | Notes |
| --- | --- |
| `solver_family` | e.g. brute force, CP-SAT, MILP |
| `solver_version` | implementation version |
| `reference_scope` | `candidate_space` or `continuous_problem` |
| `optimality_status` | e.g. optimal, feasible, timeout, failed |
| `objective_value` | objective in vessel-minutes |
| `solver_runtime_seconds` | compute time |
| `time_limit_seconds` | if used |
| `solver_gap` | solver-reported gap if applicable |
| `optimality_gap` | policy vs reference where applicable |

No solver logic is implemented in Step 2.

## RL Training Run Contract

Future RL training runs must record enough metadata to reproduce the model.

Required/expected fields:

- `training_run_id`,
- `algorithm`,
- `algorithm_version`,
- `environment_id`,
- `environment_version`,
- `formulation`,
- `training_seed`,
- `training_scenario_set` or generator config,
- `validation_scenario_set`,
- `total_timesteps`,
- algorithm hyperparameters, e.g. `learning_rate`, `gamma`,
- PPO-specific fields where relevant: `gae_lambda`, `clip_range`, `n_steps`,
  `batch_size`,
- policy/network architecture reference,
- `action_masking_enabled`,
- `reward_definition_version`,
- `observation_definition_version`,
- `candidate_generator_version`,
- checkpoint artifact IDs/paths,
- best model reference,
- final model reference,
- training start/end timestamps.

Do not assume every algorithm uses PPO parameters. Algorithm-specific parameters
should be represented cleanly.

## RL Training Metrics

Future training records should support:

- `episode_return`,
- `episode_total_waiting_time`,
- `episode_mean_waiting_time`,
- `episode_length`,
- `policy_loss`,
- `value_loss`,
- `entropy`,
- `approx_kl` where applicable,
- `explained_variance` where applicable,
- evaluation waiting metrics,
- validation metrics.

Training reward alone is not proof of policy quality. Benchmark KPI evaluation
on unseen test scenarios is the final performance measure.

## Model Artifact Contract

Trained model artifacts need metadata beyond filenames.

Required/expected fields:

- `model_id`,
- `policy_id`,
- `algorithm`,
- `version`,
- `training_run_id`,
- `git_commit_hash`,
- `environment_version`,
- `observation_definition_version`,
- `reward_definition_version`,
- `candidate_generator_version`,
- `training_seed`,
- training configuration reference,
- creation timestamp.

Do not create actual model files in Step 2.

## Experiment Config Contract

Future benchmark/training execution should be config-driven, not hard-coded in
Python.

An experiment config should eventually specify:

- `experiment_id`,
- scenario selection,
- scenario split,
- seeds,
- policies to evaluate,
- future horizon values if applicable,
- repetitions,
- output location,
- metrics,
- runtime limits,
- exact solver limits where relevant.

No runner is implemented in Step 2.

## Fair Comparison Contract

Directly compared policies must receive identical scenario instances.

For:

```text
scenario_id = heavy_001
seed = 8472
```

the following must be identical across FCFS, Greedy, PPO, candidate enumeration,
and compatible references:

- arrival sequence,
- vessel population,
- service durations,
- problem parameters.

This is the common-instance / common-randomness comparison principle.

Records must preserve enough keys, especially `scenario_id`, `scenario_version`,
and `seed`, to support paired comparisons across policies.

## Randomness Contract

Potential randomness sources:

- scenario generation,
- arrival processes,
- service-time stochasticity,
- ETA noise,
- RL initialization,
- RL exploration,
- environment stochasticity.

Every stochastic component should eventually derive from explicitly recorded
seeds. Avoid hidden global randomness.

Conceptual seed namespaces:

```text
scenario_seed
environment_seed
training_seed
evaluation_seed
```

Project 02 already uses derived random streams such as `arrival`, `eta`,
`failure`, `productivity`, `vessel`, and `workload`. Project 03 should preserve
or record equivalent seed manifests when using MiniPortSim-derived stochastic
worlds.

## Versioning Contract

Explicit versions are required for components whose changes alter the meaning of
experimental results:

- `problem_spec_version`,
- `scenario_schema_version`,
- `generator_version`,
- `candidate_generator_version`,
- `objective_version`,
- `reward_version`,
- `observation_version`,
- `metric_version`,
- `environment_version`,
- `benchmark_version`,
- `policy_version`.

The goal is scientific traceability, not bureaucracy. Do not require semantic
versioning for every internal helper function.

## Git Traceability

Every run manifest should eventually include:

- `git_commit_hash`,
- `git_dirty` or equivalent indication of uncommitted local modifications.

Publication results should not depend on code that cannot be reconstructed.

## Failure Recording

Failed experiments are scientifically useful and must not be silently dropped.

Supported failure categories include:

- invalid scenario,
- constraint violation,
- unresolved vessels,
- timeout,
- solver failure,
- environment exception,
- NaN reward,
- training failure.

Record:

- `status`,
- `failure_type`,
- `failure_message`,
- whatever run/scenario metadata exists.

Large stack traces should be separate debug artifacts, not primary benchmark
table fields.

## Invariant Violation Recording

Future runs should make invariant violations explicit.

Examples:

- vessel before arrival,
- spatial overlap,
- clearance violation,
- quay boundary violation,
- negative waiting time,
- time reversal,
- future-information leakage,
- invalid masked action executed.

Record support:

- `is_valid`,
- `validation_status`,
- `violation_count`,
- optional artifact references to detailed violation logs.

A run with physical invariant violations must not silently enter scientific
benchmark averages.

## Aggregated Benchmark Contract

Aggregates must preserve access to raw per-run values underneath.

For a group such as:

```text
formulation = dynamic
scenario_family = heavy
future_horizon_min = 240
policy_id = dynamic_maskppo_v1
n = 30 seeds
```

support statistics such as:

- `n_runs`,
- mean,
- median,
- standard deviation,
- P95 where relevant,
- minimum,
- maximum,
- confidence interval when implemented.

Do not choose or implement a specific confidence-interval method in Step 2.

## Paired Comparison Support

Because multiple policies will run on identical scenario/seed combinations,
records must make paired comparisons possible.

The key:

```text
scenario_id + scenario_version + seed
```

should pair FCFS, Greedy, PPO, candidate-space oracle, and exact/reference
results where compatible.

Do not implement statistical tests in Step 2.

## Runtime / Compute Metrics

Distinguish simulation time from compute time.

Examples:

```text
simulation_time_min = 1440
algorithm_runtime_seconds = 0.42
```

The first describes the simulated terminal horizon; the second describes
computer time.

Future supported compute fields:

- `algorithm_runtime_seconds`,
- `decision_latency_ms`,
- `training_runtime_seconds`,
- `solver_runtime_seconds`,
- `wall_clock_runtime_seconds`.

## Directory / Artifact Intent

Future directory responsibilities:

| Directory | Future responsibility |
| --- | --- |
| `data/raw` | immutable external/raw inputs, not large partner data in Git |
| `data/interim` | intermediate cleaned/converted data |
| `data/processed` | model-ready/scientific derived datasets |
| `data/synthetic` | generated synthetic scenarios/instances |
| `experiments` | run manifests and local experiment outputs |
| `models` | trained model artifacts or references |
| `reports/tables` | CSV/Markdown/LaTeX result tables |
| `reports/figures` | plots and diagrams |
| `reports/findings` | experiment summaries and interpretation |

Step 2 documents intent only. It does not create the full package/directory
scaffold.

## Relational Keys

Conceptual table relationships:

```text
runs.run_id
    |
    +--> vessels.run_id
    |
    +--> events.run_id

scenarios.scenario_id + scenario_version
    |
    +--> runs.scenario_id + scenario_version
```

`vessel_id` is unique within a scenario/run context unless future global vessel
identity is explicitly introduced.

## Nullability and Conditional Fields

Fields must distinguish:

- required,
- optional,
- conditionally required.

Examples:

- `berth_position_m` is not meaningful before assignment.
- `selected_vessel_id` is not meaningful for every system event.
- `future_horizon_min` is not required for StaticBAP.

Do not fill semantically absent fields with misleading zeros.

## Derived vs Raw Fields

Important fields should be classified as:

- raw/input,
- recorded state,
- derived metric.

Examples:

| Field | Kind |
| --- | --- |
| `arrival_time_min` | raw/input |
| `berth_start_time_min` | recorded simulation outcome |
| `waiting_time_min` | derived |
| `turnaround_time_min` | derived |

Derived fields should be recomputable from canonical raw/recorded fields where
practical.

## Data Validation Rules

Future validators/tests should check:

- `arrival_time_min >= 0`,
- `length_m > 0`,
- `service_time_min > 0`,
- `0 <= berth_position_m`,
- `waiting_time_min >= 0`,
- `turnaround_time_min >= service_time_min`,
- `vessel_count_completed <= vessel_count_generated`,
- P95 waiting is not below median waiting where both are defined from the same
  sample/method,
- `0 <= berth_utilization <= 1`,
- no time reversal within a run,
- no future information leakage outside DynamicBAP horizon `H`.

No validators are implemented in Step 2.

## Compatibility Mapping with Project 01/02

| Existing concept | Project 03 persisted field / handling |
| --- | --- |
| Project 01 `Vessel.vessel_id` | `vessel_id` |
| Project 01 `Vessel.length_m` | `length_m` |
| Project 01 `Vessel.eta` | scenario-relative `arrival_time_min` for scientific records |
| Project 01 `Vessel.workload_moves` | optional `workload_moves` |
| Project 01 `Vessel.priority` | optional `priority` |
| Project 01 `Berth.length_m` | `berth_length_m` |
| Project 01 `Berth.min_clearance_m` | `min_clearance_m` |
| Project 02 `ScenarioConfig.scenario_id` | `scenario_id` |
| Project 02 `ScenarioConfig.seed` | `seed` / `scenario_seed` |
| Project 02 `duration_hours` | `nominal_duration_min` after multiplying by 60 |
| Project 02 `max_drain_extension_hours` | `max_drain_extension_min` after multiplying by 60 |
| Project 02 `TerminationMode` | `termination_mode` |
| Project 02 `VesselArrivalPlan.arrival_time_minutes` | `arrival_time_min` |
| Project 02 `VesselLifecycleRecord.berth_time_minutes` | `berth_start_time_min` |
| Project 02 `VesselLifecycleRecord.departure_time_minutes` | current proxy for `service_end_time_min` when BAP treats departure-ready as completion |
| Project 02 metrics `average_waiting_time_minutes` | `mean_waiting_time_min` |
| Project 02 metrics `p95_waiting_time_minutes` | `p95_waiting_time_min` |

Project 03 uses `_min` suffix for persisted scientific time fields, while
Project 02 Python objects often use `_minutes`. This is a storage naming choice,
not a unit change.

## Data Privacy and Future Industry Data

Future partner/terminal data may require:

- restricted local storage,
- anonymization,
- dataset identifiers instead of raw publication,
- license/NDA handling,
- synthetic publication substitutes.

Do not assume real partner data can be committed to Git. The data contract must
be able to reference restricted external datasets without requiring their
contents in the public repository.

## Publication Traceability

The contract should support future claims such as:

```text
Dynamic Maskable PPO reduced mean waiting time by X% relative to FCFS on
benchmark suite Y.
```

Such a statement must be traceable to:

- benchmark version,
- scenario IDs,
- seeds,
- code commit,
- model ID,
- policy configuration,
- raw vessel results,
- run-level metrics,
- aggregation method.

## MLflow Position

MLflow is a future optional experiment-tracking adapter.

MLflow may eventually store/display:

- parameters,
- metrics,
- models,
- artifacts,
- training curves,
- run comparisons.

The direction is:

```text
Canonical scientific records
        |
        +--> MLflow adapter
```

not:

```text
MLflow database
        |
        +--> everything else
```

No MLflow adapter is implemented in Step 2.

## Example Records

All examples in this section are synthetic illustrations, not benchmark results.

### 1. EXAMPLE / SYNTHETIC ILLUSTRATION - Scenario Metadata

```yaml
scenario_id: synthetic_heavy_001
scenario_version: 1
scenario_family: heavy
formulation: dynamic
data_provenance: synthetic
split: test
seed: 8472
berth_length_m: 1200.0
min_clearance_m: 20.0
nominal_duration_min: 1440.0
termination_mode: drain
max_drain_extension_min: 10080.0
future_horizon_min: 240.0
vessel_count: 30
generator_version: synthetic_generator_v1
generator_config_id: heavy_v1
```

### 2. EXAMPLE / SYNTHETIC ILLUSTRATION - Vessel Input

```yaml
vessel_id: V001
arrival_time_min: 85.0
length_m: 245.0
service_time_min: 222.0
priority: 2
workload_moves: 444
```

### 3. EXAMPLE / SYNTHETIC ILLUSTRATION - Run Manifest

```json
{
  "run_id": "run_20260914_000001",
  "created_at": "2026-09-14T10:00:00Z",
  "project_version": "0.1.0",
  "git_commit_hash": "abc1234",
  "git_dirty": true,
  "scenario_id": "synthetic_heavy_001",
  "scenario_version": 1,
  "scenario_seed": 8472,
  "formulation": "dynamic",
  "policy_id": "dynamic_maskppo_v1",
  "policy_family": "maskable_ppo",
  "algorithm_version": "v1",
  "data_provenance": "synthetic",
  "future_horizon_min": 240.0,
  "status": "completed"
}
```

### 4. EXAMPLE / SYNTHETIC ILLUSTRATION - ASSIGNMENT Event

```json
{
  "run_id": "run_20260914_000001",
  "scenario_id": "synthetic_heavy_001",
  "event_index": 17,
  "simulation_time_min": 125.0,
  "event_type": "ASSIGNMENT",
  "transition_type": "agent_assignment",
  "decision_point_type": "VESSEL_ARRIVAL",
  "waiting_vessel_count": 2,
  "selected_action_type": "assignment",
  "selected_vessel_id": "V003",
  "selected_candidate_index": 1,
  "selected_berth_position_m": 320.0,
  "candidate_count": 3,
  "reward": 0.0,
  "delta_time_min": 0.0,
  "cumulative_reward": -80.0
}
```

### 5. EXAMPLE / SYNTHETIC ILLUSTRATION - Intentional Agent WAIT

```json
{
  "run_id": "run_20260914_000001",
  "scenario_id": "synthetic_heavy_001",
  "event_index": 18,
  "simulation_time_min": 125.0,
  "event_type": "WAIT",
  "transition_type": "agent_wait",
  "decision_point_type": "POST_ASSIGNMENT",
  "waiting_vessel_count": 2,
  "selected_action_type": "wait",
  "wait_selected": true,
  "candidate_count": 1,
  "feasible_assignment_count": 1,
  "delta_time_min": 15.0,
  "reward": -30.0
}
```

### 6. EXAMPLE / SYNTHETIC ILLUSTRATION - Automatic Advance

```json
{
  "run_id": "run_20260914_000001",
  "scenario_id": "synthetic_heavy_001",
  "event_index": 19,
  "simulation_time_min": 140.0,
  "event_type": "AUTOMATIC_ADVANCE",
  "transition_type": "automatic_advance",
  "waiting_vessel_count": 2,
  "selected_action_type": "none",
  "wait_selected": false,
  "candidate_count": 0,
  "feasible_assignment_count": 0,
  "delta_time_min": 70.0
}
```

### 7. EXAMPLE / SYNTHETIC ILLUSTRATION - Vessel Result

```json
{
  "run_id": "run_20260914_000001",
  "scenario_id": "synthetic_heavy_001",
  "vessel_id": "V003",
  "arrival_time_min": 125.0,
  "berth_start_time_min": 125.0,
  "berth_position_m": 320.0,
  "service_time_min": 180.0,
  "service_end_time_min": 305.0,
  "waiting_time_min": 0.0,
  "turnaround_time_min": 180.0,
  "completed": true,
  "completion_status": "completed",
  "policy_id": "dynamic_maskppo_v1"
}
```

### 8. EXAMPLE / SYNTHETIC ILLUSTRATION - Run Summary

```json
{
  "run_id": "run_20260914_000001",
  "scenario_id": "synthetic_heavy_001",
  "scenario_version": 1,
  "seed": 8472,
  "formulation": "dynamic",
  "policy_id": "dynamic_maskppo_v1",
  "vessel_count_generated": 30,
  "vessel_count_completed": 30,
  "vessel_count_unresolved": 0,
  "total_waiting_time_min": 4210.0,
  "mean_waiting_time_min": 140.33,
  "p95_waiting_time_min": 390.0,
  "mean_turnaround_time_min": 365.12,
  "p95_turnaround_time_min": 690.0,
  "berth_utilization": 0.74,
  "throughput_vessels": 30,
  "nominal_duration_min": 1440.0,
  "simulation_end_time_min": 1880.0,
  "drain_duration_min": 440.0,
  "algorithm_runtime_seconds": 0.82,
  "wall_clock_runtime_seconds": 1.15,
  "episode_return": -4210.0,
  "status": "completed",
  "is_valid": true,
  "violation_count": 0
}
```

### 9. EXAMPLE / SYNTHETIC ILLUSTRATION - RL Training Metadata

```json
{
  "training_run_id": "train_dynamic_maskppo_v1_001",
  "algorithm": "maskable_ppo",
  "algorithm_version": "v1",
  "environment_id": "dynamic_bap_env",
  "environment_version": "v1",
  "formulation": "dynamic",
  "training_seed": 123,
  "training_scenario_set": "synthetic_train_v1",
  "validation_scenario_set": "synthetic_validation_v1",
  "total_timesteps": 1000000,
  "learning_rate": 0.0003,
  "gamma": 0.99,
  "gae_lambda": 0.95,
  "clip_range": 0.2,
  "n_steps": 2048,
  "batch_size": 64,
  "action_masking_enabled": true,
  "reward_definition_version": "waiting_integral_v1",
  "observation_definition_version": "dynamic_obs_v1",
  "candidate_generator_version": "candidate_generator_v1"
}
```

### 10. EXAMPLE / SYNTHETIC ILLUSTRATION - Candidate-Space Oracle

```json
{
  "run_id": "ref_candidate_001",
  "scenario_id": "tiny_static_001",
  "policy_id": "candidate_enumeration_v1",
  "reference_scope": "candidate_space",
  "candidate_positions_m": [0.0, 250.0, 520.0],
  "objective_value": 1420.0,
  "optimality_status": "optimal_within_candidate_space"
}
```

### 11. EXAMPLE / SYNTHETIC ILLUSTRATION - Continuous Reference

```json
{
  "run_id": "ref_continuous_001",
  "scenario_id": "tiny_static_001",
  "policy_id": "continuous_solver_v1",
  "reference_scope": "continuous_problem",
  "objective_value": 1380.0,
  "solver_family": "future_continuous_bap_solver",
  "optimality_status": "optimal"
}
```

The candidate-space value is not a continuous optimum. The continuous reference
may use berth positions not present in the candidate set.

## WAIT Example: Policy WAIT vs Automatic Advance

Case A:

```text
2 vessels waiting
1 feasible assignment exists
agent chooses WAIT
```

Record:

```text
transition_type = agent_wait
```

This is policy behavior.

Case B:

```text
2 vessels waiting
0 feasible assignments exist
environment jumps to next BERTH_RELEASE event
```

Record:

```text
transition_type = automatic_advance
```

This is not policy `WAIT`.

## Candidate Oracle Example

Suppose candidate positions are:

```text
[0, 250, 520]
```

Tiny enumeration explores only combinations created from these positions. If the
best objective is:

```text
1420 vessel-minutes
```

record:

```text
reference_scope = candidate_space
```

Do not call it `continuous optimum`.

A future mathematical optimizer may find:

```text
1380 vessel-minutes
```

using a berth position not contained in the candidate set. That result may be
recorded as:

```text
reference_scope = continuous_problem
```

## Roadmap Traceability

| Contract item | Future step using it |
| --- | --- |
| Package/config conventions | Step 3 Scaffold |
| Scenario contract | Step 4 Synthetic Generator |
| Vessel input contract | Step 4 Synthetic Generator, Step 5 Core |
| Candidate metadata | Step 5 Continuous BAP Core |
| Event/vessel/run records | Steps 6-12 |
| Policy/run metadata | Step 6 Baselines onward |
| Reference-scope metadata | Step 7 Exact / candidate enumeration |
| RL training metadata | Steps 9-11 |
| Model artifact metadata | Steps 9-11 |
| Benchmark aggregate contract | Step 12 Scientific Benchmark |
| Reporting/export formats | Step 12 Results Warehouse |
