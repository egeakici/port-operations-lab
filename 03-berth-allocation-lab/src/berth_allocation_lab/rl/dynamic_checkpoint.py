"""Versioned dynamic checkpoint sidecars and strict compatibility checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sb3_contrib import MaskablePPO

from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.rl.dynamic_config import (
    ENVIRONMENT_VERSION, OBSERVATION_VERSION, POLICY_ARCHITECTURE, POLICY_ID,
    REWARD_SCALE,
)
from berth_allocation_lab.rl.dynamic_joint_scoring import DynamicJointMaskablePolicy
from berth_allocation_lab.rl.policy import CheckpointCompatibilityError, dependency_versions, metadata_path


def save_dynamic_checkpoint(model: MaskablePPO, path: Path, metadata: dict[str, Any]) -> None:
    if not isinstance(model.policy, DynamicJointMaskablePolicy):
        raise CheckpointCompatibilityError("Dynamic checkpoint requires joint-scoring policy.")
    model.save(path)
    record = {
        "model_metadata_version": 1, "policy_id": POLICY_ID,
        "policy_architecture": POLICY_ARCHITECTURE,
        "environment_version": ENVIRONMENT_VERSION,
        "observation_version": OBSERVATION_VERSION,
        "reward_scale": REWARD_SCALE, "algorithm": "MaskablePPO",
        "action_capacity": int(model.action_space.n),
        "candidate_capacity": 2 * int(metadata["max_vessels"]),
        "dependency_versions": dependency_versions(),
        "architecture_hyperparameters": {
            key: getattr(model.policy, key) for key in
            ("vessel_embedding_dim", "context_dim", "scorer_layers", "value_layers")},
        **metadata,
    }
    metadata_path(path).write_text(json.dumps(record, indent=2, default=list,
                                              sort_keys=True), encoding="utf-8")


def load_dynamic_checkpoint(path: str | Path, env: DynamicBAPEnv, *,
                            allow_cross_horizon: bool = False) -> tuple[MaskablePPO, dict[str, Any]]:
    path = Path(path)
    sidecar = metadata_path(path)
    if not path.is_file() or not sidecar.is_file():
        raise CheckpointCompatibilityError("Dynamic checkpoint or metadata sidecar is missing.")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    expected = {
        "policy_id": POLICY_ID, "policy_architecture": POLICY_ARCHITECTURE,
        "environment_version": ENVIRONMENT_VERSION, "observation_version": OBSERVATION_VERSION,
        "max_vessels": env.max_vessels, "action_capacity": env.action_space.n,
        "time_scale_min": env.time_scale_min, "length_scale_m": env.length_scale_m,
        "reward_scale": REWARD_SCALE,
    }
    errors = [f"{key}: {metadata.get(key)!r} != {value!r}"
              for key, value in expected.items() if metadata.get(key) != value]
    if not allow_cross_horizon and metadata.get("horizon_min") != env.future_horizon_min:
        errors.append("H differs; cross-horizon diagnostic must be explicit")
    if "candidate_capacity" in metadata and metadata["candidate_capacity"] != env.candidate_capacity:
        errors.append("candidate_capacity differs")
    if errors:
        raise CheckpointCompatibilityError("Incompatible dynamic checkpoint: " + "; ".join(errors))
    model = MaskablePPO.load(path, device="cpu")
    if not isinstance(model.policy, DynamicJointMaskablePolicy):
        raise CheckpointCompatibilityError("Checkpoint contains a static or unsupported policy.")
    if model.observation_space != env.observation_space or model.action_space != env.action_space:
        raise CheckpointCompatibilityError("Checkpoint Gymnasium spaces differ from DynamicBAPEnv.")
    saved_arch = metadata.get("architecture_hyperparameters", {})
    for key, value in saved_arch.items():
        actual = getattr(model.policy, key)
        comparable = list(actual) if isinstance(actual, tuple) else actual
        if comparable != value:
            raise CheckpointCompatibilityError(f"Architecture field {key} differs from model.")
    return model, metadata
