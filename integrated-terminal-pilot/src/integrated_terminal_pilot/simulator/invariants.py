"""Runtime physical invariants INV01-INV20.

``check(kernel, full=False)`` runs the *cheap* subset (cost independent of the
container count: berth geometry, crane exclusivity, capacity, reservations,
work orders, clock). ``full=True`` adds the O(N) checks (one location per
container, status/location consistency, occupancy recomputation, dispatch index
consistency, ledger order). Kernels run the full set after every cycle in
``invariant_mode="full"`` (tests, audit) and at least at the start and end of
every episode; ``"cheap"`` runs the subset every cycle (spec §8.2 step 6).

A violation raises ``InvariantViolation`` (code = the invariant, or the Step 1
code where one exists) and the run becomes ``FAILED``. Nothing is suppressed.

INV20 (clones share no mutable state) is a property of ``KernelState.clone`` and
is verified by ``shared_mutable_objects``, used in the clone tests.
"""

from __future__ import annotations

from berth_allocation_lab.core import is_within_quay
from berth_allocation_lab.core.numerics import NUMERICAL_TOLERANCE

from integrated_terminal_pilot.simulator.errors import InvariantViolation
from integrated_terminal_pilot.simulator.events import E_TIME, TIME_TOL
from integrated_terminal_pilot.simulator.ledger import (
    L_SEQ, L_TIME, PHYSICAL, STATUS_LOCATION_KIND, L_CLASS, L_TINDEX,
)
from integrated_terminal_pilot.simulator.state import OCCUPYING_PHASES, SHIP_SIDE

TEU_TOL = 1e-9


def _fail(invariant: str, message: str, code: str | None = None) -> None:
    raise InvariantViolation(invariant, message, code=code)


def check(kernel, *, full: bool = False) -> None:
    _cheap(kernel)
    if full:
        _full(kernel)


