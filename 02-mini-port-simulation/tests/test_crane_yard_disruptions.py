from __future__ import annotations

from datetime import datetime

import simpy
from terminal_core import (
    Berth,
    ContainerLoadState,
    ContainerSize,
    CraneStatus,
    OperationTaskStatus,
    QuayCrane,
    Terminal,
    TerminalEventType,
    Vessel,
    VesselStatus,
    YardBlock,
    YardCapability,
)

from mini_port_sim import (
    CargoWorkSpec,
    DisruptionConfig,
    PortSimulation,
    ScenarioConfig,
    ServiceConfig,
    TrafficConfig,
    VesselArrivalPlan,
    berth_dispatcher_process,
    crane_dispatcher_process,
    crane_failure_process,
    prepare_discharge_work_for_vessel,
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
            planned_arrival_time_minutes=0.0,
        ),
    )
    simulation.add_process(berth_dispatcher_process)
    simulation.add_process(crane_dispatcher_process)
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


def test_partial_yard_capacity_leaves_no_partial_discharge_state() -> None:
    terminal = create_terminal(
        crane_count=2,
        crane_moves_per_hour=60.0,
        yard_capacity_teu=100.0,
    )
    vessel = create_vessel(workload_moves=120, max_cranes=2)
    terminal.register_vessel(vessel, occurred_at=START_TIME)
    terminal.arrive_vessel("V001", occurred_at=START_TIME)
    terminal.berth_vessel("V001", "B01", 0.0, occurred_at=START_TIME)
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=create_scenario(),
    )

    task_ids = prepare_discharge_work_for_vessel(simulation, "V001")

    assert task_ids is None
    assert terminal.operation_task_count == 0
    assert terminal.container_group_count == 0
    assert terminal.get_yard_block("Y01").reserved_teu == 0.0


def test_reefer_cargo_requires_reefer_yard_capability() -> None:
    terminal = create_terminal(
        crane_count=1,
        crane_moves_per_hour=60.0,
        yard_capacity_teu=100.0,
    )
    vessel = create_vessel(workload_moves=20, max_cranes=1)
    terminal.register_vessel(vessel, occurred_at=START_TIME)
    terminal.arrive_vessel("V001", occurred_at=START_TIME)
    terminal.berth_vessel("V001", "B01", 0.0, occurred_at=START_TIME)
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=create_scenario(),
    )
    reefer_specs = (
        CargoWorkSpec(
            workload_moves=20,
            is_reefer=True,
        ),
    )

    assert (
        prepare_discharge_work_for_vessel(
            simulation,
            "V001",
            cargo_specs=reefer_specs,
        )
        is None
    )
    assert terminal.operation_task_count == 0

    terminal.register_yard_block(
        YardBlock(
            block_id="Y02",
            capacity_teu=100.0,
            capabilities={
                YardCapability.GENERAL,
                YardCapability.REEFER_POWER,
            },
        ),
        occurred_at=START_TIME,
    )

    task_ids = prepare_discharge_work_for_vessel(
        simulation,
        "V001",
        cargo_specs=reefer_specs,
    )

    assert task_ids == ("T-V001-001",)
    assert terminal.get_operation_task("T-V001-001").status == (
        OperationTaskStatus.READY
    )
    assert terminal.get_yard_block("Y02").reserved_teu == 20.0


def test_forty_foot_cargo_keeps_moves_and_teu_separate() -> None:
    terminal = create_terminal(
        crane_count=1,
        crane_moves_per_hour=60.0,
        yard_capacity_teu=250.0,
    )
    vessel = create_vessel(workload_moves=100, max_cranes=1)
    terminal.register_vessel(vessel, occurred_at=START_TIME)
    terminal.arrive_vessel("V001", occurred_at=START_TIME)
    terminal.berth_vessel("V001", "B01", 0.0, occurred_at=START_TIME)
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=create_scenario(),
    )

    task_ids = prepare_discharge_work_for_vessel(
        simulation,
        "V001",
        cargo_specs=(
            CargoWorkSpec(
                workload_moves=100,
                container_size=ContainerSize.FORTY_FT,
            ),
        ),
    )

    assert task_ids == ("T-V001-001",)
    assert simulation.task_work_plans["T-V001-001"].workload_moves == 100
    assert terminal.get_operation_task("T-V001-001").planned_teu == 200.0
    assert terminal.get_yard_block("Y01").reserved_teu == 200.0


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

    assert simulation.process_count == 4


