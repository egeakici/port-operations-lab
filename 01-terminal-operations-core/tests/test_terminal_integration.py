from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from types import MappingProxyType

import pytest

from terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from terminal_core.exceptions import (
    OperationTaskProgressError,
    TerminalOperationError,
)
from terminal_core.integration import (
    DEFAULT_REFERENCE_START_TIME,
    REFERENCE_BACKUP_CRANE_ID,
    REFERENCE_BERTH_ID,
    REFERENCE_DISCHARGE_TASK_ID,
    REFERENCE_GROUP_ID,
    REFERENCE_INBOUND_VESSEL_ID,
    REFERENCE_LOAD_TASK_ID,
    REFERENCE_OUTBOUND_VESSEL_ID,
    REFERENCE_PARTIAL_DISCHARGE_TEU,
    REFERENCE_PRIMARY_CRANE_ID,
    REFERENCE_REMAINING_DISCHARGE_TEU,
    REFERENCE_SCENARIO_ID,
    REFERENCE_TRANS_TEU,
    REFERENCE_YARD_BLOCK_ID,
    IntegrationCheckpoint,
    IntegrationScenarioResult,
    build_reference_terminal,
    run_reference_scenario,
)
from terminal_core.operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.quay_crane import CraneStatus
from terminal_core.terminal import Terminal
from terminal_core.terminal_event import TerminalEventType
from terminal_core.terminal_state import ContainerGroupLocation
from terminal_core.vessel import VesselStatus


def test_reference_terminal_factory_builds_only_initial_registry() -> None:
    terminal = build_reference_terminal()
    state = terminal.snapshot()

    assert terminal.current_time == DEFAULT_REFERENCE_START_TIME
    assert state.vessel_count == 2
    assert state.berth_count == 1
    assert state.quay_crane_count == 2
    assert state.yard_block_count == 1
    assert state.container_group_count == 0
    assert state.operation_task_count == 0
    assert state.event_count == 0


def test_reference_scenario_runs_end_to_end() -> None:
    result = run_reference_scenario()

    assert result.scenario_id == REFERENCE_SCENARIO_ID
    assert result.started_at == DEFAULT_REFERENCE_START_TIME
    assert result.completed_at == _at(240)
    assert result.checkpoint_names == tuple(
        checkpoint.value
        for checkpoint in IntegrationCheckpoint
    )
    assert set(result.checkpoints) == set(IntegrationCheckpoint)
    assert result.event_count > 0

    final = result.final_state
    assert final.get_vessel(
        REFERENCE_INBOUND_VESSEL_ID
    ).status == VesselStatus.DEPARTED
    assert final.get_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID
    ).status == VesselStatus.DEPARTED
    assert final.get_berth(REFERENCE_BERTH_ID).occupancy_count == 0
    assert final.get_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID
    ).status == CraneStatus.AVAILABLE
    assert final.get_quay_crane(
        REFERENCE_BACKUP_CRANE_ID
    ).status == CraneStatus.AVAILABLE
    assert final.get_operation_task(
        REFERENCE_DISCHARGE_TASK_ID
    ).status == OperationTaskStatus.COMPLETED
    assert final.get_operation_task(
        REFERENCE_LOAD_TASK_ID
    ).status == OperationTaskStatus.COMPLETED

    with pytest.raises(TypeError):
        result.checkpoints[IntegrationCheckpoint.FINAL] = result.initial_state

    with pytest.raises(FrozenInstanceError):
        result.scenario_id = "changed"


