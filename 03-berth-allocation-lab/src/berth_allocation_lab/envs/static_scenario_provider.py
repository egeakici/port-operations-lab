"""Deterministic synthetic scenario provider for generated StaticBAP resets."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field, replace
from numbers import Integral, Real
from typing import Callable, Iterable

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
# Mixture component choice is a pure function of seed // SPLIT_SEED_STRIDE.
MIXTURE_SELECTION_VERSION = "sha256_partition_index_v1"

_SEED_SUFFIX = re.compile(r"_seed\d+$")


def split_of_seed(seed: int) -> str:
    """Return the dataset split that owns a non-negative generation seed."""

    _validate_seed(seed)
    offset = int(seed) % SPLIT_SEED_STRIDE
    return next(split for split, value in SPLIT_SEED_OFFSETS.items() if value == offset)


def sample_split_seed(split: str, rng: np.random.Generator) -> int:
    """Draw uniformly among a split's seeds in [0, SAMPLED_SEED_LIMIT)."""

    offset = SPLIT_SEED_OFFSETS[split]
    count = (SAMPLED_SEED_LIMIT - offset + SPLIT_SEED_STRIDE - 1) // SPLIT_SEED_STRIDE
    return SPLIT_SEED_STRIDE * int(rng.integers(0, count)) + offset


@dataclass(frozen=True)
class SyntheticScenarioProvider:
    """Generate ``{base_scenario_id}_{split}_seed{s}`` for seeds of one split.

    Every other configuration field is preserved. The split is a required
    argument and restricts accepted seeds to its partition, so train,
    validation and test instances never share a generation seed.
    ``excluded_seeds`` reserves seeds of this configuration (for example
    historically inspected fixtures): they are rejected and never sampled.
    """

    config: SyntheticScenarioConfig
    base_scenario_id: str
    split: str
    excluded_seeds: frozenset[int] = frozenset()
    generator: SyntheticScenarioGenerator = field(
        default_factory=SyntheticScenarioGenerator, compare=False, repr=False,
    )

    def __post_init__(self) -> None:
        excluded = frozenset(self.excluded_seeds)
        for seed in excluded:
            _validate_seed(seed)
        object.__setattr__(self, "excluded_seeds", frozenset(int(s) for s in excluded))
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

    @property
    def vessel_count(self) -> int:
        return self.config.traffic.vessel_count

    def sample_seed(self, rng: np.random.Generator) -> int:
        """Draw uniformly among this split's non-excluded seeds."""

        while True:
            seed = sample_split_seed(self.split, rng)
            if seed not in self.excluded_seeds:
                return seed

    def __call__(self, seed: int) -> BAPScenarioInstance:
        _validate_seed(seed)
        seed = int(seed)
        if split_of_seed(seed) != self.split:
            raise ValueError(
                f"Seed {seed} belongs to the {split_of_seed(seed)} split, not {self.split}; "
                f"{self.split} seeds satisfy seed % {SPLIT_SEED_STRIDE} == "
                f"{SPLIT_SEED_OFFSETS[self.split]}."
            )
        if seed in self.excluded_seeds:
            raise ValueError(f"Seed {seed} is reserved for {self.base_scenario_id} and excluded.")
        return self.generator.generate(replace(
            self.config,
            scenario_id=f"{self.base_scenario_id}_{self.split}_seed{seed}",
            seed=seed,
            split=self.split,
        ))


@dataclass(frozen=True)
class MixtureScenarioProvider:
    """Pick one same-split component per generation seed with fixed weights.

    The component for seed ``s`` depends only on the partition index
    ``s // 3``: ``u = int(sha256(f"bap_mixture_v1:{s // 3}")[:8]) / 2**64`` is
    compared with the cumulative normalized weights. The chosen component
    generates the instance, so family, split, seed and identity are its own.
    """

    components: tuple[SyntheticScenarioProvider, ...]
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        components, weights = tuple(self.components), tuple(self.weights)
        if not components:
            raise ValueError("A mixture needs at least one component.")
        if any(not isinstance(c, SyntheticScenarioProvider) for c in components):
            raise TypeError("Mixture components must be SyntheticScenarioProvider instances.")
        if len(weights) != len(components):
            raise ValueError("Provide exactly one weight per component.")
        if any(isinstance(w, bool) or not isinstance(w, Real) or not math.isfinite(w) or w <= 0
               for w in weights):
            raise ValueError("Mixture weights must be finite and positive.")
        if len({c.split for c in components}) != 1:
            raise ValueError("All mixture components must use the same split.")
        if len({c.base_scenario_id for c in components}) != len(components):
            raise ValueError("Mixture components need distinct base scenario IDs.")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "weights", tuple(float(w) for w in weights))

    @property
    def split(self) -> str:
        return self.components[0].split

    @property
    def vessel_count(self) -> int:
        """Largest component vessel count; the environment capacity must cover it."""

        return max(c.vessel_count for c in self.components)

    def component_for(self, seed: int) -> SyntheticScenarioProvider:
        _validate_seed(seed)
        digest = hashlib.sha256(f"bap_mixture_v1:{int(seed) // SPLIT_SEED_STRIDE}".encode()).digest()
        value = int.from_bytes(digest[:8], "big") / 2**64
        total, cumulative = sum(self.weights), 0.0
        for component, weight in zip(self.components, self.weights):
            cumulative += weight / total
            if value < cumulative:
                return component
        return self.components[-1]  # cumulative rounding just below 1.0

    def sample_seed(self, rng: np.random.Generator) -> int:
        """Draw split seeds until the selected component does not exclude it."""

        while True:
            seed = sample_split_seed(self.split, rng)
            if seed not in self.component_for(seed).excluded_seeds:
                return seed

    def __call__(self, seed: int) -> BAPScenarioInstance:
        return self.component_for(seed)(seed)


def iter_split_seeds(split: str, start: int = 0) -> Iterable[int]:
    """Yield a split's seeds in increasing order, beginning at or after start."""

    offset = SPLIT_SEED_OFFSETS[split]
    seed = start + (offset - start) % SPLIT_SEED_STRIDE
    while True:
        yield seed
        seed += SPLIT_SEED_STRIDE


def _validate_seed(seed: object) -> None:
    if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("Generation seed must be a non-negative integer.")
