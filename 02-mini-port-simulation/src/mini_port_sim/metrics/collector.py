from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import TYPE_CHECKING, Any

from terminal_core import TerminalEventType

if TYPE_CHECKING:
    from mini_port_sim.simulation import PortSimulation


@dataclass(frozen=True)
class VesselMetrics:
    vessel_id: str
    arrival_time_minutes: float
    berth_time_minutes: float | None
    operation_start_minutes: float | None
    operation_end_minutes: float | None
    departure_time_minutes: float | None
    waiting_time_minutes: float | None
    turnaround_time_minutes: float | None
    eta_deviation_minutes: float | None

    def to_dict(self) -> dict[str, float | str | None]:
        return {
            "vessel_id": self.vessel_id,
            "arrival_time_minutes": self.arrival_time_minutes,
            "berth_time_minutes": self.berth_time_minutes,
            "operation_start_minutes": self.operation_start_minutes,
            "operation_end_minutes": self.operation_end_minutes,
            "departure_time_minutes": self.departure_time_minutes,
            "waiting_time_minutes": self.waiting_time_minutes,
            "turnaround_time_minutes": self.turnaround_time_minutes,
            "eta_deviation_minutes": self.eta_deviation_minutes,
        }


@dataclass(frozen=True)
class SimulationMetrics:
    scenario_id: str | None
    seed: int | None
    duration_minutes: float
    vessel_metrics: tuple[VesselMetrics, ...]
    completed_vessel_count: int
    unfinished_vessel_count: int
    total_handled_moves: float
    average_waiting_time_minutes: float | None
    median_waiting_time_minutes: float | None
    p95_waiting_time_minutes: float | None
    waiting_vessel_count_at_end: int
    average_current_wait_age_minutes: float | None
    max_current_wait_age_minutes: float | None
    average_turnaround_time_minutes: float | None
    p95_turnaround_time_minutes: float | None
    throughput_vessels_per_day: float
    max_queue_length: int
    berth_utilization: float
    crane_utilization: float
    crane_idle_minutes: float
    crane_downtime_minutes: float
    crane_failure_count: int
    average_crane_downtime_minutes: float | None
    final_yard_utilization: float
    average_yard_utilization: float
    peak_yard_utilization: float
    yard_capacity_rejection_count: int
    event_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "seed": self.seed,
            "duration_minutes": self.duration_minutes,
            "vessel_metrics": [
                metrics.to_dict() for metrics in self.vessel_metrics
            ],
            "completed_vessel_count": self.completed_vessel_count,
            "unfinished_vessel_count": self.unfinished_vessel_count,
            "total_handled_moves": self.total_handled_moves,
            "average_waiting_time_minutes": (
                self.average_waiting_time_minutes
            ),
            "median_waiting_time_minutes": (
                self.median_waiting_time_minutes
            ),
            "p95_waiting_time_minutes": self.p95_waiting_time_minutes,
            "waiting_vessel_count_at_end": self.waiting_vessel_count_at_end,
            "average_current_wait_age_minutes": (
                self.average_current_wait_age_minutes
            ),
            "max_current_wait_age_minutes": self.max_current_wait_age_minutes,
            "average_turnaround_time_minutes": (
                self.average_turnaround_time_minutes
            ),
            "p95_turnaround_time_minutes": (
                self.p95_turnaround_time_minutes
            ),
            "throughput_vessels_per_day": self.throughput_vessels_per_day,
            "max_queue_length": self.max_queue_length,
            "berth_utilization": self.berth_utilization,
            "crane_utilization": self.crane_utilization,
            "crane_idle_minutes": self.crane_idle_minutes,
            "crane_downtime_minutes": self.crane_downtime_minutes,
            "crane_failure_count": self.crane_failure_count,
            "average_crane_downtime_minutes": (
                self.average_crane_downtime_minutes
            ),
            "final_yard_utilization": self.final_yard_utilization,
            "average_yard_utilization": self.average_yard_utilization,
            "peak_yard_utilization": self.peak_yard_utilization,
            "yard_capacity_rejection_count": (
                self.yard_capacity_rejection_count
            ),
            "event_count": self.event_count,
        }

    @property
    def yard_utilization(self) -> float:
        return self.final_yard_utilization


