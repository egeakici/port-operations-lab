from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from terminal_core.berth import Berth
from terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from terminal_core.exceptions import (
    TerminalConsistencyError,
    TerminalDuplicateEntityError,
    TerminalInventoryError,
    TerminalLookupError,
    TerminalOperationError,
    TerminalSerializationError,
    TerminalStateConsistencyError,
    TerminalTimeError,
    YardOperationError,
)
from terminal_core.operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.quay_crane import CraneStatus, QuayCrane
from terminal_core.terminal import (
    TERMINAL_SCHEMA_VERSION,
    Terminal,
)
from terminal_core.terminal_event import (
    TerminalEntityType,
    TerminalEvent,
    TerminalEventType,
)
from terminal_core.terminal_state import ContainerGroupLocation
from terminal_core.vessel import Vessel, VesselStatus
from terminal_core.yard_block import YardBlock, YardCapability


CURRENT_TIME = datetime(2026, 8, 5, 9, 0)
ETA = datetime(2026, 8, 5, 8, 0)


def vessel_location(vessel_id: str = "V001") -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.VESSEL,
        location_id=vessel_id,
    )


def yard_location(block_id: str = "Y01") -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.YARD_BLOCK,
        location_id=block_id,
    )


def gate_location(gate_id: str = "GATE-1") -> TaskLocation:
    return TaskLocation(
        location_type=TaskLocationType.GATE,
        location_id=gate_id,
    )


def create_vessel(
    vessel_id: str = "V001",
    status: VesselStatus = VesselStatus.APPROACHING,
    max_cranes: int = 2,
) -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=250.0,
        eta=ETA,
        workload_moves=120,
        priority=2,
        max_cranes=max_cranes,
        status=status,
    )


def create_berth(berth_id: str = "B01") -> Berth:
    return Berth(
        berth_id=berth_id,
        length_m=700.0,
        min_clearance_m=20.0,
    )


def create_crane(crane_id: str = "QC01") -> QuayCrane:
    return QuayCrane(
        crane_id=crane_id,
        position_m=100.0,
        moves_per_hour=30.0,
    )


def create_yard_block(
    block_id: str = "Y01",
    capabilities: set[YardCapability] | None = None,
) -> YardBlock:
    return YardBlock(
        block_id=block_id,
        capacity_teu=500.0,
        capabilities=capabilities
        or {
            YardCapability.GENERAL,
        },
    )


def create_import_group(
    group_id: str = "G001",
    source_vessel_id: str = "V001",
    quantity: int = 50,
) -> ContainerGroup:
    return ContainerGroup(
        group_id=group_id,
        container_size=ContainerSize.FORTY_FT,
        quantity=quantity,
        flow=ContainerFlow.IMPORT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id=source_vessel_id,
    )


def create_export_group(
    group_id: str = "G002",
    target_vessel_id: str = "V001",
    quantity: int = 50,
) -> ContainerGroup:
    return ContainerGroup(
        group_id=group_id,
        container_size=ContainerSize.FORTY_FT,
        quantity=quantity,
        flow=ContainerFlow.EXPORT,
        load_state=ContainerLoadState.LADEN,
        target_vessel_id=target_vessel_id,
    )


def create_discharge_task(
    task_id: str = "T001",
    group_id: str = "G001",
    planned_teu: float = 100.0,
) -> OperationTask:
    return OperationTask(
        task_id=task_id,
        task_type=OperationType.DISCHARGE,
        group_id=group_id,
        planned_teu=planned_teu,
        source=vessel_location(),
        target=yard_location(),
    )


def create_gate_in_task(
    task_id: str = "T-GI",
    group_id: str = "G002",
    planned_teu: float = 100.0,
) -> OperationTask:
    return OperationTask(
        task_id=task_id,
        task_type=OperationType.GATE_IN,
        group_id=group_id,
        planned_teu=planned_teu,
        source=gate_location(),
        target=yard_location(),
    )


def create_load_task(
    task_id: str = "T-LOAD",
    group_id: str = "G002",
    planned_teu: float = 100.0,
) -> OperationTask:
    return OperationTask(
        task_id=task_id,
        task_type=OperationType.LOAD,
        group_id=group_id,
        planned_teu=planned_teu,
        source=yard_location(),
        target=vessel_location(),
    )


