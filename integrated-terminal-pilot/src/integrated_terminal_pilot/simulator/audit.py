"""Independent post-run / checkpoint audits that reuse Projects 01 and 03 validators.

* ``realized_schedule_audit`` - the realized projection (data contract §11):
  ``service_time = departure - berth_start`` per departed vessel, checked with
  Project 03 ``find_schedule_violations`` (no overlap, no clearance violation, no
  start before arrival, inside the quay).
* ``project01_snapshot_check`` - the Project 01 audit projection (data contract §12)
  validated by Project 01 ``TerminalState`` cross-entity validation.

Project 01 projection: documented losses (beyond those listed in §12)

* Reservations are not projected. Project 01 ``YardBlock`` forbids a group being
  both stored and reserved in the same block, but Project I reserves per work
  order, so the next batch of a group is routinely reserved in a block that
  already stores earlier batches. Reservations are verified by INV07/INV17 and
  the ledger replay instead.
* Groups with the ``PRE_EPISODE`` sentinel are omitted (Project 01 requires every
  referenced vessel to be registered; ``PRE_EPISODE`` is never a vessel record).
* Containers in ``TRANSFER`` are counted at their source, EXTERNAL locations are
  omitted, and work orders are not projected (all as specified in §12).

The projection never feeds back into the kernel.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from berth_allocation_lab.core import find_schedule_violations
from berth_allocation_lab.core.types import BAPPlacement
from berth_allocation_lab.data import BAPVesselInput

from integrated_terminal_pilot.scenarios.models import PRE_EPISODE

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
P01_VESSEL_STATUS = {"NOT_ARRIVED": "approaching", "WAITING": "waiting", "BERTHING_PREP": "berthed",
                     "HANDLING": "operating", "DEPARTURE_PREP": "ready_to_depart", "DEPARTED": "departed"}
P01_CRANE_STATUS = {"available": "available", "assigned": "assigned", "operating": "operating"}
P01_LOCATION = {"VESSEL": "vessel", "YARD_BLOCK": "yard_block", "GATE": "gate"}


def realized_schedule_audit(kernel) -> dict[str, Any]:
    catalog, s = kernel.catalog, kernel.state
    vessels, placements = [], []
    for record in catalog.vessels:
        v = s.vessels[record.vessel_id]
        if v.departure_time_min is None:
            continue
        service = v.departure_time_min - v.berth_start_time_min
        vessels.append(BAPVesselInput(record.vessel_id, record.arrival_time_min, record.length_m, service,
                                      record.workload_moves))
        placements.append(BAPPlacement(record.vessel_id, v.berth_position_m, v.berth_start_time_min,
                                       record.length_m, service))
    complete = s.status == "COMPLETED"
    violations = find_schedule_violations(vessels, placements, catalog.berth_length_m, catalog.min_clearance_m,
                                          require_complete=complete)
    return {"ok": not violations, "complete_episode": complete, "departed_vessels": len(vessels),
            "violations": [{"code": v.code.value, "vessel_ids": list(v.vessel_ids), "message": v.message}
                           for v in violations]}


def project01_terminal_state(kernel):
    """Build a Project 01 ``TerminalState`` from the current kernel state (raises if Project 01 rejects it)."""
    from terminal_core import ContainerGroupLocation, TaskLocation, TaskLocationType, TerminalState

    catalog, s = kernel.catalog, kernel.state
    now = EPOCH + timedelta(minutes=s.now_min)
    vessels = {}
    for record in catalog.vessels:
        v = s.vessels[record.vessel_id]
        vessels[record.vessel_id] = {
            "vessel_id": record.vessel_id, "length_m": record.length_m,
            "eta": (EPOCH + timedelta(minutes=record.arrival_time_min)).isoformat(),
            "workload_moves": record.workload_moves, "priority": record.priority,
            "max_cranes": record.max_cranes, "status": P01_VESSEL_STATUS[v.phase]}
    occupancies = [{"vessel": vessels[vid], "start_position_m": s.vessels[vid].berth_position_m}
                   for vid in s.reveal_order
                   if s.vessels[vid].phase in ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP")]
    berths = {"QUAY": {"berth_id": "QUAY", "length_m": catalog.berth_length_m,
                       "min_clearance_m": catalog.min_clearance_m, "occupancies": occupancies}}
    cranes = {}
    for record in catalog.cranes:
        crane = s.cranes[record.crane_id]
        cranes[record.crane_id] = {"crane_id": record.crane_id,
                                   "position_m": float(record.record.get("home_position_m", 0.0)),
                                   "moves_per_hour": record.nominal_moves_per_hour,
                                   "status": P01_CRANE_STATUS[crane.status],
                                   "assigned_vessel_id": crane.assigned_vessel_id}
    groups = {gid: dict(g) for gid, g in catalog.groups.items()
              if PRE_EPISODE not in (g["source_vessel_id"], g["target_vessel_id"])}
    amounts: dict[tuple[str, str, str], float] = {}
    for c in catalog.containers:
        if c.group_id not in groups:
            continue
        kind, location_id = s.c_loc_kind[c.index], s.c_loc_id[c.index]
        if kind == "TRANSFER":
            kind, location_id = s.work_orders[location_id].source  # counted at the source (§12)
        if kind not in P01_LOCATION:
            continue
        key = (c.group_id, kind, location_id)
        amounts[key] = amounts.get(key, 0.0) + c.size_teu
    stored: dict[str, dict[str, float]] = {b.block_id: {} for b in catalog.blocks}
    locations = []
    for (group_id, kind, location_id), teu in sorted(amounts.items()):
        locations.append(ContainerGroupLocation(group_id, TaskLocation(TaskLocationType(P01_LOCATION[kind]),
                                                                       location_id), teu))
        if kind == "YARD_BLOCK":
            stored[location_id][group_id] = teu
    blocks = {b.block_id: {"block_id": b.block_id, "capacity_teu": b.capacity_teu,
                           "capabilities": sorted(b.capabilities), "status": s.blocks[b.block_id].status,
                           "stored_groups": stored[b.block_id], "reservations": {}}
              for b in catalog.blocks}
    return TerminalState(current_time=now, vessels=vessels, berths=berths, quay_cranes=cranes,
                         yard_blocks=blocks, container_groups=groups, group_locations=tuple(locations))


def project01_snapshot_check(kernel) -> dict[str, Any]:
    try:
        state = project01_terminal_state(kernel)
    except Exception as error:  # report, never repair
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    return {"ok": True, "vessels": len(state.vessels), "group_locations": len(state.group_locations),
            "omitted": ["reservations", "PRE_EPISODE groups", "EXTERNAL locations", "work orders"]}


__all__ = ["project01_snapshot_check", "project01_terminal_state", "realized_schedule_audit"]
