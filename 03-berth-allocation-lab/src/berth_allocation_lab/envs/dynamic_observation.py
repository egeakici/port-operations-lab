"""Horizon-bounded, fixed-capacity DynamicBAP observation encoding."""

from __future__ import annotations

import numpy as np
from gymnasium import spaces

OBSERVATION_VERSION = "dynamic_obs_v1"
VESSEL_FEATURES = ("arrival_relative_time", "length_over_quay", "service_over_time_scale")
STATUS_FEATURES = ("announced", "waiting", "in_service", "completed")
PLACEMENT_FEATURES = ("position_over_quay", "start_relative_time", "end_relative_time")
CANDIDATE_FEATURES = ("position_over_quay", "waiting_over_time_scale")
TERMINAL_FEATURES = ("quay_over_length_scale", "clearance_over_quay")
_BIG = float(np.finfo(np.float32).max)


def build_dynamic_observation_space(max_vessels: int, action_capacity: int) -> spaces.Dict:
    return spaces.Dict({
        "current_time": spaces.Box(0, _BIG, shape=(1,), dtype=np.float32),
        "horizon": spaces.Box(0, _BIG, shape=(1,), dtype=np.float32),
        "terminal_features": spaces.Box(0, _BIG, shape=(2,), dtype=np.float32),
        "vessel_features": spaces.Box(-_BIG, _BIG, shape=(max_vessels, 3), dtype=np.float32),
        "visible_mask": spaces.MultiBinary(max_vessels),
        "status_features": spaces.MultiBinary((max_vessels, 4)),
        "placement_features": spaces.Box(-_BIG, _BIG, shape=(max_vessels, 3), dtype=np.float32),
        "candidate_features": spaces.Box(0, _BIG, shape=(action_capacity, 2), dtype=np.float32),
        "action_mask": spaces.MultiBinary(int(action_capacity)),
    })


def encode_dynamic_observation(env) -> dict[str, np.ndarray]:
    scenario = env._scenario
    quay = scenario.berth_length_m
    t = env.current_time_min
    scale = env.time_scale_min
    m = env.max_vessels
    n = env.action_space.n
    vessels = np.zeros((m, 3), dtype=np.float32)
    visible = np.zeros(m, dtype=np.int8)
    status = np.zeros((m, 4), dtype=np.int8)
    placements = np.zeros((m, 3), dtype=np.float32)
    candidates = np.zeros((n, 2), dtype=np.float32)
    for slot, vessel_id in enumerate(env._slot_ids):
        vessel = env._vessel_by_id[vessel_id]
        visible[slot] = 1
        vessels[slot] = ((vessel.arrival_time_min - t) / scale,
                         vessel.length_m / quay, vessel.service_time_min / scale)
        status[slot, ("ANNOUNCED", "WAITING", "IN_SERVICE", "COMPLETED").index(
            env._status[vessel_id])] = 1
        placement = env._placement_by_id.get(vessel_id)
        if placement is not None and env._status[vessel_id] == "IN_SERVICE":
            placements[slot] = (placement.berth_position_m / quay,
                                (placement.berth_start_time_min - t) / scale,
                                (placement.service_end_time_min - t) / scale)
    for action, (_, _, position) in env._choices.items():
        slot = (action - 1) // env.candidate_capacity
        vessel = env._vessel_by_id[env._slot_ids[slot]]
        candidates[action] = (position / quay, (t - vessel.arrival_time_min) / scale)
    observation = {
        "current_time": np.array([t / scale], dtype=np.float32),
        "horizon": np.array([env.future_horizon_min / scale], dtype=np.float32),
        "terminal_features": np.array((quay / env.length_scale_m,
                                        scenario.min_clearance_m / quay), dtype=np.float32),
        "vessel_features": vessels,
        "visible_mask": visible,
        "status_features": status,
        "placement_features": placements,
        "candidate_features": candidates,
        "action_mask": env.action_masks().astype(np.int8),
    }
    if any(not np.all(np.isfinite(value)) for value in observation.values()):
        raise ValueError("Dynamic observation exceeds finite float32 range.")
    return observation
