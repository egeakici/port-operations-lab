# Step 2 Stabilization Report

**SYNTHETIC — NOT CALIBRATED TO A REAL TERMINAL.**

This report covers the targeted stabilization of the Step 2 generator
`itp_generator_v1`, started from commit `032bc23`. It is not Step 3: no crane or yard policy,
simulation kernel, RL training, policy execution or held-out evaluation was run.

Every new numerical value is **PROPOSED_PENDING_REVIEW**. Each one is technically validated
on development seeds only and needs user approval before any validation comparison (§11).

## 1. Original failure

The first Step 2 development run is `experiments/scenarios/development/dev_3f1f0d9335_3e15947a/`.
It is kept unchanged as a historical artifact (`source_git_dirty = true`, manifest SHA-256
`3a12da33…7659352`). That run reported:

- `itp_yard_bottleneck`: 5 of 5 seeds BLOCKED. Decision S2-025 was BLOCKED because its
  pre-episode inventory could not fit 2 × 800 TEU.
- `itp_heavy`: seed 10,000,000 was rejected with `YARD_CAPACITY_EXCEEDED`. The four accepted seeds
  started at a mean occupancy of 0.744, against a target of 0.5.
- `itp_medium` and `itp_low` were accepted.

## 2. Evidence: mandatory initial inventory

*Mandatory* initial inventory is the cargo that the cargo and timing contract requires to be
in the yard at t = 0:

```text
mandatory_TEU = Σ size_teu over
    exports with  arrival(dest) − export_cutoff_min − lead < 0      (pre-staged exports)
  + transshipment with origin PRE_EPISODE                            (no eligible earlier vessel)
lead ~ U[0, export_gate_lead_max_min]      (2880 min; keyed draw per container)
minimum initial occupancy = mandatory_TEU / Σ capacity_teu
```

Probes used the generator's own draw functions. The development seeds were taken from
10,000,000 in contiguous windows (core: 30 medium, 30 heavy, 10 low, 10 bottleneck).

| Family | A. Pre-staged export TEU (mean) | B. Pre-episode transshipment TEU (mean) | D. Mandatory TEU min / mean / max | Share of export TEU pre-staged | Mean last arrival |
| --- | ---: | ---: | --- | ---: | ---: |
| itp_medium | 3,140 | 798 | 1,732 / 3,938 / 6,037 | 0.61 | 2,907 min |
| itp_heavy | 4,911 | 1,155 | 3,356 / 6,066 / 9,686 | 0.64 | 2,789 min |
| itp_low | 1,959 | 545 | 1,821 / 2,504 / 2,914 | 0.75 | 2,093 min |
| itp_yard_bottleneck | 3,604 | 912 | 3,010 / 4,516 / 5,980 | 0.61 | 2,941 min |

Under the **pre-stabilization** yard (columns F to I):

| Family | F. Capacity | H. Minimum occupancy (max over seeds) | I. 0.5 target feasible | Fits capacity |
| --- | ---: | ---: | ---: | ---: |
| itp_medium | 8,800 TEU | 0.686 | 19 / 30 | 30 / 30 |
| itp_heavy | 8,800 TEU | 1.101 | 2 / 30 | 29 / 30 |
| itp_low | 8,800 TEU | 0.331 | 10 / 10 | 10 / 10 |
| itp_yard_bottleneck | 1,600 TEU | 3.737 | 0 / 10 | 0 / 10 |

**C. Background inventory.** Background imports are not contract-mandatory. Before the
stabilization they filled only to the target, or not at all when mandatory inventory already
exceeded it.

**G and J. Size compatibility.** Every block accepts 20 ft and 40 ft containers with general
capability. Aggregate TEU capacity is therefore not misleading at G0; the only granularity loss
is less than 2 TEU per block, when a 40 ft draw no longer fits.

The size test `test_block_size_eligibility_is_enforced` shows the opposite case. If blocks
accepted only 20 ft, the aggregate capacity would be misleading, and generation fails
explicitly.

## 3. Root cause

**The pre-staging rule was not wrong.** The rule `gate-in = arrival − cutoff − U[0, 2880]` is
causal: a negative request means the container was physically received before t = 0. Every
heavy vessel arrives within about 46 h, well inside the roughly 54 h (cutoff + maximum lead)
pre-staging window. A large part of the whole episode's export cargo therefore must already
be in the yard at t = 0. This is a genuine consequence of the traffic intensity and the lead
assumption, not a code defect.

