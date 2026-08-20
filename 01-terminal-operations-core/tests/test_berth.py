from datetime import datetime

import pytest

from terminal_core.berth import(Berth, BerthOccupancy)
from terminal_core.exceptions import(
    BerthPlacementError,
    BerthValidationError,
    VesselNotFoundAtBerthError,
)
from terminal_core.vessel import Vessel

def create_vessel(
        vessel_id: str,
        length_m: float,
) -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=length_m,
        eta=datetime(2026, 8, 1, 10, 0),
        workload_moves=1000,
        priority=2,
        max_cranes=3,
    )

def test_valid_berth_is_created() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
        min_clearance_m=25.0,
    )

    assert berth.berth_id == "B01"
    assert berth.start_position_m == 0.0
    assert berth.end_position_m == 1200.0
    assert berth.occupancy_count == 0

def test_empty_berth_id_is_rejected()-> None:
    with pytest.raises(
        BerthValidationError,
        match="Berth ID cannot be empty.",
    ):
        Berth(
            berth_id= "   ",
            length_m=1200.0,
        )

def test_negative_berth_length_is_rejected() -> None:
    with pytest.raises(
        BerthValidationError,
        match="Berth length must be greater than zero.",
    ):
        Berth(
            berth_id="B01",
            length_m=-100.0,
        )


def test_negative_clearance_is_rejected() -> None:
    with pytest.raises(
        BerthValidationError,
        match="Minimum clearance cannot be negative.",
    ):
        Berth(
            berth_id="B01",
            length_m=1200.0,
            min_clearance_m=-10.0,
        )

def test_occupancy_interval_is_calculated() -> None:
    vessel = create_vessel(
        vessel_id="V001",
        length_m=280.0,
    )

    occupancy = BerthOccupancy(
        vessel=vessel,
        start_position_m=100.0,
    )

    assert occupancy.start_position_m == 100.0
    assert occupancy.end_position_m == 380.0
    assert occupancy.interval_m == (100.0, 380.0)

def test_overlapping_occupancies_are_detected() -> None:
    vessel1 = create_vessel("V001", 280.0)
    vessel2 = create_vessel("V002", 315.5)

    first = BerthOccupancy(
        vessel=vessel1,
        start_position_m=100.0,
    )

    second = BerthOccupancy(
        vessel=vessel2,
        start_position_m=350.0,
    )

    assert first.overlaps_with(second)
    assert second.overlaps_with(first)


def test_non_overlapping_occupancies_are_detected() -> None:
    vessel1 = create_vessel("V001", 280.0)
    vessel2 = create_vessel("V002", 315.5)

    first = BerthOccupancy(
        vessel=vessel1,
        start_position_m=100.0,
    )

    second = BerthOccupancy(
        vessel=vessel2,
        start_position_m=405.0,
    )

    assert not first.overlaps_with(second)
    assert first.gap_to(second) == 25.0

def test_vessels_can_be_placed_safely() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
        min_clearance_m=25.0,
    )

    vessel1 = create_vessel("V001", 280.0)
    vessel2 = create_vessel("V002", 315.5)

    berth.place_vessel(
        vessel=vessel1,
        start_position_m=100.0,
    )

    berth.place_vessel(
        vessel=vessel2,
        start_position_m=405.0,
    )

    assert berth.occupancy_count == 2
    assert berth.contains_vessel("V001")
    assert berth.contains_vessel("V002")

def test_insufficient_clearance_is_rejected() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
        min_clearance_m=25.0,
    )

    vessel1 = create_vessel("V001", 280.0)
    vessel2 = create_vessel("V002", 315.5)

    berth.place_vessel(
        vessel=vessel1,
        start_position_m=100.0,
    )

    with pytest.raises(
        BerthPlacementError,
        match="does not have safe clearance",
    ):
        berth.place_vessel(
            vessel=vessel2,
            start_position_m=390.0,
        )

    assert berth.occupancy_count == 1

def test_vessel_outside_berth_is_rejected() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
    )

    vessel = create_vessel(
        vessel_id="V001",
        length_m=315.5,
    )

    with pytest.raises(
        BerthPlacementError,
        match="does not fit within",
    ):
        berth.place_vessel(
            vessel=vessel,
            start_position_m=900.0,
        )

    assert berth.occupancy_count == 0

def test_same_vessel_cannot_be_placed_twice() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
    )

    vessel = create_vessel(
        vessel_id="V001",
        length_m=280.0,
    )

    berth.place_vessel(
        vessel=vessel,
        start_position_m=100.0,
    )

    with pytest.raises(
        BerthPlacementError,
        match="is already placed",
    ):
        berth.place_vessel(
            vessel=vessel,
            start_position_m=500.0,
        )

def test_vessel_can_be_removed() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
    )

    vessel = create_vessel(
        vessel_id="V001",
        length_m=280.0,
    )

    berth.place_vessel(
        vessel=vessel,
        start_position_m=100.0,
    )

    removed = berth.remove_vessel("V001")

    assert removed.vessel.vessel_id == "V001"
    assert berth.occupancy_count == 0
    assert not berth.contains_vessel("V001")

def test_unknown_vessel_cannot_be_removed() -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
    )

    with pytest.raises(
        VesselNotFoundAtBerthError,
        match="Vessel V999 is not placed",
    ):
        berth.remove_vessel("V999")

def test_berth_json_round_trip(tmp_path) -> None:
    berth = Berth(
        berth_id="B01",
        length_m=1200.0,
        min_clearance_m=25.0,
    )

    vessel1 = create_vessel("V001", 280.0)
    vessel2 = create_vessel("V002", 315.5)

    berth.place_vessel(
        vessel=vessel1,
        start_position_m=100.0,
    )

    berth.place_vessel(
        vessel=vessel2,
        start_position_m=405.0,
    )

    file_path = tmp_path / "berth.json"

    berth.save_to_json(file_path)
    loaded_berth = Berth.load_from_json(file_path)

    assert file_path.exists()
    assert loaded_berth.berth_id == berth.berth_id
    assert loaded_berth.length_m == berth.length_m
    assert loaded_berth.min_clearance_m == 25.0
    assert loaded_berth.occupancy_count == 2

    assert (
        loaded_berth.occupancies[0].interval_m
        == (100.0, 380.0)
    )

    assert (
        loaded_berth.occupancies[1].interval_m
        == (405.0, 720.5)
    )