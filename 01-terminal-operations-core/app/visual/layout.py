from __future__ import annotations

import math

from app.visual.models import VisualPoint, VisualRect


SCENE_WIDTH = 1400.0
SCENE_HEIGHT = 820.0
MARGIN_X = 48.0

WATER_TOP = 36.0
WATER_HEIGHT = 268.0
QUAY_Y = 330.0
APRON_Y = 370.0
YARD_Y = 456.0
YARD_HEIGHT = 270.0
GATE_Y = 748.0
GATE_HEIGHT = 52.0

QUAY_X = MARGIN_X
QUAY_WIDTH = SCENE_WIDTH - (2 * MARGIN_X)


def clamp(value: float, minimum: float, maximum: float) -> float:
    if not math.isfinite(value):
        return minimum
    return max(minimum, min(maximum, value))


def ratio(value: float, total: float) -> float:
    if total <= 0 or not math.isfinite(total):
        return 0.0
    return clamp(value / total, 0.0, 1.0)


def point_on_rect(rect: VisualRect, *, side: str = "center") -> VisualPoint:
    if side == "top":
        return VisualPoint(rect.center.x, rect.y)
    if side == "bottom":
        return VisualPoint(rect.center.x, rect.y + rect.height)
    if side == "left":
        return VisualPoint(rect.x, rect.center.y)
    if side == "right":
        return VisualPoint(rect.x + rect.width, rect.center.y)
    return rect.center


def yard_grid_rects(count: int) -> tuple[VisualRect, ...]:
    if count <= 0:
        return ()

    columns = min(3, max(1, count))
    rows = math.ceil(count / columns)
    gap = 24.0
    cell_width = (QUAY_WIDTH - gap * (columns - 1)) / columns
    cell_height = min(116.0, (YARD_HEIGHT - gap * (rows - 1)) / rows)

    rects: list[VisualRect] = []
    for index in range(count):
        row = index // columns
        column = index % columns
        rects.append(
            VisualRect(
                x=QUAY_X + column * (cell_width + gap),
                y=YARD_Y + row * (cell_height + gap),
                width=cell_width,
                height=cell_height,
            )
        )
    return tuple(rects)


def anchorage_rects(count: int) -> tuple[VisualRect, ...]:
    if count <= 0:
        return ()
    columns = min(4, count)
    gap = 14.0
    width = 168.0
    height = 56.0
    start_x = QUAY_X + 24.0
    start_y = WATER_TOP + 56.0
    rects: list[VisualRect] = []
    for index in range(count):
        row = index // columns
        column = index % columns
        rects.append(
            VisualRect(
                x=start_x + column * (width + gap),
                y=start_y + row * (height + gap),
                width=width,
                height=height,
            )
        )
    return tuple(rects)


def gate_rects(count: int) -> tuple[VisualRect, ...]:
    if count <= 0:
        return ()
    columns = min(4, count)
    gap = 12.0
    width = 150.0
    height = GATE_HEIGHT
    total_width = columns * width + (columns - 1) * gap
    start_x = SCENE_WIDTH - MARGIN_X - total_width
    rects: list[VisualRect] = []
    for index in range(count):
        row = index // columns
        column = index % columns
        rects.append(
            VisualRect(
                x=start_x + column * (width + gap),
                y=GATE_Y + row * (height + gap),
                width=width,
                height=height,
            )
        )
    return tuple(rects)

