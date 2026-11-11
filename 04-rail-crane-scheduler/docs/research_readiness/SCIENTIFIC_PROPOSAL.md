# Project 04: consolidated O1-O6 proposal

PROPOSED — OWNER_APPROVAL_PENDING. This is an uncalibrated synthetic study. The
machine-readable authority is `configs/research/primary_candidate_v1.json`, not
this prose. Its canonical SHA-256 and exact approval declaration are in
`APPROVAL_PACKAGE.json` and `OWNER_REVIEW.md`. No owner receipt was created.

## Consolidated decisions

| Decision | Exact recommendation | Rationale and scientific limit |
| --- | --- | --- |
| O1 | Global rail x in meters, origin 0 at synthetic lower rail end; +x left to right. Rail [0,360]. Hull lower edge 36, length 288; local u maps to 36+u for +1 orientation and 36+288-u for -1. Crane rail reference points, d=24 m normally / 36 m heavy. Closed spatial boundaries, half-open resource intervals, closed safety. Time epsilon 1e-8 min, position epsilon 1e-6 m. | Explicit transform, no inferred body widths. Kernel never subtracts epsilon from clearance; independent validator tolerance is roundoff comparison only. This cannot certify crane-body, boom, ship or road collision safety. |
| O2 | Exactly two fixed-rank cranes, straight constant-speed committed travel, then stationary setup and nonpreemptive processing. Both may operate concurrently when full piecewise-linear paths are safe. Time=distance/speed; process=60*moves/rate. WAIT advances to next strictly later travel/setup/process completion; settle tied completions before new dispatch, then completion time / crane rank / task ID. Idle cranes hold. | Existing kernel is retained. Pair dispatch plus WAIT cannot jointly yield/reposition. The CP optimum and PPO reachable schedules apply to this dispatch subclass, not unrestricted continuous QCSP. |
| O3 | See complete physical/family/cohort tables below; standalone effective processing rates 30 moves/h normally, 24 heavy; explicit setup 1 min; speeds 45 m/min normally, 30 heavy; no nominal-times-efficiency factors. | Synthetic choices of plausible scale, not measured terminal constants. Processing excludes separately modelled gantry travel/setup. The separation of losses is assumed, not an empirical calibration or equivalence with Project I. |
| O4 | Exact finite-event-dispatch reference, maximum 5 jobs, primary tiny family has 4. Tick 1/30 min (2 s), no rounding; 100,000 enumeration nodes; total wall budget 10 s including cold import, enumeration, model build and solve. One solver thread, solver seed 0, scaled integers below 2^50, representability checked at time epsilon. | Complete path domain required. OPTIMAL only certifies this finite model; FEASIBLE is an incumbent, INFEASIBLE only the supported complete finite model, UNKNOWN uncertified, TIMEOUT exhausted budget. Node exhaustion/non-grid inputs are unsupported, never an optimum or infeasibility proof. |
| O5 | MaskablePPO, stable 32 task slots, 65 actions (WAIT + 2*32 pairs); maximum 256 decisions. See PPO table. Gamma=1, negative elapsed minutes /60, failure subtracts (17280+1)/60; no shaping. | Separate Crane PPO, no berth PPO checkpoint reuse. Failure is worse than any horizon-bounded complete return. Full state/masks are known static workload only. Five seeds all retained; validation chooses a checkpoint within each seed. |
| O6 | 512 train, 128 validation, 256 untouched test scenarios, stratified equally across four families. 20,000 scenario bootstrap draws, seed 7042026, nominal joint 95% confidence across eight intervals: four makespan and four failure contrasts, each two-sided 99.375% Bonferroni percentile CI. Minimum 60 common complete pairs per family. | Scenario is independent unit; five PPO seeds are nested inside scenario. Inference is approximate, not a power guarantee or exact coverage theorem. Retain every failure/timeout/unsupported cell and support loss; no test-based seed selection. |

## Full physical and scenario design

All physical rates, layouts, workloads and times below are synthetic assumptions
except units/conventions inherited from the Project 04 contract. No bay plan,
crane-body dimensions, TOS records, or measured crane telemetry was supplied.

