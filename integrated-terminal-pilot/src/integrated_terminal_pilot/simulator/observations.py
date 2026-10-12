"""Decision-time observations built from kernel state (the policy-facing boundary).

The kernel holds the complete exogenous future (needed to execute the
scenario). Policies never receive the kernel, its state, its event queue or the
scenario catalog; they receive only these immutable observations:

* ``CraneObservation`` / ``YardObservation`` - the Step 3 contracts
  (``itp_crane_obs_v1`` / ``itp_yard_obs_v1``), built from current state only.
* ``BerthView`` - the integration-fixture berth observation: revealed vessels
  (announced, waiting, occupying, departed), current legal immediate
  assignments and the WAIT bit. No hidden vessel contributes a slot, a count or
  a bit (D18, spec §10). It is not the Step 5 ``BerthViewAdapter``.

None of these carries scheduled gate-in or pickup times, unannounced vessels,
future completion times, scenario identity, seed or fingerprints.
"""

from __future__ import annotations

from dataclasses import dataclass

from integrated_terminal_pilot.policies.observations import (
    CraneObservation, CraneVesselView, CraneView, YardBlockView, YardContainerView, YardObservation,
    YardRequest,
)

BERTH_VIEW_SCHEMA = "itp_berth_view_v1"
BERTH_VIEW_STATUS = {"NOT_ARRIVED": "ANNOUNCED", "WAITING": "WAITING", "BERTHING_PREP": "OCCUPYING",
                     "HANDLING": "OCCUPYING", "DEPARTURE_PREP": "OCCUPYING", "DEPARTED": "DEPARTED"}


@dataclass(frozen=True)
class BerthVesselView:
    vessel_id: str
    slot_index: int
    status: str                       # ANNOUNCED | WAITING | OCCUPYING | DEPARTED
    arrival_time_min: float           # exact from announcement (D18)
    length_m: float
    nominal_service_time_min: float   # D20
    berth_position_m: float | None
    berth_start_time_min: float | None
    estimated_release_time_min: float | None  # ServiceForecaster v1, occupying vessels only


@dataclass(frozen=True)
class BerthView:
    time_min: float
    decision_id: str
    berth_length_m: float
    min_clearance_m: float
    future_horizon_min: float
    vessels: tuple[BerthVesselView, ...]                      # slot (reveal) order
    legal_choices: tuple[tuple[str, int, float, float], ...]  # (vessel_id, candidate_index, position, arrival)
    wait_legal: bool
    schema_version: str = BERTH_VIEW_SCHEMA


def build_berth_view(kernel) -> BerthView:
    catalog, state = kernel.catalog, kernel.state
    vessels = []
    for vessel_id in state.reveal_order:
        v = state.vessels[vessel_id]
        record = catalog.vessel_by_id[vessel_id]
        occupying = v.phase in ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP")
        vessels.append(BerthVesselView(
            vessel_id=vessel_id, slot_index=v.slot_index, status=BERTH_VIEW_STATUS[v.phase],
            arrival_time_min=record.arrival_time_min, length_m=record.length_m,
            nominal_service_time_min=record.nominal_service_time_min,
            berth_position_m=v.berth_position_m, berth_start_time_min=v.berth_start_time_min,
            estimated_release_time_min=kernel.forecast_release(vessel_id) if occupying else None))
    return BerthView(time_min=state.now_min, decision_id=state.pending.decision_id,
                     berth_length_m=catalog.berth_length_m, min_clearance_m=catalog.min_clearance_m,
                     future_horizon_min=catalog.physics.future_horizon_min, vessels=tuple(vessels),
                     legal_choices=kernel.legal_berth_choices(), wait_legal=kernel.berth_wait_legal())


def build_crane_observation(kernel, decision_id: str | None) -> CraneObservation:
    catalog, state = kernel.catalog, kernel.state
    vessels = []
    held = {}
    for crane in state.cranes.values():
        if crane.assigned_vessel_id is not None:
            held.setdefault(crane.assigned_vessel_id, []).append(crane.crane_id)
    for vessel_id in state.reveal_order:
        v = state.vessels[vessel_id]
        if v.phase not in ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP"):
            continue
        record = catalog.vessel_by_id[vessel_id]
        vessels.append(CraneVesselView(
            vessel_id=vessel_id, phase=v.phase, length_m=record.length_m,
            berth_position_m=v.berth_position_m, berth_start_time_min=v.berth_start_time_min,
            max_cranes=record.max_cranes, remaining_moves=kernel.remaining_moves(vessel_id),
            assigned_crane_ids=tuple(sorted(held.get(vessel_id, ()))), priority=record.priority))
    cranes = []
    for crane in state.cranes.values():
        record = catalog.crane_by_id[crane.crane_id]
        cranes.append(CraneView(crane_id=crane.crane_id, status=crane.status,
                                assigned_vessel_id=crane.assigned_vessel_id,
                                nominal_moves_per_hour=record.nominal_moves_per_hour,
                                compatible_vessel_ids=record.compatible_vessel_ids,
                                activity=crane.activity))
    return CraneObservation(time_min=state.now_min, vessels=tuple(vessels), cranes=tuple(cranes),
                            decision_id=decision_id)


def build_yard_observation(kernel) -> YardObservation:
    catalog, state = kernel.catalog, kernel.state
    request = kernel.pending_yard_request()
    containers = []
    for i in request.container_indices:
        c = catalog.containers[i]
        containers.append(YardContainerView(
            container_id=c.container_id, container_group_id=c.group_id,
            container_size=c.container_size, size_teu=c.size_teu, cargo_flow=c.cargo_flow,
            load_state=c.load_state, is_reefer=c.is_reefer, is_hazardous=c.is_hazardous,
            origin_vessel_id=c.origin_vessel_id, destination_vessel_id=c.destination_vessel_id,
            status=state.c_status[i]))
    yard_request = YardRequest(work_order_id=request.work_order_id,
                               operation_type=request.operation_type,
                               source_location_id=request.source_location_id,
                               containers=tuple(containers))
    blocks = []
    for record in catalog.blocks:
        block = state.blocks[record.block_id]
        blocks.append(YardBlockView(
            block_id=record.block_id, status=block.status, capabilities=tuple(record.capabilities),
            allowed_sizes=tuple(record.allowed_sizes), capacity_teu=record.capacity_teu,
            occupied_teu=block.occupied_teu, reserved_teu=block.reserved_teu,
            blocked_teu=block.blocked_teu,
            handling_capacity_moves_per_hour=record.handling_capacity_moves_per_hour,
            transfer_point_x_m=record.transfer_point_x_m, transfer_point_y_m=record.transfer_point_y_m))
    return YardObservation(time_min=state.now_min, request=yard_request, blocks=tuple(blocks),
                           decision_id=state.pending.decision_id)


__all__ = ["BERTH_VIEW_SCHEMA", "BerthVesselView", "BerthView", "build_berth_view",
           "build_crane_observation", "build_yard_observation"]
