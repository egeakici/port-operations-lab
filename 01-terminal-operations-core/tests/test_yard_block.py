import pytest

from src.terminal_core.exceptions import (
    InvalidYardBlockStatusTransitionError,
    YardBlockValidationError,
    YardCapacityError,
    YardCompatibilityError,
    YardOperationError,
    YardReservationError,
)
from src.terminal_core.yard_block import (
    YardBlock,
    YardBlockStatus,
    YardCapability,
)


def create_general_block(
    block_id: str = "A01",
    capacity_teu: float = 800.0,
) -> YardBlock:
    return YardBlock(
        block_id=block_id,
        capacity_teu=capacity_teu,
        capabilities={
            YardCapability.GENERAL,
        },
    )


def create_reefer_block(
    block_id: str = "R01",
    capacity_teu: float = 600.0,
) -> YardBlock:
    return YardBlock(
        block_id=block_id,
        capacity_teu=capacity_teu,
        capabilities={
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        },
    )


def test_valid_yard_block_is_created() -> None:
    block = create_general_block()

    assert block.block_id == "A01"
    assert block.capacity_teu == 800.0
    assert block.capabilities == {
        YardCapability.GENERAL,
    }
    assert block.status == YardBlockStatus.OPEN
    assert block.stored_groups == {}
    assert block.reservations == {}


def test_new_yard_block_is_empty() -> None:
    block = create_general_block()

    assert block.occupied_teu == 0
    assert block.reserved_teu == 0
    assert block.available_teu == 800.0
    assert block.occupancy_ratio == 0
    assert block.planned_occupancy_ratio == 0


def test_empty_block_id_is_rejected() -> None:
    with pytest.raises(
        YardBlockValidationError,
        match="Yard block ID cannot be empty",
    ):
        YardBlock(
            block_id="   ",
            capacity_teu=800.0,
        )


def test_zero_capacity_is_rejected() -> None:
    with pytest.raises(
        YardBlockValidationError,
        match="capacity must be greater than zero",
    ):
        YardBlock(
            block_id="A01",
            capacity_teu=0.0,
        )


def test_negative_capacity_is_rejected() -> None:
    with pytest.raises(
        YardBlockValidationError,
        match="capacity must be greater than zero",
    ):
        YardBlock(
            block_id="A01",
            capacity_teu=-100.0,
        )


def test_empty_capability_set_is_rejected() -> None:
    with pytest.raises(
        YardBlockValidationError,
        match="at least one capability",
    ):
        YardBlock(
            block_id="A01",
            capacity_teu=800.0,
            capabilities=set(),
        )


def test_invalid_capability_value_is_rejected() -> None:
    with pytest.raises(
        YardBlockValidationError,
        match="YardCapability values",
    ):
        YardBlock(
            block_id="A01",
            capacity_teu=800.0,
            capabilities={
                "general",
            },
        )


def test_general_block_supports_general_requirement() -> None:
    block = create_general_block()

    result = block.supports_requirements(
        {
            YardCapability.GENERAL,
        }
    )

    assert result is True


def test_general_block_does_not_support_reefer() -> None:
    block = create_general_block()

    result = block.supports_requirements(
        {
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        }
    )

    assert result is False


def test_reefer_block_supports_reefer_requirements() -> None:
    block = create_reefer_block()

    result = block.supports_requirements(
        {
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        }
    )

    assert result is True


def test_block_can_be_closed_and_reopened() -> None:
    block = create_general_block()

    block.close()

    assert block.status == YardBlockStatus.CLOSED

    block.reopen()

    assert block.status == YardBlockStatus.OPEN


def test_block_maintenance_lifecycle() -> None:
    block = create_general_block()

    block.start_maintenance()

    assert block.status == YardBlockStatus.MAINTENANCE

    block.finish_maintenance()

    assert block.status == YardBlockStatus.OPEN


def test_closed_block_can_enter_maintenance() -> None:
    block = create_general_block()

    block.close()
    block.start_maintenance()

    assert block.status == YardBlockStatus.MAINTENANCE