| Parameter | Proposed value and units | Origin, rationale, sensitivity and uncertainty |
| --- | --- | --- |
| Crane fleet | 2; ranks 0,1; initial x=36,324 m; available t=0 min | Inherited two-crane scope; assumed symmetric endpoints encourage concurrent service. High sensitivity to interference/initial layout; not measured. |
| Rail/reach | Rail and each reach [0,360] m | Assumed common rail; full reach avoids mixing reach allocation with dispatch learning. High geometry sensitivity; real reach DATA_GAP. |
| Hull | Lower edge 36 m, length 288 m, t0=0 min, no calendar epoch | Assumed hull fits rail with 36 m margins. Coordinate origin is arbitrary; length/initial positions affect travel. No empirical vessel identity. |
| Bays | Tiny local [36,108,180,252] m (72 m spacing); others 12+24*i, i=0..11 (12 bays) | Assumed coarse work locations, not literal ISO bay numbering or container body dimensions. Tiny coarse grid keeps a tractable, constructible two-zone reference stratum; others introduce adjacent work interference. High sensitivity. |
| Clearance | 24 m; heavy 36 m | Assumed reference-point threshold; heavy is 1.5 times base. Not a body width or certified physical clearance. Very high sensitivity and uncertainty. |
| Travel speed | 45 m/min; heavy 30 m/min | Manufacturer specs give 45 m/min as a gantry speed scale. Heavy 30 is assumed degraded speed. Constant speed omits acceleration/wind constraints. Medium/high sensitivity; neither value measured here. |
| Effective productive rate | 30 moves/h; heavy 24 moves/h | Assumed productive-stage rates. Manufacturer discussion describes roughly 30 net moves/h in one operating example; context only, not a calibrated decomposition. Heavy is an assumed 20% reduction. Very high sensitivity; no efficiency multiplication. |
| Setup | 1 min/job | Explicit assumed stationary handling overhead, no measured breakdown. High sensitivity for tiny jobs. Not copied as an approved fixture default. |
| Horizon | 17,280 min (12 days) | Administrative bound above heavy worst sequential process 32*180*60/24=14,400 min plus conservative movement/setup allowance 416 min. No promise about observed service duration. Low sensitivity when nonbinding; critical if reached. |
| Completion | All original nonpreemptive jobs independently validated | Inherited objective; incomplete schedules have null makespan, never a short successful objective. |
| Failure | Invalid action/plan, deadlock, horizon, decision bound, incompatible inputs | No job dropping or failure imputation. Retain error/status evidence. |
| Release/precedence | Every task ready t=0; empty predecessor list | Implemented static v1; stack dependencies and dynamic arrivals unsupported, not assumed solved. |
| Operations | LOAD or DISCHARGE per scenario, same durations in this model | Seed modulo 4 {0,1} gives DISCHARGE, otherwise LOAD; no mixed-operation precedence/cargo claim. Operation type is not a learned causal distinction here. |
| Orientation | Even seeds +1, odd -1 | Assumed exactly balanced conventions; held-out orientations do not leak outcomes. |
| Workload draw | Independent discrete uniform integer within family; task bay chosen uniformly with replacement | Existing named SHA-256 streams. Repeated bays allowed. No acceptance sampling on scheduler success. High distribution sensitivity. |
| Geometry jitter | 0 m; geometry/workload/position nonces all 0 | Exact geometry and grid aid audit/CP eligibility; randomness is workload and job bay assignment. Other geometry distributions require a new approved study. |
| Numerical tolerances | 1e-8 min; 1e-6 m | Assumed numerical comparison bounds, far below physical scales. No safety relaxation in dispatch. Critical at equality; no empirical precision claim. |

| Family | Jobs | Bays | Moves per job, inclusive | Other changes | Fixed weight |
| --- | ---: | ---: | --- | --- | ---: |
| tiny | 4 | 4 | discrete uniform 6..18 | base physics, CP eligible | .25 |
| small | 8 | 12 | discrete uniform 20..60 | base physics | .25 |
| medium | 20 | 12 | discrete uniform 30..90 | base physics | .25 |
| heavy | 32 | 12 | discrete uniform 60..180 | d=36, speed=30, rate=24 | .25 |

