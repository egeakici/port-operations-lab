from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path

import pytest

from src.terminal_core.berth import Berth
from src.terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from src.terminal_core.exceptions import (
    ContainerGroupLocationValidationError,
    TerminalEventValidationError,
    TerminalStateConsistencyError,
    TerminalStateDuplicateEntityError,
    TerminalStateLookupError,
    TerminalStateReferenceError,
    TerminalStateValidationError,
)
from src.terminal_core.operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from src.terminal_core.quay_crane import QuayCrane
from src.terminal_core.terminal_event import (
    TerminalEntityType,
    TerminalEvent,
    TerminalEventType,
)
from src.terminal_core.terminal_state import (
    TERMINAL_STATE_SCHEMA_VERSION,
    ContainerGroupLocation,
    TerminalState,
)
from src.terminal_core.vessel import Vessel, VesselStatus
from src.terminal_core.yard_block import YardBlock, YardCapability


ETA = datetime(2026, 8, 5, 8, 0)
STARTED_AT = datetime(2026, 8, 5, 10, 0)
CURRENT_TIME = datetime(2026, 8, 5, 10, 40)
COMPLETED_AT = datetime(2026, 8, 5, 10, 20)


class SampleIntEnum(IntEnum):
    VALUE = 1


class CustomObject:
    pass


def vessel_location(
    location_id: str = "V001",
) -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.VESSEL,
        location_id=location_id,
    )


def yard_location(
    location_id: str = "Y01",
) -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.YARD_BLOCK,
        location_id=location_id,
    )


def gate_location(
    location_id: str = "GATE-1",
) -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.GATE,
        location_id=location_id,
    )


def create_vessel(
    vessel_id: str = "V001",
    status: VesselStatus = VesselStatus.OPERATING,
    max_cranes: int = 3,
) -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=250.0,
        eta=ETA,
        workload_moves=1500,
        priority=2,
        max_cranes=max_cranes,
        status=status,
    )


def create_berth(
    vessel: Vessel | None = None,
    berth_id: str = "B01",
) -> Berth:
    if vessel is None:
        vessel = create_vessel()

    berth = Berth(
        berth_id=berth_id,
        length_m=800.0,
        min_clearance_m=20.0,
    )
    berth.place_vessel(vessel, 100.0)

    return berth


def create_crane(
    vessel: Vessel | None = None,
    crane_id: str = "QC01",
    operating: bool = True,
) -> QuayCrane:
    if vessel is None:
        vessel = create_vessel()

    crane = QuayCrane(
        crane_id=crane_id,
        position_m=140.0,
        moves_per_hour=30.0,
    )
    crane.assign_to_vessel(vessel)

    if operating:
        crane.start_operation()

    return crane


def create_import_group(
    group_id: str = "G001",
    source_vessel_id: str = "V001",
    quantity: int = 50,
    is_reefer: bool = False,
) -> ContainerGroup:
    return ContainerGroup(
        group_id=group_id,
        container_size=ContainerSize.FORTY_FT,
        quantity=quantity,
        flow=ContainerFlow.IMPORT,
        load_state=ContainerLoadState.LADEN,
        is_reefer=is_reefer,
        source_vessel_id=source_vessel_id,
    )


def create_export_group(
    group_id: str = "G002",
    target_vessel_id: str = "V001",
) -> ContainerGroup:
    return ContainerGroup(
        group_id=group_id,
        container_size=ContainerSize.FORTY_FT,
        quantity=50,
        flow=ContainerFlow.EXPORT,
        load_state=ContainerLoadState.LADEN,
        target_vessel_id=target_vessel_id,
    )


def create_transshipment_group(
    group_id: str = "G003",
    source_vessel_id: str = "V001",
    target_vessel_id: str = "V002",
) -> ContainerGroup:
    return ContainerGroup(
        group_id=group_id,
        container_size=ContainerSize.FORTY_FT,
        quantity=50,
        flow=ContainerFlow.TRANSSHIPMENT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id=source_vessel_id,
        target_vessel_id=target_vessel_id,
    )


