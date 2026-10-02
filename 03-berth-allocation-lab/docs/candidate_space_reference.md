# Candidate-Space Reference

Step 7 implements `static_candidate_enumeration_v1`. It minimizes total vessel
waiting exactly within the frozen candidate model, subject to the shared
absolute numerical tolerance (`1e-9`). It is not an unrestricted continuous BAP
optimizer, a production-scale scheduler, or an online simulation policy.

## Search Model

All inputs are known. Construction order is `(arrival_time_min, vessel_id)`.
At each DFS node, `candidate_starts` regenerates sorted Step 5 candidates
against that node's immutable partial schedule. For each position it calls
the canonical `earliest_feasible_start`. No metre grid, independent start-time
choice, vessel resequencing or intentional WAIT is introduced.

The search branches over every candidate. A later construction decision can
have an earlier physical service start: construction order is not chronology.
At every evaluated complete leaf, the core validator checks completeness and
physical constraints, and `total_waiting_time` must agree with incremental
waiting. The selected path is also replayed against its own candidate lists
and earliest starts to produce reconstructible offline decision records.

For a partial schedule, accumulated waiting is a lower bound because future
waiting is non-negative. The only pruning condition is strictly:

```text
accumulated_waiting > incumbent_value + NUMERICAL_TOLERANCE
```

There is no independent-future-vessel bound. The optional initial FCFS
(default) or Rollout schedule is validated for feasibility and candidate-model
membership, and supplies only an upper-bound value. Disabling initialization
does not affect correctness. `enable_pruning=False` and `stop_at_zero=False`
support full-tree auditing against the independent test enumerator.

## Determinism And Certificates

Ascending candidates and canonical vessel ordering define deterministic DFS.
The returned certified trajectory is the first DFS leaf within tolerance of
the minimum, not the initial heuristic schedule. Record-low leaves still within
tolerance are retained so successive tiny improvements cannot discard the
first eligible tie. This is not a globally lexicographic optimum claim.

Exhaustion of the unpruned tree proves candidate-space optimality. A DFS leaf
with exactly zero canonical waiting also proves optimality immediately because
zero is a global lower bound on this objective. A zero-cost heuristic alone
does not shortcut DFS or select the certified trajectory.

Heuristic fallback is returned only when a resource cutoff occurs before a
DFS leaf reaches the bound within tolerance. Such a fallback is `feasible`,
even if its waiting is zero. Every invocation has independent local search
state. Placements, decisions and counters repeat deterministically unless a
wall-clock cutoff intervenes; runtime itself need not repeat.

## API And Limits

```python
from berth_allocation_lab.solvers import (
    CandidateEnumerationConfig,
    StaticCandidateEnumeration,
)
from berth_allocation_lab.evaluation import run_static_policy

solver = StaticCandidateEnumeration(CandidateEnumerationConfig(
    max_vessels=6,
    max_search_nodes=250_000,
    time_limit_seconds=None,
    initial_incumbent="fcfs",
))
reference = solver.solve(scenario)
print(reference.diagnostics.certified_optimal_objective)
run = run_static_policy(scenario, solver, "experiments/runs")
```

`solve` returns `CandidateEnumerationResult(best_placements, decision_records,
diagnostics)`. `schedule` adapts that result to the existing `StaticPolicy`
interface without retaining mutable last-result state.

Default maximum size is 6; callers may explicitly raise it to 7 or 8. Larger
configuration limits are rejected. Exceeding the configured scenario size
returns `size_limit`, with no search or truncation. Node budget is always a
finite positive integer. Nodes include the root, visited partial/complete
nodes and nodes immediately pruned; unentered cutoff children are not counted.
`complete_schedules_evaluated` excludes pruned complete nodes.

An optional finite positive deadline uses monotonic `perf_counter`. It is
cooperative, checked before initialization and at each node. A single core
operation or initial heuristic can overrun it; it is not process preemption.
Runtime includes heuristic initialization, search, final validation and replay,
but not artifact I/O. The runner additionally measures adapter overhead.

## Scientific Records

The frozen Step 2 names are preserved:

```text
policy_id = static_candidate_enumeration_v1
policy_family = reference_solver
algorithm_version = v1
solver_family = exhaustive_enumeration
solver_version = v1
reference_scope = candidate_space
```

| Outcome | optimality_status | Run status | failure_type | Certified objective |
| --- | --- | --- | --- | --- |
| Exhausted or zero-cost proof | optimal | completed | null | populated |
| Node/time cutoff with valid incumbent | feasible | completed_with_limit | null | null |
| Time cutoff, no incumbent | timeout | failed | `search_limit_reached` | null |
| Node cutoff, no incumbent | failed | failed | `search_limit_reached` | null |
| Oversized input (`size_limit`) | failed | failed | `size_limit_exceeded` | null |
| Genuine error | failed | failed | exception class | null |

