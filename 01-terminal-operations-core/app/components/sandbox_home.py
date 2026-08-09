from __future__ import annotations

import streamlit as st

from app import session_store
from app.components.state_views import render_overview_metrics
from app.ui_helpers import date_time_input, render_last_feedback, run_terminal_command


def _recommended_actions() -> list[str]:
    terminal = session_store.get_sandbox_terminal()
    state = terminal.snapshot()
    actions: list[str] = []

    if not (
        state.berth_count
        and state.vessel_count
        and state.quay_crane_count
        and state.yard_block_count
    ):
        return ["Add infrastructure in Terminal Setup."]

    for vessel_id in state.vessel_ids:
        vessel = state.get_vessel(vessel_id)
        if vessel.status.value == "approaching":
            actions.append(f"{vessel.vessel_id}: arrive vessel.")
        elif vessel.status.value == "waiting":
            actions.append(f"{vessel.vessel_id}: berth vessel.")
        elif vessel.status.value == "operating":
            actions.append(f"{vessel.vessel_id}: depart when ship-side work is complete.")

    for crane_id in state.quay_crane_ids:
        crane = state.get_quay_crane(crane_id)
        if crane.status.value == "failed":
            actions.append(f"{crane.crane_id}: repair quay crane")

    for task_id in state.operation_task_ids:
        task = state.get_operation_task(task_id)
        if task.status.value == "created":
            actions.append(f"{task.task_id}: mark ready.")
        elif task.status.value == "ready":
            actions.append(f"{task.task_id}: assign resource")
        elif task.status.value == "assigned":
            actions.append(f"{task.task_id}: start task")
        elif task.status.value == "in_progress":
            actions.append(f"{task.task_id}: record progress or complete")
        elif task.status.value == "blocked":
            actions.append(f"{task.task_id}: resume or unassign")

    return actions[:8]


def _render_setup_checklist() -> None:
    terminal = session_store.get_sandbox_terminal()
    items = (
        ("Berth", bool(terminal.berth_ids)),
        ("Vessel", bool(terminal.vessel_ids)),
        ("Quay Crane", bool(terminal.quay_crane_ids)),
        ("Yard Block", bool(terminal.yard_block_ids)),
    )
    completed = sum(1 for _, done in items if done)
    if completed == len(items):
        return

    st.subheader(f"Terminal Setup: {completed} / {len(items)}")
    for label, done in items:
        marker = "[x]" if done else "[ ]"
        st.markdown(f"{marker} Add at least one {label.lower()}")
    st.info(
        "Operational controls will become available as the required entities are registered."
    )
    st.button(
        "Go to Terminal Setup",
        use_container_width=True,
        disabled=True,
        help="Open the Terminal Setup tab to add infrastructure.",
    )


def render_control_center() -> None:
    terminal = session_store.get_sandbox_terminal()
    state = terminal.snapshot()
    st.subheader("Control Center")
    render_last_feedback()
    render_overview_metrics(state)
    _render_setup_checklist()

    left, right = st.columns([1, 1])
    with left:
        with st.form("advance_time_form"):
            st.subheader("Advance Terminal Time")
            new_time = date_time_input(
                "New terminal time",
                default=terminal.current_time,
                key="advance_terminal_time",
                help="Terminal time can move forward only.",
            )
            if st.form_submit_button("Advance Terminal Time", use_container_width=True):
                run_terminal_command(
                    "ADVANCE_TERMINAL_TIME",
                    {"new_time": new_time.isoformat()},
                    lambda terminal: terminal.advance_time_to(new_time),
                )

    with right:
        st.subheader("Recommended Next Actions")
        actions = _recommended_actions()
        if not actions:
            st.info("No immediate guidance. Add infrastructure, cargo, or tasks.")
        else:
            for action in actions:
                st.markdown(f"<span class='cc-chip'>{action}</span>", unsafe_allow_html=True)
