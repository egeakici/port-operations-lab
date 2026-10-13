# Pre-Step 6 Synthetic Parameter Approval Matrix

This is an independent audit of every decision-register record that is still
`PROPOSED_PENDING_REVIEW`, read from `configs/generator/itp_generator_v1_decisions.yaml` after D15/D17
(S2-075) were recorded on 2026-10-13. It covers **28 pending records**; the register also holds 24
FROZEN, 0 BLOCKED and 0 DEFERRED. The count is computed at run time by
`benchmark.profiles.approval_state()`.

**Nothing in this matrix is approved.** The 2026-10-13 package approved AM-01 … AM-09 and S2-075
only. Every row below stays pending until the owner approves it separately and explicitly. Values
were not changed, and no sensitivity range was chosen using any A-arm result.

Already settled (not rows of this matrix):

- **Ten user-approved v1 reference values (2026-10-09):** S2-019 (4 cranes, historical v1 reference),
  S2-020, S2-021, S2-022, S2-023, S2-031, S2-032, S2-033, S2-034 and S2-071A (two-crane efficiency 0.92).
- **S2-075 (2026-10-13):** D15 = 10, D17 = 240 min.
- **The new approved eight-crane primary research profile** (AM-02) is a derived, versioned profile.
  It changes no register value; S2-019 stays 4.
- **13 records** frozen by Step 1 / Step 2 brief rules.

Legend:

- **Materiality:** H = can change cargo or turnaround outcomes materially; M = changes them under
  some families or profiles; L = provenance, labelling or unused by v1 physics.
- `UNVERIFIED_SYNTHETIC_ASSUMPTION` = no documented empirical source; the value is a design choice.
- **Recommendation labels:**
  - `KEEP_AS_SYNTHETIC_V1`: plausible as a declared synthetic constant; approve as is or amend.
  - `REQUIRES_USER_DECISION`: an outcome-relevant design choice the owner should make deliberately.
  - `REQUIRES_CONTRACT_FIX`: the record or its contract needs a correction before approval. No row
    currently carries this label.

## Matrix (28 rows)

