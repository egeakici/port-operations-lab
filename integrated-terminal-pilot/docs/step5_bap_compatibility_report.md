# Step 5 BAP Compatibility Report

How the Project 03 frozen berth policies were connected to the Step 4 integrated kernel, with source
evidence, gate results and every unsupported condition. Implements
[bap_compatibility_contract.md](bap_compatibility_contract.md) without changing it.
Reproduce with `python scripts/run_step5_independent_benchmark.py --check-compatibility` (read-only)
and `--exact-gate` (development data only).

## 1. Project 03 sources audited (read-only)

| Module (`03-berth-allocation-lab/src/berth_allocation_lab/…`) | Symbols used | Finding |
| --- | --- | --- |
| `policies/dynamic_fcfs.py` | `online_fcfs_action(env)` | Reads only `env.legal_choices`; `min` by `(arrival, vessel_id, position)`; raises when no assignment exists; never WAITs |
| `policies/dynamic_online_rollout.py` | `online_rollout_choice(visible)`, `POLICY_ID = dynamic_online_rollout_v1` | Input is a `DynamicVisibleState` only (no env, no event queue). Scores every legal action (WAIT first when legal) by a visible-cohort FCFS continuation with fixed placement ends; WAIT advances to the next visible event and takes the best immediate assignment; tie-break by lowest action index. **No future-truth access.** `online_rollout_action(env)` is the only env-reading entry and is not used |
| `envs/dynamic_visible_state.py` | `DynamicVisibleState` | 9 fields: time, quay, clearance, H, vessels by slot, statuses, active placements, legal choices, WAIT bit |
| `envs/dynamic_bap_env.py` | `DynamicBAPEnv`, `_EVENT_PRIORITY`, `_cache_choices`, `action_masks`, `_has_visible_future_event` | Action 0 = WAIT, `1 + slot·P + c`, `P = 2M`; slots at first reveal in `(time, priority, vessel_id)` order, never reused; scenario vessel count ≤ M (no truncation); candidates = `candidate_positions` filtered by `is_placement_feasible`, indexed after filtering; WAIT legal iff an assignment exists and a revealed future event exists |
| `envs/dynamic_observation.py` | `encode_dynamic_observation(env)`, `build_dynamic_observation_space` | `dynamic_obs_v1`: 9 keys; time scale 1440 min, length scale 1000 m; placement end feature `(end − now)/1440` for IN_SERVICE vessels only |
| `rl/dynamic_checkpoint.py` | `load_dynamic_checkpoint(path, env, allow_cross_horizon=False)` | Checks sidecar ids, M, N, scales, reward scale, H, P; loads with `device="cpu"`; checks spaces and architecture |
| `rl/dynamic_config.py` | constants | `dynamic_maskable_ppo_v1`, `dynamic_joint_action_scoring_v1`, `dynamic_bap_env_v1`, `dynamic_obs_v1`; regimes tiny (M = 8) / medium_heavy (M = 24); H ∈ {0, 240}; training seeds exactly (11, 23, 37) |
| `rl/dynamic_evaluation.py` | `run_dynamic_episode` | Project 03 evaluation: `model.predict(observation, deterministic=True, action_masks=mask)`; used unchanged for the S1 berth-only reference |

The `--check-compatibility` report records the path and SHA-256 of each module and 11 source
assertions (all PASS on this HEAD).

## 2. Frozen checkpoints (never modified; read-only CPU inference)

`03-berth-allocation-lab/experiments/rl/dynamic_extended_cuda/<experiment>/seed_<s>/best_validation_model.zip`

| Regime | Training seed | M / N | SHA-256 | G01-G03 | G04 load | Project I eligibility |
| --- | --- | --- | --- | --- | --- | --- |
| medium_heavy | 11 | 24 / 1153 | `3373e06060a6f14cae422d7041d863cf18001bed285d1b896bffbe4dfae32018` | PASS | PASS | PASS on all four families |
| medium_heavy | 23 | 24 / 1153 | `a2a105108d9b030cec8e26538012cbe1c2c2bc872f992e1a11ac0cd428ffd625` | PASS | PASS | PASS on all four families |
| medium_heavy | 37 | 24 / 1153 | `8318b49712fbbd04c6adbf1b357e2c5916fae539306b50272ded7464d002a3a6` | PASS | PASS | PASS on all four families |
| tiny | 11 | 8 / 129 | `35a1a0ba0b8d231fb26b2aa2ecfebad49e9b3ab9a949c2ea306054dbe1a7f46d` | PASS | not attempted | **BLOCK** (G12) |
| tiny | 23 | 8 / 129 | `4773a36832f02179e27bd00e4308829ae9a4eb00612ad8528b6975b88628c874` | PASS | not attempted | **BLOCK** (G12) |
| tiny | 37 | 8 / 129 | `7a3138ce37f3ef18c7c1b74df7e20f7a977f552a2e69e21dea828c79a9cd956a` | PASS | not attempted | **BLOCK** (G12) |

