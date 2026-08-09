from __future__ import annotations

from datetime import datetime

import pytest

from app.visual import layout
from app.visual.presenter import build_terminal_visual_scene
from src.terminal_core.berth import Berth
from src.terminal_core.quay_crane import QuayCrane
from src.terminal_core.terminal import Terminal
from src.terminal_core.vessel import Vessel


def _terminal_with_scaled_berth() -> Terminal:
    terminal = Terminal(current_time=datetime(2026, 1, 1, 8, 0))
    terminal.register_berth(Berth("B01", 700.0))
    terminal.register_vessel(
        Vessel("V001", 210.0, terminal.current_time, 10, 2, 1)
    )
    terminal.arrive_vessel("V001")
    terminal.berth_vessel("V001", "B01", 70.0)
    return terminal


def test_yard_grid_layout_is_deterministic() -> None:
    first = layout.yard_grid_rects(7)
    second = layout.yard_grid_rects(7)

    assert first == second
    assert len(first) == 7
    assert first[0].x < first[1].x < first[2].x
    assert first[3].y > first[0].y


def test_berth_scale_uses_real_start_and_length_meters() -> None:
    scene = build_terminal_visual_scene(_terminal_with_scaled_berth().snapshot())

    vessel = scene.vessels[0]
    assert vessel.normalized_x == pytest.approx(0.10)
    assert vessel.normalized_width == pytest.approx(0.30)


def test_crane_scale_uses_quay_position_meters() -> None:
    terminal = Terminal(current_time=datetime(2026, 1, 1, 8, 0))
    terminal.register_berth(Berth("B01", 700.0))
    terminal.register_quay_crane(QuayCrane("QC01", 350.0, 25.0))

    scene = build_terminal_visual_scene(terminal.snapshot())

    assert scene.cranes[0].normalized_x == pytest.approx(0.50)
