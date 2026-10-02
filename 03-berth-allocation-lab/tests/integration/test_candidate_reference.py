import json
import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from berth_allocation_lab.cli import main
from berth_allocation_lab.core import NUMERICAL_TOLERANCE as EPS, candidate_positions, earliest_feasible_start
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.evaluation import compare_static_baselines, run_static_policy
from berth_allocation_lab.evaluation.comparison import compare_to_candidate_reference
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator
from berth_allocation_lab.solvers import CandidateEnumerationConfig as Config, StaticCandidateEnumeration as Solver


def read_json(root, name):
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_certified_record_roundtrip_and_path(manual_static_scenario, tmp_path):
    scenario = manual_static_scenario
    result = run_static_policy(scenario, Solver(), tmp_path, run_id="reference")
    root = tmp_path / "reference"
    manifest = read_json(root, "manifest.json")
    summary = read_json(root, "run_summary.json")
    diagnostics = read_json(root, "solver_diagnostics.json")
    restored = BAPScenarioInstance.load_json(root / "scenario.json")
    assert restored == scenario
    assert restored.content_fingerprint == scenario.content_fingerprint
    assert manifest["scenario_fingerprint"] == diagnostics["scenario_fingerprint"] == scenario.content_fingerprint
    assert manifest["scenario_seed"] == summary["seed"] == scenario.seed
    assert manifest["scenario_id"] == diagnostics["scenario_id"] == summary["scenario_id"] == scenario.scenario_id
    assert manifest["policy_id"] == "static_candidate_enumeration_v1"
    assert manifest["policy_family"] == "reference_solver"
    assert manifest["solver_family"] == "exhaustive_enumeration"
    assert manifest["reference_scope"] == summary["reference_scope"] == "candidate_space"
    assert manifest["optimality_status"] == diagnostics["optimality_status"] == "optimal"
    assert manifest["status"] == summary["status"] == "completed"
    assert summary["objective_value"] == diagnostics["certified_optimal_objective"] == 0
    assert summary["optimality_gap"] == 0
    assert read_json(root, "violations.json") == []
    assert read_json(root, "incumbent_metrics.json")["metrics"] is None
    assert "git_commit_hash" in manifest and "git_dirty" in manifest
    assert {v.vessel_id for v in result.vessels} == {v.vessel_id for v in scenario.vessels}
    rows = [json.loads(line) for line in (root / "decisions.jsonl").read_text().splitlines()]
    partial = ()
    for vessel, placement, record in zip(scenario.vessels, result.placements, rows, strict=True):
        candidates = candidate_positions(vessel, partial, scenario.berth_length_m, scenario.min_clearance_m)
        assert record["candidate_positions_m"] == list(candidates)
        assert record["selected_berth_position_m"] == candidates[record["selected_candidate_index"]]
        assert record["selected_start_time_min"] == earliest_feasible_start(
            vessel, placement.berth_position_m, partial, scenario.berth_length_m, scenario.min_clearance_m)
        assert "simulation_time_min" not in record
        partial = (*partial, placement)
    repeated = run_static_policy(restored, Solver())
    assert repeated.placements == result.placements
    assert repeated.summary.objective_value == result.summary.objective_value
    assert repeated.solver_diagnostics.nodes_explored == result.solver_diagnostics.nodes_explored


@pytest.mark.parametrize("incumbent,status", [("none", "failed"), ("fcfs", "completed_with_limit"),
                                              ("rollout", "completed_with_limit")])
def test_cutoff_artifacts_never_supply_certified_metrics(manual_static_scenario, tmp_path, incumbent, status):
    result = run_static_policy(manual_static_scenario, Solver(Config(max_search_nodes=1, initial_incumbent=incumbent)),
                               tmp_path, run_id="limited")
    root = tmp_path / "limited"
    manifest, summary, diagnostics = [read_json(root, name) for name in
                                    ("manifest.json", "run_summary.json", "solver_diagnostics.json")]
    assert manifest["status"] == summary["status"] == status
    assert diagnostics["termination_reason"] == "node_limit"
    assert manifest["failure_type"] == ("search_limit_reached" if incumbent == "none" else None)
    assert manifest["optimality_status"] == ("failed" if incumbent == "none" else "feasible")
    assert summary["objective_value"] is None
    assert summary["total_waiting_time_min"] is None
    assert summary["optimality_gap"] is diagnostics["certified_optimal_objective"] is None
    assert result.summary.is_valid == (incumbent != "none")
    if incumbent != "none":
        assert read_json(root, "incumbent_metrics.json")["metrics"]["objective_value"] == diagnostics["best_feasible_objective"]
        assert summary["vessel_count_completed"] == 3
        assert all(v.completed for v in result.vessels)
        assert read_json(root, "violations.json") == []
    else:
        assert summary["vessel_count_unresolved"] == 3
    fcfs, _ = compare_static_baselines(manual_static_scenario)
    with pytest.raises(ValueError):
        compare_to_candidate_reference(fcfs, result)


