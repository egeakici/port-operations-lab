from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time
from typing import Any

import streamlit as st


def date_time_input(
    label: str,
    *,
    default: datetime,
    key: str,
) -> datetime:
    st.caption(label)
    left, right = st.columns(2)
    selected_date = left.date_input(
        f"{label} date",
        value=default.date(),
        key=f"{key}_date",
    )
    selected_time = right.time_input(
        f"{label} time",
        value=default.time().replace(microsecond=0),
        key=f"{key}_time",
    )
    if isinstance(selected_time, time):
        return datetime.combine(selected_date, selected_time)
    return datetime.combine(selected_date, default.time().replace(microsecond=0))


def metric_card(label: str, value: str, caption: str | None = None) -> None:
    caption_html = f"<div class='mps-muted'>{caption}</div>" if caption else ""
    st.markdown(
        "<div class='mps-card'>"
        f"<div class='mps-card-label'>{label}</div>"
        f"<div class='mps-card-value'>{value}</div>"
        f"{caption_html}</div>",
        unsafe_allow_html=True,
    )


def optional_select(
    label: str,
    options: Iterable[str],
    *,
    key: str,
) -> str | None:
    values = ("None",) + tuple(options)
    selected = st.selectbox(label, values, key=key)
    return None if selected == "None" else str(selected)


def download_json_button(
    label: str,
    data: bytes,
    file_name: str,
    *,
    key: str,
) -> None:
    st.download_button(
        label,
        data=data,
        file_name=file_name,
        mime="application/json",
        key=key,
        width="stretch",
    )
