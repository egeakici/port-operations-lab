"""Split-aware scenario mixtures, fixed evaluation suites and leakage audits.

Seeds follow the Step 8 partition (``seed % 3``: train 0, validation 1,
test 2). Historically inspected Step 7 fixtures are identified by physical
content (quay, clearance and vessel inputs, independent of scenario ID and
split) so that they can never re-enter training or model selection unnoticed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.envs import MixtureScenarioProvider, iter_split_seeds, split_of_seed
from berth_allocation_lab.rl.config import (
    RLConfigError,
    ScenarioComponentConfig,
    StaticPPOExperimentConfig,
    SuiteSpec,
)
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


TINY_CONGESTED_SOURCE = "configs/scenarios/synthetic_tiny_congested.yaml"
# Step 7 reference fixtures: (vessel_count, seed) of the tiny congested preset.
HISTORICAL_TINY_FIXTURES = (*((n, 42) for n in range(2, 9)), (6, 0), (6, 1))
# Seed budget when scanning a partition for suite members.
_MAX_SCAN = 1_000_000


class SplitLeakageError(RuntimeError):
    """Train/validation/test or historical-fixture overlap; never ignored."""


@dataclass(frozen=True)
class ScenarioSuite:
    name: str
    split: str
    scenarios: tuple[BAPScenarioInstance, ...]

    def identities(self) -> list[dict[str, object]]:
        return [scenario_identity(s) for s in self.scenarios]


def physical_fingerprint(scenario: BAPScenarioInstance) -> str:
    """Hash of quay, clearance and vessel inputs only (ID/split/seed-free)."""

    payload = json.dumps({
        "berth_length_m": scenario.berth_length_m,
        "min_clearance_m": scenario.min_clearance_m,
        "vessels": [(v.arrival_time_min, v.length_m, v.service_time_min) for v in scenario.vessels],
    }, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scenario_identity(scenario: BAPScenarioInstance) -> dict[str, object]:
    return {
        "scenario_id": scenario.scenario_id,
        "scenario_seed": scenario.seed,
        "scenario_family": scenario.scenario_family,
        "scenario_split": scenario.split,
        "vessel_count": scenario.vessel_count,
        "generator_version": scenario.generator_version,
        "scenario_fingerprint": scenario.content_fingerprint,
        "physical_fingerprint": physical_fingerprint(scenario),
    }


def build_mixture(
    components: Sequence[ScenarioComponentConfig],
    split: str,
    project_root: Path,
    max_vessels: int,
) -> MixtureScenarioProvider:
    providers = [c.provider(split, project_root) for c in components]
    for component, provider in zip(components, providers):
        if provider.vessel_count > max_vessels:
            raise RLConfigError(
                f"Component {component.name} has {provider.vessel_count} vessels, above "
                f"max_vessels={max_vessels}; capacities must cover every scenario."
            )
    return MixtureScenarioProvider(tuple(providers), tuple(c.weight for c in components))


def build_suite(
    name: str,
    mixture: MixtureScenarioProvider,
    *,
    seeds_per_component: int | None = None,
    seeds: Iterable[int] | None = None,
    first_seed: int = 0,
    used_seeds: set[int] | None = None,
) -> ScenarioSuite:
    """Deterministic suite from explicit seeds or the first N seeds per component.

    Without explicit seeds the split partition is scanned in increasing order
    from ``first_seed``; each seed is used by exactly the component the mixture
    rule assigns to it, skipping reserved seeds and seeds already in
    ``used_seeds``, until every component has N scenarios. Chosen seeds are
    added to ``used_seeds`` so that suites of one split can share no seed.
    """

    if (seeds is None) == (seeds_per_component is None):
        raise ValueError("Give exactly one of seeds or seeds_per_component.")
    if seeds is not None:
        chosen = [int(s) for s in seeds]
        if len(set(chosen)) != len(chosen):
            raise ValueError("Explicit suite seeds must be distinct.")
        for seed in chosen:
            if split_of_seed(seed) != mixture.split:
                raise ValueError(f"Seed {seed} is not a {mixture.split} seed (seed % 3 rule).")
            if used_seeds is not None and seed in used_seeds:
                raise SplitLeakageError(f"Seed {seed} is already used by another {mixture.split} suite.")
        if used_seeds is not None:
            used_seeds.update(chosen)
        return ScenarioSuite(name, mixture.split, tuple(mixture(seed) for seed in chosen))

    counts = {id(c): 0 for c in mixture.components}
    scenarios = []
    for scanned, seed in enumerate(iter_split_seeds(mixture.split, first_seed)):
        if all(n >= seeds_per_component for n in counts.values()):
            break
        if scanned > _MAX_SCAN:
            raise RuntimeError("Suite construction did not fill every component.")
        if used_seeds is not None and seed in used_seeds:
            continue
        component = mixture.component_for(seed)
        if counts[id(component)] < seeds_per_component and seed not in component.excluded_seeds:
            counts[id(component)] += 1
            scenarios.append(component(seed))
            if used_seeds is not None:
                used_seeds.add(seed)
    return ScenarioSuite(name, mixture.split, tuple(scenarios))


def build_config_suite(config: StaticPPOExperimentConfig, spec: SuiteSpec,
                       seeds: Iterable[int] | None = None,
                       used_seeds: set[int] | None = None) -> ScenarioSuite:
    mixture = build_mixture(spec.components, spec.split, config.project_root(), config.max_vessels)
    if seeds is not None:
        return build_suite(spec.name, mixture, seeds=seeds, used_seeds=used_seeds)
    return build_suite(spec.name, mixture, seeds_per_component=spec.seeds_per_component,
                       first_seed=spec.first_seed, used_seeds=used_seeds)


def build_config_suites(config: StaticPPOExperimentConfig) -> dict[str, ScenarioSuite]:
    """Validation, test and diagnostic suites in that order.

    With ``seed_exclusive_suites`` all suites of one split draw from a shared
    used-seed set, so no generation seed (whose vessel stream would be shared,
    e.g. a 6-vessel instance equal to the first six vessels of an 8-vessel one)
    appears in two suites; the result is verified explicitly.
    """

    used: dict[str, set[int]] = {}
    suites = {}
    for spec in (config.validation, config.test, *config.diagnostics):
        shared = used.setdefault(spec.split, set()) if config.seed_exclusive_suites else None
        suites[spec.name] = build_config_suite(config, spec, used_seeds=shared)
    if config.seed_exclusive_suites:
        assert_seed_exclusive(suites.values())
    return suites


def assert_seed_exclusive(suites: Iterable[ScenarioSuite]) -> None:
    """No generation seed is used twice within or across suites of a split."""

    owner: dict[tuple[str, int], str] = {}
    for suite in suites:
        for scenario in suite.scenarios:
            key = (suite.split, scenario.seed)
            if key in owner:
                raise SplitLeakageError(
                    f"Seed {scenario.seed} is used by {owner[key]} and {suite.name}/{scenario.scenario_id}.")
            owner[key] = f"{suite.name}/{scenario.scenario_id}"


def previously_examined_fingerprints(config: StaticPPOExperimentConfig) -> frozenset[str]:
    """Physical fingerprints of every suite of the configs listed in prior_configs."""

    examined = set()
    for prior_path in config.prior_configs:
        prior = StaticPPOExperimentConfig.load_yaml(config.resolve(prior_path))
        for suite in build_config_suites(prior).values():
            examined.update(physical_fingerprint(s) for s in suite.scenarios)
    return frozenset(examined)


def audit_fresh_suites(suites: Iterable[ScenarioSuite], examined: frozenset[str]) -> dict[str, int]:
    """Raise if any suite repeats a physical instance examined by a prior config."""

    checked = 0
    for suite in suites:
        for scenario in suite.scenarios:
            checked += 1
            if physical_fingerprint(scenario) in examined:
                raise SplitLeakageError(
                    f"{suite.name}/{scenario.scenario_id} was already examined by a prior experiment.")
    return {"checked_instances": checked, "previously_examined_instances": len(examined)}


def historical_fixture_fingerprints(project_root: Path) -> frozenset[str]:
    """Physical fingerprints of the Step 7 tiny congested reference fixtures."""

    base = SyntheticScenarioConfig.load_yaml(project_root / TINY_CONGESTED_SOURCE)
    generator = SyntheticScenarioGenerator()
    return frozenset(
        physical_fingerprint(generator.generate(replace(
            base, seed=seed, traffic=replace(base.traffic, vessel_count=count))))
        for count, seed in HISTORICAL_TINY_FIXTURES
    )


def audit_split_isolation(
    groups: dict[str, Iterable[dict[str, object]]],
    historical: frozenset[str] = frozenset(),
    *,
    historical_allowed: Iterable[str] = (),
) -> dict[str, object]:
    """Raise SplitLeakageError on any prohibited overlap; return a summary.

    ``groups`` maps a group name (for example ``train_episodes``,
    ``validation``, ``test``) to scenario identity records. Checks: identity
    consistency with split and seed partition, one fingerprint per scenario ID,
    no physical instance or generation seed shared by different splits, and no
    historical fixture outside ``historical_allowed`` groups.
    """

    allowed = set(historical_allowed)
    owner_by_physical: dict[str, str] = {}
    seed_split: dict[tuple[str, int], str] = {}
    fingerprint_by_id: dict[str, str] = {}
    counts = {}
    for group, records in groups.items():
        records = list(records)
        counts[group] = len(records)
        for record in records:
            split, seed = record["scenario_split"], int(record["scenario_seed"])
            scenario_id = str(record["scenario_id"])
            if split_of_seed(seed) != split or not scenario_id.endswith(f"_{split}_seed{seed}"):
                raise SplitLeakageError(f"Inconsistent identity for {scenario_id} in {group}.")
            previous = fingerprint_by_id.setdefault(scenario_id, str(record["scenario_fingerprint"]))
            if previous != record["scenario_fingerprint"]:
                raise SplitLeakageError(f"Scenario ID {scenario_id} has two different contents.")
            physical = str(record["physical_fingerprint"])
            owner = owner_by_physical.setdefault(physical, split)
            if owner != split:
                raise SplitLeakageError(f"{scenario_id} ({group}) repeats a {owner} instance.")
            family = str(record["scenario_family"])
            if seed_split.setdefault((family, seed), split) != split:
                raise SplitLeakageError(f"Seed {seed} of {family} is used by two splits.")
            if physical in historical and group not in allowed:
                raise SplitLeakageError(f"{scenario_id} ({group}) recreates a Step 7 fixture.")
    return {"groups": counts, "distinct_physical_instances": len(owner_by_physical),
            "historical_fixtures_checked": len(historical)}
