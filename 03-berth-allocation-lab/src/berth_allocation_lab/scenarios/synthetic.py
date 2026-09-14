from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from mini_port_sim.rng import (
    ARRIVAL_STREAM,
    VESSEL_STREAM,
    WORKLOAD_STREAM,
    RandomStreams,
)
from mini_port_sim.scenario import ServiceConfig, TerminalConfig, TrafficConfig

from berth_allocation_lab.config import load_yaml_config
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput


SCENARIO_SCHEMA_VERSION = 1
SYNTHETIC_GENERATOR_VERSION = "synthetic_v1"
SUPPORTED_FORMULATIONS = frozenset({"static", "dynamic"})
SUPPORTED_SPLITS = frozenset({"train", "validation", "test"})


@dataclass(frozen=True)
class SyntheticScenarioConfig:
    """Validated configuration for non-calibrated synthetic BAP generation."""

    scenario_id: str
    scenario_version: int
    scenario_family: str
    formulation: str
    data_provenance: str
    split: str
    seed: int
    terminal: TerminalConfig
    traffic: TrafficConfig
    service: ServiceConfig
    generator_version: str = SYNTHETIC_GENERATOR_VERSION
    scenario_schema_version: int = SCENARIO_SCHEMA_VERSION
    future_horizon_min: float | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_string(self.scenario_id, "Scenario ID")
        _validate_positive_int(self.scenario_version, "Scenario version")
        _validate_non_empty_string(self.scenario_family, "Scenario family")
        if self.formulation not in SUPPORTED_FORMULATIONS:
            raise ValueError("Formulation must be 'static' or 'dynamic'.")
        if self.data_provenance != "synthetic":
            raise ValueError("Synthetic generator only supports synthetic data.")
        if self.split not in SUPPORTED_SPLITS:
            raise ValueError("Split must be train, validation, or test.")
        _validate_int(self.seed, "Seed")
        if self.generator_version != SYNTHETIC_GENERATOR_VERSION:
            raise ValueError(
                f"Unsupported synthetic generator version: "
                f"{self.generator_version}"
            )
        if self.scenario_schema_version != SCENARIO_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported scenario schema version: "
                f"{self.scenario_schema_version}"
            )
        if not isinstance(self.terminal, TerminalConfig):
            raise TypeError("Terminal config must be a TerminalConfig.")
        if not isinstance(self.traffic, TrafficConfig):
            raise TypeError("Traffic config must be a TrafficConfig.")
        if not isinstance(self.service, ServiceConfig):
            raise TypeError("Service config must be a ServiceConfig.")
        if self.future_horizon_min is not None:
            _validate_non_negative_number(
                self.future_horizon_min,
                "Future horizon",
            )
        if (
            self.formulation == "static"
            and self.future_horizon_min is not None
        ):
            raise ValueError(
                "Static synthetic configs must not define future_horizon_min."
            )
        if self.traffic.max_vessel_length_m > self.terminal.berth_length_m:
            raise ValueError(
                "Maximum vessel length cannot exceed berth length for "
                "standard synthetic v1 scenarios."
            )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SyntheticScenarioConfig":
        if not isinstance(data, dict):
            raise ValueError("Synthetic scenario config must be a dictionary.")

        return cls(
            scenario_id=data["scenario_id"],
            scenario_version=int(data["scenario_version"]),
            scenario_family=data["scenario_family"],
            formulation=data["formulation"],
            data_provenance=data["data_provenance"],
            split=data["split"],
            seed=int(data["seed"]),
            generator_version=data.get(
                "generator_version",
                SYNTHETIC_GENERATOR_VERSION,
            ),
            scenario_schema_version=int(
                data.get("scenario_schema_version", SCENARIO_SCHEMA_VERSION)
            ),
            future_horizon_min=(
                None
                if data.get("future_horizon_min") is None
                else float(data["future_horizon_min"])
            ),
            terminal=TerminalConfig.from_dict(data.get("terminal", {})),
            traffic=TrafficConfig.from_dict(data.get("traffic", {})),
            service=ServiceConfig.from_dict(data.get("service", {})),
        )

    @classmethod
    def load_yaml(cls, file_path: str | Path) -> "SyntheticScenarioConfig":
        return cls.from_mapping(load_yaml_config(file_path))

    def with_formulation(self, formulation: str) -> "SyntheticScenarioConfig":
        return replace(
            self,
            formulation=formulation,
            future_horizon_min=(
                None if formulation == "static" else self.future_horizon_min
            ),
        )


class SyntheticScenarioGenerator:
    """Generate deterministic non-calibrated synthetic BAP instances."""

    def generate(
        self,
        config: SyntheticScenarioConfig,
    ) -> BAPScenarioInstance:
        streams = RandomStreams(master_seed=config.seed)
        arrival_rng = streams.get(ARRIVAL_STREAM)
        vessel_rng = streams.get(VESSEL_STREAM)
        workload_rng = streams.get(WORKLOAD_STREAM)
        elapsed_minutes = 0.0
        vessels: list[BAPVesselInput] = []

        for index in range(config.traffic.vessel_count):
            if index > 0:
                elapsed_minutes += arrival_rng.expovariate(
                    1.0 / config.traffic.mean_interarrival_minutes
                )

            length_m = round(
                vessel_rng.uniform(
                    config.traffic.min_vessel_length_m,
                    config.traffic.max_vessel_length_m,
                ),
                2,
            )
            workload_moves = workload_rng.randint(
                config.traffic.min_workload_moves,
                config.traffic.max_workload_moves,
            )
            service_time_min = planned_berth_occupancy_minutes(
                service=config.service,
                workload_moves=workload_moves,
            )
            vessels.append(
                BAPVesselInput(
                    vessel_id=f"V{index + 1:03d}",
                    arrival_time_min=elapsed_minutes,
                    length_m=length_m,
                    service_time_min=service_time_min,
                    workload_moves=workload_moves,
                )
            )

        arrival_generation_end_min = vessels[-1].arrival_time_min

        return BAPScenarioInstance(
            scenario_id=config.scenario_id,
            scenario_version=config.scenario_version,
            scenario_family=config.scenario_family,
            formulation=config.formulation,
            data_provenance=config.data_provenance,
            split=config.split,
            seed=config.seed,
            generator_version=config.generator_version,
            scenario_schema_version=config.scenario_schema_version,
            berth_length_m=config.terminal.berth_length_m,
            min_clearance_m=config.terminal.min_clearance_m,
            nominal_duration_min=arrival_generation_end_min,
            arrival_generation_end_min=arrival_generation_end_min,
            future_horizon_min=config.future_horizon_min,
            vessels=tuple(vessels),
        )


def planned_berth_occupancy_minutes(
    *,
    service: ServiceConfig,
    workload_moves: int,
) -> float:
    """Return Project 03 v1 planned berth occupancy duration in minutes."""

    return (
        service.berthing_preparation_minutes
        + service.service_duration_minutes(workload_moves)
        + service.departure_preparation_minutes
    )


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


def _validate_non_negative_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number.")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")

