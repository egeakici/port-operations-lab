# Dynamic Maskable PPO (Step 11 Part A)

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
value coefficient 0.5, maximum gradient norm 0.5 and CPU. These were fixed
from Step 9 before Step 11 results. Only training rewards are multiplied by
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
