"""Maskable PPO checkpoints and a StaticPolicy-compatible inference adapter.

Inference always passes the current action mask and uses deterministic
actions. A masked or malformed prediction raises; there is no fallback to
FCFS or any other policy.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gymnasium
import numpy as np
import sb3_contrib
import stable_baselines3
import torch
from sb3_contrib import MaskablePPO

from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.envs import ENVIRONMENT_VERSION, OBSERVATION_VERSION, StaticBAPEnv
from berth_allocation_lab.policies.base import StaticScheduleResult
from berth_allocation_lab.rl.candidate_scoring import CandidateScoringMaskablePolicy
from berth_allocation_lab.rl.config import (CANDIDATE_ARCHITECTURE, FLAT_ARCHITECTURE,
                                            POLICY_ID, V2_POLICY_ID)


MODEL_METADATA_VERSION = 1
ENVIRONMENT_ID = "StaticBAPEnv"
REWARD_DEFINITION_VERSION = "negative_waiting_v1"
CANDIDATE_GENERATOR_VERSION = "boundary_candidates_v1"


class CheckpointCompatibilityError(ValueError):
    """A checkpoint does not match the environment it is asked to act in."""


class MaskedActionError(RuntimeError):
    """The model produced an index that the current action mask forbids."""


def dependency_versions() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "torch": torch.__version__,
        "gymnasium": gymnasium.__version__,
        "stable_baselines3": stable_baselines3.__version__,
        "sb3_contrib": sb3_contrib.__version__,
    }


def hardware_metadata() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "torch_threads": torch.get_num_threads(),
        "cuda_available": torch.cuda.is_available(),
    }


def metadata_path(checkpoint: str | Path) -> Path:
    path = Path(checkpoint)
    return path.with_name(path.stem + ".metadata.json")


def build_model_metadata(model: MaskablePPO, metadata: dict[str, Any]) -> dict[str, Any]:
    """Versioned model record; ``metadata`` adds run fields (seed, scales, ...)."""

    architecture = (CANDIDATE_ARCHITECTURE if isinstance(model.policy, CandidateScoringMaskablePolicy)
                    else FLAT_ARCHITECTURE)
    return {
        "model_metadata_version": MODEL_METADATA_VERSION,
        "policy_id": POLICY_ID,
        "policy_family": "maskable_ppo",
        "algorithm": "MaskablePPO",
        "algorithm_version": "v2" if architecture == CANDIDATE_ARCHITECTURE else "v1",
        "environment_id": ENVIRONMENT_ID,
        "environment_version": ENVIRONMENT_VERSION,
        "observation_definition_version": OBSERVATION_VERSION,
        "reward_definition_version": REWARD_DEFINITION_VERSION,
        "candidate_generator_version": CANDIDATE_GENERATOR_VERSION,
        "action_capacity": int(model.action_space.n),
        "policy_architecture": architecture,
        "architecture_hyperparameters": (
            {key: list(value) if isinstance(value, tuple) else value
             for key, value in model.policy._get_constructor_parameters().items()
             if key in {"vessel_embedding_dim", "context_dim", "scorer_layers", "value_layers"}}
            if architecture == CANDIDATE_ARCHITECTURE else
            {"net_arch": model.policy.net_arch}),
        "dependency_versions": dependency_versions(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **metadata,
        "policy_architecture": architecture,
    }


def save_checkpoint(model: MaskablePPO, path: str | Path, metadata: dict[str, Any]) -> Path:
    """Save ``<name>.zip`` and its ``<name>.metadata.json`` sidecar."""

    path = Path(path)
    model.save(path)
    record = build_model_metadata(model, metadata)
    metadata_path(path).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_checkpoint(path: str | Path, device: str = "cpu", *,
                    expected_architecture: str | None = None) -> tuple[MaskablePPO, dict[str, Any]]:
    path = Path(path)
    sidecar = metadata_path(path)
    if not path.is_file() or not sidecar.is_file():
        raise CheckpointCompatibilityError(f"Checkpoint {path} or its metadata sidecar is missing.")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    if metadata.get("model_metadata_version") != MODEL_METADATA_VERSION:
        raise CheckpointCompatibilityError("Unsupported model metadata version.")
    model = MaskablePPO.load(path, device=device)
    if int(model.action_space.n) != metadata.get("action_capacity"):
        raise CheckpointCompatibilityError("Checkpoint action space differs from its metadata.")
    architecture = metadata.get("policy_architecture", FLAT_ARCHITECTURE)
    actual = (CANDIDATE_ARCHITECTURE if isinstance(model.policy, CandidateScoringMaskablePolicy)
              else FLAT_ARCHITECTURE)
    if architecture != actual or (expected_architecture is not None and architecture != expected_architecture):
        raise CheckpointCompatibilityError("Checkpoint policy_architecture differs from requested/model architecture.")
    return model, metadata


def check_checkpoint_compatibility(metadata: dict[str, Any], model: MaskablePPO,
                                   env: StaticBAPEnv, *, expected_architecture: str | None = None) -> None:
    """Reject a checkpoint whose schema, capacity, scales or spaces differ."""

    architecture = metadata.get("policy_architecture", FLAT_ARCHITECTURE)
    actual = (CANDIDATE_ARCHITECTURE if isinstance(model.policy, CandidateScoringMaskablePolicy)
              else FLAT_ARCHITECTURE)
    expected = {
        "policy_id": V2_POLICY_ID if actual == CANDIDATE_ARCHITECTURE else POLICY_ID,
        "environment_version": ENVIRONMENT_VERSION,
        "observation_definition_version": OBSERVATION_VERSION,
        "max_vessels": env.max_vessels,
        "action_capacity": env.action_capacity,
        "time_scale_min": env.time_scale_min,
        "length_scale_m": env.length_scale_m,
    }
    errors = [f"{key}: checkpoint {metadata.get(key)!r} != environment {value!r}"
              for key, value in expected.items() if metadata.get(key) != value]
    if architecture != actual or (expected_architecture is not None and architecture != expected_architecture):
        errors.append("policy_architecture differs from model or requested architecture")
    if actual == CANDIDATE_ARCHITECTURE:
        saved = metadata.get("architecture_hyperparameters") or {}
        for key in ("vessel_embedding_dim", "context_dim", "scorer_layers", "value_layers"):
            if saved.get(key) != getattr(model.policy, key):
                if not (isinstance(getattr(model.policy, key), tuple) and
                        saved.get(key) == list(getattr(model.policy, key))):
                    errors.append(f"architecture_hyperparameters.{key} differs from model")
    if int(model.action_space.n) != env.action_capacity:
        errors.append("model action space differs from environment action capacity")
    if model.observation_space != env.observation_space:
        errors.append("model observation space differs from environment observation space")
    trained = metadata.get("dependency_versions", {})
    for package, version in (("stable_baselines3", stable_baselines3.__version__),
                             ("sb3_contrib", sb3_contrib.__version__)):
        if str(trained.get(package, "")).split(".")[0] != version.split(".")[0]:
            errors.append(f"{package} major version {trained.get(package)} != installed {version}")
    if errors:
        raise CheckpointCompatibilityError("Incompatible checkpoint: " + "; ".join(errors))


def masked_predict(model: MaskablePPO, observation: dict[str, Any], mask: np.ndarray) -> int:
    """Deterministic masked action as a plain int; raise if it is not allowed."""

    action, _ = model.predict(observation, action_masks=mask, deterministic=True)
    values = np.asarray(action)
    if values.size != 1 or not np.issubdtype(values.dtype, np.integer):
        raise MaskedActionError(f"Model returned a non-scalar or non-integer action {action!r}.")
    index = int(values.reshape(()))
    if not 0 <= index < mask.size or not mask[index]:
        raise MaskedActionError(f"Model selected masked action {index}.")
    return index


class MaskablePPOStaticPolicy:
    """StaticPolicy adapter: a learned heuristic, never a certified solver."""

    policy_family = "maskable_ppo"
    algorithm_version = "v1"

    def __init__(self, model: MaskablePPO, metadata: dict[str, Any]) -> None:
        expected = V2_POLICY_ID if isinstance(model.policy, CandidateScoringMaskablePolicy) else POLICY_ID
        if metadata.get("policy_id") != expected:
            raise CheckpointCompatibilityError(f"Checkpoint policy_id must be {expected}.")
        self.model = model
        self.metadata = dict(metadata)
        self.policy_id = expected
        self.algorithm_version = "v2" if expected == V2_POLICY_ID else "v1"

    @classmethod
    def load(cls, path: str | Path, device: str = "cpu") -> "MaskablePPOStaticPolicy":
        return cls(*load_checkpoint(path, device))

    def make_env(self, scenario: BAPScenarioInstance) -> StaticBAPEnv:
        return StaticBAPEnv(
            scenario=scenario,
            max_vessels=self.metadata["max_vessels"],
            time_scale_min=self.metadata["time_scale_min"],
            length_scale_m=self.metadata["length_scale_m"],
            policy_id=self.policy_id,
        )

    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        env = self.make_env(scenario)
        check_checkpoint_compatibility(self.metadata, self.model, env)
        observation, _ = env.reset()
        while not env.terminated:
            observation, *_ = env.step(masked_predict(self.model, observation, env.action_masks()))
        return StaticScheduleResult(self.policy_id, env.placements, env.decision_records)
