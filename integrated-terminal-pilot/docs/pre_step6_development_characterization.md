# Pre-Step 6 Development Characterization (eight-crane research profile)

**Label: `DEVELOPMENT_CHARACTERIZATION`.** These are development scenarios only (10M seed band).
It is not S1/S2 validation, not a ranking and not a selection. No validation (11M) or test (12M)
scenario was generated or read. No result below changed the eight-crane profile, the common P_y,
D15/D17/R5, the cargo margin, the B2 objective or any checkpoint (safeguard S3, decision
firewall).

## 1. Plan (written before any run)

- **Plan:** `itp_pre_step6_characterization_plan_v1`, hash
  `33eaf016a12dba1242a29de6d0576cf4d4b20afe1026c71215fd745f9fdf2009`, written exclusively to
  `experiments/pre_step6_characterization/33eaf016a12d/plan.json` with a `.sha256` sidecar and a
  `plan_history.jsonl` entry **before** the first run.
- **Scenarios:** 12 stored development scenarios from source batch `dev_f5789d8c91_1ee66026`
  (families low, medium, heavy and yard bottleneck × seeds 10,000,000 / 10,000,001 / 10,000,002).
  Each file's SHA-256 and physical and exogenous fingerprints are verified against the batch index
  before use; split guard: development only.
- **Arms:** A1, A2, A3-train11, A3-train23, A3-train37.
- **Items (104):**
  - 60 primary runs (`itp_primary_balanced_qc8_v1`, 12 scenarios × 5 arms);
  - 40 sensitivity runs (balanced 4 and 6 cranes, seed 10,000,000 of each family × 5 arms;
    `SENSITIVITY_ONLY_QC4_QC6`);
  - 4 determinism repeats (A1, primary profile, seed 10,000,000 of each family).
- **Predeclared partial subset:** if capped, the 20 primary runs of seed 10,000,000 run first. No cap
  was needed.
- **Command:** `python scripts/run_pre_step6_characterization.py --run --progress`. The run is
  resumable, records are written exclusively, and an existing record must carry the same plan hash
  and item.

**Coverage: 104 / 104 complete (60 / 60 primary, 40 / 40 sensitivity, 4 / 4 repeats).** Report:
`experiments/pre_step6_characterization/33eaf016a12d/reports/report_7406d6dbb9fa.json`.

## 2. Profile and fingerprints

| | Historical v1 source (S2-019) | Primary research profile `itp_primary_balanced_qc8_v1` |
| --- | --- | --- |
| Cranes | QC01–QC04 (30 moves/h, rail R1, compatibility none) | QC01–QC08. QC05–QC08 are copies of the homogeneous source crane; home positions follow even spacing, e.g. QC05 at 675 m |
| `max_cranes_per_vessel` | 2 | 2 (verified per vessel) |
| Two-crane efficiency, basis | 0.92, assigned | 0.92, assigned |
| P_c / P_y | `primitive_crane_greedy_v1` / `yard_first_fit_v1` | `primitive_crane_greedy_v1` / `yard_occupancy_balance_v1` |
| D15 / D17 / R5 | 10 / 240 min / on | 10 / 240 min / on (S2-075 FROZEN, AM-04) |
| Example: heavy seed 10,000,000 physical fingerprint | `7259e7465434…` | `f97ab28c768a…` (derived) |
| Exogenous schedule fingerprint | source | **identical** (asserted for every run) |

Every run record carries:

- the source and derived scenario, physical, resource and exogenous fingerprints;
- the resolved-physics fingerprint, the eight crane records, the derivation version and the profile
  id and role;
- the D15/D17/R5 values with their approval provenance;
- the arm, the separate PPO training seed and the checkpoint SHA-256;
- package versions (Python 3.13.2, torch 2.6.0 CPU, sb3-contrib 2.8.0, numpy 2.2.3), the Git HEAD
  `6cdd959` with its dirty state (the uncommitted pre-Step 6 changes), the plan hash, the trace
  mode and the cargo-metric schema;
- `scientific_protocol_lock = BLOCKED` (28 pending records).

**Pairing and physics checks.**

- **Within profile:** in every profile × scenario cell, all five arms share one comparison
  fingerprint, one resolved-physics fingerprint, one exogenous fingerprint and one `N_out`. All
  cells pass.
- **Across profiles:** for every scenario, the 4-, 6- and 8-crane profiles have three distinct
  resolved-physics fingerprints. Passes.
- **Determinism:** all 4 repeats reproduced their trace digests exactly.

