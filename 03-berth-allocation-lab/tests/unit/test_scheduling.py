from __future__ import annotations

import pytest

from berth_allocation_lab.core import BAPPlacement, earliest_feasible_start
from berth_allocation_lab.data import BAPVesselInput


def vessel(
    arrival: float = 0.0,
    service: float = 100.0,
    length: float = 100.0,
) -> BAPVesselInput:
    return BAPVesselInput("NEW", arrival, length, service)


def test_empty_schedule_starts_at_arrival() -> None:
    assert earliest_feasible_start(vessel(12.5), 0.0, (), 500.0, 10.0) == 12.5


def test_same_space_blocker_delays_to_its_end() -> None:
    blockers = (BAPPlacement("A", 0.0, 0.0, 100.0, 60.0),)
    assert earliest_feasible_start(vessel(), 0.0, blockers, 500.0, 10.0) == 60.0


def test_blocker_ending_at_arrival_does_not_delay() -> None:
    blockers = (BAPPlacement("A", 0.0, 0.0, 100.0, 60.0),)
    assert earliest_feasible_start(vessel(arrival=60.0), 0.0, blockers, 500.0, 10.0) == 60.0


def test_spatially_distant_vessel_does_not_delay() -> None:
    blockers = (BAPPlacement("A", 200.0, 0.0, 100.0, 500.0),)
    assert earliest_feasible_start(vessel(), 0.0, blockers, 500.0, 10.0) == 0.0


def test_chained_blockers_jump_to_true_earliest_start() -> None:
    blockers = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 60.0),
        BAPPlacement("B", 0.0, 60.0, 100.0, 90.0),
    )
    assert earliest_feasible_start(vessel(), 0.0, blockers, 500.0, 10.0) == 150.0


def test_several_overlapping_blockers_do_not_skip_earlier_event() -> None:
    blockers = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 30.0),
        BAPPlacement("B", 0.0, 20.0, 100.0, 30.0),
        BAPPlacement("C", 0.0, 49.0, 100.0, 21.0),
    )
    assert earliest_feasible_start(
        vessel(service=25.0), 0.0, blockers, 500.0, 10.0
    ) == 70.0


def test_unsorted_blockers_give_same_result() -> None:
    blockers = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 60.0),
        BAPPlacement("B", 0.0, 60.0, 100.0, 90.0),
    )
    forward = earliest_feasible_start(vessel(), 0.0, blockers, 500.0, 10.0)
    reverse = earliest_feasible_start(vessel(), 0.0, blockers[::-1], 500.0, 10.0)
    assert forward == reverse == 150.0


def test_arrival_after_all_blockers_is_unchanged() -> None:
    blockers = (BAPPlacement("A", 0.0, 0.0, 100.0, 60.0),)
    assert earliest_feasible_start(vessel(arrival=100.0), 0.0, blockers, 500.0, 10.0) == 100.0


def test_fractional_continuous_times_are_preserved() -> None:
    blockers = (BAPPlacement("A", 0.0, 12.5, 100.0, 25.25),)
    result = earliest_feasible_start(
        vessel(arrival=12.5, service=10.125),
        0.0,
        blockers,
        500.0,
        10.0,
    )
    assert result == pytest.approx(37.75)


def test_invalid_fixed_position_raises() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        earliest_feasible_start(vessel(length=200.0), 301.0, (), 500.0, 10.0)

