"""Episode result, KPIs (protocol §7) and post-run audits.

Every vessel of the scenario is included. Unfinished vessels are censored at the
scenario-fixed ``T_end = last_arrival + max_drain_extension_min`` (D24), never at
an earlier deadlock or truncation time. Container count, TEU and crane moves are
reported separately and never summed.

Nominal and realized service are kept side by side for every vessel:
``nominal_service_time_min`` (D20, an input) versus realized occupancy
``departure - berth_start`` (D21, an outcome), with a decomposition of the
handling phase explaining the difference.
"""

from __future__ import annotations

from typing import Any

import numpy

from integrated_terminal_pilot.simulator.ledger import ledger_sha256, replay_audit
from integrated_terminal_pilot.simulator.state import CRANE_BLOCK_REASONS


def _p95(values: list[float]) -> float | None:
    return float(numpy.percentile(values, 95)) if values else None


def _mean(values: list[float]) -> float | None:
    return float(sum(values) / len(values)) if values else None


def build_result(kernel, *, audits: bool = True, include_vessels: bool = True,
                 run_id: str | None = None) -> dict[str, Any]:
    catalog, s = kernel.catalog, kernel.state
    physics = catalog.physics
    t_end = catalog.drain_limit_min
    end_time = s.now_min
    vessels = []
    turnaround_total = waiting_total = 0.0
    waits, occupancies, handling_durations = [], [], []
    for record in catalog.vessels:
        v = s.vessels[record.vessel_id]
        departure = v.departure_time_min
        turnaround = (min(departure, t_end) if departure is not None else t_end) - record.arrival_time_min
        waiting = (v.berth_start_time_min if v.berth_start_time_min is not None else t_end) - record.arrival_time_min
        turnaround_total += turnaround
        waiting_total += waiting
        waits.append(waiting)
        realized_occupancy = None if departure is None else departure - v.berth_start_time_min
        handling = (None if v.handling_end_time_min is None or v.handling_start_time_min is None
                    else v.handling_end_time_min - v.handling_start_time_min)
        if realized_occupancy is not None:
            occupancies.append(realized_occupancy)
        if handling is not None:
            handling_durations.append(handling)
        if include_vessels:
            nominal_handling = physics.service_minutes_per_move * record.workload_moves
            acc = dict(sorted(v.acc.items()))
            vessels.append({
                "vessel_id": record.vessel_id,
                "arrival_time_min": record.arrival_time_min,
                "length_m": record.length_m,
                "workload_moves": record.workload_moves,
                "phase": v.phase,
                "berth_position_m": v.berth_position_m,
                "berth_start_time_min": v.berth_start_time_min,
                "actual_handling_start_time_min": v.handling_start_time_min,
                "realized_handling_completion_time_min": v.handling_end_time_min,
                "actual_departure_time_min": departure,
                "waiting_time_min": waiting,
                "turnaround_min_censored": turnaround,
                "nominal_service_time_min": record.nominal_service_time_min,
                "realized_berth_occupancy_min": realized_occupancy,
                "nominal_handling_min": nominal_handling,
                "realized_handling_min": handling,
                "service_delta_min": (None if realized_occupancy is None
                                      else realized_occupancy - record.nominal_service_time_min),
                "completed_moves": v.completed_moves,
                "remaining_moves": kernel.remaining_moves(record.vessel_id),
                "rolled_over_containers": len(v.rolled_over_container_ids),
                "service_explanation": _explain(record, v, acc, handling, nominal_handling),
                "accumulators": acc,
            })
    n_cranes = len(s.cranes)
    makespan = (max((v.departure_time_min for v in s.vessels.values() if v.departure_time_min is not None),
                    default=0.0) if s.status == "COMPLETED" else t_end)
    crane_productive = sum(c.productive_min for c in s.cranes.values())
    crane_idle = sum(c.idle_min for c in s.cranes.values())
    blocked = {reason: sum(c.blocked_min_by_reason.get(reason, 0.0) for c in s.cranes.values())
               for reason in CRANE_BLOCK_REASONS}
    released = [s.c_release_time[c.index] - c.pickup_time_min for c in catalog.containers
                if c.cargo_flow == "import" and s.c_status[c.index] == "RELEASED_TO_LANDSIDE"
                and c.pickup_time_min is not None]
    terminal = [c for c in catalog.containers
                if s.c_status[c.index] in ("RELEASED_TO_LANDSIDE", "DEPARTED_BY_VESSEL")]
    rolled = [c for c in catalog.containers if s.c_rolled[c.index]]
    capacity_total = sum(b.capacity_teu for b in catalog.blocks)
    elapsed = max(end_time, 1e-12)
    blocks = {}
    for record in catalog.blocks:
        block = s.blocks[record.block_id]
        blocks[record.block_id] = {
            "occupied_teu": block.occupied_teu, "reserved_teu": block.reserved_teu,
            "peak_occupied_teu": block.peak_occupied_teu,
            "peak_occupancy_fraction": block.peak_occupied_teu / record.capacity_teu,
            "mean_occupancy_fraction": block.teu_minutes / elapsed / record.capacity_teu,
            "busy_min": block.busy_min, "handled_moves": block.handled_moves,
            "handling_capacity_moves_per_hour": record.handling_capacity_moves_per_hour,
        }
    unfinished = sum(kernel.remaining_moves(v.vessel_id) for v in catalog.vessels)
    result: dict[str, Any] = {
        "kernel_version": "itp_kernel_v1",
        "run_id": run_id,
        "scenario_id": catalog.scenario_id,
        "fingerprints": catalog.fingerprints,
        "status": s.status,
        "status_reason": s.status_reason,
        "status_details": s.status_details,
        "end_time_min": end_time,
        "T_end_min": t_end,
        "kpi": {
            "total_turnaround_min": turnaround_total,
            "mean_turnaround_min": turnaround_total / max(len(catalog.vessels), 1),
            "total_berth_waiting_min": waiting_total,
            "mean_berth_waiting_min": _mean(waits),
            "p95_berth_waiting_min": _p95(waits),
            "mean_realized_occupancy_min": _mean(occupancies),
            "mean_handling_duration_min": _mean(handling_durations),
            "crane_productive_min": crane_productive,
            "crane_idle_min": crane_idle,
            "crane_blocked_min_by_reason": blocked,
            "crane_utilization": crane_productive / (n_cranes * makespan) if n_cranes and makespan > 0 else None,
            "crane_rate_shortfall_moves": sum(c.rate_shortfall_moves for c in s.cranes.values()),
            "crane_transport_shortfall_moves": sum(c.transport_shortfall_moves for c in s.cranes.values()),
            "crane_yard_shortfall_moves": sum(c.yard_shortfall_moves for c in s.cranes.values()),
            "yard_blocked_crane_min": blocked["YARD_CAPACITY"],
            "peak_yard_occupancy_teu": s.kpi.get("peak_yard_teu", 0.0),
            "peak_block_occupancy_fraction": max((b["peak_occupancy_fraction"] for b in blocks.values()),
                                                 default=0.0),
            "mean_yard_occupancy_fraction": (sum(b.teu_minutes for b in s.blocks.values())
                                             / elapsed / capacity_total) if capacity_total else None,
            "gate_waiting_container_min": s.kpi.get("gate_waiting_container_min", 0.0),
            "mean_pickup_delay_min": _mean(released),
            "p95_pickup_delay_min": _p95(released),
            "container_throughput": len(terminal),
            "teu_throughput": float(sum(c.size_teu for c in terminal)),
            "crane_moves_completed": sum(c.moves_completed for c in s.cranes.values()),
            "unfinished_workload_moves": unfinished,
            "rolled_over_containers": len(rolled),
            "rolled_over_teu": float(sum(c.size_teu for c in rolled)),
            "makespan_min": makespan,
            "waiting_vessel_min_integral": s.kpi.get("waiting_vessel_min", 0.0),
            "peak_concurrent_landside_batches_per_block": s.kpi.get("peak_concurrent_landside_batches_per_block",
                                                                     0.0),
        },
        "counts": {
            "vessels": len(catalog.vessels),
            "departed_vessels": sum(1 for v in s.vessels.values() if v.phase == "DEPARTED"),
            "containers": len(catalog.containers),
            "kernel_cycles": s.cycles,
            "kernel_events_scheduled": s.next_event_seq - 1,
            "stale_events_discarded": s.stale_events_discarded,
            "work_orders": s.next_work_order_seq - 1,
            "decisions": len(s.decision_log),
            "ledger_records": None if s.ledger is None else len(s.ledger),
            "crane_blocking_episodes": len(s.block_episodes),
        },
        "cranes": {c.crane_id: {"productive_min": c.productive_min, "idle_min": c.idle_min,
                                "blocked_min_by_reason": dict(sorted(c.blocked_min_by_reason.items())),
                                "moves_completed": c.moves_completed}
                   for c in s.cranes.values()},
        "blocks": blocks,
        "vessels": vessels,
    }
    if audits:
        result["audits"] = run_audits(kernel)
        if s.ledger is not None:
            result["ledger_sha256"] = ledger_sha256(s.ledger)
    return result


