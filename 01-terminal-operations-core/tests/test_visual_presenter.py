from __future__ import annotations

from datetime import datetime

from app.visual.presenter import build_terminal_visual_scene
from terminal_core.berth import Berth
from terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from terminal_core.integration import IntegrationCheckpoint, run_reference_scenario
from terminal_core.operation_task import (
    OperationTask,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.quay_crane import QuayCrane
from terminal_core.terminal import Terminal
from terminal_core.terminal_state import ContainerGroupLocation
from terminal_core.vessel import Vessel
from terminal_core.yard_block import YardBlock


def test_empty_state_scene_is_empty_and_non_mutating() -> None:
    state = Terminal(current_time=datetime(2026, 1, 1, 8, 0)).snapshot()
    before = state.to_dict()

    scene = build_terminal_visual_scene(state)

    assert scene.is_empty
    assert state.to_dict() == before


def test_partial_terminal_shows_berth_crane_and_yard() -> None:
    terminal = Terminal(current_time=datetime(2026, 1, 1, 8, 0))
    terminal.register_berth(Berth("B01", 700.0))
    terminal.register_quay_crane(QuayCrane("QC01", 100.0, 25.0))
    terminal.register_yard_block(YardBlock("Y01", 500.0))

    scene = build_terminal_visual_scene(terminal.snapshot())

    assert [berth.berth_id for berth in scene.berths] == ["B01"]
    assert [crane.crane_id for crane in scene.cranes] == ["QC01"]
    assert [yard.block_id for yard in scene.yard_blocks] == ["Y01"]


def test_waiting_and_approaching_vessels_use_anchorage_area() -> None:
    result = run_reference_scenario()
    scene = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.INBOUND_WAITING)
    )

    anchorage = {vessel.vessel_id: vessel.status for vessel in scene.anchorage_vessels}
    assert anchorage["V-IN"] == "waiting"
    assert anchorage["V-OUT"] == "approaching"
    assert not scene.vessels


def test_berthed_vessel_and_cargo_use_physical_group_locations() -> None:
    result = run_reference_scenario()
    scene = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.DISCHARGE_IN_PROGRESS)
    )

    vessel = next(vessel for vessel in scene.vessels if vessel.vessel_id == "V-IN")
    assert vessel.berth_id == "B01"
    assert [(badge.group_id, badge.teu) for badge in vessel.cargo] == [
        ("G-TRANS", 100.0)
    ]
    yard = next(block for block in scene.yard_blocks if block.block_id == "Y01")
    assert yard.stored_groups == ()


def test_completed_discharge_moves_cargo_to_yard_from_actual_inventory() -> None:
    result = run_reference_scenario()
    scene = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.DISCHARGE_COMPLETED)
    )

    yard = next(block for block in scene.yard_blocks if block.block_id == "Y01")
    assert [(badge.group_id, badge.teu) for badge in yard.stored_groups] == [
        ("G-TRANS", 100.0)
    ]
    vessel = next(vessel for vessel in scene.vessels if vessel.vessel_id == "V-IN")
    assert vessel.cargo == ()


def test_active_and_blocked_tasks_become_logical_flows() -> None:
    result = run_reference_scenario()
    in_progress = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.DISCHARGE_IN_PROGRESS)
    )
    blocked = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.CRANE_FAILED)
    )
    completed = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.DISCHARGE_COMPLETED)
    )

    flow = in_progress.task_flows[0]
    assert flow.task_id == "T-DISCHARGE"
    assert flow.source_id == "V-IN"
    assert flow.target_id == "Y01"
    assert flow.progress_pct == 40.0
    assert not flow.blocked

    blocked_flow = blocked.task_flows[0]
    assert blocked_flow.task_id == "T-DISCHARGE"
    assert blocked_flow.blocked
    assert completed.task_flows == ()


def test_failed_crane_has_explicit_failed_indicator() -> None:
    result = run_reference_scenario()
    scene = build_terminal_visual_scene(
        result.get_checkpoint(IntegrationCheckpoint.CRANE_FAILED)
    )

    crane = next(crane for crane in scene.cranes if crane.crane_id == "QC01")
    assert crane.status == "failed"
    assert crane.failed


def test_gate_locations_are_discovered_without_gate_registry() -> None:
    terminal = Terminal(current_time=datetime(2026, 1, 1, 8, 0))
    terminal.register_yard_block(YardBlock("Y01", 500.0))
    terminal.register_vessel(Vessel("V001", 210.0, terminal.current_time, 10, 2, 1))
    terminal.register_container_group(
        ContainerGroup(
            "G001",
            ContainerSize.FORTY_FT,
            50,
            ContainerFlow.EXPORT,
            ContainerLoadState.LADEN,
            target_vessel_id="V001",
        ),
        initial_locations=(
            ContainerGroupLocation(
                "G001",
                TaskLocation(TaskLocationType.GATE, "GATE-01"),
                100.0,
            ),
        ),
    )
    terminal.register_operation_task(
        OperationTask(
            "T-GATE-IN",
            OperationType.GATE_IN,
            "G001",
            100.0,
            TaskLocation(TaskLocationType.GATE, "GATE-01"),
            TaskLocation(TaskLocationType.YARD_BLOCK, "Y01"),
        )
    )

    scene = build_terminal_visual_scene(terminal.snapshot())

    assert [gate.gate_id for gate in scene.gates] == ["GATE-01"]
    assert [(badge.group_id, badge.teu) for badge in scene.gates[0].cargo] == [
        ("G001", 100.0)
    ]


def test_scene_generation_is_deterministic() -> None:
    state = run_reference_scenario().get_checkpoint(
        IntegrationCheckpoint.DISCHARGE_IN_PROGRESS
    )

    assert build_terminal_visual_scene(state) == build_terminal_visual_scene(state)

