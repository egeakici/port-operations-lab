from dataclasses import asdict, replace

import pytest

from berth_allocation_lab.core import (
    BAPPlacement, NUMERICAL_TOLERANCE as EPS, candidate_positions,
    earliest_feasible_start, is_schedule_feasible, total_waiting_time,
)
from berth_allocation_lab.data import BAPVesselInput as Vessel
from berth_allocation_lab.evaluation.comparison import candidate_space_reference_gap
from berth_allocation_lab.policies import StaticFCFS, StaticGreedyRollout
from berth_allocation_lab.solvers import CandidateEnumerationConfig as Config, StaticCandidateEnumeration as Solver


def independent_leaves(scenario):
    """Unpruned test oracle using only Step 5, not solver/policy search helpers."""
    vessels = sorted(scenario.vessels, key=lambda v: (v.arrival_time_min, v.vessel_id))

    def enumerate_suffix(partial):
        if len(partial) == len(vessels):
            yield total_waiting_time(scenario.vessels, partial), partial
            return
        vessel = vessels[len(partial)]
        for x in candidate_positions(vessel, partial, scenario.berth_length_m, scenario.min_clearance_m):
            start = earliest_feasible_start(vessel, x, partial, scenario.berth_length_m, scenario.min_clearance_m)
            placement = BAPPlacement(vessel.vessel_id, x, start, vessel.length_m, vessel.service_time_min)
            yield from enumerate_suffix((*partial, placement))

    return list(enumerate_suffix(()))


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
def test_independent_enumeration_coverage_and_ties(manual_static_scenario, count):
    scenario = replace(manual_static_scenario, scenario_id=f"tiny_fractional_{count}",
                       berth_length_m=300.5, min_clearance_m=10.25,
                       vessels=tuple(Vessel(chr(65+i), i * 0.25, 160.125 if i % 2 else 130.125,
                                            4.5 + i) for i in range(count)))
    leaves = independent_leaves(scenario)
    minimum = min(cost for cost, _ in leaves)
    first = next(path for cost, path in leaves if cost <= minimum + EPS)
    solver = Solver(Config(initial_incumbent="none", enable_pruning=False, stop_at_zero=False))
    snapshot = scenario.to_dict()
    result = solver.solve(scenario)
    assert result.diagnostics.optimality_status == "optimal"
    assert result.diagnostics.termination_reason == "exhausted"
    assert result.diagnostics.complete_schedules_evaluated == len(leaves)
    assert result.diagnostics.certified_optimal_objective == pytest.approx(minimum, abs=EPS)
    assert result.best_placements == first
    assert is_schedule_feasible(scenario.vessels, first, scenario.berth_length_m, scenario.min_clearance_m)
    assert scenario.to_dict() == snapshot
    again = solver.solve(scenario)
    assert again.best_placements == result.best_placements
    assert again.decision_records == result.decision_records
    first_stats, second_stats = asdict(result.diagnostics), asdict(again.diagnostics)
    first_stats.pop("solver_runtime_seconds")
    second_stats.pop("solver_runtime_seconds")
    assert first_stats == second_stats
    bounded = Solver(Config(stop_at_zero=False)).solve(scenario)
    assert bounded.best_placements == first
    assert bounded.diagnostics.certified_optimal_objective == result.diagnostics.certified_optimal_objective


@pytest.mark.parametrize("length, expected", [(240, 0), (260, 7.5)])
def test_hand_calculated_two_vessels(manual_static_scenario, length, expected):
    scenario = replace(manual_static_scenario, scenario_id=f"two_{length}", min_clearance_m=20,
                       vessels=(Vessel("B", 0, length, 12), Vessel("A", 0, 240, 7.5)))
    result = Solver().solve(scenario)
    assert [p.vessel_id for p in result.best_placements] == ["A", "B"]
    assert result.diagnostics.certified_optimal_objective == expected
    assert result.diagnostics.termination_reason == ("zero_cost_certificate" if expected == 0 else "exhausted")
    if expected == 0:
        assert result.best_placements[1].berth_position_m == 260


