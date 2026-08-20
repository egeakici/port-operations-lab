from __future__ import annotations

from datetime import datetime

from app.visual.presenter import build_terminal_visual_scene
from app.visual.svg_renderer import render_terminal_svg
from terminal_core.integration import IntegrationCheckpoint, run_reference_scenario
from terminal_core.terminal import Terminal
from terminal_core.vessel import Vessel


def test_empty_terminal_svg_renders_empty_state() -> None:
    scene = build_terminal_visual_scene(
        Terminal(current_time=datetime(2026, 1, 1, 8, 0)).snapshot()
    )

    svg = render_terminal_svg(scene)

    assert "Terminal map is empty." in svg
    assert "Schematic terminal view" in svg


def test_svg_escapes_user_controlled_ids() -> None:
    terminal = Terminal(current_time=datetime(2026, 1, 1, 8, 0))
    unsafe_id = "<script>alert(1)</script>"
    terminal.register_vessel(Vessel(unsafe_id, 210.0, terminal.current_time, 10, 2, 1))

    svg = render_terminal_svg(build_terminal_visual_scene(terminal.snapshot()))

    assert unsafe_id not in svg
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg


def test_failed_crane_svg_contains_status_text() -> None:
    result = run_reference_scenario()
    scene = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.CRANE_FAILED)
    )

    svg = render_terminal_svg(scene)

    assert "QC01" in svg
    assert "FAILED" in svg


def test_reference_scenario_maps_render_for_every_checkpoint() -> None:
    result = run_reference_scenario()

    for checkpoint in IntegrationCheckpoint:
        scene = build_terminal_visual_scene(result.get_checkpoint(checkpoint))
        svg = render_terminal_svg(scene)
        assert "<svg" in svg
        assert "</svg>" in svg


def test_svg_rendering_is_deterministic() -> None:
    state = run_reference_scenario().get_checkpoint(
        IntegrationCheckpoint.DISCHARGE_IN_PROGRESS
    )
    scene = build_terminal_visual_scene(state)

    assert render_terminal_svg(scene) == render_terminal_svg(scene)

