from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from mini_port_sim.rng import RandomStreams


class TerminationMode(Enum):
    HORIZON = "horizon"
    DRAIN = "drain"


@dataclass(frozen=True)
class TerminalConfig:
    berth_length_m: float = 1200.0
    min_clearance_m: float = 20.0
    quay_crane_count: int = 4
    yard_block_count: int = 3

    def __post_init__(self) -> None:
        _validate_positive_number(
            self.berth_length_m,
            "Berth length",
        )

        _validate_non_negative_number(
            self.min_clearance_m,
            "Minimum clearance",
        )

        _validate_positive_int(
            self.quay_crane_count,
            "Quay crane count",
        )

        _validate_positive_int(
            self.yard_block_count,
            "Yard block count",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "berth_length_m": self.berth_length_m,
            "min_clearance_m": self.min_clearance_m,
            "quay_crane_count": self.quay_crane_count,
            "yard_block_count": self.yard_block_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TerminalConfig":
        if not isinstance(data, dict):
            raise ValueError("Terminal config must be a dictionary.")

        return cls(
            berth_length_m=data.get("berth_length_m", cls.berth_length_m),
            min_clearance_m=data.get("min_clearance_m", cls.min_clearance_m),
            quay_crane_count=data.get(
                "quay_crane_count",
                cls.quay_crane_count,
            ),
            yard_block_count=data.get("yard_block_count", cls.yard_block_count),
        )


@dataclass(frozen=True)
class TrafficConfig:
    vessel_count: int = 25
    mean_interarrival_minutes: float = 180.0
    min_vessel_length_m: float = 180.0
    max_vessel_length_m: float = 360.0
    min_workload_moves: int = 200
    max_workload_moves: int = 1200

    def __post_init__(self) -> None:
        _validate_positive_int(
            self.vessel_count,
            "Vessel count",
        )

        _validate_positive_number(
            self.mean_interarrival_minutes,
            "Mean interarrival minutes",
        )

        _validate_positive_number(
            self.min_vessel_length_m,
            "Minimum vessel length",
        )

        _validate_positive_number(
            self.max_vessel_length_m,
            "Maximum vessel length",
        )

        if self.min_vessel_length_m > self.max_vessel_length_m:
            raise ValueError(
                "Minimum vessel length cannot exceed maximum vessel length."
            )

        _validate_positive_int(
            self.min_workload_moves,
            "Minimum workload moves",
        )

        _validate_positive_int(
            self.max_workload_moves,
            "Maximum workload moves",
        )

        if self.min_workload_moves > self.max_workload_moves:
            raise ValueError(
                "Minimum workload moves cannot exceed maximum workload moves."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel_count": self.vessel_count,
            "mean_interarrival_minutes": self.mean_interarrival_minutes,
            "min_vessel_length_m": self.min_vessel_length_m,
            "max_vessel_length_m": self.max_vessel_length_m,
            "min_workload_moves": self.min_workload_moves,
            "max_workload_moves": self.max_workload_moves,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrafficConfig":
        if not isinstance(data, dict):
            raise ValueError("Traffic config must be a dictionary.")

        return cls(
            vessel_count=data.get("vessel_count", cls.vessel_count),
            mean_interarrival_minutes=data.get(
                "mean_interarrival_minutes",
                cls.mean_interarrival_minutes,
            ),
            min_vessel_length_m=data.get(
                "min_vessel_length_m",
                cls.min_vessel_length_m,
            ),
            max_vessel_length_m=data.get(
                "max_vessel_length_m",
                cls.max_vessel_length_m,
            ),
            min_workload_moves=data.get(
                "min_workload_moves",
                cls.min_workload_moves,
            ),
            max_workload_moves=data.get(
                "max_workload_moves",
                cls.max_workload_moves,
            ),
        )


@dataclass(frozen=True)
class ServiceConfig:
    berthing_preparation_minutes: float = 30.0
    service_minutes_per_move: float = 0.5
    departure_preparation_minutes: float = 20.0

    def __post_init__(self) -> None:
        _validate_non_negative_number(
            self.berthing_preparation_minutes,
            "Berthing preparation minutes",
        )

        _validate_positive_number(
            self.service_minutes_per_move,
            "Service minutes per move",
        )

        _validate_non_negative_number(
            self.departure_preparation_minutes,
            "Departure preparation minutes",
        )

    def service_duration_minutes(self, workload_moves: int) -> float:
        _validate_non_negative_int(
            workload_moves,
            "Workload moves",
        )

        return workload_moves * self.service_minutes_per_move

    def to_dict(self) -> dict[str, Any]:
        return {
            "berthing_preparation_minutes": (
                self.berthing_preparation_minutes
            ),
            "service_minutes_per_move": self.service_minutes_per_move,
            "departure_preparation_minutes": (
                self.departure_preparation_minutes
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServiceConfig":
        if not isinstance(data, dict):
            raise ValueError("Service config must be a dictionary.")

        return cls(
            berthing_preparation_minutes=data.get(
                "berthing_preparation_minutes",
                cls.berthing_preparation_minutes,
            ),
            service_minutes_per_move=data.get(
                "service_minutes_per_move",
                cls.service_minutes_per_move,
            ),
            departure_preparation_minutes=data.get(
                "departure_preparation_minutes",
                cls.departure_preparation_minutes,
            ),
        )


@dataclass(frozen=True)
class ScenarioConfig:
    scenario_id: str
    duration_hours: float
    seed: int
    termination_mode: TerminationMode = TerminationMode.HORIZON
    terminal: TerminalConfig = field(default_factory=TerminalConfig)
    traffic: TrafficConfig = field(default_factory=TrafficConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenario_id, str)
            or not self.scenario_id.strip()
        ):
            raise ValueError("Scenario ID cannot be empty.")

        _validate_positive_number(
            self.duration_hours,
            "Scenario duration",
        )

        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("Scenario seed must be an integer.")

        if not isinstance(self.termination_mode, TerminationMode):
            raise ValueError(
                "Scenario termination mode must be a TerminationMode value."
            )

        if not isinstance(self.terminal, TerminalConfig):
            raise ValueError("Scenario terminal must be a TerminalConfig.")

        if not isinstance(self.traffic, TrafficConfig):
            raise ValueError("Scenario traffic must be a TrafficConfig.")

        if not isinstance(self.service, ServiceConfig):
            raise ValueError("Scenario service must be a ServiceConfig.")

    @property
    def duration_minutes(self) -> float:
        return self.duration_hours * 60.0

    def random_streams(self) -> RandomStreams:
        return RandomStreams(master_seed=self.seed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "duration_hours": self.duration_hours,
            "seed": self.seed,
            "termination_mode": self.termination_mode.value,
            "terminal": self.terminal.to_dict(),
            "traffic": self.traffic.to_dict(),
            "service": self.service.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioConfig":
        if not isinstance(data, dict):
            raise ValueError("Scenario config must be a dictionary.")

        try:
            return cls(
                scenario_id=data["scenario_id"],
                duration_hours=data["duration_hours"],
                seed=data["seed"],
                termination_mode=TerminationMode(
                    data.get(
                        "termination_mode",
                        TerminationMode.HORIZON.value,
                    )
                ),
                terminal=TerminalConfig.from_dict(data.get("terminal", {})),
                traffic=TrafficConfig.from_dict(data.get("traffic", {})),
                service=ServiceConfig.from_dict(data.get("service", {})),
            )
        except KeyError as error:
            raise ValueError(f"Missing scenario field: {error}") from error

    @classmethod
    def load_json(cls, file_path: str | Path) -> "ScenarioConfig":
        path = Path(file_path)

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return cls.from_dict(data)

    def save_json(self, file_path: str | Path) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            json.dump(
                self.to_dict(),
                file,
                ensure_ascii=False,
                indent=2,
            )


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


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")

    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")

    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")
