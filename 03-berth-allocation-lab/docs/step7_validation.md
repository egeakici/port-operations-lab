# Step 7 Implementation And Measured Audit

Date: 2026-10-01. Scope: Step 7 only; no Step 8, RL, continuous mathematical
optimizer, new dependency, or upstream code modification. No commit was made.

## Preflight

The starting worktree was clean. Read the frozen problem/data contracts,
synthetic scenarios, continuous core, static baselines and Project 03 README,
and inspected their actual schema, geometry, candidate, earliest-start,
objective, policy, runner and recorder implementations.

Step 6 hardening is present: realizable Greedy Rollout, the shared FCFS
next-placement helper, unambiguous unresolved-vessel accounting, static guards,
utilization validation without silent clipping, canonical record fields and
the registered `slow` marker. No Step 6 rewrite was needed.

Pre-change baseline, from Project 03:

```text
python -m pytest -m "not slow"
114 passed, 3 deselected in 35.99s
```

The Step 2 roadmap traceability ends at 12, but this request uses a 13-step
roadmap. That discrepancy is reported, not silently edited.

## Files And API

Created under `03-berth-allocation-lab/`:

- `src/berth_allocation_lab/solvers/candidate_enumeration.py`
- `src/berth_allocation_lab/solvers/reference_types.py`
- `src/berth_allocation_lab/evaluation/comparison.py`
- `configs/scenarios/synthetic_tiny_congested.yaml`
- `scripts/run_candidate_reference_smoke.py`
- `tests/unit/test_candidate_enumeration.py`
- `tests/integration/test_candidate_reference.py`
- `docs/candidate_space_reference.md`
- `docs/step7_validation.md`

Modified: `README.md`, `src/berth_allocation_lab/cli.py`,
`src/berth_allocation_lab/solvers/__init__.py`,
`src/berth_allocation_lab/policies/base.py`,
`src/berth_allocation_lab/evaluation/runner.py`,
`src/berth_allocation_lab/tracking/records.py`, and
`src/berth_allocation_lab/tracking/recorder.py`.

Public API: `StaticCandidateEnumeration(config).solve(scenario)` returns
placements, decisions and typed diagnostics. Its `schedule` adapter works with
`run_static_policy`. `CandidateEnumerationConfig` defaults to 6 vessels and
250000 nodes, optionally up to 8 vessels and a cooperative time cutoff.
`compare_to_candidate_reference` supplies fingerprint-checked certified gaps.

[Reference semantics](candidate_space_reference.md) documents the fixed order,
node-local candidate regeneration, core earliest starts, immutable DFS,
strict accumulated-waiting pruning, tolerance-aware first-leaf ties, validated
FCFS upper-bound initialization, objective recomputation, statuses and artifacts.
No unrestricted continuous optimum is claimed.

## Reproducible Experiments

Executed from Project 03:

```text
python scripts/run_candidate_reference_smoke.py --output experiments/step7_smoke_20261001_verified
```

The script evaluated 12 distinct scenarios and recorded 36 method runs using
identical scenario objects for FCFS, Rollout and reference. All references
were certified; all obeyed `Exact <= Rollout <= FCFS` within `1e-9`.
Zero FCFS waiting occurred in **1/12** cases overall, **1/9** generated cases,
and **0/5** generated cases of size 6-8. These are small correctness checks,
not a statistical performance study.

Every size/seed has a new scenario identity and fingerprint. No vessel-list
slicing is used. Runtime includes initial FCFS, DFS, final validation and
decision replay. These are measurements from this machine/run, not promises;
the slow regression suite was also running during this verified smoke run.

| Scenario | FCFS waiting | Rollout waiting | Reference waiting | Nodes | Solver seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Manual 2 | 7.500000 | 7.500000 | 7.500000 | 7 | 0.001152 |
| Manual 3 | 900.000000 | 0.000000 | 0.000000 | 13 | 0.001543 |
| Manual 4 | 109.000000 | 109.000000 | 109.000000 | 57 | 0.003495 |
| Generated 2, seed 42 | 0.000000 | 0.000000 | 0.000000 | 4 | 0.000478 |
| Generated 3, seed 42 | 357.669450 | 282.313763 | 282.313763 | 27 | 0.001686 |
| Generated 4, seed 42 | 707.593895 | 632.238208 | 632.238208 | 105 | 0.009158 |
| Generated 5, seed 42 | 1362.429525 | 1058.218151 | 1058.218151 | 431 | 0.057590 |
| Generated 6, seed 42 | 1989.496004 | 1612.784630 | 1612.784630 | 1535 | 0.271234 |
| Generated 7, seed 42 | 2870.127735 | 2337.060674 | 2337.060674 | 9938 | 1.964391 |
| Generated 8, seed 42 | 3793.821169 | 3297.398421 | 3188.254108 | 43194 | 9.978448 |
| Generated 6, seed 0 | 2243.460298 | 2243.460298 | 2243.460298 | 271 | 0.061613 |
| Generated 6, seed 1 | 2037.001375 | 1639.471168 | 1639.471168 | 1994 | 0.240999 |

Waiting is total vessel-minutes. Manual 3 and generated 2 stop with
`zero_cost_certificate`; all others stop with `exhausted`. All have
`optimality_status=optimal` and run status `completed`.

### Manual Cases

