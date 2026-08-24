from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mini_port_sim.metrics.collector import SimulationMetrics


def metrics_summary(metrics: SimulationMetrics) -> dict[str, Any]:
    return {
        "scenario_id": metrics.scenario_id,
        "seed": metrics.seed,
        "duration_hours": metrics.duration_minutes / 60.0,
        "completed_vessels": metrics.completed_vessel_count,
        "unfinished_vessels": metrics.unfinished_vessel_count,
        "throughput_vessels_per_day": metrics.throughput_vessels_per_day,
        "average_waiting_hours": _minutes_to_hours(
            metrics.average_waiting_time_minutes
        ),
        "median_waiting_hours": _minutes_to_hours(
            metrics.median_waiting_time_minutes
        ),
        "p95_waiting_hours": _minutes_to_hours(
            metrics.p95_waiting_time_minutes
        ),
        "waiting_vessels_at_end": metrics.waiting_vessel_count_at_end,
        "average_current_wait_age_hours": _minutes_to_hours(
            metrics.average_current_wait_age_minutes
        ),
        "max_current_wait_age_hours": _minutes_to_hours(
            metrics.max_current_wait_age_minutes
        ),
        "average_turnaround_hours": _minutes_to_hours(
            metrics.average_turnaround_time_minutes
        ),
        "p95_turnaround_hours": _minutes_to_hours(
            metrics.p95_turnaround_time_minutes
        ),
        "max_queue_length": metrics.max_queue_length,
        "berth_utilization": metrics.berth_utilization,
        "crane_utilization": metrics.crane_utilization,
        "crane_idle_hours": metrics.crane_idle_minutes / 60.0,
        "crane_downtime_hours": metrics.crane_downtime_minutes / 60.0,
        "crane_failure_count": metrics.crane_failure_count,
        "average_crane_downtime_hours": _minutes_to_hours(
            metrics.average_crane_downtime_minutes
        ),
        "final_yard_utilization": metrics.final_yard_utilization,
        "average_yard_utilization": metrics.average_yard_utilization,
        "peak_yard_utilization": metrics.peak_yard_utilization,
        "yard_capacity_rejection_count": (
            metrics.yard_capacity_rejection_count
        ),
        "total_handled_moves": metrics.total_handled_moves,
    }


def save_metrics_json(
    metrics: SimulationMetrics,
    file_path: str | Path,
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(metrics.to_dict(), file, ensure_ascii=False, indent=2)


def _minutes_to_hours(value: float | None) -> float | None:
    if value is None:
        return None

    return value / 60.0
