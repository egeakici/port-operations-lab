import pytest

from src.terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from src.terminal_core.exceptions import (
    ContainerCargoError,
    ContainerFlowError,
    ContainerGroupValidationError,
    YardCompatibilityError,
)
from src.terminal_core.yard_block import (
    YardBlock,
    YardCapability,
)


def create_import_group(
    group_id: str = "G001",
    container_size: ContainerSize = ContainerSize.FORTY_FT,
    quantity: int = 50,
    load_state: ContainerLoadState = ContainerLoadState.LADEN,
    is_reefer: bool = False,
    is_hazardous: bool = False,
) -> ContainerGroup:
    return ContainerGroup(
        group_id=group_id,
        container_size=container_size,
        quantity=quantity,
        flow=ContainerFlow.IMPORT,
        load_state=load_state,
        is_reefer=is_reefer,
        is_hazardous=is_hazardous,
        source_vessel_id="V001",
    )


def test_valid_import_group_is_created() -> None:
    group = create_import_group()

    assert group.group_id == "G001"
    assert group.container_size == ContainerSize.FORTY_FT
    assert group.quantity == 50
    assert group.flow == ContainerFlow.IMPORT
    assert group.load_state == ContainerLoadState.LADEN
    assert group.source_vessel_id == "V001"
    assert group.target_vessel_id is None
    assert group.teu_per_container == 2.0
    assert group.total_teu == 100.0
    assert group.required_yard_capabilities == {
        YardCapability.GENERAL,
    }


def test_valid_reefer_import_group_requires_reefer_power() -> None:
    group = create_import_group(
        is_reefer=True
    )

    assert group.required_yard_capabilities == {
        YardCapability.GENERAL,
        YardCapability.REEFER_POWER,
    }


def test_valid_hazardous_group_requires_hazardous_capability() -> None:
    group = create_import_group(
        is_hazardous=True
    )

    assert group.required_yard_capabilities == {
        YardCapability.GENERAL,
        YardCapability.HAZARDOUS,
    }


def test_reefer_hazardous_group_requires_both_capabilities() -> None:
    group = create_import_group(
        is_reefer=True,
        is_hazardous=True,
    )

    assert group.required_yard_capabilities == {
        YardCapability.GENERAL,
        YardCapability.REEFER_POWER,
        YardCapability.HAZARDOUS,
    }


def test_valid_export_group_is_created() -> None:
    group = ContainerGroup(
        group_id="G002",
        container_size=ContainerSize.TWENTY_FT,
        quantity=40,
        flow=ContainerFlow.EXPORT,
        load_state=ContainerLoadState.LADEN,
        target_vessel_id="V002",
    )

    assert group.source_vessel_id is None
    assert group.target_vessel_id == "V002"


def test_valid_transshipment_group_is_created() -> None:
    group = ContainerGroup(
        group_id="G003",
        container_size=ContainerSize.FORTY_FT,
        quantity=25,
        flow=ContainerFlow.TRANSSHIPMENT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id="V001",
        target_vessel_id="V004",
    )

    assert group.source_vessel_id == "V001"
    assert group.target_vessel_id == "V004"


def test_empty_group_requires_only_empty_capability() -> None:
    group = create_import_group(
        load_state=ContainerLoadState.EMPTY
    )

    assert group.required_yard_capabilities == {
        YardCapability.EMPTY,
    }


def test_twenty_foot_teu_is_calculated() -> None:
    group = create_import_group(
        container_size=ContainerSize.TWENTY_FT,
        quantity=60,
    )

    assert group.teu_per_container == 1.0
    assert group.total_teu == 60.0


