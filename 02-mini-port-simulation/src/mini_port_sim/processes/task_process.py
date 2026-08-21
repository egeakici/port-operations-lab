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
from mini_port_sim.policies.yard_policy import FirstFitYardPolicy

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


def prepare_discharge_work_for_vessel(
    simulation: "PortSimulation",
    vessel_id: str,
    yard_policy: FirstFitYardPolicy | None = None,
) -> tuple[str, ...] | None:
    if vessel_id in simulation.vessel_task_ids:
        return simulation.vessel_task_ids[vessel_id]

    policy = yard_policy or FirstFitYardPolicy()
    vessel = simulation.terminal.get_vessel(vessel_id)
    move_chunks = _split_workload_moves(
        vessel.workload_moves,
        max(1, min(vessel.max_cranes, simulation.terminal.quay_crane_count)),
    )
    task_ids: list[str] = []

    for index, moves in enumerate(move_chunks, start=1):
        group_id = f"G-{vessel_id}-{index:03d}"
        task_id = f"T-{vessel_id}-{index:03d}"
        group = ContainerGroup(
            group_id=group_id,
            container_size=ContainerSize.TWENTY_FT,
            quantity=moves,
            flow=ContainerFlow.IMPORT,
            load_state=ContainerLoadState.LADEN,
            source_vessel_id=vessel_id,
        )
        decision = policy.choose(simulation.terminal, group)

        if decision is None:
            return None

        now = simulation.now_datetime()
        simulation.terminal.register_container_group(
            group,
            occurred_at=now,
        )
        simulation.terminal.reserve_yard_capacity(
            block_id=decision.block_id,
            group_id=group_id,
            teu=group.total_teu,
            occurred_at=now,
        )

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
        simulation.terminal.register_operation_task(
            task,
            occurred_at=now,
        )
        simulation.terminal.mark_task_ready(
            task_id,
            occurred_at=now,
        )
        simulation.task_work_plans[task_id] = TaskWorkPlan(
            task_id=task_id,
            group_id=group_id,
            vessel_id=vessel_id,
            yard_block_id=decision.block_id,
            workload_moves=moves,
            planned_teu=group.total_teu,
        )
        task_ids.append(task_id)

    simulation.vessel_task_ids[vessel_id] = tuple(task_ids)

    return simulation.vessel_task_ids[vessel_id]


def crane_task_process(
    simulation: "PortSimulation",
    assignment: CraneTaskAssignment,
) -> "Generator[simpy.events.Event, Any, None]":
    plan = simulation.task_work_plans[assignment.task_id]
    terminal = simulation.terminal
    now = simulation.now_datetime()

    terminal.assign_task_resource(
        assignment.task_id,
        assignment.crane_id,
        occurred_at=now,
    )
    terminal.start_task(
        assignment.task_id,
        occurred_at=now,
    )
    simulation.register_active_task_process(
        assignment.crane_id,
        assignment.task_id,
        simulation.env.active_process,
    )

    started_at = simulation.elapsed_minutes
    rate = _effective_crane_moves_per_hour(
        simulation,
        assignment,
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
