from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from terminal_core import Berth, QuayCrane, Terminal, YardBlock

from mini_port_sim.metrics import SimulationMetrics
from mini_port_sim.scenario import ScenarioConfig
from mini_port_sim.simulation import PortSimulation
from mini_port_sim.visualization import (
    BerthTimelineSegment,
    CraneTimelineSegment,
    ReplayFrame,
    build_berth_timeline,
    build_crane_timeline,
    build_event_replay,
)


@dataclass(frozen=True)
class ExperimentResult:
    scenario: ScenarioConfig
    simulation: PortSimulation
    metrics: SimulationMetrics
    replay_frames: tuple[ReplayFrame, ...]
    berth_timeline: tuple[BerthTimelineSegment, ...]
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
            "yard_utilization": self.metrics.yard_utilization,
            "max_queue_length": self.metrics.max_queue_length,
            "total_handled_moves": self.metrics.total_handled_moves,
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


def _crane_position(
    index: int,
    crane_count: int,
    berth_length_m: float,
) -> float:
    if crane_count <= 1:
        return berth_length_m / 2.0

    spacing = berth_length_m / (crane_count + 1)

    return spacing * (index + 1)
