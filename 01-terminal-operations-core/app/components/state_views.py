from __future__ import annotations

import html

import streamlit as st

from app import presenters
from terminal_core.terminal_state import TerminalState


def _dataframe_or_info(rows: list[dict[str, object]], message: str) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info(message)


def render_overview_metrics(state: TerminalState) -> None:
    metrics = presenters.build_overview_metrics(state)
    columns = st.columns(4)
    for index, metric in enumerate(metrics):
        columns[index % 4].metric(metric["label"], metric["value"])


def render_berth_layout(state: TerminalState) -> None:
    st.subheader("Berth Layout")
    rows = presenters.build_berth_rows(state)
    if not rows:
        st.info("No berths registered.")
        return

    html_rows = []
    for row in rows:
        vessel = row["vessel_id"] or "empty"
        interval = (
            "-"
            if row["start_position_m"] is None
            else f"{row['start_position_m']} - {row['end_position_m']} m"
        )
        html_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['berth_id']))}</td>"
            f"<td>{html.escape(str(row['length_m']))}</td>"
            f"<td>{html.escape(str(vessel))}</td>"
            f"<td>{html.escape(str(interval))}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='cc-layout'>"
        "<thead><tr><th>Berth</th><th>Length m</th>"
        "<th>Vessel</th><th>Interval</th></tr></thead>"
        "<tbody>"
        + "".join(html_rows)
        + "</tbody></table>",
        unsafe_allow_html=True,
    )


def render_state_tables(state: TerminalState) -> None:
    render_berth_layout(state)
    st.subheader("Vessels")
    _dataframe_or_info(
        presenters.build_vessel_rows(state),
        "No vessels registered.",
    )
    st.subheader("Quay Cranes")
    _dataframe_or_info(
        presenters.build_crane_rows(state),
        "No quay cranes registered.",
    )
    st.subheader("Yard Blocks")
    _dataframe_or_info(
        presenters.build_yard_rows(state),
        "No yard blocks registered.",
    )
    st.subheader("Container Groups")
    _dataframe_or_info(
        presenters.build_group_rows(state),
        "No container groups registered.",
    )
    st.subheader("Cargo Locations")
    _dataframe_or_info(
        presenters.build_cargo_location_rows(state),
        "No cargo locations recorded.",
    )
    st.subheader("Operation Tasks")
    _dataframe_or_info(
        presenters.build_task_rows(state),
        "No operation tasks registered.",
    )


def render_live_state(state: TerminalState) -> None:
    render_overview_metrics(state)
    render_state_tables(state)
    with st.expander("Raw TerminalState JSON"):
        st.json(state.to_dict())

