from datetime import datetime

import pytest

from src.terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from src.terminal_core.exceptions import (
    InvalidOperationTaskStatusTransitionError,
    OperationRouteError,
    OperationTaskAssignmentError,
    OperationTaskProgressError,
    OperationTaskStateError,
    OperationTaskValidationError,
    TaskLocationValidationError,
)
from src.terminal_core.operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from src.terminal_core.quay_crane import QuayCrane


STARTED_AT = datetime(2026, 8, 5, 10, 0)
RESTARTED_AT = datetime(2026, 8, 5, 10, 45)
COMPLETED_AT = datetime(2026, 8, 5, 11, 30)


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


def create_discharge_task(
    task_id: str = "T001",
    group_id: str = "CG001",
    planned_teu: float = 100.0,
    priority: int = 2,
    release_time: datetime | None = None,
    due_time: datetime | None = None,
    predecessor_task_ids: set[str] | None = None,
) -> OperationTask:
    return OperationTask(
        task_id=task_id,
        task_type=OperationType.DISCHARGE,
        group_id=group_id,
        planned_teu=planned_teu,
        source=vessel_location(),
        target=yard_location(),
        priority=priority,
        release_time=release_time,
        due_time=due_time,
        predecessor_task_ids=(
            set()
            if predecessor_task_ids is None
            else predecessor_task_ids
        ),
    )


def start_task(
    task: OperationTask | None = None,
    resource_id: str = "QC01",
    started_at: datetime = STARTED_AT,
) -> OperationTask:
    if task is None:
        task = create_discharge_task()

    task.mark_ready()
    task.assign_resource(resource_id)
    task.start(started_at)

    return task


def complete_task() -> OperationTask:
    task = start_task()
    task.record_progress(task.planned_teu)
    task.complete(COMPLETED_AT)

    return task


def assert_round_trip_matches(
    task: OperationTask,
) -> None:
    loaded_task = OperationTask.from_dict(
        task.to_dict()
    )

    assert loaded_task.task_id == task.task_id
    assert loaded_task.task_type == task.task_type
    assert loaded_task.group_id == task.group_id
    assert loaded_task.planned_teu == task.planned_teu
    assert loaded_task.source == task.source
    assert loaded_task.target == task.target
    assert loaded_task.priority == task.priority
    assert loaded_task.release_time == task.release_time
    assert loaded_task.due_time == task.due_time
    assert (
        loaded_task.predecessor_task_ids
        == task.predecessor_task_ids
    )
    assert loaded_task.status == task.status
    assert (
        loaded_task.assigned_resource_id
        == task.assigned_resource_id
    )
    assert loaded_task.completed_teu == task.completed_teu
    assert loaded_task.started_at == task.started_at
    assert loaded_task.completed_at == task.completed_at
    assert loaded_task.blocked_reason == task.blocked_reason


def test_valid_discharge_task_is_created() -> None:
    task = create_discharge_task(
        release_time=STARTED_AT,
        due_time=COMPLETED_AT,
        predecessor_task_ids={"T000"},
    )

    assert task.task_id == "T001"
    assert task.status == OperationTaskStatus.CREATED
    assert task.completed_teu == 0.0
    assert task.assigned_resource_id is None
    assert task.started_at is None
    assert task.completed_at is None
    assert task.blocked_reason is None
    assert task.remaining_teu == 100.0
    assert task.progress_ratio == 0.0
    assert task.is_terminal is False


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {
                "task_id": "   ",
            },
            "task ID",
        ),
        (
            {
                "group_id": "   ",
            },
            "group ID",
        ),
        (
            {
                "planned_teu": 0,
            },
            "Planned TEU",
        ),
        (
            {
                "planned_teu": -1,
            },
            "Planned TEU",
        ),
        (
            {
                "planned_teu": True,
            },
            "Planned TEU",
        ),
        (
            {
                "priority": 4,
            },
            "priority",
        ),
        (
            {
                "priority": True,
            },
            "priority",
        ),
        (
            {
                "release_time": "soon",
            },
            "datetime",
        ),
        (
            {
                "predecessor_task_ids": ["T000"],
            },
            "set",
        ),
        (
            {
                "predecessor_task_ids": {"   "},
            },
            "valid task ID",
        ),
        (
            {
                "predecessor_task_ids": {"T001"},
            },
            "own predecessor",
        ),
    ],
)
def test_invalid_basic_task_data_is_rejected(
    kwargs,
    match,
) -> None:
    valid_kwargs = {
        "task_id": "T001",
        "task_type": OperationType.DISCHARGE,
        "group_id": "CG001",
        "planned_teu": 100.0,
        "source": vessel_location(),
        "target": yard_location(),
    }
    valid_kwargs.update(kwargs)

    with pytest.raises(
        OperationTaskValidationError,
        match=match,
    ):
        OperationTask(**valid_kwargs)


