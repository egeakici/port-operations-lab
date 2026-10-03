"""Paired dynamic evaluation; held-out suites require the frozen decision gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.rl.dynamic_checkpoint import load_dynamic_checkpoint
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig, POLICY_ID
from berth_allocation_lab.rl.dynamic_decision import DynamicDecisionError, verify_dynamic_test_gate
from berth_allocation_lab.rl.dynamic_evaluation import FCFS_ID, ROLLOUT_ID, run_dynamic_episode
from berth_allocation_lab.rl.dynamic_suites import audit_dynamic_suites, dynamic_suites


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--training-seed", required=True, type=int)
    parser.add_argument("--suite", choices=("validation", "test", "density_diagnostic"),
                        default="validation")
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--run-root", type=Path, help="Override the configured run output root.")
    parser.add_argument("--cross-horizon-h0", action="store_true",
                        help="Diagnostic only: evaluate an H=240 checkpoint at H=0.")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config = DynamicPPOConfig.load_yaml(args.config)
    if args.cross_horizon_h0 and config.horizon_min != 240:
        parser.error("Cross-horizon diagnostic requires an H=240-trained config.")
    evaluation_horizon = 0 if args.cross_horizon_h0 else config.horizon_min
    if args.training_seed not in config.training.training_seeds:
        parser.error("Training seed is outside the frozen seed set.")
    if args.output.exists():
        parser.error("Refusing to overwrite an evaluation artifact.")
    gate = None
    if args.suite != "validation":
        if args.decision is None:
            parser.error("Held-out evaluation requires --decision and its SHA-256 sidecar.")
        gate = verify_dynamic_test_gate(args.decision, config)
    suites = dynamic_suites(config)
    audit = audit_dynamic_suites(config, suites)
    suite = suites[args.suite]
    run_root = args.run_root if args.run_root is not None else config.resolve(config.output_dir)
    run_dir = run_root / config.experiment_id / f"seed_{args.training_seed}"
    if args.suite != "validation" and args.run_root is not None:
        parser.error("Held-out evaluation must use the frozen configured run root.")
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        parser.error(f"Missing run manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("status") != "completed" or
            manifest.get("config_sha256") != config.source_sha256 or
            manifest.get("training_seed") != args.training_seed):
        parser.error("Incomplete run or mismatched config/seed.")
    checkpoint = run_dir / "best_validation_model.zip"
    if args.suite != "validation":
        recorded = json.loads(args.decision.read_text(encoding="utf-8"))["regimes"][config.regime]
        selected = next(row for row in recorded["seeds"] if row["training_seed"] == args.training_seed)
        if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != selected["checkpoint_sha256"]:
            raise DynamicDecisionError("Selected checkpoint hash differs from frozen decision.")
    env = DynamicBAPEnv(scenario=suite.scenarios[0], max_vessels=config.max_vessels,
                        future_horizon_min=evaluation_horizon)
    env.reset()
    model, checkpoint_metadata = load_dynamic_checkpoint(
        checkpoint, env, allow_cross_horizon=args.cross_horizon_h0)
    rows = []
    for scenario in suite.scenarios:
        for method in (FCFS_ID, ROLLOUT_ID, POLICY_ID):
            rows.append(run_dynamic_episode(scenario, horizon_min=evaluation_horizon,
                                            max_vessels=config.max_vessels,
                                            method=method, model=model))
    record = {"config_sha256": config.source_sha256, "suite": suite.name,
              "training_horizon_min": config.horizon_min,
              "evaluation_horizon_min": evaluation_horizon,
              "comparison_label": "cross_horizon_diagnostic" if args.cross_horizon_h0 else "matched_horizon",
              "suite_audit": audit, "test_gate": gate,
              "training_seed": args.training_seed, "checkpoint_metadata": checkpoint_metadata,
              "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
    print(json.dumps({"output": str(args.output), "suite": suite.name,
                      "episodes": len(rows), "invalid": sum(not row["schedule_valid"] for row in rows)}))


if __name__ == "__main__":
    main()
