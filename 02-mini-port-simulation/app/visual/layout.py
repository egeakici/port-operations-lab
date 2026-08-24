from __future__ import annotations

import math

from app.visual.models import VisualRect


SCENE_WIDTH = 1400.0
SCENE_HEIGHT = 820.0
MARGIN_X = 48.0
WATER_TOP = 36.0
QUAY_Y = 330.0
APRON_Y = 370.0
YARD_Y = 470.0
YARD_HEIGHT = 250.0
QUAY_X = MARGIN_X
QUAY_WIDTH = SCENE_WIDTH - (2 * MARGIN_X)


def clamp(value: float, minimum: float, maximum: float) -> float:
    if not math.isfinite(value):
        return minimum
    return max(minimum, min(maximum, value))


def ratio(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return clamp(value / total, 0.0, 1.0)


def anchorage_rects(count: int) -> tuple[VisualRect, ...]:
    if count <= 0:
        return ()
    columns = min(5, count)
    gap = 14.0
    width = 160.0
    height = 54.0
    start_x = QUAY_X + 24.0
    start_y = WATER_TOP + 58.0
    return tuple(
        VisualRect(
            x=start_x + (index % columns) * (width + gap),
            y=start_y + (index // columns) * (height + gap),
            width=width,
            height=height,
        )
        for index in range(count)
    )


def yard_rects(count: int) -> tuple[VisualRect, ...]:
    if count <= 0:
        return ()
    columns = min(4, count)
    rows = math.ceil(count / columns)
    gap = 18.0
    width = (QUAY_WIDTH - (columns - 1) * gap) / columns
    height = min(104.0, (YARD_HEIGHT - (rows - 1) * gap) / rows)
    return tuple(
        VisualRect(
            x=QUAY_X + (index % columns) * (width + gap),
            y=YARD_Y + (index // columns) * (height + gap),
            width=width,
            height=height,
        )
        for index in range(count)
    )

