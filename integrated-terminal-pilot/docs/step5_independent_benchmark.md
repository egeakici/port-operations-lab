# Step 5 — Independent Integrated Benchmark

Step 5 connects the Project 03 frozen berth policies to the Step 4 integrated terminal through one
observable, deterministic adapter. A1, A2 and A3 can now act on the same physics as arms of S1.
It implements and verifies the arms. It is **not** the S1 experiment: every run here is a
development diagnostic, the protocol lock is BLOCKED
([step5_protocol_readiness.md](step5_protocol_readiness.md)), and no arm is ranked.

## 1. Architecture

```text
TerminalKernel (Step 4, unchanged physics)
   │ advance() → DecisionRequest(BERTH)
   ▼
kernel.berth_view()  ──►  BerthView (immutable; revealed vessels, forecasts, physical legal set, WAIT bit)
   │
   ▼
benchmark.adapter.adapt_berth_view      G08 legal set = Project 03 candidates, G09 ≤ P, G10 slots, G17 forecast > now
   │                         │                                  │
   ▼                         ▼                                  ▼
A1 online_fcfs_action   A2 online_rollout_choice(DynamicVisibleState)   A3 encode_dynamic_observation → MaskablePPO.predict
   (Project 03, unchanged)    (Project 03, unchanged)                      (Project 03 encoder + frozen checkpoint, CPU)
   │
   ▼
BerthAction (WAIT | ASSIGN vessel, continuous position)   G19: outside the mask → run FAILED, no repair
   │
   ▼
kernel.apply_berth_action → PhysicalActionValidator (Step 4, identical for every arm)
   │
   ▼
primitive_crane_greedy_v1 (P_c) + one declared common P_y profile → crane, transfer, yard, landside physics
```

Policy injection uses the existing Step 4 `run_episode(kernel, berth_policy=…)` path. There is no
second simulator and no physics change. The only Step 4 edit is backward compatible: `run_episode`
also records per-berth-decision view-build, decide and apply wall times in `EpisodeRun.berth_timings`.
All Step 4 tests pass unchanged.

| Module (`src/integrated_terminal_pilot/benchmark/`) | Content |
| --- | --- |
| `adapter.py` | `adapt_berth_view`, `AdaptedBerthState`, `visible_state` (A2 input), `P03ObservationHost` + `dynamic_observation` (A3 input) |
| `policies.py` | `BerthPolicy` interface, `OnlineFcfsBerthPolicy` (A1), `OnlineRolloutBerthPolicy` (A2), `FrozenPpoBerthPolicy` (A3), registry `create_berth_policy(arm, training_seed=…)` |
| `checkpoints.py` | six-checkpoint inventory, audited hashes, gates G01–G04/G21, read-only cached CPU loading |
| `profiles.py` | yard profiles (`protocol_v1_first_fit` default, `am01_balanced_diagnostic`), live approval state |
| `runner.py` | `run_arm`: one arm on one scenario, provenance-complete record, per-scenario A3 support gate |
| `exact_gate.py` | PASS-EXACT gate against Project 03 `DynamicBAPEnv` |
| `development.py` | CLI: `--check-compatibility`, `--dry-run`, `--smoke`, `--report`, `--exact-gate` |

## 2. Policy versions

| Arm | `policy_id` | Project 03 code | Notes |
| --- | --- | --- | --- |
| A1 | `a1_p03_dynamic_online_fcfs_v1` | `dynamic_fcfs.online_fcfs_action` (`dynamic_online_fcfs_v1`) | key (arrival, vessel_id, position); never WAITs |
| A2 | `a2_p03_dynamic_online_rollout_v1` | `dynamic_online_rollout.online_rollout_choice` (`dynamic_online_rollout_v1`) | berth-only visible-cohort rollout |
| A3 | `a3_p03_dynamic_maskable_ppo_v1_medium_heavy_train_seed{11,23,37}` | `dynamic_maskable_ppo_v1`, `dynamic_obs_v1`, M = 24, N = 1153, H = 240 | one arm row per training seed; hash recorded per run |

Adapter version `itp_berth_view_adapter_v1`. Hashes and the PASS/BLOCK matrix are in
[step5_bap_compatibility_report.md](step5_bap_compatibility_report.md).

## 3. Decision timing, WAIT and information boundary

- **Epochs.** A berth decision opens only after a D07 epoch event (arrival, departure, horizon
  entry) when a legal immediate assignment exists. After an assignment, the kernel re-queries at the
  same timestamp. This is the Project 03 `DynamicBAPEnv` timing; the PASS-EXACT gate reproduces it
  decision by decision.