def _cheap(kernel) -> None:
    catalog, s = kernel.catalog, kernel.state
    # INV12: no pending event predates the clock (the heap minimum is events[0]).
    if s.events and s.events[0][E_TIME] < s.now_min - TIME_TOL:
        _fail("INV12", "a pending event predates the current clock")
    # INV01: occupying vessels inside the quay, pairwise separated with clearance.
    occupying = []
    for vessel_id, v in s.vessels.items():
        if v.phase in OCCUPYING_PHASES:
            record = catalog.vessel_by_id[vessel_id]
            if not is_within_quay(v.berth_position_m, record.length_m, catalog.berth_length_m):
                _fail("INV01", f"{vessel_id} outside the quay")
            occupying.append((vessel_id, v.berth_position_m, v.berth_position_m + record.length_m))
        elif v.berth_position_m is not None and v.phase not in ("DEPARTED",):
            _fail("INV01", f"{vessel_id} in {v.phase} has a berth position")
    clearance = catalog.min_clearance_m
    for a_index, (a_id, a_start, a_end) in enumerate(occupying):
        for b_id, b_start, b_end in occupying[a_index + 1:]:
            # Project 03 are_spatially_separated: clearance once between hulls, 1e-9 m tolerance.
            if not (a_end + clearance <= b_start + NUMERICAL_TOLERANCE
                    or b_end + clearance <= a_start + NUMERICAL_TOLERANCE):
                _fail("INV01", f"{a_id} and {b_id} overlap or violate clearance")
    # INV02/INV03/INV14: crane exclusivity, max_cranes, productive => eligible work.
    held: dict[str, int] = {}
    for crane_id, crane in s.cranes.items():
        if crane.assigned_vessel_id is None:
            if crane.status != "available" or crane.current_work_order_id is not None:
                _fail("INV02", f"{crane_id} unassigned but {crane.status} / {crane.current_work_order_id}")
            continue
        v = s.vessels[crane.assigned_vessel_id]
        if v.phase not in ("BERTHING_PREP", "HANDLING"):
            _fail("INV02", f"{crane_id} assigned to {v.vessel_id} in phase {v.phase}")
        held[v.vessel_id] = held.get(v.vessel_id, 0) + 1
        if crane.current_work_order_id is not None:
            wo = s.work_orders.get(crane.current_work_order_id)
            if wo is None or wo.crane_id != crane_id or wo.vessel_id != v.vessel_id or v.phase != "HANDLING":
                _fail("INV14", f"{crane_id} works {crane.current_work_order_id} without eligible assigned work")
        if crane.activity == "PRODUCTIVE" and crane.current_work_order_id is None:
            _fail("INV14", f"{crane_id} productive without a batch")
    for vessel_id, count in held.items():
        if count > catalog.vessel_by_id[vessel_id].max_cranes:
            _fail("INV03", f"{vessel_id} holds {count} cranes > max_cranes")
    # Ship-side batches: one per busy crane, valid progress (INV02, INV08).
    for crane_id, crane in s.cranes.items():
        if crane.current_work_order_id is None:
            continue
        wo = s.work_orders.get(crane.current_work_order_id)
        if wo is None or wo.operation_type not in SHIP_SIDE or wo.crane_id != crane_id:
            _fail("INV02", f"{crane_id}: batch {crane.current_work_order_id} is not its ship-side batch")
        if wo.completed_moves < -1e-9 or wo.completed_moves > wo.move_count + 1e-6:
            _fail("INV08", f"{wo.work_order_id} progress {wo.completed_moves} outside [0, {wo.move_count}]")
    # INV07/INV08: block capacity; landside virtual clock never overtakes a pending batch.
    for block_id, block in s.blocks.items():
        record = catalog.block_by_id[block_id]
        if block.occupied_teu < -TEU_TOL or block.occupied_count < 0:
            _fail("INV08", f"{block_id} negative occupancy", code="YARD_CAPACITY_EXCEEDED")
        if block.occupied_teu + block.reserved_teu + block.blocked_teu > record.capacity_teu + TEU_TOL:
            _fail("INV07", f"{block_id}: {block.occupied_teu} + {block.reserved_teu} + {block.blocked_teu} > "
                           f"{record.capacity_teu}", code="YARD_CAPACITY_EXCEEDED")
        if block.land_heap and block.land_heap[0][0] < block.land_v - 1e-6:
            _fail("INV08", f"{block_id}: landside batch {block.land_heap[0][1]} overdue")
        if s.phase == "EVENTS" and block.land_scheduled_wo != (block.land_heap[0][1] if block.land_heap else None):
            _fail("INV19", f"{block_id}: landside completion event not held by the head batch")
    # INV08/INV13: vessel progress counters.
    for vessel_id, v in s.vessels.items():
        record = catalog.vessel_by_id[vessel_id]
        rolled = len(v.rolled_over_container_ids)
        if not (0 <= v.discharge_completed <= v.discharge_started <= record.discharge_move_count
                and 0 <= v.loads_completed <= v.loads_started
                and v.loads_started + rolled <= record.load_move_count):
            _fail("INV08", f"{vessel_id} progress counters inconsistent")
        if kernel.remaining_moves(vessel_id) < 0:
            _fail("INV08", f"{vessel_id} negative remaining work")
        if v.phase in ("DEPARTURE_PREP", "DEPARTED"):
            if v.discharge_completed != record.discharge_move_count \
                    or v.loads_completed + rolled != record.load_move_count:
                _fail("INV13", f"{vessel_id} left handling with unfinished work")