def test_float_planned_teu_is_allowed() -> None:
    task = create_discharge_task(
        planned_teu=12.5
    )

    assert task.planned_teu == 12.5


def test_due_time_before_release_time_is_rejected() -> None:
    with pytest.raises(
        OperationTaskValidationError,
        match="Due time",
    ):
        create_discharge_task(
            release_time=COMPLETED_AT,
            due_time=STARTED_AT,
        )


def test_valid_task_locations_are_created() -> None:
    assert vessel_location().location_type == TaskLocationType.VESSEL
    assert yard_location().location_type == TaskLocationType.YARD_BLOCK
    assert gate_location().location_type == TaskLocationType.GATE


def test_invalid_task_location_type_is_rejected() -> None:
    with pytest.raises(
        TaskLocationValidationError,
        match="TaskLocationType",
    ):
        TaskLocation(
            location_type="vessel",
            location_id="V001",
        )


def test_empty_task_location_id_is_rejected() -> None:
    with pytest.raises(
        TaskLocationValidationError,
        match="cannot be empty",
    ):
        TaskLocation(
            location_type=TaskLocationType.VESSEL,
            location_id="   ",
        )


def test_task_location_dictionary_round_trip() -> None:
    location = yard_location()

    assert TaskLocation.from_dict(
        location.to_dict()
    ) == location


def test_invalid_task_location_snapshot_is_rejected() -> None:
    with pytest.raises(
        TaskLocationValidationError,
        match="Invalid task location snapshot",
    ):
        TaskLocation.from_dict(
            {
                "location_type": "rail",
                "location_id": "R01",
            }
        )


@pytest.mark.parametrize(
    "task_type,source,target",
    [
        (
            OperationType.DISCHARGE,
            vessel_location(),
            yard_location(),
        ),
        (
            OperationType.LOAD,
            yard_location(),
            vessel_location(),
        ),
        (
            OperationType.YARD_TRANSFER,
            yard_location("Y01"),
            yard_location("Y02"),
        ),
        (
            OperationType.GATE_IN,
            gate_location(),
            yard_location(),
        ),
        (
            OperationType.GATE_OUT,
            yard_location(),
            gate_location(),
        ),
    ],
)
def test_valid_operation_routes_are_allowed(
    task_type,
    source,
    target,
) -> None:
    task = OperationTask(
        task_id="T001",
        task_type=task_type,
        group_id="CG001",
        planned_teu=25.0,
        source=source,
        target=target,
    )

    assert task.task_type == task_type


@pytest.mark.parametrize(
    "task_type,source,target",
    [
        (
            OperationType.DISCHARGE,
            yard_location(),
            yard_location("Y02"),
        ),
        (
            OperationType.LOAD,
            vessel_location(),
            yard_location(),
        ),
        (
            OperationType.YARD_TRANSFER,
            vessel_location(),
            yard_location(),
        ),
        (
            OperationType.GATE_IN,
            vessel_location(),
            yard_location(),
        ),
        (
            OperationType.GATE_OUT,
            yard_location(),
            vessel_location(),
        ),
    ],
)
def test_invalid_operation_routes_are_rejected(
    task_type,
    source,
    target,
) -> None:
    with pytest.raises(
        OperationRouteError,
        match="must be",
    ):
        OperationTask(
            task_id="T001",
            task_type=task_type,
            group_id="CG001",
            planned_teu=25.0,
            source=source,
            target=target,
        )


