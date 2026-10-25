# Step8 statistical analysis protocol and results

**PROVISIONAL — SYNTHETIC / UNCALIBRATED. Project I is NOT finally closed.**

Official full canonical return verification is BYTES_METADATA_ONLY_PENDING. Primary Holm interval construction and the required diagnostic campaign remain blocked. The numerical calculations below are conditional previews, not final public inferential claims.

Analysis `364375d614664f77b7e36ae945e533df2380f42a97f0c6d49bf22ca66d9565e6`; code `adc41af1525ffe89aa2fb32e4dc8d9a3f46a57bd3b22366a6a358ea165031664`. Step7 manifest `d180f1dec4fb212185b40658f7be47dc66d0bd08e66b6636f88cb45c42b8357d`; lock `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`. Frozen scientific revision `8cc697f26575ca18ed98a164390a5a40e137b343`; analysis HEAD `901602e1df803ba7f9b5b3f56972c31d10176941`.

For every traffic scenario, Delta=policy minus comparator; negative time/cargo favors the policy. TA is D24 sum min(departure,Tend)-arrival over ALL vessels; Tend=last arrival+10080. Delta R is U(policy)/Nout - U(comparator)/Nout. Unique original container obligations—not TEU/moves—define Nout. Loaded-but-not-departed and D17 rollover are separately preserved. Nout=0 is NOT_APPLICABLE.

Time bootstrap:10000 paired scenario draws, PCG64 numpy.default_rng(120001), percentile2.5/97.5 using linear quantile. Cargo:10000 paired draws, seed20261013, one-sided percentile95 UPPER bound <=.01; zero-margin sensitivity separately. Sorted family/scenario order; reset RNG per estimand and per single-family result; overall draws families in sorted order and weights each.5. A3 models11/23/37 average within scenario before resampling; missing/blocked seed invalidates aggregate. No150-scenario fiction. DEADLOCK/TRUNCATED outcomes retain D24 censoring; FAILED only removes involved contrasts with IDs; exogenous drift quarantines whole scenario. The actual campaign has no such failures/exclusions. All50 test scenarios per family are retained.

Primary Holm family: B1-A1n and B2-A2. The frozen construction is unspecified: all primary CIs below are UNADJUSTED95% and primary verdicts BLOCKED. Wilcoxon Pratt two-sided normal-approximation p-values with continuity correction are supplementary robustness fields, not the decision rule or a substitute Holm implementation. Secondary lower time requires upper CI<0, higher time lower CI>0, otherwise no detectable difference. NI failure is NOT_DEMONSTRATED, not automatic inferiority. A combined claim requires the correct time criterion AND the registered NI comparison. B2-A1 and A3-A2 have no registered cargo NI pair; no new formal comparator is silently added.

