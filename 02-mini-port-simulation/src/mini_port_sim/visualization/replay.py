from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_core import TerminalEventType

if TYPE_CHECKING:
    from mini_port_sim.simulation import PortSimulation


@dataclass(frozen=True)
class ReplayFrame:
    elapsed_minutes: float
    event_id: str
    event_type: str
    entity_type: str
    entity_id: str
    queue_length: int
    completed_vessel_count: int
    failed_crane_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "elapsed_minutes": self.elapsed_minutes,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "queue_length": self.queue_length,
            "completed_vessel_count": self.completed_vessel_count,
            "failed_crane_count": self.failed_crane_count,
        }


def build_event_replay(
    simulation: "PortSimulation",
) -> tuple[ReplayFrame, ...]:
    frames: list[ReplayFrame] = []
    queue_length = 0
    completed_vessels: set[str] = set()
    failed_cranes: set[str] = set()

    for event in simulation.terminal.events:
        if event.event_type == TerminalEventType.VESSEL_WAITING:
            queue_length += 1
        elif event.event_type == TerminalEventType.VESSEL_BERTHED:
            queue_length = max(0, queue_length - 1)
        elif event.event_type == TerminalEventType.VESSEL_DEPARTED:
            completed_vessels.add(event.correlation_id or event.entity_id)
        elif event.event_type == TerminalEventType.CRANE_FAILED:
            failed_cranes.add(event.entity_id)
        elif event.event_type == TerminalEventType.CRANE_REPAIRED:
            failed_cranes.discard(event.entity_id)

        frames.append(
            ReplayFrame(
                elapsed_minutes=(
                    event.occurred_at - simulation.start_time
                ).total_seconds()
                / 60.0,
                event_id=event.event_id,
                event_type=event.event_type.value,
                entity_type=event.entity_type.value,
                entity_id=event.entity_id,
                queue_length=queue_length,
                completed_vessel_count=len(completed_vessels),
                failed_crane_count=len(failed_cranes),
            )
        )

    return tuple(frames)


def save_replay_json(
    frames: tuple[ReplayFrame, ...],
    file_path: str | Path,
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            [frame.to_dict() for frame in frames],
            file,
            ensure_ascii=False,
            indent=2,
        )