## 3. Outcomes by family and arm (primary profile, 3 scenarios each)

Status: **all 60 primary runs COMPLETED.** There are no drain-limit truncations, no deadlocks, no
FAILED runs and 0 validator rejections; all physical audits pass, and the per-vessel move and
outbound reconciliations pass. The earlier four-crane first-fit truncations (Step 5 smoke) do not
occur under this profile. `U` equals the rolled-over count in every cell, so every non-loaded
obligation is a D17 rollover from a departed vessel; no vessel ended loaded but not departed.

| Family | Arm | Departed | Cargo-fulfilled vessels | Outbound N_out | Not loaded U | R per scenario | Mean D24 total turnaround (vessel-min) | Mean berth wait (min) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | A1 / A2 / A3-11 / A3-23 / A3-37 | 24/24 each | 24 each | 7,018 | 0 each | 0, 0, 0 (all arms) | 6,501 / 6,562 / 6,501 / 6,501 / 6,558 | 58 / 60 / 58 / 58 / 61 |
| medium | A1 / A2 / A3-11 / A3-23 / A3-37 | 48/48 each | 48 each | 13,229 | 0 each | 0, 0, 0 (all arms) | 15,558 / 14,984 / 15,225 / 15,475 / 15,319 | 235 / 199 / 208 / 226 / 222 |
| heavy | A1 | 72/72 | 69 | 20,766 | 110 | 0.0000, 0.0157, 0.0000 | 49,072 | 1,274 |
| heavy | A2 | 72/72 | 63 | 20,766 | 238 | 0.0170, 0.0100, 0.0073 | 46,056 | 1,118 |
| heavy | A3-11 | 72/72 | 56 | 20,766 | 559 | 0.0212, 0.0515, 0.0073 | 47,637 | 1,180 |
| heavy | A3-23 | 72/72 | 67 | 20,766 | 163 | 0.0066, 0.0115, 0.0053 | 46,892 | 1,170 |
| heavy | A3-37 | 72/72 | 57 | 20,766 | 465 | 0.0212, 0.0365, 0.0090 | 48,204 | 1,194 |
| bottleneck | A1 | 54/54 | 54 | 16,946 | 0 | 0, 0, 0 | 42,146 | 1,089 |
| bottleneck | A2 | 54/54 | 45 | 16,946 | 375 | 0.0371, 0.0218, 0.0106 | 38,819 | 925 |
| bottleneck | A3-11 | 54/54 | 47 | 16,946 | 310 | 0.0526, 0.0092, 0.0000 | 39,241 | 948 |
| bottleneck | A3-23 | 54/54 | 51 | 16,946 | 121 | 0.0249, 0.0000, 0.0000 | 40,820 | 1,018 |
| bottleneck | A3-37 | 54/54 | 46 | 16,946 | 259 | 0.0371, 0.0132, 0.0000 | 39,046 | 936 |

**Physical departure is not cargo fulfilment.** On heavy and bottleneck, every vessel departs, but
up to 16 of 72 (heavy) and 9 of 54 (bottleneck) vessels leave with rolled-over outbound cargo. The
arms with lower mean turnaround on these families tend to roll over more cargo. This is the pattern
the CARGO-NI rule exists to adjudicate. No non-inferiority test is computed here: the rule is for
Step 7 and three development scenarios per family support no inference.

Further descriptive measures (primary profile):

- **Realized / nominal occupancy:** mean 2.17 (low), 2.21 (medium), 2.33 (heavy) and 3.43
  (bottleneck); maximum 4.96.
- **Completed-only mean turnaround:** 816 / 957 / 1,982 / 2,223 min (low / medium / heavy /
  bottleneck, all arms pooled; every vessel completed).
- **Crane utilization (eight cranes charged):** 0.51–0.52 (low), 0.56–0.61 (medium), 0.66–0.72
  (heavy) and 0.70–0.78 (bottleneck).
- **Busiest yard block share of ship moves:** 0.090–0.099 in every cell, close to 1/12 for 12
  blocks. The balanced P_y removes the first-fit concentration seen in the Step 4 closure
  (first-fit heavy four-crane 0.32 in the earlier sanity run).
- Phase-time decomposition and handling-cause shares are stored per run (`time_decomposition`).