| # | ID / provenance | Parameter, value, unit, scope | Contract role | Effect (code path; KPIs / cargo) | Evidence | Sensitivity | Risk | Recommendation | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | S2-005; STEP1_PROPOSED (protocol §6.1, "PROPOSED addition") | Diagnostic seed band 13,000,000–13,999,999 | RNG / split governance | `scenarios/config.py` split bands; generation refused outside development. No physics | Collision audit (protocol §6.2) | L | Band reuse would contaminate Step 8; none observed | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 2 | S2-007; STEP1_INFERRED (roadmap Step 4 gate) | Development batch counts 30/30/10/10 | Development data volume | `scenarios/outputs.py` default batch plan; supplies the 80-scenario gates | Step 4 equivalence protocol minimum | L | None for results; development only | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 3 | S2-008; STEP2_BRIEF label | Intended bottleneck labels (none / none / none / `yard_block_handling`) | Descriptive design label | Recorded in manifests; changes no draw | Step 2 stabilization §11 | L | Mislabel risk: Step 4/5 showed the bottleneck family is handling-bound | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 4 | S2-010; STEP1_PROPOSED; mirrors P03 `synthetic_medium.yaml` | `itp_medium`: 16 vessels, mean inter-arrival 190 min, length U[200,360] m, workload U{250…900} | Traffic (primary family) | `scenarios/generator.py` vessel draws; sets berth load, crane demand, N_out | Project 03 preset (PPO support) | H | Traffic intensity sets congestion and rollover; tied to PPO support | REQUIRES_USER_DECISION | PENDING |
| 5 | S2-011; STEP1_PROPOSED; mirrors P03 `synthetic_heavy.yaml` | `itp_heavy`: 24 vessels, 120 min, same ranges | Traffic (primary family) | As row 4; 24 = PPO `max_vessels` | Project 03 preset | H | Heaviest load; four-crane truncation (Step 4/5); 24 is the PPO capacity limit | REQUIRES_USER_DECISION | PENDING |
| 6 | S2-012; REPOSITORY_DERIVED (P03 `synthetic_low.yaml`) | `itp_low`: 8 vessels, 300 min | Traffic (development family) | As row 4 | Closest repository preset; Step 1 defines no LOW | M | Not a primary family; must not enter primary claims (S2-015) | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 7 | S2-013; REPOSITORY_DERIVED (P02 `yard_bottleneck.json`) | `itp_yard_bottleneck`: 18 vessels, 160 min, workload U{300…900} | Traffic (development family) | As row 4 | P02 preset; ETA and productivity noise deliberately dropped (D18/D19) | M | Bottleneck strength also depends on S2-033/034 (approved) | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 8 | S2-014; STEP1_PROPOSED | Medium and heavy are `primary` | Experimental design | Index/manifest; decides which families enter Step 7 primary contrasts | Protocol §6.5 | H | Changing it after viewing results would be selection | REQUIRES_USER_DECISION | PENDING |
| 9 | S2-015; STEP2_PROVISIONAL | Low and bottleneck are `development_diagnostic` | Experimental design | Excluded from primary contrasts | Step 2 brief §8 | M | Promoting them needs an amendment before validation | REQUIRES_USER_DECISION | PENDING |
| 10 | S2-026; STEP2_PROVISIONAL | 40 bays per block | Yard geometry | Generator block footprint → transfer points → `simulator/kernel.py` transport distances; G1 grid | Arithmetic fit to the 1200 m quay (stabilization report) | M | Interacts with transport (row 19); `UNVERIFIED_SYNTHETIC_ASSUMPTION` | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 11 | S2-027; STEP2_PROVISIONAL | 14 rows | Yard geometry | Block geometry / G1 grid (capacity itself is S2-022, approved) | Arithmetic (2240 TEU ≥ 2200) | L | `UNVERIFIED_SYNTHETIC_ASSUMPTION` | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 12 | S2-028; STEP2_PROVISIONAL | 5 tiers (fill limit 0.8) | Yard geometry | `operating_fill_limit`; validator capacity bound (geometric × fill) | Step 1 fill rule | L | Bounds feasible capacity_teu values | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 13 | S2-035; STEP2_PROVISIONAL (amendment A9) | 3 block lines parallel to the quay | Yard layout | Block origins → quay-to-block distances 100–1308 m (transport coupling) | Stabilization report §6 | M | Far blocks bind transport; P_y choice interacts (balanced uses far blocks) | REQUIRES_USER_DECISION | PENDING |
| 14 | S2-040; STEP2_PROVISIONAL | Apron 100 m, block gap 40 m, line gap 40 m, gate setback 100 m | Yard layout | Generator layout → transport distances; gate position | Simple synthetic layout | M | With D10 transport, cranes are capped below 30 moves/h beyond ~750 m; `UNVERIFIED_SYNTHETIC_ASSUMPTION` | REQUIRES_USER_DECISION | PENDING |
| 15 | S2-041; STEP1_PROPOSED | Ground slot 6.5 × 2.8 m | Yard geometry | Block footprint; transfer points | Step 1 proposed synthetic footprint | L | Only via distances | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 16 | S2-043; STEP2_PROVISIONAL | Capabilities `general`; sizes 20/40 ft everywhere | Yard eligibility | Step 3 eligibility tests in P_y | Consistent with S2-053 = 0 | L | Becomes material if special cargo is added | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 17 | S2-050; STEP2_PROVISIONAL | Discharge share U[0.4, 0.6] of workload | Traffic mix | `generator.py` discharge/load split → import vs outbound obligations; **sets N_out** | Symmetric placeholder | H | Directly scales the CARGO-NI denominator and load-wait exposure | REQUIRES_USER_DECISION | PENDING |
| 18 | S2-051; STEP2_PROVISIONAL | Transshipment 30 % of load; ≤ 50 % of discharge; connection ≥ 720 min | Traffic mix / inter-vessel dependency | `generator.py` transshipment links; kernel load waits (`CARGO_UNAVAILABLE`, D17 rollover) | Placeholder so every flow occurs | H | The main driver of rollover and of PREFIX divergences; berth order changes cargo availability | REQUIRES_USER_DECISION | PENDING |
| 19 | S2-052; STEP2_PROVISIONAL | 40 ft share 0.6 (≈1.6 TEU/container) | Traffic mix | Container sizes → TEU occupancy, yard pressure | Placeholder, not calibrated | M | Changes TEU pressure, not move counts | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 20 | S2-053; STEP2_PROVISIONAL | Empty/reefer/hazardous shares 0.0 | Traffic mix | All cargo general laden | No layout for special blocks (Step 1) | L | Non-zero needs a layout amendment first | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 21 | S2-054; STEP2_PROVISIONAL | Weight bounds (20 ft 8–28 t, 40 ft 10–30 t; empties 2.3/3.8 t) | Data realism | Recorded only; unused by v1 physics | Uniform synthetic bounds | L | None in v1 | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 22 | S2-060; STEP2_PROVISIONAL | Export gate lead ≤ 2880 min; import dwell U[720, 4320]; initial import pickup ≤ 2880 | Landside timing | `generator.py` export pre-staging and pickup requests → mandatory inventory, gate flow, R5 release queue | Synthetic, uniform | H | Sets yard occupancy and landside load; outbound cargo availability | REQUIRES_USER_DECISION | PENDING |
| 23 | S2-071; STEP1_PROPOSED (Project 02 ServiceConfig) | Efficiency one 1.0, three 0.82, four-plus 0.72 | Crane physics | `simulator/catalog.py` efficiency(n); unreachable with `max_cranes_per_vessel = 2` | Project 02 defaults | L (v1 profiles) | Matters only if `max_cranes_per_vessel` changes | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 24 | S2-073; STEP1_PROPOSED | Transport enabled, 250 m/min, handover 2 min, 4 units per crane | Transport coupling | `simulator/kernel.py` transport rate cap per crane (cycle 2d/v + handover) | Step 1 proposal; protocol §11 levels 3/4/6 units, 150/250/400 m/min | H | Caps crane rates at far blocks; interacts with the balanced P_y; `UNVERIFIED_SYNTHETIC_ASSUMPTION` | REQUIRES_USER_DECISION | PENDING |
| 25 | S2-074; STEP1_PROPOSED (spec §5.3–5.4) | ρ0 0.7, g_min 0.5, landside reserve 0.2, gate demand = μ_b | Yard coupling | `simulator/physics.py` share_block_capacity / congestion factor; kernel handling rates | Step 1 proposal | H | Governs the yard-handling bottleneck and landside/ship sharing | REQUIRES_USER_DECISION | PENDING |
| 26 | S2-077; STEP1_PROPOSED (Project 03 default) | Drain extension 10080 min | Termination | `catalog.drain_limit_min` = last arrival + extension = `T_end`; D24 censoring; CARGO-NI cutoff | Project 03 dynamic default | H | Sets the censoring point of the primary KPI and the cargo cutoff | REQUIRES_USER_DECISION | PENDING |
| 27 | S2-078; STEP1_PROPOSED | Same-timestamp cycle limit 10000 | Kernel safety guard | `kernel.py` livelock guard | Step 1 proposal | L | A safety bound; never hit in development runs | KEEP_AS_SYNTHETIC_V1 | PENDING |
| 28 | S2-079; STEP2_PROVISIONAL | Export cutoff 360 min | Landside timing | `generator.py` export gate-in times; validator DQ11 causality | Placeholder (6 h) | M | Shifts export availability relative to arrival | REQUIRES_USER_DECISION | PENDING |

