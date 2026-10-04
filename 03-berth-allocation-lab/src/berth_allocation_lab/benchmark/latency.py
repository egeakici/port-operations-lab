"""Bounded CPU policy-decision timing on predeclared validation fixtures."""

from __future__ import annotations

import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.inputs import load_all
from berth_allocation_lab.core import find_schedule_violations, total_waiting_time
from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action
from berth_allocation_lab.policies.dynamic_online_rollout import online_rollout_choice
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.rl.dynamic_suites import dynamic_suites
from berth_allocation_lab.rl.suites import physical_fingerprint


def fixture_plan(config: BenchmarkConfig, per_family: int = 2) -> list[dict[str, Any]]:
    """Choose lexicographically first validation identities, before timing."""
    if per_family < 1:
        raise BenchmarkError("At least one fixture per family is required.")
    plan = []
    for source in config.sources:
        frozen = DynamicPPOConfig.load_yaml(config.resolve(source.config_path))
        suite = dynamic_suites(frozen)["validation"]
        for family in config.families[source.regime]:
            choices = sorted((s for s in suite.scenarios
                              if s.scenario_id.startswith(family + "_validation_seed")),
                             key=lambda s: s.scenario_id)
            if len(choices) < per_family:
                raise BenchmarkError(f"Not enough validation fixtures: {family}")
            plan.extend({"regime": source.regime, "family": family,
                         "scenario_id": s.scenario_id,
                         "physical_fingerprint": physical_fingerprint(s),
                         "training_seed": 11, "policy_horizon_min": 240}
                        for s in choices[:per_family])
    return plan


