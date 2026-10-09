# Step 2 — Unified Synthetic Scenario Generator

Generator `itp_generator_v1`, scenario schema `itp_scenario_v1`, package
`integrated_terminal_pilot.scenarios`. Built on Step 1 commit `48b9f80`;
first implemented in commit `032bc23`, then **stabilized** (configuration schema 2,
12-block reference yard, rebuilt yard-bottleneck family). The evidence, alternatives
and approval table are in [step2_stabilization_report.md](step2_stabilization_report.md).

**SYNTHETIC — NOT CALIBRATED TO A REAL TERMINAL.** Step 2 generates immutable
scenario definitions only. It allocates no berths, assigns no cranes,
places no containers in slots, simulates nothing, and produces no performance
results. No policy, PPO inference or training was run.

## 1. Installation and commands

From `integrated-terminal-pilot` in PowerShell (Projects 01–03 must already be
installed in editable mode, as for Project 03):

```powershell
python -m pip install -e .
python scripts/generate_integrated_scenarios.py --dry-run
python scripts/generate_integrated_scenarios.py --generate --family itp_medium=5 --family itp_heavy=5 --family itp_low=5
python scripts/validate_integrated_scenarios.py --validate --run-dir experiments/scenarios/development/<run_id>
python scripts/validate_integrated_scenarios.py --audit --run-dir experiments/scenarios/development/<run_id>
python -m pytest -q
```

| Mode | Effect |
| --- | --- |
| `--dry-run` | Validates the configuration and decision register; prints planned families, seeds, output directory, decision statuses and PPO compatibility expectations; writes nothing |
| `--generate` | Generates, validates, projects and resets `DynamicBAPEnv` for each scenario. Writes a new immutable run (refuses an existing run or a stale `.partial`) |
| `--validate` | Re-reads every stored scenario: schema, DQ rules, fingerprints, index reconciliation |
| `--audit` | Manifest sidecar and per-file SHA-256, unique ids and physical fingerprints, split/seed bands, absence of validation/test/diagnostic directories, Project 03 collision audit, DQ summary, compatibility coverage |

Without `--family`, `--generate` uses `development_batch` (30 medium, 30 heavy,
10 low, 10 bottleneck; contiguous seeds from 10,000,000). Other options: `--first-seed-offset`,
`--profile degenerate_equivalence_v1`, `--run-id`, `--output-root`,
`--config`, `--decisions`. No GPU is needed and no model weights are loaded.

## 2. Configuration and decision resolution

- `configs/generator/itp_generator_v1.yaml` holds the parameter values.
- `configs/generator/itp_generator_v1_decisions.yaml` holds one record per
  decision, with these fields: `decision_id`, `parameter_name`, `parameter_paths`,
  `selected_value(s)`, `unit`, `allowed_range`, `source_kind`,
  `source_document`, `source_section`, `rationale`, `status`,
  `linked_step1_decision`, `impact_on_generator`, `impact_on_future_simulator`.
- The loader fails if any parameter is uncovered or covered twice, or if a
  record's value differs from the configuration. It also fails if a value not taken from a
  FROZEN Step 1 decision (or a Step 2 process rule) is labelled `FROZEN`.

Status counts: **13 FROZEN, 38 PROPOSED_PENDING_REVIEW, 0 BLOCKED, 0 DEFERRED**
(51 records). Before the stabilization they were 13 / 37 / 1 / 0. The stabilization
removed the four superseded bottleneck-yard records S2-024, S2-025 (BLOCKED), S2-029 and
S2-030, and added S2-008, S2-033, S2-034 and S2-035.

