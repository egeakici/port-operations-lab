"""Small source-grounded Step 12B diagnostic contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from berth_allocation_lab.benchmark.config import BenchmarkError
from berth_allocation_lab.benchmark.diagnostics import (
    _observable_snapshot, _same_schedule, _selected_traces,
)
from berth_allocation_lab.benchmark.stats import classify


def test_same_cost_need_not_mean_same_schedule():
    a = {"placements": [{"vessel_id": "A", "berth_position_m": 0,
                         "berth_start_time_min": 10}], "total_waiting_time_min": 10}
    b = {"placements": [{"vessel_id": "A", "berth_position_m": 10,
                         "berth_start_time_min": 10}], "total_waiting_time_min": 10}
    assert not _same_schedule(a, b)
    assert _same_schedule(a, a)
    assert classify(a["total_waiting_time_min"] - b["total_waiting_time_min"]) == "tie"


def test_observable_snapshot_excludes_hidden_vessel():
    vessels = [SimpleNamespace(vessel_id="A", arrival_time_min=0),
               SimpleNamespace(vessel_id="B", arrival_time_min=100),
               SimpleNamespace(vessel_id="C", arrival_time_min=500)]
    scenario = SimpleNamespace(vessels=vessels)
    record = {"decision_history": [{"action_type": "ASSIGN", "selected_vessel_id": "A",
                                    "simulation_time_min": 0},
                                   {"action_type": "WAIT", "selected_vessel_id": None,
                                    "simulation_time_min": 20}],
              "placements": [{"vessel_id": "A", "berth_start_time_min": 0,
                              "service_time_min": 100}]}
    snapshot = _observable_snapshot(scenario, record, 1)
    assert snapshot["waiting_vessel_ids"] == []
    assert snapshot["announced_vessel_ids"] == ["B"]
    assert snapshot["active_vessel_ids"] == ["A"]
    assert "C" not in str(snapshot)


def test_intentional_wait_trace_is_not_automatic_advance():
    record = {"decision_history": [{"action_type": "ASSIGN"}, {"action_type": "WAIT"}],
              "event_records": [{"event_type": "AUTOMATIC_ADVANCE"}]}
    assert sum(d["action_type"] == "WAIT" for d in record["decision_history"]) == 1
    assert sum(e["event_type"] == "AUTOMATIC_ADVANCE" for e in record["event_records"]) == 1


def test_case_selection_is_deterministic_and_seed_specific():
    rows = [{"regime": "tiny", "family": "dynamic_tiny_n6", "training_seed": seed,
             "scenario_id": "same", "physical_fingerprint": "fp", "reference": "fcfs",
             "reference_total_min": 10 - delta,
             "paired_delta_min": delta, "intentional_waits": 0,
             "identical_fcfs_schedule": False, "source_evaluation": "source"}
            for seed, delta in ((11, -5), (23, 10), (37, -2))]
    template = {"decision_history": [{"action_type": "ASSIGN", "selected_vessel_id": "A",
                                      "selected_berth_position_m": 0,
                                      "simulation_time_min": 0}],
                "placements": [], "total_waiting_time_min": 10}
    keyed = {("tiny", seed, "same", method): dict(template) for seed in (11, 23, 37)
             for method in ("dynamic_maskable_ppo_v1", "dynamic_online_fcfs_v1")}
    scenario = SimpleNamespace(vessels=[SimpleNamespace(vessel_id="A", arrival_time_min=0)])
    selected = _selected_traces(rows, keyed, {("tiny", "same"): scenario})
    assert [(x["category"], x["training_seed"]) for x in selected] == [
        ("best_fcfs_improvement", 11), ("worst_fcfs_deterioration", 23)]


def test_classification_tolerance_frozen():
    assert classify(1e-6) == "tie"
    assert classify(-1e-6) == "tie"
    assert classify(2e-6) == "loss"
    assert classify(-2e-6) == "win"
