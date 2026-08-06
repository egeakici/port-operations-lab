from __future__ import annotations

import streamlit as st

from app import session_store
from app.ui_helpers import date_time_input, run_terminal_command, select_or_text


def render_vessel_controls() -> None:
    terminal = session_store.get_sandbox_terminal()
    vessel_ids = terminal.vessel_ids
    berth_ids = terminal.berth_ids
    left, middle, right = st.columns(3)

    with left:
        with st.form("arrive_vessel_form"):
            st.subheader("Vessel Arrive")
            vessel_id = select_or_text(
                "Vessel ID",
                vessel_ids,
                key="arrive_vessel_id",
                help="Only approaching vessels can arrive.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="arrive_vessel_occurred_at",
            )
            if st.form_submit_button("Arrive Vessel", use_container_width=True):
                run_terminal_command(
                    "ARRIVE_VESSEL",
                    {
                        "vessel_id": vessel_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.arrive_vessel(
                        vessel_id,
                        occurred_at=occurred_at,
                    ),
                )

    with middle:
        with st.form("berth_vessel_form"):
            st.subheader("Berth Vessel")
            vessel_id = select_or_text(
                "Vessel ID",
                vessel_ids,
                key="berth_vessel_id",
                help="Only waiting vessels can be berthed.",
            )
            berth_id = select_or_text(
                "Berth ID",
                berth_ids,
                key="berth_vessel_berth_id",
            )
            start_position_m = st.number_input(
                "Start position (m)",
                min_value=0.0,
                value=0.0,
                step=5.0,
                key="berth_start_position_m",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="berth_vessel_occurred_at",
            )
            if st.form_submit_button("Berth Vessel", use_container_width=True):
                run_terminal_command(
                    "BERTH_VESSEL",
                    {
                        "vessel_id": vessel_id,
                        "berth_id": berth_id,
                        "start_position_m": start_position_m,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.berth_vessel(
                        vessel_id,
                        berth_id,
                        start_position_m,
                        occurred_at=occurred_at,
                    ),
                )

    with right:
        with st.form("depart_vessel_form"):
            st.subheader("Depart Vessel")
            vessel_id = select_or_text(
                "Vessel ID",
                vessel_ids,
                key="depart_vessel_id",
                help="Only operating vessels that have no remaining ship-side work can depart.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="depart_vessel_occurred_at",
            )
            if st.form_submit_button("Depart Vessel", use_container_width=True):
                run_terminal_command(
                    "DEPART_VESSEL",
                    {
                        "vessel_id": vessel_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.depart_vessel(
                        vessel_id,
                        occurred_at=occurred_at,
                    ),
                )

