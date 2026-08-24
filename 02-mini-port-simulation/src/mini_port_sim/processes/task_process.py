from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import simpy
from terminal_core import (
    ContainerFlow,
    ContainerGroup,
    ContainerLoadState,
    ContainerSize,
    OperationTask,
    OperationTaskStatus,
    OperationType,
    TaskLocation,
    TaskLocationType,
)
from terminal_core.exceptions import TerminalOperationError

from mini_port_sim.policies.crane_policy import CraneTaskAssignment
from mini_port_sim.policies.yard_policy import FirstFitYardPolicy, YardDecision

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    from mini_port_sim.simulation import PortSimulation


@dataclass(frozen=True)
class TaskWorkPlan:
    task_id: str
    group_id: str
    vessel_id: str
    yard_block_id: str
    workload_moves: int
    planned_teu: float


@dataclass(frozen=True)
class CargoWorkSpec:
    workload_moves: int
    container_size: ContainerSize = ContainerSize.TWENTY_FT
    load_state: ContainerLoadState = ContainerLoadState.LADEN
    is_reefer: bool = False
    is_hazardous: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.workload_moves, bool)
            or not isinstance(self.workload_moves, int)
            or self.workload_moves <= 0
        ):
            raise ValueError("Cargo work spec moves must be positive.")

        if not isinstance(self.container_size, ContainerSize):
            raise ValueError("Cargo container size must be a ContainerSize.")

        if not isinstance(self.load_state, ContainerLoadState):
            raise ValueError("Cargo load state must be a ContainerLoadState.")

        if not isinstance(self.is_reefer, bool):
            raise ValueError("Cargo reefer flag must be a boolean.")

        if not isinstance(self.is_hazardous, bool):
            raise ValueError("Cargo hazardous flag must be a boolean.")


@dataclass(frozen=True)
class PreparedDischargeTask:
    group: ContainerGroup
    task: OperationTask
    yard_decision: YardDecision
    work_plan: TaskWorkPlan


def prepare_discharge_work_for_vessel(
    simulation: "PortSimulation",
    vessel_id: str,
    yard_policy: FirstFitYardPolicy | None = None,
    cargo_specs: tuple[CargoWorkSpec, ...] | None = None,
) -> tuple[str, ...] | None:
    if vessel_id in simulation.vessel_task_ids:
        return simulation.vessel_task_ids[vessel_id]

    policy = yard_policy or FirstFitYardPolicy()
    vessel = simulation.terminal.get_vessel(vessel_id)
    specs = cargo_specs or _default_cargo_specs(
        vessel.workload_moves,
        max(
            1,
            min(vessel.max_cranes, simulation.terminal.quay_crane_count),
        ),
    )
    prepared_tasks: list[PreparedDischargeTask] = []
    planned_teu_by_block: dict[str, float] = {}
    now = simulation.now_datetime()

    for index, spec in enumerate(specs, start=1):
        group_id = f"G-{vessel_id}-{index:03d}"
        task_id = f"T-{vessel_id}-{index:03d}"
        group = ContainerGroup(
            group_id=group_id,
            container_size=spec.container_size,
            quantity=spec.workload_moves,
            flow=ContainerFlow.IMPORT,
            load_state=spec.load_state,
            is_reefer=spec.is_reefer,
            is_hazardous=spec.is_hazardous,
            source_vessel_id=vessel_id,
        )
        decision = _choose_yard_for_planned_work(
            simulation,
            policy,
            group,
            planned_teu_by_block,
        )

        if decision is None:
            simulation.record_yard_capacity_rejection()
            return None

        task = OperationTask(
            task_id=task_id,
            task_type=OperationType.DISCHARGE,
            group_id=group_id,
            planned_teu=group.total_teu,
            source=TaskLocation(
                TaskLocationType.VESSEL,
                vessel_id,
            ),
            target=TaskLocation(
                TaskLocationType.YARD_BLOCK,
                decision.block_id,
            ),
            priority=vessel.priority,
            release_time=now,
        )
        planned_teu_by_block[decision.block_id] = (
            planned_teu_by_block.get(decision.block_id, 0.0)
            + group.total_teu
        )
        prepared_tasks.append(
            PreparedDischargeTask(
                group=group,
                task=task,
                yard_decision=decision,
                work_plan=TaskWorkPlan(
                    task_id=task_id,
                    group_id=group_id,
                    vessel_id=vessel_id,
                    yard_block_id=decision.block_id,
                    workload_moves=spec.workload_moves,
                    planned_teu=group.total_teu,
                ),
            )
        )

    task_ids: list[str] = []
    for prepared in prepared_tasks:
        simulation.terminal.register_container_group(
            prepared.group,
            occurred_at=now,
        )
        simulation.terminal.reserve_yard_capacity(
            block_id=prepared.yard_decision.block_id,
            group_id=prepared.group.group_id,
            teu=prepared.group.total_teu,
            occurred_at=now,
        )
        simulation.terminal.register_operation_task(
            prepared.task,
            occurred_at=now,
        )
        simulation.terminal.mark_task_ready(
            prepared.task.task_id,
            occurred_at=now,
        )
        simulation.task_work_plans[prepared.task.task_id] = (
            prepared.work_plan
        )
        task_ids.append(prepared.task.task_id)

    simulation.vessel_task_ids[vessel_id] = tuple(task_ids)

    return simulation.vessel_task_ids[vessel_id]


