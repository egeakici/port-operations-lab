from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from mini_port_sim.experiments import run_scenario_experiment
from mini_port_sim.metrics import metrics_summary, save_metrics_json
from mini_port_sim.scenario import ScenarioConfig
from mini_port_sim.visualization import (
    build_vessel_timeline,
    save_berth_timeline_png,
    save_crane_timeline_png,
    save_replay_json,
    save_timeline_json,
    save_vessel_timeline_png,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mini-port-sim",
        description="Run a MiniPortSim scenario and write result artifacts.",
    )
    parser.add_argument(
        "--scenario",
        required=True,
        help="Path to a scenario JSON file.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Optional seed override.",
    )
    parser.add_argument(
        "--output",
        default="results",
        help="Output directory for result artifacts.",
    )
    parser.add_argument(
        "--start-time",
        default="2026-08-20T08:00:00",
        help="ISO simulation start datetime.",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Also write simple PNG timelines if matplotlib is installed.",
    )
    args = parser.parse_args(argv)

    scenario = ScenarioConfig.load_json(args.scenario)
    if args.seed is not None:
        scenario = replace(scenario, seed=args.seed)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = run_scenario_experiment(
        scenario,
        start_time=datetime.fromisoformat(args.start_time),
    )
    vessel_timeline = build_vessel_timeline(result.simulation)

    summary = metrics_summary(result.metrics)
    _save_json(summary, output_dir / "summary.json")
    save_metrics_json(result.metrics, output_dir / "metrics.json")
    save_replay_json(result.replay_frames, output_dir / "replay.json")
    save_timeline_json(
        berth_segments=result.berth_timeline,
        vessel_segments=vessel_timeline,
        crane_segments=result.crane_timeline,
        file_path=output_dir / "timeline.json",
    )

    if args.png:
        save_berth_timeline_png(
            result.berth_timeline,
            output_dir / "berth_timeline.png",
        )
        save_vessel_timeline_png(
            vessel_timeline,
            output_dir / "vessel_timeline.png",
        )
        save_crane_timeline_png(
            result.crane_timeline,
            output_dir / "crane_timeline.png",
        )

    print(json.dumps(summary, indent=2))

    return 0


def _save_json(data, file_path: Path) -> None:
    with file_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
