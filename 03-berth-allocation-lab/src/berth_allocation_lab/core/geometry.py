"""Continuous quay, time-interval, and clearance geometry."""

from __future__ import annotations

from berth_allocation_lab.core.numerics import (
    NUMERICAL_TOLERANCE,
    is_finite_number,
)
from berth_allocation_lab.core.types import BAPPlacement


def is_within_quay(
    berth_position_m: float,
    vessel_length_m: float,
    berth_length_m: float,
) -> bool:
    """Return whether a vessel footprint lies in ``[0, berth_length_m]``.

    All distances are meters. No clearance is required from quay boundaries.
    Invalid or non-finite dimensions are infeasible and are never clamped.
    """

    if not all(
        is_finite_number(value)
        for value in (berth_position_m, vessel_length_m, berth_length_m)
    ):
        return False
    if vessel_length_m <= 0.0 or berth_length_m <= 0.0:
        return False
    return (
        berth_position_m >= -NUMERICAL_TOLERANCE
        and berth_position_m + vessel_length_m
        <= berth_length_m + NUMERICAL_TOLERANCE
    )


def time_intervals_overlap(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> bool:
    """Return whether two positive half-open minute intervals overlap.

    Endpoint contact is not overlap. Intersections no larger than the shared
    numerical tolerance are treated as floating-point noise.
    """

    _validate_time_interval(start_a, end_a, "A")
    _validate_time_interval(start_b, end_b, "B")
    overlap = min(end_a, end_b) - max(start_a, start_b)
    return overlap > NUMERICAL_TOLERANCE


def are_spatially_separated(
    placement_a: BAPPlacement,
    placement_b: BAPPlacement,
    min_clearance_m: float,
) -> bool:
    """Return whether two vessel footprints have the required meter gap.

    Clearance is added once between hull intervals, never at quay boundaries.
    """

    _validate_clearance(min_clearance_m)
    a_left_of_b = (
        placement_a.berth_end_position_m + min_clearance_m
        <= placement_b.berth_position_m + NUMERICAL_TOLERANCE
    )
    b_left_of_a = (
        placement_b.berth_end_position_m + min_clearance_m
        <= placement_a.berth_position_m + NUMERICAL_TOLERANCE
    )
    return a_left_of_b or b_left_of_a


def space_time_conflict(
    placement_a: BAPPlacement,
    placement_b: BAPPlacement,
    min_clearance_m: float,
) -> bool:
    """Return whether placements conflict in both time and berth space."""

    return time_intervals_overlap(
        placement_a.berth_start_time_min,
        placement_a.service_end_time_min,
        placement_b.berth_start_time_min,
        placement_b.service_end_time_min,
    ) and not are_spatially_separated(
        placement_a,
        placement_b,
        min_clearance_m,
    )


def _validate_time_interval(start: float, end: float, label: str) -> None:
    if not is_finite_number(start) or not is_finite_number(end):
        raise ValueError(f"Time interval {label} must contain finite values.")
    if end <= start:
        raise ValueError(f"Time interval {label} must have positive duration.")


def _validate_clearance(min_clearance_m: float) -> None:
    if not is_finite_number(min_clearance_m) or min_clearance_m < 0.0:
        raise ValueError("Minimum clearance must be a finite non-negative number.")

