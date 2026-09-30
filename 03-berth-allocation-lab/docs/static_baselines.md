# Static Baselines And Scientific Runs

Step 6 builds complete static schedules in `(arrival_time_min, vessel_id)`
order. Both policies use the same Step 5 candidate generator, earliest-start
function, and shared FCFS next-placement rule. They are deterministic and use
total vessel waiting time without heuristic weights.

- `static_fcfs_v1`: choose the next vessel's candidate minimizing
  `(earliest_start_time_min, berth_position_m)`.
- `static_greedy_rollout_v1`: for each current candidate, temporarily place
  that vessel, then complete all remaining vessels sequentially with the
  exact shared FCFS rule. Score the current and continuation waiting in
  vessel-minutes. Choose minimum `(score, current_start, position)`.

The rollout continuation is a realizable schedule. The policy is neither an
exact solver nor a claim of global or continuous BAP optimality.

## FCFS Dominance Under Frozen V1 Rules

Greedy Rollout's final total waiting is no greater than `static_fcfs_v1`'s,
up to the shared `NUMERICAL_TOLERANCE`. This guarantee assumes identical vessel
order, candidate generator, shared FCFS next-placement and tie-breaking,
deterministic continuation, non-negative waiting, and no mutation while
evaluating candidates.

At decision `k`, let `C_k` be waiting already realized and `S_k` the chosen
realizable FCFS-rollout suffix score. After placing the current vessel with
waiting `W_i`, the rollout's next FCFS placement remains one of the candidates
at decision `k+1`: the partial schedule is identical to the one used in that
rollout, and the shared FCFS rule is deterministic. Therefore:

```text
S_(k+1) <= S_k - W_i
C_(k+1) + S_(k+1) <= C_k + S_k
```

Initially, the full FCFS trajectory is one evaluated candidate and
`C_0 + S_0 <= TotalWaiting(FCFS)`. At termination, the suffix is empty, so
`TotalWaiting(Greedy Rollout) <= TotalWaiting(FCFS)`. This is dominance only
relative to the frozen v1 FCFS candidate-space construction, not proof of a
candidate-space or continuous optimum.

The manual fixture has a 500 m quay and 10 m clearance. Vessels in order are
`A(0, 100 m, 100 min)`, `B(0, 250 m, 1000 min)`, and
`C(100, 200 m, 100 min)`. A's candidates are `0` and `400` m. FCFS chooses
`0` m; B's candidates then include `0`, `110`, and `250` m, so FCFS places B
at the leftmost immediate start `110` m. C waits until minute 1000, giving
900 vessel-minutes of total waiting. For A at `400` m, the FCFS continuation
places B at `0` m and C at `260` m when A departs at minute 100. Its total
waiting is 0, so Rollout chooses A at `400` m. The strict improvement follows
from a completed FCFS continuation, not independent future-vessel estimates.

## Metrics And Records

The runner validates complete schedules with the Step 5 validator. Failed
and invalid runs have null headline KPIs. A vessel with one placement is not
unresolved merely because that placement conflicts; it is marked failed and
its raw outcome is retained. Missing or ambiguous placements are unresolved.

`metric_version = static_metrics_v1_type7` and
`percentile_method = type7_linear`. P95 sorts values, uses rank
`(n - 1) * 0.95`, and linearly interpolates. Utilization is
`occupied_quay_length_minutes / (berth_length_m * utilization_window_min)`.
The window runs from scenario minute 0 to the last service completion.
Clearance and waiting are not occupied hull area. Utilization above one plus
`NUMERICAL_TOLERANCE` raises an error; floating-point noise just above one
snaps to one. Algorithm runtime uses `perf_counter()` around policy execution
only.

The manifest retains Step 2 names `scenario_seed`, `scenario_split`,
`data_provenance`, and `project_version`. The run summary uses `seed` and the
canonical `simulation_end_time_min`, set to the last service completion for a
successful static run. Its utilization components are stored alongside the
derived ratio. `StaticDecisionRecord.record_schema_version = 1`; its
`decision_index` is an offline construction index, not simulation time.

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

The manifest records scenario fingerprint, seed, formulation, provenance,
split, policy and algorithm versions, metric/percentile versions, UTC time,
package version, and local Git commit/dirty state where available. Decision
and placement rows carry `run_id` and `scenario_id`. JSONL is the local Step 6
record format; later warehouse exports may materialize Parquet.

MEDIUM and HEAVY presets are dynamic by default. Request a static twin to
preserve their vessel sampling while recording formulation `static`:

```bash
berth-allocation-lab --compare-baselines configs/scenarios/synthetic_low.yaml
berth-allocation-lab --compare-baselines configs/scenarios/synthetic_medium.yaml --static-twin
```

Single-seed smoke runs and the 20-seed-per-family dominance check are
implementation sanity checks, not scientific benchmark conclusions.
