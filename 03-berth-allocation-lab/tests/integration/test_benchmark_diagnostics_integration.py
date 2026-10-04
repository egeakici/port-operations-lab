"""Read-only Step 12B checks against the frozen completed campaigns."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.diagnostics import build_diagnostics, verify_step12a
from berth_allocation_lab.benchmark.inputs import sha256_file
from berth_allocation_lab.benchmark.latency import fixture_plan, hardware_metadata, measure_latency

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def configs():
    return (BenchmarkConfig.load(ROOT / "configs/benchmark/step12_static.yaml"),
            BenchmarkConfig.load(ROOT / "configs/benchmark/step12_dynamic_h240.yaml"))


@pytest.fixture(scope="module")
def evidence(configs):
    return verify_step12a(configs)


@pytest.fixture(scope="module")
def diagnostics(configs, evidence):
    return build_diagnostics(*configs, evidence)


def test_step12a_outputs_complete_and_hashed(evidence):
    assert set(evidence) == {"static", "dynamic"}
    assert evidence["dynamic"]["summary"]["regimes"][0]["gap_closed_seed_mean"] == pytest.approx(
        0.55852968518)
    assert evidence["dynamic"]["summary"]["regimes"][1]["gap_closed_seed_mean"] == pytest.approx(
        0.26071203406)


def test_missing_part_a_manifest_blocks(monkeypatch, configs):
    missing = ROOT / "experiments/benchmark/step12/missing"
    config = configs[0]
    from dataclasses import replace
    with pytest.raises(BenchmarkError, match="manifest missing"):
        verify_step12a((replace(config, benchmark_id="missing"),))
    assert not missing.exists()


def test_wait_and_agreement_from_locked_records(diagnostics):
    waits = diagnostics["dynamic_wait_summary"]
    assert len(waits) == 5 * 3 * 3
    for row in waits:
        assert row["intentional_waits"] <= row["legal_wait_opportunities"]
        assert row["waits_with_announced"] <= row["intentional_waits"]
        assert row["decisions_with_announced"] <= row["decision_count"]
        if row["method"] == "fcfs":
            assert row["intentional_waits"] == 0
    assert len(diagnostics["dynamic_action_agreement"]) == 15
    assert all(0 <= row["assignment_agreement_same_state"] <= 1
               for row in diagnostics["dynamic_action_agreement"])


def test_tails_traces_and_static_separation(diagnostics):
    assert len(diagnostics["dynamic_selected_traces"]) in range(3, 6)
    assert all(trace["physical_fingerprint"] for trace in
               diagnostics["dynamic_selected_traces"])
    assert all(not row["placements_available"] for row in diagnostics["static_tail_risk"])
    assert all(row["regime"] in {"tiny", "medium_heavy"}
               for row in diagnostics["static_method_comparison"])
    ranked = [r for r in diagnostics["dynamic_worst_cases"] if r["regime"] == "tiny" and
              r["reference"] == "fcfs" and r["training_seed"] == 11 and
              r["ranking"] == "deterioration"]
    assert [r["rank"] for r in ranked] == list(range(1, 6))
    assert [r["paired_delta_min"] for r in ranked] == sorted(
        (r["paired_delta_min"] for r in ranked), reverse=True)


def test_fixture_plan_fixed_and_disjoint_from_test(configs):
    plan = fixture_plan(configs[1], per_family=2)
    assert plan == fixture_plan(configs[1], per_family=2)
    assert len(plan) == 10
    assert all("_validation_seed" in row["scenario_id"] for row in plan)
    assert len({row["physical_fingerprint"] for row in plan}) == 10


def test_completed_outputs_are_immutable_and_sources_unchanged(configs, evidence):
    root = ROOT / "experiments/benchmark/step12b"
    for name in ("locked_diagnostics_v3", "cpu_latency_v2"):
        path = root / name
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "completed"
        assert manifest["training_performed"] is False
        assert manifest["test_inference_performed"] is False
        assert all(sha256_file(path / filename) == digest for filename, digest
                   in manifest["derived_sha256"].items())
    assert verify_step12a(configs)["dynamic"]["manifest_sha256"] == evidence["dynamic"][
        "manifest_sha256"]


@pytest.mark.slow
def test_tiny_bounded_latency_smoke(configs):
    result = measure_latency(configs[1], per_family=1, passes=1)
    assert len(result["fixture_plan"]) == 5
    assert len(result["measurements"]) == 15
    assert len(result["summary"]) == 6
    assert all(row["schedule_valid"] for row in result["measurements"])
    assert sum(row["decision_count"] for row in result["measurements"]) == len(
        result["decision_samples"])
    assert result["manifest"]["hardware"]["device"] == "cpu"
