# Step 7 returned-results owner review - 2026-10-23

**Conclusion:** The current results support integrated berth coordination with a cargo-first objective. They do not support the stronger claim that the frozen PPO jointly optimizes berth, cranes and yard while preserving cargo performance. PPO is operational and fast, but its modest time gains against FCFS come with substantially worse cargo outcomes; it is slower than A2 on average. All findings below are descriptive SYNTHETIC / UNCALIBRATED observations. Formal uncertainty and noninferiority belong to Step8.

## Integrity and scientific coverage

- Return audit: **BYTES_AND_PAIRED_METADATA_VERIFIED**; 31626 manifested files, 13,451,426,704 bytes.
- Manifest canonical SHA256: `d180f1dec4fb212185b40658f7be47dc66d0bd08e66b6636f88cb45c42b8357d`.
- Lock file SHA256: `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`.
- Source revision: `8cc697f26575ca18ed98a164390a5a40e137b343`.
- All1960 rows completed;0 FAILED,0 G_BLOCKED,0 interrupted and0 not run. 1260 integrated and700 authentic berth-projection reference episodes.
- 140 traffic scenarios:20 validation +50 test per Medium/Heavy family. The three frozen PPO training seeds11/23/37 are nested within scenario, not150 independent traffic cases per family.
- Project I561/561 passed, all9 slow gates; Project03 eligible fast420/420 passed, 16 deselected and6 whole training/archive-consumer modules excluded for the documented authorized scope;0 skipped/errors.
- All manifested compressed bytes match the execution manifest. Approvals, source, checkpoints, scenario/lock associations, cross-arm fingerprints, N_out/T_end and1960 raw result/CSV core metrics agree. Full re-inflation and independent recomputation of every canonical uncompressed stream is NOT complete. The official full return gate remains pending manual execution; this receipt must not be relabelled as that gate.
- All1260 integrated episodes ended COMPLETED. No DEADLOCK or TRUNCATED_DRAIN_LIMIT was observed. A completed episode may still have unloaded containers; completion is not a superiority claim.
- Seven copied reference files were initially absent, all with long Windows paths. They were restored exclusively from the original checksum-verified v2 transport archive; each byte count/SHA256 matches the original execution manifest. No result, expected hash, model content or scenario was regenerated. The initial failed audit and restoration receipt are retained. Copy-internal cause is not proven.
- Current bytes/metadata audit receipt: `experiments/step7_return_review_20261023/bytes_metadata_audit.json`.
- The original verifier passed its protected-source checks before entering canonical row verification; only CRLF/LF-equivalent content differences are permitted. Review scripts live outside the locked source inventory.

## Primary test results

Each family contains50 paired traffic scenarios. TA below is **mean turnaround per vessel in simulated minutes**, not wall-clock computation time. U is mean original outbound containers not loaded per scenario. R is the mean scenario U/N_out, displayed as a percentage. PPO rows average all three seeds within scenario.

