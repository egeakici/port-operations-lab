# project i executive results summary

**SYNTHETIC / UNCALIBRATED. PROJECT_I_FINAL_CLOSED=NO. Primary adjusted inference is POST_HOC_MULTIPLICITY_COMPLETION.**

Step7 source `8cc697f26575ca18ed98a164390a5a40e137b343`; lock `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`; return VERIFIED_FULL_CANONICAL reused. Current analysis HEAD `2a05112bd5576b31dc7db36618ea3dfc287f07bb`.

Bundle `integrated-terminal-pilot/experiments/step8_final_closure/4b959879b7ed0606/releases/818f2604c2efabc8`. Primary method `cf94c23a9ad77e4db55438e72f45ae72e3869d58c93a52a806b842dc1b3da966`. Packet `9103d8987cc581551e40f015fe0dec8e77320ac65bbf924db1f115b728ac729b`; approval AWAITING_EXPLICIT_OWNER.

This study compares berth-only and terminal-aware berth decisions under shared crane, transport,
yard and cargo constraints in a synthetic integrated terminal. A locked paired campaign of1960 episodes
includes50 independent test scenarios in each of Medium and Heavy and three frozen PPO checkpoints.
Cargo-first model-based B2 reduces average turnaround and original outbound cargo loss relative to
berth-only A2; frozen berth PPO offers faster inference but mixed cargo safety. Primary multiplicity
analysis is completed with an explicitly post-hoc conservative simultaneous-bootstrap procedure and
supporting Holm tests. Independent13M sensitivity/coupling diagnostics have the exact execution status
shown below; unfinished diagnostics prevent scientific closure. Results support conditional terminal-aware
decision support, not joint three-problem RL or calibrated real-terminal productivity claims.

| Family | Contrast | Delta min/vessel [simultaneous interval] | Direction | Holm p |
| --- | --- | --- | --- | --- |
| itp_heavy | B1-A1n | 22.518 [-10.368, 56.492] | NO_DETECTABLE_DIFFERENCE | 0.13489 |
| itp_heavy | B2-A2 | -101.970 [-133.406, -71.804] | LOWER_TIME | 0.00019998 |
| itp_medium | B1-A1n | 19.077 [2.431, 35.989] | HIGHER_TIME | 0.012599 |
| itp_medium | B2-A2 | -20.364 [-37.642, -4.520] | LOWER_TIME | 0.012599 |
| equal_family_overall | B1-A1n | 20.797 [2.510, 39.770] | HIGHER_TIME | 0.011299 |
| equal_family_overall | B2-A2 | -61.167 [-79.022, -44.403] | LOWER_TIME | 0.00019998 |

B2 versus A2 improves average turnaround and cargo loss in both primary families. The adjusted
time evidence is a disclosed post-hoc methodological completion, not a fully preregistered adjusted test.
Medium has18/50 worse-time scenarios and Heavy6/50; average benefit is not dominance. B2 is model-based, not RL.

PPO versus FCFS improves time in both families. The approved +1pp cargo non-inferiority passes in Medium
(upper +0.566327pp) but is NOT_DEMONSTRATED in Heavy (upper +2.879220pp) and equal-family overall.
Zero-margin sensitivity fails in both. PPO versus A2 is slower on mean time. All11/23/37 seeds are retained;
their within-scenario average is one traffic replicate, not three independent scenarios.

B2 versus B2-T on Heavy reduces mean original unloaded containers45.12 to0.48, with mean time cost
+7.48857min/vessel and raw95% interval[-0.76182,15.66806]. That positive time cost is not statistically
established. AM07 cargo-first objective shows a tradeoff; this is not an RL effect. B1's simple integrated
release estimator can perform worse than its nominal control; more information alone is not sufficient.

The S1 reference is the authentic unchanged Project03 nominal BAP environment. Negative difference-in-differences
means the comparator-relative advantage is stronger in the integrated environment, not that the two environments
have directly comparable absolute physical times. Rankings, signs and tails remain in derived_arrays.json.
