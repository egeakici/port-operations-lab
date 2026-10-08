"""Read-only BAP replay in the Project 02 Mini Port Simulation visual language."""

from __future__ import annotations

import sys
import math
import time
from html import escape
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
for path in (PROJECT_ROOT / "src", REPO_ROOT / "02-mini-port-simulation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import streamlit as st
import streamlit.components.v1 as components

from app.styles import apply_styles
from app.ui_helpers import metric_card
from berth_allocation_lab.replay import ReplayError, load_catalog, load_scenario
from berth_allocation_lab.replay.records import _evaluation_path
from berth_allocation_lab.replay.timeline import (
    compare_compatible, decision_context, events_for, index_at_time, snapshot,
    space_time_rectangles, step_index, switch_time,
)
from berth_allocation_lab.replay.visuals import render_quay_svg, space_time_figure

POLICIES = {
    "Online FCFS": ("fcfs", None),
    "Dynamic PPO seed 11": ("ppo", 11),
    "Dynamic PPO seed 23": ("ppo", 23),
    "Dynamic PPO seed 37": ("ppo", 37),
    "Online Rollout": ("rollout", None),
}
FAMILY_LABELS = {
    "tiny_n6": "Tiny n6", "tiny_n7": "Tiny n7", "tiny_n8": "Tiny n8",
    "medium": "Medium n16", "heavy": "Heavy n24",
}


@st.cache_data(show_spinner=False)
def _catalog(root: str, manifest_mtime_ns: int):
    return load_catalog(Path(root))


@st.cache_data(show_spinner=False)
def _scenario(root: str, scenario_id: str, seed: int, source_hash: str,
              source_mtime_ns: int, source_size: int, manifest_hash: str):
    catalog = load_catalog(Path(root))
    return load_scenario(catalog, scenario_id, seed)


def _initialize() -> None:
    state = st.session_state
    state.setdefault("bap_policy", "Dynamic PPO seed 11")
    state.setdefault("bap_ppo_seed", 11)
    state.setdefault("bap_event_index", 0)
    state.setdefault("bap_time", 0.0)
    state.setdefault("bap_time_slider", 0.0)
    state.setdefault("bap_playing", False)
    state.setdefault("bap_speed", 1.0)
    state.setdefault("bap_compare", False)
    state.setdefault("bap_last_tick", time.monotonic())
    state.setdefault("bap_last_scenario", None)
    state.setdefault("bap_last_policy", None)


def _reset_for_scenario(scenario_id: str) -> None:
    state = st.session_state
    if state["bap_last_scenario"] == scenario_id:
        return
    state["bap_last_scenario"] = scenario_id
    state["bap_event_index"] = 0
    state["bap_time"] = 0.0
    state["bap_time_slider"] = 0.0
    state["bap_playing"] = False
    state["bap_selected_vessel"] = "None"


def _preserve_time_on_policy_change(policy: str, events) -> None:
    state = st.session_state
    if state["bap_last_policy"] == policy:
        return
    state["bap_last_policy"] = policy
    state["bap_playing"] = False
    state["bap_event_index"] = switch_time(events, state["bap_time"])
    state["bap_last_tick"] = time.monotonic()


def _on_scrub(events) -> None:
    state = st.session_state
    state["bap_time"] = float(state["bap_time_slider"])
    state["bap_event_index"] = index_at_time(events, state["bap_time"])
    state["bap_playing"] = False


def _sidebar(catalog):
    st.sidebar.header("Replay Control")
    families = list(dict.fromkeys(option.family for option in catalog.scenarios))
    st.session_state.setdefault("bap_family", families[0])
    family = st.sidebar.selectbox("Scenario family", families, key="bap_family",
                                  format_func=lambda name: FAMILY_LABELS.get(name, name))
    options = [o for o in catalog.scenarios if o.family == family]
    ids = [o.scenario_id for o in options]
    if st.session_state.get("bap_scenario") not in ids:
        st.session_state["bap_scenario"] = ids[0]
    scenario_id = st.sidebar.selectbox("Recorded scenario", ids, key="bap_scenario",
                                       format_func=lambda sid: sid.replace("dynamic_", ""))
    policy = st.sidebar.selectbox("Policy", list(POLICIES), key="bap_policy")
    method, seed = POLICIES[policy]
    if seed is not None:
        st.session_state["bap_ppo_seed"] = seed
    seed = st.session_state["bap_ppo_seed"]
    st.sidebar.toggle("Compare policies", key="bap_compare")
    st.sidebar.select_slider("Playback speed", options=(0.5, 1.0, 2.0, 4.0),
                             format_func=lambda x: f"{x:g}x", key="bap_speed")
    st.sidebar.caption(f"HELD-OUT TEST  |  H=240 min  |  scenario seed "
                       f"{next(o for o in options if o.scenario_id == scenario_id).scenario_id.split('seed')[-1]}")
    return scenario_id, policy, method, seed


def _initial_link(catalog) -> float | None:
    state = st.session_state
    if state.get("bap_link_applied"):
        return None
    requested = st.query_params.get("scenario")
    option = next((o for o in catalog.scenarios if o.scenario_id == requested), None)
    if option is not None:
        state["bap_family"] = option.family
        state["bap_scenario"] = option.scenario_id
    labels = {"fcfs": "Online FCFS", "rollout": "Online Rollout",
              **{f"ppo{seed}": f"Dynamic PPO seed {seed}" for seed in (11, 23, 37)}}
    policy = labels.get(st.query_params.get("policy"))
    if policy is not None:
        state["bap_policy"] = policy
    state["bap_compare"] = st.query_params.get("compare") == "1"
    try:
        requested_time = float(st.query_params.get("time", "0"))
    except ValueError:
        requested_time = 0.0
    state["bap_link_applied"] = True
    return requested_time if math.isfinite(requested_time) and requested_time >= 0 else None


def _metric_row(run, state) -> None:
    metrics = st.columns(6)
    values = (
        ("Final total waiting", f"{run.total_waiting_time_min:,.1f}", "vessel-min"),
        ("Final mean waiting", f"{run.mean_waiting_time_min:,.1f}", "min / vessel"),
        ("Final P95 waiting", f"{run.p95_waiting_time_min:,.1f}" if run.p95_waiting_time_min is not None else "-", "min / vessel"),
        ("Mean turnaround", f"{run.mean_turnaround_time_min:,.1f}" if run.mean_turnaround_time_min is not None else "-", "min / vessel"),
        ("Current queue", str(len(state.waiting)), "vessels"),
        ("Intentional WAITs", str(run.intentional_waits) if run.intentional_waits is not None else "-", "recorded"),
    )
    for column, (label, value, caption) in zip(metrics, values):
        with column:
            metric_card(label, value, caption)


def _clock_controls(events, max_time: float) -> None:
    state = st.session_state
    now = time.monotonic()
    if state["bap_playing"] and now - state["bap_last_tick"] >= 0.5 / state["bap_speed"]:
        if state["bap_event_index"] >= len(events) - 1:
            state["bap_playing"] = False
            st.rerun()
        else:
            state["bap_event_index"] += 1
            state["bap_time"] = events[state["bap_event_index"]].time_min
        state["bap_last_tick"] = now
    with st.container(key="bap-toolbar"):
        controls = st.columns(5)
        if controls[0].button("|<", help="Restart", width="stretch"):
            state["bap_event_index"], state["bap_time"], state["bap_playing"] = 0, events[0].time_min, False
        if controls[1].button("<", help="Previous recorded event", width="stretch"):
            state["bap_event_index"] = step_index(events, state["bap_event_index"], -1)
            state["bap_time"], state["bap_playing"] = events[state["bap_event_index"]].time_min, False
        if controls[2].button("Pause" if state["bap_playing"] else "Play",
                              help="Pause playback" if state["bap_playing"] else "Play recorded events",
                              width="stretch"):
            state["bap_playing"] = not state["bap_playing"]
            state["bap_last_tick"] = time.monotonic()
            st.rerun()
        if controls[3].button(">", help="Next recorded event", width="stretch"):
            state["bap_event_index"] = step_index(events, state["bap_event_index"], 1)
            state["bap_time"], state["bap_playing"] = events[state["bap_event_index"]].time_min, False
        if controls[4].button(">|", help="Last event", width="stretch"):
            state["bap_event_index"] = len(events) - 1
            state["bap_time"], state["bap_playing"] = events[-1].time_min, False
    state["bap_time"] = min(max(float(state["bap_time"]), 0.0), max_time)
    state["bap_time_slider"] = state["bap_time"]
    st.slider("Simulation time (min)", min_value=0.0,
              max_value=float(max_time), step=0.1,
              key="bap_time_slider", on_change=_on_scrub, args=(events,))


def _render_map(scenario, run, t, *, index=None, selected=None):
    events = events_for(run, scenario.horizon_min)
    state = snapshot(run, scenario.horizon_min, t, events, index)
    components.html(render_quay_svg(scenario, run, state, selected), height=235, scrolling=False)
    st.caption(f"Continuous quay: 0-{scenario.berth_length_m:g} m | "
               f"minimum clearance: {scenario.min_clearance_m:g} m")
    return state


def _render_replay_tab(scenario, run, events, t, event_index):
    selected = st.session_state.get("bap_selected_vessel", "None")
    state = _render_map(scenario, run, t, index=event_index,
                        selected=None if selected == "None" else selected)
    _metric_row(run, state)
    current = events[event_index] if event_index >= 0 else None
    if current:
        label = (f"Latest recorded event {event_index + 1}/{len(events)} "
                 f"at t={current.time_min:,.1f} min | {current.kind}")
        latest_action = next((e for e in reversed(events[:event_index + 1])
                              if e.kind in {"WAIT", "ASSIGNMENT"}), None)
        if latest_action and latest_action.kind == "WAIT":
            st.warning(label + f" | Latest policy action: intentional WAIT at "
                       f"t={latest_action.time_min:,.1f} min")
        else:
            st.caption(label + ("  |  display-only boundary" if current.origin != "recorded" else ""))
    cols = st.columns([1, 1, 1])
    with cols[0]:
        st.subheader("Waiting queue")
        st.write(", ".join(state.waiting) or "None")
    with cols[1]:
        st.subheader("Announced")
        st.write(", ".join(state.announced) or "None")
    with cols[2]:
        st.subheader("In service / completed")
        st.write(f"{', '.join(state.active) or 'None'} / {len(state.completed)} completed")
    if state.reserved:
        st.caption("Assigned for future service: " + ", ".join(state.reserved))
    vessels = sorted((v.vessel_id for v in run.vessels))
    selected = st.selectbox("Inspect vessel", ["None", *vessels], key="bap_selected_vessel")
    if selected != "None":
        vessel = next(v for v in run.vessels if v.vessel_id == selected)
        st.table([{"Field": key, "Value": value} for key, value in (
            ("Vessel", selected), ("Length", f"{vessel.length_m:.1f} m"),
            ("Arrival", f"{vessel.arrival_time_min:.1f} min"),
            ("Berth position", f"{vessel.berth_position_m:.1f} m"),
            ("Service", f"{vessel.berth_start_time_min:.1f}-{vessel.service_end_time_min:.1f} min"),
            ("Waiting", f"{vessel.waiting_time_min:.1f} min"),
        )])


def _render_comparison(scenario, t, selected_policy):
    compare_compatible(*scenario.runs.values())
    st.subheader("Same physical scenario")
    rows = []
    fcfs = scenario.runs["fcfs"].total_waiting_time_min
    for method in ("fcfs", "ppo", "rollout"):
        run = scenario.runs[method]
        name = "Online FCFS" if method == "fcfs" else (
            f"Dynamic PPO seed {run.training_seed}" if method == "ppo" else "Online Rollout")
        rows.append({"Policy": name, "Final total waiting (vessel-min)": round(run.total_waiting_time_min, 2),
                     "Delta vs FCFS (vessel-min)": round(run.total_waiting_time_min - fcfs, 2),
                     "Mean wait (min/vessel)": round(run.mean_waiting_time_min, 2),
                     "P95 wait (min/vessel)": None if run.p95_waiting_time_min is None else round(run.p95_waiting_time_min, 2),
                     "Intentional WAITs": run.intentional_waits, "Valid schedule": run.schedule_valid})
    st.dataframe(rows, hide_index=True, width="stretch")
    for method, row in zip(("fcfs", "ppo", "rollout"), rows):
        st.markdown(f"**{row['Policy']}**" + (" (selected)" if method == selected_policy else ""))
        _render_map(scenario, scenario.runs[method], t)


def _render_decisions(scenario, run, events, index):
    st.subheader("Recorded decisions")
    if run.decisions is None or run.events is None:
        st.info("Recorded decision history is unavailable; only the verified schedule can be replayed.")
        return
    decisions = [e for e in events[:index + 1] if e.decision_index is not None and
                 e.kind in {"WAIT", "ASSIGNMENT"}]
    if not decisions:
        st.info("No recorded policy decision has occurred at this event yet.")
        return
    current = decisions[-1]
    decision, context = decision_context(run, scenario.horizon_min, current.decision_index)
    rows = (
        ("Recorded time", f"{decision['simulation_time_min']:.2f} min"),
        ("Policy", run.policy_id + (f" / seed {run.training_seed}" if run.training_seed else "")),
        ("Action", "Intentional WAIT" if decision["action_type"] == "WAIT" else "Assign"),
        ("Selected vessel", decision.get("selected_vessel_id") or "Not applicable"),
        ("Berth position", f"{decision['selected_berth_position_m']:.2f} m"
         if decision.get("selected_berth_position_m") is not None else "Not applicable"),
        ("Waiting before action", ", ".join(context.waiting) or "None"),
        ("Announced before action", ", ".join(context.announced) or "None"),
        ("Active before action", ", ".join(context.active) or "None"),
    )
    st.table([{"Field": key, "Recorded / visible value": value} for key, value in rows])
    if current.kind == "WAIT":
        position = next((i for i, e in enumerate(events)
                         if e.kind == "WAIT" and e.decision_index == current.decision_index), None)
        next_event = events[position + 1] if position is not None and position + 1 < len(events) else None
        if next_event:
            st.caption(f"Next recorded event: {next_event.kind} at t={next_event.time_min:.2f} min")
    st.caption("Visible vessel lists are reconstructed from the recorded event prefix. "
               "Unrecorded legal alternatives and neural-network rationale are unavailable.")
    vicinity = events[max(0, index - 5):min(len(events), index + 6)]
    st.dataframe([{"Time (min)": round(e.time_min, 2), "Event": e.kind,
                   "Vessel": e.vessel_id or "-", "Origin": e.origin} for e in vicinity],
                 hide_index=True, width="stretch")


def _replay_workspace(scenario, method: str) -> None:
    run = scenario.runs[method]
    events = events_for(run, scenario.horizon_min)
    if not events:
        st.warning("No recorded or derivable replay events are available.")
        return
    maximum = max(events_for(other, scenario.horizon_min)[-1].time_min
                  for other in scenario.runs.values()) if st.session_state["bap_compare"] else events[-1].time_min
    _clock_controls(events, maximum)
    index = min(st.session_state["bap_event_index"], len(events) - 1)
    t = float(st.session_state["bap_time"])
    tabs = st.tabs(["Berth Replay", "Space-Time", "Policy Comparison", "Decisions", "Source"])
    with tabs[0]:
        if st.session_state["bap_compare"]:
            _render_comparison(scenario, t, method)
        else:
            _render_replay_tab(scenario, run, events, t, index)
    with tabs[1]:
        st.plotly_chart(space_time_figure(scenario, run, t,
                        selected_vessel_id=st.session_state.get("bap_selected_vessel")),
                        width="stretch")
        st.caption("Retrospective complete schedule; it was not visible to the online policy in advance.")
    with tabs[2]:
        _render_comparison(scenario, t, method)
    with tabs[3]:
        _render_decisions(scenario, run, events, index)
    with tabs[4]:
        st.table([{"Field": "Scenario", "Value": scenario.option.scenario_id},
                  {"Field": "Physical fingerprint", "Value": scenario.option.fingerprint},
                  {"Field": "Split", "Value": run.source_split.upper()},
                  {"Field": "Experiment", "Value": run.source_experiment},
                  {"Field": "Evaluation artifact", "Value": run.evaluation_path},
                  {"Field": "SHA-256", "Value": run.evaluation_sha256},
                  {"Field": "Quay / clearance", "Value": f"{scenario.berth_length_m:g} / {scenario.min_clearance_m:g} m"},
                  {"Field": "Horizon", "Value": f"{scenario.horizon_min:g} min"}])


def main() -> None:
    st.set_page_config(page_title="Berth Allocation Replay", page_icon="BA",
                       layout="wide", initial_sidebar_state="auto")
    _initialize()
    apply_styles()
    st.markdown("""<style>
    @media (max-width: 700px) {
      .st-key-bap-toolbar [data-testid='stHorizontalBlock'] {
        display: flex !important; flex-wrap: nowrap !important; gap: 0.3rem !important;
      }
      .st-key-bap-toolbar [data-testid='stColumn'] {
        flex: 1 1 0 !important; min-width: 0 !important; width: 0 !important;
      }
      .st-key-bap-toolbar button {min-height: 2.5rem; padding: 0.25rem !important;}
    }
    </style>""", unsafe_allow_html=True)
    st.title("Berth Allocation Replay")
    st.markdown("<p class='mps-subtitle'>Port Operations Lab / Project 03</p>",
                unsafe_allow_html=True)
    manifest = PROJECT_ROOT / "experiments/benchmark/step12/dynamic_h240_locked_v1/manifest.json"
    try:
        catalog = _catalog(str(PROJECT_ROOT), manifest.stat().st_mtime_ns if manifest.is_file() else -1)
        link_time = _initial_link(catalog)
        scenario_id, policy, method, seed = _sidebar(catalog)
        _reset_for_scenario(scenario_id)
        if link_time is not None:
            st.session_state["bap_time"] = link_time
        source = catalog.sources[(next(o.regime for o in catalog.scenarios
                                        if o.scenario_id == scenario_id), seed)]
        path = _evaluation_path(PROJECT_ROOT, source["evaluation_path"])
        stat = path.stat()
        scenario = _scenario(str(PROJECT_ROOT), scenario_id, seed, source["evaluation_sha256"],
                             stat.st_mtime_ns, stat.st_size, catalog.benchmark_manifest_sha256)
        _preserve_time_on_policy_change(policy, events_for(scenario.runs[method], scenario.horizon_min))
    except (ReplayError, OSError, ValueError, KeyError, TypeError) as error:
        st.error(f"Frozen replay unavailable: {error}")
        st.caption("Restore the Git-ignored Step 11/12 evidence and final Project 03 archive. "
                   "No synthetic replacement or new model evaluation will be generated here.")
        return
    st.markdown("<div class='mps-strip'>"
                f"<span class='mps-chip'>{escape(FAMILY_LABELS.get(scenario.option.family, scenario.option.family))}</span>"
                f"<span class='mps-chip'>{scenario.option.vessel_count} vessels</span>"
                "<span class='mps-chip'>HELD-OUT TEST</span>"
                f"<span class='mps-chip'>H={scenario.horizon_min:g} min</span>"
                f"<span class='mps-chip'>{escape(policy)}</span>"
                "</div>", unsafe_allow_html=True)
    st.warning("Synthetic, uncalibrated BAP replay. Results are not real-terminal performance estimates.")
    st.fragment(run_every="500ms" if st.session_state["bap_playing"] else None)(
        _replay_workspace)(scenario, method)
    with st.expander("Scientific limits"):
        st.markdown("Service durations are exogenous; Crane/Yard optimization is absent. "
                    "Online Rollout is heuristic, not a dynamic optimum. Candidate-space Exact "
                    "applies only to supported Static cases. PPO three-seed mean is not a replayable "
                    "policy. H=240 information value and WAIT causality are unproven. CPU/CUDA "
                    "inference parity is untested; latency figures are bounded engineering measurements. "
                    "No commercial savings are established.")


if __name__ == "__main__":
    main()
