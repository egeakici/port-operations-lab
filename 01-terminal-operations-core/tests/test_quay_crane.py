from datetime import datetime

import pytest

from terminal_core.exceptions import (
    CraneAssignmentError,
    CraneOperationError,
    QuayCraneValidationError,
)
from terminal_core.quay_crane import (
    CraneStatus,
    QuayCrane,
)
from terminal_core.vessel import Vessel


def create_vessel(
    vessel_id: str = "V001",
) -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=280.0,
        eta=datetime(2026, 8, 2, 9, 0),
        workload_moves=1500,
        priority=2,
        max_cranes=3,
    )


def create_crane(
    crane_id: str = "QC01",
) -> QuayCrane:
    return QuayCrane(
        crane_id=crane_id,
        position_m=250.0,
        moves_per_hour=30.0,
    )


def test_valid_crane_is_created() -> None:
    crane = create_crane()

    assert crane.crane_id == "QC01"
    assert crane.position_m == 250.0
    assert crane.moves_per_hour == 30.0
    assert crane.status == CraneStatus.AVAILABLE
    assert crane.assigned_vessel_id is None


def test_empty_crane_id_is_rejected() -> None:
    with pytest.raises(
        QuayCraneValidationError,
        match="Crane ID cannot be empty.",
    ):
        QuayCrane(
            crane_id="   ",
            position_m=250.0,
            moves_per_hour=30.0,
        )


def test_negative_position_is_rejected() -> None:
    with pytest.raises(
        QuayCraneValidationError,
        match="Crane position cannot be negative.",
    ):
        QuayCrane(
            crane_id="QC01",
            position_m=-10.0,
            moves_per_hour=30.0,
        )


def test_zero_productivity_is_rejected() -> None:
    with pytest.raises(
        QuayCraneValidationError,
        match="Crane productivity must be greater than zero.",
    ):
        QuayCrane(
            crane_id="QC01",
            position_m=250.0,
            moves_per_hour=0.0,
        )


def test_crane_can_be_assigned_to_vessel() -> None:
    crane = create_crane()
    vessel = create_vessel()

    crane.assign_to_vessel(vessel)

    assert crane.status == CraneStatus.ASSIGNED
    assert crane.assigned_vessel_id == "V001"


def test_crane_cannot_be_assigned_twice() -> None:
    crane = create_crane()
    vessel1 = create_vessel("V001")
    vessel2 = create_vessel("V002")

    crane.assign_to_vessel(vessel1)

    with pytest.raises(
        CraneAssignmentError,
        match="is not available for assignment",
    ):
        crane.assign_to_vessel(vessel2)

    assert crane.assigned_vessel_id == "V001"


def test_complete_operation_lifecycle() -> None:
    crane = create_crane()
    vessel = create_vessel()

    crane.assign_to_vessel(vessel)
    crane.start_operation()

    assert crane.status == CraneStatus.OPERATING
    assert crane.assigned_vessel_id == "V001"

    crane.stop_operation()

    assert crane.status == CraneStatus.ASSIGNED

    released_vessel_id = crane.release_from_vessel()

    assert released_vessel_id == "V001"
    assert crane.status == CraneStatus.AVAILABLE
    assert crane.assigned_vessel_id is None


def test_unassigned_crane_cannot_start_operation() -> None:
    crane = create_crane()

    with pytest.raises(
        CraneOperationError,
        match="cannot start operation",
    ):
        crane.start_operation()


def test_operating_crane_can_fail_and_be_repaired() -> None:
    crane = create_crane()
    vessel = create_vessel()

    crane.assign_to_vessel(vessel)
    crane.start_operation()

    interrupted_vessel_id = crane.mark_failed()

    assert interrupted_vessel_id == "V001"
    assert crane.status == CraneStatus.FAILED
    assert crane.assigned_vessel_id is None

    crane.repair()

    assert crane.status == CraneStatus.AVAILABLE
    assert crane.assigned_vessel_id is None


def test_crane_maintenance_lifecycle() -> None:
    crane = create_crane()

    crane.start_maintenance()

    assert crane.status == CraneStatus.MAINTENANCE
    assert crane.assigned_vessel_id is None

    crane.finish_maintenance()

    assert crane.status == CraneStatus.AVAILABLE


def test_assigned_crane_cannot_enter_maintenance() -> None:
    crane = create_crane()
    vessel = create_vessel()

    crane.assign_to_vessel(vessel)

    with pytest.raises(
        CraneOperationError,
        match="cannot enter maintenance",
    ):
        crane.start_maintenance()


def test_crane_can_move_when_available() -> None:
    crane = create_crane()

    travelled_distance = crane.move_to(600.0)

    assert travelled_distance == 350.0
    assert crane.position_m == 600.0


def test_operating_crane_cannot_move() -> None:
    crane = create_crane()
    vessel = create_vessel()

    crane.assign_to_vessel(vessel)
    crane.start_operation()

    with pytest.raises(
        CraneOperationError,
        match="cannot move",
    ):
        crane.move_to(600.0)

    assert crane.position_m == 250.0


def test_nominal_moves_are_estimated() -> None:
    crane = create_crane()

    estimated_moves = crane.estimate_moves(5.0)

    assert estimated_moves == 150.0


def test_negative_operation_hours_are_rejected() -> None:
    crane = create_crane()

    with pytest.raises(
        QuayCraneValidationError,
        match="Operation hours cannot be negative.",
    ):
        crane.estimate_moves(-1.0)


def test_operating_crane_json_round_trip(tmp_path) -> None:
    crane = create_crane()
    vessel = create_vessel()

    crane.assign_to_vessel(vessel)
    crane.move_to(500.0)
    crane.start_operation()

    file_path = tmp_path / "quay_crane.json"

    crane.save_to_json(file_path)
    loaded_crane = QuayCrane.load_from_json(file_path)

    assert file_path.exists()
    assert loaded_crane.crane_id == "QC01"
    assert loaded_crane.position_m == 500.0
    assert loaded_crane.moves_per_hour == 30.0
    assert loaded_crane.status == CraneStatus.OPERATING
    assert loaded_crane.assigned_vessel_id == "V001"


def test_invalid_restored_state_is_rejected() -> None:
    invalid_data = {
        "crane_id": "QC01",
        "position_m": 250.0,
        "moves_per_hour": 30.0,
        "status": "operating",
        "assigned_vessel_id": None,
    }

    with pytest.raises(
        QuayCraneValidationError,
        match="requires an assigned vessel",
    ):
        QuayCrane.from_dict(invalid_data)