def test_regenerates_candidates_and_prunes(manual_static_scenario, monkeypatch):
    from berth_allocation_lab.solvers import candidate_enumeration as module
    original = module.candidate_starts
    seen = []

    def spy(vessel, partial, scenario):
        choices = original(vessel, partial, scenario)
        if len(partial) == 1:
            seen.append((partial[0].berth_position_m, tuple(x for x, _ in choices)))
        return choices

    monkeypatch.setattr(module, "candidate_starts", spy)
    result = Solver(Config(initial_incumbent="none", stop_at_zero=False)).solve(manual_static_scenario)
    assert len({x for x, _ in seen}) == 2
    assert len({choices for _, choices in seen}) == 2
    assert result.diagnostics.branches_pruned > 0
    assert result.diagnostics.certified_optimal_objective == 0


def test_heuristic_zero_bound_does_not_choose_heuristic_tie(manual_static_scenario):
    scenario = manual_static_scenario
    heuristic = StaticGreedyRollout().schedule(scenario)
    result = Solver(Config(initial_incumbent="rollout")).solve(scenario)
    independent = independent_leaves(scenario)
    first_zero = next(path for cost, path in independent if cost == 0)
    assert result.best_placements == first_zero
    assert result.best_placements != heuristic.placements
    assert result.diagnostics.incumbent_source == "dfs_leaf"
    assert result.diagnostics.complete_schedules_evaluated >= 1


def test_fixed_construction_order_is_not_start_chronology(manual_static_scenario):
    scenario = replace(manual_static_scenario, scenario_id="nonchronological",
                       vessels=(Vessel("A", 0, 300, 100), Vessel("B", 0, 300, 100),
                                Vessel("C", 1, 180, 10)))
    result = Solver().solve(scenario)
    assert [p.vessel_id for p in result.best_placements] == ["A", "B", "C"]
    assert [p.berth_start_time_min for p in result.best_placements] == [0, 100, 1]
    assert result.diagnostics.certified_optimal_objective == 100


@pytest.mark.parametrize("incumbent,status", [("none", "failed"), ("fcfs", "feasible"), ("rollout", "feasible")])
def test_node_limit_never_certifies(manual_static_scenario, incumbent, status):
    result = Solver(Config(max_search_nodes=1, initial_incumbent=incumbent)).solve(manual_static_scenario)
    assert result.diagnostics.optimality_status == status
    assert result.diagnostics.termination_reason == "node_limit"
    assert result.diagnostics.nodes_explored == 1
    assert result.diagnostics.certified_optimal_objective is None
    assert result.diagnostics.optimality_gap is None
    with pytest.raises(ValueError, match="certified"):
        candidate_space_reference_gap(900, result.diagnostics)


def test_cutoff_after_leaf_returns_dfs_incumbent(manual_static_scenario):
    result = Solver(Config(max_search_nodes=4, initial_incumbent="none")).solve(manual_static_scenario)
    assert result.diagnostics.optimality_status == "feasible"
    assert result.diagnostics.complete_schedules_evaluated == 1
    assert result.diagnostics.incumbent_source == "dfs_leaf"


@pytest.mark.parametrize("after_heuristic", [False, True])
def test_time_limit_with_controlled_clock(manual_static_scenario, monkeypatch, after_heuristic):
    from berth_allocation_lab.solvers import candidate_enumeration as module
    ticks = iter([0, 0 if after_heuristic else 2])
    monkeypatch.setattr(module, "perf_counter", lambda: next(ticks, 2))
    result = Solver(Config(time_limit_seconds=1)).solve(manual_static_scenario)
    assert result.diagnostics.termination_reason == "time_limit"
    assert result.diagnostics.optimality_status == ("feasible" if after_heuristic else "failed")
    assert result.diagnostics.certified_optimal_objective is None


def test_size_limit_and_static_guard(manual_static_scenario):
    result = Solver(Config(max_vessels=2)).solve(manual_static_scenario)
    assert result.diagnostics.termination_reason == "size_limit"
    assert result.diagnostics.optimality_status == "failed"
    assert result.diagnostics.nodes_explored == 0
    assert result.best_placements == ()
    with pytest.raises(ValueError, match="static"):
        Solver().solve(replace(manual_static_scenario, formulation="dynamic"))


