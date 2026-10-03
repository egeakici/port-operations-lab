"""Validation-only checkpoint selection for real online MaskablePPO."""

from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

import torch
import yaml
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.rl.dynamic_checkpoint import save_dynamic_checkpoint
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig, POLICY_ID
from berth_allocation_lab.rl.dynamic_evaluation import (
    FCFS_ID, ROLLOUT_ID, cached_validation_reference, evaluate_validation,
)
from berth_allocation_lab.rl.dynamic_joint_scoring import DynamicJointMaskablePolicy
from berth_allocation_lab.rl.dynamic_suites import (
    audit_dynamic_suites, dynamic_mixture, dynamic_suites,
)
from berth_allocation_lab.rl.dynamic_wrappers import DynamicTrainingRewardScale
from berth_allocation_lab.rl.policy import dependency_versions, hardware_metadata
from berth_allocation_lab.rl.progress import progress_bar
from berth_allocation_lab.tracking.git_metadata import get_git_metadata


def dynamic_run_directory(config: DynamicPPOConfig, training_seed: int,
                          output_root: str | Path | None = None) -> Path:
    root = Path(output_root) if output_root is not None else config.resolve(config.output_dir)
    return root / config.experiment_id / f"seed_{training_seed}"


def _make_env(mixture, max_vessels, horizon_min, time_scale, length_scale):
    env = DynamicBAPEnv(scenario_provider=mixture, max_vessels=max_vessels,
                        future_horizon_min=horizon_min,
                        time_scale_min=time_scale, length_scale_m=length_scale)
    return Monitor(DynamicTrainingRewardScale(env))