Termination reasons are `exhausted`, `zero_cost_certificate`, `node_limit`,
`time_limit`, `size_limit`. An instance above `max_vessels` (no search, no
truncation) and a node/time stop before any valid incumbent are recorded
limit outcomes, not exceptions: the runner records them without raising,
keeps `termination_reason`, sets summary `validation_status` to
`size_limit_exceeded` or `search_limit_reached`, and reports no feasible or
certified objective and no headline KPIs. An exception has null termination
reason and explicit
`failure_type`/`failure_message` (the exception class and message), rather
than a fabricated cutoff, so a limit is never confused with a programming
error. Invalid configuration/dynamic input raises at the public boundary.

`solver_diagnostics.json` (record schema 1) stores scenario fingerprint,
optimality status, best feasible and certified objectives, node/prune/leaf
counters, solver runtime, termination reason, all configuration limits and
switches, incumbent source, solver identity and errors. `optimality_gap` is
zero for a certified self-reference and null otherwise; no solver gap or
lower-bound estimate is fabricated after interruption.

The shared recorder still writes manifest, scenario, placements, vessels,
decisions, violations and run summary, with Git metadata and scenario seed.
Solver metadata is also visible in manifest and summary. Baselines retain
their existing behavior and have null optional reference fields.

For a feasible cutoff, placements and completed vessel outcomes remain useful
raw data. `is_valid=True` means physical validity, not optimality. The summary
uses `valid_uncertified`, leaves headline objective/waiting/turnaround/utilization
KPIs null, and stores the named `best_feasible_objective`. Derived incumbent
KPIs are separate in `incumbent_metrics.json` (schema 1); this artifact has null
metrics for certified/failed runs. Consumers must require `completed` and
`optimal` when selecting a certified reference. Validation/serialization
failure clears certification in the persisted scientific records.

## Comparisons And Worked Example

`evaluation.comparison.compare_to_candidate_reference(heuristic, reference)`
checks scenario fingerprints and successful records before computing a
**candidate-space reference gap**. The numeric helper
`candidate_space_reference_gap(objective, diagnostics)` requires an optimal
candidate-space certificate; its caller is responsible for pairing instances.

Absolute gap is `heuristic - reference`. Relative gap divides by a positive
reference. With a zero reference, a zero gap is 0 and a positive gap has null
relative gap, never infinity or an epsilon denominator. Differences within
the central tolerance snap to zero; meaningfully beating the reference raises.

For the Step 6 fixture, Q=500 m, clearance=10 m:

```text
A: arrival=0, length=100, service=100
B: arrival=0, length=250, service=1000
C: arrival=100, length=200, service=100
```

FCFS puts A at 0 and B at 110, so C waits 900 minutes. DFS can retain A at
0, put B at 250, then C at 0 at minute 100, giving zero waiting. Rollout's
different zero-cost trajectory starts A at 400. The reference returns its
first zero-cost DFS leaf, not Rollout's tie. The FCFS absolute gap is 900;
its relative gap is undefined. `Exact <= Rollout <= FCFS` applies only when
all methods use these same frozen decisions and the reference is certified.

The future unrestricted continuous optimizer may choose arbitrary real-valued
positions and more general times/order. This solver does not establish that
optimum. Step 8 can compare trajectories against this reference only while
preserving the same order, candidates, earliest-start rule and objective.

## Reproduction

```bash
berth-allocation-lab --run-candidate-reference configs/scenarios/synthetic_tiny_congested.yaml
berth-allocation-lab --run-candidate-reference path/to/tiny_static.json --max-vessels 8 --max-search-nodes 250000
python scripts/run_candidate_reference_smoke.py --output experiments/step7_smoke_NEW
```

The committed tiny config has its own identity: static, 600 m quay, 60 minute
mean interarrival, 6 vessels. Other physical distributions match LOW. The smoke
script creates distinct identified configs for sizes 2-8 at seed 42 and size 6
at seeds 0 and 1; it never relabels a slice of a larger instance. It records
all 36 method runs, generated configs, summary JSON, and a detailed metric
report. Existing output roots are never overwritten.

See [Step 7 measured audit](step7_validation.md) for actual measurements and
commands. These are controlled synthetic correctness checks, not broad
statistical or real-terminal performance claims. Step 8 and RL are not added.

Roadmap discrepancy retained for separate review: the Step 2 traceability
table ends at Step 12, while the current instruction describes 13 steps.
