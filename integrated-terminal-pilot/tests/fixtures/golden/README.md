# Golden fixture — Step 1 worked example

`itp_example_development_seed10000000.scenario.json` is the hand-written
scenario of `docs/container_yard_foundation.md` §11 (two vessels, five
containers, two blocks, one crane), converted to a complete `itp_scenario_v1`
document. It involves no random draws and is marked
`generator_version = "hand_written_example"`, `scenario_family = "itp_example"`,
`fingerprints.generator_config_fingerprint = null`. That makes it distinguishable from
generated scenarios. Values are illustrative and synthetic.

Taken verbatim from §11.1: identity fields, vessels, yard-block inputs,
container groups, containers and initial container locations.

Fixture-only assumptions (fields the excerpt omits; none changes a physical
interpretation of the example):

| # | Field | Value | Basis |
| --- | --- | --- | --- |
| F1 | `terminal.quay` | 1200.0 m, clearance 20.0 m, quay line y = 0 | D04 primary geometry, D03 |
| F2 | `terminal.gates` | one gate `G01` at x = 600 m, y = 150 + 4 × 2.8 + 100 m | Step 1 proposes one gate; position by the Step 2 layout rule (gate 100 m behind the deepest block) |
| F3 | `resources.quay_cranes` | `QC01`, 30.0 moves/h, rail `R1`, home 600 m | §11 text: "one crane at 30 moves/h" |
| F4 | `physics` | `standard_v1` profile of `configs/generator/itp_generator_v1.yaml` | Data contract §6 defaults; export cutoff 360 min keeps CNT-000004's gate-in (120) ≤ 600 − 360 |
| F5 | Derived block fields | `geometric_slot_count` 128, `geometric_capacity_teu` 128.0, `operating_fill_limit` 0.75, transfer points (126, 150) and (426, 150) | Computed from the §11.1 geometry, matching the values stated in §11.1 |
| F6 | `initial_state.block_status` | both blocks `open` | v1 default (data contract §7) |
| F7 | `identity.physics_profile` | `standard_v1` | Additive Step 2 identity key (amendment A2) |

The §11.5 G1 snapshot is not part of this G0 fixture. Tests check it with the
G1 slot validator, using the block geometry given in §11.1.
