# Scientific Experiment Protocol

Protocol `itp_protocol_v1`. Items marked PROPOSED must be resolved
before any validation comparison is read. The complete protocol is locked
before the held-out test campaign (§9).

## 1. Research questions and estimands

### S1 — Transfer of existing BAP policies (FROZEN)

*Do the relative performance characteristics of frozen berth-only policies
change when the same berth decisions are executed inside a terminal with
shared crane resources and yard constraints?*

Policies: Online FCFS (A1), berth-only Online Rollout (A2), frozen Dynamic
PPO seeds 11/23/37 (A3). Project 03 held-out evidence, which is context only and
not re-tested: PPO improved on FCFS but stayed behind Rollout in total waiting
(medium/heavy, H = 240). No ordering is assumed for Project I.

For policies X, Y and scenario s:

```text
Δ_ref(X,Y;s) = KPI_ref(X;s) − KPI_ref(Y;s)   # Project 03 DynamicBAPEnv on the berth projection (nominal service)
Δ_int(X,Y;s) = KPI_int(X;s) − KPI_int(Y;s)   # integrated kernel, same crane/yard primitives for X and Y
S1 estimand:  E_s[ Δ_int(X,Y;s) − Δ_ref(X,Y;s) ]   (difference in differences)
```

Plus: the rank order of mean KPI under ref vs. int; the per-scenario
sign-agreement rate of `Δ_ref` and `Δ_int`; and Kendall τ of per-scenario
policy rankings. The S1 primary KPI is total turnaround in both worlds
(in the reference, turnaround = waiting + nominal service, so it orders policies
exactly as total waiting does). Total waiting is secondary.

### S2 — Value of integrated coordination (FROZEN)

*Does explicitly accounting for berth, quay-crane and yard information improve
terminal-wide performance compared with independent decision policies running
in the same physical terminal?* Estimands are the paired contrasts of §3. A
null or negative result is a valid outcome.

## 2. Mechanisms kept distinct

| Mechanism | Definition | Where it varies |
| --- | --- | --- |
| Shared physical constraints | Cranes, transport and yard limit realized service | Never varies between arms. Always active in execution (S1 compares *against* the reference world without them) |
| Independent decisions | Berth rule uses berth-only information; crane and yard follow fixed primitives | A1, A2, A3 |
| Information-aware decisions | Berth rule reads crane, transport and yard state | B1, B2 (A1n uses the same rule with berth-only information) |
| Short-horizon predictive evaluation | Candidate actions scored by forward simulation of the visible cohort | A2 (berth-only model), B2 (integrated model) |
| Computational budget | Search breadth and depth, plus wall-clock | Breadth and depth equal for A2 and B2; wall-clock reported for all |

## 3. Arms

Crane policy **P_c** and yard policy **P_y** are the Step 3 primitives and are
**identical in every arm** (FROZEN for the primary factorial):

- P_c — greedy by berth order: at each CRANE decision, berthed vessels with
  remaining work are visited in `(berth_start_time_min, vessel_id)` order. Each
  receives available cranes in `crane_id` order up to `max_cranes`. This is the
  Project 02 `GreedyCranePolicy` rule lifted from tasks to vessels.
- P_y — first fit: the first OPEN block in `block_id` order that supports the
  group's capabilities and size and passes the TEU test. This is the Project 02
  `FirstFitYardPolicy` rule.