**The yard was too small for the traffic.** The 4 × 2,200 TEU yard (8,800 TEU) came from the
Project 03 family configurations, where it was never exercised physically. A steady-state
heavy terminal with these dwell assumptions needs more storage than that: about 6,000 TEU of
exports staged for the next two days, plus imports dwelling 0.5–3 days. The Project 02
bottleneck yard of 2 × 800 TEU was smaller than its mandatory inventory for every seed.

**Initial infeasibility and episode-wide pressure are different things.**
- *Initial storage infeasibility* means mandatory inventory exceeds capacity at t = 0. This
  occurred in 1 of 30 heavy seeds and in all bottleneck seeds.
- *Episode-wide pressure* is the cumulative TEU passing through the yard divided by its static
  capacity: about 1.5 for medium and 2.3 for heavy on the old yard. It is not an occupancy,
  because capacity is reused as containers leave. It was never used as a feasibility criterion.

## 4. Pre-staging definition (unchanged formula, now explicit and tested)

`generator.export_prestaging(arrival, cutoff, lead)`:

```text
request = arrival − cutoff − lead            # lead drawn from the container's keyed stream
request <  0  →  present_at_episode_start = true, scheduled_gate_in_time_min = null  (MANDATORY)
request >= 0  →  present = false, gate-in request = request ∈ [0, arrival − cutoff]  (DQ11)
```

**Boundaries tested** (`test_export_prestaging_boundaries`):

| Case | Result |
| --- | --- |
| Arrival before the cutoff | Always pre-staged; no admissible in-episode gate-in exists |
| Arrival exactly at the cutoff, lead 0 | Gate-in at t = 0 |
| Arrival exactly at the cutoff, lead > 0 | Pre-staged |
| Request exactly 0 | In-episode gate-in |
| Request just below 0 | Pre-staged |
| Late export | In-episode gate-in at most `arrival − cutoff` |
| Generated scenarios | Contain pre-staged exports of both sizes, plus in-episode gate-ins |

**What the rule does not do:**
- No negative-time events are created.
- No gate-in time is moved later to fit the yard.
- The rule reads only exogenous data, never policy results.

**Mandatory and optional inventory** (`_place_initial_inventory`):

1. Mandatory inventory is placed first. It is never dropped. If it exceeds total operating
   capacity, or fits no eligible block, the scenario is rejected with
   `YARD_CAPACITY_EXCEEDED`.
2. Optional background imports (origin `PRE_EPISODE`) are added one keyed draw at a time,
   only while some block is below its share of the target. Each one is an individual
   container; no anonymous TEU are used.
3. If mandatory TEU exceed the target, no background is added and nothing is removed or
   resampled. The scenario is still generated and reports
   `target_status = MANDATORY_EXCEEDS_TARGET`.
4. A run is considered stabilized only if no declared seed reports that status.

Background containers get the last container ids, so the target never relabels vessel cargo.

## 5. Alternatives considered (development windows only)

| Alternative | Capacity | Heavy minimum occupancy (max, core / second window) | 0.5 target met: medium / heavy (core) | Assessment |
| --- | ---: | --- | --- | --- |
| A. Old 4 × 1 line | 8,800 | 1.101 / 0.970 | 19/30 / 2/30 | Infeasible |
| A + lead shortened to U[0, 1440] | 8,800 | 1.023 | 28/30 / 16/30 | Rejected twice over: it moves gate-ins later only to fit the yard, and it is still infeasible |
| B. 8 blocks, 2 lines | 17,600 | 0.550 / 0.485 | 30/30 / 29/30 | Rejected: one heavy core seed exceeds the target |
| D. 8 blocks, 6 tiers (2,800 TEU) | 22,400 | 0.432 / 0.381 | 30/30 / 30/30 | Feasible, but changes two dimensions (line count and stack height / fill limit) and every block record |
| **C. 12 blocks, 3 lines (selected)** | **26,400** | **0.367 / 0.323** | **30/30 / 30/30** | Feasible with margin; one dimension changes (number of block lines) |
| Per-seed resizing | — | — | — | Forbidden: infrastructure must be fixed per family |

**Not used:** larger rows per block (for example 28-row blocks), because this is
unrealistically wide for one block's yard equipment and would break the G1 geometry intended
for Project 05.