- **WAIT** is legal iff an assignment is legal **and** a visible future event exists (an announced
  vessel with arrival > now, or an occupying vessel, whose forecast is > now). A WAIT ends the
  berth phase; the next decision comes at the next epoch event, so a WAIT can neither loop at one
  time nor skip exogenous events. An illegal WAIT fails the run (tested).
- **What a berth policy sees.** Only the `BerthView`: vessels revealed by H = 240 announcement or
  arrival, their status, exact arrival, length, nominal service, actual berth position and start,
  the ServiceForecaster v1 release of occupying vessels, the physical legal set and the WAIT bit.
- **What it never sees.** Unannounced vessels, gate-in and pickup schedules, yard inventory or
  occupancy, crane state, work orders, the event queue, realized future completions, scenario seed
  or fingerprints, and any kernel clone. The policy objects never receive the kernel. Passing one
  raises G20, and the source contains no kernel, clone or queue access (tested). Perturbing hidden
  future arrivals, pickup times and yard capacity leaves every view and every A1/A2/A3 decision
  identical (tested).

## 4. Nominal versus realized service

| Quantity | Value seen by policies | Rule |
| --- | --- | --- |
| Vessel service in `vessel_features[:,2]`, rollout inputs | nominal `30 + 0.5·moves + 20` (D20), immutable | never replaced by realized work |
| End of occupancy of a berthed vessel | `estimated_release` (ServiceForecaster v1, current state only) | strictly > now while the vessel is at the quay; violation = kernel defect (G17), never clamped |
| Quay availability | actual occupancy until `VESSEL_DEPARTED` | a nominal or forecast end never frees quay |
| Waiting vessel | nominal service only; no realized remaining work | same for all arms |

The same adapted state feeds A1 (choice table), A2 (visible state) and A3 (observation), so every
arm sees identical information. Unavoidable differences come from the algorithms: FCFS ignores
times; Rollout projects occupying vessels to their forecast and unstarted vessels to nominal;
PPO reads the forecast through the frozen feature, a declared distribution shift.

Tested cases (overrun fixture, `tests/step5_support.py`):

- **Overrun.** V001's nominal end is 75 and it departs at 150. At t = 100 the view shows a release
  of 150, the placement ends at 150 (not 75), the legal set excludes [0, 380), and an ASSIGN there is
  rejected `BERTH_OCCUPIED` with no state change.
- **End-time update.** The same vessel showed 75 at t = 0 (EXACT) and 150 at t = 100
  (FORECAST-substituted).
- **Zero remaining work, departure prep pending.** At t = 140 V001's handling has ended (130); it
  remains OCCUPYING with release 150.
- **Exact boundary.** V005 arrives at 150, exactly when V001 departs. The departure (priority 30)
  is processed before the decision, so V001 is DEPARTED and position 0 is legal.
- **Waiting vessel with cargo.** The view exposes nominal service only (no realized estimate).

## 5. Common crane and yard policies, fairness

Every arm uses `primitive_crane_greedy_v1` and one declared yard profile:
`protocol_v1_first_fit` (`yard_first_fit_v1`, frozen protocol default) or the labelled
`am01_balanced_diagnostic` (`yard_occupancy_balance_v1`, AM-01 PROPOSED). Runs use the scenario's
own fleet (four cranes, the approved reference) with the `assigned` efficiency basis.
`comparison_fingerprint` hashes the scenario, physical, exogenous, physics-config and resource
fingerprints, the crane count, the efficiency basis, P_c and P_y. It contains no berth-policy
identity and is asserted equal across all arms of a scenario and profile (tests and smoke report).
Rejections are handled identically: any validator rejection or gate failure marks the run
`FAILED` with its code. There is no repair, no fallback policy and no extra drain time.

## 6. Metrics, compliance and censoring

Each run record (`itp_step5_run_v1`) contains:

- **Identity:** scenario id/family/split/seed, all scenario fingerprints, the arm with
  `ppo_training_seed` kept separate from `scenario_seed`, policy description (checkpoint path and
  hash, inference configuration, search budget), shared components, comparison fingerprint.
- **Outcome:** terminal status (COMPLETED / TRUNCATED_DRAIN_LIMIT / DEADLOCK / FAILED / BLOCKED),
  failure code, rejections, end time and `T_end`.
- **Cargo compliance (Step 4 closure `service_compliance`):** departed versus cargo-fulfilled
  vessels, required and completed ship moves, rolled-over containers and moves, unfinished moves,
  completion ratio, completed-only mean turnaround with its denominator, and the restricted
  observed turnaround with its horizon definition.
