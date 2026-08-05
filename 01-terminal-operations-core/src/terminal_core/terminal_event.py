from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from src.terminal_core.exceptions import (
    TerminalEventEntityMismatchError,
    TerminalEventPayloadError,
    TerminalEventValidationError,
)


class TerminalEntityType(Enum):
    VESSEL = "vessel"
    BERTH = "berth"
    QUAY_CRANE = "quay_crane"
    YARD_BLOCK = "yard_block"
    CONTAINER_GROUP = "container_group"
    OPERATION_TASK = "operation_task"


class TerminalEventType(Enum):
    VESSEL_ARRIVED = "vessel_arrived"
    VESSEL_WAITING = "vessel_waiting"
    VESSEL_BERTHED = "vessel_berthed"
    VESSEL_OPERATION_STARTED = "vessel_operation_started"
    VESSEL_OPERATION_COMPLETED = "vessel_operation_completed"
    VESSEL_DEPARTED = "vessel_departed"

    BERTH_OCCUPANCY_ADDED = "berth_occupancy_added"
    BERTH_OCCUPANCY_REMOVED = "berth_occupancy_removed"

    CRANE_ASSIGNED = "crane_assigned"
    CRANE_RELEASED = "crane_released"
    CRANE_OPERATION_STARTED = "crane_operation_started"
    CRANE_OPERATION_STOPPED = "crane_operation_stopped"
    CRANE_FAILED = "crane_failed"
    CRANE_REPAIRED = "crane_repaired"
    CRANE_MAINTENANCE_STARTED = "crane_maintenance_started"
    CRANE_MAINTENANCE_COMPLETED = "crane_maintenance_completed"

    YARD_RESERVATION_CREATED = "yard_reservation_created"
    YARD_RESERVATION_CANCELLED = "yard_reservation_cancelled"
    YARD_RESERVATION_COMMITTED = "yard_reservation_committed"
    YARD_GROUP_STORED = "yard_group_stored"
    YARD_GROUP_RELEASED = "yard_group_released"
    YARD_BLOCK_CLOSED = "yard_block_closed"
    YARD_BLOCK_REOPENED = "yard_block_reopened"
    YARD_BLOCK_MAINTENANCE_STARTED = "yard_block_maintenance_started"
    YARD_BLOCK_MAINTENANCE_COMPLETED = "yard_block_maintenance_completed"

    CONTAINER_GROUP_REGISTERED = "container_group_registered"

    TASK_CREATED = "task_created"
    TASK_READY = "task_ready"
    TASK_ASSIGNED = "task_assigned"
    TASK_UNASSIGNED = "task_unassigned"
    TASK_STARTED = "task_started"
    TASK_PROGRESS_RECORDED = "task_progress_recorded"
    TASK_BLOCKED = "task_blocked"
    TASK_RESUMED = "task_resumed"
    TASK_COMPLETED = "task_completed"
    TASK_CANCELLED = "task_cancelled"
    TASK_FAILED = "task_failed"


VALID_EVENT_ENTITY_TYPES: dict[
    TerminalEventType,
    TerminalEntityType,
] = {
    TerminalEventType.VESSEL_ARRIVED: TerminalEntityType.VESSEL,
    TerminalEventType.VESSEL_WAITING: TerminalEntityType.VESSEL,
    TerminalEventType.VESSEL_BERTHED: TerminalEntityType.VESSEL,
    TerminalEventType.VESSEL_OPERATION_STARTED: TerminalEntityType.VESSEL,
    TerminalEventType.VESSEL_OPERATION_COMPLETED: TerminalEntityType.VESSEL,
    TerminalEventType.VESSEL_DEPARTED: TerminalEntityType.VESSEL,
    TerminalEventType.BERTH_OCCUPANCY_ADDED: TerminalEntityType.BERTH,
    TerminalEventType.BERTH_OCCUPANCY_REMOVED: TerminalEntityType.BERTH,
    TerminalEventType.CRANE_ASSIGNED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.CRANE_RELEASED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.CRANE_OPERATION_STARTED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.CRANE_OPERATION_STOPPED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.CRANE_FAILED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.CRANE_REPAIRED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.CRANE_MAINTENANCE_STARTED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.CRANE_MAINTENANCE_COMPLETED: TerminalEntityType.QUAY_CRANE,
    TerminalEventType.YARD_RESERVATION_CREATED: TerminalEntityType.YARD_BLOCK,
    TerminalEventType.YARD_RESERVATION_CANCELLED: TerminalEntityType.YARD_BLOCK,
    TerminalEventType.YARD_RESERVATION_COMMITTED: TerminalEntityType.YARD_BLOCK,
    TerminalEventType.YARD_GROUP_STORED: TerminalEntityType.YARD_BLOCK,
    TerminalEventType.YARD_GROUP_RELEASED: TerminalEntityType.YARD_BLOCK,
    TerminalEventType.YARD_BLOCK_CLOSED: TerminalEntityType.YARD_BLOCK,
    TerminalEventType.YARD_BLOCK_REOPENED: TerminalEntityType.YARD_BLOCK,
    TerminalEventType.YARD_BLOCK_MAINTENANCE_STARTED: (
        TerminalEntityType.YARD_BLOCK
    ),
    TerminalEventType.YARD_BLOCK_MAINTENANCE_COMPLETED: (
        TerminalEntityType.YARD_BLOCK
    ),
    TerminalEventType.CONTAINER_GROUP_REGISTERED: (
        TerminalEntityType.CONTAINER_GROUP
    ),
    TerminalEventType.TASK_CREATED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_READY: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_ASSIGNED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_UNASSIGNED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_STARTED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_PROGRESS_RECORDED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_BLOCKED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_RESUMED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_COMPLETED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_CANCELLED: TerminalEntityType.OPERATION_TASK,
    TerminalEventType.TASK_FAILED: TerminalEntityType.OPERATION_TASK,
}