def test_size_limit_record_and_error_record(manual_static_scenario, tmp_path, monkeypatch):
    result = run_static_policy(manual_static_scenario, Solver(Config(max_vessels=2)), tmp_path, run_id="size")
    assert result.manifest.status == "failed"
    assert result.solver_diagnostics.termination_reason == "size_limit"
    assert len(read_json(tmp_path / "size", "scenario.json")["vessels"]) == 3
    # Recorded size outcome, not a raised ValueError; no objective or KPIs.
    manifest, summary, diagnostics = [read_json(tmp_path / "size", name) for name in
                                    ("manifest.json", "run_summary.json", "solver_diagnostics.json")]
    assert manifest["failure_type"] == diagnostics["failure_type"] == "size_limit_exceeded"
    assert manifest["optimality_status"] == summary["optimality_status"] == "failed"
    assert summary["validation_status"] == "size_limit_exceeded" and summary["status"] == "failed"
    assert "ValueError" not in manifest["failure_message"]
    for key in ("objective_value", "total_waiting_time_min", "best_feasible_objective",
                "certified_optimal_objective", "berth_utilization"):
        assert summary[key] is None, key
    assert read_json(tmp_path / "size", "violations.json") == []
    from berth_allocation_lab.solvers import candidate_enumeration as module

    def fail(*args):
        raise RuntimeError("controlled core failure")

    monkeypatch.setattr(module, "candidate_starts", fail)
    result = run_static_policy(manual_static_scenario, Solver(Config(initial_incumbent="none")), tmp_path, run_id="error")
    assert result.manifest.status == "failed"
    assert result.solver_diagnostics.optimality_status == "failed"
    assert "controlled core failure" in result.manifest.failure_message
    assert result.summary.certified_optimal_objective is None
    # A genuine error keeps its exception class; it is never a search limit.
    assert result.manifest.failure_type == result.solver_diagnostics.failure_type == "RuntimeError"
    assert result.solver_diagnostics.termination_reason is None
    assert result.summary.validation_status == "exception"


@pytest.mark.parametrize("limit,optimality", [("time_limit", "timeout"), ("node_limit", "failed")])
def test_limit_without_incumbent_is_classified_not_raised(manual_static_scenario, tmp_path, monkeypatch,
                                                         limit, optimality):
    if limit == "time_limit":
        from berth_allocation_lab.solvers import candidate_enumeration as module
        ticks = iter([0])
        monkeypatch.setattr(module, "perf_counter", lambda: next(ticks, 2))
        config = Config(time_limit_seconds=1, initial_incumbent="none")
    else:
        config = Config(max_search_nodes=1, initial_incumbent="none")
    result = run_static_policy(manual_static_scenario, Solver(config), tmp_path, run_id=limit)
    root = tmp_path / limit
    manifest, summary, diagnostics = [read_json(root, name) for name in
                                    ("manifest.json", "run_summary.json", "solver_diagnostics.json")]
    assert manifest["status"] == summary["status"] == "failed"
    assert manifest["failure_type"] == diagnostics["failure_type"] == "search_limit_reached"
    assert manifest["optimality_status"] == summary["optimality_status"] == diagnostics["optimality_status"] == optimality
    assert diagnostics["termination_reason"] == limit
    assert limit in manifest["failure_message"] and "ValueError" not in manifest["failure_message"]
    assert summary["validation_status"] == "search_limit_reached"
    for key in ("objective_value", "total_waiting_time_min", "mean_waiting_time_min", "p95_waiting_time_min",
                "mean_turnaround_time_min", "berth_utilization", "best_feasible_objective",
                "certified_optimal_objective", "optimality_gap"):
        assert summary[key] is None, key
    assert diagnostics["best_feasible_objective"] is diagnostics["certified_optimal_objective"] is None
    assert read_json(root, "violations.json") == []
    assert read_json(root, "incumbent_metrics.json")["metrics"] is None
    assert summary["vessel_count_completed"] == 0 and summary["vessel_count_unresolved"] == 3
    assert not result.summary.is_valid and result.placements == ()


