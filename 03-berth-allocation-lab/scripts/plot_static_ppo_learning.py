"""Plot training reward and validation waiting for Static Maskable PPO runs.

Example:
    python scripts/plot_static_ppo_learning.py \
        --experiment-dir experiments/rl/static_ppo/static_ppo_tiny_v1 --output curves.png
"""

from __future__ import annotations

import argparse
import csv
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
    runs = sorted(p for p in args.experiment_dir.glob("seed_*") if p.is_dir())
    if not runs:
        parser.error(f"No seed_* runs below {args.experiment_dir}.")

    figure, (train_axis, validation_axis) = plt.subplots(1, 2, figsize=(12, 4.5))
    baselines = {}
    for run in runs:  # every seed is drawn, including weak or failed runs
        rows = list(csv.DictReader((run / "training_log.csv").open(encoding="utf-8")))
        points = [(int(r["timesteps"]), float(r["mean_episode_raw_return"])) for r in rows
                  if r["mean_episode_raw_return"]]
        if points:
            train_axis.plot(*zip(*points), label=run.name)
        history = json.loads((run / "validation_metrics.json").read_text(encoding="utf-8"))["history"]
        valid = [(h["timesteps"], h["mean_total_waiting_time_min"]) for h in history
                 if h["mean_total_waiting_time_min"] is not None]
        if valid:
            validation_axis.plot(*zip(*valid), marker="o", markersize=3, label=run.name)
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        baselines = manifest.get("validation_baselines") or baselines
    for name, key, style in (("FCFS", "fcfs_mean_total_waiting_time_min", "--"),
                             ("Greedy Rollout", "rollout_mean_total_waiting_time_min", ":")):
        if baselines.get(key) is not None:
            validation_axis.axhline(baselines[key], linestyle=style, color="black", label=f"{name} (validation)")
    train_axis.set_title("Training reward (raw, unscaled; training scenarios)")
    train_axis.set_xlabel("training timesteps")
    train_axis.set_ylabel("mean episode return = -total waiting [vessel-min]")
    validation_axis.set_title("Validation total waiting (frozen suite, deterministic)")
    validation_axis.set_xlabel("training timesteps")
    validation_axis.set_ylabel("mean total waiting [vessel-min]")
    for axis in (train_axis, validation_axis):
        axis.legend(fontsize="small")
    figure.suptitle(args.experiment_dir.name)
    figure.tight_layout()
    figure.savefig(args.output, dpi=120)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
