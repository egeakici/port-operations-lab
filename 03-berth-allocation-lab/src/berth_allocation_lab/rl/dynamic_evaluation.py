"""Paired online evaluation in raw vessel-minutes; no test access by default."""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
from sb3_contrib import MaskablePPO

from berth_allocation_lab.core import total_waiting_time, turnaround_time, waiting_time
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action
from berth_allocation_lab.policies.dynamic_online_rollout import (
    POLICY_ID as ROLLOUT_ID, online_rollout_choice,
)
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.rl.suites import ScenarioSuite, physical_fingerprint

FCFS_ID = "dynamic_online_fcfs_v1"


def run_dynamic_episode(scenario: BAPScenarioInstance, *, horizon_min: float,
                        max_vessels: int, method: str, model: MaskablePPO | None = None,
                        time_scale_min: float = 1440.0,
                        length_scale_m: float = 1000.0) -> dict[str, Any]:
    """Run one policy on one immutable instance; only the evaluator owns it."""
    env = DynamicBAPEnv(scenario=scenario, max_vessels=max_vessels,
                        future_horizon_min=horizon_min, time_scale_min=time_scale_min,
                        length_scale_m=length_scale_m)
    observation, _ = env.reset()
    started = time.perf_counter()
    inference_seconds = 0.0
    rollout_decision_seconds = []
    legal_waits = selected_waits = announced_waits = 0
    wait_costs = []
    legal_action_counts = []
    fcfs_agree = assignment_decisions = 0
    failure = None
    try:
        while not env.terminated and not env.truncated:
            visible = env.visible_state()
            mask = env.action_masks()
            legal_action_counts.append(int(mask.sum()))
            legal_waits += int(mask[0])
            fcfs = online_fcfs_action(env)
            start = time.perf_counter()
            if method == FCFS_ID:
                action = fcfs
            elif method == ROLLOUT_ID:
                choice = online_rollout_choice(visible)
                action = choice.action
                rollout_decision_seconds.append(choice.runtime_seconds)
            elif method == "dynamic_maskable_ppo_v1" and model is not None:
                action, _ = model.predict(observation, deterministic=True, action_masks=mask)
                action = int(action)
            else:
                raise ValueError(f"Unsupported dynamic method {method!r}.")
            inference_seconds += time.perf_counter() - start
            if not mask[action]:
                raise ValueError(f"Policy selected masked action {action}.")
            selected_waits += int(action == 0)
            if action == 0:
                announced_waits += int(any(s == "ANNOUNCED" for s in visible.statuses_by_slot))
            else:
                assignment_decisions += 1
                fcfs_agree += int(action == fcfs)
            observation, reward, _, _, _ = env.step(action)
            if action == 0:
                wait_costs.append(-reward)
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
    elapsed = time.perf_counter() - started
    complete = env.terminated and not env.truncated and failure is None
    result: dict[str, Any] = {
        "scenario_id": scenario.scenario_id,
        "scenario_seed": scenario.seed,
        "scenario_family": scenario.scenario_family,
        "physical_fingerprint": physical_fingerprint(scenario),
        "method": method, "horizon_min": horizon_min,
        "status": "completed_valid" if complete else
                  "invalid_transition" if failure else "truncated",
        "failure": failure, "schedule_valid": complete,
        "truncated": env.truncated,
        "vessel_count": scenario.vessel_count,
        "vessel_count_completed": sum(s == "COMPLETED" for s in env._status.values()),
        "episode_duration_min": env.current_time_min,
        "peak_waiting_queue": env._peak_queue,
        "assignments": len(env.placements),
        "intentional_waits": selected_waits, "legal_wait_opportunities": legal_waits,
        "wait_rate": selected_waits / legal_waits if legal_waits else None,
        "waits_with_announced_vessel": announced_waits,
        "waiting_after_wait_actions_min": wait_costs,
        "forced_advances": env._forced_advances,
        "horizon_entries": sum(r["event_type"] == "HORIZON_ENTRY" for r in env.event_records),
        "assignment_agreement_with_fcfs": (fcfs_agree / assignment_decisions
                                            if assignment_decisions else None),
        "runtime_seconds": elapsed, "inference_seconds": inference_seconds,
        "rollout_mean_decision_seconds": (statistics.fmean(rollout_decision_seconds)
                                          if rollout_decision_seconds else None),
        "decision_count": len(env.decision_records),
        "decision_history": list(env.decision_records),
        "event_records": list(env.event_records),
        "placements": [asdict(p) for p in env.placements],
        "mean_legal_actions": statistics.fmean(legal_action_counts) if legal_action_counts else None,
    }
    if not complete:
        result.update(total_waiting_time_min=None, mean_waiting_time_min=None,
                      p95_waiting_time_min=None, mean_turnaround_time_min=None,
                      p95_turnaround_time_min=None)
        return result
    by_id = {v.vessel_id: v for v in scenario.vessels}
    waits = [waiting_time(by_id[p.vessel_id], p) for p in env.placements]
    turns = [turnaround_time(by_id[p.vessel_id], p) for p in env.placements]
    total = total_waiting_time(scenario.vessels, env.placements)
    if not math.isclose(env.episode_return, -total, abs_tol=1e-9, rel_tol=0):
        raise ValueError("Dynamic reward does not match canonical total waiting.")
    result.update(total_waiting_time_min=total,
                  vessel_results=[{
                      "vessel_id": p.vessel_id,
                      "arrival_time_min": by_id[p.vessel_id].arrival_time_min,
                      "berth_start_time_min": p.berth_start_time_min,
                      "service_end_time_min": p.service_end_time_min,
                      "berth_position_m": p.berth_position_m,
                      "waiting_time_min": waiting_time(by_id[p.vessel_id], p),
                      "turnaround_time_min": turnaround_time(by_id[p.vessel_id], p),
                  } for p in env.placements],
                  mean_waiting_time_min=statistics.fmean(waits),
                  p95_waiting_time_min=float(np.percentile(waits, 95)),
                  mean_turnaround_time_min=statistics.fmean(turns),
                  p95_turnaround_time_min=float(np.percentile(turns, 95)))
    return result


