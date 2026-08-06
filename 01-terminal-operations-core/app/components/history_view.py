from __future__ import annotations

import json

import streamlit as st

from app import presenters, session_store


def render_history_view() -> None:
    terminal = session_store.get_sandbox_terminal()
    commands = session_store.command_history()
    st.subheader("Event Timeline")
    event_rows = presenters.build_event_rows(terminal.events)
    if event_rows:
        st.dataframe(event_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No Terminal domain events yet.")

    st.subheader("Command History")
    command_rows = presenters.build_command_rows(commands)
    if command_rows:
        st.dataframe(command_rows, use_container_width=True, hide_index=True)
        selected = st.selectbox(
            "Selected command sequence",
            options=[command.sequence for command in commands],
            key="selected_history_sequence_widget",
        )
        selected_record = next(
            command
            for command in commands
            if command.sequence == selected
        )
        st.session_state[session_store.SELECTED_HISTORY_SEQUENCE] = selected
        left, right = st.columns(2)
        with left:
            st.caption("Before Terminal JSON")
            st.json(json.loads(selected_record.before_terminal_json))
        with right:
            st.caption("After Terminal JSON")
            if selected_record.after_terminal_json is None:
                st.info("No after snapshot for failed commands.")
            else:
                st.json(json.loads(selected_record.after_terminal_json))
    else:
        st.info("No commands have been submitted.")

    st.subheader("Named Checkpoints")
    checkpoints = list(st.session_state[session_store.NAMED_CHECKPOINTS].values())
    if checkpoints:
        rows = [
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "name": checkpoint.name,
                "created_at": checkpoint.created_at.isoformat(),
                "command_sequence": checkpoint.command_sequence,
                "event_count": checkpoint.state.event_count,
            }
            for checkpoint in checkpoints
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        checkpoint = st.selectbox(
            "Inspect checkpoint",
            options=checkpoints,
            format_func=lambda item: f"{item.name} ({item.checkpoint_id})",
            key="inspect_checkpoint_select",
        )
        with st.expander("Checkpoint cargo, tasks, and raw state"):
            st.dataframe(
                presenters.build_cargo_location_rows(checkpoint.state),
                use_container_width=True,
                hide_index=True,
            )
            st.dataframe(
                presenters.build_task_rows(checkpoint.state),
                use_container_width=True,
                hide_index=True,
            )
            st.json(checkpoint.state.to_dict())
    else:
        st.info("No named checkpoints saved.")