def test_same_source_and_target_location_is_rejected() -> None:
    with pytest.raises(
        OperationRouteError,
        match="same",
    ):
        OperationTask(
            task_id="T001",
            task_type=OperationType.YARD_TRANSFER,
            group_id="CG001",
            planned_teu=25.0,
            source=yard_location(),
            target=yard_location(),
        )


def test_initial_lifecycle_reaches_in_progress() -> None:
    task = create_discharge_task()

    task.mark_ready()
    task.assign_resource("QC01")
    task.start(STARTED_AT)

    assert task.status == OperationTaskStatus.IN_PROGRESS
    assert task.assigned_resource_id == "QC01"
    assert task.started_at == STARTED_AT
    assert task.blocked_reason is None


def test_start_without_explicit_time_sets_datetime() -> None:
    task = create_discharge_task()
    task.mark_ready()
    task.assign_resource("QC01")

    task.start()

    assert isinstance(task.started_at, datetime)


def test_start_without_resource_is_rejected() -> None:
    task = create_discharge_task()
    task.mark_ready()

    with pytest.raises(
        OperationTaskAssignmentError,
        match="assigned resource",
    ):
        task.start()


def test_assign_from_created_is_rejected() -> None:
    task = create_discharge_task()

    with pytest.raises(
        InvalidOperationTaskStatusTransitionError,
        match="created -> assigned",
    ):
        task.assign_resource("QC01")


def test_mark_ready_twice_is_rejected() -> None:
    task = create_discharge_task()
    task.mark_ready()

    with pytest.raises(
        InvalidOperationTaskStatusTransitionError,
        match="ready -> ready",
    ):
        task.mark_ready()


def test_in_progress_task_cannot_be_unassigned_directly() -> None:
    task = start_task()

    with pytest.raises(
        OperationTaskStateError,
        match="blocked before unassigning",
    ):
        task.unassign_resource()


def test_assigned_task_can_be_unassigned_to_ready() -> None:
    task = create_discharge_task()
    task.mark_ready()
    task.assign_resource("QC01")

    released_resource_id = task.unassign_resource()

    assert released_resource_id == "QC01"
    assert task.status == OperationTaskStatus.READY
    assert task.assigned_resource_id is None
    assert task.blocked_reason is None


def test_blocked_task_can_be_unassigned_to_ready() -> None:
    task = start_task()
    task.block("Quay crane failure")

    released_resource_id = task.unassign_resource()

    assert released_resource_id == "QC01"
    assert task.status == OperationTaskStatus.READY
    assert task.assigned_resource_id is None
    assert task.blocked_reason is None


def test_unassign_without_resource_is_rejected() -> None:
    task = create_discharge_task()
    task.mark_ready()

    with pytest.raises(
        OperationTaskAssignmentError,
        match="no assigned resource",
    ):
        task.unassign_resource()


def test_progress_metrics_start_at_zero() -> None:
    task = create_discharge_task()

    assert task.completed_teu == 0.0
    assert task.remaining_teu == task.planned_teu
    assert task.progress_ratio == 0.0


def test_partial_and_multiple_progress_is_recorded() -> None:
    task = start_task()

    task.record_progress(30)
    task.record_progress(20)

    assert task.completed_teu == 50.0
    assert task.remaining_teu == 50.0
    assert task.progress_ratio == 0.5


def test_progress_can_reach_planned_teu_without_completing() -> None:
    task = start_task()

    task.record_progress(100.0)

    assert task.completed_teu == task.planned_teu
    assert task.remaining_teu == 0.0
    assert task.progress_ratio == 1.0
    assert task.status == OperationTaskStatus.IN_PROGRESS


@pytest.mark.parametrize(
    "teu",
    [
        0,
        -1,
        True,
    ],
)
def test_invalid_progress_amount_is_rejected(teu) -> None:
    task = start_task()

    with pytest.raises(
        OperationTaskProgressError,
        match="greater than zero",
    ):
        task.record_progress(teu)


def test_progress_cannot_exceed_remaining_teu() -> None:
    task = start_task()
    task.record_progress(80)

    with pytest.raises(
        OperationTaskProgressError,
        match="exceeds",
    ):
        task.record_progress(30)

    assert task.completed_teu == 80