def test_runner_error_is_not_masked_by_limit_diagnostics(manual_static_scenario):
    class WrongScenario(Solver):
        def schedule(self, scenario):
            result = super().schedule(scenario)
            return replace(result, solver_diagnostics=replace(result.solver_diagnostics,
                                                              scenario_fingerprint="other"))

    result = run_static_policy(manual_static_scenario,
                               WrongScenario(Config(max_search_nodes=1, initial_incumbent="none")))
    assert result.manifest.failure_type == result.solver_diagnostics.failure_type == "ValueError"
    assert "different scenario" in result.manifest.failure_message
    assert result.manifest.optimality_status == "failed"


def test_bad_certified_objective_is_not_persisted_as_optimal(manual_static_scenario, tmp_path):
    class CorruptReference(Solver):
        def schedule(self, scenario):
            result = super().schedule(scenario)
            return replace(result, solver_diagnostics=replace(result.solver_diagnostics,
                                                             certified_optimal_objective=123))

    result = run_static_policy(manual_static_scenario, CorruptReference(), tmp_path, run_id="corrupt")
    assert not result.summary.is_valid
    assert result.solver_diagnostics.optimality_status == "failed"
    assert result.summary.certified_optimal_objective is None
    assert read_json(tmp_path / "corrupt", "manifest.json")["optimality_status"] == "failed"


def test_solver_serialization_failure_clears_certification(manual_static_scenario, tmp_path):
    class UnserializableReference(Solver):
        def schedule(self, scenario):
            result = super().schedule(scenario)
            record = replace(result.decision_records[0], selected_score=float("nan"))
            return replace(result, decision_records=(record, *result.decision_records[1:]))

    result = run_static_policy(manual_static_scenario, UnserializableReference(), tmp_path, run_id="serialization")
    root = tmp_path / "serialization"
    for name in ("manifest.json", "run_summary.json", "solver_diagnostics.json"):
        assert read_json(root, name)["optimality_status"] == "failed"
    assert result.summary.objective_value is None
    assert not result.summary.is_valid
    assert result.solver_diagnostics.certified_optimal_objective is None


@pytest.mark.parametrize("seed", [0, 1, 42])
def test_generated_tiny_baseline_inequalities(seed):
    config = SyntheticScenarioConfig.load_yaml(Path(__file__).resolve().parents[2] /
                                               "configs/scenarios/synthetic_tiny_congested.yaml")
    config = replace(config, scenario_id=f"tiny_test_n6_seed{seed}", seed=seed)
    scenario = SyntheticScenarioGenerator().generate(config)
    fcfs, rollout = compare_static_baselines(scenario)
    exact = run_static_policy(scenario, Solver())
    assert exact.scenario is rollout.scenario is fcfs.scenario is scenario
    assert exact.solver_diagnostics.optimality_status == "optimal"
    assert exact.summary.objective_value <= rollout.summary.objective_value + EPS
    assert rollout.summary.objective_value <= fcfs.summary.objective_value + EPS
    assert compare_to_candidate_reference(fcfs, exact).absolute_gap_min >= 0
    assert compare_to_candidate_reference(rollout, exact).absolute_gap_min >= 0
    changed = replace(fcfs, scenario=replace(scenario, scenario_id="different"))
    with pytest.raises(ValueError, match="identical"):
        compare_to_candidate_reference(changed, exact)


def test_cli_json_success_cutoff_and_size_guard(manual_static_scenario, tmp_path, capsys):
    path = tmp_path / "scenario.json"
    manual_static_scenario.save_json(path)
    common = ["--run-candidate-reference", str(path), "--output", str(tmp_path / "runs")]
    assert main(common) == 0
    assert "Certified candidate-space objective" in capsys.readouterr().out
    assert main([*common, "--max-search-nodes", "1"]) == 1
    assert "No certified optimum" in capsys.readouterr().out
    assert main([*common, "--max-vessels", "2"]) == 1
    assert "no truncation" in capsys.readouterr().out


def test_manual_smoke_scenarios_keep_fingerprint_after_json_roundtrip(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/run_candidate_reference_smoke.py"
    fixtures = runpy.run_path(str(script))["manual_scenarios"]
    for scenario in fixtures():
        path = tmp_path / f"{scenario.scenario_id}.json"
        scenario.save_json(path)
        restored = BAPScenarioInstance.load_json(path)
        assert restored.content_fingerprint == scenario.content_fingerprint
