"""Frozen Project 03 Dynamic Maskable PPO checkpoints: inventory, gates G01-G04/G18/G21, read-only loading.

The six checkpoints (two regimes x training seeds 11/23/37) are inventoried individually. A
checkpoint is never averaged, merged, re-saved, fine-tuned or moved to CUDA. Loading uses the
unchanged Project 03 ``load_dynamic_checkpoint`` (``allow_cross_horizon=False``) with a
``DynamicBAPEnv`` built on the scenario's berth projection as a compatibility host only (G04).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.audit import P03_ROOT

CHECKPOINT_ROOT = P03_ROOT / "experiments" / "rl" / "dynamic_extended_cuda"
DECISION_FILE = CHECKPOINT_ROOT / "validation_decision.json"
DECISION_FILE_SHA256 = "f2f912346e4a9260bf7752874fa1343fea63e0b7f2594f8083bf05c60c3e3423"
TRAINING_SEEDS = (11, 23, 37)
REGIME_EXPERIMENT = {"medium_heavy": "dynamic_ppo_medium_heavy_v1_extended_cuda",
                     "tiny": "dynamic_ppo_tiny_v1_extended_cuda"}
REGIME_MAX_VESSELS = {"medium_heavy": 24, "tiny": 8}
# repository_capability_audit.md section 5.2 (Step 1 audit table).
AUDITED_SHA256 = {
    ("tiny", 11): "35a1a0ba0b8d231fb26b2aa2ecfebad49e9b3ab9a949c2ea306054dbe1a7f46d",
    ("tiny", 23): "4773a36832f02179e27bd00e4308829ae9a4eb00612ad8528b6975b88628c874",
    ("tiny", 37): "7a3138ce37f3ef18c7c1b74df7e20f7a977f552a2e69e21dea828c79a9cd956a",
    ("medium_heavy", 11): "3373e06060a6f14cae422d7041d863cf18001bed285d1b896bffbe4dfae32018",
    ("medium_heavy", 23): "a2a105108d9b030cec8e26538012cbe1c2c2bc872f992e1a11ac0cd428ffd625",
    ("medium_heavy", 37): "8318b49712fbbd04c6adbf1b357e2c5916fae539306b50272ded7464d002a3a6",
}
INFERENCE_CONFIG = {"device": "cpu", "deterministic": True, "torch_num_threads": 1,
                    "predict_call": "model.predict(obs, deterministic=True, action_masks=mask)",
                    "loader": "berth_allocation_lab.rl.dynamic_checkpoint.load_dynamic_checkpoint",
                    "allow_cross_horizon": False}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CheckpointRef:
    regime: str
    training_seed: int

    @property
    def experiment_id(self) -> str:
        return REGIME_EXPERIMENT[self.regime]

    @property
    def directory(self) -> Path:
        return CHECKPOINT_ROOT / self.experiment_id / f"seed_{self.training_seed}"

    @property
    def model_path(self) -> Path:
        return self.directory / "best_validation_model.zip"

    @property
    def metadata_path(self) -> Path:
        return self.directory / "best_validation_model.metadata.json"

    @property
    def max_vessels(self) -> int:
        return REGIME_MAX_VESSELS[self.regime]

    @property
    def audited_sha256(self) -> str:
        return AUDITED_SHA256[(self.regime, self.training_seed)]


def all_checkpoints() -> tuple[CheckpointRef, ...]:
    return tuple(CheckpointRef(regime, seed) for regime in ("medium_heavy", "tiny") for seed in TRAINING_SEEDS)


def _decision_entry(decision: dict[str, Any], ref: CheckpointRef) -> dict[str, Any] | None:
    regime = decision.get("regimes", {}).get(ref.regime, {})
    return next((s for s in regime.get("seeds", ()) if s.get("training_seed") == ref.training_seed), None)


def static_checkpoint_gates(ref: CheckpointRef) -> dict[str, Any]:
    """G01-G03 and the sidecar part of G04/G06 (no model load)."""
    gates: dict[str, dict[str, Any]] = {}
    exists = ref.model_path.is_file() and ref.metadata_path.is_file()
    gates["G01"] = {"pass": exists, "detail": str(ref.model_path)}
    sha = file_sha256(ref.model_path) if ref.model_path.is_file() else None
    decision_sha = file_sha256(DECISION_FILE) if DECISION_FILE.is_file() else None
    sidecar = DECISION_FILE.with_name(DECISION_FILE.name + ".sha256")
    sidecar_sha = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.is_file() else None
    entry = None
    if decision_sha is not None:
        entry = _decision_entry(json.loads(DECISION_FILE.read_text(encoding="utf-8")), ref)
    g02 = (sha == ref.audited_sha256 and decision_sha == DECISION_FILE_SHA256 and sidecar_sha == decision_sha
           and entry is not None and entry.get("checkpoint_sha256") == sha)
    gates["G02"] = {"pass": g02, "sha256": sha, "audited_sha256": ref.audited_sha256,
                    "decision_file_sha256": decision_sha, "decision_sidecar_sha256": sidecar_sha,
                    "decision_entry_sha256": None if entry is None else entry.get("checkpoint_sha256")}
    metadata = json.loads(ref.metadata_path.read_text(encoding="utf-8")) if exists else {}
    gates["G03"] = {"pass": metadata.get("training_seed") == ref.training_seed
                    and ref.experiment_id in str(ref.directory),
                    "sidecar_training_seed": metadata.get("training_seed"), "experiment_id": ref.experiment_id}
    expected = {"policy_id": "dynamic_maskable_ppo_v1", "policy_architecture": "dynamic_joint_action_scoring_v1",
                "environment_version": "dynamic_bap_env_v1", "observation_version": "dynamic_obs_v1",
                "max_vessels": ref.max_vessels, "action_capacity": 1 + ref.max_vessels * 2 * ref.max_vessels,
                "candidate_capacity": 2 * ref.max_vessels, "horizon_min": 240,
                "time_scale_min": 1440.0, "length_scale_m": 1000.0}
    mismatches = {k: [metadata.get(k), v] for k, v in expected.items() if metadata.get(k) != v}
    gates["G04_sidecar"] = {"pass": not mismatches, "mismatches": mismatches}
    gates["G06"] = {"pass": metadata.get("time_scale_min") == 1440.0 and metadata.get("length_scale_m") == 1000.0}
    return {"regime": ref.regime, "training_seed": ref.training_seed, "path": str(ref.model_path),
            "sha256": sha, "metadata": {k: metadata.get(k) for k in sorted(set(expected) | {
                "training_seed", "checkpoint_kind", "timesteps", "git_commit_hash", "dependency_versions",
                "device_actual"})},
            "gates": gates, "pass": all(g["pass"] for g in gates.values())}


class LoadedCheckpoint:
    """A frozen checkpoint loaded once, read-only, on CPU, for deterministic inference."""

    def __init__(self, ref: CheckpointRef, model, metadata: dict[str, Any], sha256: str,
                 load_seconds: float, torch_threads: int) -> None:
        self.ref = ref
        self.model = model
        self.metadata = metadata
        self.sha256 = sha256
        self.load_seconds = load_seconds
        self.torch_threads = torch_threads

    def predict(self, observation, mask) -> int:
        action, _ = self.model.predict(observation, deterministic=True, action_masks=mask)
        return int(action)


_CACHE: dict[CheckpointRef, LoadedCheckpoint] = {}


def load_checkpoint(ref: CheckpointRef, host_projection) -> LoadedCheckpoint:
    """G01-G04 then Project 03 ``load_dynamic_checkpoint`` on a ``DynamicBAPEnv`` host (cached per process)."""
    if ref in _CACHE:
        cached = _CACHE[ref]
        verify_host_spaces(cached, host_projection)
        return cached
    import torch
    from berth_allocation_lab.envs import DynamicBAPEnv
    from berth_allocation_lab.rl.dynamic_checkpoint import load_dynamic_checkpoint

    static = static_checkpoint_gates(ref)
    if not static["pass"]:
        failed = [g for g, r in static["gates"].items() if not r["pass"]]
        raise CheckpointGateError(failed[0], f"{ref}: static gates failed: {failed}")
    torch.set_num_threads(INFERENCE_CONFIG["torch_num_threads"])
    env = DynamicBAPEnv(scenario=host_projection, max_vessels=ref.max_vessels,
                        future_horizon_min=host_projection.future_horizon_min)
    env.reset()
    started = time.perf_counter()
    model, metadata = load_dynamic_checkpoint(ref.model_path, env, allow_cross_horizon=False)
    load_seconds = time.perf_counter() - started
    sha_after = file_sha256(ref.model_path)
    if sha_after != ref.audited_sha256:
        raise CheckpointGateError("G21", f"{ref.model_path} changed while loading")
    loaded = LoadedCheckpoint(ref, model, metadata, sha_after, load_seconds, torch.get_num_threads())
    _CACHE[ref] = loaded
    return loaded


def verify_host_spaces(loaded: LoadedCheckpoint, host_projection) -> None:
    from berth_allocation_lab.envs import DynamicBAPEnv

    env = DynamicBAPEnv(scenario=host_projection, max_vessels=loaded.ref.max_vessels,
                        future_horizon_min=host_projection.future_horizon_min)
    env.reset()
    if loaded.model.observation_space != env.observation_space or loaded.model.action_space != env.action_space:
        raise CheckpointGateError("G04", "checkpoint spaces differ from the DynamicBAPEnv host")


class CheckpointGateError(RuntimeError):
    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"{gate}: {message}")
        self.gate = gate


def verify_all_hashes() -> dict[str, Any]:
    """G21: re-hash the six checkpoints and the decision file (read-only)."""
    rows = []
    for ref in all_checkpoints():
        sha = file_sha256(ref.model_path) if ref.model_path.is_file() else None
        rows.append({"regime": ref.regime, "training_seed": ref.training_seed, "sha256": sha,
                     "expected": ref.audited_sha256, "ok": sha == ref.audited_sha256})
    decision_sha = file_sha256(DECISION_FILE) if DECISION_FILE.is_file() else None
    return {"checkpoints": rows, "decision_file_sha256": decision_sha,
            "decision_file_ok": decision_sha == DECISION_FILE_SHA256,
            "ok": all(r["ok"] for r in rows) and decision_sha == DECISION_FILE_SHA256}


__all__ = ["AUDITED_SHA256", "CHECKPOINT_ROOT", "CheckpointGateError", "CheckpointRef", "DECISION_FILE",
           "INFERENCE_CONFIG", "LoadedCheckpoint", "TRAINING_SEEDS", "all_checkpoints", "file_sha256",
           "load_checkpoint", "static_checkpoint_gates", "verify_all_hashes"]
