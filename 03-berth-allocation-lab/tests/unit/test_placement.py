from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from berth_allocation_lab.core import BAPPlacement


def test_placement_is_immutable_with_derived_edges() -> None:
    placement = BAPPlacement("V001", 12.5, 37.75, 100.25, 42.5)

    assert placement.berth_end_position_m == pytest.approx(112.75)
    assert placement.service_end_time_min == pytest.approx(80.25)
    with pytest.raises(FrozenInstanceError):
        placement.berth_position_m = 20.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vessel_id": ""},
        {"berth_position_m": float("nan")},
        {"berth_start_time_min": float("inf")},
        {"length_m": 0.0},
        {"service_time_min": -1.0},
        {
            "berth_position_m": 1e308,
            "length_m": 1e308,
        },
        {
            "berth_start_time_min": 1e308,
            "service_time_min": 1e308,
        },
    ],
)
def test_placement_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "vessel_id": "V001",
        "berth_position_m": 0.0,
        "berth_start_time_min": 0.0,
        "length_m": 100.0,
        "service_time_min": 60.0,
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        BAPPlacement(**values)  # type: ignore[arg-type]

