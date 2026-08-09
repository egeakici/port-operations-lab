from __future__ import annotations

import html
import math

from app.visual import layout
from app.visual.models import (
    CargoBadgeVisual,
    TerminalVisualScene,
    VisualPoint,
    VisualRect,
)


STATUS_STYLES = {
    "approaching": {"fill": "#1f6f8b", "stroke": "#8bd3e6"},
    "waiting": {"fill": "#675f22", "stroke": "#f5d76e"},
    "berthed": {"fill": "#23635a", "stroke": "#7de2d1"},
    "operating": {"fill": "#1d6b47", "stroke": "#7ee2a8"},
    "departed": {"fill": "#404954", "stroke": "#9aa8b3"},
    "available": {"fill": "#1d6b47", "stroke": "#7ee2a8"},
    "assigned": {"fill": "#245b86", "stroke": "#8fc7ff"},
    "failed": {"fill": "#7a2525", "stroke": "#ff8b8b"},
    "maintenance": {"fill": "#5b4b1f", "stroke": "#ffd166"},
    "open": {"fill": "#1f5d46", "stroke": "#83e0b0"},
    "closed": {"fill": "#4a5360", "stroke": "#aab5c0"},
    "blocked": {"fill": "#7a2525", "stroke": "#ff8b8b"},
    "in_progress": {"fill": "#245b86", "stroke": "#8fc7ff"},
}

DEFAULT_STYLE = {"fill": "#263746", "stroke": "#9fb4c2"}


def render_terminal_svg(
    scene: TerminalVisualScene,
    *,
    show_labels: bool = True,
    show_cargo: bool = True,
    show_task_flows: bool = True,
    show_reservations: bool = False,
    show_crane_assignments: bool = True,
    selected_vessel_id: str | None = None,
    selected_crane_id: str | None = None,
    selected_yard_block_id: str | None = None,
    selected_task_id: str | None = None,
    selected_group_id: str | None = None,
) -> str:
    parts = [
        f"<svg viewBox=\"0 0 {_num(scene.width)} {_num(scene.height)}\" "
        "width=\"100%\" preserveAspectRatio=\"xMidYMid meet\" "
        "role=\"img\" aria-label=\"Schematic terminal map\">",
        _defs(),
        _background(scene),
    ]

    if scene.is_empty:
        parts.append(_empty_state())

    if show_task_flows:
        parts.extend(
            _task_flow(flow, selected=flow.task_id == selected_task_id)
            for flow in scene.task_flows
        )

    parts.extend(_berth(berth, show_labels=show_labels) for berth in scene.berths)
    parts.extend(
        _vessel(
            vessel,
            show_labels=show_labels,
            show_cargo=show_cargo,
            selected=(
                vessel.vessel_id == selected_vessel_id
                or _has_selected_group(vessel.cargo, selected_group_id)
            ),
        )
        for vessel in scene.vessels
    )
    parts.append(_anchorage(scene, show_labels=show_labels, show_cargo=show_cargo))
    parts.extend(
        _crane(
            crane,
            show_labels=show_labels,
            show_assignment=show_crane_assignments,
            selected=crane.crane_id == selected_crane_id,
        )
        for crane in scene.cranes
    )
    parts.extend(
        _yard_block(
            block,
            show_labels=show_labels,
            show_cargo=show_cargo,
            show_reservations=show_reservations,
            selected=(
                block.block_id == selected_yard_block_id
                or _has_selected_group(block.stored_groups, selected_group_id)
                or _has_selected_group(block.reservations, selected_group_id)
            ),
        )
        for block in scene.yard_blocks
    )
    parts.extend(
        _gate(gate, show_labels=show_labels, show_cargo=show_cargo)
        for gate in scene.gates
    )
    parts.append(_departed_summary(scene))
    parts.append(_legend())
    parts.append("</svg>")
    return "".join(parts)


