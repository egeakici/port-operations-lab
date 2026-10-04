# Step 12A: Scientific Benchmark Core

This phase analyzes frozen Step 9 Static PPO and Step 11 Dynamic PPO held-out
test records. It performs no training, checkpoint selection, test inference or
new diagnostic episodes. The starting Git HEAD was
`b87af8408940d2720c553bea88ee86090d1ec7b8` with a clean worktree; it
contains `docs: record dynamic PPO campaign results` and its Step 11 parent.

The two branches use separate physical test suites and must not be ranked
against each other. Static v1/v2 comparisons retain the validation-only
`v2_rule_1` choice: tiny v1 and medium/heavy v2. Tiny candidate-space Exact
is exact only for the fixed-order finite-candidate problem. Dynamic uses
H=240, a causal Online Rollout reference and three frozen PPO seeds
(11, 23, 37). Its original `dynamic_rule_1` R1/R2 outcomes are preserved,
not reselected. No H=0-trained control is available.

The input gate checks decision SHA-256 sidecars; selected checkpoint hashes,
sidecars and training manifests; config and suite fingerprints; train/validation
versus test disjointness; completed valid rows; complete method/seed/scenario
pairing; and no duplicate rows. Dynamic vessel placements are checked with the
canonical BAP core, as are raw waiting totals and the negative-episode-return
identity. Historical Static per-scenario records contain raw total and mean
waiting rather than placements: their total/mean/vessel-count identity and
the locked aggregate report are cross-checked. The absence of static
placements in these records is a source limitation, not a replay request.

The unit of paired comparison and bootstrap resampling is one physical
scenario. For each scenario, the PPO seed mean is computed across the three
checkpoints before aggregation. Family means use the weights in the frozen
experiment configs. Delta is PPO minus reference in vessel-minutes; negative
is a win, with `1e-6` vessel-minutes as the tie tolerance. The stratified
paired bootstrap draws 10,000 within-family samples with RNG seed 12012 and
reports percentile 95% intervals conditional on these three trained models.
It does not treat `3*N` seed results as independent scenarios or estimate
training-seed uncertainty. Gap closure is `(FCFS-PPO)/(FCFS-Rollout)` and is
undefined when FCFS does not exceed Rollout; values are not clipped.

Run from `03-berth-allocation-lab` in PowerShell, one command per line:

```powershell
python scripts/run_scientific_benchmark.py --config configs/benchmark/step12_static.yaml --dry-run
python scripts/run_scientific_benchmark.py --config configs/benchmark/step12_dynamic_h240.yaml --dry-run
python scripts/run_scientific_benchmark.py --config configs/benchmark/step12_static.yaml
python scripts/run_scientific_benchmark.py --config configs/benchmark/step12_dynamic_h240.yaml
```

The completed derived artifacts live under
`experiments/benchmark/step12/<benchmark_id>/`. Output directories are
exclusive: a second execution with the same ID fails rather than overwriting
anything. Change the benchmark ID for a new analysis. The manifest records
source and derived SHA-256 hashes. Existing locked records contain all required
per-scenario data, so `replay_audit.json` records `not_required`; no CPU/CUDA
action-parity claim follows. CUDA training and CPU held-out inference are
separate provenance fields. Future Step 12B diagnostic seeds reserve the
8,000,000+ region; Part A generates none.

Only synthetic, uncalibrated traffic is represented. Online Rollout is a
heuristic, not an optimum. Interval estimates describe scenario sampling
conditional on the frozen models, not deployment to real terminals. Step 12B
owns WAIT traces, horizon/counterfactual diagnostics, latency and scientific
interpretation. Step 13 owns the broader results warehouse and reporting.
