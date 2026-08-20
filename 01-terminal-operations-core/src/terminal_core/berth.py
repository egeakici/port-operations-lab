from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from terminal_core.exceptions import (
    BerthPlacementError,
    BerthValidationError,
    VesselNotFoundAtBerthError,
)
from terminal_core.vessel import Vessel

@dataclass
class Berth:
    berth_id: str
    length_m: float
    min_clearance_m: float = 20.0
    occupancies: list[BerthOccupancy] = field(
        default_factory = list,
        repr = False,
    )

    def __post_init__(self) -> None:
        if not self.berth_id.strip():
            raise BerthValidationError("Berth ID cannot be empty.")

        if self.length_m <= 0:
            raise BerthValidationError(
                "Berth length must be greater than zero."
            )

        if self.min_clearance_m < 0 :
            raise BerthValidationError(
                "Minimum clearance cannot be negative."
            )

    @property
    def start_position_m(self) -> float:
        return 0.0

    @property 
    def end_position_m(self) -> float:
        return self.length_m

    @property
    def occupancy_count(self) -> int:
        return len(self.occupancies)


    def can_accommodate(self, occupancy: "BerthOccupancy") -> bool:
        return (
            occupancy.start_position_m >= self.start_position_m
            and occupancy.end_position_m <= self.end_position_m
        )

    def has_safe_clearance(
            self,
            first: "BerthOccupancy",
            second: "BerthOccupancy"
    ) -> bool:
        if first.overlaps_with(second):
            return False
        return first.gap_to(second) >= self.min_clearance_m

    def place_vessel(
            self,
            vessel: Vessel,
            start_position_m: float,
    ) -> BerthOccupancy:
        new_occupancy = BerthOccupancy(
            vessel=vessel,
            start_position_m=start_position_m,
        )

        if not self.can_accommodate(new_occupancy):
            raise BerthPlacementError(
                f"Vessel {vessel.vessel_id} does not fit within "
                f"berth {self.berth_id}."
            )
        if self.contains_vessel(vessel.vessel_id):
            raise BerthPlacementError(
                f"Vessel {vessel.vessel_id} is already placed "
                f"at berth {self.berth_id}."
            )
        for existing_occupancy in self.occupancies:
            if not self.has_safe_clearance(
                new_occupancy,
                existing_occupancy,
            ):
                raise BerthPlacementError(
                    f"Vessel {vessel.vessel_id} does not have safe "
                    f"clearance from vessel "
                    f"{existing_occupancy.vessel.vessel_id}."
                )
        self.occupancies.append(new_occupancy)

        return new_occupancy

    def contains_vessel(self, vessel_id: str) -> bool:
        return any(
            occupancy.vessel.vessel_id == vessel_id
            for occupancy in self.occupancies
        )

    def remove_vessel(self, vessel_id: str) -> BerthOccupancy:
        for occupancy in self.occupancies:
            if occupancy.vessel.vessel_id == vessel_id:
                self.occupancies.remove(occupancy)
                return occupancy

        raise VesselNotFoundAtBerthError(
            f"Vessel {vessel_id} is not placed "
            f"at berth {self.berth_id}."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "berth_id": self.berth_id,
            "length_m": self.length_m,
            "min_clearance_m": self.min_clearance_m,
            "occupancies": [
                occupancy.to_dict()
                for occupancy in self.occupancies
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Berth":
        berth = cls(
            berth_id=data["berth_id"],
            length_m=data["length_m"],
            min_clearance_m=data["min_clearance_m"],
        )
        berth.occupancies = [
            BerthOccupancy.from_dict(occupancy_data)
            for occupancy_data in data.get("occupancies", [])
        ]
        return berth

    def save_to_json(self, file_path: str | Path) -> None:
        path = Path(file_path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open("w", encoding="utf-8") as file:
            json.dump(
                self.to_dict(),
                file,
                ensure_ascii=False,
                indent=4,
            )

    @classmethod
    def load_from_json(cls, file_path: str | Path) -> "Berth":
        path = Path(file_path)

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return cls.from_dict(data)

@dataclass
class BerthOccupancy:
    vessel: Vessel
    start_position_m: float

    def __post_init__(self) -> float:
        if self.start_position_m < 0:
            raise ValueError(
                "Occupancy start position cannot be negative."
            )

    @property
    def end_position_m(self) -> float:
        return self.start_position_m + self.vessel.length_m

    @property
    def interval_m(self) -> tuple[float, float]:
        return (
            self.start_position_m,
            self.end_position_m,
        )

    def overlaps_with(self, other:"BerthOccupancy") -> bool:
        return (
            self.start_position_m < other.end_position_m
            and other.start_position_m < self.end_position_m
        )

    def gap_to( self, other: "BerthOccupancy") -> float:
        if self.overlaps_with(other):
            return 0.0

        if self.end_position_m <= other.start_position_m:
            return other.start_position_m - self.end_position_m

        return self.start_position_m - other.end_position_m

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel": self.vessel.to_dict(),
            "start_position_m": self.start_position_m,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BerthOccupancy":
        return cls(
            vessel=Vessel.from_dict(data["vessel"]),
            start_position_m=data["start_position_m"],
        )
