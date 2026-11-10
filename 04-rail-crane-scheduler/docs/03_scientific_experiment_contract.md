# Scientific experiment contract

Design only; no episodes, seed sets, datasets, benchmarks or training are produced.
All candidate policy IDs below are **proposed**, distinct from frozen prior arms.
P04-S01-009 through P04-S01-014 govern this contract.

## Validity, objective and KPIs

Compare validity first, then makespan on feasible complete instances. Never rank
an incomplete episode ahead of a complete one by elapsed time. On common valid
instances define `T=C_max=max_j C_j-t0`. Use `[t0,t0+T]` for successful-episode
accounting. On failures use the observed `[t0,t_stop]` diagnostic window but set
objective makespan to null; never pool that elapsed window into successful T.
Zero-work valid geometry gives `T=0`, no actions/work, undefined ratios and an
explicit `ZERO_WORK` flag. Such fixtures belong to correctness diagnostics,
excluded from nonempty performance aggregation with their counts reported.

For crane k, let `P_k`, `S_k`, `M_k`, `I_kc` denote process, setup, travel and
idle minutes by exclusive cause c. Require
`P_k+S_k+M_k+sum_c I_kc=T` for a successful episode. Proposed idle cause priority:
`UNAVAILABLE` (later extension), `NO_READY_WORK`, `RAIL_OR_REACH_BLOCKED`,
`POLICY_WAIT`, `NO_REMAINING_WORK`. Classify each idle interval once, based on
readiness and existence of physically legal dispatch/reposition proposals; log
secondary reasons separately without summing them. Static v1 has no unavailable
cranes; their idle cause is zero. Idle-time priority is accounting, not causality.

| KPI | Exact definition, unit and granularity |
| --- | --- |
| Makespan | T minutes/episode, only `SOLVED_VALID` |
| Productive crane utilization | `P_k/T` per crane, `sum_k P_k/(2T)` episode fraction; setup excluded; null for T=0 |
| Occupied crane utilization | `(P_k+S_k+M_k)/T`; fleet numerator summed and denominator `2T`; reported separately |
| Travel distance / time | `D_k=sum_segments abs(x_end-x_start)` meters, `M_k=sum travel durations` minutes; fleet totals sum over two cranes |
| Setup / blocked / idle time | `S_k`, individual `I_kc`, fleet sums in crane-minutes; idle fraction `sum_kc I_kc/(2T)`; blocked is only `RAIL_OR_REACH_BLOCKED`, no extra double-counted total |
| Task queue delay | `Q_j=U_j-r_j` minutes/task; mean `sum Q_j/n`, median and nearest-rank P95; n completed original jobs, not moves |
| Ready-task dispatch delay | Define `e_j=max(t0,r_j,max predecessor C_i)` (empty max=t0); `D_j=U_j-e_j` minutes/task; same summaries; processing-start delay is `S_j-e_j=D_j+h_kj`, named separately |
| Work allocation fairness | `W_k=sum assigned w_j`; Jain index `(W_1+W_2)^2/(2*(W_1^2+W_2^2))`; null if total zero; move-based imbalance `abs(W_1-W_2)/(W_1+W_2)`; neither is optimized |
| Resource conflicts / violations | Count independent validator findings by invariant ID per submitted plan; count rejected policy actions per decision and total; violations never become feasible via penalty |
| Solver compute | Monotonic wall seconds from fully parsed immutable input to final returned proposal, including solver/model construction; independent validation timed separately; parse/I/O and hardware/threads/budget recorded |
| Policy decision latency | Seconds per observation-to-action call, includes mask computation and feature encoding; excludes future physical validation/execution; cold initialization/model load separate; episode call count, total, mean, nearest-rank P95 and max |
| Success / failure | `n_SOLVED_VALID/n_attempted_nonempty_supported`, rates for truncation/deadlock/invalid/no-plan using the same denominator; mutually exclusive final status counts; unsupported and invalid-input counts also reported against all submitted inputs |
| Completion fraction | `sum completed original moves/sum original moves` at stop, dimensionless; unfinished jobs/moves explicit; zero workload fraction null, not synthetic 100% cargo fulfillment |
| Optimality diagnostic | If a valid feasible incumbent F and valid bound L for the same model exist: absolute `F-L` minutes, relative `(F-L)/F` for F>0; model/grid identity required; zero F gives relative gap null |

