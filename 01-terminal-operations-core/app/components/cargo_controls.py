from __future__ import annotations

from datetime import timedelta

import streamlit as st

from app import session_store
from app.ui_helpers import date_time_input, run_terminal_command, select_or_text
from src.terminal_core.container_group import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
)
from src.terminal_core.operation_task import (
    OperationTask,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from src.terminal_core.terminal_state import ContainerGroupLocation


def _optional_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _location_options() -> list[str]:
    return [location_type.value for location_type in TaskLocationType]


def render_cargo_and_task_forms() -> None:
    render_container_group_form()
    render_operation_task_form()
    render_yard_controls()


def render_container_group_form() -> None:
    terminal = session_store.get_sandbox_terminal()
    with st.form("add_container_group_form"):
        st.subheader("Add Container Group")
        columns = st.columns(3)
        group_id = columns[0].text_input(
            "Group ID",
            value="G001",
            key="group_id",
        )
        container_size = columns[1].selectbox(
            "Container size",
            options=[size.value for size in ContainerSize],
            key="container_size",
        )
        quantity = columns[2].number_input(
            "Quantity",
            min_value=1,
            value=50,
            step=1,
            key="container_quantity",
        )

        columns = st.columns(3)
        flow = columns[0].selectbox(
            "Flow",
            options=[item.value for item in ContainerFlow],
            key="container_flow",
        )
        load_state = columns[1].selectbox(
            "Load state",
            options=[item.value for item in ContainerLoadState],
            key="container_load_state",
        )
        source_vessel_id = columns[2].text_input(
            "Source vessel ID",
            value="",
            key="group_source_vessel_id",
            help="Required for import and transshipment cargo.",
        )

        columns = st.columns(3)
        target_vessel_id = columns[0].text_input(
            "Target vessel ID",
            value="",
            key="group_target_vessel_id",
            help="Required for export and transshipment cargo.",
        )
        is_reefer = columns[1].checkbox("Reefer", key="group_is_reefer")
        is_hazardous = columns[2].checkbox("Hazardous", key="group_is_hazardous")

        use_initial_location = st.checkbox(
            "Create initial physical location",
            value=False,
            key="group_use_initial_location",
            help="Use this for export gate inventory or cargo already on a vessel/yard.",
        )
        location_type = st.selectbox(
            "Initial location type",
            options=_location_options(),
            index=2,
            key="group_initial_location_type",
            disabled=not use_initial_location,
        )
        columns = st.columns(2)
        location_id = columns[0].text_input(
            "Initial location ID",
            value="GATE-IN",
            key="group_initial_location_id",
            disabled=not use_initial_location,
        )
        initial_teu = columns[1].number_input(
            "Initial TEU",
            min_value=0.1,
            value=100.0,
            step=5.0,
            key="group_initial_teu",
            disabled=not use_initial_location,
        )
        occurred_at = date_time_input(
            "Occurred at",
            default=terminal.current_time,
            key="add_group_occurred_at",
        )
        if st.form_submit_button("Add Container Group", use_container_width=True):
            def operation(terminal):
                initial_locations = ()
                if use_initial_location:
                    initial_locations = (
                        ContainerGroupLocation(
                            group_id=group_id,
                            location=TaskLocation(
                                TaskLocationType(location_type),
                                location_id,
                            ),
                            teu=initial_teu,
                        ),
                    )
                return terminal.register_container_group(
                    ContainerGroup(
                        group_id=group_id,
                        container_size=ContainerSize(container_size),
                        quantity=int(quantity),
                        flow=ContainerFlow(flow),
                        load_state=ContainerLoadState(load_state),
                        is_reefer=is_reefer,
                        is_hazardous=is_hazardous,
                        source_vessel_id=_optional_text(source_vessel_id),
                        target_vessel_id=_optional_text(target_vessel_id),
                    ),
                    initial_locations=initial_locations,
                    occurred_at=occurred_at,
                )

            run_terminal_command(
                "REGISTER_CONTAINER_GROUP",
                {
                    "group_id": group_id,
                    "container_size": container_size,
                    "quantity": quantity,
                    "flow": flow,
                    "load_state": load_state,
                    "source_vessel_id": source_vessel_id,
                    "target_vessel_id": target_vessel_id,
                    "initial_location": (
                        None
                        if not use_initial_location
                        else {
                            "location_type": location_type,
                            "location_id": location_id,
                            "teu": initial_teu,
                        }
                    ),
                    "occurred_at": occurred_at.isoformat(),
                },
                operation,
            )


def render_operation_task_form() -> None:
    terminal = session_store.get_sandbox_terminal()
    with st.form("add_operation_task_form"):
        st.subheader("Add Operation Task")
        columns = st.columns(4)
        task_id = columns[0].text_input("Task ID", value="T001", key="task_id")
        task_type = columns[1].selectbox(
            "Operation type",
            options=[item.value for item in OperationType],
            key="task_type",
        )
        group_id = columns[2].selectbox(
            "Group ID",
            options=terminal.container_group_ids or ("G001",),
            key="task_group_id",
        )
        planned_teu = columns[3].number_input(
            "Planned TEU",
            min_value=0.1,
            value=100.0,
            step=5.0,
            key="task_planned_teu",
        )

        columns = st.columns(4)
        source_type = columns[0].selectbox(
            "Source type",
            options=_location_options(),
            key="task_source_type",
        )
        source_id = columns[1].text_input(
            "Source ID",
            value="V001",
            key="task_source_id",
        )
        target_type = columns[2].selectbox(
            "Target type",
            options=_location_options(),
            index=1,
            key="task_target_type",
        )
        target_id = columns[3].text_input(
            "Target ID",
            value="Y01",
            key="task_target_id",
        )

        columns = st.columns(4)
        priority = columns[0].select_slider(
            "Task priority",
            options=[1, 2, 3],
            value=2,
            key="task_priority",
        )
        use_release = columns[1].checkbox("Set release time", key="task_use_release")
        use_due = columns[2].checkbox("Set due time", key="task_use_due")
        predecessors = columns[3].text_input(
            "Predecessor task IDs",
            value="",
            key="task_predecessors",
            help="Comma-separated task IDs.",
        )
        release_time = date_time_input(
            "Release time",
            default=terminal.current_time,
            key="task_release_time",
            help="Only used when Set release time is checked.",
        )
        due_time = date_time_input(
            "Due time",
            default=terminal.current_time + timedelta(hours=2),
            key="task_due_time",
            help="Only used when Set due time is checked.",
        )
        occurred_at = date_time_input(
            "Occurred at",
            default=terminal.current_time,
            key="add_task_occurred_at",
        )
        if st.form_submit_button("Add Operation Task", use_container_width=True):
            predecessor_ids = {
                item.strip()
                for item in predecessors.split(",")
                if item.strip()
            }
            run_terminal_command(
                "REGISTER_OPERATION_TASK",
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "group_id": group_id,
                    "planned_teu": planned_teu,
                    "source": {
                        "location_type": source_type,
                        "location_id": source_id,
                    },
                    "target": {
                        "location_type": target_type,
                        "location_id": target_id,
                    },
                    "priority": priority,
                    "predecessors": sorted(predecessor_ids),
                    "occurred_at": occurred_at.isoformat(),
                },
                lambda terminal: terminal.register_operation_task(
                    OperationTask(
                        task_id=task_id,
                        task_type=OperationType(task_type),
                        group_id=group_id,
                        planned_teu=planned_teu,
                        source=TaskLocation(TaskLocationType(source_type), source_id),
                        target=TaskLocation(TaskLocationType(target_type), target_id),
                        priority=int(priority),
                        release_time=release_time if use_release else None,
                        due_time=due_time if use_due else None,
                        predecessor_task_ids=predecessor_ids,
                    ),
                    occurred_at=occurred_at,
                ),
            )


