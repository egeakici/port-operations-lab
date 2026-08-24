from __future__ import annotations

import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
for path in (
    PROJECT_ROOT,
    PROJECT_ROOT / "src",
    REPO_ROOT / "01-terminal-operations-core" / "src",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import streamlit as st
import streamlit.components.v1 as components

from app import session_store
from app.presenters import (
    format_minutes,
    format_number,
    format_percent,
    json_bytes,
    simulation_clock,
)
from app.simulation_service import (
    build_custom_scenario,
    default_scenario_option,
    event_rows_csv_bytes,
    filter_event_rows,
    list_scenario_options,
    load_preset_scenario,
    nearest_replay_frame_index,
    run_simulation_from_ui,
)
from app.styles import apply_styles
from app.ui_helpers import date_time_input, download_json_button, metric_card
from app.visual.svg_renderer import render_terminal_replay_svg
from app.visual.terminal_replay import (
    build_terminal_replay_scene,
    current_waiting_queue,
)
from mini_port_sim import ScenarioConfig, TerminationMode


DEFAULT_START_TIME = datetime(2026, 8, 20, 8, 0)


def main() -> None:
    st.set_page_config(
        page_title="Mini Port Simulation Lab",
        page_icon="MP",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    session_store.initialize_session()
    apply_styles()

    st.title("Mini Port Simulation Lab")
    st.markdown(
        "<p class='mps-subtitle'>Run, replay, and inspect discrete-event "
        "container terminal simulations powered by MiniPortSim.</p>",
        unsafe_allow_html=True,
    )

    _render_sidebar()
    bundle = st.session_state[session_store.RUN_BUNDLE]

    if st.session_state[session_store.RUN_ERROR]:
        st.error(st.session_state[session_store.RUN_ERROR])

    if bundle is None:
        st.info("Choose a preset or custom scenario in the sidebar, then run the simulation.")
        return

    tabs = st.tabs(["Overview", "Terminal Replay", "Timelines", "Events", "Scenario"])
    with tabs[0]:
        _render_overview(bundle)
    with tabs[1]:
        _render_replay(bundle)
    with tabs[2]:
        _render_timelines(bundle)
    with tabs[3]:
        _render_events(bundle)
    with tabs[4]:
        _render_scenario(bundle)


def _render_sidebar() -> None:
    st.sidebar.header("Simulation Control")
    scenario_options = list_scenario_options()
    if not scenario_options:
        st.sidebar.error("No scenario JSON files were found.")
        return

    mode = st.sidebar.radio(
        "Scenario mode",
        ("Preset", "Custom"),
        key=session_store.SCENARIO_MODE,
        horizontal=True,
    )
    start_time = date_time_input(
        "Simulation start time",
        default=DEFAULT_START_TIME,
        key="mps_start_time",
    )

    scenario: ScenarioConfig | None = None
    if mode == "Preset":
        scenario = _render_preset_controls(scenario_options)
    else:
        scenario = _render_custom_controls()

    if st.sidebar.button("Run Simulation", type="primary", use_container_width=True):
        if scenario is None:
            session_store.store_error("No valid scenario is selected.")
            return
        try:
            with st.spinner("Running MiniPortSim..."):
                bundle = run_simulation_from_ui(
                    scenario,
                    start_time=start_time,
                )
            session_store.store_run(bundle)
            st.success("Simulation completed.")
            st.rerun()
        except Exception as error:
            session_store.store_error(f"{type(error).__name__}: {error}")


def _render_preset_controls(
    scenario_options,
) -> ScenarioConfig | None:
    default = default_scenario_option(scenario_options)
    default_index = scenario_options.index(default) if default is not None else 0
    selected = st.sidebar.selectbox(
        "Load Scenario",
        options=scenario_options,
        index=default_index,
        format_func=lambda option: option.label,
        key=session_store.SELECTED_SCENARIO_PATH,
    )
    seed = st.sidebar.number_input(
        "Seed",
        min_value=0,
        max_value=2_147_483_647,
        value=int(st.session_state[session_store.SEED]),
        step=1,
        key=session_store.SEED,
    )
    st.sidebar.caption(
        f"Duration: {selected.scenario.duration_hours:g} h | "
        f"Mode: {selected.scenario.termination_mode.value.upper()}"
    )
    return load_preset_scenario(selected.path, seed=int(seed))


def _render_custom_controls() -> ScenarioConfig | None:
    seed = st.sidebar.number_input(
        "Seed",
        min_value=0,
        max_value=2_147_483_647,
        value=int(st.session_state[session_store.SEED]),
        step=1,
        key=session_store.SEED,
    )
    with st.sidebar.expander("Simulation", expanded=True):
        scenario_id = st.text_input("Scenario ID", value="custom_lab")
        duration_hours = st.number_input(
            "Duration hours",
            min_value=0.1,
            max_value=720.0,
            value=72.0,
            step=1.0,
        )
        termination_mode = st.selectbox(
            "Termination mode",
            [mode.value for mode in TerminationMode],
            index=0,
        )
        max_drain_extension_hours = st.number_input(
            "Max drain extension hours",
            min_value=0.0,
            max_value=720.0,
            value=168.0,
            step=1.0,
        )

    with st.sidebar.expander("Traffic", expanded=True):
        vessel_count = st.number_input("Vessel count", 1, 200, 32, 1)
        mean_interarrival_minutes = st.number_input(
            "Mean interarrival minutes",
            1.0,
            1440.0,
            150.0,
            5.0,
        )
        min_vessel_length_m = st.number_input("Min vessel length m", 1.0, 500.0, 180.0, 5.0)
        max_vessel_length_m = st.number_input("Max vessel length m", 1.0, 500.0, 360.0, 5.0)
        min_workload_moves = st.number_input("Min workload moves", 1, 5000, 250, 10)
        max_workload_moves = st.number_input("Max workload moves", 1, 5000, 1000, 10)

    with st.sidebar.expander("Terminal / Berth / Cranes / Yard", expanded=True):
        berth_length_m = st.number_input("Berth length m", 100.0, 5000.0, 1200.0, 50.0)
        min_clearance_m = st.number_input("min_clearance_m", 0.0, 200.0, 20.0, 1.0)
        quay_crane_count = st.number_input("Quay crane count", 1, 20, 5, 1)
        quay_crane_moves_per_hour = st.number_input(
            "Quay crane moves/hour",
            1.0,
            120.0,
            30.0,
            1.0,
        )
        yard_block_count = st.number_input("Yard block count", 1, 20, 4, 1)
        yard_block_capacity_teu = st.number_input(
            "Yard block capacity TEU",
            1.0,
            20000.0,
            2200.0,
            100.0,
        )

    with st.sidebar.expander("Service", expanded=False):
        berthing_preparation_minutes = st.number_input("Berthing prep minutes", 0.0, 1440.0, 30.0, 5.0)
        service_minutes_per_move = st.number_input("Service minutes per move", 0.01, 10.0, 0.5, 0.05)
        departure_preparation_minutes = st.number_input("Departure prep minutes", 0.0, 1440.0, 20.0, 5.0)
        two_crane_efficiency = st.slider("Two crane efficiency", 0.1, 1.0, 0.92, 0.01)
        three_crane_efficiency = st.slider("Three crane efficiency", 0.1, 1.0, 0.82, 0.01)
        four_plus_crane_efficiency = st.slider("Four plus crane efficiency", 0.1, 1.0, 0.72, 0.01)

    with st.sidebar.expander("Disruptions", expanded=False):
        eta_delay_stddev_minutes = st.number_input("ETA delay stddev minutes", 0.0, 1440.0, 20.0, 5.0)
        productivity_min_factor = st.slider("Productivity min factor", 0.1, 2.0, 0.85, 0.01)
        productivity_max_factor = st.slider("Productivity max factor", 0.1, 2.0, 1.08, 0.01)
        crane_failures_enabled = st.checkbox("Crane failures enabled", value=True)
        mean_time_to_failure_minutes = st.number_input("Mean time to failure minutes", 1.0, 10000.0, 900.0, 30.0)
        mean_repair_minutes = st.number_input("Mean repair minutes", 1.0, 5000.0, 90.0, 10.0)

    try:
        return build_custom_scenario(
            scenario_id=scenario_id,
            duration_hours=duration_hours,
            seed=int(seed),
            termination_mode=termination_mode,
            max_drain_extension_hours=max_drain_extension_hours,
            terminal={
                "berth_length_m": berth_length_m,
                "min_clearance_m": min_clearance_m,
                "quay_crane_count": quay_crane_count,
                "quay_crane_moves_per_hour": quay_crane_moves_per_hour,
                "yard_block_count": yard_block_count,
                "yard_block_capacity_teu": yard_block_capacity_teu,
            },
            traffic={
                "vessel_count": vessel_count,
                "mean_interarrival_minutes": mean_interarrival_minutes,
                "min_vessel_length_m": min_vessel_length_m,
                "max_vessel_length_m": max_vessel_length_m,
                "min_workload_moves": min_workload_moves,
                "max_workload_moves": max_workload_moves,
            },
            service={
                "berthing_preparation_minutes": berthing_preparation_minutes,
                "service_minutes_per_move": service_minutes_per_move,
                "departure_preparation_minutes": departure_preparation_minutes,
                "two_crane_efficiency": two_crane_efficiency,
                "three_crane_efficiency": three_crane_efficiency,
                "four_plus_crane_efficiency": four_plus_crane_efficiency,
            },
            disruptions={
                "eta_delay_stddev_minutes": eta_delay_stddev_minutes,
                "productivity_min_factor": productivity_min_factor,
                "productivity_max_factor": productivity_max_factor,
                "crane_failures_enabled": crane_failures_enabled,
                "mean_time_to_failure_minutes": mean_time_to_failure_minutes,
                "mean_repair_minutes": mean_repair_minutes,
            },
        )
    except ValueError as error:
        st.sidebar.error(str(error))
        return None


def _render_overview(bundle) -> None:
    metrics = bundle.metrics
    scenario = bundle.scenario
    st.subheader("Run Summary")
    st.markdown(
        "<div class='mps-strip'>"
        f"<span class='mps-chip'>{scenario.scenario_id}</span>"
        f"<span class='mps-chip'>Seed {scenario.seed}</span>"
        f"<span class='mps-chip'>{scenario.termination_mode.value.upper()}</span>"
        f"<span class='mps-chip'>{format_minutes(metrics.duration_minutes)}</span>"
        f"<span class='mps-chip'>{metrics.event_count} events</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.write("")
    top = st.columns(5)
    with top[0]:
        metric_card("Completed Vessels", format_number(metrics.completed_vessel_count))
    with top[1]:
        metric_card("Unfinished Vessels", format_number(metrics.unfinished_vessel_count))
    with top[2]:
        metric_card("Throughput", format_number(metrics.throughput_vessels_per_day), "vessels/day")
    with top[3]:
        metric_card("Average Waiting", format_minutes(metrics.average_waiting_time_minutes))
    with top[4]:
        metric_card("P95 Waiting", format_minutes(metrics.p95_waiting_time_minutes))

    second = st.columns(5)
    with second[0]:
        metric_card("Average Turnaround", format_minutes(metrics.average_turnaround_time_minutes))
    with second[1]:
        metric_card("Berth Utilization", format_percent(metrics.berth_utilization))
    with second[2]:
        metric_card("Crane Utilization", format_percent(metrics.crane_utilization))
    with second[3]:
        metric_card("Peak Yard Utilization", format_percent(metrics.peak_yard_utilization))
    with second[4]:
        metric_card("Handled Moves", format_number(metrics.total_handled_moves))

    with st.expander("Secondary metrics"):
        rows = {
            "Median waiting": format_minutes(metrics.median_waiting_time_minutes),
            "Current waiting vessels": format_number(metrics.waiting_vessel_count_at_end),
            "Oldest current waiting vessel": format_minutes(metrics.max_current_wait_age_minutes),
            "Crane downtime": format_minutes(metrics.crane_downtime_minutes),
            "Crane failure count": format_number(metrics.crane_failure_count),
            "Average crane downtime": format_minutes(metrics.average_crane_downtime_minutes),
            "Crane idle time": format_minutes(metrics.crane_idle_minutes),
            "Final yard utilization": format_percent(metrics.final_yard_utilization),
            "Average yard utilization": format_percent(metrics.average_yard_utilization),
            "Yard rejection count": format_number(metrics.yard_capacity_rejection_count),
            "Max queue length": format_number(metrics.max_queue_length),
        }
        st.table([{"Metric": key, "Value": value} for key, value in rows.items()])

    st.subheader("Vessel KPIs")
    st.dataframe(
        [
            {
                "Vessel": vessel.vessel_id,
                "Arrival": format_minutes(vessel.arrival_time_minutes),
                "Wait": format_minutes(vessel.waiting_time_minutes),
                "Operation start": format_minutes(vessel.operation_start_minutes),
                "Operation end": format_minutes(vessel.operation_end_minutes),
                "Departure": format_minutes(vessel.departure_time_minutes),
                "Turnaround": format_minutes(vessel.turnaround_time_minutes),
                "ETA deviation": format_minutes(vessel.eta_deviation_minutes),
            }
            for vessel in metrics.vessel_metrics
        ],
        use_container_width=True,
        hide_index=True,
    )


def _render_replay(bundle) -> None:
    frames = bundle.result.replay_frames
    if not frames:
        st.warning("This run has no replay frames.")
        return

    index = int(st.session_state[session_store.REPLAY_INDEX])
    index = max(0, min(index, len(frames) - 1))
    st.session_state[session_store.REPLAY_INDEX] = index
    scene = build_terminal_replay_scene(bundle, index)

    _render_replay_controls(bundle, scene)
    selector_cols = st.columns(3)
    selected_vessel = selector_cols[0].selectbox(
        "Inspect vessel",
        ("None",) + tuple(
            sorted(
                {
                    vessel.vessel_id
                    for vessel in (
                        scene.waiting_vessels
                        + scene.berthed_vessels
                        + scene.departed_vessels
                    )
                }
            )
        ),
        key=session_store.SELECTED_VESSEL_ID,
    )
    selected_crane = selector_cols[1].selectbox(
        "Inspect crane",
        ("None",) + tuple(crane.crane_id for crane in scene.cranes),
        key=session_store.SELECTED_CRANE_ID,
    )
    selected_yard = selector_cols[2].selectbox(
        "Inspect yard",
        ("None",) + tuple(yard.yard_id for yard in scene.yards),
        key=session_store.SELECTED_YARD_ID,
    )

    svg = render_terminal_replay_svg(
        scene,
        selected_vessel_id=None if selected_vessel == "None" else selected_vessel,
        selected_crane_id=None if selected_crane == "None" else selected_crane,
        selected_yard_id=None if selected_yard == "None" else selected_yard,
    )
    components.html(svg, height=760, scrolling=False)

    left, right = st.columns([1.1, 1])
    with left:
        _render_waiting_queue(bundle, index)
    with right:
        _render_entity_inspector(
            bundle,
            scene,
            None if selected_vessel == "None" else selected_vessel,
            None if selected_crane == "None" else selected_crane,
            None if selected_yard == "None" else selected_yard,
        )

    if st.session_state[session_store.REPLAY_PLAYING]:
        speed = float(st.session_state[session_store.REPLAY_SPEED])
        if index < len(frames) - 1:
            time.sleep(max(0.15, 0.8 / speed))
            st.session_state[session_store.REPLAY_INDEX] = index + 1
            st.rerun()
        st.session_state[session_store.REPLAY_PLAYING] = False


def _render_replay_controls(bundle, scene) -> None:
    frames = bundle.result.replay_frames
    st.subheader("Terminal Replay")
    st.caption(simulation_clock(bundle.result.simulation.start_time, scene.elapsed_minutes))
    controls = st.columns([0.7, 0.7, 0.9, 0.7, 0.7, 1.1, 4])
    if controls[0].button("|<", use_container_width=True):
        st.session_state[session_store.REPLAY_INDEX] = 0
        st.rerun()
    if controls[1].button("<", use_container_width=True):
        st.session_state[session_store.REPLAY_INDEX] = max(
            0,
            st.session_state[session_store.REPLAY_INDEX] - 1,
        )
        st.rerun()
    play_label = "Pause" if st.session_state[session_store.REPLAY_PLAYING] else "Play"
    if controls[2].button(play_label, use_container_width=True):
        st.session_state[session_store.REPLAY_PLAYING] = not st.session_state[
            session_store.REPLAY_PLAYING
        ]
        st.rerun()
    if controls[3].button(">", use_container_width=True):
        st.session_state[session_store.REPLAY_INDEX] = min(
            len(frames) - 1,
            st.session_state[session_store.REPLAY_INDEX] + 1,
        )
        st.rerun()
    if controls[4].button(">|", use_container_width=True):
        st.session_state[session_store.REPLAY_INDEX] = len(frames) - 1
        st.rerun()
    controls[5].selectbox(
        "Speed",
        (0.5, 1.0, 2.0, 5.0),
        index=(0.5, 1.0, 2.0, 5.0).index(
            st.session_state[session_store.REPLAY_SPEED]
        ),
        key=session_store.REPLAY_SPEED,
    )
    selected = controls[6].slider(
        "Event index",
        min_value=0,
        max_value=len(frames) - 1,
        value=int(st.session_state[session_store.REPLAY_INDEX]),
        key="mps_replay_slider",
    )
    if selected != st.session_state[session_store.REPLAY_INDEX]:
        st.session_state[session_store.REPLAY_INDEX] = selected
        st.rerun()


def _render_waiting_queue(bundle, frame_index: int) -> None:
    st.subheader("Waiting Queue")
    rows = current_waiting_queue(bundle, frame_index)
    if not rows:
        st.info("No vessels are waiting at this replay frame.")
        return
    st.dataframe(
        [
            {
                "#": index + 1,
                "Vessel": row["vessel_id"],
                "Status": str(row["status"]).upper(),
                "Waiting": format_minutes(float(row["waiting_minutes"])),
                "Workload": format_number(row["workload_moves"]),
            }
            for index, row in enumerate(rows)
        ],
        hide_index=True,
        use_container_width=True,
    )


def _render_entity_inspector(
    bundle,
    scene,
    vessel_id: str | None,
    crane_id: str | None,
    yard_id: str | None,
) -> None:
    st.subheader("Entity Inspector")
    if vessel_id:
        _render_vessel_inspector(bundle, scene, vessel_id)
    if crane_id:
        _render_crane_inspector(scene, crane_id)
    if yard_id:
        _render_yard_inspector(scene, yard_id)
    if not any((vessel_id, crane_id, yard_id)):
        st.info("Select a vessel, crane, or yard block above.")


def _render_vessel_inspector(bundle, scene, vessel_id: str) -> None:
    vessel_visual = next(
        (
            vessel
            for vessel in (
                scene.waiting_vessels
                + scene.berthed_vessels
                + scene.departed_vessels
            )
            if vessel.vessel_id == vessel_id
        ),
        None,
    )
    metrics = next(
        (
            vessel
            for vessel in bundle.metrics.vessel_metrics
            if vessel.vessel_id == vessel_id
        ),
        None,
    )
    plan = next(
        (
            plan
            for plan in bundle.result.simulation.arrival_plans
            if plan.vessel.vessel_id == vessel_id
        ),
        None,
    )
    rows = {
        "Vessel": vessel_id,
        "Status": vessel_visual.status.upper() if vessel_visual else "-",
        "Length": "-" if vessel_visual is None or vessel_visual.length_m is None else f"{vessel_visual.length_m:g} m",
        "Workload": format_number(plan.vessel.workload_moves if plan else None),
        "Planned arrival": format_minutes(plan.planned_arrival_time_minutes if plan else None),
        "Actual arrival": format_minutes(plan.arrival_time_minutes if plan else None),
        "Waiting time": format_minutes(metrics.waiting_time_minutes if metrics else None),
        "Berth": vessel_visual.berth_id if vessel_visual and vessel_visual.berth_id else "-",
        "Berth position": "-" if vessel_visual is None or vessel_visual.start_position_m is None else f"{vessel_visual.start_position_m:g} m",
        "Operation start": format_minutes(metrics.operation_start_minutes if metrics else None),
        "Operation end": format_minutes(metrics.operation_end_minutes if metrics else None),
        "Departure": format_minutes(metrics.departure_time_minutes if metrics else None),
    }
    st.table([{"Field": key, "Value": value} for key, value in rows.items()])


def _render_crane_inspector(scene, crane_id: str) -> None:
    crane = next((item for item in scene.cranes if item.crane_id == crane_id), None)
    if crane is None:
        return
    rows = {
        "Crane": crane.crane_id,
        "Status": crane.status.upper(),
        "Position": f"{crane.position_m:g} m",
        "Nominal moves/hour": format_number(crane.moves_per_hour),
        "Current vessel": crane.assigned_vessel_id or "-",
        "Current task": crane.task_id or "-",
    }
    st.table([{"Field": key, "Value": value} for key, value in rows.items()])


def _render_yard_inspector(scene, yard_id: str) -> None:
    yard = next((item for item in scene.yards if item.yard_id == yard_id), None)
    if yard is None:
        return
    rows = {
        "Yard block": yard.yard_id,
        "Status": yard.status.upper(),
        "Occupied": f"{yard.occupied_teu:g} TEU",
        "Capacity": f"{yard.capacity_teu:g} TEU",
        "Utilization": format_percent(yard.utilization),
        "Capability": "GENERAL",
    }
    st.table([{"Field": key, "Value": value} for key, value in rows.items()])


def _render_timelines(bundle) -> None:
    st.subheader("Timelines")
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("Install plotly from requirements-demo.txt to see interactive timelines.")
        st.json(
            {
                "berth_timeline": [
                    segment.to_dict() for segment in bundle.result.berth_timeline
                ],
                "vessel_timeline": [
                    segment.to_dict() for segment in bundle.result.vessel_timeline
                ],
                "crane_timeline": [
                    segment.to_dict() for segment in bundle.result.crane_timeline
                ],
            }
        )
        return

    timeline_tabs = st.tabs(["Berth Time-Space", "Vessels", "Cranes"])
    with timeline_tabs[0]:
        fig = go.Figure()
        for segment in bundle.result.berth_timeline:
            fig.add_shape(
                type="rect",
                x0=segment.start_minutes,
                x1=segment.end_minutes,
                y0=segment.start_position_m,
                y1=segment.end_position_m,
                fillcolor="#2ec4b6",
                opacity=0.55,
                line={"color": "#7de2d1"},
            )
            fig.add_annotation(
                x=(segment.start_minutes + segment.end_minutes) / 2,
                y=(segment.start_position_m + segment.end_position_m) / 2,
                text=segment.vessel_id,
                showarrow=False,
                font={"color": "white"},
            )
        fig.update_layout(
            xaxis_title="Simulation minutes",
            yaxis_title="Berth position (m)",
            height=430,
            margin={"l": 40, "r": 20, "t": 20, "b": 40},
        )
        st.plotly_chart(fig, use_container_width=True)

    with timeline_tabs[1]:
        st.plotly_chart(
            _bar_timeline_figure(
                [
                    {
                        "row": segment.vessel_id,
                        "state": segment.state,
                        "start": segment.start_minutes,
                        "end": segment.end_minutes,
                    }
                    for segment in bundle.result.vessel_timeline
                ],
                title="Vessel timeline",
            ),
            use_container_width=True,
        )

    with timeline_tabs[2]:
        st.plotly_chart(
            _bar_timeline_figure(
                _crane_timeline_with_idle(bundle),
                title="Crane timeline",
            ),
            use_container_width=True,
        )


def _bar_timeline_figure(rows: list[dict[str, object]], *, title: str):
    import plotly.graph_objects as go

    fig = go.Figure()
    colors = {
        "waiting": "#f4d35e",
        "berthed_preparation": "#7de2d1",
        "operating": "#2ec4b6",
        "ready_to_depart": "#8fc7ff",
        "failed": "#ff8b8b",
        "idle": "#52606b",
    }
    for row in rows:
        fig.add_trace(
            go.Bar(
                x=[float(row["end"]) - float(row["start"])],
                y=[row["row"]],
                base=[row["start"]],
                orientation="h",
                name=str(row["state"]),
                marker_color=colors.get(str(row["state"]), "#9fb4c2"),
                hovertext=(
                    f"{row['row']} | {row['state']} | "
                    f"{format_minutes(float(row['start']))} - "
                    f"{format_minutes(float(row['end']))}"
                ),
                showlegend=False,
            )
        )
    fig.update_layout(
        title=title,
        barmode="stack",
        xaxis_title="Simulation minutes",
        yaxis_title="Entity",
        height=max(360, 32 * len({row["row"] for row in rows}) + 120),
        margin={"l": 40, "r": 20, "t": 48, "b": 40},
    )
    return fig


def _crane_timeline_with_idle(bundle) -> list[dict[str, object]]:
    horizon = bundle.metrics.duration_minutes
    rows: list[dict[str, object]] = []
    by_crane: dict[str, list[tuple[float, float, str]]] = {
        crane_id: [] for crane_id in bundle.result.simulation.terminal.quay_crane_ids
    }
    for segment in bundle.result.crane_timeline:
        by_crane.setdefault(segment.crane_id, []).append(
            (segment.start_minutes, segment.end_minutes, segment.state)
        )
    for crane_id, segments in by_crane.items():
        cursor = 0.0
        for start, end, state in sorted(segments):
            if start > cursor:
                rows.append({"row": crane_id, "state": "idle", "start": cursor, "end": start})
            rows.append({"row": crane_id, "state": state, "start": start, "end": end})
            cursor = max(cursor, end)
        if cursor < horizon:
            rows.append({"row": crane_id, "state": "idle", "start": cursor, "end": horizon})
    return rows


def _render_events(bundle) -> None:
    st.subheader("Event Log")
    rows = bundle.event_rows
    event_types = sorted({row["event_type"] for row in rows})
    vessels = sorted({row["related_vessel"] for row in rows if row["related_vessel"]})
    cranes = sorted({row["related_crane"] for row in rows if row["related_crane"]})

    filters = st.columns([2, 1.3, 1.3, 2])
    selected_event_types = filters[0].multiselect("Event type", event_types)
    selected_vessel = filters[1].selectbox("Vessel", ("All",) + tuple(vessels))
    selected_crane = filters[2].selectbox("Crane", ("All",) + tuple(cranes))
    search_text = filters[3].text_input("Search")
    max_minutes = bundle.metrics.duration_minutes
    time_range = st.slider(
        "Simulation time range",
        min_value=0.0,
        max_value=float(max_minutes),
        value=(0.0, float(max_minutes)),
        step=1.0,
    )
    filtered = filter_event_rows(
        rows,
        event_types=tuple(selected_event_types),
        vessel_id=None if selected_vessel == "All" else selected_vessel,
        crane_id=None if selected_crane == "All" else selected_crane,
        time_range=time_range,
        search_text=search_text,
    )
    left, right = st.columns([2, 1])
    with left:
        selected_event = st.selectbox(
            "Jump to event",
            ("None",) + tuple(row["event_id"] for row in filtered),
            key=session_store.SELECTED_EVENT_ID,
        )
    with right:
        if st.button("Jump Replay To Event", use_container_width=True):
            if selected_event != "None":
                target = next(row for row in rows if row["event_id"] == selected_event)
                st.session_state[session_store.REPLAY_INDEX] = nearest_replay_frame_index(
                    bundle.result.replay_frames,
                    float(target["simulation_time_minutes"]),
                )
                st.rerun()

    st.dataframe(
        [
            {
                "Simulation Time": format_minutes(row["simulation_time_minutes"]),
                "Datetime": row["datetime"],
                "Event Type": row["event_type"],
                "Entity": f"{row['entity_type']}:{row['entity_id']}",
                "Related Vessel": row["related_vessel"],
                "Related Crane": row["related_crane"],
                "Related Task": row["related_task"],
                "Details": row["details"],
            }
            for row in filtered
        ],
        hide_index=True,
        use_container_width=True,
    )


def _render_scenario(bundle) -> None:
    st.subheader("Scenario Configuration")
    st.json(bundle.scenario.to_dict())
    st.subheader("Exports")
    timeline_data = {
        "berth_timeline": [
            segment.to_dict() for segment in bundle.result.berth_timeline
        ],
        "vessel_timeline": [
            segment.to_dict() for segment in bundle.result.vessel_timeline
        ],
        "crane_timeline": [
            segment.to_dict() for segment in bundle.result.crane_timeline
        ],
    }
    export_cols = st.columns(5)
    with export_cols[0]:
        download_json_button(
            "Metrics JSON",
            json_bytes(bundle.metrics),
            "metrics.json",
            key="mps_download_metrics",
        )
    with export_cols[1]:
        download_json_button(
            "Scenario JSON",
            json_bytes(bundle.scenario),
            "scenario.json",
            key="mps_download_scenario",
        )
    with export_cols[2]:
        download_json_button(
            "Replay JSON",
            json_bytes([frame.to_dict() for frame in bundle.result.replay_frames]),
            "replay.json",
            key="mps_download_replay",
        )
    with export_cols[3]:
        download_json_button(
            "Timeline JSON",
            json_bytes(timeline_data),
            "timeline.json",
            key="mps_download_timeline",
        )
    with export_cols[4]:
        st.download_button(
            "Event CSV",
            data=event_rows_csv_bytes(bundle.event_rows),
            file_name="events.csv",
            mime="text/csv",
            key="mps_download_events",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()

