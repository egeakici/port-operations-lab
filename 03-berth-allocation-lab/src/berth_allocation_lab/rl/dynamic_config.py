"""Validated Step 11 config; inherited YAML resolves before fingerprinting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from berth_allocation_lab.config import load_yaml_config
from berth_allocation_lab.envs import DynamicSyntheticScenarioProvider
from berth_allocation_lab.rl.config import PPOHyperparameters, TrainingSettings
from berth_allocation_lab.scenarios import SyntheticScenarioConfig

POLICY_ID = "dynamic_maskable_ppo_v1"
POLICY_ARCHITECTURE = "dynamic_joint_action_scoring_v1"
OBSERVATION_VERSION = "dynamic_obs_v1"
ENVIRONMENT_VERSION = "dynamic_bap_env_v1"
REWARD_SCALE = 1.0 / 1440.0
FROZEN_PPO = {
    "gamma": 1.0, "learning_rate": 3e-4, "n_steps": 256, "batch_size": 256,
    "n_epochs": 10, "gae_lambda": 0.95, "clip_range": 0.2,
    "ent_coef": 0.01, "vf_coef": 0.5, "max_grad_norm": 0.5,
    "device": "cpu", "vec_env": "dummy",
}


class DynamicConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DynamicComponent:
    name: str
    source_config: str
    base_scenario_id: str
    vessel_count: int | None = None
    weight: float = 1.0
    excluded_seeds: tuple[int, ...] = ()

    def provider(self, split: str, root: Path, horizon_min: float) -> DynamicSyntheticScenarioProvider:
        cfg = SyntheticScenarioConfig.load_yaml(root / self.source_config)
        if cfg.formulation == "static":
            cfg = cfg.with_formulation("dynamic")
        cfg = replace(cfg, future_horizon_min=horizon_min)
        if self.vessel_count is not None:
            cfg = replace(cfg, traffic=replace(cfg.traffic, vessel_count=self.vessel_count))
        return DynamicSyntheticScenarioProvider(
            cfg, self.base_scenario_id, split, frozenset(self.excluded_seeds))


@dataclass(frozen=True)
class DynamicSuiteSpec:
    name: str
    split: str
    first_seed: int
    seeds_per_component: int


@dataclass(frozen=True)
class DynamicPPOConfig:
    experiment_id: str
    regime: str
    horizon_min: float
    max_vessels: int
    components: tuple[DynamicComponent, ...]
    training: TrainingSettings
    ppo: PPOHyperparameters
    validation: DynamicSuiteSpec
    test: DynamicSuiteSpec
    diagnostics: tuple[DynamicSuiteSpec, ...]
    output_dir: str
    prior_configs: tuple[str, ...]
    require_validation_decision: bool = True
    time_scale_min: float = 1440.0
    length_scale_m: float = 1000.0
    reward_scale: float = REWARD_SCALE
    policy_id: str = POLICY_ID
    policy_architecture: str = POLICY_ARCHITECTURE
    observation_version: str = OBSERVATION_VERSION
    environment_version: str = ENVIRONMENT_VERSION
    schema_version: int = 1
    source_path: str | None = field(default=None, compare=False)
    source_sha256: str | None = field(default=None, compare=False)

    @classmethod
    def load_yaml(cls, path: str | Path) -> "DynamicPPOConfig":
        path = Path(path).resolve()
        root = next((p for p in path.parents if (p / "pyproject.toml").is_file()), None)
        if root is None:
            raise DynamicConfigError("Config must be below the Project 03 root.")
        mapping = _load_inherited(path, root, set())
        config = cls.from_mapping(mapping)
        digest = hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest()
        return replace(config, source_path=str(path), source_sha256=digest)

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "DynamicPPOConfig":
        allowed = {"schema_version", "experiment_id", "regime", "horizon_min", "max_vessels",
                   "components", "training", "ppo", "validation", "test", "diagnostics",
                   "output_dir", "prior_configs", "require_validation_decision",
                   "time_scale_min", "length_scale_m", "reward_scale", "policy_id",
                   "policy_architecture", "observation_version", "environment_version"}
        _unknown(mapping, allowed, "experiment")
        components = tuple(DynamicComponent(
            name=c["name"], source_config=c["source_config"],
            base_scenario_id=c["base_scenario_id"], vessel_count=c.get("vessel_count"),
            weight=c.get("weight", 1.0), excluded_seeds=tuple(c.get("excluded_seeds", ())))
            for c in mapping["components"])
        training = TrainingSettings(**{**mapping["training"],
                                       "training_seeds": tuple(mapping["training"]["training_seeds"])})
        ppo = PPOHyperparameters(**mapping["ppo"])
        suites = {name: DynamicSuiteSpec(name=name, split=split, **mapping[name])
                  for name, split in (("validation", "validation"), ("test", "test"))}
        diagnostics = tuple(DynamicSuiteSpec(name=d["name"], split="test",
                                             first_seed=d["first_seed"],
                                             seeds_per_component=d["seeds_per_component"])
                            for d in mapping.get("diagnostics", ()))
        config = cls(
            experiment_id=mapping["experiment_id"], regime=mapping["regime"],
            horizon_min=mapping["horizon_min"], max_vessels=mapping["max_vessels"],
            components=components, training=training, ppo=ppo,
            validation=suites["validation"], test=suites["test"], diagnostics=diagnostics,
            output_dir=mapping["output_dir"], prior_configs=tuple(mapping["prior_configs"]),
            require_validation_decision=mapping.get("require_validation_decision", True),
            time_scale_min=mapping.get("time_scale_min", 1440.0),
            length_scale_m=mapping.get("length_scale_m", 1000.0),
            reward_scale=mapping.get("reward_scale", REWARD_SCALE),
            policy_id=mapping.get("policy_id", POLICY_ID),
            policy_architecture=mapping.get("policy_architecture", POLICY_ARCHITECTURE),
            observation_version=mapping.get("observation_version", OBSERVATION_VERSION),
            environment_version=mapping.get("environment_version", ENVIRONMENT_VERSION),
            schema_version=mapping.get("schema_version", 1),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.schema_version != 1 or self.policy_id != POLICY_ID or self.policy_architecture != POLICY_ARCHITECTURE:
            raise DynamicConfigError("Dynamic policy identifiers or schema version do not match v1.")
        if self.observation_version != OBSERVATION_VERSION or self.environment_version != ENVIRONMENT_VERSION:
            raise DynamicConfigError("Dynamic environment/observation version mismatch.")
        if self.regime not in {"tiny", "medium_heavy"}:
            raise DynamicConfigError("regime must be tiny or medium_heavy.")
        if self.horizon_min not in {0, 240}:
            raise DynamicConfigError("Part A supports only H=0 or H=240.")
        if self.max_vessels not in {8, 24} or (self.regime == "tiny") != (self.max_vessels == 8):
            raise DynamicConfigError("Regime and max_vessels disagree.")
        if self.reward_scale != REWARD_SCALE or self.time_scale_min != 1440.0 or self.length_scale_m != 1000.0:
            raise DynamicConfigError("Reward or observation scales differ from the frozen contract.")
        for name, expected in FROZEN_PPO.items():
            if getattr(self.ppo, name) != expected:
                raise DynamicConfigError(f"ppo.{name} must remain {expected!r}.")
        if self.ppo.n_envs not in {1, 4, 8}:
            raise DynamicConfigError("n_envs must be 1, 4 or 8.")
        if self.ppo.policy != "MultiInputPolicy":
            raise DynamicConfigError("PPO must use the Dict-compatible policy interface.")
        if self.training.training_seeds != (11, 23, 37):
            raise DynamicConfigError("Training seeds must be 11, 23, 37.")
        if self.training.total_timesteps <= 0 or self.training.eval_freq <= 0:
            raise DynamicConfigError("Training budgets must be positive.")
        if not self.components or len({c.name for c in self.components}) != len(self.components):
            raise DynamicConfigError("Components must be nonempty with unique names.")
        if any(c.weight <= 0 or not c.base_scenario_id for c in self.components):
            raise DynamicConfigError("Component weights and IDs must be valid.")
        for spec in (self.validation, self.test, *self.diagnostics):
            if spec.seeds_per_component <= 0:
                raise DynamicConfigError("Suite sizes must be positive.")
            if spec.split == "validation" and spec.first_seed < 5_000_000:
                raise DynamicConfigError("Validation seeds must start in the new 5M region.")
            if spec.split == "test" and spec.name == "test" and spec.first_seed < 6_000_000:
                raise DynamicConfigError("Test seeds must start in the new 6M region.")
            if spec.name not in {"validation", "test"} and spec.first_seed < 7_000_000:
                raise DynamicConfigError("Diagnostic seeds must start in the new 7M region.")
        if not self.prior_configs:
            raise DynamicConfigError("Prior Step 9 configs are required for exposure audit.")

    def project_root(self) -> Path:
        if self.source_path is None:
            return Path.cwd()
        return next(p for p in Path(self.source_path).parents if (p / "pyproject.toml").is_file())

    def resolve(self, path: str) -> Path:
        value = Path(path)
        return value if value.is_absolute() else self.project_root() / value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unknown(mapping: dict[str, Any], allowed: set[str], where: str) -> None:
    extra = set(mapping) - allowed
    if extra:
        raise DynamicConfigError(f"Unknown {where} fields: {sorted(extra)}")


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        merged[key] = (_merge(merged[key], value) if key in merged and
                       isinstance(merged[key], dict) and isinstance(value, dict) else value)
    return merged


def _load_inherited(path: Path, root: Path, seen: set[Path]) -> dict[str, Any]:
    if path in seen:
        raise DynamicConfigError("Config inheritance cycle.")
    seen.add(path)
    data = dict(load_yaml_config(path))
    parent = data.pop("extends", None)
    if parent is None:
        return data
    parent_path = (root / parent).resolve()
    if not parent_path.is_relative_to(root.resolve()):
        raise DynamicConfigError("Inherited config must remain in Project 03.")
    return _merge(_load_inherited(parent_path, root, seen), data)
