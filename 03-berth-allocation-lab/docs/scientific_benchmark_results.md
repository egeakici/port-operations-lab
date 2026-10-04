# Step 12B: Scientific BAP Findings

## Scope and provenance

This is a post-hoc descriptive analysis of frozen synthetic Step 9 and Step 11
held-out results. It does not train, reselect or infer on test scenarios. The
starting HEAD was `d0cff5575c6e5702b134b3e9e07776bfc9b51692`, with a clean
worktree. The completed Step 12A benchmarks `static_locked_v1` and
`dynamic_h240_locked_v1` passed source and derived SHA-256 verification.
Their manifest hashes, full source paths and derived hashes are in the Step 12B
`source_references.json` and `manifest.json` files. Dynamic primary results
use H=240 and CPU-held-out inference from CUDA-trained checkpoints 11/23/37.
Static and Dynamic have different physical suites and information contracts;
their raw waiting values cannot be ranked against each other.

## Frozen benchmark findings

Weighted mean total waiting is in raw vessel-minutes, lower is better:

| Branch and regime | FCFS | Rollout | PPO seed mean | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Static tiny v1 | 2971.19 | 2715.97 | 2860.27 | Below FCFS; above Rollout |
| Static tiny v2 | 2971.19 | 2715.97 | 2958.02 | Near FCFS; above Rollout |
| Static medium/heavy v1 | 1306.28 | 908.97 | 1529.22 | Worse than both |
| Static medium/heavy v2 | 1306.28 | 908.97 | 1322.09 | Near, but above FCFS; above Rollout |
| Dynamic tiny | 2841.05 | 2382.62 | 2585.00 | Below FCFS; above Rollout |
| Dynamic medium/heavy | 1610.71 | 1142.49 | 1488.64 | Below FCFS; above Rollout |

The frozen static `v2_rule_1` selects tiny v1 and medium/heavy v2; this
document does not reselect them. Tiny candidate-space Exact is exact only
within the fixed-order finite candidate space, not unrestricted continuous
BAP. Static source rows lack placement and vessel traces: scenario waiting
distributions and paired differences are available, detailed action behavior
is not. Dynamic `dynamic_rule_1` R1 passed in validation for both regimes;
its R2 values are validation descriptors, not the test results below.

On dynamic held-out tests, PPO seed-mean improvement over FCFS was 256.05
vessel-minutes in tiny and 122.07 in medium/heavy. Gap closure relative to
the FCFS-to-Online-Rollout gap was 0.55853 and 0.26071. By seed 11/23/37,
the tiny closures were 0.55194/0.46840/0.65524; medium/heavy were
0.23288/0.19648/0.35278. PPO remained slower in schedule quality than
Online Rollout by 202.38 and 346.15 vessel-minutes respectively. Online
Rollout is a causal heuristic, not a theoretical optimum. Paired bootstrap
95% intervals for seed-mean PPO minus FCFS were [-331.10, -182.85] (tiny,
150 independent scenarios) and [-203.07, -45.91] (medium/heavy, 100).
Intervals reflect scenario sampling conditional on three frozen models,
not training-seed uncertainty or real-terminal generalization.

## Decision behavior and WAIT

The original evaluator compared PPO assignment actions with Online FCFS
at the **same PPO-encountered state**, including the encoded vessel and
candidate position. It did not compare independently evolving action indices.
Complete schedule equality additionally checks vessel order, berth position
and berth-start time; equal objective alone does not imply equal schedules.
The full per-family, per-seed agreement, order and position counts are in
`dynamic_action_agreement.csv`.

| Family | PPO intentional WAITs, seeds 11/23/37 | PPO same-state FCFS assignment agreement, seeds 11/23/37 |
| --- | ---: | ---: |
| tiny n6 | 5 / 11 / 0 | 51.3% / 27.0% / 62.3% |
| tiny n7 | 14 / 18 / 5 | 37.7% / 19.1% / 49.7% |
| tiny n8 | 7 / 45 / 19 | 36.0% / 16.8% / 35.5% |
| medium | 0 / 0 / 5 | 97.4% / 97.5% / 7.5% |
| heavy | 13 / 0 / 53 | 82.3% / 84.7% / 7.4% |

The large medium/heavy seed-37 disagreement is a genuine observed
cross-seed behavior difference, not evidence that a different seed should be
chosen on test results. Online FCFS selected no intentional WAIT. Legal WAIT
opportunities, WAIT-bearing episodes, ANNOUNCED-visible decisions and
waiting cost accumulated after WAIT are in `dynamic_wait_summary.csv`.
`forced_advances` are separate automatic environment transitions and are not
counted as policy WAIT. ANNOUNCED visibility is derived from frozen arrivals,
H=240 and the recorded decision prefix; the full per-decision mask was not
stored. Choosing WAIT is not random, so associations with good or bad
outcomes do not estimate WAIT's causal effect.

## Tail risk and selected traces

