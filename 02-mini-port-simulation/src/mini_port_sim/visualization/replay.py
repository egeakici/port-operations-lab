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
    state: "SimulationReplayState | None" = None

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
            "state": self.state.to_dict() if self.state is not None else None,
        }


@dataclass(frozen=True)
class SimulationReplayState:
    elapsed_minutes: float
    vessels: dict[str, dict[str, Any]]
    cranes: dict[str, dict[str, Any]]
    yards: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "elapsed_minutes": self.elapsed_minutes,
            "vessels": self.vessels,
            "cranes": self.cranes,
            "yards": self.yards,
        }


def build_event_replay(
    simulation: "PortSimulation",
) -> tuple[ReplayFrame, ...]:
    frames: list[ReplayFrame] = []
    queue_length = 0
    completed_vessels: set[str] = set()
    failed_cranes: set[str] = set()
    state_builder = _ReplayStateBuilder(simulation)

    for event in simulation.terminal.events:
        elapsed = (
            event.occurred_at - simulation.start_time
        ).total_seconds() / 60.0
        state_builder.apply_event(event, elapsed)

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
                state=state_builder.snapshot(elapsed),
            )
        )

    return tuple(frames)


def build_state_replay(
    simulation: "PortSimulation",
) -> tuple[SimulationReplayState, ...]:
    return tuple(
        frame.state
        for frame in build_event_replay(simulation)
        if frame.state is not None
    )


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


class _ReplayStateBuilder:
    def __init__(self, simulation: "PortSimulation") -> None:
        self.simulation = simulation
        self.vessels: dict[str, dict[str, Any]] = {}
        self.cranes: dict[str, dict[str, Any]] = {
            crane_id: {
                "status": "available",
                "assigned_vessel_id": None,
                "task_id": None,
            }
            for crane_id in simulation.terminal.quay_crane_ids
        }
        self.yards: dict[str, dict[str, Any]] = {
            block_id: {
                "occupied_teu": 0.0,
                "capacity_teu": (
                    simulation.terminal.get_yard_block(block_id).capacity_teu
                ),
            }
            for block_id in simulation.terminal.yard_block_ids
        }

    def apply_event(self, event, elapsed_minutes: float) -> None:
        if event.event_type == TerminalEventType.VESSEL_ARRIVED:
            vessel = self.simulation.terminal.get_vessel(
                event.correlation_id or event.entity_id
            )
            self.vessels[vessel.vessel_id] = {
                "status": "arrived",
                "length_m": vessel.length_m,
                "berth_id": None,
                "start_position_m": None,
            }
        elif event.event_type == TerminalEventType.VESSEL_WAITING:
            self._vessel(event.correlation_id or event.entity_id)[
                "status"
            ] = "waiting"
        elif event.event_type == TerminalEventType.BERTH_OCCUPANCY_ADDED:
            vessel_id = str(event.payload["vessel_id"])
            vessel_state = self._vessel(vessel_id)
            vessel_state["berth_id"] = event.entity_id
            vessel_state["start_position_m"] = event.payload[
                "start_position_m"
            ]
        elif event.event_type == TerminalEventType.VESSEL_BERTHED:
            self._vessel(event.correlation_id or event.entity_id)[
                "status"
            ] = "berthed"
        elif event.event_type == TerminalEventType.VESSEL_OPERATION_STARTED:
            self._vessel(event.correlation_id or event.entity_id)[
                "status"
            ] = "operating"
        elif event.event_type == TerminalEventType.VESSEL_OPERATION_COMPLETED:
            self._vessel(event.correlation_id or event.entity_id)[
                "status"
            ] = "ready_to_depart"
        elif event.event_type == TerminalEventType.VESSEL_DEPARTED:
            vessel_state = self._vessel(event.correlation_id or event.entity_id)
            vessel_state["status"] = "departed"
            vessel_state["berth_id"] = None
            vessel_state["start_position_m"] = None
        elif event.event_type == TerminalEventType.CRANE_ASSIGNED:
            crane = self._crane(event.entity_id)
            crane["status"] = "assigned"
            crane["assigned_vessel_id"] = event.payload.get("vessel_id")
            crane["task_id"] = event.payload.get("task_id")
        elif event.event_type == TerminalEventType.CRANE_OPERATION_STARTED:
            crane = self._crane(event.entity_id)
            crane["status"] = "operating"
            crane["task_id"] = event.payload.get("task_id")
        elif event.event_type == TerminalEventType.CRANE_OPERATION_STOPPED:
            self._crane(event.entity_id)["status"] = "assigned"
        elif event.event_type == TerminalEventType.CRANE_RELEASED:
            crane = self._crane(event.entity_id)
            crane["status"] = "available"
            crane["assigned_vessel_id"] = None
            crane["task_id"] = None
        elif event.event_type == TerminalEventType.CRANE_FAILED:
            crane = self._crane(event.entity_id)
            crane["status"] = "failed"
            crane["assigned_vessel_id"] = None
        elif event.event_type == TerminalEventType.CRANE_REPAIRED:
            self._crane(event.entity_id)["status"] = "available"
        elif event.event_type == TerminalEventType.YARD_GROUP_STORED:
            yard = self._yard(event.entity_id)
            yard["occupied_teu"] += float(event.payload.get("teu", 0.0))
        elif event.event_type == TerminalEventType.YARD_GROUP_RELEASED:
            yard = self._yard(event.entity_id)
            yard["occupied_teu"] = max(
                0.0,
                yard["occupied_teu"] - float(event.payload.get("teu", 0.0)),
            )

    def snapshot(self, elapsed_minutes: float) -> SimulationReplayState:
        return SimulationReplayState(
            elapsed_minutes=elapsed_minutes,
            vessels={
                vessel_id: dict(state)
                for vessel_id, state in self.vessels.items()
            },
            cranes={
                crane_id: dict(state)
                for crane_id, state in self.cranes.items()
            },
            yards={
                yard_id: dict(state)
                for yard_id, state in self.yards.items()
            },
        )

    def _vessel(self, vessel_id: str) -> dict[str, Any]:
        return self.vessels.setdefault(
            vessel_id,
            {
                "status": "unknown",
                "length_m": None,
                "berth_id": None,
                "start_position_m": None,
            },
        )

    def _crane(self, crane_id: str) -> dict[str, Any]:
        return self.cranes.setdefault(
            crane_id,
            {
                "status": "available",
                "assigned_vessel_id": None,
                "task_id": None,
            },
        )

    def _yard(self, yard_id: str) -> dict[str, Any]:
        return self.yards.setdefault(
            yard_id,
            {
                "occupied_teu": 0.0,
                "capacity_teu": 0.0,
            },
        )
