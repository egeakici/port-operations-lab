"""Shared physical and mathematical core for continuous berth allocation."""

from berth_allocation_lab.core.candidates import candidate_positions
from berth_allocation_lab.core.feasibility import (
    ScheduleViolation,
    ScheduleViolationCode,
    find_schedule_violations,
    is_arrival_feasible,
    is_placement_feasible,
    is_schedule_feasible,
    is_valid_vessel_input,
)
from berth_allocation_lab.core.geometry import (
    are_spatially_separated,
    is_within_quay,
    space_time_conflict,
    time_intervals_overlap,
)
from berth_allocation_lab.core.numerics import NUMERICAL_TOLERANCE
from berth_allocation_lab.core.objectives import (
    total_waiting_time,
    turnaround_time,
    waiting_time,
)
from berth_allocation_lab.core.scheduling import earliest_feasible_start
from berth_allocation_lab.core.types import BAPPlacement


__all__ = [
    "BAPPlacement",
    "NUMERICAL_TOLERANCE",
    "ScheduleViolation",
    "ScheduleViolationCode",
    "are_spatially_separated",
    "candidate_positions",
    "earliest_feasible_start",
    "find_schedule_violations",
    "is_arrival_feasible",
    "is_placement_feasible",
    "is_schedule_feasible",
    "is_valid_vessel_input",
    "is_within_quay",
    "space_time_conflict",
    "time_intervals_overlap",
    "total_waiting_time",
    "turnaround_time",
    "waiting_time",
]

