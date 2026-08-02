from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.terminal_core.exceptions import (
    CraneAssignmentError,
    CraneOperationError,
    InvalidCraneStatusTransitionError,
    QuayCraneValidationError,
)
from src.terminal_core.vessel import Vessel


class CraneStatus(Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    OPERATING = "operating"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


VALID_CRANE_STATUS_TRANSITIONS = {
    CraneStatus.AVAILABLE: {
        CraneStatus.ASSIGNED,
        CraneStatus.FAILED,
        CraneStatus.MAINTENANCE,
    },
    CraneStatus.ASSIGNED: {
        CraneStatus.AVAILABLE,
        CraneStatus.OPERATING,
        CraneStatus.FAILED,
    },
    CraneStatus.OPERATING: {
        CraneStatus.ASSIGNED,
        CraneStatus.FAILED,
    },
    CraneStatus.FAILED: {
        CraneStatus.AVAILABLE,
    },
    CraneStatus.MAINTENANCE: {
        CraneStatus.AVAILABLE,
    },
}


@dataclass
class QuayCrane:
    crane_id: str
    position_m: float
    moves_per_hour: float

    status: CraneStatus = field(
        default=CraneStatus.AVAILABLE,
        init=False,
    )

    assigned_vessel_id: str | None = field(
        default=None,
        init=False,
    )

    def __post_init__(self) -> None:
        if not self.crane_id.strip():
            raise QuayCraneValidationError(
                "Crane ID cannot be empty."
            )

        if self.position_m < 0:
            raise QuayCraneValidationError(
                "Crane position cannot be negative."
            )

        if self.moves_per_hour <= 0:
            raise QuayCraneValidationError(
                "Crane productivity must be greater than zero."
            )

    def _transition_to(
        self,
        new_status: CraneStatus,
    ) -> None:
        allowed_statuses = VALID_CRANE_STATUS_TRANSITIONS[
            self.status
        ]

        if new_status not in allowed_statuses:
            raise InvalidCraneStatusTransitionError(
                f"Invalid crane status transition: "
                f"{self.status.value} -> {new_status.value}"
            )

        self.status = new_status

    def assign_to_vessel(
        self,
        vessel: Vessel,
    ) -> None:
        if self.status != CraneStatus.AVAILABLE:
            raise CraneAssignmentError(
                f"Crane {self.crane_id} is not available "
                f"for assignment."
            )

        if self.assigned_vessel_id is not None:
            raise CraneAssignmentError(
                f"Crane {self.crane_id} is already assigned "
                f"to vessel {self.assigned_vessel_id}."
            )

        self.assigned_vessel_id = vessel.vessel_id
        self._transition_to(CraneStatus.ASSIGNED)

    def release_from_vessel(self) -> str:
        if self.status != CraneStatus.ASSIGNED:
            raise CraneAssignmentError(
                f"Crane {self.crane_id} cannot be released "
                f"while its status is {self.status.value}."
            )

        if self.assigned_vessel_id is None:
            raise CraneAssignmentError(
                f"Crane {self.crane_id} has no assigned vessel."
            )

        released_vessel_id = self.assigned_vessel_id

        self.assigned_vessel_id = None
        self._transition_to(CraneStatus.AVAILABLE)

        return released_vessel_id

    def start_operation(self) -> None:
        if self.status != CraneStatus.ASSIGNED:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot start operation "
                f"while its status is {self.status.value}."
            )

        if self.assigned_vessel_id is None:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot start operation "
                f"without an assigned vessel."
            )

        self._transition_to(CraneStatus.OPERATING)

    def stop_operation(self) -> None:
        if self.status != CraneStatus.OPERATING:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot stop operation "
                f"while its status is {self.status.value}."
            )

        if self.assigned_vessel_id is None:
            raise CraneOperationError(
                f"Crane {self.crane_id} has no assigned vessel."
            )

        self._transition_to(CraneStatus.ASSIGNED)

    def mark_failed(self) -> str | None:
        if self.status not in {
            CraneStatus.AVAILABLE,
            CraneStatus.ASSIGNED,
            CraneStatus.OPERATING,
        }:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot fail "
                f"while its status is {self.status.value}."
            )

        interrupted_vessel_id = self.assigned_vessel_id

        self.assigned_vessel_id = None
        self._transition_to(CraneStatus.FAILED)

        return interrupted_vessel_id

    def repair(self) -> None:
        if self.status != CraneStatus.FAILED:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot be repaired "
                f"while its status is {self.status.value}."
            )

        if self.assigned_vessel_id is not None:
            raise CraneOperationError(
                f"Failed crane {self.crane_id} must not have "
                f"an assigned vessel."
            )

        self._transition_to(CraneStatus.AVAILABLE)

    def start_maintenance(self) -> None:
        if self.status != CraneStatus.AVAILABLE:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot enter maintenance "
                f"while its status is {self.status.value}."
            )

        if self.assigned_vessel_id is not None:
            raise CraneOperationError(
                f"Crane {self.crane_id} must be released before "
                f"maintenance."
            )

        self._transition_to(CraneStatus.MAINTENANCE)

    def finish_maintenance(self) -> None:
        if self.status != CraneStatus.MAINTENANCE:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot finish maintenance "
                f"while its status is {self.status.value}."
            )

        if self.assigned_vessel_id is not None:
            raise CraneOperationError(
                f"Crane {self.crane_id} must not have an assigned "
                f"vessel during maintenance."
            )

        self._transition_to(CraneStatus.AVAILABLE)

    def move_to(
        self,
        new_position_m: float,
    ) -> float:
        if new_position_m < 0:
            raise QuayCraneValidationError(
                "Crane position cannot be negative."
            )

        if self.status in {
            CraneStatus.OPERATING,
            CraneStatus.FAILED,
            CraneStatus.MAINTENANCE,
        }:
            raise CraneOperationError(
                f"Crane {self.crane_id} cannot move "
                f"while its status is {self.status.value}."
            )

        travelled_distance_m = abs(
            new_position_m - self.position_m
        )

        self.position_m = new_position_m

        return travelled_distance_m

    def estimate_moves(
        self,
        hours: float,
    ) -> float:
        if hours < 0:
            raise QuayCraneValidationError(
                "Operation hours cannot be negative."
            )

        return self.moves_per_hour * hours

    def to_dict(self) -> dict[str, Any]:
        return {
            "crane_id": self.crane_id,
            "position_m": self.position_m,
            "moves_per_hour": self.moves_per_hour,
            "status": self.status.value,
            "assigned_vessel_id": self.assigned_vessel_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> QuayCrane:
        crane = cls(
            crane_id=data["crane_id"],
            position_m=data["position_m"],
            moves_per_hour=data["moves_per_hour"],
        )

        status = CraneStatus(data["status"])
        assigned_vessel_id = data.get("assigned_vessel_id")

        crane._restore_state(
            status=status,
            assigned_vessel_id=assigned_vessel_id,
        )

        return crane

    def _restore_state(
        self,
        status: CraneStatus,
        assigned_vessel_id: str | None,
    ) -> None:
        statuses_requiring_vessel = {
            CraneStatus.ASSIGNED,
            CraneStatus.OPERATING,
        }

        statuses_without_vessel = {
            CraneStatus.AVAILABLE,
            CraneStatus.FAILED,
            CraneStatus.MAINTENANCE,
        }

        if (
            status in statuses_requiring_vessel
            and not assigned_vessel_id
        ):
            raise QuayCraneValidationError(
                f"Crane status {status.value} requires "
                f"an assigned vessel."
            )

        if (
            status in statuses_without_vessel
            and assigned_vessel_id is not None
        ):
            raise QuayCraneValidationError(
                f"Crane status {status.value} cannot have "
                f"an assigned vessel."
            )

        self.status = status
        self.assigned_vessel_id = assigned_vessel_id

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
    ) -> QuayCrane:
        path = Path(file_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return cls.from_dict(data)