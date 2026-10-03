"""Fresh dynamic scenario suites and cross-formulation exposure audit."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from berth_allocation_lab.envs import MixtureScenarioProvider
from berth_allocation_lab.rl.config import StaticPPOExperimentConfig
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.rl.suites import (
    ScenarioSuite, SplitLeakageError, assert_seed_exclusive, audit_fresh_suites,
    audit_split_isolation, build_config_suites, build_suite,
    historical_fixture_fingerprints, physical_fingerprint,
)
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


def dynamic_mixture(config: DynamicPPOConfig, split: str) -> MixtureScenarioProvider:
    providers = tuple(c.provider(split, config.project_root(), config.horizon_min)
                      for c in config.components)
    if any(p.vessel_count > config.max_vessels for p in providers):
        raise ValueError("Dynamic mixture exceeds max_vessels.")
    return MixtureScenarioProvider(providers, tuple(c.weight for c in config.components))


def dynamic_suites(config: DynamicPPOConfig) -> dict[str, ScenarioSuite]:
    used: dict[str, set[int]] = {}
    suites = {}
    for spec in (config.validation, config.test, *config.diagnostics):
        mixture = dynamic_mixture(config, spec.split)
        suites[spec.name] = build_suite(
            spec.name, mixture, seeds_per_component=spec.seeds_per_component,
            first_seed=spec.first_seed, used_seeds=used.setdefault(spec.split, set()))
    assert_seed_exclusive(suites.values())
    return suites


def prior_exposure_fingerprints(config: DynamicPPOConfig) -> frozenset[str]:
    root = config.project_root()
    examined = set(historical_fixture_fingerprints(root))
    for path in config.prior_configs:
        prior = StaticPPOExperimentConfig.load_yaml(config.resolve(path))
        for suite in build_config_suites(prior).values():
            examined.update(physical_fingerprint(s) for s in suite.scenarios)
    generator = SyntheticScenarioGenerator()
    for family in ("low", "medium", "heavy"):
        source = SyntheticScenarioConfig.load_yaml(root / "configs" / "scenarios" /
                                                   f"synthetic_{family}.yaml")
        if family == "low":
            source = replace(source.with_formulation("dynamic"),
                             future_horizon_min=240.0, scenario_id="synthetic_low_dynamic")
        examined.add(physical_fingerprint(generator.generate(source)))
    return frozenset(examined)


def audit_dynamic_suites(config: DynamicPPOConfig, suites: dict[str, ScenarioSuite]) -> dict:
    examined = prior_exposure_fingerprints(config)
    isolation = audit_split_isolation({name: suite.identities() for name, suite in suites.items()},
                                      historical_fixture_fingerprints(config.project_root()))
    freshness = audit_fresh_suites(suites.values(), examined)
    return {"split_isolation": isolation, "prior_exposure": freshness}
