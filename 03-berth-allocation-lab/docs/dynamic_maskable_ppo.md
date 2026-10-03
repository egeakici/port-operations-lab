# Dynamic Maskable PPO (Step 11)

This document was written before the Step 11 extended runs. Part A implements
and pilots the method; Part B alone may evaluate held-out test suites. The
dynamic problem is online: unlike StaticBAP, the agent knows only arrived
vessels and arrivals announced within horizon `H`. `ANNOUNCED` vessels cannot
be assigned; `WAITING` vessels can. The environment remains
`dynamic_bap_env_v1` / `dynamic_obs_v1`.

## Model and objective

The Dict observation has `current_time`, `horizon`, `terminal_features`,
`vessel_features`, `visible_mask`, `status_features`, `placement_features`,
`candidate_features` and `action_mask`. For capacity `M`, there are
`1 + 2*M*M` actions: index zero is WAIT, all others encode vessel slot and
candidate position. M=8 has 129 actions; M=24 has 1153. A masked action is
never selected. WAIT availability follows the Step 10 visible-event rule.

`dynamic_joint_action_scoring_v1` shares a 64-dimensional vessel encoder and
128-dimensional pooled global context, scores each vessel-candidate pair with
the same two-layer 128-wide MLP, and has a separate WAIT head that includes
pooled ANNOUNCED vessel embeddings. The critic pools legal assignment
embeddings. Network parameter count does not depend on `M`. Neither hidden
vessel rows nor scenario IDs enter the policy. Absolute `current_time` remains
in the observation but is deliberately excluded from the network, a
time-translation-invariance hypothesis. This could discard useful
time-of-day arrival patterns; no architecture search occurs in Part A.
Step 9's pooled static scorer became FCFS-like, so announcement use and WAIT
decisions are explicit diagnostics here.

MaskablePPO uses gamma 1.0, learning rate 3e-4, 256 steps per environment,
batch 256, 10 epochs, GAE lambda 0.95, clip 0.2, entropy coefficient 0.01,
value coefficient 0.5 and maximum gradient norm 0.5. These were fixed
from Step 9 before Step 11 results. The existing configs default to CPU;
CUDA is an optional execution device and does not change these settings.
The run manifest and checkpoint record the requested and actual device.
If `cuda` is requested but PyTorch cannot see a CUDA device, training fails
before creating a run directory. Only training rewards are multiplied by
1/1440. The raw event-driven reward remains `-queue_length * delta_time`,
and a valid complete episode has raw return equal to negative total waiting
minutes. `DummyVecEnv` has independent seeds per sub-environment: 1 for debug,
4 for smoke/pilot, 8 for extended. No VecNormalize is used. Gymnasium
truncation remains separate from termination; SB3 bootstraps truncated
episodes, so truncated episodes are not treated as complete scientific costs.

## Suites and references

The three training seeds are 11, 23, 37, distinct from generator seeds.
Generator partition is seed modulo 3: train 0, validation 1, test 2. Dynamic
validation starts in the 5M seed region, test in 6M and diagnostics in 7M.
Physical fingerprints are audited against Step 7 fixtures, Step 9 pilot,
extended v1/v2 suites and Step 10 smoke. The tiny 6/7/8-vessel static preset
is converted outside the environment to dynamic H=240 with clean IDs;
medium/heavy use their existing dynamic presets. The extended validation
sizes are 20 per family and test sizes 50 per family. No Part A test
evaluation is authorized.

Online FCFS is the primary engineering reference. Online Rollout evaluates
all legal actions, including WAIT, on an immutable visible-only snapshot:
in-service completions, waiting vessels and announced arrivals. It never
reads hidden arrivals or horizon-entry timestamps. It simulates visible
events and shared quay geometry, then completes with FCFS. For an initial
WAIT, the next visible decision gets one best legal assignment lookahead
before FCFS continuation; this makes the corrected A/B fixture choose WAIT
(20 minutes versus 90). This is the addendum's hand-worked requirement and
is more than literal FCFS continuation after the first candidate. Ties use
action index. The real environment may stop at a newly visible hidden-vessel
horizon entry while executing WAIT; that is causal because time advanced.
Reference cache keys include physical fingerprint, H and policy version.
No static Rollout or offline Exact result is treated as an online competitor.

