from __future__ import annotations

import html
import math

from app.visual import layout
from app.visual.models import TerminalReplayScene


STATUS_STYLES = {
    "arrived": ("#675f22", "#f5d76e"),
    "waiting": ("#675f22", "#f5d76e"),
    "berthed": ("#23635a", "#7de2d1"),
    "operating": ("#1d6b47", "#7ee2a8"),
    "ready_to_depart": ("#245b86", "#8fc7ff"),
    "departed": ("#404954", "#9aa8b3"),
    "available": ("#1d6b47", "#7ee2a8"),
    "assigned": ("#245b86", "#8fc7ff"),
    "failed": ("#7a2525", "#ff8b8b"),
    "open": ("#1f5d46", "#83e0b0"),
}


def render_terminal_replay_svg(
    scene: TerminalReplayScene,
    *,
    selected_vessel_id: str | None = None,
    selected_crane_id: str | None = None,
    selected_yard_id: str | None = None,
) -> str:
    parts = [
        f"<svg viewBox='0 0 {_num(scene.width)} {_num(scene.height)}' "
        "width='100%' preserveAspectRatio='xMidYMid meet' "
        "role='img' aria-label='MiniPortSim terminal replay'>",
        _defs(),
        _background(scene),
    ]
    parts.extend(_berth(berth) for berth in scene.berths)
    parts.extend(
        _vessel(vessel, selected=vessel.vessel_id == selected_vessel_id)
        for vessel in scene.berthed_vessels
    )
    parts.append(_anchorage(scene, selected_vessel_id=selected_vessel_id))
    parts.extend(
        _crane(crane, selected=crane.crane_id == selected_crane_id)
        for crane in scene.cranes
    )
    parts.extend(
        _yard(yard, selected=yard.yard_id == selected_yard_id)
        for yard in scene.yards
    )
    parts.append(_departed(scene))
    parts.append(_legend())
    parts.append("</svg>")
    return "".join(parts)


def _defs() -> str:
    return """
<defs>
  <pattern id="mpsWaterLines" patternUnits="userSpaceOnUse" width="36" height="20">
    <path d="M0 10 H36" stroke="#2a6f85" stroke-width="1" opacity="0.35" />
  </pattern>
</defs>
"""


def _background(scene: TerminalReplayScene) -> str:
    title = "No replay frame"
    if scene.event_id is not None:
        title = f"{scene.event_id} | {scene.event_type}"
    return (
        f"<rect x='0' y='0' width='{_num(scene.width)}' height='{_num(scene.height)}' fill='#0b1117' />"
        f"<rect x='0' y='0' width='{_num(scene.width)}' height='{_num(layout.QUAY_Y - 6)}' fill='#0d3342' />"
        f"<rect x='0' y='0' width='{_num(scene.width)}' height='{_num(layout.QUAY_Y - 6)}' fill='url(#mpsWaterLines)' opacity='0.55' />"
        f"<text x='{_num(layout.MARGIN_X)}' y='30' class='map-title'>SEA / APPROACH / WAITING AREA</text>"
        f"<text x='{_num(scene.width - layout.MARGIN_X)}' y='30' text-anchor='end' class='caption'>{_esc(title)}</text>"
        f"<rect x='0' y='{_num(layout.QUAY_Y + 18)}' width='{_num(scene.width)}' height='36' fill='#202a33' />"
        f"<line x1='{_num(layout.QUAY_X)}' y1='{_num(layout.QUAY_Y)}' "
        f"x2='{_num(layout.QUAY_X + layout.QUAY_WIDTH)}' y2='{_num(layout.QUAY_Y)}' "
        "stroke='#d6d1bd' stroke-width='8' />"
        f"<text x='{_num(scene.width / 2)}' y='{_num(layout.QUAY_Y + 43)}' "
        "text-anchor='middle' class='section-label'>QUAY / BERTH / APRON</text>"
        f"<text x='{_num(layout.MARGIN_X)}' y='{_num(layout.YARD_Y - 18)}' class='section-label'>YARD</text>"
        "<style>"
        ".map-title{font:700 18px sans-serif;fill:#cfe8ef;letter-spacing:0}"
        ".section-label{font:700 13px sans-serif;fill:#d9e2e8;letter-spacing:0}"
        ".caption{font:12px sans-serif;fill:#9fb4c2}"
        ".label{font:700 13px sans-serif;fill:#f4f8fa;letter-spacing:0}"
        ".small{font:11px sans-serif;fill:#dce7eb;letter-spacing:0}"
        ".tiny{font:10px sans-serif;fill:#c7d4da;letter-spacing:0}"
        ".highlight{stroke:#f4d35e!important;stroke-width:4!important}"
        "</style>"
    )


