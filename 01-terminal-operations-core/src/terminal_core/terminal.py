from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .berth import Berth
from .container_group import (
    ContainerFlow,
    ContainerGroup,
)
from .exceptions import (
    TerminalConsistencyError,
    TerminalDomainError,
    TerminalDuplicateEntityError,
    TerminalInventoryError,
    TerminalLookupError,
    TerminalOperationError,
    TerminalReferenceError,
    TerminalSerializationError,
    TerminalTimeError,
    TerminalValidationError,
)
from .operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from .quay_crane import CraneStatus, QuayCrane
from .terminal_event import (
    TerminalEntityType,
    TerminalEvent,
    TerminalEventType,
)
from .terminal_state import (
    STATE_TEU_ABS_TOLERANCE,
    ContainerGroupLocation,
    TerminalState,
)
from .vessel import Vessel, VesselStatus
from .yard_block import YardBlock


TERMINAL_SCHEMA_VERSION = 1
_EVENT_ID_PATTERN = re.compile(r"^EVT-(\d{6})$")
_SHIP_SIDE_TASK_TYPES = {
    OperationType.DISCHARGE,
    OperationType.LOAD,
}
_ACTIVE_TASK_STATUSES = {
    OperationTaskStatus.ASSIGNED,
    OperationTaskStatus.IN_PROGRESS,
    OperationTaskStatus.BLOCKED,
}


