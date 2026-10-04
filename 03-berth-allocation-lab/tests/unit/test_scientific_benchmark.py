"""Hand-worked contracts for the frozen Step 12A statistical core."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError, BenchmarkSource
from berth_allocation_lab.benchmark.inputs import LockedDataset, _checkpoint, verify_decision
from berth_allocation_lab.benchmark.runner import analyze, dry_run, output_names, run
from berth_allocation_lab.benchmark.stats import (
    classify, gap_closed, improvement_percent, paired_bootstrap, paired_summary,
    scenario_seed_means, verify_replay, weighted_mean,
)


def _fixture(formulation: str, tmp_path: Path) -> tuple[BenchmarkConfig, LockedDataset]:
    source = BenchmarkSource("tiny", "v1", "fixture", "none", "none")
    config = BenchmarkConfig("fixture", formulation, str(tmp_path), (source,), {},
                             {"tiny": {"a": 0.5, "b": 0.5}}, 100, 0.95, 12012,
                             "off", tmp_path / "config.yaml", tmp_path)
    scenarios = {f"{family}{index}": {"family": family, "physical_fingerprint": f"{family}{index}"}
                 for family in ("a", "b") for index in (1, 2)}
    costs = {}
    for sid in scenarios:
        base = 10.0 if sid.startswith("a") else 30.0
        costs[("fcfs", None, sid)] = base
        costs[("rollout", None, sid)] = base - 4.0
        for seed, improvement in ((11, 1.0), (23, 2.0), (37, 3.0)):
            costs[("ppo", seed, sid)] = base - improvement
    dataset = LockedDataset(source, {"a": 0.5, "b": 0.5}, scenarios, costs, [],
                            {"missing_rows": 0}, {"evaluation_sha256": "fixture"})
    return config, dataset


def test_weighting_and_seed_mean_are_scenario_level(tmp_path):
    config, dataset = _fixture("dynamic", tmp_path)
    result = analyze(config, [dataset], {})
    row = result["summaries"][0]
    assert row["fcfs_weighted_mean_min"] == 20
    assert row["rollout_weighted_mean_min"] == 16
    assert row["ppo_seed_mean_weighted_min"] == 18
    assert row["gap_closed_seed_mean"] == 0.5
    assert row["gap_closed_by_seed"] == {"11": 0.25, "23": 0.5, "37": 0.75}
    paired = next(r for r in result["comparisons"] if r["family"] == "WEIGHTED" and
                  r["method"] == "ppo_seed_mean" and r["reference"] == "fcfs")
    assert paired["n_physical_scenarios"] == 4
    assert (paired["wins"], paired["ties"], paired["losses"]) == (4, 0, 0)
    assert paired["mean_delta_min"] == -2
    assert len([r for r in result["differences"] if r["method"] == "ppo_seed_mean" and
                r["reference"] == "fcfs"]) == 4
    assert all(r["n_physical_scenarios"] == 4 for r in result["intervals"])
    assert next(r for r in result["family_metrics"] if r["method"] == "ppo_seed_mean" and
                r["family"] == "a")["fcfs_to_rollout_gap_closed"] == 0.5


def test_branch_isolation_and_exact_scope(tmp_path):
    config, dataset = _fixture("static", tmp_path)
    dataset.costs.update({("exact", None, sid): 3.0 for sid in dataset.scenarios})
    result = analyze(config, [dataset], {"previously_selected": {"tiny": "v1"}})
    exact = next(r for r in result["family_metrics"] if r["method"] == "candidate_space_exact")
    assert exact["exact_scope"] == "fixed_order_finite_candidate_space"
    assert exact["is_previously_selected_version"] is True
    assert "static_family_metrics.csv" in output_names("static")
    assert "dynamic_tiny_family_metrics.csv" not in output_names("static")
    assert "static_family_metrics.csv" not in output_names("dynamic")
    assert all("gap_closed_seed_mean" not in row for row in result["summaries"])


def test_weighted_mean_requires_complete_families():
    assert weighted_mean({"a": [0, 10], "b": [30]}, {"a": 0.5, "b": 0.5}) == 17.5
    with pytest.raises(BenchmarkError):
        weighted_mean({"a": [10]}, {"a": 0.5, "b": 0.5})


def test_seed_matrix_requires_same_scenarios_and_all_seeds():
    assert scenario_seed_means({11: {"x": 1}, 23: {"x": 4}, 37: {"x": 7}}) == {"x": 4}
    with pytest.raises(BenchmarkError):
        scenario_seed_means({11: {"x": 1}, 23: {"x": 4}})
    with pytest.raises(BenchmarkError):
        scenario_seed_means({11: {"x": 1}, 23: {"x": 4}, 37: {"y": 7}})


def test_gap_and_percentage_are_not_clipped():
    assert gap_closed(12, 10, 8) == -1
    assert gap_closed(6, 10, 8) == 2
    assert gap_closed(8, 8, 8) is None
    assert gap_closed(8, 7, 8) is None
    assert improvement_percent(8, 0) is None
    assert improvement_percent(12, 10) == -20
    assert improvement_percent(8, 10) == 20


def test_tie_tolerance_and_paired_counts():
    assert classify(-1e-6) == "tie"
    assert classify(1e-6) == "tie"
    assert classify(-1.01e-6) == "win"
    assert classify(1.01e-6) == "loss"
    result = paired_summary([-3, 0, 1e-7, 2])
    assert (result["wins"], result["ties"], result["losses"]) == (1, 2, 1)
    assert result["median_delta_min"] == pytest.approx(5e-8)


def test_bootstrap_is_paired_stratified_and_deterministic():
    values = {"a": [-2, -2], "b": [4, 6]}
    weights = {"a": 0.5, "b": 0.5}
    one = paired_bootstrap(values, weights, resamples=1000, seed=12012)
    two = paired_bootstrap(values, weights, resamples=1000, seed=12012)
    assert one == two
    assert one["estimate_min"] == 1.5
    assert one["n_physical_scenarios"] == 4
    assert one["ci_lower_min"] >= 1
    assert one["ci_upper_min"] <= 2
    assert paired_bootstrap({"a": [0, 0], "b": [10, 10]}, weights,
                            resamples=100)["ci_lower_min"] == 5


def test_replay_fails_closed_with_full_context():
    verify_replay({"s/ppo/11": 1.0}, {"s/ppo/11": 1.000001},
                  device="cpu", dependencies={"torch": "2"})
    with pytest.raises(BenchmarkError, match="locked=.*replayed=.*device=cpu"):
        verify_replay({"s/ppo/11": 1.0}, {"s/ppo/11": 1.01},
                      device="cpu", dependencies={"torch": "2"})
    with pytest.raises(BenchmarkError):
        verify_replay({"s": 1.0}, {"s": float("nan")}, device="cpu", dependencies={})
    with pytest.raises(BenchmarkError, match="keys differ"):
        verify_replay({"s": 1}, {"t": 1}, device="cpu", dependencies={})


def test_missing_decision_and_artifact_fail(tmp_path):
    with pytest.raises(BenchmarkError, match="missing"):
        verify_decision(tmp_path / "missing.json")
    decision = tmp_path / "decision.json"
    decision.write_text(json.dumps({"uses_test_results": False,
                                    "source_git_dirty_at_decision": False,
                                    "final_testing_permitted": True}), encoding="utf-8")
    with pytest.raises(BenchmarkError, match="sidecar"):
        verify_decision(decision)


def test_dry_run_is_read_only_and_run_is_exclusive(monkeypatch, tmp_path):
    config, dataset = _fixture("dynamic", tmp_path)
    monkeypatch.setattr("berth_allocation_lab.benchmark.runner.load_all",
                        lambda _: ([dataset], {}))
    monkeypatch.setattr("berth_allocation_lab.benchmark.runner._source_reconciliation",
                        lambda _: {"status": "fixture"})
    monkeypatch.setattr("berth_allocation_lab.benchmark.runner.sha256_file", lambda _: "fixture")
    monkeypatch.setattr("berth_allocation_lab.benchmark.runner.get_git_metadata",
                        lambda: ("fixture", False))
    config.source_path.write_text("fixture", encoding="utf-8")
    audit = dry_run(config)
    assert audit["status"] == "ready"
    assert audit["estimated_replay_episodes"] == 0
    assert not (tmp_path / "fixture").exists()
    path = run(config)
    assert (path / "manifest.json").is_file()
    assert not (path / "static_family_metrics.csv").exists()
    with pytest.raises(BenchmarkError, match="already exists"):
        run(config)


def test_config_rejects_malformed_bootstrap(tmp_path):
    import yaml

    root = Path(__file__).resolve().parents[2]
    source = yaml.safe_load((root / "configs/benchmark/step12_static.yaml").read_text())
    path = root / "configs/benchmark" / "step12_static.yaml"
    assert BenchmarkConfig.load(path).formulation == "static"
    source["bootstrap"]["confidence_level"] = "bad"
    monkey_file = tmp_path / "config.yaml"
    monkey_file.write_text(yaml.safe_dump(source), encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("fixture", encoding="utf-8")
    with pytest.raises(BenchmarkError, match="bootstrap"):
        BenchmarkConfig.load(monkey_file)


def test_checkpoint_hash_and_best_validation_sidecar(tmp_path):
    model = tmp_path / "best_validation_model.zip"
    model.write_bytes(b"model")
    digest = hashlib.sha256(b"model").hexdigest()
    sidecar = tmp_path / "best_validation_model.metadata.json"
    metadata = {"experiment_id": "fixture", "training_seed": 11,
                "timesteps": 42, "checkpoint_kind": "best_validation",
                "config_sha256": "config", "git_dirty": False}
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    assert _checkpoint(model, experiment="fixture", seed=11, selected_step=42,
                       expected_sha=digest, config_sha="config") == metadata
    with pytest.raises(BenchmarkError, match="hash mismatch"):
        _checkpoint(model, experiment="fixture", seed=11, selected_step=42,
                    expected_sha="wrong", config_sha="config")
    with pytest.raises(BenchmarkError, match="sidecar mismatch"):
        _checkpoint(model, experiment="fixture", seed=23, selected_step=42,
                    expected_sha=digest, config_sha="config")
