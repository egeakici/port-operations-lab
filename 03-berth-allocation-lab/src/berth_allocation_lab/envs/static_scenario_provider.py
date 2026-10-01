"""Deterministic synthetic scenario provider for generated StaticBAP resets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from numbers import Integral
from typing import Callable

import numpy as np

from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


ScenarioProvider = Callable[[int], BAPScenarioInstance]
"""Map a non-negative generation seed to one scenario that records it as seed.

A provider may also define ``sample_seed(rng) -> int``; StaticBAPEnv then uses
it instead of a uniform draw.
"""

# Seed s belongs to split p iff s % SPLIT_SEED_STRIDE == SPLIT_SEED_OFFSETS[p],
# so no generation seed, and hence no generated instance, is shared by splits.
SPLIT_SEED_STRIDE = 3
SPLIT_SEED_OFFSETS = {"train": 0, "validation": 1, "test": 2}
# Sampled generation seeds lie in [0, SAMPLED_SEED_LIMIT).
SAMPLED_SEED_LIMIT = 2**31 - 1

_SEED_SUFFIX = re.compile(r"_seed\d+$")


def split_of_seed(seed: int) -> str:
    """Return the dataset split that owns a non-negative generation seed."""

    _validate_seed(seed)
    offset = int(seed) % SPLIT_SEED_STRIDE
    return next(split for split, value in SPLIT_SEED_OFFSETS.items() if value == offset)


@dataclass(frozen=True)
class SyntheticScenarioProvider:
    """Generate ``{base_scenario_id}_{split}_seed{s}`` for seeds of one split.

    Every other configuration field is preserved. The split is a required
    argument and restricts accepted seeds to its partition, so train,
    validation and test instances never share a generation seed.
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
        if self.split not in SPLIT_SEED_OFFSETS:
            raise ValueError("split must be train, validation, or test.")

    def sample_seed(self, rng: np.random.Generator) -> int:
        """Draw uniformly among this split's seeds in [0, SAMPLED_SEED_LIMIT)."""

        offset = SPLIT_SEED_OFFSETS[self.split]
        count = (SAMPLED_SEED_LIMIT - offset + SPLIT_SEED_STRIDE - 1) // SPLIT_SEED_STRIDE
        return SPLIT_SEED_STRIDE * int(rng.integers(0, count)) + offset

    def __call__(self, seed: int) -> BAPScenarioInstance:
        _validate_seed(seed)
        seed = int(seed)
        if split_of_seed(seed) != self.split:
            raise ValueError(
                f"Seed {seed} belongs to the {split_of_seed(seed)} split, not {self.split}; "
                f"{self.split} seeds satisfy seed % {SPLIT_SEED_STRIDE} == "
                f"{SPLIT_SEED_OFFSETS[self.split]}."
            )
        return self.generator.generate(replace(
            self.config,
            scenario_id=f"{self.base_scenario_id}_{self.split}_seed{seed}",
            seed=seed,
            split=self.split,
        ))


def _validate_seed(seed: object) -> None:
    if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("Generation seed must be a non-negative integer.")