def create_yard_transfer_task(
    task_id: str = "T-YT",
    group_id: str = "G001",
    planned_teu: float = 60.0,
) -> OperationTask:
    return OperationTask(
        task_id=task_id,
        task_type=OperationType.YARD_TRANSFER,
        group_id=group_id,
        planned_teu=planned_teu,
        source=yard_location("Y01"),
        target=yard_location("Y02"),
    )


def create_gate_out_task(
    task_id: str = "T-GO",
    group_id: str = "G001",
    planned_teu: float = 100.0,
) -> OperationTask:
    return OperationTask(
        task_id=task_id,
        task_type=OperationType.GATE_OUT,
        group_id=group_id,
        planned_teu=planned_teu,
        source=yard_location(),
        target=gate_location(),
    )


def create_berthed_vessel_and_berth(
    vessel_id: str = "V001",
) -> tuple[Vessel, Berth]:
    vessel = create_vessel(
        vessel_id=vessel_id,
        status=VesselStatus.BERTHED,
    )
    berth = create_berth()
    berth.place_vessel(vessel, 50.0)
    return vessel, berth


def create_block_storing_group(
    group: ContainerGroup,
    *,
    block_id: str = "Y01",
    teu: float = 100.0,
) -> YardBlock:
    block = create_yard_block(block_id)
    block.store_group(
        group.group_id,
        teu,
        group.required_yard_capabilities,
    )
    return block


def create_block_reserving_group(
    group: ContainerGroup,
    *,
    block_id: str = "Y02",
    teu: float = 60.0,
) -> YardBlock:
    block = create_yard_block(block_id)
    block.reserve_capacity(
        group.group_id,
        teu,
        group.required_yard_capabilities,
    )
    return block


def create_ready_terminal() -> Terminal:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())
    terminal.arrive_vessel("V001")
    terminal.register_berth(create_berth())
    terminal.berth_vessel("V001", "B01", 50.0)
    terminal.register_quay_crane(create_crane())
    terminal.register_yard_block(create_yard_block())
    terminal.register_container_group(create_import_group())
    terminal.reserve_yard_capacity(
        block_id="Y01",
        group_id="G001",
        teu=100.0,
    )
    terminal.register_operation_task(create_discharge_task())
    return terminal


def test_empty_terminal_snapshot_and_schema_version() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)

    assert terminal.to_dict()["schema_version"] == TERMINAL_SCHEMA_VERSION
    assert terminal.snapshot().event_count == 0
    assert terminal.vessel_ids == ()


def test_registration_clones_inputs_and_getters_return_clones() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    vessel = create_vessel()

    terminal.register_vessel(vessel)
    vessel.transition_to(VesselStatus.WAITING)
    fetched = terminal.get_vessel("V001")
    fetched.transition_to(VesselStatus.WAITING)

    assert terminal.get_vessel("V001").status == VesselStatus.APPROACHING


def test_duplicate_registration_is_rejected() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())

    with pytest.raises(TerminalDuplicateEntityError):
        terminal.register_vessel(create_vessel())


def test_group_registration_sets_initial_import_location_and_event() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())

    event = terminal.register_container_group(create_import_group())

    assert event.event_id == "EVT-000001"
    assert event.event_type == TerminalEventType.CONTAINER_GROUP_REGISTERED
    assert terminal.group_teu_at(
        "G001",
        TaskLocationType.VESSEL,
        "V001",
    ) == 100.0


def test_unknown_group_location_lookup_is_rejected() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)

    with pytest.raises(TerminalLookupError):
        terminal.locations_for_group("G999")


def test_time_can_advance_but_not_move_backwards() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    later = CURRENT_TIME + timedelta(minutes=5)

    terminal.advance_time_to(later)

    assert terminal.current_time == later

    with pytest.raises(TerminalTimeError):
        terminal.advance_time_to(CURRENT_TIME)


def test_command_time_rejects_naive_aware_mismatch() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)

    with pytest.raises(TerminalTimeError):
        terminal.register_vessel(
            create_vessel(),
            occurred_at=datetime(2026, 8, 5, 9, 1, tzinfo=timezone.utc),
        )


def test_event_sequence_and_causation_are_deterministic() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())

    arrived, waiting = terminal.arrive_vessel("V001")

    assert (arrived.event_id, waiting.event_id) == (
        "EVT-000001",
        "EVT-000002",
    )
    assert waiting.causation_id == arrived.event_id
    assert waiting.correlation_id == "V001"


