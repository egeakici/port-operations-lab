from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terminal_core.integration import (
    REFERENCE_BACKUP_CRANE_ID,
    REFERENCE_DISCHARGE_TASK_ID,
    REFERENCE_GROUP_ID,
    REFERENCE_INBOUND_VESSEL_ID,
    REFERENCE_LOAD_TASK_ID,
    REFERENCE_OUTBOUND_VESSEL_ID,
    REFERENCE_PRIMARY_CRANE_ID,
    IntegrationCheckpoint,
    run_reference_scenario,
)
from terminal_core.operation_task import TaskLocationType


def main() -> None:
    result = run_reference_scenario()
    final_state = result.final_state

    print(f"Scenario: {result.scenario_id}")
    print(f"Started: {result.started_at}")
    print(f"Completed: {result.completed_at}")
    print(f"Events: {result.event_count}")
    print()

    print("Checkpoints:")
    for checkpoint in IntegrationCheckpoint:
        print(f"- {checkpoint.value}")
    print()

    print("Final vessels:")
    for vessel_id in (
        REFERENCE_INBOUND_VESSEL_ID,
        REFERENCE_OUTBOUND_VESSEL_ID,
    ):
        vessel = final_state.get_vessel(vessel_id)
        print(f"- {vessel.vessel_id}: {vessel.status.value}")
    print()

    print("Final cranes:")
    for crane_id in (
        REFERENCE_PRIMARY_CRANE_ID,
        REFERENCE_BACKUP_CRANE_ID,
    ):
        crane = final_state.get_quay_crane(crane_id)
        print(f"- {crane.crane_id}: {crane.status.value}")
    print()

    print("Completed tasks:")
    for task_id in (
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_LOAD_TASK_ID,
    ):
        task = final_state.get_operation_task(task_id)
        print(f"- {task.task_id}: {task.status.value}")
    print()

    final_teu = final_state.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.VESSEL,
        REFERENCE_OUTBOUND_VESSEL_ID,
    )
    print("Final cargo location:")
    print(
        f"- {REFERENCE_GROUP_ID}: {final_teu} TEU on "
        f"{REFERENCE_OUTBOUND_VESSEL_ID}"
    )


if __name__ == "__main__":
    main()