def test_checkpoint_order_and_contents() -> None:
    result = run_reference_scenario()

    initial = result.get_checkpoint(IntegrationCheckpoint.INITIAL)
    assert initial.vessel_count == 2
    assert initial.berth_count == 1
    assert initial.quay_crane_count == 2
    assert initial.yard_block_count == 1

    inbound_waiting = result.get_checkpoint(
        IntegrationCheckpoint.INBOUND_WAITING
    )
    assert inbound_waiting.get_vessel(
        REFERENCE_INBOUND_VESSEL_ID
    ).status == VesselStatus.WAITING

    inbound_berthed = result.get_checkpoint(
        IntegrationCheckpoint.INBOUND_BERTHED
    )
    assert inbound_berthed.get_vessel(
        REFERENCE_INBOUND_VESSEL_ID
    ).status == VesselStatus.BERTHED
    assert inbound_berthed.get_berth(
        REFERENCE_BERTH_ID
    ).occupancy_count == 1
    assert inbound_berthed.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.VESSEL,
        REFERENCE_INBOUND_VESSEL_ID,
    ) == REFERENCE_TRANS_TEU

    discharge_progress = result.get_checkpoint(
        IntegrationCheckpoint.DISCHARGE_IN_PROGRESS
    )
    task = discharge_progress.get_operation_task(
        REFERENCE_DISCHARGE_TASK_ID
    )
    assert task.status == OperationTaskStatus.IN_PROGRESS
    assert task.completed_teu == REFERENCE_PARTIAL_DISCHARGE_TEU
    assert discharge_progress.get_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID
    ).status == CraneStatus.OPERATING

    failed = result.get_checkpoint(IntegrationCheckpoint.CRANE_FAILED)
    failed_task = failed.get_operation_task(REFERENCE_DISCHARGE_TASK_ID)
    assert failed.get_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID
    ).status == CraneStatus.FAILED
    assert failed_task.status == OperationTaskStatus.BLOCKED
    assert failed_task.completed_teu == REFERENCE_PARTIAL_DISCHARGE_TEU

    discharge_done = result.get_checkpoint(
        IntegrationCheckpoint.DISCHARGE_COMPLETED
    )
    assert discharge_done.get_operation_task(
        REFERENCE_DISCHARGE_TASK_ID
    ).status == OperationTaskStatus.COMPLETED
    assert discharge_done.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.YARD_BLOCK,
        REFERENCE_YARD_BLOCK_ID,
    ) == REFERENCE_TRANS_TEU
    assert discharge_done.get_quay_crane(
        REFERENCE_BACKUP_CRANE_ID
    ).status == CraneStatus.AVAILABLE

    inbound_departed = result.get_checkpoint(
        IntegrationCheckpoint.INBOUND_DEPARTED
    )
    assert inbound_departed.get_vessel(
        REFERENCE_INBOUND_VESSEL_ID
    ).status == VesselStatus.DEPARTED
    assert inbound_departed.get_berth(
        REFERENCE_BERTH_ID
    ).occupancy_count == 0

    outbound_berthed = result.get_checkpoint(
        IntegrationCheckpoint.OUTBOUND_BERTHED
    )
    assert outbound_berthed.get_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID
    ).status == VesselStatus.BERTHED

    load_done = result.get_checkpoint(IntegrationCheckpoint.LOAD_COMPLETED)
    assert load_done.get_operation_task(
        REFERENCE_LOAD_TASK_ID
    ).status == OperationTaskStatus.COMPLETED
    assert load_done.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.VESSEL,
        REFERENCE_OUTBOUND_VESSEL_ID,
    ) == REFERENCE_TRANS_TEU
    assert load_done.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.YARD_BLOCK,
        REFERENCE_YARD_BLOCK_ID,
    ) == 0.0


