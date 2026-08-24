from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mini_port_sim import ExperimentResult, ScenarioConfig


@dataclass(frozen=True)
class ScenarioOption:
    label: str
    path: Path
    scenario: ScenarioConfig


@dataclass(frozen=True)
class SimulationRunBundle:
    result: ExperimentResult
    event_rows: tuple[dict[str, Any], ...]

    @property
    def scenario(self) -> ScenarioConfig:
        return self.result.scenario

    @property
    def metrics(self):
        return self.result.metrics