def create_yard_block(
    group: ContainerGroup | None = None,
    stored_teu: float = 40.0,
    block_id: str = "Y01",
    capabilities: set[YardCapability] | None = None,
) -> YardBlock:
    if group is None:
        group = create_import_group()

    if capabilities is None:
        capabilities = {
            YardCapability.GENERAL,
        }

    block = YardBlock(
        block_id=block_id,
        capacity_teu=500.0,
        capabilities=capabilities,
    )
    block.store_group(
        group.group_id,
        stored_teu,
        group.required_yard_capabilities,
    )

    return block


def create_discharge_task(
    group_id: str = "G001",
    task_id: str = "T001",
    planned_teu: float = 100.0,
    vessel_id: str = "V001",
    yard_id: str = "Y01",
) -> OperationTask:
    return OperationTask(
        task_id=task_id,
        task_type=OperationType.DISCHARGE,
        group_id=group_id,
        planned_teu=planned_teu,
        source=vessel_location(vessel_id),
        target=yard_location(yard_id),
    )


def start_task(
    task: OperationTask | None = None,
    resource_id: str = "QC01",
) -> OperationTask:
    if task is None:
        task = create_discharge_task()

    task.mark_ready()
    task.assign_resource(resource_id)
    task.start(STARTED_AT)

    return task


def complete_task(
    task_id: str = "T000",
) -> OperationTask:
    task = create_discharge_task(
        task_id=task_id,
        planned_teu=20.0,
    )
    task.mark_ready()
    task.assign_resource("QC99")
    task.start(STARTED_AT)
    task.record_progress(task.planned_teu)
    task.complete(COMPLETED_AT)

    return task


def create_event(
    event_id: str,
    occurred_at: datetime,
) -> TerminalEvent:
    return TerminalEvent(
        event_id=event_id,
        event_type=TerminalEventType.TASK_STARTED,
        occurred_at=occurred_at,
        entity_type=TerminalEntityType.OPERATION_TASK,
        entity_id="T001",
        payload={
            "resource_id": "QC01",
        },
    )


def create_valid_state(
    *,
    events: tuple[TerminalEvent, ...] = (),
) -> TerminalState:
    vessel = create_vessel()
    berth = create_berth(vessel)
    crane = create_crane(vessel)
    group = create_import_group()
    block = create_yard_block(group)
    task = start_task()
    task.record_progress(40.0)

    return TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[
            vessel,
        ],
        berths=[
            berth,
        ],
        quay_cranes=[
            crane,
        ],
        yard_blocks=[
            block,
        ],
        container_groups=[
            group,
        ],
        operation_tasks=[
            task,
        ],
        group_locations=[
            ContainerGroupLocation(
                group_id=group.group_id,
                location=vessel_location(vessel.vessel_id),
                teu=60.0,
            ),
            ContainerGroupLocation(
                group_id=group.group_id,
                location=yard_location(block.block_id),
                teu=40.0,
            ),
        ],
        events=events,
    )


def test_valid_container_group_location_is_created() -> None:
    location = ContainerGroupLocation(
        group_id="G001",
        location=yard_location(),
        teu=40,
    )

    assert location.group_id == "G001"
    assert location.teu == 40.0
    assert location.to_dict() == {
        "group_id": "G001",
        "location": yard_location().to_dict(),
        "teu": 40.0,
    }
    assert ContainerGroupLocation.from_dict(
        location.to_dict()
    ) == location


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {
                "group_id": "   ",
            },
            "group ID",
        ),
        (
            {
                "location": yard_location().to_dict(),
            },
            "TaskLocation",
        ),
        (
            {
                "teu": 0,
            },
            "TEU",
        ),
        (
            {
                "teu": -10,
            },
            "TEU",
        ),
        (
            {
                "teu": True,
            },
            "TEU",
        ),
        (
            {
                "teu": float("nan"),
            },
            "TEU",
        ),
        (
            {
                "teu": float("inf"),
            },
            "TEU",
        ),
        (
            {
                "teu": "40",
            },
            "TEU",
        ),
    ],
)
def test_invalid_container_group_locations_are_rejected(
    kwargs,
    match,
) -> None:
    valid_kwargs = {
        "group_id": "G001",
        "location": yard_location(),
        "teu": 40.0,
    }
    valid_kwargs.update(kwargs)

    with pytest.raises(
        ContainerGroupLocationValidationError,
        match=match,
    ):
        ContainerGroupLocation(**valid_kwargs)


