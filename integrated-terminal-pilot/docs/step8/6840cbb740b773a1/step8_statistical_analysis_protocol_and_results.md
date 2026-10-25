# step8 statistical analysis protocol and results

**SYNTHETIC / UNCALIBRATED. PROJECT_I_FINAL_CLOSED=NO. Primary adjusted inference is POST_HOC_MULTIPLICITY_COMPLETION.**

Step7 source `8cc697f26575ca18ed98a164390a5a40e137b343`; lock `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`; return VERIFIED_FULL_CANONICAL reused. Current analysis HEAD `2a05112bd5576b31dc7db36618ea3dfc287f07bb`.

Bundle `integrated-terminal-pilot/experiments/step8_final_closure/9a2aa1617a43bbbf/releases/6840cbb740b773a1`. Primary method `cf94c23a9ad77e4db55438e72f45ae72e3869d58c93a52a806b842dc1b3da966`. Packet `033723f5f37effb80f40ae25138b0428e95f5246124372bbaf0e2a960c993b3f`; approval AWAITING_EXPLICIT_OWNER.

{
  "id": "POST_HOC_METHOD_SPECIFICATION_20261025_V1",
  "date": "2026-10-25",
  "classification": "POST_HOC_MULTIPLICITY_COMPLETION",
  "approval": "PENDING_EXPLICIT_OWNER_ACCEPTANCE",
  "fixed_before_new_adjusted_computation": true,
  "previously_seen": "Step7 outcomes and Step8 unadjusted intervals were available; no adjusted alternatives were compared.",
  "hypotheses": [
    "B1-A1n",
    "B2-A2"
  ],
  "m": 2,
  "populations": [
    "itp_heavy",
    "itp_medium",
    "equal_family_overall"
  ],
  "population_scope": "Separate m=2 family in each population; no simultaneous coverage across populations, metrics or secondary contrasts claimed.",
  "alpha": 0.05,
  "intervals": "Conservative Bonferroni simultaneous percentile intervals: marginal confidence 1-alpha/m=0.975; linear quantiles [alpha/(2m),1-alpha/(2m)]. These are NOT described as exact Holm-inverted intervals. Union bound gives familywise coverage to the extent that marginal nonparametric bootstrap intervals have nominal coverage. This is an approximate bootstrap procedure, not finite-sample exact coverage.",
  "holm_tests": "Two-sided centered paired bootstrap p=(1+count(abs(draw-estimate)>=abs(estimate)))/(B+1). Stable ascending p then hypothesis ID. Holm adjusted p at rank i is min(1,max over ranks j<=i of (m-j+1)*p[j]). Supporting tests, not substitutes for interval decisions.",
  "decision": "Time direction follows the simultaneous interval. If a Holm test disagrees, report the disagreement, do not switch methods. Qualified exploratory primary conclusion only.",
  "bootstrap": {
    "resamples": 10000,
    "seed": 120001,
    "rng": "numpy.default_rng PCG64",
    "unit": "paired traffic scenario",
    "strata": "family",
    "overall_weights": [
      0.5,
      0.5
    ],
    "quantile": "linear"
  },
  "metrics": [
    "difference",
    "difference_per_vessel",
    "percent"
  ],
  "cargo": "UNCHANGED AM06: 10000 draws, seed20261013, one-sided upper95, +0.01 margin and separate zero-margin sensitivity. No multiplicity-adjusted cargo claim.",
  "PPO": "All11/23/37 averaged within each scenario before inference; individual seeds retained.",
  "authority": "Final Closure specification03 authorizes post-hoc methodological completion, but not fabrication of owner acceptance.",
  "references": [
    "https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html",
    "https://www.jstor.org/stable/4615733"
  ]
}

| Family | Contrast | Delta min/vessel [simultaneous interval] | Direction | Holm p |
| --- | --- | --- | --- | --- |
| itp_heavy | B1-A1n | 22.518 [-10.368, 56.492] | NO_DETECTABLE_DIFFERENCE | 0.13489 |
| itp_heavy | B2-A2 | -101.970 [-133.406, -71.804] | LOWER_TIME | 0.00019998 |
| itp_medium | B1-A1n | 19.077 [2.431, 35.989] | HIGHER_TIME | 0.012599 |
| itp_medium | B2-A2 | -20.364 [-37.642, -4.520] | LOWER_TIME | 0.012599 |
| equal_family_overall | B1-A1n | 20.797 [2.510, 39.770] | HIGHER_TIME | 0.011299 |
| equal_family_overall | B2-A2 | -61.167 [-79.022, -44.403] | LOWER_TIME | 0.00019998 |

