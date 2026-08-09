from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from app.visual.presenter import build_terminal_visual_scene
from app.visual.svg_renderer import render_terminal_svg
from src.terminal_core.terminal_state import TerminalState


def render_terminal_map(
    state: TerminalState,
    *,
    key_prefix: str,
) -> None:
    scene = build_terminal_visual_scene(state)
    st.subheader("Terminal Map")
    st.caption(
        "Schematic terminal view. Cargo locations come from TerminalState inventory; "
        "operation arrows show logical flows, not physical transport routes."
    )

    controls = st.columns([1, 1, 1, 1, 1, 1])
    show_labels = controls[0].checkbox(
        "Show labels",
        value=True,
        key=f"{key_prefix}_map_show_labels",
    )
    show_cargo = controls[1].checkbox(
        "Show cargo",
        value=True,
        key=f"{key_prefix}_map_show_cargo",
    )
    show_task_flows = controls[2].checkbox(
        "Show active task flows",
        value=True,
        key=f"{key_prefix}_map_show_task_flows",
    )
    show_reservations = controls[3].checkbox(
        "Show reservations",
        value=False,
        key=f"{key_prefix}_map_show_reservations",
    )
    show_crane_assignments = controls[4].checkbox(
        "Show crane assignments",
        value=True,
        key=f"{key_prefix}_map_show_crane_assignments",
    )
    compact_height = controls[5].checkbox(
        "Compact height",
        value=False,
        key=f"{key_prefix}_map_compact_height",
    )

    selectors = st.columns(5)
    selected_vessel_id = _optional_select(
        selectors[0],
        "Highlight vessel",
        tuple(vessel.vessel_id for vessel in scene.vessels + scene.anchorage_vessels),
        key=f"{key_prefix}_map_selected_vessel",
    )
    selected_crane_id = _optional_select(
        selectors[1],
        "Highlight crane",
        tuple(crane.crane_id for crane in scene.cranes),
        key=f"{key_prefix}_map_selected_crane",
    )
    selected_yard_block_id = _optional_select(
        selectors[2],
        "Highlight yard block",
        tuple(block.block_id for block in scene.yard_blocks),
        key=f"{key_prefix}_map_selected_yard",
    )
    selected_task_id = _optional_select(
        selectors[3],
        "Highlight task",
        tuple(flow.task_id for flow in scene.task_flows),
        key=f"{key_prefix}_map_selected_task",
    )
    selected_group_id = _optional_select(
        selectors[4],
        "Highlight cargo group",
        state.container_group_ids,
        key=f"{key_prefix}_map_selected_group",
    )

    svg = render_terminal_svg(
        scene,
        show_labels=show_labels,
        show_cargo=show_cargo,
        show_task_flows=show_task_flows,
        show_reservations=show_reservations,
        show_crane_assignments=show_crane_assignments,
        selected_vessel_id=selected_vessel_id,
        selected_crane_id=selected_crane_id,
        selected_yard_block_id=selected_yard_block_id,
        selected_task_id=selected_task_id,
        selected_group_id=selected_group_id,
    )
    height = 620 if compact_height else 780
    components.html(svg, height=height, scrolling=False)


def _optional_select(
    column,
    label: str,
    options: tuple[str, ...],
    *,
    key: str,
) -> str | None:
    values = ("None",) + tuple(options)
    selected = column.selectbox(label, values, key=key)
    return None if selected == "None" else selected

