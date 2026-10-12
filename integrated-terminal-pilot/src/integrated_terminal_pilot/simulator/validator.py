"""The authoritative ``PhysicalActionValidator`` (integration specification §6).

Every berth, crane and yard action is validated against the *current* kernel
state before any mutation. Validation is read-only and atomic: an action is
accepted as a whole or rejected with ``PhysicalActionRejected`` (a structured
``rejection_code``) and the state is left byte-identical. Nothing is repaired:
an illegal assignment is never turned into a different legal one.

The validator is identical for every experimental arm. Policies, forward models
and coordinators may choose different actions; they can never change what is
physically legal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from berth_allocation_lab.core import are_spatially_separated, is_within_quay
from berth_allocation_lab.core.types import BAPPlacement

from integrated_terminal_pilot.policies.actions import CraneAction, YardAction
from integrated_terminal_pilot.simulator.errors import PhysicalActionRejected
from integrated_terminal_pilot.simulator.events import TIME_TOL

BERTH_ACTION_SCHEMA = "itp_berth_action_v1"

# Structured rejection codes.
STALE_ACTION = "STALE_ACTION"                       # wrong decision id / time / kind
INVALID_ACTION = "INVALID_ACTION"                   # malformed action object
UNKNOWN_VESSEL = "UNKNOWN_VESSEL"
VESSEL_NOT_WAITING = "VESSEL_NOT_WAITING"
NON_FINITE_POSITION = "NON_FINITE_POSITION"
POSITION_OUTSIDE_QUAY = "POSITION_OUTSIDE_QUAY"
BERTH_OCCUPIED = "BERTH_OCCUPIED"                   # overlap or clearance violation with an occupying vessel
WAIT_NOT_LEGAL = "WAIT_NOT_LEGAL"
UNKNOWN_CRANE = "UNKNOWN_CRANE"
CRANE_NOT_AVAILABLE = "CRANE_NOT_AVAILABLE"
CRANE_INCOMPATIBLE = "CRANE_INCOMPATIBLE"
VESSEL_NOT_SERVICEABLE = "VESSEL_NOT_SERVICEABLE"
NO_REMAINING_WORK = "NO_REMAINING_WORK"
MAX_CRANES_EXCEEDED = "MAX_CRANES_EXCEEDED"
RELEASE_NOT_ASSIGNED = "RELEASE_NOT_ASSIGNED"
RELEASE_DURING_BATCH = "RELEASE_DURING_BATCH"
CONTAINER_SET_MISMATCH = "CONTAINER_SET_MISMATCH"
REQUIRED_TEU_MISMATCH = "REQUIRED_TEU_MISMATCH"
UNKNOWN_BLOCK = "UNKNOWN_BLOCK"
BLOCK_NOT_OPEN = "BLOCK_NOT_OPEN"
SIZE_NOT_ALLOWED = "SIZE_NOT_ALLOWED"
CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
MISSING_DESTINATION_CAPACITY = "MISSING_DESTINATION_CAPACITY"   # DQ14
UNAVAILABLE_SOURCE_INVENTORY = "UNAVAILABLE_SOURCE_INVENTORY"   # DQ13

REJECTION_CODES = (
    STALE_ACTION, INVALID_ACTION, UNKNOWN_VESSEL, VESSEL_NOT_WAITING, NON_FINITE_POSITION,
    POSITION_OUTSIDE_QUAY, BERTH_OCCUPIED, WAIT_NOT_LEGAL, UNKNOWN_CRANE, CRANE_NOT_AVAILABLE,
    CRANE_INCOMPATIBLE, VESSEL_NOT_SERVICEABLE, NO_REMAINING_WORK, MAX_CRANES_EXCEEDED,
    RELEASE_NOT_ASSIGNED, RELEASE_DURING_BATCH, CONTAINER_SET_MISMATCH, REQUIRED_TEU_MISMATCH,
    UNKNOWN_BLOCK, BLOCK_NOT_OPEN, SIZE_NOT_ALLOWED, CAPABILITY_MISMATCH,
    MISSING_DESTINATION_CAPACITY, UNAVAILABLE_SOURCE_INVENTORY,
)


@dataclass(frozen=True)
class BerthAction:
    """WAIT, or start serving one waiting vessel now at a continuous quay position (D06)."""

    policy_id: str
    action_type: str                   # "ASSIGN" | "WAIT"
    vessel_id: str | None = None
    berth_position_m: float | None = None
    decision_id: str | None = None
    schema_version: str = BERTH_ACTION_SCHEMA

    @classmethod
    def wait(cls, policy_id: str, decision_id: str | None = None) -> "BerthAction":
        return cls(policy_id, "WAIT", decision_id=decision_id)

    @classmethod
    def assign(cls, policy_id: str, vessel_id: str, berth_position_m: float,
               decision_id: str | None = None) -> "BerthAction":
        return cls(policy_id, "ASSIGN", vessel_id, berth_position_m, decision_id)


def _reject(kind: str, code: str, message: str) -> None:
    raise PhysicalActionRejected(code, message, decision_kind=kind)


def _check_pending(kernel, kind: str, action_decision_id: str | None, action_time: float | None) -> None:
    pending = kernel.state.pending
    if pending is None or pending.kind != kind:
        _reject(kind, STALE_ACTION, f"no pending {kind} decision (pending: "
                                    f"{None if pending is None else pending.kind})")
    if action_decision_id is not None and action_decision_id != pending.decision_id:
        _reject(kind, STALE_ACTION, f"action for decision {action_decision_id}, pending {pending.decision_id}")
    if action_time is not None and abs(action_time - kernel.state.now_min) > TIME_TOL:
        _reject(kind, STALE_ACTION, f"action time {action_time} != kernel time {kernel.state.now_min}")


# ---------------------------------------------------------------------------- berth

def occupying_placements(kernel) -> tuple[BAPPlacement, ...]:
    """Quay rectangles of every occupying vessel, ending at its current forecast release.

    Only positions and lengths matter for immediate-start legality: every
    occupying vessel covers ``now`` (its forecast release is asserted > now).
    """
    placements = []
    for vessel_id in kernel.state.reveal_order:
        v = kernel.state.vessels[vessel_id]
        if v.phase in ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP"):
            record = kernel.catalog.vessel_by_id[vessel_id]
            release = kernel.forecast_release(vessel_id)
            placements.append(BAPPlacement(vessel_id, v.berth_position_m, v.berth_start_time_min,
                                           record.length_m, release - v.berth_start_time_min))
    return tuple(placements)


def berth_position_rejection(kernel, vessel_id: str, position: float, *,
                             placements: tuple[BAPPlacement, ...] | None = None) -> tuple[str, str] | None:
    """Physical legality of starting ``vessel_id`` now at ``position`` (None if legal).

    Legality depends only on *actual* occupancy: the quay interval of every vessel
    that has not yet departed, plus clearance. A predicted end time never frees quay.
    """
    catalog, state = kernel.catalog, kernel.state
    record = catalog.vessel_by_id.get(vessel_id)
    vessel = state.vessels.get(vessel_id)
    if record is None or vessel is None or vessel.visibility == "HIDDEN":
        return UNKNOWN_VESSEL, f"vessel {vessel_id!r} is not a visible vessel"
    if vessel.phase != "WAITING":
        return VESSEL_NOT_WAITING, f"{vessel_id} is {vessel.phase}, not WAITING"
    if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position):
        return NON_FINITE_POSITION, f"position {position!r} is not finite"
    if not is_within_quay(float(position), record.length_m, catalog.berth_length_m):
        return POSITION_OUTSIDE_QUAY, f"{vessel_id} at {position} m leaves the quay [0, {catalog.berth_length_m}]"
    proposed = BAPPlacement(vessel_id, float(position), state.now_min, record.length_m,
                            record.nominal_service_time_min)
    for other in (occupying_placements(kernel) if placements is None else placements):
        if not are_spatially_separated(proposed, other, catalog.min_clearance_m):
            return BERTH_OCCUPIED, (f"{vessel_id} at {position} m overlaps {other.vessel_id} "
                                    f"[{other.berth_position_m}, {other.berth_end_position_m}] "
                                    f"with clearance {catalog.min_clearance_m} m")
    return None


def validate_berth_action(kernel, action: BerthAction) -> None:
    if not isinstance(action, BerthAction) or action.schema_version != BERTH_ACTION_SCHEMA:
        _reject("BERTH", INVALID_ACTION, f"expected a BerthAction, got {type(action).__name__}")
    _check_pending(kernel, "BERTH", action.decision_id, None)
    if action.action_type == "WAIT":
        if not kernel.berth_wait_legal():
            _reject("BERTH", WAIT_NOT_LEGAL, "WAIT needs a legal assignment and a visible future event "
                                             "(Project 03 rule)")
        return
    if action.action_type != "ASSIGN":
        _reject("BERTH", INVALID_ACTION, f"unknown berth action type {action.action_type!r}")
    problem = berth_position_rejection(kernel, action.vessel_id, action.berth_position_m)
    if problem is not None:
        _reject("BERTH", *problem)


# ---------------------------------------------------------------------------- crane

def validate_crane_action(kernel, action: CraneAction) -> None:
    if not isinstance(action, CraneAction):
        _reject("CRANE", INVALID_ACTION, f"expected a CraneAction, got {type(action).__name__}")
    _check_pending(kernel, "CRANE", action.decision_id, action.time_min)
    catalog, state = kernel.catalog, kernel.state
    held = kernel.crane_count_by_vessel()
    for crane_id in action.releases:
        crane = state.cranes.get(crane_id)
        if crane is None:
            _reject("CRANE", UNKNOWN_CRANE, f"unknown crane {crane_id}")
        if crane.assigned_vessel_id is None:
            _reject("CRANE", RELEASE_NOT_ASSIGNED, f"{crane_id} holds no vessel")
        if crane.current_work_order_id is not None:
            _reject("CRANE", RELEASE_DURING_BATCH, f"{crane_id} is inside batch {crane.current_work_order_id} "
                                                   "(non-preemptive, D08)")
        held[crane.assigned_vessel_id] = held.get(crane.assigned_vessel_id, 0) - 1
    for assignment in action.assignments:
        vessel_id = assignment.vessel_id
        record = catalog.vessel_by_id.get(vessel_id)
        vessel = state.vessels.get(vessel_id)
        if record is None or vessel is None:
            _reject("CRANE", UNKNOWN_VESSEL, f"unknown vessel {vessel_id}")
        if vessel.phase not in ("BERTHING_PREP", "HANDLING"):
            _reject("CRANE", VESSEL_NOT_SERVICEABLE, f"{vessel_id} is {vessel.phase}; cranes serve only "
                                                     "BERTHING_PREP/HANDLING vessels")
        if kernel.remaining_moves(vessel_id) <= 0:
            _reject("CRANE", NO_REMAINING_WORK, f"{vessel_id} has no remaining ship-side work")
        for crane_id in assignment.crane_ids:
            crane = state.cranes.get(crane_id)
            if crane is None:
                _reject("CRANE", UNKNOWN_CRANE, f"unknown crane {crane_id}")
            if crane.status != "available" or crane.assigned_vessel_id is not None:
                _reject("CRANE", CRANE_NOT_AVAILABLE, f"{crane_id} is {crane.status} "
                                                      f"(vessel {crane.assigned_vessel_id})")
            compatible = catalog.crane_by_id[crane_id].compatible_vessel_ids
            if compatible is not None and vessel_id not in compatible:
                _reject("CRANE", CRANE_INCOMPATIBLE, f"{crane_id} cannot serve {vessel_id}")
        total = held.get(vessel_id, 0) + len(assignment.crane_ids)
        if total > record.max_cranes:
            _reject("CRANE", MAX_CRANES_EXCEEDED, f"{vessel_id} would hold {total} > max_cranes "
                                                  f"{record.max_cranes}")
        held[vessel_id] = total


# ---------------------------------------------------------------------------- yard

def validate_yard_action(kernel, action: YardAction) -> None:
    if not isinstance(action, YardAction):
        _reject("YARD", INVALID_ACTION, f"expected a YardAction, got {type(action).__name__}")
    _check_pending(kernel, "YARD", action.decision_id, action.time_min)
    catalog, state = kernel.catalog, kernel.state
    request = kernel.pending_yard_request()
    if action.work_order_id != request.work_order_id:
        _reject("YARD", STALE_ACTION, f"action for {action.work_order_id}, pending {request.work_order_id}")
    expected_ids = tuple(catalog.containers[i].container_id for i in request.container_indices)
    if action.container_ids != expected_ids:
        _reject("YARD", CONTAINER_SET_MISMATCH, f"action names {action.container_ids[:5]}..., request "
                                                f"{expected_ids[:5]}... (exact membership required)")
    required = float(sum(catalog.containers[i].size_teu for i in request.container_indices))
    if abs(action.required_teu - required) > 1e-9:
        _reject("YARD", REQUIRED_TEU_MISMATCH, f"required_teu {action.required_teu} != {required}")
    source_status = "ABOARD_ARRIVED_VESSEL" if request.operation_type == "DISCHARGE" else "AT_GATE"
    source_kind = "VESSEL" if request.operation_type == "DISCHARGE" else "GATE"
    for i in request.container_indices:
        if (state.c_status[i] != source_status or state.c_loc_kind[i] != source_kind
                or state.c_loc_id[i] != request.source_location_id or state.c_claim[i] is not None):
            _reject("YARD", UNAVAILABLE_SOURCE_INVENTORY,
                    f"{catalog.containers[i].container_id} is {state.c_status[i]} at "
                    f"{state.c_loc_kind[i]}/{state.c_loc_id[i]} (claimed by {state.c_claim[i]})")
    if action.action_type == "NO_ACTION":
        return
    block_record = catalog.block_by_id.get(action.block_id)
    if block_record is None:
        _reject("YARD", UNKNOWN_BLOCK, f"unknown block {action.block_id}")
    block = state.blocks[action.block_id]
    if block.status != "open":
        _reject("YARD", BLOCK_NOT_OPEN, f"{action.block_id} is {block.status}")
    first = catalog.containers[request.container_indices[0]]
    if first.container_size not in block_record.allowed_sizes:
        _reject("YARD", SIZE_NOT_ALLOWED, f"{action.block_id} does not accept {first.container_size}")
    if not first.required_capabilities <= block_record.capabilities:
        _reject("YARD", CAPABILITY_MISMATCH, f"{action.block_id} lacks {sorted(first.required_capabilities)}")
    available = block_record.capacity_teu - block.occupied_teu - block.reserved_teu - block.blocked_teu
    if available + 1e-9 < required:
        _reject("YARD", MISSING_DESTINATION_CAPACITY,
                f"{action.block_id} has {available} TEU available, batch needs {required} (DQ14)")


__all__ = [
    "BERTH_ACTION_SCHEMA", "BerthAction", "REJECTION_CODES", "berth_position_rejection",
    "occupying_placements", "validate_berth_action", "validate_crane_action", "validate_yard_action",
]
