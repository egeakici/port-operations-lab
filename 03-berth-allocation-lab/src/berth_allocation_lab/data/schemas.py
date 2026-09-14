from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BAPVesselInput:
    """Immutable vessel input for a generated BAP problem instance."""

    vessel_id: str
    arrival_time_min: float
    length_m: float
    service_time_min: float
    workload_moves: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.vessel_id, str) or not self.vessel_id.strip():
            raise ValueError("Vessel ID cannot be empty.")
        _validate_non_negative_number(
            self.arrival_time_min,
            "Arrival time",
        )
        _validate_positive_number(self.length_m, "Vessel length")
        _validate_positive_number(self.service_time_min, "Service time")
        if self.workload_moves is not None:
            _validate_non_negative_int(self.workload_moves, "Workload moves")

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel_id": self.vessel_id,
            "arrival_time_min": self.arrival_time_min,
            "length_m": self.length_m,
            "service_time_min": self.service_time_min,
            "workload_moves": self.workload_moves,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BAPVesselInput":
        if not isinstance(data, dict):
            raise ValueError("Vessel input must be a dictionary.")

        return cls(
            vessel_id=data["vessel_id"],
            arrival_time_min=float(data["arrival_time_min"]),
            length_m=float(data["length_m"]),
            service_time_min=float(data["service_time_min"]),
            workload_moves=(
                None
                if data.get("workload_moves") is None
                else int(data["workload_moves"])
            ),
        )


@dataclass(frozen=True)
class BAPScenarioInstance:
    """Immutable generated BAP scenario instance."""

    scenario_id: str
    scenario_version: int
    scenario_family: str
    formulation: str
    data_provenance: str
    split: str
    seed: int
    generator_version: str
    scenario_schema_version: int
    berth_length_m: float
    min_clearance_m: float
    nominal_duration_min: float
    arrival_generation_end_min: float
    vessels: tuple[BAPVesselInput, ...]
    future_horizon_min: float | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_string(self.scenario_id, "Scenario ID")
        _validate_positive_int(self.scenario_version, "Scenario version")
        _validate_non_empty_string(self.scenario_family, "Scenario family")
        if self.formulation not in {"static", "dynamic"}:
            raise ValueError("Formulation must be 'static' or 'dynamic'.")
        if self.data_provenance != "synthetic":
            raise ValueError("Step 4 scenario instances must be synthetic.")
        if self.split not in {"train", "validation", "test"}:
            raise ValueError("Split must be train, validation, or test.")
        _validate_int(self.seed, "Seed")
        _validate_non_empty_string(self.generator_version, "Generator version")
        _validate_positive_int(
            self.scenario_schema_version,
            "Scenario schema version",
        )
        _validate_positive_number(self.berth_length_m, "Berth length")
        _validate_non_negative_number(
            self.min_clearance_m,
            "Minimum clearance",
        )
        _validate_non_negative_number(
            self.nominal_duration_min,
            "Nominal duration",
        )
        _validate_non_negative_number(
            self.arrival_generation_end_min,
            "Arrival generation end",
        )
        if not self.vessels:
            raise ValueError("Scenario instance must contain vessels.")
        if self.future_horizon_min is not None:
            _validate_non_negative_number(
                self.future_horizon_min,
                "Future horizon",
            )

        ordered = tuple(
            sorted(self.vessels, key=lambda vessel: vessel.arrival_time_min)
        )
        if ordered != self.vessels:
            raise ValueError("Scenario vessels must be ordered by arrival time.")

        for vessel in self.vessels:
            if vessel.length_m > self.berth_length_m:
                raise ValueError(
                    f"Vessel {vessel.vessel_id} length exceeds berth length."
                )

    @property
    def vessel_count(self) -> int:
        return len(self.vessels)

    @property
    def content_fingerprint(self) -> str:
        payload = json.dumps(
            self.to_dict(include_fingerprint=False),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self, *, include_fingerprint: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "scenario_family": self.scenario_family,
            "formulation": self.formulation,
            "data_provenance": self.data_provenance,
            "split": self.split,
            "seed": self.seed,
            "generator_version": self.generator_version,
            "scenario_schema_version": self.scenario_schema_version,
            "berth_length_m": self.berth_length_m,
            "min_clearance_m": self.min_clearance_m,
            "nominal_duration_min": self.nominal_duration_min,
            "arrival_generation_end_min": self.arrival_generation_end_min,
            "future_horizon_min": self.future_horizon_min,
            "vessel_count": self.vessel_count,
            "vessels": [vessel.to_dict() for vessel in self.vessels],
        }
        if include_fingerprint:
            data["content_fingerprint"] = self.content_fingerprint
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BAPScenarioInstance":
        if not isinstance(data, dict):
            raise ValueError("Scenario instance must be a dictionary.")

        return cls(
            scenario_id=data["scenario_id"],
            scenario_version=int(data["scenario_version"]),
            scenario_family=data["scenario_family"],
            formulation=data["formulation"],
            data_provenance=data["data_provenance"],
            split=data["split"],
            seed=int(data["seed"]),
            generator_version=data["generator_version"],
            scenario_schema_version=int(data["scenario_schema_version"]),
            berth_length_m=float(data["berth_length_m"]),
            min_clearance_m=float(data["min_clearance_m"]),
            nominal_duration_min=float(data["nominal_duration_min"]),
            arrival_generation_end_min=float(
                data["arrival_generation_end_min"]
            ),
            future_horizon_min=(
                None
                if data.get("future_horizon_min") is None
                else float(data["future_horizon_min"])
            ),
            vessels=tuple(
                BAPVesselInput.from_dict(vessel_data)
                for vessel_data in data["vessels"]
            ),
        )

    def save_json(self, file_path: str | Path) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            json.dump(
                self.to_dict(),
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

    @classmethod
    def load_json(cls, file_path: str | Path) -> "BAPScenarioInstance":
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return cls.from_dict(data)


def _validate_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty.")


def _validate_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")


def _validate_positive_int(value: int, field_name: str) -> None:
    _validate_int(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    _validate_int(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")


def _validate_positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number.")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")


def _validate_non_negative_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")

