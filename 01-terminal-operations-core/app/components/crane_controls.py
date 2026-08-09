from __future__ import annotations

import streamlit as st

from app import session_store
from app.ui_helpers import date_time_input, run_terminal_command, select_registered
from src.terminal_core.quay_crane import CraneStatus


def _crane_ids_with_status(status: CraneStatus) -> tuple[str, ...]:
    terminal = session_store.get_sandbox_terminal()
    return tuple(
        crane_id
        for crane_id in terminal.quay_crane_ids
        if terminal.get_quay_crane(crane_id).status == status
    )


def render_crane_controls() -> None:
    terminal = session_store.get_sandbox_terminal()
    crane_ids = terminal.quay_crane_ids
    failed_crane_ids = _crane_ids_with_status(CraneStatus.FAILED)
    available_crane_ids = _crane_ids_with_status(CraneStatus.AVAILABLE)
    maintenance_crane_ids = _crane_ids_with_status(CraneStatus.MAINTENANCE)
    st.subheader("Crane Commands")
    left, middle, right = st.columns(3)

    with left:
        with st.form("move_crane_form"):
            crane_id = select_registered(
                "Crane ID",
                crane_ids,
                key="move_crane_id",
                empty_message="No quay cranes are registered yet. Add a quay crane in Terminal Setup.",
            )
            new_position_m = st.number_input(
                "New position (m)",
                min_value=0.0,
                value=100.0,
                step=5.0,
                key="move_crane_position_m",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="move_crane_occurred_at",
            )
            if st.form_submit_button(
                "Move Quay Crane",
                use_container_width=True,
                disabled=crane_id is None,
            ):
                if crane_id is None:
                    return
                run_terminal_command(
                    "MOVE_QUAY_CRANE",
                    {
                        "crane_id": crane_id,
                        "new_position_m": new_position_m,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.move_quay_crane(
                        crane_id,
                        new_position_m,
                        occurred_at=occurred_at,
                    ),
                )

    with middle:
        with st.form("fail_crane_form"):
            crane_id = select_registered(
                "Crane ID",
                crane_ids,
                key="fail_crane_id",
                empty_message="No quay cranes are registered yet. Add a quay crane in Terminal Setup.",
            )
            reason = st.text_input(
                "Failure reason",
                value="Mechanical failure",
                key="fail_crane_reason",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="fail_crane_occurred_at",
            )
            if st.form_submit_button(
                "Fail Quay Crane",
                use_container_width=True,
                disabled=crane_id is None,
            ):
                if crane_id is None:
                    return
                run_terminal_command(
                    "FAIL_QUAY_CRANE",
                    {
                        "crane_id": crane_id,
                        "reason": reason,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.fail_quay_crane(
                        crane_id,
                        reason=reason,
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("repair_crane_form"):
            crane_id = select_registered(
                "Crane ID",
                failed_crane_ids,
                key="repair_crane_id",
                empty_message="No failed quay cranes are available.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="repair_crane_occurred_at",
            )
            if st.form_submit_button(
                "Repair Quay Crane",
                use_container_width=True,
                disabled=crane_id is None,
            ):
                if crane_id is None:
                    return
                run_terminal_command(
                    "REPAIR_QUAY_CRANE",
                    {
                        "crane_id": crane_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.repair_quay_crane(
                        crane_id,
                        occurred_at=occurred_at,
                    ),
                )

    with right:
        with st.form("crane_maintenance_form"):
            action = st.selectbox(
                "Maintenance command",
                options=("start_maintenance", "finish_maintenance"),
                key="crane_maintenance_action",
            )
            maintenance_options = (
                available_crane_ids
                if action == "start_maintenance"
                else maintenance_crane_ids
            )
            empty_message = (
                "No available quay cranes can start maintenance."
                if action == "start_maintenance"
                else "No quay cranes are currently in maintenance."
            )
            crane_id = select_registered(
                "Crane ID",
                maintenance_options,
                key="maintenance_crane_id",
                empty_message=empty_message,
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="maintenance_crane_occurred_at",
            )
            if st.form_submit_button(
                "Apply Crane Maintenance Command",
                use_container_width=True,
                disabled=crane_id is None,
            ):
                if crane_id is None:
                    return
                operations = {
                    "start_maintenance": lambda terminal: terminal.start_quay_crane_maintenance(
                        crane_id,
                        occurred_at=occurred_at,
                    ),
                    "finish_maintenance": lambda terminal: terminal.finish_quay_crane_maintenance(
                        crane_id,
                        occurred_at=occurred_at,
                    ),
                }
                run_terminal_command(
                    f"CRANE_{action.upper()}",
                    {
                        "crane_id": crane_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    operations[action],
                )
