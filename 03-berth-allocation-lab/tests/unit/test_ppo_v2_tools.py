"""One-time decision artifact and paired-comparison guardrails."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from berth_allocation_lab.rl.config import StaticPPOExperimentConfig
from berth_allocation_lab.rl.decision import record_v2_validation_decision


ROOT = Path(__file__).resolve().parents[2]
compare = runpy.run_path(str(ROOT / "scripts" / "compare_static_ppo_versions.py"))["compare"]


def _config(stem, version):
    suffix = "extended" if version == "v1" else "v2"
    return StaticPPOExperimentConfig.load_yaml(ROOT / "configs" / "rl" / f"static_ppo_{stem}_{suffix}.yaml")


def _runs(root, config, means):
    paths = []
    for seed, mean in zip((11, 23, 37), means):
        directory = root / config.experiment_id / f"seed_{seed}"
        directory.mkdir(parents=True)
        (directory / "best.zip").write_bytes(f"{seed}:{mean}".encode())
        (directory / "manifest.json").write_text(json.dumps({
            "status": "completed", "experiment_id": config.experiment_id,
            "config_sha256": config.source_sha256, "training_seed": seed,
            "git_commit_hash": "fixture", "git_dirty": False,
            "total_timesteps_completed": config.training.total_timesteps,
            "selection": {"selected_timesteps": 100, "selected_mean_total_waiting_time_min": mean},
            "checkpoints": {"best_validation": {"path": "best.zip", "model_id": f"{config.experiment_id}/{seed}"}},
            "validation_baselines": {"fcfs_mean_total_waiting_time_min": 20,
                                     "rollout_mean_total_waiting_time_min": 5},
            "validation_scenario_set": [{"physical_fingerprint": "same"}],
        }), encoding="utf-8")
        paths.append(directory)
    return paths


def test_v2_decision_written_once_with_digest_and_matched_seeds(tmp_path):
    regimes = {}
    for stem, name in (("tiny", "tiny"), ("medium_heavy", "medium_heavy")):
        old, new = _config(stem, "v1"), _config(stem, "v2")
        regimes[name] = (old, _runs(tmp_path, old, [10, 10, 10]),
                         new, _runs(tmp_path, new, [9, 9, 11] if name == "tiny" else [11, 11, 9]))
    path = tmp_path / "decision.json"
    decision = record_v2_validation_decision(regimes, path)
    assert decision["conclusion"] == "mixed" and decision["uses_test_results"] is False
    assert decision["regimes"]["tiny"]["criterion_met"]
    assert not decision["regimes"]["medium_heavy"]["criterion_met"]
    assert path.with_name("decision.json.sha256").read_text().split()[0] == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        record_v2_validation_decision(regimes, path)


def _evaluation(directory, fingerprint="same", v2=False):
    directory.mkdir()
    manifest = {"experiment_id": "v2" if v2 else "v1", "checkpoint_kind": "best_validation",
                "suites": {"test": {"identities": [{"physical_fingerprint": fingerprint}]}}}
    (directory / "evaluation_manifest.json").write_text(json.dumps(manifest))
    base = {"suite": "test", "component": "bap_tiny_n6", "physical_fingerprint": fingerprint,
            "is_valid": True, "exact_certified": True}
    rows = [{**base, "method": method, "total_waiting_time_min": value}
            for method, value in (("fcfs", 10), ("rollout", 8), ("exact", 7))]
    rows.append({**base, "method": "ppo", "training_seed": 11,
                 "total_waiting_time_min": 8 if v2 else 9})
    (directory / "per_instance.jsonl").write_text("\n".join(map(json.dumps, rows)) + "\n")


def test_comparison_reports_paired_delta_and_rejects_different_suites(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    _evaluation(first)
    _evaluation(second, v2=True)
    result = compare(first, second)
    assert result["paired_rows"][0]["v2_minus_v1_min"] == -1
    assert result["groups"][0]["exact_certified_count"] == 1
    assert result["groups"][0]["v1_cross_seed_mean_waiting_min"] == 9
    assert result["groups"][0]["v2_cross_seed_mean_waiting_min"] == 8
    changed = tmp_path / "changed"
    _evaluation(changed, fingerprint="different", v2=True)
    with pytest.raises(ValueError, match="non-identical"):
        compare(first, changed)
