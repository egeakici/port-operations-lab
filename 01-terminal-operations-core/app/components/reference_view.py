from __future__ import annotations

import streamlit as st

from app import presenters, session_store
from app.components.state_views import render_live_state
from src.terminal_core.integration import IntegrationCheckpoint


def render_reference_view() -> None:
    result = session_store.get_reference_result()
    summary = presenters.build_scenario_summary(result)
    st.subheader("Reference Scenario")
    st.write(f"Scenario ID: {summary['scenario_id']}")
    st.caption("Failure checkpoint marker: QC01 FAILED and T-DISCHARGE BLOCKED")
    columns = st.columns(4)
    columns[0].metric("Started", summary["started_at"])
    columns[1].metric("Completed", summary["completed_at"])
    columns[2].metric("Events", summary["event_count"])
    columns[3].metric("Checkpoints", len(summary["checkpoint_names"]))

    checkpoints = list(IntegrationCheckpoint)
    current_index = st.session_state[session_store.REFERENCE_CHECKPOINT_INDEX]
    current_index = max(0, min(current_index, len(checkpoints) - 1))

    controls = st.columns([1, 1, 1, 1, 3])
    if controls[0].button("Reset", key="reference_reset"):
        current_index = 0
    if controls[1].button("Previous", key="reference_previous"):
        current_index = max(0, current_index - 1)
    if controls[2].button("Next", key="reference_next"):
        current_index = min(len(checkpoints) - 1, current_index + 1)
    if controls[3].button("Final", key="reference_final"):
        current_index = len(checkpoints) - 1

    selected_checkpoint = controls[4].selectbox(
        "Reference checkpoint",
        options=checkpoints,
        index=current_index,
        format_func=lambda checkpoint: checkpoint.value,
        key="reference_checkpoint_select",
    )
    current_index = checkpoints.index(selected_checkpoint)
    st.session_state[session_store.REFERENCE_CHECKPOINT_INDEX] = current_index

    state = result.get_checkpoint(selected_checkpoint)
    st.markdown(
        f"<div class='cc-strip'>Selected checkpoint: "
        f"<span class='cc-status'>{selected_checkpoint.value}</span></div>",
        unsafe_allow_html=True,
    )

    crane_rows = presenters.build_crane_rows(state)
    task_rows = presenters.build_task_rows(state)
    st.write(
        "Crane status markers: "
        + ", ".join(
            f"{row['crane_id']} {str(row['status']).upper()}"
            for row in crane_rows
        )
    )
    st.write(
        "Task status markers: "
        + ", ".join(
            f"{row['task_id']} {str(row['status']).upper()}"
            for row in task_rows
        )
    )

    st.subheader("Checkpoint State")
    render_live_state(state)

    st.subheader("Reference Event Timeline")
    event_rows = presenters.build_event_rows(result.events[: state.event_count])
    if event_rows:
        st.dataframe(event_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No reference events at this checkpoint.")
