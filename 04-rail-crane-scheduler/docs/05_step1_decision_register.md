# Step 01 decision register and owner decision packet

The matching [JSON manifest](../configs/research/step1_problem_contract_v1.json)
contains the same unique stable IDs, evidence, categories, status, materiality,
affected steps, tests and change consequences. Proposed values do not become
approved through documentation. There are no genuinely calibrated P04 values.

Category abbreviations in the table expand exactly to `OWNER_SCOPE` (O),
`REPOSITORY_CONTRACT` (C), `RESEARCH_PROPOSAL` (R),
`UNVERIFIED_SYNTHETIC_ASSUMPTION` (U). Status abbreviations expand to
`OWNER_SCOPE_ACCEPTED` (A), `INHERITED_FROZEN` (F),
`PROPOSED_PENDING_REVIEW` (P), `DEFERRED` (D), `BLOCKED` (B).
F is scoped to inherited historical rules, not newly approved P04 coefficients.

| Decision ID | Topic / rule or proposal | Evidence / category / status | Materiality; affected steps; required check; consequence of change |
| --- | --- | --- | --- |
| P04-S01-001 | Target quay rail QCSP; one berthed vessel, two fixed cranes, known static jobs; QCAP later | Owner specification §§1,4 / O / A | Defines problem; 01–14; scope/identity check; change requires formulation major version |
| P04-S01-002 | Atomic bay/workload jobs non-preemptive; preserve original mapping, no cargo inference | Owner §§4,5; E02,E27,E33 / O / A | Defines completion; 02–14; INV01/05/09; change invalidates duration/completion comparisons |
| P04-S01-003 | Full-interval non-crossing/order/separation; safety mandatory | Owner §5; E39 confirms absent inherited travel / O / A | Physical validity; 02–14; INV03/06/07/14 and X1/X2; change requires new physics/results |
| P04-S01-004 | Meters/minutes/moves; explicit berth/ship/rail transform and orientation | E01,E04,E05,E08,E25; problem spec / R / P | Schema material; 02–14; both orientations, units, INV08/13; change requires adapter/schema migration |
| P04-S01-005 | Recommend reference-point separation input d; body widths absent; do not inherit berth clearance | Owner §5; E05,E25,E26 / R / P | Safety geometry material; freeze convention in 02, value before 04; INV07/08; change invalidates geometry fingerprints |
| P04-S01-006 | Recommend fixed effective rho per crane/job plus explicit stationary overhead; numeric values null | E11,E28,E35,E36; model gap / U / P | Physics material; 02–07 and 13; dimensional/zero-distance/rate checks, bounded equivalence; change invalidates durations and benchmarks |
| P04-S01-007 | Recommend constant-speed straight committed moves; own travel/setup/process exclusive; different cranes may overlap safely | Owner §§4,10; E01,E29,E31 / R / P | Action/time material; represent in 02, accept before 04; INV03/05/06/14; change requires path/action and solver review |
| P04-S01-008 | Propose deterministic completion-first ties, half-open resource intervals, closed safety; epsilon_t/epsilon_x values null | E30,E49 / R / P | Numeric boundary material; 02–14; INV10/13 and same-time fixtures; change changes trace/version fingerprints |
| P04-S01-009 | Validity then minimize makespan from planning start; secondary metrics separate | Owner §6 / O / A | Scientific objective; 01–14; complete/incomplete/zero-work KPI checks; amendment required for other reward/objective |
| P04-S01-010 | Four deterministic safe heuristic families; bounded CP-SAT reference with independent validation | Owner §7; scientific contract / O / A | Baseline role fixed, detailed design proposed; 05–07/11; deterministic safe coverage/status/gap checks; freeze versions before comparison |
| P04-S01-011 | One separate centralized crane Maskable PPO, new training; no P03 weight transfer assumption | Owner §7; E14,E18,E44 / O / A | Architecture direction fixed; 08–11/13; mask/space/reward/sidecar reviews; change requires new research arm |
| P04-S01-012 | Propose crane/task slots plus WAIT; elapsed-time reward; bounded failure penalty; yield/action grammar reviewed at 08–09 | scientific contract; E14,E48 patterns / R / P | Interface/reward material; 08–11; WAIT progress, reachable support, telescoping, discount audit; changing after freeze requires version/retraining |
| P04-S01-013 | Common physics/validator/splits; scenario unit; training seeds nested; online comparator matched to visibility | Owner §6; E19–E21,E34,E44 / O / A | Fairness mandatory; 02–14; split/fingerprint/leakage/pairing audits; protocol amendment needed for changes |
| P04-S01-014 | Proposed synthetic families and string seed namespaces; counts/rates/speeds/work distributions unapproved | Owner §9; scientific contract / U / P | Scenario design material; 02–03/07/10–11; reproducibility/split/coverage audits; distribution changes define new study version |
| P04-S01-015 | Preserve frozen projects, protocol hashes/checkpoints, source lock and Project I manual execution boundary | Owner §§2,3; E37,E39,E40–E43; Project I AGENTS.md / C / F | Historical integrity; all steps; source hashes/diff/unchanged checks; new experiment must be separate, never rewrite history |
| P04-S01-016 | Three-phase integration; old CraneAction cannot execute rail paths; current positions and ship bays absent | E22–E34,E39; adapter matrix / R / P | Integration conflict; 02/13; stale/reject/no-mutation/cargo mapping tests; successor versioned support required |
| P04-S01-017 | Keep exactly 14 named stages, Step 02 next | Owner §11 / O / A | Scope/governance; 01–14; gate coverage; renumbering requires owner amendment |
| P04-S01-018 | CP-SAT grid/resolution/rounding/error bounds and budgets remain unresolved | Owner §§7,10; scientific contract / R / P | Optimality comparability; 02 schema metadata, decision before 06; continuous validation/error proof; change invalidates model optimality claims |
| P04-S01-019 | Real calibration, multiple vessels/QCAP, dynamic dependencies, yard/three-branch RL deferred | Owner §§1,4,7; E26,E39 / O / D | Outside v1; later version, 08 dynamic diagnostic/13–14 caveats; data/visibility/protocol review; no scope creep |
| P04-S01-020 | Prior reference numbers are contextual only: I primary fleet 8, max per vessel 2, nominal 30 moves/h, assigned two-crane factor 0.92; original fleet 4 | E35,E36,E38 / C / F | Integration compatibility, not P04 parameter approval; 02/13; source/status and rate-equivalence audit; preserve I and version any P04 adoption |

