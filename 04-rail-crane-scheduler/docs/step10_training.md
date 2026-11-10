# Step 10 new crane PPO tools

No learn() call was executed by development tests. An actual **untrained**
MaskablePPO MultiInputPolicy is created on CPU, uses the real action masks,
saves/reloads deterministically and rejects corruption/interface/source changes.
Test checkpoints are SMOKE_UNTRAINED_NOT_RESEARCH with trained_steps=0 and cannot
pass a trained-model gate. Project03 berth models are never loaded.

TrainingConfig requires all budgets, hyperparameters, network sizes, seeds and
device choices explicitly. Installed API versions: Python 3.13.2, NumPy 2.2.3,
Gymnasium 1.2.3, Torch 2.6.0, SB3/SB3-contrib 2.8.0. No install/upgrade performed.
Gamma=1 is required for this reward profile. Normalization uses known current
geometry/work only, with no fitted held-out statistics. CUDA selection is explicit;
unavailable CUDA does not silently become CPU unless fallback is permitted.

The manual trainer verifies an exact source/config/input approval digest before
reading train/validation cohorts, rejects role/hash changes and physical split
duplicates, and never reads a test list. An ExecutionPermit covers only exact
approved input hashes/roles. Scenario metadata alone cannot unlock research.
There is no approved primary profile or training budget in this checkout.

Training uses a single seeded scenario-cycle environment, mask-aware vector
environment and finite configured timesteps. A vector adapter disables timeout
value bootstrapping for absorbing failure truncations. Validation is separate and
selects lexicographically by failure rate, mean valid makespan and earlier step;
all seeds/checkpoints/failures are retained. Validation RNG consumption is isolated
by saving/restoring Python/NumPy/Torch RNG state.

Checkpoint writes use a unique partial directory then rename to an immutable final
directory. Sidecar records model hash, interfaces, config/source/dependency hashes,
device, seed, training steps and RNG state. Selection/progress are explicit.
Resume accepts exactly one predeclared seed and a compatible trained checkpoint,
restarts episodes at a saved optimizer boundary and retains the old checkpoint.
It is **not bitwise uninterrupted replay**; this limitation is recorded. Ctrl+C
retains only previously complete optimizer-boundary checkpoints, never claims a
mid-update state is consistent. Resume writes a new run directory.

Actual long training and the training-loop/resume optimization execution have
not been run. CPU-only untrained API checks establish integration, not learned
quality or final scientific readiness. Source/config changes require a new lock
and review before any owner-manual run. Full commands appear in the final runbook.