| Arm | Berth decision rule | Information for berth decisions | Forward model | WAIT | Role |
| --- | --- | --- | --- | --- | --- |
| **A1** | Online FCFS (Project 03 `online_fcfs_action`) | berth-only | none | never | Primary |
| **A1n** | Greedy minimum *estimated release time* over all legal (vessel, position); ties by FCFS key; estimates from **nominal** service | berth-only | none | never | Secondary control (separates the rule change from the information change) |
| **B1** | Same greedy rule as A1n, estimates from the **integrated one-step estimator** (crane availability, multi-crane efficiency, transport distance from the candidate position to the vessel's load and preview-discharge blocks, current yard congestion) | berth + crane + yard | none | never | Primary |
| **A2** | Project 03 `online_rollout_choice` on the adapter's visible state | berth-only | berth-only nominal (visible cohort, FCFS continuation) | yes | Primary |
| **B2** | Integrated rollout: same candidate set as A2 (all legal actions plus WAIT if legal); each scored by an `observable_clone()` kernel run of the visible cohort to completion with FCFS berth continuation and P_c/P_y; score = visible-cohort total turnaround; tie-break by action index | berth + crane + yard | integrated kernel (same physics) | yes | Primary |
| **A3** | Frozen Dynamic PPO, each of seeds 11, 23, 37 (medium/heavy checkpoints), gate PASS-FORECAST | berth-only (`dynamic_obs_v1`) | none | yes (learned) | S1; reported in S2 tables |
| **B3** | Optional: B2 with candidates pruned or ordered by PPO top-k | berth + crane + yard | integrated | yes | Exploratory; not part of any primary claim; requires gate PASS |

A2's score (visible-cohort waiting under nominal service) is monotone in
visible-cohort turnaround under its own model. A2 and B2 therefore optimise the
same objective and differ only in the forward model. The integrated one-step
estimator (B1) and the B2 forward-model details are fixed in Step 6, using
development data only.

## 4. Contrasts

Paired per scenario (same exogenous inputs, same physics, same split).

| Contrast | Estimates | Does **not** estimate |
| --- | --- | --- |
| **C1 = B1 − A1** | Total effect of an information-aware greedy berth rule versus FCFS | Pure information value (it also changes the rule) |
| C1a = A1n − A1 | Effect of the greedy rule itself under berth-only information | — |
| **C1b = B1 − A1n** | Value of integrated information within a fixed greedy rule (no search) | Value under search |
| C2 = A2 − A1 | Value of berth-only lookahead (search and WAIT) over FCFS | Integration |
| **C3 = B2 − A2** | Value of the integrated forward model at equal search breadth and depth (main S2 contrast) | Computation-matched value (B2 costs more wall-clock; reported) |
| C4 = (B2 − A2) − (B1 − A1n) | Interaction: is integrated information worth more with search? | — |
| C5 = B2 − A1 | Total difference | **Not** a pure coordination effect (it bundles rule, search, WAIT, information and compute) |
| C6 = A3 − A1, A3 − A2 | Frozen PPO standing in the integrated terminal | Crane or yard awareness (PPO has none) |

**Primary family (Holm-adjusted, α = 0.05):** C1b and C3. All other
contrasts are secondary or descriptive.

## 5. Computational budget control

- Structural budget (FROZEN): A2 and B2 evaluate the same candidate set and
  roll out the same visible cohort to completion under the same continuation
  rule. The only difference is the forward model's physics.
- Wall-clock (reported, never used to rank): mean, median, P95 and max
  decision time per epoch; total decision time per episode; forward
  simulations per decision; kernel events simulated in forward models. CPU,
  single thread, hardware and Python and package versions recorded. Model
  loading is excluded, following the Project 03 latency convention.
- If B2's mean decision time on development scenarios exceeds 2.0 s
  (PROPOSED cap), a pre-registered cohort cap (maximum visible vessels rolled
  out, chosen on development data only) applies to **both** A2 and B2, and is
  frozen before validation.

## 6. Scenario splits, seeds and randomness

### 6.1 Seed bands (FROZEN after collision audit)

| Split | Scenario seeds | Use |
| --- | --- | --- |
| development | 10,000,000 – 10,999,999 | Implementation, debugging, timing, design of B1/B2 internals |
| validation | 11,000,000 – 11,999,999 | Confirmation of PROPOSED items; selection among pre-declared policy-internal options |
| test (held-out) | 12,000,000 – 12,999,999 | Final campaign only, generated after the protocol lock |
| diagnostic | 13,000,000 – 13,999,999 | Step 8 ablations and sensitivity (fresh scenarios, not the test set) — PROPOSED addition to the three bands in the brief |

### 6.2 Collision audit (performed in Step 1)

| Existing reservation (source) | Range | Collision with Project I bands? |
| --- | --- | --- |
| Project 03 static validation / test / diagnostics (`configs/rl/static_ppo_*`) | first seeds 1,000,000 / 2,000,000 / 3,000,000 (a few hundred seeds each) | No |
| Project 03 dynamic validation / test / diagnostics (`configs/rl/dynamic_ppo_*`, `rl/dynamic_config.py` lower bounds 5M/6M/7M) | first seeds 5,000,000 / 6,000,000 / 7,000,000 | No |
| Project 03 future diagnostic reservation (`benchmark/runner.py`: `"8000000+; no instances generated"`) | Written open-ended; every other Project 03 region is a 1M-wide band | No under the 1M-band convention. Under a literal open-ended reading the *numbers* overlap, but no instances exist and generation namespaces are disjoint (§6.3) |
| Project 03 PPO training sampling (`static_scenario_provider.py`: `SAMPLED_SEED_LIMIT = 2**31 − 1`, train split `seed % 3 == 0`) | the entire train-split integer range | Numerically unavoidable for any band. Disjoint by namespace (§6.3) and checked by fingerprint audit (§6.4) |
| Project 02 scenario files | seed 42 | No |
| Project 03 bootstrap seed (`configs/benchmark/step12_dynamic_h240.yaml`) | 12012 (analysis seed, not a scenario seed) | No |
| PPO training seeds | 11, 23, 37 (training identities, not scenario seeds) | No |

A regex search (`\b1[0-3]_?\d{3}_?\d{3}\b`) over all tracked `.py`, `.yaml`,
`.yml`, `.md`, `.json` and `.toml` files found no use of the 10M–13M range.

### 6.3 Namespaced, entity-keyed exogenous streams (FROZEN)

A Project I seed is **never** passed to a Project 03 generator or provider.
Every exogenous draw comes from a stream keyed by stable identities:

```text
stream_seed(key) = int.from_bytes(sha256(
    f"itp_v1|{family}|{split}|{scenario_seed}|{entity_kind}|{entity_id}|{attribute}"
).digest()[:8], "big")
```

This is the Project 02 `RandomStreams.derive_seed` hashing pattern with a
Project I namespace and entity keys. Examples:
`vessel|V007|interarrival`, `vessel|V007|length`, `vessel|V007|manifest_size`,
`container|CNT-000417|size`, `container|CNT-000417|pickup_delay`. Consequences:

- Exogenous inputs are materialized in the scenario before any policy runs.
  A policy can never change them (DQ17).
- Adding or changing one attribute's distribution does not shift other
  attributes' draws.
- Identical seeds in two families give unrelated scenarios.

### 6.4 Fingerprint audits (Step 2 gate)

- Project I `physical_fingerprint`s are unique across all Project I splits.
- No Project I `berth_projection_physical_fingerprint` equals the Project 03
  `physical_fingerprint` of any regenerated Project 03 validation, test or
  diagnostic suite instance, or of the historical tiny fixtures
  (`rl/suites.py::historical_fixture_fingerprints`).
- Results are stored in the Step 2 audit manifest.

### 6.5 Scenario families and counts (PROPOSED; confirmed at Step 2, frozen before validation)

| Family | Vessels | Mean inter-arrival | Vessel length | Workload | Purpose |
| --- | --- | --- | --- | --- | --- |
| `itp_medium` | 16 | 190 min | U[200, 360] m | U{250…900} moves | In PPO medium/heavy support |
| `itp_heavy` | 24 | 120 min | same | same | In PPO medium/heavy support (M = 24) |

Counts: validation 20 per family; test 50 per family (100 total, matching
the Project 03 medium/heavy held-out size); diagnostic 20 per family per
condition. Counts may only be changed before validation results are read.

### 6.6 Identities recorded per run

`scenario_id`, all fingerprints (data contract §10), split, scenario seed,
family, arm id and version, policy versions, forecaster version, PPO training
seed and checkpoint SHA-256 (A3/B3), physics config hash, protocol lock hash,
git commit and dirty flag, package versions.

## 7. KPIs

### 7.1 Primary KPI (FROZEN, D24)

```text
T_end(s)        = last_arrival_min(s) + max_drain_extension_min       # scenario-fixed, policy-independent
turnaround_i    = min(departure_i, T_end) − arrival_i                 # minutes; departure_i = ∞ if never departed
total_turnaround(s) = Σ_i turnaround_i over all vessels of s          # vessel-minutes, lower is better
mean_turnaround(s)  = total_turnaround(s) / n_vessels(s)
```

Every vessel of the scenario is always included. Unfinished vessels are
charged up to the scenario-fixed `T_end`, never to an earlier deadlock or
truncation time. An arm cannot gain by leaving vessels unfinished or by
stopping early.

### 7.2 Secondary KPIs

| KPI | Unit | Definition / denominator |
| --- | --- | --- |
| total berth waiting | vessel-min | Σ (`berth_start` or `T_end`) − arrival |
| mean, P95 berth waiting | min | over all vessels; P95 = `numpy.percentile(..., 95)` (linear) |
| mean realized occupancy | min | mean (departure − berth_start) over departed vessels |
| mean handling duration | min | mean (handling_end − handling_start) |
| crane productive / idle / blocked time | crane-min | Σ over cranes over [0, makespan]; blocked split by reason |
| crane utilization | fraction | productive crane-min / (n_cranes × makespan) |
| crane rate shortfall | moves | ∫ (crane_rate − allocated rate) dt / 60 |
| peak yard occupancy | TEU | max over t of Σ_b occupied_teu_b |
| peak block occupancy fraction | fraction | max over b, t of occupied_teu_b / capacity_teu_b |
| mean yard occupancy fraction | fraction | time-weighted over [0, makespan] of Σ occupied / Σ capacity |
| yard-blocked crane time | crane-min | crane time BLOCKED(YARD_CAPACITY) |
| gate waiting | container-min | Σ time containers spend AT_GATE |
| pickup delay | min | mean and P95 of (release completion − scheduled pickup) |
| container throughput | containers | completed exits (RELEASED_TO_LANDSIDE + DEPARTED_BY_VESSEL) |
| TEU throughput | TEU | Σ `size_teu` of completed exits |
| crane moves / yard moves completed | moves | ledger counts (foundation §5) |
| conservation status | pass/fail | foundation §8.3 audit |
| unfinished workload | moves | ship-side moves not completed at episode end |
| rolled-over containers | containers, TEU | D17 |
| invalid physical actions | count | validator rejections; any > 0 marks the run FAILED |
| decision computation time | ms per epoch; s per episode | §5 |
| makespan | min | last departure, or `T_end` if incomplete |
| completion status | category | integration specification §9 |

Container count, TEU and crane moves are reported separately and never summed
together.

## 8. Incomplete and invalid cases

| Run outcome | KPI treatment | Comparison treatment |
| --- | --- | --- |
| COMPLETED | as defined | included |
| TRUNCATED_DRAIN_LIMIT, DEADLOCK | censored at `T_end` (§7.1); unfinished counts reported | included; completion rate per arm reported next to every table |
| FAILED (invariant, validation, livelock, illegal action) | none | the scenario is excluded from paired contrasts involving that arm; listed by id; any test-set FAILED is reported as a defect |
| A3 BLOCK (gate) | none | A3 unsupported on that scenario; reported, not imputed |
| EXOGENOUS_INPUT_DRIFT | none | all arms of that scenario quarantined |

## 9. Pre-registration and held-out lock (FROZEN)

1. **Step 2 end:** physics coefficients, families and generator are frozen
   *before any arm comparison is run on any split*. Coefficients are chosen a
   priori (documented rationale) and never tuned to results.
2. **Steps 5–6:** development data for implementation and timing. Validation is
   used only to (a) confirm that PROPOSED items behave as intended (no
   degeneracy, deadlock rate below 5 %), and (b) choose among pre-declared
   options inside B1/B2 by a pre-declared rule (best validation mean total
   turnaround, ties to the simpler option). The test split is not generated.
3. **Step 7 start — lock:** write `protocol_lock_v1.json` exclusively
   (`open(..., "x")`) with a `.sha256` sidecar, from a clean Git worktree. It
   contains hashes of these documents and all configs, physics coefficients,
   arm and policy versions, forecaster version, checkpoint hashes, family
   definitions, test seed list, analysis plan (contrasts, bootstrap seed,
   Holm family) and the Step 8 sensitivity ranges (§11).
4. Test scenarios are generated only by a script that verifies the lock
   first. This follows the Project 03 `verify_dynamic_test_gate` pattern.
5. After test results are read, no parameter, arm or analysis change may be
   presented as confirmatory. Deviations are amendments, and their results are
   labelled exploratory.

## 10. Statistical analysis

- Unit of analysis: scenario. All contrasts are paired differences
  `Δ(s) = KPI(X;s) − KPI(Y;s)`.
- Family-weighted mean: 0.5 × `itp_medium` + 0.5 × `itp_heavy` (Project 03
  convention); per-family means are also reported.
- Uncertainty: deterministic stratified (by family) scenario bootstrap,
  10,000 resamples, percentile 95 % CI, bootstrap seed `120001` (PROPOSED;
  analysis namespace). For A3, the three seeds are reported individually and as
  the scenario-first three-seed mean. Intervals are conditional on the three
  frozen models and do not measure training-seed uncertainty.
- Claims: "X better than Y" requires a Holm-adjusted CI (primary family) or
  95 % CI (secondary) entirely below 0. "Worse" requires a CI entirely above 0.
  Otherwise "no detectable difference". Wilcoxon signed-rank p-values are
  reported as a robustness check, not as the decision rule.
- Tail reporting: per-scenario win/tie/loss counts, P95 and worst `Δ(s)` with
  scenario ids (Project 03 tail-risk convention).

## 11. Ablations and sensitivity (Step 8; ranges FROZEN at the lock, PROPOSED now)

**Coordinator information ablations.** B2's forward model with couplings
switched on or off. Execution physics is always full.

| Variant | Forward model crane coupling (A) | Transport (B) | Yard (C) |
| --- | --- | --- | --- |
| none | off (nominal 0.5 min/move per vessel) | off | off |
| crane-aware | on | off | off |
| yard-aware | off (nominal) | on | on |
| both (= B2) | on | on | on |

"none" must reproduce A2's decisions on the same states. Disagreement
indicates an implementation inconsistency and blocks Step 8 interpretation.

**Sensitivity** (one factor at a time around base; arms A1, A2, B2, A3; 20
diagnostic scenarios per family per condition):

| Factor | Levels |
| --- | --- |
| Crane fleet size | 4, 6, 8 |
| Crane nominal moves/h | 25, 30, 35 |
| Multi-crane efficiency | Project 02 table; ideal (all 1.0) |
| Transport units per crane / speed | 3, 4, 6 / 150, 250, 400 m/min |
| Yard handling capacity | × 0.5, × 1, × 2 |
| Congestion strength `g_min` | 1.0 (off), 0.5, 0.3 |
| Initial yard occupancy fraction | 0.3, 0.5, 0.7 |

Predictive-model computation cost is reported separately for every variant.

## 12. Allowed and disallowed claims

Allowed: paired, synthetic, conditional statements about the arms on the
frozen families, with intervals and completion rates.

Not allowed: real-terminal productivity or ROI; optimality (Rollout is a
heuristic); crane-aware or yard-aware PPO; a "coordination effect" read from
C5; any statement about scenarios outside the families; reuse of Project 03
held-out results as Project I evidence.