On local cost fixtures, Online Rollout took about 0.05 s per tiny/medium
scenario and 0.42 s for heavy; these are engineering costs, not performance
results. Validation references are computed once and reused by matching key.

## Checkpoints and records

At timestep zero and every evaluation event, select the checkpoint with the
lowest raw weighted mean total waiting on the frozen validation suite;
ties keep the earliest. Save both best-validation and final checkpoints with
model metadata and full run manifest. Training reward never selects a model.
Each run records configuration, provenance, split identities, audit,
validation history, episodes, losses, WAIT counts, throughput and runtime.
Three-seed means, paired differences and percentages are descriptive; a
zero reference waiting time makes percentage improvement undefined.

## Dynamic Rule 1

Pre-registered **before extended runs**, applied separately per H=240 regime
to all three best-validation checkpoints:

- R1, useful learning: three-seed mean PPO total waiting is lower than online
  FCFS **and** at least two of three seeds are lower than FCFS.
- R2, horizon-aware competitiveness, descriptive: per-seed and mean fraction
  of FCFS-to-Online-Rollout gap closed is `(FCFS - PPO) / (FCFS - Rollout)`.
  It is undefined when `FCFS <= Rollout`.

Close or mixed outcomes are inconclusive, not significance claims. Rule
outcome does **not** determine permission to test. Before Part B testing,
all extended runs must complete, their best checkpoints and audits must
exist, the decision must be written once with its SHA-256 sidecar, and the
worktree must be clean. The dynamic evaluation script refuses test and
diagnostic suites unless that gate passes. H=240-trained at H=0 is only a
cross-horizon diagnostic; a controlled information comparison requires a
separately trained H=0 policy. H=0 campaign configs are prepared but not run.
The same decision rule can be recorded separately for two H=0 regimes; H=0
and H=240 runs must never be mixed in one decision record.
For the B diagnostic only, `evaluate_dynamic_ppo.py --cross-horizon-h0`
loads an H=240 checkpoint and evaluates the same physical suite at H=0;
the output labels both horizons. This is not the controlled A-vs-C contrast.

## Commands

From Project 03, after `pip install -e ".[rl,dev]"`:

```powershell
python scripts/measure_dynamic_rollout.py
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_smoke.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny.yaml --training-seed 23 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny.yaml --training-seed 37 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy.yaml --training-seed 23 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy.yaml --training-seed 37 --progress
```

Extended commands are prepared, **not run** in Part A:

```powershell
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny_extended.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny_extended.yaml --training-seed 23 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny_extended.yaml --training-seed 37 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy_extended.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy_extended.yaml --training-seed 23 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy_extended.yaml --training-seed 37 --progress
```

The extended configs request 300,000 tiny / 500,000 medium-heavy transitions
per seed. Pilot results and campaign runtime estimates appear below only after
bounded runs actually finish. No final held-out test result belongs in Part A.

On a machine with a CUDA-enabled PyTorch installation, select the separate
CUDA configs instead of editing the CPU campaign files. They inherit the
same hyperparameters and scenario suites but use distinct experiment IDs,
config hashes and output directories:

```powershell
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny_extended_cuda.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy_extended_cuda.yaml --training-seed 11 --progress
```

Use the same config with seeds 23 and 37 for the rest of each campaign.
CPU and CUDA training can yield different trajectories despite matching
seeds, so compare their recorded runs rather than treating them as identical.

The separate H=0 controls are prepared, not run; use the same three training
seeds after scheduling their compute budget:

```powershell
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny_h0_extended.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny_h0_extended.yaml --training-seed 23 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_tiny_h0_extended.yaml --training-seed 37 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy_h0_extended.yaml --training-seed 11 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy_h0_extended.yaml --training-seed 23 --progress
python scripts/train_dynamic_ppo.py --config configs/rl/dynamic_ppo_medium_heavy_h0_extended.yaml --training-seed 37 --progress
```

## Pilot Results

