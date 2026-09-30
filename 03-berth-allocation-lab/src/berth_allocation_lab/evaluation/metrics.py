"""Policy-independent KPIs for complete static schedules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from berth_allocation_lab.core import (
    BAPPlacement,
    NUMERICAL_TOLERANCE,
    is_schedule_feasible,
    total_waiting_time,
    turnaround_time,
    waiting_time,
)
from berth_allocation_lab.core.numerics import is_finite_number
from berth_allocation_lab.data import BAPScenarioInstance


METRIC_VERSION = "static_metrics_v1_type7"
PERCENTILE_METHOD = "type7_linear"


@dataclass(frozen=True)
class StaticMetrics:
    total_waiting_time_min: float
    mean_waiting_time_min: float
    p95_waiting_time_min: float
    mean_turnaround_time_min: float
    p95_turnaround_time_min: float
    berth_utilization: float
    occupied_quay_length_minutes: float
    utilization_window_min: float
    throughput_vessels: int
    schedule_end_time_min: float
    objective_value: float


def percentile_type7(values: Sequence[float], percentile: float) -> float:
    """Return linear Type-7 percentile; p lies in [0, 1]."""

    if not values:
        raise ValueError("Percentile requires at least one value.")
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("Percentile must lie in [0, 1].")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def schedule_end_time(placements: Sequence[BAPPlacement]) -> float:
    """Return latest service completion minute, or zero for empty input."""

    return max((p.service_end_time_min for p in placements), default=0.0)


def berth_utilization_from_components(
    occupied_quay_length_minutes: float,
    berth_length_m: float,
    utilization_window_min: float,
) -> float:
    """Return physical utilization; reject an excess beyond numeric noise."""

    if not all(
        is_finite_number(value)
        for value in (
            occupied_quay_length_minutes,
            berth_length_m,
            utilization_window_min,
        )
    ):
        raise ValueError("Utilization components must be finite numbers.")
    if occupied_quay_length_minutes < 0 or berth_length_m <= 0 or utilization_window_min <= 0:
        raise ValueError("Utilization requires non-negative area and positive dimensions.")
    utilization = occupied_quay_length_minutes / (
        berth_length_m * utilization_window_min
    )
    if not is_finite_number(utilization) or utilization > 1.0 + NUMERICAL_TOLERANCE:
        raise ValueError("Berth utilization exceeds physical quay-time capacity.")
    return 1.0 if utilization > 1.0 else utilization


def calculate_static_metrics(
    scenario: BAPScenarioInstance,
    placements: Sequence[BAPPlacement],
) -> StaticMetrics:
    """Calculate v1 KPIs for a complete, physically valid static schedule.

    Utilization uses [0, last service completion] and hull length-minutes.
    No unresolved or invalid schedule can produce a benchmark metric row.
    """

    if scenario.formulation != "static":
        raise ValueError("Static metrics require a static scenario.")
    if not scenario.vessels:
        raise ValueError("Static metrics require at least one vessel.")
    if not is_schedule_feasible(
        scenario.vessels,
        placements,
        scenario.berth_length_m,
        scenario.min_clearance_m,
    ):
        raise ValueError("Static metrics require a valid complete schedule.")

    by_id = {placement.vessel_id: placement for placement in placements}
    waits = [waiting_time(v, by_id[v.vessel_id]) for v in scenario.vessels]
    turns = [turnaround_time(v, by_id[v.vessel_id]) for v in scenario.vessels]
    total_wait = total_waiting_time(scenario.vessels, placements)
    end = schedule_end_time(placements)
    occupied_length_minutes = sum(
        placement.length_m * placement.service_time_min
        for placement in placements
    )
    utilization_window_min = end
    utilization = berth_utilization_from_components(
        occupied_length_minutes,
        scenario.berth_length_m,
        utilization_window_min,
    )
    count = len(scenario.vessels)
    return StaticMetrics(
        total_waiting_time_min=total_wait,
        mean_waiting_time_min=total_wait / count,
        p95_waiting_time_min=percentile_type7(waits, 0.95),
        mean_turnaround_time_min=sum(turns) / count,
        p95_turnaround_time_min=percentile_type7(turns, 0.95),
        berth_utilization=utilization,
        occupied_quay_length_minutes=occupied_length_minutes,
        utilization_window_min=utilization_window_min,
        throughput_vessels=count,
        schedule_end_time_min=end,
        objective_value=total_wait,
    )