def test_capture_builds_immutable_snapshot_and_queries() -> None:
    event_1 = create_event("EVT-001", STARTED_AT)
    event_2 = create_event("EVT-002", STARTED_AT)
    state = create_valid_state(
        events=(
            event_1,
            event_2,
        )
    )

    assert state.vessel_count == 1
    assert state.berth_count == 1
    assert state.quay_crane_count == 1
    assert state.yard_block_count == 1
    assert state.container_group_count == 1
    assert state.operation_task_count == 1
    assert state.vessel_ids == ("V001",)
    assert state.event_count == 2
    assert state.last_event_id == "EVT-002"
    assert state.get_vessel("V001").status == VesselStatus.OPERATING
    assert state.get_quay_crane("QC01").assigned_vessel_id == "V001"
    assert state.get_operation_task("T001").completed_teu == 40.0
    assert state.group_teu_at("G001") == 100.0
    assert state.group_teu_at(
        "G001",
        TaskLocationType.YARD_BLOCK,
        "Y01",
    ) == 40.0
    assert state.task_ids_by_status(
        OperationTaskStatus.IN_PROGRESS
    ) == ("T001",)

    with pytest.raises(FrozenInstanceError):
        state.current_time = ETA

    with pytest.raises(TypeError):
        state.vessels["V001"] = {}

    with pytest.raises(TypeError):
        state.vessels["V001"]["status"] = "departed"

    with pytest.raises(AttributeError):
        state.berths["B01"]["occupancies"].append({})


def test_original_entity_and_output_aliases_are_not_kept() -> None:
    vessel = create_vessel()
    berth = create_berth(vessel)
    crane = create_crane(vessel)
    group = create_import_group()
    block = create_yard_block(group)
    task = start_task()
    task.record_progress(40.0)

    state = TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[vessel],
        berths=[berth],
        quay_cranes=[crane],
        yard_blocks=[block],
        container_groups=[group],
        operation_tasks=[task],
        group_locations=[
            ContainerGroupLocation("G001", vessel_location(), 60.0),
            ContainerGroupLocation("G001", yard_location(), 40.0),
        ],
    )

    vessel.status = VesselStatus.DEPARTED
    data = state.to_dict()
    data["vessels"]["V001"]["status"] = "departed"
    vessel_copy = state.get_vessel("V001")
    vessel_copy.status = VesselStatus.DEPARTED

    assert state.vessels["V001"]["status"] == "operating"


def test_dictionary_and_json_round_trip(tmp_path) -> None:
    state = create_valid_state(
        events=(
            create_event("EVT-001", STARTED_AT),
        )
    )
    data = state.to_dict()

    loaded_state = TerminalState.from_dict(data)

    assert data["schema_version"] == TERMINAL_STATE_SCHEMA_VERSION
    assert loaded_state.to_dict() == data
    assert loaded_state.group_teu_at("G001") == 100.0

    file_path = tmp_path / "snapshots" / "terminal_state.json"
    state.save_to_json(file_path)
    json_state = TerminalState.load_from_json(file_path)

    assert file_path.exists()
    assert json_state.to_dict() == data

    with pytest.raises(TypeError):
        json_state.yard_blocks["Y01"]["stored_groups"]["G001"] = 1


def test_constructor_input_snapshot_alias_is_not_kept() -> None:
    state = create_valid_state()
    data = state.to_dict()
    vessels = data["vessels"]

    copied_state = TerminalState(
        current_time=CURRENT_TIME,
        vessels=vessels,
        berths=data["berths"],
        quay_cranes=data["quay_cranes"],
        yard_blocks=data["yard_blocks"],
        container_groups=data["container_groups"],
        operation_tasks=data["operation_tasks"],
        group_locations=tuple(
            ContainerGroupLocation.from_dict(item)
            for item in data["group_locations"]
        ),
    )
    vessels["V001"]["status"] = "departed"

    assert copied_state.vessels["V001"]["status"] == "operating"


