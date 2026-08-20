from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, time
from typing import Any

import streamlit as st

from app.command_service import execute_terminal_command
from app import session_store
from terminal_core.terminal import Terminal


def date_time_input(
    label: str,
    *,
    default: datetime,
    key: str,
    help: str | None = None,
) -> datetime:
    st.caption(label)
    left, right = st.columns(2)
    selected_date = left.date_input(
        f"{label} date",
        value=default.date(),
        key=f"{key}_date",
        help=help,
    )
    selected_time = right.time_input(
        f"{label} time",
        value=default.time().replace(microsecond=0),
        key=f"{key}_time",
        help=help,
    )
    if isinstance(selected_time, time):
        return datetime.combine(selected_date, selected_time)
    return datetime.combine(selected_date, default.time().replace(microsecond=0))


def run_terminal_command(
    command_name: str,
    parameters: Mapping[str, Any],
    operation: Callable[[Terminal], Any],
) -> None:
    terminal = session_store.get_sandbox_terminal()
    result = execute_terminal_command(
        terminal,
        command_name=command_name,
        parameters=parameters,
        operation=operation,
        sequence=session_store.next_command_sequence(),
    )
    session_store.replace_sandbox_terminal(result.terminal)
    session_store.append_command_record(result.record)
    st.rerun()


def render_last_feedback() -> None:
    feedback = st.session_state.get(session_store.LAST_COMMAND_FEEDBACK)
    if feedback is None:
        return
    if feedback.success:
        st.success(f"{feedback.command_name} succeeded")
        st.caption("Current state updated")
        if feedback.new_event_types:
            st.markdown("New events:")
            for event_type in feedback.new_event_types:
                st.markdown(f"- {event_type.upper()}")
    else:
        st.error(f"{feedback.command_name} rejected")
        if feedback.error_message:
            st.caption(feedback.error_message)
        st.caption("No terminal changes were committed.")


def select_registered(
    label: str,
    options: tuple[str, ...],
    *,
    key: str,
    empty_message: str,
    help: str | None = None,
) -> str | None:
    if options:
        return st.selectbox(label, options=options, key=key, help=help)
    st.info(empty_message)
    return None
