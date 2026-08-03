from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.terminal_core.exceptions import (
    InvalidYardBlockStatusTransitionError,
    YardBlockValidationError,
    YardCapacityError,
    YardCompatibilityError,
    YardOperationError,
    YardReservationError,
)


class YardCapability(Enum):
    GENERAL = "general"
    REEFER_POWER = "reefer_power"
    HAZARDOUS = "hazardous"
    EMPTY = "empty"


class YardBlockStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    MAINTENANCE = "maintenance"


VALID_YARD_BLOCK_STATUS_TRANSITIONS = {
    YardBlockStatus.OPEN: {
        YardBlockStatus.CLOSED,
        YardBlockStatus.MAINTENANCE,
    },
    YardBlockStatus.CLOSED: {
        YardBlockStatus.OPEN,
        YardBlockStatus.MAINTENANCE,
    },
    YardBlockStatus.MAINTENANCE: {
        YardBlockStatus.OPEN,
    },
}


@dataclass
class YardBlock:
    block_id: str
    capacity_teu: float

    capabilities: set[YardCapability] = field(
        default_factory=lambda: {
            YardCapability.GENERAL,
        }
    )

    status: YardBlockStatus = field(
        default=YardBlockStatus.OPEN,
        init=False,
    )

    stored_groups: dict[str, float] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    reservations: dict[str, float] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not self.block_id.strip():
            raise YardBlockValidationError(
                "Yard block ID cannot be empty."
            )

        if self.capacity_teu <= 0:
            raise YardBlockValidationError(
                "Yard block capacity must be "
                "greater than zero."
            )

        if not isinstance(self.capabilities, set):
            raise YardBlockValidationError(
                "Yard block capabilities must be a set."
            )

        if not self.capabilities:
            raise YardBlockValidationError(
                "Yard block must have at least "
                "one capability."
            )

        if not all(
            isinstance(capability, YardCapability)
            for capability in self.capabilities
        ):
            raise YardBlockValidationError(
                "All yard block capabilities must be "
                "YardCapability values."
            )

    def supports_requirements(
        self,
        required_capabilities: set[YardCapability],
    ) -> bool:
        return required_capabilities.issubset(
            self.capabilities
        )

    @property
    def occupied_teu(self) -> float:
        return sum(
            self.stored_groups.values()
        )

    @property
    def reserved_teu(self) -> float:
        return sum(
            self.reservations.values()
        )

    @property
    def available_teu(self) -> float:
        return (
            self.capacity_teu
            - self.occupied_teu
            - self.reserved_teu
        )

    @property
    def occupancy_ratio(self) -> float:
        return (
            self.occupied_teu
            / self.capacity_teu
        )

    @property
    def planned_occupancy_ratio(self) -> float:
        planned_teu = (
            self.occupied_teu
            + self.reserved_teu
        )

        return (
            planned_teu
            / self.capacity_teu
        )

    def reserve_capacity(
        self,
        group_id: str,
        teu: float,
        required_capabilities: set[YardCapability],
    ) -> None:
        if not group_id.strip():
            raise YardBlockValidationError(
                "Container group ID cannot be empty."
            )

        if teu <= 0:
            raise YardBlockValidationError(
                "Reserved TEU must be greater than zero."
            )

        if not isinstance(
            required_capabilities,
            set,
        ):
            raise YardBlockValidationError(
                "Required capabilities must be a set."
            )

        if not required_capabilities:
            raise YardBlockValidationError(
                "Reservation must define at least "
                "one required capability."
            )

        if not all(
            isinstance(capability, YardCapability)
            for capability in required_capabilities
        ):
            raise YardBlockValidationError(
                "All required capabilities must be "
                "YardCapability values."
            )

        if self.status != YardBlockStatus.OPEN:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot accept "
                f"reservations while its status is "
                f"{self.status.value}."
            )

        if group_id in self.reservations:
            raise YardReservationError(
                f"Container group {group_id} already has "
                f"a reservation in block {self.block_id}."
            )

        if group_id in self.stored_groups:
            raise YardReservationError(
                f"Container group {group_id} is already stored "
                f"in block {self.block_id}."
            )

        if not self.supports_requirements(
            required_capabilities
        ):
            raise YardCompatibilityError(
                f"Yard block {self.block_id} does not support "
                f"the required capabilities."
            )

        if teu > self.available_teu:
            raise YardCapacityError(
                f"Yard block {self.block_id} does not have "
                f"enough available capacity."
            )

        self.reservations[group_id] = teu

    def cancel_reservation(
        self,
        group_id: str,
    ) -> float:
        if not group_id.strip():
            raise YardBlockValidationError(
                "Container group ID cannot be empty."
            )

        if group_id not in self.reservations:
            raise YardReservationError(
                f"Container group {group_id} has no reservation "
                f"in block {self.block_id}."
            )

        cancelled_teu = self.reservations.pop(
            group_id
        )

        return cancelled_teu

    def commit_reservation(
        self,
        group_id: str,
    ) -> float:
        if not group_id.strip():
            raise YardBlockValidationError(
                "Container group ID cannot be empty."
            )

        if self.status != YardBlockStatus.OPEN:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot receive "
                f"container groups while its status is "
                f"{self.status.value}."
            )

        if group_id not in self.reservations:
            raise YardReservationError(
                f"Container group {group_id} has no reservation "
                f"in block {self.block_id}."
            )

        if group_id in self.stored_groups:
            raise YardReservationError(
                f"Container group {group_id} is already stored "
                f"in block {self.block_id}."
            )

        committed_teu = self.reservations[
            group_id
        ]

        del self.reservations[group_id]

        self.stored_groups[group_id] = (
            committed_teu
        )

        return committed_teu

    def store_group(
        self,
        group_id: str,
        teu: float,
        required_capabilities: set[YardCapability],
    ) -> None:
        if not group_id.strip():
            raise YardBlockValidationError(
                "Container group ID cannot be empty."
            )

        if teu <= 0:
            raise YardBlockValidationError(
                "Stored TEU must be greater than zero."
            )

        if not isinstance(
            required_capabilities,
            set,
        ):
            raise YardBlockValidationError(
                "Required capabilities must be a set."
            )

        if not required_capabilities:
            raise YardBlockValidationError(
                "Stored group must define at least "
                "one required capability."
            )

        if not all(
            isinstance(capability, YardCapability)
            for capability in required_capabilities
        ):
            raise YardBlockValidationError(
                "All required capabilities must be "
                "YardCapability values."
            )

        if self.status != YardBlockStatus.OPEN:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot receive "
                f"container groups while its status is "
                f"{self.status.value}."
            )

        if group_id in self.stored_groups:
            raise YardOperationError(
                f"Container group {group_id} is already stored "
                f"in block {self.block_id}."
            )

        if group_id in self.reservations:
            raise YardReservationError(
                f"Container group {group_id} already has "
                f"a reservation in block {self.block_id}. "
                f"Commit the reservation instead."
            )

        if not self.supports_requirements(
            required_capabilities
        ):
            raise YardCompatibilityError(
                f"Yard block {self.block_id} does not support "
                f"the required capabilities."
            )

        if teu > self.available_teu:
            raise YardCapacityError(
                f"Yard block {self.block_id} does not have "
                f"enough available capacity."
            )

        self.stored_groups[group_id] = teu

    def release_group(
        self,
        group_id: str,
        teu: float | None = None,
    ) -> float:
        if not group_id.strip():
            raise YardBlockValidationError(
                "Container group ID cannot be empty."
            )

        if self.status != YardBlockStatus.OPEN:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot release "
                f"container groups while its status is "
                f"{self.status.value}."
            )

        if group_id not in self.stored_groups:
            raise YardOperationError(
                f"Container group {group_id} is not stored "
                f"in block {self.block_id}."
            )

        stored_teu = self.stored_groups[group_id]

        if teu is None:
            released_teu = self.stored_groups.pop(
                group_id
            )

            return released_teu

        if teu <= 0:
            raise YardBlockValidationError(
                "Released TEU must be greater than zero."
            )

        if teu > stored_teu:
            raise YardCapacityError(
                f"Cannot release {teu} TEU from group "
                f"{group_id}; only {stored_teu} TEU "
                f"is stored."
            )

        if teu == stored_teu:
            self.stored_groups.pop(group_id)
        else:
            self.stored_groups[group_id] = (
                stored_teu - teu
            )

        return teu

    def _transition_to(
        self,
        new_status: YardBlockStatus,
    ) -> None:
        allowed_statuses = (
            VALID_YARD_BLOCK_STATUS_TRANSITIONS[
                self.status
            ]
        )

        if new_status not in allowed_statuses:
            raise InvalidYardBlockStatusTransitionError(
                f"Invalid yard block status transition: "
                f"{self.status.value} -> "
                f"{new_status.value}"
            )

        self.status = new_status

    def close(self) -> None:
        if self.status != YardBlockStatus.OPEN:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot be "
                f"closed while its status is "
                f"{self.status.value}."
            )

        self._transition_to(
            YardBlockStatus.CLOSED
        )

    def reopen(self) -> None:
        if self.status != YardBlockStatus.CLOSED:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot be "
                f"reopened while its status is "
                f"{self.status.value}."
            )

        self._transition_to(
            YardBlockStatus.OPEN
        )

    def start_maintenance(self) -> None:
        if self.status not in {
            YardBlockStatus.OPEN,
            YardBlockStatus.CLOSED,
        }:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot enter "
                f"maintenance while its status is "
                f"{self.status.value}."
            )

        self._transition_to(
            YardBlockStatus.MAINTENANCE
        )

    def finish_maintenance(self) -> None:
        if self.status != YardBlockStatus.MAINTENANCE:
            raise YardOperationError(
                f"Yard block {self.block_id} cannot finish "
                f"maintenance while its status is "
                f"{self.status.value}."
            )

        self._transition_to(
            YardBlockStatus.OPEN
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id,
            "capacity_teu": self.capacity_teu,
            "capabilities": sorted(
                capability.value
                for capability in self.capabilities
            ),
            "status": self.status.value,
            "stored_groups": dict(
                self.stored_groups
            ),
            "reservations": dict(
                self.reservations
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> YardBlock:
        try:
            capabilities = {
                YardCapability(value)
                for value in data["capabilities"]
            }

            status = YardBlockStatus(
                data["status"]
            )

            stored_groups = dict(
                data.get("stored_groups", {})
            )

            reservations = dict(
                data.get("reservations", {})
            )

            block = cls(
                block_id=data["block_id"],
                capacity_teu=data["capacity_teu"],
                capabilities=capabilities,
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise YardBlockValidationError(
                f"Invalid yard block snapshot: {error}"
            ) from error

        block._restore_state(
            status=status,
            stored_groups=stored_groups,
            reservations=reservations,
        )

        return block

    def _restore_state(
        self,
        status: YardBlockStatus,
        stored_groups: dict[str, float],
        reservations: dict[str, float],
    ) -> None:
        if not isinstance(
            status,
            YardBlockStatus,
        ):
            raise YardBlockValidationError(
                "Invalid yard block status."
            )

        self._validate_group_records(
            records=stored_groups,
            record_name="stored group",
        )

        self._validate_group_records(
            records=reservations,
            record_name="reservation",
        )

        duplicate_group_ids = (
            set(stored_groups)
            & set(reservations)
        )

        if duplicate_group_ids:
            duplicate_text = ", ".join(
                sorted(duplicate_group_ids)
            )

            raise YardBlockValidationError(
                f"Container groups cannot be both stored "
                f"and reserved: {duplicate_text}."
            )

        total_used_teu = (
            sum(stored_groups.values())
            + sum(reservations.values())
        )

        if total_used_teu > self.capacity_teu:
            raise YardCapacityError(
                f"Restored yard usage {total_used_teu} TEU "
                f"exceeds block capacity "
                f"{self.capacity_teu} TEU."
            )

        self.status = status
        self.stored_groups = dict(
            stored_groups
        )
        self.reservations = dict(
            reservations
        )

    @staticmethod
    def _validate_group_records(
        records: dict[str, float],
        record_name: str,
    ) -> None:
        if not isinstance(records, dict):
            raise YardBlockValidationError(
                f"{record_name.title()} records "
                f"must be a dictionary."
            )

        for group_id, teu in records.items():
            if (
                not isinstance(group_id, str)
                or not group_id.strip()
            ):
                raise YardBlockValidationError(
                    f"Every {record_name} must have "
                    f"a valid group ID."
                )

            if (
                isinstance(teu, bool)
                or not isinstance(teu, (int, float))
                or teu <= 0
            ):
                raise YardBlockValidationError(
                    f"Every {record_name} TEU value "
                    f"must be greater than zero."
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
    ) -> YardBlock:
        path = Path(file_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return cls.from_dict(data)