def render_yard_controls() -> None:
    terminal = session_store.get_sandbox_terminal()
    st.subheader("Yard Commands")
    left, middle, right = st.columns(3)
    with left:
        with st.form("reserve_yard_form"):
            block_id = select_or_text(
                "Yard block ID",
                terminal.yard_block_ids,
                key="reserve_block_id",
            )
            group_id = select_or_text(
                "Group ID",
                terminal.container_group_ids,
                key="reserve_group_id",
            )
            teu = st.number_input(
                "Reserve TEU",
                min_value=0.1,
                value=100.0,
                step=5.0,
                key="reserve_teu",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="reserve_yard_occurred_at",
            )
            if st.form_submit_button("Reserve Yard Capacity", use_container_width=True):
                run_terminal_command(
                    "RESERVE_YARD_CAPACITY",
                    {
                        "block_id": block_id,
                        "group_id": group_id,
                        "teu": teu,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.reserve_yard_capacity(
                        block_id=block_id,
                        group_id=group_id,
                        teu=teu,
                        occurred_at=occurred_at,
                    ),
                )

    with middle:
        with st.form("cancel_yard_reservation_form"):
            block_id = select_or_text(
                "Yard block ID",
                terminal.yard_block_ids,
                key="cancel_reservation_block_id",
            )
            group_id = select_or_text(
                "Group ID",
                terminal.container_group_ids,
                key="cancel_reservation_group_id",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="cancel_reservation_occurred_at",
            )
            if st.form_submit_button("Cancel Yard Reservation", use_container_width=True):
                run_terminal_command(
                    "CANCEL_YARD_RESERVATION",
                    {
                        "block_id": block_id,
                        "group_id": group_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.cancel_yard_reservation(
                        block_id=block_id,
                        group_id=group_id,
                        occurred_at=occurred_at,
                    ),
                )

    with right:
        with st.form("yard_status_form"):
            block_id = select_or_text(
                "Yard block ID",
                terminal.yard_block_ids,
                key="yard_status_block_id",
            )
            action = st.selectbox(
                "Yard status command",
                options=(
                    "close",
                    "reopen",
                    "start_maintenance",
                    "finish_maintenance",
                ),
                key="yard_status_action",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="yard_status_occurred_at",
            )
            if st.form_submit_button("Apply Yard Status Command", use_container_width=True):
                operations = {
                    "close": lambda terminal: terminal.close_yard_block(
                        block_id,
                        occurred_at=occurred_at,
                    ),
                    "reopen": lambda terminal: terminal.reopen_yard_block(
                        block_id,
                        occurred_at=occurred_at,
                    ),
                    "start_maintenance": lambda terminal: terminal.start_yard_block_maintenance(
                        block_id,
                        occurred_at=occurred_at,
                    ),
                    "finish_maintenance": lambda terminal: terminal.finish_yard_block_maintenance(
                        block_id,
                        occurred_at=occurred_at,
                    ),
                }
                run_terminal_command(
                    f"YARD_{action.upper()}",
                    {
                        "block_id": block_id,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    operations[action],
                )