| Source kind | Examples |
| --- | --- |
| Step 1 FROZEN | quay 1200 m / 20 m (D04), ServiceConfig 30/0.5/20 (D20), productivity 1.0 (D19), H = 240 (D18), seed bands (D23), stream namespace, bay axis X, degenerate profile |
| Step 1 PROPOSED values | crane 30 moves/h, efficiency 0.92/0.82/0.72, transport 250 m/min / 2 min / 4 units, congestion 0.70/0.50, landside share 0.2, batch 10, rollover wait 240, drain 10080, slot footprint 6.5 × 2.8 m, medium/heavy traffic, diagnostic band |
| Inferred from Step 1 sensitivity grids | initial occupancy 0.5 (middle of 0.3/0.5/0.7), ≥ 30 development scenarios per primary family |
| Repository-derived | crane fleet 4 (selected as the v1 reference by the stabilization brief §9; 6 and 8 remain sensitivity levels); 2200 TEU per block (Project 03 family configs); max_cranes 2 (Project 02 generator); low traffic (Project 03 `synthetic_low.yaml`); bottleneck traffic (Project 02 `yard_bottleneck.json`) |
| Inferred from Step 1 sensitivity grids (stabilization) | bottleneck initial occupancy 0.7 and block handling ×0.5 (protocol §11 levels) |
| Step 2 provisional, **no Step 1 value** | 12 blocks in 3 block lines (stabilization); block handling 60 moves/h (bottleneck 30); block grid 40×14×5; layout spacing (40 m roads between blocks and between lines); discharge share U[0.4, 0.6]; transshipment 0.3 of load, ≤ 0.5 of discharge, ≥ 720 min connection; 40 ft share 0.6; empty/reefer/hazardous 0.0; weights; export cutoff 360 min; export lead U[0, 2880]; import dwell U[720, 4320]; initial pickup U[0, 2880] |

Development scenarios may use PROPOSED values. **No validation or test
comparison is authorized until they are approved and frozen.** Every manifest records
`final_experiments_authorized: false`.

### 2.1 Choices that still require a decision

The first Step 2 run exposed a yard-sizing problem:
- the bottleneck family was BLOCKED (its mandatory initial inventory was 1.9–3.7 × its
  1,600 TEU yard);
- heavy seed 10,000,000 was rejected;
- most heavy seeds started far above the 0.5 occupancy target.

The stabilization fixed this with a fixed, family-level yard configuration. It did
**not** change any cargo or timing distribution (see the
[stabilization report](step2_stabilization_report.md)). What remains open is approval,
not implementation:

1. **Reference yard** (S2-022, S2-023, S2-026–S2-028, S2-035, S2-040): 12 blocks of
   2200 TEU in 3 block lines, 26,400 TEU.
2. **Bottleneck design** (S2-008, S2-033, S2-034): the same terminal, with block handling
   ×0.5 (30 moves/h) and initial occupancy 0.7.
3. **Crane fleet of 4** (S2-019): the user selected it as the v1 reference; the formal freeze
   is pending.
4. **Block handling capacity** (S2-031, 60 moves/h): there is no defensible source. It must be
   decided before Step 4 freezes physics.
5. **Cargo composition and landside timing** (S2-050 to S2-054, S2-060, S2-079): these are
   synthetic research assumptions, not calibrated values.
6. **Family roles:** `itp_low` and `itp_yard_bottleneck` remain development/diagnostic
   families. They cannot enter primary claims without a protocol amendment.

## 3. Step 2 clarifications and additive amendments

None of these changes a FROZEN Step 1 decision. Each resolves an omission or
inconsistency found while implementing. Step 1 documents are unchanged.

