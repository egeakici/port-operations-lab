from __future__ import annotations

from datetime import datetime

import simpy
from terminal_core import (
    Berth,
    CraneStatus,
    OperationTaskStatus,
    QuayCrane,
    Terminal,
    TerminalEventType,
    Vessel,
    VesselStatus,
    YardBlock,
)

from mini_port_sim import (
    DisruptionConfig,
    PortSimulation,
    ScenarioConfig,
    ServiceConfig,
    TrafficConfig,
    VesselArrivalPlan,
    berth_dispatcher_process,
    vessel_arrival_process,
)


START_TIME = datetime(2026, 8, 20, 8, 0)


def create_terminal(
    *,
    crane_count: int = 2,
    crane_moves_per_hour: float = 60.0,
    yard_capacity_teu: float = 500.0,
) -> Terminal:
    terminal = Terminal(current_time=START_TIME)
    terminal.register_berth(
        Berth(berth_id="B01", length_m=700.0),
        occurred_at=START_TIME,
    )
    for index in range(crane_count):
        terminal.register_quay_crane(
            QuayCrane(
                crane_id=f"QC{index + 1:02d}",
                position_m=100.0 + (index * 40.0),
                moves_per_hour=crane_moves_per_hour,
            ),
            occurred_at=START_TIME,
        )
    terminal.register_yard_block(
        YardBlock(
            block_id="Y01",
            capacity_teu=yard_capacity_teu,
        ),
        occurred_at=START_TIME,
    )

    return terminal


def create_vessel(
    *,
    vessel_id: str = "V001",
    workload_moves: int = 120,
    max_cranes: int = 2,
) -> Vessel:
    return Vessel(
        vessel_id=vessel_id,
        length_m=250.0,
        eta=START_TIME,
        workload_moves=workload_moves,
        priority=2,
        max_cranes=max_cranes,
    )


def create_scenario(
    *,
    crane_failures_enabled: bool = False,
    productivity_min_factor: float = 1.0,
    productivity_max_factor: float = 1.0,
) -> ScenarioConfig:
    return ScenarioConfig(
        scenario_id="crane-yard",
        duration_hours=4,
        seed=42,
        traffic=TrafficConfig(vessel_count=1),
        service=ServiceConfig(
            berthing_preparation_minutes=0.0,
            service_minutes_per_move=1.0,
            departure_preparation_minutes=0.0,
            two_crane_efficiency=1.0,
        ),
        disruptions=DisruptionConfig(
            crane_failures_enabled=crane_failures_enabled,
            productivity_min_factor=productivity_min_factor,
            productivity_max_factor=productivity_max_factor,
            mean_time_to_failure_minutes=5.0,
            mean_repair_minutes=10.0,
        ),
    )


def run_single_arrival(
    simulation: PortSimulation,
    vessel: Vessel,
    *,
    until_minutes: float,
) -> None:
    plans = (
        VesselArrivalPlan(
            vessel=vessel,
            arrival_time_minutes=0.0,
        ),
    )
    simulation.add_process(berth_dispatcher_process)
    simulation.add_process(lambda sim: vessel_arrival_process(sim, plans))
    simulation.run(until_minutes=until_minutes)


def test_vessel_service_uses_parallel_quay_crane_capacity() -> None:
    terminal = create_terminal(crane_count=2, crane_moves_per_hour=60.0)
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=create_scenario(),
    )

    run_single_arrival(
        simulation,
        create_vessel(workload_moves=120, max_cranes=2),
        until_minutes=60.0,
    )

    assert terminal.get_vessel("V001").status == VesselStatus.DEPARTED
    assert terminal.get_quay_crane("QC01").status == CraneStatus.AVAILABLE
    assert terminal.get_quay_crane("QC02").status == CraneStatus.AVAILABLE
    assert terminal.operation_task_count == 2
    assert all(
        terminal.get_operation_task(task_id).status
        == OperationTaskStatus.COMPLETED
        for task_id in terminal.operation_task_ids
    )
    assert terminal.group_teu_at("G-V001-001") == 60.0
    assert terminal.group_teu_at("G-V001-002") == 60.0
    assert simulation.lifecycle_records[0].operation_end_minutes == 60.0


def test_yard_capacity_blocks_discharge_work_before_crane_assignment() -> None:
    terminal = create_terminal(
        crane_count=1,
        crane_moves_per_hour=60.0,
        yard_capacity_teu=50.0,
    )
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=create_scenario(),
    )

    run_single_arrival(
        simulation,
        create_vessel(workload_moves=100, max_cranes=1),
        until_minutes=20.0,
    )

    assert terminal.get_vessel("V001").status == VesselStatus.BERTHED
    assert terminal.operation_task_count == 0
    assert terminal.get_quay_crane("QC01").status == CraneStatus.AVAILABLE
    assert simulation.completed_vessel_ids == []


def test_crane_failure_interrupts_work_and_repaired_crane_finishes_remaining() -> None:
    terminal = create_terminal(crane_count=1, crane_moves_per_hour=60.0)
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=create_scenario(),
    )

    def fail_once(sim: PortSimulation):
        yield sim.env.timeout(30.0)
        active = sim.active_task_for_crane("QC01")
        assert active is not None
        active.process.interrupt("Deterministic test failure.")
        yield sim.env.timeout(0)
        assert terminal.get_quay_crane("QC01").status == CraneStatus.FAILED
        yield sim.env.timeout(30.0)
        terminal.repair_quay_crane(
            "QC01",
            occurred_at=sim.now_datetime(),
        )
        sim.request_crane_dispatch()

    simulation.add_process(fail_once)
    run_single_arrival(
        simulation,
        create_vessel(workload_moves=120, max_cranes=1),
        until_minutes=150.0,
    )

    assert terminal.get_vessel("V001").status == VesselStatus.DEPARTED
    task = terminal.get_operation_task("T-V001-001")
    assert task.status == OperationTaskStatus.COMPLETED
    assert task.completed_teu == 120.0
    assert terminal.get_quay_crane("QC01").status == CraneStatus.AVAILABLE
    assert simulation.lifecycle_records[0].operation_end_minutes == 150.0

    event_types = [event.event_type for event in terminal.events]
    assert TerminalEventType.CRANE_FAILED in event_types
    assert TerminalEventType.CRANE_REPAIRED in event_types
    assert TerminalEventType.TASK_BLOCKED in event_types
    assert event_types.count(TerminalEventType.TASK_COMPLETED) == 1


def test_start_basic_operations_registers_failure_process_when_enabled() -> None:
    terminal = create_terminal(crane_count=1)
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=create_scenario(crane_failures_enabled=True),
    )

    simulation.start_basic_operations()

    assert simulation.process_count == 3