def collect_metrics(simulation: "PortSimulation") -> SimulationMetrics:
    vessel_metrics = _collect_vessel_metrics(simulation)
    waiting_times = _known(
        metrics.waiting_time_minutes for metrics in vessel_metrics
    )
    current_wait_ages = _current_wait_ages(vessel_metrics, simulation)
    turnaround_times = _known(
        metrics.turnaround_time_minutes for metrics in vessel_metrics
    )
    duration = max(simulation.elapsed_minutes, 0.0)
    completed_vessel_ids = set(simulation.completed_vessel_ids)
    crane_operating_minutes = _crane_operating_minutes(simulation, duration)
    crane_downtime_intervals = _crane_downtime_intervals(
        simulation,
        duration,
    )
    crane_downtime = sum(
        end - start for _, start, end in crane_downtime_intervals
    )
    total_crane_minutes = simulation.terminal.quay_crane_count * duration
    yard_stats = _yard_utilization_stats(simulation, duration)

    return SimulationMetrics(
        scenario_id=(
            simulation.scenario.scenario_id
            if simulation.scenario is not None
            else None
        ),
        seed=simulation.seed,
        duration_minutes=duration,
        vessel_metrics=vessel_metrics,
        completed_vessel_count=len(completed_vessel_ids),
        unfinished_vessel_count=max(
            0,
            simulation.terminal.vessel_count - len(completed_vessel_ids),
        ),
        total_handled_moves=_total_handled_moves(simulation),
        average_waiting_time_minutes=_average(waiting_times),
        median_waiting_time_minutes=_median(waiting_times),
        p95_waiting_time_minutes=_percentile(waiting_times, 95),
        waiting_vessel_count_at_end=len(current_wait_ages),
        average_current_wait_age_minutes=_average(current_wait_ages),
        max_current_wait_age_minutes=(
            max(current_wait_ages) if current_wait_ages else None
        ),
        average_turnaround_time_minutes=_average(turnaround_times),
        p95_turnaround_time_minutes=_percentile(turnaround_times, 95),
        throughput_vessels_per_day=(
            len(completed_vessel_ids) / (duration / 1440.0)
            if duration > 0
            else 0.0
        ),
        max_queue_length=_max_queue_length(simulation),
        berth_utilization=_berth_utilization(simulation, duration),
        crane_utilization=(
            min(1.0, crane_operating_minutes / total_crane_minutes)
            if total_crane_minutes > 0
            else 0.0
        ),
        crane_idle_minutes=max(
            0.0,
            total_crane_minutes - crane_operating_minutes - crane_downtime,
        ),
        crane_downtime_minutes=crane_downtime,
        crane_failure_count=sum(
            1
            for event in simulation.terminal.events
            if event.event_type == TerminalEventType.CRANE_FAILED
        ),
        average_crane_downtime_minutes=(
            crane_downtime / len(crane_downtime_intervals)
            if crane_downtime_intervals
            else None
        ),
        final_yard_utilization=yard_stats["final"],
        average_yard_utilization=yard_stats["average"],
        peak_yard_utilization=yard_stats["peak"],
        yard_capacity_rejection_count=(
            simulation.yard_capacity_rejection_count
        ),
        event_count=simulation.terminal.event_count,
    )


def _collect_vessel_metrics(
    simulation: "PortSimulation",
) -> tuple[VesselMetrics, ...]:
    records = {
        record.vessel_id: record
        for record in simulation.lifecycle_records
    }
    arrival_times = {
        plan.vessel.vessel_id: plan.arrival_time_minutes
        for plan in simulation.arrival_plans
    }
    planned_arrival_times = {
        plan.vessel.vessel_id: plan.planned_arrival_time_minutes
        for plan in simulation.arrival_plans
    }
    vessel_ids = sorted(
        set(simulation.terminal.vessel_ids)
        | {
            vessel_id
            for vessel_id, arrival_time in arrival_times.items()
            if arrival_time <= simulation.elapsed_minutes
        }
    )
    metrics: list[VesselMetrics] = []

    for vessel_id in vessel_ids:
        arrival_time = arrival_times.get(vessel_id)
        if arrival_time is None:
            arrival_time = _first_event_minutes(
                simulation,
                vessel_id,
                TerminalEventType.VESSEL_ARRIVED,
            )

        if arrival_time is None:
            continue

        record = records.get(vessel_id)
        berth_time = (
            record.berth_time_minutes
            if record is not None
            else _first_event_minutes(
                simulation,
                vessel_id,
                TerminalEventType.VESSEL_BERTHED,
            )
        )
        departure_time = (
            record.departure_time_minutes
            if record is not None
            else _first_event_minutes(
                simulation,
                vessel_id,
                TerminalEventType.VESSEL_DEPARTED,
            )
        )
        operation_start = (
            record.operation_start_minutes
            if record is not None
            else _first_event_minutes(
                simulation,
                vessel_id,
                TerminalEventType.VESSEL_OPERATION_STARTED,
            )
        )
        operation_end = (
            record.operation_end_minutes
            if record is not None
            else _first_event_minutes(
                simulation,
                vessel_id,
                TerminalEventType.VESSEL_OPERATION_COMPLETED,
            )
        )
        planned_arrival = planned_arrival_times.get(vessel_id)

        metrics.append(
            VesselMetrics(
                vessel_id=vessel_id,
                arrival_time_minutes=arrival_time,
                berth_time_minutes=berth_time,
                operation_start_minutes=operation_start,
                operation_end_minutes=operation_end,
                departure_time_minutes=departure_time,
                waiting_time_minutes=(
                    berth_time - arrival_time
                    if berth_time is not None
                    else None
                ),
                turnaround_time_minutes=(
                    departure_time - arrival_time
                    if departure_time is not None
                    else None
                ),
                eta_deviation_minutes=(
                    arrival_time - planned_arrival
                    if planned_arrival is not None
                    else None
                ),
            )
        )

    return tuple(metrics)