| ID | Issue found | Resolution |
| --- | --- | --- |
| A1 | Data contract §2.1 gives `scenario_id = itp_{family}_…`, but families are named `itp_medium` and the worked example uses `itp_example_development_seed…` | `scenario_id = {scenario_family}_{split}_seed{seed}` (the family carries the `itp_` prefix), matching the worked example |
| A2 | Standard and degenerate profiles of one seed would share an id | Additive identity key `physics_profile` (`standard_v1` / `degenerate_equivalence_v1`). Non-standard ids get the suffix `__{profile}`. Exogenous draws are profile-independent |
| A3 | Data contract §10 component fingerprints cover neither vessel records (lengths, max_cranes) nor initial yard locations, which DQ16 requires | Exogenous fingerprint includes full vessel records. Manifest fingerprint includes groups and `initial_state` and excludes the identity-only `source_scenario_id`. Physics fingerprint includes `yard_fidelity` and `physics_profile`. Additive key `generator_config_fingerprint` in the fingerprint block (null for hand-written fixtures) |
| A4 | Foundation §2 names `export_cutoff_min` as a Step 2 parameter, but no scenario field holds it, so DQ11 could not be checked from a scenario | Additive physics key `physics.landside.export_cutoff_min` |
| A5 | `BAPScenarioInstance` requires `scenario_version` and `scenario_schema_version`; data contract §11 gives no values | Both 1 (the Project 03 v1 values) |
| A6 | Step 1 taxonomy has no code for duplicate vessel/crane/block ids, invalid geometry, capability mismatch or seed-namespace violations | Additive codes `DUPLICATE_ENTITY_ID`, `INVALID_ENTITY_ID` (DQ01 extended to all registries), `INVALID_ENTITY_ATTRIBUTE`, `INVALID_YARD_GEOMETRY`, `YARD_CAPABILITY_MISMATCH` (new DQ21) and `SEED_NAMESPACE_VIOLATION` (new DQ22). Step 1 codes are unchanged |
| A7 | The worked-example excerpt puts `yard_blocks` at top level; data contract §2/§3 places them under `terminal` | Canonical position `terminal.yard_blocks`; the golden fixture follows the data contract |
| A8 | The Step 2 brief asks for LOW and YARD BOTTLENECK profiles "defined in Step 1"; Step 1 defines only medium and heavy | Added as development/diagnostic families from repository sources (Project 03 low preset, Project 02 yard_bottleneck.json without its ETA/productivity noise, which D18/D19 forbid) |
| A9 | (Stabilization) One line of blocks cannot hold more than four 260 m blocks along the 1200 m quay | **Configuration** schema 2 adds `families.*.yard.block_line_count`, `yard_layout.block_line_gap_m` and the descriptive label `families.*.intended_bottleneck`. Blocks form equal lines parallel to the quay: line 1 is nearest the quay, and ids run line by line, left to right. The **scenario** schema is unchanged, because block records already carry 2-D origins and the validator already checks 2-D footprint overlap. Configuration schema 1 is rejected with an explicit message |
| A10 | (Stabilization) The first diagnostics did not separate contract-implied initial inventory from background occupancy | Generator diagnostics report mandatory and optional initial TEU, minimum and realized occupancy, and `target_status` (`MET` / `MANDATORY_EXCEEDS_TARGET`). The scenario index adds `mandatory_initial_teu`, `optional_initial_teu`, `initial_occupancy_fraction` and `initial_target_status`. Wall-clock stage timings appear only in the manifest, so the index and quality report stay byte-reproducible |

## 4. Scenario format

Top-level keys exactly as data contract §2: `schema_version`, `identity`,
`terminal` (`quay`, `gates`, `yard_blocks`), `resources.quay_cranes`,
`vessels`, `container_groups`, `containers`, `initial_state`, `physics`,
`fingerprints`. Unknown or missing keys are rejected (DQ20). Files are
`{scenario_id}.scenario.json`, written with `indent=2` and sorted keys, so they are
byte-reproducible.

Not stored anywhere in a scenario: berth positions, berth start times, crane
assignments, slot placements of G0 containers, realized service, departures,
waiting, throughput or any KPI. Time-zero statuses are limited to
`EXPECTED_BY_VESSEL`, `EXPECTED_BY_LANDSIDE` and `IN_YARD`.

## 5. Individual containers

Every container is a `ContainerRecord` (foundation §2) with a `CNT-nnnnnn` id. The id is
synthetic and deliberately not ISO 6346. Project 01's `ContainerGroup` is reused
unchanged as the grouping layer, and every group is checked by
`ContainerGroup.from_dict`. Names follow the frozen Step 1 contract. The
conceptual names in the Step 2 brief map as follows:

| Brief name | Step 1 field |
| --- | --- |
| `flow_type` | `cargo_flow` |
| `container_size_ft` | `container_size` (`20_ft` / `40_ft`) |
| `expected_release_time_min` | `scheduled_pickup_time_min` (imports; exogenous request, hidden until due) |
| `terminal_entry_time_min`, `actual_release_time_min` | mutable state (Step 4), never in a scenario |
| `current_status`, `current_location_type`, `yard_block_id`, `bay`, `row`, `tier` | `initial_state.container_locations[*].status` / `.location` (time zero only) |

