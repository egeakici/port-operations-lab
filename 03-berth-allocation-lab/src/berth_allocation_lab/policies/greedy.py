"""Static one-step waiting-time lookahead over core berth candidates."""

from __future__ import annotations

from berth_allocation_lab.core import BAPPlacement, waiting_time
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.policies.base import (
    StaticDecisionRecord,
    StaticScheduleResult,
    candidate_starts,
    ordered_vessels,
    placement_at,
)


class StaticGreedyLookahead:
    """Evaluate remaining vessels independently for each current candidate."""

    policy_id = "static_greedy_lookahead_v1"
    policy_family = "greedy"
    algorithm_version = "v1"

    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        ordered = ordered_vessels(scenario.vessels)
        placements: list[BAPPlacement] = []
        decisions: list[StaticDecisionRecord] = []
        for index, vessel in enumerate(ordered):
            choices = candidate_starts(vessel, placements, scenario)
            if not choices:
                raise ValueError(f"No candidate for vessel {vessel.vessel_id}.")
            scored: list[tuple[float, float, float]] = []
            for position, start in choices:
                proposed = placement_at(vessel, position, start)
                temporary = (*placements, proposed)
                score = waiting_time(vessel, proposed)
                for future in ordered[index + 1 :]:
                    future_choices = candidate_starts(future, temporary, scenario)
                    if not future_choices:
                        raise ValueError(f"No candidate for vessel {future.vessel_id}.")
                    future_position, future_start = min(
                        future_choices, key=lambda choice: (choice[1], choice[0])
                    )
                    score += waiting_time(
                        future,
                        placement_at(future, future_position, future_start),
                    )
                scored.append((score, start, position))
            selected_index = min(range(len(choices)), key=lambda j: scored[j])
            position, start = choices[selected_index]
            placement = placement_at(vessel, position, start)
            placements.append(placement)
            decisions.append(
                StaticDecisionRecord(
                    decision_index=index,
                    vessel_id=vessel.vessel_id,
                    policy_id=self.policy_id,
                    candidate_count=len(choices),
                    candidate_positions_m=tuple(x for x, _ in choices),
                    selected_candidate_index=selected_index,
                    selected_berth_position_m=position,
                    selected_start_time_min=start,
                    selected_waiting_time_min=waiting_time(vessel, placement),
                    selected_score=scored[selected_index][0],
                )
            )
        return StaticScheduleResult(self.policy_id, tuple(placements), tuple(decisions))