def test_physical_teu_is_conserved_at_registered_checkpoints() -> None:
    result = run_reference_scenario()
    expected = {
        IntegrationCheckpoint.INBOUND_BERTHED: (
            REFERENCE_TRANS_TEU,
            0.0,
            0.0,
        ),
        IntegrationCheckpoint.DISCHARGE_IN_PROGRESS: (
            REFERENCE_TRANS_TEU,
            0.0,
            0.0,
        ),
        IntegrationCheckpoint.CRANE_FAILED: (
            REFERENCE_TRANS_TEU,
            0.0,
            0.0,
        ),
        IntegrationCheckpoint.DISCHARGE_COMPLETED: (
            0.0,
            REFERENCE_TRANS_TEU,
            0.0,
        ),
        IntegrationCheckpoint.LOAD_COMPLETED: (
            0.0,
            0.0,
            REFERENCE_TRANS_TEU,
        ),
        IntegrationCheckpoint.FINAL: (
            0.0,
            0.0,
            REFERENCE_TRANS_TEU,
        ),
    }

    for checkpoint, amounts in expected.items():
        state = result.get_checkpoint(checkpoint)
        inbound, yard, outbound = amounts

        assert state.group_teu_at(
            REFERENCE_GROUP_ID,
            TaskLocationType.VESSEL,
            REFERENCE_INBOUND_VESSEL_ID,
        ) == inbound
        assert state.group_teu_at(
            REFERENCE_GROUP_ID,
            TaskLocationType.YARD_BLOCK,
            REFERENCE_YARD_BLOCK_ID,
        ) == yard
        assert state.group_teu_at(
            REFERENCE_GROUP_ID,
            TaskLocationType.VESSEL,
            REFERENCE_OUTBOUND_VESSEL_ID,
        ) == outbound
        assert state.group_teu_at(REFERENCE_GROUP_ID) == REFERENCE_TRANS_TEU


def test_discharge_lifecycle_and_reassignment_are_preserved() -> None:
    result = run_reference_scenario()
    progress = result.get_checkpoint(
        IntegrationCheckpoint.DISCHARGE_IN_PROGRESS
    ).get_operation_task(REFERENCE_DISCHARGE_TASK_ID)
    failed = result.get_checkpoint(
        IntegrationCheckpoint.CRANE_FAILED
    ).get_operation_task(REFERENCE_DISCHARGE_TASK_ID)
    completed = result.get_checkpoint(
        IntegrationCheckpoint.DISCHARGE_COMPLETED
    ).get_operation_task(REFERENCE_DISCHARGE_TASK_ID)

    assert progress.status == OperationTaskStatus.IN_PROGRESS
    assert progress.assigned_resource_id == REFERENCE_PRIMARY_CRANE_ID
    assert progress.started_at == _at(50)
    assert failed.status == OperationTaskStatus.BLOCKED
    assert failed.assigned_resource_id == REFERENCE_PRIMARY_CRANE_ID
    assert failed.completed_teu == REFERENCE_PARTIAL_DISCHARGE_TEU
    assert completed.status == OperationTaskStatus.COMPLETED
    assert completed.started_at == progress.started_at
    assert completed.completed_teu == REFERENCE_TRANS_TEU
    assert completed.assigned_resource_id is None

    event_types = [event.event_type for event in result.events]
    assert _contains_subsequence(
        event_types,
        [
            TerminalEventType.TASK_CREATED,
            TerminalEventType.TASK_READY,
            TerminalEventType.CRANE_ASSIGNED,
            TerminalEventType.TASK_ASSIGNED,
            TerminalEventType.VESSEL_OPERATION_STARTED,
            TerminalEventType.CRANE_OPERATION_STARTED,
            TerminalEventType.TASK_STARTED,
            TerminalEventType.TASK_PROGRESS_RECORDED,
            TerminalEventType.CRANE_FAILED,
            TerminalEventType.TASK_BLOCKED,
            TerminalEventType.TASK_UNASSIGNED,
            TerminalEventType.CRANE_ASSIGNED,
            TerminalEventType.TASK_ASSIGNED,
            TerminalEventType.CRANE_OPERATION_STARTED,
            TerminalEventType.TASK_STARTED,
            TerminalEventType.TASK_PROGRESS_RECORDED,
            TerminalEventType.YARD_RESERVATION_COMMITTED,
            TerminalEventType.YARD_GROUP_STORED,
            TerminalEventType.CRANE_RELEASED,
            TerminalEventType.TASK_COMPLETED,
        ],
    )