def test_lookup_errors_are_explicit() -> None:
    state = create_valid_state()

    with pytest.raises(
        TerminalStateLookupError,
        match="Unknown vessel",
    ):
        state.get_vessel("V999")

    with pytest.raises(
        TerminalStateValidationError,
        match="cannot be empty",
    ):
        state.get_vessel("   ")

    with pytest.raises(
        TerminalStateValidationError,
        match="OperationTaskStatus",
    ):
        state.task_ids_by_status("in_progress")

    with pytest.raises(
        TerminalStateLookupError,
        match="Unknown container group ID",
    ):
        state.locations_for_group("G999")

    with pytest.raises(
        TerminalStateLookupError,
        match="Unknown container group ID",
    ):
        state.group_teu_at("G999")


def test_registered_group_without_locations_returns_empty() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    state = TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[
            vessel,
        ],
        container_groups=[
            group,
        ],
    )

    assert state.locations_for_group("G001") == ()
    assert state.group_teu_at("G001") == 0.0


def test_duplicate_entities_and_events_are_rejected() -> None:
    vessel = create_vessel()

    with pytest.raises(
        TerminalStateDuplicateEntityError,
        match="Duplicate vessel ID",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[
                vessel,
                vessel,
            ],
        )

    event = create_event("EVT-001", STARTED_AT)

    with pytest.raises(
        TerminalStateDuplicateEntityError,
        match="Duplicate event ID",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            events=[
                event,
                event,
            ],
        )


def test_event_order_and_future_events_are_rejected() -> None:
    with pytest.raises(
        TerminalStateConsistencyError,
        match="non-decreasing",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            events=[
                create_event("EVT-002", CURRENT_TIME),
                create_event("EVT-001", STARTED_AT),
            ],
        )

    with pytest.raises(
        TerminalStateConsistencyError,
        match="after",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            events=[
                create_event(
                    "EVT-003",
                    datetime(2026, 8, 5, 11, 0),
                ),
            ],
        )

    with pytest.raises(
        TerminalEventValidationError,
        match="TerminalEvent",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            events=[
                "bad",
            ],
        )


@pytest.mark.parametrize(
    "updates,match",
    [
        (
            {
                "schema_version": 2,
            },
            "Unsupported",
        ),
        (
            {
                "schema_version": True,
            },
            "schema_version",
        ),
        (
            {
                "current_time": "not-a-date",
            },
            "Invalid terminal state snapshot",
        ),
        (
            {
                "event_count": 0,
                "last_event_id": "EVT-001",
            },
            "last_event_id",
        ),
        (
            {
                "event_count": 1,
                "last_event_id": None,
            },
            "Last event ID",
        ),
        (
            {
                "group_locations": {},
            },
            "Group locations",
        ),
    ],
)
def test_invalid_terminal_state_snapshots_are_rejected(
    updates,
    match,
) -> None:
    data = create_valid_state().to_dict()
    data.update(updates)

    with pytest.raises(
        TerminalStateValidationError,
        match=match,
    ):
        TerminalState.from_dict(data)