def test_forty_foot_teu_is_calculated() -> None:
    group = create_import_group(
        container_size=ContainerSize.FORTY_FT,
        quantity=60,
    )

    assert group.teu_per_container == 2.0
    assert group.total_teu == 120.0


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {
                "group_id": "   ",
            },
            "ID cannot be empty",
        ),
        (
            {
                "quantity": 0,
            },
            "positive integer",
        ),
        (
            {
                "quantity": -1,
            },
            "positive integer",
        ),
        (
            {
                "quantity": 1.5,
            },
            "positive integer",
        ),
        (
            {
                "quantity": True,
            },
            "positive integer",
        ),
        (
            {
                "container_size": "40_ft",
            },
            "ContainerSize",
        ),
        (
            {
                "flow": "import",
            },
            "ContainerFlow",
        ),
        (
            {
                "load_state": "laden",
            },
            "ContainerLoadState",
        ),
        (
            {
                "is_reefer": "true",
            },
            "boolean",
        ),
        (
            {
                "is_hazardous": "false",
            },
            "boolean",
        ),
        (
            {
                "source_vessel_id": "   ",
            },
            "Source vessel ID",
        ),
    ],
)
def test_invalid_basic_group_data_is_rejected(
    kwargs,
    match,
) -> None:
    valid_kwargs = {
        "group_id": "G001",
        "container_size": ContainerSize.FORTY_FT,
        "quantity": 50,
        "flow": ContainerFlow.IMPORT,
        "load_state": ContainerLoadState.LADEN,
        "source_vessel_id": "V001",
    }
    valid_kwargs.update(kwargs)

    with pytest.raises(
        ContainerGroupValidationError,
        match=match,
    ):
        ContainerGroup(**valid_kwargs)


def test_empty_target_vessel_id_is_rejected() -> None:
    with pytest.raises(
        ContainerGroupValidationError,
        match="Target vessel ID",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.EXPORT,
            load_state=ContainerLoadState.LADEN,
            target_vessel_id="   ",
        )


def test_import_group_requires_source_vessel() -> None:
    with pytest.raises(
        ContainerFlowError,
        match="source vessel",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.IMPORT,
            load_state=ContainerLoadState.LADEN,
        )


def test_import_group_rejects_target_vessel() -> None:
    with pytest.raises(
        ContainerFlowError,
        match="target vessel",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.IMPORT,
            load_state=ContainerLoadState.LADEN,
            source_vessel_id="V001",
            target_vessel_id="V002",
        )


def test_export_group_requires_target_vessel() -> None:
    with pytest.raises(
        ContainerFlowError,
        match="target vessel",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.EXPORT,
            load_state=ContainerLoadState.LADEN,
        )


def test_export_group_rejects_source_vessel() -> None:
    with pytest.raises(
        ContainerFlowError,
        match="source vessel",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.EXPORT,
            load_state=ContainerLoadState.LADEN,
            source_vessel_id="V001",
            target_vessel_id="V002",
        )


def test_transshipment_group_requires_source_vessel() -> None:
    with pytest.raises(
        ContainerFlowError,
        match="source vessel",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.TRANSSHIPMENT,
            load_state=ContainerLoadState.LADEN,
            target_vessel_id="V002",
        )


def test_transshipment_group_requires_target_vessel() -> None:
    with pytest.raises(
        ContainerFlowError,
        match="target vessel",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.TRANSSHIPMENT,
            load_state=ContainerLoadState.LADEN,
            source_vessel_id="V001",
        )


def test_transshipment_group_rejects_same_vessels() -> None:
    with pytest.raises(
        ContainerFlowError,
        match="different source and target",
    ):
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.TRANSSHIPMENT,
            load_state=ContainerLoadState.LADEN,
            source_vessel_id="V001",
            target_vessel_id="V001",
        )


def test_empty_group_cannot_be_reefer() -> None:
    with pytest.raises(
        ContainerCargoError,
        match="reefer",
    ):
        create_import_group(
            load_state=ContainerLoadState.EMPTY,
            is_reefer=True,
        )


def test_empty_group_cannot_be_hazardous() -> None:
    with pytest.raises(
        ContainerCargoError,
        match="hazardous",
    ):
        create_import_group(
            load_state=ContainerLoadState.EMPTY,
            is_hazardous=True,
        )


def test_yard_allocation_data_is_created() -> None:
    group = create_import_group(
        is_reefer=True
    )

    allocation = group.yard_allocation_data()

    assert allocation == {
        "group_id": "G001",
        "teu": 100.0,
        "required_capabilities": {
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        },
    }


