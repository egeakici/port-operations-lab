from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TerminationMode(Enum):
    HORIZON = "horizon"
    DRAIN = "drain"


@dataclass(frozen=True)
class ScenarioConfig:
    scenario_id: str
    duration_hours: float
    seed: int
    termination_mode: TerminationMode = TerminationMode.HORIZON

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("Scenario ID cannot be empty.")

        if self.duration_hours <= 0:
            raise ValueError("Scenario duration must be greater than zero.")

        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("Scenario seed must be an integer.")

        if not isinstance(self.termination_mode, TerminationMode):
            raise ValueError(
                "Scenario termination mode must be a TerminationMode value."
            )