def _defs() -> str:
    return """
<defs>
  <marker id="arrowhead" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
    <path d="M0,0 L10,4 L0,8 Z" fill="#f4d35e" />
  </marker>
  <pattern id="waterLines" patternUnits="userSpaceOnUse" width="36" height="20">
    <path d="M0 10 H36" stroke="#2a6f85" stroke-width="1" opacity="0.35" />
  </pattern>
</defs>
"""


def _background(scene: TerminalVisualScene) -> str:
    return (
        f"<rect x=\"0\" y=\"0\" width=\"{_num(scene.width)}\" height=\"{_num(scene.height)}\" "
        "fill=\"#0b1117\" />"
        f"<rect x=\"0\" y=\"0\" width=\"{_num(scene.width)}\" height=\"{_num(layout.QUAY_Y - 6)}\" "
        "fill=\"#0d3342\" />"
        f"<rect x=\"0\" y=\"0\" width=\"{_num(scene.width)}\" height=\"{_num(layout.QUAY_Y - 6)}\" "
        "fill=\"url(#waterLines)\" opacity=\"0.55\" />"
        f"<text x=\"{_num(layout.MARGIN_X)}\" y=\"30\" class=\"map-title\">SEA / WATER</text>"
        f"<rect x=\"0\" y=\"{_num(layout.QUAY_Y + 18)}\" width=\"{_num(scene.width)}\" height=\"36\" "
        "fill=\"#202a33\" />"
        f"<line x1=\"{_num(layout.QUAY_X)}\" y1=\"{_num(layout.QUAY_Y)}\" "
        f"x2=\"{_num(layout.QUAY_X + layout.QUAY_WIDTH)}\" y2=\"{_num(layout.QUAY_Y)}\" "
        "stroke=\"#d6d1bd\" stroke-width=\"8\" />"
        f"<text x=\"{_num(scene.width / 2)}\" y=\"{_num(layout.QUAY_Y + 43)}\" "
        "text-anchor=\"middle\" class=\"section-label\">QUAY / WORKING APRON</text>"
        f"<text x=\"{_num(layout.MARGIN_X)}\" y=\"{_num(layout.YARD_Y - 18)}\" "
        "class=\"section-label\">YARD AREA</text>"
        f"<text x=\"{_num(layout.MARGIN_X)}\" y=\"{_num(scene.height - 14)}\" "
        "class=\"caption\">Schematic terminal view: berth positions use meter data; yard and gate positions are UI layout.</text>"
        "<style>"
        ".map-title{font:700 18px sans-serif;fill:#cfe8ef;letter-spacing:0}"
        ".section-label{font:700 13px sans-serif;fill:#d9e2e8;letter-spacing:0}"
        ".caption{font:12px sans-serif;fill:#9fb4c2}"
        ".label{font:700 13px sans-serif;fill:#f4f8fa;letter-spacing:0}"
        ".small{font:11px sans-serif;fill:#dce7eb;letter-spacing:0}"
        ".tiny{font:10px sans-serif;fill:#c7d4da;letter-spacing:0}"
        ".muted{fill:#9fb4c2}"
        ".highlight{stroke:#f4d35e!important;stroke-width:4!important}"
        "</style>"
    )


def _empty_state() -> str:
    return (
        "<g>"
        f"<rect x=\"{_num(layout.QUAY_X + 340)}\" y=\"{_num(layout.WATER_TOP + 82)}\" "
        "width=\"520\" height=\"122\" rx=\"8\" fill=\"#101922\" stroke=\"#52606b\" />"
        f"<text x=\"{_num(layout.SCENE_WIDTH / 2)}\" y=\"{_num(layout.WATER_TOP + 128)}\" "
        "text-anchor=\"middle\" class=\"label\">Terminal map is empty.</text>"
        f"<text x=\"{_num(layout.SCENE_WIDTH / 2)}\" y=\"{_num(layout.WATER_TOP + 154)}\" "
        "text-anchor=\"middle\" class=\"small\">Add berths, vessels, cranes, and yard blocks from Terminal Setup.</text>"
        "</g>"
    )