The heavy family intentionally bundles stressors; it does not identify the causal
effect of clearance, rate or workload separately. These are work-group workloads,
not a measured complete vessel stowage plan. No nominal 0.92 factor is inherited
from Project I. The 30 moves/h number alone does not establish rate equivalence.

## Randomness and cohorts

Counter-SHA256 generator v2 uses separate geometry/workload/positions streams.
Namespace is `p04_qcsp_synthetic_v1/{role}/{family}`. Family order is tiny, small,
medium, heavy; family seed stride 10000. PPO RNG namespace is separately
`p04_qcsp_synthetic_v1/rl_training_rng`; its five seeds do not select scenarios.

| Role | Count/family | tiny seeds | small seeds | medium seeds | heavy seeds |
| --- | ---: | --- | --- | --- | --- |
| train | 128 | 100000..100127 | 110000..110127 | 120000..120127 | 130000..130127 |
| validation | 32 | 200000..200031 | 210000..210031 | 220000..220031 | 230000..230031 |
| test | 64 | 300000..300063 | 310000..310063 | 320000..320063 | 330000..330063 |

Seeds/bands/counts are synthetic protocol choices, not observations. Counts are a
bounded initial research budget, not a demonstrated power calculation. Physical
fingerprints must be disjoint, even if seed/ID/role differ. Any collision stops
generation with retained evidence; no silent reroll or exclusion is allowed.
Generation includes test input bytes, but all model/interface decisions are frozen
before generation; no test scheduler outcomes are computed until selection lock.

## Exact PPO configuration

| Parameter | Proposed value | Rationale / provenance / sensitivity |
| --- | --- | --- |
| Training seeds | 1103,2207,3301,4409,5501 | Five independent predeclared RNG replicates, all reported; assumed budget. Moderate variance-estimation uncertainty. |
| Budget per seed | 1,048,576 timesteps = 512*2048 | Explicit initial CPU budget; no runtime or convergence assertion. High learning sensitivity. |
| Rollout/batch/epochs | 2048 /128 /10 | Standard PPO scale with 16 whole minibatches per rollout; assumed, not tuned on test. High optimization sensitivity. |
| Learning rate | Constant 0.0003 | Common SB3 scale; freeze schedule so resume does not silently restart annealing. High sensitivity. |
| Gamma / GAE lambda | 1 /0.95 | Gamma preserves undiscounted makespan return; lambda controls variance/bias. Gamma is scientifically material. |
| Clip / entropy / value / max gradient | .2 /.01 /.5 /.5 | Explicit PPO design assumptions, no shaping. Moderate/high sensitivity. |
| Network | Separate policy/value [128,128], Tanh; Adam epsilon 1e-5 | Explicit small CPU MLP, installed SB3 policy behavior verified. No claim of architecture optimality. |
| Validation and checkpoint intervals | Every 65,536 steps =32 rollouts; 16 checkpoints/seed including final | Optimizer boundaries only. Fixed selection opportunities; high selection-frequency sensitivity. |
| Selection | Lowest validation failure rate, then valid makespan mean, then earliest step | Validity first; all-failed candidates tie on undefined quality. No test access and no seed selection. |
| Capacity/actions/episode steps | M=32 /65 /256 | Capacity covers heavy jobs; finite progress needs at most 4n+3=131 kernel decisions, with conservative bound. Oversize input rejects. |
| Reward scale/failure margin | 60 min /1 min | Successful return -T/60; failure extra -(17280+1)/60. Numeric scale is assumed; no secondary reward. |
| Normalization | x/reach by 360 m and lower endpoint; clock by 17280 min; workload by scenario original max moves; speed/rate by per-scenario maxima; remaining commitment by max(360/v+setup+60*max_moves/rate) | Known input state only, no test-fitted scale and no clipping. Clock/tasks/cranes/mask/geometry feature layout remains v1. |
| Device/resources | CPU; torch 2 threads, 1 DummyVecEnv; no fallback; minimum 2 GiB available RAM and 10 GiB free disk | Observed i7-1355U/Iris Xe machine, no CUDA device available. Resource thresholds are engineering safeguards, not measurements of training demand. |

No `learn()` or optimizer step was executed during readiness work. Real untrained
inference/save/reload and actual fixture-step callback wiring were tested. Training
throughput, convergence, optimizer-boundary interruption and learned-policy quality
remain unmeasured until the owner's approved manual run.

