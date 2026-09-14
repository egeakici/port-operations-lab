# Synthetic Scenarios

Status: Project 03 Step 4

Step 4 generates controlled, non-calibrated synthetic BAP instances. These
scenarios are engineering benchmark inputs, not empirical claims about a real
port.

## Generated Fields

Each generated vessel has:

- `vessel_id`
- `arrival_time_min`
- `length_m`
- `workload_moves`
- `service_time_min`

The same generated instance can later be consumed by StaticBAP with full
information or DynamicBAP with limited information. Formulation metadata must
not alter vessel ground truth.

## V1 Distributions

Synthetic v1 uses Project 02-compatible assumptions:

- First vessel arrives at `0.0` minutes.
- Later interarrival times are exponential with
  `mean_interarrival_minutes`.
- Vessel length is uniform between `min_vessel_length_m` and
  `max_vessel_length_m`, rounded to two decimal places for compatibility with
  Project 02.
- Workload is integer-uniform between `min_workload_moves` and
  `max_workload_moves`.

## Service Duration

For Project 03 v1:

```text
service_time_min =
  berthing_preparation_minutes
  + service_duration_minutes(workload_moves)
  + departure_preparation_minutes
```

This is a planned, exogenous berth-occupancy duration for BAP. It is not a claim
that a future detailed crane/yard simulation will always realize exactly that
duration.

## Reproducibility

Generation is deterministic from:

```text
config + generator_version + seed
```

The generator uses Project 02 `RandomStreams` and does not mutate Python global
random state.