def test_progress_outside_in_progress_is_rejected() -> None:
    task = create_discharge_task()
    task.mark_ready()

    with pytest.raises(
        OperationTaskStateError,
        match="in progress",
    ):
        task.record_progress(10)

    task.assign_resource("QC01")

    with pytest.raises(
        OperationTaskStateError,
        match="in progress",
    ):
        task.record_progress(10)


def test_block_and_resume_preserve_runtime_state() -> None:
    task = start_task()
    task.record_progress(40)

    task.block("Quay crane failure")

    assert task.status == OperationTaskStatus.BLOCKED
    assert task.completed_teu == 40
    assert task.assigned_resource_id == "QC01"
    assert task.blocked_reason == "Quay crane failure"

    task.resume()

    assert task.status == OperationTaskStatus.IN_PROGRESS
    assert task.blocked_reason is None
    assert task.started_at == STARTED_AT
    assert task.completed_teu == 40


def test_empty_block_reason_is_rejected() -> None:
    task = start_task()

    with pytest.raises(
        OperationTaskStateError,
        match="reason",
    ):
        task.block("   ")


def test_ready_task_cannot_be_blocked() -> None:
    task = create_discharge_task()
    task.mark_ready()

    with pytest.raises(
        OperationTaskStateError,
        match="in-progress",
    ):
        task.block("No resource")


def test_resume_without_resource_is_rejected_from_snapshot() -> None:
    task = start_task()
    task.block("Resource failed")
    task.assigned_resource_id = None

    with pytest.raises(
        OperationTaskAssignmentError,
        match="assigned resource",
    ):
        task.resume()


def test_blocked_task_can_be_reassigned_and_started() -> None:
    task = start_task()
    task.record_progress(40)
    task.block("Quay crane failure")

    released_resource_id = task.unassign_resource()
    task.assign_resource("QC02")
    task.start(RESTARTED_AT)

    assert released_resource_id == "QC01"
    assert task.status == OperationTaskStatus.IN_PROGRESS
    assert task.started_at == STARTED_AT
    assert task.completed_teu == 40
    assert task.assigned_resource_id == "QC02"
    assert task.blocked_reason is None


def test_complete_after_full_progress_releases_resource() -> None:
    task = start_task()
    task.record_progress(100)

    released_resource_id = task.complete(COMPLETED_AT)

    assert released_resource_id == "QC01"
    assert task.status == OperationTaskStatus.COMPLETED
    assert task.assigned_resource_id is None
    assert task.completed_at == COMPLETED_AT
    assert task.remaining_teu == 0.0
    assert task.progress_ratio == 1.0
    assert task.is_terminal is True


def test_complete_with_missing_progress_is_rejected() -> None:
    task = start_task()
    task.record_progress(80)

    with pytest.raises(
        OperationTaskProgressError,
        match="all planned TEU",
    ):
        task.complete(COMPLETED_AT)

    assert task.status == OperationTaskStatus.IN_PROGRESS
    assert task.assigned_resource_id == "QC01"


def test_complete_before_started_at_is_rejected() -> None:
    task = start_task()
    task.record_progress(100)

    with pytest.raises(
        OperationTaskValidationError,
        match="earlier",
    ):
        task.complete(
            datetime(2026, 8, 5, 9, 59)
        )


def test_completed_task_cannot_transition_again() -> None:
    task = complete_task()

    with pytest.raises(
        InvalidOperationTaskStatusTransitionError,
        match="completed -> ready",
    ):
        task.mark_ready()


@pytest.mark.parametrize(
    "prepare,expected_resource",
    [
        (
            lambda task: None,
            None,
        ),
        (
            lambda task: task.mark_ready(),
            None,
        ),
        (
            lambda task: (
                task.mark_ready(),
                task.assign_resource("QC01"),
            ),
            "QC01",
        ),
        (
            lambda task: (
                task.mark_ready(),
                task.assign_resource("QC01"),
                task.start(STARTED_AT),
                task.record_progress(25),
                task.block("Resource failed"),
            ),
            "QC01",
        ),
    ],
)
def test_cancel_allowed_states(
    prepare,
    expected_resource,
) -> None:
    task = create_discharge_task()
    prepare(task)

    released_resource_id = task.cancel()

    assert released_resource_id == expected_resource
    assert task.status == OperationTaskStatus.CANCELLED
    assert task.assigned_resource_id is None
    assert task.blocked_reason is None
    assert task.completed_at is None
    assert task.is_terminal is True


