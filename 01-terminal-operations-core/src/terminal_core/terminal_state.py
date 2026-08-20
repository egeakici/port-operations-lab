from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from terminal_core.berth import Berth
from terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
)
from terminal_core.exceptions import (
    ContainerGroupLocationValidationError,
    TaskLocationValidationError,
    TerminalDomainError,
    TerminalEventValidationError,
    TerminalStateConsistencyError,
    TerminalStateDuplicateEntityError,
    TerminalStateLookupError,
    TerminalStateReferenceError,
    TerminalStateValidationError,
)
from terminal_core.operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.quay_crane import CraneStatus, QuayCrane
from terminal_core.terminal_event import TerminalEvent
from terminal_core.vessel import Vessel, VesselStatus
from terminal_core.yard_block import YardBlock


TERMINAL_STATE_SCHEMA_VERSION = 1
STATE_TEU_ABS_TOLERANCE = 1e-9


@dataclass(frozen=True)
class ContainerGroupLocation:
    group_id: str
    location: TaskLocation
    teu: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.group_id, str)
            or not self.group_id.strip()
        ):
            raise ContainerGroupLocationValidationError(
                "Container group location group ID cannot be empty."
            )

        if type(self.location) is not TaskLocation:
            raise ContainerGroupLocationValidationError(
                "Container group location must use a TaskLocation."
            )

        if (
            isinstance(self.teu, bool)
            or not isinstance(self.teu, (int, float))
            or not math.isfinite(self.teu)
            or self.teu <= 0
        ):
            raise ContainerGroupLocationValidationError(
                "Container group location TEU must be a finite "
                "number greater than zero."
            )

        object.__setattr__(
            self,
            "teu",
            float(self.teu),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "location": self.location.to_dict(),
            "teu": self.teu,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> ContainerGroupLocation:
        if not isinstance(data, dict):
            raise ContainerGroupLocationValidationError(
                "Invalid container group location snapshot: "
                "data must be a dictionary."
            )

        try:
            return cls(
                group_id=data["group_id"],
                location=TaskLocation.from_dict(
                    data["location"]
                ),
                teu=data["teu"],
            )
        except TaskLocationValidationError as error:
            raise ContainerGroupLocationValidationError(
                f"Invalid container group location snapshot: {error}"
            ) from error
        except (
            KeyError,
            TypeError,
            ValueError,
            ContainerGroupLocationValidationError,
        ) as error:
            raise ContainerGroupLocationValidationError(
                f"Invalid container group location snapshot: {error}"
            ) from error


@dataclass(frozen=True)
class TerminalState:
    current_time: datetime
    vessels: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    berths: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    quay_cranes: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    yard_blocks: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    container_groups: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    operation_tasks: Mapping[str, Mapping[str, Any]] = field(
        default_factory=dict
    )
    group_locations: tuple[ContainerGroupLocation, ...] = field(
        default_factory=tuple
    )
    event_count: int = 0
    last_event_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.current_time, datetime):
            raise TerminalStateValidationError(
                "TerminalState current_time must be a datetime value."
            )

        _validate_event_metadata(
            self.event_count,
            self.last_event_id,
        )

        frozen_vessels, vessel_entities = _normalize_snapshot_registry(
            self.vessels,
            registry_name="vessel",
            entity_factory=Vessel.from_dict,
            id_attribute="vessel_id",
        )
        frozen_berths, berth_entities = _normalize_snapshot_registry(
            self.berths,
            registry_name="berth",
            entity_factory=Berth.from_dict,
            id_attribute="berth_id",
        )
        frozen_cranes, crane_entities = _normalize_snapshot_registry(
            self.quay_cranes,
            registry_name="quay crane",
            entity_factory=QuayCrane.from_dict,
            id_attribute="crane_id",
        )
        frozen_blocks, block_entities = _normalize_snapshot_registry(
            self.yard_blocks,
            registry_name="yard block",
            entity_factory=YardBlock.from_dict,
            id_attribute="block_id",
        )
        frozen_groups, group_entities = _normalize_snapshot_registry(
            self.container_groups,
            registry_name="container group",
            entity_factory=ContainerGroup.from_dict,
            id_attribute="group_id",
        )
        frozen_tasks, task_entities = _normalize_snapshot_registry(
            self.operation_tasks,
            registry_name="operation task",
            entity_factory=OperationTask.from_dict,
            id_attribute="task_id",
        )
        normalized_locations = _normalize_group_locations(
            self.group_locations
        )

        _validate_cross_entity_consistency(
            current_time=self.current_time,
            vessels=vessel_entities,
            berths=berth_entities,
            quay_cranes=crane_entities,
            yard_blocks=block_entities,
            container_groups=group_entities,
            operation_tasks=task_entities,
            group_locations=normalized_locations,
        )

        object.__setattr__(self, "vessels", frozen_vessels)
        object.__setattr__(self, "berths", frozen_berths)
        object.__setattr__(
            self,
            "quay_cranes",
            frozen_cranes,
        )
        object.__setattr__(
            self,
            "yard_blocks",
            frozen_blocks,
        )
        object.__setattr__(
            self,
            "container_groups",
            frozen_groups,
        )
        object.__setattr__(
            self,
            "operation_tasks",
            frozen_tasks,
        )
        object.__setattr__(
            self,
            "group_locations",
            normalized_locations,
        )

    @classmethod
    def capture(
        cls,
        *,
        current_time: datetime,
        vessels: Iterable[Vessel] = (),
        berths: Iterable[Berth] = (),
        quay_cranes: Iterable[QuayCrane] = (),
        yard_blocks: Iterable[YardBlock] = (),
        container_groups: Iterable[ContainerGroup] = (),
        operation_tasks: Iterable[OperationTask] = (),
        group_locations: Iterable[ContainerGroupLocation] = (),
        events: Iterable[TerminalEvent] = (),
    ) -> TerminalState:
        event_list = _normalize_events_for_capture(
            events,
            current_time,
        )

        return cls(
            current_time=current_time,
            vessels=_capture_entity_registry(
                vessels,
                expected_type=Vessel,
                id_attribute="vessel_id",
                entity_label="vessel",
            ),
            berths=_capture_entity_registry(
                berths,
                expected_type=Berth,
                id_attribute="berth_id",
                entity_label="berth",
            ),
            quay_cranes=_capture_entity_registry(
                quay_cranes,
                expected_type=QuayCrane,
                id_attribute="crane_id",
                entity_label="quay crane",
            ),
            yard_blocks=_capture_entity_registry(
                yard_blocks,
                expected_type=YardBlock,
                id_attribute="block_id",
                entity_label="yard block",
            ),
            container_groups=_capture_entity_registry(
                container_groups,
                expected_type=ContainerGroup,
                id_attribute="group_id",
                entity_label="container group",
            ),
            operation_tasks=_capture_entity_registry(
                operation_tasks,
                expected_type=OperationTask,
                id_attribute="task_id",
                entity_label="operation task",
            ),
            group_locations=tuple(group_locations),
            event_count=len(event_list),
            last_event_id=(
                event_list[-1].event_id
                if event_list
                else None
            ),
        )

    @property
    def vessel_count(self) -> int:
        return len(self.vessels)

    @property
    def berth_count(self) -> int:
        return len(self.berths)

    @property
    def quay_crane_count(self) -> int:
        return len(self.quay_cranes)

    @property
    def yard_block_count(self) -> int:
        return len(self.yard_blocks)

    @property
    def container_group_count(self) -> int:
        return len(self.container_groups)

    @property
    def operation_task_count(self) -> int:
        return len(self.operation_tasks)

    @property
    def vessel_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.vessels))

    @property
    def berth_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.berths))

    @property
    def quay_crane_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.quay_cranes))

    @property
    def yard_block_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.yard_blocks))

    @property
    def container_group_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.container_groups))

    @property
    def operation_task_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.operation_tasks))

    def get_vessel(self, vessel_id: str) -> Vessel:
        return _get_entity_copy(
            self.vessels,
            entity_id=vessel_id,
            registry_name="vessel",
            entity_factory=Vessel.from_dict,
        )

    def get_berth(self, berth_id: str) -> Berth:
        return _get_entity_copy(
            self.berths,
            entity_id=berth_id,
            registry_name="berth",
            entity_factory=Berth.from_dict,
        )

    def get_quay_crane(self, crane_id: str) -> QuayCrane:
        return _get_entity_copy(
            self.quay_cranes,
            entity_id=crane_id,
            registry_name="quay crane",
            entity_factory=QuayCrane.from_dict,
        )

    def get_yard_block(self, block_id: str) -> YardBlock:
        return _get_entity_copy(
            self.yard_blocks,
            entity_id=block_id,
            registry_name="yard block",
            entity_factory=YardBlock.from_dict,
        )

    def get_container_group(self, group_id: str) -> ContainerGroup:
        return _get_entity_copy(
            self.container_groups,
            entity_id=group_id,
            registry_name="container group",
            entity_factory=ContainerGroup.from_dict,
        )

    def get_operation_task(self, task_id: str) -> OperationTask:
        return _get_entity_copy(
            self.operation_tasks,
            entity_id=task_id,
            registry_name="operation task",
            entity_factory=OperationTask.from_dict,
        )

    def locations_for_group(
        self,
        group_id: str,
    ) -> tuple[ContainerGroupLocation, ...]:
        _validate_lookup_id(group_id, "Container group ID")

        if group_id not in self.container_groups:
            raise TerminalStateLookupError(
                f"Unknown container group ID in TerminalState: "
                f"{group_id}."
            )

        return tuple(
            location
            for location in self.group_locations
            if location.group_id == group_id
        )

    def group_teu_at(
        self,
        group_id: str,
        location_type: TaskLocationType | None = None,
        location_id: str | None = None,
    ) -> float:
        _validate_lookup_id(group_id, "Container group ID")

        if (
            location_type is not None
            and not isinstance(location_type, TaskLocationType)
        ):
            raise TerminalStateValidationError(
                "Location type filter must be a TaskLocationType value."
            )

        if location_id is not None:
            _validate_lookup_id(location_id, "Location ID")

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

    def task_ids_by_status(
        self,
        status: OperationTaskStatus,
    ) -> tuple[str, ...]:
        if not isinstance(status, OperationTaskStatus):
            raise TerminalStateValidationError(
                "Task status filter must be an OperationTaskStatus value."
            )

        task_ids = [
            task_id
            for task_id, snapshot in self.operation_tasks.items()
            if snapshot["status"] == status.value
        ]

        return tuple(sorted(task_ids))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TERMINAL_STATE_SCHEMA_VERSION,
            "current_time": self.current_time.isoformat(),
            "vessels": _thaw_state_value(self.vessels),
            "berths": _thaw_state_value(self.berths),
            "quay_cranes": _thaw_state_value(
                self.quay_cranes
            ),
            "yard_blocks": _thaw_state_value(
                self.yard_blocks
            ),
            "container_groups": _thaw_state_value(
                self.container_groups
            ),
            "operation_tasks": _thaw_state_value(
                self.operation_tasks
            ),
            "group_locations": [
                location.to_dict()
                for location in self.group_locations
            ],
            "event_count": self.event_count,
            "last_event_id": self.last_event_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> TerminalState:
        if not isinstance(data, dict):
            raise TerminalStateValidationError(
                "Invalid terminal state snapshot: "
                "data must be a dictionary."
            )

        try:
            schema_version = data["schema_version"]
            _validate_schema_version(schema_version)
            current_time = _datetime_from_snapshot(
                data["current_time"],
                "current_time",
            )
            group_locations_data = data.get(
                "group_locations",
                [],
            )

            if not isinstance(group_locations_data, list):
                raise TerminalStateValidationError(
                    "Group locations snapshot must be a list."
                )

            group_locations = tuple(
                ContainerGroupLocation.from_dict(
                    location_data
                )
                for location_data in group_locations_data
            )

            return cls(
                current_time=current_time,
                vessels=data.get("vessels", {}),
                berths=data.get("berths", {}),
                quay_cranes=data.get("quay_cranes", {}),
                yard_blocks=data.get("yard_blocks", {}),
                container_groups=data.get(
                    "container_groups",
                    {},
                ),
                operation_tasks=data.get(
                    "operation_tasks",
                    {},
                ),
                group_locations=group_locations,
                event_count=data.get("event_count", 0),
                last_event_id=data.get("last_event_id"),
            )
        except TerminalDomainError:
            raise
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise TerminalStateValidationError(
                f"Invalid terminal state snapshot: {error}"
            ) from error

    def save_to_json(
        self,
        file_path: str | Path,
    ) -> None:
        path = Path(file_path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self.to_dict(),
                file,
                ensure_ascii=False,
                indent=4,
            )

    @classmethod
    def load_from_json(
        cls,
        file_path: str | Path,
    ) -> TerminalState:
        path = Path(file_path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return cls.from_dict(data)


def _normalize_snapshot_registry(
    snapshots: Mapping[str, Mapping[str, Any]],
    *,
    registry_name: str,
    entity_factory: Callable[[dict[str, Any]], Any],
    id_attribute: str,
) -> tuple[Mapping[str, Mapping[str, Any]], dict[str, Any]]:
    if not isinstance(snapshots, Mapping):
        raise TerminalStateValidationError(
            f"TerminalState {registry_name} registry must be a mapping."
        )

    frozen_items: dict[str, Mapping[str, Any]] = {}
    entities: dict[str, Any] = {}

    for entity_id in sorted(snapshots):
        snapshot = snapshots[entity_id]

        if (
            not isinstance(entity_id, str)
            or not entity_id.strip()
        ):
            raise TerminalStateValidationError(
                f"TerminalState {registry_name} registry keys "
                "must be non-empty strings."
            )

        if not isinstance(snapshot, Mapping):
            raise TerminalStateValidationError(
                f"TerminalState {registry_name} snapshot "
                f"{entity_id} must be a mapping."
            )

        raw_frozen_snapshot = _freeze_state_value(
            snapshot,
            f"{registry_name}s.{entity_id}",
        )
        snapshot_dict = _thaw_state_value(
            raw_frozen_snapshot
        )

        try:
            entity = entity_factory(snapshot_dict)
        except TerminalDomainError as error:
            raise TerminalStateValidationError(
                f"Invalid {registry_name} snapshot {entity_id} "
                f"in TerminalState: {error}"
            ) from error
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise TerminalStateValidationError(
                f"Invalid {registry_name} snapshot {entity_id} "
                f"in TerminalState: {error}"
            ) from error

        actual_id = getattr(entity, id_attribute)

        if actual_id != entity_id:
            raise TerminalStateConsistencyError(
                f"TerminalState {registry_name} registry key "
                f"{entity_id} does not match snapshot "
                f"{id_attribute} {actual_id}."
            )

        canonical_snapshot = entity.to_dict()
        frozen_items[entity_id] = _freeze_state_value(
            canonical_snapshot,
            f"{registry_name}s.{entity_id}",
        )
        entities[entity_id] = entity

    return MappingProxyType(frozen_items), entities


def _capture_entity_registry(
    entities: Iterable[Any],
    *,
    expected_type: type,
    id_attribute: str,
    entity_label: str,
) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    for entity in entities:
        if not isinstance(entity, expected_type):
            raise TerminalStateValidationError(
                f"TerminalState capture expected {entity_label} "
                f"entities, got {type(entity).__name__}."
            )

        entity_id = getattr(entity, id_attribute)

        if entity_id in registry:
            raise TerminalStateDuplicateEntityError(
                f"Duplicate {entity_label} ID in TerminalState "
                f"capture: {entity_id}."
            )

        registry[entity_id] = entity.to_dict()

    return registry


def _normalize_events_for_capture(
    events: Iterable[TerminalEvent],
    current_time: datetime,
) -> tuple[TerminalEvent, ...]:
    if not isinstance(current_time, datetime):
        raise TerminalStateValidationError(
            "TerminalState current_time must be a datetime value."
        )

    normalized_events = tuple(events)
    seen_event_ids: set[str] = set()
    previous_event: TerminalEvent | None = None

    for event in normalized_events:
        if not isinstance(event, TerminalEvent):
            raise TerminalEventValidationError(
                "TerminalState capture events must be "
                "TerminalEvent values."
            )

        if event.event_id in seen_event_ids:
            raise TerminalStateDuplicateEntityError(
                f"Duplicate event ID in TerminalState capture: "
                f"{event.event_id}."
            )

        seen_event_ids.add(event.event_id)

        if previous_event is not None and _datetime_is_after(
            previous_event.occurred_at,
            event.occurred_at,
            message=(
                "TerminalState capture events must be in "
                "non-decreasing occurred_at order."
            ),
        ):
            raise TerminalStateConsistencyError(
                "TerminalState capture events must be in "
                "non-decreasing occurred_at order."
            )

        if _datetime_is_after(
            event.occurred_at,
            current_time,
            message=(
                "TerminalEvent occurred_at and TerminalState "
                "current_time must use comparable datetime values."
            ),
        ):
            raise TerminalStateConsistencyError(
                f"TerminalEvent {event.event_id} occurs after "
                "TerminalState current_time."
            )

        previous_event = event

    return normalized_events


def _normalize_group_locations(
    group_locations: Iterable[ContainerGroupLocation],
) -> tuple[ContainerGroupLocation, ...]:
    if not isinstance(group_locations, Iterable):
        raise TerminalStateValidationError(
            "Group locations must be an iterable."
        )

    normalized_locations: list[ContainerGroupLocation] = []
    seen_locations: set[tuple[str, str, str]] = set()

    for location in group_locations:
        if type(location) is not ContainerGroupLocation:
            raise ContainerGroupLocationValidationError(
                "Group locations must contain "
                "ContainerGroupLocation values."
            )

        key = (
            location.group_id,
            location.location.location_type.value,
            location.location.location_id,
        )

        if key in seen_locations:
            raise TerminalStateConsistencyError(
                "Duplicate container group location in "
                f"TerminalState: {location.group_id} at "
                f"{location.location.location_type.value} "
                f"{location.location.location_id}."
            )

        seen_locations.add(key)
        normalized_locations.append(location)

    return tuple(
        sorted(
            normalized_locations,
            key=lambda location: (
                location.group_id,
                location.location.location_type.value,
                location.location.location_id,
            ),
        )
    )


def _validate_cross_entity_consistency(
    *,
    current_time: datetime,
    vessels: dict[str, Vessel],
    berths: dict[str, Berth],
    quay_cranes: dict[str, QuayCrane],
    yard_blocks: dict[str, YardBlock],
    container_groups: dict[str, ContainerGroup],
    operation_tasks: dict[str, OperationTask],
    group_locations: tuple[ContainerGroupLocation, ...],
) -> None:
    _validate_container_group_references(
        vessels,
        container_groups,
    )
    berthed_vessel_ids = _validate_berth_vessel_consistency(
        vessels,
        berths,
    )
    _validate_crane_vessel_consistency(
        vessels,
        quay_cranes,
        berthed_vessel_ids,
    )
    _validate_yard_group_consistency(
        yard_blocks,
        container_groups,
    )
    _validate_group_location_consistency(
        vessels,
        yard_blocks,
        container_groups,
        group_locations,
    )
    _validate_yard_stored_group_locations(
        yard_blocks,
        group_locations,
    )
    _validate_task_consistency(
        current_time=current_time,
        vessels=vessels,
        yard_blocks=yard_blocks,
        quay_cranes=quay_cranes,
        container_groups=container_groups,
        operation_tasks=operation_tasks,
    )
    _validate_task_dependency_graph(operation_tasks)


def _validate_container_group_references(
    vessels: dict[str, Vessel],
    container_groups: dict[str, ContainerGroup],
) -> None:
    for group in container_groups.values():
        if (
            group.source_vessel_id is not None
            and group.source_vessel_id not in vessels
        ):
            raise TerminalStateReferenceError(
                f"ContainerGroup {group.group_id} references "
                f"source vessel {group.source_vessel_id}, but "
                f"{group.source_vessel_id} is not registered "
                "in TerminalState."
            )

        if (
            group.target_vessel_id is not None
            and group.target_vessel_id not in vessels
        ):
            raise TerminalStateReferenceError(
                f"ContainerGroup {group.group_id} references "
                f"target vessel {group.target_vessel_id}, but "
                f"{group.target_vessel_id} is not registered "
                "in TerminalState."
            )


def _validate_berth_vessel_consistency(
    vessels: dict[str, Vessel],
    berths: dict[str, Berth],
) -> set[str]:
    occupied_vessels: dict[str, str] = {}

    for berth in berths.values():
        berth_vessels: set[str] = set()

        for occupancy in berth.occupancies:
            vessel_id = occupancy.vessel.vessel_id

            if vessel_id not in vessels:
                raise TerminalStateReferenceError(
                    f"Berth {berth.berth_id} occupancy references "
                    f"vessel {vessel_id}, but {vessel_id} is not "
                    "registered in TerminalState."
                )

            if vessel_id in berth_vessels:
                raise TerminalStateConsistencyError(
                    f"Berth {berth.berth_id} has duplicate "
                    f"occupancy for vessel {vessel_id}."
                )

            if vessel_id in occupied_vessels:
                raise TerminalStateConsistencyError(
                    f"Vessel {vessel_id} is placed in multiple "
                    "berth occupancies."
                )

            if (
                occupancy.vessel.to_dict()
                != vessels[vessel_id].to_dict()
            ):
                raise TerminalStateConsistencyError(
                    f"Berth {berth.berth_id} occupancy vessel "
                    f"{vessel_id} does not match the registered "
                    "vessel snapshot."
                )

            if vessels[vessel_id].status not in {
                VesselStatus.BERTHED,
                VesselStatus.OPERATING,
            }:
                raise TerminalStateConsistencyError(
                    f"Vessel {vessel_id} has status "
                    f"{vessels[vessel_id].status.value} but is "
                    "present in a berth occupancy."
                )

            berth_vessels.add(vessel_id)
            occupied_vessels[vessel_id] = berth.berth_id

    for vessel in vessels.values():
        if (
            vessel.status
            in {
                VesselStatus.BERTHED,
                VesselStatus.OPERATING,
            }
            and vessel.vessel_id not in occupied_vessels
        ):
            raise TerminalStateConsistencyError(
                f"Vessel {vessel.vessel_id} has status "
                f"{vessel.status.value} but is not present in "
                "any berth occupancy."
            )

    return set(occupied_vessels)


def _validate_crane_vessel_consistency(
    vessels: dict[str, Vessel],
    quay_cranes: dict[str, QuayCrane],
    berthed_vessel_ids: set[str],
) -> None:
    crane_counts_by_vessel: dict[str, int] = {}

    for crane in quay_cranes.values():
        assigned_vessel_id = crane.assigned_vessel_id

        if assigned_vessel_id is None:
            continue

        if assigned_vessel_id not in vessels:
            raise TerminalStateReferenceError(
                f"QuayCrane {crane.crane_id} references "
                f"vessel {assigned_vessel_id}, but "
                f"{assigned_vessel_id} is not registered "
                "in TerminalState."
            )

        if assigned_vessel_id not in berthed_vessel_ids:
            raise TerminalStateConsistencyError(
                f"QuayCrane {crane.crane_id} is assigned to "
                f"vessel {assigned_vessel_id}, but that vessel "
                "is not in a berth occupancy."
            )

        if (
            crane.status == CraneStatus.OPERATING
            and vessels[assigned_vessel_id].status
            != VesselStatus.OPERATING
        ):
            raise TerminalStateConsistencyError(
                f"Operating QuayCrane {crane.crane_id} requires "
                f"vessel {assigned_vessel_id} to be operating."
            )

        if (
            crane.status == CraneStatus.ASSIGNED
            and vessels[assigned_vessel_id].status
            not in {
                VesselStatus.BERTHED,
                VesselStatus.OPERATING,
            }
        ):
            raise TerminalStateConsistencyError(
                f"Assigned QuayCrane {crane.crane_id} requires "
                f"vessel {assigned_vessel_id} to be berthed or "
                "operating."
            )

        crane_counts_by_vessel[assigned_vessel_id] = (
            crane_counts_by_vessel.get(assigned_vessel_id, 0)
            + 1
        )

    for vessel_id, crane_count in crane_counts_by_vessel.items():
        if crane_count > vessels[vessel_id].max_cranes:
            raise TerminalStateConsistencyError(
                f"Vessel {vessel_id} has {crane_count} assigned "
                f"cranes, exceeding max_cranes "
                f"{vessels[vessel_id].max_cranes}."
            )


def _validate_yard_group_consistency(
    yard_blocks: dict[str, YardBlock],
    container_groups: dict[str, ContainerGroup],
) -> None:
    reservation_totals: dict[str, float] = {}

    for block in yard_blocks.values():
        for group_id in block.stored_groups:
            if group_id not in container_groups:
                raise TerminalStateReferenceError(
                    f"YardBlock {block.block_id} stores "
                    f"ContainerGroup {group_id}, but {group_id} "
                    "is not registered in TerminalState."
                )

            _validate_block_supports_group(block, container_groups[group_id])

        for group_id, teu in block.reservations.items():
            if group_id not in container_groups:
                raise TerminalStateReferenceError(
                    f"YardBlock {block.block_id} reserves "
                    f"ContainerGroup {group_id}, but {group_id} "
                    "is not registered in TerminalState."
                )

            _validate_block_supports_group(block, container_groups[group_id])
            reservation_totals[group_id] = (
                reservation_totals.get(group_id, 0.0)
                + teu
            )

    for group_id, total_teu in reservation_totals.items():
        if _teu_greater(
            total_teu,
            container_groups[group_id].total_teu,
        ):
            raise TerminalStateConsistencyError(
                f"Yard reservations for ContainerGroup {group_id} "
                f"total {total_teu} TEU, exceeding group total "
                f"{container_groups[group_id].total_teu} TEU."
            )


def _validate_block_supports_group(
    block: YardBlock,
    group: ContainerGroup,
) -> None:
    if not block.supports_requirements(
        group.required_yard_capabilities
    ):
        raise TerminalStateConsistencyError(
            f"YardBlock {block.block_id} does not support "
            f"ContainerGroup {group.group_id} requirements."
        )


def _validate_group_location_consistency(
    vessels: dict[str, Vessel],
    yard_blocks: dict[str, YardBlock],
    container_groups: dict[str, ContainerGroup],
    group_locations: tuple[ContainerGroupLocation, ...],
) -> None:
    totals_by_group: dict[str, float] = {}

    for group_location in group_locations:
        group_id = group_location.group_id

        if group_id not in container_groups:
            raise TerminalStateReferenceError(
                f"ContainerGroupLocation references group "
                f"{group_id}, but {group_id} is not registered "
                "in TerminalState."
            )

        location = group_location.location

        if location.location_type == TaskLocationType.VESSEL:
            if location.location_id not in vessels:
                raise TerminalStateReferenceError(
                    f"ContainerGroupLocation for group {group_id} "
                    f"references vessel {location.location_id}, "
                    "but that vessel is not registered in "
                    "TerminalState."
                )

            _validate_group_vessel_location(
                container_groups[group_id],
                location.location_id,
            )

        elif location.location_type == TaskLocationType.YARD_BLOCK:
            if location.location_id not in yard_blocks:
                raise TerminalStateReferenceError(
                    f"ContainerGroupLocation for group {group_id} "
                    f"references yard block {location.location_id}, "
                    "but that block is not registered in "
                    "TerminalState."
                )

        elif (
            container_groups[group_id].flow
            == ContainerFlow.TRANSSHIPMENT
        ):
            raise TerminalStateConsistencyError(
                f"Transshipment ContainerGroup {group_id} cannot "
                "be located at a gate."
            )

        totals_by_group[group_id] = (
            totals_by_group.get(group_id, 0.0)
            + group_location.teu
        )

    for group_id, location_total in totals_by_group.items():
        group_total = container_groups[group_id].total_teu

        if _teu_greater(location_total, group_total):
            raise TerminalStateConsistencyError(
                f"ContainerGroup {group_id} locations total "
                f"{location_total} TEU, exceeding group total "
                f"{group_total} TEU."
            )


def _validate_group_vessel_location(
    group: ContainerGroup,
    vessel_id: str,
) -> None:
    if (
        group.flow == ContainerFlow.IMPORT
        and vessel_id != group.source_vessel_id
    ):
        raise TerminalStateConsistencyError(
            f"Import ContainerGroup {group.group_id} can only be "
            "located on its source vessel."
        )

    if (
        group.flow == ContainerFlow.EXPORT
        and vessel_id != group.target_vessel_id
    ):
        raise TerminalStateConsistencyError(
            f"Export ContainerGroup {group.group_id} can only be "
            "located on its target vessel."
        )

    if (
        group.flow == ContainerFlow.TRANSSHIPMENT
        and vessel_id
        not in {
            group.source_vessel_id,
            group.target_vessel_id,
        }
    ):
        raise TerminalStateConsistencyError(
            f"Transshipment ContainerGroup {group.group_id} can "
            "only be located on its source or target vessel."
        )


def _validate_yard_stored_group_locations(
    yard_blocks: dict[str, YardBlock],
    group_locations: tuple[ContainerGroupLocation, ...],
) -> None:
    location_amounts: dict[tuple[str, str], float] = {}

    for group_location in group_locations:
        if (
            group_location.location.location_type
            == TaskLocationType.YARD_BLOCK
        ):
            key = (
                group_location.location.location_id,
                group_location.group_id,
            )
            location_amounts[key] = (
                location_amounts.get(key, 0.0)
                + group_location.teu
            )

    stored_amounts: dict[tuple[str, str], float] = {}

    for block in yard_blocks.values():
        for group_id, teu in block.stored_groups.items():
            stored_amounts[(block.block_id, group_id)] = teu

    for key, stored_teu in stored_amounts.items():
        if key not in location_amounts:
            raise TerminalStateConsistencyError(
                f"YardBlock {key[0]} stores ContainerGroup "
                f"{key[1]}, but no matching group location exists."
            )

        if not _teu_close(stored_teu, location_amounts[key]):
            raise TerminalStateConsistencyError(
                f"YardBlock {key[0]} stores {stored_teu} TEU "
                f"for ContainerGroup {key[1]}, but group "
                f"location records {location_amounts[key]} TEU."
            )

    for key, location_teu in location_amounts.items():
        if key not in stored_amounts:
            raise TerminalStateConsistencyError(
                f"ContainerGroup {key[1]} has {location_teu} TEU "
                f"located in YardBlock {key[0]}, but the block "
                "does not store that group."
            )


def _validate_task_consistency(
    *,
    current_time: datetime,
    vessels: dict[str, Vessel],
    yard_blocks: dict[str, YardBlock],
    quay_cranes: dict[str, QuayCrane],
    container_groups: dict[str, ContainerGroup],
    operation_tasks: dict[str, OperationTask],
) -> None:
    active_teu_by_leg: dict[tuple[str, OperationType], float] = {}
    active_ship_side_cranes: dict[str, str] = {}

    for task in operation_tasks.values():
        if task.group_id not in container_groups:
            raise TerminalStateReferenceError(
                f"OperationTask {task.task_id} references "
                f"ContainerGroup {task.group_id}, but "
                f"{task.group_id} is not registered in "
                "TerminalState."
            )

        group = container_groups[task.group_id]

        if _teu_greater(task.planned_teu, group.total_teu):
            raise TerminalStateConsistencyError(
                f"OperationTask {task.task_id} planned TEU "
                f"{task.planned_teu} exceeds ContainerGroup "
                f"{group.group_id} total TEU {group.total_teu}."
            )

        _validate_task_flow_compatibility(task, group)
        _validate_task_location_references(
            task,
            vessels,
            yard_blocks,
        )
        _validate_task_vessel_endpoints(task, group)
        _validate_task_times(task, current_time)

        if (
            _is_committed_task(task)
            and task.task_type != OperationType.YARD_TRANSFER
        ):
            leg_key = (task.group_id, task.task_type)
            active_teu_by_leg[leg_key] = (
                active_teu_by_leg.get(leg_key, 0.0)
                + task.planned_teu
            )

        if _is_active_ship_side_task(task):
            _validate_task_crane_consistency(
                task,
                quay_cranes,
                active_ship_side_cranes,
            )

    for (group_id, operation_type), total_teu in active_teu_by_leg.items():
        group_total = container_groups[group_id].total_teu

        if _teu_greater(total_teu, group_total):
            raise TerminalStateConsistencyError(
                f"Committed {operation_type.value} tasks for "
                f"ContainerGroup {group_id} total {total_teu} "
                f"TEU, exceeding group total {group_total} TEU."
            )


def _validate_task_flow_compatibility(
    task: OperationTask,
    group: ContainerGroup,
) -> None:
    allowed_operations = {
        ContainerFlow.IMPORT: {
            OperationType.DISCHARGE,
            OperationType.GATE_OUT,
            OperationType.YARD_TRANSFER,
        },
        ContainerFlow.EXPORT: {
            OperationType.GATE_IN,
            OperationType.LOAD,
            OperationType.YARD_TRANSFER,
        },
        ContainerFlow.TRANSSHIPMENT: {
            OperationType.DISCHARGE,
            OperationType.LOAD,
            OperationType.YARD_TRANSFER,
        },
    }

    if task.task_type not in allowed_operations[group.flow]:
        raise TerminalStateConsistencyError(
            f"OperationTask {task.task_id} type "
            f"{task.task_type.value} is not compatible with "
            f"ContainerGroup {group.group_id} flow "
            f"{group.flow.value}."
        )


def _validate_task_location_references(
    task: OperationTask,
    vessels: dict[str, Vessel],
    yard_blocks: dict[str, YardBlock],
) -> None:
    for endpoint_name, location in (
        ("source", task.source),
        ("target", task.target),
    ):
        if (
            location.location_type == TaskLocationType.VESSEL
            and location.location_id not in vessels
        ):
            raise TerminalStateReferenceError(
                f"OperationTask {task.task_id} {endpoint_name} "
                f"references vessel {location.location_id}, "
                "but that vessel is not registered in "
                "TerminalState."
            )

        if (
            location.location_type == TaskLocationType.YARD_BLOCK
            and location.location_id not in yard_blocks
        ):
            raise TerminalStateReferenceError(
                f"OperationTask {task.task_id} {endpoint_name} "
                f"references yard block {location.location_id}, "
                "but that block is not registered in "
                "TerminalState."
            )


def _validate_task_vessel_endpoints(
    task: OperationTask,
    group: ContainerGroup,
) -> None:
    if (
        task.task_type == OperationType.DISCHARGE
        and task.source.location_id != group.source_vessel_id
    ):
        raise TerminalStateConsistencyError(
            f"OperationTask {task.task_id} discharge source "
            "must match the container group's source vessel."
        )

    if (
        task.task_type == OperationType.LOAD
        and task.target.location_id != group.target_vessel_id
    ):
        raise TerminalStateConsistencyError(
            f"OperationTask {task.task_id} load target must "
            "match the container group's target vessel."
        )


def _validate_task_times(
    task: OperationTask,
    current_time: datetime,
) -> None:
    if (
        task.status
        in {
            OperationTaskStatus.READY,
            OperationTaskStatus.ASSIGNED,
            OperationTaskStatus.IN_PROGRESS,
            OperationTaskStatus.BLOCKED,
            OperationTaskStatus.COMPLETED,
        }
        and task.release_time is not None
        and _datetime_is_after(
            task.release_time,
            current_time,
            message=(
                "Task release_time and TerminalState current_time "
                "must use comparable datetime values."
            ),
        )
    ):
        raise TerminalStateConsistencyError(
            f"OperationTask {task.task_id} release_time is after "
            "TerminalState current_time."
        )

    if (
        task.started_at is not None
        and _datetime_is_after(
            task.started_at,
            current_time,
            message=(
                "Task started_at and TerminalState current_time "
                "must use comparable datetime values."
            ),
        )
    ):
        raise TerminalStateConsistencyError(
            f"OperationTask {task.task_id} started_at is after "
            "TerminalState current_time."
        )

    if (
        task.completed_at is not None
        and _datetime_is_after(
            task.completed_at,
            current_time,
            message=(
                "Task completed_at and TerminalState current_time "
                "must use comparable datetime values."
            ),
        )
    ):
        raise TerminalStateConsistencyError(
            f"OperationTask {task.task_id} completed_at is after "
            "TerminalState current_time."
        )


def _validate_task_crane_consistency(
    task: OperationTask,
    quay_cranes: dict[str, QuayCrane],
    active_ship_side_cranes: dict[str, str],
) -> None:
    if task.assigned_resource_id is None:
        return

    crane_id = task.assigned_resource_id

    if crane_id not in quay_cranes:
        raise TerminalStateReferenceError(
            f"OperationTask {task.task_id} assigned resource "
            f"{crane_id} is not registered as a quay crane."
        )

    if crane_id in active_ship_side_cranes:
        raise TerminalStateConsistencyError(
            f"QuayCrane {crane_id} is assigned to multiple "
            "active ship-side tasks."
        )

    crane = quay_cranes[crane_id]

    if task.status == OperationTaskStatus.ASSIGNED:
        if crane.status != CraneStatus.ASSIGNED:
            raise TerminalStateConsistencyError(
                f"Assigned OperationTask {task.task_id} requires "
                f"QuayCrane {crane_id} to be assigned."
            )

        _validate_task_crane_vessel_match(task, crane)
        active_ship_side_cranes[crane_id] = task.task_id
        return

    if task.status == OperationTaskStatus.IN_PROGRESS:
        if crane.status != CraneStatus.OPERATING:
            raise TerminalStateConsistencyError(
                f"In-progress OperationTask {task.task_id} requires "
                f"QuayCrane {crane_id} to be operating."
            )

        _validate_task_crane_vessel_match(task, crane)
        active_ship_side_cranes[crane_id] = task.task_id
        return

    if task.status == OperationTaskStatus.BLOCKED:
        if crane.status == CraneStatus.FAILED:
            return

        if crane.status not in {
            CraneStatus.ASSIGNED,
            CraneStatus.OPERATING,
        }:
            raise TerminalStateConsistencyError(
                f"Blocked OperationTask {task.task_id} requires "
                f"QuayCrane {crane_id} to be assigned, operating, "
                "or failed."
            )

        _validate_task_crane_vessel_match(task, crane)
        active_ship_side_cranes[crane_id] = task.task_id


def _validate_task_crane_vessel_match(
    task: OperationTask,
    crane: QuayCrane,
) -> None:
    if crane.assigned_vessel_id is None:
        raise TerminalStateConsistencyError(
            f"QuayCrane {crane.crane_id} must carry an assigned "
            f"vessel for OperationTask {task.task_id}."
        )

    expected_vessel_id = (
        task.source.location_id
        if task.task_type == OperationType.DISCHARGE
        else task.target.location_id
    )

    if crane.assigned_vessel_id != expected_vessel_id:
        raise TerminalStateConsistencyError(
            f"OperationTask {task.task_id} assigned crane "
            f"{crane.crane_id} is attached to vessel "
            f"{crane.assigned_vessel_id}, not {expected_vessel_id}."
        )


def _validate_task_dependency_graph(
    operation_tasks: dict[str, OperationTask],
) -> None:
    for task in operation_tasks.values():
        for predecessor_id in task.predecessor_task_ids:
            if predecessor_id not in operation_tasks:
                raise TerminalStateReferenceError(
                    f"OperationTask {task.task_id} references "
                    f"predecessor {predecessor_id}, but "
                    f"{predecessor_id} is not registered in "
                    "TerminalState."
                )

            predecessor = operation_tasks[predecessor_id]

            if (
                task.status
                in {
                    OperationTaskStatus.READY,
                    OperationTaskStatus.ASSIGNED,
                    OperationTaskStatus.IN_PROGRESS,
                    OperationTaskStatus.BLOCKED,
                    OperationTaskStatus.COMPLETED,
                }
                and predecessor.status
                != OperationTaskStatus.COMPLETED
            ):
                raise TerminalStateConsistencyError(
                    f"OperationTask {task.task_id} requires "
                    f"predecessor {predecessor_id} to be completed."
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise TerminalStateConsistencyError(
                "OperationTask dependency graph contains a cycle."
            )

        if task_id in visited:
            return

        visiting.add(task_id)

        for predecessor_id in operation_tasks[
            task_id
        ].predecessor_task_ids:
            visit(predecessor_id)

        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in operation_tasks:
        visit(task_id)


def _get_entity_copy(
    registry: Mapping[str, Mapping[str, Any]],
    *,
    entity_id: str,
    registry_name: str,
    entity_factory: Callable[[dict[str, Any]], Any],
) -> Any:
    _validate_lookup_id(entity_id, f"{registry_name.title()} ID")

    if entity_id not in registry:
        raise TerminalStateLookupError(
            f"Unknown {registry_name} ID in TerminalState: "
            f"{entity_id}."
        )

    return entity_factory(
        _thaw_state_value(registry[entity_id])
    )


def _validate_lookup_id(
    value: str | None,
    field_name: str,
) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise TerminalStateValidationError(
            f"{field_name} cannot be empty."
        )


def _validate_event_metadata(
    event_count: int,
    last_event_id: str | None,
) -> None:
    if (
        isinstance(event_count, bool)
        or not isinstance(event_count, int)
        or event_count < 0
    ):
        raise TerminalStateValidationError(
            "TerminalState event_count must be a non-negative integer."
        )

    if event_count == 0 and last_event_id is not None:
        raise TerminalStateValidationError(
            "TerminalState last_event_id must be None when "
            "event_count is zero."
        )

    if event_count > 0:
        _validate_lookup_id(last_event_id, "Last event ID")


def _validate_schema_version(
    schema_version: int,
) -> None:
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version <= 0
    ):
        raise TerminalStateValidationError(
            "TerminalState schema_version must be a positive integer."
        )

    if schema_version != TERMINAL_STATE_SCHEMA_VERSION:
        raise TerminalStateValidationError(
            f"Unsupported TerminalState schema_version: "
            f"{schema_version}."
        )


def _datetime_from_snapshot(
    value: str,
    field_name: str,
) -> datetime:
    if not isinstance(value, str):
        raise TerminalStateValidationError(
            f"{field_name} must be an ISO datetime string."
        )

    return datetime.fromisoformat(value)


def _datetime_is_after(
    first: datetime,
    second: datetime,
    *,
    message: str,
) -> bool:
    try:
        return first > second
    except TypeError as error:
        raise TerminalStateConsistencyError(message) from error


def _is_active_task(task: OperationTask) -> bool:
    return task.status in {
        OperationTaskStatus.ASSIGNED,
        OperationTaskStatus.IN_PROGRESS,
        OperationTaskStatus.BLOCKED,
    }


def _is_committed_task(task: OperationTask) -> bool:
    return task.status in {
        OperationTaskStatus.CREATED,
        OperationTaskStatus.READY,
        OperationTaskStatus.ASSIGNED,
        OperationTaskStatus.IN_PROGRESS,
        OperationTaskStatus.BLOCKED,
    }


def _is_active_ship_side_task(task: OperationTask) -> bool:
    return (
        _is_active_task(task)
        and task.task_type
        in {
            OperationType.DISCHARGE,
            OperationType.LOAD,
        }
    )


def _teu_close(
    first: float,
    second: float,
) -> bool:
    return math.isclose(
        first,
        second,
        abs_tol=STATE_TEU_ABS_TOLERANCE,
    )


def _teu_greater(
    first: float,
    second: float,
) -> bool:
    return first > second and not _teu_close(first, second)


def _freeze_state_value(
    value: Any,
    path: str,
) -> Any:
    if isinstance(value, Enum):
        raise TerminalStateValidationError(
            f"Invalid state snapshot value at {path}: "
            "Enum is not JSON-safe. Use its value instead."
        )

    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise TerminalStateValidationError(
                f"Invalid state snapshot value at {path}: "
                "float must be finite."
            )

        return value

    if isinstance(value, Mapping):
        frozen_items = {}

        for key, item in value.items():
            if (
                not isinstance(key, str)
                or not key.strip()
            ):
                raise TerminalStateValidationError(
                    f"Invalid state snapshot value at {path}: "
                    "mapping keys must be non-empty strings."
                )

            frozen_items[key] = _freeze_state_value(
                item,
                f"{path}.{key}",
            )

        return MappingProxyType(frozen_items)

    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_state_value(
                item,
                f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        )

    raise TerminalStateValidationError(
        f"Invalid state snapshot value at {path}: "
        f"{type(value).__name__} is not JSON-safe."
    )


def _thaw_state_value(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _thaw_state_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [
            _thaw_state_value(item)
            for item in value
        ]

    return value