**Flows.**
- **Import:** discharged from a scenario vessel and picked up on the landside.
  Its pickup request time is `arrival + U[dwell]`, and it may fall before physical
  availability (fulfilment waits, per the Step 1 contract).
- **Export:** gate-in request at `destination arrival − cutoff − U[0, lead]`
  (`generator.export_prestaging`).
  - **Negative request:** the container entered before the episode. It is **mandatory**
    initial inventory with no in-episode gate-in.
  - **Otherwise:** the request lies in `[0, arrival − cutoff]`.
  - A vessel arriving before the cutoff has no admissible in-episode gate-in, so all of its
    exports are pre-staged.
  - Times are never shifted to fit the yard.
- **Initial inventory classes:**
  - *Mandatory* (pre-staged exports, pre-episode transshipment) always exists. It is rejected
    (`YARD_CAPACITY_EXCEEDED`) only if it exceeds the operating capacity or fits no eligible block.
  - *Optional* background imports (origin `PRE_EPISODE`, pickup U[0, 2880]) are added only
    while the occupancy target leaves room.
  - If mandatory TEU exceed the target, no background is added and nothing is removed or
    resampled. The scenario then reports `MANDATORY_EXCEEDS_TARGET`.
- **Transshipment:** discharged from an inbound vessel and loaded onto a vessel
  arriving at least 720 min later. Transshipment demand that no earlier vessel can serve
  is pre-episode transshipment inventory with origin `PRE_EPISODE` (the only
  allowed sentinel, foundation §2.1).

No fictional vessel ids are used.

## 6. TEU and move reconciliation

- **Size and TEU:** 20 ft = 1.0 TEU, 40 ft = 2.0 TEU.
- **Moves:** one ship-side crane move per container per vessel (D14). A transshipment
  container counts once at its inbound vessel and once at its outbound vessel.
- **Vessel workload:** `workload_moves` = discharge count + load count. It is drawn first
  with the Project 03 distribution and then split, so the berth projection keeps the Project 03
  workload distribution.
- **Nominal service:** `30 + 0.5 × workload + 20`, computed with Project 03
  `planned_berth_occupancy_minutes` and Project 02 `ServiceConfig`.
- **Validator checks:** group quantity and TEU against members, vessel move and TEU
  counts against containers, and nominal service against the formula.

## 7. Yard geometry and G0/G1

- **Layout:** blocks form `block_line_count` equal lines parallel to the quay.
  - Each line is centred along the quay. Line 1 starts `apron_depth_m` inland, and lines are
    separated by `block_line_gap_m` roads.
  - Blocks have 1-based Bay/Row/Tier grids, `bay_axis = X` and an even bay count.
  - Reference layout: 3 lines of 4 blocks. B01–B04 are at y = 100.0 m, B05–B08 at 179.2 m and
    B09–B12 at 258.4 m; x origins are 20, 320, 620 and 920 m. The gate is at (600, 397.6).
- **Capacity:** `capacity_teu ≤ geometric slots × (max_tiers − 1)/max_tiers`.
- **Transfer point:** the middle of the quay-side edge. Rectilinear quay-to-block distances
  range from 100 m to 1,308 m (quay point anywhere on the quay). Inner-line blocks are reached along the 40 m roads
  between blocks, so the rectilinear metric remains meaningful.
- **Separate quantities:** geometric capacity, TEU capacity, handling rate (moves/h)
  and transport coupling (physics block) are separate parameters. Occupied and reserved TEU
  are state, derived from container locations.

Generated scenarios are **G0**. Every yard container is `BLOCK_ONLY` with null
bay/row/tier, and a fabricated slot is rejected (`FIDELITY_MISLABEL`). The G1
schema (`slot_resolution = "SLOT"` plus `initial_state.slot_occupancy`) and
the foundation §6.4 slot rules are implemented in the validator and tested
on the foundation §11.5 snapshot. No stacking, relocation or accessibility
logic exists.

