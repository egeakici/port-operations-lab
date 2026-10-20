# Step 7 single owner approval packet

**All 28 values are still PENDING.**

Canonical packet SHA-256: `823c39239b289571da0047d87fe2d80863fe6840323bd34d8c7ad6fec99d0636`.

Recommendation: retain these exact current values as a declared **SYNTHETIC, UNCALIBRATED V1**.
This is a proposal, not approval or a claim that the values describe a real terminal.

Exact YAML values and units below come from the live validated register; every covered config leaf matches.
The 15 keep recommendations and 13 deliberate owner decisions are preserved from the prior matrix.

| ID | Exact existing values by config path | Unit / source kind | Evidence / uncertainty | KPI impact and interdependence | Recommendation | Status |
| --- | --- | --- | --- | --- | --- | --- |
| S2-005 | `{"seed_bands.diagnostic": {"first": 13000000, "last": 13999999}}` | integer seed; STEP1_PROPOSED | Collision audit (protocol §6.2); Band reuse would contaminate Step 8; none observed | `scenarios/config.py` split bands; generation refused outside development. No physics | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-007 | `{"development_batch": {"itp_heavy": 30, "itp_low": 10, "itp_medium": 30, "itp_yard_bottleneck": 10}}` | scenarios; STEP1_INFERRED | Step 4 equivalence protocol minimum; None for results; development only | `scenarios/outputs.py` default batch plan; supplies the 80-scenario gates | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-008 | `{"families.itp_heavy.intended_bottleneck": "none", "families.itp_low.intended_bottleneck": "none", "families.itp_medium.intended_bottleneck": "none", "families.itp_yard_bottleneck.intended_bottleneck": "yard_block_handling"}` | none; STEP2_BRIEF | Step 2 stabilization §11; Mislabel risk: Step 4/5 showed the bottleneck family is handling-bound | Recorded in manifests; changes no draw | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-010 | `{"families.itp_medium.traffic": {"max_vessel_length_m": 360.0, "max_workload_moves": 900, "mean_interarrival_minutes": 190.0, "min_vessel_length_m": 200.0, "min_workload_moves": 250, "vessel_count": 16}}` | vessels; minutes; meters; moves; STEP1_PROPOSED | Project 03 preset (PPO support); Traffic intensity sets congestion and rollover; tied to PPO support | `scenarios/generator.py` vessel draws; sets berth load, crane demand, N_out | REQUIRES_USER_DECISION | PENDING |
| S2-011 | `{"families.itp_heavy.traffic": {"max_vessel_length_m": 360.0, "max_workload_moves": 900, "mean_interarrival_minutes": 120.0, "min_vessel_length_m": 200.0, "min_workload_moves": 250, "vessel_count": 24}}` | vessels; minutes; meters; moves; STEP1_PROPOSED | Project 03 preset; Heaviest load; four-crane truncation (Step 4/5); 24 is the PPO capacity limit | As row 4; 24 = PPO `max_vessels` | REQUIRES_USER_DECISION | PENDING |
| S2-012 | `{"families.itp_low.traffic": {"max_vessel_length_m": 360.0, "max_workload_moves": 900, "mean_interarrival_minutes": 300.0, "min_vessel_length_m": 200.0, "min_workload_moves": 250, "vessel_count": 8}}` | vessels; minutes; meters; moves; REPOSITORY_DERIVED | Closest repository preset; Step 1 defines no LOW; Not a primary family; must not enter primary claims (S2-015) | As row 4 | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-013 | `{"families.itp_yard_bottleneck.traffic": {"max_vessel_length_m": 360.0, "max_workload_moves": 900, "mean_interarrival_minutes": 160.0, "min_vessel_length_m": 200.0, "min_workload_moves": 300, "vessel_count": 18}}` | vessels; minutes; meters; moves; REPOSITORY_DERIVED | P02 preset; ETA and productivity noise deliberately dropped (D18/D19); Bottleneck strength also depends on S2-033/034 (approved) | As row 4 | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-014 | `{"families.itp_heavy.role": "primary", "families.itp_medium.role": "primary"}` | none; STEP1_PROPOSED | Protocol §6.5; Changing it after viewing results would be selection | Index/manifest; decides which families enter Step 7 primary contrasts | REQUIRES_USER_DECISION | PENDING |
| S2-015 | `{"families.itp_low.role": "development_diagnostic", "families.itp_yard_bottleneck.role": "development_diagnostic"}` | none; STEP2_PROVISIONAL | Step 2 brief §8; Promoting them needs an amendment before validation | Excluded from primary contrasts | REQUIRES_USER_DECISION | PENDING |
| S2-026 | `{"families.itp_heavy.yard.bay_count": 40, "families.itp_low.yard.bay_count": 40, "families.itp_medium.yard.bay_count": 40, "families.itp_yard_bottleneck.yard.bay_count": 40}` | bays; STEP2_PROVISIONAL | Arithmetic fit to the 1200 m quay (stabilization report); Interacts with transport (row 19); `UNVERIFIED_SYNTHETIC_ASSUMPTION` | Generator block footprint → transfer points → `simulator/kernel.py` transport distances; G1 grid | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-027 | `{"families.itp_heavy.yard.row_count": 14, "families.itp_low.yard.row_count": 14, "families.itp_medium.yard.row_count": 14, "families.itp_yard_bottleneck.yard.row_count": 14}` | rows; STEP2_PROVISIONAL | Arithmetic (2240 TEU ≥ 2200); `UNVERIFIED_SYNTHETIC_ASSUMPTION` | Block geometry / G1 grid (capacity itself is S2-022, approved) | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-028 | `{"families.itp_heavy.yard.max_tiers": 5, "families.itp_low.yard.max_tiers": 5, "families.itp_medium.yard.max_tiers": 5, "families.itp_yard_bottleneck.yard.max_tiers": 5}` | tiers; STEP2_PROVISIONAL | Step 1 fill rule; Bounds feasible capacity_teu values | `operating_fill_limit`; validator capacity bound (geometric × fill) | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-035 | `{"families.itp_heavy.yard.block_line_count": 3, "families.itp_low.yard.block_line_count": 3, "families.itp_medium.yard.block_line_count": 3, "families.itp_yard_bottleneck.yard.block_line_count": 3}` | lines; STEP2_PROVISIONAL | Stabilization report §6; Far blocks bind transport; P_y choice interacts (balanced uses far blocks) | Block origins → quay-to-block distances 100–1308 m (transport coupling) | REQUIRES_USER_DECISION | PENDING |
| S2-040 | `{"yard_layout.apron_depth_m": 100.0, "yard_layout.block_gap_m": 40.0, "yard_layout.block_line_gap_m": 40.0, "yard_layout.gate_setback_m": 100.0}` | m; STEP2_PROVISIONAL | Simple synthetic layout; With D10 transport, cranes are capped below 30 moves/h beyond ~750 m; `UNVERIFIED_SYNTHETIC_ASSUMPTION` | Generator layout → transport distances; gate position | REQUIRES_USER_DECISION | PENDING |
| S2-041 | `{"yard_layout.ground_slot_length_m": 6.5, "yard_layout.ground_slot_width_m": 2.8}` | m; STEP1_PROPOSED | Step 1 proposed synthetic footprint; Only via distances | Block footprint; transfer points | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-043 | `{"yard_layout.allowed_sizes": ["20_ft", "40_ft"], "yard_layout.capabilities": ["general"]}` | none; STEP2_PROVISIONAL | Consistent with S2-053 = 0; Becomes material if special cargo is added | Step 3 eligibility tests in P_y | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-050 | `{"cargo.discharge_share_max": 0.6, "cargo.discharge_share_min": 0.4}` | fraction of workload_moves; STEP2_PROVISIONAL | Symmetric placeholder; Directly scales the CARGO-NI denominator and load-wait exposure | `generator.py` discharge/load split → import vs outbound obligations; **sets N_out** | REQUIRES_USER_DECISION | PENDING |
| S2-051 | `{"cargo.max_transshipment_share_of_discharge": 0.5, "cargo.min_transshipment_connection_min": 720.0, "cargo.transshipment_share_of_load": 0.3}` | fraction; fraction; minutes; STEP2_PROVISIONAL | Placeholder so every flow occurs; The main driver of rollover and of PREFIX divergences; berth order changes cargo availability | `generator.py` transshipment links; kernel load waits (`CARGO_UNAVAILABLE`, D17 rollover) | REQUIRES_USER_DECISION | PENDING |
| S2-052 | `{"cargo.forty_ft_share": 0.6}` | fraction of containers; STEP2_PROVISIONAL | Placeholder, not calibrated; Changes TEU pressure, not move counts | Container sizes → TEU occupancy, yard pressure | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-053 | `{"cargo.empty_share": 0.0, "cargo.hazardous_share": 0.0, "cargo.reefer_share": 0.0}` | fraction of containers; STEP2_PROVISIONAL | No layout for special blocks (Step 1); Non-zero needs a layout amendment first | All cargo general laden | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-054 | `{"cargo.empty_weight_kg": {"20_ft": 2300, "40_ft": 3800}, "cargo.laden_weight_kg": {"20_ft": {"max": 28000, "min": 8000}, "40_ft": {"max": 30000, "min": 10000}}}` | kg; STEP2_PROVISIONAL | Uniform synthetic bounds; None in v1 | Recorded only; unused by v1 physics | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-060 | `{"landside.export_gate_lead_max_min": 2880.0, "landside.import_dwell_max_min": 4320.0, "landside.import_dwell_min_min": 720.0, "landside.initial_import_pickup_max_min": 2880.0}` | min; STEP2_PROVISIONAL | Synthetic, uniform; Sets yard occupancy and landside load; outbound cargo availability | `generator.py` export pre-staging and pickup requests → mandatory inventory, gate flow, R5 release queue | REQUIRES_USER_DECISION | PENDING |
| S2-071 | `{"physics_profiles.standard_v1.crane.efficiency.four_plus": 0.72, "physics_profiles.standard_v1.crane.efficiency.one": 1.0, "physics_profiles.standard_v1.crane.efficiency.three": 0.82}` | factor; STEP1_PROPOSED | Project 02 defaults; Matters only if `max_cranes_per_vessel` changes | `simulator/catalog.py` efficiency(n); unreachable with `max_cranes_per_vessel = 2` | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-073 | `{"physics_profiles.standard_v1.transport": {"enabled": true, "handover_min": 2.0, "speed_m_per_min": 250.0, "units_per_crane": 4}}` | bool; m/min; min; units; STEP1_PROPOSED | Step 1 proposal; protocol §11 levels 3/4/6 units, 150/250/400 m/min; Caps crane rates at far blocks; interacts with the balanced P_y; `UNVERIFIED_SYNTHETIC_ASSUMPTION` | `simulator/kernel.py` transport rate cap per crane (cycle 2d/v + handover) | REQUIRES_USER_DECISION | PENDING |
| S2-074 | `{"physics_profiles.standard_v1.yard": {"congestion_g_min": 0.5, "congestion_rho0": 0.7, "constraints_enabled": true, "gate_flow_demand": "block_handling_capacity", "landside_reserved_fraction": 0.2}}` | bool; fraction; factor; fraction; mode; STEP1_PROPOSED | Step 1 proposal; Governs the yard-handling bottleneck and landside/ship sharing | `simulator/physics.py` share_block_capacity / congestion factor; kernel handling rates | REQUIRES_USER_DECISION | PENDING |
| S2-077 | `{"physics_profiles.standard_v1.episode": {"max_drain_extension_min": 10080.0}}` | min; STEP1_PROPOSED | Project 03 dynamic default; Sets the censoring point of the primary KPI and the cargo cutoff | `catalog.drain_limit_min` = last arrival + extension = `T_end`; D24 censoring; CARGO-NI cutoff | REQUIRES_USER_DECISION | PENDING |
| S2-078 | `{"physics_profiles.standard_v1.kernel": {"same_timestamp_cycle_limit": 10000}}` | cycles; STEP1_PROPOSED | Step 1 proposal; A safety bound; never hit in development runs | `kernel.py` livelock guard | KEEP_AS_SYNTHETIC_V1 | PENDING |
| S2-079 | `{"physics_profiles.standard_v1.landside": {"export_cutoff_min": 360.0}}` | min; STEP2_PROVISIONAL | Placeholder (6 h); Shifts export availability relative to arrival | `generator.py` export gate-in times; validator DQ11 causality | REQUIRES_USER_DECISION | PENDING |

