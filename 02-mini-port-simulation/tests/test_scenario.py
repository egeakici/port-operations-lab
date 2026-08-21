from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from terminal_core import Terminal

from mini_port_sim import (
    ARRIVAL_STREAM,
    FAILURE_STREAM,
    WORKLOAD_STREAM,
    PortSimulation,
    RandomStreams,
    ScenarioConfig,
    TerminalConfig,
    TerminationMode,
    TrafficConfig,
)


START_TIME = datetime(2026, 8, 20, 8, 0)


def test_scenario_config_exposes_duration_minutes_and_nested_configs() -> None:
    scenario = ScenarioConfig(
        scenario_id="medium",
        duration_hours=36,
        seed=42,
        terminal=TerminalConfig(
            berth_length_m=900.0,
            quay_crane_count=3,
        ),
        traffic=TrafficConfig(
            vessel_count=12,
            mean_interarrival_minutes=120.0,
        ),
    )

    assert scenario.duration_minutes == 2160.0
    assert scenario.termination_mode == TerminationMode.HORIZON
    assert scenario.terminal.berth_length_m == 900.0
    assert scenario.traffic.vessel_count == 12


def test_scenario_config_round_trips_through_dict() -> None:
    scenario = ScenarioConfig(
        scenario_id="roundtrip",
        duration_hours=12,
        seed=7,
        termination_mode=TerminationMode.DRAIN,
        terminal=TerminalConfig(yard_block_count=2),
        traffic=TrafficConfig(
            min_workload_moves=100,
            max_workload_moves=500,
        ),
    )

    restored = ScenarioConfig.from_dict(scenario.to_dict())

    assert restored == scenario


def test_scenario_config_loads_smoke_json() -> None:
    scenario = ScenarioConfig.load_json("scenarios/smoke.json")

    assert scenario.scenario_id == "smoke"
    assert scenario.seed == 42
    assert scenario.duration_minutes == 1440.0
    assert scenario.traffic.vessel_count == 5


def test_scenario_validation_rejects_invalid_ranges() -> None:
    with pytest.raises(ValueError, match="Minimum vessel length"):
        TrafficConfig(
            min_vessel_length_m=400.0,
            max_vessel_length_m=300.0,
        )

    with pytest.raises(ValueError, match="Scenario seed"):
        ScenarioConfig(
            scenario_id="bad",
            duration_hours=1,
            seed=True,
        )


def test_random_stream_manifest_is_stable_for_same_master_seed() -> None:
    first = RandomStreams(master_seed=42).manifest()
    second = RandomStreams(master_seed=42).manifest()

    assert first == second
    assert first[ARRIVAL_STREAM] != first[FAILURE_STREAM]


def test_random_streams_are_independent_between_names() -> None:
    baseline_failure = RandomStreams(master_seed=42).get(
        FAILURE_STREAM
    ).random()
    streams = RandomStreams(master_seed=42)

    arrival_rng = streams.get(ARRIVAL_STREAM)
    for _ in range(25):
        arrival_rng.random()

    assert streams.get(FAILURE_STREAM).random() == baseline_failure


def test_random_streams_are_repeatable_for_same_scenario_seed() -> None:
    scenario = ScenarioConfig(
        scenario_id="repeatable",
        duration_hours=1,
        seed=99,
    )
    first = scenario.random_streams()
    second = scenario.random_streams()

    first_draws = [
        first.get(WORKLOAD_STREAM).randint(
            scenario.traffic.min_workload_moves,
            scenario.traffic.max_workload_moves,
        )
        for _ in range(5)
    ]
    second_draws = [
        second.get(WORKLOAD_STREAM).randint(
            scenario.traffic.min_workload_moves,
            scenario.traffic.max_workload_moves,
        )
        for _ in range(5)
    ]

    assert first_draws == second_draws


def test_port_simulation_can_be_created_and_run_from_scenario() -> None:
    terminal = Terminal(current_time=START_TIME)
    scenario = ScenarioConfig(
        scenario_id="engine",
        duration_hours=2,
        seed=123,
    )
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=scenario,
    )

    snapshot = simulation.run_scenario()

    assert simulation.seed == 123
    assert simulation.scenario == scenario
    assert simulation.elapsed_minutes == 120.0
    assert snapshot.current_time == START_TIME + timedelta(hours=2)


def test_port_simulation_owns_random_streams_from_scenario_seed() -> None:
    scenario = ScenarioConfig(
        scenario_id="rng-owner",
        duration_hours=1,
        seed=77,
    )
    first = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )
    second = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )

    first_arrivals = [
        first.rng.get(ARRIVAL_STREAM).random()
        for _ in range(5)
    ]
    second_arrivals = [
        second.rng.get(ARRIVAL_STREAM).random()
        for _ in range(5)
    ]

    assert first.random_streams is first.rng
    assert first_arrivals == second_arrivals


def test_port_simulation_random_streams_are_stateful_within_one_run() -> None:
    simulation = PortSimulation(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        seed=42,
    )
    arrival_rng = simulation.rng.get(ARRIVAL_STREAM)

    first_draw = arrival_rng.random()
    second_draw = simulation.rng.get(ARRIVAL_STREAM).random()

    assert second_draw != first_draw


def test_port_simulation_without_seed_rejects_rng_access() -> None:
    simulation = PortSimulation(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
    )

    with pytest.raises(ValueError, match="no RandomStreams"):
        simulation.rng
