"""Pre-registered validation decision for the extended v1 campaign.

The rule (documented in docs/static_maskable_ppo.md, "Extended v1 campaign")
uses only validation results of each seed's best-validation checkpoint:

* tiny: useful learning if, for at least 2 of 3 seeds,
  ``(FCFS - PPO) / (FCFS - Rollout) >= 0.25``; a non-positive FCFS-Rollout gap
  makes the ratio undefined and the seed does not pass;
* medium/heavy: competitive if, for at least 2 of 3 seeds,
  ``PPO <= 1.10 * FCFS``.

The decision is written once (exclusive creation) with a SHA-256 sidecar
before any test-split evaluation; test results never change it. Final testing
is permitted once all configured seeds completed and the decision is recorded,
whatever its outcome.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from berth_allocation_lab.core import NUMERICAL_TOLERANCE
from berth_allocation_lab.rl.config import StaticPPOExperimentConfig
from berth_allocation_lab.tracking.git_metadata import get_git_metadata


DECISION_RULE_VERSION = "static_ppo_v1_extended_validation_rule_v1"
DECISION_RULE_REFERENCE = "docs/static_maskable_ppo.md#extended-v1-campaign"
TINY_GAP_CLOSURE_THRESHOLD = 0.25
MEDIUM_HEAVY_FCFS_RATIO_THRESHOLD = 1.10
REQUIRED_PASSING_SEEDS = 2
V2_MOTIVATION = ("the flat MultiInputPolicy architecture is the bottleneck, "
                 "motivating a candidate-scoring v2")


class ValidationDecisionError(ValueError):
    """Missing, altered or mismatching validation decision."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_outcome(kind: str, ppo: float | None, fcfs: float | None, rollout: float | None) -> dict[str, Any]:
    """Rule inputs and pass/fail for one seed (validation means, raw minutes)."""

    if kind == "tiny":
        gap = None if fcfs is None or rollout is None else fcfs - rollout
        ratio = (None if ppo is None or gap is None or gap <= NUMERICAL_TOLERANCE
                 else (fcfs - ppo) / gap)
        return {"gap_closure": ratio, "passes": ratio is not None and ratio >= TINY_GAP_CLOSURE_THRESHOLD}
    if kind == "medium_heavy":
        ratio = None if ppo is None or fcfs is None or fcfs <= 0 else ppo / fcfs
        passes = ppo is not None and fcfs is not None and ppo <= MEDIUM_HEAVY_FCFS_RATIO_THRESHOLD * fcfs
        return {"ppo_over_fcfs": ratio, "passes": passes}
    raise ValueError("kind must be tiny or medium_heavy.")


def regime_decision(kind: str, config: StaticPPOExperimentConfig,
                    run_dirs: Sequence[str | Path]) -> dict[str, Any]:
    """Collect validation inputs for one regime and apply its criterion."""

    problems, seeds = [], []
    for run_dir in map(Path, run_dirs):
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        selection = manifest.get("selection") or {}
        baselines = manifest.get("validation_baselines") or {}
        best = (manifest.get("checkpoints") or {}).get("best_validation")
        if manifest.get("status") != "completed" or best is None:
            problems.append(f"{run_dir.name}: status {manifest.get('status')}, no selected checkpoint")
        if manifest.get("experiment_id") != config.experiment_id or manifest.get(
                "config_sha256") != config.source_sha256:
            problems.append(f"{run_dir.name}: trained with a different config")
        ppo = selection.get("selected_mean_total_waiting_time_min")
        fcfs = baselines.get("fcfs_mean_total_waiting_time_min")
        rollout = baselines.get("rollout_mean_total_waiting_time_min")
        seeds.append({
            "training_seed": manifest.get("training_seed"),
            "status": manifest.get("status"),
            "git_commit_hash": manifest.get("git_commit_hash"),
            "git_dirty": manifest.get("git_dirty"),
            "total_timesteps_completed": manifest.get("total_timesteps_completed"),
            "selected_timesteps": selection.get("selected_timesteps"),
            "checkpoint_id": None if best is None else best["model_id"],
            "checkpoint_sha256": None if best is None else _sha256(run_dir / best["path"]),
            "ppo_validation_mean_min": ppo,
            "fcfs_validation_mean_min": fcfs,
            "rollout_validation_mean_min": rollout,
            **seed_outcome(kind, ppo, fcfs, rollout),
        })
    found = sorted(s["training_seed"] for s in seeds if s["training_seed"] is not None)
    if found != sorted(config.training.training_seeds):
        problems.append(f"seeds {found} differ from configured {sorted(config.training.training_seeds)}")
    passing = sum(s["passes"] for s in seeds)
    criterion = ("(FCFS - PPO) / (FCFS - Rollout) >= 0.25 for >= 2 of 3 seeds" if kind == "tiny"
                 else "PPO <= 1.10 * FCFS for >= 2 of 3 seeds")
    return {
        "regime": kind,
        "experiment_id": config.experiment_id,
        "config_path": config.source_path and Path(config.source_path).name,
        "config_sha256": config.source_sha256,
        "selection_metric": config.selection_metric,
        "criterion": criterion,
        "seeds": seeds,
        "passing_seeds": passing,
        "criterion_met": not problems and passing >= REQUIRED_PASSING_SEEDS,
        "complete": not problems,
        "problems": problems,
    }


