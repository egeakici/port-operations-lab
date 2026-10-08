# Project I — Integrated Terminal Pilot

Project I ("I" = **Integration**) is an intermediate research project between
Project 03 (Berth Allocation Lab, complete) and Project 04 (Rail Crane
Scheduler, future). It connects berth, quay-crane and yard decisions inside
one physically consistent, synthetic experimental terminal and measures
whether coordinating them changes terminal-wide performance.

It is **not** Project 04, Project 05, Project 09, a production Terminal
Operating System, a commercial product, or a new RL training project.

Current status: **Step 1 of 8 — Integration Specification and Compatibility
Contracts — documentation complete, awaiting user review.** No simulator,
generator, policy or adapter code exists yet.

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

## Next step

Step 2 — Unified Synthetic Scenario Generator. Its prerequisites are listed in
[docs/implementation_roadmap.md](docs/implementation_roadmap.md#step-2-prerequisites).
