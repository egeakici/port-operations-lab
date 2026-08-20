from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
from typing import Any

from terminal_core.berth import Berth
from terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from terminal_core.operation_task import (
    OperationTask,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.quay_crane import QuayCrane
from terminal_core.terminal import Terminal
from terminal_core.terminal_event import TerminalEvent
from terminal_core.terminal_state import (
    ContainerGroupLocation,
    TerminalState,
)
from terminal_core.vessel import Vessel
from terminal_core.yard_block import YardBlock, YardCapability


REFERENCE_SCENARIO_ID = "two-vessel-transshipment-v1"
DEFAULT_REFERENCE_START_TIME = datetime(2026, 1, 1, 8, 0)

REFERENCE_BERTH_ID = "B01"
REFERENCE_INBOUND_VESSEL_ID = "V-IN"
REFERENCE_OUTBOUND_VESSEL_ID = "V-OUT"
REFERENCE_PRIMARY_CRANE_ID = "QC01"
REFERENCE_BACKUP_CRANE_ID = "QC02"
REFERENCE_YARD_BLOCK_ID = "Y01"
REFERENCE_GROUP_ID = "G-TRANS"
REFERENCE_DISCHARGE_TASK_ID = "T-DISCHARGE"
REFERENCE_LOAD_TASK_ID = "T-LOAD"

REFERENCE_TRANS_TEU = 100.0
REFERENCE_PARTIAL_DISCHARGE_TEU = 40.0
REFERENCE_REMAINING_DISCHARGE_TEU = 60.0


class IntegrationCheckpoint(Enum):
    INITIAL = "initial"
    INBOUND_WAITING = "inbound_waiting"
    INBOUND_BERTHED = "inbound_berthed"
    DISCHARGE_IN_PROGRESS = "discharge_in_progress"
    CRANE_FAILED = "crane_failed"
    DISCHARGE_COMPLETED = "discharge_completed"
    INBOUND_DEPARTED = "inbound_departed"
    OUTBOUND_BERTHED = "outbound_berthed"
    LOAD_COMPLETED = "load_completed"
    FINAL = "final"


@dataclass(frozen=True)
class IntegrationScenarioResult:
    scenario_id: str
    started_at: datetime
    completed_at: datetime
    checkpoints: Mapping[IntegrationCheckpoint, TerminalState]
    events: tuple[TerminalEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.scenario_id, "Scenario ID")

        if not isinstance(self.started_at, datetime):
            raise ValueError("Scenario started_at must be a datetime value.")

        if not isinstance(self.completed_at, datetime):
            raise ValueError("Scenario completed_at must be a datetime value.")

        try:
            completed_before_started = self.completed_at < self.started_at
        except TypeError as error:
            raise ValueError(
                "Scenario started_at and completed_at must be comparable."
            ) from error

        if completed_before_started:
            raise ValueError(
                "Scenario completed_at cannot be earlier than started_at."
            )

        if not isinstance(self.checkpoints, Mapping):
            raise ValueError("Scenario checkpoints must be a mapping.")

        checkpoint_copy: dict[IntegrationCheckpoint, TerminalState] = {}

        for checkpoint, state in self.checkpoints.items():
            if not isinstance(checkpoint, IntegrationCheckpoint):
                raise ValueError(
                    "Scenario checkpoint keys must be "
                    "IntegrationCheckpoint values."
                )

            if not isinstance(state, TerminalState):
                raise ValueError(
                    "Scenario checkpoint values must be TerminalState values."
                )

            checkpoint_copy[checkpoint] = state

        required_checkpoints = set(IntegrationCheckpoint)
        missing_checkpoints = required_checkpoints - set(checkpoint_copy)

        if missing_checkpoints:
            names = ", ".join(
                checkpoint.value
                for checkpoint in IntegrationCheckpoint
                if checkpoint in missing_checkpoints
            )
            raise ValueError(f"Scenario checkpoints are missing: {names}.")

        event_tuple = tuple(self.events)
        seen_event_ids: set[str] = set()
        previous_event: TerminalEvent | None = None

        for event in event_tuple:
            if not isinstance(event, TerminalEvent):
                raise ValueError(
                    "Scenario events must contain TerminalEvent values."
                )

            if event.event_id in seen_event_ids:
                raise ValueError(
                    f"Scenario events contain duplicate ID {event.event_id}."
                )

            if (
                previous_event is not None
                and previous_event.occurred_at > event.occurred_at
            ):
                raise ValueError(
                    "Scenario events must be in non-decreasing time order."
                )

            try:
                event_after_completion = event.occurred_at > self.completed_at
            except TypeError as error:
                raise ValueError(
                    "Scenario event times must be comparable with "
                    "completed_at."
                ) from error

            if event_after_completion:
                raise ValueError(
                    f"Scenario event {event.event_id} occurs after "
                    "completed_at."
                )

            seen_event_ids.add(event.event_id)
            previous_event = event

        ordered_checkpoints = {
            checkpoint: checkpoint_copy[checkpoint]
            for checkpoint in IntegrationCheckpoint
        }

        object.__setattr__(
            self,
            "checkpoints",
            MappingProxyType(ordered_checkpoints),
        )
        object.__setattr__(self, "events", event_tuple)

    @property
    def checkpoint_names(self) -> tuple[str, ...]:
        return tuple(checkpoint.value for checkpoint in IntegrationCheckpoint)

    def get_checkpoint(
        self,
        checkpoint: IntegrationCheckpoint,
    ) -> TerminalState:
        if not isinstance(checkpoint, IntegrationCheckpoint):
            raise ValueError("Checkpoint must be an IntegrationCheckpoint.")

        return self.checkpoints[checkpoint]

    @property
    def initial_state(self) -> TerminalState:
        return self.get_checkpoint(IntegrationCheckpoint.INITIAL)

    @property
    def final_state(self) -> TerminalState:
        return self.get_checkpoint(IntegrationCheckpoint.FINAL)

    @property
    def event_count(self) -> int:
        return len(self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "checkpoints": {
                checkpoint.value: self.checkpoints[checkpoint].to_dict()
                for checkpoint in IntegrationCheckpoint
            },
            "events": [
                event.to_dict()
                for event in self.events
            ],
        }


def build_reference_terminal(
    start_time: datetime = DEFAULT_REFERENCE_START_TIME,
) -> Terminal:
    _validate_datetime(start_time, "Reference start time")

    terminal = Terminal(current_time=start_time)
    terminal.register_berth(
        Berth(
            berth_id=REFERENCE_BERTH_ID,
            length_m=700.0,
            min_clearance_m=20.0,
        )
    )
    terminal.register_quay_crane(
        QuayCrane(
            crane_id=REFERENCE_PRIMARY_CRANE_ID,
            position_m=100.0,
            moves_per_hour=25.0,
        )
    )
    terminal.register_quay_crane(
        QuayCrane(
            crane_id=REFERENCE_BACKUP_CRANE_ID,
            position_m=350.0,
            moves_per_hour=28.0,
        )
    )
    terminal.register_yard_block(
        YardBlock(
            block_id=REFERENCE_YARD_BLOCK_ID,
            capacity_teu=500.0,
            capabilities={YardCapability.GENERAL},
        )
    )
    terminal.register_vessel(
        Vessel(
            vessel_id=REFERENCE_INBOUND_VESSEL_ID,
            length_m=210.0,
            eta=_at(start_time, minutes=10),
            workload_moves=50,
            priority=2,
            max_cranes=2,
        )
    )
    terminal.register_vessel(
        Vessel(
            vessel_id=REFERENCE_OUTBOUND_VESSEL_ID,
            length_m=230.0,
            eta=_at(start_time, minutes=160),
            workload_moves=50,
            priority=2,
            max_cranes=2,
        )
    )
    terminal.snapshot()

    return terminal


def run_reference_scenario(
    start_time: datetime = DEFAULT_REFERENCE_START_TIME,
) -> IntegrationScenarioResult:
    _validate_datetime(start_time, "Reference start time")

    terminal = build_reference_terminal(start_time)
    checkpoints: dict[IntegrationCheckpoint, TerminalState] = {}
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.INITIAL,
        terminal,
    )

    _run_inbound_setup_phase(terminal, checkpoints, start_time)
    _run_discharge_phase(terminal, checkpoints, start_time)
    _run_outbound_phase(terminal, checkpoints, start_time)

    return IntegrationScenarioResult(
        scenario_id=REFERENCE_SCENARIO_ID,
        started_at=start_time,
        completed_at=terminal.current_time,
        checkpoints=checkpoints,
        events=terminal.events,
    )


