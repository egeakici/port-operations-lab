from __future__ import annotations

import json
from datetime import datetime

import pytest

from app import session_store
from app.models import CommandRecord, canonical_json
from src.terminal_core.berth import Berth
from src.terminal_core.terminal import Terminal


def test_new_session_initialization() -> None:
    state = {}

    session_store.initialize_session(state)

    assert set(
        [
            session_store.SANDBOX_TERMINAL,
            session_store.SANDBOX_NAME,
            session_store.COMMAND_HISTORY,
            session_store.NAMED_CHECKPOINTS,
            session_store.REFERENCE_CHECKPOINT_INDEX,
            session_store.DEBUG_MODE,
        ]
    ).issubset(state)


def test_independent_terminal_state() -> None:
    first = {}
    second = {}
    session_store.initialize_session(first)
    session_store.initialize_session(second)
    first[session_store.SANDBOX_TERMINAL].register_berth(Berth("B01", 100.0))

    assert first[session_store.SANDBOX_TERMINAL].berth_ids == ("B01",)
    assert second[session_store.SANDBOX_TERMINAL].berth_ids == ()


def test_command_append() -> None:
    state = {}
    session_store.initialize_session(state)
    terminal = state[session_store.SANDBOX_TERMINAL]
    record = CommandRecord(
        sequence=1,
        command_name="NOOP",
        attempted_at=datetime(2026, 1, 1, 8, 0),
        parameters={"a": 1},
        success=True,
        new_event_ids=(),
        new_event_types=(),
        error_type=None,
        error_message=None,
        before_terminal_json=canonical_json(terminal.to_dict()),
        after_terminal_json=canonical_json(terminal.to_dict()),
    )

    session_store.append_command_record(record, state)

    assert session_store.command_history(state) == [record]
    assert state[session_store.LAST_COMMAND_FEEDBACK] == record


def test_named_checkpoint_save_duplicate_and_restore() -> None:
    state = {}
    session_store.initialize_session(state)
    state[session_store.SANDBOX_TERMINAL].register_berth(Berth("B01", 100.0))
    checkpoint = session_store.save_checkpoint("saved", state=state)
    state[session_store.SANDBOX_TERMINAL].register_berth(Berth("B02", 100.0))

    with pytest.raises(ValueError):
        session_store.save_checkpoint("saved", state=state)

    restored = session_store.restore_checkpoint(checkpoint.checkpoint_id, state)

    assert restored.berth_ids == ("B01",)
    assert checkpoint.state.berth_ids == ("B01",)


def test_reset_clears_sandbox() -> None:
    state = {}
    session_store.initialize_session(state)
    state[session_store.SANDBOX_TERMINAL].register_berth(Berth("B01", 100.0))
    session_store.save_checkpoint("saved", state=state)

    session_store.clear_sandbox(state=state)

    assert state[session_store.SANDBOX_TERMINAL].berth_ids == ()
    assert state[session_store.COMMAND_HISTORY] == []
    assert state[session_store.NAMED_CHECKPOINTS] == {}


def test_reference_result_does_not_replace_sandbox() -> None:
    state = {}
    session_store.initialize_session(state)
    original = state[session_store.SANDBOX_TERMINAL]

    result = session_store.get_reference_result(state)

    assert result.scenario_id == "two-vessel-transshipment-v1"
    assert state[session_store.SANDBOX_TERMINAL] is original


def test_terminal_json_and_package_round_trip() -> None:
    state = {}
    session_store.initialize_session(state)
    state[session_store.SANDBOX_TERMINAL].register_berth(Berth("B01", 100.0))
    session_store.save_checkpoint("saved", state=state)

    terminal = session_store.parse_terminal_json_bytes(
        session_store.terminal_json_bytes(state)
    )
    package = session_store.parse_sandbox_package_bytes(
        session_store.sandbox_package_bytes(state)
    )

    assert terminal.berth_ids == ("B01",)
    assert package[0].berth_ids == ("B01",)
    assert package[2]["checkpoint-001"].name == "saved"


def test_invalid_import_preserves_current_state() -> None:
    state = {}
    session_store.initialize_session(state)
    state[session_store.SANDBOX_TERMINAL].register_berth(Berth("B01", 100.0))
    before = state[session_store.SANDBOX_TERMINAL].to_dict()

    with pytest.raises(ValueError):
        session_store.import_terminal_json(b"{not-json", state)

    assert state[session_store.SANDBOX_TERMINAL].to_dict() == before


def test_import_validation_rejects_schema_terminal_and_size() -> None:
    valid_terminal = Terminal(datetime(2026, 1, 1, 8, 0)).to_dict()

    with pytest.raises(ValueError):
        session_store.parse_sandbox_package_bytes(
            json.dumps({"schema_version": 999, "terminal": valid_terminal}).encode()
        )

    with pytest.raises(Exception):
        session_store.parse_terminal_json_bytes(b"{}")

    with pytest.raises(ValueError):
        session_store.parse_terminal_json_bytes(b"x" * (session_store.MAX_IMPORT_BYTES + 1))

