# Project 04 — Rail Crane Scheduler

**Current engineering state: IMPLEMENTATION_PARTIAL_BLOCKED.** The fourteen-stage
batch implementation has fixture-tested contracts, generation, scheduling,
independent verification, four heuristics, RL tools, evaluation, replay and an
isolated adapter. OR-Tools integration and owner-approved research physics remain
pending. No PPO optimization, trained research checkpoint or held-out campaign
was executed. Step 01's original scientific contract/history is preserved below.

Start with [the consolidated development report](docs/development_run/FINAL_REPORT.md),
[machine status](docs/development_run/FINAL_STATUS.json),
[manual PowerShell runbook](docs/MANUAL_EXECUTION.md), and
[one owner decision packet](docs/development_run/OWNER_DECISIONS.md).

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

The existing root `.gitignore` excludes this project directory. The owner already
committed the original nine Step 01 documents; new source/tests/docs remain ignored
unless explicitly tracked later. Root ignore rules were left unchanged, nothing
was staged and no commit/push was performed. Local experiments/model smoke files
must remain excluded from source commits.

Projects 01–03 and Project I remain read-only. The local Project I closure pointer
reports `PROJECT_I_FINAL_CLOSED=NO`; its Step 7 campaign is complete, while new
diagnostics remain pending. This does not block independent Project 04 design.
Project I's B2 is model-based coordination, not a newly trained crane PPO.

The original Step 01 gate applies to its completed documentation-only task. The
later batch mandate authorizes separate stages; receipts retain every failed and
successful attempt. Next owner actions are research-profile/interface approval,
isolated OR-Tools dependency verification and separately authorized manual
training/evaluation. No real-terminal calibration, commercial benefit, joint
terminal RL or empirical performance superiority is claimed.

From repository root, without installation:

```powershell
$env:PYTHONPATH = (Resolve-Path .\04-rail-crane-scheduler\src).Path
python -B -m rail_crane_scheduler training --mode check
python -B -m rail_crane_scheduler evaluation --mode status
python -B 04-rail-crane-scheduler/scripts/check_stage.py 14
```