@dataclass(frozen=True)
class TerminalEvent:
    event_id: str
    event_type: TerminalEventType
    occurred_at: datetime
    entity_type: TerminalEntityType
    entity_id: str
    payload: Mapping[str, Any] = field(
        default_factory=dict,
    )
    correlation_id: str | None = None
    causation_id: str | None = None

    def __post_init__(self) -> None:
        self._validate_required_id(
            self.event_id,
            "Event ID",
        )

        if not isinstance(
            self.event_type,
            TerminalEventType,
        ):
            raise TerminalEventValidationError(
                "Event type must be a TerminalEventType value."
            )

        if not isinstance(
            self.occurred_at,
            datetime,
        ):
            raise TerminalEventValidationError(
                "Occurred at must be a datetime value."
            )

        if not isinstance(
            self.entity_type,
            TerminalEntityType,
        ):
            raise TerminalEventValidationError(
                "Entity type must be a TerminalEntityType value."
            )

        self._validate_required_id(
            self.entity_id,
            "Entity ID",
        )
        self._validate_optional_id(
            self.correlation_id,
            "Correlation ID",
        )
        self._validate_optional_id(
            self.causation_id,
            "Causation ID",
        )

        if self.causation_id == self.event_id:
            raise TerminalEventValidationError(
                "An event cannot be its own causation event."
            )

        self._validate_event_entity_match()

        if not isinstance(self.payload, Mapping):
            raise TerminalEventPayloadError(
                "Payload must be a mapping."
            )

        frozen_payload = _freeze_json_value(
            self.payload,
            "payload",
        )

        object.__setattr__(
            self,
            "payload",
            frozen_payload,
        )

    @staticmethod
    def _validate_required_id(
        value: str,
        field_name: str,
    ) -> None:
        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise TerminalEventValidationError(
                f"{field_name} cannot be empty."
            )

    @staticmethod
    def _validate_optional_id(
        value: str | None,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise TerminalEventValidationError(
                f"{field_name} cannot be empty."
            )

    def _validate_event_entity_match(self) -> None:
        expected_entity_type = (
            VALID_EVENT_ENTITY_TYPES[
                self.event_type
            ]
        )

        if self.entity_type != expected_entity_type:
            raise TerminalEventEntityMismatchError(
                f"Event type {self.event_type.value} requires "
                f"entity type {expected_entity_type.value}, "
                f"not {self.entity_type.value}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat(),
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "payload": _thaw_json_value(
                self.payload
            ),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> TerminalEvent:
        if not isinstance(data, dict):
            raise TerminalEventValidationError(
                "Invalid terminal event snapshot: "
                "data must be a dictionary."
            )

        try:
            event_id = data["event_id"]
            event_type = TerminalEventType(
                data["event_type"]
            )
            occurred_at = datetime.fromisoformat(
                data["occurred_at"]
            )
            entity_type = TerminalEntityType(
                data["entity_type"]
            )
            entity_id = data["entity_id"]
            payload = data.get(
                "payload",
                {},
            )
            correlation_id = data.get(
                "correlation_id"
            )
            causation_id = data.get(
                "causation_id"
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise TerminalEventValidationError(
                f"Invalid terminal event snapshot: {error}"
            ) from error

        return cls(
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
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
    ) -> TerminalEvent:
        path = Path(file_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return cls.from_dict(data)


def _freeze_json_value(
    value: Any,
    path: str,
) -> Any:
    if value is None or isinstance(
        value,
        (str, bool, int),
    ):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TerminalEventPayloadError(
                f"Invalid payload value at {path}: "
                "float must be finite."
            )

        return value

    if isinstance(value, Mapping):
        frozen_items = {}

        for key, item in value.items():
            if (
                not isinstance(key, str)
                or not key.strip()
            ):
                raise TerminalEventPayloadError(
                    f"Payload key at {path} must be a "
                    "non-empty string."
                )

            frozen_items[key] = _freeze_json_value(
                item,
                f"{path}.{key}",
            )

        return MappingProxyType(frozen_items)

    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(
                item,
                f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        )

    raise TerminalEventPayloadError(
        f"Invalid payload value at {path}: "
        f"{type(value).__name__} is not JSON-safe."
    )


def _thaw_json_value(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _thaw_json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [
            _thaw_json_value(item)
            for item in value
        ]

    return value
