from __future__ import annotations

from typing import TYPE_CHECKING

from terminal_core import CraneStatus

from mini_port_sim.rng import FAILURE_STREAM

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    import simpy

    from mini_port_sim.simulation import PortSimulation


def crane_failure_process(
    simulation: "PortSimulation",
) -> "Generator[simpy.events.Event, Any, None]":
    if simulation.scenario is None:
        raise ValueError("Crane failures require a scenario.")

    disruptions = simulation.scenario.disruptions
    if not disruptions.crane_failures_enabled:
        return

    rng = simulation.rng.get(FAILURE_STREAM)

    while True:
        delay = rng.expovariate(1.0 / disruptions.mean_time_to_failure_minutes)
        yield simulation.env.timeout(delay)

        crane_ids = tuple(simulation.terminal.quay_crane_ids)
        if not crane_ids:
            continue

        crane_id = rng.choice(crane_ids)
        crane = simulation.terminal.get_quay_crane(crane_id)
        if crane.status in {CraneStatus.FAILED, CraneStatus.MAINTENANCE}:
            continue

        active = simulation.active_task_for_crane(crane_id)
        reason = "Simulated stochastic crane failure."
        if active is not None:
            active.process.interrupt(reason)
            yield simulation.env.timeout(0)
        else:
            simulation.terminal.fail_quay_crane(
                crane_id,
                reason=reason,
                occurred_at=simulation.now_datetime(),
            )

        if simulation.terminal.get_quay_crane(crane_id).status != (
            CraneStatus.FAILED
        ):
            continue

        repair_delay = rng.expovariate(1.0 / disruptions.mean_repair_minutes)
        yield simulation.env.timeout(repair_delay)

        simulation.terminal.repair_quay_crane(
            crane_id,
            occurred_at=simulation.now_datetime(),
        )
        simulation.request_crane_dispatch()
