from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app import session_store
from app.components.cargo_controls import render_cargo_and_task_forms
from app.components.crane_controls import render_crane_controls
from app.components.history_view import render_history_view
from app.components.reference_view import render_reference_view
from app.components.sandbox_home import render_control_center
from app.components.setup_forms import render_setup_forms
from app.components.state_views import render_live_state
from app.components.task_controls import render_task_controls
from app.components.vessel_controls import render_vessel_controls
from app.models import CommandRecord, canonical_json
from app.styles import apply_styles
from app.ui_helpers import date_time_input
from app.visual.terminal_map import render_terminal_map
from src.terminal_core.terminal import Terminal


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "sandbox"


def _record_ui_action(
    command_name: str,
    *,
    before_json: str,
    after_json: str | None,
    parameters: dict[str, object],
    success: bool = True,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    record = CommandRecord(
        sequence=session_store.next_command_sequence(),
        command_name=command_name,
        attempted_at=datetime.now(),
        parameters=parameters,
        success=success,
        new_event_ids=(),
        new_event_types=(),
        error_type=error_type,
        error_message=error_message,
        before_terminal_json=before_json,
        after_terminal_json=after_json,
    )
    session_store.append_command_record(record)


def _render_sidebar() -> None:
    terminal = session_store.get_sandbox_terminal()
    st.sidebar.header("Interactive Sandbox")
    sandbox_name = st.sidebar.text_input(
        "Scenario name",
        value=st.session_state[session_store.SANDBOX_NAME],
        help="Used for exported file names and package metadata.",
    )
    sandbox_description = st.sidebar.text_area(
        "Scenario description",
        value=st.session_state[session_store.SANDBOX_DESCRIPTION],
    )
    st.session_state[session_store.SANDBOX_NAME] = sandbox_name
    st.session_state[session_store.SANDBOX_DESCRIPTION] = sandbox_description
    st.sidebar.write(f"Current terminal time: {terminal.current_time.isoformat()}")
    st.sidebar.write(f"Current event count: {terminal.event_count}")
    st.sidebar.write(
        f"Current command count: {len(st.session_state[session_store.COMMAND_HISTORY])}"
    )
    last_success = next(
        (
            command.command_name
            for command in reversed(st.session_state[session_store.COMMAND_HISTORY])
            if command.success
        ),
        "None",
    )
    st.sidebar.write(f"Last successful command: {last_success}")
    st.sidebar.toggle("Debug mode", key=session_store.DEBUG_MODE)

    with st.sidebar.expander("New Empty Terminal", expanded=True):
        with st.form("new_empty_terminal_form"):
            name = st.text_input("New scenario name", value="Manual terminal")
            description = st.text_area("New scenario description", value="")
            initial_time = date_time_input(
                "Initial time",
                default=datetime(2026, 1, 1, 8, 0),
                key="new_terminal_initial_time",
            )
            confirm = st.checkbox(
                "I understand this clears the current sandbox",
                key="new_terminal_confirm",
            )
            if st.form_submit_button("Create Empty Terminal", use_container_width=True):
                if not confirm:
                    st.warning("Confirm sandbox replacement before creating a new terminal.")
                else:
                    session_store.clear_sandbox(
                        name=name,
                        description=description,
                        current_time=initial_time,
                    )
                    st.success("New empty terminal created.")
                    st.rerun()

    with st.sidebar.expander("Quick Start / Reset"):
        confirm_reference = st.checkbox(
            "Replace sandbox with reference infrastructure",
            key="load_reference_confirm",
        )
        if st.button("Load Reference Infrastructure", use_container_width=True):
            if confirm_reference:
                session_store.load_reference_infrastructure()
                st.success("Reference infrastructure loaded into sandbox.")
                st.rerun()
            else:
                st.warning("Confirm replacement before loading reference infrastructure.")

        confirm_reset = st.checkbox(
            "Confirm Reset Sandbox",
            key="reset_sandbox_confirm",
        )
        if st.button("Reset Sandbox", use_container_width=True):
            if confirm_reset:
                session_store.clear_sandbox()
                st.success("Sandbox reset.")
                st.rerun()
            else:
                st.warning("Confirm reset before clearing the sandbox.")

    with st.sidebar.expander("Checkpoint"):
        with st.form("save_checkpoint_form"):
            checkpoint_name = st.text_input("Checkpoint name", value="Checkpoint")
            checkpoint_description = st.text_area("Checkpoint description", value="")
            if st.form_submit_button("Save Current State", use_container_width=True):
                try:
                    checkpoint = session_store.save_checkpoint(
                        checkpoint_name,
                        checkpoint_description,
                    )
                    st.success(f"Saved checkpoint: {checkpoint.name}")
                except ValueError as error:
                    st.error(str(error))

        checkpoints = st.session_state[session_store.NAMED_CHECKPOINTS]
        if checkpoints:
            selected_id = st.selectbox(
                "Restore checkpoint",
                options=tuple(checkpoints),
                format_func=lambda checkpoint_id: checkpoints[checkpoint_id].name,
                key="restore_checkpoint_select",
            )
            confirm_restore = st.checkbox(
                "Confirm Restore Selected Checkpoint",
                key="restore_checkpoint_confirm",
            )
            if st.button("Restore Selected Checkpoint", use_container_width=True):
                if not confirm_restore:
                    st.warning("Confirm checkpoint restore before replacing the sandbox.")
                else:
                    before_json = canonical_json(
                        session_store.get_sandbox_terminal().to_dict()
                    )
                    restored = session_store.restore_checkpoint(selected_id)
                    _record_ui_action(
                        "UI_RESTORE_CHECKPOINT",
                        before_json=before_json,
                        after_json=canonical_json(restored.to_dict()),
                        parameters={"checkpoint_id": selected_id},
                    )
                    st.success(f"Restored checkpoint: {checkpoints[selected_id].name}")
                    st.rerun()


def _render_import_export() -> None:
    terminal = session_store.get_sandbox_terminal()
    scenario_name = st.session_state[session_store.SANDBOX_NAME]
    st.subheader("Download")
    left, right = st.columns(2)
    left.download_button(
        "Download Current Terminal JSON",
        data=session_store.terminal_json_bytes(),
        file_name=f"terminal_{_slug(scenario_name)}.json",
        mime="application/json",
        use_container_width=True,
    )
    right.download_button(
        "Download Full Sandbox Scenario",
        data=session_store.sandbox_package_bytes(),
        file_name=f"sandbox_{_slug(scenario_name)}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.subheader("Upload")
    left, right = st.columns(2)
    with left:
        uploaded_terminal = st.file_uploader(
            "Upload Terminal JSON",
            type=("json",),
            key="terminal_json_upload",
        )
        confirm_import = st.checkbox(
            "Confirm Terminal JSON import",
            key="confirm_terminal_json_import",
        )
        if st.button("Import Terminal JSON", use_container_width=True):
            if uploaded_terminal is None:
                st.warning("Choose a Terminal JSON file first.")
            elif not confirm_import:
                st.warning("Confirm import before replacing the sandbox terminal.")
            else:
                before_json = canonical_json(terminal.to_dict())
                try:
                    imported = session_store.import_terminal_json(
                        uploaded_terminal.getvalue()
                    )
                except Exception as error:
                    _record_ui_action(
                        "UI_IMPORT_TERMINAL_JSON",
                        before_json=before_json,
                        after_json=None,
                        parameters={"file_name": uploaded_terminal.name},
                        success=False,
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                    st.error(f"Terminal JSON import failed: {error}")
                else:
                    _record_ui_action(
                        "UI_IMPORT_TERMINAL_JSON",
                        before_json=before_json,
                        after_json=canonical_json(imported.to_dict()),
                        parameters={"file_name": uploaded_terminal.name},
                    )
                    st.success("Terminal JSON imported.")
                    st.rerun()

    with right:
        uploaded_package = st.file_uploader(
            "Upload Sandbox Scenario",
            type=("json",),
            key="sandbox_package_upload",
        )
        confirm_package = st.checkbox(
            "Confirm Sandbox Scenario import",
            key="confirm_sandbox_package_import",
        )
        if st.button("Import Sandbox Scenario", use_container_width=True):
            if uploaded_package is None:
                st.warning("Choose a sandbox scenario package first.")
            elif not confirm_package:
                st.warning("Confirm import before replacing the sandbox.")
            else:
                before_json = canonical_json(terminal.to_dict())
                try:
                    imported = session_store.import_sandbox_package(
                        uploaded_package.getvalue()
                    )
                except Exception as error:
                    _record_ui_action(
                        "UI_IMPORT_SANDBOX_PACKAGE",
                        before_json=before_json,
                        after_json=None,
                        parameters={"file_name": uploaded_package.name},
                        success=False,
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                    st.error(f"Sandbox scenario import failed: {error}")
                else:
                    _record_ui_action(
                        "UI_IMPORT_SANDBOX_PACKAGE",
                        before_json=before_json,
                        after_json=canonical_json(imported.to_dict()),
                        parameters={"file_name": uploaded_package.name},
                    )
                    st.success("Sandbox scenario imported.")
                    st.rerun()

    with st.expander("Raw current Terminal JSON"):
        st.json(json.loads(canonical_json(terminal.to_dict())))


def _render_interactive_sandbox() -> None:
    sandbox_tabs = st.tabs(
        [
            "Control Center",
            "Terminal Setup",
            "Cargo & Tasks",
            "Terminal Map",
            "Live State",
            "Events & History",
            "Import / Export",
        ]
    )
    with sandbox_tabs[0]:
        render_control_center()
        render_vessel_controls()
    with sandbox_tabs[1]:
        render_setup_forms()
    with sandbox_tabs[2]:
        render_cargo_and_task_forms()
        render_task_controls()
        render_crane_controls()
    with sandbox_tabs[3]:
        render_terminal_map(
            session_store.get_sandbox_terminal().snapshot(),
            key_prefix="sandbox",
        )
    with sandbox_tabs[4]:
        render_live_state(session_store.get_sandbox_terminal().snapshot())
    with sandbox_tabs[5]:
        render_history_view()
    with sandbox_tabs[6]:
        _render_import_export()


def main() -> None:
    st.set_page_config(
        page_title="Terminal Operations Control Center",
        page_icon="⚓",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    session_store.initialize_session()
    apply_styles()
    st.title("Terminal Operations Control Center")
    st.markdown(
        "<p class='cc-subtitle'>Build, operate, inspect, and export a terminal "
        "scenario using the Terminal Operations Core.</p>",
        unsafe_allow_html=True,
    )
    _render_sidebar()

    interactive_tab, reference_tab = st.tabs(
        ["Interactive Sandbox", "Reference Scenario"]
    )
    with interactive_tab:
        _render_interactive_sandbox()
    with reference_tab:
        render_reference_view()

    if st.session_state[session_store.DEBUG_MODE]:
        with st.expander("Debug session keys"):
            st.write(sorted(st.session_state.keys()))


if __name__ == "__main__":
    main()