def _run_inbound_setup_phase(
    terminal: Terminal,
    checkpoints: dict[IntegrationCheckpoint, TerminalState],
    start_time: datetime,
) -> None:
    terminal.arrive_vessel(
        REFERENCE_INBOUND_VESSEL_ID,
        occurred_at=_at(start_time, minutes=10),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.INBOUND_WAITING,
        terminal,
    )

    terminal.berth_vessel(
        REFERENCE_INBOUND_VESSEL_ID,
        REFERENCE_BERTH_ID,
        50.0,
        occurred_at=_at(start_time, minutes=20),
    )
    terminal.register_container_group(
        _create_reference_group(),
        initial_locations=(
            ContainerGroupLocation(
                group_id=REFERENCE_GROUP_ID,
                location=_vessel_location(REFERENCE_INBOUND_VESSEL_ID),
                teu=REFERENCE_TRANS_TEU,
            ),
        ),
        occurred_at=_at(start_time, minutes=25),
    )
    terminal.register_operation_task(
        _create_reference_discharge_task(),
        occurred_at=_at(start_time, minutes=30),
    )
    terminal.register_operation_task(
        _create_reference_load_task(start_time),
        occurred_at=_at(start_time, minutes=32),
    )
    terminal.reserve_yard_capacity(
        block_id=REFERENCE_YARD_BLOCK_ID,
        group_id=REFERENCE_GROUP_ID,
        teu=REFERENCE_TRANS_TEU,
        occurred_at=_at(start_time, minutes=35),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.INBOUND_BERTHED,
        terminal,
    )


