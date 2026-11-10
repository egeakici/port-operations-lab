# Consolidated owner review packet — no implied approval

All items below remain OWNER_APPROVAL_REQUIRED. Step 01 P04-S01 statuses and
historical records are unchanged. Safe engineering used explicitly labelled
proposed fixture physics under the master/Steps03–04 permission, not empirical
or owner-approved constants. Code/tests do not turn proposals into preregistration.

| Issue / inherited contract | Exact options and recommendation | Dependent gate |
| --- | --- | --- |
| O1 / P04-S01-004,005 | Recommend explicit ship origin/orientation, global meter axis and reference-point d supplied as input. Alternative body-aware envelopes need widths, edge clearance and a new supported physical profile. No body dimensions are inferred. | Primary schema/physics lock |
| O2 / P04-S01-007,012 | Recommend the implemented constant-speed, straight, committed travel + stationary setup/process variant with safe cross-crane concurrency. Its action model has no joint yield/reposition; accept this restricted dispatch subclass or commission a versioned richer action/kernel model. | Physical and RL action support lock |
| O3 / P04-S01-006,008,014 | Recommend standalone effective rates plus explicit setup, rail/reach/positions, speed, d, horizon, tolerances and workload/distribution/range/seed-role definitions. Alternative nominal × assigned-efficiency requires demonstrated loss accounting. Supply actual reviewed values; fixture numbers are not the proposal's approved defaults. | Primary generation, physical experiments, training |
| O4 / P04-S01-018 | Recommend the finite-event-dispatch CP model for <=5 jobs with exact integer representability, explicit node/tick/time budgets. Alternative general moving-crane CP requires a new formulation/proof. It is not a continuous global optimum. OR-Tools is absent; isolated dependency resolution/test is separate from approval. | CP reference execution/claim |
| O5 / P04-S01-012 | Recommend the implemented stable slots/pair+WAIT action map, known-state normalization, gamma=1 elapsed-time reward and explicit failure bound; no shaping. Choose M/step limit/scale/margin/network/budget/seeds/validation interval. Alternative discount/shaping/yield changes require interface amendment and tests. | Meaningful PPO training/interface freeze |
| O6 / P04-S01-013,014 | Choose disjoint cohorts, scenario counts/weights, primary comparator hierarchy, minimum scenario support, bootstrap seed/draws/confidence and multiplicity/interval plan before test. CP results are eligible only for matched supported subclass. Keep failures unconditional and PPO seeds nested. | Confirmatory benchmark lock |

Use exact canonical payload/source hashes and a separately recorded owner approval
receipt. manual-confirm must equal the approved payload digest. No approval file
was created by this development run. Ordinary naming/test repairs are complete
and do not need decisions. Missing real ship bay/cargo/rail data and a native
successor integration API remain DATA_GAP/INCOMPATIBLE_PHYSICS, not automatic
reasons to change frozen Project I. This packet is the single review surface.
