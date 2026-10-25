# Project I final scientific report — provisional research manuscript

**PROVISIONAL — SYNTHETIC / UNCALIBRATED. Project I is NOT finally closed.**

Official full canonical return verification is BYTES_METADATA_ONLY_PENDING. Primary Holm interval construction and the required diagnostic campaign remain blocked. The numerical calculations below are conditional previews, not final public inferential claims.

Analysis `af6b483cfaee4774333bede116667bd22a25d418b4a6bf76e933fe53260ce38e`; code `406e7907d29720db08b9e1b56093dbc71e78c38230a051c05bf9b8beca75f8e3`. Step7 manifest `d180f1dec4fb212185b40658f7be47dc66d0bd08e66b6636f88cb45c42b8357d`; lock `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`. Frozen scientific revision `8cc697f26575ca18ed98a164390a5a40e137b343`; analysis HEAD `901602e1df803ba7f9b5b3f56972c31d10176941`.

## Abstract

We evaluated berth-only FCFS, authentic online Rollout and three frozen PPO checkpoints alongside nominal/integrated greedy rules and model-based integrated rollout in an uncalibrated synthetic terminal. Step7 contains1960 completed episodes over140 traffic scenarios. Primary test inference uses50 independent scenarios in each Medium/Heavy family; validation remains separate. Cargo-first B2 reduces mean turnaround and unloaded obligations versus nominal A2, with stronger Heavy effects. Frozen PPO improves mean time versus FCFS but exhibits cargo deterioration, especially Heavy, and remains slower than A2. Formal primary confirmation and project closure remain blocked by canonical return verification, unspecified primary Holm construction and missing source-consistent13M diagnostics.

## Problem, architecture and frozen design

S1 measures transfer of policy-relative performance from authentic P03 nominal BAP projections into the integrated terminal. S2 asks whether coordinated berth decisions improve outcomes in identical terminal physics. The event-driven kernel shares quay cranes, transport capacity and a block-level yard. All primary arms use eight cranes, greedy crane allocation, common occupancy-balancing yard placement, assigned multi-crane efficiency, D15 batch10, D17 wait240 and R5 FIFO release. A2 uses unchanged P03 visible-cohort lookahead; A3 is unchanged deterministic CPU MaskablePPO with H240 and PASS-FORECAST occupancy substitution. B1 uses accepted integrated release estimates; B2/B2-T share an integrated forward evaluator. B2 ranks cargo first then time; B2-T ranks time only. All legal candidates plus WAIT are retained, no timeout or policy fallback. AM01–10 and actual owner28-value approval precede test generation.

## Scenarios and inference

20validation and50test scenarios per family;9 integrated arm/checkpoint identities and5 reference identities per scenario. Physics and exogenous fingerprints, Nout and Tend are paired across arms. Three training seeds are nested, not independent traffic units. D24 and outbound LOAD_COMPLETED metrics prevent departure/completion from substituting for cargo success. Methods and all confidence/NI results are in the accompanying statistical report; primary Holm ambiguity is disclosed, not repaired after seeing outcomes.

## Test outcomes