def record_validation_decision(
    tiny_config: StaticPPOExperimentConfig, tiny_runs: Sequence[str | Path],
    medium_heavy_config: StaticPPOExperimentConfig, medium_heavy_runs: Sequence[str | Path],
    output: str | Path,
) -> dict[str, Any]:
    """Apply the frozen rule and write ``validation_decision.json`` exactly once."""

    output = Path(output)
    tiny = regime_decision("tiny", tiny_config, tiny_runs)
    medium_heavy = regime_decision("medium_heavy", medium_heavy_config, medium_heavy_runs)
    complete = tiny["complete"] and medium_heavy["complete"]
    both = tiny["criterion_met"] and medium_heavy["criterion_met"]
    commit, dirty = get_git_metadata()
    decision = {
        "decision_rule_version": DECISION_RULE_VERSION,
        "decision_rule_reference": DECISION_RULE_REFERENCE,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": commit,
        "source_git_dirty_at_decision": dirty,
        "uses_test_results": False,
        "regimes": {"tiny": tiny, "medium_heavy": medium_heavy},
        "campaign_complete": complete,
        "conclusion": (None if not complete else
                       "both criteria met; candidate-scoring v2 is optional" if both else
                       f"at least one criterion failed; {V2_MOTIVATION}"),
        "final_testing_permitted": complete,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as file:  # exclusive: never overwrite a decision
        json.dump(decision, file, indent=2, sort_keys=True)
    digest = _sha256(output)
    with output.with_name(output.name + ".sha256").open("x", encoding="utf-8") as file:
        file.write(f"{digest}  {output.name}\n")
    return {**decision, "sha256": digest}


def verify_validation_decision(path: str | Path, config: StaticPPOExperimentConfig,
                               checkpoint_hashes: dict[str, str]) -> dict[str, Any]:
    """Check digest, permission and that the evaluated checkpoints were the selected ones."""

    path = Path(path)
    sidecar = path.with_name(path.name + ".sha256")
    if not path.is_file() or not sidecar.is_file():
        raise ValidationDecisionError(f"{path} or its .sha256 sidecar is missing.")
    digest = _sha256(path)
    if sidecar.read_text(encoding="utf-8").split()[0] != digest:
        raise ValidationDecisionError("Validation decision does not match its recorded SHA-256.")
    decision = json.loads(path.read_text(encoding="utf-8"))
    if decision.get("decision_rule_version") != DECISION_RULE_VERSION or not decision.get(
            "final_testing_permitted"):
        raise ValidationDecisionError("The recorded decision does not permit final testing.")
    regime = next((r for r in decision["regimes"].values() if r["experiment_id"] == config.experiment_id
                   and r["config_sha256"] == config.source_sha256), None)
    if regime is None:
        raise ValidationDecisionError(f"No decision recorded for {config.experiment_id} with this config.")
    selected = {s["checkpoint_id"]: s["checkpoint_sha256"] for s in regime["seeds"]}
    for model_id, digest_value in checkpoint_hashes.items():
        if selected.get(model_id) != digest_value:
            raise ValidationDecisionError(f"Checkpoint {model_id} was not the recorded selection.")
    return {"path": path.as_posix(), "sha256": digest, "decision_rule_version": DECISION_RULE_VERSION,
            "regime": regime["regime"], "criterion_met": regime["criterion_met"],
            "conclusion": decision["conclusion"]}
