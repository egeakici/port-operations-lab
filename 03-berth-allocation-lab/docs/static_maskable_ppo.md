# Static Maskable PPO

Step 9 trains and evaluates a reinforcement-learning policy for the frozen
static candidate-space formulation (`static_maskable_ppo_v1`). The learned
model is a small numerical neural network trained with Proximal Policy
Optimization from sb3-contrib; it is not a language model, does not call any
external AI service, and is not an exact solver.

## What Is Learned

At each decision of `StaticBAPEnv` the policy `pi_theta(a | o)` maps the Step 8
Dict observation to a probability distribution over candidate indices. The
environment is unchanged: vessels come in `(arrival_time_min, vessel_id)`
order, Step 5 generates the candidates, the core fixes the earliest feasible
start, and the reward is `-W_k`. The policy only chooses which canonical
candidate position to use. There is no WAIT, resequencing, continuous position
output, priority bonus or information horizon.

**Maskable PPO** is PPO whose categorical action distribution assigns zero
probability to masked actions. The candidate count changes with the partial
schedule, so most of the fixed `2 * max_vessels` indices are invalid in a given
state. Masking keeps the agent from wasting experience on impossible actions
and keeps every sampled action physically meaningful. Masks are active during
rollout collection (`learn(use_masking=True)`), validation, test evaluation and
every inference call (`model.predict(obs, action_masks=env.action_masks(),
deterministic=True)`). A masked or malformed prediction raises
`MaskedActionError`; there is no fallback to FCFS or any other policy, and the
environment still rejects masked actions itself.

**MultiInputPolicy** is required because the observation is a `spaces.Dict`.
SB3's default `CombinedExtractor` flattens each Box/MultiBinary key and one-hot
encodes `current_vessel_index` (Discrete), then concatenates them for separate
policy and value MLPs (`net_arch: {pi: [128, 128], vf: [128, 128]}`, tanh,
default SB3 initialization). No custom network, attention or recurrence is used.

## Objective Alignment

`gamma = 1.0` is the required primary setting. The undiscounted return is
`sum_k r_k = -J` with `J` the total vessel waiting, so with `gamma = 1` the
return PPO maximizes is the frozen objective. This does not make PPO exact: it
still relies on a learned value function, GAE (`gae_lambda = 0.95`, kept
separate from gamma), clipping and sampled gradients. A config with
`gamma < 1` is rejected unless it sets `ppo.alternative_training_objective:
true`; such runs are a different objective and are not Step 9 v1 results.

**Training-only reward scale.** HEAVY episodes return several thousand
negative minutes. `TrainingRewardScale` multiplies each reward by a fixed
positive constant (`reward_scale = 1/1440`) for the PPO learner only. With
`gamma = 1` a constant positive factor preserves the ordering of complete
episode returns and the optimal policy set; it changes numerical dynamics
(value-loss magnitude, effective entropy weight), not the objective. There is
no per-episode normalization and no `VecNormalize`. The raw reward is kept in
the step `info`, `StaticBAPEnv` itself is untouched, and validation, checkpoint
selection, testing and all baselines use unwrapped environments and raw
vessel-minutes. The scale is recorded in the training manifest and checkpoint
metadata.

## Seeds, Splits And Scenario Identity

**Training seed** (for example `11`) seeds PyTorch, NumPy, policy
initialization, action sampling and the environment RNG through
`MaskablePPO(seed=...)`. That RNG produces a stream of **scenario generation
seeds**. Both are recorded: the training seed in the manifest, every episode's
scenario seed, family, split and fingerprints in `train_episodes.csv`.

Splits use the Step 8 partition (`seed % 3`: train `0`, validation `1`, test
`2`), so train/validation/test instances can never share a generation seed.
Explicit evaluation seed lists must follow it (validation `1, 4, 7, ...`, test
`2, 5, 8, ...`). Traffic family and split are independent: every family has
its own train, validation and test instances.