def _berth(berth) -> str:
    rect = berth.rect
    return (
        f"<g><title>{_esc(berth.berth_id)} | {berth.length_m:g} m | min_clearance_m {berth.min_clearance_m:g}</title>"
        f"<rect x='{_num(rect.x)}' y='{_num(rect.y)}' width='{_num(rect.width)}' "
        f"height='{_num(rect.height)}' fill='#303943' stroke='#d6d1bd' stroke-width='2' />"
        f"<text x='{_num(rect.x + 6)}' y='{_num(rect.y - 6)}' class='tiny'>0m</text>"
        f"<text x='{_num(rect.x + rect.width - 4)}' y='{_num(rect.y - 6)}' text-anchor='end' class='tiny'>{_esc(f'{berth.length_m:g}m')}</text>"
        f"<text x='{_num(rect.center_x)}' y='{_num(rect.center_y + 5)}' text-anchor='middle' class='label'>{_esc(berth.berth_id)}</text>"
        "</g>"
    )


def _vessel(vessel, *, selected: bool) -> str:
    rect = vessel.rect
    fill, stroke = STATUS_STYLES.get(vessel.status, ("#263746", "#9fb4c2"))
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
    length = "-" if vessel.length_m is None else f"{vessel.length_m:g} m"
    pos = "" if vessel.start_position_m is None else f" @ {vessel.start_position_m:g} m"
    return (
        f"<g><title>{_esc(vessel.vessel_id)} | {_esc(vessel.status.upper())} | {length}{_esc(pos)}</title>"
        f"<polygon points='{point_text}' fill='{fill}' stroke='{stroke}' stroke-width='2.5' class='{cls.strip()}' />"
        f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + 25)}' text-anchor='middle' class='label'>{_esc(vessel.vessel_id)}</text>"
        f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + 43)}' text-anchor='middle' class='small'>{_esc(vessel.status.upper())}</text>"
        f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + 60)}' text-anchor='middle' class='tiny'>{_esc(length)}</text>"
        "</g>"
    )


def _anchorage(scene: TerminalReplayScene, *, selected_vessel_id: str | None) -> str:
    if not scene.waiting_vessels:
        return ""
    parts = [
        f"<text x='{_num(layout.QUAY_X + 24)}' y='{_num(layout.WATER_TOP + 44)}' "
        "class='section-label'>WAITING VESSELS</text>"
    ]
    for vessel in scene.waiting_vessels:
        rect = vessel.rect
        fill, stroke = STATUS_STYLES.get(vessel.status, ("#263746", "#9fb4c2"))
        cls = " highlight" if vessel.vessel_id == selected_vessel_id else ""
        parts.append(
            f"<g><title>{_esc(vessel.vessel_id)} | {_esc(vessel.status.upper())}</title>"
            f"<rect x='{_num(rect.x)}' y='{_num(rect.y)}' width='{_num(rect.width)}' height='{_num(rect.height)}' "
            f"rx='20' fill='{fill}' stroke='{stroke}' stroke-width='2' class='{cls.strip()}' />"
            f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + 23)}' text-anchor='middle' class='label'>{_esc(vessel.vessel_id)}</text>"
            f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + 42)}' text-anchor='middle' class='small'>{_esc(vessel.status.upper())}</text>"
            "</g>"
        )
    return "".join(parts)


