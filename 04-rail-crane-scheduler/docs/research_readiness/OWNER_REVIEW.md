# One owner review ? Project 04 research profile

OWNER_APPROVAL_PENDING. No owner receipt, primary generation, PPO optimization or
held-out scientific campaign was created/run by this readiness task.

Canonical profile SHA-256:

`d06b10d8e04fd0d3655c22267a4ed6cb48b9caa745fec12ac71a8a7bb19dddbc`

The digest is of existing `contracts.canonical` bytes (sorted compact UTF-8 JSON),
not the pretty-printed file's raw Get-FileHash result. Exact file bytes and all
candidate-view hashes are recorded separately in APPROVAL_PACKAGE.json.

Review [the proposed scientific contract](SCIENTIFIC_PROPOSAL.md),
[all 136 numerical values and provenance entries](NUMERICAL_PROVENANCE.json),
[the exact profile](../../configs/research/primary_candidate_v1.json), and
[the manual sequence](MANUAL_RESEARCH.md). All six choices are proposed, including
the scientific acceptance of the existing restricted action/CP model.

| Decision | Exact proposed choice |
| --- | --- |
| O1 | Global meters, rail [0,360], hull origin 36/length 288, both orientations, reference points, d=24 m (heavy36), epsilon_t=1e-8 min / epsilon_x=1e-6 m; body dimensions excluded DATA_GAP. |
| O2 | Two committed constant-speed cranes, stationary setup/process, safe concurrency, event WAIT, no joint yield/reposition or stack precedence. |
| O3 | Base speed45 m/min, effective productive rate30 moves/h, setup1 min; heavy speed30/rate24/d36. Jobs4/8/20/32, move ranges6..18/20..60/30..90/60..180, horizon17280 min, frozen bays/cohorts/namespaces. Synthetic, not empirical. |
| O4 | Finite-event dispatch <=5 jobs, tick1/30 min, 100000 nodes, 10 s total, one thread/seed0, no rounding; independently valid OPTIMAL only certifies that subclass. |
| O5 | M32/actions65/256 decisions, [128,128] Tanh, gamma1, elapsed/60 reward, no shaping; PPO rollout2048/batch128/epochs10/lr0.0003 constant, GAE0.95/clip0.2/entropy0.01/value0.5/grad0.5; 1048576 steps per seed1103,2207,3301,4409,5501, validation/checkpoints65536; CPU2 threads, one env, no fallback. |
| O6 | Train512/validation128/test256, equal four-family weights; all five seeds nested within physical scenario; four named heuristic contrasts, primary balanced_finish_v1; 20000 stratified bootstrap draws/seed7042026; eight Bonferroni percentile intervals99.375% each, joint nominal95%; >=60/64 common complete scenarios per family plus unconditional failures. |

Exact owner declaration to send after review (one line; approval is not inferred
from opening this file or from a successful test):

```text
I APPROVE PROJECT04 PROFILE d06b10d8e04fd0d3655c22267a4ed6cb48b9caa745fec12ac71a8a7bb19dddbc O1-O6 AND EXACT DERIVED PLANS p04_exact_campaign_derivation_v1 FOR MANUAL FOREGROUND GENERATION BASELINES FIVE-SEED PPO VALIDATION-ONLY SELECTION HELDOUT EVALUATION AND REPORTING WITH THE DECLARED BUDGETS. NO AUTOMATIC CAMPAIGNS OR SCIENTIFIC CLOSURE.
```

This is one consolidated approval of numerical O1-O6 choices, bounded manual
campaigns, and the explicitly named exact child-plan derivation amendment. It
allows future actual generated-input and validation-selected checkpoint hashes
to be bound mechanically under that root; it does not authorize arbitrary plans,
new budgets, changed physics/source/device/cohorts, test-based model selection,
automatic campaigns, commits/push or an automatic scientific-closure statement.

After that genuine owner approval, record the matching immutable receipt at:

`experiments/research_v1_d06b10d8e04f/owner_approval.json`

No such receipt exists now. The manual RecordApproval action requires the exact
declaration and a genuine owner-evidence reference; it never runs a campaign.
PrepareGeneration only writes contracts/parameters and may run before approval.
Generate/Train/Evaluate fail closed without the real matching receipt. The
immutable profile itself keeps PROPOSED; ValidateProfile separately reports a
verified external receipt when present.

Before owner training, ensure at least 2 GiB RAM is available and 10 GiB disk is
free; these preflight thresholds are enforced. No runtime/convergence guarantee
was measured. Genuine optimization-boundary resume has not been exercised because
optimizer updates were expressly forbidden; fixture/model/metadata/RNG/progress
guards have engineering coverage, and restart semantics are documented.