**Historical fixtures.** The Step 7 tiny congested reference fixtures
(`n = 2..8` with seed 42, and `n = 6` with seeds 0 and 1) were inspected
during development. All tiny components set `excluded_seeds: [0, 1, 42]`, so
these seeds are never sampled for training or selected for validation. A
second, independent guard recomputes the fixtures' *physical fingerprints*
(quay, clearance and vessel inputs, independent of ID and split) and fails the
run on any match. These fixtures remain engineering regression cases, never
held-out evidence.

**Mixtures.** `MixtureScenarioProvider` combines same-split components with
explicit weights. The component for seed `s` is a pure function of `s // 3`
(`sha256` based, documented in the Step 8 environment note); the chosen
component generates the instance with its own family and parameters. IDs are
`{base_scenario_id}_{split}_seed{s}`, for example `bap_tiny_n7_train_seed123`,
`bap_medium_validation_seed1`, `bap_heavy_test_seed8`.

**Leakage audit.** Before training, the validation and test suites are
checked; after training, every training episode is checked against them. The
audit fails on an identity inconsistent with its split/seed, one scenario ID
with two contents, a physical instance or family seed shared by two splits, or
a historical fixture. Evaluation repeats the audit over all training episodes
and evaluated suites. A leaking training run is recorded with
`status = failed`, `failure_type = split_leakage`.

## Training Regimes

| | Regime A: tiny congested | Regime B: MEDIUM/HEAVY |
| --- | --- | --- |
| Config | `configs/rl/static_ppo_tiny.yaml` | `configs/rl/static_ppo_medium_heavy.yaml` |
| Components | tiny congested 6, 7, 8 vessels (600 m quay), weights 1:1:1 | static twins of MEDIUM (16 vessels) and HEAVY (24 vessels), 1200 m quay, weights 0.5:0.5 |
| `max_vessels` / actions | 8 / 16 | 24 / 48 |
| Validation suite | 6 per component (18) | 6 per component (12) |
| Test suite | 10 per component (30) | 10 per component (20) |
| Diagnostics (test seeds, reported separately) | LOW (10) | LOW (10), cross-family tiny 6/7/8 (4 each) |
| Exact reference | yes (certified cases only) | only on tiny diagnostic instances |

MEDIUM and HEAVY presets are dynamic; their components declare
`static_twin: true` explicitly. Each regime has its own model because capacity
(and thus observation/action shapes) differs; a checkpoint is always evaluated
with the capacity it was trained with. LOW is never a training distribution:
it is a separately reported low-congestion diagnostic. The tiny model cannot be
evaluated on MEDIUM/HEAVY (capacity 8 < 16), so it has no cross-family suite.

`configs/rl/static_ppo_smoke.yaml` is a pipeline smoke (2048 timesteps,
smaller network) and never performance evidence.

## Hyperparameters

| Parameter | Value |
| --- | --- |
| algorithm / policy | MaskablePPO / MultiInputPolicy |
| gamma | 1.0 |
| learning_rate | 3e-4 (constant) |
| n_steps / batch_size / n_epochs | 512 / 128 / 5 |
| gae_lambda / clip_range | 0.95 / 0.2 |
| ent_coef / vf_coef / max_grad_norm | 0.01 / 0.5 / 0.5 |
| net_arch | pi [128, 128], vf [128, 128] |
| environments | 1 (single process, `DummyVecEnv`) |
| device | cpu |
| reward_scale (training only) | 1/1440 |

These are initial engineering choices, not tuned values. No hyperparameter
search was run, and test results must never be used to change them.

## Budgets And Runtime

Measured on this machine (Windows 11, 12 logical CPUs, CPU-only torch 2.6):
the raw environment runs about 3200 random masked steps/s on tiny and about
800 on MEDIUM/HEAVY instances; MaskablePPO learning runs about 870 and 340
timesteps/s respectively. Importing Stable-Baselines3 takes about 7-20 s in
this environment because a global TensorFlow installation is pulled in through
TensorBoard; RL modules import SB3 lazily so other Project 03 modules do not
pay this cost.

| Workload | Budget | Purpose |
| --- | --- | --- |
| Integration smoke | 2,048 timesteps (tests: 512) | rollouts, updates, save/load |
| Multi-seed pilot | 10,000 timesteps x 3 seeds | full reproducible workflow |
| Extended | config default 100,000 timesteps x 3 seeds | learning study |