`dynamic_tail_risk.csv` reports scenario-total mean/median/P95/max separately
from individual-vessel waiting P95/max, for each family and seed. For example,
heavy seed 11 has scenario-total P95 of 6195.44 (FCFS), 4487.37 (Rollout)
and 5392.80 (PPO) vessel-minutes. The seed-11 heavy PPO-minus-FCFS
paired P95 is +320.87 and maximum is +1832.41. These are descriptive tails,
not a new optimization criterion. The full paired rows are in
`dynamic_scenario_differences.csv`; `dynamic_worst_cases.csv` deterministically
ranks the five largest deteriorations and improvements per regime, reference
and seed. A positive PPO-minus-reference delta is worse; ties use 1e-6
vessel-minutes.

Five deterministic source-grounded examples are saved in
`dynamic_selected_traces.json`:

- Best FCFS improvement: heavy seed 37, `dynamic_heavy_test_seed6000137`,
  PPO 4088.34 vs FCFS 7281.27 (-3192.94). At t=0 both selected V001,
  but PPO chose berth position 865.65 m versus FCFS 0 m; V002 was announced.
- Severe FCFS deterioration: heavy seed 23, `dynamic_heavy_test_seed6000005`,
  PPO 4432.41 vs FCFS 2564.00 (+1868.41). At t=592.93, V007/V008 were
  waiting; PPO selected V008 while FCFS selected V007 at the same state.
- Severe Rollout deterioration: heavy seed 37,
  `dynamic_heavy_test_seed6000317`, PPO 7379.37 vs Rollout 4576.07
  (+2803.30). At t=0 PPO placed V001 at 869.47 m; V002/V003/V004 were
  announced. This is not proof that announcement information caused the choice.
- Intentional WAIT: tiny n8 seed 23, `dynamic_tiny_n8_test_seed6000461`,
  PPO 6633.97 vs FCFS 4934.71 (+1699.27). At t=11.14 V002 was waiting
  and V003-V008 were announced. FCFS's action at that exact point cannot be
  cited because its earlier trajectory had diverged.
- FCFS-like schedule: medium seed 11, `dynamic_medium_test_seed6000023`,
  both total 313.69. At t=0 both selected V001 at 0 m; schedule equality
  is checked separately from cost equality.

The trace snapshot reconstructs only legally visible statuses from frozen
arrival inputs and already recorded assignment prefixes. The full set of
legal alternatives at each historical decision was not recorded and is
explicitly unavailable. These examples describe actions and later placements;
they do not reveal a neural network's internal reason for acting.

## Decision-time computation

The bounded timing protocol used the first two lexicographically sorted
**validation** scenarios per each of five families (10 fixtures), chosen
before timing. Each of Online FCFS, Online Rollout and PPO seed 11 ran one
warmup pass and three timed passes on the same Windows 11 machine, Python
3.13.2, NumPy 2.2.3, PyTorch 2.6.0+cpu, SB3/sb3-contrib 2.8.0, one Torch
thread and BLAS/OMP settings of one thread. PPO checkpoint loading was
excluded from steady-state decision time. The selected fixtures, hardware,
per-decision samples, environment-step time and episode wall time are stored
under `cpu_latency_v2`. All timed actions were legal and schedules valid.

| Regime | Method | Mean / median / P95 / max decision time, ms | Decisions |
| --- | --- | ---: | ---: |
| Tiny | FCFS | 0.013 / 0.013 / 0.019 / 0.077 | 126 |
| Tiny | Rollout | 38.111 / 24.388 / 140.142 / 260.287 | 129 |
| Tiny | PPO | 7.384 / 6.012 / 13.909 / 54.486 | 126 |
| Medium/heavy | FCFS | 0.012 / 0.011 / 0.020 / 0.140 | 240 |
| Medium/heavy | Rollout | 44.709 / 21.003 / 179.991 / 490.324 | 258 |
| Medium/heavy | PPO | 16.667 / 13.272 / 32.048 / 131.008 | 243 |

Rollout timing includes its actual visible-continuation computation, not a
lookup. Decision counts differ because policies choose different trajectories.
This is an engineering measurement on ten fixtures, not a production SLA.
Training runtime is separate; CUDA training does not imply faster CPU
inference. CPU/CUDA action parity was not tested.

## Limits and next step

H=240 permits ANNOUNCED-vessel information, but improvement over FCFS does
not establish that the model used that information. No H=0-trained control
exists, and no new horizon/counterfactual campaign was run. Results use
uncalibrated synthetic traffic and BAP-only behavior; they imply neither
real-terminal throughput gains nor commercial savings. The completed Step 12
records are suitable inputs for Step 13's results warehouse and presentation
layer, provided these provenance, missing-trace and external-validity limits
remain visible. New experiments require a separately declared protocol and
user approval; none were started here.

## Reproduction

From `03-berth-allocation-lab`, PowerShell commands are:

```powershell
python scripts/run_scientific_diagnostics.py --dry-run
python scripts/run_scientific_diagnostics.py --diagnostics
python scripts/run_scientific_diagnostics.py --latency
```

The completed output directories are `experiments/benchmark/step12b/locked_diagnostics_v3`
and `experiments/benchmark/step12b/cpu_latency_v2`. They are immutable;
re-running with the same ID intentionally fails. Use a fresh `--diagnostic-id`
for a new measurement. Earlier bounded development outputs `locked_diagnostics_v1`,
`locked_diagnostics_v2`, `cpu_latency_smoke_v1` and `cpu_latency_v1` remain
preserved and are not the primary Step 12B results. `experiments/` is ignored
by Git and needs separate backup.