- **KPIs (protocol section 7):** the T_end-censored total turnaround (D24, every vessel), mean/P95
  waiting, occupancy, handling, crane productive/idle/blocked time, yard occupancy, gate and pickup
  delays, container / TEU / move throughput (never summed together), makespan.
- **Time decomposition and per-vessel rows** with move reconciliation
  (`required = completed + rolled over + unfinished`), container status counts at stop
  (gate and pickup backlog), and the realized/nominal occupancy ratio.
- **Decisions:** count, WAITs, legal-WAIT epochs, legal assignments per epoch, timeouts (always 0;
  no cap exists), EXACT/FORECAST epoch counts, wall-time statistics (view build, adapter incl. mask
  derivation, policy, encode, inference, rollout runtime, apply), rollout root evaluations, PPO
  support diagnostics.
- **Trace digest** (`itp_trace_v1`, summary or full; identical digest in both modes) and
  engineering times. Checkpoint load and policy setup are recorded separately and excluded from
  run time.

No departure-only success is claimed, and no weighted scalar is defined. The cargo-compliance
criterion is a pending proposal ([step5_protocol_readiness.md](step5_protocol_readiness.md) section 4).

## 7. Verification results

Environment: Windows 11, Python 3.13.2, torch 2.6.0+cpu (1 inference thread), sb3-contrib 2.8.0.
HEAD `60b340d` plus the uncommitted Step 5 changes.

**Compatibility check** (`--check-compatibility --exact-scenarios 4`): 11/11 source assertions PASS.
Six checkpoint static gates (G01–G03 and sidecar) PASS. G04 loads PASS for medium/heavy seeds
11/23/37. G18: repeated inference on a 16-epoch fixture is identical. G19: all actions are in the
mask. Arm status: A1 PASS, A2 PASS, A3-train11/23/37 PASS, tiny 11/23/37 BLOCK (G12/G11).
Hashes are unchanged before and after.

**PASS-EXACT gate** (`--exact-gate`; 80 degenerate development scenarios × 5 arms; 1,806 s):

| Arm | Scenarios passed | Scope FULL / PREFIX | Decisions compared | WAITs compared |
| --- | --- | --- | --- | --- |
| A1 | 80 / 80 | 80 / 0 | 1,460 | 0 |
| A2 | 80 / 80 | 78 / 2 | 1,534 | 86 |
| A3-train11 | 80 / 80 | 75 / 5 | 1,442 | 15 |
| A3-train23 | 80 / 80 | 77 / 3 | 1,447 | 0 |
| A3-train37 | 80 / 80 | 73 / 7 | 1,462 | 58 |

Every compared decision has the same time, Project 03 action index, vessel and position, and an
adapter observation bit-equal to Project 03's (7,345 of 7,466 integrated decisions compared). All
17 PREFIX cases diverge because a vessel berthed before its cargo was available
(`CARGO_UNAVAILABLE`, with rollover), after which realized occupancy legitimately differs from
nominal (compatibility report section 5).

**A1 = Step 4 fixture:** byte-identical canonical traces apart from the policy id (low seed
10,000,000 standard physics; overrun fixture). The Step 4 FCFS 80/80 degenerate-equivalence gate
was re-run and passes 80/80 (section 9).

**Development smoke** (`--smoke --run-id s5dev_smoke_v1`; plan `1f19cc66…`; 50 items: 20 primary
first-fit runs, 5 balanced diagnostics, 5 determinism repeats, 20 Project 03 berth-only
references; development seed 10,000,000 of each family). Report:
`experiments/step5_development/s5dev_smoke_v1/reports/report_633d46da8f5d.md`.

| Family | Arm | Status | Departed | Cargo fulfilled | Rolled over | Unfinished moves | T_end-censored total turnaround (vessel-min) | WAITs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | A1 / A2 / A3-11 / A3-23 / A3-37 | all COMPLETED | 8/8 each | 8 each | 0 | 0 | 16,547 / 17,009 / 16,535 / 16,535 / 16,817 | 0 / 1 / 0 / 0 / 0 |
| medium | A1 / A2 / A3-11 / A3-23 / A3-37 | all COMPLETED | 16/16 each | 16 each | 0 | 0 | 60,306 / 60,250 / 55,420 / 55,405 / 55,314 | 0 / 0 / 0 / 7 / 2 |
| heavy | A1 | TRUNCATED_DRAIN_LIMIT | 19/24 | 19 | 0 | 2,514 | 152,324 | 0 |
| heavy | A2 | TRUNCATED_DRAIN_LIMIT | 19/24 | 16 | 90 | 3,192 | 149,055 | 3 |
| heavy | A3-11 / A3-23 / A3-37 | TRUNCATED_DRAIN_LIMIT | 20 / 18 / 19 | 17 / 16 / 17 | 66 / 58 / 53 | 3,093 / 3,795 / 3,240 | 138,076 / 142,340 / 139,683 | 9 / 39 / 9 |
| bottleneck | A1 | TRUNCATED_DRAIN_LIMIT | 10/18 | 10 | 0 | 3,495 | 143,938 | 0 |
| bottleneck | A2 | TRUNCATED_DRAIN_LIMIT | 13/18 | 9 | 206 | 3,311 | 129,907 | 0 |
| bottleneck | A3-11 / A3-23 / A3-37 | TRUNCATED_DRAIN_LIMIT | 12 / 12 / 12 | 5 / 6 / 3 | 405 / 264 / 475 | 3,844 / 3,550 / 3,986 | 127,322 / 131,135 / 126,774 | 13 / 35 / 8 |