`validation_decision.json` SHA-256 `f2f912346e4a9260bf7752874fa1343fea63e0b7f2594f8083bf05c60c3e3423`
equals its sidecar, and each medium/heavy entry's `checkpoint_sha256` equals the file hash (G02).
Each sidecar's `training_seed` equals the directory seed (G03). Hashes are re-verified before and
after every compatibility check and in the test suite (G21).

**Seeds stay separate.** Each training seed is its own arm row (`A3-train11`, `A3-train23`,
`A3-train37`) with its own checkpoint hash. Actions are never averaged, no "mean PPO" checkpoint is
created, and the three seeds are not independent scenario samples: in any interval they are a
separate dimension, never pooled with scenario seeds.

Inference configuration (recorded per run): CPU, `torch.set_num_threads(1)`, deterministic
`predict` with `action_masks`, Project 03 loader with `allow_cross_horizon=False`. Model load time is
reported separately (`checkpoint_load_seconds_excluded`) and never charged to per-decision latency.

## 3. Policy × family × checkpoint matrix

| Family (vessels, quay) | A1 | A2 | A3 medium_heavy 11 / 23 / 37 | A3 tiny 11 / 23 / 37 |
| --- | --- | --- | --- | --- |
| `itp_low` (8, 1200 m) | PASS | PASS | PASS / PASS / PASS | BLOCK G12 (quay 1200 ≠ 600) |
| `itp_medium` (16, 1200 m) | PASS | PASS | PASS / PASS / PASS | BLOCK G12, G11 (16 > 8) |
| `itp_heavy` (24, 1200 m) | PASS | PASS | PASS / PASS / PASS | BLOCK G12, G11 (24 > 8) |
| `itp_yard_bottleneck` (18, 1200 m) | PASS | PASS | PASS / PASS / PASS | BLOCK G12, G11 (18 > 8) |

Family PASS is necessary, not sufficient: every A3 run also passes the per-scenario exogenous gate
(`runner.a3_scenario_gate`: G11, G12, G14, G16 on the actual scenario) and the per-epoch adapter
gates. Hand-written fixtures with 1–50 moves per vessel are outside the [250, 900] training workload
support and are **BLOCKED** for A3 (tested), not run. `itp_low` (8 vessels) uses the M = 24
checkpoints: vessel count ≤ M is the contract condition; the low traffic intensity is a distribution
shift, measured, not blocked.

## 4. Observation, action and mask semantics

The adapter (`benchmark/adapter.py`) maps the kernel's immutable `BerthView` and nothing else:

| `dynamic_obs_v1` element | Integrated source | Mode |
| --- | --- | --- |
| `current_time`, `horizon`, `terminal_features` | `BerthView.time_min`, `future_horizon_min` (240), quay/clearance | EXACT |
| slots, `visible_mask`, `vessel_features` | `BerthView.vessels` in reveal order (kernel: `(time, D22 priority, vessel_id)`, arrival before horizon entry); arrival, length, **nominal** service | EXACT (G10 re-checked each epoch) |
| `status_features` | ANNOUNCED → ANNOUNCED, WAITING → WAITING, OCCUPYING (berthing prep, handling, departure prep) → IN_SERVICE, DEPARTED → COMPLETED | EXACT |
| `placement_features[:,0:2]` | actual berth position and start | EXACT |
| `placement_features[:,2]` | `(ServiceForecaster v1 release − now)/1440` via an adapter `BAPPlacement` with `service = release − start` | EXACT when release = nominal end, else FORECAST-SUBSTITUTED (recorded per epoch) |
| `candidate_features`, `action_mask` | Project 03 `candidate_positions` / `is_placement_feasible` on the adapter placements; must equal the kernel's physical legal set (G08/G09) | EXACT |