class _ValidationMonitor(BaseCallback):
    def __init__(self, *, config: DynamicPPOConfig, suite, eval_freq: int,
                 run_dir: Path, checkpoint_metadata: dict[str, Any], progress=None) -> None:
        super().__init__(verbose=0)
        self.config = config
        self.suite = suite
        self.eval_freq = eval_freq
        self.run_dir = run_dir
        self.checkpoint_metadata = checkpoint_metadata
        self.progress = progress
        self.history: list[dict[str, Any]] = []
        self.best: dict[str, Any] | None = None
        self.episodes: list[dict[str, Any]] = []
        self.training_log: list[dict[str, Any]] = []
        self.wait_opportunities = 0
        self.wait_selections = 0
        self.validation_seconds = 0.0
        self.started = 0.0
        self.next_eval = eval_freq

    def _validate(self) -> None:
        started = time.perf_counter()
        result = evaluate_validation(self.suite, self.config, POLICY_ID, self.model)
        elapsed = time.perf_counter() - started
        self.validation_seconds += elapsed
        row = {"timesteps": self.num_timesteps,
               "weighted_mean_total_waiting_min": result["weighted_mean_total_waiting_min"],
               "valid_count": result["valid_count"],
               "truncated_count": result["truncated_count"],
               "validation_seconds": elapsed,
               "wait_opportunities": sum(r["legal_wait_opportunities"] for r in result["rows"]),
               "wait_selections": sum(r["intentional_waits"] for r in result["rows"]),
               "mean_episode_reward_scaled": (
                   statistics.fmean(e["scaled_episode_reward"] for e in self.episodes[-100:]
                                    if e["scaled_episode_reward"] is not None)
                   if any(e["scaled_episode_reward"] is not None for e in self.episodes[-100:])
                   else None),
               "rows": result["rows"]}
        self.history.append(row)
        value = row["weighted_mean_total_waiting_min"]
        if value is not None and (self.best is None or value < self.best["weighted_mean_total_waiting_min"] - 1e-9):
            self.best = row
            save_dynamic_checkpoint(self.model, self.run_dir / "best_validation_model.zip",
                                    {**self.checkpoint_metadata, "checkpoint_kind": "best_validation",
                                     "timesteps": self.num_timesteps,
                                     "validation_waiting_min": value})
        if self.progress is not None:
            self.progress.write(
                f"{self.progress.desc}: timestep={self.num_timesteps} "
                f"validation={value if value is not None else 'invalid'} "
                f"best={None if self.best is None else self.best['weighted_mean_total_waiting_min']}")

    def _on_training_start(self) -> None:
        self.started = time.perf_counter()
        self._validate()

    def _on_rollout_start(self) -> None:
        metrics = {k.split("/", 1)[1]: v for k, v in self.logger.name_to_value.items()
                   if k.startswith("train/")}
        if metrics:
            self.training_log.append({"timesteps": self.num_timesteps,
                                      "episodes": len(self.episodes),
                                      "mean_episode_reward_scaled": (
                                          statistics.fmean(e["scaled_episode_reward"]
                                                           for e in self.episodes[-100:]
                                                           if e["scaled_episode_reward"] is not None)
                                          if any(e["scaled_episode_reward"] is not None
                                                 for e in self.episodes[-100:]) else None),
                                      "wait_opportunities": self.wait_opportunities,
                                      "wait_selections": self.wait_selections,
                                      **{k: float(v) if hasattr(v, "item") else v
                                         for k, v in metrics.items()}})
        if self.num_timesteps >= self.next_eval:
            self._validate()
            self.next_eval = (self.num_timesteps // self.eval_freq + 1) * self.eval_freq

    def _on_step(self) -> bool:
        masks = self.locals.get("action_masks")
        actions = self.locals.get("actions")
        if masks is not None and actions is not None:
            self.wait_opportunities += sum(bool(mask[0]) for mask in masks)
            self.wait_selections += sum(int(action) == 0 for action in actions)
        for env_index, (info, done) in enumerate(zip(self.locals["infos"], self.locals["dones"])):
            if done:
                self.episodes.append({"timesteps": self.num_timesteps, "env_index": env_index,
                                      "status": "completed_valid" if info.get("schedule_valid") else "truncated",
                                      "scenario_id": info.get("scenario_id"),
                                      "scenario_seed": info.get("scenario_seed"),
                                      "scenario_fingerprint": info.get("scenario_fingerprint"),
                                      "physical_fingerprint": info.get("physical_fingerprint"),
                                      "total_waiting_time_min": info.get("total_waiting_time_min"),
                                      "scaled_episode_reward": (info.get("episode") or {}).get("r")})
        if self.progress is not None:
            self.progress.update(max(0, min(self.num_timesteps, self.progress.total) - self.progress.n))
        return True

    def _on_training_end(self) -> None:
        metrics = {k.split("/", 1)[1]: v for k, v in self.logger.name_to_value.items()
                   if k.startswith("train/")}
        if metrics and (not self.training_log or self.training_log[-1]["timesteps"] != self.num_timesteps):
            self.training_log.append({"timesteps": self.num_timesteps,
                                      "episodes": len(self.episodes),
                                      "mean_episode_reward_scaled": (
                                          statistics.fmean(e["scaled_episode_reward"]
                                                           for e in self.episodes[-100:]
                                                           if e["scaled_episode_reward"] is not None)
                                          if any(e["scaled_episode_reward"] is not None
                                                 for e in self.episodes[-100:]) else None),
                                      "wait_opportunities": self.wait_opportunities,
                                      "wait_selections": self.wait_selections,
                                      **{k: float(v) if hasattr(v, "item") else v
                                         for k, v in metrics.items()}})
        if not self.history or self.history[-1]["timesteps"] != self.num_timesteps:
            self._validate()


def train_dynamic_ppo(config: DynamicPPOConfig, training_seed: int, *,
                      output_root: str | Path | None = None,
                      total_timesteps: int | None = None, eval_freq: int | None = None,
                      progress: bool = False) -> dict[str, Any]:
    config.validate()
    if training_seed not in config.training.training_seeds:
        raise ValueError("Training seed is not in the frozen seed set.")
    if config.ppo.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested, but PyTorch does not detect an available CUDA device.")
    total = total_timesteps or config.training.total_timesteps
    frequency = eval_freq or config.training.eval_freq
    if total <= 0 or frequency <= 0:
        raise ValueError("Training budget and evaluation frequency must be positive.")
    run_dir = dynamic_run_directory(config, training_seed, output_root)
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite {run_dir}.")
    run_dir.mkdir(parents=True)
    (run_dir / "config.yaml").write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
    commit, dirty = get_git_metadata()
    started = time.perf_counter()
    manifest: dict[str, Any] = {
        "run_id": f"{config.experiment_id}__seed_{training_seed}__{uuid.uuid4().hex[:8]}",
        "experiment_id": config.experiment_id, "regime": config.regime,
        "policy_id": POLICY_ID, "policy_architecture": config.policy_architecture,
        "observation_version": config.observation_version,
        "environment_version": config.environment_version,
        "formulation": "dynamic", "status": "started", "training_seed": training_seed,
        "horizon_min": config.horizon_min, "max_vessels": config.max_vessels,
        "action_capacity": 1 + 2 * config.max_vessels**2,
        "candidate_capacity": 2 * config.max_vessels,
        "reward_scale": config.reward_scale, "hyperparameters": asdict(config.ppo),
        "device_requested": config.ppo.device,
        "total_timesteps_requested": total, "eval_freq": frequency,
        "git_commit_hash": commit, "git_dirty": dirty,
        "config_sha256": config.source_sha256,
        "dependency_versions": dependency_versions(), "hardware": hardware_metadata(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    vec_env = None
    monitor = None
    learning_seconds = None
    try:
        suites = dynamic_suites(config)
        manifest["suite_audit"] = audit_dynamic_suites(config, suites)
        manifest["validation_scenario_set"] = suites["validation"].identities()
        manifest["test_scenario_set_identities_only"] = suites["test"].identities()
        manifest["diagnostic_scenario_set_identities_only"] = {
            name: suite.identities() for name, suite in suites.items()
            if name not in {"validation", "test"}}
        mixture = dynamic_mixture(config, "train")
        manifest["training_scenario_set"] = {
            "split": "train", "seed_rule": "seed % 3 == 0",
            "components": [asdict(c) for c in config.components],
            "environment_seeds": ([training_seed] if config.ppo.n_envs == 1 else
                                  [training_seed * 1000 + i for i in range(config.ppo.n_envs)]),
        }
        cache = run_dir.parent / "validation_reference_cache.json"
        references = {method: cached_validation_reference(suites["validation"], config, method, cache)
                      for method in (FCFS_ID, ROLLOUT_ID)}
        manifest["validation_references"] = {
            method: {key: value for key, value in result.items() if key != "rows"}
            for method, result in references.items()}
        for method, result in references.items():
            if result["weighted_mean_total_waiting_min"] is None:
                raise ValueError(f"{method} validation reference contains invalid episodes.")
        factory = partial(_make_env, mixture, config.max_vessels, config.horizon_min,
                          config.time_scale_min, config.length_scale_m)
        vec_env = DummyVecEnv([factory for _ in range(config.ppo.n_envs)])
        ppo = config.ppo
        torch.set_num_threads(1)
        model = MaskablePPO(
            DynamicJointMaskablePolicy, vec_env, gamma=ppo.gamma,
            learning_rate=ppo.learning_rate, n_steps=ppo.n_steps,
            batch_size=ppo.batch_size, n_epochs=ppo.n_epochs,
            gae_lambda=ppo.gae_lambda, clip_range=ppo.clip_range,
            ent_coef=ppo.ent_coef, vf_coef=ppo.vf_coef,
            max_grad_norm=ppo.max_grad_norm, seed=training_seed,
            device=ppo.device, verbose=0)
        manifest["device_actual"] = str(model.device)
        if model.device.type != ppo.device:
            raise RuntimeError(f"Requested {ppo.device}, but model is on {model.device}.")
        vec_env.seed(training_seed if config.ppo.n_envs == 1 else training_seed * 1000)
        checkpoint_metadata = {
            "training_seed": training_seed, "max_vessels": config.max_vessels,
            "time_scale_min": config.time_scale_min,
            "length_scale_m": config.length_scale_m,
            "horizon_min": config.horizon_min, "config_sha256": config.source_sha256,
            "git_commit_hash": commit, "git_dirty": dirty,
            "hyperparameters": asdict(config.ppo),
            "device_requested": ppo.device, "device_actual": str(model.device),
        }
        with progress_bar(enabled=progress, total=total, unit="step",
                          description=f"{config.experiment_id} seed {training_seed}") as bar:
            monitor = _ValidationMonitor(config=config, suite=suites["validation"],
                                         eval_freq=frequency, run_dir=run_dir,
                                         checkpoint_metadata=checkpoint_metadata, progress=bar)
            learn_start = time.perf_counter()
            model.learn(total_timesteps=total, callback=monitor, use_masking=True,
                        log_interval=None)
            learning_seconds = time.perf_counter() - learn_start - monitor.validation_seconds
        save_dynamic_checkpoint(model, run_dir / "final_model.zip",
                                {**checkpoint_metadata, "checkpoint_kind": "final",
                                 "timesteps": model.num_timesteps})
        manifest["total_timesteps_completed"] = model.num_timesteps
        manifest["checkpoints"] = {
            "final": "final_model.zip",
            "best_validation": "best_validation_model.zip" if monitor.best else None}
        manifest["selection"] = {
            "metric": "weighted_mean_validation_total_waiting_min",
            "rule": "lowest raw weighted family mean; ties keep earliest checkpoint",
            "selected_timesteps": monitor.best["timesteps"] if monitor.best else None,
            "selected_mean_total_waiting_min": (
                monitor.best["weighted_mean_total_waiting_min"] if monitor.best else None),
        }
        manifest["status"] = "completed" if monitor.best else "failed"
        manifest["failure_type"] = None if monitor.best else "no_valid_validation_checkpoint"
        manifest["training_episodes"] = len(monitor.episodes)
        manifest["training_wait_opportunities"] = monitor.wait_opportunities
        manifest["training_wait_selections"] = monitor.wait_selections
        (run_dir / "validation_metrics.json").write_text(
            json.dumps({"history": monitor.history}, indent=2), encoding="utf-8")
        (run_dir / "train_episodes.json").write_text(json.dumps(monitor.episodes, indent=2), encoding="utf-8")
        (run_dir / "training_log.json").write_text(json.dumps(monitor.training_log, indent=2),
                                                   encoding="utf-8")
    except KeyboardInterrupt:
        manifest.update(status="interrupted", failure_type="interrupted")
        raise
    except Exception as error:
        manifest.update(status="failed", failure_type=type(error).__name__,
                        failure_message=str(error))
        raise
    finally:
        if vec_env is not None:
            vec_env.close()
        manifest.update(ended_at=datetime.now(timezone.utc).isoformat(),
                        training_runtime_seconds=time.perf_counter() - started,
                        validation_runtime_seconds=(monitor.validation_seconds if monitor else 0.0),
                        learning_runtime_seconds=learning_seconds,
                        learning_steps_per_second=(
                            manifest.get("total_timesteps_completed", 0) / learning_seconds
                            if learning_seconds and learning_seconds > 0 else None))
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str),
                                               encoding="utf-8")
    return manifest
