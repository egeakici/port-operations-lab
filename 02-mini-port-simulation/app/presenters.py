from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from typing import Any


def format_minutes(value: float | None) -> str:
    if value is None:
        return "-"
    if value < 60:
        return f"{value:.0f} min"
    hours = value / 60.0
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24.0:.1f} d"


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100.0:.1f}%"


def format_number(value: float | int | None, *, digits: int = 1) -> str:
    if value is None:
        return "-"
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.{digits}f}"


def simulation_clock(start_time: datetime, elapsed_minutes: float) -> str:
    current = start_time + timedelta(minutes=elapsed_minutes)
    return f"t={format_minutes(elapsed_minutes)} | {current:%Y-%m-%d %H:%M}"


def json_bytes(data: Any) -> bytes:
    return json.dumps(
        _json_safe(data),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value