The observation tensor is produced by Project 03 `encode_dynamic_observation` itself, called on a
duck-typed host (`P03ObservationHost`) exposing exactly the attributes it reads, so key order,
dtypes, normalization and mask meaning are Project 03's by construction. No key is added (G20), no
value is clamped, nothing is padded: more than M revealed vessels raises G11, a forecast at or
before `now` raises G17 (a kernel defect).

**Legal set equivalence.** Every occupying placement covers `now` (forecast > now), so the
immediate-start candidates depend only on positions and lengths; the adapter recomputes them with
Project 03 code and asserts equality with the kernel's legal set and WAIT bit at every epoch. A
predicted end never frees quay: a vessel past its nominal end stays in the placements until its
actual `VESSEL_DEPARTED` (tested on the overrun fixture).

**A2 visible state.** `DynamicVisibleState` is built from the same adapted state: revealed vessels
with nominal service, mapped statuses, forecast-ended placements, the Project 03 choice table, the
WAIT bit. The rollout's forward model is therefore berth-only: occupying vessels release at their
forecast, unstarted vessels use nominal service, no cranes, no yard, no hidden vessels, no gate or
pickup times, no kernel clone.

**A1 choice table.** `online_fcfs_action` receives the same `(action, vessel, candidate, position,
arrival)` tuples. The Step 4 integration fixture used `enumerate(...)` indices instead of
`1 + slot·P + c`; the FCFS key does not read the index, so decisions are identical (proved by full
trace equality, section 5).

## 5. Gate results

**Degenerate PASS-EXACT gate** (`--exact-gate`; 80 contiguous development seeds of the
`degenerate_equivalence_v1` profile: 30 medium, 30 heavy, 10 low, 10 bottleneck; each arm run in the
integrated kernel and, independently, in Project 03 `DynamicBAPEnv` with the same unchanged policy
code): see the results table in
[step5_independent_benchmark.md](step5_independent_benchmark.md#7-verification-results).

**Exactness scope (documented interpretation).** The degenerate profile removes crane, transport and
yard delays, but not cargo availability. A berth schedule different from FCFS can start a vessel
before its export or transshipment cargo is in the yard. The kernel then correctly extends handling
(`CARGO_UNAVAILABLE`) or rolls cargo over (D17), so realized occupancy exceeds nominal and Project 03's
fixed-duration world is no longer the same physical system. The gate compares every decision
strictly before `scope_end` = min(first nominal end not matched by an exact departure, first
FORECAST-substituted epoch), reports `scope = FULL | PREFIX` with the divergence time, vessels and
handling causes, and requires identical decisions and bit-equal observations on the compared
prefix. FCFS never triggers such a divergence on these seeds; Rollout and PPO sometimes do (WAIT or
different order). This is the contract's own PASS-EXACT definition ("every epoch has forecast =
nominal end") applied per epoch; it is listed for user confirmation in
[step5_protocol_readiness.md](step5_protocol_readiness.md) section 3.

**A1 = Step 4 fixture.** Full canonical traces (events, ledger, blocking, decisions, final state,
result) are byte-identical after replacing the recorded policy id, on `itp_low` seed 10,000,000
(standard physics) and on the overrun fixture (`test_a1_reproduces_the_step4_fcfs_fixture_trace_exactly`).

**PASS-FORECAST.** Every standard-physics development smoke run of every A3 seed passes all
per-epoch gates with FORECAST-substituted epochs (counts in the smoke report). Per contract section 6
the run records the maximum `placement_features[:,2]` and the number of epochs above the training
maximum `(50 + 0.5·900)/1440 ≈ 0.347`; these describe distribution shift and do not reject a run.

## 6. Unsupported conditions (explicit BLOCKs)

- Tiny checkpoints: every Project I family (1200 m quay; 8–24 vessels).
- Any scenario outside the medium/heavy exogenous support (quay ≠ 1200 m or clearance ≠ 20 m,
  more than 24 vessels, H ≠ 240, vessel length outside [200, 360] m, workload outside [250, 900]).
- More than 24 revealed vessels at an epoch (G11), a candidate count above P (G09), a legal-set or
  WAIT-bit mismatch (G08), a slot-order violation (G10), forecast ≤ now (G17), a model action outside
  the mask (G19). Each fails the run with `BERTH_POLICY_GATE_<id>`; nothing is repaired or replaced
  by a fallback policy.
- CUDA inference (contract section 10): not used.