@dataclass
class Terminal:
    current_time: datetime
    _vessels: dict[str, Vessel] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _berths: dict[str, Berth] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _quay_cranes: dict[str, QuayCrane] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _yard_blocks: dict[str, YardBlock] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _container_groups: dict[str, ContainerGroup] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _operation_tasks: dict[str, OperationTask] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _group_locations: dict[tuple[str, TaskLocationType, str], float] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _events: list[TerminalEvent] = field(
        default_factory=list,
        init=False,
        repr=False,
    )
    _next_event_sequence: int = field(
        default=1,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.current_time, datetime):
            raise TerminalValidationError(
                "Terminal current_time must be a datetime value."
            )

    @classmethod
    def create(
        cls,
        *,
        current_time: datetime,
        vessels: tuple[Vessel, ...] = (),
        berths: tuple[Berth, ...] = (),
        quay_cranes: tuple[QuayCrane, ...] = (),
        yard_blocks: tuple[YardBlock, ...] = (),
        container_groups: tuple[ContainerGroup, ...] = (),
        operation_tasks: tuple[OperationTask, ...] = (),
        group_locations: tuple[ContainerGroupLocation, ...] = (),
        events: tuple[TerminalEvent, ...] = (),
    ) -> Terminal:
        terminal = cls(current_time=current_time)

        for vessel in vessels:
            terminal._add_entity_copy(
                terminal._vessels,
                _clone_vessel(vessel),
                "vessel",
                "vessel_id",
            )

        for berth in berths:
            terminal._add_entity_copy(
                terminal._berths,
                _clone_berth(berth),
                "berth",
                "berth_id",
            )

        for crane in quay_cranes:
            terminal._add_entity_copy(
                terminal._quay_cranes,
                _clone_crane(crane),
                "quay crane",
                "crane_id",
            )

        for block in yard_blocks:
            terminal._add_entity_copy(
                terminal._yard_blocks,
                _clone_yard_block(block),
                "yard block",
                "block_id",
            )

        for group in container_groups:
            terminal._add_entity_copy(
                terminal._container_groups,
                _clone_group(group),
                "container group",
                "group_id",
            )

        for task in operation_tasks:
            terminal._add_entity_copy(
                terminal._operation_tasks,
                _clone_task(task),
                "operation task",
                "task_id",
            )

        terminal._set_initial_group_locations(group_locations)
        terminal._events = [_clone_event(event) for event in events]
        terminal._validate_event_log()
        terminal._next_event_sequence = terminal._derive_next_event_sequence()
        terminal._relink_berth_occupancy_vessels()
        terminal.snapshot()

        return terminal

    @property
    def vessel_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._vessels))

    @property
    def berth_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._berths))

    @property
    def quay_crane_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._quay_cranes))

    @property
    def yard_block_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._yard_blocks))

    @property
    def container_group_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._container_groups))

    @property
    def operation_task_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._operation_tasks))

    @property
    def vessel_count(self) -> int:
        return len(self._vessels)

    @property
    def berth_count(self) -> int:
        return len(self._berths)

    @property
    def quay_crane_count(self) -> int:
        return len(self._quay_cranes)

    @property
    def yard_block_count(self) -> int:
        return len(self._yard_blocks)

    @property
    def container_group_count(self) -> int:
        return len(self._container_groups)

    @property
    def operation_task_count(self) -> int:
        return len(self._operation_tasks)

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def events(self) -> tuple[TerminalEvent, ...]:
        return tuple(self._events)

    def get_vessel(self, vessel_id: str) -> Vessel:
        return _clone_vessel(self._get(self._vessels, vessel_id, "vessel"))

    def get_berth(self, berth_id: str) -> Berth:
        return _clone_berth(self._get(self._berths, berth_id, "berth"))

    def get_quay_crane(self, crane_id: str) -> QuayCrane:
        return _clone_crane(
            self._get(self._quay_cranes, crane_id, "quay crane")
        )

    def get_yard_block(self, block_id: str) -> YardBlock:
        return _clone_yard_block(
            self._get(self._yard_blocks, block_id, "yard block")
        )

    def get_container_group(self, group_id: str) -> ContainerGroup:
        return _clone_group(
            self._get(
                self._container_groups,
                group_id,
                "container group",
            )
        )

    def get_operation_task(self, task_id: str) -> OperationTask:
        return _clone_task(
            self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
        )

    def locations_for_group(
        self,
        group_id: str,
    ) -> tuple[ContainerGroupLocation, ...]:
        _validate_id(group_id, "Container group ID")

        if group_id not in self._container_groups:
            raise TerminalLookupError(
                f"Unknown container group ID in Terminal: {group_id}."
            )

        return tuple(
            location
            for location in self._export_group_locations()
            if location.group_id == group_id
        )

    def group_teu_at(
        self,
        group_id: str,
        location_type: TaskLocationType | None = None,
        location_id: str | None = None,
    ) -> float:
        _validate_id(group_id, "Container group ID")

        if (
            location_type is not None
            and not isinstance(location_type, TaskLocationType)
        ):
            raise TerminalValidationError(
                "Location type filter must be a TaskLocationType value."
            )

        if location_id is not None:
            _validate_id(location_id, "Location ID")

        return sum(
            location.teu
            for location in self.locations_for_group(group_id)
            if (
                location_type is None
                or location.location.location_type == location_type
            )
            and (
                location_id is None
                or location.location.location_id == location_id
            )
        )

    def snapshot(self) -> TerminalState:
        return TerminalState.capture(
            current_time=self.current_time,
            vessels=self._vessels.values(),
            berths=self._berths.values(),
            quay_cranes=self._quay_cranes.values(),
            yard_blocks=self._yard_blocks.values(),
            container_groups=self._container_groups.values(),
            operation_tasks=self._operation_tasks.values(),
            group_locations=self._export_group_locations(),
            events=self._events,
        )

    def advance_time_to(self, new_time: datetime) -> None:
        if not isinstance(new_time, datetime):
            raise TerminalTimeError(
                "Terminal time can only advance to a datetime value."
            )

        self._ensure_comparable_time(new_time)

        if new_time < self.current_time:
            raise TerminalTimeError("Terminal time cannot move backwards.")

        self.current_time = new_time

    def register_vessel(
        self,
        vessel: Vessel,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        with self._atomic():
            self._resolve_occurred_at(occurred_at)
            copied = _clone_vessel(vessel)

            if copied.status not in {
                VesselStatus.APPROACHING,
                VesselStatus.WAITING,
            }:
                raise TerminalOperationError(
                    "Terminal can only register approaching or "
                    "waiting vessels incrementally."
                )

            self._add_entity_copy(
                self._vessels,
                copied,
                "vessel",
                "vessel_id",
            )

    def register_berth(
        self,
        berth: Berth,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        with self._atomic():
            self._resolve_occurred_at(occurred_at)
            copied = _clone_berth(berth)

            if copied.occupancies:
                raise TerminalOperationError(
                    "Terminal can only register empty berths "
                    "incrementally."
                )

            self._add_entity_copy(
                self._berths,
                copied,
                "berth",
                "berth_id",
            )

    def register_quay_crane(
        self,
        crane: QuayCrane,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        with self._atomic():
            self._resolve_occurred_at(occurred_at)
            copied = _clone_crane(crane)

            if (
                copied.status != CraneStatus.AVAILABLE
                or copied.assigned_vessel_id is not None
            ):
                raise TerminalOperationError(
                    "Terminal can only register available, "
                    "unassigned quay cranes incrementally."
                )

            self._add_entity_copy(
                self._quay_cranes,
                copied,
                "quay crane",
                "crane_id",
            )

    def register_yard_block(
        self,
        block: YardBlock,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        with self._atomic():
            self._resolve_occurred_at(occurred_at)
            copied = _clone_yard_block(block)

            if copied.stored_groups or copied.reservations:
                raise TerminalOperationError(
                    "Terminal can only register empty yard blocks "
                    "incrementally."
                )

            self._add_entity_copy(
                self._yard_blocks,
                copied,
                "yard block",
                "block_id",
            )

    def register_container_group(
        self,
        group: ContainerGroup,
        *,
        initial_locations: Iterable[ContainerGroupLocation] = (),
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            copied = _clone_group(group)
            self._add_entity_copy(
                self._container_groups,
                copied,
                "container group",
                "group_id",
            )
            self._set_group_initial_location(
                copied,
                tuple(initial_locations),
            )

            return self._emit_event(
                TerminalEventType.CONTAINER_GROUP_REGISTERED,
                TerminalEntityType.CONTAINER_GROUP,
                copied.group_id,
                occurred_at=event_time,
                correlation_id=copied.group_id,
                payload={
                    "flow": copied.flow.value,
                    "total_teu": copied.total_teu,
                },
            )

    def register_operation_task(
        self,
        task: OperationTask,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            copied = _clone_task(task)

            if (
                copied.status != OperationTaskStatus.CREATED
                or not math.isclose(
                    copied.completed_teu,
                    0.0,
                    abs_tol=STATE_TEU_ABS_TOLERANCE,
                )
                or copied.assigned_resource_id is not None
            ):
                raise TerminalOperationError(
                    "Terminal can only register new created tasks "
                    "with no progress or resource."
                )

            self._add_entity_copy(
                self._operation_tasks,
                copied,
                "operation task",
                "task_id",
            )

            return self._emit_event(
                TerminalEventType.TASK_CREATED,
                TerminalEntityType.OPERATION_TASK,
                copied.task_id,
                occurred_at=event_time,
                correlation_id=copied.task_id,
                payload={
                    "group_id": copied.group_id,
                    "task_type": copied.task_type.value,
                    "planned_teu": copied.planned_teu,
                },
            )

    def arrive_vessel(
        self,
        vessel_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, TerminalEvent]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            vessel = self._get(self._vessels, vessel_id, "vessel")

            if vessel.status != VesselStatus.APPROACHING:
                raise TerminalOperationError(
                    "Only approaching vessels can arrive."
                )

            vessel.transition_to(VesselStatus.WAITING)
            arrived = self._emit_event(
                TerminalEventType.VESSEL_ARRIVED,
                TerminalEntityType.VESSEL,
                vessel_id,
                occurred_at=event_time,
                correlation_id=vessel_id,
            )
            waiting = self._emit_event(
                TerminalEventType.VESSEL_WAITING,
                TerminalEntityType.VESSEL,
                vessel_id,
                occurred_at=event_time,
                correlation_id=vessel_id,
                causation_id=arrived.event_id,
            )

            return arrived, waiting

    def berth_vessel(
        self,
        vessel_id: str,
        berth_id: str,
        start_position_m: float,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, TerminalEvent]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            vessel = self._get(self._vessels, vessel_id, "vessel")
            berth = self._get(self._berths, berth_id, "berth")

            if vessel.status != VesselStatus.WAITING:
                raise TerminalOperationError(
                    "Only waiting vessels can be berthed."
                )

            occupancy = berth.place_vessel(vessel, start_position_m)
            vessel.transition_to(VesselStatus.BERTHED)
            self._relink_berth_occupancy_vessels()
            occupancy_added = self._emit_event(
                TerminalEventType.BERTH_OCCUPANCY_ADDED,
                TerminalEntityType.BERTH,
                berth_id,
                occurred_at=event_time,
                correlation_id=vessel_id,
                payload={
                    "vessel_id": vessel_id,
                    "start_position_m": occupancy.start_position_m,
                    "end_position_m": occupancy.end_position_m,
                },
            )
            berthed = self._emit_event(
                TerminalEventType.VESSEL_BERTHED,
                TerminalEntityType.VESSEL,
                vessel_id,
                occurred_at=event_time,
                correlation_id=vessel_id,
                causation_id=occupancy_added.event_id,
                payload={
                    "berth_id": berth_id,
                },
            )

            return occupancy_added, berthed

    def depart_vessel(
        self,
        vessel_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, TerminalEvent, TerminalEvent]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            vessel = self._get(self._vessels, vessel_id, "vessel")
            berth = self._find_berth_for_vessel(vessel_id)

            if vessel.status != VesselStatus.OPERATING:
                raise TerminalOperationError(
                    "Only operating vessels can depart."
                )

            completed = self._emit_event(
                TerminalEventType.VESSEL_OPERATION_COMPLETED,
                TerminalEntityType.VESSEL,
                vessel_id,
                occurred_at=event_time,
                correlation_id=vessel_id,
            )
            self._ensure_vessel_can_depart(vessel_id)
            berth.remove_vessel(vessel_id)
            occupancy_removed = self._emit_event(
                TerminalEventType.BERTH_OCCUPANCY_REMOVED,
                TerminalEntityType.BERTH,
                berth.berth_id,
                occurred_at=event_time,
                correlation_id=vessel_id,
                causation_id=completed.event_id,
                payload={
                    "vessel_id": vessel_id,
                },
            )
            vessel.transition_to(VesselStatus.DEPARTED)
            departed = self._emit_event(
                TerminalEventType.VESSEL_DEPARTED,
                TerminalEntityType.VESSEL,
                vessel_id,
                occurred_at=event_time,
                correlation_id=vessel_id,
                causation_id=occupancy_removed.event_id,
            )

            return completed, occupancy_removed, departed

    def reserve_yard_capacity(
        self,
        *,
        block_id: str,
        group_id: str,
        teu: float,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            group = self._get(
                self._container_groups,
                group_id,
                "container group",
            )
            block = self._get(self._yard_blocks, block_id, "yard block")
            block.reserve_capacity(
                group_id,
                teu,
                group.required_yard_capabilities,
            )

            return self._emit_event(
                TerminalEventType.YARD_RESERVATION_CREATED,
                TerminalEntityType.YARD_BLOCK,
                block_id,
                occurred_at=event_time,
                correlation_id=group_id,
                payload={
                    "group_id": group_id,
                    "teu": float(teu),
                },
            )

    def cancel_yard_reservation(
        self,
        *,
        block_id: str,
        group_id: str,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            self._get(self._container_groups, group_id, "container group")
            block = self._get(self._yard_blocks, block_id, "yard block")
            cancelled_teu = block.cancel_reservation(group_id)

            return self._emit_event(
                TerminalEventType.YARD_RESERVATION_CANCELLED,
                TerminalEntityType.YARD_BLOCK,
                block_id,
                occurred_at=event_time,
                correlation_id=group_id,
                payload={
                    "group_id": group_id,
                    "teu": cancelled_teu,
                },
            )

    def close_yard_block(
        self,
        block_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        return self._change_yard_block_status(
            block_id,
            lambda block: block.close(),
            TerminalEventType.YARD_BLOCK_CLOSED,
            occurred_at=occurred_at,
        )

    def reopen_yard_block(
        self,
        block_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        return self._change_yard_block_status(
            block_id,
            lambda block: block.reopen(),
            TerminalEventType.YARD_BLOCK_REOPENED,
            occurred_at=occurred_at,
        )

    def start_yard_block_maintenance(
        self,
        block_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        return self._change_yard_block_status(
            block_id,
            lambda block: block.start_maintenance(),
            TerminalEventType.YARD_BLOCK_MAINTENANCE_STARTED,
            occurred_at=occurred_at,
        )

    def finish_yard_block_maintenance(
        self,
        block_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        return self._change_yard_block_status(
            block_id,
            lambda block: block.finish_maintenance(),
            TerminalEventType.YARD_BLOCK_MAINTENANCE_COMPLETED,
            occurred_at=occurred_at,
        )

    def mark_task_ready(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            self._validate_task_can_be_ready(task, event_time)
            task.mark_ready()

            return self._emit_event(
                TerminalEventType.TASK_READY,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                payload={
                    "group_id": task.group_id,
                },
            )

    def assign_task_resource(
        self,
        task_id: str,
        resource_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            _validate_id(resource_id, "Resource ID")
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )

            if task.status != OperationTaskStatus.READY:
                raise TerminalOperationError(
                    "Only ready tasks can receive a resource."
                )

            if task.task_type in _SHIP_SIDE_TASK_TYPES:
                crane = self._get(
                    self._quay_cranes,
                    resource_id,
                    "quay crane",
                )
                vessel = self._get(
                    self._vessels,
                    self._ship_side_vessel_id(task),
                    "vessel",
                )
                self._ensure_vessel_is_berthed(vessel.vessel_id)
                self._ensure_vessel_has_crane_capacity(vessel.vessel_id)
                crane.assign_to_vessel(vessel)
                crane_event = self._emit_event(
                    TerminalEventType.CRANE_ASSIGNED,
                    TerminalEntityType.QUAY_CRANE,
                    resource_id,
                    occurred_at=event_time,
                    correlation_id=task_id,
                    payload={
                        "task_id": task_id,
                        "vessel_id": vessel.vessel_id,
                    },
                )
                task.assign_resource(resource_id)
                task_event = self._emit_event(
                    TerminalEventType.TASK_ASSIGNED,
                    TerminalEntityType.OPERATION_TASK,
                    task_id,
                    occurred_at=event_time,
                    correlation_id=task_id,
                    causation_id=crane_event.event_id,
                    payload={
                        "resource_id": resource_id,
                    },
                )
                return crane_event, task_event

            task.assign_resource(resource_id)
            task_event = self._emit_event(
                TerminalEventType.TASK_ASSIGNED,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                payload={
                    "resource_id": resource_id,
                },
            )
            return (task_event,)

    def unassign_task_resource(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            resource_id = task.assigned_resource_id
            events: list[TerminalEvent] = []

            if resource_id and task.task_type in _SHIP_SIDE_TASK_TYPES:
                events.extend(
                    self._release_crane_for_task(
                        task,
                        event_time,
                        correlation_id=task_id,
                    )
                )

            actual_resource_id = task.unassign_resource()
            task_event = self._emit_event(
                TerminalEventType.TASK_UNASSIGNED,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                causation_id=(
                    events[-1].event_id
                    if events
                    else None
                ),
                payload={
                    "resource_id": actual_resource_id,
                },
            )
            events.append(task_event)

            return tuple(events)

    def start_task(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            events = self._prepare_task_resource_for_work(
                task,
                event_time,
            )
            task.start(event_time)
            task_event = self._emit_event(
                TerminalEventType.TASK_STARTED,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                causation_id=(
                    events[-1].event_id
                    if events
                    else None
                ),
                payload={
                    "resource_id": task.assigned_resource_id,
                },
            )
            events.append(task_event)

            return tuple(events)

    def record_task_progress(
        self,
        task_id: str,
        teu: float,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            task.record_progress(teu)

            return self._emit_event(
                TerminalEventType.TASK_PROGRESS_RECORDED,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                payload={
                    "teu": float(teu),
                    "completed_teu": task.completed_teu,
                },
            )

    def block_task(
        self,
        task_id: str,
        reason: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            task.block(reason)

            return self._emit_event(
                TerminalEventType.TASK_BLOCKED,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                payload={
                    "reason": reason,
                    "resource_id": task.assigned_resource_id,
                },
            )

    def resume_task(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            events = self._prepare_task_resource_for_work(
                task,
                event_time,
            )
            task.resume()
            task_event = self._emit_event(
                TerminalEventType.TASK_RESUMED,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                causation_id=(
                    events[-1].event_id
                    if events
                    else None
                ),
                payload={
                    "resource_id": task.assigned_resource_id,
                },
            )
            events.append(task_event)

            return tuple(events)

    def complete_task(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            resource_id = task.assigned_resource_id
            transfer_events = self._complete_inventory_transfer(
                task,
                event_time,
            )
            completed_resource_id = task.complete(event_time)
            events = list(transfer_events)

            if (
                resource_id is not None
                and completed_resource_id == resource_id
                and task.task_type in _SHIP_SIDE_TASK_TYPES
            ):
                events.extend(
                    self._release_crane_by_id(
                        resource_id,
                        event_time,
                        correlation_id=task_id,
                        causation_id=(
                            events[-1].event_id
                            if events
                            else None
                        ),
                    )
                )

            task_event = self._emit_event(
                TerminalEventType.TASK_COMPLETED,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                causation_id=(
                    events[-1].event_id
                    if events
                    else None
                ),
                payload={
                    "completed_teu": task.completed_teu,
                    "resource_id": resource_id,
                },
            )
            events.append(task_event)

            return tuple(events)

    def cancel_task(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        return self._finish_task_without_inventory(
            task_id,
            occurred_at=occurred_at,
            action=lambda task: task.cancel(),
            event_type=TerminalEventType.TASK_CANCELLED,
        )

    def fail_task(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        return self._finish_task_without_inventory(
            task_id,
            occurred_at=occurred_at,
            action=lambda task: task.fail(),
            event_type=TerminalEventType.TASK_FAILED,
        )

    def fail_quay_crane(
        self,
        crane_id: str,
        *,
        reason: str = "Quay crane failed.",
        occurred_at: datetime | None = None,
    ) -> tuple[TerminalEvent, ...]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            crane = self._get(self._quay_cranes, crane_id, "quay crane")
            affected_task = self._active_task_for_resource(crane_id)
            interrupted_vessel_id = crane.mark_failed()
            crane_event = self._emit_event(
                TerminalEventType.CRANE_FAILED,
                TerminalEntityType.QUAY_CRANE,
                crane_id,
                occurred_at=event_time,
                correlation_id=(
                    affected_task.task_id
                    if affected_task is not None
                    else crane_id
                ),
                payload={
                    "reason": reason,
                    "interrupted_vessel_id": interrupted_vessel_id,
                },
            )
            events = [crane_event]

            if affected_task is not None:
                if affected_task.status == OperationTaskStatus.IN_PROGRESS:
                    affected_task.block(
                        f"Quay crane {crane_id} failed: {reason}"
                    )
                    events.append(
                        self._emit_event(
                            TerminalEventType.TASK_BLOCKED,
                            TerminalEntityType.OPERATION_TASK,
                            affected_task.task_id,
                            occurred_at=event_time,
                            correlation_id=affected_task.task_id,
                            causation_id=crane_event.event_id,
                            payload={
                                "reason": affected_task.blocked_reason,
                                "resource_id": crane_id,
                            },
                        )
                    )
                elif affected_task.status == OperationTaskStatus.ASSIGNED:
                    affected_task.unassign_resource()
                    events.append(
                        self._emit_event(
                            TerminalEventType.TASK_UNASSIGNED,
                            TerminalEntityType.OPERATION_TASK,
                            affected_task.task_id,
                            occurred_at=event_time,
                            correlation_id=affected_task.task_id,
                            causation_id=crane_event.event_id,
                            payload={
                                "resource_id": crane_id,
                            },
                        )
                    )

            return tuple(events)

    def repair_quay_crane(
        self,
        crane_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        return self._change_crane_state(
            crane_id,
            lambda crane: crane.repair(),
            TerminalEventType.CRANE_REPAIRED,
            occurred_at=occurred_at,
        )

    def start_quay_crane_maintenance(
        self,
        crane_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        return self._change_crane_state(
            crane_id,
            lambda crane: crane.start_maintenance(),
            TerminalEventType.CRANE_MAINTENANCE_STARTED,
            occurred_at=occurred_at,
        )

    def finish_quay_crane_maintenance(
        self,
        crane_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> TerminalEvent:
        return self._change_crane_state(
            crane_id,
            lambda crane: crane.finish_maintenance(),
            TerminalEventType.CRANE_MAINTENANCE_COMPLETED,
            occurred_at=occurred_at,
        )

    def move_quay_crane(
        self,
        crane_id: str,
        new_position_m: float,
        *,
        occurred_at: datetime | None = None,
    ) -> float:
        with self._atomic():
            self._resolve_occurred_at(occurred_at)
            crane = self._get(self._quay_cranes, crane_id, "quay crane")
            return crane.move_to(new_position_m)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TERMINAL_SCHEMA_VERSION,
            "current_time": self.current_time.isoformat(),
            "vessels": {
                vessel_id: self._vessels[vessel_id].to_dict()
                for vessel_id in sorted(self._vessels)
            },
            "berths": {
                berth_id: self._berths[berth_id].to_dict()
                for berth_id in sorted(self._berths)
            },
            "quay_cranes": {
                crane_id: self._quay_cranes[crane_id].to_dict()
                for crane_id in sorted(self._quay_cranes)
            },
            "yard_blocks": {
                block_id: self._yard_blocks[block_id].to_dict()
                for block_id in sorted(self._yard_blocks)
            },
            "container_groups": {
                group_id: self._container_groups[group_id].to_dict()
                for group_id in sorted(self._container_groups)
            },
            "operation_tasks": {
                task_id: self._operation_tasks[task_id].to_dict()
                for task_id in sorted(self._operation_tasks)
            },
            "group_locations": [
                location.to_dict()
                for location in self._export_group_locations()
            ],
            "events": [
                event.to_dict()
                for event in self._events
            ],
            "next_event_sequence": self._next_event_sequence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Terminal:
        if not isinstance(data, dict):
            raise TerminalSerializationError(
                "Invalid terminal snapshot: data must be a dictionary."
            )

        try:
            _validate_schema_version(data["schema_version"])
            current_time = _datetime_from_snapshot(
                data["current_time"],
                "current_time",
            )
            next_event_sequence = data.get("next_event_sequence")
            _validate_next_event_sequence_value(next_event_sequence)

            terminal = cls.create(
                current_time=current_time,
                vessels=_restore_registry(
                    data.get("vessels", {}),
                    registry_name="vessel",
                    entity_factory=Vessel.from_dict,
                    id_attribute="vessel_id",
                ),
                berths=_restore_registry(
                    data.get("berths", {}),
                    registry_name="berth",
                    entity_factory=Berth.from_dict,
                    id_attribute="berth_id",
                ),
                quay_cranes=_restore_registry(
                    data.get("quay_cranes", {}),
                    registry_name="quay crane",
                    entity_factory=QuayCrane.from_dict,
                    id_attribute="crane_id",
                ),
                yard_blocks=_restore_registry(
                    data.get("yard_blocks", {}),
                    registry_name="yard block",
                    entity_factory=YardBlock.from_dict,
                    id_attribute="block_id",
                ),
                container_groups=_restore_registry(
                    data.get("container_groups", {}),
                    registry_name="container group",
                    entity_factory=ContainerGroup.from_dict,
                    id_attribute="group_id",
                ),
                operation_tasks=_restore_registry(
                    data.get("operation_tasks", {}),
                    registry_name="operation task",
                    entity_factory=OperationTask.from_dict,
                    id_attribute="task_id",
                ),
                group_locations=tuple(
                    ContainerGroupLocation.from_dict(snapshot)
                    for snapshot in data.get("group_locations", [])
                ),
                events=tuple(
                    TerminalEvent.from_dict(snapshot)
                    for snapshot in data.get("events", [])
                ),
            )
            terminal._next_event_sequence = next_event_sequence
            terminal._validate_next_event_sequence()
            terminal.snapshot()
            return terminal
        except TerminalSerializationError:
            raise
        except (
            TerminalConsistencyError,
            TerminalDuplicateEntityError,
            TerminalInventoryError,
            TerminalReferenceError,
            TerminalTimeError,
        ):
            raise
        except TerminalDomainError as error:
            raise TerminalSerializationError(
                f"Invalid terminal snapshot: {error}"
            ) from error
        except (KeyError, TypeError, ValueError) as error:
            raise TerminalSerializationError(
                f"Invalid terminal snapshot: {error}"
            ) from error

    def save_to_json(self, file_path: str | Path) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as file:
            json.dump(
                self.to_dict(),
                file,
                ensure_ascii=False,
                indent=4,
            )

    @classmethod
    def load_from_json(cls, file_path: str | Path) -> Terminal:
        path = Path(file_path)

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return cls.from_dict(data)

    @contextmanager
    def _atomic(self) -> Iterator[None]:
        before = self.to_dict()

        try:
            yield
            self.snapshot()
        except Exception:
            self._restore_from_dict(before)
            raise

    def _restore_from_dict(self, data: dict[str, Any]) -> None:
        restored = Terminal.from_dict(data)
        self.current_time = restored.current_time
        self._vessels = restored._vessels
        self._berths = restored._berths
        self._quay_cranes = restored._quay_cranes
        self._yard_blocks = restored._yard_blocks
        self._container_groups = restored._container_groups
        self._operation_tasks = restored._operation_tasks
        self._group_locations = restored._group_locations
        self._events = restored._events
        self._next_event_sequence = restored._next_event_sequence

    def _add_entity_copy(
        self,
        registry: dict[str, Any],
        entity: Any,
        entity_name: str,
        id_attribute: str,
    ) -> None:
        entity_id = getattr(entity, id_attribute)

        if entity_id in registry:
            raise TerminalDuplicateEntityError(
                f"Duplicate {entity_name} ID in Terminal: {entity_id}."
            )

        registry[entity_id] = entity

    def _get(
        self,
        registry: dict[str, Any],
        entity_id: str,
        entity_name: str,
    ) -> Any:
        _validate_id(entity_id, f"{entity_name.title()} ID")

        if entity_id not in registry:
            raise TerminalLookupError(
                f"Unknown {entity_name} ID in Terminal: {entity_id}."
            )

        return registry[entity_id]

    def _resolve_occurred_at(
        self,
        occurred_at: datetime | None,
    ) -> datetime:
        if occurred_at is None:
            return self.current_time

        if not isinstance(occurred_at, datetime):
            raise TerminalTimeError(
                "Command occurred_at must be a datetime value."
            )

        self._ensure_comparable_time(occurred_at)

        if occurred_at < self.current_time:
            raise TerminalTimeError(
                "Command occurred_at cannot be earlier than "
                "Terminal current_time."
            )

        self.current_time = occurred_at
        return occurred_at

    def _ensure_comparable_time(self, value: datetime) -> None:
        try:
            value < self.current_time
        except TypeError as error:
            raise TerminalTimeError(
                "Terminal datetimes must all be either naive or aware."
            ) from error

    def _emit_event(
        self,
        event_type: TerminalEventType,
        entity_type: TerminalEntityType,
        entity_id: str,
        *,
        occurred_at: datetime,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> TerminalEvent:
        event_sequence = self._next_available_event_sequence()
        event = TerminalEvent(
            event_id=f"EVT-{event_sequence:06d}",
            event_type=event_type,
            occurred_at=occurred_at,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        if self._events and self._events[-1].occurred_at > event.occurred_at:
            raise TerminalTimeError(
                "Terminal events must be emitted in chronological order."
            )

        self._events.append(event)
        self._next_event_sequence = event_sequence + 1
        return event

    def _next_available_event_sequence(self) -> int:
        event_ids = {
            event.event_id
            for event in self._events
        }
        sequence = self._next_event_sequence

        while f"EVT-{sequence:06d}" in event_ids:
            sequence += 1

        return sequence

    def _validate_event_log(self) -> None:
        seen_event_ids: set[str] = set()
        previous_event: TerminalEvent | None = None

        for event in self._events:
            if event.event_id in seen_event_ids:
                raise TerminalDuplicateEntityError(
                    f"Duplicate event ID in Terminal: {event.event_id}."
                )

            if (
                previous_event is not None
                and previous_event.occurred_at > event.occurred_at
            ):
                raise TerminalConsistencyError(
                    "Terminal events must be in non-decreasing "
                    "occurred_at order."
                )

            self._ensure_event_time_is_not_future(event)
            seen_event_ids.add(event.event_id)
            previous_event = event

    def _ensure_event_time_is_not_future(
        self,
        event: TerminalEvent,
    ) -> None:
        try:
            is_future = event.occurred_at > self.current_time
        except TypeError as error:
            raise TerminalTimeError(
                "Terminal event times must be comparable with "
                "current_time."
            ) from error

        if is_future:
            raise TerminalTimeError(
                f"TerminalEvent {event.event_id} occurs after "
                "Terminal current_time."
            )

    def _derive_next_event_sequence(self) -> int:
        max_sequence = 0

        for event in self._events:
            match = _EVENT_ID_PATTERN.match(event.event_id)

            if match is not None:
                max_sequence = max(max_sequence, int(match.group(1)))

        return max_sequence + 1

    def _validate_next_event_sequence(self) -> None:
        max_sequence = self._derive_next_event_sequence() - 1

        if self._next_event_sequence <= max_sequence:
            raise TerminalSerializationError(
                "Terminal next_event_sequence must be greater than "
                "existing generated event IDs."
            )

    def _set_initial_group_locations(
        self,
        group_locations: tuple[ContainerGroupLocation, ...],
    ) -> None:
        for location in group_locations:
            if type(location) is not ContainerGroupLocation:
                raise TerminalValidationError(
                    "Initial group locations must be "
                    "ContainerGroupLocation values."
                )

            key = self._location_key(
                location.group_id,
                location.location.location_type,
                location.location.location_id,
            )

            if key in self._group_locations:
                raise TerminalConsistencyError(
                    "Duplicate initial container group location "
                    f"for {location.group_id}."
                )

            self._validate_group_location_reference(
                location.group_id,
                location.location.location_type,
                location.location.location_id,
            )
            self._validate_teu(location.teu, "Location TEU")
            self._group_locations[key] = location.teu

    def _set_group_initial_location(
        self,
        group: ContainerGroup,
        initial_locations: tuple[ContainerGroupLocation, ...],
    ) -> None:
        if initial_locations:
            for location in initial_locations:
                if location.group_id != group.group_id:
                    raise TerminalInventoryError(
                        "Initial locations for a registered group "
                        "must belong to that group."
                    )

            self._set_initial_group_locations(initial_locations)
            return

        if group.flow in {
            ContainerFlow.IMPORT,
            ContainerFlow.TRANSSHIPMENT,
        }:
            if group.source_vessel_id is None:
                raise TerminalReferenceError(
                    "Import and transshipment groups need a "
                    "source vessel location."
                )

            self._increase_group_location(
                group.group_id,
                TaskLocationType.VESSEL,
                group.source_vessel_id,
                group.total_teu,
            )

    def _export_group_locations(self) -> tuple[ContainerGroupLocation, ...]:
        locations = [
            ContainerGroupLocation(
                group_id=group_id,
                location=TaskLocation(
                    location_type=location_type,
                    location_id=location_id,
                ),
                teu=teu,
            )
            for (
                group_id,
                location_type,
                location_id,
            ), teu in self._group_locations.items()
        ]

        return tuple(
            sorted(
                locations,
                key=lambda location: (
                    location.group_id,
                    location.location.location_type.value,
                    location.location.location_id,
                ),
            )
        )

    def _location_key(
        self,
        group_id: str,
        location_type: TaskLocationType,
        location_id: str,
    ) -> tuple[str, TaskLocationType, str]:
        _validate_id(group_id, "Container group ID")
        _validate_id(location_id, "Location ID")

        if not isinstance(location_type, TaskLocationType):
            raise TerminalValidationError(
                "Location type must be a TaskLocationType value."
            )

        return group_id, location_type, location_id

    def _get_group_location_teu(
        self,
        group_id: str,
        location_type: TaskLocationType,
        location_id: str,
    ) -> float:
        return self._group_locations.get(
            self._location_key(group_id, location_type, location_id),
            0.0,
        )

    def _increase_group_location(
        self,
        group_id: str,
        location_type: TaskLocationType,
        location_id: str,
        teu: float,
    ) -> None:
        self._validate_group_location_reference(
            group_id,
            location_type,
            location_id,
        )
        self._validate_teu(teu, "Location TEU")
        key = self._location_key(group_id, location_type, location_id)
        self._group_locations[key] = (
            self._group_locations.get(key, 0.0)
            + float(teu)
        )

    def _decrease_group_location(
        self,
        group_id: str,
        location_type: TaskLocationType,
        location_id: str,
        teu: float,
    ) -> None:
        self._validate_group_location_reference(
            group_id,
            location_type,
            location_id,
        )
        self._validate_teu(teu, "Location TEU")
        key = self._location_key(group_id, location_type, location_id)
        current_teu = self._group_locations.get(key, 0.0)

        if (
            current_teu < float(teu)
            and not math.isclose(
                current_teu,
                float(teu),
                abs_tol=STATE_TEU_ABS_TOLERANCE,
            )
        ):
            raise TerminalInventoryError(
                f"ContainerGroup {group_id} only has {current_teu} "
                f"TEU at {location_type.value} {location_id}."
            )

        remaining_teu = current_teu - float(teu)

        if math.isclose(
            remaining_teu,
            0.0,
            abs_tol=STATE_TEU_ABS_TOLERANCE,
        ):
            self._group_locations.pop(key, None)
        else:
            self._group_locations[key] = remaining_teu

    def _validate_group_location_reference(
        self,
        group_id: str,
        location_type: TaskLocationType,
        location_id: str,
    ) -> None:
        if group_id not in self._container_groups:
            raise TerminalReferenceError(
                f"Unknown container group ID in Terminal: {group_id}."
            )

        if (
            location_type == TaskLocationType.VESSEL
            and location_id not in self._vessels
        ):
            raise TerminalReferenceError(
                f"Unknown vessel ID in Terminal: {location_id}."
            )

        if (
            location_type == TaskLocationType.YARD_BLOCK
            and location_id not in self._yard_blocks
        ):
            raise TerminalReferenceError(
                f"Unknown yard block ID in Terminal: {location_id}."
            )

    def _validate_teu(self, teu: float, label: str) -> None:
        if (
            isinstance(teu, bool)
            or not isinstance(teu, (int, float))
            or not math.isfinite(teu)
            or teu <= 0
        ):
            raise TerminalValidationError(
                f"{label} must be a finite number greater than zero."
            )

    def _validate_task_can_be_ready(
        self,
        task: OperationTask,
        event_time: datetime,
    ) -> None:
        if task.status != OperationTaskStatus.CREATED:
            raise TerminalOperationError(
                "Only created tasks can be marked ready."
            )

        if task.release_time is not None:
            try:
                release_is_future = task.release_time > event_time
            except TypeError as error:
                raise TerminalTimeError(
                    "Task release_time must be comparable with "
                    "command time."
                ) from error

            if release_is_future:
                raise TerminalOperationError(
                    "Task release_time has not been reached."
                )

        for predecessor_id in task.predecessor_task_ids:
            predecessor = self._get(
                self._operation_tasks,
                predecessor_id,
                "operation task",
            )

            if predecessor.status != OperationTaskStatus.COMPLETED:
                raise TerminalOperationError(
                    f"Task {task.task_id} requires predecessor "
                    f"{predecessor_id} to be completed."
                )

        source_teu = self._get_group_location_teu(
            task.group_id,
            task.source.location_type,
            task.source.location_id,
        )

        if (
            source_teu < task.planned_teu
            and not math.isclose(
                source_teu,
                task.planned_teu,
                abs_tol=STATE_TEU_ABS_TOLERANCE,
            )
        ):
            raise TerminalInventoryError(
                f"Task {task.task_id} does not have enough "
                "source inventory."
            )

        if task.target.location_type == TaskLocationType.YARD_BLOCK:
            block = self._get(
                self._yard_blocks,
                task.target.location_id,
                "yard block",
            )
            reserved_teu = block.reservations.get(task.group_id)

            if not math.isclose(
                reserved_teu or 0.0,
                task.planned_teu,
                abs_tol=STATE_TEU_ABS_TOLERANCE,
            ):
                raise TerminalOperationError(
                    f"Task {task.task_id} requires an exact yard "
                    "reservation before it can be ready."
                )

    def _prepare_task_resource_for_work(
        self,
        task: OperationTask,
        event_time: datetime,
    ) -> list[TerminalEvent]:
        events: list[TerminalEvent] = []

        if task.task_type not in _SHIP_SIDE_TASK_TYPES:
            return events

        if task.assigned_resource_id is None:
            raise TerminalOperationError(
                "Ship-side task has no assigned quay crane."
            )

        crane = self._get(
            self._quay_cranes,
            task.assigned_resource_id,
            "quay crane",
        )

        if crane.status == CraneStatus.FAILED:
            raise TerminalOperationError(
                "Failed quay cranes cannot operate tasks."
            )

        vessel = self._get(
            self._vessels,
            self._ship_side_vessel_id(task),
            "vessel",
        )

        if vessel.status == VesselStatus.BERTHED:
            vessel.transition_to(VesselStatus.OPERATING)
            events.append(
                self._emit_event(
                    TerminalEventType.VESSEL_OPERATION_STARTED,
                    TerminalEntityType.VESSEL,
                    vessel.vessel_id,
                    occurred_at=event_time,
                    correlation_id=task.task_id,
                    payload={
                        "task_id": task.task_id,
                    },
                )
            )

        if crane.status == CraneStatus.ASSIGNED:
            crane.start_operation()
            events.append(
                self._emit_event(
                    TerminalEventType.CRANE_OPERATION_STARTED,
                    TerminalEntityType.QUAY_CRANE,
                    crane.crane_id,
                    occurred_at=event_time,
                    correlation_id=task.task_id,
                    causation_id=(
                        events[-1].event_id
                        if events
                        else None
                    ),
                    payload={
                        "task_id": task.task_id,
                    },
                )
            )

        return events

    def _complete_inventory_transfer(
        self,
        task: OperationTask,
        event_time: datetime,
    ) -> tuple[TerminalEvent, ...]:
        events: list[TerminalEvent] = []

        if task.task_type == OperationType.DISCHARGE:
            self._decrease_group_location(
                task.group_id,
                TaskLocationType.VESSEL,
                task.source.location_id,
                task.planned_teu,
            )
            events.extend(
                self._commit_target_yard(task, event_time)
            )
            return tuple(events)

        if task.task_type == OperationType.LOAD:
            events.extend(
                self._release_source_yard(task, event_time)
            )
            self._increase_group_location(
                task.group_id,
                TaskLocationType.VESSEL,
                task.target.location_id,
                task.planned_teu,
            )
            return tuple(events)

        if task.task_type == OperationType.YARD_TRANSFER:
            events.extend(
                self._release_source_yard(task, event_time)
            )
            events.extend(
                self._commit_target_yard(task, event_time)
            )
            return tuple(events)

        if task.task_type == OperationType.GATE_IN:
            self._decrease_group_location(
                task.group_id,
                TaskLocationType.GATE,
                task.source.location_id,
                task.planned_teu,
            )

            events.extend(
                self._commit_target_yard(task, event_time)
            )
            return tuple(events)

        if task.task_type == OperationType.GATE_OUT:
            events.extend(
                self._release_source_yard(task, event_time)
            )
            self._increase_group_location(
                task.group_id,
                TaskLocationType.GATE,
                task.target.location_id,
                task.planned_teu,
            )
            return tuple(events)

        raise TerminalOperationError(
            f"Unsupported task type: {task.task_type.value}."
        )

    def _commit_target_yard(
        self,
        task: OperationTask,
        event_time: datetime,
    ) -> tuple[TerminalEvent, TerminalEvent]:
        block = self._get(
            self._yard_blocks,
            task.target.location_id,
            "yard block",
        )
        committed_teu = block.commit_reservation(task.group_id)

        if not math.isclose(
            committed_teu,
            task.planned_teu,
            abs_tol=STATE_TEU_ABS_TOLERANCE,
        ):
            raise TerminalConsistencyError(
                "Committed yard reservation TEU must match task "
                "planned TEU."
            )

        self._increase_group_location(
            task.group_id,
            TaskLocationType.YARD_BLOCK,
            task.target.location_id,
            committed_teu,
        )
        committed = self._emit_event(
            TerminalEventType.YARD_RESERVATION_COMMITTED,
            TerminalEntityType.YARD_BLOCK,
            block.block_id,
            occurred_at=event_time,
            correlation_id=task.group_id,
            payload={
                "group_id": task.group_id,
                "task_id": task.task_id,
                "teu": committed_teu,
            },
        )
        stored = self._emit_event(
            TerminalEventType.YARD_GROUP_STORED,
            TerminalEntityType.YARD_BLOCK,
            block.block_id,
            occurred_at=event_time,
            correlation_id=task.group_id,
            causation_id=committed.event_id,
            payload={
                "group_id": task.group_id,
                "task_id": task.task_id,
                "teu": committed_teu,
            },
        )

        return committed, stored

    def _release_source_yard(
        self,
        task: OperationTask,
        event_time: datetime,
    ) -> tuple[TerminalEvent, ...]:
        block = self._get(
            self._yard_blocks,
            task.source.location_id,
            "yard block",
        )
        released_teu = block.release_group(
            task.group_id,
            task.planned_teu,
        )

        self._decrease_group_location(
            task.group_id,
            TaskLocationType.YARD_BLOCK,
            task.source.location_id,
            released_teu,
        )

        return (
            self._emit_event(
                TerminalEventType.YARD_GROUP_RELEASED,
                TerminalEntityType.YARD_BLOCK,
                block.block_id,
                occurred_at=event_time,
                correlation_id=task.group_id,
                payload={
                    "group_id": task.group_id,
                    "task_id": task.task_id,
                    "teu": released_teu,
                },
            ),
        )

    def _finish_task_without_inventory(
        self,
        task_id: str,
        *,
        occurred_at: datetime | None,
        action: Any,
        event_type: TerminalEventType,
    ) -> tuple[TerminalEvent, ...]:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            task = self._get(
                self._operation_tasks,
                task_id,
                "operation task",
            )
            resource_id = task.assigned_resource_id
            events: list[TerminalEvent] = []

            if resource_id and task.task_type in _SHIP_SIDE_TASK_TYPES:
                events.extend(
                    self._release_crane_for_task(
                        task,
                        event_time,
                        correlation_id=task_id,
                    )
                )

            released_resource_id = action(task)
            task_event = self._emit_event(
                event_type,
                TerminalEntityType.OPERATION_TASK,
                task_id,
                occurred_at=event_time,
                correlation_id=task_id,
                causation_id=(
                    events[-1].event_id
                    if events
                    else None
                ),
                payload={
                    "resource_id": released_resource_id,
                },
            )
            events.append(task_event)

            return tuple(events)

    def _release_crane_for_task(
        self,
        task: OperationTask,
        event_time: datetime,
        *,
        correlation_id: str,
    ) -> tuple[TerminalEvent, ...]:
        if task.assigned_resource_id is None:
            return ()

        return tuple(
            self._release_crane_by_id(
                task.assigned_resource_id,
                event_time,
                correlation_id=correlation_id,
            )
        )

    def _release_crane_by_id(
        self,
        crane_id: str,
        event_time: datetime,
        *,
        correlation_id: str,
        causation_id: str | None = None,
    ) -> list[TerminalEvent]:
        crane = self._get(self._quay_cranes, crane_id, "quay crane")
        events: list[TerminalEvent] = []

        if crane.status == CraneStatus.FAILED:
            return events

        if crane.status == CraneStatus.OPERATING:
            crane.stop_operation()
            stopped = self._emit_event(
                TerminalEventType.CRANE_OPERATION_STOPPED,
                TerminalEntityType.QUAY_CRANE,
                crane_id,
                occurred_at=event_time,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            events.append(stopped)
            causation_id = stopped.event_id

        if crane.status == CraneStatus.ASSIGNED:
            released_vessel_id = crane.release_from_vessel()
            events.append(
                self._emit_event(
                    TerminalEventType.CRANE_RELEASED,
                    TerminalEntityType.QUAY_CRANE,
                    crane_id,
                    occurred_at=event_time,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    payload={
                        "vessel_id": released_vessel_id,
                    },
                )
            )

        return events

    def _change_yard_block_status(
        self,
        block_id: str,
        action: Any,
        event_type: TerminalEventType,
        *,
        occurred_at: datetime | None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            block = self._get(self._yard_blocks, block_id, "yard block")
            action(block)

            return self._emit_event(
                event_type,
                TerminalEntityType.YARD_BLOCK,
                block_id,
                occurred_at=event_time,
                correlation_id=block_id,
            )

    def _change_crane_state(
        self,
        crane_id: str,
        action: Any,
        event_type: TerminalEventType,
        *,
        occurred_at: datetime | None,
    ) -> TerminalEvent:
        with self._atomic():
            event_time = self._resolve_occurred_at(occurred_at)
            crane = self._get(self._quay_cranes, crane_id, "quay crane")
            action(crane)

            return self._emit_event(
                event_type,
                TerminalEntityType.QUAY_CRANE,
                crane_id,
                occurred_at=event_time,
                correlation_id=crane_id,
            )

    def _ship_side_vessel_id(self, task: OperationTask) -> str:
        if task.task_type == OperationType.DISCHARGE:
            return task.source.location_id

        if task.task_type == OperationType.LOAD:
            return task.target.location_id

        raise TerminalOperationError(
            "Task is not a ship-side operation."
        )

    def _ensure_vessel_is_berthed(self, vessel_id: str) -> None:
        self._find_berth_for_vessel(vessel_id)

    def _ensure_vessel_has_crane_capacity(self, vessel_id: str) -> None:
        vessel = self._get(self._vessels, vessel_id, "vessel")
        assigned_count = sum(
            1
            for crane in self._quay_cranes.values()
            if crane.assigned_vessel_id == vessel_id
        )

        if assigned_count >= vessel.max_cranes:
            raise TerminalOperationError(
                f"Vessel {vessel_id} has no spare crane capacity."
            )

    def _find_berth_for_vessel(self, vessel_id: str) -> Berth:
        for berth in self._berths.values():
            if berth.contains_vessel(vessel_id):
                return berth

        raise TerminalLookupError(
            f"Vessel {vessel_id} is not placed at any berth."
        )

    def _ensure_vessel_can_depart(self, vessel_id: str) -> None:
        for crane in self._quay_cranes.values():
            if crane.assigned_vessel_id == vessel_id:
                raise TerminalOperationError(
                    f"Vessel {vessel_id} still has assigned cranes."
                )

        for task in self._operation_tasks.values():
            if (
                task.status in _ACTIVE_TASK_STATUSES
                and task.task_type in _SHIP_SIDE_TASK_TYPES
                and self._ship_side_vessel_id(task) == vessel_id
            ):
                raise TerminalOperationError(
                    f"Vessel {vessel_id} still has active tasks."
                )

        for group in self._container_groups.values():
            if group.source_vessel_id != vessel_id:
                continue

            remaining_teu = self._get_group_location_teu(
                group.group_id,
                TaskLocationType.VESSEL,
                vessel_id,
            )

            if remaining_teu > STATE_TEU_ABS_TOLERANCE:
                raise TerminalOperationError(
                    f"Vessel {vessel_id} still has source cargo "
                    f"for ContainerGroup {group.group_id}."
                )

    def _active_task_for_resource(
        self,
        resource_id: str,
    ) -> OperationTask | None:
        for task in self._operation_tasks.values():
            if (
                task.assigned_resource_id == resource_id
                and task.status in _ACTIVE_TASK_STATUSES
            ):
                return task

        return None

    def _relink_berth_occupancy_vessels(self) -> None:
        for berth in self._berths.values():
            for occupancy in berth.occupancies:
                vessel_id = occupancy.vessel.vessel_id

                if vessel_id in self._vessels:
                    occupancy.vessel = self._vessels[vessel_id]


def _validate_id(value: str | None, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise TerminalValidationError(f"{field_name} cannot be empty.")


def _validate_schema_version(schema_version: int) -> None:
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version <= 0
    ):
        raise TerminalSerializationError(
            "Terminal schema_version must be a positive integer."
        )

    if schema_version != TERMINAL_SCHEMA_VERSION:
        raise TerminalSerializationError(
            f"Unsupported Terminal schema_version: {schema_version}."
        )


def _validate_next_event_sequence_value(value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise TerminalSerializationError(
            "Terminal next_event_sequence must be a positive integer."
        )


def _datetime_from_snapshot(value: str, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TerminalSerializationError(
            f"{field_name} must be an ISO datetime string."
        )

    return datetime.fromisoformat(value)


def _restore_registry(
    snapshots: Mapping[str, Any],
    *,
    registry_name: str,
    entity_factory: Any,
    id_attribute: str,
) -> tuple[Any, ...]:
    if not isinstance(snapshots, Mapping):
        raise TerminalSerializationError(
            f"Terminal {registry_name} registry must be a mapping."
        )

    entities: list[Any] = []

    for registry_key, snapshot in snapshots.items():
        _validate_id(registry_key, f"{registry_name.title()} registry key")
        entity = entity_factory(snapshot)
        entity_id = getattr(entity, id_attribute)

        if registry_key != entity_id:
            raise TerminalSerializationError(
                f"Terminal {registry_name} registry key {registry_key} "
                f"does not match entity ID {entity_id}."
            )

        entities.append(entity)

    return tuple(entities)


def _clone_vessel(vessel: Vessel) -> Vessel:
    if not isinstance(vessel, Vessel):
        raise TerminalValidationError("Expected a Vessel value.")

    return Vessel.from_dict(vessel.to_dict())


def _clone_berth(berth: Berth) -> Berth:
    if not isinstance(berth, Berth):
        raise TerminalValidationError("Expected a Berth value.")

    return Berth.from_dict(berth.to_dict())


def _clone_crane(crane: QuayCrane) -> QuayCrane:
    if not isinstance(crane, QuayCrane):
        raise TerminalValidationError("Expected a QuayCrane value.")

    return QuayCrane.from_dict(crane.to_dict())


def _clone_yard_block(block: YardBlock) -> YardBlock:
    if not isinstance(block, YardBlock):
        raise TerminalValidationError("Expected a YardBlock value.")

    return YardBlock.from_dict(block.to_dict())


def _clone_group(group: ContainerGroup) -> ContainerGroup:
    if not isinstance(group, ContainerGroup):
        raise TerminalValidationError("Expected a ContainerGroup value.")

    return ContainerGroup.from_dict(group.to_dict())


def _clone_task(task: OperationTask) -> OperationTask:
    if not isinstance(task, OperationTask):
        raise TerminalValidationError("Expected an OperationTask value.")

    return OperationTask.from_dict(task.to_dict())


def _clone_event(event: TerminalEvent) -> TerminalEvent:
    if not isinstance(event, TerminalEvent):
        raise TerminalValidationError("Expected a TerminalEvent value.")

    return TerminalEvent.from_dict(event.to_dict())
