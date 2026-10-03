"""Pre-registered dynamic_rule_1 using selected validation checkpoints only."""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.rl.policy import metadata_path
from berth_allocation_lab.tracking.git_metadata import get_git_metadata

RULE_VERSION = "dynamic_rule_1"


class DynamicDecisionError(ValueError):
    pass


def gap_closed(ppo: float, fcfs: float, rollout: float) -> float | None:
    return None if fcfs <= rollout else (fcfs - ppo) / (fcfs - rollout)


def dynamic_rule(ppo_values: list[float], fcfs: float, rollout: float) -> dict[str, Any]:
    if len(ppo_values) != 3 or any(not isinstance(v, (int, float)) for v in ppo_values):
        raise DynamicDecisionError("Exactly three valid PPO validation means are required.")
    mean = statistics.fmean(ppo_values)
    wins = sum(v < fcfs for v in ppo_values)
    return {
        "r1_useful_learning": mean < fcfs and wins >= 2,
        "r1_seed_wins_vs_fcfs": wins,
        "ppo_mean_waiting_min": mean,
        "fcfs_mean_waiting_min": fcfs,
        "rollout_mean_waiting_min": rollout,
        "r2_gap_closed_by_seed": [gap_closed(v, fcfs, rollout) for v in ppo_values],
        "r2_gap_closed_mean": gap_closed(mean, fcfs, rollout),
        "interpretation": ("useful learning by R1; R2 descriptive only" if mean < fcfs and wins >= 2
                           else "R1 not met; mixed or close outcomes are inconclusive"),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _regime(config: DynamicPPOConfig) -> dict[str, Any]:
    root = config.resolve(config.output_dir) / config.experiment_id
    rows = []
    for seed in config.training.training_seeds:
        run = root / f"seed_{seed}"
        manifest_path = run / "manifest.json"
        if not manifest_path.is_file():
            raise DynamicDecisionError(f"Missing run manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checkpoint = run / "best_validation_model.zip"
        if (manifest.get("status") != "completed" or
                manifest.get("config_sha256") != config.source_sha256 or
                manifest.get("experiment_id") != config.experiment_id or
                manifest.get("training_seed") != seed or
                manifest.get("checkpoints", {}).get("best_validation") != checkpoint.name or
                not checkpoint.is_file() or not metadata_path(checkpoint).is_file()):
            raise DynamicDecisionError(f"Incomplete or incompatible run: {run}")
        if not all(manifest.get("suite_audit", {}).values()):
            raise DynamicDecisionError(f"Suite audit missing or failed: {run}")
        ppo = manifest["selection"]["selected_mean_total_waiting_min"]
        refs = manifest["validation_references"]
        fcfs = refs["dynamic_online_fcfs_v1"]["weighted_mean_total_waiting_min"]
        rollout = refs["dynamic_online_rollout_v1"]["weighted_mean_total_waiting_min"]
        if any(v is None for v in (ppo, fcfs, rollout)):
            raise DynamicDecisionError(f"Invalid validation result: {run}")
        rows.append({"training_seed": seed, "ppo_validation_waiting_min": ppo,
                     "fcfs_validation_waiting_min": fcfs,
                     "rollout_validation_waiting_min": rollout,
                     "selected_timesteps": manifest["selection"]["selected_timesteps"],
                     "checkpoint_sha256": _sha256(checkpoint),
                     "validation_physical_fingerprints": [r["physical_fingerprint"] for r in
                                                          manifest["validation_scenario_set"]],
                     "git_commit_hash": manifest["git_commit_hash"],
                     "git_dirty": manifest["git_dirty"]})
    if len({tuple(r["validation_physical_fingerprints"]) for r in rows}) != 1:
        raise DynamicDecisionError("Training seeds saw different validation suites.")
    if len({r["fcfs_validation_waiting_min"] for r in rows}) != 1 or len({r["rollout_validation_waiting_min"] for r in rows}) != 1:
        raise DynamicDecisionError("Validation reference results differ across training seeds.")
    rule = dynamic_rule([r["ppo_validation_waiting_min"] for r in rows],
                        rows[0]["fcfs_validation_waiting_min"],
                        rows[0]["rollout_validation_waiting_min"])
    return {"regime": config.regime, "horizon_min": config.horizon_min,
            "experiment_id": config.experiment_id,
            "config_sha256": config.source_sha256, "seeds": rows, **rule}


def record_dynamic_decision(configs: tuple[DynamicPPOConfig, DynamicPPOConfig],
                            output: str | Path) -> dict[str, Any]:
    output = Path(output)
    sidecar = output.with_name(output.name + ".sha256")
    if output.exists() or sidecar.exists():
        raise FileExistsError("Dynamic decision is immutable and already exists.")
    if any(not config.require_validation_decision for config in configs) or len({c.horizon_min for c in configs}) != 1:
        raise DynamicDecisionError("A decision needs two extended regimes trained at the same horizon.")
    regimes = {config.regime: _regime(config) for config in configs}
    if set(regimes) != {"tiny", "medium_heavy"}:
        raise DynamicDecisionError("Both frozen regimes are required.")
    commit, dirty = get_git_metadata()
    decision = {"decision_rule_version": RULE_VERSION,
                "horizon_min": configs[0].horizon_min,
                "decision_rule_reference": "docs/dynamic_maskable_ppo.md#dynamic-rule-1",
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "source_git_commit": commit, "source_git_dirty_at_decision": dirty,
                "uses_test_results": False, "final_testing_permitted": True,
                "regimes": regimes}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(decision, stream, indent=2, sort_keys=True)
    digest = _sha256(output)
    with sidecar.open("x", encoding="utf-8") as stream:
        stream.write(f"{digest}  {output.name}\n")
    return {**decision, "sha256": digest}


def verify_dynamic_test_gate(decision_path: str | Path, config: DynamicPPOConfig) -> dict[str, Any]:
    """Fail closed before any held-out generation/evaluation in Part B."""
    commit, dirty = get_git_metadata()
    if commit is None or dirty is not False:
        raise DynamicDecisionError("Final testing requires a clean Git worktree.")
    path = Path(decision_path)
    sidecar = path.with_name(path.name + ".sha256")
    if not path.is_file() or not sidecar.is_file() or sidecar.read_text(encoding="utf-8").split()[0] != _sha256(path):
        raise DynamicDecisionError("Decision JSON or SHA-256 sidecar missing or altered.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("decision_rule_version") != RULE_VERSION or not decision.get("final_testing_permitted"):
        raise DynamicDecisionError("Frozen dynamic decision rule or permission differs.")
    recorded = decision["regimes"].get(config.regime)
    current = _regime(config)
    if recorded != current:
        raise DynamicDecisionError("Run manifests, audits or selected checkpoints changed since decision.")
    return {"decision_sha256": _sha256(path), "regime": config.regime,
            "r1_useful_learning": recorded["r1_useful_learning"]}