def _berth(berth, *, show_labels: bool) -> str:
    rect = berth.rect
    label = _esc(berth.berth_id)
    title = _esc(
        f"{berth.berth_id} | Length: {berth.length_m:g} m | min_clearance_m: {berth.min_clearance_m:g}"
    )
    parts = [
        f"<g><title>{title}</title>",
        f"<rect x=\"{_num(rect.x)}\" y=\"{_num(rect.y)}\" width=\"{_num(rect.width)}\" "
        f"height=\"{_num(rect.height)}\" fill=\"#303943\" stroke=\"#d6d1bd\" stroke-width=\"2\" />",
        f"<text x=\"{_num(rect.x + 6)}\" y=\"{_num(rect.y - 6)}\" class=\"tiny\">0m</text>",
        f"<text x=\"{_num(rect.x + rect.width - 4)}\" y=\"{_num(rect.y - 6)}\" "
        f"text-anchor=\"end\" class=\"tiny\">{_esc(f'{berth.length_m:g}m')}</text>",
    ]
    if show_labels:
        parts.append(
            f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.center.y + 5)}\" "
            f"text-anchor=\"middle\" class=\"label\">{label}</text>"
        )
    parts.append("</g>")
    return "".join(parts)


def _vessel(vessel, *, show_labels: bool, show_cargo: bool, selected: bool) -> str:
    rect = vessel.rect
    style = STATUS_STYLES.get(vessel.status, DEFAULT_STYLE)
    cls = " highlight" if selected else ""
    bow = rect.x + rect.width
    points = [
        (rect.x + 14, rect.y),
        (bow - 22, rect.y),
        (bow, rect.y + rect.height / 2),
        (bow - 22, rect.y + rect.height),
        (rect.x + 14, rect.y + rect.height),
        (rect.x, rect.y + rect.height / 2),
    ]
    point_text = " ".join(f"{_num(x)},{_num(y)}" for x, y in points)
    title = _esc(
        f"{vessel.vessel_id} | Status: {vessel.status.upper()} | Length: {vessel.length_m:g} m"
    )
    parts = [
        f"<g><title>{title}</title>",
        f"<polygon points=\"{point_text}\" fill=\"{style['fill']}\" stroke=\"{style['stroke']}\" "
        f"stroke-width=\"2.5\" class=\"{cls.strip()}\" />",
    ]
    if show_labels:
        parts.extend(
            [
                f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 25)}\" "
                f"text-anchor=\"middle\" class=\"label\">{_esc(vessel.vessel_id)}</text>",
                f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 43)}\" "
                f"text-anchor=\"middle\" class=\"small\">{_esc(vessel.status.upper())}</text>",
                f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 60)}\" "
                f"text-anchor=\"middle\" class=\"tiny\">{_esc(f'{vessel.length_m:g} m')}</text>",
            ]
        )
    if show_cargo:
        parts.append(_cargo_lines(vessel.cargo, rect.x + 8, rect.y + rect.height + 14))
    parts.append("</g>")
    return "".join(parts)


def _anchorage(scene: TerminalVisualScene, *, show_labels: bool, show_cargo: bool) -> str:
    if not scene.anchorage_vessels:
        return ""
    parts = [
        f"<text x=\"{_num(layout.QUAY_X + 24)}\" y=\"{_num(layout.WATER_TOP + 42)}\" "
        "class=\"section-label\">ANCHORAGE / WAITING AREA</text>"
    ]
    for vessel in scene.anchorage_vessels:
        rect = vessel.rect
        style = STATUS_STYLES.get(vessel.status, DEFAULT_STYLE)
        parts.append(
            f"<g><title>{_esc(vessel.vessel_id)} | {_esc(vessel.status.upper())}</title>"
            f"<rect x=\"{_num(rect.x)}\" y=\"{_num(rect.y)}\" width=\"{_num(rect.width)}\" "
            f"height=\"{_num(rect.height)}\" rx=\"20\" fill=\"{style['fill']}\" "
            f"stroke=\"{style['stroke']}\" stroke-width=\"2\" />"
        )
        if show_labels:
            parts.append(
                f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 23)}\" "
                f"text-anchor=\"middle\" class=\"label\">{_esc(vessel.vessel_id)}</text>"
                f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 42)}\" "
                f"text-anchor=\"middle\" class=\"small\">{_esc(vessel.status.upper())}</text>"
            )
        if show_cargo and vessel.cargo:
            parts.append(_cargo_lines(vessel.cargo, rect.x + 4, rect.y + rect.height + 12))
        parts.append("</g>")
    return "".join(parts)