Written after the bounded runs on 2026-10-03. These are validation-only
engineering pilots, not the extended decision and not held-out results.
All three tiny runs completed 10,240 transitions; their selected checkpoints
were at 5,120, 10,240 and 5,120 transitions respectively. The same 60
validation scenarios gave FCFS 2,831.0 and Online Rollout 2,293.3 mean
total-waiting minutes. Paired replay had 60/60 valid schedules per method
and seed, with no truncations.

| Tiny seed | PPO min | PPO-FCFS min | PPO-Rollout min | PPO WAITs / legal WAIT decisions | Learning steps/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 11 | 2,540.2 | -290.8 | +247.0 | 0 / 305 | 132.1 |
| 23 | 2,568.1 | -262.9 | +274.8 | 6 / 303 | 122.7 |
| 37 | 2,556.8 | -274.2 | +263.5 | 0 / 310 | 134.8 |

The pilot three-seed mean is 2,555.1 minutes. All seeds beat FCFS on this
validation suite, but none reaches Online Rollout. Only one of three selected
policies deliberately waited, so this short run does not establish useful
announcement/horizon reasoning. The validation curves drop sharply from
their untrained values then flatten near 2,540-2,570 minutes. The plot is
`reports/figures/dynamic_tiny_pilot_learning.png`; per-run manifests and
raw paired decision/event/vessel records are under `experiments/rl/dynamic_pilot/`.

Medium/heavy pilot: **pending**. An interrupted seed-11 cost probe advanced
to about 3,000 of 20,480 requested transitions but produced no complete
manifest and is not a result. The first 1,024-transition optimization cycle
took about 60-70 seconds with M=24, implying roughly 18-22 minutes per
20,480-transition seed and roughly one hour for all three. A 500,000-step
extended seed may require roughly 8-10 hours at that rate, versus about
40-50 minutes for a 300,000-step tiny seed at the observed 120-135 learning
steps/s. These are rough local estimates, not promises; resource scheduling
should be decided before the medium/heavy pilot is resumed. No H=0 training
or held-out test evaluation occurred.

## Extended CUDA Campaign And Part B Results

Written after the six extended training runs and all held-out evaluations
on 2026-10-03. The Part A protocol and Dynamic Rule 1 above were not
changed. All runs used clean Git commit
`1b71b5d428f11a3d8aa2fa018839bb9199b0c37a`. The committed CUDA
configs inherit the frozen extended configs and change only experiment/output
identity and `ppo.device`; this engineering deviation preceded the runs.
All six manifests report actual CUDA training and contain selected/final
checkpoints with metadata. Tiny completed 301,056 transitions per seed and
medium/heavy 501,760. CUDA training is not necessarily bitwise reproducible.
Statements above about pending runs describe the earlier Part A state.

The exclusive, validation-only decision is
`experiments/rl/dynamic_extended_cuda/validation_decision.json`, with
`.sha256` sidecar and digest
`f2f912346e4a9260bf7752874fa1343fea63e0b7f2594f8083bf05c60c3e3423`.
It records `uses_test_results=false`, `source_git_dirty_at_decision=false`
and `final_testing_permitted=true`. The test gate was verified before
each held-out suite. Copied from the JSON without changing the rule:
Displayed numbers are rounded; the immutable JSON contains full precision.

| Regime | Selected steps, seeds 11/23/37 | Validation PPO by seed (min) | FCFS / Rollout (min) | R1 | R2 by seed; mean |
| --- | --- | --- | --- | --- | --- |
| Tiny | 301056 / 301056 / 290816 | 2443.782860 / 2513.362980 / 2448.356261 | 2831.020346 / 2293.301351 | true, 3/3 wins | 0.720148 / 0.590750 / 0.711643; 0.674180 |
| Medium/heavy | 260096 / 100352 / 380928 | 1456.088383 / 1540.200154 / 1425.941864 | 1662.913847 / 1196.485499 | true, 3/3 wins | 0.443424 / 0.263092 / 0.508057; 0.404858 |

