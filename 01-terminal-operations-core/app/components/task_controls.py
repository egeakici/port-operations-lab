from __future__ import annotations

import streamlit as st

from app import session_store
from app.ui_helpers import date_time_input, run_terminal_command, select_or_text


def render_task_controls() -> None:
    terminal = session_store.get_sandbox_terminal()
    task_ids = terminal.operation_task_ids
    crane_ids = terminal.quay_crane_ids

    st.subheader("Task Lifecycle Commands")
    first, second, third = st.columns(3)

    with first:
        with st.form("task_ready_form"):
            task_id = select_or_text("Task ID", task_ids, key="ready_task_id")
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="ready_task_occurred_at",
            )
            if st.form_submit_button("Mark Task Ready", use_container_width=True):
                run_terminal_command(
                    "MARK_TASK_READY",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    lambda terminal: terminal.mark_task_ready(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_assign_form"):
            task_id = select_or_text("Task ID", task_ids, key="assign_task_id")
            resource_id = select_or_text(
                "Resource ID",
                crane_ids,
                key="assign_resource_id",
                help="For ship-side work this should be a quay crane ID.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="assign_task_occurred_at",
            )
            if st.form_submit_button("Assign Task Resource", use_container_width=True):
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
            task_id = select_or_text("Task ID", task_ids, key="unassign_task_id")
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="unassign_task_occurred_at",
            )
            if st.form_submit_button("Unassign Task Resource", use_container_width=True):
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
            task_id = select_or_text("Task ID", task_ids, key="start_task_id")
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="start_task_occurred_at",
            )
            if st.form_submit_button("Start Task", use_container_width=True):
                run_terminal_command(
                    "START_TASK",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    lambda terminal: terminal.start_task(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_progress_form"):
            task_id = select_or_text("Task ID", task_ids, key="progress_task_id")
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
            if st.form_submit_button("Record Task Progress", use_container_width=True):
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
            task_id = select_or_text("Task ID", task_ids, key="block_task_id")
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
            if st.form_submit_button("Block Task", use_container_width=True):
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
            task_id = select_or_text("Task ID", task_ids, key="resume_task_id")
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="resume_task_occurred_at",
            )
            if st.form_submit_button("Resume Task", use_container_width=True):
                run_terminal_command(
                    "RESUME_TASK",
                    {"task_id": task_id, "occurred_at": occurred_at.isoformat()},
                    lambda terminal: terminal.resume_task(
                        task_id,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("task_finish_form"):
            task_id = select_or_text("Task ID", task_ids, key="finish_task_id")
            action = st.selectbox(
                "Finish command",
                options=("complete", "cancel", "fail"),
                key="task_finish_action",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="finish_task_occurred_at",
            )
            if st.form_submit_button("Apply Task Finish Command", use_container_width=True):
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