def _crane(crane, *, show_labels: bool, show_assignment: bool, selected: bool) -> str:
    rect = crane.rect
    style = STATUS_STYLES.get(crane.status, DEFAULT_STYLE)
    cls = " highlight" if selected else ""
    title = _esc(
        f"{crane.crane_id} | Status: {crane.status.upper()} | Position: {crane.position_m:g} m"
    )
    parts = [
        f"<g><title>{title}</title>",
        f"<line x1=\"{_num(rect.center.x)}\" y1=\"{_num(layout.QUAY_Y + 2)}\" "
        f"x2=\"{_num(rect.center.x)}\" y2=\"{_num(rect.y + 44)}\" "
        f"stroke=\"{style['stroke']}\" stroke-width=\"3\" />",
        f"<rect x=\"{_num(rect.x)}\" y=\"{_num(rect.y)}\" width=\"{_num(rect.width)}\" "
        f"height=\"{_num(rect.height)}\" rx=\"5\" fill=\"{style['fill']}\" "
        f"stroke=\"{style['stroke']}\" stroke-width=\"2\" class=\"{cls.strip()}\" />",
    ]
    if show_labels:
        failed = " !" if crane.failed else ""
        parts.append(
            f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 22)}\" "
            f"text-anchor=\"middle\" class=\"label\">{_esc(crane.crane_id + failed)}</text>"
            f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 41)}\" "
            f"text-anchor=\"middle\" class=\"small\">{_esc(crane.status.upper())}</text>"
        )
    if show_assignment and crane.assigned_vessel_id:
        assignment = crane.assigned_vessel_id
        if crane.active_task_id:
            assignment += f" / {crane.active_task_id}"
        parts.append(
            f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + rect.height + 14)}\" "
            f"text-anchor=\"middle\" class=\"tiny\">{_esc(assignment)}</text>"
        )
    parts.append("</g>")
    return "".join(parts)