## Evaluation and acceptance rules

All methods use identical scenario bytes/physics/masks/validator. Comparator IDs
are the actual implemented `ordered_sweep_v1`, `nearest_feasible_v1`,
`longest_work_v1`, `balanced_finish_v1`. The last is the primary comparator;
its implemented rule prioritizes committed load then projected finish. Do not
reinterpret it as an unrestricted earliest-finish optimizer. All four comparisons
are retained, without choosing a favorable comparator after test.

Validation baseline campaign: 128 scenarios *5 arms=640 cells; 96 CP cells are
explicitly ineligible. Held-out campaign: 256 scenarios *10 arms=2560 cells (four
heuristics, five PPO seeds, CP); 192 CP cells are ineligible, retained as such.
CP tiny timeout/unsupported/FEASIBLE results remain in coverage/status reports;
only independently valid OPTIMAL references with matching bound support certified
finite-subclass gaps. CP is descriptive, outside the confirmatory contrasts.

Primary quality: equal-family-weighted mean of paired scenario differences in
valid complete makespan minutes, candidate minus comparator. Average all five PPO
seeds inside each scenario. Quality uses the common complete intersection of all
five seeds and all four heuristics; minimum 60/64 per family, at least 240/256
scenarios. Failure accounting always retains all submitted supported scenarios.
No false quality value is assigned to unfinished jobs. Also report every seed,
family, status, completion fraction, utilization, travel/idle, latency and violation.

Bootstrap physical scenarios within family; same resampled indices across seeds
and contrasts. Freeze family weights .25, 20,000 draws, RNG seed 7042026. Linear
percentile quantiles at .003125 and .996875 give each 99.375% interval: Bonferroni
over four quality and four unconditional failure-difference intervals for nominal
joint 95%. This is approximate bootstrap inference, not an exact small-sample or
rare-failure guarantee. Degenerate all-zero failure intervals cannot rule out
unobserved rare failures. No post-hoc Holm test or unadjusted CI is substituted.

Support superiority only when the adjusted primary makespan upper bound is <0,
the primary unconditional failure-difference upper bound is <=0, and every family
meets support. Otherwise state inconclusive, worse or unsupported as appropriate;
negative findings do not prevent an honest scientific report.

Latency uses fixed CPU two-thread sequential execution. Record cold model load
separately; perform 16 unrecorded deterministic warmup predictions per model and
scenario; every measured decision includes fresh encoding/mask/predict. Report
mean, nearest-rank P95, max and count, separately from whole-episode wall time,
validation and I/O. These warmups are timing design, not optimizer updates.

Functioning software requires passing engineering checks. Physical success requires
independent complete schedule verification. Trained status requires a genuine
hash-bound checkpoint with >0 optimizer updates and the declared total seed budget.
Improvement requires the approved adjusted paired evidence above. A mathematical
reference requires matching finite-model OPTIMAL and validated bound. Technical
Project I interoperability still requires a separately versioned real successor API,
rail/bay/cargo data and reconciliation tests. Full closure requires audited complete
cohorts/models/results/figures/claims and explicit review; it is never auto-set.

## Source references (context, not calibration)

- [Liebherr STS technical specification](https://www.liebherr.com/en-int/maritime-cranes/products/port-equipment/ship-to-shore-container-cranes-5391550): published gantry travel speed scale 45 m/min.
- [Konecranes STS technical data](https://www.konecranes.com/system/files/2024-04/7593_sts_monobox_technical_doc_v1.pdf): published gantry travel speed 45 or 55 m/min, distinct from trolley/hoist speed and transverse rail span.
- [Konecranes quayside concept discussion](https://www.konecranes.com/sites/default/files/download/port_tech_int_issue_77_konecranes_article_new_quayside_crane_concept.pdf): a 120-second cycle / roughly 30 moves/h example; not a measured Project 04 rate or verified loss breakdown.
- [Installed MaskablePPO documentation](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html): masks must be supplied during prediction/evaluation; installed 2.8.0 source is the implementation authority.
- Repository Step 01 scientific contract and decision register retain their original unapproved historical state. This proposal supersedes their pending choices only upon exact owner approval, without rewriting historical evidence.
