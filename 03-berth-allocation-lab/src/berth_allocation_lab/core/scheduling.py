"""Continuous-time scheduling helpers."""

from __future__ import annotations

from typing import Sequence

from berth_allocation_lab.core.feasibility import is_valid_vessel_input
from berth_allocation_lab.core.geometry import (
    are_spatially_separated,
    is_within_quay,
    time_intervals_overlap,
)
from berth_allocation_lab.core.numerics import is_finite_number
from berth_allocation_lab.core.types import BAPPlacement
from berth_allocation_lab.data import BAPVesselInput


def earliest_feasible_start(
    vessel: BAPVesselInput,
    berth_position_m: float,
    existing_placements: Sequence[BAPPlacement],
    berth_length_m: float,
    min_clearance_m: float,
) -> float:
    """Return the earliest feasible minute at one fixed berth position.

    The search starts at arrival and jumps directly to conflicting service-end
    events. Existing placements are assumed to form an internally valid partial
    schedule; their input order does not affect the result.
    """

    if not is_valid_vessel_input(vessel):
        raise ValueError("Vessel has invalid physical input.")
    if not is_finite_number(min_clearance_m) or min_clearance_m < 0.0:
        raise ValueError("Minimum clearance must be finite and non-negative.")
    if not is_within_quay(
        berth_position_m,
        vessel.length_m,
        berth_length_m,
    ):
        raise ValueError("Vessel does not fit at the requested berth position.")
    if any(
        not isinstance(placement, BAPPlacement)
        for placement in existing_placements
    ):
        raise TypeError("Existing placements must be BAPPlacement instances.")
    if any(
        placement.vessel_id == vessel.vessel_id
        for placement in existing_placements
    ):
        raise ValueError(f"Vessel {vessel.vessel_id} is already placed.")

    footprint = BAPPlacement(
        vessel_id=vessel.vessel_id,
        berth_position_m=berth_position_m,
        berth_start_time_min=vessel.arrival_time_min,
        length_m=vessel.length_m,
        service_time_min=vessel.service_time_min,
    )
    spatial_blockers = tuple(
        placement
        for placement in existing_placements
        if not are_spatially_separated(
            footprint,
            placement,
            min_clearance_m,
        )
    )

    start_time = float(vessel.arrival_time_min)
    while True:
        end_time = start_time + vessel.service_time_min
        conflicts = tuple(
            placement
            for placement in spatial_blockers
            if time_intervals_overlap(
                start_time,
                end_time,
                placement.berth_start_time_min,
                placement.service_end_time_min,
            )
        )
        if not conflicts:
            return start_time
        start_time = min(
            placement.service_end_time_min for placement in conflicts
        )