def test_yard_allocation_capabilities_are_fresh_sets() -> None:
    group = create_import_group()

    first_capabilities = group.required_yard_capabilities
    first_capabilities.add(
        YardCapability.HAZARDOUS
    )

    assert group.required_yard_capabilities == {
        YardCapability.GENERAL,
    }


def test_yard_block_can_reserve_using_group_allocation_data() -> None:
    group = create_import_group(
        is_reefer=True
    )
    block = YardBlock(
        block_id="R01",
        capacity_teu=600.0,
        capabilities={
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        },
    )

    allocation = group.yard_allocation_data()

    block.reserve_capacity(
        group_id=allocation["group_id"],
        teu=allocation["teu"],
        required_capabilities=allocation[
            "required_capabilities"
        ],
    )

    assert "G001" in block.reservations
    assert block.reserved_teu == group.total_teu


def test_yard_block_rejects_incompatible_group_allocation() -> None:
    group = create_import_group(
        is_reefer=True
    )
    block = YardBlock(
        block_id="A01",
        capacity_teu=600.0,
        capabilities={
            YardCapability.GENERAL,
        },
    )

    allocation = group.yard_allocation_data()

    with pytest.raises(
        YardCompatibilityError,
        match="does not support",
    ):
        block.reserve_capacity(
            group_id=allocation["group_id"],
            teu=allocation["teu"],
            required_capabilities=allocation[
                "required_capabilities"
            ],
        )


def test_container_group_dictionary_round_trip() -> None:
    group = create_import_group(
        is_reefer=True,
        is_hazardous=True,
    )

    data = group.to_dict()
    loaded_group = ContainerGroup.from_dict(data)

    assert loaded_group == group
    assert loaded_group is not group
    assert loaded_group.total_teu == group.total_teu
    assert (
        loaded_group.required_yard_capabilities
        == group.required_yard_capabilities
    )


def test_container_group_json_round_trip(tmp_path) -> None:
    group = create_import_group(
        is_reefer=True
    )
    file_path = tmp_path / "container_group.json"

    group.save_to_json(file_path)
    loaded_group = ContainerGroup.load_from_json(
        file_path
    )

    assert file_path.exists()
    assert loaded_group == group
    assert loaded_group.total_teu == group.total_teu
    assert (
        loaded_group.required_yard_capabilities
        == group.required_yard_capabilities
    )


@pytest.mark.parametrize(
    "invalid_data",
    [
        {
            "group_id": "G001",
            "container_size": "45_ft",
            "quantity": 50,
            "flow": "import",
            "load_state": "laden",
            "source_vessel_id": "V001",
        },
        {
            "group_id": "G001",
            "container_size": "40_ft",
            "quantity": 50,
            "flow": "coastal",
            "load_state": "laden",
            "source_vessel_id": "V001",
        },
        {
            "group_id": "G001",
            "quantity": 50,
            "flow": "import",
            "load_state": "laden",
            "source_vessel_id": "V001",
        },
    ],
)
def test_invalid_snapshot_is_rejected(
    invalid_data,
) -> None:
    with pytest.raises(
        ContainerGroupValidationError,
        match="Invalid container group snapshot",
    ):
        ContainerGroup.from_dict(
            invalid_data
        )


def test_snapshot_flow_error_keeps_exception_type() -> None:
    invalid_data = {
        "group_id": "G001",
        "container_size": "40_ft",
        "quantity": 50,
        "flow": "import",
        "load_state": "laden",
    }

    with pytest.raises(
        ContainerFlowError,
        match="source vessel",
    ):
        ContainerGroup.from_dict(
            invalid_data
        )


def test_snapshot_cargo_error_keeps_exception_type() -> None:
    invalid_data = {
        "group_id": "G001",
        "container_size": "40_ft",
        "quantity": 50,
        "flow": "import",
        "load_state": "empty",
        "is_reefer": True,
        "source_vessel_id": "V001",
    }

    with pytest.raises(
        ContainerCargoError,
        match="reefer",
    ):
        ContainerGroup.from_dict(
            invalid_data
        )