def _run_discharge_phase(
    terminal: Terminal,
    checkpoints: dict[IntegrationCheckpoint, TerminalState],
    start_time: datetime,
) -> None:
    terminal.mark_task_ready(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(start_time, minutes=40),
    )
    terminal.assign_task_resource(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_PRIMARY_CRANE_ID,
        occurred_at=_at(start_time, minutes=45),
    )
    terminal.start_task(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(start_time, minutes=50),
    )
    terminal.record_task_progress(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_PARTIAL_DISCHARGE_TEU,
        occurred_at=_at(start_time, minutes=80),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.DISCHARGE_IN_PROGRESS,
        terminal,
    )

    terminal.fail_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID,
        reason="Reference hydraulic fault",
        occurred_at=_at(start_time, minutes=90),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.CRANE_FAILED,
        terminal,
    )

    terminal.unassign_task_resource(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(start_time, minutes=95),
    )
    terminal.assign_task_resource(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_BACKUP_CRANE_ID,
        occurred_at=_at(start_time, minutes=100),
    )
    terminal.start_task(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(start_time, minutes=105),
    )
    terminal.record_task_progress(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_REMAINING_DISCHARGE_TEU,
        occurred_at=_at(start_time, minutes=135),
    )
    terminal.complete_task(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(start_time, minutes=140),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.DISCHARGE_COMPLETED,
        terminal,
    )

    terminal.repair_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID,
        occurred_at=_at(start_time, minutes=145),
    )
    terminal.depart_vessel(
        REFERENCE_INBOUND_VESSEL_ID,
        occurred_at=_at(start_time, minutes=150),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.INBOUND_DEPARTED,
        terminal,
    )