@pytest.mark.parametrize(
    "mutate,exception_type,match",
    [
        (
            lambda data: data["vessels"]["V001"].update(
                {
                    "status": SampleIntEnum.VALUE,
                }
            ),
            TerminalStateValidationError,
            "Enum is not JSON-safe",
        ),
        (
            lambda data: data["vessels"]["V001"].update(
                {
                    "eta": ETA,
                }
            ),
            TerminalStateValidationError,
            "Invalid state snapshot value",
        ),
        (
            lambda data: data["vessels"].update(
                {
                    "V999": data["vessels"]["V001"],
                }
            ),
            TerminalStateConsistencyError,
            "does not match",
        ),
        (
            lambda data: data["vessels"]["V001"].update(
                {
                    "length_m": -1,
                }
            ),
            TerminalStateValidationError,
            "Invalid vessel snapshot",
        ),
        (
            lambda data: data.update(
                {
                    "vessels": [],
                }
            ),
            TerminalStateValidationError,
            "registry must be a mapping",
        ),
        (
            lambda data: data["vessels"].update(
                {
                    "V002": [],
                }
            ),
            TerminalStateValidationError,
            "must be a mapping",
        ),
    ],
)
def test_invalid_registry_snapshots_are_rejected(
    mutate,
    exception_type,
    match,
) -> None:
    data = create_valid_state().to_dict()
    mutate(data)

    with pytest.raises(
        exception_type,
        match=match,
    ):
        TerminalState.from_dict(data)


def test_container_group_missing_vessel_reference_is_rejected() -> None:
    vessel = create_vessel()
    group = create_import_group(source_vessel_id="V999")

    with pytest.raises(
        TerminalStateReferenceError,
        match="source vessel V999",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[vessel],
            container_groups=[group],
        )


