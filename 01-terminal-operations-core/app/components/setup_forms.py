from __future__ import annotations

from datetime import timedelta

import streamlit as st

from app import session_store
from app.ui_helpers import date_time_input, run_terminal_command
from terminal_core.berth import Berth
from terminal_core.quay_crane import QuayCrane
from terminal_core.vessel import Vessel
from terminal_core.yard_block import YardBlock, YardCapability


def render_setup_forms() -> None:
    terminal = session_store.get_sandbox_terminal()
    left, right = st.columns(2)

    with left:
        with st.form("add_berth_form"):
            st.subheader("Add Berth")
            berth_id = st.text_input("Berth ID", value="B01", key="berth_id")
            length_m = st.number_input(
                "Length (m)",
                min_value=1.0,
                value=700.0,
                step=10.0,
                key="berth_length_m",
            )
            min_clearance_m = st.number_input(
                "Minimum clearance (m)",
                min_value=0.0,
                value=20.0,
                step=1.0,
                key="berth_min_clearance_m",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="add_berth_occurred_at",
            )
            if st.form_submit_button("Add Berth", use_container_width=True):
                run_terminal_command(
                    "REGISTER_BERTH",
                    {
                        "berth_id": berth_id,
                        "length_m": length_m,
                        "min_clearance_m": min_clearance_m,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.register_berth(
                        Berth(
                            berth_id=berth_id,
                            length_m=length_m,
                            min_clearance_m=min_clearance_m,
                        ),
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("add_crane_form"):
            st.subheader("Add Quay Crane")
            crane_id = st.text_input("Crane ID", value="QC01", key="crane_id")
            position_m = st.number_input(
                "Position (m)",
                min_value=0.0,
                value=50.0,
                step=5.0,
                key="crane_position_m",
            )
            moves_per_hour = st.number_input(
                "Moves per hour",
                min_value=0.1,
                value=30.0,
                step=1.0,
                key="crane_moves_per_hour",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="add_crane_occurred_at",
            )
            if st.form_submit_button("Add Quay Crane", use_container_width=True):
                run_terminal_command(
                    "REGISTER_QUAY_CRANE",
                    {
                        "crane_id": crane_id,
                        "position_m": position_m,
                        "moves_per_hour": moves_per_hour,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.register_quay_crane(
                        QuayCrane(
                            crane_id=crane_id,
                            position_m=position_m,
                            moves_per_hour=moves_per_hour,
                        ),
                        occurred_at=occurred_at,
                    ),
                )

    with right:
        with st.form("add_vessel_form"):
            st.subheader("Add Vessel")
            vessel_id = st.text_input("Vessel ID", value="V001", key="vessel_id")
            length_m = st.number_input(
                "Vessel length (m)",
                min_value=1.0,
                value=250.0,
                step=10.0,
                key="vessel_length_m",
            )
            eta = date_time_input(
                "ETA",
                default=terminal.current_time + timedelta(minutes=30),
                key="vessel_eta",
            )
            workload_moves = st.number_input(
                "Workload moves",
                min_value=0,
                value=800,
                step=50,
                key="vessel_workload_moves",
            )
            priority = st.select_slider(
                "Priority",
                options=[1, 2, 3],
                value=2,
                key="vessel_priority",
            )
            max_cranes = st.number_input(
                "Maximum cranes",
                min_value=1,
                value=2,
                step=1,
                key="vessel_max_cranes",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="add_vessel_occurred_at",
            )
            if st.form_submit_button("Add Vessel", use_container_width=True):
                run_terminal_command(
                    "REGISTER_VESSEL",
                    {
                        "vessel_id": vessel_id,
                        "length_m": length_m,
                        "eta": eta.isoformat(),
                        "workload_moves": workload_moves,
                        "priority": priority,
                        "max_cranes": max_cranes,
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.register_vessel(
                        Vessel(
                            vessel_id=vessel_id,
                            length_m=length_m,
                            eta=eta,
                            workload_moves=int(workload_moves),
                            priority=int(priority),
                            max_cranes=int(max_cranes),
                        ),
                        occurred_at=occurred_at,
                    ),
                )

        with st.form("add_yard_block_form"):
            st.subheader("Add Yard Block")
            block_id = st.text_input("Yard Block ID", value="Y01", key="yard_block_id")
            capacity_teu = st.number_input(
                "Capacity (TEU)",
                min_value=1.0,
                value=500.0,
                step=25.0,
                key="yard_capacity_teu",
            )
            capabilities = st.multiselect(
                "Capabilities",
                options=[capability.value for capability in YardCapability],
                default=[YardCapability.GENERAL.value],
                key="yard_capabilities",
            )
            occurred_at = date_time_input(
                "Occurred at",
                default=terminal.current_time,
                key="add_yard_occurred_at",
            )
            if st.form_submit_button("Add Yard Block", use_container_width=True):
                selected_capabilities = {
                    YardCapability(value)
                    for value in capabilities
                }
                run_terminal_command(
                    "REGISTER_YARD_BLOCK",
                    {
                        "block_id": block_id,
                        "capacity_teu": capacity_teu,
                        "capabilities": sorted(capabilities),
                        "occurred_at": occurred_at.isoformat(),
                    },
                    lambda terminal: terminal.register_yard_block(
                        YardBlock(
                            block_id=block_id,
                            capacity_teu=capacity_teu,
                            capabilities=selected_capabilities,
                        ),
                        occurred_at=occurred_at,
                    ),
                )