def test_checkpoint_immutability_after_scenario_completion() -> None:
    result = run_reference_scenario()

    failed = result.get_checkpoint(IntegrationCheckpoint.CRANE_FAILED)
    final = result.final_state

    assert failed.get_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID
    ).status == CraneStatus.FAILED
    assert failed.get_operation_task(
        REFERENCE_DISCHARGE_TASK_ID
    ).status == OperationTaskStatus.BLOCKED
    assert final.get_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID
    ).status == CraneStatus.AVAILABLE
    assert final.get_operation_task(
        REFERENCE_DISCHARGE_TASK_ID
    ).status == OperationTaskStatus.COMPLETED
    assert isinstance(result.checkpoints, MappingProxyType)


def test_invalid_early_load_ready_rolls_back() -> None:
    terminal = _terminal_at_inbound_berthed()
    before = terminal.to_dict()

    with pytest.raises(TerminalOperationError):
        terminal.mark_task_ready(
            REFERENCE_LOAD_TASK_ID,
            occurred_at=_at(40),
        )

    assert terminal.to_dict() == before
    assert terminal.get_operation_task(
        REFERENCE_LOAD_TASK_ID
    ).status == OperationTaskStatus.CREATED


def test_partial_discharge_completion_rolls_back() -> None:
    terminal = _terminal_at_partial_discharge()
    before = terminal.to_dict()

    with pytest.raises(OperationTaskProgressError):
        terminal.complete_task(
            REFERENCE_DISCHARGE_TASK_ID,
            occurred_at=_at(85),
        )

    assert terminal.to_dict() == before
    task = terminal.get_operation_task(REFERENCE_DISCHARGE_TASK_ID)
    assert task.status == OperationTaskStatus.IN_PROGRESS
    assert task.completed_teu == REFERENCE_PARTIAL_DISCHARGE_TEU
    assert terminal.get_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID
    ).status == CraneStatus.OPERATING
    assert terminal.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.VESSEL,
        REFERENCE_INBOUND_VESSEL_ID,
    ) == REFERENCE_TRANS_TEU
    assert terminal.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.YARD_BLOCK,
        REFERENCE_YARD_BLOCK_ID,
    ) == 0.0


def test_save_load_after_crane_failure_can_continue_to_same_final_state(
    tmp_path,
) -> None:
    terminal = _terminal_at_crane_failed()
    before_failed_rollback = terminal.to_dict()

    with pytest.raises(OperationTaskProgressError):
        terminal.complete_task(
            REFERENCE_DISCHARGE_TASK_ID,
            occurred_at=_at(91),
        )

    assert terminal.to_dict() == before_failed_rollback

    path = tmp_path / "reference-terminal.json"
    terminal.save_to_json(path)
    loaded = Terminal.load_from_json(path)
    _continue_from_crane_failed(loaded)

    expected = run_reference_scenario().final_state.to_dict()
    actual = loaded.snapshot().to_dict()

    assert actual == expected
    assert len({
        event.event_id
        for event in loaded.events
    }) == len(loaded.events)
    assert [event.event_id for event in loaded.events] == [
        event.event_id
        for event in run_reference_scenario().events
    ]
    assert loaded.get_operation_task(
        REFERENCE_DISCHARGE_TASK_ID
    ).started_at == _at(50)
    assert loaded.group_teu_at(
        REFERENCE_GROUP_ID,
        TaskLocationType.VESSEL,
        REFERENCE_OUTBOUND_VESSEL_ID,
    ) == REFERENCE_TRANS_TEU


def test_reference_scenario_is_deterministic() -> None:
    start_time = datetime(2026, 1, 2, 8, 0)

    first = run_reference_scenario(start_time)
    second = run_reference_scenario(start_time)

    assert first.to_dict() == second.to_dict()


