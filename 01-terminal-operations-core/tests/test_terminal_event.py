from dataclasses import FrozenInstanceError
from datetime import datetime
from enum import Enum
from pathlib import Path

import pytest

from src.terminal_core.exceptions import (
    TerminalEventEntityMismatchError,
    TerminalEventPayloadError,
    TerminalEventValidationError,
)
from src.terminal_core.operation_task import (
    OperationTask,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from src.terminal_core.quay_crane import QuayCrane
from src.terminal_core.terminal_event import (
    TerminalEntityType,
    TerminalEvent,
    TerminalEventType,
    VALID_EVENT_ENTITY_TYPES,
)
from src.terminal_core.vessel import Vessel


OCCURRED_AT = datetime(2026, 8, 5, 10, 30)
STARTED_AT = datetime(2026, 8, 5, 10, 45)


class SampleEnum(Enum):
    VALUE = "value"


class CustomPayloadObject:
    pass


def create_task_started_event(
    **overrides,
) -> TerminalEvent:
    data = {
        "event_id": "EVT-002",
        "event_type": TerminalEventType.TASK_STARTED,
        "occurred_at": OCCURRED_AT,
        "entity_type": TerminalEntityType.OPERATION_TASK,
        "entity_id": "T001",
        "payload": {
            "resource_id": "QC01",
            "completed_teu": 40.0,
            "success": True,
            "details": {
                "previous_status": "assigned",
                "tags": [
                    "discharge",
                    "priority",
                ],
            },
        },
        "correlation_id": "T001",
        "causation_id": "EVT-001",
    }
    data.update(overrides)

    return TerminalEvent(**data)


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


def create_discharge_task() -> OperationTask:
    return OperationTask(
        task_id="T001",
        task_type=OperationType.DISCHARGE,
        group_id="G001",
        planned_teu=100.0,
        source=vessel_location(),
        target=yard_location(),
    )


def assert_events_match(
    event: TerminalEvent,
    loaded_event: TerminalEvent,
) -> None:
    assert loaded_event.event_id == event.event_id
    assert loaded_event.event_type == event.event_type
    assert loaded_event.occurred_at == event.occurred_at
    assert loaded_event.entity_type == event.entity_type
    assert loaded_event.entity_id == event.entity_id
    assert loaded_event.to_dict()["payload"] == event.to_dict()["payload"]
    assert loaded_event.correlation_id == event.correlation_id
    assert loaded_event.causation_id == event.causation_id


def test_valid_task_started_event_is_created() -> None:
    event = create_task_started_event()

    assert event.event_id == "EVT-002"
    assert event.event_type == TerminalEventType.TASK_STARTED
    assert event.occurred_at == OCCURRED_AT
    assert event.entity_type == TerminalEntityType.OPERATION_TASK
    assert event.entity_id == "T001"
    assert event.payload["resource_id"] == "QC01"
    assert event.payload["details"]["tags"] == (
        "discharge",
        "priority",
    )
    assert event.correlation_id == "T001"
    assert event.causation_id == "EVT-001"


def test_default_payload_and_optional_ids() -> None:
    event = TerminalEvent(
        event_id="EVT-001",
        event_type=TerminalEventType.TASK_CREATED,
        occurred_at=OCCURRED_AT,
        entity_type=TerminalEntityType.OPERATION_TASK,
        entity_id="T001",
    )

    assert event.payload == {}
    assert event.correlation_id is None
    assert event.causation_id is None


@pytest.mark.parametrize(
    "overrides,match",
    [
        (
            {
                "event_id": "   ",
            },
            "Event ID",
        ),
        (
            {
                "event_id": 123,
            },
            "Event ID",
        ),
        (
            {
                "event_type": "task_started",
            },
            "Event type",
        ),
        (
            {
                "occurred_at": "2026-08-05T10:30:00",
            },
            "Occurred at",
        ),
        (
            {
                "entity_type": "operation_task",
            },
            "Entity type",
        ),
        (
            {
                "entity_id": "   ",
            },
            "Entity ID",
        ),
        (
            {
                "entity_id": 123,
            },
            "Entity ID",
        ),
        (
            {
                "correlation_id": "   ",
            },
            "Correlation ID",
        ),
        (
            {
                "correlation_id": 123,
            },
            "Correlation ID",
        ),
        (
            {
                "causation_id": "   ",
            },
            "Causation ID",
        ),
        (
            {
                "causation_id": 123,
            },
            "Causation ID",
        ),
        (
            {
                "event_id": "EVT-001",
                "causation_id": "EVT-001",
            },
            "own causation",
        ),
    ],
)
def test_invalid_basic_event_data_is_rejected(
    overrides,
    match,
) -> None:
    with pytest.raises(
        TerminalEventValidationError,
        match=match,
    ):
        create_task_started_event(**overrides)


@pytest.mark.parametrize(
    "event_type,entity_type,entity_id",
    [
        (
            TerminalEventType.VESSEL_ARRIVED,
            TerminalEntityType.VESSEL,
            "V001",
        ),
        (
            TerminalEventType.BERTH_OCCUPANCY_ADDED,
            TerminalEntityType.BERTH,
            "B01",
        ),
        (
            TerminalEventType.CRANE_FAILED,
            TerminalEntityType.QUAY_CRANE,
            "QC01",
        ),
        (
            TerminalEventType.YARD_RESERVATION_CREATED,
            TerminalEntityType.YARD_BLOCK,
            "Y01",
        ),
        (
            TerminalEventType.CONTAINER_GROUP_REGISTERED,
            TerminalEntityType.CONTAINER_GROUP,
            "G001",
        ),
        (
            TerminalEventType.TASK_STARTED,
            TerminalEntityType.OPERATION_TASK,
            "T001",
        ),
    ],
)
def test_valid_event_entity_combinations_are_allowed(
    event_type,
    entity_type,
    entity_id,
) -> None:
    event = TerminalEvent(
        event_id="EVT-001",
        event_type=event_type,
        occurred_at=OCCURRED_AT,
        entity_type=entity_type,
        entity_id=entity_id,
    )

    assert event.entity_type == entity_type


@pytest.mark.parametrize(
    "event_type,entity_type",
    [
        (
            TerminalEventType.TASK_STARTED,
            TerminalEntityType.VESSEL,
        ),
        (
            TerminalEventType.CRANE_FAILED,
            TerminalEntityType.YARD_BLOCK,
        ),
        (
            TerminalEventType.VESSEL_DEPARTED,
            TerminalEntityType.OPERATION_TASK,
        ),
        (
            TerminalEventType.YARD_GROUP_STORED,
            TerminalEntityType.CONTAINER_GROUP,
        ),
    ],
)
def test_event_entity_mismatch_is_rejected(
    event_type,
    entity_type,
) -> None:
    with pytest.raises(
        TerminalEventEntityMismatchError,
        match="requires entity type",
    ):
        TerminalEvent(
            event_id="EVT-001",
            event_type=event_type,
            occurred_at=OCCURRED_AT,
            entity_type=entity_type,
            entity_id="X001",
        )


def test_all_event_types_are_mapped() -> None:
    assert set(VALID_EVENT_ENTITY_TYPES) == set(
        TerminalEventType
    )


def test_nested_json_safe_payload_is_allowed() -> None:
    event = create_task_started_event()

    assert event.payload["details"]["previous_status"] == "assigned"
    assert event.payload["details"]["tags"] == (
        "discharge",
        "priority",
    )


@pytest.mark.parametrize(
    "payload,match",
    [
        (
            {
                1: "bad",
            },
            "Payload key at payload",
        ),
        (
            {
                "": "bad",
            },
            "Payload key at payload",
        ),
        (
            {
                "value": {
                    "bad",
                },
            },
            "payload.value",
        ),
        (
            {
                "value": OCCURRED_AT,
            },
            "payload.value",
        ),
        (
            {
                "value": SampleEnum.VALUE,
            },
            "payload.value",
        ),
        (
            {
                "value": Path("x"),
            },
            "payload.value",
        ),
        (
            {
                "value": b"bytes",
            },
            "payload.value",
        ),
        (
            {
                "value": CustomPayloadObject(),
            },
            "payload.value",
        ),
        (
            {
                "value": float("nan"),
            },
            "payload.value",
        ),
        (
            {
                "value": float("inf"),
            },
            "payload.value",
        ),
        (
            {
                "value": float("-inf"),
            },
            "payload.value",
        ),
        (
            {
                "metrics": [
                    1,
                    {
                        "bad",
                    },
                ],
            },
            "payload.metrics\\[1\\]",
        ),
        (
            None,
            "Payload must be a mapping",
        ),
        (
            [
                "not",
                "mapping",
            ],
            "Payload must be a mapping",
        ),
    ],
)
def test_invalid_payload_values_are_rejected(
    payload,
    match,
) -> None:
    with pytest.raises(
        TerminalEventPayloadError,
        match=match,
    ):
        create_task_started_event(
            payload=payload
        )


def test_event_fields_are_immutable() -> None:
    event = create_task_started_event()

    with pytest.raises(FrozenInstanceError):
        event.entity_id = "T999"


def test_payload_is_deeply_immutable() -> None:
    event = create_task_started_event()

    with pytest.raises(TypeError):
        event.payload["resource_id"] = "QC99"

    with pytest.raises(TypeError):
        event.payload["details"]["x"] = 10

    with pytest.raises(AttributeError):
        event.payload["details"]["tags"].append("late")


def test_input_payload_alias_is_not_kept() -> None:
    original_payload = {
        "details": {
            "resource_id": "QC01",
        },
    }

    event = create_task_started_event(
        payload=original_payload
    )
    original_payload["details"]["resource_id"] = "QC99"

    assert (
        event.payload["details"]["resource_id"]
        == "QC01"
    )


def test_to_dict_result_is_independent() -> None:
    event = create_task_started_event()
    data = event.to_dict()

    data["payload"]["resource_id"] = "QC99"
    data["payload"]["details"]["tags"].append("late")

    assert event.payload["resource_id"] == "QC01"
    assert event.payload["details"]["tags"] == (
        "discharge",
        "priority",
    )


def test_dictionary_round_trip_preserves_event() -> None:
    event = create_task_started_event()
    data = event.to_dict()

    loaded_event = TerminalEvent.from_dict(data)

    assert_events_match(event, loaded_event)
    assert loaded_event.to_dict() == data

    with pytest.raises(TypeError):
        loaded_event.payload["resource_id"] = "QC99"


def test_json_round_trip_preserves_event(tmp_path) -> None:
    event = create_task_started_event()
    file_path = tmp_path / "terminal_event.json"

    event.save_to_json(file_path)
    loaded_event = TerminalEvent.load_from_json(
        file_path
    )

    assert file_path.exists()
    assert_events_match(event, loaded_event)
    assert loaded_event.payload["details"]["tags"] == (
        "discharge",
        "priority",
    )

    with pytest.raises(TypeError):
        loaded_event.payload["details"]["x"] = 10


@pytest.mark.parametrize(
    "snapshot,exception_type,match",
    [
        (
            "not a dict",
            TerminalEventValidationError,
            "dictionary",
        ),
        (
            {
                "event_type": "task_started",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "operation_task",
                "entity_id": "T001",
            },
            TerminalEventValidationError,
            "Invalid terminal event snapshot",
        ),
        (
            {
                "event_id": "EVT-001",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "operation_task",
                "entity_id": "T001",
            },
            TerminalEventValidationError,
            "Invalid terminal event snapshot",
        ),
        (
            {
                "event_id": "EVT-001",
                "event_type": "unknown",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "operation_task",
                "entity_id": "T001",
            },
            TerminalEventValidationError,
            "Invalid terminal event snapshot",
        ),
        (
            {
                "event_id": "EVT-001",
                "event_type": "task_started",
                "occurred_at": "not-a-date",
                "entity_type": "operation_task",
                "entity_id": "T001",
            },
            TerminalEventValidationError,
            "Invalid terminal event snapshot",
        ),
        (
            {
                "event_id": "EVT-001",
                "event_type": "task_started",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "terminal",
                "entity_id": "T001",
            },
            TerminalEventValidationError,
            "Invalid terminal event snapshot",
        ),
        (
            {
                "event_id": "EVT-001",
                "event_type": "task_started",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "operation_task",
            },
            TerminalEventValidationError,
            "Invalid terminal event snapshot",
        ),
        (
            {
                "event_id": "EVT-001",
                "event_type": "task_started",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "vessel",
                "entity_id": "V001",
            },
            TerminalEventEntityMismatchError,
            "requires entity type",
        ),
        (
            {
                "event_id": "EVT-001",
                "event_type": "task_started",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "operation_task",
                "entity_id": "T001",
                "payload": {
                    "bad": {
                        "set",
                    },
                },
            },
            TerminalEventPayloadError,
            "payload.bad",
        ),
        (
            {
                "event_id": "EVT-001",
                "event_type": "task_started",
                "occurred_at": OCCURRED_AT.isoformat(),
                "entity_type": "operation_task",
                "entity_id": "T001",
                "causation_id": "EVT-001",
            },
            TerminalEventValidationError,
            "own causation",
        ),
    ],
)
def test_invalid_snapshots_are_rejected(
    snapshot,
    exception_type,
    match,
) -> None:
    with pytest.raises(
        exception_type,
        match=match,
    ):
        TerminalEvent.from_dict(snapshot)


def test_operation_task_event_chain_is_manual_and_immutable() -> None:
    task = create_discharge_task()
    created_event = TerminalEvent(
        event_id="EVT-001",
        event_type=TerminalEventType.TASK_CREATED,
        occurred_at=OCCURRED_AT,
        entity_type=TerminalEntityType.OPERATION_TASK,
        entity_id=task.task_id,
        payload={
            "task_type": task.task_type.value,
            "group_id": task.group_id,
            "planned_teu": task.planned_teu,
            "source": task.source.to_dict(),
            "target": task.target.to_dict(),
        },
        correlation_id=task.task_id,
    )

    task.mark_ready()
    task.assign_resource("QC01")
    task.start(STARTED_AT)

    started_event = TerminalEvent(
        event_id="EVT-002",
        event_type=TerminalEventType.TASK_STARTED,
        occurred_at=STARTED_AT,
        entity_type=TerminalEntityType.OPERATION_TASK,
        entity_id=task.task_id,
        payload={
            "resource_id": "QC01",
            "started_at": task.started_at.isoformat(),
        },
        correlation_id=task.task_id,
        causation_id=created_event.event_id,
    )

    task.record_progress(40)

    assert created_event.correlation_id == started_event.correlation_id
    assert started_event.causation_id == created_event.event_id
    assert created_event.payload["planned_teu"] == 100.0
    assert started_event.payload["resource_id"] == "QC01"
    assert task.status.name == "IN_PROGRESS"
    assert not hasattr(task, "events")

    with pytest.raises(TypeError):
        started_event.payload["resource_id"] = "QC99"


def test_quay_crane_failed_event_stores_only_ids() -> None:
    vessel = Vessel(
        vessel_id="V001",
        length_m=280.0,
        eta=OCCURRED_AT,
        workload_moves=1500,
        priority=2,
        max_cranes=3,
    )
    crane = QuayCrane(
        crane_id="QC01",
        position_m=120.0,
        moves_per_hour=30.0,
    )

    crane.assign_to_vessel(vessel)
    crane.start_operation()
    interrupted_vessel_id = crane.mark_failed()

    event = TerminalEvent(
        event_id="EVT-QC01-FAILED",
        event_type=TerminalEventType.CRANE_FAILED,
        occurred_at=OCCURRED_AT,
        entity_type=TerminalEntityType.QUAY_CRANE,
        entity_id=crane.crane_id,
        payload={
            "interrupted_vessel_id": interrupted_vessel_id,
        },
    )

    assert event.entity_id == "QC01"
    assert event.payload["interrupted_vessel_id"] == "V001"
    assert "crane" not in event.payload
