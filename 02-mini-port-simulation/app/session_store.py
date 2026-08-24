from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


SCENARIO_MODE = "mps_scenario_mode"
SELECTED_SCENARIO_PATH = "mps_selected_scenario_path"
SEED = "mps_seed"
RUN_BUNDLE = "mps_run_bundle"
RUN_ERROR = "mps_run_error"
REPLAY_INDEX = "mps_replay_index"
REPLAY_PLAYING = "mps_replay_playing"
REPLAY_SPEED = "mps_replay_speed"
SELECTED_EVENT_ID = "mps_selected_event_id"
SELECTED_VESSEL_ID = "mps_selected_vessel_id"
SELECTED_CRANE_ID = "mps_selected_crane_id"
SELECTED_YARD_ID = "mps_selected_yard_id"
EVENT_TYPE_FILTER = "mps_event_type_filter"
EVENT_SEARCH = "mps_event_search"


def _state(state: MutableMapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    if state is not None:
        return state

    import streamlit as st

    return st.session_state


def initialize_session(state: MutableMapping[str, Any] | None = None) -> None:
    store = _state(state)
    store.setdefault(SCENARIO_MODE, "Preset")
    store.setdefault(SEED, 42)
    store.setdefault(RUN_BUNDLE, None)
    store.setdefault(RUN_ERROR, None)
    store.setdefault(REPLAY_INDEX, 0)
    store.setdefault(REPLAY_PLAYING, False)
    store.setdefault(REPLAY_SPEED, 1.0)
    store.setdefault(SELECTED_EVENT_ID, None)
    store.setdefault(SELECTED_VESSEL_ID, None)
    store.setdefault(SELECTED_CRANE_ID, None)
    store.setdefault(SELECTED_YARD_ID, None)
    store.setdefault(EVENT_TYPE_FILTER, [])
    store.setdefault(EVENT_SEARCH, "")


def store_run(bundle: Any, state: MutableMapping[str, Any] | None = None) -> None:
    initialize_session(state)
    store = _state(state)
    store[RUN_BUNDLE] = bundle
    store[RUN_ERROR] = None
    store[REPLAY_INDEX] = 0
    store[REPLAY_PLAYING] = False
    store[SELECTED_EVENT_ID] = (
        bundle.result.replay_frames[0].event_id
        if bundle.result.replay_frames
        else None
    )


def store_error(message: str, state: MutableMapping[str, Any] | None = None) -> None:
    initialize_session(state)
    store = _state(state)
    store[RUN_ERROR] = message
    store[REPLAY_PLAYING] = False

