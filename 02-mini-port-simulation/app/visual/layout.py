from __future__ import annotations

import math

from app.visual.models import VisualRect


SCENE_WIDTH = 1400.0
SCENE_HEIGHT = 860.0
MARGIN_X = 48.0
WATER_TOP = 36.0
QUAY_Y = 360.0
APRON_Y = 400.0
YARD_Y = 500.0
YARD_HEIGHT = 250.0
QUAY_X = MARGIN_X
QUAY_WIDTH = SCENE_WIDTH - (2 * MARGIN_X)
ANCHORAGE_X = QUAY_X + 24.0
ANCHORAGE_Y = WATER_TOP + 50.0
ANCHORAGE_WIDTH = QUAY_WIDTH - 48.0
ANCHORAGE_HEIGHT = 160.0
ANCHORAGE_MAX_VISIBLE = 30


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
    visible_count = min(count, ANCHORAGE_MAX_VISIBLE)
    columns = min(10, visible_count)
    gap = 8.0
    width = (ANCHORAGE_WIDTH - (columns - 1) * gap) / columns
    height = 32.0
    return tuple(
        VisualRect(
            x=ANCHORAGE_X + (index % columns) * (width + gap),
            y=ANCHORAGE_Y + (index // columns) * (height + gap),
            width=width,
            height=height,
        )
        for index in range(visible_count)
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