| Family | Policy-comparator | n | Delta total TA [raw95%CI] vessel-min | Mean paired % [95%CI] | Delta R fraction | R upper95 fraction | NI(+.01) | Time verdict | Combined |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| itp_medium | B1-A1n | 50 | 305.228 [74.466, 542.615] | 1.845 [0.553, 3.192] | 0.000495 | NA | NOT_PREREGISTERED_FOR_PAIR | BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED | BLOCKED_PRIMARY_MULTIPLICITY |
| itp_medium | B2-A2 | 50 | -325.817 [-560.824, -99.323] | -1.377 [-2.610, -0.107] | -0.004434 | -0.002485 | PASSED | BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED | BLOCKED_PRIMARY_MULTIPLICITY |
| itp_medium | B1-A1 | 50 | -295.428 [-620.098, 15.247] | -1.149 [-2.791, 0.507] | 0.006870 | 0.009329 | PASSED | NO_DETECTABLE_DIFFERENCE | NO_ESTABLISHED_TIME_GAIN |
| itp_medium | A1n-A1 | 50 | -600.656 [-902.782, -312.571] | -2.891 [-4.291, -1.510] | 0.006375 | NA | NOT_PREREGISTERED_FOR_PAIR | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_PREREGISTERED_FOR_THIS_PAIR |
| itp_medium | A2-A1 | 50 | -921.348 [-1267.070, -587.295] | -4.555 [-6.194, -2.913] | 0.003430 | 0.005226 | PASSED | LOWER_TIME | TIME_GAIN_CARGO_NON_INFERIOR |
| itp_medium | A3-A1 | 50 | -605.331 [-859.262, -369.921] | -2.900 [-4.094, -1.762] | 0.003712 | 0.005663 | PASSED | LOWER_TIME | TIME_GAIN_CARGO_NON_INFERIOR |
| itp_medium | A3-A2 | 50 | 316.017 [57.438, 584.582] | 1.968 [0.463, 3.531] | 0.000282 | NA | NOT_PREREGISTERED_FOR_PAIR | HIGHER_TIME | NO_ESTABLISHED_TIME_GAIN |
| itp_medium | B2-A1 | 50 | -1247.165 [-1635.746, -878.867] | -5.927 [-7.693, -4.182] | -0.001004 | NA | NOT_PREREGISTERED_FOR_PAIR | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_PREREGISTERED_FOR_THIS_PAIR |
| itp_medium | B2-T-A2 | 50 | -323.349 [-556.848, -98.739] | -1.364 [-2.585, -0.109] | -0.004130 | -0.002222 | PASSED | LOWER_TIME | TIME_GAIN_CARGO_NON_INFERIOR |
| itp_medium | B2-B2-T | 50 | -2.467 [-12.639, 5.236] | -0.014 [-0.068, 0.024] | -0.000304 | 0.000000 | PASSED | NO_DETECTABLE_DIFFERENCE | NO_ESTABLISHED_TIME_GAIN |
| itp_heavy | B1-A1n | 50 | 540.421 [-150.039, 1250.406] | 1.207 [-0.378, 2.824] | 0.003870 | NA | NOT_PREREGISTERED_FOR_PAIR | BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED | BLOCKED_PRIMARY_MULTIPLICITY |
| itp_heavy | B2-A2 | 50 | -2447.283 [-3105.022, -1812.363] | -5.610 [-7.037, -4.240] | -0.028031 | -0.024467 | PASSED | BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED | BLOCKED_PRIMARY_MULTIPLICITY |
| itp_heavy | B1-A1 | 50 | 232.288 [-565.074, 1053.468] | 0.727 [-1.115, 2.621] | 0.038682 | 0.043044 | NOT_DEMONSTRATED | NO_DETECTABLE_DIFFERENCE | NO_ESTABLISHED_TIME_GAIN |
| itp_heavy | A1n-A1 | 50 | -308.133 [-964.573, 369.639] | -0.358 [-1.861, 1.239] | 0.034812 | NA | NOT_PREREGISTERED_FOR_PAIR | NO_DETECTABLE_DIFFERENCE | NO_ESTABLISHED_TIME_GAIN |
| itp_heavy | A2-A1 | 50 | -1807.945 [-2457.699, -1161.275] | -3.976 [-5.420, -2.504] | 0.026280 | 0.029667 | NOT_DEMONSTRATED | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_DEMONSTRATED |
| itp_heavy | A3-A1 | 50 | -1022.983 [-1580.416, -464.288] | -2.256 [-3.539, -0.941] | 0.026055 | 0.028792 | NOT_DEMONSTRATED | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_DEMONSTRATED |
| itp_heavy | A3-A2 | 50 | 784.962 [286.467, 1307.072] | 1.912 [0.743, 3.142] | -0.000224 | NA | NOT_PREREGISTERED_FOR_PAIR | HIGHER_TIME | NO_ESTABLISHED_TIME_GAIN |
| itp_heavy | B2-A1 | 50 | -4255.228 [-4860.929, -3671.404] | -9.515 [-10.786, -8.286] | -0.001751 | NA | NOT_PREREGISTERED_FOR_PAIR | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_PREREGISTERED_FOR_THIS_PAIR |
| itp_heavy | B2-T-A2 | 50 | -2627.009 [-3181.929, -2088.194] | -6.066 [-7.307, -4.855] | -0.021702 | -0.018093 | PASSED | LOWER_TIME | TIME_GAIN_CARGO_NON_INFERIOR |
| itp_heavy | B2-B2-T | 50 | 179.726 [-18.284, 376.033] | 0.467 [-0.004, 0.933] | -0.006329 | -0.004032 | PASSED | NO_DETECTABLE_DIFFERENCE | NO_ESTABLISHED_TIME_GAIN |
| equal_family_overall | B1-A1n | 100 | 422.825 [58.427, 794.716] | 1.526 [0.506, 2.558] | 0.002183 | NA | NOT_PREREGISTERED_FOR_PAIR | BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED | BLOCKED_PRIMARY_MULTIPLICITY |
| equal_family_overall | B2-A2 | 100 | -1386.550 [-1735.049, -1050.787] | -3.493 [-4.433, -2.567] | -0.016232 | -0.014150 | PASSED | BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED | BLOCKED_PRIMARY_MULTIPLICITY |
| equal_family_overall | B1-A1 | 100 | -31.570 [-464.779, 407.485] | -0.211 [-1.473, 1.040] | 0.022776 | 0.025275 | NOT_DEMONSTRATED | NO_DETECTABLE_DIFFERENCE | NO_ESTABLISHED_TIME_GAIN |
| equal_family_overall | A1n-A1 | 100 | -454.395 [-818.309, -80.135] | -1.624 [-2.666, -0.577] | 0.020593 | NA | NOT_PREREGISTERED_FOR_PAIR | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_PREREGISTERED_FOR_THIS_PAIR |
| equal_family_overall | A2-A1 | 100 | -1364.646 [-1737.222, -1002.858] | -4.265 [-5.376, -3.184] | 0.014855 | 0.016772 | NOT_DEMONSTRATED | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_DEMONSTRATED |
| equal_family_overall | A3-A1 | 100 | -814.157 [-1123.361, -504.392] | -2.578 [-3.456, -1.686] | 0.014884 | 0.016578 | NOT_DEMONSTRATED | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_DEMONSTRATED |
| equal_family_overall | A3-A2 | 100 | 550.490 [272.132, 845.303] | 1.940 [1.006, 2.945] | 0.000029 | NA | NOT_PREREGISTERED_FOR_PAIR | HIGHER_TIME | NO_ESTABLISHED_TIME_GAIN |
| equal_family_overall | B2-A1 | 100 | -2751.196 [-3114.205, -2411.329] | -7.721 [-8.796, -6.651] | -0.001378 | NA | NOT_PREREGISTERED_FOR_PAIR | LOWER_TIME | TIME_GAIN_CARGO_NI_NOT_PREREGISTERED_FOR_THIS_PAIR |
| equal_family_overall | B2-T-A2 | 100 | -1475.179 [-1772.164, -1185.522] | -3.715 [-4.573, -2.861] | -0.012916 | -0.010852 | PASSED | LOWER_TIME | TIME_GAIN_CARGO_NON_INFERIOR |
| equal_family_overall | B2-B2-T | 100 | 88.629 [-10.315, 187.128] | 0.226 [-0.012, 0.460] | -0.003316 | -0.002166 | PASSED | NO_DETECTABLE_DIFFERENCE | NO_ESTABLISHED_TIME_GAIN |