def test_maintenance_cannot_start_twice() -> None:
    block = create_general_block()

    block.start_maintenance()

    with pytest.raises(
        YardOperationError,
        match="cannot enter maintenance",
    ):
        block.start_maintenance()


def test_invalid_status_transition_is_rejected() -> None:
    block = create_general_block()

    block.start_maintenance()

    with pytest.raises(
        InvalidYardBlockStatusTransitionError,
        match="maintenance -> closed",
    ):
        block._transition_to(
            YardBlockStatus.CLOSED
        )


def test_capacity_can_be_reserved() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=150.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    assert block.reservations == {
        "G001": 150.0,
    }
    assert block.stored_groups == {}
    assert block.occupied_teu == 0
    assert block.reserved_teu == 150.0
    assert block.available_teu == 650.0


def test_planned_occupancy_includes_reservations() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=200.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    assert block.occupancy_ratio == 0
    assert block.planned_occupancy_ratio == 0.25


def test_reservation_cannot_exceed_available_capacity() -> None:
    block = create_general_block(
        capacity_teu=200.0
    )

    block.reserve_capacity(
        group_id="G001",
        teu=150.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    with pytest.raises(
        YardCapacityError,
        match="does not have enough available capacity",
    ):
        block.reserve_capacity(
            group_id="G002",
            teu=100.0,
            required_capabilities={
                YardCapability.GENERAL,
            },
        )

    assert block.reservations == {
        "G001": 150.0,
    }
    assert block.available_teu == 50.0


def test_incompatible_reservation_is_rejected() -> None:
    block = create_general_block()

    with pytest.raises(
        YardCompatibilityError,
        match="does not support",
    ):
        block.reserve_capacity(
            group_id="G001",
            teu=100.0,
            required_capabilities={
                YardCapability.GENERAL,
                YardCapability.REEFER_POWER,
            },
        )

    assert block.reservations == {}


def test_duplicate_reservation_is_rejected() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=100.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    with pytest.raises(
        YardReservationError,
        match="already has a reservation",
    ):
        block.reserve_capacity(
            group_id="G001",
            teu=50.0,
            required_capabilities={
                YardCapability.GENERAL,
            },
        )

    assert block.reservations["G001"] == 100.0


def test_closed_block_cannot_accept_reservations() -> None:
    block = create_general_block()

    block.close()

    with pytest.raises(
        YardOperationError,
        match="cannot accept reservations",
    ):
        block.reserve_capacity(
            group_id="G001",
            teu=100.0,
            required_capabilities={
                YardCapability.GENERAL,
            },
        )


def test_reservation_can_be_cancelled() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=150.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    cancelled_teu = block.cancel_reservation(
        "G001"
    )

    assert cancelled_teu == 150.0
    assert block.reservations == {}
    assert block.reserved_teu == 0
    assert block.available_teu == 800.0


def test_reservation_can_be_cancelled_while_closed() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=150.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    block.close()

    cancelled_teu = block.cancel_reservation(
        "G001"
    )

    assert cancelled_teu == 150.0
    assert block.reservations == {}
    assert block.status == YardBlockStatus.CLOSED


def test_missing_reservation_cannot_be_cancelled() -> None:
    block = create_general_block()

    with pytest.raises(
        YardReservationError,
        match="has no reservation",
    ):
        block.cancel_reservation(
            "G999"
        )


def test_reservation_can_be_committed() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=150.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    committed_teu = block.commit_reservation(
        "G001"
    )

    assert committed_teu == 150.0
    assert block.reservations == {}
    assert block.stored_groups == {
        "G001": 150.0,
    }
    assert block.occupied_teu == 150.0
    assert block.reserved_teu == 0
    assert block.available_teu == 650.0


def test_commit_does_not_change_available_capacity() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=200.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    available_before = block.available_teu

    block.commit_reservation("G001")

    available_after = block.available_teu

    assert available_before == 600.0
    assert available_after == 600.0


def test_reservation_cannot_be_committed_while_closed() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=100.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    block.close()

    with pytest.raises(
        YardOperationError,
        match="cannot receive container groups",
    ):
        block.commit_reservation(
            "G001"
        )

    assert block.reservations == {
        "G001": 100.0,
    }
    assert block.stored_groups == {}


def test_group_can_be_stored_directly() -> None:
    block = create_general_block()

    block.store_group(
        group_id="G001",
        teu=120.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    assert block.stored_groups == {
        "G001": 120.0,
    }
    assert block.occupied_teu == 120.0
    assert block.available_teu == 680.0


def test_reserved_group_must_be_committed() -> None:
    block = create_general_block()

    block.reserve_capacity(
        group_id="G001",
        teu=100.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    with pytest.raises(
        YardReservationError,
        match="Commit the reservation instead",
    ):
        block.store_group(
            group_id="G001",
            teu=100.0,
            required_capabilities={
                YardCapability.GENERAL,
            },
        )

    assert block.reservations == {
        "G001": 100.0,
    }
    assert block.stored_groups == {}


def test_stored_group_cannot_be_added_twice() -> None:
    block = create_general_block()

    block.store_group(
        group_id="G001",
        teu=100.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    with pytest.raises(
        YardOperationError,
        match="already stored",
    ):
        block.store_group(
            group_id="G001",
            teu=50.0,
            required_capabilities={
                YardCapability.GENERAL,
            },
        )

    assert block.stored_groups["G001"] == 100.0


def test_group_can_be_partially_released() -> None:
    block = create_general_block()

    block.store_group(
        group_id="G001",
        teu=150.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    released_teu = block.release_group(
        group_id="G001",
        teu=40.0,
    )

    assert released_teu == 40.0
    assert block.stored_groups == {
        "G001": 110.0,
    }
    assert block.occupied_teu == 110.0
    assert block.available_teu == 690.0


def test_complete_group_can_be_released() -> None:
    block = create_general_block()

    block.store_group(
        group_id="G001",
        teu=120.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    released_teu = block.release_group(
        "G001"
    )

    assert released_teu == 120.0
    assert block.stored_groups == {}
    assert block.occupied_teu == 0
    assert block.available_teu == 800.0


def test_exact_remaining_amount_removes_group_record() -> None:
    block = create_general_block()

    block.store_group(
        group_id="G001",
        teu=100.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    released_teu = block.release_group(
        group_id="G001",
        teu=100.0,
    )

    assert released_teu == 100.0
    assert "G001" not in block.stored_groups


def test_cannot_release_more_than_stored_amount() -> None:
    block = create_general_block()

    block.store_group(
        group_id="G001",
        teu=80.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    with pytest.raises(
        YardCapacityError,
        match="only 80.0 TEU is stored",
    ):
        block.release_group(
            group_id="G001",
            teu=100.0,
        )

    assert block.stored_groups["G001"] == 80.0


def test_missing_group_cannot_be_released() -> None:
    block = create_general_block()

    with pytest.raises(
        YardOperationError,
        match="is not stored",
    ):
        block.release_group(
            "G999"
        )


def test_group_cannot_be_released_while_block_is_closed() -> None:
    block = create_general_block()

    block.store_group(
        group_id="G001",
        teu=100.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    block.close()

    with pytest.raises(
        YardOperationError,
        match="cannot release container groups",
    ):
        block.release_group(
            "G001"
        )

    assert block.stored_groups == {
        "G001": 100.0,
    }


def test_occupancy_metrics_are_calculated() -> None:
    block = create_general_block(
        capacity_teu=800.0
    )

    block.store_group(
        group_id="G001",
        teu=200.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    block.reserve_capacity(
        group_id="G002",
        teu=200.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    assert block.occupied_teu == 200.0
    assert block.reserved_teu == 200.0
    assert block.available_teu == 400.0
    assert block.occupancy_ratio == 0.25
    assert block.planned_occupancy_ratio == 0.50


def test_yard_block_dict_round_trip() -> None:
    block = create_reefer_block()

    block.store_group(
        group_id="G001",
        teu=120.0,
        required_capabilities={
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        },
    )

    block.reserve_capacity(
        group_id="G002",
        teu=80.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    data = block.to_dict()
    loaded_block = YardBlock.from_dict(data)

    assert loaded_block.block_id == "R01"
    assert loaded_block.capacity_teu == 600.0
    assert loaded_block.capabilities == {
        YardCapability.GENERAL,
        YardCapability.REEFER_POWER,
    }
    assert loaded_block.status == YardBlockStatus.OPEN
    assert loaded_block.stored_groups == {
        "G001": 120.0,
    }
    assert loaded_block.reservations == {
        "G002": 80.0,
    }


def test_yard_block_json_round_trip(
    tmp_path,
) -> None:
    block = create_reefer_block()

    block.store_group(
        group_id="G001",
        teu=120.0,
        required_capabilities={
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        },
    )

    block.reserve_capacity(
        group_id="G002",
        teu=80.0,
        required_capabilities={
            YardCapability.GENERAL,
        },
    )

    block.close()

    file_path = tmp_path / "yard_block.json"

    block.save_to_json(file_path)

    loaded_block = YardBlock.load_from_json(
        file_path
    )

    assert file_path.exists()
    assert loaded_block.block_id == "R01"
    assert loaded_block.capacity_teu == 600.0
    assert loaded_block.capabilities == {
        YardCapability.GENERAL,
        YardCapability.REEFER_POWER,
    }
    assert loaded_block.status == YardBlockStatus.CLOSED
    assert loaded_block.stored_groups == {
        "G001": 120.0,
    }
    assert loaded_block.reservations == {
        "G002": 80.0,
    }
    assert loaded_block.occupied_teu == 120.0
    assert loaded_block.reserved_teu == 80.0
    assert loaded_block.available_teu == 400.0


def test_snapshot_exceeding_capacity_is_rejected() -> None:
    invalid_data = {
        "block_id": "A01",
        "capacity_teu": 500.0,
        "capabilities": [
            "general",
        ],
        "status": "open",
        "stored_groups": {
            "G001": 400.0,
        },
        "reservations": {
            "G002": 200.0,
        },
    }

    with pytest.raises(
        YardCapacityError,
        match="exceeds block capacity",
    ):
        YardBlock.from_dict(
            invalid_data
        )


def test_group_cannot_be_stored_and_reserved() -> None:
    invalid_data = {
        "block_id": "A01",
        "capacity_teu": 800.0,
        "capabilities": [
            "general",
        ],
        "status": "open",
        "stored_groups": {
            "G001": 100.0,
        },
        "reservations": {
            "G001": 100.0,
        },
    }

    with pytest.raises(
        YardBlockValidationError,
        match="both stored and reserved",
    ):
        YardBlock.from_dict(
            invalid_data
        )


def test_negative_stored_teu_in_snapshot_is_rejected() -> None:
    invalid_data = {
        "block_id": "A01",
        "capacity_teu": 800.0,
        "capabilities": [
            "general",
        ],
        "status": "open",
        "stored_groups": {
            "G001": -100.0,
        },
        "reservations": {},
    }

    with pytest.raises(
        YardBlockValidationError,
        match="TEU value must be greater than zero",
    ):
        YardBlock.from_dict(
            invalid_data
        )


def test_invalid_status_in_snapshot_is_rejected() -> None:
    invalid_data = {
        "block_id": "A01",
        "capacity_teu": 800.0,
        "capabilities": [
            "general",
        ],
        "status": "destroyed",
        "stored_groups": {},
        "reservations": {},
    }

    with pytest.raises(
        YardBlockValidationError,
        match="Invalid yard block snapshot",
    ):
        YardBlock.from_dict(
            invalid_data
        )