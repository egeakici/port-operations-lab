from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from app.models import CommandRecord
from app.models import thaw_json_value
from src.terminal_core.integration import IntegrationScenarioResult
from src.terminal_core.terminal_event import TerminalEvent
from src.terminal_core.terminal_state import TerminalState


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def build_overview_metrics(state: TerminalState) -> list[dict[str, Any]]:
    return [
        {"label": "Current time", "value": state.current_time.isoformat()},
        {"label": "Vessels", "value": state.vessel_count},
        {"label": "Berths", "value": state.berth_count},
        {"label": "Quay cranes", "value": state.quay_crane_count},
        {"label": "Yard blocks", "value": state.yard_block_count},
        {"label": "Container groups", "value": state.container_group_count},
        {"label": "Operation tasks", "value": state.operation_task_count},
        {"label": "Events", "value": state.event_count},
    ]


def build_berth_rows(state: TerminalState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for berth_id in state.berth_ids:
        berth = state.get_berth(berth_id)
        if not berth.occupancies:
            rows.append(
                {
                    "berth_id": berth.berth_id,
                    "length_m": berth.length_m,
                    "min_clearance_m": berth.min_clearance_m,
                    "vessel_id": None,
                    "start_position_m": None,
                    "end_position_m": None,
                    "occupancy_count": 0,
                }
            )
            continue

        for occupancy in berth.occupancies:
            rows.append(
                {
                    "berth_id": berth.berth_id,
                    "length_m": berth.length_m,
                    "min_clearance_m": berth.min_clearance_m,
                    "vessel_id": occupancy.vessel.vessel_id,
                    "start_position_m": occupancy.start_position_m,
                    "end_position_m": occupancy.end_position_m,
                    "occupancy_count": berth.occupancy_count,
                }
            )
    return rows


def build_vessel_rows(state: TerminalState) -> list[dict[str, Any]]:
    return [
        {
            "vessel_id": vessel.vessel_id,
            "status": vessel.status.value,
            "length_m": vessel.length_m,
            "eta": vessel.eta.isoformat(),
            "workload_moves": vessel.workload_moves,
            "priority": vessel.priority,
            "max_cranes": vessel.max_cranes,
        }
        for vessel in (
            state.get_vessel(vessel_id)
            for vessel_id in state.vessel_ids
        )
    ]


def build_crane_rows(state: TerminalState) -> list[dict[str, Any]]:
    active_resource_by_crane: dict[str, str] = {}
    for task_id in state.operation_task_ids:
        task = state.get_operation_task(task_id)
        if task.assigned_resource_id:
            active_resource_by_crane[task.assigned_resource_id] = task.task_id

    return [
        {
            "crane_id": crane.crane_id,
            "status": crane.status.value,
            "position_m": crane.position_m,
            "moves_per_hour": crane.moves_per_hour,
            "assigned_vessel_id": crane.assigned_vessel_id,
            "active_task_id": active_resource_by_crane.get(crane.crane_id),
        }
        for crane in (
            state.get_quay_crane(crane_id)
            for crane_id in state.quay_crane_ids
        )
    ]


def build_yard_rows(state: TerminalState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block_id in state.yard_block_ids:
        block = state.get_yard_block(block_id)
        rows.append(
            {
                "block_id": block.block_id,
                "status": block.status.value,
                "capacity_teu": block.capacity_teu,
                "occupied_teu": block.occupied_teu,
                "reserved_teu": block.reserved_teu,
                "available_teu": block.available_teu,
                "planned_occupancy_ratio": round(
                    block.planned_occupancy_ratio,
                    4,
                ),
                "capabilities": ", ".join(
                    sorted(capability.value for capability in block.capabilities)
                ),
                "stored_groups": json.dumps(
                    block.stored_groups,
                    sort_keys=True,
                ),
                "reservations": json.dumps(
                    block.reservations,
                    sort_keys=True,
                ),
            }
        )
    return rows


def build_group_rows(state: TerminalState) -> list[dict[str, Any]]:
    return [
        {
            "group_id": group.group_id,
            "flow": group.flow.value,
            "container_size": group.container_size.value,
            "quantity": group.quantity,
            "total_teu": group.total_teu,
            "load_state": group.load_state.value,
            "reefer": group.is_reefer,
            "hazardous": group.is_hazardous,
            "source_vessel_id": group.source_vessel_id,
            "target_vessel_id": group.target_vessel_id,
        }
        for group in (
            state.get_container_group(group_id)
            for group_id in state.container_group_ids
        )
    ]


def build_cargo_location_rows(state: TerminalState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_id in state.container_group_ids:
        for location in state.locations_for_group(group_id):
            rows.append(
                {
                    "group_id": location.group_id,
                    "location_type": location.location.location_type.value,
                    "location_id": location.location.location_id,
                    "teu": location.teu,
                }
            )
    return rows


def build_task_rows(state: TerminalState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_id in state.operation_task_ids:
        task = state.get_operation_task(task_id)
        rows.append(
            {
                "task_id": task.task_id,
                "status": task.status.value,
                "task_type": task.task_type.value,
                "group_id": task.group_id,
                "planned_teu": task.planned_teu,
                "completed_teu": task.completed_teu,
                "remaining_teu": task.remaining_teu,
                "progress_pct": round(task.progress_ratio * 100.0, 2),
                "assigned_resource_id": task.assigned_resource_id,
                "source": (
                    f"{task.source.location_type.value}:"
                    f"{task.source.location_id}"
                ),
                "target": (
                    f"{task.target.location_type.value}:"
                    f"{task.target.location_id}"
                ),
                "priority": task.priority,
                "release_time": (
                    task.release_time.isoformat()
                    if task.release_time
                    else None
                ),
                "due_time": (
                    task.due_time.isoformat()
                    if task.due_time
                    else None
                ),
                "predecessors": ", ".join(sorted(task.predecessor_task_ids)),
                "blocked_reason": task.blocked_reason,
            }
        )
    return rows


def build_event_rows(
    events: Iterable[TerminalEvent],
) -> list[dict[str, Any]]:
    return [
        {
            "sequence": index,
            "event_id": event.event_id,
            "occurred_at": event.occurred_at.isoformat(),
            "event_type": event.event_type.value,
            "entity_type": event.entity_type.value,
            "entity_id": event.entity_id,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "payload": json.dumps(
                thaw_json_value(event.payload),
                sort_keys=True,
            ),
        }
        for index, event in enumerate(events, start=1)
    ]


def build_command_rows(
    commands: Sequence[CommandRecord],
) -> list[dict[str, Any]]:
    return [
        {
            "sequence": command.sequence,
            "attempted_at": command.attempted_at.isoformat(),
            "command_name": command.command_name,
            "success": command.success,
            "new_events": ", ".join(command.new_event_types),
            "error_type": command.error_type,
            "error_message": command.error_message,
        }
        for command in commands
    ]


def build_scenario_summary(
    result: IntegrationScenarioResult,
) -> dict[str, Any]:
    return {
        "scenario_id": result.scenario_id,
        "started_at": result.started_at.isoformat(),
        "completed_at": result.completed_at.isoformat(),
        "event_count": result.event_count,
        "checkpoint_names": list(result.checkpoint_names),
    }


def build_state_comparison(
    before: TerminalState,
    after: TerminalState,
) -> list[dict[str, Any]]:
    keys = (
        "vessel_count",
        "berth_count",
        "quay_crane_count",
        "yard_block_count",
        "container_group_count",
        "operation_task_count",
    )
    return [
        {
            "metric": key,
            "before": getattr(before, key),
            "after": getattr(after, key),
            "delta": getattr(after, key) - getattr(before, key),
        }
        for key in keys
    ]
