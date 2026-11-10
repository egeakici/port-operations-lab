# Project 04 — Rail Crane Scheduler

**Step 01: PASS (documentation specification only).** No scheduler or physical
implementation is delivered. Steps 02–14 have not been implemented.

The target is ship-to-shore quay cranes (QCs) moving along a common quay rail,
not rail-yard RMGs, trains, wagons or truck dispatch. QCSP v1 schedules bay jobs
on one berthed vessel using two already assigned cranes. Allocating cranes
across vessels (QCAP) is a later extension. The repository's actual existing,
empty directory was `04-rail-crane-scheduler/`; this package uses it instead of
creating a second `rail-crane-scheduler/` directory.

Read the contract in this order:

1. [Problem specification](docs/01_problem_specification.md)
2. [Physical invariants and hand-worked fixtures](docs/02_physical_constraints_and_invariants.md)
3. [Scientific experiment and baseline/RL design contract](docs/03_scientific_experiment_contract.md)
4. [Source audit, reuse and integration architecture](docs/04_repository_reuse_and_integration.md)
5. [Decision register and consolidated owner packet](docs/05_step1_decision_register.md)
6. [Fourteen-step roadmap and acceptance gates](docs/06_implementation_roadmap.md)
7. [Audit, checks, closure and precise Step 02 prerequisites](docs/07_step1_audit_and_closure.md)

The [machine-readable manifest](configs/research/step1_problem_contract_v1.json)
is a design record, **not a runnable configuration**. Null physical values are
unresolved, not defaults. Recommendations have not acquired owner approval.

The existing root `.gitignore` excludes this entire project directory. These
nine documents therefore remain local and ignored; the rule was left unchanged,
and no files were staged. Any future decision to track them is separate.

Projects 01–03 and Project I remain read-only. The local Project I closure pointer
reports `PROJECT_I_FINAL_CLOSED=NO`; its Step 7 campaign is complete, while new
diagnostics remain pending. This does not block independent Project 04 design.
Project I's B2 is model-based coordination, not a newly trained crane PPO.

Next: Step 02 prepares versioned data and integration contracts, missing-field
handling, provenance, and adapter feasibility. It must not begin scheduling,
CP-SAT, simulation or PPO implementation. See the exact entry/exit gates in the
roadmap and closure note. No real-terminal calibration, commercial benefit,
jointly trained terminal policy or performance advantage is claimed.
