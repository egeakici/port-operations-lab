from __future__ import annotations

from dataclasses import replace

import pytest

from berth_allocation_lab.core import (
    NUMERICAL_TOLERANCE,
    is_schedule_feasible,
    total_waiting_time,
)
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.policies import StaticFCFS, StaticGreedyRollout
from berth_allocation_lab.policies.base import select_fcfs_placement


def test_fcfs_manual_placement_and_waiting(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    result = StaticFCFS().schedule(manual_static_scenario)
    assert [(p.vessel_id, p.berth_position_m, p.berth_start_time_min) for p in result.placements] == [
        ("A", 0.0, 0.0),
        ("B", 110.0, 0.0),
        ("C", 0.0, 1000.0),
    ]
    assert total_waiting_time(manual_static_scenario.vessels, result.placements) == 900.0
    assert is_schedule_feasible(
        manual_static_scenario.vessels,
        result.placements,
        manual_static_scenario.berth_length_m,
        manual_static_scenario.min_clearance_m,
    )


def test_greedy_rollout_strictly_improves_manual_fixture(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    fcfs = StaticFCFS().schedule(manual_static_scenario)
    greedy = StaticGreedyRollout().schedule(manual_static_scenario)

    assert [p.vessel_id for p in greedy.placements] == ["A", "B", "C"]
    assert greedy.placements[0].berth_position_m == 400.0
    assert greedy.placements[1].berth_position_m == 0.0
    assert fcfs.placements[1].berth_position_m == 110.0
    assert fcfs.decision_records[1].candidate_positions_m == (0.0, 110.0, 250.0)
    assert select_fcfs_placement(
        manual_static_scenario.vessels[1],
        fcfs.placements[:1],
        manual_static_scenario,
    ).placement == fcfs.placements[1]
    # A at 400 lets B start at 0, then C fits at 260 after A departs.
    assert greedy.placements[2].berth_position_m == 260.0
    assert greedy.placements[2].berth_start_time_min == 100.0
    assert total_waiting_time(manual_static_scenario.vessels, greedy.placements) == 0.0
    assert (
        total_waiting_time(manual_static_scenario.vessels, greedy.placements)
        < total_waiting_time(manual_static_scenario.vessels, fcfs.placements)
        - NUMERICAL_TOLERANCE
    )
    assert greedy.decision_records[1].selected_score == 0.0
    assert is_schedule_feasible(
        manual_static_scenario.vessels,
        greedy.placements,
        manual_static_scenario.berth_length_m,
        manual_static_scenario.min_clearance_m,
    )


@pytest.mark.parametrize("policy", [StaticFCFS(), StaticGreedyRollout()])
def test_repeated_schedule_is_deterministic_and_input_unchanged(
    manual_static_scenario: BAPScenarioInstance,
    policy: StaticFCFS | StaticGreedyRollout,
) -> None:
    before = manual_static_scenario.to_dict()
    first = policy.schedule(manual_static_scenario)
    second = policy.schedule(manual_static_scenario)
    assert first == second
    assert manual_static_scenario.to_dict() == before
    assert len({p.vessel_id for p in first.placements}) == len(manual_static_scenario.vessels)
    assert all(d.selected_candidate_index < d.candidate_count for d in first.decision_records)
    assert all(d.candidate_positions_m == tuple(sorted(d.candidate_positions_m)) for d in first.decision_records)


@pytest.mark.parametrize("policy", [StaticFCFS(), StaticGreedyRollout()])
def test_arrival_id_order_breaks_ties(
    manual_static_scenario: BAPScenarioInstance,
    policy: StaticFCFS | StaticGreedyRollout,
) -> None:
    vessels = (
        BAPVesselInput("Z", 0.0, 100.0, 30.0),
        BAPVesselInput("A", 0.0, 100.0, 30.0),
        BAPVesselInput("M", 10.0, 100.0, 30.0),
    )
    scenario = replace(manual_static_scenario, vessels=vessels)
    assert [d.vessel_id for d in policy.schedule(scenario).decision_records] == [
        "A", "Z", "M"
    ]


def test_fcfs_uses_leftmost_tie_on_empty_quay(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    scenario = replace(manual_static_scenario, vessels=manual_static_scenario.vessels[:1])
    result = StaticFCFS().schedule(scenario)
    assert result.placements[0].berth_position_m == 0.0
    assert result.decision_records[0].candidate_positions_m == (0.0, 400.0)


def test_greedy_candidate_evaluation_has_no_state_leakage(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    original = manual_static_scenario.to_dict()
    result = StaticGreedyRollout().schedule(manual_static_scenario)
    assert len(result.placements) == 3
    assert [d.decision_index for d in result.decision_records] == [0, 1, 2]
    assert manual_static_scenario.to_dict() == original
    assert all(d.selected_score is not None and d.selected_score >= 0 for d in result.decision_records)


@pytest.mark.parametrize("policy", [StaticFCFS(), StaticGreedyRollout()])
def test_direct_static_policy_api_rejects_dynamic_instance(
    manual_static_scenario: BAPScenarioInstance,
    policy: StaticFCFS | StaticGreedyRollout,
) -> None:
    dynamic = replace(
        manual_static_scenario,
        formulation="dynamic",
        future_horizon_min=240.0,
    )
    with pytest.raises(ValueError, match="static scenario"):
        policy.schedule(dynamic)
