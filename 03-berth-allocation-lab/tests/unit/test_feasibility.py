from __future__ import annotations

import pytest

from berth_allocation_lab.core import (
    BAPPlacement,
    ScheduleViolationCode,
    find_schedule_violations,
    is_placement_feasible,
    is_schedule_feasible,
)
from berth_allocation_lab.data import BAPVesselInput


def test_start_at_arrival_and_quay_walls_are_valid(
    manual_vessels: tuple[BAPVesselInput, ...],
) -> None:
    vessel = manual_vessels[0]

    assert is_placement_feasible(vessel, 0.0, 0.0, (), 500.0, 10.0)
    assert is_placement_feasible(vessel, 300.0, 0.0, (), 500.0, 10.0)


def test_start_before_arrival_is_invalid(
    manual_vessels: tuple[BAPVesselInput, ...],
) -> None:
    vessel = manual_vessels[2]
    assert not is_placement_feasible(vessel, 0.0, 24.0, (), 500.0, 10.0)


def test_exact_clearance_is_applied_once(
    manual_vessels: tuple[BAPVesselInput, ...],
) -> None:
    existing = (BAPPlacement("OTHER", 0.0, 0.0, 200.0, 100.0),)

    assert is_placement_feasible(
        manual_vessels[1], 210.0, 0.0, existing, 500.0, 10.0
    )
    assert not is_placement_feasible(
        manual_vessels[1], 209.0, 0.0, existing, 500.0, 10.0
    )


def test_many_non_conflicts_and_one_conflict(
    manual_vessels: tuple[BAPVesselInput, ...],
) -> None:
    vessel = manual_vessels[2]
    non_conflicts = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 25.0),
        BAPPlacement("B", 200.0, 25.0, 100.0, 60.0),
        BAPPlacement("C", 0.0, 200.0, 100.0, 50.0),
    )
    assert is_placement_feasible(
        vessel, 0.0, 25.0, non_conflicts, 500.0, 10.0
    )

    with_conflict = non_conflicts + (
        BAPPlacement("D", 100.0, 40.0, 100.0, 20.0),
    )
    assert not is_placement_feasible(
        vessel, 0.0, 25.0, with_conflict, 500.0, 10.0
    )


def test_existing_same_vessel_id_is_rejected(
    manual_vessels: tuple[BAPVesselInput, ...],
) -> None:
    vessel = manual_vessels[0]
    existing = (BAPPlacement("V001", 300.0, 0.0, 200.0, 100.0),)
    assert not is_placement_feasible(vessel, 0.0, 100.0, existing, 500.0, 10.0)


def test_schedule_validator_accepts_valid_complete_schedule(
    manual_vessels: tuple[BAPVesselInput, ...],
) -> None:
    vessels = (manual_vessels[0], manual_vessels[1])
    placements = (
        BAPPlacement("V001", 0.0, 0.0, 200.0, 100.0),
        BAPPlacement("V002", 210.0, 0.0, 200.0, 100.0),
    )
    assert is_schedule_feasible(vessels, placements, 500.0, 10.0)


def test_schedule_validator_reports_core_violations() -> None:
    vessels = (
        BAPVesselInput("A", 10.0, 200.0, 100.0),
        BAPVesselInput("B", 0.0, 200.0, 100.0),
        BAPVesselInput("C", 0.0, 50.0, 10.0),
    )
    placements = (
        BAPPlacement("A", -1.0, 0.0, 200.0, 100.0),
        BAPPlacement("B", 100.0, 0.0, 200.0, 100.0),
    )

    codes = {
        violation.code
        for violation in find_schedule_violations(
            vessels, placements, berth_length_m=500.0, min_clearance_m=10.0
        )
    }
    assert codes == {
        ScheduleViolationCode.OUT_OF_BOUNDS,
        ScheduleViolationCode.BEFORE_ARRIVAL,
        ScheduleViolationCode.SPACE_TIME_CONFLICT,
        ScheduleViolationCode.MISSING_PLACEMENT,
    }


def test_partial_schedule_can_skip_completeness_check() -> None:
    vessels = (BAPVesselInput("A", 0.0, 100.0, 10.0),)
    assert is_schedule_feasible(
        vessels,
        (),
        berth_length_m=500.0,
        min_clearance_m=10.0,
        require_complete=False,
    )


def test_schedule_validator_rejects_mismatched_placement() -> None:
    vessels = (BAPVesselInput("A", 0.0, 100.0, 10.0),)
    placements = (BAPPlacement("A", 0.0, 0.0, 101.0, 10.0),)
    violations = find_schedule_violations(vessels, placements, 500.0, 10.0)
    assert ScheduleViolationCode.VESSEL_MISMATCH in {
        violation.code for violation in violations
    }