def test_event_timeline_and_final_metadata() -> None:
    result = run_reference_scenario()
    event_ids = [event.event_id for event in result.events]
    event_sequences = [
        int(event_id.removeprefix("EVT-"))
        for event_id in event_ids
    ]

    assert len(set(event_ids)) == len(event_ids)
    assert event_sequences == sorted(event_sequences)
    assert event_sequences == list(range(1, len(event_sequences) + 1))
    assert all(
        earlier.occurred_at <= later.occurred_at
        for earlier, later in zip(result.events, result.events[1:])
    )
    assert all(
        event.occurred_at <= result.completed_at
        for event in result.events
    )
    assert result.final_state.event_count == len(result.events)
    assert result.final_state.last_event_id == result.events[-1].event_id
    assert result.completed_at == result.final_state.current_time

    vessel_events = [
        event
        for event in result.events
        if event.event_type
        in {
            TerminalEventType.VESSEL_ARRIVED,
            TerminalEventType.VESSEL_WAITING,
            TerminalEventType.VESSEL_BERTHED,
            TerminalEventType.VESSEL_DEPARTED,
        }
    ]
    assert all(event.correlation_id == event.entity_id for event in vessel_events)

    task_events = [
        event
        for event in result.events
        if event.event_type.name.startswith("TASK_")
    ]
    assert all(event.correlation_id == event.entity_id for event in task_events)
    assert _contains_subsequence(
        [event.event_type for event in result.events],
        [
            TerminalEventType.VESSEL_OPERATION_COMPLETED,
            TerminalEventType.BERTH_OCCUPANCY_REMOVED,
            TerminalEventType.VESSEL_DEPARTED,
        ],
    )


def test_integration_result_validation_rejects_bad_shapes() -> None:
    result = run_reference_scenario()

    with pytest.raises(ValueError):
        IntegrationScenarioResult(
            scenario_id=" ",
            started_at=result.started_at,
            completed_at=result.completed_at,
            checkpoints=result.checkpoints,
            events=result.events,
        )

    with pytest.raises(ValueError):
        IntegrationScenarioResult(
            scenario_id=REFERENCE_SCENARIO_ID,
            started_at=result.completed_at,
            completed_at=result.started_at,
            checkpoints=result.checkpoints,
            events=result.events,
        )

    duplicate_event = result.events[0]
    with pytest.raises(ValueError):
        IntegrationScenarioResult(
            scenario_id=REFERENCE_SCENARIO_ID,
            started_at=result.started_at,
            completed_at=result.completed_at,
            checkpoints=result.checkpoints,
            events=(
                duplicate_event,
                duplicate_event,
            ),
        )


def _terminal_at_inbound_berthed() -> Terminal:
    terminal = build_reference_terminal()
    terminal.arrive_vessel(
        REFERENCE_INBOUND_VESSEL_ID,
        occurred_at=_at(10),
    )
    terminal.berth_vessel(
        REFERENCE_INBOUND_VESSEL_ID,
        REFERENCE_BERTH_ID,
        50.0,
        occurred_at=_at(20),
    )
    terminal.register_container_group(
        _reference_group(),
        initial_locations=(
            ContainerGroupLocation(
                group_id=REFERENCE_GROUP_ID,
                location=_vessel_location(REFERENCE_INBOUND_VESSEL_ID),
                teu=REFERENCE_TRANS_TEU,
            ),
        ),
        occurred_at=_at(25),
    )
    terminal.register_operation_task(
        _reference_discharge_task(),
        occurred_at=_at(30),
    )
    terminal.register_operation_task(
        _reference_load_task(),
        occurred_at=_at(32),
    )
    terminal.reserve_yard_capacity(
        block_id=REFERENCE_YARD_BLOCK_ID,
        group_id=REFERENCE_GROUP_ID,
        teu=REFERENCE_TRANS_TEU,
        occurred_at=_at(35),
    )
    return terminal


def _terminal_at_partial_discharge() -> Terminal:
    terminal = _terminal_at_inbound_berthed()
    terminal.mark_task_ready(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(40),
    )
    terminal.assign_task_resource(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_PRIMARY_CRANE_ID,
        occurred_at=_at(45),
    )
    terminal.start_task(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(50),
    )
    terminal.record_task_progress(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_PARTIAL_DISCHARGE_TEU,
        occurred_at=_at(80),
    )
    return terminal


def _terminal_at_crane_failed() -> Terminal:
    terminal = _terminal_at_partial_discharge()
    terminal.fail_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID,
        reason="Reference hydraulic fault",
        occurred_at=_at(90),
    )
    return terminal