No task due dates in v1, so tardiness is not a KPI. Partial task-delay summaries
must carry completed/total denominators and remain failure diagnostics. Completed
work may be integrated continuously, but a non-preemptive job is not finished
until its full declared requirement settles. Individual cargo success is never
inferred from aggregate completion fraction.

Across scenarios: report per-family mean, median and nearest-rank P95 of episode
values; average per-episode utilization/fairness ratios rather than silently
pooling crane-minutes. A pooled ratio is a separately named diagnostic. Primary
family weights, sample counts, confidence method and contrasts must freeze before
Step 07 test access. No numbers are chosen here. For paired quality, use the
intersection of valid complete results and report pair-coverage plus each arm's
failures; this conditional summary cannot hide an arm's inferior feasibility.
Certified impossible inputs are a separate negative-test stratum, not performance
victories. An uncertified timeout is not infeasibility.

## Common inputs, information and inference

All arms use identical scenario bytes/physical fingerprint, original tasks, fleet,
rates, geometry, validator, event/numeric rules and metrics. Policy-specific
relaxations are forbidden; disclose search-space restrictions. Freeze train,
validation, test and diagnostics manifests with nonoverlapping scenario seeds AND
physical fingerprints; keep training RNG namespaces separate. Fit preprocessing
on training data only; select checkpoints/hyperparameters on validation only;
retain failures, all training seeds, negative findings and budget overrun records.

Proposed namespace names (no numeric bands/seeds allocated):
`p04_qcsp_v1/dev`, `/train`, `/validation`, `/test`, `/negative_diagnostic`,
`/rl_training_rng`. Step 02 defines collision-free derivation and records namespace
versions; Step 03 generates only authorized manifests. Project I's 10M–13M bands
are historical evidence, not Project 04 defaults.

The independent replication unit is the physical scenario. Multiple PPO training
seeds are nested within scenario; compute scenario-first seed means and retain
seed-specific paired results. Do not report S scenarios times R training seeds
as S*R independent traffic instances. Proposed analysis: paired scenario bootstrap
within family; fixed family aggregation; predeclared primary comparisons and
multiplicity control; scenario-count/seed-count and resampling choices reviewed
before Step 07 and Step 11 locks. No outcomes-based family, seed or test selection.

Step 07's held-out baseline records must remain sealed from PPO/environment
design and training selection until the Step 11 evaluation lock. Use development
and validation diagnostics for those decisions. If baseline test outcomes have
already influenced design, disclose that exposure and establish a fresh held-out
manifest under a versioned protocol before making confirmatory PPO claims.

Static v1 all arms know the full current vessel workload. Offline CP-SAT may also
optimize a complete future schedule; a later online visibility restriction can
give it an information advantage. Label offline oracle/reference results as such.
For online PPO use a matched visible-state heuristic/replanning CP-SAT comparator,
excluding hidden releases/failures. Do not call unmatched offline/online results
apples-to-apples. Compute/quality tradeoffs are research outcomes; no promise that
PPO beats CP-SAT or rollout.

## Future baseline designs (Step 05)

All dispatches require the same independent safety reservation; deterministic ties
use `(score, rail_rank, bay_position, task_id)`. Policies may return legal WAIT or
an explicit unsupported/deadlock outcome, never force an unsafe assignment.

