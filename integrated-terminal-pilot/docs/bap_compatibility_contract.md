# BAP Compatibility Contract

How Project 03's frozen Dynamic BAP policies (Online FCFS, Online Rollout and
Dynamic Maskable PPO seeds 11/23/37) act inside the integrated kernel without
retraining, without modifying checkpoints, and without misrepresenting their
input contract. The gate is specified here and implemented in Step 5 (FCFS,
Rollout) and Step 5/6 (PPO adapter). **No adapter is implemented in Step 1.**

## 1. Two different states

| | PPO training state | Integrated terminal state |
| --- | --- | --- |
| Owner | `berth_allocation_lab.envs.DynamicBAPEnv` (`dynamic_bap_env_v1`) | `TerminalKernelState` (`itp_state_v1`) |
| Vessel phases | HIDDEN, ANNOUNCED, WAITING, IN_SERVICE, COMPLETED | NOT_ARRIVED (hidden/announced), WAITING, BERTHING_PREP, HANDLING, DEPARTURE_PREP, DEPARTED |
| Service duration | Fixed nominal `service_time_min`; completion exactly at `start + service` | Emerges from cranes, transport and yard; release only at `VESSEL_DEPARTED` |
| Crane / yard | Absent | Present |
| Decision epochs | Arrival, completion, horizon entry | Same three event kinds (D07) |

The **berth view adapter** (`BerthViewAdapter`, Step 5) derives from the
integrated state the *subset* of information the frozen policies were trained
or designed to consume, in the same encoding. It never adds fields. Crane and
yard information cannot be appended to `dynamic_obs_v1`: that would change the
network's input contract. The frozen PPO is therefore **not** crane-aware or
yard-aware, and no Project I result may describe it as such.

## 2. Field-by-field mapping (`dynamic_obs_v1`)

Phase mapping: NOT_ARRIVED+announced → ANNOUNCED; WAITING → WAITING;
BERTHING_PREP / HANDLING / DEPARTURE_PREP → IN_SERVICE (the vessel occupies
the quay); DEPARTED → COMPLETED; not announced → no slot (hidden).

| Observation element | Project 03 meaning | Integrated value | Semantics status |
| --- | --- | --- | --- |
| `current_time` | `now/1440` | kernel `now_min/1440` | EXACT |
| `horizon` | `H/1440` | `240/1440` | EXACT (D18) |
| `terminal_features` | `quay/1000`, `clearance/quay` | `1200/1000`, `20/1200` (primary) | EXACT (G12) |
| `vessel_features[:,0]` | `(arrival − now)/1440` | same, exact arrival (no ETA noise) | EXACT |
| `vessel_features[:,1]` | `length/quay` | same | EXACT |
| `vessel_features[:,2]` | `service_time_min/1440`, the nominal planned occupancy | `nominal_service_time_min/1440` (D20, same formula and `ServiceConfig(30, 0.5, 20)` values as every Project 03 training scenario) | EXACT |
| `visible_mask`, slots | allocated at first reveal in `(time, event priority, vessel_id)` order, never reused | kernel reveal order with the same relative priorities (arrival before horizon entry) and vessel-id tie-break | EXACT (G10) |
| `status_features` | one-hot of four statuses | phase mapping above | EXACT |
| `placement_features[:,0:2]` | `position/quay`, `(start − now)/1440` | actual berth position and berth start | EXACT |
| `placement_features[:,2]` | `(end − now)/1440`, where `end` is the exactly known end of quay occupancy | `(estimated_release − now)/1440` from `ServiceForecaster v1` | **EXACT** when forecast = nominal end (degenerate profile); otherwise **FORECAST-SUBSTITUTED** |
| `candidate_features` | per legal action: `position/quay`, `(now − arrival)/1440` | same, from the adapter's legal set | EXACT |
| `action_mask` | legal immediate assignments + WAIT bit | physical legal set (§3) | EXACT (G08) |

### 2.1 Why FORECAST-SUBSTITUTED is a faithful mapping, not a reinterpretation

The field is defined in Project 03 as "end of the vessel's quay occupancy
minus now". In Project 03 that end was known exactly, because duration was
exogenous. In the integrated terminal, the end of occupancy is not yet
determined at decision time. The best non-anticipatory value of the *same
quantity* is the kernel's current forecast. The unit, normalization, sign
convention and schema are unchanged. Only the information quality changes:
exact becomes estimated. This is a declared **distribution shift**, and S1
measures exactly that.

The obvious alternative, writing the nominal end `start + service_time_min`, is
**BLOCKED BY REPOSITORY EVIDENCE**. When realized occupancy exceeds nominal,
`nominal_end − now ≤ 0` for a vessel still occupying the quay. Project 03
training never produces this, because completions are processed before decisions. It also
breaks the reused policy code. Project 03 `candidate_positions` /
`is_placement_feasible` would see no time overlap
(`min(end, now + service) − max(start, now) ≤ 0`), so they would offer positions on
physically occupied quay. `dynamic_online_rollout._VisibleContinuation.advance`
only completes placements with `end > time`, so it would keep such placements in
its active set without ever completing them, while also treating their quay
segment as free. Its rollout scores would describe an impossible schedule.

