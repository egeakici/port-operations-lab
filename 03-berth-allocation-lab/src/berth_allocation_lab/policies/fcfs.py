"""Static first-come-first-served vessel order with earliest berth start."""

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


class StaticFCFS:
    """Select minimum (earliest start, berth position) in arrival/ID order."""

    policy_id = "static_fcfs_v1"
    policy_family = "fcfs"
    algorithm_version = "v1"

    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        placements: list[BAPPlacement] = []
        decisions: list[StaticDecisionRecord] = []
        for index, vessel in enumerate(ordered_vessels(scenario.vessels)):
            choices = candidate_starts(vessel, placements, scenario)
            if not choices:
                raise ValueError(f"No candidate for vessel {vessel.vessel_id}.")
            selected_index = min(
                range(len(choices)),
                key=lambda choice_index: (
                    choices[choice_index][1],
                    choices[choice_index][0],
                ),
            )
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
                )
            )
        return StaticScheduleResult(self.policy_id, tuple(placements), tuple(decisions))
