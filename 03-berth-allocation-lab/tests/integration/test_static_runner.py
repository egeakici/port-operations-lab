from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from berth_allocation_lab.core import BAPPlacement
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.evaluation import compare_static_baselines, run_static_policy
from berth_allocation_lab.policies import (
    StaticFCFS,
    StaticScheduleResult,
)
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator


class InvalidPolicy:
    policy_id = "broken_static_v1"
    policy_family = "test"
    algorithm_version = "v1"

    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        a, b, c = scenario.vessels
        return StaticScheduleResult(
            self.policy_id,
            (
                BAPPlacement(a.vessel_id, 0.0, 0.0, a.length_m, a.service_time_min),
                BAPPlacement(b.vessel_id, 0.0, 0.0, b.length_m, b.service_time_min),
                BAPPlacement(c.vessel_id, 0.0, 100.0, c.length_m, c.service_time_min),
            ),
            (),
        )


class CrashingPolicy(InvalidPolicy):
    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        raise RuntimeError("deliberate test failure")


class UnserializablePolicy(StaticFCFS):
    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        result = super().schedule(scenario)
        corrupted = replace(result.decision_records[0], selected_score=float("nan"))
        return replace(
            result,
            decision_records=(corrupted, *result.decision_records[1:]),
        )


def test_recorder_round_trip_and_metadata(
    manual_static_scenario: BAPScenarioInstance,
    tmp_path: Path,
) -> None:
    result = run_static_policy(
        manual_static_scenario, StaticFCFS(), tmp_path, run_id="fixed_run_001"
    )
    run_dir = tmp_path / "fixed_run_001"
    assert result.summary.is_valid
    assert {p.name for p in run_dir.iterdir()} == {
        "manifest.json", "scenario.json", "decisions.jsonl", "placements.jsonl",
        "vessels.jsonl", "violations.json", "run_summary.json",
    }
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    scenario = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    decisions = [json.loads(line) for line in (run_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    vessels = [json.loads(line) for line in (run_dir / "vessels.jsonl").read_text(encoding="utf-8").splitlines()]
    assert manifest["run_id"] == "fixed_run_001"
    assert manifest["scenario_seed"] == manual_static_scenario.seed
    assert manifest["scenario_fingerprint"] == manual_static_scenario.content_fingerprint
    assert manifest["policy_id"] == "static_fcfs_v1"
    assert manifest["status"] == "completed"
    assert manifest["metric_version"] == "static_metrics_v1_type7"
    assert manifest["percentile_method"] == "type7_linear"
    assert manifest["scenario_split"] == manual_static_scenario.split
    assert manifest["project_version"]
    assert manifest["data_provenance"] == manual_static_scenario.data_provenance
    assert scenario == manual_static_scenario.to_dict()
    assert summary["objective_value"] == 900.0
    assert summary["simulation_end_time_min"] == 1100.0
    assert "schedule_end_time_min" not in summary
    assert summary["occupied_quay_length_minutes"] == 280000.0
    assert summary["utilization_window_min"] == 1100.0
    assert len(decisions) == len(vessels) == 3
    assert decisions[1]["decision_index"] == 1
    assert decisions[1]["record_schema_version"] == 1
    assert decisions[1]["run_id"] == "fixed_run_001"
    assert decisions[1]["scenario_id"] == manual_static_scenario.scenario_id
    assert "simulation_time_min" not in decisions[1]
    assert vessels[2]["waiting_time_min"] == 900.0
    assert all(v["completion_status"] == "completed" for v in vessels)


def test_fixed_run_id_cannot_overwrite_existing_artifacts(
    manual_static_scenario: BAPScenarioInstance,
    tmp_path: Path,
) -> None:
    run_static_policy(manual_static_scenario, StaticFCFS(), tmp_path, run_id="fixed")
    with pytest.raises(FileExistsError):
        run_static_policy(manual_static_scenario, StaticFCFS(), tmp_path, run_id="fixed")


def test_utf8_scenario_identity_round_trips_in_artifacts(
    manual_static_scenario: BAPScenarioInstance,
    tmp_path: Path,
) -> None:
    scenario = replace(manual_static_scenario, scenario_id="sc\u00e9nario")
    run_static_policy(scenario, StaticFCFS(), tmp_path, run_id="utf8")
    payload = (tmp_path / "utf8" / "manifest.json").read_bytes()
    assert "sc\u00e9nario".encode("utf-8") in payload
    assert json.loads(payload)["scenario_id"] == scenario.scenario_id


def test_invalid_policy_is_recorded_without_valid_kpis(
    manual_static_scenario: BAPScenarioInstance,
    tmp_path: Path,
) -> None:
    result = run_static_policy(
        manual_static_scenario, InvalidPolicy(), tmp_path, run_id="invalid_run"
    )
    assert not result.summary.is_valid
    assert result.summary.total_waiting_time_min is None
    assert result.manifest.status == "failed"
    assert result.summary.violation_count > 0
    assert result.summary.vessel_count_unresolved == 0
    assert result.summary.vessel_count_completed == 0
    assert result.violations
    assert result.vessels[0].berth_start_time_min == 0.0
    assert result.vessels[0].waiting_time_min is None
    assert result.vessels[0].completion_status == "failed"
    assert json.loads((tmp_path / "invalid_run" / "manifest.json").read_text())["failure_type"] == "invalid_schedule"
    assert json.loads((tmp_path / "invalid_run" / "violations.json").read_text())


def test_policy_exception_is_visible_and_keeps_source_scenario(
    manual_static_scenario: BAPScenarioInstance,
    tmp_path: Path,
) -> None:
    result = run_static_policy(
        manual_static_scenario, CrashingPolicy(), tmp_path, run_id="crash_run"
    )
    assert result.manifest.status == "failed"
    assert result.manifest.failure_type == "RuntimeError"
    assert result.summary.vessel_count_unresolved == 3
    assert result.summary.objective_value is None
    assert (tmp_path / "crash_run" / "scenario.json").exists()


def test_serialization_failure_updates_manifest_and_summary(
    manual_static_scenario: BAPScenarioInstance,
    tmp_path: Path,
) -> None:
    result = run_static_policy(
        manual_static_scenario, UnserializablePolicy(), tmp_path,
        run_id="serialization_failure_run",
    )
    assert not result.summary.is_valid
    assert result.manifest.failure_type == "serialization_failure"
    run_dir = tmp_path / "serialization_failure_run"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    summary = json.loads((run_dir / "run_summary.json").read_text())
    assert manifest["status"] == summary["status"] == "failed"
    assert summary["total_waiting_time_min"] is None
    vessel_rows = [
        json.loads(line)
        for line in (run_dir / "vessels.jsonl").read_text().splitlines()
    ]
    assert all(not row["completed"] for row in vessel_rows)


def test_missing_placement_is_recorded_as_unresolved(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    class MissingPolicy(StaticFCFS):
        def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
            full = super().schedule(scenario)
            return replace(full, placements=full.placements[:-1])

    result = run_static_policy(manual_static_scenario, MissingPolicy())
    assert result.manifest.status == "invalid_unresolved_vessels"
    assert result.summary.vessel_count_unresolved == 1
    assert result.summary.objective_value is None
    assert [v.completion_status for v in result.vessels] == [
        "failed", "failed", "unresolved"
    ]


def test_duplicate_placement_is_ambiguous_not_completed(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    class DuplicatePolicy(StaticFCFS):
        def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
            full = super().schedule(scenario)
            return replace(full, placements=(*full.placements, full.placements[1]))

    result = run_static_policy(manual_static_scenario, DuplicatePolicy())
    assert not result.summary.is_valid
    assert result.summary.vessel_count_unresolved == 1
    assert result.vessels[1].completion_status == "unresolved"
    assert result.vessels[1].berth_position_m is None


def test_dynamic_instance_is_rejected_without_relabeling(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    dynamic = replace(manual_static_scenario, formulation="dynamic", future_horizon_min=240.0)
    with pytest.raises(ValueError, match="static scenario"):
        run_static_policy(dynamic, StaticFCFS())


def test_one_generated_instance_is_shared_by_both_policies() -> None:
    config = SyntheticScenarioConfig.load_yaml(
        Path(__file__).resolve().parents[2] / "configs/scenarios/synthetic_low.yaml"
    )
    scenario = SyntheticScenarioGenerator().generate(config)
    fcfs, greedy = compare_static_baselines(scenario)
    assert fcfs.scenario is greedy.scenario is scenario
    assert fcfs.manifest.scenario_id == greedy.manifest.scenario_id
    assert fcfs.manifest.scenario_seed == greedy.manifest.scenario_seed
    assert fcfs.manifest.scenario_fingerprint == greedy.manifest.scenario_fingerprint
    assert fcfs.manifest.policy_id != greedy.manifest.policy_id
    assert fcfs.summary.is_valid and greedy.summary.is_valid


def test_static_twin_preserves_generated_vessels() -> None:
    config = SyntheticScenarioConfig.load_yaml(
        Path(__file__).resolve().parents[2] / "configs/scenarios/synthetic_medium.yaml"
    )
    generator = SyntheticScenarioGenerator()
    dynamic = generator.generate(config)
    static = generator.generate(config.with_formulation("static"))
    assert dynamic.vessels == static.vessels
    assert dynamic.formulation == "dynamic"
    assert static.formulation == "static"
    assert dynamic.content_fingerprint != static.content_fingerprint
    assert all(r.summary.is_valid for r in compare_static_baselines(static))
