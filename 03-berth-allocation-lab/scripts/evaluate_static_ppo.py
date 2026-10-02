"""Paired held-out evaluation of trained Static Maskable PPO checkpoints (Step 9).

Example:
    python scripts/evaluate_static_ppo.py --config configs/rl/static_ppo_tiny.yaml \
        --experiment-dir experiments/rl/static_ppo/static_ppo_tiny_v1 \
        --output experiments/rl/evaluations/static_ppo_tiny_v1_test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from berth_allocation_lab.rl import StaticPPOExperimentConfig
from berth_allocation_lab.rl.evaluation import evaluate_training_runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    runs = parser.add_mutually_exclusive_group(required=True)
    runs.add_argument("--run-dir", type=Path, action="append", help="Repeatable training run directory.")
    runs.add_argument("--experiment-dir", type=Path, help="Use every seed_* run below this directory.")
    parser.add_argument("--checkpoint", choices=("best", "final"), default="best")
    parser.add_argument("--suite", action="append",
                        help="test, validation or a diagnostic name; default: test and all diagnostics.")
    parser.add_argument("--seeds-per-component", type=int)
    parser.add_argument("--seeds", type=int, nargs="+", help="Explicit split-partition seeds for one suite.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--record-runs", action="store_true", help="Also write per-run scientific records.")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda", "auto"))
    parser.add_argument("--progress", action="store_true", help="Show terminal progress on stderr only.")
    parser.add_argument("--validation-decision", type=Path,
                        help="Recorded validation_decision.json; required for test suites of "
                             "experiments with require_validation_decision.")
    args = parser.parse_args(argv)

    config = StaticPPOExperimentConfig.load_yaml(args.config)
    run_dirs = args.run_dir or sorted(p for p in args.experiment_dir.glob("seed_*") if p.is_dir())
    output = evaluate_training_runs(
        config, run_dirs, output_dir=args.output, suites=args.suite, checkpoint=args.checkpoint,
        seeds_per_component=args.seeds_per_component, seeds=args.seeds,
        record_runs=args.record_runs, device=args.device, validation_decision=args.validation_decision,
        progress=args.progress,
    )
    print((output / "report.md").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (output / "per_instance.jsonl").read_text().splitlines()]
    invalid = [r for r in rows if not r["is_valid"]]
    print(f"{len(rows)} result rows, {len(invalid)} invalid; written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
