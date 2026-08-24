from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from terminal_core import Berth, Terminal

from mini_port_sim import (
    ARRIVAL_STREAM,
    DisruptionConfig,
    PortSimulation,
    ScenarioConfig,
    TrafficConfig,
    VESSEL_STREAM,
    VesselArrivalGenerator,
    VesselArrivalPlan,
    vessel_arrival_process,
)


START_TIME = datetime(2026, 8, 20, 8, 0)


def test_vessel_arrival_generation_is_repeatable_for_same_scenario() -> None:
    scenario = ScenarioConfig(
        scenario_id="arrivals",
        duration_hours=24,
        seed=42,
        traffic=TrafficConfig(
            vessel_count=3,
            mean_interarrival_minutes=90,
            min_vessel_length_m=180,
            max_vessel_length_m=240,
            min_workload_moves=100,
            max_workload_moves=200,
        ),
    )
    first_sim = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )
    second_sim = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )
    generator = VesselArrivalGenerator()

    first = generator.generate(first_sim)
    second = generator.generate(second_sim)

    assert [plan.vessel.to_dict() for plan in first] == [
        plan.vessel.to_dict() for plan in second
    ]
    assert [plan.arrival_time_minutes for plan in first] == [
        plan.arrival_time_minutes for plan in second
    ]
    assert first[0].arrival_time_minutes == 0.0
    assert [plan.vessel.vessel_id for plan in first] == [
        "V001",
        "V002",
        "V003",
    ]


def test_vessel_arrival_generation_consumes_simulation_owned_rng() -> None:
    scenario = ScenarioConfig(
        scenario_id="stateful-arrivals",
        duration_hours=24,
        seed=42,
        traffic=TrafficConfig(vessel_count=1),
    )
    simulation = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )
    generator = VesselArrivalGenerator()

    first = generator.generate(simulation)
    second = generator.generate(simulation)

    assert first[0].vessel.length_m != second[0].vessel.length_m


def test_vessel_attributes_use_vessel_stream_not_arrival_stream() -> None:
    scenario = ScenarioConfig(
        scenario_id="vessel-stream",
        duration_hours=24,
        seed=42,
        traffic=TrafficConfig(
            vessel_count=1,
            min_vessel_length_m=180.0,
            max_vessel_length_m=240.0,
        ),
    )
    baseline = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )
    shifted_arrival = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )

    for _ in range(20):
        shifted_arrival.rng.get(ARRIVAL_STREAM).random()

    generator = VesselArrivalGenerator()
    baseline_plan = generator.generate(baseline)[0]
    shifted_plan = generator.generate(shifted_arrival)[0]

    assert baseline_plan.vessel.length_m == shifted_plan.vessel.length_m
    assert baseline.rng.derive_seed(ARRIVAL_STREAM) != (
        baseline.rng.derive_seed(VESSEL_STREAM)
    )


def test_eta_variation_is_reproducible_and_preserves_planned_eta() -> None:
    scenario = ScenarioConfig(
        scenario_id="eta-variation",
        duration_hours=24,
        seed=42,
        traffic=TrafficConfig(
            vessel_count=4,
            mean_interarrival_minutes=90,
        ),
        disruptions=DisruptionConfig(
            eta_delay_stddev_minutes=30.0,
        ),
    )
    different_seed = ScenarioConfig(
        scenario_id="eta-variation-different",
        duration_hours=24,
        seed=43,
        traffic=TrafficConfig(
            vessel_count=4,
            mean_interarrival_minutes=90,
        ),
        disruptions=DisruptionConfig(
            eta_delay_stddev_minutes=30.0,
        ),
    )
    first_sim = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )
    second_sim = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=scenario,
    )
    different_sim = PortSimulation.from_scenario(
        terminal=Terminal(current_time=START_TIME),
        start_time=START_TIME,
        scenario=different_seed,
    )

    first = VesselArrivalGenerator().generate(first_sim)
    second = VesselArrivalGenerator().generate(second_sim)
    different = VesselArrivalGenerator().generate(different_sim)

    assert [plan.actual_arrival_time_minutes for plan in first] == [
        plan.actual_arrival_time_minutes for plan in second
    ]
    assert [plan.actual_arrival_time_minutes for plan in first] != [
        plan.actual_arrival_time_minutes for plan in different
    ]
    assert any(
        plan.planned_arrival_time_minutes != plan.actual_arrival_time_minutes
        for plan in first
    )
    assert first[1].vessel.eta == (
        START_TIME
        + timedelta(minutes=first[1].planned_arrival_time_minutes)
    )


def test_arrival_process_rejects_vessel_that_cannot_fit_any_registered_berth() -> None:
    scenario = ScenarioConfig(
        scenario_id="too-large",
        duration_hours=1,
        seed=42,
    )
    terminal = Terminal(current_time=START_TIME)
    terminal.register_berth(
        Berth(berth_id="B01", length_m=300.0),
        occurred_at=START_TIME,
    )
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=scenario,
    )
    oversized = VesselArrivalGenerator().generate(simulation)[0].vessel
    oversized.length_m = 350.0

    simulation.add_process(
        lambda sim: vessel_arrival_process(
            sim,
            (
                VesselArrivalPlan(
                    vessel=oversized,
                    planned_arrival_time_minutes=0.0,
                ),
            ),
        )
    )

    with pytest.raises(ValueError, match="cannot fit any registered berth"):
        simulation.run(until_minutes=0.0)
