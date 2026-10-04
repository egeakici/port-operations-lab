"""Read-only integration checks against frozen Step 9/11 campaigns."""

from __future__ import annotations

import copy
import io
from pathlib import Path

import pytest

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.inputs import load_all, load_dynamic, verify_decision
from berth_allocation_lab.benchmark.runner import analyze, dry_run

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def static_evidence():
    config = BenchmarkConfig.load(ROOT / "configs/benchmark/step12_static.yaml")
    return config, *load_all(config)


@pytest.fixture(scope="module")
def dynamic_evidence():
    config = BenchmarkConfig.load(ROOT / "configs/benchmark/step12_dynamic_h240.yaml")
    return config, *load_all(config)


def test_static_locked_sources_and_selection(static_evidence):
    config, datasets, decisions = static_evidence
    assert len(datasets) == 4
    assert decisions["previously_selected"] == {"tiny": "v1", "medium_heavy": "v2"}
    for item in datasets:
        assert item.audit["missing_rows"] == 0
        assert item.audit["invalid_rows"] == 0
        assert len(item.inventory) == 3
        assert all(row["evaluation_sha256"] for row in item.inventory)
        assert len(item.scenarios) == (150 if item.source.regime == "tiny" else 100)
    analysis = analyze(config, datasets, decisions)
    assert len(analysis["reconciliation"]) == 4
    assert all(row["status"] == "matched_locked_aggregate"
               for row in analysis["reconciliation"].values())
    assert all(row["exact_scope"] == "fixed_order_finite_candidate_space"
               for row in analysis["summaries"] if row["regime"] == "tiny")
    assert all("exact_scope" not in row for row in analysis["summaries"]
               if row["regime"] == "medium_heavy")


def test_dynamic_three_seed_pairing_and_step11_reconciliation(dynamic_evidence):
    config, datasets, decisions = dynamic_evidence
    assert len(datasets) == 2
    assert all(len(item.inventory) == 3 and item.audit["missing_rows"] == 0
               for item in datasets)
    analysis = analyze(config, datasets, decisions)
    scores = {row["regime"]: row for row in analysis["summaries"]}
    assert scores["tiny"]["gap_closed_seed_mean"] == pytest.approx(0.55852968518)
    assert scores["medium_heavy"]["gap_closed_seed_mean"] == pytest.approx(0.26071203406)
    assert all(row["status"] == "verified_canonical_per_scenario_rows"
               for row in analysis["reconciliation"].values())
    assert all(row["n_physical_scenarios"] in {100, 150} for row in analysis["intervals"])


def test_static_dynamic_are_not_cross_paired(static_evidence, dynamic_evidence):
    static = static_evidence[1][0]
    dynamic = dynamic_evidence[1][0]
    assert set(static.scenarios).isdisjoint(dynamic.scenarios)
    assert {row["physical_fingerprint"] for row in static.scenarios.values()}.isdisjoint(
        row["physical_fingerprint"] for row in dynamic.scenarios.values())
    assert static_evidence[2] != dynamic_evidence[2]


def test_dry_run_is_read_only(static_evidence, dynamic_evidence):
    for config, _, _ in (static_evidence, dynamic_evidence):
        target = config.resolve(config.output_root) / config.benchmark_id
        before = sorted(target.iterdir()) if target.exists() else None
        audit = dry_run(config)
        assert audit["status"] == "ready"
        assert audit["replay_needed"] is False
        assert audit["estimated_replay_episodes"] == 0
        assert sorted(target.iterdir()) == before if before is not None else not target.exists()


@pytest.mark.parametrize("defect", ["duplicate", "missing", "truncated", "fingerprint"])
def test_dynamic_adapter_rejects_corrupt_locked_rows(monkeypatch, dynamic_evidence, defect):
    import berth_allocation_lab.benchmark.inputs as inputs

    config, datasets, _ = dynamic_evidence
    source = datasets[0].source
    decisions = {name: verify_decision(config.resolve(path))
                 for name, path in config.decisions.items()}
    original = inputs._read_json

    def tampered(path):
        value = original(path)
        if path.name == "tiny_seed_11.json":
            value = copy.deepcopy(value)
            if defect == "duplicate":
                value["rows"][1] = value["rows"][0]
            elif defect == "missing":
                value["rows"].pop()
            elif defect == "truncated":
                value["rows"][0]["truncated"] = True
            else:
                value["rows"][0]["physical_fingerprint"] = "wrong"
        return value

    monkeypatch.setattr(inputs, "_read_json", tampered)
    with pytest.raises(BenchmarkError):
        load_dynamic(config, source, decisions)


def test_missing_selected_seed_is_blocking(dynamic_evidence):
    import berth_allocation_lab.benchmark.inputs as inputs

    config, datasets, _ = dynamic_evidence
    decisions = {name: verify_decision(config.resolve(path))
                 for name, path in config.decisions.items()}
    decision = copy.deepcopy(decisions["dynamic_rule_1"][0])
    decision["regimes"]["tiny"]["seeds"].pop()
    decisions["dynamic_rule_1"] = (decision, decisions["dynamic_rule_1"][1])
    with pytest.raises(BenchmarkError, match="three training seeds"):
        inputs.load_dynamic(config, datasets[0].source, decisions)


def test_static_adapter_rejects_duplicate_paired_row(monkeypatch, static_evidence):
    import berth_allocation_lab.benchmark.inputs as inputs

    config, datasets, _ = static_evidence
    source = datasets[0].source
    decisions = {name: verify_decision(config.resolve(path))
                 for name, path in config.decisions.items()}
    path = config.resolve(source.evaluation_path) / "per_instance.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    test_rows = [index for index, line in enumerate(lines)
                 if '"suite": "test"' in line]
    assert len(test_rows) >= 2
    lines[test_rows[1]] = lines[test_rows[0]]
    original = Path.open

    def opened(self, *args, **kwargs):
        if self == path and kwargs.get("encoding") == "utf-8":
            return io.StringIO("".join(lines))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    with pytest.raises(BenchmarkError, match="Duplicate static"):
        inputs.load_static(config, source, decisions)
