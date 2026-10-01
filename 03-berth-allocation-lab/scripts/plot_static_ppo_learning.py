"""Plot validation waiting against training timesteps for Static Maskable PPO runs.

Example:
    python scripts/plot_static_ppo_learning.py \
        --experiment-dir experiments/rl/static_ppo/static_ppo_tiny_v1 --output curves.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"{args.output} exists; refusing to overwrite.")

    figure, axis = plt.subplots(figsize=(7, 4))
    baselines = {}
    for run in sorted(p for p in args.experiment_dir.glob("seed_*") if p.is_dir()):
        history = json.loads((run / "validation_metrics.json").read_text(encoding="utf-8"))["history"]
        points = [(h["timesteps"], h["mean_total_waiting_time_min"]) for h in history
                  if h["mean_total_waiting_time_min"] is not None]
        axis.plot(*zip(*points), marker="o", label=f"PPO {run.name}")
        baselines = json.loads((run / "manifest.json").read_text(encoding="utf-8"))["validation_baselines"]
    for name, key, style in (("FCFS", "fcfs_mean_total_waiting_time_min", "--"),
                             ("Greedy Rollout", "rollout_mean_total_waiting_time_min", ":")):
        if baselines.get(key) is not None:
            axis.axhline(baselines[key], linestyle=style, color="black", label=f"{name} (validation)")
    axis.set_xlabel("training timesteps")
    axis.set_ylabel("mean validation total waiting [vessel-min]")
    axis.set_title(args.experiment_dir.name)
    axis.legend()
    figure.tight_layout()
    figure.savefig(args.output, dpi=120)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