def _yard_block(
    block,
    *,
    show_labels: bool,
    show_cargo: bool,
    show_reservations: bool,
    selected: bool,
) -> str:
    rect = block.rect
    style = STATUS_STYLES.get(block.status, DEFAULT_STYLE)
    cls = " highlight" if selected else ""
    stored_ratio = layout.ratio(block.stored_teu, block.capacity_teu)
    reserved_ratio = layout.ratio(block.reserved_teu, block.capacity_teu)
    bar_x = rect.x + 14
    bar_y = rect.y + 48
    bar_width = rect.width - 28
    title = _esc(
        f"{block.block_id} | {block.status.upper()} | Stored: {block.stored_teu:g} | Reserved: {block.reserved_teu:g}"
    )
    parts = [
        f"<g><title>{title}</title>",
        f"<rect x=\"{_num(rect.x)}\" y=\"{_num(rect.y)}\" width=\"{_num(rect.width)}\" "
        f"height=\"{_num(rect.height)}\" rx=\"7\" fill=\"#132119\" stroke=\"{style['stroke']}\" "
        f"stroke-width=\"2\" class=\"{cls.strip()}\" />",
        f"<rect x=\"{_num(bar_x)}\" y=\"{_num(bar_y)}\" width=\"{_num(bar_width)}\" "
        "height=\"14\" rx=\"4\" fill=\"#26323c\" />",
        f"<rect x=\"{_num(bar_x)}\" y=\"{_num(bar_y)}\" width=\"{_num(bar_width * stored_ratio)}\" "
        "height=\"14\" rx=\"4\" fill=\"#2ec4b6\" />",
        f"<rect x=\"{_num(bar_x + bar_width * stored_ratio)}\" y=\"{_num(bar_y)}\" "
        f"width=\"{_num(bar_width * reserved_ratio)}\" height=\"14\" rx=\"4\" "
        "fill=\"#f4d35e\" opacity=\"0.82\" />",
    ]
    if show_labels:
        parts.extend(
            [
                f"<text x=\"{_num(rect.x + 14)}\" y=\"{_num(rect.y + 24)}\" class=\"label\">{_esc(block.block_id)}</text>",
                f"<text x=\"{_num(rect.x + rect.width - 14)}\" y=\"{_num(rect.y + 24)}\" "
                f"text-anchor=\"end\" class=\"small\">{_esc(block.status.upper())}</text>",
                f"<text x=\"{_num(rect.x + 14)}\" y=\"{_num(rect.y + 80)}\" "
                f"class=\"small\">{_esc(f'Stored {block.stored_teu:g} / {block.capacity_teu:g} TEU')}</text>",
                f"<text x=\"{_num(rect.x + 14)}\" y=\"{_num(rect.y + 98)}\" "
                f"class=\"tiny\">{_esc('Caps: ' + _short_caps(block.capabilities))}</text>",
            ]
        )
        if show_reservations:
            parts.append(
                f"<text x=\"{_num(rect.x + rect.width - 14)}\" y=\"{_num(rect.y + 80)}\" "
                f"text-anchor=\"end\" class=\"small\">{_esc(f'+{block.reserved_teu:g} reserved')}</text>"
            )
    if show_cargo:
        parts.append(_cargo_lines(block.stored_groups, rect.x + 14, rect.y + rect.height - 8))
    if show_reservations:
        parts.append(_cargo_lines(block.reservations, rect.x + rect.width - 128, rect.y + rect.height - 8, prefix="R "))
    parts.append("</g>")
    return "".join(parts)


def _gate(gate, *, show_labels: bool, show_cargo: bool) -> str:
    rect = gate.rect
    parts = [
        f"<g><title>{_esc(gate.gate_id)}</title>",
        f"<rect x=\"{_num(rect.x)}\" y=\"{_num(rect.y)}\" width=\"{_num(rect.width)}\" "
        f"height=\"{_num(rect.height)}\" rx=\"6\" fill=\"#24313b\" stroke=\"#b9cbd2\" stroke-width=\"2\" />",
    ]
    if show_labels:
        parts.append(
            f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 22)}\" "
            f"text-anchor=\"middle\" class=\"label\">TRUCK GATE</text>"
            f"<text x=\"{_num(rect.center.x)}\" y=\"{_num(rect.y + 41)}\" "
            f"text-anchor=\"middle\" class=\"small\">{_esc(gate.gate_id)}</text>"
        )
    if show_cargo:
        parts.append(_cargo_lines(gate.cargo, rect.x + 8, rect.y + rect.height + 12))
    parts.append("</g>")
    return "".join(parts)


