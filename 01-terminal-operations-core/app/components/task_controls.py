from __future__ import annotations

import streamlit as st

from app import session_store
from app.ui_helpers import date_time_input, run_terminal_command, select_registered
from src.terminal_core.operation_task import OperationTaskStatus, OperationType


def _task_ids_with_statuses(statuses: set[OperationTaskStatus]) -> tuple[str, ...]:
    terminal = session_store.get_sandbox_terminal()
    return tuple(
        task_id
        for task_id in terminal.operation_task_ids
        if terminal.get_operation_task(task_id).status in statuses
    )


def _is_ship_side_task(task_id: str | None) -> bool:
    if task_id is None:
        return False
    task = session_store.get_sandbox_terminal().get_operation_task(task_id)
    return task.task_type in {OperationType.DISCHARGE, OperationType.LOAD}


def render_task_controls() -> None:
    terminal = session_store.get_sandbox_terminal()
    st.subheader("Task Lifecycle Commands")
    first, second, third = st.columns(3)

    with first:
        with st.form("task_ready_form"):
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses({OperationTaskStatus.CREATED}),
                key="ready_task_id",
                empty_message="No created tasks are available.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="ready_task_occurred_at",
            )
            if st.form_submit_button(
                "Mark Task Ready",
                use_container_width=True,
                disabled=task_id is None,
            ):
                if task_id is None:
                    return
                run_terminal_command(
                    "MARK_TASK_READY",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    lambda terminal: terminal.mark_task_ready(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_assign_form"):
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses({OperationTaskStatus.READY}),
                key="assign_task_id",
                empty_message="No ready tasks are available.",
            )
            if _is_ship_side_task(task_id):
                resource_id = select_registered(
                    "Resource ID",
                    terminal.quay_crane_ids,
                    key="assign_resource_id",
                    empty_message="No quay cranes are registered yet. Add a quay crane in Terminal Setup.",
                    help="Ship-side tasks must use a registered quay crane.",
                )
            else:
                resource_id = st.text_input(
                    "Resource ID",
                    value="",
                    key="assign_resource_id",
                    help="Generic resource ID for non-ship-side tasks.",
                    disabled=task_id is None,
                )
                resource_id = resource_id.strip() or None
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="assign_task_occurred_at",
            )
            disabled = task_id is None or resource_id is None
            if st.form_submit_button(
                "Assign Task Resource",
                use_container_width=True,
                disabled=disabled,
            ):
                if disabled:
                    return
                run_terminal_command(
                    "ASSIGN_TASK_RESOURCE",
                    {
                        "task_id": task_id,
                        "resource_id": resource_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.assign_task_resource(
                        task_id,
                        resource_id,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_unassign_form"):
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses(
                    {
                        OperationTaskStatus.ASSIGNED,
                        OperationTaskStatus.BLOCKED,
                    }
                ),
                key="unassign_task_id",
                empty_message="No assigned or blocked tasks are available.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="unassign_task_occurred_at",
            )
            if st.form_submit_button(
                "Unassign Task Resource",
                use_container_width=True,
                disabled=task_id is None,
            ):
                if task_id is None:
                    return
                run_terminal_command(
                    "UNASSIGN_TASK_RESOURCE",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    lambda terminal: terminal.unassign_task_resource(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                )

    with second:
        with st.form("task_start_form"):
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses({OperationTaskStatus.ASSIGNED}),
                key="start_task_id",
                empty_message="No assigned tasks are available.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="start_task_occurred_at",
            )
            if st.form_submit_button(
                "Start Task",
                use_container_width=True,
                disabled=task_id is None,
            ):
                if task_id is None:
                    return
                run_terminal_command(
                    "START_TASK",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    lambda terminal: terminal.start_task(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_progress_form"):
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses({OperationTaskStatus.IN_PROGRESS}),
                key="progress_task_id",
                empty_message="No in-progress tasks are available.",
            )
            teu = st.number_input(
                "Progress TEU",
                min_value=0.1,
                value=10.0,
                step=5.0,
                key="progress_teu",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="progress_task_occurred_at",
            )
            if st.form_submit_button(
                "Record Task Progress",
                use_container_width=True,
                disabled=task_id is None,
            ):
                if task_id is None:
                    return
                run_terminal_command(
                    "RECORD_TASK_PROGRESS",
                    {
                        "task_id": task_id,
                        "teu": teu,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.record_task_progress(
                        task_id,
                        teu,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_block_form"):
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses({OperationTaskStatus.IN_PROGRESS}),
                key="block_task_id",
                empty_message="No in-progress tasks are available.",
            )
            reason = st.text_input(
                "Block reason",
                value="Operational hold",
                key="block_reason",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="block_task_occurred_at",
            )
            if st.form_submit_button(
                "Block Task",
                use_container_width=True,
                disabled=task_id is None,
            ):
                if task_id is None:
                    return
                run_terminal_command(
                    "BLOCK_TASK",
                    {
                        "task_id": task_id,
                        "reason": reason,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.block_task(
                        task_id,
                        reason,
                        occurred_at=occurred_at,
                    ),
                )

    with third:
        with st.form("task_resume_form"):
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses({OperationTaskStatus.BLOCKED}),
                key="resume_task_id",
                empty_message="No blocked tasks are available.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="resume_task_occurred_at",
            )
            if st.form_submit_button(
                "Resume Task",
                use_container_width=True,
                disabled=task_id is None,
            ):
                if task_id is None:
                    return
                run_terminal_command(
                    "RESUME_TASK",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    lambda terminal: terminal.resume_task(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_finish_form"):
            action = st.selectbox(
                "Finish command",
                options=("complete", "cancel", "fail"),
                key="task_finish_action",
            )
            eligible_statuses = {
                "complete": {OperationTaskStatus.IN_PROGRESS},
                "cancel": {
                    OperationTaskStatus.CREATED,
                    OperationTaskStatus.READY,
                    OperationTaskStatus.ASSIGNED,
                    OperationTaskStatus.BLOCKED,
                },
                "fail": {
                    OperationTaskStatus.IN_PROGRESS,
                    OperationTaskStatus.BLOCKED,
                },
            }[action]
            task_id = select_registered(
                "Task ID",
                _task_ids_with_statuses(eligible_statuses),
                key="finish_task_id",
                empty_message=f"No tasks are eligible to {action}.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="finish_task_occurred_at",
            )
            if st.form_submit_button(
                "Apply Task Finish Command",
                use_container_width=True,
                disabled=task_id is None,
            ):
                if task_id is None:
                    return
                operations = {
                    "complete": lambda terminal: terminal.complete_task(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                    "cancel": lambda terminal: terminal.cancel_task(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                    "fail": lambda terminal: terminal.fail_task(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                }
                run_terminal_command(
                    f"TASK_{action.upper()}",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    operations[action],
                )