def _explain(record, v, acc: dict[str, float], handling: float | None, nominal_handling: float) -> list[str]:
    """Why realized handling differs from the nominal 0.5 min/move (D20 vs D21)."""
    if handling is None:
        return ["handling not completed"]
    notes = []
    delta = handling - nominal_handling
    notes.append(f"realized handling {handling:.1f} min vs nominal {nominal_handling:.1f} min "
                 f"(delta {delta:+.1f})")
    if acc.get("handling_no_crane_min", 0.0) > 1e-9:
        notes.append(f"{acc['handling_no_crane_min']:.1f} min in HANDLING without any crane")
    for key in sorted(acc):
        if key.startswith("crane_min_blocked_") and acc[key] > 1e-9:
            notes.append(f"{acc[key]:.1f} crane-min blocked ({key[len('crane_min_blocked_'):]})")
    for key, label in (("efficiency_loss_moves", "multi-crane efficiency"),
                       ("transport_shortfall_moves", "transport cycle limit"),
                       ("yard_shortfall_moves", "yard handling share")):
        if acc.get(key, 0.0) > 1e-6:
            notes.append(f"{acc[key]:.1f} moves of crane capacity lost to {label}")
    if v.rolled_over_container_ids:
        notes.append(f"{len(v.rolled_over_container_ids)} containers rolled over (D17)")
    return notes


def run_audits(kernel) -> dict[str, Any]:
    """Post-run audits: invariants, ledger replay, realized schedule, Project 01 projection."""
    from integrated_terminal_pilot.simulator import invariants as inv
    from integrated_terminal_pilot.simulator.audit import project01_snapshot_check, realized_schedule_audit

    s = kernel.state
    audits: dict[str, Any] = {}
    try:
        inv.check(kernel, full=True)
        audits["invariants"] = {"ok": True}
    except Exception as error:  # report, never repair
        audits["invariants"] = {"ok": False, "error": str(error)}
    if s.ledger is not None:
        audits["ledger_replay"] = replay_audit(kernel.catalog, s.ledger, s)
    audits["realized_schedule"] = realized_schedule_audit(kernel)
    audits["project01_projection"] = project01_snapshot_check(kernel)
    audits["ok"] = all(a.get("ok", True) for a in audits.values() if isinstance(a, dict))
    return audits


__all__ = ["build_result", "run_audits"]