## Thirteen consequential decisions

- S2-010 / S2-011: 16/24 vessels and 190/120-minute interarrival means define terminal load and PPO support; congestion and N_out follow from those traffic draws.
- S2-014 / S2-015: Medium/Heavy alone supply primary claims. Low/Bottleneck stay development diagnostics; favorable F3 cargo performance cannot promote a family.
- S2-035 / S2-040: three block lines and 100/40/40/100-metre spacing create transfer distances and couple the shared balanced yard primitive to crane transport rate.
- S2-050 / S2-051: 0.4–0.6 discharge share, 30% transshipment load share, 50% discharge limit and 720-minute connection shape outbound denominator and cargo dependencies. Arrival connection does not guarantee yard availability.
- S2-060 / S2-079: lead/dwell/pickup bounds and 360-minute cutoff govern mandatory initial inventory, hidden landside requests, load availability and gate queues.
- S2-073 / S2-074: transport speed/handover/units and yard congestion/sharing coefficients determine effective service; none is real-port calibrated.
- S2-077: 10080-minute drain extension defines common T_end, D24 censoring and the cargo completion cutoff. Shorter turnaround cannot excuse missing outbound obligations.

No value has been adjusted using F3. D15=10, D17=240, R5 and QC8 remain separately approved.
Step 7 plan: 40 validation +100 test scenarios; 1260 integrated +700 berth-reference episodes.
All checkpoint seeds are nested inside scenario; they are not extra traffic observations.
The accompanying analysis contract retains the protocol’s existing seed120001 for turnaround bootstrap and AM-06 seed20261013 for cargo; final inference is Step8.