Every run has 0 rejections, all physical audits OK, per-vessel move reconciliation OK and
identical comparison fingerprints within each scenario and profile. The five determinism repeats
reproduce their trace digests exactly. A3 per-decision inference averages 3–6 ms (policy P95
≤ 11 ms). A2 decisions average 0.003–0.52 s (P95 1.72 s, max 2.02 s on heavy). Checkpoint loads
take 0.06–2.1 s and are excluded. Every A3 run has FORECAST-substituted epochs. The occupancy
feature reaches 1.1–4.7 against a training maximum of 0.347; these are measured distribution-shift
diagnostics, not gate failures. Realized/nominal occupancy ratios reach 4.9–18.9 under the
provisional physics.

How to read this (development only): on heavy and bottleneck the arms with lower censored
turnaround also roll over far more cargo and fulfil fewer vessels. This is exactly the
"turnaround gain with cargo loss" pattern that the proposed cargo rule addresses, and it is why
departure or turnaround alone must not rank arms. One seed per family supports no conclusion. The
heavy and bottleneck truncations reproduce the Step 4 closure finding under first fit with four
cranes (pending decisions AM-01 and FLEET).

## 8. Commands (PowerShell, from `integrated-terminal-pilot`)

```powershell
python scripts/run_step5_independent_benchmark.py --check-compatibility
python scripts/run_step5_independent_benchmark.py --dry-run
python scripts/run_step5_independent_benchmark.py --smoke --policy A1 --progress
python scripts/run_step5_independent_benchmark.py --smoke --policy A2 --progress
python scripts/run_step5_independent_benchmark.py --smoke --policy A3 --checkpoint-seed 11 --progress
python scripts/run_step5_independent_benchmark.py --smoke --yard-policy am01_balanced_diagnostic --progress
python scripts/run_step5_independent_benchmark.py --report
python scripts/run_step5_independent_benchmark.py --exact-gate --progress
```

`--smoke` runs only the fixed predeclared plan (filters can narrow it, never widen it). It
refuses an existing `--run-id` unless `--resume` is given. Resume verifies the plan hash and the
selection, and writes every record exclusively. `--report` executes no simulation.

## 9. Test and regression summary

| Suite | Command | Result |
| --- | --- | --- |
| Step 5 unit | `python -m pytest -q tests/unit/test_step5_adapters.py` | 25 passed |
| Step 5 integration | `python -m pytest -q tests/integration/test_step5_benchmark.py` | 15 passed, 4 slow skipped (full PASS-EXACT gate, opt-in `ITP_RUN_SLOW=1`; run via CLI instead: 400/400) |
| Project I full | `python -m pytest -q` | 405 passed, 8 skipped (the opt-in Step 4 and Step 5 full gates) |
| Projects 01 / 02 / 03 | `python -m pytest -q` in each project | 426 / 55 / 471 passed |

## 10. Limitations

- Development diagnostics only, on one seed per family under provisional physics and the frozen
  first-fit P_y; nothing is validated or ranked.
- PASS-EXACT holds over the compared prefix. After a cargo-availability divergence, equality with
  Project 03 is not expected.
- Frozen PPO under forecast-substituted occupancy is out of its training distribution, by design
  of S1. It is neither crane-aware nor yard-aware.
- Inference uses torch 2.6.0 CPU. The checkpoints were trained with torch 2.14.1 on CUDA. CPU
  inference is deterministic and identical to Project 03's own CPU evaluation path, but
  equivalence with CUDA-time inference is not established.
- The A2 search has no time cap. Heavy decisions reach about 2 s, close to the protocol's
  PROPOSED 2.0 s B2 trigger, which applies equally to A2 and B2 (protocol section 5).