def test_cancel_preserves_completed_teu() -> None:
    task = start_task()
    task.record_progress(25)
    task.block("Resource failed")

    task.cancel()

    assert task.completed_teu == 25


def test_in_progress_task_cannot_cancel_directly() -> None:
    task = start_task()

    with pytest.raises(
        InvalidOperationTaskStatusTransitionError,
        match="in_progress -> cancelled",
    ):
        task.cancel()


def test_cancelled_task_cannot_start() -> None:
    task = create_discharge_task()
    task.cancel()

    with pytest.raises(
        OperationTaskAssignmentError,
        match="assigned resource",
    ):
        task.start(STARTED_AT)


def test_fail_from_in_progress_releases_resource() -> None:
    task = start_task()
    task.record_progress(25)

    released_resource_id = task.fail()

    assert released_resource_id == "QC01"
    assert task.status == OperationTaskStatus.FAILED
    assert task.assigned_resource_id is None
    assert task.completed_teu == 25
    assert task.completed_at is None
    assert task.is_terminal is True


def test_fail_from_blocked_releases_resource() -> None:
    task = start_task()
    task.record_progress(25)
    task.block("Resource failed")

    released_resource_id = task.fail()

    assert released_resource_id == "QC01"
    assert task.status == OperationTaskStatus.FAILED
    assert task.blocked_reason is None
    assert task.completed_teu == 25


@pytest.mark.parametrize(
    "prepare",
    [
        lambda task: None,
        lambda task: task.mark_ready(),
        lambda task: (
            task.mark_ready(),
            task.assign_resource("QC01"),
        ),
    ],
)
def test_fail_from_invalid_states_is_rejected(
    prepare,
) -> None:
    task = create_discharge_task()
    prepare(task)

    with pytest.raises(
        InvalidOperationTaskStatusTransitionError,
        match="failed",
    ):
        task.fail()


def test_failed_task_cannot_transition_again() -> None:
    task = start_task()
    task.fail()

    with pytest.raises(
        InvalidOperationTaskStatusTransitionError,
        match="failed -> ready",
    ):
        task.mark_ready()


def test_created_operation_task_dictionary_round_trip() -> None:
    task = create_discharge_task(
        release_time=STARTED_AT,
        due_time=COMPLETED_AT,
        predecessor_task_ids={"T000"},
    )

    assert_round_trip_matches(task)


def test_assigned_operation_task_dictionary_round_trip() -> None:
    task = create_discharge_task()
    task.mark_ready()
    task.assign_resource("QC01")

    assert_round_trip_matches(task)


def test_in_progress_operation_task_dictionary_round_trip() -> None:
    task = start_task()
    task.record_progress(20)

    assert_round_trip_matches(task)


def test_blocked_operation_task_dictionary_round_trip() -> None:
    task = start_task()
    task.record_progress(20)
    task.block("Resource failed")

    assert_round_trip_matches(task)


def test_completed_operation_task_dictionary_round_trip() -> None:
    task = complete_task()

    assert_round_trip_matches(task)


def test_operation_task_json_round_trip(tmp_path) -> None:
    task = start_task()
    task.record_progress(40)
    file_path = tmp_path / "operation_task.json"

    task.save_to_json(file_path)
    loaded_task = OperationTask.load_from_json(file_path)

    assert file_path.exists()
    assert loaded_task.status == task.status
    assert loaded_task.assigned_resource_id == "QC01"
    assert loaded_task.completed_teu == 40
    assert loaded_task.started_at == STARTED_AT