def _default_cargo_specs(
    workload_moves: int,
    chunk_count: int,
) -> tuple[CargoWorkSpec, ...]:
    return tuple(
        CargoWorkSpec(workload_moves=moves)
        for moves in _split_workload_moves(workload_moves, chunk_count)
    )


def _choose_yard_for_planned_work(
    simulation: "PortSimulation",
    policy: FirstFitYardPolicy,
    group: ContainerGroup,
    planned_teu_by_block: dict[str, float],
) -> YardDecision | None:
    return policy.choose(
        simulation.terminal,
        group,
        planned_teu_by_block=planned_teu_by_block,
    )


def crane_task_process(
    simulation: "PortSimulation",
    assignment: CraneTaskAssignment,
) -> "Generator[simpy.events.Event, Any, None]":
    plan = simulation.task_work_plans[assignment.task_id]
    terminal = simulation.terminal
    now = simulation.now_datetime()

    terminal.start_task(
        assignment.task_id,
        occurred_at=now,
    )
    started_at = simulation.elapsed_minutes
    rate = _effective_crane_moves_per_hour(
        simulation,
        assignment,
    )
    simulation.register_active_task_process(
        assignment.crane_id,
        assignment.task_id,
        simulation.env.active_process,
        started_at_minutes=started_at,
        moves_per_hour=rate,
    )
    duration = _remaining_duration_minutes(
        terminal.get_operation_task(assignment.task_id),
        plan,
        rate,
    )

    try:
        if duration > 0:
            yield simulation.env.timeout(duration)

        _record_remaining_progress(simulation, plan)
        terminal.complete_task(
            assignment.task_id,
            occurred_at=simulation.now_datetime(),
        )
    except simpy.Interrupt as interrupt:
        _record_elapsed_progress(
            simulation,
            plan,
            rate,
            simulation.elapsed_minutes - started_at,
        )
        reason = str(interrupt.cause or "Quay crane failure.")
        _fail_and_unassign_interrupted_task(
            simulation,
            assignment,
            reason,
        )
    finally:
        simulation.unregister_active_task_process(assignment.crane_id)
        simulation.request_crane_dispatch()


def _split_workload_moves(
    workload_moves: int,
    chunk_count: int,
) -> tuple[int, ...]:
    if workload_moves <= 0:
        return (1,)

    base = workload_moves // chunk_count
    remainder = workload_moves % chunk_count

    return tuple(
        base + (1 if index < remainder else 0)
        for index in range(chunk_count)
        if base + (1 if index < remainder else 0) > 0
    )


def _effective_crane_moves_per_hour(
    simulation: "PortSimulation",
    assignment: CraneTaskAssignment,
) -> float:
    crane = simulation.terminal.get_quay_crane(assignment.crane_id)
    efficiency = 1.0

    if simulation.scenario is not None:
        efficiency = simulation.scenario.service.crane_efficiency(
            assignment.active_crane_count
        )

    return crane.moves_per_hour * assignment.productivity_factor * efficiency


def _remaining_duration_minutes(
    task,
    plan: TaskWorkPlan,
    moves_per_hour: float,
) -> float:
    remaining_ratio = task.remaining_teu / plan.planned_teu
    remaining_moves = plan.workload_moves * remaining_ratio

    return (remaining_moves / moves_per_hour) * 60.0


def _record_remaining_progress(
    simulation: "PortSimulation",
    plan: TaskWorkPlan,
) -> None:
    task = simulation.terminal.get_operation_task(plan.task_id)

    if task.remaining_teu <= 0:
        return

    simulation.terminal.record_task_progress(
        plan.task_id,
        task.remaining_teu,
        occurred_at=simulation.now_datetime(),
    )


def _record_elapsed_progress(
    simulation: "PortSimulation",
    plan: TaskWorkPlan,
    moves_per_hour: float,
    elapsed_minutes: float,
) -> None:
    if elapsed_minutes <= 0:
        return

    task = simulation.terminal.get_operation_task(plan.task_id)
    if task.status != OperationTaskStatus.IN_PROGRESS:
        return

    completed_moves = (moves_per_hour / 60.0) * elapsed_minutes
    progress_teu = min(
        task.remaining_teu,
        plan.planned_teu * (completed_moves / plan.workload_moves),
    )

    if progress_teu > 0:
        simulation.terminal.record_task_progress(
            plan.task_id,
            progress_teu,
            occurred_at=simulation.now_datetime(),
        )


def _fail_and_unassign_interrupted_task(
    simulation: "PortSimulation",
    assignment: CraneTaskAssignment,
    reason: str,
) -> None:
    crane = simulation.terminal.get_quay_crane(assignment.crane_id)
    task = simulation.terminal.get_operation_task(assignment.task_id)

    if crane.status.value != "failed":
        simulation.terminal.fail_quay_crane(
            assignment.crane_id,
            reason=reason,
            occurred_at=simulation.now_datetime(),
        )

    task = simulation.terminal.get_operation_task(assignment.task_id)
    if task.assigned_resource_id is None:
        return

    try:
        simulation.terminal.unassign_task_resource(
            assignment.task_id,
            occurred_at=simulation.now_datetime(),
        )
    except TerminalOperationError:
        if task.status == OperationTaskStatus.BLOCKED:
            raise
