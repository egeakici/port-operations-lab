from __future__ import annotations

from typing import TYPE_CHECKING

from mini_port_sim.policies.berth_policy import FCFSLeftmostPolicy
from mini_port_sim.processes.vessel_process import vessel_service_process

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    import simpy

    from mini_port_sim.policies.berth_policy import BerthDecision
    from mini_port_sim.simulation import PortSimulation


def berth_dispatcher_process(
    simulation: "PortSimulation",
    policy: FCFSLeftmostPolicy | None = None,
) -> "Generator[simpy.events.Event, Any, None]":
    berth_policy = policy or FCFSLeftmostPolicy()

    while True:
        yield simulation.berth_dispatch_event
        simulation.reset_berth_dispatch_event()

        while True:
            decision = berth_policy.choose(
                simulation.terminal,
                simulation.waiting_vessel_ids,
            )

            if decision is None:
                break

            simulation.terminal.berth_vessel(
                decision.vessel_id,
                decision.berth_id,
                decision.start_position_m,
                occurred_at=simulation.now_datetime(),
            )
            simulation.remove_waiting_vessel(decision.vessel_id)
            simulation.add_process(
                _service_factory(decision)
            )


def _service_factory(
    decision: "BerthDecision",
):
    def start_service(simulation: "PortSimulation"):
        return vessel_service_process(
            simulation,
            decision,
        )

    return start_service
