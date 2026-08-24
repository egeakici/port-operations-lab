from __future__ import annotations

from datetime import datetime, timedelta

from terminal_core import Berth, Terminal, TerminalEventType, Vessel

from mini_port_sim import (
    PortSimulation,
    ScenarioConfig,
    ServiceConfig,
    TrafficConfig,
    VesselArrivalPlan,
    berth_dispatcher_process,
    vessel_arrival_process,
)


START_TIME = datetime(2026, 8, 20, 8, 0)


def create_vessel(vessel_id: str, *, workload_moves: int = 10) -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=250.0,
        eta=START_TIME,
        workload_moves=workload_moves,
        priority=2,
        max_cranes=2,
    )


def test_arrival_dispatch_and_lifecycle_depart_two_vessels_fcfs() -> None:
    terminal = Terminal(current_time=START_TIME)
    terminal.register_berth(
        Berth(
            berth_id="B01",
            length_m=300.0,
            min_clearance_m=20.0,
        ),
        occurred_at=START_TIME,
    )
    scenario = ScenarioConfig(
        scenario_id="lifecycle",
        duration_hours=2,
        seed=42,
        traffic=TrafficConfig(vessel_count=2),
        service=ServiceConfig(
            berthing_preparation_minutes=5.0,
            service_minutes_per_move=1.0,
            departure_preparation_minutes=5.0,
        ),
    )
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=scenario,
    )
    plans = (
        VesselArrivalPlan(
            vessel=create_vessel("V001"),
            planned_arrival_time_minutes=0.0,
        ),
        VesselArrivalPlan(
            vessel=create_vessel("V002"),
            planned_arrival_time_minutes=5.0,
        ),
    )

    simulation.add_process(berth_dispatcher_process)
    simulation.add_process(lambda sim: vessel_arrival_process(sim, plans))

    simulation.run(until_minutes=60.0)

    assert terminal.get_vessel("V001").status.value == "departed"
    assert terminal.get_vessel("V002").status.value == "departed"
    assert terminal.get_berth("B01").occupancy_count == 0
    assert simulation.waiting_vessel_ids == ()
    assert simulation.completed_vessel_ids == ["V001", "V002"]
    assert [
        record.departure_time_minutes
        for record in simulation.lifecycle_records
    ] == [20.0, 40.0]

    event_types = [event.event_type for event in terminal.events]
    assert event_types.count(TerminalEventType.VESSEL_ARRIVED) == 2
    assert event_types.count(TerminalEventType.VESSEL_BERTHED) == 2
    assert event_types.count(TerminalEventType.VESSEL_OPERATION_STARTED) == 2
    assert event_types.count(TerminalEventType.VESSEL_OPERATION_COMPLETED) == 2
    assert event_types.count(TerminalEventType.VESSEL_DEPARTED) == 2
    assert terminal.current_time == START_TIME + timedelta(minutes=60)

    completed_events = [
        event
        for event in terminal.events
        if event.event_type == TerminalEventType.VESSEL_OPERATION_COMPLETED
    ]
    departed_events = [
        event
        for event in terminal.events
        if event.event_type == TerminalEventType.VESSEL_DEPARTED
    ]
    assert completed_events[0].occurred_at == START_TIME + timedelta(minutes=15)
    assert departed_events[0].occurred_at == START_TIME + timedelta(minutes=20)


def test_basic_operations_starts_arrival_and_dispatcher_processes() -> None:
    terminal = Terminal(current_time=START_TIME)
    terminal.register_berth(
        Berth(berth_id="B01", length_m=300.0),
        occurred_at=START_TIME,
    )
    scenario = ScenarioConfig(
        scenario_id="basic",
        duration_hours=1,
        seed=42,
        traffic=TrafficConfig(vessel_count=1),
        service=ServiceConfig(
            berthing_preparation_minutes=0.0,
            service_minutes_per_move=0.1,
            departure_preparation_minutes=0.0,
        ),
    )
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=scenario,
    )

    simulation.start_basic_operations()

    assert simulation.process_count == 3


def test_dispatcher_commits_berth_before_next_same_tick_decision() -> None:
    terminal = Terminal(current_time=START_TIME)
    terminal.register_berth(
        Berth(
            berth_id="B01",
            length_m=300.0,
            min_clearance_m=20.0,
        ),
        occurred_at=START_TIME,
    )
    scenario = ScenarioConfig(
        scenario_id="same-tick",
        duration_hours=1,
        seed=42,
        service=ServiceConfig(
            berthing_preparation_minutes=0.0,
            service_minutes_per_move=1.0,
            departure_preparation_minutes=0.0,
        ),
    )
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=scenario,
    )
    plans = (
        VesselArrivalPlan(
            vessel=create_vessel("V001", workload_moves=10),
            planned_arrival_time_minutes=0.0,
        ),
        VesselArrivalPlan(
            vessel=create_vessel("V002", workload_moves=10),
            planned_arrival_time_minutes=0.0,
        ),
    )

    simulation.add_process(berth_dispatcher_process)
    simulation.add_process(lambda sim: vessel_arrival_process(sim, plans))
    simulation.run(until_minutes=1.0)

    assert terminal.get_vessel("V001").status.value == "operating"
    assert terminal.get_vessel("V002").status.value == "waiting"
    assert terminal.get_berth("B01").occupancy_count == 1
    assert simulation.waiting_vessel_ids == ("V002",)