Three-seed validation means are 2468.50 and 1474.08 minutes. Full and
post-initial zoomed plots with each seed, the mean, FCFS/Rollout lines and
a second WAIT panel are at
`experiments/rl/dynamic_extended_cuda/*_validation_learning_wait*.png`.
At step zero tiny scored 5293.87/8543.64/8330.96 and medium/heavy
18014.53/69897.97/69036.47; these are untrained policies. Tiny dropped
near 2550-2590 by its first evaluation, then improved modestly late.
Medium/heavy first evaluations were 1609.79/1702.51/1706.31.
Above 1.25 times its selected score after the first evaluation,
medium/heavy seed 11 spiked to 2255.60 at step 321536 with 234 WAITs
(229 heavy). Heavy scenarios 5000089, 5000047 and 5000113 increased
7341.5, 6918.2 and 4441.6 minutes over that seed's selected checkpoint.
Seed 23 spiked to 3870.46 at step 280576 with 126 WAITs (122 heavy),
driven by heavy 5000089 (+65464.3) and 5000032 (+24805.7); it also
reached 2122.00 at step 440320 with 68 WAITs (62 heavy). Tiny had no
post-initial spike above that threshold. All validation schedules remained
valid and untruncated. Spike/WAIT co-occurrence is not causal proof.

Validation assignment agreement with FCFS measures the same vessel and
position at the encountered state. Identical schedules also require
matching vessel start times. Selected-checkpoint diagnostics:

| Family | Seed | Agreement | Identical schedules | FCFS-equal cost | WAIT selected/legal; with ANNOUNCED |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tiny (60) | 11 | 39.76% | 1 | 5 | 16/337; 15 |
| Tiny (60) | 23 | 26.43% | 0 | 4 | 27/345; 27 |
| Tiny (60) | 37 | 53.81% | 2 | 6 | 9/338; 9 |
| Medium (20) | 11 | 97.50% | 13 | 18 | 0/299; 0 |
| Heavy (20) | 11 | 80.42% | 1 | 1 | 8/483; 8 |
| Medium (20) | 23 | 97.50% | 13 | 18 | 0/299; 0 |
| Heavy (20) | 23 | 80.83% | 1 | 2 | 0/474; 0 |
| Medium (20) | 37 | 6.25% | 0 | 15 | 0/299; 0 |
| Heavy (20) | 37 | 9.79% | 0 | 0 | 20/494; 20 |

Among validation scenarios with a PPO WAIT, PPO-versus-FCFS better/worse
counts were tiny 2/3, 7/4, 3/2 and medium/heavy 3/1, none, 4/0
for seeds 11/23/37. This selected subset is not a causal WAIT estimate.
Equal cost does not imply identical schedules.

### Held-Out H=240 Test

The frozen test suites have 150 tiny (50 each of 6/7/8 vessels) and 100
medium/heavy (50 each family) physical instances. Each selected checkpoint
was evaluated once on CPU. FCFS/Rollout were computed once per
physical-fingerprint/H/policy-version key and reused across seeds. All 2250
raw rows under `experiments/rl/dynamic_extended_cuda/evaluations/test_h240/`
are valid: zero truncations, mask violations or independently checked
physical-schedule violations.

Means below are scenario total-waiting minutes. Deltas are PPO minus the
reference; percentages are improvement over FCFS. W/E/L counts compare
PPO against the named reference on identical physical instances.

