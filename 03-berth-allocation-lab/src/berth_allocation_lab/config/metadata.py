from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScenarioConfigMetadata:
    """Minimal metadata for scaffold-level scenario configuration."""

    scenario_id: str
    scenario_version: int
    formulation: str
    data_provenance: str
    seed: int | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ScenarioConfigMetadata":
        return cls(
            scenario_id=str(data["scenario_id"]),
            scenario_version=int(data["scenario_version"]),
            formulation=str(data["formulation"]),
            data_provenance=str(data["data_provenance"]),
            seed=(None if data.get("seed") is None else int(data["seed"])),
        )


@dataclass(frozen=True)
class ExperimentConfigMetadata:
    """Minimal metadata for scaffold-level experiment configuration."""

    experiment_id: str
    experiment_version: int

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ExperimentConfigMetadata":
        return cls(
            experiment_id=str(data["experiment_id"]),
            experiment_version=int(data["experiment_version"]),
        )