At the measured rates the extended budget is roughly 2-3 min per tiny seed
and 5-7 min per MEDIUM/HEAVY seed plus validation time; it is documented, not
launched automatically.

## Checkpoint Selection

Frozen before testing: the selected checkpoint has the lowest mean total
waiting (raw minutes) over the fixed validation suite, evaluated with
deterministic masked inference at timestep 0, every `eval_freq` timesteps
(at rollout boundaries, after the preceding update) and after the final
update. Ties within `1e-9` keep the earliest timestep; an evaluation with any
invalid schedule is never selected. Training reward is never used for
selection, and `select_checkpoint` refuses non-validation inputs. If the
untrained policy is never beaten, timestep 0 is selected and reported as such.

## Artifacts

```text
experiments/rl/static_ppo/<experiment_id>/seed_<training_seed>/
    config.yaml                  resolved config + recorded overrides
    manifest.json                training run record (status, seeds, splits,
                                 hyperparameters, budgets, runtimes, Git,
                                 dependency versions, hardware, selection)
    final_model.zip (+ .metadata.json)
    best_validation_model.zip (+ .metadata.json)
    training_log.csv             per update: raw episode return/waiting,
                                 policy/value/entropy loss, approx KL,
                                 clip fraction, explained variance
    train_episodes.csv           every training episode's scenario identity
    validation_metrics.json      every validation evaluation, per scenario
```

The metadata sidecar records policy/model IDs, environment, observation,
reward and candidate-generator versions, capacity, scales, reward scale,
architecture, gamma, training seed, Git state and dependency versions.
`MaskablePPOStaticPolicy.load` rejects a checkpoint whose policy ID,
observation/environment versions, capacity, action space, observation space,
scales or SB3/sb3-contrib major versions do not match the environment. An
existing run or evaluation directory is never overwritten. Status values:
`completed`; `failed` with `nonfinite_loss`, `split_leakage`,
`no_valid_validation_checkpoint` or an exception class; `interrupted` (saved
as `interrupted_model.zip`, never declared final). Model files are Git-ignored
under `experiments/`.

## Paired Evaluation

`scripts/evaluate_static_ppo.py` loads completed runs only (the config must
be byte-identical to the training config, and the rebuilt default test suite
must match the identities recorded at training time). For every scenario of
every suite, generated once, it runs FCFS, Greedy Rollout, the candidate-space
Exact reference (instances with at most 8 vessels) and each training seed's
checkpoint through the shared `run_static_policy`, which validates schedules
and computes canonical KPIs. Outputs: `per_instance.jsonl`/`.csv` (all KPIs,
runtimes, validity, paired deltas, exact fields), `aggregate.json`,
`evaluation_manifest.json` and `report.md`.

- `delta_vs_fcfs_min = J_PPO - J_FCFS` and `delta_vs_rollout_min = J_PPO -
  J_Rollout`; negative means PPO waits less. Deltas exist only when both
  schedules are valid.
- Exact gaps use the Step 7 helper and require `optimality_status = optimal`
  and `reference_scope = candidate_space`. Absolute gap `J - J*`; relative gap
  `(J - J*) / J*` only for `J* > 0`. With `J* = 0` and positive `J` the
  relative gap is null (counted as undefined), never an epsilon ratio. A
  node-limited reference contributes no certified gap.
- Aggregates report per suite and component: count, invalid count, mean,
  median and sample standard deviation of total waiting, mean deltas, certified
  count and mean gaps; plus each training seed's mean and the mean/standard
  deviation/min/max across seeds. Invalid rows are counted, never imputed.
- `algorithm_runtime_seconds` is inference/scheduling time per instance;
  training runtime is in the training manifest.

## Reproducing

