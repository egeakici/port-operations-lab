"""Reproducible Maskable PPO training on StaticBAPEnv (Step 9).

One run = one experiment config + one training seed, written to
``<output>/<experiment_id>/seed_<training_seed>/``; an existing run directory
is never overwritten. Validation (deterministic, masked, raw vessel-minutes)
runs at timestep 0, every ``eval_freq`` timesteps and after the final update;
the best checkpoint is chosen by mean validation waiting only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
import uuid
from dataclasses import asdict
from functools import partial
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecEnv

from berth_allocation_lab.envs import MIXTURE_SELECTION_VERSION, MixtureScenarioProvider, StaticBAPEnv
from berth_allocation_lab.policies import StaticFCFS, StaticGreedyRollout
from berth_allocation_lab.rl.candidate_scoring import CandidateScoringMaskablePolicy
from berth_allocation_lab.rl.config import CANDIDATE_ARCHITECTURE, SELECTION_METRIC, StaticPPOExperimentConfig
from berth_allocation_lab.rl.evaluation import is_improvement, validation_waiting
from berth_allocation_lab.rl.progress import progress_bar
from berth_allocation_lab.rl.policy import (
    MaskablePPOStaticPolicy,
    build_model_metadata,
    dependency_versions,
    hardware_metadata,
    save_checkpoint,
)
from berth_allocation_lab.rl.suites import (
    ScenarioSuite,
    SplitLeakageError,
    audit_fresh_suites,
    audit_split_isolation,
    build_config_suites,
    build_mixture,
    historical_fixture_fingerprints,
    previously_examined_fingerprints,
)
from berth_allocation_lab.rl.wrappers import TrainingRewardScale
from berth_allocation_lab.tracking.git_metadata import get_git_metadata


TRAINING_MANIFEST_VERSION = 1
SELECTION_RULE = ("lowest mean validation total waiting (raw minutes) over all scenarios, "
                  "evaluated at timestep 0, every eval_freq timesteps and after the final update; "
                  "ties within 1e-9 keep the earliest timestep; evaluations with any invalid "
                  "schedule are never selected")
TRAIN_LOG_FIELDS = (
    "timesteps", "episodes", "mean_episode_raw_return", "mean_episode_total_waiting_min",
    "policy_gradient_loss", "value_loss", "entropy_loss", "approx_kl", "clip_fraction",
    "clip_range", "explained_variance", "loss", "learning_rate", "n_updates",
)
EPISODE_FIELDS = (
    "timesteps", "env_index", "scenario_id", "scenario_seed", "scenario_family", "scenario_split",
    "vessel_count", "scenario_fingerprint", "physical_fingerprint", "episode_return",
    "total_waiting_time_min",
)


def run_directory(config: StaticPPOExperimentConfig, training_seed: int,
                  output_root: str | Path | None = None) -> Path:
    root = Path(output_root) if output_root is not None else config.resolve(config.output_dir)
    return root / config.experiment_id / f"seed_{training_seed}"


def environment_seeds(training_seed: int, n_envs: int) -> list[int]:
    """Seeds of the training sub-environments.

    One environment keeps the pilot derivation (the training seed itself);
    with several, sub-environment i uses ``training_seed * 1000 + i`` so that
    streams of different training seeds never coincide.
    """

    return [training_seed] if n_envs == 1 else [training_seed * 1000 + i for i in range(n_envs)]


def _make_training_env(mixture: MixtureScenarioProvider, max_vessels: int, time_scale_min: float,
                       length_scale_m: float, policy_id: str, reward_scale: float) -> Monitor:
    env = StaticBAPEnv(scenario_provider=mixture, max_vessels=max_vessels, time_scale_min=time_scale_min,
                       length_scale_m=length_scale_m, policy_id=policy_id)
    return Monitor(TrainingRewardScale(env, reward_scale))


def _training_vec_env(config: StaticPPOExperimentConfig, mixture: MixtureScenarioProvider) -> VecEnv:
    factory = partial(_make_training_env, mixture, config.max_vessels, config.time_scale_min,
                      config.length_scale_m, config.policy_id, config.reward_scale)
    factories = [factory] * config.ppo.n_envs
    # SubprocVecEnv requires the caller's ``if __name__ == "__main__"`` guard on Windows.
    return SubprocVecEnv(factories) if config.ppo.vec_env == "subproc" else DummyVecEnv(factories)


def cached_baseline_means(suite: ScenarioSuite, cache_path: Path, *,
                          progress: bool = False) -> dict[str, Any]:
    """FCFS/Rollout validation means, computed once per scenario fingerprint.

    The JSON cache lives in the experiment directory and is shared by every
    training seed of the experiment; entries are deterministic objectives.
    """

    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    hits = misses = 0
    means = {}
    for name, policy in (("fcfs", StaticFCFS()), ("rollout", StaticGreedyRollout())):
        values = []
        with progress_bar(enabled=progress, total=len(suite.scenarios),
                          description=f"{suite.name} {name.upper()} references") as bar:
            for scenario in suite.scenarios:
                key = f"{policy.policy_id}:{scenario.content_fingerprint}"
                if key in cache:
                    hits += 1
                else:
                    misses += 1
                    single = ScenarioSuite(suite.name, suite.split, (scenario,))
                    cache[key] = validation_waiting(policy, single)["per_scenario"][0]["total_waiting_time_min"]
                values.append(cache[key])
                if bar is not None:
                    bar.set_postfix(cache_hits=hits, cache_misses=misses, refresh=False)
                    bar.update(1)
        means[f"{name}_mean_total_waiting_time_min"] = (
            statistics.fmean(values) if values and None not in values else None)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, cache_path)
    return {**means, "cache_hits": hits, "cache_misses": misses}


class _StaticPPOMonitor(BaseCallback):
    """Validation, best-checkpoint saving and raw-unit training logs."""

    def __init__(self, *, policy_factory: Callable[[], MaskablePPOStaticPolicy],
                 validation_suite: ScenarioSuite, eval_freq: int,
                 save_best: Callable[[dict[str, Any]], None],
                 progress=None, baseline_means: dict[str, Any] | None = None) -> None:
        super().__init__(verbose=0)
        self.policy_factory = policy_factory
        self.validation_suite = validation_suite
        self.eval_freq = eval_freq
        self.save_best = save_best
        self.next_eval = eval_freq
        self.history: list[dict[str, Any]] = []
        self.best: dict[str, Any] | None = None
        self.train_rows: list[dict[str, Any]] = []
        self.episode_rows: list[dict[str, Any]] = []
        self.validation_seconds = 0.0
        self.failure: tuple[str, str] | None = None
        self._last_updates = None
        self._logged_episodes = 0
        self.progress = progress
        self.baseline_means = baseline_means or {}
        self._progress_started = 0.0
        self._progress_refreshed = 0.0

    def _evaluate(self) -> None:
        started = time.perf_counter()
        result = validation_waiting(self.policy_factory(), self.validation_suite)
        seconds = time.perf_counter() - started
        self.validation_seconds += seconds
        entry = {"timesteps": self.num_timesteps, "suite": self.validation_suite.name,
                 "suite_split": self.validation_suite.split, "evaluation_seconds": seconds, **result}
        self.history.append(entry)
        if is_improvement(entry["mean_total_waiting_time_min"],
                          None if self.best is None else self.best["mean_total_waiting_time_min"]):
            self.best = entry
            self.save_best(entry)
        if self.progress is not None:
            self._update_progress(force=True)
            self.progress.write(
                f"{self.progress.desc}: timestep={self.num_timesteps} "
                f"validation={self._minutes(entry['mean_total_waiting_time_min'])} min "
                f"best={self._minutes(None if self.best is None else self.best['mean_total_waiting_time_min'])} min "
                f"FCFS={self._minutes(self.baseline_means.get('fcfs_mean_total_waiting_time_min'))} min "
                f"Rollout={self._minutes(self.baseline_means.get('rollout_mean_total_waiting_time_min'))} min",
                file=sys.stderr,
            )

    @staticmethod
    def _minutes(value) -> str:
        return "n/a" if value is None else f"{value:.1f}"

    def _update_progress(self, *, force: bool = False) -> None:
        bar = self.progress
        now = time.perf_counter()
        if force or now - self._progress_refreshed >= bar.mininterval:
            learning_seconds = now - self._progress_started - self.validation_seconds
            speed = self.num_timesteps / learning_seconds if learning_seconds > 0 else 0.0
            latest = self.history[-1]["mean_total_waiting_time_min"] if self.history else None
            best = self.best["mean_total_waiting_time_min"] if self.best else None
            bar.set_postfix({
                "learning steps/s": f"{speed:.0f}", "validation min": self._minutes(latest),
                "best min": self._minutes(best),
                "FCFS min": self._minutes(self.baseline_means.get("fcfs_mean_total_waiting_time_min")),
                "Rollout min": self._minutes(self.baseline_means.get("rollout_mean_total_waiting_time_min")),
            }, refresh=False)
            self._progress_refreshed = now
        # PPO may finish a rollout beyond the requested budget. Only the display
        # is capped; actual timesteps and all existing records are unchanged.
        bar.update(max(0, min(self.num_timesteps, bar.total) - bar.n))
        if force:
            bar.refresh()

    def _harvest_train_metrics(self) -> None:
        values = {k.split("/", 1)[1]: v for k, v in self.logger.name_to_value.items()
                  if k.startswith("train/")}
        if not values or values.get("n_updates") == self._last_updates:
            return
        self._last_updates = values.get("n_updates")
        episodes = self.episode_rows[self._logged_episodes:]
        self._logged_episodes = len(self.episode_rows)
        row = {
            "timesteps": self.num_timesteps,
            "episodes": len(self.episode_rows),
            "mean_episode_raw_return": _mean(e["episode_return"] for e in episodes),
            "mean_episode_total_waiting_min": _mean(e["total_waiting_time_min"] for e in episodes),
            **{k: v for k, v in values.items() if k in TRAIN_LOG_FIELDS},
        }
        self.train_rows.append(row)
        bad = [k for k, v in values.items() if isinstance(v, float) and not math.isfinite(v)]
        if bad and self.failure is None:
            self.failure = ("nonfinite_loss", f"Non-finite PPO statistics: {', '.join(sorted(bad))}.")

    def _on_training_start(self) -> None:
        if self.progress is not None:
            self._progress_started = time.perf_counter()
        self._evaluate()

    def _on_rollout_start(self) -> None:
        self._harvest_train_metrics()
        if self.failure is None and self.num_timesteps >= self.next_eval:
            self._evaluate()
            self.next_eval = (self.num_timesteps // self.eval_freq + 1) * self.eval_freq

    def _on_step(self) -> bool:
        for env_index, (info, done) in enumerate(zip(self.locals["infos"], self.locals["dones"])):
            if done:
                self.episode_rows.append({"timesteps": self.num_timesteps, "env_index": env_index,
                                          **{k: info.get(k) for k in EPISODE_FIELDS[2:]}})
        if self.progress is not None:
            self._update_progress()
        return self.failure is None

    def _on_training_end(self) -> None:
        self._harvest_train_metrics()
        if self.failure is None and (not self.history or self.history[-1]["timesteps"] != self.num_timesteps):
            self._evaluate()


def train_static_ppo(
    config: StaticPPOExperimentConfig,
    training_seed: int,
    *,
    output_root: str | Path | None = None,
    total_timesteps: int | None = None,
    eval_freq: int | None = None,
    device: str | None = None,
    progress: bool = False,
    progress_description: str | None = None,
) -> dict[str, Any]:
    """Train one seed and return its manifest; failures are recorded, not hidden.

    Classified failures (non-finite losses, split leakage, no valid validation
    checkpoint) return a manifest with ``status="failed"``. Exceptions and
    interrupts are written to the manifest and then re-raised.
    """

    if isinstance(training_seed, bool) or not isinstance(training_seed, int) or training_seed < 0:
        raise ValueError("training_seed must be a non-negative integer.")
    total = config.training.total_timesteps if total_timesteps is None else total_timesteps
    frequency = config.training.eval_freq if eval_freq is None else eval_freq
    for name, value in (("total_timesteps", total), ("eval_freq", frequency)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")
    run_dir = run_directory(config, training_seed, output_root)
    if run_dir.exists():
        raise FileExistsError(f"Run directory {run_dir} exists; refusing to overwrite it.")
    run_dir.mkdir(parents=True)

    root = config.project_root()
    overrides = {k: v for k, v in (("total_timesteps", total_timesteps), ("eval_freq", eval_freq),
                                   ("device", device), ("output_root", output_root)) if v is not None}
    plain_config = json.loads(json.dumps(config.to_dict(), default=str))
    (run_dir / "config.yaml").write_text(
        yaml.safe_dump({"config": plain_config, "overrides": json.loads(json.dumps(overrides, default=str))},
                       sort_keys=False), encoding="utf-8")
    git_commit, git_dirty = get_git_metadata()
    run_id = f"{config.experiment_id}__seed_{training_seed}__{uuid.uuid4().hex[:8]}"
    manifest: dict[str, Any] = {
        "training_manifest_version": TRAINING_MANIFEST_VERSION,
        "training_run_id": run_id,
        "experiment_id": config.experiment_id,
        "experiment_version": config.experiment_version,
        "policy_id": config.policy_id,
        "policy_architecture": config.policy_architecture,
        "architecture_hyperparameters": asdict(config.architecture) if config.policy_architecture == CANDIDATE_ARCHITECTURE else {"net_arch": config.ppo.policy_kwargs()["net_arch"]},
        "policy_family": "maskable_ppo",
        "algorithm": "MaskablePPO",
        "algorithm_version": "v2" if config.policy_architecture == CANDIDATE_ARCHITECTURE else "v1",
        "formulation": "static",
        "training_seed": training_seed,
        "action_masking_enabled": True,
        "training_reward_scale": config.reward_scale,
        "total_timesteps_requested": total,
        "eval_freq": frequency,
        "hyperparameters": asdict(config.ppo),
        "policy_kwargs": config.policy_kwargs(),
        "config_source": _relative(config.source_path, root),
        "config_sha256": config.source_sha256,
        "overrides": json.loads(json.dumps(overrides, default=str)),
        "git_commit_hash": git_commit,
        "git_dirty": git_dirty,
        "dependency_versions": dependency_versions(),
        "hardware": hardware_metadata(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "started",
        "failure_type": None,
        "failure_message": None,
    }
    started = time.perf_counter()
    learn_seconds: float | None = None
    monitor: _StaticPPOMonitor | None = None
    model: MaskablePPO | None = None
    vec_env: VecEnv | None = None
    try:
        train_mixture = build_mixture(config.components, "train", root, config.max_vessels)
        suites = build_config_suites(config)  # test/diagnostics: identities audited, never evaluated here
        validation_suite, test_suite = suites["validation"], suites["test"]
        historical = historical_fixture_fingerprints(root)
        audit_split_isolation({name: suite.identities() for name, suite in suites.items()}, historical)
        if config.prior_configs:
            manifest["freshness_audit"] = audit_fresh_suites(
                suites.values(), previously_examined_fingerprints(config))
        manifest["training_scenario_set"] = {
            "split": "train", "partition_rule": "seed % 3 == 0",
            "mixture_selection_version": MIXTURE_SELECTION_VERSION,
            "components": [_component_record(c, config, root) for c in config.components],
        }
        manifest["validation_scenario_set"] = validation_suite.identities()
        manifest["test_scenario_set_identities"] = test_suite.identities()
        manifest["diagnostic_scenario_set_identities"] = {
            spec.name: suites[spec.name].identities() for spec in config.diagnostics}
        manifest["seed_exclusive_suites"] = config.seed_exclusive_suites
        manifest["validation_baselines"] = cached_baseline_means(
            validation_suite, run_dir.parent / "validation_baseline_cache.json", progress=progress)

        ppo = config.ppo
        vec_env = _training_vec_env(config, train_mixture)
        model = MaskablePPO(
            CandidateScoringMaskablePolicy if config.policy_architecture == CANDIDATE_ARCHITECTURE else ppo.policy,
            vec_env,
            gamma=ppo.gamma, learning_rate=ppo.learning_rate, n_steps=ppo.n_steps,
            batch_size=ppo.batch_size, n_epochs=ppo.n_epochs, gae_lambda=ppo.gae_lambda,
            clip_range=ppo.clip_range, ent_coef=ppo.ent_coef, vf_coef=ppo.vf_coef,
            max_grad_norm=ppo.max_grad_norm, policy_kwargs=config.policy_kwargs(),
            seed=training_seed, device=device or ppo.device, verbose=0,
        )
        if ppo.n_envs > 1:
            vec_env.seed(training_seed * 1000)  # sub-environment i: training_seed * 1000 + i
        manifest["device"] = str(model.device)
        manifest["n_envs"] = ppo.n_envs
        manifest["vec_env"] = ppo.vec_env
        manifest["environment_seeds"] = environment_seeds(training_seed, ppo.n_envs)
        base_metadata = {
            "experiment_id": config.experiment_id, "training_run_id": run_id,
            "training_seed": training_seed, "max_vessels": config.max_vessels,
            "time_scale_min": config.time_scale_min, "length_scale_m": config.length_scale_m,
            "reward_scale": config.reward_scale, "policy": ppo.policy,
            "net_arch": ppo.policy_kwargs()["net_arch"], "gamma": ppo.gamma,
            "policy_id": config.policy_id,
            "git_commit_hash": git_commit, "git_dirty": git_dirty,
        }

        def save_best(entry: dict[str, Any]) -> None:
            save_checkpoint(model, run_dir / "best_validation_model.zip", {
                **base_metadata, "checkpoint_kind": "best_validation", "timesteps": entry["timesteps"],
                "model_id": f"{run_id}/best_validation@{entry['timesteps']}",
                "validation_mean_total_waiting_time_min": entry["mean_total_waiting_time_min"],
            })

        with progress_bar(enabled=progress, total=total, unit="step",
                          description=progress_description or
                          f"{config.experiment_id} seed {training_seed} (1/1)") as bar:
            monitor = _StaticPPOMonitor(
                policy_factory=lambda: MaskablePPOStaticPolicy(model, build_model_metadata(model, base_metadata)),
                validation_suite=validation_suite, eval_freq=frequency, save_best=save_best,
                progress=bar, baseline_means=manifest["validation_baselines"],
            )
            learn_started = time.perf_counter()
            model.learn(total_timesteps=total, callback=monitor, log_interval=None, use_masking=True)
            learn_seconds = time.perf_counter() - learn_started
        save_checkpoint(model, run_dir / "final_model.zip", {
            **base_metadata, "checkpoint_kind": "final", "timesteps": model.num_timesteps,
            "model_id": f"{run_id}/final@{model.num_timesteps}",
        })
        manifest["total_timesteps_completed"] = model.num_timesteps
        manifest["checkpoints"] = {"final": {"path": "final_model.zip",
                                             "model_id": f"{run_id}/final@{model.num_timesteps}"}}
        if monitor.best is not None:
            manifest["checkpoints"]["best_validation"] = {
                "path": "best_validation_model.zip",
                "model_id": f"{run_id}/best_validation@{monitor.best['timesteps']}"}
        manifest["selection"] = {
            "metric": SELECTION_METRIC, "rule": SELECTION_RULE,
            "selected_timesteps": None if monitor.best is None else monitor.best["timesteps"],
            "selected_mean_total_waiting_time_min": (
                None if monitor.best is None else monitor.best["mean_total_waiting_time_min"]),
        }
        manifest["split_audit"] = audit_split_isolation({
            "train_episodes": monitor.episode_rows,
            **{name: suite.identities() for name, suite in suites.items()}}, historical)
        manifest["training_episodes_per_env"] = {
            str(i): sum(e["env_index"] == i for e in monitor.episode_rows) for i in range(ppo.n_envs)}
        manifest["training_episodes"] = len(monitor.episode_rows)
        manifest["distinct_training_scenarios"] = len({e["scenario_id"] for e in monitor.episode_rows})
        if monitor.failure is not None:
            manifest["failure_type"], manifest["failure_message"] = monitor.failure
            manifest["status"] = "failed"
        elif monitor.best is None:
            manifest.update(status="failed", failure_type="no_valid_validation_checkpoint",
                            failure_message="No validation evaluation produced valid schedules.")
        else:
            manifest["status"] = "completed"
    except SplitLeakageError as error:
        manifest.update(status="failed", failure_type="split_leakage", failure_message=str(error))
    except KeyboardInterrupt:
        manifest.update(status="interrupted", failure_type="interrupted",
                        failure_message="Training interrupted; no final model was declared.")
        if model is not None:
            model.save(run_dir / "interrupted_model.zip")
        raise
    except Exception as error:
        manifest.update(status="failed", failure_type=type(error).__name__, failure_message=str(error))
        raise
    finally:
        if vec_env is not None:
            vec_env.close()
        wall = time.perf_counter() - started
        validation_seconds = monitor.validation_seconds if monitor is not None else 0.0
        # learning = model.learn() wall time minus in-training validation;
        # setup (suites, audits, validation baselines) is reported separately.
        learning = None if learn_seconds is None else learn_seconds - validation_seconds
        manifest.update(
            ended_at=datetime.now(timezone.utc).isoformat(),
            training_runtime_seconds=wall,
            validation_runtime_seconds=validation_seconds,
            learning_runtime_seconds=learning,
            setup_and_audit_runtime_seconds=None if learn_seconds is None else wall - learn_seconds,
        )
        completed = manifest.get("total_timesteps_completed")
        manifest["learning_steps_per_second"] = (
            completed / learning if completed and learning and learning > 0 else None)
        if monitor is not None:
            _write_csv(run_dir / "training_log.csv", TRAIN_LOG_FIELDS, monitor.train_rows)
            _write_csv(run_dir / "train_episodes.csv", EPISODE_FIELDS, monitor.episode_rows)
            (run_dir / "validation_metrics.json").write_text(json.dumps({
                "selection_metric": SELECTION_METRIC, "selection_rule": SELECTION_RULE,
                "best_timesteps": None if monitor.best is None else monitor.best["timesteps"],
                "history": monitor.history}, indent=2), encoding="utf-8")
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


def _component_record(component, config: StaticPPOExperimentConfig, root: Path) -> dict[str, Any]:
    synthetic = component.synthetic_config(root)
    return {**asdict(component), "scenario_family": synthetic.scenario_family,
            "resolved_vessel_count": synthetic.traffic.vessel_count,
            "source_sha256": _sha256(config.resolve(component.source_config))}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: str | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
