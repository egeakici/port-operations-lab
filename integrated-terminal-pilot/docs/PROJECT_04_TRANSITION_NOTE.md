# Project04 transition note

Project04 Rail Crane Scheduler is a separate future project. This note does not
implement it or change its files. Project I remains the existing eight-step pilot;
its precise closure state is in [the current machine gate](step8/CURRENT_FINAL_CLOSURE.json)
and [scientific closure note](../PROJECT_I_SCIENTIFIC_CLOSURE.md).

After the qualified scientific release, freeze Project I source, protocols,
models, approvals and result manifests. Reuse only stable documented public
contracts: typed observations/actions, deterministic event ordering, validation
and rejection discipline, scenario/configuration fingerprints, cargo identity,
KPI units and censored-result conventions. Version any new API in Project04;
never patch the frozen Project I kernel to make future experiments easier.

Project I did not model operational rail-crane travel interference or train yard
RL. Crane home positions are reserved fields, not evidence of solved rail scheduling.
Project04 must state its own physical assumptions, objectives, baselines, training
and evaluation splits, calibration limits, safety constraints and statistical plan.
It may cite Project I's conditional terminal-aware coordination evidence, but must
not attribute B2's model-based gains to PPO or claim three-branch joint RL.

Keep an immutable Project I master and a manifest-backed collaborator copy. Any
new analysis of it is explicitly exploratory and independently versioned; any
new scheduler campaign belongs to Project04 with its own owner execution workflow.
