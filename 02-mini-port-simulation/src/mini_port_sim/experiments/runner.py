from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from math import sqrt
from statistics import median, stdev
from typing import Any

from terminal_core import Berth, QuayCrane, Terminal, YardBlock

from mini_port_sim.metrics import SimulationMetrics
from mini_port_sim.scenario import ScenarioConfig
from mini_port_sim.simulation import PortSimulation
from mini_port_sim.visualization import (
    BerthTimelineSegment,
    CraneTimelineSegment,
    ReplayFrame,
    VesselTimelineSegment,
    build_berth_timeline,
    build_crane_timeline,
    build_event_replay,
    build_vessel_timeline,
)


@dataclass(frozen=True)
class ExperimentResult:
    scenario: ScenarioConfig
    simulation: PortSimulation
    metrics: SimulationMetrics
    replay_frames: tuple[ReplayFrame, ...]
    berth_timeline: tuple[BerthTimelineSegment, ...]
    vessel_timeline: tuple[VesselTimelineSegment, ...]
    crane_timeline: tuple[CraneTimelineSegment, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario.scenario_id,
            "seed": self.scenario.seed,
            "completed_vessels": self.metrics.completed_vessel_count,
            "unfinished_vessels": self.metrics.unfinished_vessel_count,
            "average_waiting_minutes": (
                self.metrics.average_waiting_time_minutes
            ),
            "p95_waiting_minutes": self.metrics.p95_waiting_time_minutes,
            "average_turnaround_minutes": (
                self.metrics.average_turnaround_time_minutes
            ),
            "berth_utilization": self.metrics.berth_utilization,
            "crane_utilization": self.metrics.crane_utilization,
            "final_yard_utilization": self.metrics.final_yard_utilization,
            "peak_yard_utilization": self.metrics.peak_yard_utilization,
            "max_queue_length": self.metrics.max_queue_length,
            "total_handled_moves": self.metrics.total_handled_moves,
        }


@dataclass(frozen=True)
class AggregatedMetric:
    name: str
    count: int
    mean: float
    median: float
    stddev: float
    minimum: float
    maximum: float
    ci95_half_width: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "stddev": self.stddev,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "ci95_half_width": self.ci95_half_width,
        }


@dataclass(frozen=True)
class ExperimentAggregate:
    scenario_id: str
    seed_count: int
    metrics: dict[str, AggregatedMetric]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "seed_count": self.seed_count,
            "metrics": {
                name: metric.to_dict()
                for name, metric in self.metrics.items()
            },
        }


def build_terminal_from_scenario(
    scenario: ScenarioConfig,
    *,
    start_time: datetime,
) -> Terminal:
    terminal = Terminal(current_time=start_time)
    terminal_config = scenario.terminal
    terminal.register_berth(
        Berth(
            berth_id="B01",
            length_m=terminal_config.berth_length_m,
            min_clearance_m=terminal_config.min_clearance_m,
        ),
        occurred_at=start_time,
    )

    for index in range(terminal_config.quay_crane_count):
        terminal.register_quay_crane(
            QuayCrane(
                crane_id=f"QC{index + 1:02d}",
                position_m=_crane_position(
                    index,
                    terminal_config.quay_crane_count,
                    terminal_config.berth_length_m,
                ),
                moves_per_hour=terminal_config.quay_crane_moves_per_hour,
            ),
            occurred_at=start_time,
        )

    for index in range(terminal_config.yard_block_count):
        terminal.register_yard_block(
            YardBlock(
                block_id=f"Y{index + 1:02d}",
                capacity_teu=terminal_config.yard_block_capacity_teu,
            ),
            occurred_at=start_time,
        )

    return terminal


def run_scenario_experiment(
    scenario: ScenarioConfig,
    *,
    start_time: datetime,
) -> ExperimentResult:
    terminal = build_terminal_from_scenario(
        scenario,
        start_time=start_time,
    )
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=start_time,
        scenario=scenario,
    )
    simulation.start_basic_operations()
    simulation.run_scenario()
    metrics = simulation.collect_metrics()

    return ExperimentResult(
        scenario=scenario,
        simulation=simulation,
        metrics=metrics,
        replay_frames=build_event_replay(simulation),
        berth_timeline=build_berth_timeline(simulation),
        vessel_timeline=build_vessel_timeline(simulation),
        crane_timeline=build_crane_timeline(simulation),
    )


def run_multi_seed_experiment(
    scenario: ScenarioConfig,
    *,
    seeds: tuple[int, ...],
    start_time: datetime,
) -> tuple[ExperimentResult, ...]:
    if not seeds:
        raise ValueError("Experiment seed list cannot be empty.")

    return tuple(
        run_scenario_experiment(
            replace(scenario, seed=seed),
            start_time=start_time,
        )
        for seed in seeds
    )


def aggregate_experiment_results(
    results: tuple[ExperimentResult, ...],
) -> ExperimentAggregate:
    if not results:
        raise ValueError("Cannot aggregate an empty result set.")

    metric_values = {
        "completed_vessel_count": [
            result.metrics.completed_vessel_count for result in results
        ],
        "average_waiting_time_minutes": _known(
            result.metrics.average_waiting_time_minutes
            for result in results
        ),
        "p95_waiting_time_minutes": _known(
            result.metrics.p95_waiting_time_minutes
            for result in results
        ),
        "average_turnaround_time_minutes": _known(
            result.metrics.average_turnaround_time_minutes
            for result in results
        ),
        "berth_utilization": [
            result.metrics.berth_utilization for result in results
        ],
        "crane_utilization": [
            result.metrics.crane_utilization for result in results
        ],
        "crane_downtime_minutes": [
            result.metrics.crane_downtime_minutes for result in results
        ],
        "peak_yard_utilization": [
            result.metrics.peak_yard_utilization for result in results
        ],
        "total_handled_moves": [
            result.metrics.total_handled_moves for result in results
        ],
        "yard_capacity_rejection_count": [
            result.metrics.yard_capacity_rejection_count
            for result in results
        ],
    }

    return ExperimentAggregate(
        scenario_id=results[0].scenario.scenario_id,
        seed_count=len(results),
        metrics={
            name: _aggregate_metric(name, tuple(values))
            for name, values in metric_values.items()
            if values
        },
    )


def _aggregate_metric(
    name: str,
    values: tuple[float, ...],
) -> AggregatedMetric:
    count = len(values)
    stddev = stdev(values) if count > 1 else 0.0

    return AggregatedMetric(
        name=name,
        count=count,
        mean=sum(values) / count,
        median=float(median(values)),
        stddev=stddev,
        minimum=min(values),
        maximum=max(values),
        ci95_half_width=(
            1.96 * stddev / sqrt(count)
            if count > 1
            else 0.0
        ),
    )


def _known(values) -> list[float]:
    return [float(value) for value in values if value is not None]


def _crane_position(
    index: int,
    crane_count: int,
    berth_length_m: float,
) -> float:
    if crane_count <= 1:
        return berth_length_m / 2.0

    spacing = berth_length_m / (crane_count + 1)

    return spacing * (index + 1)