## Consolidated material owner packet

No approval is needed to finish Step 01. Qualitative scope, non-preemption,
separate crane PPO and fourteen stages are already owner-selected. The following
is a single review packet for future contract/physics locks, not a repeated request
to authorize that direction. Step 02 can draft unit-bearing schemas autonomously;
it must retain unresolved fields and cannot certify all adapter gaps closed.

| Packet choice / linked decisions | Exact options; recommendation and reason | Deadline / unresolved effect |
| --- | --- | --- |
| O1 Safety representation / 004,005 | **Recommend externally specified reference-point d and explicit ship reference/orientation**, with no assumed body sizes. Alternative: body-aware envelope requiring both widths and edge clearance plus geometry source. | Before Step 02 schema freeze select convention; before Step 04 choose numeric geometry/clearance and tolerances. Current missing-data flags remain open. |
| O2 Motion commitment / 007,012 | **Recommend constant-speed, straight, non-preemptible move + stationary setup/process; other crane may act concurrently only after joint validation.** Alternative: interruptible/piecewise movement and explicit yield/reposition actions with richer state/reservations. Offline arbitrary recorded reposition is allowed; RL reachability restriction needs a separate review. | Encode variant/version in Step 02; choose core motion semantics before Step 04. Final RL action grammar including yielding before Step 09; do not freeze it now. |
| O3 Duration/parameter profile / 006,008,014 | **Recommend standalone synthetic effective-rate inputs with explicit overhead and provenance**, separate from I. Alternative: derived nominal × assigned-efficiency model with proven loss accounting. Supply rate/overhead, speed, rail/reach/initial geometry, horizon, tolerances and workload profile as a reviewed synthetic packet; no values invented here. | Required before Step 03 generation/Step 04 execution; representation/source status fields belong in Step 02. I's 30 and 0.92 are references only. |
| O4 Solver approximation / 018 | **Recommend conservative finite model plus continuous independent validation**, with time/position grid, error inflation and certification limited to encoded model. Alternative: an equivalence-proved exact encoding of a restricted continuous case. | Before Step 06; Step 02 reserves approximation/status/provenance metadata without choosing a grid. |

O1/O2 are the schema-affecting choices to resolve or explicitly version before
Step 02 acceptance; O3 blocks generation/physical execution, O4 blocks reference
solver lock. No response was received or inferred during this task. Unapproved
values remain null/PROPOSED_PENDING_REVIEW. Sample sizes, train budgets and reward
coefficients have later review gates; they are not hidden defaults in the JSON.

## Risks and explicit conflict disposition

| Risk | Disposition / responsible gate |
| --- | --- |
| I efficiency/transport/yard losses versus P04 job duration | Open `RATE_MODEL_NOT_EQUIVALENT`; 02 provenance, 04/13 bounded equivalence review |
| Task group versus original container cargo | Open `AGGREGATE_NOT_CARGO_LEDGER`; 02 identity contract, 13 cargo reconciliation |
| Instant reassignment versus timed non-crossing travel | Open `PRIMITIVE_ACTION_CANNOT_EXECUTE_RAIL_PLAN`; new successor support at 13 |
| Discrete solver versus continuous trajectories | Open `GRID_OPTIMUM_NOT_CONTINUOUS_OPTIMUM`; 06 proof/validation; retain model identity |
| Two cranes per vessel versus global fleet legality | Open `PER_VESSEL_CAP_NOT_RAIL_SAFETY`; 02/13 fleet/rail support review |
| No ship bay plan, current rail positions, empirical logs | Open DATA_GAP; separate synthetic layouts, no false real-data claim |
| Project I not finally closed despite completed Step 7 | Historical qualification retained; no blocker to standalone Step 01; no reruns |

There is no contradictory frozen Project 04 definition in the inspected local
tree. Thus no source contradiction prevents **specification PASS**. This is not
approval of pending choices or a physical-implementation PASS. A later choice
that changes frozen scope/physics/objectives requires a versioned amendment,
updated schemas/tests/fingerprints and fresh evidence in a separate study.
