"""Small, explicit configuration for one frozen benchmark branch."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from berth_allocation_lab.config import load_yaml_config


class BenchmarkError(ValueError):
    """A frozen input, benchmark config or comparison contract is invalid."""


@dataclass(frozen=True)
class BenchmarkSource:
    regime: str
    version: str
    experiment_id: str
    config_path: str
    evaluation_path: str


@dataclass(frozen=True)
class BenchmarkConfig:
    benchmark_id: str
    formulation: str
    output_root: str
    sources: tuple[BenchmarkSource, ...]
    decisions: dict[str, str]
    families: dict[str, dict[str, float]]
    bootstrap_resamples: int
    confidence_level: float
    bootstrap_seed: int
    replay_mode: str
    source_path: Path
    project_root: Path

    @classmethod
    def load(cls, path: str | Path) -> "BenchmarkConfig":
        source_path = Path(path).resolve()
        root = next((p for p in source_path.parents if (p / "pyproject.toml").is_file()), None)
        if root is None:
            raise BenchmarkError("Benchmark config must be under Project 03.")
        data = dict(load_yaml_config(source_path))
        allowed = {"schema_version", "benchmark_id", "formulation", "output_root",
                   "sources", "decisions", "families", "bootstrap", "replay_mode"}
        if set(data) - allowed or data.get("schema_version") != 1:
            raise BenchmarkError("Unsupported benchmark fields or schema version.")
        formulation = data.get("formulation")
        if formulation not in {"static", "dynamic"}:
            raise BenchmarkError("formulation must be static or dynamic.")
        benchmark_id = data.get("benchmark_id")
        if not isinstance(benchmark_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", benchmark_id):
            raise BenchmarkError("benchmark_id must be a safe lowercase directory name.")
        if data.get("replay_mode") not in {"off", "verify_if_needed"}:
            raise BenchmarkError("replay_mode must be off or verify_if_needed.")
        bootstrap = data.get("bootstrap", {})
        if set(bootstrap) != {"resamples", "confidence_level", "seed"}:
            raise BenchmarkError("bootstrap requires resamples, confidence_level and seed.")
        n, level, seed = bootstrap["resamples"], bootstrap["confidence_level"], bootstrap["seed"]
        if (type(n) is not int or n <= 0 or type(seed) is not int or
                isinstance(level, bool) or not isinstance(level, (int, float)) or
                not 0 < level < 1):
            raise BenchmarkError("Invalid bootstrap parameters.")
        sources = tuple(BenchmarkSource(**item) for item in data.get("sources", ()))
        if not sources or len({(s.regime, s.version) for s in sources}) != len(sources):
            raise BenchmarkError("Sources must be nonempty and unique by regime/version.")
        if any(not all((s.regime, s.version, s.experiment_id, s.config_path,
                        s.evaluation_path)) for s in sources):
            raise BenchmarkError("Incomplete source declaration.")
        families = data.get("families", {})
        if set(families) != {s.regime for s in sources}:
            raise BenchmarkError("Family weights must cover exactly the source regimes.")
        for regime, weights in families.items():
            if not weights or any(not isinstance(w, (int, float)) or w <= 0 for w in weights.values()):
                raise BenchmarkError(f"Invalid family weights for {regime}.")
        decisions = data.get("decisions", {})
        if set(decisions) != ({"v1", "v2"} if formulation == "static" else {"dynamic_rule_1"}):
            raise BenchmarkError("Required frozen decision paths are missing.")
        versions = {s.regime: {x.version for x in sources if x.regime == s.regime} for s in sources}
        expected = {"v1", "v2"} if formulation == "static" else {"v1"}
        if any(value != expected for value in versions.values()) or set(versions) != {"tiny", "medium_heavy"}:
            raise BenchmarkError("Both regimes and the frozen policy versions are required.")
        config = cls(benchmark_id, formulation, data["output_root"], sources, decisions,
                     {r: dict(v) for r, v in families.items()}, n, float(level), seed,
                     data["replay_mode"], source_path, root)
        for relative in [config.output_root, *decisions.values(),
                         *(value for s in sources for value in (s.config_path, s.evaluation_path))]:
            config.resolve(relative)
        return config

    def resolve(self, relative: str) -> Path:
        path = (self.project_root / relative).resolve()
        if not path.is_relative_to(self.project_root):
            raise BenchmarkError(f"Path leaves Project 03: {relative}")
        return path

    def normalized_weights(self, regime: str) -> dict[str, float]:
        values = self.families[regime]
        total = sum(values.values())
        return {family: weight / total for family, weight in values.items()}

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "benchmark_id": self.benchmark_id,
            "formulation": self.formulation, "output_root": self.output_root,
            "sources": [vars(s) for s in self.sources], "decisions": self.decisions,
            "families": self.families,
            "bootstrap": {"resamples": self.bootstrap_resamples,
                          "confidence_level": self.confidence_level,
                          "seed": self.bootstrap_seed},
            "replay_mode": self.replay_mode,
        }