## Cargo NI (+1pp and 0pp)

| Family | Comparison | n | Mean delta R (pp) | Upper95 (pp) | +1pp NI | 0pp sensitivity |
| --- | --- | --- | --- | --- | --- | --- |
| itp_heavy | B2-A2 | 50 | -2.803 | -2.447 | PASSED | PASSED |
| itp_medium | B2-A2 | 50 | -0.443 | -0.248 | PASSED | PASSED |
| equal_family_overall | B2-A2 | 100 | -1.623 | -1.415 | PASSED | PASSED |
| itp_heavy | B1-A1 | 50 | 3.868 | 4.304 | NOT_DEMONSTRATED | NOT_DEMONSTRATED |
| itp_medium | B1-A1 | 50 | 0.687 | 0.933 | PASSED | NOT_DEMONSTRATED |
| equal_family_overall | B1-A1 | 100 | 2.278 | 2.527 | NOT_DEMONSTRATED | NOT_DEMONSTRATED |
| itp_heavy | A2-A1 | 50 | 2.628 | 2.967 | NOT_DEMONSTRATED | NOT_DEMONSTRATED |
| itp_medium | A2-A1 | 50 | 0.343 | 0.523 | PASSED | NOT_DEMONSTRATED |
| equal_family_overall | A2-A1 | 100 | 1.485 | 1.677 | NOT_DEMONSTRATED | NOT_DEMONSTRATED |
| itp_heavy | A3-A1 | 50 | 2.606 | 2.879 | NOT_DEMONSTRATED | NOT_DEMONSTRATED |
| itp_medium | A3-A1 | 50 | 0.371 | 0.566 | PASSED | NOT_DEMONSTRATED |
| equal_family_overall | A3-A1 | 100 | 1.488 | 1.658 | NOT_DEMONSTRATED | NOT_DEMONSTRATED |
| itp_heavy | B2-T-A2 | 50 | -2.170 | -1.809 | PASSED | PASSED |
| itp_medium | B2-T-A2 | 50 | -0.413 | -0.222 | PASSED | PASSED |
| equal_family_overall | B2-T-A2 | 100 | -1.292 | -1.085 | PASSED | PASSED |
| itp_heavy | B2-B2-T | 50 | -0.633 | -0.403 | PASSED | PASSED |
| itp_medium | B2-B2-T | 50 | -0.030 | 0.000 | PASSED | PASSED |
| equal_family_overall | B2-B2-T | 100 | -0.332 | -0.217 | PASSED | PASSED |