**Choice of C over D.** C reuses the existing block unchanged: the same geometry, 2,200 TEU,
60 moves/h and the 0.8 fill limit. Only the number of block lines changes. D raises stack
height to 6 tiers, which changes every block's slot count, fill limit (0.83) and capacity.
D's margin is also thinner. On the heavy core window its maximum mandatory fraction is
0.43, against 0.37 for C. In the export-heavy stress (§8.2), C already reaches 0.49; scaled
to D's capacity, the same inventory would be 0.58, above the 0.5 target.

**Plausibility.** About 22 TEU of operating capacity per metre of quay is a synthetic
order-of-magnitude check, not a calibration. The yard footprint is three lines of
1,160 m × 39.2 m within a yard 197.6 m deep.

## 6. Selected configuration (configuration schema 2)

### 6.1 Old versus new yard

| Item | Old medium / heavy / low | Old bottleneck | New, all four families |
| --- | --- | --- | --- |
| Blocks × lines | 4 × 1 | 2 × 1 | **12 × 3** (B01–B04, B05–B08, B09–B12) |
| Block grid (bays × rows × tiers) | 40 × 14 × 5 | 20 × 10 × 5 | 40 × 14 × 5 |
| Geometric slots per block | 2,800 | 1,000 | 2,800 |
| Operating fill limit | 0.8 | 0.8 | 0.8 |
| capacity_teu per block | 2,200 (≤ 2,240) | 800 (≤ 800) | 2,200 (≤ 2,240) |
| Total operating capacity | 8,800 TEU | 1,600 TEU | **26,400 TEU** |
| Block handling | 60 moves/h | 60 moves/h | 60 (bottleneck **30**) |
| Initial occupancy target | 0.5 | 0.5 | 0.5 (bottleneck **0.7**) |
| Line origins y | 100 m | 100 m | 100.0 / 179.2 / 258.4 m |
| Block x origins | 20, 320, 620, 920 | 450, 620 | 20, 320, 620, 920 (each line) |
| Gate | (600, 239.2) | (600, 228) | (600, 397.6) |
| Quay-to-block distance | 100–1,150 m | 100–785 m | 100–1,308 m |

**Geometric verification.** For each block, `40 × 14 × 5 = 2,800` slots and
`2,800 × 0.8 = 2,240 ≥ 2,200`. One line is `4 × 260 + 3 × 40 = 1,160 m ≤ 1,200 m`.

Footprints are pairwise disjoint: lines are 39.2 m deep and separated by 40 m roads. Transfer
points sit at the middle of each block's quay-side edge. The gate lies behind the last line.
The loader enforces each line's width (`GeneratorConfigError`), and the validator enforces
2-D overlap, quay extent and transfer points (`INVALID_YARD_GEOMETRY`).

**Fixed per family.** The infrastructure is part of the family configuration and the
generator-config fingerprint. It is never resized per seed, and no code path depends on the
drawn cargo.

### 6.2 Fixed physical assumptions (retained)

