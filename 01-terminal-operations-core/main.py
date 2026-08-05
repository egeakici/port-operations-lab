from datetime import datetime

from src.terminal_core.operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)


task = OperationTask(
    task_id="T001",
    task_type=OperationType.DISCHARGE,
    group_id="G001",
    planned_teu=40.0,
    source=TaskLocation(
        location_type=TaskLocationType.VESSEL,
        location_id="V001",
    ),
    target=TaskLocation(
        location_type=TaskLocationType.YARD_BLOCK,
        location_id="R01",
    ),
    priority=3,
    release_time=datetime(
        2026,
        8,
        5,
        10,
        0,
    ),
    due_time=datetime(
        2026,
        8,
        5,
        14,
        0,
    ),
)


print(task)