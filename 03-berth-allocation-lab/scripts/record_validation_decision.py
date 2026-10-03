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
from berth_allocation_lab.rl.decision import record_v2_validation_decision, record_validation_decision
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.rl.dynamic_decision import record_dynamic_decision


def _runs(config: StaticPPOExperimentConfig) -> list[Path]:
    experiment = config.resolve(config.output_dir) / config.experiment_id
    return sorted(p for p in experiment.glob("seed_*") if p.is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("v1", "v2", "dynamic"), default="v1")
    parser.add_argument("--tiny-config", required=True, type=Path)
    parser.add_argument("--medium-heavy-config", required=True, type=Path)
    parser.add_argument("--v2-tiny-config", type=Path)
    parser.add_argument("--v2-medium-heavy-config", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"{args.output} exists; a recorded decision is never overwritten.")

    if args.mode == "dynamic":
        decision = record_dynamic_decision((DynamicPPOConfig.load_yaml(args.tiny_config),
                                            DynamicPPOConfig.load_yaml(args.medium_heavy_config)),
                                           args.output)
        for name, regime in decision["regimes"].items():
            print(f"{name}: R1={regime['r1_useful_learning']} "
                  f"wins={regime['r1_seed_wins_vs_fcfs']} "
                  f"R2_mean={regime['r2_gap_closed_mean']}")
        print(f"sha256: {decision['sha256']} ({args.output})")
        return 0

    tiny = StaticPPOExperimentConfig.load_yaml(args.tiny_config)
    medium_heavy = StaticPPOExperimentConfig.load_yaml(args.medium_heavy_config)
    if args.mode == "v2":
        if args.v2_tiny_config is None or args.v2_medium_heavy_config is None:
            parser.error("v2 mode requires both --v2-tiny-config and --v2-medium-heavy-config.")
        v2_tiny = StaticPPOExperimentConfig.load_yaml(args.v2_tiny_config)
        v2_medium_heavy = StaticPPOExperimentConfig.load_yaml(args.v2_medium_heavy_config)
        decision = record_v2_validation_decision({
            "tiny": (tiny, _runs(tiny), v2_tiny, _runs(v2_tiny)),
            "medium_heavy": (medium_heavy, _runs(medium_heavy), v2_medium_heavy, _runs(v2_medium_heavy)),
        }, args.output)
    else:
        decision = record_validation_decision(tiny, _runs(tiny), medium_heavy, _runs(medium_heavy), args.output)
    for name, regime in decision["regimes"].items():
        if args.mode == "v2":
            print(f"{name}: winner={regime['winner']} v2 paired wins={regime['v2_paired_seed_wins']}")
        else:
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