- Quay 1,200 m / 20 m (D04, FROZEN).
- **Four quay cranes at 30 moves/h** (S2-019; the user's v1 reference choice). Six and eight
  cranes are not rejected; they remain protocol §11 sensitivity levels.
- `max_cranes_per_vessel = 2`.
- Efficiency 1.0 / 0.92 / 0.82 / 0.72.
- Productivity 1.0 (D19).
- ServiceConfig(30, 0.5, 20) (D20, FROZEN).
- H = 240 (D18).
- Transport 250 m/min, 2 min handover, 4 units per crane.
- Congestion ρ0 0.70, g_min 0.50, landside share 0.2.
- All cargo distributions (discharge share, transshipment mix, 40 ft share 0.6, weights).
- All landside timing values (cutoff 360 min, lead U[0, 2880], dwell U[720, 4320], background
  pickup U[0, 2880]).
- The degenerate profile.

### 6.3 Nominal versus realized service (not reconciled, by design)

The nominal BAP duration remains `30 + 0.5 × workload + 20` minutes. This implies 120 moves/h
of handling. The standard fleet allows at most 2 cranes per vessel, giving
`2 × 30 × 0.92 = 55.2` moves/h. Neither value was changed to force agreement: the gap is what
Steps 4–7 measure.

The degenerate profile (`degenerate_equivalence_v1`) is applied only when requested:
- 120 moves/h cranes;
- `max_cranes = 1`;
- fleet size equal to the maximum number of vessels that can coexist on the quay;
- transport and yard couplings disabled.

## 7. Yard Bottleneck redesign

`itp_yard_bottleneck` is now a **valid initial terminal with restricted yard operations**:

- **Same physical terminal.** Quay, cranes, the 12 blocks, the layout and the 26,400 TEU
  capacity match the reference families. Distances are identical, so transport is not a
  confounder.
- **Restricted handling.** `handling_capacity_moves_per_hour = 30` (×0.5, the protocol §11
  level) per block (S2-033).
- **Higher starting occupancy.** `initial_occupancy_fraction = 0.7` (S2-034), which equals ρ0
  (S2-034). Any net inflow therefore lowers g(ρ) from the first event.
- **Traffic.** Unchanged: 18 vessels, 160 min mean inter-arrival, 300–900 moves (S2-013).
- **Declared intent.** `intended_bottleneck = yard_block_handling` (S2-008; the other families
  are `none`).

**Static stress contrast (design-time arithmetic, not an observation).** The per-block
ship-side capacity after the 20 % landside reservation is `μ × g(ρ_initial) × 0.8`:
- reference: 48 moves/h at ρ = 0.5;
- bottleneck: 24 moves/h at ρ = 0.7.

A two-crane vessel demands 55.2 moves/h, giving ratios of 0.87 and 0.43.

**Step 2 does not claim** that runtime blocking, congestion or crane starvation occurs. Only
the Step 4 simulator can observe them.

## 8. Development campaign (stabilized configuration)

### 8.1 Declared core sample

The core sample is the immutable run `experiments/scenarios/development/dev_f5789d8c91_1ee66026/`. It covers
the contiguous seeds 10,000,000–10,000,029 (medium and heavy) and 10,000,000–10,000,009 (low
and bottleneck).

**Run `dev_f5789d8c91_1ee66026`** (generator config fingerprint `f5789d8c91…e9ca179e`,
configuration SHA-256 `47c9126f…0546ce`, decisions SHA-256 `a2ea8e1d…5d9c6`, manifest
SHA-256 `13b65aa5…2326af59`, `source_git_commit = 032bc23`, `source_git_dirty = true` because
the stabilization is uncommitted).

| Family | Seeds | Accepted / planned | Rejected | Target status | Mandatory TEU min–max (max fraction) | Optional TEU (mean) | Realized initial occupancy | Containers (mean) | TEU (mean) | Exogenous occupancy proxy peak (max) |
| --- | --- | ---: | ---: | --- | --- | ---: | --- | ---: | ---: | ---: |
| itp_medium | 10,000,000–029 | 30 / 30 | 0 | 30 MET | 1,732–6,037 (0.229) | 9,256 | 0.4996–0.4999 | 14,159 | 22,648 | 0.529 |
| itp_heavy | 10,000,000–029 | 30 / 30 | 0 | 30 MET | 3,356–9,686 (0.367) | 7,128 | 0.4996–0.4999 | 16,993 | 27,182 | 0.545 |
| itp_low | 10,000,000–009 | 10 / 10 | 0 | 10 MET | 1,821–2,914 (0.110) | 10,688 | 0.4996–0.4998 | 11,009 | 17,624 | 0.523 |
| itp_yard_bottleneck | 10,000,000–009 | 10 / 10 | 0 | 10 MET | 3,010–5,980 (0.227) | 13,957 | 0.6996–0.6999 | 18,468 | 29,561 | 0.730 |

- **Validation:**
  - every scenario passes the scenario-stage validator (`--validate`: 80 / 80, 0 issues);
  - `--audit` passed: manifest and per-file hashes, unique ids, 80 unique physical
    fingerprints, development band only, and no validation/test/diagnostic directories.
- **Project 03 compatibility:**
  - the collision audit examined 902 Project 03 fingerprints and found 0 collisions;
  - all 80 projections are in medium/heavy PPO support;
  - all 80 construct a `BAPScenarioInstance` and reset `DynamicBAPEnv`
    (`max_vessels = 24`, H = 240, action space 1153). No step, policy or checkpoint was used.
- **Reconciliation:** container, group, vessel-move and TEU reconciliation passes on every
  scenario (validator DQ04–DQ06).
  - Vessels: 480 medium, 720 heavy, 80 low and 180 bottleneck.
  - Workload: 251–900 moves per vessel; nominal service 175.5–500 min.
  - Containers: 40 ft share 0.600–0.601 of containers; weights 8,000–30,000 kg.
- **Block placement:**
  - Every block holds its share of the target: block fill is 0.50 in the reference
    families and 0.70 in the bottleneck.
  - Every yard container is `BLOCK_ONLY`; no slot was fabricated.
- **Distances and fleet:** quay-to-block distances are 100–1,308 m. All families use 4 cranes
  at 30 moves/h.
- **Static stress (design arithmetic only):**
  - Per-block ship-side capacity is 48 moves/h in the reference families and 24 moves/h in
    the bottleneck.
  - Against a two-crane vessel's 55.2 moves/h, the ratios are 0.87 and 0.43.
- **Episode-wide TEU pressure ratio** (cumulative, not an occupancy): 0.86 medium,
  1.03 heavy, 0.67 low, 1.12 bottleneck.
- **Regeneration:**
  - 12 scenarios (the first 3 seeds per family) were regenerated in a new process; their file
    SHA-256 values are identical to the stored files.
  - The degenerate profile (first 5 seeds per family, 20 scenarios) passes on every one:
    - every scenario is valid;
    - 120 moves/h cranes and `max_cranes = 1`;
    - 4–5 cranes (maximum number of vessels that can coexist on the quay);
    - transport and yard couplings disabled;
    - berth-projection physical fingerprint and container manifest identical to the standard
      profile.

  Equivalence itself is a Step 4 test.
- **Performance** (Windows, CPU, one process):
  - mean 4.3 s per scenario: generation 3.1 s, validation 0.87 s, serialization 0.30 s,
    projection and reset 0.002 s;
  - files 9.8–18.9 MB (mean 14.5 MB), 1.16 GB in total;
  - peak traced Python heap about 53 MB for heavy seed 10,000,000.

  Compared with the first run (2–3 s and 5–12 MB per scenario), cost per container is
  unchanged. The growth comes from the larger optional background inventory: about 14–18
  thousand containers per scenario instead of 5–13 thousand. Generation time is dominated by
  the frozen per-entity `random.Random` seeding of protocol §6.3.

### 8.2 Development-only stress audit

These probes ran in memory: full generation and scenario validation, with nothing written.
Because the probes are development-only, they are not a held-out evaluation.

| Probe | Family / seeds | Accepted & valid | Target status | Max mandatory fraction | Class |
| --- | --- | --- | --- | ---: | --- |
| Second contiguous window | medium 10,000,030–059 | 30 / 30 | 30 MET | 0.243 | — |
| Second contiguous window | heavy 10,000,030–059 | 30 / 30 | 30 MET | 0.323 | — |
| Second contiguous window | low 10,000,010–019 | 10 / 10 | 10 MET | 0.124 | — |
| Second contiguous window | bottleneck 10,000,010–019 | 10 / 10 | 10 MET (0.7) | 0.256 | — |
| 40 ft share 0.8 | heavy core window | 30 / 30 | 30 MET | 0.412 | — |
| Export-heavy (discharge share U[0.3, 0.4]) | heavy core | 30 / 30 | 30 MET | **0.490** | boundary of supported domain |
| Early exports (lead U[0, 4320]) | heavy core | 30 / 30 | 30 MET | 0.375 | — |
| Transshipment-heavy (0.5 of load, ≤ 0.7 of discharge) | heavy core | 30 / 30 | 30 MET | 0.356 | — |
| High initial occupancy 0.7 | heavy core | 30 / 30 | 30 MET | 0.367 | — |
| Low initial occupancy 0.3 (protocol level) | heavy core | 30 / 30 structurally valid | **3 MANDATORY_EXCEEDS_TARGET**, 27 MET | 0.367 | **D. Unsupported sensitivity region** |

Results:
- No structural or initial-physical failure occurred in any probe (no class A, B or C
  failure).
- With occupancy 0.3, the heavy family cannot represent the controlled level for 10 % of
  seeds. Its mandatory inventory reaches 0.367, so 0.3 is not a supported level for
  `itp_heavy` under the current cargo and timing assumptions.

### 8.3 Supported parameter domain (evidence, not proof)

On the windows examined, the stabilized configuration supports:
- all four families at their configured targets;
- 40 ft shares up to 0.8;
- export lead up to 4,320 min;
- transshipment up to 0.5 of load;
- heavy initial occupancy from about 0.4 up to 0.7.

Discharge shares at or below 0.3–0.4 sit at the boundary for heavy at target 0.5. Heavy at
0.3 is outside the domain.

No sample proves feasibility for every future seed. A seed whose mandatory inventory exceeds
capacity is rejected explicitly. A seed whose mandatory inventory exceeds the target is
reported, never repaired.

## 9. Validity levels

| Level | Status in Step 2 |
| --- | --- |
| 1. Structural validity (ids, schema, relationships, geometry, TEU, references, timestamps) | Established: scenario-stage validator on every scenario |
| 2. Initial physical feasibility (mandatory cargo fits, eligible capacity, no double counting, size restrictions, no fabricated slots) | Established on the declared samples |
| 3. Runtime operational feasibility (blocking, recovery, deadlock, completion) | **Not established**: Step 4 |

## 10. Fingerprints and identity

| Change | Fingerprints that change | Fingerprints that do not change |
| --- | --- | --- |
| Yard capacity, block count, lines or handling | terminal geometry; physical; container manifest and exogenous schedule (only through the optional background count) | vessel records, berth projection (content and physical), all vessel-cargo container ids and attributes |
| Pre-staging assumption (export lead) | container manifest, exogenous schedule, physical | vessel records and berth projection |
| Cargo change that alters workload | berth projection | — |

**Regression check.** `test_u_project03_projection_unchanged_by_stabilization` compares the
stabilized berth projections of `itp_low` and `itp_medium` seed 10,000,000 with those recorded
by the first Step 2 run. They are identical, so the Project 03 inputs did not change.

**Versions.**
- The generator config fingerprint changes. The new run id is derived from it, and the old run
  is never relabelled.
- `generator_version` (`itp_generator_v1`, FROZEN S2-001) and `scenario_schema_version`
  (`itp_scenario_v1`) are unchanged: the scenario schema is backward compatible.
- The configuration file schema is now 2 (amendment A9).

## 11. Approval table

Status remains `PROPOSED_PENDING_REVIEW` for every row until the user approves. A small
follow-up can then freeze the approved rows without changing any physics.

| ID | Config path | Value (proposed final v1) | Unit | Source | Meaning | Step 3/4 relevance | Changes physical fingerprint | Changes berth projection | Affects initial feasibility | Recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S2-005 | `seed_bands.diagnostic` | {"first": 13000000, "last": 13999999} | integer seed | STEP1_PROPOSED | reserved diagnostic seed band | Step 8 sensitivity | no | no | no | approve |
| S2-007 | `development_batch` | {"itp_medium": 30, "itp_heavy": 30, "itp_low": 10, "itp_yard_bottleneck": 10} | scenarios | STEP1_INFERRED | development batch sizes | Step 4 equivalence sample | no | no | no | approve |
| S2-008 | `families.itp_medium.intended_bottleneck` (+3) | itp_medium.intended_bottleneck="none"; itp_heavy.intended_bottleneck="none"; itp_low.intended_bottleneck="none"; itp_yard_bottleneck.intended_bottleneck="yard_block_handling" | none | STEP2_BRIEF | declared bottleneck resource label | Step 4 reports whether it binds | no | no | no | approve |
| S2-010 | `families.itp_medium.traffic` | {"vessel_count": 16, "mean_interarrival_minutes": 190.0, "min_vessel_length_m": 200.0, "max_vessel_length_m": 360.0, "min_workload_moves": 250, "max_workload_moves": 900} | vessels; minutes; meters; moves | STEP1_PROPOSED | medium traffic (16 vessels, 190 min) | traffic load; PPO support | yes | yes | yes | approve (mirrors P03) |
| S2-011 | `families.itp_heavy.traffic` | {"vessel_count": 24, "mean_interarrival_minutes": 120.0, "min_vessel_length_m": 200.0, "max_vessel_length_m": 360.0, "min_workload_moves": 250, "max_workload_moves": 900} | vessels; minutes; meters; moves | STEP1_PROPOSED | heavy traffic (24 vessels, 120 min) | traffic load; PPO support | yes | yes | yes | approve (mirrors P03) |
| S2-012 | `families.itp_low.traffic` | {"vessel_count": 8, "mean_interarrival_minutes": 300.0, "min_vessel_length_m": 200.0, "max_vessel_length_m": 360.0, "min_workload_moves": 250, "max_workload_moves": 900} | vessels; minutes; meters; moves | REPOSITORY_DERIVED | low traffic (8 vessels, 300 min) | low-load diagnostics | yes | yes | yes | approve |
| S2-013 | `families.itp_yard_bottleneck.traffic` | {"vessel_count": 18, "mean_interarrival_minutes": 160.0, "min_vessel_length_m": 200.0, "max_vessel_length_m": 360.0, "min_workload_moves": 300, "max_workload_moves": 900} | vessels; minutes; meters; moves | REPOSITORY_DERIVED | bottleneck traffic (18 vessels, 160 min) | bottleneck diagnostics | yes | yes | yes | approve |
| S2-014 | `families.itp_medium.role` (+1) | "primary" | none | STEP1_PROPOSED | primary family role | Step 7 family set | no | no | no | approve |
| S2-015 | `families.itp_low.role` (+1) | "development_diagnostic" | none | STEP2_PROVISIONAL | development/diagnostic role | excluded from primary claims | no | no | no | approve |
| S2-019 | `families.itp_medium.terminal.quay_crane_count` (+3) | 4 | cranes | REPOSITORY_DERIVED | quay crane fleet (v1 reference) | crane policies; Coupling A | yes | no | no | **freeze (user-selected)** |
| S2-020 | `families.itp_medium.terminal.quay_crane_moves_per_hour` (+3) | 30.0 | moves/h | STEP1_PROPOSED | crane nominal rate | Coupling A | yes | no | no | approve |
| S2-021 | `families.itp_medium.terminal.max_cranes_per_vessel` (+3) | 2 | cranes | REPOSITORY_DERIVED | max cranes per vessel | crane allocation limit | yes | no | no | approve |
| S2-022 | `families.itp_medium.yard.block_count` (+3) | 12 | blocks | STEP2_PROVISIONAL | yard block count | yard capacity, distances | yes | no | yes | approve (stabilization) |
| S2-023 | `families.itp_medium.yard.capacity_teu` (+3) | 2200.0 | TEU | REPOSITORY_DERIVED | TEU capacity per block | TEU reservation gate | yes | no | yes | approve |
| S2-026 | `families.itp_medium.yard.bay_count` (+3) | 40 | bays | STEP2_PROVISIONAL | bays per block | geometry; G1 grid | yes | no | yes | approve |
| S2-027 | `families.itp_medium.yard.row_count` (+3) | 14 | rows | STEP2_PROVISIONAL | rows per block | geometry; G1 grid | yes | no | yes | approve |
| S2-028 | `families.itp_medium.yard.max_tiers` (+3) | 5 | tiers | STEP2_PROVISIONAL | max tiers (fill limit 0.8) | geometry; G1 grid | yes | no | yes | approve |
| S2-031 | `families.itp_medium.yard.handling_capacity_moves_per_hour` (+2) | 60.0 | moves/h per block | STEP2_PROVISIONAL | block handling capacity (reference) | Coupling C; yard policies | yes | no | no | approve or replace before Step 4 freeze |
| S2-032 | `families.itp_medium.yard.initial_occupancy_fraction` (+2) | 0.5 | fraction of total capacity_teu | STEP1_INFERRED | initial occupancy target (reference) | starting congestion | yes | no | yes | approve |
| S2-033 | `families.itp_yard_bottleneck.yard.handling_capacity_moves_per_hour` | 30.0 | moves/h per block | STEP2_PROVISIONAL | block handling capacity (bottleneck) | Coupling C stress | yes | no | no | approve (stabilization) |
| S2-034 | `families.itp_yard_bottleneck.yard.initial_occupancy_fraction` | 0.7 | fraction of total capacity_teu | STEP1_INFERRED | initial occupancy target (bottleneck) | starting congestion stress | yes | no | yes | approve (stabilization) |
| S2-035 | `families.itp_medium.yard.block_line_count` (+3) | 3 | lines | STEP2_PROVISIONAL | block lines parallel to the quay | distances; layout | yes | no | yes | approve (stabilization) |
| S2-040 | `yard_layout.apron_depth_m` (+3) | apron_depth_m=100.0; block_gap_m=40.0; block_line_gap_m=40.0; gate_setback_m=100.0 | m | STEP2_PROVISIONAL | layout spacing | Coupling B distances | yes | no | yes (line width) | approve |
| S2-041 | `yard_layout.ground_slot_length_m` (+1) | ground_slot_length_m=6.5; ground_slot_width_m=2.8 | m | STEP1_PROPOSED | ground slot footprint | distances; visuals | yes | no | yes (line width) | approve |
| S2-043 | `yard_layout.capabilities` (+1) | capabilities=["general"]; allowed_sizes=["20_ft", "40_ft"] | none | STEP2_PROVISIONAL | block capabilities and allowed sizes | yard eligibility | yes | no | yes | approve |
| S2-050 | `cargo.discharge_share_min` (+1) | discharge_share_min=0.4; discharge_share_max=0.6 | fraction of workload_moves | STEP2_PROVISIONAL | discharge share of workload | cargo balance | yes | no | yes | approve (synthetic) |
| S2-051 | `cargo.transshipment_share_of_load` (+2) | transshipment_share_of_load=0.3; max_transshipment_share_of_discharge=0.5; min_transshipment_connection_min=720.0 | fraction; fraction; minutes | STEP2_PROVISIONAL | transshipment mix and connection | inter-vessel dependencies; rollover | yes | no | yes | approve (synthetic) |
| S2-052 | `cargo.forty_ft_share` | 0.6 | fraction of containers | STEP2_PROVISIONAL | 40 ft share | TEU pressure | yes | no | yes | approve (synthetic) |
| S2-053 | `cargo.empty_share` (+2) | 0.0 | fraction of containers | STEP2_PROVISIONAL | empty/reefer/hazardous shares = 0 | no capability segregation in v1 | yes | no | no | approve |
| S2-054 | `cargo.laden_weight_kg` (+1) | laden_weight_kg={"20_ft": {"min": 8000, "max": 28000}, "40_ft": {"min": 10000, "max": 30000}}; empty_weight_kg={"20_ft": 2300, "40_ft": 3800} | kg | STEP2_PROVISIONAL | container weights (unused by v1 physics) | Project 05 later | yes | no | no | approve |
| S2-060 | `landside.export_gate_lead_max_min` (+3) | export_gate_lead_max_min=2880.0; import_dwell_min_min=720.0; import_dwell_max_min=4320.0; initial_import_pickup_max_min=2880.0 | min | STEP2_PROVISIONAL | landside timing (lead, dwell, background pickup) | landside demand; pre-staging | yes | no | yes | approve (synthetic) |
| S2-071 | `physics_profiles.standard_v1.crane.efficiency` | {"one": 1.0, "two": 0.92, "three": 0.82, "four_plus": 0.72} | factor | STEP1_PROPOSED | multi-crane efficiency | Coupling A | yes | no | no | approve |
| S2-073 | `physics_profiles.standard_v1.transport` | {"enabled": true, "speed_m_per_min": 250.0, "handover_min": 2.0, "units_per_crane": 4} | bool; m/min; min; units | STEP1_PROPOSED | transport coefficients | Coupling B | yes | no | no | approve |
| S2-074 | `physics_profiles.standard_v1.yard` | {"constraints_enabled": true, "congestion_rho0": 0.7, "congestion_g_min": 0.5, "landside_reserved_fraction": 0.2, "gate_flow_demand": "block_handling_capacity"} | bool; fraction; factor; fraction; mode | STEP1_PROPOSED | yard congestion / landside share | Coupling C | yes | no | no | approve |
| S2-075 | `physics_profiles.standard_v1.work` | {"batch_size_containers": 10, "max_load_wait_min": 240.0} | containers; min | STEP1_PROPOSED | work batch size, rollover wait | batching; rollover (confirm at Step 4) | yes | no | no | confirm at Step 4 |
| S2-077 | `physics_profiles.standard_v1.episode` | {"max_drain_extension_min": 10080.0} | min | STEP1_PROPOSED | drain extension | episode end; projection drain | yes | yes | no | approve |
| S2-078 | `physics_profiles.standard_v1.kernel` | {"same_timestamp_cycle_limit": 10000} | cycles | STEP1_PROPOSED | same-timestamp cycle limit | kernel livelock guard | yes | no | no | confirm at Step 4 |
| S2-079 | `physics_profiles.standard_v1.landside` | {"export_cutoff_min": 360.0} | min | STEP2_PROVISIONAL | export cutoff | export timing; DQ11 | yes | no | yes | approve (synthetic) |

FROZEN (no approval needed, 13): S2-001, S2-002, S2-003, S2-004, S2-006, S2-016, S2-017, S2-018, S2-042, S2-070, S2-072, S2-076, S2-080. Justifications for each row are in the `rationale` field of `configs/generator/itp_generator_v1_decisions.yaml`. Every value is a synthetic research assumption unless its source is STEP1_FROZEN; none is an industry calibration.

## 12. Remaining limitations

- Every cargo, landside and yard number is a synthetic research assumption (§11), not
  calibrated.
- Scenario files grew to about 10–19 MB, because background inventory is now real individual
  containers on a 26,400 TEU yard. Generation cost is dominated by the frozen per-entity stream
  seeding (protocol §6.3) and scales linearly with container count.
- The bottleneck's intended mechanism is a design statement; Step 4 must observe whether it
  binds.
- `itp_low` and `itp_yard_bottleneck` remain development/diagnostic families.