def test_berth_vessel_consistency_is_enforced() -> None:
    data = create_valid_state().to_dict()
    data["berths"]["B01"]["occupancies"][0]["vessel"][
        "workload_moves"
    ] = 999

    with pytest.raises(
        TerminalStateConsistencyError,
        match="registered vessel snapshot",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["vessels"]["V001"]["status"] = "waiting"
    data["berths"]["B01"]["occupancies"][0]["vessel"][
        "status"
    ] = "waiting"

    with pytest.raises(
        TerminalStateConsistencyError,
        match="present in a berth occupancy",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["berths"]["B01"]["occupancies"] = []

    with pytest.raises(
        TerminalStateConsistencyError,
        match="not present",
    ):
        TerminalState.from_dict(data)


def test_crane_vessel_consistency_is_enforced() -> None:
    data = create_valid_state().to_dict()
    data["quay_cranes"]["QC01"]["assigned_vessel_id"] = "V999"

    with pytest.raises(
        TerminalStateReferenceError,
        match="V999",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["vessels"]["V001"]["status"] = "berthed"
    data["berths"]["B01"]["occupancies"][0]["vessel"][
        "status"
    ] = "berthed"

    with pytest.raises(
        TerminalStateConsistencyError,
        match="requires vessel V001 to be operating",
    ):
        TerminalState.from_dict(data)

    vessel = create_vessel(max_cranes=1)
    berth = create_berth(vessel)
    crane_1 = create_crane(vessel, "QC01")
    crane_2 = create_crane(vessel, "QC02")
    group = create_import_group()

    with pytest.raises(
        TerminalStateConsistencyError,
        match="exceeding max_cranes",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[vessel],
            berths=[berth],
            quay_cranes=[
                crane_1,
                crane_2,
            ],
            container_groups=[group],
        )


def test_yard_group_consistency_is_enforced() -> None:
    vessel = create_vessel()
    berth = create_berth(vessel)
    group = create_import_group(is_reefer=True)
    block_data = YardBlock(
        block_id="Y01",
        capacity_teu=500.0,
        capabilities={
            YardCapability.GENERAL,
            YardCapability.REEFER_POWER,
        },
    ).to_dict()
    block_data["capabilities"] = ["general"]
    block_data["stored_groups"] = {
        "G001": 40.0,
    }

    with pytest.raises(
        TerminalStateConsistencyError,
        match="does not support",
    ):
        TerminalState(
            current_time=CURRENT_TIME,
            vessels={
                "V001": vessel.to_dict(),
            },
            berths={
                "B01": berth.to_dict(),
            },
            yard_blocks={
                "Y01": block_data,
            },
            container_groups={
                "G001": group.to_dict(),
            },
            group_locations=(
                ContainerGroupLocation("G001", yard_location(), 40.0),
            ),
        )

    data = create_valid_state().to_dict()
    data["yard_blocks"]["Y01"]["stored_groups"] = {
        "G999": 40.0,
    }

    with pytest.raises(
        TerminalStateReferenceError,
        match="G999",
    ):
        TerminalState.from_dict(data)


def test_group_location_consistency_is_enforced() -> None:
    data = create_valid_state().to_dict()
    data["group_locations"].append(data["group_locations"][0])

    with pytest.raises(
        TerminalStateConsistencyError,
        match="Duplicate",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["group_locations"][0]["teu"] = 70.0

    with pytest.raises(
        TerminalStateConsistencyError,
        match="exceeding group total",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["group_locations"][0]["location"]["location_id"] = "V999"

    with pytest.raises(
        TerminalStateReferenceError,
        match="V999",
    ):
        TerminalState.from_dict(data)

    vessel_1 = create_vessel("V001")
    vessel_2 = create_vessel("V002", status=VesselStatus.WAITING)
    berth = create_berth(vessel_1)
    group = create_transshipment_group()

    with pytest.raises(
        TerminalStateConsistencyError,
        match="cannot be located at a gate",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[
                vessel_1,
                vessel_2,
            ],
            berths=[
                berth,
            ],
            container_groups=[
                group,
            ],
            group_locations=[
                ContainerGroupLocation("G003", gate_location(), 10.0),
            ],
        )


def test_yard_stored_group_location_matching_is_enforced() -> None:
    data = create_valid_state().to_dict()
    data["group_locations"] = [
        location
        for location in data["group_locations"]
        if location["location"]["location_type"] != "yard_block"
    ]

    with pytest.raises(
        TerminalStateConsistencyError,
        match="no matching group location",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["group_locations"][1]["teu"] = 39.0

    with pytest.raises(
        TerminalStateConsistencyError,
        match="location records",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["group_locations"][1]["teu"] = 40.0 + 1e-10

    assert TerminalState.from_dict(data).group_teu_at(
        "G001",
        TaskLocationType.YARD_BLOCK,
    ) == pytest.approx(40.0 + 1e-10)


def test_task_group_and_flow_consistency_is_enforced() -> None:
    data = create_valid_state().to_dict()
    data["operation_tasks"]["T001"]["group_id"] = "G999"

    with pytest.raises(
        TerminalStateReferenceError,
        match="G999",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["operation_tasks"]["T001"]["planned_teu"] = 120.0

    with pytest.raises(
        TerminalStateConsistencyError,
        match="planned TEU",
    ):
        TerminalState.from_dict(data)

    vessel = create_vessel()
    berth = create_berth(vessel)
    export_group = create_export_group()
    load_task = OperationTask(
        task_id="T002",
        task_type=OperationType.LOAD,
        group_id="G002",
        planned_teu=100.0,
        source=yard_location(),
        target=vessel_location(),
    )

    TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[vessel],
        berths=[berth],
        yard_blocks=[
            YardBlock("Y01", 500.0),
        ],
        container_groups=[export_group],
        operation_tasks=[load_task],
    )

    with pytest.raises(
        TerminalStateConsistencyError,
        match="not compatible",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[vessel],
            berths=[berth],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[export_group],
            operation_tasks=[create_discharge_task(group_id="G002")],
        )


def test_task_active_commitments_are_enforced_by_flow_leg() -> None:
    vessel = create_vessel()
    berth = create_berth(vessel)
    group = create_import_group()
    task_1 = create_discharge_task(task_id="T001", planned_teu=70.0)
    task_2 = create_discharge_task(task_id="T002", planned_teu=50.0)
    crane_1 = create_crane(
        vessel,
        crane_id="QC-T001",
        operating=False,
    )
    crane_2 = create_crane(
        vessel,
        crane_id="QC-T002",
        operating=False,
    )

    for task in (task_1, task_2):
        task.mark_ready()
        task.assign_resource(
            f"QC-{task.task_id}"
        )

    with pytest.raises(
        TerminalStateConsistencyError,
        match="Committed discharge tasks",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[vessel],
            berths=[berth],
            quay_cranes=[
                crane_1,
                crane_2,
            ],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[group],
            operation_tasks=[
                task_1,
                task_2,
            ],
        )

    task_2.cancel()

    TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[vessel],
            berths=[berth],
            quay_cranes=[
                crane_1,
                crane_2,
            ],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[group],
            operation_tasks=[
                task_1,
            task_2,
        ],
    )


def test_created_and_ready_tasks_are_counted_as_teu_commitments() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    task_1 = create_discharge_task(
        task_id="T001",
        planned_teu=70.0,
    )
    task_2 = create_discharge_task(
        task_id="T002",
        planned_teu=50.0,
    )

    with pytest.raises(
        TerminalStateConsistencyError,
        match="Committed discharge tasks",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[
                vessel,
            ],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[
                group,
            ],
            operation_tasks=[
                task_1,
                task_2,
            ],
        )

    task_2.mark_ready()

    with pytest.raises(
        TerminalStateConsistencyError,
        match="Committed discharge tasks",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[
                vessel,
            ],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[
                group,
            ],
            operation_tasks=[
                task_1,
                task_2,
            ],
        )


def test_task_dependency_graph_and_time_consistency_are_enforced() -> None:
    done = complete_task()
    ready = create_discharge_task(
        task_id="T002",
        planned_teu=20.0,
    )
    ready.predecessor_task_ids = {
        done.task_id,
    }
    ready.mark_ready()

    TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[create_vessel()],
        berths=[create_berth(create_vessel())],
        yard_blocks=[
            YardBlock("Y01", 500.0),
        ],
        container_groups=[create_import_group()],
        operation_tasks=[
            done,
            ready,
        ],
    )

    ready.predecessor_task_ids = {
        "T999",
    }

    with pytest.raises(
        TerminalStateReferenceError,
        match="T999",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[create_vessel()],
            berths=[create_berth(create_vessel())],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[create_import_group()],
            operation_tasks=[
                ready,
            ],
        )

    data = create_valid_state().to_dict()
    data["operation_tasks"]["T001"]["started_at"] = datetime(
        2026,
        8,
        5,
        11,
        0,
    ).isoformat()

    with pytest.raises(
        TerminalStateConsistencyError,
        match="started_at",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["current_time"] = datetime(
        2026,
        8,
        5,
        10,
        40,
        tzinfo=timezone.utc,
    ).isoformat()

    with pytest.raises(
        TerminalStateConsistencyError,
        match="comparable datetime",
    ):
        TerminalState.from_dict(data)


def test_completed_task_requires_completed_predecessors() -> None:
    predecessor = create_discharge_task(
        task_id="T000",
        planned_teu=20.0,
    )
    predecessor.mark_ready()
    completed = complete_task(task_id="T001")
    completed.predecessor_task_ids = {
        predecessor.task_id,
    }

    with pytest.raises(
        TerminalStateConsistencyError,
        match="predecessor T000 to be completed",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[
                create_vessel(),
            ],
            berths=[
                create_berth(create_vessel()),
            ],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[
                create_import_group(),
            ],
            operation_tasks=[
                predecessor,
                completed,
            ],
        )


def test_cancelled_task_can_keep_future_release_time() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    task = create_discharge_task()
    task.release_time = datetime(2026, 8, 6, 10, 0)
    task.cancel()

    state = TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[
            vessel,
        ],
        yard_blocks=[
            YardBlock("Y01", 500.0),
        ],
        container_groups=[
            group,
        ],
        operation_tasks=[
            task,
        ],
    )

    assert state.get_operation_task("T001").status == (
        OperationTaskStatus.CANCELLED
    )
    assert state.get_operation_task("T001").release_time == (
        datetime(2026, 8, 6, 10, 0)
    )


def test_task_dependency_cycles_are_rejected() -> None:
    task_1 = create_discharge_task(task_id="T001", planned_teu=20.0)
    task_2 = create_discharge_task(task_id="T002", planned_teu=20.0)
    task_1.predecessor_task_ids = {
        "T002",
    }
    task_2.predecessor_task_ids = {
        "T001",
    }

    with pytest.raises(
        TerminalStateConsistencyError,
        match="cycle",
    ):
        TerminalState.capture(
            current_time=CURRENT_TIME,
            vessels=[create_vessel()],
            berths=[create_berth(create_vessel())],
            yard_blocks=[
                YardBlock("Y01", 500.0),
            ],
            container_groups=[create_import_group()],
            operation_tasks=[
                task_1,
                task_2,
            ],
        )


def test_task_crane_integration_is_enforced() -> None:
    data = create_valid_state().to_dict()
    data["quay_cranes"]["QC01"]["status"] = "assigned"

    with pytest.raises(
        TerminalStateConsistencyError,
        match="requires QuayCrane QC01 to be operating",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["quay_cranes"]["QC01"]["assigned_vessel_id"] = "V002"
    data["vessels"]["V002"] = create_vessel(
        "V002",
        status=VesselStatus.OPERATING,
    ).to_dict()
    data["berths"]["B02"] = create_berth(
        create_vessel("V002"),
        berth_id="B02",
    ).to_dict()

    with pytest.raises(
        TerminalStateConsistencyError,
        match="not V001",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["operation_tasks"]["T002"] = data["operation_tasks"]["T001"].copy()
    data["operation_tasks"]["T002"]["task_id"] = "T002"

    with pytest.raises(
        TerminalStateConsistencyError,
        match="multiple active",
    ):
        TerminalState.from_dict(data)


def test_blocked_task_with_failed_crane_snapshot_is_valid() -> None:
    vessel = create_vessel()
    berth = create_berth(vessel)
    crane = create_crane(vessel)
    group = create_import_group()
    task = start_task()
    task.record_progress(40.0)
    task.block("Crane failed")
    crane.mark_failed()

    state = TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[vessel],
        berths=[berth],
        quay_cranes=[crane],
        yard_blocks=[
            YardBlock("Y01", 500.0),
        ],
        container_groups=[group],
        operation_tasks=[task],
    )

    assert state.get_operation_task("T001").status == OperationTaskStatus.BLOCKED
    assert state.get_quay_crane("QC01").assigned_vessel_id is None


def test_full_integration_scenario_round_trips() -> None:
    state = create_valid_state(
        events=(
            TerminalEvent(
                event_id="EVT-001",
                event_type=TerminalEventType.TASK_CREATED,
                occurred_at=datetime(2026, 8, 5, 9, 50),
                entity_type=TerminalEntityType.OPERATION_TASK,
                entity_id="T001",
            ),
            TerminalEvent(
                event_id="EVT-002",
                event_type=TerminalEventType.TASK_STARTED,
                occurred_at=STARTED_AT,
                entity_type=TerminalEntityType.OPERATION_TASK,
                entity_id="T001",
            ),
            TerminalEvent(
                event_id="EVT-003",
                event_type=TerminalEventType.TASK_PROGRESS_RECORDED,
                occurred_at=datetime(2026, 8, 5, 10, 30),
                entity_type=TerminalEntityType.OPERATION_TASK,
                entity_id="T001",
                payload={
                    "completed_teu": 40.0,
                },
            ),
        )
    )

    loaded = TerminalState.from_dict(state.to_dict())

    assert loaded.vessel_count == 1
    assert loaded.get_vessel("V001").status == VesselStatus.OPERATING
    assert loaded.get_quay_crane("QC01").status.name == "OPERATING"
    assert loaded.group_teu_at("G001") == 100.0
    assert loaded.group_teu_at(
        "G001",
        TaskLocationType.YARD_BLOCK,
    ) == 40.0
    assert loaded.event_count == 3
    assert loaded.last_event_id == "EVT-003"


def test_state_rejects_non_json_safe_custom_snapshot_values() -> None:
    data = create_valid_state().to_dict()
    data["vessels"]["V001"]["bad"] = CustomObject()

    with pytest.raises(
        TerminalStateValidationError,
        match="CustomObject",
    ):
        TerminalState.from_dict(data)

    data = create_valid_state().to_dict()
    data["vessels"]["V001"]["bad"] = Path("x")

    with pytest.raises(
        TerminalStateValidationError,
        match="Path",
    ):
        TerminalState.from_dict(data)
