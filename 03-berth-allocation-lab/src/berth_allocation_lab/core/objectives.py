"""Pure Project 03 v1 waiting and turnaround objectives."""

from __future__ import annotations

from typing import Sequence

from berth_allocation_lab.core.feasibility import (
    is_arrival_feasible,
    is_valid_vessel_input,
)
from berth_allocation_lab.core.numerics import (
    NUMERICAL_TOLERANCE,
    is_close,
)
from berth_allocation_lab.core.types import BAPPlacement
from berth_allocation_lab.data import BAPVesselInput


def waiting_time(
    vessel: BAPVesselInput,
    placement: BAPPlacement,
) -> float:
    """Return vessel waiting time in minutes for a matching valid placement."""

    _validate_pair(vessel, placement)
    waiting = placement.berth_start_time_min - vessel.arrival_time_min
    return 0.0 if abs(waiting) <= NUMERICAL_TOLERANCE else waiting


def turnaround_time(
    vessel: BAPVesselInput,
    placement: BAPPlacement,
) -> float:
    """Return arrival-to-service-completion time in minutes."""

    _validate_pair(vessel, placement)
    return placement.service_end_time_min - vessel.arrival_time_min


def total_waiting_time(
    vessels: Sequence[BAPVesselInput],
    placements: Sequence[BAPPlacement],
) -> float:
    """Return total waiting for a complete one-placement-per-vessel schedule.

    Missing, duplicate, unknown, mismatched, or pre-arrival placements raise
    ``ValueError`` instead of being omitted from the objective.
    """

    vessel_by_id = _unique_vessels_by_id(vessels)
    placement_by_id = _unique_placements_by_id(placements)
    missing = sorted(set(vessel_by_id) - set(placement_by_id))
    unknown = sorted(set(placement_by_id) - set(vessel_by_id))
    if missing:
        raise ValueError(f"Missing placements for vessels: {', '.join(missing)}.")
    if unknown:
        raise ValueError(f"Placements reference unknown vessels: {', '.join(unknown)}.")
    return sum(
        waiting_time(vessel, placement_by_id[vessel_id])
        for vessel_id, vessel in vessel_by_id.items()
    )


def _validate_pair(
    vessel: BAPVesselInput,
    placement: BAPPlacement,
) -> None:
    if not is_valid_vessel_input(vessel):
        raise ValueError("Vessel has invalid physical input.")
    if not isinstance(placement, BAPPlacement):
        raise TypeError("Placement must be a BAPPlacement.")
    if vessel.vessel_id != placement.vessel_id:
        raise ValueError("Vessel and placement IDs do not match.")
    if not (
        is_close(vessel.length_m, placement.length_m)
        and is_close(vessel.service_time_min, placement.service_time_min)
    ):
        raise ValueError("Vessel and placement physical values do not match.")
    if not is_arrival_feasible(vessel, placement.berth_start_time_min):
        raise ValueError("Placement starts before vessel arrival.")


def _unique_vessels_by_id(
    vessels: Sequence[BAPVesselInput],
) -> dict[str, BAPVesselInput]:
    by_id: dict[str, BAPVesselInput] = {}
    for vessel in vessels:
        if vessel.vessel_id in by_id:
            raise ValueError(
                f"Duplicate vessel input for vessel {vessel.vessel_id}."
            )
        by_id[vessel.vessel_id] = vessel
    return by_id


def _unique_placements_by_id(
    placements: Sequence[BAPPlacement],
) -> dict[str, BAPPlacement]:
    by_id: dict[str, BAPPlacement] = {}
    for placement in placements:
        if placement.vessel_id in by_id:
            raise ValueError(
                f"Duplicate placement for vessel {placement.vessel_id}."
            )
        by_id[placement.vessel_id] = placement
    return by_id