| Family | Arm | Mean TA/vessel | Median vessel TA | P95 vessel TA | Mean wait/vessel | Mean of scenario P95 wait | Mean U containers | Mean R (%) | complete; fail/deadlock/trunc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| itp_medium | A1 | 1162.37 | 1056.35 | 2278.71 | 398.31 | 1107.94 | 4.80 | 0.1004 | 50/50; 0/0/0 |
| itp_medium | A1n | 1124.83 | 946.51 | 2627.91 | 354.53 | 1263.46 | 35.12 | 0.7379 | 50/50; 0/0/0 |
| itp_medium | B1 | 1143.90 | 964.70 | 2643.76 | 379.67 | 1296.57 | 37.42 | 0.7875 | 50/50; 0/0/0 |
| itp_medium | A2 | 1104.78 | 953.72 | 2483.49 | 332.07 | 1128.68 | 20.70 | 0.4434 | 50/50; 0/0/0 |
| itp_medium | A3-train11 | 1116.46 | 946.87 | 2593.16 | 350.53 | 1177.57 | 22.32 | 0.4805 | 50/50; 0/0/0 |
| itp_medium | A3-train23 | 1122.35 | 969.02 | 2488.35 | 358.94 | 1110.18 | 11.78 | 0.2476 | 50/50; 0/0/0 |
| itp_medium | A3-train37 | 1134.80 | 951.69 | 2785.64 | 363.92 | 1286.68 | 32.60 | 0.6868 | 50/50; 0/0/0 |
| itp_medium | A3 | 1124.54 | 963.14 | 2555.33 | 357.80 | 1191.48 | 22.23 | 0.4716 | 50/50; 0/0/0 |
| itp_medium | B2-T | 1084.58 | 954.32 | 2283.15 | 328.71 | 1043.97 | 1.36 | 0.0304 | 50/50; 0/0/0 |
| itp_medium | B2 | 1084.42 | 954.32 | 2305.73 | 328.76 | 1039.29 | 0.00 | 0.0000 | 50/50; 0/0/0 |
| itp_heavy | A1 | 1864.81 | 1747.59 | 3500.05 | 1092.66 | 2437.15 | 12.50 | 0.1827 | 50/50; 0/0/0 |
| itp_heavy | A1n | 1851.97 | 1236.25 | 4736.90 | 1032.85 | 3373.54 | 251.98 | 3.6638 | 50/50; 0/0/0 |
| itp_heavy | B1 | 1874.49 | 1222.99 | 4803.88 | 1058.77 | 3488.84 | 278.10 | 4.0508 | 50/50; 0/0/0 |
| itp_heavy | A2 | 1789.48 | 1298.26 | 4377.99 | 969.33 | 3120.35 | 193.16 | 2.8106 | 50/50; 0/0/0 |
| itp_heavy | A3-train11 | 1829.71 | 1240.23 | 4414.55 | 1018.80 | 3156.90 | 210.14 | 3.0732 | 50/50; 0/0/0 |
| itp_heavy | A3-train23 | 1798.82 | 1430.73 | 3892.50 | 1012.52 | 2595.72 | 83.10 | 1.2195 | 50/50; 0/0/0 |
| itp_heavy | A3-train37 | 1838.03 | 1207.74 | 4736.88 | 1014.78 | 3424.50 | 279.94 | 4.0719 | 50/50; 0/0/0 |
| itp_heavy | A3 | 1822.19 | 1407.87 | 4173.18 | 1015.37 | 3059.04 | 191.06 | 2.7882 | 50/50; 0/0/0 |
| itp_heavy | B2-T | 1680.02 | 1400.09 | 3514.92 | 909.82 | 2374.48 | 45.12 | 0.6404 | 50/50; 0/0/0 |
| itp_heavy | B2 | 1687.51 | 1466.90 | 3469.69 | 923.50 | 2283.65 | 0.48 | 0.0076 | 50/50; 0/0/0 |

TA columns are simulated minutes. Pooled vessel median/P95 are descriptive; for A3 each vessel's outcomes are averaged across the three models first. Mean of scenario P95 waiting is explicitly distinct from pooled-vessel P95; both appear in CSV. No vessel is treated as an independent bootstrap scenario.

## S1 and S2 findings

itp_medium: B2-A2, delta TA/vessel -20.364 [-35.051, -6.208] min; mean paired percentage -1.377 [-2.610, -0.107]%; mean U delta -20.70. Cargo upper95=-0.248 pp; +1pp NI PASSED, zero-margin PASSED. Time classification: BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED (unadjusted: LOWER_TIME).

itp_heavy: B2-A2, delta TA/vessel -101.970 [-129.376, -75.515] min; mean paired percentage -5.610 [-7.037, -4.240]%; mean U delta -192.68. Cargo upper95=-2.447 pp; +1pp NI PASSED, zero-margin PASSED. Time classification: BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED (unadjusted: LOWER_TIME).

itp_medium: B2-T-A2, delta TA/vessel -20.209 [-34.803, -6.171] min; mean paired percentage -1.364 [-2.585, -0.109]%; mean U delta -19.34. Cargo upper95=-0.222 pp; +1pp NI PASSED, zero-margin PASSED. Time classification: LOWER_TIME (unadjusted: LOWER_TIME).

itp_heavy: B2-T-A2, delta TA/vessel -109.459 [-132.580, -87.008] min; mean paired percentage -6.066 [-7.307, -4.855]%; mean U delta -148.04. Cargo upper95=-1.809 pp; +1pp NI PASSED, zero-margin PASSED. Time classification: LOWER_TIME (unadjusted: LOWER_TIME).

