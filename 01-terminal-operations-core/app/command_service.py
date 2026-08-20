from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models import CommandRecord, canonical_json
from terminal_core.exceptions import TerminalDomainError
from terminal_core.terminal import Terminal


@dataclass(frozen=True)
class CommandExecutionResult:
    terminal: Terminal
    record: CommandRecord
    return_value: Any = None
    rollback_restored: bool = False


def execute_terminal_command(
    terminal: Terminal,
    *,
    command_name: str,
    parameters: Mapping[str, Any],
    operation: Callable[[Terminal], Any],
    sequence: int,
) -> CommandExecutionResult:
    before = terminal.to_dict()
    before_json = canonical_json(before)
    before_event_count = terminal.event_count

    try:
        return_value = operation(terminal)
        after = terminal.to_dict()
        terminal.snapshot()
    except (TerminalDomainError, ValueError, TypeError) as error:
        current = terminal.to_dict()
        restored_terminal = terminal
        rollback_restored = False
        if current != before:
            restored_terminal = Terminal.from_dict(before)
            rollback_restored = True

        record = CommandRecord(
            sequence=sequence,
            command_name=command_name,
            attempted_at=datetime.now(),
            parameters=parameters,
            success=False,
            new_event_ids=(),
            new_event_types=(),
            error_type=type(error).__name__,
            error_message=str(error),
            before_terminal_json=before_json,
            after_terminal_json=None,
        )
        return CommandExecutionResult(
            terminal=restored_terminal,
            record=record,
            return_value=None,
            rollback_restored=rollback_restored,
        )

    new_events = terminal.events[before_event_count:]
    record = CommandRecord(
        sequence=sequence,
        command_name=command_name,
        attempted_at=datetime.now(),
        parameters=parameters,
        success=True,
        new_event_ids=tuple(event.event_id for event in new_events),
        new_event_types=tuple(event.event_type.value for event in new_events),
        error_type=None,
        error_message=None,
        before_terminal_json=before_json,
        after_terminal_json=canonical_json(after),
    )
    return CommandExecutionResult(
        terminal=terminal,
        record=record,
        return_value=return_value,
        rollback_restored=False,
    )