def test_vessel_can_be_berthed_and_berth_uses_canonical_vessel() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())
    terminal.arrive_vessel("V001")
    terminal.register_berth(create_berth())

    terminal.berth_vessel("V001", "B01", 50.0)

    assert terminal.get_vessel("V001").status == VesselStatus.BERTHED
    occupancy = terminal._berths["B01"].occupancies[0]
    assert occupancy.vessel is terminal._vessels["V001"]


def test_berthed_vessel_operations_can_start_without_task_detail() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())
    terminal.arrive_vessel("V001")
    terminal.register_berth(create_berth())
    terminal.berth_vessel("V001", "B01", 50.0)

    event = terminal.start_vessel_operations("V001")

    assert terminal.get_vessel("V001").status == VesselStatus.OPERATING
    assert event.event_type == TerminalEventType.VESSEL_OPERATION_STARTED
    assert event.correlation_id == "V001"


def test_discharge_task_happy_path_updates_state_and_events() -> None:
    terminal = create_ready_terminal()

    terminal.mark_task_ready("T001")
    terminal.assign_task_resource("T001", "QC01")
    terminal.start_task("T001")
    terminal.record_task_progress("T001", 100.0)
    events = terminal.complete_task("T001")

    assert terminal.get_operation_task("T001").status == (
        OperationTaskStatus.COMPLETED
    )
    assert terminal.get_quay_crane("QC01").status == CraneStatus.AVAILABLE
    assert terminal.group_teu_at(
        "G001",
        TaskLocationType.VESSEL,
        "V001",
    ) == 0.0
    assert terminal.group_teu_at(
        "G001",
        TaskLocationType.YARD_BLOCK,
        "Y01",
    ) == 100.0
    assert events[-1].event_type == TerminalEventType.TASK_COMPLETED
    assert terminal.snapshot().operation_task_count == 1


def test_task_ready_requires_exact_yard_reservation() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())
    terminal.register_yard_block(create_yard_block())
    terminal.register_container_group(create_import_group())
    terminal.register_operation_task(create_discharge_task())

    with pytest.raises(TerminalOperationError):
        terminal.mark_task_ready("T001")

    assert terminal.get_operation_task("T001").status == (
        OperationTaskStatus.CREATED
    )


def test_crane_failure_blocks_in_progress_ship_side_task() -> None:
    terminal = create_ready_terminal()
    terminal.mark_task_ready("T001")
    terminal.assign_task_resource("T001", "QC01")
    terminal.start_task("T001")

    events = terminal.fail_quay_crane("QC01", reason="Hydraulic leak")

    assert [event.event_type for event in events] == [
        TerminalEventType.CRANE_FAILED,
        TerminalEventType.TASK_BLOCKED,
    ]
    assert terminal.get_quay_crane("QC01").status == CraneStatus.FAILED
    assert terminal.get_operation_task("T001").status == (
        OperationTaskStatus.BLOCKED
    )


def test_blocked_task_cannot_resume_with_failed_crane() -> None:
    terminal = create_ready_terminal()
    terminal.mark_task_ready("T001")
    terminal.assign_task_resource("T001", "QC01")
    terminal.start_task("T001")
    terminal.fail_quay_crane("QC01")

    with pytest.raises(TerminalOperationError):
        terminal.resume_task("T001")


def test_assigned_task_loses_resource_when_crane_fails() -> None:
    terminal = create_ready_terminal()
    terminal.mark_task_ready("T001")
    terminal.assign_task_resource("T001", "QC01")

    terminal.fail_quay_crane("QC01")

    assert terminal.get_operation_task("T001").status == (
        OperationTaskStatus.READY
    )
    assert terminal.get_operation_task("T001").assigned_resource_id is None


def test_gate_in_task_can_commit_yard_inventory() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())
    terminal.register_yard_block(create_yard_block())
    terminal.register_container_group(
        create_export_group(),
        initial_locations=(
            ContainerGroupLocation(
                group_id="G002",
                location=gate_location(),
                teu=100.0,
            ),
        ),
    )
    terminal.reserve_yard_capacity(
        block_id="Y01",
        group_id="G002",
        teu=100.0,
    )
    terminal.register_operation_task(create_gate_in_task())

    terminal.mark_task_ready("T-GI")
    terminal.assign_task_resource("T-GI", "TRUCK-1")
    terminal.start_task("T-GI")
    terminal.record_task_progress("T-GI", 100.0)
    terminal.complete_task("T-GI")

    assert terminal.group_teu_at(
        "G002",
        TaskLocationType.YARD_BLOCK,
        "Y01",
    ) == 100.0
    assert terminal.get_operation_task("T-GI").status == (
        OperationTaskStatus.COMPLETED
    )