## 8. Randomness

Each draw uses its own `random.Random`, seeded by the frozen protocol §6.3
key `itp_v1|{family}|{split}|{seed}|{entity_kind}|{entity_id}|{attribute}`.
That key is hashed with the Project 02 SHA-256 8-byte pattern; Python's `hash()` is
never used.
- **Vessel keys:** `Vxxx`.
- **Container keys:** semantic slots such as `V007/discharge/0012`,
  `V007/export/0003`, `V007/ts_initial/0001` and `initial_import/00042`.
  Container attributes therefore do not depend on ID numbering.

Effects of cardinality and conditional draws:
- Changing a vessel's workload or discharge share changes how many container slots exist for that vessel.
- Changing transshipment parameters changes which discharge slots are transshipment.
- IDs are assigned in category order: vessel discharge, exports, pre-episode transshipment, then initial import filler. Count changes in an earlier category relabel later ones; the filler is last, so the occupancy target never relabels vessel cargo.
- The filler stops at the first draw that no longer fits the target. There is no rejection resampling.
- Tests confirm that weight-distribution changes leave arrivals, IDs and the berth projection unchanged. Yard-parameter changes leave the berth projection unchanged.

## 9. Fingerprints

| Fingerprint | Content |
| --- | --- |
| `scenario_fingerprint` | Whole document, excluding the fingerprint block |
| `terminal_geometry_fingerprint` | Quay, gates, yard blocks |
| `resource_fingerprint` | Quay cranes |
| `container_manifest_fingerprint` | Containers (without `source_scenario_id`), groups, initial state |
| `exogenous_schedule_fingerprint` | Vessel records, gate-in requests, pickup requests |
| `physics_config_fingerprint` | Physics block, yard fidelity, physics profile |
| `physical_fingerprint` | SHA-256 of the five components above (identity-free) |
| `berth_projection_fingerprint` / `berth_projection_physical_fingerprint` | Project 03 `content_fingerprint` / `rl.suites.physical_fingerprint` of the projection |
| `generator_config_fingerprint` | Canonical hash of the generator parameters |

Canonical JSON uses sorted keys, compact separators and no NaN. Wall-clock time,
paths and runtime data are never hashed.

## 10. Berth projection

`build_berth_projection` builds Project 03 `BAPScenarioInstance` and
`BAPVesselInput` (data contract §11, split label mapping development → `train`).
It carries only vessel id, arrival, length, nominal service and workload, plus
quay, clearance, H = 240 and drain settings. It never carries crane, yard,
container or landside data. `assess_ppo_support` reports the exogenous checks
G11/G12/G14/G16 per regime. `verify_dynamic_env_reset` constructs and resets
`DynamicBAPEnv` (`max_vessels = 24`), without stepping, running a policy or loading a checkpoint.
Tiny (600 m) is not generated, so every generated scenario is out of tiny support.

## 11. Validation

The scenario stage covers DQ01–DQ07, DQ09–DQ11, DQ16, DQ19, DQ20, the
time-zero prerequisites of DQ08 (one initial location per container, one container per
slot) and DQ15 (valid time-zero states), plus additive DQ21/DQ22. Every issue
records its code, DQ rule, entity, field path, message and severity
`REJECT_SCENARIO`, and the output is deterministic. Nothing is repaired.

Not validated in Step 2: runtime invariants (double location during transfers,
crane exclusivity through time, ledger conservation DQ12, source inventory
DQ13, destination reservations DQ14, cross-arm drift DQ17, leakage DQ18).
They need the Step 4 kernel.

## 12. Development data produced in Step 2

### 12.1 First run (historical, pre-stabilization; kept unchanged)

Run `experiments/scenarios/development/dev_3f1f0d9335_3e15947a/` (Git-ignored):
- **Plan:** 5 seeds per family, seeds 10,000,000–10,000,004.
- **Outcome:** 14 accepted, 1 rejected (`itp_heavy` seed 10,000,000, `YARD_CAPACITY_EXCEEDED`), and 5 blocked (`itp_yard_bottleneck`, S2-025).
- **Checks:** validate, audit, manifest hashes and the Project 03 collision audit (902 examined fingerprints, 0 collisions) all passed.
- **Provenance:** manifest SHA-256 `3a12da33…7659352`. `source_git_dirty = true`, because Step 2 files were uncommitted at generation time; regenerate from the committed tree for any later use.

