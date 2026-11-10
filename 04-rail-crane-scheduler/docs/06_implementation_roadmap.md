# Fourteen-step implementation roadmap

The owner-selected stages and names are preserved exactly. Only Step 01 is
delivered. “Freeze” below means a future versioned, fingerprinted boundary after
that gate passes; this document does not imply those artifacts already exist.
No smoke test substitutes for a research comparison. Tests in this table are
future requirements; none were run in Step 01.

| Step / name | Dependencies; deliverable and exact definition of done | Expected verification / frozen boundary | Excluded at this step |
| --- | --- | --- | --- |
| 01 Problem Specification | Actual repository audit; consistent QCSP formulation, invariants/examples, scientific contract, adapter gaps, decisions and all 14 gates; scoped documents pass static consistency | JSON/IDs/paths/units/status/source hashes and unchanged old projects; freeze this design record with pending values explicit | All algorithms, scenarios, simulation, CP-SAT, RL and old-science edits |
| 02 Data & Integration Contracts | 01; resolve/version O1/O2 and map every source field/gap. Define schema IDs and unit-bearing fields for input/jobs/cranes/bays, geometry/rate provenance, plan/path/events/outcomes/KPIs, immutable observation/proposal and integration rejection contracts. All references/units/version rules and approximation metadata unambiguous; adapter feasibility honest | Schema/identity/unknown-field/invalid-unit/round-trip design fixtures, no executable scheduling; freeze schema versions, source mapping and decisions with unresolved numerics marked; actual adapter execution waits for 13 | Generator, physical kernel, policies, optimizer, environment, training, integration execution |
| 03 Synthetic Scenario Generator | 02, accepted O3 parameter profile; deterministic labeled standalone supported instances, independent bay/job/move counts and original IDs; split namespace/fingerprint separation and categorical coverage | Same config/seed -> identical bytes/fingerprint; invalid/impossible and zero-work fixtures labeled; freeze generator/profile/split manifests with sample sizes reviewed | Scheduling algorithms, solver, PPO; no inherited empirical calibration claim |
| 04 Physical Scheduling Core | 02–03, accepted O1–O3 motion/geometry/timing; single clock, path reservations, setup/process, deterministic events, replayable state/trace and independent validator; every physical/completion invariant implemented | All INV01–14 applicable cases, X1/X2, simultaneous events, continuity/speed/conservation, deadlock/horizon/empty input, property checks; freeze core/validator/numeric/trace versions | Policy optimization, CP-SAT, training, real-terminal safety certification |
| 05 Heuristic Baselines | 04; four distinct deterministic safe policies described in scientific contract, legal WAIT and honest coverage/unsupported handling | Same input -> identical valid plan; verify constructive stratum and failures; validator rejects malicious paths; freeze policy IDs/configs, tie rules and supported action space | PPO/training and unsupported optimality claims |
| 06 CP-SAT Reference Solver | 04–05 plus O4; bounded small-instance model, status/bounds/gaps, approximation and continuous path validation; optimal only with matching certification | Hand-solvable cases, infeasible/unknown/time-limit incumbent, integer scaling/rounding and error bounds, model/validator agreement; freeze solver/formulation/grid/budget versions | Claiming unrestricted continuous optimality without proof, large campaign, RL |
| 07 Baseline Benchmark | 03–06; common frozen inputs/physics/validator/metrics and controlled comparison of four heuristics/reference; predeclare family weights/counts/contrasts/inference before test access | Pairing/source/environment hashes, failure coverage, runtime accounting, split audits, reproducibility records; freeze baseline protocol/test manifests/results before RL test use | Training, outcomes-based test reselection, commercial ranking |
| 08 Dynamic Crane Environment | 04–07; reviewed causal event-driven interface and termination/WAIT semantics on v1; any genuinely dynamic diagnostic uses a separately declared extension | Observable-state/hidden-future mutation, time progress, no competing clock, deterministic reset/termination/truncation; freeze environment event/visibility version after review | PPO training, premature final tensor/action architecture, multi-vessel/QCAP creep |
| 09 RL Observation & Action Design | 08; review stable crane/task slots, M/overflow, scales, masks/action grammar including yielding, elapsed reward/failure bound, discount/truncation semantics | Space/dtype/shape and slot stability, masks agree with validator, finite same-time decisions, WAIT anti-stall, telescoping objective tests; freeze observation/action/reward and preprocessing versions | Training/checkpoint selection or monolithic berth+crane+yard RL |
| 10 Maskable PPO Training | 07–09; approved budget and multiple training seeds; train-only fitting, validation-only selection, seed/dependency/source provenance and complete checkpoints | Split disjointness, checkpoint sidecar/space compatibility, deterministic evaluation mode, all seeds/failures retained; freeze selected checkpoint hashes and selection rule before test | Test-driven selection, reuse of P03 weights by assumption, old-science mutation |
| 11 Scientific PPO Benchmark | 07 and frozen 10 checkpoints; preregister matched-information comparisons, nested-seed paired inference/multiplicity and quality/feasibility/compute diagnostics on held-out inputs | Scenario-first pairing, no leakage, independent validation, failure/timeout/negative findings, uncertainty and certified-reference caveats; freeze results/analysis/provenance package | Guaranteed PPO superiority, retuning on test, terminal-wide superiority claim |
| 12 Interactive Replay | 04 trace contract and 07/11 validated records; read-only rail paths and Gantt linked by IDs/times/status; gaps visible | Replay agrees with immutable trace/metrics, same-time/boundary/failure visualization, no policy/simulation rerun; freeze replay/trace compatibility and artifact links | New research episodes, physics or authoritative result mutation |
| 13 Integration Adapter & Smoke | 02,04,11–12; close/restrict readiness-matrix gaps, approved versioned successor physical support, cargo mapping and single-clock boundary; proposals validated atomically with provenance | Source fingerprint/time freshness, positions/frame/order, rail safety, original-container reconciliation, hidden/stale/rejected proposals, no mutation on reject; freeze adapter/successor contract and smoke receipts | Editing frozen Project I kernel/results or treating read-only translation as physical execution/performance evidence |
| 14 Scientific Closure | All prior gates with exceptions explicit; reproducible source/protocol/input/result/checkpoint manifest, physical/learning/reference limitations, negative results, calibration limits and handoff; every claimed result traceable | Independent release audit, hashes/reproduction receipts, all failures/unsupported cells visible, source and backups preserved; freeze final versioned research release | Deployment, real-terminal benefit or joint-RL claims without a new study |