def test_gate_in_requires_physical_gate_inventory() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())
    terminal.register_yard_block(create_yard_block())
    terminal.register_container_group(create_export_group())
    terminal.reserve_yard_capacity(
        block_id="Y01",
        group_id="G002",
        teu=100.0,
    )
    terminal.register_operation_task(create_gate_in_task())

    with pytest.raises(TerminalInventoryError):
        terminal.mark_task_ready("T-GI")


def test_load_task_completion_moves_yard_inventory_to_vessel() -> None:
    vessel, berth = create_berthed_vessel_and_berth()
    group = create_export_group()
    source_block = create_block_storing_group(group)
    terminal = Terminal.create(
        current_time=CURRENT_TIME,
        vessels=(vessel,),
        berths=(berth,),
        quay_cranes=(create_crane(),),
        yard_blocks=(source_block,),
        container_groups=(group,),
        operation_tasks=(create_load_task(),),
        group_locations=(
            ContainerGroupLocation(
                group_id="G002",
                location=yard_location(),
                teu=100.0,
            ),
        ),
    )

    terminal.mark_task_ready("T-LOAD")
    terminal.assign_task_resource("T-LOAD", "QC01")
    terminal.start_task("T-LOAD")
    terminal.record_task_progress("T-LOAD", 100.0)
    terminal.complete_task("T-LOAD")

    assert terminal.group_teu_at(
        "G002",
        TaskLocationType.YARD_BLOCK,
        "Y01",
    ) == 0.0
    assert terminal.group_teu_at(
        "G002",
        TaskLocationType.VESSEL,
        "V001",
    ) == 100.0
    assert terminal.get_quay_crane("QC01").status == CraneStatus.AVAILABLE


def test_yard_transfer_completion_moves_inventory_between_blocks() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    source_block = create_block_storing_group(group, teu=60.0)
    target_block = create_block_reserving_group(group, teu=60.0)
    terminal = Terminal.create(
        current_time=CURRENT_TIME,
        vessels=(vessel,),
        yard_blocks=(source_block, target_block),
        container_groups=(group,),
        operation_tasks=(create_yard_transfer_task(),),
        group_locations=(
            ContainerGroupLocation(
                group_id="G001",
                location=yard_location("Y01"),
                teu=60.0,
            ),
        ),
    )

    terminal.mark_task_ready("T-YT")
    terminal.assign_task_resource("T-YT", "YT-RESOURCE-1")
    terminal.start_task("T-YT")
    terminal.record_task_progress("T-YT", 60.0)
    terminal.complete_task("T-YT")

    assert terminal.group_teu_at(
        "G001",
        TaskLocationType.YARD_BLOCK,
        "Y01",
    ) == 0.0
    assert terminal.group_teu_at(
        "G001",
        TaskLocationType.YARD_BLOCK,
        "Y02",
    ) == 60.0


def test_gate_out_completion_moves_yard_inventory_to_gate() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    source_block = create_block_storing_group(group)
    terminal = Terminal.create(
        current_time=CURRENT_TIME,
        vessels=(vessel,),
        yard_blocks=(source_block,),
        container_groups=(group,),
        operation_tasks=(create_gate_out_task(),),
        group_locations=(
            ContainerGroupLocation(
                group_id="G001",
                location=yard_location(),
                teu=100.0,
            ),
        ),
    )

    terminal.mark_task_ready("T-GO")
    terminal.assign_task_resource("T-GO", "TRUCK-OUT-1")
    terminal.start_task("T-GO")
    terminal.record_task_progress("T-GO", 100.0)
    terminal.complete_task("T-GO")

    assert terminal.group_teu_at(
        "G001",
        TaskLocationType.YARD_BLOCK,
        "Y01",
    ) == 0.0
    assert terminal.group_teu_at(
        "G001",
        TaskLocationType.GATE,
        "GATE-1",
    ) == 100.0


