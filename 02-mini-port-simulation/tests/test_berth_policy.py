from __future__ import annotations

from datetime import datetime

from terminal_core import Berth, Terminal, Vessel, VesselStatus

from mini_port_sim import FCFSLeftmostPolicy, leftmost_feasible_position


ETA = datetime(2026, 8, 20, 8, 0)


def create_vessel(
    vessel_id: str,
    *,
    length_m: float,
    status: VesselStatus = VesselStatus.WAITING,
) -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=length_m,
        eta=ETA,
        workload_moves=100,
        priority=2,
        max_cranes=2,
        status=status,
    )


def test_leftmost_feasible_position_finds_gap_between_occupancies() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1000.0,
        min_clearance_m=20.0,
    )
    berth.place_vessel(create_vessel("A", length_m=300), 0.0)
    berth.place_vessel(create_vessel("B", length_m=200), 500.0)

    start = leftmost_feasible_position(
        berth=berth,
        vessel=create_vessel("C", length_m=150),
    )

    assert start == 320.0


def test_leftmost_feasible_position_returns_none_when_vessel_cannot_fit() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=300.0,
        min_clearance_m=20.0,
    )

    assert leftmost_feasible_position(
        berth=berth,
        vessel=create_vessel("C", length_m=350),
    ) is None


def test_fcfs_leftmost_policy_chooses_first_waiting_feasible_vessel() -> None:
    terminal = Terminal(current_time=ETA)
    first = create_vessel("V001", length_m=350)
    second = create_vessel("V002", length_m=200)
    berth = Berth(
        berth_id="B01",
        length_m=300.0,
        min_clearance_m=20.0,
    )

    terminal.register_vessel(first, occurred_at=ETA)
    terminal.register_vessel(second, occurred_at=ETA)
    terminal.register_berth(berth, occurred_at=ETA)

    decision = FCFSLeftmostPolicy().choose(
        terminal,
        ("V001", "V002"),
    )

    assert decision is not None
    assert decision.vessel_id == "V002"
    assert decision.berth_id == "B01"
    assert decision.start_position_m == 0.0