## S1 reference transfer

| Family | S1 source-defined DID | n | Delta total TA [95%CI] vessel-min |
| --- | --- | --- | --- |
| itp_heavy | (A2-A1)_integrated-(A2-A1)_reference | 50 | -938.054 [-1592.963, -275.927] |
| itp_medium | (A2-A1)_integrated-(A2-A1)_reference | 50 | -767.127 [-1102.254, -448.372] |
| equal_family_overall | (A2-A1)_integrated-(A2-A1)_reference | 100 | -852.591 [-1219.218, -487.801] |
| itp_heavy | (A3-A1)_integrated-(A3-A1)_reference | 50 | -696.652 [-1275.721, -121.213] |
| itp_medium | (A3-A1)_integrated-(A3-A1)_reference | 50 | -547.310 [-784.272, -326.443] |
| equal_family_overall | (A3-A1)_integrated-(A3-A1)_reference | 100 | -621.981 [-930.772, -305.835] |

| Family | Contrast | Sign agreement | Reference delta [95%CI] vessel-min |
| --- | --- | --- | --- |
| itp_heavy | A2-A1 | 0.760 | -869.891 [-1091.715, -653.134] |
| itp_medium | A2-A1 | 0.540 | -154.221 [-223.096, -90.902] |
| itp_heavy | A3-A1 | 0.500 | -326.330 [-485.025, -172.373] |
| itp_medium | A3-A1 | 0.360 | -58.021 [-103.500, -22.168] |

The registered +1pp NI rule allows some cargo deterioration: A3 versus A1 PASSES in Medium (mean +0.371pp, upper +0.566pp) while its time95%CI is below zero. Thus the provisional registered combined criterion is met in Medium. It is NOT met in Heavy (mean +2.606pp, upper +2.879pp), nor in the equal-family summary (upper +1.658pp). Zero-margin sensitivity fails in both families. Do not replace the approved1pp margin with zero to make Medium fail, and do not call a1pp pass proof of zero cargo harm. This is a formal-method qualification of the earlier descriptive review, not a numeric discrepancy or redefinition.

The DID is the original protocol estimand of policy-relative effects under different physical models, not raw environment totals or a causal intervention estimate. Mean ranking and per-scenario Kendall tau-b are in `primary_s1_s2_results.json`; no Project03 held-out archive was opened.

| Family | Seed comparison (descriptive) | TA delta [95%CI] vessel-min | Cargo upper95 (pp) | NI |
| --- | --- | --- | --- | --- |
| itp_heavy | A3-train11-A1 | -842.366 [-1489.316, -160.188] | 3.268 | NOT_DEMONSTRATED |
| itp_medium | A3-train11-A1 | -734.511 [-987.422, -489.393] | 0.604 | PASSED |
| itp_heavy | A3-train23-A1 | -1583.788 [-2177.736, -985.506] | 1.299 | NOT_DEMONSTRATED |
| itp_medium | A3-train23-A1 | -640.370 [-928.990, -369.988] | 0.300 | PASSED |
| itp_heavy | A3-train37-A1 | -642.794 [-1469.979, 191.780] | 4.264 | NOT_DEMONSTRATED |
| itp_medium | A3-train37-A1 | -441.111 [-750.181, -139.479] | 0.853 | PASSED |

Conditional on the three models, no training-seed uncertainty or best-seed selection. Mean paired percentage is computed per scenario before averaging, distinct from percentage change of group means; both fields are retained. Tail counts, P95 deltas and worst scenario IDs accompany every comparison. All counts/estimates trace to scenario_paired_deltas.csv and hashed cache.
