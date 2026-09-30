"""Multi-seed FCFS dominance is an implementation invariant, not a benchmark."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from statistics import mean

import pytest

from berth_allocation_lab.core import NUMERICAL_TOLERANCE
from berth_allocation_lab.evaluation import compare_static_baselines
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.slow
@pytest.mark.parametrize("family", ["low", "medium", "heavy"])
def test_rollout_dominates_fcfs_on_twenty_seeds(family: str) -> None:
    config = SyntheticScenarioConfig.load_yaml(
        PROJECT_ROOT / "configs" / "scenarios" / f"synthetic_{family}.yaml"
    ).with_formulation("static")
    generator = SyntheticScenarioGenerator()
    fcfs_waits: list[float] = []
    rollout_waits: list[float] = []
    fcfs_runtimes: list[float] = []
    rollout_runtimes: list[float] = []
    lower = equal = higher = 0

    for seed in range(20):
        scenario = generator.generate(replace(config, seed=seed))
        fcfs, rollout = compare_static_baselines(scenario)
        assert fcfs.summary.is_valid and rollout.summary.is_valid
        assert fcfs.scenario is rollout.scenario is scenario
        fcfs_wait = fcfs.summary.total_waiting_time_min
        rollout_wait = rollout.summary.total_waiting_time_min
        assert fcfs_wait is not None and rollout_wait is not None
        assert rollout_wait <= fcfs_wait + NUMERICAL_TOLERANCE, (
            f"{family} seed {seed}: rollout {rollout_wait} > FCFS {fcfs_wait}"
        )
        if rollout_wait < fcfs_wait - NUMERICAL_TOLERANCE:
            lower += 1
        elif rollout_wait > fcfs_wait + NUMERICAL_TOLERANCE:
            higher += 1
        else:
            equal += 1
        fcfs_waits.append(fcfs_wait)
        rollout_waits.append(rollout_wait)
        fcfs_runtimes.append(fcfs.summary.algorithm_runtime_seconds)
        rollout_runtimes.append(rollout.summary.algorithm_runtime_seconds)

    assert lower + equal + higher == 20
    assert higher == 0
    print(
        "SANITY / INVARIANT CHECK "
        f"{family}: mean_fcfs_wait={mean(fcfs_waits):.4f} "
        f"mean_rollout_wait={mean(rollout_waits):.4f} "
        f"rollout_lt={lower} eq={equal} gt={higher} "
        f"mean_fcfs_runtime_s={mean(fcfs_runtimes):.4f} "
        f"mean_rollout_runtime_s={mean(rollout_runtimes):.4f}"
    )
