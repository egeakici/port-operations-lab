from __future__ import annotations

import json
from collections.abc import MutableMapping
from datetime import datetime
from typing import Any

from app.models import (
    SANDBOX_SCENARIO_SCHEMA_VERSION,
    CommandRecord,
    SandboxScenarioPackage,
    SavedCheckpoint,
    canonical_json,
)
from src.terminal_core.integration import build_reference_terminal, run_reference_scenario
from src.terminal_core.terminal import Terminal


SANDBOX_TERMINAL = "sandbox_terminal"
SANDBOX_NAME = "sandbox_name"
SANDBOX_DESCRIPTION = "sandbox_description"
COMMAND_HISTORY = "command_history"
NAMED_CHECKPOINTS = "named_checkpoints"
LAST_COMMAND_FEEDBACK = "last_command_feedback"
SELECTED_HISTORY_SEQUENCE = "selected_history_sequence"
REFERENCE_RESULT = "reference_result"
REFERENCE_CHECKPOINT_INDEX = "reference_checkpoint_index"
DEBUG_MODE = "debug_mode"

MAX_IMPORT_BYTES = 5 * 1024 * 1024


def _state(state: MutableMapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    if state is not None:
        return state

    import streamlit as st

    return st.session_state


def initialize_session(state: MutableMapping[str, Any] | None = None) -> None:
    store = _state(state)
    store.setdefault(SANDBOX_TERMINAL, Terminal(current_time=datetime(2026, 1, 1, 8, 0)))
    store.setdefault(SANDBOX_NAME, "Untitled sandbox")
    store.setdefault(SANDBOX_DESCRIPTION, "")
    store.setdefault(COMMAND_HISTORY, [])
    store.setdefault(NAMED_CHECKPOINTS, {})
    store.setdefault(LAST_COMMAND_FEEDBACK, None)
    store.setdefault(SELECTED_HISTORY_SEQUENCE, None)
    store.setdefault(REFERENCE_RESULT, None)
    store.setdefault(REFERENCE_CHECKPOINT_INDEX, 0)
    store.setdefault(DEBUG_MODE, False)


def get_sandbox_terminal(
    state: MutableMapping[str, Any] | None = None,
) -> Terminal:
    initialize_session(state)
    return _state(state)[SANDBOX_TERMINAL]


def replace_sandbox_terminal(
    terminal: Terminal,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    initialize_session(state)
    _state(state)[SANDBOX_TERMINAL] = terminal


def append_command_record(
    record: CommandRecord,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    initialize_session(state)
    _state(state)[COMMAND_HISTORY].append(record)
    _state(state)[LAST_COMMAND_FEEDBACK] = record


def command_history(
    state: MutableMapping[str, Any] | None = None,
) -> list[CommandRecord]:
    initialize_session(state)
    return list(_state(state)[COMMAND_HISTORY])


def next_command_sequence(
    state: MutableMapping[str, Any] | None = None,
) -> int:
    initialize_session(state)
    return len(_state(state)[COMMAND_HISTORY]) + 1


def save_checkpoint(
    name: str,
    description: str = "",
    state: MutableMapping[str, Any] | None = None,
) -> SavedCheckpoint:
    initialize_session(state)
    store = _state(state)
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Checkpoint name cannot be empty.")

    existing = store[NAMED_CHECKPOINTS]
    if any(checkpoint.name == clean_name for checkpoint in existing.values()):
        raise ValueError(f"Checkpoint name already exists: {clean_name}.")

    terminal = store[SANDBOX_TERMINAL]
    checkpoint_id = f"checkpoint-{len(existing) + 1:03d}"
    checkpoint = SavedCheckpoint(
        checkpoint_id=checkpoint_id,
        name=clean_name,
        description=description.strip(),
        created_at=datetime.now(),
        command_sequence=len(store[COMMAND_HISTORY]),
        terminal_json=canonical_json(terminal.to_dict()),
        state=terminal.snapshot(),
    )
    existing[checkpoint_id] = checkpoint
    return checkpoint


def restore_checkpoint(
    checkpoint_id: str,
    state: MutableMapping[str, Any] | None = None,
) -> Terminal:
    initialize_session(state)
    store = _state(state)
    checkpoint = store[NAMED_CHECKPOINTS][checkpoint_id]
    restored = Terminal.from_dict(json.loads(checkpoint.terminal_json))
    store[SANDBOX_TERMINAL] = restored
    return restored


def clear_sandbox(
    *,
    name: str = "Untitled sandbox",
    description: str = "",
    current_time: datetime | None = None,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    initialize_session(state)
    store = _state(state)
    store[SANDBOX_TERMINAL] = Terminal(
        current_time=current_time or datetime(2026, 1, 1, 8, 0)
    )
    store[SANDBOX_NAME] = name
    store[SANDBOX_DESCRIPTION] = description
    store[COMMAND_HISTORY] = []
    store[NAMED_CHECKPOINTS] = {}
    store[LAST_COMMAND_FEEDBACK] = None
    store[SELECTED_HISTORY_SEQUENCE] = None


def load_reference_infrastructure(
    state: MutableMapping[str, Any] | None = None,
) -> Terminal:
    initialize_session(state)
    store = _state(state)
    terminal = build_reference_terminal()
    store[SANDBOX_TERMINAL] = terminal
    store[SANDBOX_NAME] = "Reference infrastructure sandbox"
    store[SANDBOX_DESCRIPTION] = (
        "Manual sandbox preloaded with reference berth, vessels, cranes, and yard."
    )
    store[COMMAND_HISTORY] = []
    store[NAMED_CHECKPOINTS] = {}
    store[LAST_COMMAND_FEEDBACK] = None
    return terminal


def get_reference_result(state: MutableMapping[str, Any] | None = None) -> Any:
    initialize_session(state)
    store = _state(state)
    if store[REFERENCE_RESULT] is None:
        store[REFERENCE_RESULT] = run_reference_scenario()
    return store[REFERENCE_RESULT]


def terminal_json_bytes(
    state: MutableMapping[str, Any] | None = None,
) -> bytes:
    terminal = get_sandbox_terminal(state)
    return canonical_json(terminal.to_dict()).encode("utf-8")


def parse_terminal_json_bytes(data: bytes) -> Terminal:
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("Uploaded Terminal JSON exceeds the 5 MB limit.")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON upload: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("Terminal JSON must be a top-level object.")
    return Terminal.from_dict(parsed)


def build_sandbox_package(
    state: MutableMapping[str, Any] | None = None,
) -> SandboxScenarioPackage:
    initialize_session(state)
    store = _state(state)
    terminal = store[SANDBOX_TERMINAL]
    return SandboxScenarioPackage(
        schema_version=SANDBOX_SCENARIO_SCHEMA_VERSION,
        scenario={
            "name": store[SANDBOX_NAME],
            "description": store[SANDBOX_DESCRIPTION],
            "exported_at": datetime.now().isoformat(),
            "current_time": terminal.current_time.isoformat(),
        },
        terminal=terminal.to_dict(),
        commands=tuple(store[COMMAND_HISTORY]),
        checkpoints=tuple(store[NAMED_CHECKPOINTS].values()),
    )


def sandbox_package_bytes(
    state: MutableMapping[str, Any] | None = None,
) -> bytes:
    return canonical_json(build_sandbox_package(state).to_dict()).encode("utf-8")


def parse_sandbox_package_bytes(
    data: bytes,
) -> tuple[Terminal, list[CommandRecord], dict[str, SavedCheckpoint], dict[str, Any]]:
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("Uploaded sandbox package exceeds the 5 MB limit.")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid scenario package JSON: {error}") from error

    if not isinstance(parsed, dict):
        raise ValueError("Scenario package must be a top-level object.")
    if parsed.get("schema_version") != SANDBOX_SCENARIO_SCHEMA_VERSION:
        raise ValueError("Unsupported sandbox scenario schema version.")

    terminal = Terminal.from_dict(dict(parsed["terminal"]))
    commands = [
        CommandRecord.from_dict(command)
        for command in parsed.get("commands", [])
    ]
    checkpoints = {
        checkpoint.checkpoint_id: checkpoint
        for checkpoint in (
            SavedCheckpoint.from_dict(item)
            for item in parsed.get("checkpoints", [])
        )
    }
    scenario = dict(parsed.get("scenario", {}))
    return terminal, commands, checkpoints, scenario


def import_terminal_json(
    data: bytes,
    state: MutableMapping[str, Any] | None = None,
) -> Terminal:
    terminal = parse_terminal_json_bytes(data)
    replace_sandbox_terminal(terminal, state)
    return terminal


def import_sandbox_package(
    data: bytes,
    state: MutableMapping[str, Any] | None = None,
) -> Terminal:
    terminal, commands, checkpoints, scenario = parse_sandbox_package_bytes(data)
    initialize_session(state)
    store = _state(state)
    store[SANDBOX_TERMINAL] = terminal
    store[COMMAND_HISTORY] = commands
    store[NAMED_CHECKPOINTS] = checkpoints
    store[SANDBOX_NAME] = str(scenario.get("name", "Imported sandbox"))
    store[SANDBOX_DESCRIPTION] = str(scenario.get("description", ""))
    store[LAST_COMMAND_FEEDBACK] = commands[-1] if commands else None
    return terminal