| Family | Contrast | n scenarios | Delta min/vessel [raw95] | Paired % [raw95] | Cargo upper pp | +1pp / zero NI |
| --- | --- | --- | --- | --- | --- | --- |
| itp_heavy | B1-A1n | 50 | 22.518 [-6.252, 52.100] | 1.207 [-0.378, 2.824] | not registered | not registered |
| itp_medium | B1-A1n | 50 | 19.077 [4.654, 33.913] | 1.845 [0.553, 3.192] | not registered | not registered |
| equal_family_overall | B1-A1n | 100 | 20.797 [4.764, 37.003] | 1.526 [0.506, 2.558] | not registered | not registered |
| itp_heavy | B2-A2 | 50 | -101.970 [-129.376, -75.515] | -5.610 [-7.037, -4.240] | -2.446716 | PASSED / PASSED |
| itp_medium | B2-A2 | 50 | -20.364 [-35.051, -6.208] | -1.377 [-2.610, -0.107] | -0.248499 | PASSED / PASSED |
| equal_family_overall | B2-A2 | 100 | -61.167 [-76.618, -46.169] | -3.493 [-4.433, -2.567] | -1.415042 | PASSED / PASSED |
| itp_heavy | B1-A1 | 50 | 9.679 [-23.545, 43.895] | 0.727 [-1.115, 2.621] | 4.304390 | NOT_DEMONSTRATED / NOT_DEMONSTRATED |
| itp_medium | B1-A1 | 50 | -18.464 [-38.756, 0.953] | -1.149 [-2.791, 0.507] | 0.932879 | PASSED / NOT_DEMONSTRATED |
| equal_family_overall | B1-A1 | 100 | -4.393 [-23.984, 15.388] | -0.211 [-1.473, 1.040] | 2.527489 | NOT_DEMONSTRATED / NOT_DEMONSTRATED |
| itp_heavy | A1n-A1 | 50 | -12.839 [-40.191, 15.402] | -0.358 [-1.861, 1.239] | not registered | not registered |
| itp_medium | A1n-A1 | 50 | -37.541 [-56.424, -19.536] | -2.891 [-4.291, -1.510] | not registered | not registered |
| equal_family_overall | A1n-A1 | 100 | -25.190 [-41.692, -8.474] | -1.624 [-2.666, -0.577] | not registered | not registered |
| itp_heavy | A2-A1 | 50 | -75.331 [-102.404, -48.386] | -3.976 [-5.420, -2.504] | 2.966682 | NOT_DEMONSTRATED / NOT_DEMONSTRATED |
| itp_medium | A2-A1 | 50 | -57.584 [-79.192, -36.706] | -4.555 [-6.194, -2.913] | 0.522560 | PASSED / NOT_DEMONSTRATED |
| equal_family_overall | A2-A1 | 100 | -66.458 [-83.947, -49.563] | -4.265 [-5.376, -3.184] | 1.677180 | NOT_DEMONSTRATED / NOT_DEMONSTRATED |
| itp_heavy | A3-A1 | 50 | -42.624 [-65.851, -19.345] | -2.256 [-3.539, -0.941] | 2.879220 | NOT_DEMONSTRATED / NOT_DEMONSTRATED |
| itp_medium | A3-A1 | 50 | -37.833 [-53.704, -23.120] | -2.900 [-4.094, -1.762] | 0.566327 | PASSED / NOT_DEMONSTRATED |
| equal_family_overall | A3-A1 | 100 | -40.229 [-54.218, -26.030] | -2.578 [-3.456, -1.686] | 1.657812 | NOT_DEMONSTRATED / NOT_DEMONSTRATED |
| itp_heavy | A3-A2 | 50 | 32.707 [11.936, 54.461] | 1.912 [0.743, 3.142] | not registered | not registered |
| itp_medium | A3-A2 | 50 | 19.751 [3.590, 36.536] | 1.968 [0.463, 3.531] | not registered | not registered |
| equal_family_overall | A3-A2 | 100 | 26.229 [13.303, 40.184] | 1.940 [1.006, 2.945] | not registered | not registered |
| itp_heavy | B2-A1 | 50 | -177.301 [-202.539, -152.975] | -9.515 [-10.786, -8.286] | not registered | not registered |
| itp_medium | B2-A1 | 50 | -77.948 [-102.234, -54.929] | -5.927 [-7.693, -4.182] | not registered | not registered |
| equal_family_overall | B2-A1 | 100 | -127.624 [-145.209, -111.260] | -7.721 [-8.796, -6.651] | not registered | not registered |
| itp_heavy | B2-T-A2 | 50 | -109.459 [-132.580, -87.008] | -6.066 [-7.307, -4.855] | -1.809318 | PASSED / PASSED |
| itp_medium | B2-T-A2 | 50 | -20.209 [-34.803, -6.171] | -1.364 [-2.585, -0.109] | -0.222176 | PASSED / PASSED |
| equal_family_overall | B2-T-A2 | 100 | -64.834 [-78.293, -51.620] | -3.715 [-4.573, -2.861] | -1.085192 | PASSED / PASSED |
| itp_heavy | B2-B2-T | 50 | 7.489 [-0.762, 15.668] | 0.467 [-0.004, 0.933] | -0.403157 | PASSED / PASSED |
| itp_medium | B2-B2-T | 50 | -0.154 [-0.790, 0.327] | -0.014 [-0.068, 0.024] | 0.000000 | PASSED / PASSED |
| equal_family_overall | B2-B2-T | 100 | 3.667 [-0.435, 7.777] | 0.226 [-0.012, 0.460] | -0.216598 | PASSED / PASSED |
| itp_heavy | (B2-A2)-(B1-A1n) | 50 | -124.488 [-159.793, -89.500] | NA | not registered | not registered |
| itp_medium | (B2-A2)-(B1-A1n) | 50 | -39.440 [-57.473, -22.280] | NA | not registered | not registered |
| equal_family_overall | (B2-A2)-(B1-A1n) | 100 | -81.964 [-101.568, -62.835] | NA | not registered | not registered |

| Population | S1 contrast | Delta total vessel-min [raw95] |
| --- | --- | --- |
| itp_heavy | (A2-A1)_integrated-(A2-A1)_reference | -938.054 [-1592.963, -275.927] |
| itp_medium | (A2-A1)_integrated-(A2-A1)_reference | -767.127 [-1102.254, -448.372] |
| equal_family_overall | (A2-A1)_integrated-(A2-A1)_reference | -852.591 [-1219.218, -487.801] |
| itp_heavy | (A3-A1)_integrated-(A3-A1)_reference | -696.652 [-1275.721, -121.213] |
| itp_medium | (A3-A1)_integrated-(A3-A1)_reference | -547.310 [-784.272, -326.443] |
| equal_family_overall | (A3-A1)_integrated-(A3-A1)_reference | -621.981 [-930.772, -305.835] |