| Family | Seed | FCFS | Rollout | PPO | PPO-FCFS; improvement | PPO vs FCFS W/E/L | PPO-Rollout; improvement | PPO vs Rollout W/E/L |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tiny (150) | 11 | 2841.05 | 2382.62 | 2588.02 | -253.03; 8.91% | 108/9/33 | +205.40; -8.62% | 31/13/106 |
| Tiny (150) | 23 | 2841.05 | 2382.62 | 2626.32 | -214.73; 7.56% | 110/6/34 | +243.70; -10.23% | 30/14/106 |
| Tiny (150) | 37 | 2841.05 | 2382.62 | 2540.66 | -300.38; 10.57% | 114/14/22 | +158.05; -6.63% | 37/22/91 |
| Medium (50) | 11 | 433.85 | 327.57 | 430.06 | -3.79; 0.87% | 7/42/1 | +102.49; -31.29% | 0/21/29 |
| Medium (50) | 23 | 433.85 | 327.57 | 430.06 | -3.79; 0.87% | 7/42/1 | +102.49; -31.29% | 0/21/29 |
| Medium (50) | 37 | 433.85 | 327.57 | 433.46 | -0.39; 0.09% | 12/33/5 | +105.89; -32.33% | 2/20/28 |
| Heavy (50) | 11 | 2787.57 | 1957.40 | 2573.28 | -214.29; 7.69% | 27/10/13 | +615.88; -31.46% | 4/4/42 |
| Heavy (50) | 23 | 2787.57 | 1957.40 | 2607.37 | -180.20; 6.46% | 28/11/11 | +649.97; -33.21% | 4/4/42 |
| Heavy (50) | 37 | 2787.57 | 1957.40 | 2457.60 | -329.97; 11.84% | 29/7/14 | +500.20; -25.55% | 5/3/42 |

Tiny 6/7/8-vessel PPO means for seeds 11/23/37 were
1778.77/1796.41/1739.96, 2405.76/2432.03/2364.99 and
3579.52/3650.50/3517.04. Their FCFS means were
1877.72/2642.01/4003.41 and Rollout means
1611.21/2222.12/3314.52. Medium/heavy aggregate means weight
the two families equally, not individual vessels equally.

The three-seed **test** mean and sample SD are 2585.00 +/- 42.91 tiny
and 1488.64 +/- 38.29 medium/heavy. Test FCFS is 2841.05/1610.71;
Rollout is 2382.62/1142.49. Descriptive test R1 analogues are true
(3/3 seeds below FCFS), and R2 analogues are 0.55853 and 0.26071.
These did not select checkpoints or alter the validation decision.
Rollout remains better; medium/heavy's FCFS gain is concentrated in
heavy traffic.

