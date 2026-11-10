# Step 02: implemented contracts

Wire schema `p04_contracts_v1` is independent from proposed physics profile
`p04_reference_point_constant_speed_proposed_v1`. Immutable dataclasses in
`src/rail_crane_scheduler/contracts.py` are the single field/type source.
Unknown versions/fields, duplicate JSON keys, non-finite numbers and bool-as-number
are rejected with ContractError(code, path, message). No guessed migrations.

| DTO | Owner / consumer / representation boundary |
| --- | --- |
| ProblemMetadata | Input producer / every stage: schema, role, family, seed namespace, origin and source snapshot; empirical input unsupported |
| VesselContext | Berth authority / geometry: fixed berth, hull, orientation, elapsed planning start and optional timezone-aware epoch |
| RailGeometry | Input producer / later kernel: rail axis/bounds, explicit reference-point separation or UNRESOLVED, horizon and tolerances |
| CraneDefinition | Input producer / later kernel: ID, physical rank, initial point, reach, available time, speed/effective rate/setup; unresolved values null |
| BayDefinition | Input producer / job mapping: local meters and optional checked global meters |
| CraneTaskGroup | Input producer / scheduler: original integer moves, operation, vessel/bay and optional original source identities; no invented containers |
| QCSPProblem | Contract root: exact two-crane rank-ordered tuple, unique identities/references, work total, exact units; canonical payload hash excludes no input field |
| SchedulingDecision | Policy intention: ASSIGN_TASK(crane,task) or WAIT with no numeric duration; legality deferred to kernel |
| CraneObservation | Kernel producer later: current known workload, clock, positions/availability and assigned/completed original IDs; no hidden future |
| MotionSegment / ScheduledTask | Later planner producers: timed mode/path and departure/setup/process/completion records; structural validation only |
| CraneSchedule | Candidate only; policy/solver provenance, original problem hash, stop time, jobs/paths; cannot self-certify VALIDATED_FEASIBLE |
| CraneTraceEvent | Later kernel: version, stable event ID/sequence/time/kind and original references |
| MetricRecord | Later independent reporting: validity-gated makespan, moves, crane-minutes, distance and policy seconds; not a cargo ledger |

Canonical JSON is sorted-key, compact UTF-8, no NaN/Infinity. Float-typed fields
normalize numeric integers to float without precision-losing large conversions;
integer fields stay integer. Semantically ordered arrays remain ordered. SHA256
hashes these canonical payload bytes, with no embedded self-hash. Physical
fingerprint excludes metadata only, to detect split duplicates under new IDs.

Examples and negative fixtures are in `tests/test_step02_contracts.py`; fixture()
is TEST_FIXTURE_SYNTHETIC, not a runtime default. Direct constructors require
immutable tuples; JSON arrays decode to tuples. All representations are tested
for round-trip/hash stability. Optional JSON Schema copies are deliberately
omitted to avoid a second diverging field definition.

Step 01 decisions remain unchanged. Schema explicitly versions the proposed O1/O2
reference-point/constant-speed variant without approving it. Nullable required
numeric inputs can be serialized but cannot execute. Research approval/profile
lock remains OWNER_APPROVAL_REQUIRED; only labelled fixtures may execute the
proposed variant in subsequent engineering stages.
