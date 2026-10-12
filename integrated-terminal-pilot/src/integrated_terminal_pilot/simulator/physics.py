"""Physical rate laws of the integrated terminal (integration specification §5, §11).

Pure functions of current state. Each law is the frozen Step 1 mechanism; the
coefficients come from the scenario physics block (their approval status is
recorded in ``docs/step4_physics_approval_audit.md``). Standard and bottleneck
families use the same functions with different declared parameters.

Coupling A (D09)   crane_rate = nominal x eff(n_assigned) x productivity
Coupling B (D10)   distance = |x_v - transfer_x_b| + transfer_y_b
                   cycle    = 2 d / speed + handover
                   transport_rate = units_per_crane x 60 / cycle
Coupling C (D11)   g(rho), effective capacity = mu_b x g(rho_b), landside share,
                   proportional sharing within each flow class
Combined (§5.4)    ship-side demand = min(crane_rate, transport_rate); landside demand = mu_b

``n_assigned`` is the number of cranes *assigned* to the vessel (spec §5.1: "with
n_v cranes currently assigned to v"), recomputed whenever it changes. Assigned
cranes that are not working a batch contribute no capacity at all; the factor
only scales the rate of cranes that do work.
"""

from __future__ import annotations

from typing import Iterable

from mini_port_sim.scenario import ServiceConfig


def crane_rate_moves_per_hour(nominal_moves_per_hour: float, assigned_crane_count: int,
                              service: ServiceConfig, productivity_factor: float) -> float:
    """Coupling A: Project 02 ``ServiceConfig.crane_efficiency`` reused directly (D09)."""
    return nominal_moves_per_hour * service.crane_efficiency(assigned_crane_count) * productivity_factor


def quay_transfer_x_m(berth_position_m: float, length_m: float) -> float:
    """Quay transfer point of a berthed vessel: the middle of its hull (spec §5.2)."""
    return berth_position_m + length_m / 2.0


def transfer_distance_m(quay_x_m: float, transfer_point_x_m: float, transfer_point_y_m: float) -> float:
    """Rectilinear quay-to-block distance (spec §5.2); the quay line is y = 0 (D03)."""
    return abs(quay_x_m - transfer_point_x_m) + transfer_point_y_m


def transport_cycle_min(distance_m: float, speed_m_per_min: float, handover_min: float) -> float:
    return 2.0 * distance_m / speed_m_per_min + handover_min


def transport_rate_moves_per_hour(distance_m: float, speed_m_per_min: float, handover_min: float,
                                  units_per_crane: int) -> float:
    """Coupling B: the gang of ``units_per_crane`` transport units completes one round trip per move."""
    cycle = transport_cycle_min(distance_m, speed_m_per_min, handover_min)
    if cycle <= 0.0:
        return float("inf")
    return units_per_crane * 60.0 / cycle


def congestion_factor(occupied_teu: float, capacity_teu: float, rho0: float, g_min: float) -> float:
    """Coupling C congestion g(rho) on *physical* occupancy (reservations excluded)."""
    rho = occupied_teu / capacity_teu
    if rho <= rho0:
        return 1.0
    rho = min(rho, 1.0)
    return 1.0 - (1.0 - g_min) * (rho - rho0) / (1.0 - rho0)


def share_block_capacity(effective_capacity: float, landside_reserved_fraction: float,
                         ship_demands: Iterable[tuple[str, float]],
                         land_demands: Iterable[tuple[str, float]]) -> dict[str, float]:
    """Allocate one block's effective handling capacity to its active flows (spec §5.3).

    Landside flows are guaranteed ``landside_reserved_fraction`` of the capacity
    when they have demand; unused landside share returns to ship-side flows and
    vice versa. Within a class, flows receive shares proportional to demand.
    Returns ``{flow_id: allocated moves/h}``; every allocation is <= its demand.
    """
    ship = list(ship_demands)
    land = list(land_demands)
    ship_total = sum(d for _, d in ship)
    land_total = sum(d for _, d in land)
    land_guarantee = landside_reserved_fraction * effective_capacity if land_total > 0.0 else 0.0
    ship_alloc = min(ship_total, effective_capacity - min(land_total, land_guarantee))
    land_alloc = min(land_total, effective_capacity - ship_alloc)
    result: dict[str, float] = {}
    for flows, total, alloc in ((ship, ship_total, ship_alloc), (land, land_total, land_alloc)):
        for flow_id, demand in flows:
            result[flow_id] = demand if alloc >= total else demand * alloc / total
    return result


def allocate_block(effective_capacity: float, landside_reserved_fraction: float,
                   ship_demands: list[tuple[str, float]], land_count: int,
                   land_demand_each: float) -> tuple[dict[str, float], float]:
    """Closed form of ``share_block_capacity`` when every landside flow has the same demand.

    Landside flows of one block all demand ``gate_flow_demand = mu_b`` (spec §5.4), so
    proportional sharing gives them equal rates. Returns (ship-side rate per flow id,
    rate of each landside flow). Identical to ``share_block_capacity`` (tested).
    """
    ship_total = sum(d for _, d in ship_demands)
    land_total = land_count * land_demand_each
    land_guarantee = landside_reserved_fraction * effective_capacity if land_total > 0.0 else 0.0
    ship_alloc = min(ship_total, effective_capacity - min(land_total, land_guarantee))
    land_alloc = min(land_total, effective_capacity - ship_alloc)
    ship = {flow_id: (d if ship_alloc >= ship_total else d * ship_alloc / ship_total)
            for flow_id, d in ship_demands}
    if land_count == 0:
        return ship, 0.0
    per_flow = land_demand_each if land_alloc >= land_total else land_alloc / land_count
    return ship, per_flow


def forecast_release_min(*, now_min: float, phase: str, berth_start_time_min: float,
                         handling_end_time_min: float | None, remaining_moves: float,
                         current_rate_moves_per_hour: float, berthing_preparation_min: float,
                         departure_preparation_min: float, service_minutes_per_move: float) -> float:
    """``ServiceForecaster v1`` (spec §11, PROPOSED; frozen at Step 6). Reads current state only.

    The arguments are exactly the current-state quantities of the formula; the
    function has no access to the event queue or to the scenario's future.
    """
    if phase == "BERTHING_PREP":
        remaining_prep = max(0.0, berth_start_time_min + berthing_preparation_min - now_min)
    else:
        remaining_prep = 0.0
    if phase in ("BERTHING_PREP", "HANDLING"):
        if current_rate_moves_per_hour > 0.0:
            handling_left = 60.0 * remaining_moves / current_rate_moves_per_hour
        else:
            handling_left = service_minutes_per_move * remaining_moves
        departure_left = departure_preparation_min
    elif phase == "DEPARTURE_PREP":
        handling_left = 0.0
        departure_left = max(0.0, handling_end_time_min + departure_preparation_min - now_min)
    else:
        raise ValueError(f"forecast requested for a vessel in phase {phase}")
    return now_min + remaining_prep + handling_left + departure_left


__all__ = [
    "allocate_block", "congestion_factor", "crane_rate_moves_per_hour", "forecast_release_min", "quay_transfer_x_m",
    "share_block_capacity", "transfer_distance_m", "transport_cycle_min",
    "transport_rate_moves_per_hour",
]
