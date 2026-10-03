"""Bounded Step 11 reference-cost probe; reads Step 10 smoke fixtures only."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from berth_allocation_lab.policies.dynamic_online_rollout import POLICY_ID
from berth_allocation_lab.rl.dynamic_evaluation import run_dynamic_episode
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for family in ("tiny_congested", "medium", "heavy"):
        cfg = SyntheticScenarioConfig.load_yaml(root / "configs" / "scenarios" /
                                                f"synthetic_{family}.yaml")
        if cfg.formulation == "static":
            cfg = replace(cfg.with_formulation("dynamic"), future_horizon_min=240.0,
                          scenario_id="rollout_cost_tiny")
        instance = SyntheticScenarioGenerator().generate(cfg)
        result = run_dynamic_episode(instance, horizon_min=240.0,
                                     max_vessels=instance.vessel_count, method=POLICY_ID)
        print(json.dumps({k: result[k] for k in (
            "scenario_family", "vessel_count", "status", "decision_count",
            "mean_legal_actions", "rollout_mean_decision_seconds",
            "runtime_seconds", "total_waiting_time_min")}, sort_keys=True))


if __name__ == "__main__":
    main()
