"""Static first-come-first-served vessel order with earliest berth start."""

from __future__ import annotations

from berth_allocation_lab.core import BAPPlacement, waiting_time
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.policies.base import (
    StaticDecisionRecord,
    StaticScheduleResult,
    ordered_vessels,
    require_static_scenario,
    select_fcfs_placement,
)


class StaticFCFS:
    """Select minimum (earliest start, berth position) in arrival/ID order."""

    policy_id = "static_fcfs_v1"
    policy_family = "fcfs"
    algorithm_version = "v1"

    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult:
        require_static_scenario(scenario)
        placements: list[BAPPlacement] = []
        decisions: list[StaticDecisionRecord] = []
        for index, vessel in enumerate(ordered_vessels(scenario.vessels)):
            selection = select_fcfs_placement(vessel, placements, scenario)
            placement = selection.placement
            placements.append(placement)
            decisions.append(
                StaticDecisionRecord(
                    decision_index=index,
                    vessel_id=vessel.vessel_id,
                    policy_id=self.policy_id,
                    candidate_count=len(selection.candidates),
                    candidate_positions_m=tuple(x for x, _ in selection.candidates),
                    selected_candidate_index=selection.candidate_index,
                    selected_berth_position_m=placement.berth_position_m,
                    selected_start_time_min=placement.berth_start_time_min,
                    selected_waiting_time_min=waiting_time(vessel, placement),
                )
            )
        return StaticScheduleResult(self.policy_id, tuple(placements), tuple(decisions))