itp_medium: B2-B2-T, delta TA/vessel -0.154 [-0.790, 0.327] min; mean paired percentage -0.014 [-0.068, 0.024]%; mean U delta -1.36. Cargo upper95=0.000 pp; +1pp NI PASSED, zero-margin PASSED. Time classification: NO_DETECTABLE_DIFFERENCE (unadjusted: NO_DETECTABLE_DIFFERENCE).

itp_heavy: B2-B2-T, delta TA/vessel 7.489 [-0.762, 15.668] min; mean paired percentage 0.467 [-0.004, 0.933]%; mean U delta -44.64. Cargo upper95=-0.403 pp; +1pp NI PASSED, zero-margin PASSED. Time classification: NO_DETECTABLE_DIFFERENCE (unadjusted: NO_DETECTABLE_DIFFERENCE).

itp_medium: A3-A1, delta TA/vessel -37.833 [-53.704, -23.120] min; mean paired percentage -2.900 [-4.094, -1.762]%; mean U delta 17.43. Cargo upper95=0.566 pp; +1pp NI PASSED, zero-margin NOT_DEMONSTRATED. Time classification: LOWER_TIME (unadjusted: LOWER_TIME).

itp_heavy: A3-A1, delta TA/vessel -42.624 [-65.851, -19.345] min; mean paired percentage -2.256 [-3.539, -0.941]%; mean U delta 178.56. Cargo upper95=2.879 pp; +1pp NI NOT_DEMONSTRATED, zero-margin NOT_DEMONSTRATED. Time classification: LOWER_TIME (unadjusted: LOWER_TIME).

itp_medium: A3-A2, delta TA/vessel 19.751 [3.590, 36.536] min; mean paired percentage 1.968 [0.463, 3.531]%; mean U delta 1.53. Cargo NI is not a registered comparison for this pair. Time classification: HIGHER_TIME (unadjusted: HIGHER_TIME).

itp_heavy: A3-A2, delta TA/vessel 32.707 [11.936, 54.461] min; mean paired percentage 1.912 [0.743, 3.142]%; mean U delta -2.10. Cargo NI is not a registered comparison for this pair. Time classification: HIGHER_TIME (unadjusted: HIGHER_TIME).

itp_medium: B1-A1n, delta TA/vessel 19.077 [4.654, 33.913] min; mean paired percentage 1.845 [0.553, 3.192]%; mean U delta 2.30. Cargo NI is not a registered comparison for this pair. Time classification: BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED (unadjusted: HIGHER_TIME).

itp_heavy: B1-A1n, delta TA/vessel 22.518 [-6.252, 52.100] min; mean paired percentage 1.207 [-0.378, 2.824]%; mean U delta 26.12. Cargo NI is not a registered comparison for this pair. Time classification: BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED (unadjusted: NO_DETECTABLE_DIFFERENCE).

itp_medium: B1-A1, delta TA/vessel -18.464 [-38.756, 0.953] min; mean paired percentage -1.149 [-2.791, 0.507]%; mean U delta 32.62. Cargo upper95=0.933 pp; +1pp NI PASSED, zero-margin NOT_DEMONSTRATED. Time classification: NO_DETECTABLE_DIFFERENCE (unadjusted: NO_DETECTABLE_DIFFERENCE).

itp_heavy: B1-A1, delta TA/vessel 9.679 [-23.545, 43.895] min; mean paired percentage 0.727 [-1.115, 2.621]%; mean U delta 265.60. Cargo upper95=4.304 pp; +1pp NI NOT_DEMONSTRATED, zero-margin NOT_DEMONSTRATED. Time classification: NO_DETECTABLE_DIFFERENCE (unadjusted: NO_DETECTABLE_DIFFERENCE).

The registered +1pp NI rule allows some cargo deterioration: A3 versus A1 PASSES in Medium (mean +0.371pp, upper +0.566pp) while its time95%CI is below zero. Thus the provisional registered combined criterion is met in Medium. It is NOT met in Heavy (mean +2.606pp, upper +2.879pp), nor in the equal-family summary (upper +1.658pp). Zero-margin sensitivity fails in both families. Do not replace the approved1pp margin with zero to make Medium fail, and do not call a1pp pass proof of zero cargo harm. This is a formal-method qualification of the earlier descriptive review, not a numeric discrepancy or redefinition.