def test_two_vessels_contending_for_one_crane_leave_second_task_ready() -> None:
    terminal = create_terminal(
        crane_count=1,
        crane_moves_per_hour=60.0,
        yard_capacity_teu=500.0,
    )
    scenario = create_scenario()
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=scenario,
    )
    plans = (
        VesselArrivalPlan(
            vessel=create_vessel(
                vessel_id="V001",
                workload_moves=120,
                max_cranes=1,
            ),
            planned_arrival_time_minutes=0.0,
        ),
        VesselArrivalPlan(
            vessel=create_vessel(
                vessel_id="V002",
                workload_moves=120,
                max_cranes=1,
            ),
            planned_arrival_time_minutes=0.0,
        ),
    )

    simulation.add_process(berth_dispatcher_process)
    simulation.add_process(crane_dispatcher_process)
    simulation.add_process(lambda sim: vessel_arrival_process(sim, plans))
    simulation.run(until_minutes=1.0)

    assert terminal.get_operation_task("T-V001-001").status == (
        OperationTaskStatus.IN_PROGRESS
    )
    assert terminal.get_operation_task("T-V002-001").status == (
        OperationTaskStatus.READY
    )
    assert terminal.get_quay_crane("QC01").assigned_vessel_id == "V001"


def test_productivity_factor_changes_service_duration() -> None:
    fast_terminal = create_terminal(
        crane_count=1,
        crane_moves_per_hour=60.0,
        yard_capacity_teu=100.0,
    )
    fast_simulation = PortSimulation.from_scenario(
        terminal=fast_terminal,
        start_time=START_TIME,
        scenario=create_scenario(
            productivity_min_factor=1.0,
            productivity_max_factor=1.0,
        ),
    )
    run_single_arrival(
        fast_simulation,
        create_vessel(workload_moves=60, max_cranes=1),
        until_minutes=60.0,
    )

    slow_terminal = create_terminal(
        crane_count=1,
        crane_moves_per_hour=60.0,
        yard_capacity_teu=100.0,
    )
    slow_simulation = PortSimulation.from_scenario(
        terminal=slow_terminal,
        start_time=START_TIME,
        scenario=create_scenario(
            productivity_min_factor=0.5,
            productivity_max_factor=0.5,
        ),
    )
    run_single_arrival(
        slow_simulation,
        create_vessel(workload_moves=60, max_cranes=1),
        until_minutes=120.0,
    )

    assert fast_simulation.lifecycle_records[0].operation_end_minutes == 60.0
    assert slow_simulation.lifecycle_records[0].operation_end_minutes == 120.0


def test_two_crane_failures_can_overlap() -> None:
    terminal = create_terminal(crane_count=2)
    scenario = create_scenario(crane_failures_enabled=True)
    simulation = PortSimulation.from_scenario(
        terminal=terminal,
        start_time=START_TIME,
        scenario=scenario,
    )
    simulation.random_streams._streams["failure:QC01"] = SequenceRng(
        [10.0, 100.0]
    )
    simulation.random_streams._streams["failure:QC02"] = SequenceRng(
        [20.0, 100.0]
    )

    simulation.add_process(lambda sim: crane_failure_process(sim, "QC01"))
    simulation.add_process(lambda sim: crane_failure_process(sim, "QC02"))
    simulation.run(until_minutes=50.0)

    assert terminal.get_quay_crane("QC01").status == CraneStatus.FAILED
    assert terminal.get_quay_crane("QC02").status == CraneStatus.FAILED


class SequenceRng:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def expovariate(self, _rate: float) -> float:
        return self.values.pop(0)