def _continue_from_crane_failed(terminal: Terminal) -> None:
    terminal.unassign_task_resource(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(95),
    )
    terminal.assign_task_resource(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_BACKUP_CRANE_ID,
        occurred_at=_at(100),
    )
    terminal.start_task(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(105),
    )
    terminal.record_task_progress(
        REFERENCE_DISCHARGE_TASK_ID,
        REFERENCE_REMAINING_DISCHARGE_TEU,
        occurred_at=_at(135),
    )
    terminal.complete_task(
        REFERENCE_DISCHARGE_TASK_ID,
        occurred_at=_at(140),
    )
    terminal.repair_quay_crane(
        REFERENCE_PRIMARY_CRANE_ID,
        occurred_at=_at(145),
    )
    terminal.complete_vessel_operations(
        REFERENCE_INBOUND_VESSEL_ID,
        occurred_at=_at(148),
    )
    terminal.depart_vessel(
        REFERENCE_INBOUND_VESSEL_ID,
        occurred_at=_at(150),
    )
    terminal.arrive_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID,
        occurred_at=_at(160),
    )
    terminal.berth_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID,
        REFERENCE_BERTH_ID,
        80.0,
        occurred_at=_at(170),
    )
    terminal.mark_task_ready(
        REFERENCE_LOAD_TASK_ID,
        occurred_at=_at(175),
    )
    terminal.assign_task_resource(
        REFERENCE_LOAD_TASK_ID,
        REFERENCE_BACKUP_CRANE_ID,
        occurred_at=_at(180),
    )
    terminal.start_task(
        REFERENCE_LOAD_TASK_ID,
        occurred_at=_at(185),
    )
    terminal.record_task_progress(
        REFERENCE_LOAD_TASK_ID,
        REFERENCE_TRANS_TEU,
        occurred_at=_at(225),
    )
    terminal.complete_task(
        REFERENCE_LOAD_TASK_ID,
        occurred_at=_at(230),
    )
    terminal.complete_vessel_operations(
        REFERENCE_OUTBOUND_VESSEL_ID,
        occurred_at=_at(235),
    )
    terminal.depart_vessel(
        REFERENCE_OUTBOUND_VESSEL_ID,
        occurred_at=_at(240),
    )


def _reference_group() -> ContainerGroup:
    return ContainerGroup(
        group_id=REFERENCE_GROUP_ID,
        container_size=ContainerSize.FORTY_FT,
        quantity=50,
        flow=ContainerFlow.TRANSSHIPMENT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id=REFERENCE_INBOUND_VESSEL_ID,
        target_vessel_id=REFERENCE_OUTBOUND_VESSEL_ID,
    )


def _reference_discharge_task() -> OperationTask:
    return OperationTask(
        task_id=REFERENCE_DISCHARGE_TASK_ID,
        task_type=OperationType.DISCHARGE,
        group_id=REFERENCE_GROUP_ID,
        planned_teu=REFERENCE_TRANS_TEU,
        source=_vessel_location(REFERENCE_INBOUND_VESSEL_ID),
        target=_yard_location(),
    )


def _reference_load_task() -> OperationTask:
    return OperationTask(
        task_id=REFERENCE_LOAD_TASK_ID,
        task_type=OperationType.LOAD,
        group_id=REFERENCE_GROUP_ID,
        planned_teu=REFERENCE_TRANS_TEU,
        source=_yard_location(),
        target=_vessel_location(REFERENCE_OUTBOUND_VESSEL_ID),
        release_time=_at(170),
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


def _at(minutes: int) -> datetime:
    return DEFAULT_REFERENCE_START_TIME + timedelta(minutes=minutes)


def _contains_subsequence(
    values: list[TerminalEventType],
    expected: list[TerminalEventType],
) -> bool:
    cursor = 0

    for value in values:
        if value == expected[cursor]:
            cursor += 1

            if cursor == len(expected):
                return True

    return False