```bash
# smoke (pipeline only)
python scripts/train_static_ppo.py --config configs/rl/static_ppo_smoke.yaml --progress

# multi-seed pilot (3 seeds x 10k timesteps per regime)
python scripts/train_static_ppo.py --config configs/rl/static_ppo_tiny.yaml \
    --total-timesteps 10000 --eval-freq 2000 --output-dir experiments/rl/pilot --progress
python scripts/train_static_ppo.py --config configs/rl/static_ppo_medium_heavy.yaml \
    --total-timesteps 10000 --eval-freq 2000 --output-dir experiments/rl/pilot --progress

# held-out paired evaluation (test suite + diagnostics), no retraining
python scripts/evaluate_static_ppo.py --config configs/rl/static_ppo_tiny.yaml \
    --experiment-dir experiments/rl/pilot/static_ppo_tiny_v1 \
    --output experiments/rl/pilot_evaluations/static_ppo_tiny_v1 --progress

# learning curves
python scripts/plot_static_ppo_learning.py \
    --experiment-dir experiments/rl/pilot/static_ppo_tiny_v1 --output tiny_curves.png

# extended experiment (config default budget, explicit launch)
python scripts/train_static_ppo.py --config configs/rl/static_ppo_tiny.yaml --progress
python scripts/train_static_ppo.py --config configs/rl/static_ppo_medium_heavy.yaml --progress
```

`--progress` defaults to off and uses plain `tqdm` (no rich renderer). New display
output is stderr-only; the scripts' existing summaries/reports stay on stdout.
Each training seed has a timestep bar labeled with the experiment/regime ID,
seed and its index among the requested seeds. The postfix shows learning steps/s
(elapsed learning time excluding validation), latest/best validation waiting
and FCFS/Rollout validation means, rounded to one decimal minute. Every existing
validation event also prints a permanent line, including timestep zero and the
final validation. Baseline setup shows scenario progress and cache hits.
Evaluation shows scenario counters for FCFS, Rollout, eligible Exact instances
and each PPO checkpoint, separately for every test/diagnostic suite.

The flag is display-only, never a saved override or manifest field. Scenario and
method execution order, RNG streams, checkpoint selection, and scientific
outputs are unchanged. Wall-clock timing measurements naturally vary, including
display overhead. Bars close on normal completion, exceptions and interrupts.
If PPO finishes a rollout past the requested budget, the bar stops at its
configured total; actual completed timesteps continue to be recorded as before.

## Measured Pilot (2026-10-01)

Executed: the multi-seed pilot above (training seeds 11, 23, 37; 10,240
timesteps each, `--eval-freq 2000`) for both regimes, followed by held-out
evaluation with the best-validation checkpoints. These are short-budget
pilots on small synthetic suites, not established performance. No extended
run was launched. The working tree was uncommitted Step 9 code
(`git_dirty = true` in every manifest).

Training ran a second time from scratch with the same seeds: validation
histories, training scenario streams and final policy weights were bitwise
identical for all six runs. Wall time per seed was 12.5-16.5 s (tiny) and
54-84 s (MEDIUM/HEAVY, of which 31-41 s is setup, mostly Greedy Rollout
validation baselines on 24-vessel instances); learning ran at about 800-890
(tiny) and 210-500 (MEDIUM/HEAVY) timesteps/s. Every evaluated schedule was
valid (472 rows, 0 invalid, no masked-action errors). Split audits found no
overlap.

Validation (selection) means, raw vessel-minutes:

| Regime | FCFS | Rollout | PPO seed 11 | seed 23 | seed 37 | selected at |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| tiny (18) | 3040.9 | 2677.8 | 3031.8 | 2937.8 | 3134.6 | 8192 / 8192 / 10240 |
| MEDIUM/HEAVY (12) | 1273.6 | 885.2 | 7769.2 | 10484.0 | 7855.3 | 10240 (all) |

Held-out test, mean total waiting (vessel-minutes):

| Suite | n | Exact (certified) | Rollout | FCFS | PPO 11 | PPO 23 | PPO 37 | PPO seeds mean +/- sd |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tiny test | 30 | 2655.4 (30/30) | 2699.1 | 3018.4 | 3017.0 | 3017.7 | 3142.9 | 3059.2 +/- 72.5 |
| MEDIUM/HEAVY test | 20 | - | 1363.6 | 1907.7 | 7737.4 | 10624.9 | 8336.2 | 8899.5 +/- 1523.9 |