| Family | Method | TA/vessel (min) | Berth wait/vessel (min) | Mean U | Mean R (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| itp_medium | A1 | 1162.37 | 398.31 | 4.80 | 0.1004 |
| itp_medium | A1n | 1124.83 | 354.53 | 35.12 | 0.7379 |
| itp_medium | B1 | 1143.90 | 379.67 | 37.42 | 0.7875 |
| itp_medium | A2 | 1104.78 | 332.07 | 20.70 | 0.4434 |
| itp_medium | A3 (3-seed mean) | 1124.54 | 357.80 | 22.23 | 0.4716 |
| itp_medium | B2-T | 1084.58 | 328.71 | 1.36 | 0.0304 |
| itp_medium | B2 | 1084.42 | 328.76 | 0.00 | 0.0000 |
| itp_heavy | A1 | 1864.81 | 1092.66 | 12.50 | 0.1827 |
| itp_heavy | A1n | 1851.97 | 1032.85 | 251.98 | 3.6638 |
| itp_heavy | B1 | 1874.49 | 1058.77 | 278.10 | 4.0508 |
| itp_heavy | A2 | 1789.48 | 969.33 | 193.16 | 2.8106 |
| itp_heavy | A3 (3-seed mean) | 1822.19 | 1015.37 | 191.06 | 2.7882 |
| itp_heavy | B2-T | 1680.02 | 909.82 | 45.12 | 0.6404 |
| itp_heavy | B2 | 1687.51 | 923.50 | 0.48 | 0.0076 |

![Mean time/cargo tradeoffs](../experiments/step7_return_review_20261023/test_tradeoffs.png)

## Paired contrasts and consistency

Negative deltas favor the first method. Percentages are means of scenario-specific percentages with the comparator scenario as denominator; they need not equal the ratio of group means. No confidence interval, p-value or cargo NI verdict is computed.

| Family | Contrast | Mean paired TA change (%) | Mean U delta | TA better / worse / tie | U better / worse / tie |
| --- | --- | ---: | ---: | --- | --- |
| itp_medium | B2-A1 | -5.927 | -4.80 | 41/9/0 | 2/0/48 |
| itp_medium | B2-A2 | -1.377 | -20.70 | 32/18/0 | 14/0/36 |
| itp_medium | B2-T-A2 | -1.364 | -19.34 | 32/18/0 | 13/1/36 |
| itp_medium | B2-B2-T | -0.014 | -1.36 | 1/1/48 | 2/0/48 |
| itp_medium | A3-A1 | -2.900 | +17.43 | 40/10/0 | 1/19/30 |
| itp_medium | A3-A2 | +1.968 | +1.53 | 19/31/0 | 9/13/28 |
| itp_medium | A2-A1 | -4.555 | +15.90 | 37/9/4 | 1/14/35 |
| itp_heavy | B2-A1 | -9.515 | -12.02 | 50/0/0 | 12/1/37 |
| itp_heavy | B2-A2 | -5.610 | -192.68 | 44/6/0 | 49/0/1 |
| itp_heavy | B2-T-A2 | -6.066 | -148.04 | 45/5/0 | 45/4/1 |
| itp_heavy | B2-B2-T | +0.467 | -44.64 | 13/22/15 | 30/0/20 |
| itp_heavy | A3-A1 | -2.256 | +178.56 | 34/16/0 | 1/49/0 |
| itp_heavy | A3-A2 | +1.912 | -2.10 | 20/30/0 | 24/26/0 |
| itp_heavy | A2-A1 | -3.976 | +180.66 | 38/12/0 | 0/49/1 |

**B2 versus A2:** Heavy improves mean paired TA by5.61%, with192.68 fewer unloaded containers per scenario. TA improves in44/50 and cargo in49/50 (one cargo tie, zero cargo worsenings). Medium improves TA by1.38% and U by20.70, but TA worsens in18/50; cargo improves14/50 and ties36/50. This is favorable descriptive evidence, stronger in Heavy, not universal scenario dominance.

**B2 versus FCFS:** Mean paired TA improves9.51% Heavy and5.93% Medium. Heavy TA improves50/50, but cargo is worse in one scenario, better12 and equal37. Medium TA improves41/50 and worsens9; cargo improves2/50 and ties48. Thus zero cargo worsening against A2 must not be generalized to every comparator.

**PPO versus FCFS:** Mean paired TA improves2.26% Heavy and2.90% Medium. Mean U rises12.50 to191.06 in Heavy and4.80 to22.23 in Medium. Heavy cargo worsens49/50 scenarios; Medium cargo worsens19/50, improves1 and ties30. PPO is faster in34/50 Heavy and40/50 Medium scenarios, so some time benefit is repeatable, but the time-and-cargo success criterion is not met descriptively.

The predeclared formal cargo NI margin is0.01 in R (one percentage point), with zero-margin sensitivity. Observed PPO-minus-FCFS mean R differences are +2.606 percentage points Heavy and +0.371 Medium. These are point estimates, not a formal NI verdict; Step8 must apply the actual prespecified procedure.

**PPO versus A2:** PPO is slower on average by1.91% Heavy and1.97% Medium (paired percentage means). Heavy cargo is approximately similar in the aggregate but varies by seed; Medium PPO has slightly more unloaded cargo. All three PPO seeds have lower mean TA than FCFS and higher mean U than FCFS in both test families. Selecting seed23 after seeing its better cargo results would be outcome-driven selection and is not performed.

**B2 versus B2-T:** Cargo-first selection reduces Heavy U45.12 to0.48, at a mean paired TA increase of0.47% (about7.49 simulated minutes per vessel from group means). Cargo improves30/50, ties20 and never worsens; TA has13 improvements,22 worsenings and15 ties. In Medium,48/50 trajectories tie in TA; two scenarios account for the cargo difference. The objective tradeoff is visible and must be reported.

**Simple estimators:** B1 and A1n do not automatically improve the joint outcome. Heavy B1 is slower than FCFS on group means and has278.10 versus12.50 unloaded containers. Using integrated information alone is not a guarantee of a good policy.

## Validation consistency and PPO reference context

| Family | Validation contrast | Mean paired TA change (%) | Mean U delta |
| --- | --- | ---: | ---: |
| itp_medium | B2-A2 | -0.849 | -31.90 |
| itp_medium | A3-A1 | -1.942 | +29.55 |
| itp_medium | A3-A2 | +2.948 | +0.05 |
| itp_heavy | B2-A2 | -6.695 | -155.95 |
| itp_heavy | A3-A1 | -2.164 | +137.07 |
| itp_heavy | A3-A2 | +0.698 | +0.22 |

Validation shows the same direction: B2 has lower mean TA/U than A2; PPO has lower mean TA but higher U than FCFS. No validation result was used to tune policies. The original berth-projection context also shows PPO below FCFS on mean TA: mean total paired deltas are -326.33min Heavy and -58.02min Medium. A2 has larger reference improvements (-869.89min Heavy and -154.22min Medium). The authentic BAP model therefore exhibits a modest descriptive FCFS advantage in these projections, not superiority over A2 or proof of terminal-wide cargo optimization.

PPO mean waiting is lower than FCFS, but the mean of per-scenario P95 waits rises 2437.15 to3059.04min Heavy and1107.94 to1191.48min Medium. These are averages of scenario P95s, not one pooled vessel-level P95. PPO improves an average while worsening tail waiting and cargo; a single average is insufficient.

## Computational costs

Measured policy-selection cost only; observation building, environment processing, logging and verification add overhead. P95 uses the empirical95th percentile of archived decision times; decisions are not independent statistical samples.

| Test family | Arm | Mean policy seconds | P95 seconds | Max seconds | Mean episode wall seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| itp_medium | A2 | 0.0772 | 0.3280 | 1.6695 | 19.68 |
| itp_medium | A3 | 0.0037 | 0.0042 | 0.0078 | 18.39 |
| itp_medium | B2-T | 2.1501 | 7.4715 | 20.5128 | 68.11 |
| itp_medium | B2 | 2.1539 | 7.4177 | 20.5595 | 68.14 |
| itp_heavy | A2 | 0.6205 | 2.4591 | 8.3159 | 41.23 |
| itp_heavy | A3 | 0.0037 | 0.0041 | 0.0116 | 24.22 |
| itp_heavy | B2-T | 8.0416 | 25.1028 | 66.2377 | 287.83 |
| itp_heavy | B2 | 8.2580 | 26.1356 | 69.5401 | 295.61 |

- Validation stage: 6.85h; test stage: 20.22h. Sum of all13 measured stage durations: 28.50h, plus final sealing/launcher overhead.
- Summed outer episode wall time: 20.09h. This is not total campaign wall time; per-row verification/profiling/stage work is separate.
- Largest boundary/15-second sampled process RSS: 769.1MiB; not a continuous peak.
- Two-second compute warnings: 4139; approved warnings, not timeouts. K5-A full cohort/all legal candidates+WAIT is unchanged. No fallback, candidate cap or post-outcome speed tuning was added.
- PPO inference is approximately3.7ms per decision on this CPU. B2 Heavy averages8.26s and reaches69.54s for a policy decision. Operational suitability requires a decision-time requirement; this campaign does not certify a real-time deployment or real-terminal savings.

## WAIT, cargo-pivotal, rollover and forecast diagnostics

- All1260 integrated diagnostic rows passed independent cargo reconciliation against LOAD_COMPLETED and D17 rollover evidence. U counts containers, not TEU. B2 has24 unloaded containers across its140 integrated scenarios: all in Heavy test; Medium and both validation families have zero B2 U.
- 27244 archived berth decisions;2044 WAIT decisions. B2 has709 WAITs, B2-T689, A2312 and the three PPO models334 across validation+test. More WAITs do not imply better decisions or establish causality; actual policy trajectories differ.
- 284 cargo-pivotal decision/trajectory observations:114 on B2 trajectories and170 on B2-T trajectories. These are not284 unique traffic scenarios or independent samples. The one-container-pivotal count is0, so this campaign does not empirically demonstrate that narrow diagnostic case.
- The selected B2 Heavy cargo forecast error has mean predicted-minus-actual U +0.351 and MAE0.398 containers across1541 decisions. B2-T Heavy has mean -5.527 and MAE7.956 across1534 decisions. These are selected-trajectory forecasts on different states, not a calibrated head-to-head accuracy experiment or proof of objective causation.
- B2 selected-turnaround prediction mean error is -772.08min Heavy and -340.37min Medium (visible-cohort totals); the forward model tends to be optimistic on these observations. Future landside requests remain omitted and forecasts retain UNCALIBRATED_SYNTHETIC_FORECAST.
- B1 selected release prediction MAE is222.49min Heavy and208.00min Medium. This is consistent with the accepted estimator limitations; no estimator was changed after results.
- PPO recorded remaining-occupancy features above the documented training maximum in1772/3806 Heavy test decisions and1130/2417 Medium test decisions. This is distribution-shift evidence, not proof that this feature alone caused the cargo losses. G-blocked rows remain0.

## What the main-project claim can support

| Claim | Current evidence |
| --- | --- |
| Integrated coordination can improve time and cargo over nominal berth rollout | Favorable descriptive evidence for B2; stronger in Heavy; formal inference pending |
| Existing PPO improves time without sacrificing cargo versus FCFS | Not supported by the observed joint outcomes; time/cargo tradeoff |
| PPO is technically functional and fast | Supported for these successful frozen CPU evaluations |
| Three terminal problems have been jointly optimized by RL | Not established: RL chooses berths; crane/yard primitives are shared fixed rules; B2 is not RL |
| Real-terminal benefits or universal superiority are proven | Not established; uncalibrated synthetic scope, heterogeneous cases, no real-terminal test |

**Defensible wording:** In the approved synthetic terminal, a cargo-first integrated berth coordinator produced favorable average time/cargo outcomes relative to nominal berth rollout, especially under Heavy traffic. The frozen berth PPO remained fast and operational and improved mean time over FCFS, but increased unloaded cargo and did not outperform A2 on mean time. The experiment supports studying coordination; it does not establish joint RL optimization of berth, crane and yard.

## Remaining work and boundaries

- Step7 campaign execution and descriptive review are complete. Transfer file hashes and paired metadata pass. The official full return gate is still pending: deep canonical re-inflation was stopped during row verification when its runtime on the development laptop proved expensive, in accordance with owner-manual execution. The partial log remains; no experiment was interrupted or rerun. The original immutable final_summary remains unchanged and no final technical closure is invented.
- Owner manual audit command (no policy evaluation or training): `powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Complete-Step7.ps1 -Action VerifyReturn`.
- Step8 has NOT started. Paired bootstrap confidence intervals, formal S1/S2 conclusions, cargo noninferiority and any preregistered further diagnostics remain pending.
- No significance, NI pass, joint optimum, three-agent RL claim, causal WAIT claim or real port saving is inferred from descriptive means. No policy scoring, physics, checkpoint, approval value or scenario was modified; no training, scientific rerun or regression suite was launched on the development computer.
- If the owner starts Step8, code preparation and expensive manual execution remain separate. Do not pick a favorable PPO seed, retune from held-out outcomes or replace the frozen experiment.

## Derived artifacts

- `experiments/step7_return_review_20261023/descriptive_review.json`: independently recomputed CSV means/contrasts.
- `experiments/step7_return_review_20261023/diagnostic_review.json`: archived diagnostic summaries; no model deserialization.
- `experiments/step7_return_review_20261023/reference_restoration.json`: all7 restored paths, sources and hashes.
- `experiments/step7_return_review_20261023/test_tradeoffs.png` and `.svg`: standalone scientific plot.
- Analysis scripts in that same ignored review directory are read-existing-results tools; they are not part of, and do not alter, the locked experimental source.