Manual 2: Q=500, clearance=20, simultaneous A(length 240, service 7.5) and
B(length 260, service 12). They cannot coexist because of clearance. B waits
7.5 minutes in the fixed order. All methods have mean waiting 3.75, P95 waiting
7.125 and mean turnaround 13.5; all absolute gaps are zero.

Manual 3 is the Step 6 geometry documented in the reference note. FCFS versus
Rollout/reference has mean waiting 300 versus 0, P95 waiting 810 versus 0,
and mean turnaround 700 versus 400. FCFS's absolute candidate-space gap is
900; its relative gap is undefined because the optimum is zero.

Manual 4: Q=500, clearance=10, A(0,300,100), B(0,300,100), C(1,180,10),
D(2,180,20), where triples denote arrival, length and service. Service starts
are 0,100,1,11, showing nonchronological physical starts in fixed construction
order. All methods have mean waiting 27.25, P95 waiting 86.35 and mean turnaround
84.75; all absolute gaps are zero.

### Eight-Vessel Congestion

| Metric | FCFS | Rollout | Candidate reference |
| --- | ---: | ---: | ---: |
| Total waiting | 3793.821169 | 3297.398421 | 3188.254108 |
| Mean waiting | 474.227646 | 412.174803 | 398.531763 |
| P95 waiting | 908.621838 | 856.518313 | 806.772347 |
| Mean turnaround | 804.665146 | 742.612303 | 728.969263 |
| Absolute candidate-space gap | 605.567061 | 109.144313 | 0 |
| Algorithm runtime (s) | 0.003001 | 0.086117 | 9.978485 |

The reference explored 43194 nodes, pruned 34181 branches and evaluated 228
complete leaves. It strictly improved on Rollout here; this is not a claim
that such an improvement occurs for every instance.

Other sizes also illustrate that equal total waiting need not imply equal
P95 waiting, since only total waiting is optimized and tie trajectories differ.

### Artifacts And Complexity

The full local [measured report](../experiments/step7_smoke_20261001_verified/report.md)
includes total/mean/P95 waiting, mean turnaround, absolute gaps and runtimes
for every method/scenario, plus pruned counts, complete leaf counts, statuses,
termination reasons, fingerprints and run IDs. The accompanying
[summary JSON](../experiments/step7_smoke_20261001_verified/summary.json) links each row
to its raw run directory. These runtime artifacts remain Git-ignored.
The script and this compact audit are versionable reproduction materials.

Post-run checks reloaded all 36 scenarios from disk and matched their
fingerprints to manifests and summaries. All 9 saved generator configurations
reproduced those same fingerprints. An initial smoke run in
`experiments/step7_smoke_20261001` is superseded, not overwritten: its manual
fixtures used integer-valued physical fields whose JSON reload changed their
representation to floats. The existing schema's fingerprint is sensitive to
that representation. The final manual fixtures use canonical float fields and
explicit `scenario_version=2`, `generator_version=step7_manual_v2`; a regression
test protects their JSON round-trip. Callers constructing scenarios manually
should likewise supply the declared float fields as floats. No historical
scenario data or global schema fingerprint algorithm was rewritten.

In the seed-42 6/7/8 series, nodes grow 1535 -> 9938 -> 43194. FCFS evaluates
one construction path; Rollout repeatedly completes future FCFS suffixes;
enumeration explores a combinatorial tree. Pruning and early zero certificates
make counts strongly instance-dependent. Do not extrapolate production runtime
from these small observations.

## Verification

Python 3.13.2, pytest 9.1.1, Windows. No installation or dependency change was
needed. Commands below ran from the specified project directory.

| Directory | Command | Actual result |
| --- | --- | --- |
| Project 03 | `python -m pytest` (latest complete run) | 158 passed in 275.71s, including all 3 slow checks |
| Project 03 | `python -m pytest tests/unit/test_candidate_enumeration.py tests/integration/test_candidate_reference.py -q` | 42 passed in 3.59s |
| Project 03 | `python -m pytest -m "not slow"` (final focused run) | 156 passed, 3 deselected in 7.48s |
| Project 01 | `python -m pytest tests/test_berth.py` | 14 passed |
| Project 02 | `python -m pytest tests/test_scenario.py tests/test_berth_policy.py tests/test_vessel_arrivals.py` | 18 passed |
| Repository | `git diff --check` | clean; only local LF/CRLF conversion warnings |

The final fingerprint regression test was added after collection of the latest
full run; it passed in both final focused runs. Thus the final tree has 159
tests: 156 fast checks plus the 3 unchanged slow checks that passed in the full
run. The earlier full run also passed (156 tests at that point).

The registered slow tests cover 20 seeds each for LOW, MEDIUM and HEAVY
Rollout dominance. Step 7 tests additionally cover independent unpruned
enumeration (1-5 vessels), branch-specific candidates, fractional inputs,
clearance boundaries, ties and mutation, nonchronological starts, objective
recomputation errors, invalid bounds, size limits, controlled-clock deadlines,
node cutoffs with/without incumbents, certified-only gaps, CLI, artifact
round-trips and clearing certification on validation/serialization failure.

CLI smoke executed successfully:

```text
python -m berth_allocation_lab.cli --run-candidate-reference configs/scenarios/synthetic_tiny_congested.yaml --output experiments/step7_cli_smoke
optimal / exhausted; 1535 nodes; certified objective 1612.784630
```

Step 8 is ready to use this restricted reference for validation, provided its
decision representation remains identical. No environment implementation was
started. Review and roadmap reconciliation remain separate from this step.
