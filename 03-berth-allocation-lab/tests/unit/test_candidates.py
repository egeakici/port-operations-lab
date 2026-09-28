from __future__ import annotations

import pytest

from berth_allocation_lab.core import BAPPlacement, candidate_positions
from berth_allocation_lab.data import BAPVesselInput


def vessel(length: float = 200.0) -> BAPVesselInput:
    return BAPVesselInput("NEW", 0.0, length, 60.0)


def test_empty_quay_has_left_and_right_boundaries() -> None:
    assert candidate_positions(vessel(), (), 500.0, 10.0) == (0.0, 300.0)


def test_quay_length_vessel_has_one_candidate() -> None:
    assert candidate_positions(vessel(500.0), (), 500.0, 10.0) == (0.0,)


def test_existing_placement_induces_left_and_right_candidates() -> None:
    existing = (BAPPlacement("A", 250.0, 0.0, 100.0, 60.0),)
    assert candidate_positions(vessel(100.0), existing, 500.0, 10.0) == (
        0.0,
        140.0,
        360.0,
        400.0,
    )


def test_out_of_bounds_induced_candidates_are_filtered() -> None:
    existing = (
        BAPPlacement("A", 5.0, 0.0, 100.0, 60.0),
        BAPPlacement("B", 450.0, 0.0, 50.0, 60.0),
    )
    assert candidate_positions(vessel(100.0), existing, 500.0, 10.0) == (
        0.0,
        115.0,
        340.0,
        400.0,
    )


def test_duplicates_removed_and_order_independent() -> None:
    existing = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 60.0),
        BAPPlacement("B", 110.0, 0.0, 100.0, 60.0),
    )
    forward = candidate_positions(vessel(100.0), existing, 500.0, 10.0)
    reverse = candidate_positions(vessel(100.0), existing[::-1], 500.0, 10.0)
    assert forward == reverse == (0.0, 110.0, 220.0, 400.0)


def test_zero_clearance_candidates() -> None:
    existing = (BAPPlacement("A", 200.0, 0.0, 100.0, 60.0),)
    assert candidate_positions(vessel(100.0), existing, 500.0, 0.0) == (
        0.0,
        100.0,
        300.0,
        400.0,
    )


def test_fractional_candidates_preserve_continuous_geometry() -> None:
    existing = (BAPPlacement("A", 200.25, 0.0, 99.5, 60.0),)
    assert candidate_positions(vessel(100.25), existing, 500.5, 10.5) == (
        0.0,
        89.5,
        310.25,
        400.25,
    )


def test_numerical_near_duplicates_are_deduplicated() -> None:
    existing = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 60.0),
        BAPPlacement("B", 110.00000000000003, 0.0, 100.0, 60.0),
    )
    result = candidate_positions(vessel(100.0), existing, 500.0, 10.0)
    assert len([value for value in result if abs(value - 110.0) < 1e-6]) == 1
    assert result == tuple(sorted(result))


def test_every_candidate_is_in_bounds() -> None:
    existing = (
        BAPPlacement("A", 30.0, 0.0, 120.0, 60.0),
        BAPPlacement("B", 380.0, 0.0, 120.0, 60.0),
    )
    result = candidate_positions(vessel(125.5), existing, 500.0, 10.0)
    assert all(0.0 <= position <= 374.5 for position in result)


def test_oversized_vessel_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="exceeds berth length"):
        candidate_positions(vessel(500.001), (), 500.0, 10.0)