- **Tiny, in distribution.** Mean paired delta vs FCFS: -1.4, -0.7 and
  +124.5 min; vs Rollout: +317.9 to +443.8 min. Mean certified gap 361.6-487.5
  min (relative 15-24 %), against Rollout's 43.7 min (1.7 %). Over 90
  PPO instance-runs: 27 better than FCFS, 33 equal, 30 worse; 2 better than
  Rollout, 16 equal; 16 reach the certified optimum. PPO roughly matches FCFS
  and stays far from Rollout at this budget.
- **MEDIUM/HEAVY, in distribution.** PPO is worse than FCFS on all 60
  instance-runs (mean delta +5830 to +8717 min). Validation waiting fell from
  13,500-16,100 min (untrained) to 7,800-10,500 min, and explained variance
  rose to about 0.9, so learning is under way but 10k timesteps (about 500
  episodes) is far from sufficient.
- **Diagnostics (separate).** LOW, tiny model: PPO 314-752 vs FCFS 38.2 and
  certified optimum 21.9; LOW, MEDIUM/HEAVY model: 279-607. Cross-family tiny,
  MEDIUM/HEAVY model: PPO 3552-3906 vs FCFS 3279, Rollout 3036, optimum 3020.
  Policies trained on congestion do not transfer to low traffic at this budget.
- **Inference time per instance.** PPO 0.008-0.031 s; FCFS 0.001-0.015 s;
  Rollout 0.02 s (tiny) and 2.6 s (24-vessel HEAVY); Exact about 1 s on tiny
  test instances.

## Extended v1 Campaign

Pre-registered on 2026-10-02, before any extended run. The pilot results
above stay as reported. The policy is unchanged (`static_maskable_ppo_v1`,
MultiInputPolicy, pi/vf [128, 128]); only budget, data collection and suite
sizes change.

| | Tiny | MEDIUM/HEAVY |
| --- | --- | --- |
| Config | `configs/rl/static_ppo_tiny_extended.yaml` | `configs/rl/static_ppo_medium_heavy_extended.yaml` |
| Experiment ID | `static_ppo_tiny_v1_extended` | `static_ppo_medium_heavy_v1_extended` |
| Components | as the tiny pilot | as the MEDIUM/HEAVY pilot |
| Budget / eval_freq | 300,000 / 10,000 timesteps | 500,000 / 20,000 timesteps |
| Validation | 20 per component (60) | 20 per component (40) |
| Test | 50 per component (150) | 50 per component (100) |
| Diagnostics | LOW 20 | LOW 20, cross-family tiny 10 per component (30) |

Shared settings, chosen a priori from Stable-Baselines3 PPO defaults and not
tuned on any result: gamma 1.0, learning rate 3e-4, 8 environments
(`DummyVecEnv`), 256 steps per environment (2048 per update), batch 256,
10 epochs, GAE lambda 0.95, clip 0.2, entropy 0.01, value coefficient 0.5,
gradient-norm limit 0.5, reward scale 1/1440, CPU, training seeds 11, 23, 37.
Sub-environment `i` uses seed `training_seed * 1000 + i` (recorded as
`environment_seeds`; single-environment runs keep the pilot derivation).

**Fresh suites.** The pilot validation, test and diagnostic instances were
examined. Extended suites therefore start at fresh seed blocks (validation
`1,000,000`, test `2,000,000`, diagnostics `3,000,000` / `3,500,000`, always
within the `seed % 3` partition), suites of one split share no generation
seed (`seed_exclusive_suites`), and training and evaluation fail if any
extended instance's physical fingerprint occurs in a suite of the pilot
configs (`prior_configs`). Baseline and exact references are computed once per
instance (validation baselines via a per-experiment cache shared by seeds,
evaluation references via a fingerprint cache).

**Decision rule (validation only).** For each seed, PPO is the mean
validation waiting of its best-validation checkpoint; FCFS and Greedy Rollout
are means on the same frozen validation suite (raw vessel-minutes).

