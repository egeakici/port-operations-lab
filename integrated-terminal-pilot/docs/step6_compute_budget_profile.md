# Step 6 Compute Budget Profile (K5)

```text
K5_COMPUTE_PROFILE = MEASURED (Phase P, 15 predeclared development states)
K5_FIXED_BUDGET    = PROPOSED_NEEDS_OWNER_REVIEW
```

## 1. What the protocol fixes (§5) and what it leaves open

- **Structural budget (FROZEN).** A2 and B2 evaluate the same candidate set (all legal actions plus
  WAIT if legal). Both roll out the same visible cohort to completion under the same continuation
  rule. The only difference is the forward model's physics. B2-T inherits B2's budget exactly
  (AM-08).
- **Wall-clock** is reported (mean, median, P95, max per epoch; per episode; forward simulations;
  kernel events simulated) and is never used to rank.
- **PROPOSED trigger.** If B2's mean decision time on development scenarios exceeds 2.0 s, a
  pre-registered cohort cap (the maximum number of visible vessels rolled out, chosen on development
  data only) applies to **both** A2 and B2 and is frozen before validation.

Step 6 implements the frozen structural budget exactly. It applies **no** cap, timeout, pruning
or fallback. An engineering guard of 400,000 kernel cycles per rollout leaf exists only to stop a
runaway simulation. Hitting it fails the decision (`INCOMPLETE_ENGINEERING_PROBE`); it never
truncates a score. It was never reached in any probe or run.

## 2. Phase P measurement (`--profile-compute`)

- **States:** predeclared berth decisions #1, #5, #10, #15 and #20 of seed 10,000,000 of each
  development family. Each state is reached by driving A1 on the primary profile. 15 states exist,
  because low has only 8 berth decisions and medium 16.
- **Output:** `experiments/step6_development/compute_profile/20261013T210006Z/profile.json` (wall
  time 308 s).
- **Host:** Windows 11, Python 3.13.2, 12 logical CPUs, single process; host load was not
  controlled.
- **Timing:** `perf_counter` around each decision call; imports, checkpoint loading and trajectory
  driving are excluded.

| Per decision (s) | n | p50 | p90 | p95 | max | mean |
| --- | --- | --- | --- | --- | --- | --- |
| A2 (Project 03 nominal rollout) | 15 | 0.133 | 1.29 | 1.69 | 1.86 | 0.394 |
| **B2 / B2-T shared evaluation** | 15 | 4.45 | 47.6 | 53.9 | 59.7 | **15.25** |
| B1 | 15 | 0.0011 | 0.0037 | 0.0045 | 0.0061 | 0.0016 |
| A1n | 15 | 0.0007 | 0.0021 | 0.0042 | 0.0082 | 0.0013 |
| Projection build (in the B2 time) | 15 | 0.48 | 1.87 | 2.62 | 2.72 | 0.74 |

| Family | B2 states | B2 mean (s) | B2 max (s) |
| --- | --- | --- | --- |
| itp_low | 2 | 2.90 | 3.72 |
| itp_medium | 4 | 1.94 | 4.45 |
| itp_heavy | 5 | 25.17 | 51.41 |
| itp_yard_bottleneck | 4 | 22.35 | 59.75 |

Cost drivers per state:

- **Leaf rollouts:** 4–54. WAIT expands to one rollout per legal assignment at the next decision.
- **Kernel cycles per leaf:** up to 1,594.
- **Size:** visible cohort 2–18 vessels; legal assignments 2–18.
- **Memory:** projection 0.33–1.77 MB pickled; B2 peak memory 6.6–10.5 MB (tracemalloc, low family).
- **Records:** serialized predictions 1.4–15.8 kB per decision.

**Correctness of the measurement:**

- reversing candidate order gives a byte-identical prediction digest;
- a repeated evaluation gives an identical digest;
- B2 and B2-T selections come from the same record.

**Verdict:** the B2 mean of 15.3 s exceeds the PROPOSED 2.0 s trigger, so protocol §5 requires a
cohort-cap decision. The same states also show that A2 is much cheaper (max 1.9 s here; the
pre-Step 6 heavy runs reached 10.3 s). The nominal berth-only model and the integrated kernel
model do **not** have equal wall-clock cost, even under the identical structural budget.

## 3. Owner decision required (Q6-3) — options, no choice made

| Option | Budget | Consequence |
| --- | --- | --- |
| K5-A | Keep the frozen full-cohort structural budget; accept the cost | Faithful to §5 as frozen. Development estimate for heavy B2: about 25 s × about 30 decisions ≈ 12–13 min per episode, and the same for B2-T. A Step 7 campaign needs parallel workers and many CPU-hours. B2 and B2-T wall-clock are reported, never ranked |
| K5-B | Approve a cohort cap `k` (maximum visible vessels rolled out), applied identically to A2, B2 and B2-T | Lower cost. It changes A2's frozen Project 03 behaviour too, because the cap is shared. `k` must be chosen on development data only, by a pre-stated rule (e.g. the smallest `k` that keeps the mean B2 decision time ≤ 2.0 s on the Phase P states), and frozen before validation |
| K5-C | Another rule (e.g. a fixed per-decision leaf budget), applied equally | Needs an exact definition and an amendment |

A per-decision timeout with a fallback to FCFS is **not** offered: it would be asymmetric and is
excluded by the brief. Until a decision is recorded, only the bounded development stages F1/F2
run, and stage F3 (heavy/bottleneck rollouts) is `BLOCKED_BY_COMPUTE_REVIEW`.

## 4. Commands

```powershell
python scripts/run_step6_coordination.py --profile-compute
python scripts/run_step6_coordination.py --profile-compute --probe-family itp_low --max-wall-minutes 10
```
