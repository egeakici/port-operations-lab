from datetime import datetime

import pytest

from src.terminal_core.exceptions import (
    InvalidStatusTransitionError,
    VesselValidationError,
)
from src.terminal_core.vessel import Vessel, VesselStatus


def test_valid_vessel_is_created() -> None:
    vessel = Vessel(
        vessel_id="V001",
        length_m=280.0,
        eta=datetime(2026, 8, 2, 9, 0),
        workload_moves=1500,
        priority=2,
        max_cranes=3,
    )

    assert vessel.vessel_id == "V001"
    assert vessel.length_m == 280.0
    assert vessel.workload_moves == 1500
    assert vessel.status == VesselStatus.APPROACHING


def test_negative_length_is_rejected() -> None:
    with pytest.raises(
        VesselValidationError,
        match="Vessel length must be greater than zero.",
    ):
        Vessel(
            vessel_id="V002",
            length_m=-100.0,
            eta=datetime(2026, 8, 3, 14, 30),
            workload_moves=1000,
            priority=2,
            max_cranes=2,
        )


def test_empty_vessel_id_is_rejected() -> None:
    with pytest.raises(
        VesselValidationError,
        match="Vessel ID cannot be empty.",
    ):
        Vessel(
            vessel_id="   ",
            length_m=200.0,
            eta=datetime(2026, 8, 3, 14, 30),
            workload_moves=500,
            priority=2,
            max_cranes=2,
        )


def test_negative_workload_is_rejected() -> None:
    with pytest.raises(
        VesselValidationError,
        match="Workload moves cannot be negative.",
    ):
        Vessel(
            vessel_id="V003",
            length_m=200.0,
            eta=datetime(2026, 8, 3, 14, 30),
            workload_moves=-100,
            priority=2,
            max_cranes=2,
        )


def test_invalid_priority_is_rejected() -> None:
    with pytest.raises(
        VesselValidationError,
        match="Vessel priority must be between 1 and 3.",
    ):
        Vessel(
            vessel_id="V004",
            length_m=200.0,
            eta=datetime(2026, 8, 3, 14, 30),
            workload_moves=500,
            priority=4,
            max_cranes=2,
        )


def test_zero_max_cranes_is_rejected() -> None:
    with pytest.raises(
        VesselValidationError,
        match="Maximum crane count must be at least 1.",
    ):
        Vessel(
            vessel_id="V005",
            length_m=200.0,
            eta=datetime(2026, 8, 3, 14, 30),
            workload_moves=500,
            priority=2,
            max_cranes=0,
        )


def test_valid_status_transition() -> None:
    vessel = Vessel(
        vessel_id="V006",
        length_m=250.0,
        eta=datetime(2026, 8, 4, 10, 0),
        workload_moves=1200,
        priority=2,
        max_cranes=3,
    )

    vessel.transition_to(VesselStatus.WAITING)

    assert vessel.status == VesselStatus.WAITING


def test_complete_vessel_lifecycle() -> None:
    vessel = Vessel(
        vessel_id="V007",
        length_m=310.0,
        eta=datetime(2026, 8, 5, 8, 0),
        workload_moves=2100,
        priority=3,
        max_cranes=4,
    )

    vessel.transition_to(VesselStatus.WAITING)
    vessel.transition_to(VesselStatus.BERTHED)
    vessel.transition_to(VesselStatus.OPERATING)
    vessel.transition_to(VesselStatus.DEPARTED)

    assert vessel.status == VesselStatus.DEPARTED


def test_invalid_status_transition_is_rejected() -> None:
    vessel = Vessel(
        vessel_id="V008",
        length_m=270.0,
        eta=datetime(2026, 8, 5, 12, 0),
        workload_moves=1600,
        priority=2,
        max_cranes=3,
    )

    vessel.transition_to(VesselStatus.WAITING)
    vessel.transition_to(VesselStatus.BERTHED)

    with pytest.raises(
        InvalidStatusTransitionError,
        match="Invalid status transition: berthed -> departed",
    ):
        vessel.transition_to(VesselStatus.DEPARTED)


def test_vessel_converts_to_dictionary() -> None:
    vessel = Vessel(
        vessel_id="V009",
        length_m=295.5,
        eta=datetime(2026, 8, 6, 11, 30),
        workload_moves=1800,
        priority=2,
        max_cranes=3,
    )

    data = vessel.to_dict()

    assert data["vessel_id"] == "V009"
    assert data["length_m"] == 295.5
    assert data["eta"] == "2026-08-06T11:30:00"
    assert data["status"] == "approaching"


def test_vessel_dictionary_round_trip() -> None:
    original_vessel = Vessel(
        vessel_id="V010",
        length_m=330.0,
        eta=datetime(2026, 8, 7, 9, 45),
        workload_moves=2400,
        priority=3,
        max_cranes=4,
    )

    original_vessel.transition_to(VesselStatus.WAITING)

    vessel_data = original_vessel.to_dict()
    restored_vessel = Vessel.from_dict(vessel_data)

    assert restored_vessel == original_vessel
    assert restored_vessel is not original_vessel
    assert isinstance(restored_vessel.eta, datetime)
    assert isinstance(restored_vessel.status, VesselStatus)


def test_vessel_json_round_trip(tmp_path) -> None:
    original_vessel = Vessel(
        vessel_id="V011",
        length_m=300.0,
        eta=datetime(2026, 8, 8, 15, 0),
        workload_moves=2000,
        priority=2,
        max_cranes=3,
    )

    original_vessel.transition_to(VesselStatus.WAITING)

    file_path = tmp_path / "vessel.json"

    original_vessel.save_to_json(file_path)
    loaded_vessel = Vessel.load_from_json(file_path)

    assert file_path.exists()
    assert loaded_vessel == original_vessel
    assert loaded_vessel.status == VesselStatus.WAITING