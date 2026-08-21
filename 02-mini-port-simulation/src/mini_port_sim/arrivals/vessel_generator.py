from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from terminal_core import Vessel

from mini_port_sim.rng import (
    ARRIVAL_STREAM,
    ETA_STREAM,
    VESSEL_STREAM,
    WORKLOAD_STREAM,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    import simpy

    from mini_port_sim.simulation import PortSimulation


@dataclass(frozen=True)
class VesselArrivalPlan:
    vessel: Vessel
    arrival_time_minutes: float

    def __post_init__(self) -> None:
        if not isinstance(self.vessel, Vessel):
            raise TypeError("Arrival plan vessel must be a Vessel.")

        if self.arrival_time_minutes < 0:
            raise ValueError("Arrival time cannot be negative.")


class VesselArrivalGenerator:
    def generate(
        self,
        simulation: "PortSimulation",
    ) -> tuple[VesselArrivalPlan, ...]:
        if simulation.scenario is None:
            raise ValueError("Arrival generation requires a scenario.")

        traffic = simulation.scenario.traffic
        arrival_rng = simulation.rng.get(ARRIVAL_STREAM)
        eta_rng = simulation.rng.get(ETA_STREAM)
        vessel_rng = simulation.rng.get(VESSEL_STREAM)
        workload_rng = simulation.rng.get(WORKLOAD_STREAM)
        elapsed_minutes = 0.0
        plans: list[VesselArrivalPlan] = []

        for index in range(traffic.vessel_count):
            if index > 0:
                elapsed_minutes += arrival_rng.expovariate(
                    1.0 / traffic.mean_interarrival_minutes
                )

            length_m = vessel_rng.uniform(
                traffic.min_vessel_length_m,
                traffic.max_vessel_length_m,
            )
            workload_moves = workload_rng.randint(
                traffic.min_workload_moves,
                traffic.max_workload_moves,
            )
            actual_elapsed_minutes = _apply_eta_variation(
                elapsed_minutes,
                simulation.scenario.disruptions.eta_delay_stddev_minutes,
                eta_rng,
            )
            arrival_time = (
                simulation.start_time
                + timedelta(minutes=actual_elapsed_minutes)
            )
            vessel = Vessel(
                vessel_id=f"V{index + 1:03d}",
                length_m=round(length_m, 2),
                eta=arrival_time,
                workload_moves=workload_moves,
                priority=2,
                max_cranes=2,
            )

            plans.append(
                VesselArrivalPlan(
                    vessel=vessel,
                    arrival_time_minutes=actual_elapsed_minutes,
                )
            )

        return tuple(
            sorted(
                plans,
                key=lambda plan: (
                    plan.arrival_time_minutes,
                    plan.vessel.vessel_id,
                ),
            )
        )


def vessel_arrival_process(
    simulation: "PortSimulation",
    plans: tuple[VesselArrivalPlan, ...] | None = None,
) -> "Generator[simpy.events.Event, Any, None]":
    arrival_plans = (
        plans
        if plans is not None
        else VesselArrivalGenerator().generate(simulation)
    )

    simulation.arrival_plans = tuple(arrival_plans)

    for plan in arrival_plans:
        delay = plan.arrival_time_minutes - simulation.elapsed_minutes

        if delay < 0:
            raise ValueError("Arrival plan times must be nondecreasing.")

        if delay > 0:
            yield simulation.env.timeout(delay)

        occurred_at = simulation.now_datetime()
        _ensure_vessel_fits_registered_berth(simulation, plan)
        simulation.terminal.register_vessel(
            plan.vessel,
            occurred_at=occurred_at,
        )
        simulation.terminal.arrive_vessel(
            plan.vessel.vessel_id,
            occurred_at=occurred_at,
        )
        simulation.add_waiting_vessel(plan.vessel.vessel_id)
        simulation.request_berth_dispatch()


def _ensure_vessel_fits_registered_berth(
    simulation: "PortSimulation",
    plan: VesselArrivalPlan,
) -> None:
    if not simulation.terminal.berth_ids:
        return

    for berth_id in simulation.terminal.berth_ids:
        berth = simulation.terminal.get_berth(berth_id)

        if plan.vessel.length_m <= berth.length_m:
            return

    raise ValueError(
        f"Vessel {plan.vessel.vessel_id} with length "
        f"{plan.vessel.length_m} m cannot fit any registered berth."
    )


def _apply_eta_variation(
    planned_elapsed_minutes: float,
    stddev_minutes: float,
    eta_rng,
) -> float:
    if stddev_minutes <= 0:
        return planned_elapsed_minutes

    return max(
        0.0,
        planned_elapsed_minutes
        + eta_rng.normalvariate(0.0, stddev_minutes),
    )
