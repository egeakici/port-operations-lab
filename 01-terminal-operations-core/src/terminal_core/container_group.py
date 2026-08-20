from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from terminal_core.exceptions import (
    ContainerCargoError,
    ContainerFlowError,
    ContainerGroupValidationError,
)
from terminal_core.yard_block import YardCapability


class ContainerSize(Enum):
    TWENTY_FT = "20_ft"
    FORTY_FT = "40_ft"


class ContainerFlow(Enum):
    IMPORT = "import"
    EXPORT = "export"
    TRANSSHIPMENT = "transshipment"


class ContainerLoadState(Enum):
    LADEN = "laden"
    EMPTY = "empty"


@dataclass(frozen=True)
class ContainerGroup:
    group_id: str
    container_size: ContainerSize
    quantity: int
    flow: ContainerFlow
    load_state: ContainerLoadState
    is_reefer: bool = False
    is_hazardous: bool = False
    source_vessel_id: str | None = None
    target_vessel_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.group_id, str)
            or not self.group_id.strip()
        ):
            raise ContainerGroupValidationError(
                "Container group ID cannot be empty."
            )

        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity <= 0
        ):
            raise ContainerGroupValidationError(
                "Container group quantity must be a positive integer."
            )

        if not isinstance(
            self.container_size,
            ContainerSize,
        ):
            raise ContainerGroupValidationError(
                "Container size must be a ContainerSize value."
            )

        if not isinstance(
            self.flow,
            ContainerFlow,
        ):
            raise ContainerGroupValidationError(
                "Container flow must be a ContainerFlow value."
            )

        if not isinstance(
            self.load_state,
            ContainerLoadState,
        ):
            raise ContainerGroupValidationError(
                "Container load state must be a "
                "ContainerLoadState value."
            )

        if not isinstance(self.is_reefer, bool):
            raise ContainerGroupValidationError(
                "Container reefer flag must be a boolean."
            )

        if not isinstance(self.is_hazardous, bool):
            raise ContainerGroupValidationError(
                "Container hazardous flag must be a boolean."
            )

        self._validate_vessel_id(
            self.source_vessel_id,
            "Source vessel ID",
        )
        self._validate_vessel_id(
            self.target_vessel_id,
            "Target vessel ID",
        )
        self._validate_flow_connections()
        self._validate_cargo_properties()

    @staticmethod
    def _validate_vessel_id(
        vessel_id: str | None,
        field_name: str,
    ) -> None:
        if vessel_id is None:
            return

        if (
            not isinstance(vessel_id, str)
            or not vessel_id.strip()
        ):
            raise ContainerGroupValidationError(
                f"{field_name} must be a non-empty string."
            )

    def _validate_flow_connections(self) -> None:
        if self.flow == ContainerFlow.IMPORT:
            if self.source_vessel_id is None:
                raise ContainerFlowError(
                    "Import container groups require a "
                    "source vessel."
                )

            if self.target_vessel_id is not None:
                raise ContainerFlowError(
                    "Import container groups cannot define a "
                    "target vessel."
                )

            return

        if self.flow == ContainerFlow.EXPORT:
            if self.source_vessel_id is not None:
                raise ContainerFlowError(
                    "Export container groups cannot define a "
                    "source vessel."
                )

            if self.target_vessel_id is None:
                raise ContainerFlowError(
                    "Export container groups require a "
                    "target vessel."
                )

            return

        if self.flow == ContainerFlow.TRANSSHIPMENT:
            if self.source_vessel_id is None:
                raise ContainerFlowError(
                    "Transshipment container groups require a "
                    "source vessel."
                )

            if self.target_vessel_id is None:
                raise ContainerFlowError(
                    "Transshipment container groups require a "
                    "target vessel."
                )

            if self.source_vessel_id == self.target_vessel_id:
                raise ContainerFlowError(
                    "Transshipment container groups must use "
                    "different source and target vessels."
                )

    def _validate_cargo_properties(self) -> None:
        if (
            self.load_state == ContainerLoadState.EMPTY
            and self.is_reefer
        ):
            raise ContainerCargoError(
                "Empty container groups cannot require "
                "reefer power."
            )

        if (
            self.load_state == ContainerLoadState.EMPTY
            and self.is_hazardous
        ):
            raise ContainerCargoError(
                "Empty container groups cannot be hazardous."
            )

    @property
    def teu_per_container(self) -> float:
        teu_values = {
            ContainerSize.TWENTY_FT: 1.0,
            ContainerSize.FORTY_FT: 2.0,
        }

        try:
            return teu_values[self.container_size]
        except KeyError as error:
            raise ContainerGroupValidationError(
                "Unknown container size."
            ) from error

    @property
    def total_teu(self) -> float:
        return self.quantity * self.teu_per_container

    @property
    def required_yard_capabilities(
        self,
    ) -> set[YardCapability]:
        if self.load_state == ContainerLoadState.EMPTY:
            return {
                YardCapability.EMPTY,
            }

        capabilities = {
            YardCapability.GENERAL,
        }

        if self.is_reefer:
            capabilities.add(
                YardCapability.REEFER_POWER
            )

        if self.is_hazardous:
            capabilities.add(
                YardCapability.HAZARDOUS
            )

        return capabilities

    def yard_allocation_data(
        self,
    ) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "teu": self.total_teu,
            "required_capabilities": (
                self.required_yard_capabilities
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "container_size": self.container_size.value,
            "quantity": self.quantity,
            "flow": self.flow.value,
            "load_state": self.load_state.value,
            "is_reefer": self.is_reefer,
            "is_hazardous": self.is_hazardous,
            "source_vessel_id": self.source_vessel_id,
            "target_vessel_id": self.target_vessel_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> ContainerGroup:
        try:
            return cls(
                group_id=data["group_id"],
                container_size=ContainerSize(
                    data["container_size"]
                ),
                quantity=data["quantity"],
                flow=ContainerFlow(data["flow"]),
                load_state=ContainerLoadState(
                    data["load_state"]
                ),
                is_reefer=data.get(
                    "is_reefer",
                    False,
                ),
                is_hazardous=data.get(
                    "is_hazardous",
                    False,
                ),
                source_vessel_id=data.get(
                    "source_vessel_id"
                ),
                target_vessel_id=data.get(
                    "target_vessel_id"
                ),
            )
        except (
            ContainerFlowError,
            ContainerCargoError,
        ):
            raise
        except (
            KeyError,
            TypeError,
            ValueError,
            ContainerGroupValidationError,
        ) as error:
            raise ContainerGroupValidationError(
                f"Invalid container group snapshot: {error}"
            ) from error

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
    ) -> ContainerGroup:
        path = Path(file_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return cls.from_dict(data)