| Regime | Seed | Vessel mean/P95 waiting | Vessel mean/P95 turnaround | PPO WAIT selected/legal; announced | CPU PPO inference, suite total (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tiny | 11 | 369.72/1187.44 | 712.69/1621.74 | 26/813; 26 | 3.682 |
| Tiny | 23 | 375.19/1175.66 | 718.16/1622.16 | 74/875; 74 | 2.635 |
| Tiny | 37 | 362.95/1148.13 | 705.93/1554.44 | 24/846; 24 | 2.485 |
| Medium/heavy | 11 | 75.08/374.45 | 413.81/764.63 | 13/1955; 13 | 10.237 |
| Medium/heavy | 23 | 75.94/384.28 | 414.66/770.55 | 0/1942; 0 | 11.286 |
| Medium/heavy | 37 | 72.28/366.37 | 411.00/746.75 | 58/2000; 58 | 24.834 |

For the test references, vessel mean/P95 waiting and mean/P95
turnaround (minutes) are FCFS tiny
405.86/1214.66 and 748.84/1579.86, Rollout tiny
340.37/1120.27 and 683.35/1505.43, FCFS medium/heavy
80.54/400.37 and 419.26/762.91, and Rollout medium/heavy
57.12/302.50 and 395.85/679.56. FCFS selected zero WAITs;
Rollout selected 81/921 legal tiny and 126/2064 legal
medium/heavy WAITs.

| Medium/heavy test family | Seed | PPO vessel mean/P95 waiting (min) | PPO vessel mean/P95 turnaround (min) |
| --- | ---: | ---: | ---: |
| Medium | 11 | 26.88/185.75 | 365.00/560.74 |
| Medium | 23 | 26.88/185.75 | 365.00/560.74 |
| Medium | 37 | 27.09/185.04 | 365.22/560.74 |
| Heavy | 11 | 107.22/495.52 | 446.35/920.66 |
| Heavy | 23 | 108.64/482.05 | 447.77/876.96 |
| Heavy | 37 | 102.40/465.58 | 441.53/887.60 |

The matching reference family KPIs are: medium FCFS waiting
27.12/185.75 and turnaround 365.24/566.70; medium Rollout
20.47/149.11 and 358.60/522.01; heavy FCFS 116.15/502.85 and
455.28/842.14; heavy Rollout 81.56/392.98 and 420.69/755.58.

FCFS inference totals on these suites are about 0.0006 s tiny and
0.0008 s medium/heavy; Rollout totals are 19.413 and 32.899 s.
These are host-specific timings, not controlled hardware comparisons.
The evaluation process set `torch.set_num_threads(1)`; timings are
stored per raw row and shared reference timings were not remeasured
for every seed.
PPO WAIT affected 16/36/11 tiny scenarios, with PPO-vs-FCFS W/E/L
11/0/5, 23/0/13, 6/0/5; medium/heavy affected 5/0/17 scenarios,
with 4/0/1, none, 9/0/8. All test WAITs occurred with an ANNOUNCED
vessel visible. Subset outcomes do not measure WAIT's causal effect.

### Selection And Separate Diagnostics

| Regime | Seed | Selected validation | Held-out test | Test minus validation (min) |
| --- | ---: | ---: | ---: | ---: |
| Tiny | 11 | 2443.78 | 2588.02 | +144.23 |
| Tiny | 23 | 2513.36 | 2626.32 | +112.95 |
| Tiny | 37 | 2448.36 | 2540.66 | +92.31 |
| Medium/heavy | 11 | 1456.09 | 1501.67 | +45.58 |
| Medium/heavy | 23 | 1540.20 | 1518.71 | -21.49 |
| Medium/heavy | 37 | 1425.94 | 1445.53 | +19.59 |

The tiny three-seed mean rises from 2468.50 validation to 2585.00
test. Medium/heavy rises from 1474.08 to 1488.64, while its FCFS
reference changes from 1662.91 to 1610.71. Descriptive gap closure
falls from 0.67418 to 0.55853 tiny and 0.40486 to 0.26071
medium/heavy. Different physical suites have different difficulty;
raw differences are not by themselves pure overfitting estimates.

The separate density-diagnostic suites have 30 tiny and 20
medium/heavy instances (10 each family). FCFS/Rollout means are
2973.24/2432.15 and 1776.84/1263.57. PPO seed 11/23/37 means are
2705.79/2719.18/2615.03 tiny and 1590.85/1601.33/1581.44
medium/heavy. Three-seed means and sample SDs are
2680.00 +/- 56.66 and 1591.21 +/- 9.95. Raw rows are under
`evaluations/density_h240/`; these are not additional test samples.

Cross-horizon condition B reuses the **same test physical instances**
with H=240-trained checkpoints at H=0. FCFS schedule and total cost
were identical at H=0 and H=240 in all 150 tiny and 100
medium/heavy instances. H=0 FCFS/Rollout means were
2841.05/2487.05 and 1610.71/1443.92. PPO seed 11/23/37 means were
2617.98/2593.79/2560.86 tiny and 1524.64/1518.01/1513.08
medium/heavy; three-seed means and sample SDs were
2590.88 +/- 28.67 and 1518.58 +/- 5.80. No PPO WAIT was selected
at H=0. Raw rows are under `evaluations/test_cross_h0/`.
Condition C (separately H=0-trained policies) has not run; these
figures cannot establish the causal value of a 240-minute horizon.

Physical fingerprints from 125,693 distinct tiny and 73,183 distinct
medium/heavy training episodes had zero overlap with validation, test
or density-diagnostic sets. The latter three were pairwise disjoint
within each regime. H=0 deliberately reuses test instances. The
suite audit also checked nine historical fixtures and 502 previously
examined instances. All 18 evaluation files have a clean test gate;
their 4950 raw rows have zero invalid/truncated episodes and zero
independent physical-schedule violations. These are not 4950
independent scenarios because references and H=0 instances are reused.

CPU/CUDA inference action parity remains **unverified**. A small-subset
check was attempted, but this host reports
`torch.cuda.is_available() == False` and has no `nvidia-smi`.
CUDA training manifests do not prove equal CPU/CUDA inference actions;
absence of a comparison must not be called agreement. Synthetic-only
traffic, only three training seeds, no online Exact optimum and no
H=0-trained control remain limitations. No retraining, Step 12
implementation or commit occurred in Part B.