| Proposed family | Exact candidate rule / comparison role |
| --- | --- |
| `p04_ordered_sweep_v1` | Safe constructive reference: partition bay jobs at a feasible spatial cut; initially ordered cranes stay in disjoint service zones separated by d and sweep each assigned zone left-to-right. Choose the first cut in ascending bay order with both initial positions inside their zones, all assigned jobs reachable and safe approach paths; empty zone allowed. If none exists, report construction unsupported, not physical infeasibility. No claim this covers every feasible instance. |
| `p04_nearest_feasible_v1` | Among ready jobs reachable by idle cranes with validated approach/hold paths, minimize travel distance, then canonical ties; dispatch and reserve one commitment at a time. |
| `p04_balanced_longest_v1` | First choose idle crane with least committed original moves (include completed assignments); among physically eligible jobs choose greatest workload; canonical ties. Static cumulative load balancing never overrides feasibility. |
| `p04_earliest_completion_v1` | For each eligible pair, compute earliest feasible travel departure/setup start against committed paths, then finish; choose smallest finish, then canonical ties; WAIT to next legal event if needed. This bounded reservation estimate is not a global optimizer. |

The generator must include a declared constructible baseline stratum; policies
that restrict coordinated repositioning must report that limitation. Step 05
must either supply documented safe yielding through the common core or explicitly
mark unsupported cases, keeping them in coverage accounting. Four policies being
correct does not mean each must solve every feasible offline trajectory problem.

## CP-SAT design reference (Step 06)

Design assignment binaries y_kj, optional setup/process intervals present iff
y_kj=1, exactly-one assignment, crane NoOverlap, precedence/release and horizon
constraints, sequence/transition variables and initial travel constraints. Plain
NoOverlap plus bay endpoint distances is **not** a non-crossing model. Concurrent
trajectories, waits and coordinated movement are the difficult part.

A legitimate bounded model may use integer time ticks Delta_t and a finite set
of rail nodes Delta_x plus explicit wait/travel/process states, occupation and
edge transition conflicts. Round travel/process durations upward, never speed
up motion; retain true bay locations or bound their snapped errors explicitly.
Inflate model separation by a proven coordinate error bound (e.g. if each point
has <=eta meter error, add 2eta), and validate interpolated edge trajectories,
not only node occupancy. If the mapping cannot prove safe edges, reject the
proposal. Compare against the continuous reference validator.

Record grid dimensions, rounding, horizon bound, threads, solver seed, wall
limit, formulation hash, incumbent, best bound, solver status and validator
status. Distinguish `OPTIMAL` for the finite encoded model, `FEASIBLE`,
`INFEASIBLE`, `UNKNOWN`/timeout and invalid model/plan. A finite grid optimum is
not automatically a global continuous optimum; a restrictive model's lower bound
is not automatically a bound for the unrestricted problem. Only an explicit
equivalence proof permits that claim. Grid resolution, error tolerance and
budgets remain owner-review choices before Step 06, not installed settings.

## Separate Project 04 Maskable PPO (Steps 08–11)

One centralized agent controls both cranes. It is separate from the Project 03
berth PPO. New observations, actions and makespan reward require new training;
Project 03 weights are not transferable by default. Independent two-crane agents
would introduce coordination/nonstationarity risks; monolithic berth+crane+yard
PPO is deferred until specialists and interfaces have independent evidence.

Candidate fixed-shape input: two crane slots (position, mode, remaining travel/
setup/process and availability); M stable task slots (bay position, moves,
release/ready/completed status, operation type, remaining work, assigned crane);
rail/reach/separation and current-time/next-visible-event features; padding and
visibility masks. M, scales, clipping, overflow rejection and dtypes are design
review items. Slot IDs never silently change meaning mid-episode; oversized input
is rejected or explicitly handled, not truncated to easier work.

