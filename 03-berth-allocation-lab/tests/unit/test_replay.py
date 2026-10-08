"""Deterministic replay state, geometry and incomplete-record contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from berth_allocation_lab.replay.records import (
    ReplayError, ReplayRun, ReplayVessel, _one_run, load_catalog,
)
from berth_allocation_lab.replay.timeline import (
    compare_compatible, decision_context, events_for, index_at_time,
    snapshot, space_time_rectangles, step_index, switch_time,
)
from berth_allocation_lab.replay.visuals import quay_scale, render_quay_svg
from berth_allocation_lab.replay.records import ReplayScenario, ScenarioOption

ROOT = Path(__file__).resolve().parents[2]


def _hand_run(with_history=True):
    vessels = (
        ReplayVessel("V1", 0, 200, 10, 100, 10, 20, 10, 20),
        ReplayVessel("V2", 30, 180, 10, 300, 40, 50, 10, 20),
    )
    records = [
        (0, 0, "VESSEL_ARRIVAL", "V1", None),
        (1, 0, "WAIT", None, 0),
        (2, 10, "ASSIGNMENT", "V1", 1),
        (3, 20, "SERVICE_COMPLETION", "V1", None),
        (4, 20, "HORIZON_ENTRY", "V2", None),
        (5, 30, "VESSEL_ARRIVAL", "V2", None),
        (6, 40, "ASSIGNMENT", "V2", 2),
        (7, 50, "SERVICE_COMPLETION", "V2", None),
    ]
    events = tuple(dict(event_index=i, simulation_time_min=t, event_type=kind,
                        vessel_id=vessel, decision_index=decision)
                   for i, t, kind, vessel, decision in records)
    decisions = (
        {"decision_index": 0, "simulation_time_min": 0, "action_type": "WAIT",
         "selected_vessel_id": None, "selected_berth_position_m": None},
        {"decision_index": 1, "simulation_time_min": 10, "action_type": "ASSIGN",
         "selected_vessel_id": "V1", "selected_berth_position_m": 100},
        {"decision_index": 2, "simulation_time_min": 40, "action_type": "ASSIGN",
         "selected_vessel_id": "V2", "selected_berth_position_m": 300},
    )
    return ReplayRun("ppo", "dynamic_maskable_ppo_v1", 11, "hand", "fingerprint", "test",
                     "fixture", "experiments/fixture.json", "digest", 20, 10, None, None,
                     1, True, vessels, decisions if with_history else None,
                     events if with_history else None)


def test_event_boundaries_hidden_announced_wait_and_half_open():
    run = _hand_run()
    events = events_for(run, 10)
    assert [e.time_min for e in events] == sorted(e.time_min for e in events)
    assert index_at_time(events, 20) == 4
    before = snapshot(run, 10, 20, events, 3)
    after = snapshot(run, 10, 20, events, 4)
    assert "V2" not in before.announced + before.waiting + before.active
    assert after.announced == ("V2",)
    assert "V1" not in before.active
    assert before.completed == ("V1",)
    assert snapshot(run, 10, 30, events).waiting == ("V2",)
    assert snapshot(run, 10, 40, events).active == ("V2",)
    assert snapshot(run, 10, 50, events).active == ()
    decision, state = decision_context(run, 10, 0)
    assert decision["action_type"] == "WAIT" and state.waiting == ("V1",)
    assert state.announced == ()
    assert step_index(events, 3, 1) == 4
    assert step_index(events, 4, -1) == 3
    assert switch_time(events, 20) == 4
    assert switch_time(events, 500) == 7


def test_retrospective_rectangles_and_true_metre_scale():
    run = _hand_run()
    assert space_time_rectangles(run) == (("V1", 100, 300, 10, 20),
                                          ("V2", 300, 480, 40, 50))
    x, width = quay_scale(600, 100, 200)
    assert x == pytest.approx(46 + 908/6)
    assert width == pytest.approx(908/3)
    with pytest.raises(ValueError, match="exceeds"):
        quay_scale(600, 500, 200)
    scenario = ReplayScenario(ScenarioOption("hand", "tiny_n6", 2, "fingerprint", "tiny"),
                              1, 600, 20, 10, {"ppo": run})
    svg = render_quay_svg(scenario, run, snapshot(run, 10, 15))
    assert "width='302.667'" in svg
    assert "stroke-dasharray='3 3'" in svg
    assert "V2" not in svg  # Hidden/future vessels are not rendered on the live quay.


def test_missing_decisions_only_allows_derived_schedule_replay():
    run = _hand_run(with_history=False)
    events = events_for(run, 10)
    assert events and all(e.origin.startswith("derived") for e in events)
    assert snapshot(run, 10, 15, events).active == ("V1",)
    with pytest.raises(ReplayError, match="unavailable"):
        decision_context(run, 10, 0)


def test_policy_comparison_rejects_different_fingerprints():
    run = _hand_run()
    compare_compatible(run, replace(run, method="fcfs"))
    with pytest.raises(ReplayError, match="fingerprint"):
        compare_compatible(run, replace(run, fingerprint="other"))


def test_incomplete_or_invalid_schedule_rejected_without_fabrication():
    row = {"scenario_id": "hand", "method": "dynamic_online_fcfs_v1",
           "status": "completed_valid", "schedule_valid": True, "truncated": False,
           "vessel_count": 1, "vessel_count_completed": 1, "decision_count": 0,
           "placements": [{"vessel_id": "V1", "berth_position_m": 100,
                           "berth_start_time_min": 10, "length_m": 200,
                           "service_time_min": 10}],
           "vessel_results": [{"vessel_id": "V1", "arrival_time_min": 0,
                               "berth_start_time_min": 10, "berth_position_m": 100,
                               "service_end_time_min": 20, "waiting_time_min": 10,
                               "turnaround_time_min": 20}],
           "total_waiting_time_min": 10, "mean_waiting_time_min": 10,
           "physical_fingerprint": "f"}
    source = {"training_seed": 11, "evaluation_path": "experiments/fixture.json",
              "evaluation_sha256": "digest", "experiment_id": "fixture"}
    run = _one_run(row, source, ROOT, "test", 600, 20)
    assert run.decisions is None and run.p95_waiting_time_min is None
    with pytest.raises(ReplayError, match="canonical objective"):
        _one_run({**row, "total_waiting_time_min": 0}, source, ROOT, "test", 600, 20)
    with pytest.raises(ReplayError, match="Invalid physical schedule"):
        _one_run({**row, "placements": [{**row["placements"][0], "berth_position_m": 500}]},
                 source, ROOT, "test", 600, 20)


def test_missing_experiment_directory_is_explicit(tmp_path):
    with pytest.raises(ReplayError, match="unavailable"):
        load_catalog(tmp_path)