- Tiny: v1 shows useful learning if, for at least 2 of 3 seeds,
  `(FCFS - PPO) / (FCFS - Rollout) >= 0.25`. If `FCFS - Rollout` is not
  positive the ratio is undefined and that seed does not pass.
- MEDIUM/HEAVY: v1 is competitive if, for at least 2 of 3 seeds,
  `PPO <= 1.10 * FCFS`.
- If either criterion fails, the documented conclusion is that the flat
  MultiInputPolicy architecture is the bottleneck, motivating a
  candidate-scoring v2. If both pass, v2 is optional.

The held-out test evaluation runs only after this decision is recorded, and
test results never change it. The decision is written once by
`scripts/record_validation_decision.py` to the Git-ignored
`experiments/rl/extended_v1/validation_decision.json` (exclusive creation,
rule version `static_ppo_v1_extended_validation_rule_v1`, with a `.sha256`
sidecar). It records the source commit, config hashes, selected checkpoint
IDs and file hashes and every rule input. Final testing is permitted once all
six runs have completed and the decision is recorded, whatever its outcome.
The evaluation script refuses test-split suites of these experiments unless
the decision file verifies (digest, permission, selected checkpoints).

Commands (Windows PowerShell, from `03-berth-allocation-lab`; each training
command refuses to start if its run directory exists):

```powershell
python scripts/train_static_ppo.py --config configs/rl/static_ppo_tiny_extended.yaml --training-seed 11 --progress
python scripts/train_static_ppo.py --config configs/rl/static_ppo_tiny_extended.yaml --training-seed 23 --progress
python scripts/train_static_ppo.py --config configs/rl/static_ppo_tiny_extended.yaml --training-seed 37 --progress
python scripts/train_static_ppo.py --config configs/rl/static_ppo_medium_heavy_extended.yaml --training-seed 11 --progress
python scripts/train_static_ppo.py --config configs/rl/static_ppo_medium_heavy_extended.yaml --training-seed 23 --progress
python scripts/train_static_ppo.py --config configs/rl/static_ppo_medium_heavy_extended.yaml --training-seed 37 --progress
python scripts/plot_static_ppo_learning.py --experiment-dir experiments/rl/extended_v1/static_ppo_tiny_v1_extended --output experiments/rl/extended_v1/curves_tiny.png
python scripts/plot_static_ppo_learning.py --experiment-dir experiments/rl/extended_v1/static_ppo_medium_heavy_v1_extended --output experiments/rl/extended_v1/curves_medium_heavy.png
python scripts/record_validation_decision.py --tiny-config configs/rl/static_ppo_tiny_extended.yaml --medium-heavy-config configs/rl/static_ppo_medium_heavy_extended.yaml --output experiments/rl/extended_v1/validation_decision.json
python scripts/evaluate_static_ppo.py --config configs/rl/static_ppo_tiny_extended.yaml --experiment-dir experiments/rl/extended_v1/static_ppo_tiny_v1_extended --validation-decision experiments/rl/extended_v1/validation_decision.json --output experiments/rl/extended_v1/evaluation_tiny --progress
python scripts/evaluate_static_ppo.py --config configs/rl/static_ppo_medium_heavy_extended.yaml --experiment-dir experiments/rl/extended_v1/static_ppo_medium_heavy_v1_extended --validation-decision experiments/rl/extended_v1/validation_decision.json --output experiments/rl/extended_v1/evaluation_medium_heavy --progress
```

### Extended v1 Results (recorded after evaluation)

This section was added **after** all six training runs, the one-time
validation decision, and both final evaluations. The decision rule above was
not revised. All numbers below are raw vessel-minutes unless marked as
seconds. Source commit for every run: `13bcdc4aa9a81b35be7bc1343ff8d2fdbc8b2637`;
all six training and both evaluation manifests recorded `git_dirty=false`.
The decision artifact is `experiments/rl/extended_v1/validation_decision.json`
(SHA-256 `9ba8324a9f8284b4e5a9a14be34ae23b06e43ef578c5e714b376cfda888a164b`).

