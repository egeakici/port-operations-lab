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
    total_handled_moves: int
    average_waiting_time_minutes: float | None
    median_waiting_time_minutes: float | None
    p95_waiting_time_minutes: float | None
    average_turnaround_time_minutes: float | None
    p95_turnaround_time_minutes: float | None
    max_queue_length: int
    berth_utilization: float
    crane_utilization: float
    crane_downtime_minutes: float
    yard_utilization: float
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
            "average_turnaround_time_minutes": (
                self.average_turnaround_time_minutes
            ),
            "p95_turnaround_time_minutes": (
                self.p95_turnaround_time_minutes
            ),
            "max_queue_length": self.max_queue_length,
            "berth_utilization": self.berth_utilization,
            "crane_utilization": self.crane_utilization,
            "crane_downtime_minutes": self.crane_downtime_minutes,
            "yard_utilization": self.yard_utilization,
            "event_count": self.event_count,
        }


def collect_metrics(simulation: "PortSimulation") -> SimulationMetrics:
    vessel_metrics = _collect_vessel_metrics(simulation)
    waiting_times = _known(
        metrics.waiting_time_minutes for metrics in vessel_metrics
    )
    turnaround_times = _known(
        metrics.turnaround_time_minutes for metrics in vessel_metrics
    )
    duration = max(simulation.elapsed_minutes, 0.0)
    completed_vessel_ids = set(simulation.completed_vessel_ids)

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
        total_handled_moves=sum(
            plan.workload_moves
            for plan in simulation.task_work_plans.values()
            if simulation.terminal.get_operation_task(plan.task_id).status.value
            == "completed"
        ),
        average_waiting_time_minutes=_average(waiting_times),
        median_waiting_time_minutes=_median(waiting_times),
        p95_waiting_time_minutes=_percentile(waiting_times, 95),
        average_turnaround_time_minutes=_average(turnaround_times),
        p95_turnaround_time_minutes=_percentile(turnaround_times, 95),
        max_queue_length=_max_queue_length(simulation),
        berth_utilization=_berth_utilization(simulation, duration),
        crane_utilization=_crane_utilization(simulation, duration),
        crane_downtime_minutes=_crane_downtime_minutes(simulation, duration),
        yard_utilization=_yard_utilization(simulation),
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
        set(simulation.terminal.vessel_ids) | set(arrival_times)
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

    occupied_length_minutes = 0.0
    for record in simulation.lifecycle_records:
        vessel = simulation.terminal.get_vessel(record.vessel_id)
        occupied_length_minutes += (
            vessel.length_m
            * (record.departure_time_minutes - record.berth_time_minutes)
        )

    return min(
        1.0,
        occupied_length_minutes / (total_berth_length * duration_minutes),
    )


def _crane_utilization(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> float:
    if duration_minutes <= 0 or simulation.terminal.quay_crane_count == 0:
        return 0.0

    operating_minutes = _duration_between_events(
        simulation,
        TerminalEventType.CRANE_OPERATION_STARTED,
        TerminalEventType.CRANE_OPERATION_STOPPED,
    )

    return min(
        1.0,
        operating_minutes
        / (simulation.terminal.quay_crane_count * duration_minutes),
    )


def _crane_downtime_minutes(
    simulation: "PortSimulation",
    duration_minutes: float,
) -> float:
    if duration_minutes <= 0:
        return 0.0

    return _duration_between_events(
        simulation,
        TerminalEventType.CRANE_FAILED,
        TerminalEventType.CRANE_REPAIRED,
        close_open_at_minutes=duration_minutes,
    )


def _yard_utilization(simulation: "PortSimulation") -> float:
    if simulation.terminal.yard_block_count == 0:
        return 0.0

    total_capacity = 0.0
    total_occupied = 0.0
    for block_id in simulation.terminal.yard_block_ids:
        block = simulation.terminal.get_yard_block(block_id)
        total_capacity += block.capacity_teu
        total_occupied += block.occupied_teu

    if total_capacity <= 0:
        return 0.0

    return min(1.0, total_occupied / total_capacity)


def _duration_between_events(
    simulation: "PortSimulation",
    start_type: TerminalEventType,
    end_type: TerminalEventType,
    close_open_at_minutes: float | None = None,
) -> float:
    open_starts: dict[str, float] = {}
    total = 0.0

    for event in simulation.terminal.events:
        if event.event_type == start_type:
            open_starts[event.entity_id] = _minutes_since_start(
                simulation,
                event.occurred_at,
            )
        elif event.event_type == end_type and event.entity_id in open_starts:
            total += (
                _minutes_since_start(simulation, event.occurred_at)
                - open_starts.pop(event.entity_id)
            )

    if close_open_at_minutes is not None:
        for started_at in open_starts.values():
            total += max(0.0, close_open_at_minutes - started_at)

    return total


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
