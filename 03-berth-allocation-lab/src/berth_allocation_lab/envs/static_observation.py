"""Fixed-shape StaticBAP observation encoding over canonical raw-unit state.

Absolute minutes are encoded relative to the current vessel's arrival and
divided by a fixed ``time_scale_min``; durations are only divided. Positions
and vessel lengths are divided by the quay length. The encoding is an RL view
of the state: physics, rewards and validation always use raw float64 values.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from gymnasium import spaces

from berth_allocation_lab.core import BAPPlacement
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput


OBSERVATION_VERSION = "static_obs_v1"

VESSEL_FEATURES = ("arrival_rel_time", "length_over_quay", "service_duration")
PLACEMENT_FEATURES = ("position_over_quay", "start_rel_time", "end_rel_time")
CANDIDATE_FEATURES = ("position_over_quay", "start_rel_time", "waiting_time")
# Features of the marine terminal quay, not of the terminated episode state.
TERMINAL_FEATURES = ("berth_length_over_length_scale", "clearance_over_quay")

# "Unbounded" columns use the finite float32 range: values are never clipped,
# and a value that is not finite in float32 raises instead of being encoded.
_BIG = float(np.finfo(np.float32).max)

# (low, high) per feature column.
_VESSEL_BOUNDS = ((-_BIG, 0.0, 0.0), (_BIG, 1.0, _BIG))
_PLACEMENT_BOUNDS = ((0.0, -_BIG, -_BIG), (1.0, _BIG, _BIG))
_CANDIDATE_BOUNDS = ((0.0, -_BIG, 0.0), (1.0, _BIG, _BIG))
_TERMINAL_BOUNDS = ((0.0, 0.0), (_BIG, _BIG))

CandidateChoice = tuple[float, float, float]
"""(berth_position_m, earliest_start_min, waiting_time_min) in raw units."""


def build_observation_space(max_vessels: int, action_capacity: int) -> spaces.Dict:
    """Return the fixed Dict space for a given vessel and action capacity."""

    return spaces.Dict({
        "vessel_features": _matrix_box(max_vessels, _VESSEL_BOUNDS),
        "vessel_mask": spaces.MultiBinary(max_vessels),
        "placement_features": _matrix_box(max_vessels, _PLACEMENT_BOUNDS),
        "scheduled_mask": spaces.MultiBinary(max_vessels),
        # max_vessels is the terminal sentinel, never a real row index.
        "current_vessel_index": spaces.Discrete(max_vessels + 1),
        "current_vessel_features": _vector_box(_VESSEL_BOUNDS),
        "candidate_features": _matrix_box(action_capacity, _CANDIDATE_BOUNDS),
        "candidate_mask": spaces.MultiBinary(action_capacity),
        "terminal_features": _vector_box(_TERMINAL_BOUNDS),
    })


def reference_time_min(
    vessels: Sequence[BAPVesselInput],
    decision_index: int,
) -> float:
    """Current vessel arrival; after termination, the last vessel's arrival."""

    return vessels[min(decision_index, len(vessels) - 1)].arrival_time_min


def encode_observation(
    *,
    scenario: BAPScenarioInstance,
    vessels: Sequence[BAPVesselInput],
    placements: Sequence[BAPPlacement],
    candidates: Sequence[CandidateChoice],
    max_vessels: int,
    action_capacity: int,
    time_scale_min: float,
    length_scale_m: float,
) -> dict[str, np.ndarray | np.int64]:
    """Encode canonical state into fresh arrays; rows follow canonical order."""

    vessel_count = len(vessels)
    decision_index = len(placements)
    terminated = decision_index == vessel_count
    reference = reference_time_min(vessels, decision_index)
    quay = scenario.berth_length_m

    def rel(minute: float) -> float:
        return (minute - reference) / time_scale_min

    vessel_features = np.zeros((max_vessels, len(VESSEL_FEATURES)), dtype=np.float32)
    for row, vessel in enumerate(vessels):
        vessel_features[row] = (
            rel(vessel.arrival_time_min),
            vessel.length_m / quay,
            vessel.service_time_min / time_scale_min,
        )

    placement_features = np.zeros((max_vessels, len(PLACEMENT_FEATURES)), dtype=np.float32)
    for row, placement in enumerate(placements):
        if placement.vessel_id != vessels[row].vessel_id:
            raise ValueError("Placement rows must follow canonical vessel order.")
        placement_features[row] = (
            placement.berth_position_m / quay,
            rel(placement.berth_start_time_min),
            rel(placement.service_end_time_min),
        )

    candidate_features = np.zeros((action_capacity, len(CANDIDATE_FEATURES)), dtype=np.float32)
    for row, (position, start, waiting) in enumerate(candidates):
        candidate_features[row] = (position / quay, rel(start), waiting / time_scale_min)

    observation = {
        "vessel_features": vessel_features,
        "vessel_mask": _prefix_mask(max_vessels, vessel_count),
        "placement_features": placement_features,
        "scheduled_mask": _prefix_mask(max_vessels, decision_index),
        "current_vessel_index": np.int64(max_vessels if terminated else decision_index),
        "current_vessel_features": (
            np.zeros(len(VESSEL_FEATURES), dtype=np.float32) if terminated
            else vessel_features[decision_index].copy()
        ),
        "candidate_features": candidate_features,
        "candidate_mask": _prefix_mask(action_capacity, len(candidates)),
        "terminal_features": np.array(
            (quay / length_scale_m, scenario.min_clearance_m / quay), dtype=np.float32,
        ),
    }
    for key, value in observation.items():
        if isinstance(value, np.ndarray) and not np.all(np.isfinite(value)):
            raise ValueError(f"Observation {key} is not finite in float32; refusing to clip.")
    return observation


def _prefix_mask(size: int, count: int) -> np.ndarray:
    mask = np.zeros(size, dtype=np.int8)
    mask[:count] = 1
    return mask


def _matrix_box(rows: int, bounds: tuple[tuple[float, ...], tuple[float, ...]]) -> spaces.Box:
    low, high = (np.tile(np.asarray(b, dtype=np.float32), (rows, 1)) for b in bounds)
    return spaces.Box(low=low, high=high, dtype=np.float32)


def _vector_box(bounds: tuple[tuple[float, ...], tuple[float, ...]]) -> spaces.Box:
    low, high = (np.asarray(b, dtype=np.float32) for b in bounds)
    return spaces.Box(low=low, high=high, dtype=np.float32)
