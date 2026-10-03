"""Immutable, policy-facing online state for causal reference policies."""

from __future__ import annotations

from dataclasses import dataclass

from berth_allocation_lab.core import BAPPlacement
from berth_allocation_lab.data import BAPVesselInput


@dataclass(frozen=True)
class DynamicVisibleState:
    current_time_min: float
    berth_length_m: float
    min_clearance_m: float
    future_horizon_min: float
    vessels_by_slot: tuple[BAPVesselInput, ...]
    statuses_by_slot: tuple[str, ...]
    active_placements: tuple[BAPPlacement, ...]
    legal_choices: tuple[tuple[int, str, int, float, float], ...]
    wait_legal: bool
