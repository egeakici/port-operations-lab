from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from src.terminal_core.terminal_state import TerminalState


SANDBOX_SCENARIO_SCHEMA_VERSION = 1


def freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): freeze_json_value(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_value(item) for item in value)

    if value is None or isinstance(value, (str, bool, int, float)):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


def thaw_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): thaw_json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [thaw_json_value(item) for item in value]

    return value


def canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


@dataclass(frozen=True)
class CommandRecord:
    sequence: int
    command_name: str
    attempted_at: datetime
    parameters: Mapping[str, Any]
    success: bool
    new_event_ids: tuple[str, ...]
    new_event_types: tuple[str, ...]
    error_type: str | None
    error_message: str | None
    before_terminal_json: str
    after_terminal_json: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameters",
            freeze_json_value(dict(self.parameters)),
        )
        object.__setattr__(
            self,
            "new_event_ids",
            tuple(str(event_id) for event_id in self.new_event_ids),
        )
        object.__setattr__(
            self,
            "new_event_types",
            tuple(str(event_type) for event_type in self.new_event_types),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "command_name": self.command_name,
            "attempted_at": self.attempted_at.isoformat(),
            "parameters": thaw_json_value(self.parameters),
            "success": self.success,
            "new_event_ids": list(self.new_event_ids),
            "new_event_types": list(self.new_event_types),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "before_terminal_json": self.before_terminal_json,
            "after_terminal_json": self.after_terminal_json,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CommandRecord:
        return cls(
            sequence=int(data["sequence"]),
            command_name=str(data["command_name"]),
            attempted_at=datetime.fromisoformat(str(data["attempted_at"])),
            parameters=dict(data.get("parameters", {})),
            success=bool(data["success"]),
            new_event_ids=tuple(data.get("new_event_ids", ())),
            new_event_types=tuple(data.get("new_event_types", ())),
            error_type=data.get("error_type"),
            error_message=data.get("error_message"),
            before_terminal_json=str(data["before_terminal_json"]),
            after_terminal_json=(
                None
                if data.get("after_terminal_json") is None
                else str(data["after_terminal_json"])
            ),
        )


@dataclass(frozen=True)
class SavedCheckpoint:
    checkpoint_id: str
    name: str
    description: str
    created_at: datetime
    command_sequence: int
    terminal_json: str
    state: TerminalState

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "command_sequence": self.command_sequence,
            "terminal_json": self.terminal_json,
            "state": self.state.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SavedCheckpoint:
        return cls(
            checkpoint_id=str(data["checkpoint_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            command_sequence=int(data["command_sequence"]),
            terminal_json=str(data["terminal_json"]),
            state=TerminalState.from_dict(dict(data["state"])),
        )


@dataclass(frozen=True)
class SandboxScenarioPackage:
    schema_version: int
    scenario: Mapping[str, Any]
    terminal: Mapping[str, Any]
    commands: tuple[CommandRecord, ...]
    checkpoints: tuple[SavedCheckpoint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario": thaw_json_value(self.scenario),
            "terminal": thaw_json_value(self.terminal),
            "commands": [
                command.to_dict()
                for command in self.commands
            ],
            "checkpoints": [
                checkpoint.to_dict()
                for checkpoint in self.checkpoints
            ],
        }
