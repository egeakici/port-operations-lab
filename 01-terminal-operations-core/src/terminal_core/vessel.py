from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
import json
from pathlib import Path

from .exceptions import (
    InvalidStatusTransitionError,
    VesselValidationError
)

class VesselStatus(Enum):
    APPROACHING = "approaching"
    WAITING = "waiting"
    BERTHED = "berthed"
    OPERATING = "operating"
    READY_TO_DEPART = "ready_to_depart"
    DEPARTED = "departed"

VALID_STATUS_TRANSITIONS = {
    VesselStatus.APPROACHING: {VesselStatus.WAITING},
    VesselStatus.WAITING: {VesselStatus.BERTHED},
    VesselStatus.BERTHED: {VesselStatus.OPERATING},
    VesselStatus.OPERATING: {VesselStatus.READY_TO_DEPART},
    VesselStatus.READY_TO_DEPART: {VesselStatus.DEPARTED},
    VesselStatus.DEPARTED: set(),
}

@dataclass
class Vessel: 
    vessel_id: str
    length_m: float
    eta: datetime
    workload_moves: int
    priority: int
    max_cranes:int
    status: VesselStatus = VesselStatus.APPROACHING

    def __post_init__(self)->None:
        if not self.vessel_id.strip():
            raise VesselValidationError(
                "Vessel ID cannot be empty."
            )
        if self.length_m <= 0:
            raise VesselValidationError(
                "Vessel length must be greater than zero."
            )

        if self.workload_moves < 0:
            raise VesselValidationError(
                "Workload moves cannot be negative."
            )

        if not 1 <= self.priority <= 3:
            raise VesselValidationError(
                "Vessel priority must be between 1 and 3."
            )

        if self.max_cranes < 1:
            raise VesselValidationError(
                "Maximum crane count must be at least 1."
            )

    def transition_to(self, new_status: VesselStatus) -> None:
        allowed_statuses = VALID_STATUS_TRANSITIONS[self.status]

        if new_status not in allowed_statuses:
            raise InvalidStatusTransitionError(
                f"Invalid status transition: "
                f"{self.status.value} -> {new_status.value}"
            )
        
        self.status = new_status

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel_id": self.vessel_id,
            "length_m": self.length_m,
            "eta": self.eta.isoformat(),
            "workload_moves": self.workload_moves,
            "priority": self.priority,
            "max_cranes": self.max_cranes,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Vessel":
        return cls(
            vessel_id=data["vessel_id"],
            length_m=data["length_m"],
            eta=datetime.fromisoformat(data["eta"]),
            workload_moves=data["workload_moves"],
            priority=data["priority"],
            max_cranes=data["max_cranes"],
            status=VesselStatus(data["status"]),
    )

    def save_to_json(self, file_path: str | Path) -> None:
        path = Path(file_path)

        path.parent.mkdir(
            parents = True,
            exist_ok = True,
        )

        with path.open("w", encoding="utf-8") as file:
            json.dump(
                self.to_dict(),
                file,
                ensure_ascii=False,
                indent=4,
            )

    @classmethod
    def load_from_json(cls, file_path: str | Path) -> "Vessel":
        path = Path(file_path)

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return cls.from_dict(data)