## Direct next task: Step 02 work order

1. Read this Step 01 manifest/register and record current Git/source provenance;
   preserve prior work and keep Projects 01–03/I read-only.
2. Settle or explicitly version the O1 reference-frame/separation representation
   and O2 motion-commitment choices. Do not invent numeric approvals; O3 fields
   may remain required-without-default in schemas. Freeze no ambiguous model.
3. Specify data dictionaries and versioning/validation rules for jobs/bays/cranes,
   rail/reach/initial conditions, workload and duration basis, original source IDs,
   plan segments/modes, physical events, outcomes, metrics and provenance.
4. Specify immutable request/observation/proposal/rejection contracts with one
   authoritative clock/cargo ledger. Map every source field and explicitly fail
   unsupported missing position/bay data. Carry grid/model certification metadata
   without selecting a solver representation prematurely.
5. Review schema examples (including reverse orientation, missing ship bays,
   aggregate-only jobs, non-finite values, duplicate IDs, stale proposals, unknown
   versions and absent current positions) and adapter feasibility. Freeze Step 02
   acceptance only when representations, gaps and compatibility limits are clear.

Numeric profile approval is necessary before Step 03 generation and Step 04
physics, not a reason to implement those during Step 02. Ship stowage/real data
are not prerequisites for labelled stand-alone synthetic QCSP research. Detailed
Project I execution support is a Step 13 prerequisite, not a promised current API.

The Step 07 held-out baseline records are sealed from subsequent PPO/environment
design and selection until Step 11's evaluation lock. Development/validation
evidence supplies intermediate design feedback. Any test exposure that influenced
design requires disclosure and a fresh versioned held-out protocol.
