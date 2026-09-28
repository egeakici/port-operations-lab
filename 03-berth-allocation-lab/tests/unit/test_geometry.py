from __future__ import annotations

import pytest

from berth_allocation_lab.core import (
    BAPPlacement,
    are_spatially_separated,
    is_within_quay,
    space_time_conflict,
    time_intervals_overlap,
)


def placement(
    vessel_id: str,
    position: float,
    start: float = 0.0,
    length: float = 200.0,
    service: float = 100.0,
) -> BAPPlacement:
    return BAPPlacement(vessel_id, position, start, length, service)


@pytest.mark.parametrize(
    ("position", "length", "quay", "expected"),
    [
        (0.0, 500.0, 500.0, True),
        (300.0, 200.0, 500.0, True),
        (125.5, 200.25, 500.0, True),
        (-0.001, 100.0, 500.0, False),
        (300.001, 200.0, 500.0, False),
        (0.0, 500.001, 500.0, False),
        (0.0, 0.0, 500.0, False),
        (float("nan"), 100.0, 500.0, False),
    ],
)
def test_quay_boundaries(
    position: float,
    length: float,
    quay: float,
    expected: bool,
) -> None:
    assert is_within_quay(position, length, quay) is expected


@pytest.mark.parametrize(
    ("interval_a", "interval_b", "expected"),
    [
        ((0.0, 10.0), (10.0, 20.0), False),
        ((5.0, 10.0), (0.0, 5.0), False),
        ((0.0, 10.0), (9.0, 20.0), True),
        ((5.0, 10.0), (4.0, 6.0), True),
        ((2.0, 8.0), (0.0, 10.0), True),
        ((0.0, 10.0), (0.0, 10.0), True),
    ],
)
def test_half_open_time_overlap(
    interval_a: tuple[float, float],
    interval_b: tuple[float, float],
    expected: bool,
) -> None:
    assert time_intervals_overlap(*interval_a, *interval_b) is expected


@pytest.mark.parametrize("interval", [(0.0, 0.0), (2.0, 1.0)])
def test_time_overlap_rejects_non_positive_intervals(
    interval: tuple[float, float],
) -> None:
    with pytest.raises(ValueError, match="positive duration"):
        time_intervals_overlap(*interval, 10.0, 20.0)


def test_exact_clearance_is_spatially_separated() -> None:
    assert are_spatially_separated(placement("A", 0.0), placement("B", 210.0), 10.0)


def test_insufficient_clearance_is_not_spatially_separated() -> None:
    assert not are_spatially_separated(
        placement("A", 0.0),
        placement("B", 209.999),
        10.0,
    )


def test_zero_clearance_allows_touching_hulls() -> None:
    assert are_spatially_separated(placement("A", 0.0), placement("B", 200.0), 0.0)


def test_space_time_conflict_requires_both_dimensions() -> None:
    left = placement("A", 0.0, start=0.0)
    spatially_separate = placement("B", 210.0, start=0.0)
    temporally_separate = placement("C", 0.0, start=100.0)
    conflict = placement("D", 209.0, start=50.0)

    assert not space_time_conflict(left, spatially_separate, 10.0)
    assert not space_time_conflict(left, temporally_separate, 10.0)
    assert space_time_conflict(left, conflict, 10.0)

