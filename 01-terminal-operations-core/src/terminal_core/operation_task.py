from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .exceptions import (
    InvalidOperationTaskStatusTransitionError,
    OperationRouteError,
    OperationTaskAssignmentError,
    OperationTaskProgressError,
    OperationTaskStateError,
    OperationTaskValidationError,
    TaskLocationValidationError,
)


PROGRESS_ABS_TOLERANCE = 1e-9


class OperationType(Enum):
    DISCHARGE = "discharge"
    LOAD = "load"
    YARD_TRANSFER = "yard_transfer"
    GATE_IN = "gate_in"
    GATE_OUT = "gate_out"


class TaskLocationType(Enum):
    VESSEL = "vessel"
    YARD_BLOCK = "yard_block"
    GATE = "gate"


class OperationTaskStatus(Enum):
    CREATED = "created"
    READY = "ready"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


VALID_OPERATION_ROUTES = {
    OperationType.DISCHARGE: (
        TaskLocationType.VESSEL,
        TaskLocationType.YARD_BLOCK,
    ),
    OperationType.LOAD: (
        TaskLocationType.YARD_BLOCK,
        TaskLocationType.VESSEL,
    ),
    OperationType.YARD_TRANSFER: (
        TaskLocationType.YARD_BLOCK,
        TaskLocationType.YARD_BLOCK,
    ),
    OperationType.GATE_IN: (
        TaskLocationType.GATE,
        TaskLocationType.YARD_BLOCK,
    ),
    OperationType.GATE_OUT: (
        TaskLocationType.YARD_BLOCK,
        TaskLocationType.GATE,
    ),
}