| Regime | Seed | Completed steps | Training runtime (s) | Validation runtime (s) | Best step | Best validation mean waiting | Final-step validation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tiny | 11 | 301,056 | 248.3 | 13.6 | 110,592 | 2,613.1 | 2,629.3 |
| Tiny | 23 | 301,056 | 374.7 | 18.8 | 270,336 | 2,603.7 | 2,639.3 |
| Tiny | 37 | 301,056 | 388.5 | 21.3 | 180,224 | 2,604.0 | 2,606.9 |
| MEDIUM/HEAVY | 11 | 501,760 | 2,286.6 | 82.0 | 460,800 | 1,615.3 | 1,619.6 |
| MEDIUM/HEAVY | 23 | 501,760 | 1,509.8 | 74.9 | 460,800 | 1,542.8 | 1,605.7 |
| MEDIUM/HEAVY | 37 | 501,760 | 2,333.4 | 116.9 | 460,800 | 1,553.9 | 1,595.5 |

Requested budgets were 300,000/500,000 steps and evaluation frequencies
10,000/20,000; PPO finished the enclosing 2,048-step rollout. Runtime includes
setup; MEDIUM/HEAVY seed 11 spent 379.3 s on initial baseline setup, whereas
later seeds used the shared cache. Per-seed curves are
`experiments/rl/extended_v1/curves_tiny.png` and
`experiments/rl/extended_v1/curves_medium_heavy.png`. Their left panels show
**raw, unscaled training reward** (negative episode waiting) on training
scenarios, and their right panels show **mean total waiting** on the frozen
validation suites, with FCFS and Rollout references. Tiny improved sharply
before settling near 2,600; final-step validation was slightly worse than
each selected checkpoint. MEDIUM/HEAVY improved sharply from its untrained
policy and reached its best observed values late, but its three selected
validation means still differed by 72.5 minutes. These observations describe
the recorded trajectories, not convergence.

The frozen validation means were FCFS 2,808.0 and Rollout 2,495.5 for tiny;
FCFS 1,459.8 and Rollout 859.2 for MEDIUM/HEAVY. Applied exactly as specified
above, the tiny gap-closure ratios for seeds 11/23/37 were 0.6238/0.6538/0.6528
(3/3 pass). MEDIUM/HEAVY PPO/FCFS ratios were 1.1065/1.0569/1.0645
(2/3 pass; seed 11 failed). The recorded conclusion was **both criteria met;
candidate-scoring v2 optional**. Under the frozen gate, final testing was
permitted regardless of the decision outcome. Each seed's selected
`best_validation_model.zip` and its SHA-256 are recorded in the decision
artifact; the final checkpoints were not used for test selection.

The independent test used the same frozen scenarios for FCFS, Greedy Rollout,
Exact where eligible, and all three PPO seeds. The table reports mean total
waiting per scenario. PPO is the mean of the **three per-seed means** (not a
selected best seed); `sd` is the sample standard deviation of those three
means. Each tiny family has 50 test scenarios; MEDIUM and HEAVY each have 50.

| Regime / family | FCFS | Rollout | Certified Exact | PPO seed 11 | PPO seed 23 | PPO seed 37 | PPO mean (sd) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tiny n6 | 2,058.3 | 1,863.2 | 1,839.7 | 1,958.0 | 1,964.0 | 1,975.9 | 1,966.0 (9.1) |
| Tiny n7 | 2,808.8 | 2,605.2 | 2,541.7 | 2,723.1 | 2,658.7 | 2,703.2 | 2,695.0 (33.0) |
| Tiny n8 | 4,046.4 | 3,679.5 | 3,594.7 | 3,937.8 | 3,912.8 | 3,909.1 | 3,919.9 (15.6) |
| MEDIUM (16) | 392.8 | 265.9 | n/a | 529.9 | 445.9 | 504.9 | 493.6 (43.1) |
| HEAVY (24) | 2,219.8 | 1,552.0 | n/a | 2,636.1 | 2,563.4 | 2,495.1 | 2,564.9 (70.5) |

