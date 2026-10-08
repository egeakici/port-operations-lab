"""Exercise the real Streamlit entry point without periodic test reruns."""

from pathlib import Path

import pytest

streamlit = pytest.importorskip("streamlit")
pytest.importorskip("plotly")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]


def _widget(items, label):
    return next(item for item in items if item.label == label)


def test_replay_app_loads_and_switches_recorded_policy_and_time(monkeypatch):
    monkeypatch.setattr(streamlit, "fragment", lambda **_: lambda function: function)
    app = AppTest.from_file(str(ROOT / "frontend/bap_replay_app.py"), default_timeout=90).run()
    assert not app.exception
    assert app.title[0].value == "Berth Allocation Replay"
    assert _widget(app.selectbox, "Scenario family").value == "tiny_n6"
    assert _widget(app.selectbox, "Recorded scenario").value.startswith("dynamic_tiny_n6_test_")
    original_id = app.session_state["bap_scenario"]
    _widget(app.slider, "Simulation time (min)").set_value(100.0)
    app.run()
    assert not app.exception
    assert app.session_state["bap_time"] == pytest.approx(100.0)
    _widget(app.selectbox, "Policy").set_value("Dynamic PPO seed 23")
    app.run()
    assert not app.exception
    assert app.session_state["bap_scenario"] == original_id
    assert app.session_state["bap_time"] == pytest.approx(100.0)
    assert app.session_state["bap_ppo_seed"] == 23
    _widget(app.selectbox, "Scenario family").set_value("medium")
    app.run()
    assert not app.exception
    assert app.session_state["bap_scenario"].startswith("dynamic_medium_test_")
    assert app.session_state["bap_time"] == 0.0
