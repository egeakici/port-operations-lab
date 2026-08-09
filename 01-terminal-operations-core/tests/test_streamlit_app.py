from __future__ import annotations

from pathlib import Path

import pytest

from app import session_store
from app.models import canonical_json
from src.terminal_core.vessel import VesselStatus


streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest


def _app_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def _text_blob(app) -> str:
    values: list[str] = []
    for collection_name in (
        "title",
        "header",
        "subheader",
        "markdown",
        "text",
        "caption",
        "button",
        "tabs",
        "selectbox",
        "info",
        "success",
        "error",
    ):
        collection = getattr(app, collection_name, [])
        for item in collection:
            for attribute in ("value", "label"):
                if hasattr(item, attribute):
                    values.append(str(getattr(item, attribute)))
    return "\n".join(values)


def _widget_by_key(app, collection_name: str, key: str):
    matches = [
        item
        for item in getattr(app, collection_name, [])
        if getattr(item, "key", None) == key
    ]
    return matches[0] if matches else None


def _button_by_label(app, label: str):
    matches = [button for button in app.button if button.label == label]
    assert matches, f"Button not found: {label}"
    return matches[0]


def _metric_value(app, label: str) -> str:
    matches = [metric for metric in app.metric if metric.label == label]
    assert matches, f"Metric not found: {label}"
    return str(matches[0].value)


def _terminal(app):
    return app.session_state.filtered_state[session_store.SANDBOX_TERMINAL]


def _click(app, button_label: str):
    return _button_by_label(app, button_label).click().run(timeout=30)


def test_streamlit_app_smoke() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)

    assert not app.exception
    text = _text_blob(app)
    assert "Terminal Operations Control Center" in text
    assert "Interactive Sandbox" in text
    assert "Reference Scenario" in text
    assert "Create Empty Terminal" in text
    assert "Terminal Setup" in text
    assert "Live State" in text


def test_reference_scenario_visible() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)

    assert not app.exception
    text = _text_blob(app)
    assert "two-vessel-transshipment-v1" in text
    assert "Reference checkpoint" in text
    assert "QC01 FAILED" in text
    assert "T-DISCHARGE BLOCKED" in text


def test_empty_terminal_disables_impossible_operational_commands() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)

    assert not app.exception
    assert _metric_value(app, "Vessels") == "0"
    text = _text_blob(app)
    assert "Terminal Setup: 0 / 4" in text
    assert "[ ] Add at least one berth" in text
    assert "[ ] Add at least one vessel" in text
    assert "[ ] Add at least one quay crane" in text
    assert "[ ] Add at least one yard block" in text
    assert "No approaching vessels are available." in text

    assert _button_by_label(app, "Arrive Vessel").disabled
    assert _button_by_label(app, "Berth Vessel").disabled
    assert _button_by_label(app, "Depart Vessel").disabled
    assert _widget_by_key(app, "text_input", "arrive_vessel_id") is None
    assert _widget_by_key(app, "selectbox", "arrive_vessel_id") is None


def test_vessel_workflow_filters_vessel_command_selectors() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)

    app = _click(app, "Add Berth")
    app = _click(app, "Add Vessel")
    assert not app.exception
    assert _metric_value(app, "Vessels") == "1"
    assert _widget_by_key(app, "selectbox", "arrive_vessel_id").options == ["V001"]
    assert not _button_by_label(app, "Arrive Vessel").disabled

    app = _click(app, "Arrive Vessel")
    assert not app.exception
    terminal = _terminal(app)
    assert terminal.get_vessel("V001").status == VesselStatus.WAITING
    assert _widget_by_key(app, "selectbox", "arrive_vessel_id") is None
    assert _widget_by_key(app, "selectbox", "berth_vessel_id").options == ["V001"]
    assert _widget_by_key(app, "selectbox", "berth_vessel_berth_id").options == ["B01"]
    assert not _button_by_label(app, "Berth Vessel").disabled
    assert "ARRIVE_VESSEL succeeded" in _text_blob(app)
    assert "VESSEL_ARRIVED" in _text_blob(app)
    assert "VESSEL_WAITING" in _text_blob(app)


def test_infrastructure_prerequisites_disable_yard_crane_and_task_forms() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)

    assert _button_by_label(app, "Reserve Yard Capacity").disabled
    assert _button_by_label(app, "Cancel Yard Reservation").disabled
    assert _button_by_label(app, "Apply Yard Status Command").disabled
    assert _button_by_label(app, "Move Quay Crane").disabled
    assert _button_by_label(app, "Repair Quay Crane").disabled
    assert _button_by_label(app, "Add Operation Task").disabled
    text = _text_blob(app)
    assert "No yard blocks are registered yet." in text
    assert "No container groups are registered yet." in text
    assert "No quay cranes are registered yet." in text


def test_task_form_uses_core_routes_and_real_registries() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)

    assert _widget_by_key(app, "selectbox", "task_group_id") is None
    assert "Route: VESSEL -> YARD_BLOCK" in _text_blob(app)

    app = _click(app, "Add Vessel")
    app = _click(app, "Add Yard Block")
    app = _click(app, "Add Container Group")
    assert not app.exception

    assert _widget_by_key(app, "selectbox", "task_group_id").options == ["G001"]
    assert _widget_by_key(app, "selectbox", "task_source_id_vessel").options == ["V001"]
    assert _widget_by_key(app, "selectbox", "task_target_id_yard_block").options == ["Y01"]
    assert not _button_by_label(app, "Add Operation Task").disabled

    app.selectbox(key="task_type").select("load").run(timeout=30)
    assert "Route: YARD_BLOCK -> VESSEL" in _text_blob(app)
    assert _widget_by_key(app, "selectbox", "task_source_id_yard_block").options == ["Y01"]
    assert _widget_by_key(app, "selectbox", "task_target_id_vessel").options == ["V001"]


def test_container_group_form_is_flow_aware() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)
    app = _click(app, "Add Vessel")

    assert _widget_by_key(app, "selectbox", "group_source_vessel_id").options == ["V001"]
    assert _widget_by_key(app, "text_input", "group_target_vessel_id_disabled").disabled
    assert not _button_by_label(app, "Add Container Group").disabled

    app.selectbox(key="container_flow").select("export").run(timeout=30)
    assert _widget_by_key(app, "text_input", "group_source_vessel_id_disabled").disabled
    assert _widget_by_key(app, "selectbox", "group_target_vessel_id").options == ["V001"]

    app.selectbox(key="container_flow").select("transshipment").run(timeout=30)
    assert _widget_by_key(app, "selectbox", "group_source_vessel_id").options == ["V001"]
    assert _widget_by_key(app, "selectbox", "group_target_vessel_id").options == ["V001"]


def test_failed_domain_validation_is_reported_and_recorded() -> None:
    app = AppTest.from_file(_app_path()).run(timeout=30)

    app = _click(app, "Add Vessel")
    before_terminal_json = canonical_json(_terminal(app).to_dict())
    app = _click(app, "Add Vessel")

    assert not app.exception
    terminal = _terminal(app)
    assert canonical_json(terminal.to_dict()) == before_terminal_json
    history = app.session_state.filtered_state[session_store.COMMAND_HISTORY]
    assert history[-1].command_name == "REGISTER_VESSEL"
    assert not history[-1].success
    assert "REGISTER_VESSEL rejected" in _text_blob(app)
    assert "No terminal changes were committed." in _text_blob(app)