def weighted_validation_mean(rows: list[dict[str, Any]], config: DynamicPPOConfig) -> float | None:
    if not rows or any(r["status"] != "completed_valid" for r in rows):
        return None
    weighted = 0.0
    total_weight = sum(c.weight for c in config.components)
    for component in config.components:
        prefix = f"{component.base_scenario_id}_validation_seed"
        values = [r["total_waiting_time_min"] for r in rows if r["scenario_id"].startswith(prefix)]
        if not values:
            return None
        weighted += component.weight / total_weight * statistics.fmean(values)
    return weighted


def evaluate_validation(suite: ScenarioSuite, config: DynamicPPOConfig,
                        method: str, model: MaskablePPO | None = None) -> dict[str, Any]:
    if suite.split != "validation":
        raise ValueError("Part A evaluation accepts validation suites only.")
    rows = [run_dynamic_episode(s, horizon_min=config.horizon_min,
                                max_vessels=config.max_vessels, method=method, model=model)
            for s in suite.scenarios]
    return {"method": method, "weighted_mean_total_waiting_min": weighted_validation_mean(rows, config),
            "rows": rows, "valid_count": sum(r["schedule_valid"] for r in rows),
            "truncated_count": sum(r["truncated"] for r in rows)}


def cached_validation_reference(suite: ScenarioSuite, config: DynamicPPOConfig,
                                method: str, cache_path: Path) -> dict[str, Any]:
    """Cache by physical instance, horizon and policy version, never by ID only."""
    if method not in {FCFS_ID, ROLLOUT_ID}:
        raise ValueError("Only deterministic online references are cacheable.")
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    rows, hits = [], 0
    for scenario in suite.scenarios:
        key = f"{physical_fingerprint(scenario)}:{config.horizon_min}:{method}"
        if key in cache:
            hits += 1
        else:
            cache[key] = run_dynamic_episode(scenario, horizon_min=config.horizon_min,
                                             max_vessels=config.max_vessels, method=method)
        rows.append(cache[key])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, cache_path)
    return {"method": method, "weighted_mean_total_waiting_min": weighted_validation_mean(rows, config),
            "rows": rows, "cache_hits": hits, "cache_misses": len(rows) - hits}


def paired_delta(ppo: float | None, reference: float | None) -> float | None:
    return None if ppo is None or reference is None else ppo - reference


def percentage_improvement(ppo: float | None, reference: float | None) -> float | None:
    return None if ppo is None or reference is None or reference <= 0 else 100 * (reference - ppo) / reference
