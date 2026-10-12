"""Mutable execution state ``itp_state_v1`` (unified data contract §8).

All mutable facts live in one ``KernelState``. Each fact has exactly one owner
(spec §4); cached counters (block occupancy, vessel progress counters) carry a
checkable consistency relationship enforced by the invariants.

* Per-container facts are flat lists indexed by the catalog's container index
  (``status``, location kind/id, claiming work order, times, flags). A clone copies
  them with ``list(...)``: one C-level copy per list, no per-container objects.
* Vessels, cranes, blocks and active work orders are small records with an
  explicit ``copy()`` that also copies their nested dicts.
* Append-only logs (ledger, kernel event log, decision log, completed work
  orders, blocking episodes) hold immutable tuples; a clone copies the list of
  references, never the records.
* The event queue is a list of immutable tuples (``events.py``).

There are no generators, closures, file handles, ``MappingProxyType``, policies
or models in the state, so ``to_dict()`` / ``from_dict()`` round-trip it as JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

STATE_SCHEMA_VERSION = "itp_state_v1"

# Vessel vocabularies (data contract §8).
VESSEL_PHASES = ("NOT_ARRIVED", "WAITING", "BERTHING_PREP", "HANDLING", "DEPARTURE_PREP", "DEPARTED")
OCCUPYING_PHASES = ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP")
VISIBILITY = ("HIDDEN", "ANNOUNCED", "ARRIVED")
VESSEL_PHASE_TRANSITIONS = {
    "NOT_ARRIVED": ("WAITING",),
    "WAITING": ("BERTHING_PREP",),
    "BERTHING_PREP": ("HANDLING",),
    "HANDLING": ("DEPARTURE_PREP",),
    "DEPARTURE_PREP": ("DEPARTED",),
    "DEPARTED": (),
}

# Crane vocabularies: Project 01 CraneStatus values plus activity (data contract §5, §8).
CRANE_ACTIVITY = ("IDLE", "PRODUCTIVE", "BLOCKED")
CRANE_BLOCK_REASONS = ("VESSEL_NOT_READY", "YARD_CAPACITY", "CARGO_UNAVAILABLE", "NO_REMAINING_WORK")

# Work orders: Project 01 OperationType / OperationTaskStatus values (data contract §9).
WORK_ORDER_TYPES = ("DISCHARGE", "LOAD", "GATE_IN", "GATE_OUT")
SHIP_SIDE = ("DISCHARGE", "LOAD")
INBOUND_TO_YARD = ("DISCHARGE", "GATE_IN")

EPISODE_STATUSES = ("RUNNING", "COMPLETED", "TRUNCATED_DRAIN_LIMIT", "DEADLOCK", "FAILED")


@dataclass
class VesselState:
    vessel_id: str
    visibility: str = "HIDDEN"
    phase: str = "NOT_ARRIVED"
    slot_index: int | None = None
    berth_position_m: float | None = None
    berth_start_time_min: float | None = None
    handling_start_time_min: float | None = None
    handling_end_time_min: float | None = None
    departure_time_min: float | None = None
    load_wait_deadline_min: float | None = None
    load_wait_generation: int = 0
    rolled_over_container_ids: tuple[str, ...] = ()
    # Dispatch cursors and cached progress counters (checked by invariants).
    discharge_cursor: dict[str, int] = field(default_factory=dict)  # group -> next index in group list
    discharge_started: int = 0
    discharge_completed: int = 0
    loads_started: int = 0
    loads_completed: int = 0
    handling_completion_scheduled: bool = False
    # Accumulators (minutes, moves) explaining realized versus nominal service.
    acc: dict[str, float] = field(default_factory=dict)

    def copy(self) -> "VesselState":
        clone = VesselState(**{f.name: getattr(self, f.name) for f in fields(self)})
        clone.discharge_cursor = dict(self.discharge_cursor)
        clone.acc = dict(self.acc)
        return clone

    @property
    def completed_moves(self) -> int:
        return self.discharge_completed + self.loads_completed


@dataclass
class CraneState:
    crane_id: str
    status: str = "available"  # CraneStatus value
    assigned_vessel_id: str | None = None
    activity: str = "IDLE"
    blocked_reason: str | None = None
    current_work_order_id: str | None = None
    rate_moves_per_hour: float = 0.0
    idle_min: float = 0.0
    productive_min: float = 0.0
    blocked_min_by_reason: dict[str, float] = field(default_factory=dict)
    moves_completed: int = 0
    rate_shortfall_moves: float = 0.0
    transport_shortfall_moves: float = 0.0
    yard_shortfall_moves: float = 0.0
    activity_since_min: float = 0.0

    def copy(self) -> "CraneState":
        clone = CraneState(**{f.name: getattr(self, f.name) for f in fields(self)})
        clone.blocked_min_by_reason = dict(self.blocked_min_by_reason)
        return clone


@dataclass
class BlockState:
    block_id: str
    status: str = "open"  # YardBlockStatus value
    reservations: dict[str, float] = field(default_factory=dict)  # work_order_id -> TEU
    occupied_teu: float = 0.0
    occupied_count: int = 0
    blocked_teu: float = 0.0  # 0.0 in v1
    teu_minutes: float = 0.0
    peak_occupied_teu: float = 0.0
    busy_min: float = 0.0
    handled_moves: float = 0.0
    # Landside processor-sharing bookkeeping (spec §5.3): every landside batch of the block runs
    # at the same per-flow rate ``land_rate``; ``land_v`` integrates that rate (moves per flow).
    # A landside batch started at virtual progress v0 with m moves completes when land_v = v0 + m.
    land_rate: float = 0.0
    land_v: float = 0.0
    land_heap: list = field(default_factory=list)  # heap of (target land_v, work_order_id)
    land_scheduled_wo: str | None = None           # the one landside batch holding a completion event
    active_release_wo: str | None = None           # release admission: one GATE_OUT batch per block

    def copy(self) -> "BlockState":
        clone = BlockState(**{f.name: getattr(self, f.name) for f in fields(self)})
        clone.reservations = dict(self.reservations)
        clone.land_heap = list(self.land_heap)
        return clone

    @property
    def reserved_teu(self) -> float:
        return float(sum(self.reservations.values()))


@dataclass
class WorkOrderState:
    work_order_id: str
    operation_type: str
    container_group_id: str
    container_indices: tuple[int, ...]
    move_count: int
    planned_teu: float
    vessel_id: str | None
    crane_id: str | None
    source: tuple[str, str | None]       # (location kind, location id)
    destination: tuple[str, str | None]
    block_id: str                        # yard block whose handling capacity the batch uses
    status: str = "IN_PROGRESS"
    completed_moves: float = 0.0     # ship-side: settled fluid progress; landside: see land_v_start
    land_v_start: float = 0.0        # landside only: block.land_v when the batch started
    rate_moves_per_hour: float = 0.0
    demand_moves_per_hour: float = 0.0
    crane_rate_moves_per_hour: float = 0.0
    rate_generation: int = 0
    scheduled_generation: int = 0   # generation whose completion event is in the queue (0 = none)
    created_time_min: float = 0.0
    start_time_min: float = 0.0
    completion_time_min: float | None = None
    decision_id: str | None = None

    def copy(self) -> "WorkOrderState":
        return WorkOrderState(**{f.name: getattr(self, f.name) for f in fields(self)})


@dataclass(frozen=True)
class PendingDecision:
    """A decision the kernel needs from a policy before it can continue (one at a time)."""

    kind: str                       # BERTH | CRANE | YARD
    decision_id: str
    time_min: float
    request: tuple = ()             # YARD: (op, source_kind, source_id, group, container indices, crane, vessel, key)


@dataclass
class KernelState:
    now_min: float
    phase: str
    berth_epoch: bool
    same_time_cycles: int
    cycles: int
    next_event_seq: int
    next_ledger_seq: int
    next_work_order_seq: int
    next_decision_seq: int
    capacity_version: int
    events: list
    vessels: dict
    reveal_order: list
    cranes: dict
    blocks: dict
    work_orders: dict
    completed_work_orders: list
    # Per-container flat arrays.
    c_status: list
    c_loc_kind: list
    c_loc_id: list
    c_claim: list
    c_tindex: list
    c_entry_time: list
    c_release_time: list
    c_rolled: list
    c_pickup_due: list
    c_gate_since: list
    # Dispatch indexes (derived, maintained incrementally; invariants re-derive them).
    load_ready: dict          # vessel_id -> {"group|block": [container indices sorted]}
    releasable: dict          # block_id -> [due import indices in the block, FIFO]
    gate_queue: dict          # group_id -> [container indices]
    yard_blocked: dict        # request key -> capacity_version at the last NO_ACTION
    pending: PendingDecision | None
    status: str
    status_reason: str | None
    status_details: dict
    kpi: dict
    block_episodes: list      # (crane_id, vessel_id, reason, start, end)
    open_block_episodes: dict  # crane_id -> (vessel_id, reason, start)
    ledger: list | None
    event_log: list | None
    decision_log: list
    stale_events_discarded: int

    LIST_FIELDS = ("events", "reveal_order", "completed_work_orders", "c_status", "c_loc_kind",
                   "c_loc_id", "c_claim", "c_tindex", "c_entry_time", "c_release_time", "c_rolled",
                   "c_pickup_due", "c_gate_since", "block_episodes", "decision_log")
    RECORD_FIELDS = ("vessels", "cranes", "blocks", "work_orders")

    def clone(self, *, keep_logs: bool = True) -> "KernelState":
        """Independent copy: no mutable object is shared with ``self`` (INV20)."""
        values: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in self.RECORD_FIELDS:
                value = {key: record.copy() for key, record in value.items()}
            elif f.name in self.LIST_FIELDS:
                value = list(value)
            elif f.name in ("ledger", "event_log"):
                value = list(value) if (value is not None and keep_logs) else None
            elif f.name == "load_ready":
                value = {vid: {k: list(v) for k, v in by_key.items()} for vid, by_key in value.items()}
            elif f.name in ("releasable", "gate_queue"):
                value = {k: list(v) for k, v in value.items()}
            elif f.name in ("yard_blocked", "kpi", "open_block_episodes"):
                value = dict(value)
            elif f.name == "status_details":
                value = _deep_plain(value)
            values[f.name] = value
        return KernelState(**values)

    # ------------------------------------------------------------------ plain-data form
    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"schema_version": STATE_SCHEMA_VERSION}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in self.RECORD_FIELDS:
                value = {key: _record_dict(record) for key, record in sorted(value.items())}
            elif f.name == "pending":
                value = None if value is None else {
                    "kind": value.kind, "decision_id": value.decision_id, "time_min": value.time_min,
                    "request": _deep_plain(value.request)}
            else:
                value = _deep_plain(value)
            out[f.name] = value
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KernelState":
        if data.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError(f"state schema must be {STATE_SCHEMA_VERSION}")
        values: dict[str, Any] = {}
        record_types = {"vessels": VesselState, "cranes": CraneState, "blocks": BlockState,
                        "work_orders": WorkOrderState}
        for f in fields(cls):
            value = data[f.name]
            if f.name in record_types:
                value = {key: _record_from(record_types[f.name], rec) for key, rec in value.items()}
            elif f.name == "events":
                value = [(e[0], e[1], e[2], e[3], e[4], tuple(e[5]), e[6]) for e in value]
            elif f.name in ("completed_work_orders", "block_episodes", "decision_log"):
                value = [_tuplify(v) for v in value]
            elif f.name in ("ledger", "event_log"):
                value = None if value is None else [_tuplify(v) for v in value]
            elif f.name == "pending":
                value = None if value is None else PendingDecision(
                    value["kind"], value["decision_id"], value["time_min"], _tuplify(value["request"]))
            elif f.name == "open_block_episodes":
                value = {k: tuple(v) for k, v in value.items()}
            values[f.name] = value
        return cls(**values)


_RECORD_TUPLE_FIELDS = {"rolled_over_container_ids", "container_indices", "source", "destination"}


def _record_dict(record: Any) -> dict[str, Any]:
    return {f.name: _deep_plain(getattr(record, f.name)) for f in fields(record)}


def _record_from(kind: type, data: dict[str, Any]) -> Any:
    values = {}
    for f in fields(kind):
        value = data[f.name]
        if f.name in _RECORD_TUPLE_FIELDS and value is not None:
            value = tuple(value)
        elif f.name == "land_heap":
            value = [tuple(entry) for entry in value]
        values[f.name] = value
    return kind(**values)


def _deep_plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_deep_plain(v) for v in value]
    return value


def _tuplify(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuplify(v) for v in value)
    if isinstance(value, dict):
        return {k: _tuplify(v) for k, v in value.items()}
    return value


__all__ = [
    "BlockState", "CRANE_BLOCK_REASONS", "CraneState", "EPISODE_STATUSES", "INBOUND_TO_YARD",
    "KernelState", "OCCUPYING_PHASES", "PendingDecision", "SHIP_SIDE", "STATE_SCHEMA_VERSION",
    "VESSEL_PHASES", "VESSEL_PHASE_TRANSITIONS", "VesselState", "WORK_ORDER_TYPES", "WorkOrderState",
]
