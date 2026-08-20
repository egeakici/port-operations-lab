from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.command_service import execute_terminal_command
from app.session_store import save_checkpoint
from terminal_core.berth import Berth
from terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from terminal_core.integration import build_reference_terminal
from terminal_core.operation_task import (
    OperationTask,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.terminal import Terminal
from terminal_core.terminal_state import ContainerGroupLocation
from terminal_core.vessel import Vessel
from terminal_core.yard_block import YardBlock


def _empty_terminal() -> Terminal:
    return Terminal(current_time=datetime(2026, 1, 1, 8, 0))


def _registered_vessel() -> Vessel:
    return Vessel(
        vessel_id="V001",
        length_m=200.0,
        eta=datetime(2026, 1, 1, 8, 0),
        workload_moves=100,
        priority=2,
        max_cranes=1,
    )


def test_successful_entity_registration_record() -> None:
    terminal = _empty_terminal()
    result = execute_terminal_command(
        terminal,
        command_name="REGISTER_BERTH",
        parameters={"berth_id": "B01"},
        operation=lambda terminal: terminal.register_berth(Berth("B01", 300.0)),
        sequence=1,
    )

    assert result.record.success is True
    assert result.record.new_event_ids == ()
    assert result.terminal.berth_ids == ("B01",)


def test_duplicate_registration_failure_record() -> None:
    terminal = _empty_terminal()
    terminal.register_berth(Berth("B01", 300.0))
    before = terminal.to_dict()

    result = execute_terminal_command(
        terminal,
        command_name="REGISTER_BERTH",
        parameters={"berth_id": "B01"},
        operation=lambda terminal: terminal.register_berth(Berth("B01", 300.0)),
        sequence=2,
    )

    assert result.record.success is False
    assert result.record.error_type is not None
    assert result.terminal.to_dict() == before


def test_failure_preserves_terminal_state() -> None:
    terminal = _empty_terminal()
    before = terminal.to_dict()

    result = execute_terminal_command(
        terminal,
        command_name="ARRIVE_VESSEL",
        parameters={"vessel_id": "missing"},
        operation=lambda terminal: terminal.arrive_vessel("missing"),
        sequence=1,
    )

    assert result.record.success is False
    assert result.terminal.to_dict() == before


def test_new_event_delta_is_captured() -> None:
    terminal = _empty_terminal()
    terminal.register_vessel(_registered_vessel())

    result = execute_terminal_command(
        terminal,
        command_name="ARRIVE_VESSEL",
        parameters={"vessel_id": "V001"},
        operation=lambda terminal: terminal.arrive_vessel("V001"),
        sequence=1,
    )

    assert result.record.success is True
    assert result.record.new_event_types == ("vessel_arrived", "vessel_waiting")
    assert result.terminal.event_count == 2


def test_no_event_command_is_recorded() -> None:
    terminal = _empty_terminal()
    new_time = terminal.current_time + timedelta(hours=1)

    result = execute_terminal_command(
        terminal,
        command_name="ADVANCE_TERMINAL_TIME",
        parameters={"new_time": new_time.isoformat()},
        operation=lambda terminal: terminal.advance_time_to(new_time),
        sequence=1,
    )

    assert result.record.success is True
    assert result.record.new_event_ids == ()
    assert result.terminal.current_time == new_time


def test_vessel_arrival_through_service() -> None:
    terminal = _empty_terminal()
    terminal.register_vessel(_registered_vessel())

    result = execute_terminal_command(
        terminal,
        command_name="ARRIVE_VESSEL",
        parameters={"vessel_id": "V001"},
        operation=lambda terminal: terminal.arrive_vessel("V001"),
        sequence=1,
    )

    assert result.terminal.get_vessel("V001").status.value == "waiting"


def test_task_command_through_service() -> None:
    terminal = _empty_terminal()
    terminal.register_vessel(_registered_vessel())
    terminal.register_yard_block(YardBlock("Y01", 200.0))
    terminal.register_container_group(
        ContainerGroup(
            group_id="G001",
            container_size=ContainerSize.FORTY_FT,
            quantity=50,
            flow=ContainerFlow.EXPORT,
            load_state=ContainerLoadState.LADEN,
            target_vessel_id="V001",
        ),
        initial_locations=(
            ContainerGroupLocation(
                group_id="G001",
                location=TaskLocation(TaskLocationType.GATE, "GATE-IN"),
                teu=100.0,
            ),
        ),
    )
    terminal.register_operation_task(
        OperationTask(
            task_id="T-GATE",
            task_type=OperationType.GATE_IN,
            group_id="G001",
            planned_teu=100.0,
            source=TaskLocation(TaskLocationType.GATE, "GATE-IN"),
            target=TaskLocation(TaskLocationType.YARD_BLOCK, "Y01"),
        )
    )
    terminal.reserve_yard_capacity(block_id="Y01", group_id="G001", teu=100.0)

    result = execute_terminal_command(
        terminal,
        command_name="MARK_TASK_READY",
        parameters={"task_id": "T-GATE"},
        operation=lambda terminal: terminal.mark_task_ready("T-GATE"),
        sequence=1,
    )

    assert result.record.success is True
    assert result.terminal.get_operation_task("T-GATE").status.value == "ready"


def test_crane_failure_through_service() -> None:
    terminal = build_reference_terminal()

    result = execute_terminal_command(
        terminal,
        command_name="FAIL_QUAY_CRANE",
        parameters={"crane_id": "QC01"},
        operation=lambda terminal: terminal.fail_quay_crane("QC01"),
        sequence=1,
    )

    assert result.record.success is True
    assert result.terminal.get_quay_crane("QC01").status.value == "failed"
    assert "crane_failed" in result.record.new_event_types


def test_checkpoint_restore_data_can_rebuild_terminal() -> None:
    state = {}
    terminal = _empty_terminal()
    terminal.register_vessel(_registered_vessel())
    state["sandbox_terminal"] = terminal
    state["sandbox_name"] = "checkpoint test"
    state["sandbox_description"] = ""
    state["command_history"] = []
    state["named_checkpoints"] = {}
    checkpoint = save_checkpoint("before-arrival", state=state)

    restored = Terminal.from_dict(json.loads(checkpoint.terminal_json))

    assert restored.vessel_ids == ("V001",)
    assert restored.snapshot().to_dict() == checkpoint.state.to_dict()