def test_load_completion_rolls_back_when_source_block_is_closed() -> None:
    vessel, berth = create_berthed_vessel_and_berth()
    group = create_export_group()
    source_block = create_block_storing_group(group)
    terminal = Terminal.create(
        current_time=CURRENT_TIME,
        vessels=(vessel,),
        berths=(berth,),
        quay_cranes=(create_crane(),),
        yard_blocks=(source_block,),
        container_groups=(group,),
        operation_tasks=(create_load_task(),),
        group_locations=(
            ContainerGroupLocation(
                group_id="G002",
                location=yard_location(),
                teu=100.0,
            ),
        ),
    )
    terminal.mark_task_ready("T-LOAD")
    terminal.assign_task_resource("T-LOAD", "QC01")
    terminal.start_task("T-LOAD")
    terminal.record_task_progress("T-LOAD", 100.0)
    terminal.close_yard_block("Y01")
    before = terminal.to_dict()

    with pytest.raises(YardOperationError):
        terminal.complete_task("T-LOAD")

    assert terminal.to_dict() == before


def test_yard_transfer_completion_rolls_back_when_target_commit_fails() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    source_block = create_block_storing_group(group, teu=60.0)
    target_block = create_block_reserving_group(group, teu=60.0)
    terminal = Terminal.create(
        current_time=CURRENT_TIME,
        vessels=(vessel,),
        yard_blocks=(source_block, target_block),
        container_groups=(group,),
        operation_tasks=(create_yard_transfer_task(),),
        group_locations=(
            ContainerGroupLocation(
                group_id="G001",
                location=yard_location("Y01"),
                teu=60.0,
            ),
        ),
    )
    terminal.mark_task_ready("T-YT")
    terminal.assign_task_resource("T-YT", "YT-RESOURCE-1")
    terminal.start_task("T-YT")
    terminal.record_task_progress("T-YT", 60.0)
    terminal.close_yard_block("Y02")
    before = terminal.to_dict()

    with pytest.raises(YardOperationError):
        terminal.complete_task("T-YT")

    assert terminal.to_dict() == before


def test_gate_out_completion_rolls_back_when_source_release_fails() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    source_block = create_block_storing_group(group)
    terminal = Terminal.create(
        current_time=CURRENT_TIME,
        vessels=(vessel,),
        yard_blocks=(source_block,),
        container_groups=(group,),
        operation_tasks=(create_gate_out_task(),),
        group_locations=(
            ContainerGroupLocation(
                group_id="G001",
                location=yard_location(),
                teu=100.0,
            ),
        ),
    )
    terminal.mark_task_ready("T-GO")
    terminal.assign_task_resource("T-GO", "TRUCK-OUT-1")
    terminal.start_task("T-GO")
    terminal.record_task_progress("T-GO", 100.0)
    terminal.close_yard_block("Y01")
    before = terminal.to_dict()

    with pytest.raises(YardOperationError):
        terminal.complete_task("T-GO")

    assert terminal.to_dict() == before


def test_cancel_task_releases_assigned_crane() -> None:
    terminal = create_ready_terminal()
    terminal.mark_task_ready("T001")
    terminal.assign_task_resource("T001", "QC01")

    events = terminal.cancel_task("T001")

    assert events[-1].event_type == TerminalEventType.TASK_CANCELLED
    assert terminal.get_quay_crane("QC01").status == CraneStatus.AVAILABLE
    assert terminal.get_operation_task("T001").assigned_resource_id is None


def test_yard_block_and_crane_status_commands_emit_events() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_yard_block(create_yard_block())
    terminal.register_quay_crane(create_crane())

    closed = terminal.close_yard_block("Y01")
    reopened = terminal.reopen_yard_block("Y01")
    maintenance = terminal.start_quay_crane_maintenance("QC01")
    finished = terminal.finish_quay_crane_maintenance("QC01")

    assert closed.event_type == TerminalEventType.YARD_BLOCK_CLOSED
    assert reopened.event_type == TerminalEventType.YARD_BLOCK_REOPENED
    assert maintenance.event_type == TerminalEventType.CRANE_MAINTENANCE_STARTED
    assert finished.event_type == TerminalEventType.CRANE_MAINTENANCE_COMPLETED


def test_move_quay_crane_returns_travelled_distance() -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_quay_crane(create_crane())

    distance = terminal.move_quay_crane("QC01", 135.5)

    assert distance == 35.5
    assert terminal.get_quay_crane("QC01").position_m == 135.5


