"""Placement and complete-schedule feasibility checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from berth_allocation_lab.core.geometry import (
    is_within_quay,
    space_time_conflict,
)
from berth_allocation_lab.core.numerics import (
    NUMERICAL_TOLERANCE,
    is_close,
    is_finite_number,
)
from berth_allocation_lab.core.types import BAPPlacement
from berth_allocation_lab.data import BAPVesselInput


class ScheduleViolationCode(str, Enum):
    """Stable diagnostic codes for invalid BAP schedules."""

    INVALID_VESSEL_INPUT = "invalid_vessel_input"
    DUPLICATE_VESSEL_ID = "duplicate_vessel_id"
    DUPLICATE_PLACEMENT = "duplicate_placement"
    MISSING_PLACEMENT = "missing_placement"
    UNKNOWN_VESSEL = "unknown_vessel"
    VESSEL_MISMATCH = "vessel_mismatch"
    OUT_OF_BOUNDS = "out_of_bounds"
    BEFORE_ARRIVAL = "before_arrival"
    SPACE_TIME_CONFLICT = "space_time_conflict"


@dataclass(frozen=True)
class ScheduleViolation:
    """A concise physical or completeness violation in a BAP schedule."""

    code: ScheduleViolationCode
    vessel_ids: tuple[str, ...]
    message: str


def is_valid_vessel_input(vessel: BAPVesselInput) -> bool:
    """Return whether canonical vessel physics are finite and positive."""

    return (
        isinstance(vessel, BAPVesselInput)
        and isinstance(vessel.vessel_id, str)
        and bool(vessel.vessel_id.strip())
        and is_finite_number(vessel.arrival_time_min)
        and vessel.arrival_time_min >= 0.0
        and is_finite_number(vessel.length_m)
        and vessel.length_m > 0.0
        and is_finite_number(vessel.service_time_min)
        and vessel.service_time_min > 0.0
    )


def is_arrival_feasible(
    vessel: BAPVesselInput,
    berth_start_time_min: float,
) -> bool:
    """Return whether service starts no earlier than vessel arrival."""

    return (
        is_valid_vessel_input(vessel)
        and is_finite_number(berth_start_time_min)
        and berth_start_time_min + NUMERICAL_TOLERANCE
        >= vessel.arrival_time_min
    )


def is_placement_feasible(
    vessel: BAPVesselInput,
    berth_position_m: float,
    berth_start_time_min: float,
    existing_placements: Sequence[BAPPlacement],
    berth_length_m: float,
    min_clearance_m: float,
) -> bool:
    """Check one proposed placement without mutating or rescheduling it."""

    if not is_valid_vessel_input(vessel):
        return False
    if not is_finite_number(min_clearance_m) or min_clearance_m < 0.0:
        return False
    if not is_within_quay(
        berth_position_m,
        vessel.length_m,
        berth_length_m,
    ):
        return False
    if not is_arrival_feasible(vessel, berth_start_time_min):
        return False

    try:
        proposed = BAPPlacement(
            vessel_id=vessel.vessel_id,
            berth_position_m=berth_position_m,
            berth_start_time_min=berth_start_time_min,
            length_m=vessel.length_m,
            service_time_min=vessel.service_time_min,
        )
    except ValueError:
        return False

    for existing in existing_placements:
        if not isinstance(existing, BAPPlacement):
            return False
        if existing.vessel_id == vessel.vessel_id:
            return False
        if space_time_conflict(proposed, existing, min_clearance_m):
            return False
    return True


def find_schedule_violations(
    vessels: Sequence[BAPVesselInput],
    placements: Sequence[BAPPlacement],
    berth_length_m: float,
    min_clearance_m: float,
    *,
    require_complete: bool = True,
) -> tuple[ScheduleViolation, ...]:
    """Return deterministic diagnostics for a full or partial BAP schedule."""

    if not is_finite_number(berth_length_m) or berth_length_m <= 0.0:
        raise ValueError("Berth length must be a finite positive number.")
    if not is_finite_number(min_clearance_m) or min_clearance_m < 0.0:
        raise ValueError("Minimum clearance must be finite and non-negative.")

    violations: list[ScheduleViolation] = []
    vessel_by_id: dict[str, BAPVesselInput] = {}
    duplicate_vessel_ids: set[str] = set()
    for vessel in vessels:
        if not is_valid_vessel_input(vessel):
            vessel_id = getattr(vessel, "vessel_id", "<invalid>")
            violations.append(
                ScheduleViolation(
                    ScheduleViolationCode.INVALID_VESSEL_INPUT,
                    (str(vessel_id),),
                    f"Vessel {vessel_id} has invalid physical input.",
                )
            )
            continue
        if vessel.vessel_id in vessel_by_id:
            duplicate_vessel_ids.add(vessel.vessel_id)
        else:
            vessel_by_id[vessel.vessel_id] = vessel

    for vessel_id in sorted(duplicate_vessel_ids):
        violations.append(
            ScheduleViolation(
                ScheduleViolationCode.DUPLICATE_VESSEL_ID,
                (vessel_id,),
                f"Vessel input ID {vessel_id} occurs more than once.",
            )
        )

    placement_counts: dict[str, int] = {}
    for placement in placements:
        placement_counts[placement.vessel_id] = (
            placement_counts.get(placement.vessel_id, 0) + 1
        )
        vessel = vessel_by_id.get(placement.vessel_id)
        if vessel is None:
            violations.append(
                ScheduleViolation(
                    ScheduleViolationCode.UNKNOWN_VESSEL,
                    (placement.vessel_id,),
                    f"Placement references unknown vessel {placement.vessel_id}.",
                )
            )
            continue
        if not (
            is_close(placement.length_m, vessel.length_m)
            and is_close(placement.service_time_min, vessel.service_time_min)
        ):
            violations.append(
                ScheduleViolation(
                    ScheduleViolationCode.VESSEL_MISMATCH,
                    (placement.vessel_id,),
                    f"Placement dimensions do not match vessel {placement.vessel_id}.",
                )
            )
        if not is_within_quay(
            placement.berth_position_m,
            placement.length_m,
            berth_length_m,
        ):
            violations.append(
                ScheduleViolation(
                    ScheduleViolationCode.OUT_OF_BOUNDS,
                    (placement.vessel_id,),
                    f"Placement for {placement.vessel_id} is outside the quay.",
                )
            )
        if not is_arrival_feasible(vessel, placement.berth_start_time_min):
            violations.append(
                ScheduleViolation(
                    ScheduleViolationCode.BEFORE_ARRIVAL,
                    (placement.vessel_id,),
                    f"Placement for {placement.vessel_id} starts before arrival.",
                )
            )

    for vessel_id in sorted(placement_counts):
        if placement_counts[vessel_id] > 1:
            violations.append(
                ScheduleViolation(
                    ScheduleViolationCode.DUPLICATE_PLACEMENT,
                    (vessel_id,),
                    f"Vessel {vessel_id} has more than one placement.",
                )
            )

    if require_complete:
        for vessel_id in sorted(vessel_by_id):
            if placement_counts.get(vessel_id, 0) == 0:
                violations.append(
                    ScheduleViolation(
                        ScheduleViolationCode.MISSING_PLACEMENT,
                        (vessel_id,),
                        f"Vessel {vessel_id} has no placement.",
                    )
                )

    for index, left in enumerate(placements):
        for right in placements[index + 1 :]:
            if space_time_conflict(left, right, min_clearance_m):
                vessel_ids = tuple(sorted((left.vessel_id, right.vessel_id)))
                violations.append(
                    ScheduleViolation(
                        ScheduleViolationCode.SPACE_TIME_CONFLICT,
                        vessel_ids,
                        f"Placements {vessel_ids[0]} and {vessel_ids[1]} conflict.",
                    )
                )

    return tuple(violations)


def is_schedule_feasible(
    vessels: Sequence[BAPVesselInput],
    placements: Sequence[BAPPlacement],
    berth_length_m: float,
    min_clearance_m: float,
    *,
    require_complete: bool = True,
) -> bool:
    """Return whether a BAP schedule has no reported violations."""

    return not find_schedule_violations(
        vessels,
        placements,
        berth_length_m,
        min_clearance_m,
        require_complete=require_complete,
    )