Candidate action index `0=WAIT`, `1+k*M+slot` for `(crane,task)`, zero-based k.
A legal assignment commits an independently checked immediate trajectory and job;
moving/busy crane, hidden/unready/completed job, conflicts and padding are masked.
Masks use current visible information only and share validator semantics without
substituting for final validation. Fixed task slots alone do not solve yielding:
Step 09 must review reposition actions or disclose restricted reachability.

Proposed reward is `r_n=-(t_next-t_now)/tau`, tau>0 fixed from training-only design;
successful undiscounted episode return telescopes to `-T/tau`. Zero-time safe
dispatches give zero reward and cannot repeat indefinitely: a job is committed
once and same-time choices are finite. WAIT must consume strictly positive time
or terminate as failure, never collect positive reward or skip mandatory work.
Use an explicit finite H; proposed failure penalty `-(H+delta)/tau`, delta>0,
on invalid/incomplete termination makes failure worse than any successful T<=H
for undiscounted accounting. Coefficients, discount, horizon and handling of
library-imposed truncation must be reviewed; discount gamma<1 breaks this simple
equivalence and must not be described as identical makespan optimization.
No secondary KPI shaping is silently added. Evaluation uses validity and T,
never episodic reward alone. Terminal penalties do not replace hard constraints.

Required design reviews before execution:

| Review | Must demonstrate / freeze before next stage |
| --- | --- |
| Step 08 | Observable state/events, causal boundary, one clock, deterministic simultaneous events, WAIT progress, exact success/deadlock/truncation; compatibility with static physics |
| Step 09 | Tensor shapes/overflow/scales/slot stability; action grammar including yield decision; mask-validator agreement; no hidden information; reward telescoping and failure bound; discount/truncation audit; freeze environment/observation/action/reward versions |
| Step 10 | Reviewed training budget, multiple training seeds, split fingerprints, reproducible dependencies/hardware, validation-only selection rule, complete checkpoint sidecars and failure retention; no test access |
| Step 11 | Frozen selected checkpoints, paired test plan and multiplicity, scenario-first seed nesting, information-matched comparators, quality/feasibility/latency and negative-case analysis; retain uncertainty rather than claiming superiority |

## Proposed scenario and experiment matrix

Every row is synthetic and uncalibrated; dimensions are independent fields.
No workload distributions, rates, speeds or safety coefficients are approved here.

| Family / scientific role | Bay count vs job count vs moves | Future comparisons and coverage |
| --- | --- | --- |
| Tiny / hand verification | 5 bays proposed; explicitly enumerated small jobs; moves chosen separately | All four heuristics, bounded CP-SAT, later PPO; hand optimum only where actually proved; safe equality, zero travel, same-bay jobs, two moving paths |
| Small / routine development | 8–12 bays proposed; job count independently specified | Same physics; all baselines; CP-SAT status/gap where supported; workload asymmetry, initial positions and safe cuts |
| Medium / heterogeneity | 15–25 task groups proposed; bay count NOT inferred | Four heuristics and budgeted CP-SAT; later PPO; paired scenario quality/feasibility/latency, uneven jobs/reach |
| Heavy / stress | Separate high-move workloads and denser/severe interference; counts pending | Travel and clearance stress, solver budget exits, safe path validation; no automatic empirical realism claim |
| Dynamic diagnostic / later extension | Releases, delays or crane availability under new version | Matched visible-state dispatch/replanning versus PPO; offline CP-SAT separately labeled oracle; hidden-future mutation diagnostics |
| Negative/degenerate / correctness | Empty jobs, unreachable bay, impossible clearance, malformed identities | No performance ranking; expected rejection/certified impossibility versus uncertified timeout; no fabricated successful episodes |

Coverage targets are categorical here: each invariant's positive and negative
fixture, both crossing paths, both orientations, boundary equality, simultaneous
completions, skewed work and legal WAIT/deadlock must be represented before
benchmarking. Numerical sample sizes/distributions and power considerations are
pending protocol review. Generated seeds or favorable trial runs must not be used
to choose test coverage after observing outcomes.
