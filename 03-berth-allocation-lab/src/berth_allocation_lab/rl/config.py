"""Validated Static Maskable PPO experiment configuration.

This module does not import Stable-Baselines3. Relative paths inside an RL
YAML file resolve against the project root (the nearest ancestor of the YAML
file that contains ``pyproject.toml``).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field, replace
from numbers import Integral, Real
from pathlib import Path
from typing import Any

from berth_allocation_lab.config import load_yaml_config
from berth_allocation_lab.envs import SyntheticScenarioProvider
from berth_allocation_lab.scenarios import SyntheticScenarioConfig


RL_CONFIG_SCHEMA_VERSION = 1
POLICY_ID = "static_maskable_ppo_v1"
V2_POLICY_ID = "static_maskable_ppo_v2"
FLAT_ARCHITECTURE = "flat_mlp_v1"
CANDIDATE_ARCHITECTURE = "candidate_scoring_v2"
SUPPORTED_POLICY = "MultiInputPolicy"
SELECTION_METRIC = "mean_validation_total_waiting_time_min"
DEFAULT_REWARD_SCALE = 1.0 / 1440.0


class RLConfigError(ValueError):
    """Invalid Static Maskable PPO configuration; raised before any training."""


@dataclass(frozen=True)
class ScenarioComponentConfig:
    """One synthetic family/configuration inside a split-aware mixture."""

    name: str
    source_config: str
    base_scenario_id: str
    weight: float = 1.0
    vessel_count: int | None = None
    static_twin: bool = False
    excluded_seeds: tuple[int, ...] = ()

    def synthetic_config(self, project_root: Path) -> SyntheticScenarioConfig:
        config = SyntheticScenarioConfig.load_yaml(_resolve(project_root, self.source_config))
        if config.formulation != "static":
            if not self.static_twin:
                raise RLConfigError(
                    f"Component {self.name} uses a dynamic preset; set static_twin: true explicitly."
                )
            config = config.with_formulation("static")
        if self.vessel_count is not None:
            config = replace(config, traffic=replace(config.traffic, vessel_count=self.vessel_count))
        return config

    def provider(self, split: str, project_root: Path) -> SyntheticScenarioProvider:
        return SyntheticScenarioProvider(
            self.synthetic_config(project_root), base_scenario_id=self.base_scenario_id,
            split=split, excluded_seeds=frozenset(self.excluded_seeds),
        )


@dataclass(frozen=True)
class PPOHyperparameters:
    policy: str = SUPPORTED_POLICY
    gamma: float = 1.0
    alternative_training_objective: bool = False
    learning_rate: float = 3e-4
    n_steps: int = 512
    batch_size: int = 128
    n_epochs: int = 5
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    net_arch_pi: tuple[int, ...] = (128, 128)
    net_arch_vf: tuple[int, ...] = (128, 128)
    n_envs: int = 1
    vec_env: str = "dummy"
    device: str = "auto"

    def policy_kwargs(self) -> dict[str, Any]:
        return {"net_arch": {"pi": list(self.net_arch_pi), "vf": list(self.net_arch_vf)}}


@dataclass(frozen=True)
class CandidateArchitecture:
    vessel_embedding_dim: int = 64
    context_dim: int = 128
    scorer_layers: tuple[int, ...] = (128, 128)
    value_layers: tuple[int, ...] = (128, 128)

    def policy_kwargs(self) -> dict[str, Any]:
        return {"vessel_embedding_dim": self.vessel_embedding_dim, "context_dim": self.context_dim,
                "scorer_layers": self.scorer_layers, "value_layers": self.value_layers}


@dataclass(frozen=True)
class TrainingSettings:
    training_seeds: tuple[int, ...]
    total_timesteps: int
    eval_freq: int


@dataclass(frozen=True)
class SuiteSpec:
    """A fixed evaluation suite: first N partition seeds per component."""

    name: str
    split: str
    seeds_per_component: int
    components: tuple[ScenarioComponentConfig, ...] = ()
    first_seed: int = 0


@dataclass(frozen=True)
class StaticPPOExperimentConfig:
    experiment_id: str
    experiment_version: int
    description: str
    max_vessels: int
    components: tuple[ScenarioComponentConfig, ...]
    training: TrainingSettings
    ppo: PPOHyperparameters
    validation: SuiteSpec
    test: SuiteSpec
    diagnostics: tuple[SuiteSpec, ...] = ()
    time_scale_min: float = 1440.0
    length_scale_m: float = 1000.0
    reward_scale: float = DEFAULT_REWARD_SCALE
    exact_max_vessels: int = 8
    output_dir: str = "experiments/rl/static_ppo"
    seed_exclusive_suites: bool = False
    prior_configs: tuple[str, ...] = ()
    require_validation_decision: bool = False
    policy_id: str = POLICY_ID
    policy_architecture: str = FLAT_ARCHITECTURE
    architecture: CandidateArchitecture = field(default_factory=CandidateArchitecture)
    selection_metric: str = SELECTION_METRIC
    schema_version: int = RL_CONFIG_SCHEMA_VERSION
    source_path: str | None = field(default=None, compare=False)
    source_sha256: str | None = field(default=None, compare=False)

    @classmethod
    def load_yaml(cls, path: str | Path) -> "StaticPPOExperimentConfig":
        path = Path(path).resolve()
        config = cls.from_mapping(load_yaml_config(path))
        return replace(config, source_path=str(path),
                       source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "StaticPPOExperimentConfig":
        data = dict(data)
        _reject_unknown(data, {
            "schema_version", "experiment_id", "experiment_version", "description", "max_vessels",
            "time_scale_min", "length_scale_m", "reward_scale", "exact_max_vessels", "output_dir",
            "policy_id", "policy_architecture", "architecture", "selection_metric", "components", "training", "ppo", "validation", "test",
            "diagnostics", "seed_exclusive_suites", "prior_configs", "require_validation_decision",
        }, "experiment")
        components = tuple(_component(c) for c in _list(data, "components"))
        training = _mapping(data, "training")
        _reject_unknown(training, {"training_seeds", "total_timesteps", "eval_freq"}, "training")
        ppo = dict(_mapping(data, "ppo"))
        net_arch = ppo.pop("net_arch", {"pi": [128, 128], "vf": [128, 128]})
        _reject_unknown(ppo, {f for f in PPOHyperparameters.__dataclass_fields__
                              if not f.startswith("net_arch")}, "ppo")
        if not isinstance(net_arch, dict) or set(net_arch) != {"pi", "vf"}:
            raise RLConfigError("ppo.net_arch must define exactly pi and vf layer lists.")
        architecture = dict(data.get("architecture", {}) or {})
        _reject_unknown(architecture, set(CandidateArchitecture.__dataclass_fields__), "architecture")
        for layers in ("scorer_layers", "value_layers"):
            if layers in architecture:
                architecture[layers] = tuple(architecture[layers])
        config = cls(
            schema_version=data.get("schema_version", RL_CONFIG_SCHEMA_VERSION),
            experiment_id=data.get("experiment_id"),
            experiment_version=data.get("experiment_version"),
            description=data.get("description", ""),
            max_vessels=data.get("max_vessels"),
            time_scale_min=data.get("time_scale_min", 1440.0),
            length_scale_m=data.get("length_scale_m", 1000.0),
            reward_scale=data.get("reward_scale", DEFAULT_REWARD_SCALE),
            exact_max_vessels=data.get("exact_max_vessels", 8),
            output_dir=data.get("output_dir", "experiments/rl/static_ppo"),
            seed_exclusive_suites=data.get("seed_exclusive_suites", False),
            prior_configs=tuple(data.get("prior_configs", ()) or ()),
            require_validation_decision=data.get("require_validation_decision", False),
            policy_id=data.get("policy_id", POLICY_ID),
            policy_architecture=data.get("policy_architecture", FLAT_ARCHITECTURE),
            architecture=CandidateArchitecture(**architecture),
            selection_metric=data.get("selection_metric", SELECTION_METRIC),
            components=components,
            training=TrainingSettings(
                training_seeds=tuple(training.get("training_seeds", ())),
                total_timesteps=training.get("total_timesteps"),
                eval_freq=training.get("eval_freq"),
            ),
            ppo=PPOHyperparameters(
                **ppo, net_arch_pi=tuple(net_arch["pi"]), net_arch_vf=tuple(net_arch["vf"]),
            ),
            validation=_suite(_mapping(data, "validation"), "validation", "validation", components),
            test=_suite(_mapping(data, "test"), "test", "test", components),
            diagnostics=tuple(_diagnostic(d) for d in data.get("diagnostics", []) or []),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.schema_version != RL_CONFIG_SCHEMA_VERSION:
            raise RLConfigError(f"Unsupported RL config schema_version {self.schema_version}.")
        _text(self.experiment_id, "experiment_id")
        _positive_int(self.experiment_version, "experiment_version")
        _positive_int(self.max_vessels, "max_vessels")
        _positive_int(self.exact_max_vessels, "exact_max_vessels")
        for name in ("time_scale_min", "length_scale_m", "reward_scale"):
            _positive_number(getattr(self, name), name)
        _text(self.output_dir, "output_dir")
        expected_id = {FLAT_ARCHITECTURE: POLICY_ID,
                       CANDIDATE_ARCHITECTURE: V2_POLICY_ID}.get(self.policy_architecture)
        if expected_id is None or self.policy_id != expected_id:
            raise RLConfigError("policy_id must match policy_architecture.")
        for name in ("vessel_embedding_dim", "context_dim"):
            _positive_int(getattr(self.architecture, name), f"architecture.{name}")
        for name in ("scorer_layers", "value_layers"):
            layers = getattr(self.architecture, name)
            if not layers:
                raise RLConfigError(f"architecture.{name} must be non-empty.")
            for width in layers:
                _positive_int(width, f"architecture.{name} width")
        if self.selection_metric != SELECTION_METRIC:
            raise RLConfigError(f"selection_metric must be {SELECTION_METRIC}.")
        if not self.components:
            raise RLConfigError("At least one training component is required.")
        _validate_components(self.components, "components")
        seeds = self.training.training_seeds
        if not seeds or len(set(seeds)) != len(seeds):
            raise RLConfigError("training.training_seeds must be a non-empty list of distinct seeds.")
        for seed in seeds:
            _non_negative_int(seed, "training seed")
        _positive_int(self.training.total_timesteps, "training.total_timesteps")
        _positive_int(self.training.eval_freq, "training.eval_freq")
        self._validate_ppo()
        for suite in (self.validation, self.test, *self.diagnostics):
            _positive_int(suite.seeds_per_component, f"{suite.name}.seeds_per_component")
            _non_negative_int(suite.first_seed, f"{suite.name}.first_seed")
        for name in ("seed_exclusive_suites", "require_validation_decision"):
            if not isinstance(getattr(self, name), bool):
                raise RLConfigError(f"{name} must be a boolean.")
        for prior in self.prior_configs:
            _text(prior, "prior_configs entry")
        if len({s.name for s in (self.validation, self.test, *self.diagnostics)}) != 2 + len(self.diagnostics):
            raise RLConfigError("Evaluation suite names must be distinct.")
        for suite in self.diagnostics:
            if suite.split != "test":
                raise RLConfigError("Diagnostic suites use held-out test seeds.")
            _validate_components(suite.components, suite.name)

    def _validate_ppo(self) -> None:
        ppo = self.ppo
        if ppo.policy != SUPPORTED_POLICY:
            raise RLConfigError(f"ppo.policy must be {SUPPORTED_POLICY} for the Dict observation.")
        _positive_number(ppo.gamma, "ppo.gamma")
        if ppo.gamma > 1.0:
            raise RLConfigError("ppo.gamma must lie in (0, 1].")
        if ppo.gamma != 1.0 and ppo.alternative_training_objective is not True:
            raise RLConfigError(
                "gamma < 1 changes the training objective; set "
                "ppo.alternative_training_objective: true to label it explicitly."
            )
        for name in ("learning_rate", "clip_range", "max_grad_norm"):
            _positive_number(getattr(ppo, name), f"ppo.{name}")
        for name in ("ent_coef", "vf_coef"):
            _non_negative_number(getattr(ppo, name), f"ppo.{name}")
        if not 0.0 < ppo.gae_lambda <= 1.0:
            raise RLConfigError("ppo.gae_lambda must lie in (0, 1].")
        for name in ("n_steps", "batch_size", "n_epochs"):
            _positive_int(getattr(ppo, name), f"ppo.{name}")
        _positive_int(ppo.n_envs, "ppo.n_envs")
        if ppo.vec_env not in {"dummy", "subproc"}:
            raise RLConfigError("ppo.vec_env must be dummy or subproc.")
        if not 1 < ppo.batch_size <= ppo.n_steps * ppo.n_envs:
            raise RLConfigError("ppo.batch_size must satisfy 1 < batch_size <= n_steps * n_envs.")
        if not ppo.net_arch_pi or not ppo.net_arch_vf:
            raise RLConfigError("ppo.net_arch layers must be non-empty.")
        for width in (*ppo.net_arch_pi, *ppo.net_arch_vf):
            _positive_int(width, "ppo.net_arch width")
        if ppo.device not in {"auto", "cpu", "cuda"}:
            raise RLConfigError("ppo.device must be auto, cpu or cuda.")

    def project_root(self) -> Path:
        if self.source_path is None:
            return Path.cwd()
        for parent in Path(self.source_path).parents:
            if (parent / "pyproject.toml").is_file():
                return parent
        raise RLConfigError(f"No project root (pyproject.toml) above {self.source_path}.")

    def resolve(self, relative: str) -> Path:
        return _resolve(self.project_root(), relative)

    def policy_kwargs(self) -> dict[str, Any]:
        kwargs = self.ppo.policy_kwargs()
        if self.policy_architecture == CANDIDATE_ARCHITECTURE:
            kwargs.update(self.architecture.policy_kwargs())
        return kwargs

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ parsing


def _component(data: Any) -> ScenarioComponentConfig:
    if not isinstance(data, dict):
        raise RLConfigError("Each component must be a mapping.")
    _reject_unknown(data, set(ScenarioComponentConfig.__dataclass_fields__), "component")
    return ScenarioComponentConfig(
        name=data.get("name"), source_config=data.get("source_config"),
        base_scenario_id=data.get("base_scenario_id"), weight=data.get("weight", 1.0),
        vessel_count=data.get("vessel_count"), static_twin=data.get("static_twin", False),
        excluded_seeds=tuple(data.get("excluded_seeds", ()) or ()),
    )


def _suite(data: dict[str, Any], name: str, split: str,
           components: tuple[ScenarioComponentConfig, ...]) -> SuiteSpec:
    _reject_unknown(data, {"seeds_per_component", "first_seed"}, name)
    return SuiteSpec(name=name, split=split, seeds_per_component=data.get("seeds_per_component"),
                     components=components, first_seed=data.get("first_seed", 0))


def _diagnostic(data: Any) -> SuiteSpec:
    if not isinstance(data, dict):
        raise RLConfigError("Each diagnostic suite must be a mapping.")
    _reject_unknown(data, {"name", "seeds_per_component", "components", "first_seed"}, "diagnostic")
    _text(data.get("name"), "diagnostic name")
    if data["name"] in {"validation", "test"}:
        raise RLConfigError("Diagnostic suite names must differ from validation/test.")
    return SuiteSpec(name=data["name"], split="test", seeds_per_component=data.get("seeds_per_component"),
                     components=tuple(_component(c) for c in _list(data, "components")),
                     first_seed=data.get("first_seed", 0))


def _validate_components(components: tuple[ScenarioComponentConfig, ...], where: str) -> None:
    if not components:
        raise RLConfigError(f"{where} needs at least one component.")
    for c in components:
        _text(c.name, f"{where} component name")
        _text(c.source_config, f"{where}.{c.name}.source_config")
        _text(c.base_scenario_id, f"{where}.{c.name}.base_scenario_id")
        _positive_number(c.weight, f"{where}.{c.name}.weight")
        if c.vessel_count is not None:
            _positive_int(c.vessel_count, f"{where}.{c.name}.vessel_count")
        if not isinstance(c.static_twin, bool):
            raise RLConfigError(f"{where}.{c.name}.static_twin must be a boolean.")
        for seed in c.excluded_seeds:
            _non_negative_int(seed, f"{where}.{c.name}.excluded_seeds entry")
    for attribute in ("name", "base_scenario_id"):
        values = [getattr(c, attribute) for c in components]
        if len(set(values)) != len(values):
            raise RLConfigError(f"{where} component {attribute} values must be distinct.")


def _resolve(root: Path, relative: str) -> Path:
    path = Path(relative)
    return path if path.is_absolute() else root / path


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise RLConfigError(f"{key} must be a mapping.")
    return value


def _list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise RLConfigError(f"{key} must be a list.")
    return value


def _reject_unknown(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise RLConfigError(f"Unknown {where} field(s): {', '.join(unknown)}.")


def _text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RLConfigError(f"{name} must be a non-empty string.")


def _positive_int(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise RLConfigError(f"{name} must be a positive integer.")


def _non_negative_int(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise RLConfigError(f"{name} must be a non-negative integer.")


def _positive_number(value: Any, name: str) -> None:
    if (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
            or value <= 0):
        raise RLConfigError(f"{name} must be a finite positive number.")


def _non_negative_number(value: Any, name: str) -> None:
    if (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
            or value < 0):
        raise RLConfigError(f"{name} must be a finite non-negative number.")
