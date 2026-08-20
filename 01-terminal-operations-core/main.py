from datetime import datetime
from pathlib import Path

from terminal_core.berth import Berth
from terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from terminal_core.exceptions import TerminalDomainError
from terminal_core.operation_task import (
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.quay_crane import QuayCrane
from terminal_core.terminal_event import (
    TerminalEntityType,
    TerminalEvent,
    TerminalEventType,
)
from terminal_core.terminal_state import (
    ContainerGroupLocation,
    TerminalState,
)
from terminal_core.vessel import Vessel, VesselStatus
from terminal_core.yard_block import YardBlock, YardCapability


ETA = datetime(2026, 8, 5, 8, 0)
TASK_STARTED_AT = datetime(2026, 8, 5, 10, 0)
CURRENT_TIME = datetime(2026, 8, 5, 10, 40)


def print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def build_terminal_state() -> tuple[
    TerminalState,
    Vessel,
    OperationTask,
]:
    vessel = Vessel(
        vessel_id="V001",
        length_m=250.0,
        eta=ETA,
        workload_moves=1500,
        priority=2,
        max_cranes=3,
        status=VesselStatus.OPERATING,
    )

    berth = Berth(
        berth_id="B01",
        length_m=800.0,
        min_clearance_m=20.0,
    )
    berth.place_vessel(
        vessel=vessel,
        start_position_m=100.0,
    )

    crane = QuayCrane(
        crane_id="QC01",
        position_m=140.0,
        moves_per_hour=30.0,
    )
    crane.assign_to_vessel(vessel)
    crane.start_operation()

    group = ContainerGroup(
        group_id="G001",
        container_size=ContainerSize.FORTY_FT,
        quantity=50,
        flow=ContainerFlow.IMPORT,
        load_state=ContainerLoadState.LADEN,
        source_vessel_id=vessel.vessel_id,
    )

    yard_block = YardBlock(
        block_id="Y01",
        capacity_teu=500.0,
        capabilities={
            YardCapability.GENERAL,
        },
    )
    yard_block.store_group(
        group_id=group.group_id,
        teu=40.0,
        required_capabilities=group.required_yard_capabilities,
    )

    task = OperationTask(
        task_id="T001",
        task_type=OperationType.DISCHARGE,
        group_id=group.group_id,
        planned_teu=100.0,
        source=TaskLocation(
            location_type=TaskLocationType.VESSEL,
            location_id=vessel.vessel_id,
        ),
        target=TaskLocation(
            location_type=TaskLocationType.YARD_BLOCK,
            location_id=yard_block.block_id,
        ),
        priority=2,
        release_time=datetime(2026, 8, 5, 9, 30),
    )
    task.mark_ready()
    task.assign_resource(crane.crane_id)
    task.start(TASK_STARTED_AT)
    task.record_progress(40.0)

    events = [
        TerminalEvent(
            event_id="EVT-001",
            event_type=TerminalEventType.TASK_CREATED,
            occurred_at=datetime(2026, 8, 5, 9, 50),
            entity_type=TerminalEntityType.OPERATION_TASK,
            entity_id=task.task_id,
            payload={
                "group_id": task.group_id,
                "planned_teu": task.planned_teu,
            },
        ),
        TerminalEvent(
            event_id="EVT-002",
            event_type=TerminalEventType.TASK_STARTED,
            occurred_at=TASK_STARTED_AT,
            entity_type=TerminalEntityType.OPERATION_TASK,
            entity_id=task.task_id,
            payload={
                "resource_id": crane.crane_id,
            },
        ),
        TerminalEvent(
            event_id="EVT-003",
            event_type=TerminalEventType.TASK_PROGRESS_RECORDED,
            occurred_at=datetime(2026, 8, 5, 10, 30),
            entity_type=TerminalEntityType.OPERATION_TASK,
            entity_id=task.task_id,
            payload={
                "completed_teu": task.completed_teu,
            },
        ),
    ]

    state = TerminalState.capture(
        current_time=CURRENT_TIME,
        vessels=[
            vessel,
        ],
        berths=[
            berth,
        ],
        quay_cranes=[
            crane,
        ],
        yard_blocks=[
            yard_block,
        ],
        container_groups=[
            group,
        ],
        operation_tasks=[
            task,
        ],
        group_locations=[
            ContainerGroupLocation(
                group_id=group.group_id,
                location=TaskLocation(
                    location_type=TaskLocationType.VESSEL,
                    location_id=vessel.vessel_id,
                ),
                teu=60.0,
            ),
            ContainerGroupLocation(
                group_id=group.group_id,
                location=TaskLocation(
                    location_type=TaskLocationType.YARD_BLOCK,
                    location_id=yard_block.block_id,
                ),
                teu=40.0,
            ),
        ],
        events=events,
    )

    return state, vessel, task


def show_snapshot_summary(state: TerminalState) -> None:
    print_section("1. TerminalState snapshot ozeti")

    print(f"Current time: {state.current_time.isoformat()}")
    print(f"Vessels: {state.vessel_count} -> {state.vessel_ids}")
    print(f"Berths: {state.berth_count} -> {state.berth_ids}")
    print(f"Quay cranes: {state.quay_crane_count} -> {state.quay_crane_ids}")
    print(f"Yard blocks: {state.yard_block_count} -> {state.yard_block_ids}")
    print(
        "Container groups: "
        f"{state.container_group_count} -> {state.container_group_ids}"
    )
    print(
        "Operation tasks: "
        f"{state.operation_task_count} -> {state.operation_task_ids}"
    )
    print(f"Event count: {state.event_count}")
    print(f"Last event ID: {state.last_event_id}")


def show_entity_queries(state: TerminalState) -> None:
    print_section("2. Entity kopyalarini query etmek")

    vessel = state.get_vessel("V001")
    berth = state.get_berth("B01")
    crane = state.get_quay_crane("QC01")
    group = state.get_container_group("G001")
    yard_block = state.get_yard_block("Y01")
    task = state.get_operation_task("T001")

    print(f"Vessel V001 status: {vessel.status.value}")
    print(f"Berth B01 occupancy count: {berth.occupancy_count}")
    print(
        "Crane QC01: "
        f"{crane.status.value}, assigned vessel={crane.assigned_vessel_id}"
    )
    print(f"Group G001 flow: {group.flow.value}, total TEU={group.total_teu}")
    print(f"Yard Y01 stored groups: {yard_block.stored_groups}")
    print(
        "Task T001: "
        f"{task.status.value}, completed={task.completed_teu}/"
        f"{task.planned_teu}, resource={task.assigned_resource_id}"
    )


def show_group_locations(state: TerminalState) -> None:
    print_section("3. ContainerGroupLocation ile fiziksel dagilim")

    for location in state.locations_for_group("G001"):
        print(
            f"G001 -> {location.location.location_type.value} "
            f"{location.location.location_id}: {location.teu} TEU"
        )

    print(f"G001 total located TEU: {state.group_teu_at('G001')}")
    print(
        "G001 TEU in yard blocks: "
        f"{state.group_teu_at('G001', TaskLocationType.YARD_BLOCK)}"
    )
    print(
        "G001 TEU still on vessel V001: "
        f"{state.group_teu_at('G001', TaskLocationType.VESSEL, 'V001')}"
    )


def show_task_queries(state: TerminalState) -> None:
    print_section("4. OperationTask durum sorgulari")

    print(
        "IN_PROGRESS task IDs: "
        f"{state.task_ids_by_status(OperationTaskStatus.IN_PROGRESS)}"
    )
    print(
        "COMPLETED task IDs: "
        f"{state.task_ids_by_status(OperationTaskStatus.COMPLETED)}"
    )


def show_immutability(
    state: TerminalState,
    original_vessel: Vessel,
    original_task: OperationTask,
) -> None:
    print_section("5. Snapshot immutable mi?")

    print(
        "Snapshot task progress before original mutation: "
        f"{state.get_operation_task('T001').completed_teu}"
    )

    original_task.record_progress(10.0)
    original_vessel.status = VesselStatus.DEPARTED

    print(
        "Original task progress after mutation: "
        f"{original_task.completed_teu}"
    )
    print(
        "Snapshot task progress after original mutation: "
        f"{state.get_operation_task('T001').completed_teu}"
    )
    print(
        "Original vessel status after mutation: "
        f"{original_vessel.status.value}"
    )
    print(
        "Snapshot vessel status after original mutation: "
        f"{state.get_vessel('V001').status.value}"
    )

    copied_task = state.get_operation_task("T001")
    copied_task.record_progress(5.0)

    print(
        "Copied task can change independently: "
        f"{copied_task.completed_teu}"
    )
    print(
        "Snapshot still unchanged: "
        f"{state.get_operation_task('T001').completed_teu}"
    )

    try:
        state.vessels["V001"]["status"] = "departed"
    except TypeError as error:
        print(f"Direct nested snapshot mutation rejected: {error}")


def show_serialization(state: TerminalState) -> None:
    print_section("6. Dict ve JSON round-trip")

    data = state.to_dict()
    loaded_from_dict = TerminalState.from_dict(data)

    print(f"Schema version: {data['schema_version']}")
    print(
        "Dict round-trip preserved snapshot: "
        f"{loaded_from_dict.to_dict() == data}"
    )

    file_path = Path("data") / "terminal_state_demo.json"
    state.save_to_json(file_path)
    loaded_from_json = TerminalState.load_from_json(file_path)

    print(f"JSON saved to: {file_path}")
    print(
        "JSON round-trip task status: "
        f"{loaded_from_json.get_operation_task('T001').status.value}"
    )


def show_consistency_errors(state: TerminalState) -> None:
    print_section("7. TerminalState hangi hatalari yakalar?")

    data = state.to_dict()
    data["operation_tasks"]["T001"]["group_id"] = "G999"

    try:
        TerminalState.from_dict(data)
    except TerminalDomainError as error:
        print("Missing task group reference rejected:")
        print(f"  {type(error).__name__}: {error}")

    data = state.to_dict()
    data["quay_cranes"]["QC01"]["status"] = "assigned"

    try:
        TerminalState.from_dict(data)
    except TerminalDomainError as error:
        print("In-progress task with non-operating crane rejected:")
        print(f"  {type(error).__name__}: {error}")

    data = state.to_dict()
    data["group_locations"][0]["teu"] = 70.0

    try:
        TerminalState.from_dict(data)
    except TerminalDomainError as error:
        print("Group location total above group total rejected:")
        print(f"  {type(error).__name__}: {error}")


def main() -> None:
    state, original_vessel, original_task = build_terminal_state()

    show_snapshot_summary(state)
    show_entity_queries(state)
    show_group_locations(state)
    show_task_queries(state)
    show_immutability(state, original_vessel, original_task)
    show_serialization(state)
    show_consistency_errors(state)


if __name__ == "__main__":
    main()
