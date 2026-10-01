"""Train Static Maskable PPO for one or more training seeds (Step 9).

Example:
    python scripts/train_static_ppo.py --config configs/rl/static_ppo_tiny.yaml --training-seed 11
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from berth_allocation_lab.rl import StaticPPOExperimentConfig
from berth_allocation_lab.rl.training import run_directory, train_static_ppo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--training-seed", type=int, action="append",
                        help="Repeatable; defaults to every seed in the config.")
    parser.add_argument("--total-timesteps", type=int, help="Override the config budget (recorded).")
    parser.add_argument("--eval-freq", type=int, help="Override validation frequency (recorded).")
    parser.add_argument("--output-dir", type=Path, help="Override the output root (recorded).")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"))
    args = parser.parse_args(argv)

    config = StaticPPOExperimentConfig.load_yaml(args.config)
    seeds = args.training_seed or list(config.training.training_seeds)
    for seed in seeds:  # fail before training if any run directory already exists
        if run_directory(config, seed, args.output_dir).exists():
            parser.error(f"{run_directory(config, seed, args.output_dir)} exists; choose --output-dir.")
    failures = 0
    for seed in seeds:
        manifest = train_static_ppo(config, seed, output_root=args.output_dir,
                                    total_timesteps=args.total_timesteps, eval_freq=args.eval_freq,
                                    device=args.device)
        selection = manifest.get("selection") or {}
        baselines = manifest.get("validation_baselines") or {}
        print(f"seed {seed}: status={manifest['status']} timesteps={manifest.get('total_timesteps_completed')} "
              f"runtime={manifest['training_runtime_seconds']:.1f}s "
              f"(learning {manifest.get('learning_steps_per_second') or 0:.0f} steps/s)")
        print(f"  best validation mean waiting {selection.get('selected_mean_total_waiting_time_min')} min "
              f"at timestep {selection.get('selected_timesteps')}; validation FCFS "
              f"{baselines.get('fcfs_mean_total_waiting_time_min')}, Rollout "
              f"{baselines.get('rollout_mean_total_waiting_time_min')}")
        if manifest["status"] != "completed":
            failures += 1
            print(f"  {manifest['failure_type']}: {manifest['failure_message']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
