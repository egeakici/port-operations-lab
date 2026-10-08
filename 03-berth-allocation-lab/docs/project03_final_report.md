# Project 03 - Berth Allocation Lab

## 1. Purpose

Project 03 studies berth-allocation decisions under controlled, reproducible
synthetic traffic. This is a frozen research baseline, not a terminal deployment.
The authoritative evidence is the completed Step 9, 11 and 12 artifacts; the
Step 13 SQLite database, CSVs and figures are derived, independently verifiable
views of those records.

## 2. Problem formulation

Vessels require a contiguous segment of a continuous quay for their service
interval. Feasibility enforces quay bounds, nonoverlap in space and time, and
`min_clearance_m`. The primary reported objective is total vessel waiting
time in vessel-minutes (lower is better). Candidate positions discretize
decisions without changing the physical quay geometry.

## 3. Static and Dynamic BAP

Static BAP schedules a known vessel set with full information. Dynamic BAP
decides online at events, observing waiting vessels, current berth occupancy
and announced arrivals within H=240 minutes. Its WAIT action is legal only
from visible information. Static and Dynamic physical suites and information
contracts differ: their raw waiting values must not be ranked against each
other. Validation selected checkpoints; every number below is held-out test
unless explicitly labeled otherwise.

## 4. Methods

FCFS assigns in arrival order. Static Greedy Rollout and Dynamic Online
Rollout use feasible lookahead; Dynamic Rollout is a causal heuristic, **not**
an optimum. Tiny Static candidate-space Exact is exact only for its fixed
order, finite candidate set, **not** the unrestricted continuous global BAP.
Static and Dynamic Maskable PPO use legal-action masks. The frozen `v2_rule_1`
selected Static tiny v1 and medium/heavy v2 on validation; the frozen Dynamic
rule selected its checkpoints before test evaluation. Step 13 did not reselect.

## 5. Experiment design

Synthetic train, validation, held-out test and diagnostic suites have distinct
roles. Physical scenario seeds are not PPO training seeds. PPO was trained
with seeds 11, 23 and 37. Scenario-first three-seed mean is an aggregate,
not a fourth trained policy. Static tiny and Dynamic tiny each use 150 test
scenarios; medium/heavy each use 100. Family-weighted aggregates are reported
below. Paired comparisons use the same physical scenarios per method.

## 6. Static results

Weighted mean total waiting, vessel-minutes (lower is better):

| Regime/version | FCFS | Rollout | PPO three-seed mean | Candidate-space Exact | Frozen selection |
| --- | ---: | ---: | ---: | ---: | --- |
| Tiny v1 | 2971.19 | 2715.97 | 2860.27 | 2658.69 | selected |
| Tiny v2 | 2971.19 | 2715.97 | 2958.02 | 2658.69 | not selected |
| Medium/heavy v1 | 1306.28 | 908.97 | 1529.22 | unavailable | not selected |
| Medium/heavy v2 | 1306.28 | 908.97 | 1322.09 | unavailable | selected |

Tiny v1 beat FCFS but not Rollout; medium/heavy v2 remained slightly worse
than FCFS. No combined Static champion is claimed. Source table:
`static_summary.csv` in the final release `tables/` directory.

## 7. Dynamic results

H=240, held-out weighted mean total waiting, vessel-minutes:

| Regime | FCFS | PPO three-seed mean | Online Rollout | PPO improvement vs FCFS | PPO above Rollout | FCFS-to-Rollout gap closed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Tiny | 2841.05 | 2585.00 | 2382.62 | 256.05 | 202.38 | 55.85% |
| Medium/heavy | 1610.71 | 1488.64 | 1142.49 | 122.07 | 346.15 | 26.07% |

The paired scenario-bootstrap 95% PPO-minus-FCFS intervals are
[-331.10, -182.85] (tiny) and [-203.07, -45.91] (medium/heavy).
These are conditional on the three frozen models and do not measure
training-seed uncertainty or external validity. The gap-closure ratios
reconcile to 0.55852968518 and 0.26071203406. Source tables:
`dynamic_summary.csv` and `bootstrap_intervals.csv`.

## 8. Three-seed stability

| Regime | Seed 11 PPO | Seed 23 PPO | Seed 37 PPO | Gap closure by seed 11 / 23 / 37 |
| --- | ---: | ---: | ---: | --- |
| Tiny | 2588.02 | 2626.32 | 2540.66 | 55.19% / 46.84% / 65.52% |
| Medium/heavy | 1501.67 | 1518.71 | 1445.53 | 23.29% / 19.65% / 35.28% |