def _run_outbound_phase(
    terminal: Terminal,
    checkpoints: dict[IntegrationCheckpoint, TerminalState],
    start_time: datetime,
) -> None:
    terminal.arrive_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID,
        occurred_at=_at(start_time, minutes=160),
    )
    terminal.berth_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID,
        REFERENCE_BERTH_ID,
        80.0,
        occurred_at=_at(start_time, minutes=170),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.OUTBOUND_BERTHED,
        terminal,
    )

    terminal.mark_task_ready(
        REFERENCE_LOAD_TASK_ID,
        occurred_at=_at(start_time, minutes=175),
    )
    terminal.assign_task_resource(
        REFERENCE_LOAD_TASK_ID,
        REFERENCE_BACKUP_CRANE_ID,
        occurred_at=_at(start_time, minutes=180),
    )
    terminal.start_task(
        REFERENCE_LOAD_TASK_ID,
        occurred_at=_at(start_time, minutes=185),
    )
    terminal.record_task_progress(
        REFERENCE_LOAD_TASK_ID,
        REFERENCE_TRANS_TEU,
        occurred_at=_at(start_time, minutes=225),
    )
    terminal.complete_task(
        REFERENCE_LOAD_TASK_ID,
        occurred_at=_at(start_time, minutes=230),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.LOAD_COMPLETED,
        terminal,
    )

    terminal.depart_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID,
        occurred_at=_at(start_time, minutes=240),
    )
    _capture_checkpoint(
        checkpoints,
        IntegrationCheckpoint.FINAL,
        terminal,
    )


def _capture_checkpoint(
    checkpoints: dict[IntegrationCheckpoint, TerminalState],
    checkpoint: IntegrationCheckpoint,
    terminal: Terminal,
) -> None:
    if checkpoint in checkpoints:
        raise ValueError(f"Duplicate checkpoint: {checkpoint.value}.")

    checkpoints[checkpoint] = terminal.snapshot()


def _create_reference_group() -> ContainerGroup:
    return ContainerGroup(
        group_id=REFERENCE_GROUP_ID,
        container_size=ContainerSize.FORTY_FT,
        quantity=50,
        flow=ContainerFlow.TRANSSHIPMENT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id=REFERENCE_INBOUND_VESSEL_ID,
        target_vessel_id=REFERENCE_OUTBOUND_VESSEL_ID,
    )


def _create_reference_discharge_task() -> OperationTask:
    return OperationTask(
        task_id=REFERENCE_DISCHARGE_TASK_ID,
        task_type=OperationType.DISCHARGE,
        group_id=REFERENCE_GROUP_ID,
        planned_teu=REFERENCE_TRANS_TEU,
        source=_vessel_location(REFERENCE_INBOUND_VESSEL_ID),
        target=_yard_location(),
        priority=2,
    )


def _create_reference_load_task(start_time: datetime) -> OperationTask:
    return OperationTask(
        task_id=REFERENCE_LOAD_TASK_ID,
        task_type=OperationType.LOAD,
        group_id=REFERENCE_GROUP_ID,
        planned_teu=REFERENCE_TRANS_TEU,
        source=_yard_location(),
        target=_vessel_location(REFERENCE_OUTBOUND_VESSEL_ID),
        priority=2,
        release_time=_at(start_time, minutes=170),
        predecessor_task_ids={REFERENCE_DISCHARGE_TASK_ID},
    )


def _vessel_location(vessel_id: str) -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.VESSEL,
        location_id=vessel_id,
    )


def _yard_location() -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.YARD_BLOCK,
        location_id=REFERENCE_YARD_BLOCK_ID,
    )


def _at(start_time: datetime, *, minutes: int) -> datetime:
    return start_time + timedelta(minutes=minutes)


def _validate_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime value.")


def _validate_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty.")