def _first_event_minutes(
    simulation: "PortSimulation",
    vessel_id: str,
    event_type: TerminalEventType,
) -> float | None:
    for event in simulation.terminal.events:
        if event.event_type == event_type and event.correlation_id == vessel_id:
            return _minutes_since_start(simulation, event.occurred_at)

    return None


def _max_queue_length(simulation: "PortSimulation") -> int:
    queue_length = 0
    max_queue = 0

    for event in simulation.terminal.events:
        if event.event_type == TerminalEventType.VESSEL_WAITING:
            queue_length += 1
            max_queue = max(max_queue, queue_length)
        elif event.event_type == TerminalEventType.VESSEL_BERTHED:
            queue_length = max(0, queue_length - 1)

    return max_queue


def _berth_utilization(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> float:
    if duration_minutes <= 0 or simulation.terminal.berth_count == 0:
        return 0.0

    total_berth_length = sum(
        simulation.terminal.get_berth(berth_id).length_m
        for berth_id in simulation.terminal.berth_ids
    )
    if total_berth_length <= 0:
        return 0.0

    occupied_length_minutes = sum(
        interval["vessel_length_m"]
        * (interval["end_minutes"] - interval["start_minutes"])
        for interval in _berth_intervals(simulation, duration_minutes)
    )

    return min(
        1.0,
        occupied_length_minutes / (total_berth_length * duration_minutes),
    )


def _crane_operating_minutes(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> float:
    if duration_minutes <= 0:
        return 0.0

    return sum(
        end - start
        for _, _, start, end in _crane_operating_intervals(
            simulation,
            duration_minutes,
        )
    )


def _crane_downtime_intervals(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> tuple[tuple[str, float, float], ...]:
    return tuple(
        (crane_id, start, end)
        for crane_id, start, end in _crane_failed_intervals(
            simulation,
            duration_minutes,
        )
    )


def _yard_utilization_stats(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> dict[str, float]:
    if simulation.terminal.yard_block_count == 0:
        return {"final": 0.0, "average": 0.0, "peak": 0.0}

    total_capacity = sum(
        simulation.terminal.get_yard_block(block_id).capacity_teu
        for block_id in simulation.terminal.yard_block_ids
    )
    if total_capacity <= 0:
        return {"final": 0.0, "average": 0.0, "peak": 0.0}

    points = _yard_occupancy_points(simulation, duration_minutes)
    if not points:
        return {"final": 0.0, "average": 0.0, "peak": 0.0}

    peak = max(teu / total_capacity for _, teu in points)
    final = points[-1][1] / total_capacity
    area = 0.0

    for (start, teu), (end, _) in zip(points, points[1:]):
        area += max(0.0, end - start) * teu

    if duration_minutes > points[-1][0]:
        area += (duration_minutes - points[-1][0]) * points[-1][1]

    average = (
        area / duration_minutes / total_capacity
        if duration_minutes > 0
        else final
    )

    return {
        "final": min(1.0, final),
        "average": min(1.0, average),
        "peak": min(1.0, peak),
    }


def _berth_intervals(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> tuple[dict[str, float | str], ...]:
    open_intervals: dict[str, dict[str, float | str]] = {}
    intervals: list[dict[str, float | str]] = []

    for event in simulation.terminal.events:
        elapsed = _minutes_since_start(simulation, event.occurred_at)
        if event.event_type == TerminalEventType.BERTH_OCCUPANCY_ADDED:
            vessel_id = str(event.payload["vessel_id"])
            vessel = simulation.terminal.get_vessel(vessel_id)
            open_intervals[vessel_id] = {
                "vessel_id": vessel_id,
                "berth_id": event.entity_id,
                "start_position_m": float(event.payload["start_position_m"]),
                "end_position_m": float(event.payload["end_position_m"]),
                "vessel_length_m": vessel.length_m,
                "start_minutes": elapsed,
            }
        elif event.event_type == TerminalEventType.BERTH_OCCUPANCY_REMOVED:
            vessel_id = str(event.payload["vessel_id"])
            interval = open_intervals.pop(vessel_id, None)
            if interval is not None:
                interval["end_minutes"] = elapsed
                intervals.append(interval)

    for interval in open_intervals.values():
        interval["end_minutes"] = duration_minutes
        intervals.append(interval)

    return tuple(intervals)


def _crane_operating_intervals(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> tuple[tuple[str, str | None, float, float], ...]:
    operating: dict[str, tuple[float, str | None]] = {}
    intervals: list[tuple[str, str | None, float, float]] = []

    for event in simulation.terminal.events:
        elapsed = _minutes_since_start(simulation, event.occurred_at)
        if event.event_type == TerminalEventType.CRANE_OPERATION_STARTED:
            operating[event.entity_id] = (
                elapsed,
                event.payload.get("task_id"),
            )
        elif event.event_type in {
            TerminalEventType.CRANE_OPERATION_STOPPED,
            TerminalEventType.CRANE_FAILED,
        }:
            started = operating.pop(event.entity_id, None)
            if started is not None:
                start_minutes, task_id = started
                intervals.append(
                    (event.entity_id, task_id, start_minutes, elapsed)
                )

    for crane_id, (start_minutes, task_id) in operating.items():
        intervals.append(
            (crane_id, task_id, start_minutes, duration_minutes)
        )

    return tuple(intervals)


def _crane_failed_intervals(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> tuple[tuple[str, float, float], ...]:
    failed: dict[str, float] = {}
    intervals: list[tuple[str, float, float]] = []

    for event in simulation.terminal.events:
        elapsed = _minutes_since_start(simulation, event.occurred_at)
        if event.event_type == TerminalEventType.CRANE_FAILED:
            failed[event.entity_id] = elapsed
        elif (
            event.event_type == TerminalEventType.CRANE_REPAIRED
            and event.entity_id in failed
        ):
            intervals.append(
                (event.entity_id, failed.pop(event.entity_id), elapsed)
            )

    for crane_id, start_minutes in failed.items():
        intervals.append((crane_id, start_minutes, duration_minutes))

    return tuple(intervals)


def _yard_occupancy_points(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> tuple[tuple[float, float], ...]:
    occupied_teu = 0.0
    points: list[tuple[float, float]] = [(0.0, 0.0)]

    for event in simulation.terminal.events:
        elapsed = _minutes_since_start(simulation, event.occurred_at)
        if event.event_type == TerminalEventType.YARD_GROUP_STORED:
            occupied_teu += float(event.payload.get("teu", 0.0))
            points.append((elapsed, occupied_teu))
        elif event.event_type == TerminalEventType.YARD_GROUP_RELEASED:
            occupied_teu = max(
                0.0,
                occupied_teu - float(event.payload.get("teu", 0.0)),
            )
            points.append((elapsed, occupied_teu))

    if points[-1][0] < duration_minutes:
        points.append((duration_minutes, occupied_teu))

    return tuple(points)


def _total_handled_moves(simulation: "PortSimulation") -> float:
    handled = 0.0
    active_by_task = {
        active.task_id: active
        for active in simulation.active_task_processes()
    }

    for plan in simulation.task_work_plans.values():
        task = simulation.terminal.get_operation_task(plan.task_id)
        if plan.planned_teu <= 0:
            continue

        completed_moves = plan.workload_moves * (
            task.completed_teu / plan.planned_teu
        )
        active = active_by_task.get(plan.task_id)

        if active is not None:
            completed_moves += (
                active.moves_per_hour
                / 60.0
                * max(0.0, simulation.elapsed_minutes - active.started_at_minutes)
            )

        handled += min(plan.workload_moves, completed_moves)

    return handled


def _current_wait_ages(
    vessel_metrics: tuple[VesselMetrics, ...],
    simulation: "PortSimulation",
) -> tuple[float, ...]:
    return tuple(
        simulation.elapsed_minutes - metrics.arrival_time_minutes
        for metrics in vessel_metrics
        if metrics.berth_time_minutes is None
    )


def _minutes_since_start(
    simulation: "PortSimulation",
    occurred_at,
) -> float:
    return (occurred_at - simulation.start_time).total_seconds() / 60.0


def _known(values) -> tuple[float, ...]:
    return tuple(value for value in values if value is not None)


def _average(values: tuple[float, ...]) -> float | None:
    if not values:
        return None

    return sum(values) / len(values)


def _median(values: tuple[float, ...]) -> float | None:
    if not values:
        return None

    return float(median(values))


def _percentile(
    values: tuple[float, ...],
    percentile: float,
) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    index = int(round((percentile / 100.0) * (len(ordered) - 1)))

    return ordered[index]