@pytest.mark.parametrize("kwargs", [dict(max_vessels=9), dict(max_vessels=True),
    dict(max_search_nodes=0), dict(max_search_nodes=float("inf")),
    dict(time_limit_seconds=float("nan")), dict(time_limit_seconds=0),
    dict(initial_incumbent="other"), dict(enable_pruning=1)])
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)


def test_objective_recomputation_error_is_failed(manual_static_scenario, monkeypatch):
    from berth_allocation_lab.solvers import candidate_enumeration as module
    original = module.total_waiting_time
    monkeypatch.setattr(module, "total_waiting_time", lambda *args: original(*args) + 1)
    result = Solver(Config(initial_incumbent="none")).solve(manual_static_scenario)
    assert result.diagnostics.optimality_status == "failed"
    assert result.diagnostics.certified_optimal_objective is None
    assert "disagree" in result.diagnostics.failure_message


def test_gap_zero_positive_and_invalid(manual_static_scenario):
    ref = Solver().solve(manual_static_scenario).diagnostics
    assert candidate_space_reference_gap(900, ref).relative_gap is None
    assert candidate_space_reference_gap(0, ref).relative_gap == 0
    positive = replace(ref, best_feasible_objective=100, certified_optimal_objective=100)
    assert candidate_space_reference_gap(150, positive).relative_gap == 0.5
    assert candidate_space_reference_gap(150, positive).absolute_gap_min == 50
    with pytest.raises(ValueError, match="beats"):
        candidate_space_reference_gap(99, positive)
    for value in (float("inf"), float("nan"), -1):
        with pytest.raises(ValueError):
            candidate_space_reference_gap(value, ref)


def test_baseline_inequalities(manual_static_scenario):
    scenario = manual_static_scenario
    exact = Solver().solve(scenario).diagnostics.certified_optimal_objective
    rollout = total_waiting_time(scenario.vessels, StaticGreedyRollout().schedule(scenario).placements)
    fcfs = total_waiting_time(scenario.vessels, StaticFCFS().schedule(scenario).placements)
    assert exact <= rollout + EPS <= fcfs + 2 * EPS
    assert exact == rollout == 0
    assert fcfs == 900


def test_tolerance_ties_track_first_leaf_as_minimum_falls(manual_static_scenario, monkeypatch):
    """Isolate numerical tie bookkeeping with controlled non-negative costs."""
    from berth_allocation_lab.solvers import candidate_enumeration as module
    scenario = replace(manual_static_scenario, scenario_id="tie_chain",
                       vessels=(Vessel("A", 0, 100, 100), Vessel("B", 0, 100, 100)))
    costs = {0: 10, 110: 10 - 0.75 * EPS, 290: 20, 400: 10 - 1.5 * EPS}
    monkeypatch.setattr(module, "waiting_time", lambda vessel, p: 0 if vessel.vessel_id == "A" else costs[p.berth_position_m])
    monkeypatch.setattr(module, "total_waiting_time", lambda vessels, placements: costs[placements[1].berth_position_m])
    result = Solver(Config(initial_incumbent="none", stop_at_zero=False)).solve(scenario)
    assert result.diagnostics.optimality_status == "optimal"
    assert [p.berth_position_m for p in result.best_placements] == [0, 110]


def test_non_candidate_heuristic_cannot_supply_bound(manual_static_scenario, monkeypatch):
    original = StaticFCFS.schedule

    def invalid_trajectory(self, scenario):
        result = original(self, scenario)
        # A feasible translated single-vessel schedule is not necessarily a
        # member of the frozen boundary-candidate representation.
        return replace(result, placements=(replace(result.placements[0], berth_position_m=123),))

    scenario = replace(manual_static_scenario, scenario_id="one_non_candidate",
                       vessels=(Vessel("A", 0, 100, 100),))
    monkeypatch.setattr(StaticFCFS, "schedule", invalid_trajectory)
    result = Solver().solve(scenario)
    assert result.diagnostics.optimality_status == "failed"
    assert "outside" in result.diagnostics.failure_message