**Sensitivity levels (seed 10,000,000, balanced; descriptive, never a fleet choice).** All 40 runs
COMPLETED with 0 rejections and audits OK. For A1 on seed 10,000,000, the D24 total turnaround
falls from four to six to eight cranes on every family: low 9,157 → 6,907 → 6,827; medium
27,937 → 20,254 → 18,166; heavy 99,884 → 71,710 → 63,630; bottleneck 67,132 → 49,258 → 43,888.
This is the expected capacity effect of more cranes on identical traffic. These are different
physics, never same-physics contrasts. The pattern of rollover across arms is similar to the primary
profile.

## 4. Frozen PPO occupancy feature (A3; `OUT_OF_DISTRIBUTION_MEASURED`)

The table pools every occupying-vessel value of `placement_features[:,2]` at every A3 decision
epoch of the primary profile. The training bound is (50 + 0.5 · 900) / 1440 ≈ 0.347.

| Group | Vessel-epoch values | p50 | p90 | p95 | max | Fraction above 0.347 |
| --- | --- | --- | --- | --- | --- | --- |
| A3-train11 (all families) | 430 | 0.234 | 0.552 | 0.687 | 2.815 | 0.291 |
| A3-train23 | 440 | 0.245 | 0.604 | 0.692 | 2.815 | 0.311 |
| A3-train37 | 444 | 0.239 | 0.614 | 0.735 | 2.682 | 0.315 |
| low (all seeds) | 108 | 0.208 | 0.610 | 0.664 | 1.066 | 0.287 |
| medium | 263 | 0.231 | 0.473 | 0.517 | 0.705 | 0.205 |
| heavy | 531 | 0.202 | 0.484 | 0.583 | 1.426 | 0.217 |
| yard bottleneck | 412 | 0.330 | 0.807 | 0.955 | 2.815 | 0.490 |

Epochs with at least one value above the bound: 91 (seed 11), 95 (seed 23) and 101 (seed 37).

For comparison (descriptive, different physics): the Step 5 four-crane first-fit smoke showed epoch
maxima between 1.1 and 4.7. Under eight cranes and the balanced P_y, the maxima are 0.70–2.82, and
20–49 % of occupying-vessel values still exceed the training bound. **Training support is not
restored.** A3 operates under a measured distribution shift by design of S1. Nothing was changed in
response.

## 5. Decision timing (primary profile; checkpoint load and imports excluded)

| Arm | View build (mean, ms) | Adapter incl. mask (mean, ms) | Policy (mean) | Policy p95 (worst run) | Policy max | Run wall (mean, s) |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | 1.55 | 1.27 | 0.03 ms | 0.001 s | 0.001 s | 14.1 |
| A2 | 1.76 | 1.40 | 390 ms (rollout 0.39 s) | 9.50 s | 10.28 s (heavy) | 23.3 |
| A3-train11 | 1.64 | 1.26 | 12.8 ms (inference 11.8 ms) | 0.054 s | 0.061 s | 14.0 |
| A3-train23 | 1.74 | 1.26 | 14.4 ms (inference 13.3 ms) | 0.064 s | 0.104 s | 14.9 |
| A3-train37 | 2.03 | 1.32 | 13.4 ms (inference 12.4 ms) | 0.070 s | 0.103 s | 14.2 |

- **Excluded setup:** checkpoint load and torch import are recorded separately
  (`policy_setup_seconds_excluded`; 52.8 s once, for the first A3 load in the process).
- **Concurrent load:** part of the campaign ran while unit tests executed on the same machine, so
  absolute latencies are indicative only (Step 5 measured 3–6 ms A3 inference with no concurrent
  load).
- **A2 warning:** under eight cranes, the heavy family has larger visible cohorts and the A2
  per-decision cost reaches about 10 s (p95 9.5 s in the worst run). This exceeds the protocol's
  PROPOSED 2.0 s cap trigger, which applies equally to A2, B2 and B2-T. Per safeguard S3 nothing was
  changed; it is reported for the Step 6 compute-budget design.

## 6. PPO environment caution

Inference used torch 2.6.0 (CPU, one thread, deterministic, masked) on Python 3.13.2. The
checkpoint sidecars record training with torch 2.14.1+cu130 on CUDA. Project 03 contains no archived
golden observation→action probes, so equality with training-time CUDA inference cannot be checked
and is not claimed. No historical result was reconstructed and no validation data was read.
Checkpoint hashes are unchanged.

## 7. Physical validity verdict (safeguard S3)

There is no physical invalidity:

- 0 truncations, 0 deadlocks, 0 failures and 0 validator rejections;
- all invariants and audits pass;
- exogenous traffic is identical.

The eight-crane primary profile stands as approved. No STOP was triggered, and no profile, fleet
or rule change was made or proposed on the basis of these results.
