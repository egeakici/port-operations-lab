from __future__ import annotations

import pytest

from berth_allocation_lab.core import (
    BAPPlacement,
    total_waiting_time,
    turnaround_time,
    waiting_time,
)
from berth_allocation_lab.data import BAPVesselInput


def test_waiting_and_turnaround_are_manually_calculable() -> None:
    vessel = BAPVesselInput("A", 10.0, 100.0, 30.0)
    placement = BAPPlacement("A", 0.0, 25.0, 100.0, 30.0)

    assert waiting_time(vessel, placement) == 15.0
    assert turnaround_time(vessel, placement) == 45.0


def test_total_waiting_requires_and_sums_complete_schedule() -> None:
    vessels = (
        BAPVesselInput("A", 0.0, 100.0, 30.0),
        BAPVesselInput("B", 10.0, 100.0, 40.0),
    )
    placements = (
        BAPPlacement("B", 110.0, 25.0, 100.0, 40.0),
        BAPPlacement("A", 0.0, 5.0, 100.0, 30.0),
    )
    assert total_waiting_time(vessels, placements) == 20.0


def test_missing_placement_raises() -> None:
    vessels = (
        BAPVesselInput("A", 0.0, 100.0, 30.0),
        BAPVesselInput("B", 0.0, 100.0, 30.0),
    )
    placements = (BAPPlacement("A", 0.0, 0.0, 100.0, 30.0),)
    with pytest.raises(ValueError, match="Missing placements.*B"):
        total_waiting_time(vessels, placements)


def test_duplicate_placement_raises() -> None:
    vessel = BAPVesselInput("A", 0.0, 100.0, 30.0)
    placements = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 30.0),
        BAPPlacement("A", 0.0, 30.0, 100.0, 30.0),
    )
    with pytest.raises(ValueError, match="Duplicate placement"):
        total_waiting_time((vessel,), placements)


def test_prearrival_or_mismatched_placement_raises() -> None:
    vessel = BAPVesselInput("A", 10.0, 100.0, 30.0)
    before_arrival = BAPPlacement("A", 0.0, 9.0, 100.0, 30.0)
    mismatch = BAPPlacement("A", 0.0, 10.0, 101.0, 30.0)

    with pytest.raises(ValueError, match="before vessel arrival"):
        waiting_time(vessel, before_arrival)
    with pytest.raises(ValueError, match="physical values"):
        turnaround_time(vessel, mismatch)


def test_waiting_for_tolerance_valid_placement_is_non_negative() -> None:
    vessel = BAPVesselInput("A", 10.0, 100.0, 30.0)
    placement = BAPPlacement("A", 0.0, 10.0 - 5e-10, 100.0, 30.0)
    assert waiting_time(vessel, placement) == 0.0

