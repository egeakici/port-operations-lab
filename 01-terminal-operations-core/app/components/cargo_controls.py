from __future__ import annotations

from datetime import timedelta

import streamlit as st

from app import session_store
from app.ui_helpers import date_time_input, run_terminal_command, select_registered
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
    VALID_OPERATION_ROUTES,
)
from src.terminal_core.terminal_state import ContainerGroupLocation


def _optional_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _location_options() -> list[str]:
    return [location_type.value for location_type in TaskLocationType]


def _registered_location_input(
    label: str,
    location_type: TaskLocationType,
    *,
    key: str,
) -> str | None:
    terminal = session_store.get_sandbox_terminal()
    if location_type == TaskLocationType.VESSEL:
        return select_registered(
            label,
            terminal.vessel_ids,
            key=key,
            empty_message="No vessels are registered yet. Add a vessel in Terminal Setup.",
        )
    if location_type == TaskLocationType.YARD_BLOCK:
        return select_registered(
            label,
            terminal.yard_block_ids,
            key=key,
            empty_message="No yard blocks are registered yet. Add a yard block in Terminal Setup.",
        )
    return st.text_input(label, value="GATE-IN", key=key)


def render_cargo_and_task_forms() -> None:
    render_container_group_form()
    render_operation_task_form()
    render_yard_controls()


def render_container_group_form() -> None:
    terminal = session_store.get_sandbox_terminal()
    vessel_ids = terminal.vessel_ids
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
        selected_flow = ContainerFlow(flow)
        if selected_flow in {ContainerFlow.IMPORT, ContainerFlow.TRANSSHIPMENT}:
            with columns[2]:
                source_vessel_id = select_registered(
                    "Source vessel",
                    vessel_ids,
                    key="group_source_vessel_id",
                    empty_message="No vessels are registered yet. Add a vessel in Terminal Setup.",
                )
        else:
            source_vessel_id = None
            columns[2].text_input(
                "Source vessel",
                value="-",
                key="group_source_vessel_id_disabled",
                disabled=True,
            )

        columns = st.columns(3)
        if selected_flow in {ContainerFlow.EXPORT, ContainerFlow.TRANSSHIPMENT}:
            with columns[0]:
                target_vessel_id = select_registered(
                    "Target vessel",
                    vessel_ids,
                    key="group_target_vessel_id",
                    empty_message="No vessels are registered yet. Add a vessel in Terminal Setup.",
                )
        else:
            target_vessel_id = None
            columns[0].text_input(
                "Target vessel",
                value="-",
                key="group_target_vessel_id_disabled",
                disabled=True,
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
        missing_required_vessel = (
            (
                selected_flow in {ContainerFlow.IMPORT, ContainerFlow.TRANSSHIPMENT}
                and source_vessel_id is None
            )
            or (
                selected_flow in {ContainerFlow.EXPORT, ContainerFlow.TRANSSHIPMENT}
                and target_vessel_id is None
            )
        )
        if st.form_submit_button(
            "Add Container Group",
            use_container_width=True,
            disabled=missing_required_vessel,
        ):
            if missing_required_vessel:
                return
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
                        source_vessel_id=source_vessel_id,
                        target_vessel_id=target_vessel_id,
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
        with columns[2]:
            group_id = select_registered(
                "Group ID",
                terminal.container_group_ids,
                key="task_group_id",
                empty_message="No container groups are registered yet.",
            )
        planned_teu = columns[3].number_input(
            "Planned TEU",
            min_value=0.1,
            value=50.0,
            step=5.0,
            key="task_planned_teu",
        )

        selected_task_type = OperationType(task_type)
        source_type, target_type = VALID_OPERATION_ROUTES[selected_task_type]
        st.caption(f"Route: {source_type.value.upper()} -> {target_type.value.upper()}")
        columns = st.columns(2)
        with columns[0]:
            source_id = _registered_location_input(
                f"Source ({source_type.value})",
                source_type,
                key=f"task_source_id_{source_type.value}",
            )
        with columns[1]:
            target_id = _registered_location_input(
                f"Target ({target_type.value})",
                target_type,
                key=f"task_target_id_{target_type.value}",
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
        predecessors = columns[3].multiselect(
            "Predecessor task IDs",
            options=terminal.operation_task_ids,
            key="task_predecessors",
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
        disabled = group_id is None or source_id is None or target_id is None
        if st.form_submit_button(
            "Add Operation Task",
            use_container_width=True,
            disabled=disabled,
        ):
            if disabled:
                return
            predecessor_ids = set(predecessors)
            run_terminal_command(
                "REGISTER_OPERATION_TASK",
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "group_id": group_id,
                    "planned_teu": planned_teu,
                    "source": {
                        "location_type": source_type.value,
                        "location_id": source_id,
                    },
                    "target": {
                        "location_type": target_type.value,
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
                        source=TaskLocation(source_type, source_id),
                        target=TaskLocation(target_type, target_id),
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
            block_id = select_registered(
                "Yard block ID",
                terminal.yard_block_ids,
                key="reserve_block_id",
                empty_message="No yard blocks are registered yet. Add a yard block in Terminal Setup.",
            )
            group_id = select_registered(
                "Group ID",
                terminal.container_group_ids,
                key="reserve_group_id",
                empty_message="No container groups are registered yet.",
            )
            teu = st.number_input(
                "Reserve TEU",
                min_value=0.1,
                value=50.0,
                step=5.0,
                key="reserve_teu",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="reserve_yard_occurred_at",
            )
            disabled = block_id is None or group_id is None
            if st.form_submit_button(
                "Reserve Yard Capacity",
                use_container_width=True,
                disabled=disabled,
            ):
                if disabled:
                    return
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
            block_id = select_registered(
                "Yard block ID",
                terminal.yard_block_ids,
                key="cancel_reservation_block_id",
                empty_message="No yard blocks are registered yet. Add a yard block in Terminal Setup.",
            )
            group_id = select_registered(
                "Group ID",
                terminal.container_group_ids,
                key="cancel_reservation_group_id",
                empty_message="No container groups are registered yet.",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="cancel_reservation_occurred_at",
            )
            disabled = block_id is None or group_id is None
            if st.form_submit_button(
                "Cancel Yard Reservation",
                use_container_width=True,
                disabled=disabled,
            ):
                if disabled:
                    return
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
            block_id = select_registered(
                "Yard block ID",
                terminal.yard_block_ids,
                key="yard_status_block_id",
                empty_message="No yard blocks are registered yet. Add a yard block in Terminal Setup.",
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
            if st.form_submit_button(
                "Apply Yard Status Command",
                use_container_width=True,
                disabled=block_id is None,
            ):
                if block_id is None:
                    return
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
