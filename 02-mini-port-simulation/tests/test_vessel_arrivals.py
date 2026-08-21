from __future__ import annotations

from datetime import datetime

from terminal_core import Terminal

from mini_port_sim import (
    PortSimulation,
    ScenarioConfig,
    TrafficConfig,
    VesselArrivalGenerator,
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