Summary: 15 rows `KEEP_AS_SYNTHETIC_V1`, 13 rows `REQUIRES_USER_DECISION`, 0 `REQUIRES_CONTRACT_FIX`.

## Outcome-sensitive groups (flagged, not tuned)

- **Scenario-family mix and traffic** (rows 4–9): determine load and which families are primary.
- **Cargo mix and landside timing** (rows 17, 18, 22, 28): determine `N_out`, transshipment dependencies,
  cargo availability and therefore rollover. This group is the most consequential for CARGO-NI.
- **Transport and yard coupling** (rows 13, 14, 24, 25): determine realized crane rates and yard
  handling bottlenecks. They interact with the AM-01 balanced P_y.
- **Termination** (row 26): defines `T_end`, the D24 censoring point and the cargo cutoff.
- **Discharge–load sequencing (D16)** is a frozen Step 1 rule, not a pending row. The **rollover wait
  (D17)** was approved on 2026-10-13, with sensitivity at 120 and 480 min.

Possible pre-registered sensitivity levels, where the protocol already names them: transport units
3/4/6 and speed 150/250/400 (protocol §11); D17 120/480 (AM-03); crane fleet 4/6 (AM-02). No other
ranges are proposed here, because choosing them now would be unprincipled.

## Owner approval request (one action, separately reviewed)

Please review the 28 rows and reply with one of:

1. **"Approve all 28 rows as synthetic v1 values"**: each record becomes FROZEN with an approval block
   dated on your approval day. Scope: synthetic, uncalibrated v1.
2. **"Approve rows … ; amend rows … to …"**: each amendment is recorded append-only before any
   validation data exist.
3. **"Hold"**: the lock stays BLOCKED.

Until one of these is recorded, `SCIENTIFIC_PROTOCOL_LOCK = BLOCKED` and validation is not authorized.
