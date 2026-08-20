from __future__ import annotations

from datetime import datetime, timedelta

from mini_port_sim import PortSimulation, ScenarioConfig, TerminationMode
from terminal_core import Berth, Terminal, Vessel, VesselStatus


def test_terminal_core_public_api_can_seed_a_simulation() -> None:
    start_time = datetime(2026, 8, 20, 8, 0)
    terminal = Terminal(current_time=start_time)
    vessel = Vessel(
        vessel_id="V001",
        length_m=250.0,
        eta=start_time,
        workload_moves=120,
        priority=2,
        max_cranes=2,
    )

    terminal.register_vessel(vessel, occurred_at=start_time)
    terminal.register_berth(
        Berth(berth_id="B01", length_m=700.0),
        occurred_at=start_time,
    )
    simulation = PortSimulation(
        terminal=terminal,
        start_time=start_time,
        seed=42,
    )

    assert simulation.terminal.vessel_ids == ("V001",)
    assert simulation.terminal.berth_ids == ("B01",)
    assert simulation.terminal.get_vessel("V001").status == (
        VesselStatus.APPROACHING
    )


def test_simulation_clock_advances_terminal_time_from_one_source() -> None:
    start_time = datetime(2026, 8, 20, 8, 0)
    terminal = Terminal(current_time=start_time)
    simulation = PortSimulation(
        terminal=terminal,
        start_time=start_time,
    )

    snapshot = simulation.advance_to(90.0)

    assert simulation.elapsed_minutes == 90.0
    assert simulation.now_datetime() == start_time + timedelta(minutes=90)
    assert terminal.current_time == simulation.now_datetime()
    assert snapshot.current_time == simulation.now_datetime()


def test_scenario_config_records_step_one_simulation_contract() -> None:
    scenario = ScenarioConfig(
        scenario_id="smoke",
        duration_hours=24.0,
        seed=7,
        termination_mode=TerminationMode.HORIZON,
    )

    assert scenario.scenario_id == "smoke"
    assert scenario.duration_hours == 24.0
    assert scenario.seed == 7
