from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mini_port_sim import (
    DisruptionConfig,
    ScenarioConfig,
    ServiceConfig,
    TerminalConfig,
    TerminationMode,
    TrafficConfig,
    build_berth_timeline,
    build_crane_timeline,
    build_event_replay,
    build_terminal_from_scenario,
    collect_metrics,
    metrics_summary,
    run_multi_seed_experiment,
    run_scenario_experiment,
)
from mini_port_sim.scenario import ScenarioConfig as ScenarioConfigLoader


START_TIME = datetime(2026, 8, 20, 8, 0)


def tiny_scenario(
    *,
    seed: int = 42,
    termination_mode: TerminationMode = TerminationMode.DRAIN,
) -> ScenarioConfig:
    return ScenarioConfig(
        scenario_id="tiny",
        duration_hours=4,
        seed=seed,
        termination_mode=termination_mode,
        terminal=TerminalConfig(
            berth_length_m=600.0,
            min_clearance_m=20.0,
            quay_crane_count=2,
            quay_crane_moves_per_hour=60.0,
            yard_block_count=2,
            yard_block_capacity_teu=500.0,
        ),
        traffic=TrafficConfig(
            vessel_count=2,
            mean_interarrival_minutes=30.0,
            min_vessel_length_m=200.0,
            max_vessel_length_m=220.0,
            min_workload_moves=60,
            max_workload_moves=60,
        ),
        service=ServiceConfig(
            berthing_preparation_minutes=0.0,
            service_minutes_per_move=1.0,
            departure_preparation_minutes=0.0,
            two_crane_efficiency=1.0,
        ),
        disruptions=DisruptionConfig(
            eta_delay_stddev_minutes=0.0,
            productivity_min_factor=1.0,
            productivity_max_factor=1.0,
        ),
    )


def test_metrics_report_vessel_kpis_and_utilization() -> None:
    result = run_scenario_experiment(
        tiny_scenario(),
        start_time=START_TIME,
    )
    metrics = collect_metrics(result.simulation)
    summary = metrics_summary(metrics)

    assert metrics.completed_vessel_count == 2
    assert metrics.unfinished_vessel_count == 0
    assert metrics.total_handled_moves == 120
    assert metrics.average_waiting_time_minutes is not None
    assert metrics.average_turnaround_time_minutes is not None
    assert metrics.max_queue_length >= 1
    assert 0.0 < metrics.berth_utilization <= 1.0
    assert 0.0 < metrics.crane_utilization <= 1.0
    assert 0.0 < metrics.yard_utilization <= 1.0
    assert summary["completed_vessels"] == 2


def test_replay_and_timeline_artifacts_are_json_safe() -> None:
    result = run_scenario_experiment(
        tiny_scenario(),
        start_time=START_TIME,
    )
    replay = build_event_replay(result.simulation)
    berth_timeline = build_berth_timeline(result.simulation)
    crane_timeline = build_crane_timeline(result.simulation)

    assert len(replay) == result.simulation.terminal.event_count
    assert replay[0].elapsed_minutes == 0.0
    assert replay[-1].completed_vessel_count == 2
    assert len(berth_timeline) == 2
    assert all(
        segment.end_minutes > segment.start_minutes
        for segment in berth_timeline
    )
    assert crane_timeline
    assert replay[0].to_dict()["event_id"].startswith("EVT-")
    assert berth_timeline[0].to_dict()["vessel_id"].startswith("V")
    assert crane_timeline[0].to_dict()["crane_id"].startswith("QC")


def test_experiment_runner_is_reproducible_for_same_seed() -> None:
    scenario = tiny_scenario(seed=77)

    first = run_scenario_experiment(
        scenario,
        start_time=START_TIME,
    )
    second = run_scenario_experiment(
        scenario,
        start_time=START_TIME,
    )

    assert first.metrics.to_dict() == second.metrics.to_dict()
    assert [frame.to_dict() for frame in first.replay_frames] == [
        frame.to_dict() for frame in second.replay_frames
    ]


def test_multi_seed_experiment_runs_all_requested_worlds() -> None:
    results = run_multi_seed_experiment(
        tiny_scenario(),
        seeds=(1, 2, 3),
        start_time=START_TIME,
    )

    assert [result.scenario.seed for result in results] == [1, 2, 3]
    assert all(result.metrics.completed_vessel_count >= 1 for result in results)


def test_project_scenario_files_load() -> None:
    scenario_dir = Path(__file__).parents[1] / "scenarios"
    scenario_ids = {
        ScenarioConfigLoader.load_json(path).scenario_id
        for path in scenario_dir.glob("*.json")
    }

    assert {
        "smoke",
        "low_traffic",
        "medium_traffic",
        "heavy_traffic",
        "crane_failure",
        "yard_bottleneck",
    }.issubset(scenario_ids)


def test_drain_mode_finishes_vessels_arriving_before_horizon() -> None:
    scenario = tiny_scenario(
        seed=42,
        termination_mode=TerminationMode.DRAIN,
    )

    result = run_scenario_experiment(
        scenario,
        start_time=START_TIME,
    )

    assert result.simulation.elapsed_minutes >= scenario.duration_minutes
    assert result.metrics.unfinished_vessel_count == 0