## One owner decision

Do you explicitly approve all 28 listed current synthetic v1 values and their specified medium/heavy primary vs low/bottleneck diagnostic roles, including their lack of real-terminal calibration, for the Step 7 pre-validation scientific lock? If any row differs, state the replacement now.

Suggested explicit response: “I approve all 28 exact values in the linked Step 7 packet as uncalibrated synthetic v1, with Medium/Heavy primary and Low/Bottleneck diagnostic roles, for the pre-validation scientific lock. Retain the accompanying source-defined counts and analysis contract.”

If any value changes, supply the replacement and rationale before validation/test generation. No held-out outcomes have been read.

## Owner reply received —2026-10-14 (append-only)

The owner answered **`1`** to the exact packet-linked question. Displayed option1
was **“Approve all 28 exact packet values as uncalibrated synthetic v1”**;
option2 was amendment. This is explicit approval of the28 exact values and
Medium/Heavy primary versus Low/Bottleneck diagnostic roles, with the displayed
lack-of-real-terminal-calibration qualification. The approved packet hash is
`823c39239b289571da0047d87fe2d80863fe6840323bd34d8c7ad6fec99d0636`.

Raw incoming reply and its displayed-question/option context are archived at
`experiments/step7_paired_v1/owner_reply_20261014.txt` and
`experiments/step7_paired_v1/owner_reply_context_20261014.json`.
The original pending proposal above and its machine packet remain unchanged.
Register activation is sequenced after the in-flight mandatory regression
finishes so its live approval-state fixtures retain the same snapshot. The
approval does not bypass clean regressions, source checks or exclusive lock
creation, and no sensitive scenario has been generated or evaluated.


## Manual-only execution update - 2026-10-14

The owner supersedes unattended continuation and automatic commits with CODE-ONLY DEVELOPMENT / MANUAL EXECUTION. The old supervisor is disabled with its original bytes archived by hash. The known old processes are absent and the full regression has no sealed completion result; it is incomplete, not PASS. Actual 28-value approval is archived and remains valid, but live activation, fresh current-source regressions, the new pre-lock plan, commits, lock and campaign are explicit owner-run steps. No new scientific episode, training, expensive test or commit was executed during this adaptation. Prior pending-state descriptions above are historical intake state, not a request for repeated approval. See [manual_execution_runbook.md](manual_execution_runbook.md) and [step7_manual_execution_audit.md](step7_manual_execution_audit.md). All scientific values/roles, frozen policy source and checkpoints are retained.