| Family | S1 source-defined DID | n | Delta total TA [95%CI] vessel-min |
| --- | --- | --- | --- |
| itp_heavy | (A2-A1)_integrated-(A2-A1)_reference | 50 | -938.054 [-1592.963, -275.927] |
| itp_medium | (A2-A1)_integrated-(A2-A1)_reference | 50 | -767.127 [-1102.254, -448.372] |
| equal_family_overall | (A2-A1)_integrated-(A2-A1)_reference | 100 | -852.591 [-1219.218, -487.801] |
| itp_heavy | (A3-A1)_integrated-(A3-A1)_reference | 50 | -696.652 [-1275.721, -121.213] |
| itp_medium | (A3-A1)_integrated-(A3-A1)_reference | 50 | -547.310 [-784.272, -326.443] |
| equal_family_overall | (A3-A1)_integrated-(A3-A1)_reference | 100 | -621.981 [-930.772, -305.835] |

## Objective ablation and operational diagnostics

B2 versus B2-T isolates cargo priority within the matched evaluator. Medium has48/50 time ties; Heavy has a time/cargo tradeoff. This does not make the cargo-first rule universally superior. The different-method trajectories are not matched states after divergence.

| Family | Arm | Decisions | WAIT | Mean selection s | P95 selection s | Max selection s | Mean outer wall s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| itp_medium | A2 | 859 | 59 | 0.077234 | 0.328088 | 1.669485 | 19.68 |
| itp_medium | A3 | 2417 | 17 | 0.003714 | 0.004161 | 0.007815 | 18.39 |
| itp_medium | B2-T | 954 | 154 | 2.150131 | 7.472148 | 20.512786 | 68.11 |
| itp_medium | B2 | 953 | 153 | 2.153888 | 7.437174 | 20.559493 | 68.14 |
| itp_heavy | A2 | 1375 | 175 | 0.620536 | 2.465382 | 8.315885 | 41.23 |
| itp_heavy | A3 | 3806 | 206 | 0.003715 | 0.004149 | 0.011599 | 24.22 |
| itp_heavy | B2-T | 1534 | 334 | 8.041617 | 25.108976 | 66.237669 | 287.83 |
| itp_heavy | B2 | 1541 | 341 | 8.257999 | 26.135556 | 69.540056 | 295.61 |

| Family | Arm | Cargo pivotal observations | 1-container pivots | Mean U forecast error | U MAE | Cohort TA signed error min | B1 release MAE min |
| --- | --- | --- | --- | --- | --- | --- | --- |
| itp_medium | B1 | 0 | 0 | NA | NA | NA | 207.999 |
| itp_medium | B2-T | 2 | 0 | -0.134 | 0.134 | -346.099 | NA |
| itp_medium | B2 | 4 | 0 | 0.000 | 0.000 | -340.372 | NA |
| itp_heavy | B1 | 0 | 0 | NA | NA | NA | 222.491 |
| itp_heavy | B2-T | 134 | 0 | -5.527 | 7.956 | -970.023 | NA |
| itp_heavy | B2 | 86 | 0 | 0.351 | 0.398 | -772.082 | NA |

## Required sensitivity coverage

| Requirement | Authority | Planned scope | Actual coverage | Gate |
| --- | --- | --- | --- | --- |
| Matched cargo-first objective | AM07/08 | B2 vs B2-T same140 traffic cases | 100 test +40 validation paired | COMPUTED, provisional return |
| Model-only coupling ablations | protocol11 + approved scoped equality | none/crane-aware/yard-aware/both; outer physics full | 0 new13M; exact coupling episode matrix unspecified | BLOCKED API + scope contract |
| OFAT sensitivity | protocol11 / locked ranges | 20 diagnostic cases/family/condition, A1/A2/B2/A3x3 | 0/4320 listed cells; 120 explicitly unsupported | PENDING MANUAL; implementation blocked |
| D17 120/480 | AM03 / locked ranges | included as OFAT conditions | 0 new13M | PENDING MANUAL |
| Low/Bottleneck | approved family roles | diagnostic only; not specified as extra primary/condition families | historical development retained | not promoted; no invented new family campaign |

## Limitations and failure modes

The synthetic v1 coefficients have no real-terminal calibration. Fifty test traffic scenarios per family are independent units; containers, decision epochs, vessels and training seeds are not extra traffic samples. Intervals are conditional on exactly three preselected PPO models. D24 includes every vessel and censors unfinished vessels at the common T_end; 1260 integrated episodes completed without deadlock/truncation, which does not imply every cargo obligation was loaded. U counts unique original obligations without LOAD_COMPLETED; TEU, moves and departure are separate facets.