def hardware_metadata() -> dict[str, Any]:
    import stable_baselines3
    import sb3_contrib
    import torch

    return {"os": platform.platform(), "processor": platform.processor(),
            "python": sys.version, "numpy": np.__version__,
            "torch": torch.__version__, "stable_baselines3": stable_baselines3.__version__,
            "sb3_contrib": sb3_contrib.__version__, "device": "cpu",
            "torch_num_threads": torch.get_num_threads(),
            "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
            "mkl_num_threads": os.environ.get("MKL_NUM_THREADS"),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS")}


def measure_latency(config: BenchmarkConfig, *, per_family: int = 2,
                    passes: int = 3) -> dict[str, Any]:
    """Warm up once; time identical fixtures/methods without loading in the timer."""
    if passes < 1:
        raise BenchmarkError("Timed passes must be positive.")
    import torch
    from berth_allocation_lab.rl.dynamic_checkpoint import load_dynamic_checkpoint

    torch.set_num_threads(1)
    datasets, _ = load_all(config)
    plan = fixture_plan(config, per_family)
    scenarios, models, load_seconds = {}, {}, {}
    for dataset in datasets:
        source = dataset.source
        frozen = DynamicPPOConfig.load_yaml(config.resolve(source.config_path))
        validation = dynamic_suites(frozen)["validation"]
        selected = {entry["scenario_id"] for entry in plan if entry["regime"] == source.regime}
        scenarios.update({(source.regime, s.scenario_id): s for s in validation.scenarios
                          if s.scenario_id in selected})
        checkpoint = next(Path(entry["checkpoint_path"]) for entry in dataset.inventory
                          if entry["training_seed"] == 11)
        sample = scenarios[(source.regime, sorted(selected)[0])]
        env = DynamicBAPEnv(scenario=sample, max_vessels=frozen.max_vessels,
                            future_horizon_min=240)
        env.reset()
        start = time.perf_counter()
        model, _ = load_dynamic_checkpoint(checkpoint, env)
        load_seconds[source.regime] = time.perf_counter() - start
        models[source.regime] = (model, frozen)
    measurements, decision_samples, signatures = [], [], {}
    for timed_pass in range(-1, passes):
        for item in plan:
            regime, sid = item["regime"], item["scenario_id"]
            scenario = scenarios[(regime, sid)]
            model, frozen = models[regime]
            for method in ("fcfs", "rollout", "ppo"):
                env = DynamicBAPEnv(scenario=scenario, max_vessels=frozen.max_vessels,
                                    future_horizon_min=240)
                obs, _ = env.reset()
                decision_times, step_times, legal_counts = [], [], []
                started = time.perf_counter()
                while not env.terminated and not env.truncated:
                    mask = env.action_masks()
                    legal_counts.append(int(mask.sum()))
                    before = time.perf_counter_ns()
                    if method == "fcfs":
                        action = online_fcfs_action(env)
                    elif method == "rollout":
                        choice = online_rollout_choice(env.visible_state())
                        action = choice.action
                        legal_counts[-1] = len(choice.scores)
                    else:
                        action, _ = model.predict(obs, deterministic=True, action_masks=mask)
                        action = int(action)
                    decision_times.append((time.perf_counter_ns() - before) / 1e6)
                    if not mask[action]:
                        raise BenchmarkError(f"Timed policy chose illegal action: {method}/{sid}")
                    before = time.perf_counter_ns()
                    obs, _, _, _, _ = env.step(action)
                    step_times.append((time.perf_counter_ns() - before) / 1e6)
                episode_ms = (time.perf_counter() - started) * 1000
                violations = find_schedule_violations(
                    scenario.vessels, env.placements, scenario.berth_length_m,
                    scenario.min_clearance_m)
                if env.truncated or violations or len(env.placements) != scenario.vessel_count:
                    raise BenchmarkError(f"Timed schedule invalid: {method}/{sid}")
                signature = tuple((p.vessel_id, p.berth_position_m, p.berth_start_time_min)
                                  for p in env.placements)
                key = method, regime, sid
                if key in signatures and signatures[key] != signature:
                    raise BenchmarkError(f"Latency instrumentation changed schedule: {key}")
                signatures[key] = signature
                if timed_pass >= 0:
                    decision_samples.extend({**item, "method": method, "pass": timed_pass + 1,
                                             "decision_index": index,
                                             "decision_latency_ms": value,
                                             "env_step_latency_ms": step_times[index],
                                             "legal_actions_evaluated": legal_counts[index]}
                                            for index, value in enumerate(decision_times))
                    measurements.append({**item, "method": method, "pass": timed_pass + 1,
                                         "decision_count": len(decision_times),
                                         "mean_decision_ms": statistics.fmean(decision_times),
                                         "median_decision_ms": statistics.median(decision_times),
                                         "p95_decision_ms": float(np.percentile(decision_times, 95)),
                                         "max_decision_ms": max(decision_times),
                                         "total_decision_ms": sum(decision_times),
                                         "total_env_step_ms": sum(step_times),
                                         "episode_wall_ms": episode_ms,
                                         "mean_legal_actions_evaluated": statistics.fmean(legal_counts),
                                         "total_waiting_min": total_waiting_time(
                                             scenario.vessels, env.placements),
                                         "schedule_valid": True})
    summary = []
    for method in ("fcfs", "rollout", "ppo"):
        for regime in sorted({item["regime"] for item in plan}):
            subset = [r for r in measurements if r["method"] == method and
                      r["regime"] == regime]
            samples = [r["decision_latency_ms"] for r in decision_samples
                       if r["method"] == method and r["regime"] == regime]
            total_decisions = sum(r["decision_count"] for r in subset)
            summary.append({"method": method, "regime": regime,
                            "fixture_count": sum(item["regime"] == regime for item in plan),
                            "timed_passes": passes, "decision_count": total_decisions,
                            "weighted_mean_decision_ms": sum(r["mean_decision_ms"] *
                                                             r["decision_count"] for r in subset) /
                            total_decisions,
                            "median_decision_ms": statistics.median(samples),
                            "p95_decision_ms": float(np.percentile(samples, 95)),
                            "max_decision_ms": max(samples),
                            "total_policy_ms": sum(r["total_decision_ms"] for r in subset),
                            "total_env_step_ms": sum(r["total_env_step_ms"] for r in subset),
                            "total_episode_wall_ms": sum(r["episode_wall_ms"] for r in subset)})
    return {"manifest": {"status": "completed", "purpose": "engineering_decision_latency",
                         "fixture_rule": ("first two lexicographic validation IDs per family"
                                          if per_family == 2 else
                                          f"first {per_family} lexicographic validation IDs per family"),
                         "warmup_passes": 1, "timed_passes": passes,
                         "training_seed": 11, "horizon_min": 240,
                         "hardware": hardware_metadata(),
                         "checkpoint_load_seconds": load_seconds,
                         "cpu_cuda_action_parity": "not_verified"},
            "fixture_plan": plan, "measurements": measurements,
            "decision_samples": decision_samples, "summary": summary}