VALID_OPERATION_TASK_STATUS_TRANSITIONS = {
    OperationTaskStatus.CREATED: {
        OperationTaskStatus.READY,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.READY: {
        OperationTaskStatus.ASSIGNED,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.ASSIGNED: {
        OperationTaskStatus.READY,
        OperationTaskStatus.IN_PROGRESS,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.IN_PROGRESS: {
        OperationTaskStatus.BLOCKED,
        OperationTaskStatus.COMPLETED,
        OperationTaskStatus.FAILED,
    },
    OperationTaskStatus.BLOCKED: {
        OperationTaskStatus.READY,
        OperationTaskStatus.IN_PROGRESS,
        OperationTaskStatus.CANCELLED,
        OperationTaskStatus.FAILED,
    },
    OperationTaskStatus.COMPLETED: set(),
    OperationTaskStatus.CANCELLED: set(),
    OperationTaskStatus.FAILED: set(),
}


@dataclass(frozen=True)
class TaskLocation:
    location_type: TaskLocationType
    location_id: str

    def __post_init__(self) -> None:
        if not isinstance(
            self.location_type,
            TaskLocationType,
        ):
            raise TaskLocationValidationError(
                "Location type must be a "
                "TaskLocationType value."
            )

        if (
            not isinstance(self.location_id, str)
            or not self.location_id.strip()
        ):
            raise TaskLocationValidationError(
                "Task location ID cannot be empty."
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "location_type": self.location_type.value,
            "location_id": self.location_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> TaskLocation:
        try:
            return cls(
                location_type=TaskLocationType(
                    data["location_type"]
                ),
                location_id=data["location_id"],
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            TaskLocationValidationError,
        ) as error:
            raise TaskLocationValidationError(
                f"Invalid task location snapshot: {error}"
            ) from error


@dataclass
class OperationTask:
    task_id: str
    task_type: OperationType
    group_id: str
    planned_teu: float
    source: TaskLocation
    target: TaskLocation
    priority: int = 2
    release_time: datetime | None = None
    due_time: datetime | None = None
    predecessor_task_ids: set[str] = field(
        default_factory=set,
    )

    status: OperationTaskStatus = field(
        default=OperationTaskStatus.CREATED,
        init=False,
    )

    completed_teu: float = field(
        default=0.0,
        init=False,
    )

    assigned_resource_id: str | None = field(
        default=None,
        init=False,
    )

    started_at: datetime | None = field(
        default=None,
        init=False,
    )

    completed_at: datetime | None = field(
        default=None,
        init=False,
    )

    blocked_reason: str | None = field(
        default=None,
        init=False,
    )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.task_id, str)
            or not self.task_id.strip()
        ):
            raise OperationTaskValidationError(
                "Operation task ID cannot be empty."
            )

        if not isinstance(
            self.task_type,
            OperationType,
        ):
            raise OperationTaskValidationError(
                "Task type must be an OperationType value."
            )

        if (
            not isinstance(self.group_id, str)
            or not self.group_id.strip()
        ):
            raise OperationTaskValidationError(
                "Container group ID cannot be empty."
            )

        if (
            isinstance(self.planned_teu, bool)
            or not isinstance(
                self.planned_teu,
                (int, float),
            )
            or self.planned_teu <= 0
        ):
            raise OperationTaskValidationError(
                "Planned TEU must be greater than zero."
            )

        if not isinstance(
            self.source,
            TaskLocation,
        ):
            raise OperationTaskValidationError(
                "Task source must be a TaskLocation."
            )

        if not isinstance(
            self.target,
            TaskLocation,
        ):
            raise OperationTaskValidationError(
                "Task target must be a TaskLocation."
            )

        if self.source == self.target:
            raise OperationRouteError(
                "Task source and target cannot be the same."
            )

        self._validate_route()

        if (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
            or self.priority not in {1, 2, 3}
        ):
            raise OperationTaskValidationError(
                "Task priority must be 1, 2, or 3."
            )

        self._validate_optional_datetime(
            self.release_time,
            "Release time",
        )
        self._validate_optional_datetime(
            self.due_time,
            "Due time",
        )

        if (
            self.release_time is not None
            and self.due_time is not None
            and self.due_time < self.release_time
        ):
            raise OperationTaskValidationError(
                "Due time cannot be earlier "
                "than release time."
            )

        if not isinstance(
            self.predecessor_task_ids,
            set,
        ):
            raise OperationTaskValidationError(
                "Predecessor task IDs must be a set."
            )

        for predecessor_id in (
            self.predecessor_task_ids
        ):
            if (
                not isinstance(predecessor_id, str)
                or not predecessor_id.strip()
            ):
                raise OperationTaskValidationError(
                    "Every predecessor must have "
                    "a valid task ID."
                )

        if (
            self.task_id
            in self.predecessor_task_ids
        ):
            raise OperationTaskValidationError(
                "A task cannot be its own predecessor."
            )

        self.predecessor_task_ids = set(
            self.predecessor_task_ids
        )

    @property
    def remaining_teu(self) -> float:
        return max(
            0.0,
            self.planned_teu - self.completed_teu,
        )

    @property
    def progress_ratio(self) -> float:
        return min(
            1.0,
            max(
                0.0,
                self.completed_teu / self.planned_teu,
            ),
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            OperationTaskStatus.COMPLETED,
            OperationTaskStatus.CANCELLED,
            OperationTaskStatus.FAILED,
        }

    @staticmethod
    def _validate_optional_datetime(
        value: datetime | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if not isinstance(value, datetime):
            raise OperationTaskValidationError(
                f"{field_name} must be a datetime value."
            )

    def _validate_route(self) -> None:
        expected_source_type, expected_target_type = (
            VALID_OPERATION_ROUTES[
                self.task_type
            ]
        )

        actual_source_type = (
            self.source.location_type
        )

        actual_target_type = (
            self.target.location_type
        )

        if (
            actual_source_type
            != expected_source_type
        ):
            raise OperationRouteError(
                f"{self.task_type.value} task source "
                f"must be "
                f"{expected_source_type.value}, not "
                f"{actual_source_type.value}."
            )

        if (
            actual_target_type
            != expected_target_type
        ):
            raise OperationRouteError(
                f"{self.task_type.value} task target "
                f"must be "
                f"{expected_target_type.value}, not "
                f"{actual_target_type.value}."
            )

    def _transition_to(
        self,
        new_status: OperationTaskStatus,
    ) -> None:
        if not isinstance(
            new_status,
            OperationTaskStatus,
        ):
            raise InvalidOperationTaskStatusTransitionError(
                "New task status must be an "
                "OperationTaskStatus value."
            )

        allowed_statuses = (
            VALID_OPERATION_TASK_STATUS_TRANSITIONS[
                self.status
            ]
        )

        if new_status not in allowed_statuses:
            raise InvalidOperationTaskStatusTransitionError(
                f"Invalid operation task status "
                f"transition: "
                f"{self.status.value} -> "
                f"{new_status.value}."
            )

        self.status = new_status

    def mark_ready(self) -> None:
        self._transition_to(
            OperationTaskStatus.READY
        )

    def assign_resource(
        self,
        resource_id: str,
    ) -> None:
        if (
            not isinstance(resource_id, str)
            or not resource_id.strip()
        ):
            raise OperationTaskAssignmentError(
                "Assigned resource ID cannot be empty."
            )

        self._transition_to(
            OperationTaskStatus.ASSIGNED
        )

        self.assigned_resource_id = resource_id

    def unassign_resource(self) -> str:
        if self.assigned_resource_id is None:
            raise OperationTaskAssignmentError(
                "Operation task has no "
                "assigned resource."
            )

        if self.status == OperationTaskStatus.IN_PROGRESS:
            raise OperationTaskStateError(
                "In-progress operation tasks must be "
                "blocked before unassigning resources."
            )

        resource_id = self.assigned_resource_id

        self._transition_to(
            OperationTaskStatus.READY
        )

        self.assigned_resource_id = None
        self.blocked_reason = None

        return resource_id

    def start(
        self,
        started_at: datetime | None = None,
    ) -> None:
        if self.status != OperationTaskStatus.ASSIGNED:
            raise OperationTaskStateError(
                "Operation task can only start from "
                "assigned status."
            )

        if self.assigned_resource_id is None:
            raise OperationTaskAssignmentError(
                "Operation task cannot start without "
                "an assigned resource."
            )

        self._validate_optional_datetime(
            started_at,
            "Started at",
        )

        actual_started_at = (
            started_at
            if started_at is not None
            else datetime.now()
        )

        self._transition_to(
            OperationTaskStatus.IN_PROGRESS
        )

        if self.started_at is None:
            self.started_at = actual_started_at

        self.blocked_reason = None

    def record_progress(
        self,
        teu: float,
    ) -> None:
        if self.status != OperationTaskStatus.IN_PROGRESS:
            raise OperationTaskStateError(
                "Operation task progress can only be "
                "recorded while in progress."
            )

        if (
            isinstance(teu, bool)
            or not isinstance(
                teu,
                (int, float),
            )
            or teu <= 0
        ):
            raise OperationTaskProgressError(
                "Progress TEU must be greater than zero."
            )

        new_completed_teu = (
            self.completed_teu
            + teu
        )

        if (
            new_completed_teu > self.planned_teu
            and not math.isclose(
                new_completed_teu,
                self.planned_teu,
                abs_tol=PROGRESS_ABS_TOLERANCE,
            )
        ):
            raise OperationTaskProgressError(
                f"Progress {new_completed_teu} TEU exceeds "
                f"planned TEU {self.planned_teu}."
            )

        if math.isclose(
            new_completed_teu,
            self.planned_teu,
            abs_tol=PROGRESS_ABS_TOLERANCE,
        ):
            self.completed_teu = self.planned_teu
        else:
            self.completed_teu = new_completed_teu

    def block(
        self,
        reason: str,
    ) -> None:
        if self.status != OperationTaskStatus.IN_PROGRESS:
            raise OperationTaskStateError(
                "Operation task can only be blocked "
                "while in-progress."
            )

        if (
            not isinstance(reason, str)
            or not reason.strip()
        ):
            raise OperationTaskStateError(
                "Block reason cannot be empty."
            )

        if self.assigned_resource_id is None:
            raise OperationTaskAssignmentError(
                "Operation task cannot be blocked without "
                "an assigned resource."
            )

        self._transition_to(OperationTaskStatus.BLOCKED)

        self.blocked_reason = reason

    def resume(self) -> None:
        if self.status != OperationTaskStatus.BLOCKED:
            raise OperationTaskStateError(
                "Operation task can only resume from "
                "blocked status."
            )

        if self.assigned_resource_id is None:
            raise OperationTaskAssignmentError(
                "Operation task cannot resume without "
                "an assigned resource."
            )

        self._transition_to(
            OperationTaskStatus.IN_PROGRESS
        )

        self.blocked_reason = None

    def complete(
        self,
        completed_at: datetime | None = None,
    ) -> str:
        if self.assigned_resource_id is None:
            raise OperationTaskAssignmentError(
                "Operation task cannot complete without "
                "an assigned resource."
            )

        if not math.isclose(
            self.completed_teu,
            self.planned_teu,
            abs_tol=PROGRESS_ABS_TOLERANCE,
        ):
            raise OperationTaskProgressError(
                "Operation task cannot complete before "
                "all planned TEU is complete."
            )

        self._validate_optional_datetime(
            completed_at,
            "Completed at",
        )

        actual_completed_at = (
            completed_at
            if completed_at is not None
            else datetime.now()
        )

        if (
            self.started_at is not None
            and actual_completed_at < self.started_at
        ):
            raise OperationTaskValidationError(
                "Completed at cannot be earlier than "
                "started at."
            )

        resource_id = self.assigned_resource_id

        self._transition_to(
            OperationTaskStatus.COMPLETED
        )

        self.completed_teu = self.planned_teu
        self.completed_at = actual_completed_at
        self.assigned_resource_id = None
        self.blocked_reason = None

        return resource_id

    def cancel(self) -> str | None:
        resource_id = self.assigned_resource_id

        self._transition_to(
            OperationTaskStatus.CANCELLED
        )

        self.assigned_resource_id = None
        self.blocked_reason = None

        return resource_id

    def fail(self) -> str | None:
        resource_id = self.assigned_resource_id

        self._transition_to(
            OperationTaskStatus.FAILED
        )

        self.assigned_resource_id = None
        self.blocked_reason = None

        return resource_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "group_id": self.group_id,
            "planned_teu": self.planned_teu,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "priority": self.priority,
            "release_time": (
                self.release_time.isoformat()
                if self.release_time is not None
                else None
            ),
            "due_time": (
                self.due_time.isoformat()
                if self.due_time is not None
                else None
            ),
            "predecessor_task_ids": sorted(
                self.predecessor_task_ids
            ),
            "status": self.status.value,
            "assigned_resource_id": (
                self.assigned_resource_id
            ),
            "completed_teu": self.completed_teu,
            "started_at": (
                self.started_at.isoformat()
                if self.started_at is not None
                else None
            ),
            "completed_at": (
                self.completed_at.isoformat()
                if self.completed_at is not None
                else None
            ),
            "blocked_reason": self.blocked_reason,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> OperationTask:
        try:
            task = cls(
                task_id=data["task_id"],
                task_type=OperationType(
                    data["task_type"]
                ),
                group_id=data["group_id"],
                planned_teu=data["planned_teu"],
                source=TaskLocation.from_dict(
                    data["source"]
                ),
                target=TaskLocation.from_dict(
                    data["target"]
                ),
                priority=data.get(
                    "priority",
                    2,
                ),
                release_time=cls._datetime_from_snapshot(
                    data.get("release_time"),
                    "release_time",
                ),
                due_time=cls._datetime_from_snapshot(
                    data.get("due_time"),
                    "due_time",
                ),
                predecessor_task_ids=set(
                    data.get(
                        "predecessor_task_ids",
                        [],
                    )
                ),
            )

            status = OperationTaskStatus(
                data["status"]
            )

            task._restore_state(
                status=status,
                assigned_resource_id=data.get(
                    "assigned_resource_id"
                ),
                completed_teu=data.get(
                    "completed_teu",
                    0.0,
                ),
                started_at=cls._datetime_from_snapshot(
                    data.get("started_at"),
                    "started_at",
                ),
                completed_at=cls._datetime_from_snapshot(
                    data.get("completed_at"),
                    "completed_at",
                ),
                blocked_reason=data.get(
                    "blocked_reason"
                ),
            )
        except (
            OperationRouteError,
            TaskLocationValidationError,
        ):
            raise
        except (
            KeyError,
            TypeError,
            ValueError,
            OperationTaskValidationError,
        ) as error:
            raise OperationTaskValidationError(
                f"Invalid operation task snapshot: {error}"
            ) from error

        return task

    @staticmethod
    def _datetime_from_snapshot(
        value: str | None,
        field_name: str,
    ) -> datetime | None:
        if value is None:
            return None

        if not isinstance(value, str):
            raise OperationTaskValidationError(
                f"{field_name} must be an ISO datetime string."
            )

        return datetime.fromisoformat(value)

    def _restore_state(
        self,
        status: OperationTaskStatus,
        assigned_resource_id: str | None,
        completed_teu: float,
        started_at: datetime | None,
        completed_at: datetime | None,
        blocked_reason: str | None,
    ) -> None:
        if not isinstance(
            status,
            OperationTaskStatus,
        ):
            raise OperationTaskValidationError(
                "Invalid operation task status."
            )

        if (
            isinstance(completed_teu, bool)
            or not isinstance(
                completed_teu,
                (int, float),
            )
            or completed_teu < 0
        ):
            raise OperationTaskProgressError(
                "Completed TEU must be zero or greater."
            )

        normalized_completed_teu = completed_teu

        if (
            completed_teu > self.planned_teu
            and not math.isclose(
                completed_teu,
                self.planned_teu,
                abs_tol=PROGRESS_ABS_TOLERANCE,
            )
        ):
            raise OperationTaskProgressError(
                "Completed TEU cannot exceed planned TEU."
            )

        if math.isclose(
            completed_teu,
            self.planned_teu,
            abs_tol=PROGRESS_ABS_TOLERANCE,
        ):
            normalized_completed_teu = self.planned_teu

        if (
            assigned_resource_id is not None
            and (
                not isinstance(
                    assigned_resource_id,
                    str,
                )
                or not assigned_resource_id.strip()
            )
        ):
            raise OperationTaskAssignmentError(
                "Assigned resource ID cannot be empty."
            )

        self._validate_optional_datetime(
            started_at,
            "Started at",
        )
        self._validate_optional_datetime(
            completed_at,
            "Completed at",
        )

        if (
            started_at is not None
            and completed_at is not None
            and completed_at < started_at
        ):
            raise OperationTaskValidationError(
                "Completed at cannot be earlier than "
                "started at."
            )

        if (
            blocked_reason is not None
            and (
                not isinstance(blocked_reason, str)
                or not blocked_reason.strip()
            )
        ):
            raise OperationTaskStateError(
                "Blocked reason cannot be empty."
            )

        self._validate_restored_status_invariants(
            status=status,
            assigned_resource_id=assigned_resource_id,
            completed_teu=normalized_completed_teu,
            started_at=started_at,
            completed_at=completed_at,
            blocked_reason=blocked_reason,
        )

        self.status = status
        self.assigned_resource_id = assigned_resource_id
        self.completed_teu = normalized_completed_teu
        self.started_at = started_at
        self.completed_at = completed_at
        self.blocked_reason = blocked_reason

    def _validate_restored_status_invariants(
        self,
        status: OperationTaskStatus,
        assigned_resource_id: str | None,
        completed_teu: float,
        started_at: datetime | None,
        completed_at: datetime | None,
        blocked_reason: str | None,
    ) -> None:
        if status == OperationTaskStatus.CREATED:
            if (
                assigned_resource_id is not None
                or not math.isclose(
                    completed_teu,
                    0.0,
                    abs_tol=PROGRESS_ABS_TOLERANCE,
                )
                or started_at is not None
                or completed_at is not None
                or blocked_reason is not None
            ):
                raise OperationTaskStateError(
                    "Created operation tasks cannot have "
                    "runtime state."
                )

            return

        if status == OperationTaskStatus.READY:
            if (
                assigned_resource_id is not None
                or completed_at is not None
                or blocked_reason is not None
            ):
                raise OperationTaskStateError(
                    "Ready operation tasks cannot have "
                    "assigned resources, completion times, "
                    "or block reasons."
                )

            return

        if status == OperationTaskStatus.ASSIGNED:
            if (
                assigned_resource_id is None
                or completed_at is not None
                or blocked_reason is not None
            ):
                raise OperationTaskStateError(
                    "Assigned operation tasks require a "
                    "resource and cannot have completion "
                    "times or block reasons."
                )

            return

        if status == OperationTaskStatus.IN_PROGRESS:
            if (
                assigned_resource_id is None
                or started_at is None
                or completed_at is not None
                or blocked_reason is not None
            ):
                raise OperationTaskStateError(
                    "In-progress operation tasks require "
                    "a resource and start time only."
                )

            return

        if status == OperationTaskStatus.BLOCKED:
            if (
                assigned_resource_id is None
                or started_at is None
                or completed_at is not None
                or blocked_reason is None
            ):
                raise OperationTaskStateError(
                    "Blocked operation tasks require a "
                    "resource, start time, and block reason."
                )

            return

        if status == OperationTaskStatus.COMPLETED:
            if not math.isclose(
                completed_teu,
                self.planned_teu,
                abs_tol=PROGRESS_ABS_TOLERANCE,
            ):
                raise OperationTaskProgressError(
                    "Completed operation tasks require "
                    "all planned TEU to be complete."
                )

            if (
                assigned_resource_id is not None
                or started_at is None
                or completed_at is None
                or blocked_reason is not None
            ):
                raise OperationTaskStateError(
                    "Completed operation tasks require "
                    "full progress, start time, completion "
                    "time, and no assigned resource."
                )

            return

        if status == OperationTaskStatus.CANCELLED:
            if (
                assigned_resource_id is not None
                or completed_at is not None
                or blocked_reason is not None
            ):
                raise OperationTaskStateError(
                    "Cancelled operation tasks cannot have "
                    "assigned resources, completion times, "
                    "or block reasons."
                )

            return

        if status == OperationTaskStatus.FAILED:
            if (
                assigned_resource_id is not None
                or started_at is None
                or completed_at is not None
                or blocked_reason is not None
            ):
                raise OperationTaskStateError(
                    "Failed operation tasks require a start "
                    "time and no assigned resource."
                )

    def save_to_json(
        self,
        file_path: str | Path,
    ) -> None:
        path = Path(file_path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self.to_dict(),
                file,
                ensure_ascii=False,
                indent=4,
            )

    @classmethod
    def load_from_json(
        cls,
        file_path: str | Path,
    ) -> OperationTask:
        path = Path(file_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return cls.from_dict(data)
