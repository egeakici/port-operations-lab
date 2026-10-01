"""Tiny deterministic DFS over the frozen, fixed-order candidate model."""

from __future__ import annotations

from collections import deque
from time import perf_counter

from berth_allocation_lab.core import (
    BAPPlacement,
    NUMERICAL_TOLERANCE,
    find_schedule_violations,
    total_waiting_time,
    waiting_time,
)
from berth_allocation_lab.core.numerics import is_close, is_finite_number
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.policies import StaticFCFS, StaticGreedyRollout
from berth_allocation_lab.policies.base import (
    StaticDecisionRecord,
    StaticScheduleResult,
    candidate_starts,
    ordered_vessels,
    placement_at,
    require_static_scenario,
)
from berth_allocation_lab.solvers.reference_types import (
    SEARCH_LIMIT_FAILURE,
    SEARCH_LIMIT_REASONS,
    CandidateEnumerationConfig,
    CandidateEnumerationDiagnostics,
    CandidateEnumerationResult,
)


class StaticCandidateEnumeration:
    """Exact within candidate space only; no arbitrary positions or sequencing."""

    policy_id = "static_candidate_enumeration_v1"
    policy_family = "reference_solver"
    algorithm_version = "v1"

    def __init__(self, config: CandidateEnumerationConfig | None = None) -> None:
        self.config = config or CandidateEnumerationConfig()

    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        result = self.solve(scenario)
        return StaticScheduleResult(
            self.policy_id, result.best_placements, result.decision_records,
            solver_diagnostics=result.diagnostics,
        )

    def solve(self, scenario: BAPScenarioInstance) -> CandidateEnumerationResult:
        require_static_scenario(scenario)
        started = perf_counter()
        config = self.config
        vessels = ordered_vessels(scenario.vessels)
        nodes = pruned = leaves = 0
        bound = float("inf")
        heuristic = ()
        # Keep record-low leaves within EPS of the current bound. Keeping only
        # one tolerance-tied leaf can lose the first eligible tie as the bound falls.
        frontier: deque[tuple[float, tuple[BAPPlacement, ...]]] = deque()
        lowest_leaf = float("inf")
        reason = None
        failure_type = failure_message = None

        def time_expired() -> bool:
            return (
                config.time_limit_seconds is not None
                and perf_counter() - started >= config.time_limit_seconds
            )

        def search(partial: tuple[BAPPlacement, ...], accumulated: float) -> None:
            nonlocal nodes, pruned, leaves, bound, lowest_leaf, reason
            if reason is not None:
                return
            if time_expired():
                reason = "time_limit"
                return
            if nodes >= config.max_search_nodes:
                reason = "node_limit"
                return
            nodes += 1
            if config.enable_pruning and accumulated > bound + NUMERICAL_TOLERANCE:
                pruned += 1
                return
            if len(partial) == len(vessels):
                leaves += 1
                objective = self._validate_complete(scenario, partial)
                if not is_close(objective, accumulated):
                    raise ValueError("Incremental and canonical objectives disagree.")
                bound = min(bound, objective)
                if objective < lowest_leaf:
                    frontier.append((objective, partial))
                    lowest_leaf = objective
                while frontier and frontier[0][0] > bound + NUMERICAL_TOLERANCE:
                    frontier.popleft()
                if config.stop_at_zero and objective == 0.0:
                    reason = "zero_cost_certificate"
                return
            vessel = vessels[len(partial)]
            choices = candidate_starts(vessel, partial, scenario)
            if not choices:
                raise ValueError(f"No candidate for {vessel.vessel_id}.")
            for position, start in choices:
                if reason is not None:
                    break
                placement = placement_at(vessel, position, start)
                search((*partial, placement), accumulated + waiting_time(vessel, placement))

        chosen = ()
        decisions = ()
        objective = None
        source = None
        status = "failed"
        try:
            if len(vessels) > config.max_vessels:
                reason = "size_limit"
            else:
                if time_expired():
                    reason = "time_limit"
                elif config.initial_incumbent != "none":
                    policy = (
                        StaticFCFS() if config.initial_incumbent == "fcfs"
                        else StaticGreedyRollout()
                    )
                    heuristic = policy.schedule(scenario).placements
                    bound = self._validate_complete(scenario, heuristic)
                    self._decisions(scenario, heuristic)
                if reason is None:
                    search((), 0.0)
                reason = reason or "exhausted"
                if frontier:
                    objective, chosen = frontier[0]
                    source = "dfs_leaf"
                elif heuristic:
                    chosen, objective, source = heuristic, bound, config.initial_incumbent
                if chosen:
                    recomputed = self._validate_complete(scenario, chosen)
                    if not is_close(recomputed, objective):
                        raise ValueError("Selected and canonical objectives disagree.")
                    decisions = self._decisions(scenario, chosen)
                    status = "feasible"
                    if reason in {"exhausted", "zero_cost_certificate"}:
                        if source != "dfs_leaf":
                            raise ValueError("Certification requires a DFS leaf, not a heuristic.")
                        status = "optimal"
                elif reason in SEARCH_LIMIT_REASONS:
                    # A resource stop without incumbent is a recorded search
                    # outcome, not a program error.
                    status = "timeout" if reason == "time_limit" else "failed"
                    failure_type = SEARCH_LIMIT_FAILURE
                    failure_message = f"Search stopped by {reason} before any valid incumbent."
        except Exception as error:
            status, reason = "failed", None
            failure_type, failure_message = type(error).__name__, str(error)
            chosen, decisions, objective, source = (), (), None, None

        diagnostics = CandidateEnumerationDiagnostics(
            scenario_fingerprint=scenario.content_fingerprint,
            optimality_status=status,
            best_feasible_objective=objective,
            certified_optimal_objective=objective if status == "optimal" else None,
            nodes_explored=nodes, branches_pruned=pruned,
            complete_schedules_evaluated=leaves,
            solver_runtime_seconds=perf_counter() - started,
            termination_reason=reason,
            max_vessels=config.max_vessels, max_search_nodes=config.max_search_nodes,
            time_limit_seconds=config.time_limit_seconds,
            initial_incumbent=config.initial_incumbent,
            enable_pruning=config.enable_pruning, stop_at_zero=config.stop_at_zero,
            incumbent_source=source,
            optimality_gap=0.0 if status == "optimal" else None,
            failure_type=failure_type, failure_message=failure_message,
        )
        return CandidateEnumerationResult(chosen, decisions, diagnostics)

    @staticmethod
    def _validate_complete(
        scenario: BAPScenarioInstance,
        placements: tuple[BAPPlacement, ...],
    ) -> float:
        violations = find_schedule_violations(
            scenario.vessels, placements,
            scenario.berth_length_m, scenario.min_clearance_m,
        )
        if violations:
            raise ValueError("; ".join(v.message for v in violations))
        objective = total_waiting_time(scenario.vessels, placements)
        if not is_finite_number(objective):
            raise ValueError("Objective must be finite.")
        return objective

    def _decisions(
        self,
        scenario: BAPScenarioInstance,
        placements: tuple[BAPPlacement, ...],
    ) -> tuple[StaticDecisionRecord, ...]:
        records = []
        partial = ()
        trajectory = zip(ordered_vessels(scenario.vessels), placements, strict=True)
        for index, (vessel, placement) in enumerate(trajectory):
            if placement.vessel_id != vessel.vessel_id:
                raise ValueError("Selected trajectory violates fixed construction order.")
            choices = candidate_starts(vessel, partial, scenario)
            selected = next(
                (j for j, (x, s) in enumerate(choices)
                 if is_close(x, placement.berth_position_m)
                 and is_close(s, placement.berth_start_time_min)),
                None,
            )
            if selected is None:
                raise ValueError("Selected trajectory is outside the frozen candidate model.")
            records.append(StaticDecisionRecord(
                decision_index=index, vessel_id=vessel.vessel_id, policy_id=self.policy_id,
                candidate_count=len(choices), candidate_positions_m=tuple(x for x, _ in choices),
                selected_candidate_index=selected,
                selected_berth_position_m=placement.berth_position_m,
                selected_start_time_min=placement.berth_start_time_min,
                selected_waiting_time_min=waiting_time(vessel, placement),
            ))
            partial = (*partial, placement)
        return tuple(records)
