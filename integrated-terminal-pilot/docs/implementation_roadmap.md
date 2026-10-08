# Implementation Roadmap

The approved eight-step scope of Project I. No new steps are introduced. Each
step lists inputs, outputs, dependencies, a completion gate, expected tests
and exclusions. Gates apply in addition to the standing rules:

- Project 01–03 directories unchanged
  (`git diff --stat -- 01-terminal-operations-core 02-mini-port-simulation 03-berth-allocation-lab` empty).
- Project 01/02/03 fast suites still pass with unchanged counts (426 / 55 /
  463 at Step 1).
- No commit without user review.

```text
Step 1 ──► Step 2 ──► Step 3 ──► Step 4 ──► Step 5 ──► Step 6 ──► Step 7 ──► Step 8
 spec       generator   primitives  kernel      A1/A2/A3    A1n/B1/B2   locked test  analysis,
                                                + S1 ref    (+B3)       campaign     ablations
```

Step 3 depends on Step 2's observation-relevant records. Step 4 depends on
Steps 2–3. Step 5 needs Step 4. Step 6 needs Steps 4–5 (shared adapter,
timing). Step 7 needs every PROPOSED item resolved. Step 8 needs Step 7
records.

## Step 1 — Integration Specification and Compatibility Contracts (this step)

- **Inputs:** repository at `66990eb`; Project 03 frozen release and checkpoints (read-only).
- **Outputs:** `README.md` and the eight documents in `docs/`.
- **Gate:** user review; acceptance checklist of the Step 1 brief.
- **Tests:** baseline suites (recorded in the audit); JSON examples parse;
  worked-example reconciliation recomputed.
- **Excluded:** any code, generator, simulator, adapter, training or evaluation.

## Step 2 — Unified Synthetic Scenario Generator

### Step 2 prerequisites

1. User approval of these Step 1 documents. Decisions D01–D27 then become the
   working baseline.
2. Confirmation or amendment of every Step 2-tagged PROPOSED item in the
   decision register: physics coefficients (D09–D11), transport and yard
   values, family definitions and counts (protocol §6.5), weight bounds,
   `export_cutoff_min`, dwell/pickup distribution, initial occupancy, yard
   layout and block count, crane fleet size, `max_cranes` rule.
3. Package scaffold `integrated-terminal-pilot/pyproject.toml` (package
   `integrated_terminal_pilot`, dependencies D01) installed in editable mode in
   the existing environment, without changing Project 01–03 installs.
