from __future__ import annotations

from typing import TYPE_CHECKING

from terminal_core import OperationTaskStatus

from mini_port_sim.policies.crane_policy import GreedyCranePolicy
from mini_port_sim.processes.task_process import crane_task_process
from mini_port_sim.rng import PRODUCTIVITY_STREAM

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    import simpy

    from mini_port_sim.simulation import PortSimulation


def crane_dispatcher_process(
    simulation: "PortSimulation",
    policy: GreedyCranePolicy | None = None,
) -> "Generator[simpy.events.Event, Any, None]":
    crane_policy = policy or GreedyCranePolicy()

    while True:
        yield simulation.crane_dispatch_event
        simulation.reset_crane_dispatch_event()

        while True:
            dispatched = False

            for vessel_id in simulation.crane_waiting_vessel_ids:
                task_ids = simulation.vessel_task_ids.get(vessel_id, ())
                if not task_ids:
                    continue

                if _all_tasks_completed(simulation, task_ids):
                    continue

                assignments = crane_policy.choose(
                    simulation.terminal,
                    vessel_id=vessel_id,
                    task_ids=task_ids,
                    productivity_factor=_productivity_factor(simulation),
                )

                if not assignments:
                    continue

                now = simulation.now_datetime()
                for assignment in assignments:
                    simulation.terminal.assign_task_resource(
                        assignment.task_id,
                        assignment.crane_id,
                        occurred_at=now,
                    )
                    simulation.add_process(
                        lambda sim, assignment=assignment: crane_task_process(
                            sim,
                            assignment,
                        )
                    )

                dispatched = True

            if not dispatched:
                break


def _productivity_factor(simulation: "PortSimulation") -> float:
    if simulation.scenario is None:
        return 1.0

    return simulation.scenario.disruptions.productivity_factor(
        simulation.rng.get(PRODUCTIVITY_STREAM)
    )


def _all_tasks_completed(
    simulation: "PortSimulation",
    task_ids: tuple[str, ...],
) -> bool:
    return all(
        simulation.terminal.get_operation_task(task_id).status
        == OperationTaskStatus.COMPLETED
        for task_id in task_ids
    )
