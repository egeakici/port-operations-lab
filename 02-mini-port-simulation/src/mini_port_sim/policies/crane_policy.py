from __future__ import annotations

from dataclasses import dataclass

from terminal_core import CraneStatus, OperationTaskStatus, Terminal


@dataclass(frozen=True)
class CraneTaskAssignment:
    task_id: str
    crane_id: str
    active_crane_count: int
    productivity_factor: float


class GreedyCranePolicy:
    def choose(
        self,
        terminal: Terminal,
        *,
        vessel_id: str,
        task_ids: tuple[str, ...],
        productivity_factor: float = 1.0,
    ) -> tuple[CraneTaskAssignment, ...]:
        vessel = terminal.get_vessel(vessel_id)
        ready_task_ids = tuple(
            task_id
            for task_id in task_ids
            if terminal.get_operation_task(task_id).status
            == OperationTaskStatus.READY
        )
        available_crane_ids = tuple(
            crane_id
            for crane_id in terminal.quay_crane_ids
            if terminal.get_quay_crane(crane_id).status
            == CraneStatus.AVAILABLE
        )
        current_vessel_crane_count = sum(
            1
            for crane_id in terminal.quay_crane_ids
            if terminal.get_quay_crane(crane_id).assigned_vessel_id
            == vessel_id
        )
        spare_vessel_crane_capacity = max(
            0,
            vessel.max_cranes - current_vessel_crane_count,
        )
        assignment_count = min(
            len(ready_task_ids),
            len(available_crane_ids),
            spare_vessel_crane_capacity,
        )

        if assignment_count <= 0:
            return ()

        active_crane_count = current_vessel_crane_count + assignment_count

        return tuple(
            CraneTaskAssignment(
                task_id=task_id,
                crane_id=crane_id,
                active_crane_count=active_crane_count,
                productivity_factor=productivity_factor,
            )
            for task_id, crane_id in zip(
                ready_task_ids[:assignment_count],
                available_crane_ids[:assignment_count],
            )
        )
