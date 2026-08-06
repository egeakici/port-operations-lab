from __future__ import annotations

from pathlib import Path

import pytest


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
    ):
        collection = getattr(app, collection_name, [])
        for item in collection:
            for attribute in ("value", "label"):
                if hasattr(item, attribute):
                    values.append(str(getattr(item, attribute)))
    return "\n".join(values)


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

