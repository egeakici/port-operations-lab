"""Project 02-colored quay SVG and retrospective Plotly space-time diagram."""

from __future__ import annotations

from html import escape

from berth_allocation_lab.replay.records import ReplayRun, ReplayScenario
from berth_allocation_lab.replay.timeline import ReplaySnapshot, space_time_rectangles

WATER = "#0d3342"
QUAY = "#303d45"
TEAL = "#2ec4b6"
AMBER = "#f4d35e"
TEXT = "#f4f8fa"
MUTED = "#9fb4c2"


def quay_scale(berth_length_m: float, position_m: float, length_m: float,
               *, left_px: float = 46.0, span_px: float = 908.0) -> tuple[float, float]:
    if berth_length_m <= 0 or position_m < -1e-6 or length_m <= 0 or (
            position_m + length_m > berth_length_m + 1e-6):
        raise ValueError("Vessel geometry exceeds the continuous quay.")
    return left_px + span_px * position_m / berth_length_m, span_px * length_m / berth_length_m


def render_quay_svg(scenario: ReplayScenario, run: ReplayRun,
                    state: ReplaySnapshot, selected_vessel_id: str | None = None) -> str:
    length = scenario.berth_length_m
    tick_step = 100 if length <= 700 else 250 if length <= 1600 else 500
    ticks = list(range(0, int(length) + 1, tick_step))
    if not ticks or ticks[-1] != length:
        ticks.append(length)
    parts = [
        "<svg viewBox='0 0 1000 230' xmlns='http://www.w3.org/2000/svg' "
        "role='img' aria-label='Continuous quay replay' "
        "style='width:100%;height:auto;display:block;font-family:Inter,Arial,sans-serif'>",
        "<style>@media (max-width:600px) {"
        ".map-caption {font-size:30px} .ship-id {font-size:36px} "
        ".scale-label {font-size:25px}}</style>",
        "<rect width='1000' height='230' fill='#0b1117'/>",
        "<rect x='0' y='0' width='1000' height='154' fill='#0d3342'/>",
        "<path d='M0 30 H1000 M0 68 H1000 M0 106 H1000' stroke='#2a6f85' "
        "stroke-opacity='.25'/>",
        f"<text class='map-caption' x='46' y='28' fill='{MUTED}' font-size='13'>SEA / ACTIVE SERVICE</text>",
        f"<text class='map-caption' x='954' y='28' text-anchor='end' fill='{MUTED}' font-size='13'>"
        f"t = {state.time_min:,.1f} min</text>",
        f"<rect x='46' y='154' width='908' height='36' fill='{QUAY}'/>",
        "<path d='M46 154 H954' stroke='#7de2d1' stroke-width='3'/>",
    ]
    for vessel in run.vessels:
        if vessel.vessel_id not in state.active:
            continue
        x, width = quay_scale(length, vessel.berth_position_m, vessel.length_m)
        selected = selected_vessel_id == vessel.vessel_id
        stroke = AMBER if selected else "#7de2d1"
        parts.extend([
            f"<g><title>{escape(vessel.vessel_id)} | {vessel.length_m:g} m | "
            f"{vessel.berth_position_m:g}-{vessel.berth_position_m + vessel.length_m:g} m</title>",
            f"<rect x='{x:.3f}' y='91' width='{width:.3f}' height='52' rx='5' "
            f"fill='#23635a' stroke='{stroke}' stroke-width='{3 if selected else 2}'/>",
            f"<path d='M{x+8:.3f} 98 H{x+width-15:.3f} L{x+width-7:.3f} 117 "
            f"L{x+width-15:.3f} 136 H{x+8:.3f} Z' fill='#2ec4b6' opacity='.30'/>",
            f"<text class='ship-id' x='{x+width/2:.3f}' y='121' text-anchor='middle' fill='{TEXT}' "
            f"font-size='15' font-weight='700'>{escape(vessel.vessel_id)}</text></g>",
        ])
        if scenario.min_clearance_m and vessel.berth_position_m + vessel.length_m < length:
            margin = min(scenario.min_clearance_m, length - vessel.berth_position_m - vessel.length_m)
            end_x, _ = quay_scale(length, vessel.berth_position_m + vessel.length_m, margin)
            parts.append(f"<path d='M{end_x:.3f} 148 H{end_x + 908*margin/length:.3f}' "
                         f"stroke='{AMBER}' stroke-width='3' stroke-dasharray='3 3' opacity='.85'/>")
    for tick in ticks:
        x = 46 + 908 * tick / length
        anchor = "start" if tick == 0 else "end" if tick == length else "middle"
        parts.extend((f"<path d='M{x:.3f} 190 V199' stroke='{MUTED}'/>",
                      f"<text class='scale-label' x='{x:.3f}' y='215' text-anchor='{anchor}' fill='{MUTED}' "
                      f"font-size='12'>{tick:g} m</text>"))
    parts.append("</svg>")
    return "".join(parts)


def space_time_figure(scenario: ReplayScenario, run: ReplayRun,
                      time_min: float, selected_vessel_id: str | None = None):
    import plotly.graph_objects as go

    figure = go.Figure()
    by_id = {v.vessel_id: v for v in run.vessels}
    for vessel_id, x0, x1, y0, y1 in space_time_rectangles(run):
        vessel = by_id[vessel_id]
        selected = selected_vessel_id == vessel_id
        figure.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                         fillcolor=TEAL, opacity=0.68 if selected else 0.42,
                         line={"color": AMBER if selected else "#7de2d1",
                               "width": 3 if selected else 1})
        figure.add_trace(go.Scatter(
            x=[(x0+x1)/2], y=[(y0+y1)/2], mode="markers+text",
            marker={"size": 18, "opacity": 0.01}, text=[vessel_id],
            textposition="middle center", textfont={"color": TEXT, "size": 11},
            customdata=[[x0, x1-x0, y0, y1, vessel.waiting_time_min]],
            hovertemplate=("%{text}<br>Position %{customdata[0]:.1f} m"
                           "<br>Length %{customdata[1]:.1f} m"
                           "<br>Service %{customdata[2]:.1f} to %{customdata[3]:.1f} min"
                           "<br>Waiting %{customdata[4]:.1f} min<extra></extra>"),
            showlegend=False,
        ))
    figure.add_hline(y=time_min, line_color=AMBER, line_dash="dash",
                     annotation_text=f"Current t={time_min:,.1f} min",
                     annotation_position="top right")
    figure.update_layout(
        title="Retrospective berth allocation | held-out synthetic test",
        xaxis={"title": "Berth position (m)", "range": [0, scenario.berth_length_m],
               "gridcolor": "#30424d"},
        yaxis={"title": "Simulation time (min)", "range": [0, max(v.service_end_time_min
                    for v in run.vessels) * 1.03], "gridcolor": "#30424d"},
        height=570, margin={"l": 45, "r": 20, "t": 55, "b": 50},
        paper_bgcolor="#0b1117", plot_bgcolor="#0d1c25", font={"color": TEXT},
        showlegend=False,
    )
    return figure