def _task_flow(flow, *, selected: bool) -> str:
    stroke = "#ff8b8b" if flow.blocked else "#f4d35e"
    dash = " stroke-dasharray=\"9 7\"" if flow.blocked else ""
    cls = " highlight" if selected else ""
    mid_x = (flow.source.x + flow.target.x) / 2.0
    mid_y = (flow.source.y + flow.target.y) / 2.0 - 8.0
    label = f"{flow.task_id} {flow.task_type.upper()} {flow.completed_teu:g}/{flow.planned_teu:g} TEU"
    if flow.blocked:
        label += " BLOCKED"
    return (
        f"<g><title>{_esc(flow.task_id)} | {_esc(flow.status.upper())} | "
        f"{_esc(flow.source_id)} -> {_esc(flow.target_id)}</title>"
        f"<line x1=\"{_num(flow.source.x)}\" y1=\"{_num(flow.source.y)}\" "
        f"x2=\"{_num(flow.target.x)}\" y2=\"{_num(flow.target.y)}\" "
        f"stroke=\"{stroke}\" stroke-width=\"3\" marker-end=\"url(#arrowhead)\""
        f"{dash} class=\"{cls.strip()}\" />"
        f"<rect x=\"{_num(mid_x - 112)}\" y=\"{_num(mid_y - 18)}\" width=\"224\" height=\"34\" "
        "rx=\"5\" fill=\"#111920\" stroke=\"#3a4650\" />"
        f"<text x=\"{_num(mid_x)}\" y=\"{_num(mid_y + 4)}\" text-anchor=\"middle\" "
        f"class=\"tiny\">{_esc(label)}</text>"
        "</g>"
    )


def _departed_summary(scene: TerminalVisualScene) -> str:
    if not scene.departed_vessels:
        return ""
    labels = []
    for vessel in scene.departed_vessels[:5]:
        cargo = ""
        if vessel.cargo:
            cargo = " (" + ", ".join(
                f"{badge.group_id} {badge.teu:g} TEU" for badge in vessel.cargo[:2]
            ) + ")"
        labels.append(vessel.vessel_id + cargo)
    if len(scene.departed_vessels) > 5:
        labels.append(f"+{len(scene.departed_vessels) - 5} more")
    return (
        f"<text x=\"{_num(layout.QUAY_X)}\" y=\"{_num(layout.GATE_Y + 28)}\" "
        f"class=\"small\">{_esc('Departed: ' + ', '.join(labels))}</text>"
    )


def _legend() -> str:
    x = layout.QUAY_X
    y = layout.SCENE_HEIGHT - 48
    return (
        f"<g><text x=\"{_num(x)}\" y=\"{_num(y)}\" class=\"caption\">"
        "Legend: Vessel | Quay Crane | Yard Block | Active Cargo Flow | Failed Resource | Reservation"
        "</text>"
        f"<text x=\"{_num(x)}\" y=\"{_num(y + 18)}\" class=\"caption\">"
        "Operation arrows are logical cargo flows, not physical transport routes."
        "</text></g>"
    )


def _cargo_lines(
    badges: tuple[CargoBadgeVisual, ...],
    x: float,
    y: float,
    *,
    prefix: str = "",
) -> str:
    if not badges:
        return ""
    visible = badges[:2]
    parts = []
    for index, badge in enumerate(visible):
        parts.append(
            f"<text x=\"{_num(x)}\" y=\"{_num(y + index * 14)}\" "
            f"class=\"tiny\">{_esc(prefix + badge.group_id + ' ' + f'{badge.teu:g}' + ' TEU')}</text>"
        )
    if len(badges) > len(visible):
        parts.append(
            f"<text x=\"{_num(x)}\" y=\"{_num(y + len(visible) * 14)}\" "
            f"class=\"tiny\">{_esc('+' + str(len(badges) - len(visible)) + ' more')}</text>"
        )
    return "".join(parts)


def _has_selected_group(
    badges: tuple[CargoBadgeVisual, ...],
    selected_group_id: str | None,
) -> bool:
    return selected_group_id is not None and any(
        badge.group_id == selected_group_id for badge in badges
    )


def _short_caps(capabilities: tuple[str, ...]) -> str:
    names = {
        "general": "GENERAL",
        "reefer_power": "REEFER",
        "hazardous": "HAZ",
        "empty": "EMPTY",
    }
    return " / ".join(names.get(capability, capability.upper()) for capability in capabilities)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _num(value: float) -> str:
    if not math.isfinite(value):
        return "0"
    return f"{value:.2f}".rstrip("0").rstrip(".")

