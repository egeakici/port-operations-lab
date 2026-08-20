from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from terminal_core import (
    Terminal,
    TerminalEventType,
    Vessel,
    VesselStatus,
)

from mini_port_sim import PortSimulation


START_TIME = datetime(2026, 8, 20, 8, 0)


def create_vessel(vessel_id: str = "V001") -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=250.0,
        eta=START_TIME,
        workload_moves=120,
        priority=2,
        max_cranes=2,
    )


def test_simulation_starts_with_simpy_environment_at_zero() -> None:
    terminal = Terminal(current_time=START_TIME)
    simulation = PortSimulation(
        terminal=terminal,
        start_time=START_TIME,
        seed=42,
    )

    assert simulation.env.now == 0
    assert simulation.elapsed_minutes == 0.0
    assert simulation.now_datetime() == START_TIME


def test_run_advances_terminal_time_to_horizon() -> None:
    terminal = Terminal(current_time=START_TIME)
    simulation = PortSimulation(
        terminal=terminal,
        start_time=START_TIME,
    )

    snapshot = simulation.run(until_minutes=90.0)

    assert simulation.env.now == 90.0
    assert simulation.elapsed_minutes == 90.0
    assert simulation.now_datetime() == START_TIME + timedelta(minutes=90)
    assert terminal.current_time == simulation.now_datetime()
    assert snapshot.current_time == simulation.now_datetime()


def test_process_can_apply_core_command_at_simulation_time() -> None:
    terminal = Terminal(current_time=START_TIME)
    terminal.register_vessel(create_vessel(), occurred_at=START_TIME)
    simulation = PortSimulation(
        terminal=terminal,
        start_time=START_TIME,
    )

    def vessel_arrival(sim: PortSimulation):
        yield sim.env.timeout(60)
        sim.terminal.arrive_vessel(
            "V001",
            occurred_at=sim.now_datetime(),
        )

    process = simulation.add_process(vessel_arrival)

    simulation.run(until_minutes=120)

    assert simulation.process_count == 1
    assert process.processed
    assert terminal.get_vessel("V001").status == VesselStatus.WAITING
    assert terminal.events[0].event_type == TerminalEventType.VESSEL_ARRIVED
    assert terminal.events[0].occurred_at == START_TIME + timedelta(minutes=60)
    assert terminal.events[1].event_type == TerminalEventType.VESSEL_WAITING
    assert terminal.current_time == START_TIME + timedelta(minutes=120)


def test_run_rejects_moving_simulation_time_backwards() -> None:
    terminal = Terminal(current_time=START_TIME)
    simulation = PortSimulation(
        terminal=terminal,
        start_time=START_TIME,
    )

    simulation.run(until_minutes=120)

    with pytest.raises(ValueError, match="cannot move backwards"):
        simulation.run(until_minutes=60)


def test_run_for_hours_advances_relative_to_current_time() -> None:
    terminal = Terminal(current_time=START_TIME)
    simulation = PortSimulation(
        terminal=terminal,
        start_time=START_TIME,
    )

    simulation.run_for_hours(1.5)
    snapshot = simulation.run_for_hours(0.5)

    assert simulation.elapsed_minutes == 120.0
    assert snapshot.current_time == START_TIME + timedelta(hours=2)
