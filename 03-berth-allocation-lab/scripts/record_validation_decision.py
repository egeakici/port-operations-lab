"""Record the pre-registered extended v1 validation decision once (Step 9).

Example:
    python scripts/record_validation_decision.py \
        --tiny-config configs/rl/static_ppo_tiny_extended.yaml \
        --medium-heavy-config configs/rl/static_ppo_medium_heavy_extended.yaml \
        --output experiments/rl/extended_v1/validation_decision.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from berth_allocation_lab.rl import StaticPPOExperimentConfig
from berth_allocation_lab.rl.decision import record_validation_decision


def _runs(config: StaticPPOExperimentConfig) -> list[Path]:
    experiment = config.resolve(config.output_dir) / config.experiment_id
    return sorted(p for p in experiment.glob("seed_*") if p.is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tiny-config", required=True, type=Path)
    parser.add_argument("--medium-heavy-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"{args.output} exists; a recorded decision is never overwritten.")

    tiny = StaticPPOExperimentConfig.load_yaml(args.tiny_config)
    medium_heavy = StaticPPOExperimentConfig.load_yaml(args.medium_heavy_config)
    decision = record_validation_decision(tiny, _runs(tiny), medium_heavy, _runs(medium_heavy), args.output)
    for name, regime in decision["regimes"].items():
        print(f"{name}: criterion met={regime['criterion_met']} "
              f"({regime['passing_seeds']} passing seeds; {regime['criterion']})")
        for problem in regime["problems"]:
            print(f"  problem: {problem}")
    print(f"conclusion: {decision['conclusion']}")
    print(f"final testing permitted: {decision['final_testing_permitted']}")
    print(f"sha256: {decision['sha256']}  ({args.output})")
    print(json.dumps({"written": str(args.output)}))
    return 0 if decision["final_testing_permitted"] else 1


if __name__ == "__main__":
    sys.exit(main())