B2-A2 changes the physical forecast and objective priority (coordination package). B2-T-A2 controls turnaround priority but still changes modelling assumptions. B2-B2-T is a matched objective ablation, although subsequent states diverge. None establishes universal global optimality or three-agent RL. No computational budget matching by wall time is claimed. Full cohort, legal candidates and WAIT remain uncapped; 2-second warnings are not timeouts.

B2 improves cargo against A2 in14/50 Medium and49/50 Heavy cases (all other cases tie), but Medium time worsens18/50 and Heavy6/50. Against FCFS, one Heavy case has worse B2 cargo. The mean can hide adverse tails; worst IDs and P95 paired deltas are retained in machine tables. Frozen PPO improves mean time against FCFS but increases cargo loss, especially Heavy; a failed NI result means NI NOT_DEMONSTRATED, not automatic statistical inferiority. Its mean of scenario P95 waiting increases against FCFS; selecting its best seed post-test is forbidden.

PPO remaining-occupancy features exceeded the training maximum in1772/3806 Heavy test decisions and1130/2417 Medium test decisions. This is distribution shift, not a causal diagnosis. B2 forecasts omit future landside gate-in/pickup under Q6-2, and remain UNCALIBRATED_SYNTHETIC_FORECAST. Selected forecasts belong to different visited states. Observed WAIT/cargo-pivotal coincidence does not identify counterfactual effects. Cargo primary causal tags are UNKNOWN_OR_MULTIPLE_CONSTRAINTS. Zero one-container pivots does not remove the design's permitted one-container priority.

Historical campaign stage durations sum28.50h, including profiling/reporting gates; outer episode wall sums20.09h. Sampled RSS maximum769.1MiB is not a continuous peak. B2 Heavy mean8.258s, P9526.136s, maximum69.540s per policy selection is a research cost, not a certified operational SLA. Simulation minutes are not CPU/wall seconds. CUDA was not used to accelerate the event simulator.

The official canonical return PASS is missing. The protocol specifies a Holm-adjusted confidence interval but no construction/inversion/order rule; the source and locked contract contain no implementation. Raw95% intervals are provided without substituting a Wilcoxon p-value or post-hoc Bonferroni rule. The required13M study also has genuine source-contract gaps. These block final closure, regardless of favorable estimates.

## Interpretation and future research

The narrower supported pattern is that terminal-aware, cargo-first berth coordination can improve synthetic outcomes; the existing frozen berth PPO does not establish cargo-preserving terminal-wide optimization. There are no three RL agents: crane and yard policies are fixed rules, and B2 is not RL. No real-terminal savings, universal optimality or field validity follows.

Future studies should separately examine (1) integrated-physics retraining with berth-only information as a control, (2) integrated-aware PPO with crane/yard/cargo observations under matched training/objectives, (3) new crane/yard decision control as a distinct extension, and (4) empirical calibration and prospective port trials. None was run or authorized as a hidden Step8 rescue. Yard RL performance cannot be inferred from this berth PPO experiment.

## Reproducibility and closure

All arrays/tables/figures bind to original manifest, source, lock and analysis hashes. No original episode was repeated, no model/physics/policy changed, and no automatic commit occurred. The release manifest binds this manuscript and figures. See the closure note for exact remaining gates.

## Supporting figures

![01 primary outcome table](../../../experiments/step8_analysis/af6b483cfaee4774/figures/01_primary_outcome_table.png)

![02 paired time effects](../../../experiments/step8_analysis/af6b483cfaee4774/figures/02_paired_time_effects.png)

![03 cargo noninferiority](../../../experiments/step8_analysis/af6b483cfaee4774/figures/03_cargo_noninferiority.png)

![04 time cargo tradeoff](../../../experiments/step8_analysis/af6b483cfaee4774/figures/04_time_cargo_tradeoff.png)

![05 ppo all seeds](../../../experiments/step8_analysis/af6b483cfaee4774/figures/05_ppo_all_seeds.png)

![06 wait and forecast](../../../experiments/step8_analysis/af6b483cfaee4774/figures/06_wait_and_forecast.png)

![07 compute cost](../../../experiments/step8_analysis/af6b483cfaee4774/figures/07_compute_cost.png)

![08 cargo first objective ablation](../../../experiments/step8_analysis/af6b483cfaee4774/figures/08_cargo_first_objective_ablation.png)