Verified in Step 1 with the real Project 03 functions, using the integration
specification §8.5 trace: V001 occupies `[0, 200]` m until 58, and V002 (400 m) is
waiting on a 600 m quay at t = 52. With the true occupancy the legal set is `[]`.
With the nominal end (52, so `end − now = 0`) the same calls return
`[0.0, 200.0]`, which is quay that V001 still physically occupies.

### 2.2 Forecast guards

- The forecast is `> now` at every berth decision. This holds by construction
  because departures (priority 30) are processed before decisions. A violation
  is a kernel error (`FAIL_RUN`), never clamped.
- The forecaster reads only current state (integration specification §11). It
  never reads the event queue or the scenario's future.
- The same forecaster output feeds the PPO observation, the A2 Rollout
  visible state, and the B-arm observations, so every berth-only arm has
  identical current-state information.

## 3. Action and mask compatibility

- `M = max_vessels` of the checkpoint (24 medium/heavy, 8 tiny),
  `P = 2M`, `N = 1 + M·P` (1153 / 129).
- Adapter placements: one `BAPPlacement(vessel_id, berth_position_m,
  berth_start_time_min, length_m, service_time_min = estimated_release − berth_start)`
  per occupying vessel. Departed vessels are excluded (they neither block nor
  add boundaries, as in Project 03).
- Candidates per waiting vessel come from `candidate_positions(vessel, placements,
  berth_length_m, min_clearance_m)` filtered by
  `is_placement_feasible(vessel, x, now, placements, ...)`, ordered by
  position, and indexed `0…k−1`. This is identical to `DynamicBAPEnv._cache_choices`.
- **Equivalence with physical legality.** An immediate start at `now`
  conflicts with an occupying vessel iff their quay intervals (with clearance)
  overlap, because every occupying placement covers `now` (`berth_start ≤ now <
  estimated_release`). The legal set therefore does not depend on the forecast
  value, only on `forecast > now`. The adapter asserts at every epoch that its
  mask equals the `PhysicalActionValidator` legal set (G08).
- WAIT bit: `True` iff some vessel is WAITING with a legal assignment **and**
  a visible future event exists: an ANNOUNCED vessel with `arrival > now`, or an
  occupying vessel (forecast `> now`). This is the Project 03 rule, using only
  visible data.
- Decoding `1 + slot·P + c` → `(vessel_id, position)` uses the adapter's
  cached choice table. The kernel then applies the berth start through the
  validator.

## 4. Scenario restrictions for frozen PPO

| Restriction | Medium/heavy checkpoints | Tiny checkpoints |
| --- | --- | --- |
| Quay / clearance | exactly 1200.0 m / 20.0 m | exactly 600.0 m / 20.0 m |
| Vessels per episode (all, not concurrent) | ≤ 24 | ≤ 8 |
| Vessel length | within training support [200, 360] m | same |
| Workload moves | within training support [250, 900] | same |
| Horizon | 240 min | 240 min |
| Quay topology | single continuous quay, immediate starts (D04, D06) | same |
| Vessel attributes in observation | only arrival, length, nominal service | same |

Exogenous inputs outside training support (length, workload) are a
generator design error for PPO-eligible families and **BLOCK** A3 on that
scenario. Endogenous, policy-dependent values outside training ranges are
**not** blocked; they are measured (§6). Examples: forecast remaining occupancy above
the training maximum `(50 + 0.5·900)/1440 ≈ 0.347`, or episode times beyond the
training range. They are the subject of S1.

## 5. Compatibility gate

Every check is automated (Step 5/6) and its result is stored in the run
manifest.