def test_json_round_trip_preserves_terminal(tmp_path) -> None:
    terminal = create_ready_terminal()
    terminal.mark_task_ready("T001")
    path = tmp_path / "terminal.json"

    terminal.save_to_json(path)
    restored = Terminal.load_from_json(path)

    assert restored.to_dict() == terminal.to_dict()
    assert restored.get_operation_task("T001").status == (
        OperationTaskStatus.READY
    )


def test_next_event_sequence_is_restored_after_existing_events() -> None:
    event = TerminalEvent(
        event_id="EVT-000010",
        event_type=TerminalEventType.VESSEL_ARRIVED,
        occurred_at=CURRENT_TIME,
        entity_type=TerminalEntityType.VESSEL,
        entity_id="V001",
        correlation_id="V001",
    )
    terminal = Terminal.create(
        current_time=CURRENT_TIME,
        vessels=(
            create_vessel(status=VesselStatus.WAITING),
        ),
        events=(event,),
    )

    terminal.register_container_group(create_import_group())

    assert terminal.events[-1].event_id == "EVT-000011"


def test_invalid_schema_version_is_rejected() -> None:
    data = Terminal(current_time=CURRENT_TIME).to_dict()
    data["schema_version"] = True

    with pytest.raises(TerminalSerializationError):
        Terminal.from_dict(data)


def test_restore_rejects_registry_key_entity_id_mismatch() -> None:
    data = Terminal(current_time=CURRENT_TIME).to_dict()
    data["vessels"] = {
        "V001": create_vessel("V999").to_dict(),
    }

    with pytest.raises(TerminalSerializationError):
        Terminal.from_dict(data)


def test_event_log_restore_rejects_future_events() -> None:
    event = TerminalEvent(
        event_id="EVT-000001",
        event_type=TerminalEventType.VESSEL_ARRIVED,
        occurred_at=CURRENT_TIME + timedelta(minutes=1),
        entity_type=TerminalEntityType.VESSEL,
        entity_id="V001",
        correlation_id="V001",
    )

    with pytest.raises(TerminalTimeError):
        Terminal.create(
            current_time=CURRENT_TIME,
            vessels=(
                create_vessel(status=VesselStatus.WAITING),
            ),
            events=(event,),
        )


def test_initial_group_locations_reject_duplicates() -> None:
    vessel = create_vessel(status=VesselStatus.WAITING)
    group = create_import_group()
    location = ContainerGroupLocation(
        group_id="G001",
        location=vessel_location(),
        teu=50.0,
    )

    with pytest.raises(TerminalConsistencyError):
        Terminal.create(
            current_time=CURRENT_TIME,
            vessels=(vessel,),
            container_groups=(group,),
            group_locations=(location, location),
        )


def test_atomic_rollback_restores_state_when_validation_fails(
    monkeypatch,
) -> None:
    terminal = Terminal(current_time=CURRENT_TIME)
    terminal.register_vessel(create_vessel())
    before = terminal.to_dict()

    def broken_snapshot():
        raise TerminalStateConsistencyError("boom")

    monkeypatch.setattr(terminal, "snapshot", broken_snapshot)

    with pytest.raises(TerminalStateConsistencyError):
        terminal.register_container_group(create_import_group())

    assert terminal.to_dict() == before


def test_vessel_departure_requires_no_source_cargo() -> None:
    terminal = create_ready_terminal()
    terminal.mark_task_ready("T001")
    terminal.assign_task_resource("T001", "QC01")
    terminal.start_task("T001")
    terminal.record_task_progress("T001", 100.0)
    terminal.complete_task("T001")

    completed = terminal.complete_vessel_operations("V001")
    events = terminal.depart_vessel("V001")

    assert completed.event_type == TerminalEventType.VESSEL_OPERATION_COMPLETED
    assert [event.event_type for event in events] == [
        TerminalEventType.BERTH_OCCUPANCY_REMOVED,
        TerminalEventType.VESSEL_DEPARTED,
    ]
    assert events[1].causation_id == events[0].event_id
    assert events[-1].event_type == TerminalEventType.VESSEL_DEPARTED
    assert terminal.get_vessel("V001").status == VesselStatus.DEPARTED


def test_vessel_departure_rejects_remaining_import_cargo() -> None:
    terminal = create_ready_terminal()

    with pytest.raises(TerminalOperationError):
        terminal.depart_vessel("V001")
