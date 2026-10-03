"""Split-safe dynamic generator with the static provider's seed protocol."""

from __future__ import annotations

from berth_allocation_lab.envs.static_scenario_provider import (
    SPLIT_SEED_OFFSETS,
    SyntheticScenarioProvider,
    _SEED_SUFFIX,
    _validate_seed,
)


class DynamicSyntheticScenarioProvider(SyntheticScenarioProvider):
    """Generate dynamic instances without changing the static provider API."""

    def __post_init__(self) -> None:
        excluded = frozenset(self.excluded_seeds)
        for seed in excluded:
            _validate_seed(seed)
        object.__setattr__(self, "excluded_seeds", frozenset(int(s) for s in excluded))
        if self.config.formulation != "dynamic":
            raise ValueError("Dynamic provider requires a dynamic config.")
        if (not isinstance(self.base_scenario_id, str) or not self.base_scenario_id.strip()
                or _SEED_SUFFIX.search(self.base_scenario_id)):
            raise ValueError("base_scenario_id must be a clean ID without a _seed<N> suffix.")
        if self.split not in SPLIT_SEED_OFFSETS:
            raise ValueError("split must be train, validation, or test.")