| ID | Check | PASS criterion |
| --- | --- | --- |
| G01 | Checkpoint existence | `best_validation_model.zip` and `.metadata.json` exist at `03-berth-allocation-lab/experiments/rl/dynamic_extended_cuda/{experiment_id}/seed_{s}/` |
| G02 | Hash / provenance | SHA-256 equals the audit table and the matching `validation_decision.json` entry; decision file hash equals its `.sha256` sidecar (`f2f91234…3423`) |
| G03 | Training seed / regime | Sidecar `training_seed` = requested seed ∈ {11, 23, 37}; experiment id matches regime |
| G04 | Loader checks | `load_dynamic_checkpoint(path, env)` succeeds with `allow_cross_horizon=False`. `env` is a `DynamicBAPEnv` built on the scenario's berth projection with the checkpoint's `max_vessels` and reset once, used only as a compatibility host |
| G05 | Observation schema and ordering | Adapter output keys, shapes and dtypes equal `build_dynamic_observation_space(M, N)`; `observation_space.contains(obs)` |
| G06 | Normalization | `time_scale_min = 1440.0`, `length_scale_m = 1000.0`; no adapter-side rescaling |
| G07 | Action encoding | `0 = WAIT`, `1 + slot·P + c`, `P = 2M` |
| G08 | Mask | Shape `(N,)`; equals the physical legal set at every epoch |
| G09 | Candidate semantics | Candidates from Project 03 `candidate_positions` / `is_placement_feasible` on adapter placements; every candidate accepted by the validator; count ≤ P |
| G10 | Vessel ordering | Slot order equals Project 03 reveal order |
| G11 | Capacity | Scenario vessel count ≤ M |
| G12 | Geometry | §4 quay and clearance |
| G13 | Topology / timing | Single quay; immediate starts only |
| G14 | H = 240 information | Announcement at `arrival − 240`; no slot, feature, count or WAIT effect from hidden vessels |
| G15 | Service-field semantics | `vessel_features[:,2]` = D20 nominal with `ServiceConfig(30, 0.5, 20)` |
| G16 | Exogenous support | §4 length and workload ranges |
| G17 | Placement-end semantics | `estimated_release > now` for all occupying vessels; mode recorded per epoch (EXACT / FORECAST) |
| G18 | Deterministic inference | CPU device (as Project 03 loader); `model.predict(obs, deterministic=True, action_masks=mask)`; `torch.set_num_threads(1)`; repeated inference on a fixed fixture set returns identical actions |
| G19 | Legal action handling | Returned action is in the mask; otherwise the run is `FAILED` (no repair, no fallback policy) |
| G20 | No appended features | Exactly the nine `dynamic_obs_v1` keys; no crane or yard keys |
| G21 | Immutability | Checkpoint opened read-only; hashes re-verified after the campaign |

### 5.1 Outcomes

| Mode | Condition | Allowed use |
| --- | --- | --- |
| **PASS-EXACT** | All checks pass and every epoch has forecast = nominal end | Degenerate equivalence test: integrated PPO actions must equal Project 03 `DynamicBAPEnv` PPO actions on the projection, action by action |
| **PASS-FORECAST** | All checks pass; at least one epoch with forecast ≠ nominal end | Arm A3 in S1 and S2 tables, labelled "frozen berth-only PPO under forecast-substituted occupancy; distribution-shifted transfer" |
| **BLOCK** | Any of G01–G16, G18–G21 fails | A3 is not run on the affected scenario or family; reported as unsupported with the failing check id; no partial or padded result |

A G17 violation is a kernel defect (`FAIL_RUN`), not a gate outcome.

## 6. Support diagnostics recorded for PASS-FORECAST

Per decision epoch: number of occupying vessels with forecast ≠ nominal end;
maximum `|placement_features[:,2]|`; whether any observation value lies
outside the per-feature envelope of the Project 03 medium/heavy validation
suites (envelope computed from projections of the Project 03 validation
generators, never from test data); forecast error at departure
(`realized_release − forecast`). Results are summarised per arm and scenario
family. They describe distribution shift; they do not reject results.

## 7. Control versus advisory use

- **A3 (direct control).** PPO selects the berth action in the integrated
  kernel. Because the mask equals the physical legal set, every selected action
  is executable. Cranes and yard follow the same primitive policies as A1.
  This is direct control of berth decisions only.
- **B3 (advisory, optional).** PPO logits or top-k actions may be used by an
  integrated coordinator to prune or order candidates before integrated
  forward evaluation. PPO never overrides the validator. B3 runs only if the
  gate is PASS-FORECAST or PASS-EXACT, and it is excluded from the primary
  factorial claim.

## 8. Reference evaluator for S1

For every Project I scenario, the berth projection (data contract §11) is also
run through Project 03 `DynamicBAPEnv` with `online_fcfs_action`,
`online_rollout_action` and the frozen PPO (same checkpoints, same CPU
inference). This produces the **berth-only reference** ranking on exactly the same
exogenous traffic, which the integrated ranking is compared against. These runs
use new Project I scenarios. Project 03 held-out scenarios are never reused as
Project I evidence.

## 9. Online FCFS and Online Rollout adapters

- **FCFS** uses the adapter's `legal_choices` tuples `(action, vessel_id,
  candidate_index, position, arrival)` and Project 03
  `online_fcfs_action` ordering `(arrival, vessel_id, position)`.
- **Rollout (A2)** receives a `DynamicVisibleState` built by the adapter
  (vessels by slot with nominal service, mapped statuses, adapter placements,
  legal choices, WAIT bit) and calls Project 03 `online_rollout_choice`
  unchanged. Its forward model is berth-only by construction: occupying vessels
  release at their forecast; unstarted vessels use nominal service; no cranes,
  no yard.

## 10. Prohibitions

- No checkpoint, sidecar or decision-file modification; no fine-tuning,
  retraining or recalibration of PPO.
- No padding of physical quantities, no clamping of negative times, no
  re-scaling, no reinterpretation of fields, no extra keys.
- No CUDA inference in Project I. CPU/CUDA parity is unverified in Project 03.
- No claim that frozen PPO is crane-aware, yard-aware or "integrated".
