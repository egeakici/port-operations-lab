"""Degenerate equivalence test (implementation roadmap, Step 4 gate).

For a scenario generated with the ``degenerate_equivalence_v1`` physics profile
(transport and yard couplings off, cranes at 120 moves/h, ``max_cranes = 1``,
crane fleet >= the maximum number of vessels that can share the quay,
preparation 30/20, identical quay geometry), the integrated kernel driven by
the Project 03 online FCFS rule plus P_c / P_y (arm A1's primitives) must
reproduce Project 03 ``DynamicBAPEnv`` with ``online_fcfs_action`` on the
scenario's berth projection.

The reference is the *real* Project 03 environment and policy, run separately
on the projection. Nothing is compared against a second copy of the kernel.

What it establishes: agreement of the berth layer (allocation order,
positions, start times, occupancy, waiting, turnaround, schedule validity) when
crane, transport and yard physics introduce no delay. It does not establish
crane, yard or inventory correctness (other Step 4 tests cover those).
"""

from __future__ import annotations

from typing import Any

from integrated_terminal_pilot.scenarios.berth_projection import (
    build_berth_projection, projection_physical_fingerprint,
)
from integrated_terminal_pilot.simulator.drivers import default_policies, run_episode
from integrated_terminal_pilot.simulator.kernel import TerminalKernel

POSITION_TOL_M = 1e-9
TIME_TOL_MIN = 1e-6


def run_project03_reference(projection, max_vessels: int = 24) -> dict[str, Any]:
    """Project 03 ``DynamicBAPEnv`` + ``online_fcfs_action`` on the berth projection (unchanged code)."""
    from berth_allocation_lab.envs import DynamicBAPEnv
    from berth_allocation_lab.policies.dynamic_fcfs import run_online_fcfs

    env = DynamicBAPEnv(scenario=projection, max_vessels=max_vessels,
                        future_horizon_min=projection.future_horizon_min)
    _, _, info = run_online_fcfs(env)
    order = [r["selected_vessel_id"] for r in env.decision_records if r["action_type"] == "ASSIGN"]
    placements = {p.vessel_id: p for p in env.placements}
    arrivals = {v.vessel_id: v.arrival_time_min for v in projection.vessels}
    return {
        "terminated": env.terminated, "truncated": env.truncated,
        "schedule_valid": bool(info.get("schedule_valid", False)),
        "order": order,
        "positions": {vid: p.berth_position_m for vid, p in placements.items()},
        "starts": {vid: p.berth_start_time_min for vid, p in placements.items()},
        "occupancy": {vid: p.service_time_min for vid, p in placements.items()},
        "total_waiting_min": float(info.get("total_waiting_time_min", info["waiting_cost_min"])),
        "total_turnaround_min": sum(p.service_end_time_min - arrivals[vid] for vid, p in placements.items()),
        "wait_actions": sum(1 for r in env.decision_records if r["action_type"] == "WAIT"),
    }


def degenerate_equivalence(doc: dict[str, Any], *, validate: bool = True,
                           invariant_mode: str = "cheap") -> dict[str, Any]:
    """Run both worlds on one degenerate-profile scenario and compare them field by field."""
    if doc["identity"]["physics_profile"] != "degenerate_equivalence_v1":
        raise ValueError("degenerate_equivalence needs a degenerate_equivalence_v1 scenario")
    projection = build_berth_projection(doc)
    reference = run_project03_reference(projection)
    kernel = TerminalKernel.from_scenario(doc, validate=validate, invariant_mode=invariant_mode)
    run = run_episode(kernel, **default_policies())
    result = kernel.result()
    s = kernel.state
    order = [entry[3][2] for entry in s.decision_log if entry[2] == "BERTH" and entry[3][0] == "ASSIGN"]
    vessels = {v["vessel_id"]: v for v in result["vessels"]}
    checks: dict[str, Any] = {}
    checks["projection_physical_fingerprint"] = (
        doc["fingerprints"]["berth_projection_physical_fingerprint"] == projection_physical_fingerprint(projection))
    checks["integrated_completed"] = run.status == "COMPLETED" and result["status"] == "COMPLETED"
    checks["reference_terminated_valid"] = reference["terminated"] and reference["schedule_valid"]
    checks["allocation_order"] = order == reference["order"]
    position_err = max((abs(vessels[vid]["berth_position_m"] - x) for vid, x in reference["positions"].items()),
                       default=0.0)
    start_err = max((abs(vessels[vid]["berth_start_time_min"] - t) for vid, t in reference["starts"].items()),
                    default=0.0)
    occupancy_err = max((abs(vessels[vid]["realized_berth_occupancy_min"] - vessels[vid]["nominal_service_time_min"])
                         for vid in vessels if vessels[vid]["realized_berth_occupancy_min"] is not None),
                        default=float("inf"))
    reference_occupancy_err = max((abs(reference["occupancy"][vid] - vessels[vid]["nominal_service_time_min"])
                                   for vid in reference["occupancy"]), default=0.0)
    waiting_err = abs(result["kpi"]["total_berth_waiting_min"] - reference["total_waiting_min"])
    integrated_turnaround = sum(v["actual_departure_time_min"] - v["arrival_time_min"] for v in vessels.values()
                                if v["actual_departure_time_min"] is not None)
    turnaround_err = abs(integrated_turnaround - reference["total_turnaround_min"])
    checks["positions_within_1e-9_m"] = position_err <= POSITION_TOL_M
    checks["starts_within_1e-6_min"] = start_err <= TIME_TOL_MIN
    checks["occupancy_equals_nominal_within_1e-6"] = occupancy_err <= TIME_TOL_MIN
    checks["total_waiting_within_1e-6"] = waiting_err <= TIME_TOL_MIN
    checks["total_turnaround_within_1e-6"] = turnaround_err <= TIME_TOL_MIN
    checks["realized_schedule_valid"] = result["audits"]["realized_schedule"]["ok"]
    checks["audits_ok"] = result["audits"]["ok"]
    blocked = result["kpi"]["crane_blocked_min_by_reason"]
    return {
        "scenario_id": doc["identity"]["scenario_id"],
        "family": doc["identity"]["scenario_family"],
        "seed": doc["identity"]["scenario_seed"],
        "vessels": len(doc["vessels"]),
        "cranes": len(doc["resources"]["quay_cranes"]),
        "pass": all(bool(v) for v in checks.values()),
        "checks": checks,
        "errors": {"max_position_m": position_err, "max_start_min": start_err,
                   "max_occupancy_minus_nominal_min": occupancy_err,
                   "reference_max_occupancy_minus_nominal_min": reference_occupancy_err,
                   "total_waiting_min": waiting_err, "total_turnaround_min": turnaround_err},
        "integrated": {"total_waiting_min": result["kpi"]["total_berth_waiting_min"],
                       "total_turnaround_min": integrated_turnaround,
                       "cargo_unavailable_crane_min": blocked["CARGO_UNAVAILABLE"],
                       "yard_capacity_crane_min": blocked["YARD_CAPACITY"],
                       "rolled_over_containers": result["kpi"]["rolled_over_containers"],
                       "wall_seconds": run.wall_seconds},
        "reference": {"total_waiting_min": reference["total_waiting_min"],
                      "total_turnaround_min": reference["total_turnaround_min"],
                      "wait_actions": reference["wait_actions"]},
    }


__all__ = ["degenerate_equivalence", "run_project03_reference"]
