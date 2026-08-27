from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.simulation_service import (
    build_custom_scenario,
    filter_event_rows,
    nearest_replay_frame_index,
    run_simulation_from_ui,
)
from app.visual.svg_renderer import render_terminal_replay_svg
from app.visual import layout
from app.visual.terminal_replay import (
    build_terminal_replay_scene,
    current_waiting_queue,
)
from mini_port_sim import (
    DisruptionConfig,
    ScenarioConfig,
    ServiceConfig,
    TerminalConfig,
    TerminationMode,
    TrafficConfig,
)


START_TIME = datetime(2026, 8, 20, 8, 0)


@dataclass(frozen=True)
class FakeFrame:
    elapsed_minutes: float


def test_custom_scenario_form_values_build_real_config() -> None:
    scenario = build_custom_scenario(
        scenario_id="ui_custom",
        duration_hours=72,
        seed=42,
        termination_mode="horizon",
        max_drain_extension_hours=24,
        terminal={
            "berth_length_m": 1200,
            "min_clearance_m": 20,
            "quay_crane_count": 5,
            "quay_crane_moves_per_hour": 31,
            "yard_block_count": 4,
            "yard_block_capacity_teu": 2200,
        },
        traffic={
            "vessel_count": 35,
            "mean_interarrival_minutes": 150,
            "min_vessel_length_m": 180,
            "max_vessel_length_m": 360,
            "min_workload_moves": 250,
            "max_workload_moves": 1000,
        },
        service={
            "berthing_preparation_minutes": 30,
            "service_minutes_per_move": 0.5,
            "departure_preparation_minutes": 20,
            "two_crane_efficiency": 0.92,
            "three_crane_efficiency": 0.82,
            "four_plus_crane_efficiency": 0.72,
        },
        disruptions={
            "eta_delay_stddev_minutes": 20,
            "productivity_min_factor": 0.85,
            "productivity_max_factor": 1.08,
            "crane_failures_enabled": True,
            "mean_time_to_failure_minutes": 900,
            "mean_repair_minutes": 90,
        },
    )

    assert scenario.scenario_id == "ui_custom"
    assert scenario.terminal.min_clearance_m == 20
    assert scenario.terminal.quay_crane_count == 5
    assert scenario.disruptions.crane_failures_enabled is True
    assert scenario.traffic.vessel_count == 35


def test_nearest_replay_frame_index_uses_closest_event_time() -> None:
    frames = (
        FakeFrame(0.0),
        FakeFrame(10.0),
        FakeFrame(25.0),
        FakeFrame(60.0),
    )

    assert nearest_replay_frame_index(frames, 23.0) == 2
    assert nearest_replay_frame_index(frames, 55.0) == 3
    assert nearest_replay_frame_index((), 55.0) == 0


def test_event_filtering_supports_type_vessel_crane_time_and_search() -> None:
    rows = (
        {
            "event_id": "E1",
            "simulation_time_minutes": 10.0,
            "event_type": "vessel_waiting",
            "entity_type": "vessel",
            "entity_id": "V001",
            "related_vessel": "V001",
            "related_crane": None,
            "related_task": None,
            "details": {"note": "queue"},
        },
        {
            "event_id": "E2",
            "simulation_time_minutes": 20.0,
            "event_type": "crane_failed",
            "entity_type": "quay_crane",
            "entity_id": "QC01",
            "related_vessel": None,
            "related_crane": "QC01",
            "related_task": None,
            "details": {"reason": "failure"},
        },
    )

    assert len(filter_event_rows(rows, event_types=("crane_failed",))) == 1
    assert len(filter_event_rows(rows, vessel_id="V001")) == 1
    assert len(filter_event_rows(rows, crane_id="QC01")) == 1
    assert len(filter_event_rows(rows, time_range=(0.0, 15.0))) == 1
    assert len(filter_event_rows(rows, search_text="failure")) == 1


def test_replay_scene_and_svg_use_simulation_backend_outputs() -> None:
    scenario = ScenarioConfig(
        scenario_id="frontend-smoke",
        duration_hours=3,
        seed=42,
        termination_mode=TerminationMode.HORIZON,
        terminal=TerminalConfig(
            berth_length_m=600,
            min_clearance_m=20,
            quay_crane_count=2,
            quay_crane_moves_per_hour=60,
            yard_block_count=2,
            yard_block_capacity_teu=500,
        ),
        traffic=TrafficConfig(
            vessel_count=2,
            mean_interarrival_minutes=30,
            min_vessel_length_m=200,
            max_vessel_length_m=220,
            min_workload_moves=60,
            max_workload_moves=80,
        ),
        service=ServiceConfig(
            berthing_preparation_minutes=0,
            departure_preparation_minutes=0,
        ),
        disruptions=DisruptionConfig(
            eta_delay_stddev_minutes=0,
            productivity_min_factor=1,
            productivity_max_factor=1,
        ),
    )
    bundle = run_simulation_from_ui(scenario, start_time=START_TIME)
    scene = build_terminal_replay_scene(bundle, 0)
    svg = render_terminal_replay_svg(scene)

    assert scene.berths[0].length_m == 600
    assert scene.cranes
    assert scene.yards
    assert "MiniPortSim terminal replay" in svg
    assert "QUAY / BERTH / APRON" in svg
    assert current_waiting_queue(bundle, 0)


def test_waiting_anchorage_layout_caps_visible_vessels_before_berth() -> None:
    rects = layout.anchorage_rects(60)

    assert len(rects) == layout.ANCHORAGE_MAX_VISIBLE
    assert max(rect.y + rect.height for rect in rects) < layout.QUAY_Y - 90.0
