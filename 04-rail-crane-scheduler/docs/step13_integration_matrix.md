# Step 13 isolated adapter and successor integration guide

| Actual source | Status | Boundary |
| --- | --- | --- |
| Project01 QuayCrane ID/position; OperationTask ID/routes | EXACT_NATIVE identities/units; ADAPTER_NEEDED task grouping | Immediate move_to is not timed shared-rail execution; TEU is not moves |
| Project02 PortSimulation.env/elapsed_minutes and TaskWorkPlan | ADAPTER_NEEDED | One simulator clock; explicit source group/move mapping and new rail reservations required |
| I policies/observations.py CraneObservation/CraneVesselView | ADAPTER_NEEDED | Actual schema itp_crane_observation_v1; time/vessel/berth/work/cap can be checked |
| I CraneView | MISSING_DATA | No current rail position, speed, bay job or footprint; cannot create faithful QCSP input alone |
| I scenarios/models.py LOCATION_KEYS; validation.py non-yard slot rule | MISSING_DATA | Yard geometry is not vessel stowage; no inferred ship-bay positions |
| I simulator/physics.py crane_rate_moves_per_hour | AGGREGATE_APPROXIMATION | Nominal × assigned efficiency plus transport/yard restrictions is not automatically P04 effective rate |
| I policies/actions.py CraneAction and simulator/validator.py validate_crane_action | INCOMPATIBLE_PHYSICS | Vessel/crane allocation action cannot represent timed bay motion; no fake native action emitted |
| I simulator/ledger.py and WorkOrderState original container_indices | ADAPTER_NEEDED | Actual execution/ledger remain terminal authority; synthetic P04 jobs do not certify cargo loading |

`p04_isolated_crane_proposal_v1` accepts one primitive-style snapshot only with
explicit TEST_FIXTURE_SYNTHETIC bay/motion/task enrichment. Source snapshot hash
is computed from that actual synthetic observation, not invented historical
provenance. Missing data, axis/clearance/cap/clock/work mismatches or absent source
task references reject. No actual frozen run is enriched or replayed.

The output is an immutable forecast proposal with original task links, job moves,
bay/crane IDs and times, bound to source hash/decision/clock. The isolated harness
rejects stale/altered/partial proposals before mutation, then executes only its
own Project04 fixture kernel and reconciles exactly-once tasks/moves/forecast.
This is ISOLATED_SMOKE_PASS, not live Project I integration or terminal benefit.

A successor needs live rail state, declared body/separation/movement model,
ship bay/task mappings, resource locks, atomic freshness validation, clock-owned
execution events and original-container ledger reconciliation. BAP owns berth
decisions; scheduler proposes only QCSP plans. State change invalidates forecasts
and triggers a new plan, never non-preemptive-task cancellation. Do not patch the
historic kernel to bypass these gaps. LIVE_INTEGRATION_PENDING and
FULL_TERMINAL_INTEGRATION_NOT_PERFORMED remain explicit.
