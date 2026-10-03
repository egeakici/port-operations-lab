"""Train dynamic MaskablePPO with validation-only checkpoint selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.rl.dynamic_training import train_dynamic_ppo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--training-seed", required=True, type=int)
    parser.add_argument("--total-timesteps", type=int)
    parser.add_argument("--eval-freq", type=int)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    result = train_dynamic_ppo(
        DynamicPPOConfig.load_yaml(args.config), args.training_seed,
        output_root=args.output_dir, total_timesteps=args.total_timesteps,
        eval_freq=args.eval_freq, progress=args.progress)
    print(json.dumps({key: result[key] for key in
                      ("status", "total_timesteps_completed", "selection",
                       "learning_steps_per_second")}, indent=2))


if __name__ == "__main__":
    main()