Seed variation is visible, especially in policy behavior. Three seeds do
not justify a strong estimate of training-seed uncertainty. The complete
values are in `dynamic_by_seed.csv`.

## 9. WAIT and policy behavior

PPO used intentional WAIT, with counts varying by family and seed. In tiny
n8 the seed-11/23/37 counts were 7/45/19; in heavy they were 13/0/53.
Online FCFS selected no intentional WAIT. Same-state FCFS assignment
agreement in medium was 97.4%/97.5%/7.5% for seeds 11/23/37. These
are descriptive diagnostics; the causal contribution of WAIT, announcement
visibility or any specific action was not identified. Automatic forced
advances are not policy WAIT. Source table: `wait_diagnostics.csv`;
same-state comparisons are preserved in the Step 12B source artifacts.

## 10. Tail risk and failure cases

Improvements in averages coexist with deterioration on individual scenarios.
Heavy seed 23, `dynamic_heavy_test_seed6000005`, had PPO 4432.41 versus
FCFS 2564.00 (+1868.41 vessel-minutes). Heavy seed 37,
`dynamic_heavy_test_seed6000317`, had PPO 7379.37 versus Rollout 4576.07
(+2803.30). Heavy seed 11 scenario-total P95 was 6195.44 FCFS, 4487.37
Rollout and 5392.80 PPO. These examples are outcomes, not explanations of
network reasoning. Source table: `tail_risk.csv`; selected action traces
remain in the Step 12B primary diagnostics.

## 11. Decision-time cost

The bounded validation-fixture CPU timing benchmark measured mean decision
times (ms): tiny FCFS 0.013, PPO 7.384, Rollout 38.111; medium/heavy FCFS
0.012, PPO 16.667, Rollout 44.709. Its per-method median, P95, maximum,
fixture and decision counts are in `latency_summary.csv`. It used one warmup
and three timed passes, with checkpoint loading excluded. This is neither a
production SLA nor a CUDA training-speed measurement. CPU/CUDA action parity
was not tested.

## 12. What the evidence demonstrates

On frozen, held-out synthetic traffic, Dynamic PPO reduced total waiting
against Online FCFS in both tested regimes, while Online Rollout retained
better schedule quality. The three-seed PPO aggregate closed only part of
the FCFS-to-Rollout gap. The immutable source chain and paired scenario
design make these statements auditable.

## 13. What the evidence does not demonstrate

Traffic is synthetic and uncalibrated to a real terminal. No H=0-trained
control isolates information value. No causal WAIT effect was estimated.
Online Rollout is not an optimum; candidate-space Exact does not establish
unrestricted continuous optimality. Three training seeds leave training
uncertainty wide. CPU/CUDA action-by-action parity is unknown. Berth-only
waiting-time changes establish neither whole-terminal productivity nor
commercial ROI.

## 14. Integrated terminal implications

Berth assignments will eventually interact with crane availability, yard
congestion and landside flow. Project 03 contains none of those constraints;
their integration is a distinct future research protocol, not a conclusion
about guaranteed improvement from this study.

## 15. Reproduction and provenance

Run each command from `03-berth-allocation-lab` in PowerShell:

```powershell
python scripts/build_project03_results.py --dry-run
python scripts/build_project03_results.py --build
python scripts/verify_project03_release.py
```

`--build` creates a release exclusively and cannot overwrite it. For an
existing release, run `--verify` or the standalone verifier. The SQLite
query catalog is `docs/project03_results_queries.md`. The final release at
`experiments/results/project03/project03_final_v1/` includes hashed
`manifest.json`, `project03_results.sqlite`, the CSV and figure files, and
provenance/backup inventory. Frozen Step 12A/B sources remain authoritative.
Experiments are Git-ignored: Git alone is not a scientific backup.

Optional external backup, after verification (replace the path with your
external drive):

```powershell
python scripts/create_project03_backup.py --output "D:\\project03_final_v1.zip"
```

## 16. Final status

Project 03 is complete for the current frozen synthetic Berth Allocation
research scope. It is not production-ready, commercially validated,
real-terminal optimized or globally optimal. Future experiments must have
new identities and protocols outside this frozen baseline.
