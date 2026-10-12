"""Append-only container movement ledger ``itp_ledger_v1`` (container_yard_foundation §8).

In memory a ledger record is an immutable tuple (cheap to share between clones);
``record_to_dict`` materializes the schema fields of foundation §8 for export.

Event classes:

* ``PHYSICAL`` - a container status/location transition T1-T11. Only these move
  inventory. ``*_COMPLETED`` of a ship-side transfer carries ``crane_moves = 1``.
* ``PLAN`` - ``YARD_RESERVATION_CREATED`` / ``YARD_RESERVATION_RELEASED``. A
  reservation is never throughput and never changes a location.
* ``EXCEPTION`` - ``ROLLED_OVER`` (D17). (``TRANSFER_ABORTED`` is unreachable in v1;
  validator rejections leave the kernel state byte-identical and are therefore
  recorded by the episode runner, not appended here.)

``WORK_ORDER_PLANNED`` is not emitted: a v1 work order is created and started in
one atomic transition (its id is committed only when the batch starts), so no
planned-but-unstarted stage exists. The type stays reserved.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable

LEDGER_SCHEMA_VERSION = "itp_ledger_v1"

(L_SEQ, L_TIME, L_TYPE, L_CLASS, L_CONTAINER, L_GROUP, L_FROM, L_TO, L_SOURCE, L_DEST, L_TEU,
 L_CRANE_MOVES, L_RESOURCE, L_VESSEL, L_WORK_ORDER, L_CAUSATION, L_TINDEX) = range(17)

PHYSICAL, PLAN, EXCEPTION = "PHYSICAL", "PLAN", "EXCEPTION"

# Foundation §4.4 transition table: event type -> (from status, to status, source kind, destination kind).
TRANSITIONS = {
    "VESSEL_ARRIVED_WITH_CARGO": ("EXPECTED_BY_VESSEL", "ABOARD_ARRIVED_VESSEL", "VESSEL", "VESSEL"),  # T1
    "DISCHARGE_STARTED": ("ABOARD_ARRIVED_VESSEL", "DISCHARGING", "VESSEL", "TRANSFER"),             # T2
    "DISCHARGE_COMPLETED": ("DISCHARGING", "IN_YARD", "TRANSFER", "YARD_BLOCK"),                     # T3
    "GATE_ARRIVED": ("EXPECTED_BY_LANDSIDE", "AT_GATE", "EXTERNAL_LANDSIDE", "GATE"),               # T4
    "RECEIVE_STARTED": ("AT_GATE", "RECEIVING", "GATE", "TRANSFER"),                                 # T5
    "RECEIVE_COMPLETED": ("RECEIVING", "IN_YARD", "TRANSFER", "YARD_BLOCK"),                         # T6
    "RELEASE_STARTED": ("IN_YARD", "RETRIEVING_TO_LANDSIDE", "YARD_BLOCK", "TRANSFER"),              # T7
    "RELEASE_COMPLETED": ("RETRIEVING_TO_LANDSIDE", "RELEASED_TO_LANDSIDE", "TRANSFER",
                          "EXTERNAL_LANDSIDE"),                                                      # T8
    "LOAD_STARTED": ("IN_YARD", "LOADING", "YARD_BLOCK", "TRANSFER"),                                # T9
    "LOAD_COMPLETED": ("LOADING", "LOADED", "TRANSFER", "VESSEL"),                                   # T10
    "DEPARTED_WITH_VESSEL": ("LOADED", "DEPARTED_BY_VESSEL", "VESSEL", "VESSEL"),                    # T11
}
ALLOWED_STATUS_PAIRS = {(f, t) for f, t, _, _ in TRANSITIONS.values()}
TERMINAL_STATUSES = frozenset({"RELEASED_TO_LANDSIDE", "DEPARTED_BY_VESSEL"})
# Location kind expected for each container status (foundation §4.3).
STATUS_LOCATION_KIND = {
    "EXPECTED_BY_VESSEL": "VESSEL", "ABOARD_ARRIVED_VESSEL": "VESSEL", "DISCHARGING": "TRANSFER",
    "EXPECTED_BY_LANDSIDE": "EXTERNAL_LANDSIDE", "AT_GATE": "GATE", "RECEIVING": "TRANSFER",
    "IN_YARD": "YARD_BLOCK", "RETRIEVING_TO_LANDSIDE": "TRANSFER",
    "RELEASED_TO_LANDSIDE": "EXTERNAL_LANDSIDE", "LOADING": "TRANSFER", "LOADED": "VESSEL",
    "DEPARTED_BY_VESSEL": "VESSEL",
}
SHIP_SIDE_COMPLETIONS = ("DISCHARGE_COMPLETED", "LOAD_COMPLETED")
YARD_MOVE_EVENTS = ("DISCHARGE_COMPLETED", "RECEIVE_COMPLETED", "RELEASE_STARTED", "LOAD_STARTED")
THROUGHPUT_EVENTS = ("RELEASE_COMPLETED", "DEPARTED_WITH_VESSEL")


def location_tuple(kind: str, location_id: str | None) -> tuple[str, str | None, str | None]:
    """G0 location: (kind, location_id, slot_resolution). Bay/row/tier are always null in G0 (DQ19)."""
    return (kind, location_id, "BLOCK_ONLY" if kind == "YARD_BLOCK" else None)


def location_dict(loc: tuple) -> dict[str, Any]:
    return {"kind": loc[0], "location_id": loc[1], "bay": None, "row": None, "tier": None,
            "slot_resolution": loc[2]}


def ledger_event_id(sequence: int) -> str:
    return f"LE-{sequence:08d}"


def idempotency_key(record: tuple) -> str:
    if record[L_CLASS] == PHYSICAL:
        return f"{record[L_CONTAINER]}#{record[L_TINDEX]}"
    return f"{record[L_TYPE]}#{record[L_WORK_ORDER]}#{record[L_CONTAINER]}"


def record_to_dict(record: tuple, *, run_id: str | None, scenario_id: str | None) -> dict[str, Any]:
    return {
        "event_id": ledger_event_id(record[L_SEQ]),
        "run_id": run_id,
        "scenario_id": scenario_id,
        "sequence_number": record[L_SEQ],
        "simulation_time_min": record[L_TIME],
        "event_type": record[L_TYPE],
        "event_class": record[L_CLASS],
        "container_id": record[L_CONTAINER],
        "container_group_id": record[L_GROUP],
        "from_status": record[L_FROM],
        "to_status": record[L_TO],
        "source_location": location_dict(record[L_SOURCE]),
        "destination_location": location_dict(record[L_DEST]),
        "quantity_teu": record[L_TEU],
        "crane_moves": record[L_CRANE_MOVES],
        "handling_resource_id": record[L_RESOURCE],
        "related_vessel_id": record[L_VESSEL],
        "related_work_order_id": record[L_WORK_ORDER],
        "causation_id": record[L_CAUSATION],
        "transition_index": record[L_TINDEX],
        "idempotency_key": idempotency_key(record),
    }


def ledger_jsonl_lines(records: Iterable[tuple], *, run_id: str | None,
                       scenario_id: str | None) -> Iterable[str]:
    for record in records:
        yield json.dumps(record_to_dict(record, run_id=run_id, scenario_id=scenario_id),
                         sort_keys=True, separators=(",", ":"), allow_nan=False)


def ledger_sha256(records: Iterable[tuple], *, run_id: str | None = None,
                  scenario_id: str | None = None) -> str:
    """SHA-256 of the canonical JSONL ledger (determinism test of ADR §6.5)."""
    digest = hashlib.sha256()
    for line in ledger_jsonl_lines(records, run_id=run_id, scenario_id=scenario_id):
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def replay_audit(catalog, records: list[tuple], state) -> dict[str, Any]:
    """Foundation §8.3 post-run audit: duplicates, replay, conservation, recomputation.

    Returns a report with ``ok`` and a list of ``issues`` (code, message). Never repairs.
    """
    issues: list[tuple[str, str]] = []

    def issue(code: str, message: str) -> None:
        if len(issues) < 50:
            issues.append((code, message))

    keys = Counter(idempotency_key(r) for r in records)
    duplicates = [k for k, n in keys.items() if n > 1]
    if duplicates:
        issue("INVENTORY_CONSERVATION_FAILURE", f"duplicate idempotency keys {duplicates[:5]}")
    previous_seq, previous_time = -1, -1.0
    loc = {c.container_id: (status, kind, lid)
           for c, (status, kind, lid) in zip(catalog.containers, catalog.initial_locations)}
    tindex = {cid: 0 for cid in loc}
    reserved: dict[tuple[str, str], float] = {}
    counts = Counter()
    for record in records:
        if record[L_SEQ] <= previous_seq:
            issue("EVENT_ORDER_VIOLATION", f"sequence {record[L_SEQ]} not increasing")
        if record[L_TIME] < previous_time - 1e-9:
            issue("EVENT_ORDER_VIOLATION", f"time {record[L_TIME]} decreases at {record[L_SEQ]}")
        previous_seq, previous_time = record[L_SEQ], record[L_TIME]
        cid = record[L_CONTAINER]
        if cid not in loc:
            issue("UNKNOWN_REFERENCE", f"ledger references unknown container {cid}")
            continue
        if record[L_CLASS] == PLAN:
            key = (record[L_WORK_ORDER], cid)
            if record[L_TYPE] == "YARD_RESERVATION_CREATED":
                if key in reserved:
                    issue("INVENTORY_CONSERVATION_FAILURE", f"double reservation {key}")
                reserved[key] = record[L_TEU]
            elif record[L_TYPE] == "YARD_RESERVATION_RELEASED":
                if reserved.pop(key, None) is None:
                    issue("INVENTORY_CONSERVATION_FAILURE", f"release of missing reservation {key}")
            continue
        if record[L_CLASS] != PHYSICAL:
            counts[record[L_TYPE]] += 1
            continue
        status, kind, lid = loc[cid]
        source = record[L_SOURCE]
        if (kind, lid) != (source[0], source[1]):
            issue("UNAVAILABLE_SOURCE_INVENTORY",
                  f"{cid} at {kind}/{lid}, ledger source {source[0]}/{source[1]} (seq {record[L_SEQ]})")
        if record[L_FROM] != status or (record[L_FROM], record[L_TO]) not in ALLOWED_STATUS_PAIRS:
            issue("INVALID_STATUS_TRANSITION",
                  f"{cid}: {status} -> {record[L_FROM]}->{record[L_TO]} (seq {record[L_SEQ]})")
        expected = TRANSITIONS.get(record[L_TYPE])
        if expected is None or expected[:2] != (record[L_FROM], record[L_TO]) \
                or expected[2] != source[0] or expected[3] != record[L_DEST][0]:
            issue("INVALID_STATUS_TRANSITION", f"{cid}: {record[L_TYPE]} inconsistent with T1-T11")
        if record[L_DEST][0] == "YARD_BLOCK" and record[L_DEST][2] != "BLOCK_ONLY":
            issue("FIDELITY_MISLABEL", f"{cid}: G0 yard location not BLOCK_ONLY")
        tindex[cid] += 1
        if record[L_TINDEX] != tindex[cid]:
            issue("INVENTORY_CONSERVATION_FAILURE", f"{cid}: transition_index {record[L_TINDEX]} "
                                                    f"!= replay {tindex[cid]}")
        if record[L_TYPE] in ("DISCHARGE_COMPLETED", "LOAD_COMPLETED", "RECEIVE_COMPLETED",
                              "RELEASE_COMPLETED") and record[L_WORK_ORDER] is None:
            issue("INVENTORY_CONSERVATION_FAILURE", f"{cid}: completed move without work order (INV04)")
        loc[cid] = (record[L_TO], record[L_DEST][0], record[L_DEST][1])
        counts[record[L_TYPE]] += 1
    # 3-4: final locations and conservation.
    if len(loc) != len(catalog.containers):
        issue("INVENTORY_CONSERVATION_FAILURE", "container count changed")
    mismatched = 0
    for c in catalog.containers:
        final = (state.c_status[c.index], state.c_loc_kind[c.index], state.c_loc_id[c.index])
        if loc[c.container_id] != final:
            mismatched += 1
            if mismatched <= 5:
                issue("INVENTORY_CONSERVATION_FAILURE",
                      f"{c.container_id}: replay {loc[c.container_id]} != kernel {final}")
        if tindex[c.container_id] != state.c_tindex[c.index]:
            issue("INVENTORY_CONSERVATION_FAILURE", f"{c.container_id}: transition count mismatch")
    # 5: per-block occupancy recomputed from replayed locations.
    occupied: dict[str, float] = {b.block_id: 0.0 for b in catalog.blocks}
    count: dict[str, int] = {b.block_id: 0 for b in catalog.blocks}
    for c in catalog.containers:
        status, kind, lid = loc[c.container_id]
        if kind == "YARD_BLOCK":
            occupied[lid] += c.size_teu
            count[lid] += 1
    for block_id, block in state.blocks.items():
        if abs(occupied[block_id] - block.occupied_teu) > 1e-9 or count[block_id] != block.occupied_count:
            issue("INVENTORY_CONSERVATION_FAILURE",
                  f"{block_id}: recomputed {occupied[block_id]} TEU/{count[block_id]} != cache "
                  f"{block.occupied_teu}/{block.occupied_count}")
        open_res = sum(teu for (wo, _cid), teu in reserved.items()
                       if state.work_orders.get(wo) is not None
                       and state.work_orders[wo].destination[1] == block_id)
        if abs(open_res - block.reserved_teu) > 1e-9:
            issue("INVENTORY_CONSERVATION_FAILURE",
                  f"{block_id}: ledger open reservations {open_res} != state {block.reserved_teu}")
    # 6: KPIs recomputed from the ledger.
    crane_moves = counts["DISCHARGE_COMPLETED"] + counts["LOAD_COMPLETED"]
    yard_moves = sum(counts[t] for t in YARD_MOVE_EVENTS)
    throughput = counts["RELEASE_COMPLETED"] + counts["DEPARTED_WITH_VESSEL"]
    kernel_crane_moves = sum(c.moves_completed for c in state.cranes.values())
    if crane_moves != kernel_crane_moves:
        issue("INVENTORY_CONSERVATION_FAILURE",
              f"ledger crane moves {crane_moves} != crane accumulators {kernel_crane_moves}")
    vessel_moves = sum(v.completed_moves for v in state.vessels.values())
    if crane_moves != vessel_moves:
        issue("INVENTORY_CONSERVATION_FAILURE",
              f"ledger crane moves {crane_moves} != vessel progress {vessel_moves}")
    terminal = sum(1 for c in catalog.containers if loc[c.container_id][0] in TERMINAL_STATUSES)
    if throughput != terminal:
        issue("INVENTORY_CONSERVATION_FAILURE", f"throughput {throughput} != terminal statuses {terminal}")
    return {
        "ok": not issues,
        "issues": [{"code": code, "message": message} for code, message in issues],
        "records": len(records),
        "physical_records": sum(1 for r in records if r[L_CLASS] == PHYSICAL),
        "crane_moves": crane_moves,
        "yard_moves": yard_moves,
        "container_throughput": throughput,
        "rolled_over_records": counts["ROLLED_OVER"],
    }


__all__ = [
    "ALLOWED_STATUS_PAIRS", "EXCEPTION", "LEDGER_SCHEMA_VERSION", "PHYSICAL", "PLAN",
    "STATUS_LOCATION_KIND", "TERMINAL_STATUSES", "TRANSITIONS", "idempotency_key",
    "ledger_event_id", "ledger_jsonl_lines", "ledger_sha256", "location_dict", "location_tuple",
    "record_to_dict", "replay_audit",
]
