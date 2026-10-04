"""Scenario-paired, family-stratified summaries in raw vessel-minutes."""

from __future__ import annotations

import statistics
from collections.abc import Mapping

import numpy as np

from berth_allocation_lab.benchmark.config import BenchmarkError

TIE_TOLERANCE = 1e-6
TRAINING_SEEDS = (11, 23, 37)


def classify(delta: float) -> str:
    if abs(delta) <= TIE_TOLERANCE:
        return "tie"
    return "win" if delta < 0 else "loss"


def improvement_percent(candidate: float, reference: float) -> float | None:
    return None if reference <= 0 else 100.0 * (reference - candidate) / reference


def gap_closed(ppo: float, fcfs: float, rollout: float) -> float | None:
    return None if fcfs <= rollout else (fcfs - ppo) / (fcfs - rollout)


def weighted_mean(values: Mapping[str, list[float]], weights: Mapping[str, float]) -> float:
    if set(values) != set(weights) or any(not rows for rows in values.values()):
        raise BenchmarkError("Every frozen family must have at least one scenario.")
    return sum(weights[family] * statistics.fmean(rows)
               for family, rows in values.items())


def paired_summary(deltas: list[float]) -> dict[str, float | int]:
    if not deltas:
        raise BenchmarkError("Paired comparison has no scenarios.")
    verdicts = [classify(value) for value in deltas]
    return {"n_physical_scenarios": len(deltas),
            "wins": verdicts.count("win"), "ties": verdicts.count("tie"),
            "losses": verdicts.count("loss"),
            "win_fraction": verdicts.count("win") / len(deltas),
            "mean_delta_min": statistics.fmean(deltas),
            "median_delta_min": statistics.median(deltas)}


def scenario_seed_means(by_seed: Mapping[int, Mapping[str, float]]) -> dict[str, float]:
    if set(by_seed) != set(TRAINING_SEEDS):
        raise BenchmarkError("Exactly training seeds 11, 23 and 37 are required.")
    scenarios = set(by_seed[TRAINING_SEEDS[0]])
    if not scenarios or any(set(by_seed[seed]) != scenarios for seed in TRAINING_SEEDS):
        raise BenchmarkError("Three seeds must cover identical physical scenarios.")
    return {scenario: statistics.fmean(by_seed[seed][scenario] for seed in TRAINING_SEEDS)
            for scenario in sorted(scenarios)}


def paired_bootstrap(
    deltas_by_family: Mapping[str, list[float]],
    weights: Mapping[str, float],
    *,
    resamples: int = 10_000,
    confidence_level: float = 0.95,
    seed: int = 12012,
) -> dict[str, float | int]:
    """Resample physical scenario identities, preserving paired deltas and strata."""
    point = weighted_mean(deltas_by_family, weights)
    if resamples <= 0 or not 0 < confidence_level < 1:
        raise BenchmarkError("Invalid bootstrap request.")
    rng = np.random.default_rng(seed)
    samples = np.zeros(resamples, dtype=np.float64)
    for family in sorted(weights):
        deltas = np.asarray(deltas_by_family[family], dtype=np.float64)
        if not np.isfinite(deltas).all():
            raise BenchmarkError("Bootstrap requires finite paired differences.")
        indices = rng.integers(0, len(deltas), size=(resamples, len(deltas)))
        samples += weights[family] * deltas[indices].mean(axis=1)
    alpha = (1 - confidence_level) / 2
    lower, upper = np.quantile(samples, [alpha, 1 - alpha])
    return {"estimate_min": point, "ci_lower_min": float(lower),
            "ci_upper_min": float(upper),
            "n_physical_scenarios": sum(map(len, deltas_by_family.values())),
            "bootstrap_seed": seed, "resamples": resamples,
            "confidence_level": confidence_level}


def verify_replay(locked: Mapping[str, float], replayed: Mapping[str, float],
                  *, device: str, dependencies: Mapping[str, str]) -> None:
    """Fail closed on a deterministic replay mismatch; never alter locked values."""
    if set(locked) != set(replayed):
        raise BenchmarkError("Replay scenario/method keys differ from locked evidence.")
    for key in sorted(locked):
        difference = abs(locked[key] - replayed[key])
        if not np.isfinite(difference) or difference > TIE_TOLERANCE:
            raise BenchmarkError(
                f"Replay mismatch {key}: locked={locked[key]!r}, replayed={replayed[key]!r}, "
                f"absolute_difference={difference!r}, device={device}, "
                f"dependencies={dict(dependencies)!r}")
