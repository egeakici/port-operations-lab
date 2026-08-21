from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mini_port_sim.policies.berth_policy import BerthDecision

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    import simpy

    from mini_port_sim.simulation import PortSimulation


@dataclass(frozen=True)
class VesselLifecycleRecord:
    vessel_id: str
    berth_id: str
    start_position_m: float
    berth_time_minutes: float
    operation_start_minutes: float
    operation_end_minutes: float
    departure_time_minutes: float


def vessel_service_process(
    simulation: "PortSimulation",
    decision: BerthDecision,
) -> "Generator[simpy.events.Event, Any, None]":
    if simulation.scenario is None:
        raise ValueError("Vessel service requires a scenario.")

    service = simulation.scenario.service
    vessel = simulation.terminal.get_vessel(decision.vessel_id)
    berth_time = simulation.elapsed_minutes

    if service.berthing_preparation_minutes > 0:
        yield simulation.env.timeout(service.berthing_preparation_minutes)

    operation_start = simulation.elapsed_minutes
    simulation.terminal.start_vessel_operations(
        decision.vessel_id,
        occurred_at=simulation.now_datetime(),
    )

    service_duration = service.service_duration_minutes(vessel.workload_moves)
    if service_duration > 0:
        yield simulation.env.timeout(service_duration)

    operation_end = simulation.elapsed_minutes
    simulation.terminal.complete_vessel_operations(
        decision.vessel_id,
        occurred_at=simulation.now_datetime(),
    )

    if service.departure_preparation_minutes > 0:
        yield simulation.env.timeout(service.departure_preparation_minutes)

    departure_time = simulation.elapsed_minutes
    simulation.terminal.depart_vessel(
        decision.vessel_id,
        occurred_at=simulation.now_datetime(),
    )
    simulation.completed_vessel_ids.append(decision.vessel_id)
    simulation.lifecycle_records.append(
        VesselLifecycleRecord(
            vessel_id=decision.vessel_id,
            berth_id=decision.berth_id,
            start_position_m=decision.start_position_m,
            berth_time_minutes=berth_time,
            operation_start_minutes=operation_start,
            operation_end_minutes=operation_end,
            departure_time_minutes=departure_time,
        )
    )
    simulation.request_berth_dispatch()