4. The worked example of [container_yard_foundation.md §11](container_yard_foundation.md#11-worked-example-illustrative-values-not-empirical-terminal-data)
   adopted as the first hand-written fixture.

### Step 2 scope

- **Inputs:** data contract, foundation schemas, protocol §6.
- **Outputs:** generator `itp_generator_v1` producing `itp_scenario_v1`
  documents; entity-keyed streams (protocol §6.3); scenario-stage
  validators (DQ01–DQ07, DQ09–DQ11, DQ16, DQ20 with the foundation §9 codes);
  fingerprints (data contract §10); berth-projection builder; Step 2 audit
  manifest (fingerprint uniqueness, Project 03 collision audit, coefficient
  freeze record).
- **Gate:** generated development scenarios pass all scenario validators; every
  projection constructs a valid `BAPScenarioInstance`, and a `DynamicBAPEnv`
  (`max_vessels=24`, H=240) resets on it; the collision audit passes;
  coefficients are frozen and recorded before any policy comparison.
- **Expected tests:** byte-identical regeneration for the same seed; keyed
  independence (changing one attribute's distribution leaves other draws
  unchanged); one negative test per scenario-stage error code;
  group/vessel/TEU/move reconciliation; projection round-trip; worked-example
  fixture validates.
- **Excluded:** kernel, policies, any arm comparison.

## Step 3 — Primitive Crane & Yard Policies

- **Inputs:** Step 2 records; observation contracts (integration
  specification §7 and §10).
- **Outputs:** policy interfaces (`BerthPolicy`, `CranePolicy`, `YardPolicy`)
  over immutable observation dataclasses; P_c (greedy by berth order) and P_y
  (first fit) of protocol §3; action dataclasses consumed by the Step 4
  validator.
- **Gate:** rule equivalence with Project 02 `GreedyCranePolicy` and
  `FirstFitYardPolicy` on Project 01 `Terminal` fixtures. Equivalence is checked
  for identical choices where the Project 02 rule is defined; the documented
  generalizations (vessel-level crane assignment, size compatibility) are
  tested separately.
- **Expected tests:** equivalence fixtures; determinism; no access to hidden
  fields (observation types have no hidden attributes); capability and size
  filtering; `max_cranes` limit.
- **Excluded:** coordination policies, kernel.

## Step 4 — Cloneable Integrated Terminal Simulator

- **Inputs:** Steps 2–3; architecture ADR; integration specification §§4–11.
- **Outputs:** `TerminalKernel` (state `itp_state_v1`, event queue,
  transitions, `PhysicalActionValidator`, ledger `itp_ledger_v1`,
  `ServiceForecaster v1` as a kernel query, `clone()`, `observable_clone()`),
  post-run audits (ledger replay, realized-projection schedule validation,
  Project 01 `TerminalState` projection), run records.
- **Gate:** all tests below pass, including the degenerate equivalence test.

### Degenerate equivalence test (required)

Construction: for each of ≥ 30 development scenarios of each family, build the
degenerate profile (data contract §6). That means transport and yard couplings
off, cranes at 120 moves/h, `max_cranes = 1`, crane fleet ≥ maximum concurrent
vessels, preparation 30/20, and identical quay geometry and clearance. Run
integrated A1 (FCFS + P_c + P_y). Separately, run Project 03 `DynamicBAPEnv`
with `online_fcfs_action` on the berth projection.

| Compared quantity | Required agreement |
| --- | --- |
| Projection physical fingerprint | identical (same object) |
| Vessel allocation order | identical sequence |
| Berth positions | equal within 1e-9 m |
| Berth start times | equal within 1e-6 min |
| Realized occupancy per vessel | equals nominal within 1e-6 min |
| Total waiting time | equal within 1e-6 vessel-min |
| Schedule validity | `find_schedule_violations` on the realized projection returns `()`; Project 03 episode `schedule_valid = True` |
| Total turnaround | equal within 1e-6 (Project 03 turnaround = service end − arrival; nominal service already includes the 30 + 20 preparation, so it equals integrated departure − arrival) |

Turnaround can legitimately differ only if the preparation durations differ
from the D20 values, or if a crane is not available at the end of berthing
preparation. Both are excluded by the profile. A test failure is a defect,
never a tolerance adjustment. Extensions run in Steps 5–6 on the same
profile: A2 (Rollout) action-by-action equality, and A3 PPO PASS-EXACT
action-by-action equality.

The degenerate test shows agreement of the berth layer only. It does not
establish crane, yard or inventory correctness, which the following tests
cover.

### Additional required tests

| Area | Test and pass criterion |
| --- | --- |
| Hand-worked traces | Integration specification §8.5 trace and foundation §11 timeline reproduced exactly (times, statuses, TEU counters) |
| Crane exclusivity | Property test over random action sequences: no crane assigned to two vessels; no vessel above `max_cranes`; release only between batches |
| Container conservation | Ledger replay (foundation §8.3) passes on every test episode; count constant; per-block TEU recomputation equals cache |
| Yard capacity | `occupied + reserved + blocked ≤ capacity` at every kernel cycle; discharge with no eligible block → crane `BLOCKED(YARD_CAPACITY)`, never overfill |
| Event ordering | Same-timestamp events processed by priority / key / sequence; departure before arrival before horizon entry; stale completion events discarded; scheduling in the past raises |
| Transfer blocking and recovery | A capacity-freeing event at t restarts blocked work at t (no lag); gate containers wait AT_GATE and are received when capacity returns |
| Deadlock handling | Constructed deadlock fixture ends `DEADLOCK` with evidence snapshot; drain-limit fixture ends `TRUNCATED_DRAIN_LIMIT`; livelock guard raises at the cycle limit |
| Estimated vs realized service | Overrun fixture: a planner expecting nominal release sees no legal position until real departure (spec §8.5); forecast > now at every berth epoch; forecast never reads the queue (instrumented test) |
| Rollover | Fixture where an export arrives too late: rolled over after `max_load_wait_min`; vessel departs; residual reported |
| Determinism | Two runs, identical ledger SHA-256 |
| Clone fidelity | Original and clone continued identically produce identical ledgers; mutating a clone leaves the original unchanged; `observable_clone()` contains no hidden vessel or landside event |
| Fidelity labels | G0 runs never emit slot fields (DQ19); G1 fixture snapshots validated (DQ09, DQ10) |
| Invalid actions | Every validator rejection leaves state byte-identical and raises the documented error |

- **Excluded:** experimental arms beyond A1; parameter tuning.

## Step 5 — Independent Integrated Benchmark

- **Inputs:** Step 4 kernel; BAP compatibility contract.
- **Outputs:** `BerthViewAdapter`; arms A1, A2, A3 (seeds 11/23/37,
  medium/heavy) in the integrated kernel; S1 reference runs (Project 03
  `DynamicBAPEnv` on projections) for development and validation scenarios;
  gate implementation G01–G21; support diagnostics; timing profile.
- **Gate:** gate PASS-EXACT in the degenerate profile (PPO and Rollout
  action-by-action equality with the Project 03 environment); PASS-FORECAST on
  validation families; the adapter observation is bit-equal to
  `encode_dynamic_observation` of a real `DynamicBAPEnv` whenever forecasts
  equal nominal ends; deadlock rate < 5 % per arm on validation; checkpoint
  hashes re-verified.
- **Expected tests:** gate unit tests (one failure fixture per G-check);
  mask = physical legal set at every epoch; repeated-inference determinism;
  S1 pipeline end-to-end on development data.
- **Excluded:** test split; coordination arms.

## Step 6 — Integrated Coordination Policies

- **Inputs:** Steps 4–5; protocol §§3–5.
- **Outputs:** A1n and B1 (shared greedy rule; nominal vs integrated one-step
  estimator); B2 (integrated rollout on `observable_clone()`, FCFS
  continuation, P_c/P_y, visible-cohort turnaround score, WAIT scored with the
  same "next revealed decision" semantics as Project 03
  `finish_after_wait`); forward-model coupling switches for the Step 8
  ablations; optional B3; frozen `ServiceForecaster v1` and landside forecast
  rules (D25, D26).
- **Gate:** information-leakage tests pass. Perturbing any hidden datum
  (unannounced vessel arrival or attributes, future gate-in or pickup times)
  leaves every decision of every online arm unchanged up to the time that
  datum becomes visible. B2's "none" ablation reproduces A2 decisions on the
  same states. Every PROPOSED item tagged Step 6 is resolved by its
  pre-declared validation rule.
- **Expected tests:** leakage tests; ablation consistency; cohort-cap
  behaviour; timing within the protocol §5 cap or cap applied to A2 and B2.
- **Excluded:** test split.

## Step 7 — Paired Experimental Campaign

- **Inputs:** everything above; no open PROPOSED items.
- **Outputs:** `protocol_lock_v1.json` (+ `.sha256`); test scenarios generated
  after lock verification; runs of A1, A1n, B1, A2, B2, A3 ×3 (and B3 if
  enabled) on all test scenarios; run manifests; ledgers; audits.
- **Gate:** lock verified before generation; all audits pass or failures
  are recorded per protocol §8; checkpoint hashes re-verified after the
  campaign; no code change between lock and campaign end (commit recorded).
- **Expected tests:** lock verifier refuses a modified lock or dirty tree;
  DQ17 cross-arm exogenous fingerprint equality per scenario.
- **Excluded:** any re-tuning; Step 8 analyses beyond the locked plan.

## Step 8 — Scientific Results, Ablation and Project Closure

- **Inputs:** Step 7 records; diagnostic-band scenarios (13M) generated under the lock.
- **Outputs:** S1 and S2 results (protocol §§1, 4, 10); coordinator
  ablations and sensitivity (protocol §11); computation-cost report; final
  report with limitations; reproducibility instructions; closure note.
- **Gate:** every number traceable to run records; claims restricted to
  protocol §12; Project 01–03 unchanged.
- **Excluded:** new arms, new training, real-terminal claims.

## Scope exclusions (whole project)

New PPO training; crane RL; yard RL; multi-agent RL; central neural
coordinator; full 3D stacking optimization; relocation RL; detailed
road-network routing; rail-crane scheduling; commercial frontend; user
authentication; REST API; cloud deployment; production TOS integration.
Project 04 and Project 05 remain separate future projects. The Project I
container and yard contracts are designed so that Project 05 can add slot
placements and relocation optimization without breaking them
([container_yard_foundation.md §10](container_yard_foundation.md#10-project-05-extension-points)).