Across the 150 tiny test scenarios, PPO's per-seed paired differences from
FCFS were -98.2/-126.0/-108.5 minutes, but differences from Rollout were
+157.0/+129.2/+146.7 minutes. Certified Exact covered **150/150** tiny
test instances. PPO's per-seed mean absolute gaps were 214.3/186.5/204.0
minutes. The corresponding means of *per-instance* relative gaps were
0.0951/0.0839/0.0905; they are not ratios of aggregated means.

Across the 100 MEDIUM/HEAVY test scenarios, PPO's paired differences from
FCFS were +276.7/+198.4/+193.7 minutes, and from Rollout
+674.0/+595.7/+591.1 minutes. The cross-seed PPO mean was 1,529.2 (sample
sd 46.6), versus FCFS 1,306.3 and Rollout 909.0. There is no certified
Exact reference for 16- or 24-vessel test instances under the frozen
`max_vessels=8` limit; no exact gap is claimed for them. The positive
validation decision therefore did **not** translate into competitive
MEDIUM/HEAVY test performance. Tiny PPO improved on FCFS but not Rollout.

Diagnostics are separate from independent in-distribution testing. LOW
traffic (20 scenarios per regime) gave PPO seed means 622.3/686.3/732.0
for tiny and 242.3/174.9/149.6 for MEDIUM/HEAVY, against FCFS 82.5 and
Rollout 56.2. MEDIUM/HEAVY cross-family tiny diagnostics (10 per tiny
component) gave PPO means 3,094.3/2,933.6/2,928.9, versus FCFS 2,868.7
and Rollout 2,635.8. Those diagnostics are newly seeded, but the diagnostic
*questions* were explored in the pilot; they are not another independent
confirmation set. Exact certified 170/170 eligible tiny-regime scenarios
including LOW, and 50/50 eligible MEDIUM/HEAVY diagnostics. No node-limited
or uncertified Exact result was treated as optimal. Positive relative gaps
against zero Exact optimum remain undefined, not epsilon-adjusted.

Raw per-scenario, per-policy results (including mean/P95 waiting, mean/P95
turnaround, validity, policy-run time, paired deltas and certified gaps) are
in `evaluation_tiny/per_instance.jsonl` and
`evaluation_medium_heavy/per_instance.jsonl`, under
`experiments/rl/extended_v1/`. `aggregate.json` documents grouped means and
cross-seed sample spread; `evaluation_manifest.json` records config/checkpoint
hashes, dependencies, scenario fingerprints, audit summaries and runtime.
Both evaluations reported zero invalid schedules, zero masked-action errors,
zero interrupted/failed runs and no detected split or pilot-content leakage.
Their total runtimes were 351.6 s (tiny) and 774.3 s (MEDIUM/HEAVY);
per-method policy runtime and Exact runtime are separate in each manifest.
The `algorithm_runtime_seconds` field is end-to-end policy execution for one
scenario, not neural-network forward-pass latency alone.

Limitations: synthetic uncalibrated traffic, three training seeds, one frozen
validation/test campaign, fixed vessel order and candidate positions, and no
hyperparameter or architecture search. The LOW diagnostics show especially
poor transfer. These results do not establish PPO convergence or superiority
to the stronger Rollout baseline. Future questions include candidate-scoring
architectures, richer training distributions, and replication on fresh
empirically calibrated scenarios; none was started in this campaign.

## Known Limitations

- Fixed vessel order and the finite candidate model: PPO cannot beat the
  certified candidate-space optimum, and nothing here is a continuous-BAP
  result.
- Synthetic, non-calibrated traffic; three training seeds and small suites
  cannot establish population-level performance.
- Default hyperparameters and finite budgets; no tuning study.
- CPU training used eight environments in one `DummyVecEnv`, not parallel
  environment processes.
- Bitwise reproducibility of training holds for the same software stack and
  CPU; it is not guaranteed across library versions or hardware.
- The tiny model's capacity (8) prevents MEDIUM/HEAVY cross-family evaluation.
- Exact evaluation of 8-vessel instances can take seconds and may stop at the
  node limit, in which case no certified gap is reported.
