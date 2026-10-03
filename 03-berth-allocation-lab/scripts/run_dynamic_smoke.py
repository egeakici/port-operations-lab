"""Small, non-persistent Step 10 engineering smoke report."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from berth_allocation_lab.core import turnaround_time, waiting_time
from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.policies.dynamic_fcfs import run_online_fcfs
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for family in ("low", "medium", "heavy"):
        config = SyntheticScenarioConfig.load_yaml(root / "configs" / "scenarios" /
                                                   f"synthetic_{family}.yaml")
        if family == "low":
            config = replace(config.with_formulation("dynamic"),
                             future_horizon_min=240.0,
                             scenario_id="synthetic_low_dynamic")
        scenario = SyntheticScenarioGenerator().generate(config)
        for horizon in (0.0, 240.0):
            env = DynamicBAPEnv(scenario=scenario, max_vessels=scenario.vessel_count,
                                future_horizon_min=horizon)
            start = perf_counter()
            _, _, info = run_online_fcfs(env, seed=11)
            runtime = perf_counter() - start
            events, placements = env.event_records, env.placements
            _, _, replay_info = run_online_fcfs(env, seed=11)
            by_id = {v.vessel_id: v for v in scenario.vessels}
            waits = [waiting_time(by_id[p.vessel_id], p) for p in placements]
            turns = [turnaround_time(by_id[p.vessel_id], p) for p in placements]
            print(json.dumps({
                "family": family, "horizon_min": horizon,
                "vessel_count": scenario.vessel_count,
                "completed": info["vessel_count_completed"],
                "total_waiting_min": sum(waits),
                "mean_waiting_min": sum(waits) / len(waits),
                "mean_turnaround_min": sum(turns) / len(turns),
                "episode_duration_min": info["simulation_time_min"],
                "peak_waiting_queue": info["peak_waiting_queue"],
                "intentional_waits": sum(r["action_type"] == "WAIT" for r in env.decision_records),
                "forced_advances": info["forced_advances"],
                "horizon_entries": sum(r["event_type"] == "HORIZON_ENTRY" for r in events),
                "invalid_schedules": int(not info["schedule_valid"]),
                "runtime_seconds": runtime,
                "deterministic_replay": (events == env.event_records and
                                         placements == env.placements and
                                         info["scenario_fingerprint"] == replay_info["scenario_fingerprint"]),
            }, sort_keys=True))


if __name__ == "__main__":
    main()