def _crane(crane, *, selected: bool) -> str:
    rect = crane.rect
    fill, stroke = STATUS_STYLES.get(crane.status, ("#263746", "#9fb4c2"))
    cls = " highlight" if selected else ""
    assignment = crane.assigned_vessel_id or ""
    if crane.task_id:
        assignment = f"{assignment} / {crane.task_id}".strip(" /")
    return (
        f"<g><title>{_esc(crane.crane_id)} | {_esc(crane.status.upper())} | {crane.position_m:g} m</title>"
        f"<line x1='{_num(rect.center_x)}' y1='{_num(layout.QUAY_Y + 2)}' "
        f"x2='{_num(rect.center_x)}' y2='{_num(rect.y + 44)}' stroke='{stroke}' stroke-width='3' />"
        f"<rect x='{_num(rect.x)}' y='{_num(rect.y)}' width='{_num(rect.width)}' height='{_num(rect.height)}' "
        f"rx='5' fill='{fill}' stroke='{stroke}' stroke-width='2' class='{cls.strip()}' />"
        f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + 22)}' text-anchor='middle' class='label'>{_esc(crane.crane_id)}</text>"
        f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + 41)}' text-anchor='middle' class='small'>{_esc(crane.status.upper())}</text>"
        f"<text x='{_num(rect.center_x)}' y='{_num(rect.y + rect.height + 14)}' text-anchor='middle' class='tiny'>{_esc(assignment)}</text>"
        "</g>"
    )


def _yard(yard, *, selected: bool) -> str:
    rect = yard.rect
    fill, stroke = STATUS_STYLES.get(yard.status, ("#132119", "#83e0b0"))
    cls = " highlight" if selected else ""
    bar_x = rect.x + 14
    bar_y = rect.y + 48
    bar_width = rect.width - 28
    return (
        f"<g><title>{_esc(yard.yard_id)} | {yard.occupied_teu:g}/{yard.capacity_teu:g} TEU</title>"
        f"<rect x='{_num(rect.x)}' y='{_num(rect.y)}' width='{_num(rect.width)}' height='{_num(rect.height)}' "
        f"rx='7' fill='{fill}' stroke='{stroke}' stroke-width='2' class='{cls.strip()}' />"
        f"<rect x='{_num(bar_x)}' y='{_num(bar_y)}' width='{_num(bar_width)}' height='14' rx='4' fill='#26323c' />"
        f"<rect x='{_num(bar_x)}' y='{_num(bar_y)}' width='{_num(bar_width * yard.utilization)}' height='14' rx='4' fill='#2ec4b6' />"
        f"<text x='{_num(rect.x + 14)}' y='{_num(rect.y + 24)}' class='label'>{_esc(yard.yard_id)}</text>"
        f"<text x='{_num(rect.x + rect.width - 14)}' y='{_num(rect.y + 24)}' text-anchor='end' class='small'>{yard.utilization * 100:.0f}%</text>"
        f"<text x='{_num(rect.x + 14)}' y='{_num(rect.y + 80)}' class='small'>{yard.occupied_teu:g} / {yard.capacity_teu:g} TEU</text>"
        "</g>"
    )


def _departed(scene: TerminalReplayScene) -> str:
    if not scene.departed_vessels:
        return ""
    labels = ", ".join(vessel.vessel_id for vessel in scene.departed_vessels[:8])
    if len(scene.departed_vessels) > 8:
        labels += f", +{len(scene.departed_vessels) - 8} more"
    return (
        f"<text x='{_num(layout.QUAY_X)}' y='{_num(scene.height - 72)}' class='small'>"
        f"{_esc('Departed: ' + labels)}</text>"
    )


def _legend() -> str:
    return (
        f"<text x='{_num(layout.QUAY_X)}' y='{_num(layout.SCENE_HEIGHT - 38)}' class='caption'>"
        "Legend: waiting vessel | berthed/operating vessel | quay crane | failed resource | yard occupancy"
        "</text>"
    )


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _num(value: float) -> str:
    if not math.isfinite(value):
        return "0"
    return f"{value:.2f}".rstrip("0").rstrip(".")