| Family | Scenarios | Vessels | Containers (mean) | TEU (mean) | Moves (mean) | Import / export / transshipment | 40 ft share | Initial occupancy | TEU pressure ratio |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| itp_medium | 5 | 16 | 8,660 | 13,864 | 9,270 | 0.468 / 0.373 / 0.160 | 0.601 | 0.505 | 1.58 |
| itp_heavy | 4 | 24 | 12,519 | 20,074 | 13,904 | 0.442 / 0.391 / 0.167 | 0.603 | 0.744 | 2.28 |
| itp_low | 5 | 8 | 5,468 | 8,776 | 4,668 | 0.569 / 0.302 / 0.129 | 0.605 | 0.500 | 1.00 |

Across families:
- vessel length 201.5–359.0 m;
- workload 260–897 moves;
- nominal service 180–498.5 min;
- weights 8,000–30,000 kg;
- 4 cranes at 30 moves/h;
- blocks of 2,200 TEU;
- quay-to-block distances 100–1,150 m.

All 14 projections are in medium/heavy PPO input support and reset `DynamicBAPEnv`. There were no duplicate ids and 14 unique physical fingerprints.

Measured performance (Windows, CPU, single process):
- 2.1 s (medium), 2.8 s (heavy) and 1.2 s (low) per scenario for generation and validation;
- files of 5–12 MB;
- peak memory about 55 MB per heavy scenario.


### 12.2 Stabilized run

Run `experiments/scenarios/development/dev_f5789d8c91_1ee66026/` (Git-ignored):
- **Plan:** contiguous seeds from 10,000,000: 30 medium, 30 heavy, 10 low and 10 bottleneck.
- **Outcome:** 80 accepted, 0 rejected, 0 blocked. All 80 meet their occupancy target
  (0.5; 0.7 for the bottleneck).
- **Checks:**
  - `--validate` (80/80) and `--audit` passed, as did the Project 03 collision audit
    (902 examined fingerprints, 0 collisions).
  - All 80 projections are in medium/heavy PPO support and reset `DynamicBAPEnv`.
- **Provenance:** manifest SHA-256 `13b65aa5…2326af59`. `source_git_dirty = true`, because
  the stabilization was uncommitted at generation time.
- **Performance:** 4.3 s per scenario; files of 9.8–18.9 MB, 1.16 GB in total.

The per-family figures, the stress audit and the supported parameter domain are in the
[stabilization report](step2_stabilization_report.md) §8.

## 13. Known limitations

- Cargo, landside and yard parameters are synthetic research assumptions (PROPOSED; §2,
  approval table in the stabilization report).
- No seed of the declared windows is rejected. Accepted sets are fixed contiguous seed lists,
  never back-filled, so there is no hidden selection. Future seeds are not guaranteed: an
  infeasible seed is rejected explicitly and a target infeasibility is reported, never repaired.
- Initial occupancy 0.3 is not a supported level for `itp_heavy` (its mandatory inventory
  reaches 0.37).
- Step 2 establishes structural validity and initial physical feasibility only. Runtime
  feasibility (blocking, recovery, deadlock) is Step 4.
- G1 is a data and validation foundation only. Weights are recorded but unused.
- Only general laden cargo is generated (special-cargo shares are 0.0).
- Tiny (600 m) scenarios are not generated.
- Scenario files are large (10–19 MB): individual containers are the source of truth. Lazy or
  streaming loading may be needed in Step 4.

## 14. Prerequisites for Step 3

Approval of these Step 2 documents, the stabilization report and the decision register. The Step 3 policy
interfaces can be built on `itp_scenario_v1` as it stands, because policies consume scenario
records and Step 4 observations. The §2.1 decisions must be settled before Step 4 freezes
physics and before any validation comparison.