def _full(kernel) -> None:
    catalog, s = kernel.catalog, kernel.state
    # Work orders, reservations and the landside queues (INV08, INV15, INV17).
    reserved_by_block: dict[str, float] = {}
    landside_by_block: dict[str, set[str]] = {}
    for work_order_id, wo in s.work_orders.items():
        if wo.status != "IN_PROGRESS":
            _fail("INV15", f"{work_order_id} active in status {wo.status}")
        progress = kernel.work_order_progress(wo)
        if progress < -1e-6 or progress > wo.move_count + 1e-6:
            _fail("INV08", f"{work_order_id} progress {progress} outside [0, {wo.move_count}]")
        if wo.operation_type in SHIP_SIDE:
            if s.cranes[wo.crane_id].current_work_order_id != work_order_id:
                _fail("INV02", f"{work_order_id}: crane {wo.crane_id} not on this batch")
        else:
            landside_by_block.setdefault(wo.block_id, set()).add(work_order_id)
        if wo.operation_type in ("DISCHARGE", "GATE_IN"):
            reserved_by_block[wo.block_id] = reserved_by_block.get(wo.block_id, 0.0) + wo.planned_teu
    for block_id, block in s.blocks.items():
        if any(t < 0 for t in block.reservations.values()):
            _fail("INV08", f"{block_id} negative reservation")
        for work_order_id in block.reservations:
            wo = s.work_orders.get(work_order_id)
            if wo is None or wo.block_id != block_id or wo.operation_type not in ("DISCHARGE", "GATE_IN"):
                _fail("INV17", f"{block_id} reservation {work_order_id} has no open inbound batch")
        if abs(block.reserved_teu - reserved_by_block.get(block_id, 0.0)) > TEU_TOL:
            _fail("INV17", f"{block_id} reserved {block.reserved_teu} != open inbound batches "
                           f"{reserved_by_block.get(block_id, 0.0)}")
        if {wid for _, wid in block.land_heap} != landside_by_block.get(block_id, set()):
            _fail("INV15", f"{block_id}: landside queue differs from its in-progress landside batches")
    occupied = {b: 0.0 for b in s.blocks}
    counts = {b: 0 for b in s.blocks}
    claimed: dict[str, list[int]] = {}
    for c in catalog.containers:
        i = c.index
        status, kind, location_id = s.c_status[i], s.c_loc_kind[i], s.c_loc_id[i]
        # INV05: one valid location consistent with the status.
        if STATUS_LOCATION_KIND.get(status) != kind:
            _fail("INV05", f"{c.container_id}: status {status} at location kind {kind}",
                  code="DUPLICATE_PHYSICAL_LOCATION")
        if kind == "YARD_BLOCK":
            if location_id not in occupied:
                _fail("INV05", f"{c.container_id} in unknown block {location_id}")
            occupied[location_id] += c.size_teu
            counts[location_id] += 1
        elif kind == "VESSEL":
            expected = c.origin_vessel_id if status in ("EXPECTED_BY_VESSEL", "ABOARD_ARRIVED_VESSEL") \
                else c.destination_vessel_id
            if location_id != expected:
                _fail("INV05", f"{c.container_id} aboard {location_id}, expected {expected}")
            vessel = s.vessels.get(location_id)
            if vessel is not None:
                arrived = vessel.phase != "NOT_ARRIVED"
                if (status == "EXPECTED_BY_VESSEL") == arrived:
                    _fail("INV05", f"{c.container_id} {status} but {location_id} is {vessel.phase}")
                if status == "ABOARD_ARRIVED_VESSEL" and vessel.phase == "DEPARTED":
                    _fail("INV05", f"{c.container_id} aboard departed inbound vessel (orphaned cargo)")
                if status == "LOADED" and vessel.phase == "DEPARTED":
                    _fail("INV05", f"{c.container_id} LOADED on departed vessel {location_id}")
                if status == "DEPARTED_BY_VESSEL" and vessel.phase != "DEPARTED":
                    _fail("INV05", f"{c.container_id} departed with {location_id} still {vessel.phase}")
        elif kind == "TRANSFER":
            wo = s.work_orders.get(location_id)
            if wo is None or i not in wo.container_indices or s.c_claim[i] != location_id:
                _fail("INV15", f"{c.container_id} in TRANSFER {location_id} without its in-progress batch")
        elif kind == "GATE" and location_id != catalog.gate_id:
            _fail("INV05", f"{c.container_id} at unknown gate {location_id}")
        # INV09: loaded/loading only for the destination, never before availability (ledger replay
        # checks the order); flow rules for release/load.
        if status in ("LOADING", "LOADED", "DEPARTED_BY_VESSEL") and c.cargo_flow == "import":
            _fail("INV09", f"import {c.container_id} is {status}")
        if status in ("RETRIEVING_TO_LANDSIDE", "RELEASED_TO_LANDSIDE") and c.cargo_flow != "import":
            _fail("INV09", f"{c.cargo_flow} {c.container_id} released to landside")
        if status in ("RETRIEVING_TO_LANDSIDE", "RELEASED_TO_LANDSIDE") and not s.c_pickup_due[i]:
            _fail("INV09", f"{c.container_id} released before its pickup request")
        if s.c_claim[i] is not None:
            claimed.setdefault(s.c_claim[i], []).append(i)
    # INV06: cached occupancy equals inventory.
    for block_id, block in s.blocks.items():
        if abs(block.occupied_teu - occupied[block_id]) > TEU_TOL or block.occupied_count != counts[block_id]:
            _fail("INV06", f"{block_id}: cache {block.occupied_teu} TEU/{block.occupied_count} != inventory "
                           f"{occupied[block_id]}/{counts[block_id]}", code="INVENTORY_CONSERVATION_FAILURE")
    # INV15/INV11: claims exactly the members of in-progress batches; counters match statuses.
    for work_order_id, wo in s.work_orders.items():
        if sorted(claimed.get(work_order_id, [])) != sorted(wo.container_indices):
            _fail("INV15", f"{work_order_id} claims differ from its members")
    if set(claimed) - set(s.work_orders):
        _fail("INV15", f"claims by non-active work orders {sorted(set(claimed) - set(s.work_orders))[:3]}")
    for vessel_id, v in s.vessels.items():
        record = catalog.vessel_by_id[vessel_id]
        discharged = sum(1 for _g, members in record.discharge_groups for i in members
                         if s.c_status[i] not in ("EXPECTED_BY_VESSEL", "ABOARD_ARRIVED_VESSEL", "DISCHARGING"))
        loaded = sum(1 for i in record.load_container_indices if s.c_status[i] in ("LOADED", "DEPARTED_BY_VESSEL"))
        if discharged != v.discharge_completed or loaded != v.loads_completed:
            _fail("INV11", f"{vessel_id}: counters {v.discharge_completed}/{v.loads_completed} != statuses "
                           f"{discharged}/{loaded}")
    # Dispatch indexes re-derived from statuses (no fictitious availability).
    ready_expected: dict[str, set[int]] = {}
    for c in catalog.containers:
        i = c.index
        if s.c_status[i] == "IN_YARD" and s.c_claim[i] is None and c.destination_vessel_id in s.vessels \
                and not s.c_rolled[i] and s.vessels[c.destination_vessel_id].phase != "DEPARTED":
            ready_expected.setdefault(c.destination_vessel_id, set()).add(i)
    ready_actual = {vid: {i for members in by_key.values() for i in members}
                    for vid, by_key in s.load_ready.items() if by_key}
    if {k: v for k, v in ready_expected.items() if v} != ready_actual:
        _fail("INV09", "load-ready index differs from yard inventory")
    releasable_expected = {c.index for c in catalog.containers
                           if s.c_status[c.index] == "IN_YARD" and s.c_pickup_due[c.index]
                           and c.cargo_flow == "import"}
    releasable_actual = set()
    for block_id, members in s.releasable.items():
        for i in members:
            if s.c_status[i] != "IN_YARD" or not s.c_pickup_due[i] or s.c_loc_id[i] != block_id:
                _fail("INV09", f"{catalog.containers[i].container_id} queued for release but not due in {block_id}")
            releasable_actual.add(i)
    if releasable_actual != releasable_expected:
        _fail("INV09", "release queue differs from due imports in the yard")
    for block_id, block in s.blocks.items():
        active = [w for w in s.work_orders.values() if w.operation_type == "GATE_OUT" and w.block_id == block_id]
        if len(active) > 1 or (active[0].work_order_id if active else None) != block.active_release_wo:
            _fail("INV15", f"{block_id}: release admission violated ({[w.work_order_id for w in active]})")
    for members in s.gate_queue.values():
        for i in members:
            if s.c_status[i] != "AT_GATE":
                _fail("INV05", f"{catalog.containers[i].container_id} queued at gate but {s.c_status[i]}")
    # INV19 (+INV16 via replay audit): ledger order and transition indices.
    if s.ledger:
        previous_seq, previous_time = 0, -1.0
        last_index: dict[str, int] = {}
        for record in s.ledger:
            if record[L_SEQ] <= previous_seq or record[L_TIME] < previous_time - TIME_TOL:
                _fail("INV19", f"ledger order broken at sequence {record[L_SEQ]}")
            previous_seq, previous_time = record[L_SEQ], record[L_TIME]
            if record[L_CLASS] == PHYSICAL:
                cid = record[4]
                if record[L_TINDEX] != last_index.get(cid, 0) + 1:
                    _fail("INV11", f"{cid} transition index {record[L_TINDEX]} not consecutive")
                last_index[cid] = record[L_TINDEX]


def shared_mutable_objects(a, b) -> list[str]:
    """INV20 helper: names of mutable containers reachable from both states (should be empty)."""
    seen_a: dict[int, str] = {}

    def walk(obj, path, out):
        if isinstance(obj, (list, dict, set)) or hasattr(obj, "__dataclass_fields__"):
            if id(obj) in out:
                return
            if isinstance(obj, (list, dict, set)) or not getattr(type(obj), "__dataclass_params__").frozen:
                out[id(obj)] = path
            children = (obj.items() if isinstance(obj, dict) else
                        enumerate(obj) if isinstance(obj, (list, set)) else
                        ((f, getattr(obj, f)) for f in obj.__dataclass_fields__))
            for key, child in children:
                if isinstance(obj, set):
                    child = key
                walk(child, f"{path}.{key}", out)

    walk(a, "state", seen_a)
    seen_b: dict[int, str] = {}
    walk(b, "state", seen_b)
    return sorted(seen_a[i] for i in set(seen_a) & set(seen_b))


__all__ = ["check", "shared_mutable_objects"]
