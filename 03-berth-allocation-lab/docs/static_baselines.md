# Static Baselines And Scientific Runs

Step 6 schedules a complete static BAP instance with two deterministic policies.
Both process vessels in `(arrival_time_min, vessel_id)` order and use the Step 5
candidate, earliest-start, and objective helpers.

- `static_fcfs_v1` chooses the candidate minimizing `(earliest_start, position)`.
- `static_greedy_lookahead_v1` temporarily places the current vessel at each
  candidate, then independently estimates the minimum waiting time for each
  remaining vessel. It chooses the minimum `(current wait + estimated future
  waits, current start, position)`. The estimate does not schedule future
  vessels against one another; it is a heuristic, not a global optimum.

The runner validates every completed schedule with the Step 5 validator.
Invalid or failed runs have null objective/KPI values and remain traceable.
Unambiguous raw placement outcomes remain in failed vessel rows, while their
derived metrics stay null and `completed` stays false.

## Metrics

`static_metrics_v1_type7` uses waiting and turnaround in minutes. P95 uses
linear Type-7 interpolation: sort values, use rank `(n - 1) * 0.95`, and
interpolate between the adjacent ranks. Utilization is hull length-minutes
divided by `berth_length_m * schedule_end_time_min` over the window from
scenario minute 0 through last service completion. Clearance and waiting
occupy no hull area. Throughput counts completed vessels. Algorithm runtime
uses `perf_counter()` seconds around policy execution only; validation and
artifact writing are excluded, and schedule time remains a separate quantity.

## Artifacts

Each persisted run creates `experiments/runs/<run_id>/` with:

```text
manifest.json
scenario.json
decisions.jsonl
placements.jsonl
vessels.jsonl
violations.json
run_summary.json
```

The manifest records the scenario fingerprint, seed, formulation, provenance,
split, policy and algorithm versions, metric version, UTC timestamp, package
version, and local Git commit/dirty state when available. `decision_index` is
an offline choice index, not a simulation timestamp. `scenario.json` and raw
placement rows allow independent reconstruction. Decision and placement rows
carry `run_id` and `scenario_id` for joins. JSONL is the local Step 6
record format; later warehouse exports may materialize Parquet.

For MEDIUM and HEAVY presets, which are declared dynamic, explicitly request
a static twin before comparison. The generator reuses the same seed and vessel
sampling, clears the future horizon, and records the resulting instance as
`static`. The static runner rejects an instance still marked `dynamic`.

```bash
berth-allocation-lab --compare-baselines configs/scenarios/synthetic_low.yaml
berth-allocation-lab --compare-baselines configs/scenarios/synthetic_medium.yaml --static-twin
```

These single-seed comparisons are smoke experiments, not statistical evidence.
