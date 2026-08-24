from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_core import TerminalEventType

if TYPE_CHECKING:
    from mini_port_sim.simulation import PortSimulation


@dataclass(frozen=True)
class BerthTimelineSegment:
    vessel_id: str
    berth_id: str
    start_position_m: float
    end_position_m: float
    start_minutes: float
    end_minutes: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel_id": self.vessel_id,
            "berth_id": self.berth_id,
            "start_position_m": self.start_position_m,
            "end_position_m": self.end_position_m,
            "start_minutes": self.start_minutes,
            "end_minutes": self.end_minutes,
        }


@dataclass(frozen=True)
class CraneTimelineSegment:
    crane_id: str
    state: str
    start_minutes: float
    end_minutes: float
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "crane_id": self.crane_id,
            "state": self.state,
            "start_minutes": self.start_minutes,
            "end_minutes": self.end_minutes,
            "task_id": self.task_id,
        }


def build_berth_timeline(
    simulation: "PortSimulation",
) -> tuple[BerthTimelineSegment, ...]:
    segments: list[BerthTimelineSegment] = []

    for record in simulation.lifecycle_records:
        vessel = simulation.terminal.get_vessel(record.vessel_id)
        segments.append(
            BerthTimelineSegment(
                vessel_id=record.vessel_id,
                berth_id=record.berth_id,
                start_position_m=record.start_position_m,
                end_position_m=record.start_position_m + vessel.length_m,
                start_minutes=record.berth_time_minutes,
                end_minutes=record.departure_time_minutes,
            )
        )

    return tuple(segments)


def build_crane_timeline(
    simulation: "PortSimulation",
) -> tuple[CraneTimelineSegment, ...]:
    segments: list[CraneTimelineSegment] = []
    open_operating: dict[str, tuple[float, str | None]] = {}
    open_failed: dict[str, float] = {}

    for event in simulation.terminal.events:
        elapsed = (
            event.occurred_at - simulation.start_time
        ).total_seconds() / 60.0

        if event.event_type == TerminalEventType.CRANE_OPERATION_STARTED:
            open_operating[event.entity_id] = (
                elapsed,
                event.payload.get("task_id"),
            )
        elif (
            event.event_type == TerminalEventType.CRANE_OPERATION_STOPPED
            and event.entity_id in open_operating
        ):
            started_at, task_id = open_operating.pop(event.entity_id)
            segments.append(
                CraneTimelineSegment(
                    crane_id=event.entity_id,
                    state="operating",
                    start_minutes=started_at,
                    end_minutes=elapsed,
                    task_id=task_id,
                )
            )
        elif event.event_type == TerminalEventType.CRANE_FAILED:
            open_failed[event.entity_id] = elapsed
        elif (
            event.event_type == TerminalEventType.CRANE_REPAIRED
            and event.entity_id in open_failed
        ):
            segments.append(
                CraneTimelineSegment(
                    crane_id=event.entity_id,
                    state="failed",
                    start_minutes=open_failed.pop(event.entity_id),
                    end_minutes=elapsed,
                )
            )

    for crane_id, (started_at, task_id) in open_operating.items():
        segments.append(
            CraneTimelineSegment(
                crane_id=crane_id,
                state="operating",
                start_minutes=started_at,
                end_minutes=simulation.elapsed_minutes,
                task_id=task_id,
            )
        )

    for crane_id, started_at in open_failed.items():
        segments.append(
            CraneTimelineSegment(
                crane_id=crane_id,
                state="failed",
                start_minutes=started_at,
                end_minutes=simulation.elapsed_minutes,
            )
        )

    return tuple(
        sorted(
            segments,
            key=lambda segment: (
                segment.crane_id,
                segment.start_minutes,
                segment.state,
            ),
        )
    )


def save_timeline_json(
    *,
    berth_segments: tuple[BerthTimelineSegment, ...],
    crane_segments: tuple[CraneTimelineSegment, ...],
    file_path: str | Path,
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "berth_timeline": [
                    segment.to_dict() for segment in berth_segments
                ],
                "crane_timeline": [
                    segment.to_dict() for segment in crane_segments
                ],
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