@pytest.mark.parametrize(
    "updates,exception_type,match",
    [
        (
            {
                "task_type": "unknown",
            },
            OperationTaskValidationError,
            "Invalid operation task snapshot",
        ),
        (
            {
                "status": "paused",
            },
            OperationTaskValidationError,
            "Invalid operation task snapshot",
        ),
        (
            {
                "source": {
                    "location_type": "rail",
                    "location_id": "R01",
                },
            },
            TaskLocationValidationError,
            "Invalid task location snapshot",
        ),
        (
            {
                "completed_teu": -1,
            },
            OperationTaskProgressError,
            "Completed TEU",
        ),
        (
            {
                "completed_teu": 120,
            },
            OperationTaskProgressError,
            "exceed",
        ),
        (
            {
                "status": "assigned",
            },
            OperationTaskStateError,
            "Assigned",
        ),
        (
            {
                "status": "in_progress",
                "assigned_resource_id": "QC01",
            },
            OperationTaskStateError,
            "In-progress",
        ),
        (
            {
                "status": "blocked",
                "assigned_resource_id": "QC01",
                "started_at": STARTED_AT.isoformat(),
            },
            OperationTaskStateError,
            "Blocked",
        ),
        (
            {
                "status": "completed",
                "started_at": STARTED_AT.isoformat(),
                "completed_at": COMPLETED_AT.isoformat(),
            },
            OperationTaskStateError,
            "Completed",
        ),
        (
            {
                "status": "completed",
                "completed_teu": 100,
                "started_at": STARTED_AT.isoformat(),
            },
            OperationTaskStateError,
            "Completed",
        ),
        (
            {
                "status": "completed",
                "completed_teu": 100,
                "started_at": STARTED_AT.isoformat(),
                "completed_at": COMPLETED_AT.isoformat(),
                "assigned_resource_id": "QC01",
            },
            OperationTaskStateError,
            "Completed",
        ),
        (
            {
                "status": "failed",
                "assigned_resource_id": "QC01",
                "started_at": STARTED_AT.isoformat(),
            },
            OperationTaskStateError,
            "Failed",
        ),
        (
            {
                "status": "created",
                "completed_teu": 10,
            },
            OperationTaskStateError,
            "Created",
        ),
    ],
)
def test_invalid_operation_task_snapshots_are_rejected(
    updates,
    exception_type,
    match,
) -> None:
    data = create_discharge_task().to_dict()
    data.update(updates)

    with pytest.raises(
        exception_type,
        match=match,
    ):
        OperationTask.from_dict(data)


def test_snapshot_with_same_source_and_target_is_rejected() -> None:
    data = {
        "task_id": "T001",
        "task_type": "yard_transfer",
        "group_id": "CG001",
        "planned_teu": 100,
        "source": yard_location().to_dict(),
        "target": yard_location().to_dict(),
        "status": "created",
        "completed_teu": 0,
    }

    with pytest.raises(
        OperationRouteError,
        match="same",
    ):
        OperationTask.from_dict(data)


def test_snapshot_missing_required_field_is_rejected() -> None:
    data = create_discharge_task().to_dict()
    del data["task_id"]

    with pytest.raises(
        OperationTaskValidationError,
        match="Invalid operation task snapshot",
    ):
        OperationTask.from_dict(data)


def test_operation_task_can_reference_container_group_by_id() -> None:
    group = ContainerGroup(
        group_id="CG001",
        container_size=ContainerSize.FORTY_FT,
        quantity=50,
        flow=ContainerFlow.IMPORT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id="V001",
    )
    task = create_discharge_task(
        group_id=group.group_id,
        planned_teu=80.0,
    )

    assert task.group_id == group.group_id
    assert task.planned_teu <= group.total_teu


def test_group_total_planned_teu_is_terminal_level_rule() -> None:
    group = ContainerGroup(
        group_id="CG001",
        container_size=ContainerSize.FORTY_FT,
        quantity=50,
        flow=ContainerFlow.IMPORT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id="V001",
    )
    tasks = [
        create_discharge_task(
            task_id="T001",
            group_id=group.group_id,
            planned_teu=40.0,
        ),
        create_discharge_task(
            task_id="T002",
            group_id=group.group_id,
            planned_teu=60.0,
        ),
    ]

    assert sum(
        task.planned_teu
        for task in tasks
    ) <= group.total_teu


def test_operation_task_stores_only_quay_crane_resource_id() -> None:
    crane = QuayCrane(
        crane_id="QC01",
        position_m=120.0,
        moves_per_hour=30.0,
    )
    task = create_discharge_task()
    task.mark_ready()

    task.assign_resource(crane.crane_id)

    assert task.assigned_resource_id == crane.crane_id
    assert not hasattr(task, "assigned_resource")
