"""Plot all dynamic validation seeds, their mean and online references."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config = DynamicPPOConfig.load_yaml(args.config)
    root = config.resolve(config.output_dir) / config.experiment_id
    histories = []
    refs = []
    for seed in config.training.training_seeds:
        run = root / f"seed_{seed}"
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        history = json.loads((run / "validation_metrics.json").read_text(encoding="utf-8"))["history"]
        if manifest["status"] != "completed":
            raise ValueError(f"Seed {seed} is not complete.")
        points = [(r["timesteps"], r["weighted_mean_total_waiting_min"]) for r in history]
        if any(y is None for _, y in points):
            raise ValueError(f"Seed {seed} contains an invalid validation episode.")
        histories.append((seed, points))
        refs.append(manifest["validation_references"])
    if len({tuple(t for t, _ in h) for _, h in histories}) != 1:
        raise ValueError("Validation step grids differ across seeds; no mean line is defined.")
    fcfs = [r["dynamic_online_fcfs_v1"]["weighted_mean_total_waiting_min"] for r in refs]
    rollout = [r["dynamic_online_rollout_v1"]["weighted_mean_total_waiting_min"] for r in refs]
    if len(set(fcfs)) != 1 or len(set(rollout)) != 1:
        raise ValueError("Reference lines differ across seeds.")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for seed, points in histories:
        ax.plot([t for t, _ in points], [y for _, y in points], alpha=0.6, label=f"PPO seed {seed}")
    xs = [t for t, _ in histories[0][1]]
    means = [statistics.fmean(histories[j][1][i][1] for j in range(len(histories)))
             for i in range(len(xs))]
    ax.plot(xs, means, color="black", linewidth=2.5, label="PPO three-seed mean")
    ax.axhline(fcfs[0], linestyle="--", color="tab:green", label="Online FCFS")
    ax.axhline(rollout[0], linestyle=":", color="tab:red", label="Online Rollout")
    ax.set(xlabel="Training transitions", ylabel="Validation total waiting (min)",
           title=f"{config.regime} H={config.horizon_min:g}")
    ax.legend(fontsize=8)
    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    print(args.output)


if __name__ == "__main__":
    main()
