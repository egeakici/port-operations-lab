"""Deterministic synthetic scenario provider for generated StaticBAP resets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from numbers import Integral
from typing import Callable

from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


ScenarioProvider = Callable[[int], BAPScenarioInstance]
"""Map a non-negative generation seed to one scenario that records it as seed."""

_SEED_SUFFIX = re.compile(r"_seed\d+$")
_SPLITS = frozenset({"train", "validation", "test"})


@dataclass(frozen=True)
class SyntheticScenarioProvider:
    """Generate ``{base_scenario_id}_seed{s}`` with seed ``s`` and an explicit split.

    Every other configuration field is preserved. The split is a required
    argument, so presets whose split follows the traffic family are never
    silently reused as a training distribution.
    """

    config: SyntheticScenarioConfig
    base_scenario_id: str
    split: str
    generator: SyntheticScenarioGenerator = field(
        default_factory=SyntheticScenarioGenerator, compare=False, repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.config, SyntheticScenarioConfig):
            raise TypeError("config must be a SyntheticScenarioConfig.")
        if self.config.formulation != "static":
            raise ValueError(
                "StaticBAP provider requires a static config; create a static twin "
                "explicitly with config.with_formulation('static')."
            )
        if (not isinstance(self.base_scenario_id, str) or not self.base_scenario_id.strip()
                or _SEED_SUFFIX.search(self.base_scenario_id)):
            raise ValueError("base_scenario_id must be a clean ID without a _seed<N> suffix.")
        if self.split not in _SPLITS:
            raise ValueError("split must be train, validation, or test.")

    def __call__(self, seed: int) -> BAPScenarioInstance:
        if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
            raise ValueError("Generation seed must be a non-negative integer.")
        seed = int(seed)
        return self.generator.generate(replace(
            self.config,
            scenario_id=f"{self.base_scenario_id}_seed{seed}",
            seed=seed,
            split=self.split,
        ))
