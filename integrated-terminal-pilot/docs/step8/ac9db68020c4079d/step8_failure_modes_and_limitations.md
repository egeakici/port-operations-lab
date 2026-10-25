# Step8 failure modes and limitations

**PROVISIONAL — SYNTHETIC / UNCALIBRATED. Project I is NOT finally closed.**

Official full canonical return verification is VERIFIED_FULL_CANONICAL. Primary Holm interval construction and the required diagnostic campaign remain blocked. The numerical calculations below are conditional previews, not final public inferential claims.

Analysis `ac9db68020c4079d293a202eb52a0fb9f2d995e1de79d5eecc070ddfe7dbdedf`; code `406e7907d29720db08b9e1b56093dbc71e78c38230a051c05bf9b8beca75f8e3`. Step7 manifest `d180f1dec4fb212185b40658f7be47dc66d0bd08e66b6636f88cb45c42b8357d`; lock `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`. Frozen scientific revision `8cc697f26575ca18ed98a164390a5a40e137b343`; analysis HEAD `2a05112bd5576b31dc7db36618ea3dfc287f07bb`.

The synthetic v1 coefficients have no real-terminal calibration. Fifty test traffic scenarios per family are independent units; containers, decision epochs, vessels and training seeds are not extra traffic samples. Intervals are conditional on exactly three preselected PPO models. D24 includes every vessel and censors unfinished vessels at the common T_end; 1260 integrated episodes completed without deadlock/truncation, which does not imply every cargo obligation was loaded. U counts unique original obligations without LOAD_COMPLETED; TEU, moves and departure are separate facets.

B2-A2 changes the physical forecast and objective priority (coordination package). B2-T-A2 controls turnaround priority but still changes modelling assumptions. B2-B2-T is a matched objective ablation, although subsequent states diverge. None establishes universal global optimality or three-agent RL. No computational budget matching by wall time is claimed. Full cohort, legal candidates and WAIT remain uncapped; 2-second warnings are not timeouts.

B2 improves cargo against A2 in14/50 Medium and49/50 Heavy cases (all other cases tie), but Medium time worsens18/50 and Heavy6/50. Against FCFS, one Heavy case has worse B2 cargo. The mean can hide adverse tails; worst IDs and P95 paired deltas are retained in machine tables. Frozen PPO improves mean time against FCFS but increases cargo loss, especially Heavy; a failed NI result means NI NOT_DEMONSTRATED, not automatic statistical inferiority. Its mean of scenario P95 waiting increases against FCFS; selecting its best seed post-test is forbidden.

PPO remaining-occupancy features exceeded the training maximum in1772/3806 Heavy test decisions and1130/2417 Medium test decisions. This is distribution shift, not a causal diagnosis. B2 forecasts omit future landside gate-in/pickup under Q6-2, and remain UNCALIBRATED_SYNTHETIC_FORECAST. Selected forecasts belong to different visited states. Observed WAIT/cargo-pivotal coincidence does not identify counterfactual effects. Cargo primary causal tags are UNKNOWN_OR_MULTIPLE_CONSTRAINTS. Zero one-container pivots does not remove the design's permitted one-container priority.

Historical campaign stage durations sum28.50h, including profiling/reporting gates; outer episode wall sums20.09h. Sampled RSS maximum769.1MiB is not a continuous peak. B2 Heavy mean8.258s, P9526.136s, maximum69.540s per policy selection is a research cost, not a certified operational SLA. Simulation minutes are not CPU/wall seconds. CUDA was not used to accelerate the event simulator.

The official canonical return PASS is missing. The protocol specifies a Holm-adjusted confidence interval but no construction/inversion/order rule; the source and locked contract contain no implementation. Raw95% intervals are provided without substituting a Wilcoxon p-value or post-hoc Bonferroni rule. The required13M study also has genuine source-contract gaps. These block final closure, regardless of favorable estimates.

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

Archive diagnostics:27244 decisions,2044 WAIT;284 pivotal trajectory observations (B2=114,B2-T=170); zero one-container pivots;4139 compute warnings. These are repeated trajectory observations, not distinct traffic replications. Full selected-state arrays remain in original diagnostic archives.
