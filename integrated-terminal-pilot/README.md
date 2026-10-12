# Project I — Integrated Terminal Pilot

Project I ("I" = **Integration**) is an intermediate research project between
Project 03 (Berth Allocation Lab, complete) and Project 04 (Rail Crane
Scheduler, future). It connects berth, quay-crane and yard decisions inside
one physically consistent, synthetic experimental terminal and measures
whether coordinating them changes terminal-wide performance.

It is **not** Project 04, Project 05, Project 09, a production Terminal
Operating System, a commercial product, or a new RL training project.

Current status:

- Step 1 — Integration Specification and Compatibility Contracts: **Complete** (commit `48b9f80`).
- Step 2 — Unified Synthetic Scenario Generator: **Implemented** (commit `032bc23`) and
  **stabilized** (commit `c42d64c`). The 12-block reference yard and the rebuilt
  yard-bottleneck family are technically validated on development seeds. Their numerical
  values remain PROPOSED until the user approves them
  ([stabilization report and approval table](docs/step2_stabilization_report.md),
  [open decisions](docs/step2_scenario_generator.md#21-choices-that-still-require-a-decision)).
- Step 3 — Primitive Crane & Yard Policies: **Complete** (commit `cc508ef`).
  P_c (`primitive_crane_greedy_v1`) and P_y (`yard_first_fit_v1`) work over immutable
  decision-time observations and return declarative actions
  ([docs/step3_primitive_policies.md](docs/step3_primitive_policies.md)).
- Step 4 — Cloneable Integrated Terminal Simulator: **Implemented** (uncommitted, awaiting user
  review). One deterministic, cloneable event kernel executes berth, crane, transfer, yard and
  landside operations on individually identified containers
  ([docs/step4_integrated_simulator.md](docs/step4_integrated_simulator.md)). Ten v1 reference
  values are user-approved; the remaining physics stays PROPOSED
  ([docs/step4_physics_approval_audit.md](docs/step4_physics_approval_audit.md)).
- Step 4 closure (pre-Step-5 diagnostics, not a new step): **in progress, awaiting user
  decisions**. Summary trace mode, isolated diagnostic overrides, vessel-time decomposition,
  cargo-fulfilment accounting and a development-only FCFS characterization campaign
  ([docs/step4_closure_diagnostics.md](docs/step4_closure_diagnostics.md)). Amendment AM-01 (common
  balanced yard baseline) is **PROPOSED**, not approved
  ([docs/protocol_amendments.md](docs/protocol_amendments.md)); the Step 5 reference yard policy is
  not finalized.
- Next: Step 5 — Independent Integrated Benchmark (not started).

Packages: `integrated_terminal_pilot.scenarios` (Step 2), `integrated_terminal_pilot.policies`
(Step 3) and `integrated_terminal_pilot.simulator` (Step 4). No policy comparison, PPO adapter,
coordinator or RL code exists.

## Step 4 quick start

From this directory in PowerShell (development data only; outputs go to the Git-ignored
`experiments/step4_*` directories, never overwriting a run):

```powershell
python -m pytest -q tests/unit -k step4
python scripts/run_integrated_smoke.py --family itp_low --seed 10000000 --repeat
python scripts/validate_integrated_trace.py --run-dir experiments/step4_smoke/<run_id> --replay --show-state
python scripts/run_degenerate_equivalence.py --family itp_medium=30 --family itp_heavy=30 --family itp_low=10 --family itp_yard_bottleneck=10
python scripts/measure_step4_performance.py --family itp_heavy --clone-at-min 1500
python scripts/run_step4_closure_campaign.py --dry-run
python scripts/run_step4_closure_campaign.py --report
```

The smoke runs use a labelled physical integration fixture (Project 03 online FCFS over the
kernel's legal set) plus P_c / P_y. They are correctness checks, not policy results.

## Step 2 quick start

From this directory in PowerShell (Projects 01–03 installed in editable mode):

```powershell
python -m pip install -e .
python scripts/generate_integrated_scenarios.py --dry-run
python scripts/generate_integrated_scenarios.py --generate --family itp_medium=2 --family itp_heavy=2 --family itp_low=2 --family itp_yard_bottleneck=2
python scripts/validate_integrated_scenarios.py --validate --run-dir experiments/scenarios/development/<run_id>
python scripts/validate_integrated_scenarios.py --audit --run-dir experiments/scenarios/development/<run_id>
python -m pytest -q
```

- **Configuration:** `configs/generator/itp_generator_v1.yaml` with its decision register
  `configs/generator/itp_generator_v1_decisions.yaml` (every parameter has a source and a
  status: FROZEN, PROPOSED_PENDING_REVIEW, BLOCKED or DEFERRED).
- **Output:** generated runs go to the Git-ignored
  `experiments/scenarios/development/<run_id>/`, with `manifest.json` (+ `.sha256`),
  per-file hashes, the scenario index, the validation and fingerprint audits, and the quality report.
  Runs are immutable.
- **Scope:** only the development split can be generated. Validation, test and diagnostic
  bands are reserved.
- **Scenario contents:** each scenario contains individually identified containers
  (import, export, transshipment, initial inventory), container groups reconciled to TEU and moves,
  G0 block-level yard geometry with a Bay/Row/Tier foundation, a quay crane fleet, immutable
  landside requests, a Project 03 berth projection and fingerprints.
- **Full description:** [docs/step2_scenario_generator.md](docs/step2_scenario_generator.md).
- **Golden fixture:** the Step 1 worked example, at `tests/fixtures/golden/`.

## Research questions (frozen)

- **S1 — Transfer of existing BAP policies.** Do the relative performance
  characteristics of frozen berth-only policies (Online FCFS, berth-only
  Online Rollout, frozen Dynamic Maskable PPO seeds 11/23/37) change when the
  same berth decisions are physically executed in a terminal with shared quay
  cranes and yard constraints?
- **S2 — Value of integrated coordination.** Does explicitly using berth,
  quay-crane and yard information improve terminal-wide performance relative
  to independent decisions executed in the *same* physical terminal?

Any scientifically valid outcome — improvement, no effect, or deterioration —
is an acceptable result.

## Step 1 documents

Read in this order:

| Document | Content |
| --- | --- |
| [docs/integration_specification.md](docs/integration_specification.md) | System boundary, decision register, physical couplings, shared state, event order, service semantics, exclusions |
| [docs/repository_capability_audit.md](docs/repository_capability_audit.md) | Source-verified inventory of Projects 01–03, reuse classification, empirical probes, baseline tests |
| [docs/unified_data_contract.md](docs/unified_data_contract.md) | Scenario format, entity records, units, mutable/immutable split, serialization, fingerprints |
| [docs/container_yard_foundation.md](docs/container_yard_foundation.md) | Container identity, lifecycle, TEU/move accounting, Bay/Row/Tier geometry, G0/G1 fidelity, event ledger, data quality, worked example |
| [docs/simulator_architecture_decision.md](docs/simulator_architecture_decision.md) | SimPy reuse vs. cloneable deterministic kernel, with source evidence |
| [docs/bap_compatibility_contract.md](docs/bap_compatibility_contract.md) | Frozen Dynamic PPO compatibility gate, nominal vs. realized service, PASS/BLOCK rules |
| [docs/scientific_experiment_protocol.md](docs/scientific_experiment_protocol.md) | S1/S2, A1/B1/A2/B2, A3/B3, splits, seeds, KPIs, uncertainty, held-out lock |
| [docs/implementation_roadmap.md](docs/implementation_roadmap.md) | Eight steps, inputs/outputs, gates, tests, exclusions |
| [docs/step2_scenario_generator.md](docs/step2_scenario_generator.md) | Step 2: generator usage, decision resolution, amendments A1–A10, container model, validation, development data, limitations |
| [docs/step2_stabilization_report.md](docs/step2_stabilization_report.md) | Step 2 stabilization: yard-capacity root cause, pre-staging rule, alternatives, 12-block reference, bottleneck redesign, development campaign, approval table |
| [docs/step3_primitive_policies.md](docs/step3_primitive_policies.md) | Step 3: observation and action contracts, P_c and P_y, diagnostic yard heuristic, Project 02 equivalence, visibility rules, Step 4 integration notes |
| [docs/step4_integrated_simulator.md](docs/step4_integrated_simulator.md) | Step 4: kernel architecture, API, events, state, cloning, hidden-information boundary, physical rules, termination, invariants, trace, metrics, results |
| [docs/step4_physics_approval_audit.md](docs/step4_physics_approval_audit.md) | Step 4: user-approved values, remaining provisional parameters, execution rules needing review |

## Status vocabulary used in every document

- **FROZEN** — decided for Project I v1; changing it requires a documented
  protocol amendment before any validation result is read.
- **PROPOSED** — the intended choice; must be confirmed or replaced (with
  reasons) at the step named in the decision register, before validation.
- **BLOCKED BY REPOSITORY EVIDENCE** — source inspection showed the option is
  incompatible with the existing code or its scientific contracts.
- **DEFERRED** — out of Project I scope; each deferral states whether the v1
  contracts can absorb it without breaking changes.

## Relationship to completed projects

Projects 01–03 are consumed as installed packages
(`terminal_core`, `mini_port_sim`, `berth_allocation_lab`). Project I never
edits their source, configurations, checkpoints or experiment artifacts.
Project 03's frozen release and checkpoints are referenced by path and
SHA-256 only.

## Known limitations (Steps 2–4)

- Most cargo, landside and yard parameters are synthetic research assumptions, PROPOSED and
  not calibrated. They must be approved before any validation comparison. Data is never
  altered to pass, and infeasible inputs are rejected explicitly.
- Step 2 establishes structural validity and initial physical feasibility only. Whether
  the yard or the cranes actually bind at runtime is a Step 4 question.
- Generated scenarios are G0 (block-level). G1 slot data is validated but never
  fabricated. No stacking or relocation logic exists.
- Scenario files are about 10–19 MB, because individual containers are the source of truth.
- Step 4 measured on development seeds that, under P_y first fit, one block's handling capacity caps
  discharge and that heavy and bottleneck seeds can reach the drain limit; this needs a decision
  before Step 5 (see the physics approval audit §5).

## Next step

Step 5 — Independent Integrated Benchmark
([roadmap](docs/implementation_roadmap.md#step-5--independent-integrated-benchmark)). Its
prerequisites are listed in [docs/step4_integrated_simulator.md](docs/step4_integrated_simulator.md) §15.
