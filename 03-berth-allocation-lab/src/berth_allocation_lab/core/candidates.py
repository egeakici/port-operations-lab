"""Finite boundary candidates over continuous quay geometry."""

from __future__ import annotations

from typing import Sequence

from berth_allocation_lab.core.feasibility import is_valid_vessel_input
from berth_allocation_lab.core.numerics import (
    NUMERICAL_TOLERANCE,
    is_finite_number,
)
from berth_allocation_lab.core.types import BAPPlacement
from berth_allocation_lab.data import BAPVesselInput


def candidate_positions(
    vessel: BAPVesselInput,
    existing_placements: Sequence[BAPPlacement],
    berth_length_m: float,
    min_clearance_m: float,
) -> tuple[float, ...]:
    """Return sorted in-bounds boundary positions in meters.

    Candidates come from quay boundaries and both clearance-adjusted sides of
    existing placements. They are an encoding for candidate-based consumers,
    not a discretization or definition of the continuous physical problem.
    """

    if not is_valid_vessel_input(vessel):
        raise ValueError("Vessel has invalid physical input.")
    if not is_finite_number(berth_length_m) or berth_length_m <= 0.0:
        raise ValueError("Berth length must be a finite positive number.")
    if not is_finite_number(min_clearance_m) or min_clearance_m < 0.0:
        raise ValueError("Minimum clearance must be finite and non-negative.")
    if vessel.length_m > berth_length_m + NUMERICAL_TOLERANCE:
        raise ValueError("Vessel length exceeds berth length.")
    if any(
        not isinstance(placement, BAPPlacement)
        for placement in existing_placements
    ):
        raise TypeError("Existing placements must be BAPPlacement instances.")

    max_position = max(0.0, berth_length_m - vessel.length_m)
    raw_candidates = [0.0, max_position]
    for placement in existing_placements:
        raw_candidates.extend(
            (
                placement.berth_end_position_m + min_clearance_m,
                placement.berth_position_m
                - min_clearance_m
                - vessel.length_m,
            )
        )

    in_bounds = sorted(
        _snap_to_quay_boundary(position, max_position)
        for position in raw_candidates
        if (
            position >= -NUMERICAL_TOLERANCE
            and position <= max_position + NUMERICAL_TOLERANCE
        )
    )
    deduplicated: list[float] = []
    for position in in_bounds:
        if (
            not deduplicated
            or position - deduplicated[-1] > NUMERICAL_TOLERANCE
        ):
            deduplicated.append(position)
    return tuple(deduplicated)


def _snap_to_quay_boundary(position: float, max_position: float) -> float:
    if abs(position) <= NUMERICAL_TOLERANCE:
        return 0.0
    if abs(position - max_position) <= NUMERICAL_TOLERANCE:
        return max_position
    return float(position)

