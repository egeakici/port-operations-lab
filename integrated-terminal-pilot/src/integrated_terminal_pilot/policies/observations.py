"""Immutable decision-time observations for the primitive crane and yard policies.

An observation is what the Step 4 kernel exposes to an online policy at one
decision point (integration specification §7 and §10). It is never the Step 2
scenario document and never the mutable kernel state:

* Every record is a frozen dataclass of primitives and tuples. Collections are
  canonicalised (sorted by stable id) at construction, so semantically equal
  observations compare equal and their record order cannot influence a policy.
* View types declare only decision-relevant fields. They have no attribute for
  hidden information (future arrivals, gate-in or pickup times, weights,
  scenario id, seed or fingerprints, spec §10), so a policy cannot read it.
* Construction validates internal consistency and raises
  ``ObservationError`` (outcome class ``INVALID_INPUT``). A malformed
  observation never reaches a policy and is never turned into a decision.

``from_scenario_*`` helpers copy the allowed static fields of Step 2 records;
the dynamic fields (status, assignment, occupancy, reservations) must come from
the caller (Step 4: kernel state; Step 3 tests: hand-built snapshots).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

# Copies of two itp_scenario_v1 tables (scenarios.models). Importing that package would load
# the generator and with it SimPy/gymnasium; policies must stay dependency-free.
# test_policy_contract_tables_match_scenario_schema pins them equal.
ID_PATTERNS = {
    "vessel": re.compile(r"^V\d{3}$"),
    "crane": re.compile(r"^QC\d{2}$"),
    "block": re.compile(r"^B\d{2}$"),
    "gate": re.compile(r"^G\d{2}$"),
    "container": re.compile(r"^CNT-\d{6}$"),
    "group": re.compile(r"^GRP-\d{4}$"),
}
TEU_BY_SIZE = {"20_ft": 1.0, "40_ft": 2.0}

CRANE_OBSERVATION_SCHEMA = "itp_crane_obs_v1"
YARD_OBSERVATION_SCHEMA = "itp_yard_obs_v1"

# Vocabularies (unified data contract §8; Project 01 enums by value).
VESSEL_PHASES = ("NOT_ARRIVED", "WAITING", "BERTHING_PREP", "HANDLING", "DEPARTURE_PREP", "DEPARTED")
BERTHED_PHASES = ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP")
CRANE_SERVICE_PHASES = ("BERTHING_PREP", "HANDLING")  # data contract §5 "Allocation"
CRANE_STATUSES = ("available", "assigned", "operating", "failed", "maintenance")  # CraneStatus
CRANE_ACTIVITIES = ("IDLE", "PRODUCTIVE", "BLOCKED")
YARD_BLOCK_STATUSES = ("open", "closed", "maintenance")  # YardBlockStatus
YARD_CAPABILITIES = ("empty", "general", "hazardous", "reefer_power")  # YardCapability
CONTAINER_SIZES = tuple(sorted(TEU_BY_SIZE))
CARGO_FLOWS = ("export", "import", "transshipment")
# Yard decisions exist only for discharge and gate-receive batches (spec §6, §7 DISPATCH);
# load and landside-release sources are fixed by container location.
YARD_OPERATION_SOURCE = {"DISCHARGE": "VESSEL", "GATE_IN": "GATE"}
YARD_OPERATION_FLOWS = {"DISCHARGE": ("import", "transshipment"), "GATE_IN": ("export",)}
YARD_OPERATION_STATUS = {"DISCHARGE": "ABOARD_ARRIVED_VESSEL", "GATE_IN": "AT_GATE"}
WORK_ORDER_PATTERN = r"^WO-\d{6}$"
TOL = 1e-9


class ObservationError(ValueError):
    """The observation is malformed (outcome class ``INVALID_INPUT``)."""

    code = "INVALID_INPUT"


def _fail(message: str) -> None:
    raise ObservationError(message)


def _finite(value: Any, where: str, *, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(f"{where} must be a finite number.")
    if minimum is not None and value < minimum:
        _fail(f"{where} must be >= {minimum}.")


def _id(value: Any, kind: str, where: str) -> None:
    if not isinstance(value, str) or not ID_PATTERNS[kind].match(value):
        _fail(f"{where}: invalid {kind} id {value!r}.")


def _set(obj: Any, name: str, value: Any) -> None:
    object.__setattr__(obj, name, value)


def _id_tuple(values: Any, kind: str, where: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        _fail(f"{where} must be a collection of ids.")
    result = tuple(sorted(values))
    for value in result:
        _id(value, kind, where)
    if len(set(result)) != len(result):
        _fail(f"{where} contains duplicate ids.")
    return result


def _unique(records: tuple[Any, ...], key: str, where: str) -> None:
    ids = [getattr(r, key) for r in records]
    if len(ids) != len(set(ids)):
        _fail(f"{where}: duplicate {key}.")


def _canonical(records: Any, kind: type, key: str, where: str) -> tuple[Any, ...]:
    if isinstance(records, (str, bytes, dict)) or not hasattr(records, "__iter__"):
        _fail(f"{where} must be a collection of {kind.__name__}.")
    result = tuple(records)
    if not all(isinstance(r, kind) for r in result):
        _fail(f"{where} must contain only {kind.__name__} records.")
    _unique(result, key, where)
    return tuple(sorted(result, key=lambda r: getattr(r, key)))


# --------------------------------------------------------------------------- crane

@dataclass(frozen=True)
class CraneVesselView:
    """A visible vessel as seen by the crane policy (no arrival schedule, no cargo list)."""

    vessel_id: str
    phase: str
    length_m: float
    berth_position_m: float | None
    berth_start_time_min: float | None
    max_cranes: int
    remaining_moves: int
    assigned_crane_ids: tuple[str, ...] = ()
    priority: int = 2

    def __post_init__(self) -> None:
        where = f"vessel {self.vessel_id!r}"
        _id(self.vessel_id, "vessel", where)
        if self.phase not in VESSEL_PHASES:
            _fail(f"{where}: unknown phase {self.phase!r}.")
        _finite(self.length_m, f"{where}.length_m", minimum=TOL)
        if isinstance(self.max_cranes, bool) or not isinstance(self.max_cranes, int) or self.max_cranes < 1:
            _fail(f"{where}.max_cranes must be an integer >= 1.")
        if isinstance(self.remaining_moves, bool) or not isinstance(self.remaining_moves, int) \
                or self.remaining_moves < 0:
            _fail(f"{where}.remaining_moves must be a non-negative integer.")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int) or not 1 <= self.priority <= 3:
            _fail(f"{where}.priority must be 1..3.")
        _set(self, "assigned_crane_ids", _id_tuple(self.assigned_crane_ids, "crane",
                                                   f"{where}.assigned_crane_ids"))
        berthed = self.phase in BERTHED_PHASES
        if berthed:
            _finite(self.berth_position_m, f"{where}.berth_position_m", minimum=0.0)
            _finite(self.berth_start_time_min, f"{where}.berth_start_time_min", minimum=0.0)
        elif self.berth_position_m is not None or self.berth_start_time_min is not None:
            _fail(f"{where}: only berthed vessels have a berth position and start time.")
        if self.assigned_crane_ids and self.phase not in CRANE_SERVICE_PHASES:
            _fail(f"{where}: cranes can be held only in phases {CRANE_SERVICE_PHASES}.")
        if len(self.assigned_crane_ids) > self.max_cranes:
            _fail(f"{where}: {len(self.assigned_crane_ids)} cranes exceed max_cranes {self.max_cranes}.")

    @property
    def spare_crane_capacity(self) -> int:
        return self.max_cranes - len(self.assigned_crane_ids)

    @property
    def crane_eligible(self) -> bool:
        """Data contract §5 "Allocation": berthed in BERTHING_PREP/HANDLING, work left, below max_cranes."""
        return (self.phase in CRANE_SERVICE_PHASES and self.remaining_moves > 0
                and self.spare_crane_capacity > 0)


@dataclass(frozen=True)
class CraneView:
    """A quay crane's current state. Future failures or repairs are never exposed."""

    crane_id: str
    status: str
    assigned_vessel_id: str | None
    nominal_moves_per_hour: float
    compatible_vessel_ids: tuple[str, ...] | None = None  # None = all vessels (data contract §5)
    activity: str | None = None

    def __post_init__(self) -> None:
        where = f"crane {self.crane_id!r}"
        _id(self.crane_id, "crane", where)
        if self.status not in CRANE_STATUSES:
            _fail(f"{where}: unknown status {self.status!r}.")
        if self.assigned_vessel_id is not None:
            _id(self.assigned_vessel_id, "vessel", f"{where}.assigned_vessel_id")
        if self.status in ("assigned", "operating") and self.assigned_vessel_id is None:
            _fail(f"{where}: status {self.status} requires an assigned vessel.")
        if self.status in ("available", "failed", "maintenance") and self.assigned_vessel_id is not None:
            _fail(f"{where}: status {self.status} cannot hold a vessel assignment.")
        if self.activity is not None and self.activity not in CRANE_ACTIVITIES:
            _fail(f"{where}: unknown activity {self.activity!r}.")
        if self.assigned_vessel_id is None and self.activity not in (None, "IDLE"):
            _fail(f"{where}: an unassigned crane can only be IDLE.")
        _finite(self.nominal_moves_per_hour, f"{where}.nominal_moves_per_hour", minimum=TOL)
        if self.compatible_vessel_ids is not None:
            _set(self, "compatible_vessel_ids",
                 _id_tuple(self.compatible_vessel_ids, "vessel", f"{where}.compatible_vessel_ids"))

    def can_serve(self, vessel_id: str) -> bool:
        return self.compatible_vessel_ids is None or vessel_id in self.compatible_vessel_ids

    @classmethod
    def from_scenario_crane(cls, record: dict[str, Any], *, status: str = "available",
                            assigned_vessel_id: str | None = None,
                            activity: str | None = None) -> "CraneView":
        """Static fields from a Step 2 crane record; state supplied by the caller."""
        compatible = record["compatible_vessel_ids"]
        return cls(crane_id=record["crane_id"], status=status, assigned_vessel_id=assigned_vessel_id,
                   nominal_moves_per_hour=float(record["nominal_moves_per_hour"]),
                   compatible_vessel_ids=None if compatible is None else tuple(compatible),
                   activity=activity)


@dataclass(frozen=True)
class CraneObservation:
    """Input of a CRANE decision (spec §7 step 2)."""

    time_min: float
    vessels: tuple[CraneVesselView, ...]
    cranes: tuple[CraneView, ...]
    decision_id: str | None = None
    schema_version: str = field(default=CRANE_OBSERVATION_SCHEMA)

    def __post_init__(self) -> None:
        if self.schema_version != CRANE_OBSERVATION_SCHEMA:
            _fail(f"Crane observation schema must be {CRANE_OBSERVATION_SCHEMA}.")
        _finite(self.time_min, "time_min", minimum=0.0)
        if self.decision_id is not None and (not isinstance(self.decision_id, str) or not self.decision_id):
            _fail("decision_id must be a non-empty string or None.")
        _set(self, "vessels", _canonical(self.vessels, CraneVesselView, "vessel_id", "vessels"))
        _set(self, "cranes", _canonical(self.cranes, CraneView, "crane_id", "cranes"))
        vessels = {v.vessel_id: v for v in self.vessels}
        crane_ids = {c.crane_id for c in self.cranes}
        held: dict[str, list[str]] = {vid: [] for vid in vessels}
        for crane in self.cranes:
            if crane.assigned_vessel_id is None:
                continue
            if crane.assigned_vessel_id not in vessels:
                _fail(f"crane {crane.crane_id} is assigned to vessel {crane.assigned_vessel_id}, "
                      "which is not in the observation.")
            if not crane.can_serve(crane.assigned_vessel_id):
                _fail(f"crane {crane.crane_id} is assigned to incompatible vessel {crane.assigned_vessel_id}.")
            held[crane.assigned_vessel_id].append(crane.crane_id)
        for vessel in self.vessels:
            unknown = sorted(set(vessel.assigned_crane_ids) - crane_ids)
            if unknown:
                _fail(f"vessel {vessel.vessel_id} lists unknown cranes {unknown}.")
            if tuple(sorted(held[vessel.vessel_id])) != vessel.assigned_crane_ids:
                _fail(f"vessel {vessel.vessel_id}: assigned_crane_ids {vessel.assigned_crane_ids} "
                      f"disagree with crane assignments {tuple(sorted(held[vessel.vessel_id]))}.")


# --------------------------------------------------------------------------- yard

@dataclass(frozen=True)
class YardContainerView:
    """One individually identified container of a yard request (no timing, weight or scenario id)."""

    container_id: str
    container_group_id: str
    container_size: str
    size_teu: float
    cargo_flow: str
    load_state: str
    is_reefer: bool
    is_hazardous: bool
    origin_vessel_id: str | None
    destination_vessel_id: str | None
    status: str

    def __post_init__(self) -> None:
        where = f"container {self.container_id!r}"
        _id(self.container_id, "container", where)
        _id(self.container_group_id, "group", f"{where}.container_group_id")
        if self.container_size not in TEU_BY_SIZE:
            _fail(f"{where}: unsupported container size {self.container_size!r}.")
        if self.size_teu != TEU_BY_SIZE[self.container_size]:
            _fail(f"{where}: size_teu {self.size_teu!r} != {TEU_BY_SIZE[self.container_size]} "
                  f"for {self.container_size}.")
        if self.cargo_flow not in CARGO_FLOWS:
            _fail(f"{where}: unknown cargo flow {self.cargo_flow!r}.")
        if self.load_state not in ("laden", "empty"):
            _fail(f"{where}: load_state must be laden or empty.")
        if not isinstance(self.is_reefer, bool) or not isinstance(self.is_hazardous, bool):
            _fail(f"{where}: is_reefer and is_hazardous must be booleans.")
        if self.load_state == "empty" and (self.is_reefer or self.is_hazardous):
            _fail(f"{where}: empty containers cannot be reefer or hazardous.")
        needs_origin = self.cargo_flow in ("import", "transshipment")
        needs_destination = self.cargo_flow in ("export", "transshipment")
        for value, needed, name in ((self.origin_vessel_id, needs_origin, "origin_vessel_id"),
                                    (self.destination_vessel_id, needs_destination,
                                     "destination_vessel_id")):
            if needed and value is None:
                _fail(f"{where}: {self.cargo_flow} requires {name}.")
            if not needed and value is not None:
                _fail(f"{where}: {self.cargo_flow} must not define {name}.")
            if value is not None:
                _id(value, "vessel", f"{where}.{name}")  # PRE_EPISODE cargo is already IN_YARD
        if self.origin_vessel_id is not None and self.origin_vessel_id == self.destination_vessel_id:
            _fail(f"{where}: origin and destination vessels must differ.")

    @property
    def required_capabilities(self) -> tuple[str, ...]:
        """Project 01 ``ContainerGroup.required_yard_capabilities`` by value."""
        if self.load_state == "empty":
            return ("empty",)
        required = {"general"}
        if self.is_reefer:
            required.add("reefer_power")
        if self.is_hazardous:
            required.add("hazardous")
        return tuple(sorted(required))

    @classmethod
    def from_scenario_container(cls, record: dict[str, Any], *, status: str) -> "YardContainerView":
        """Allowed fields of a Step 2 ContainerRecord; gate-in/pickup times and weight are dropped."""
        return cls(container_id=record["container_id"], container_group_id=record["container_group_id"],
                   container_size=record["container_size"], size_teu=float(record["size_teu"]),
                   cargo_flow=record["cargo_flow"], load_state=record["load_state"],
                   is_reefer=record["is_reefer"], is_hazardous=record["is_hazardous"],
                   origin_vessel_id=record["origin_vessel_id"],
                   destination_vessel_id=record["destination_vessel_id"], status=status)


@dataclass(frozen=True)
class YardRequest:
    """A discharge or gate-receive work order awaiting a destination block (one homogeneous batch).

    The batch is a processing convenience over explicit container ids (D15): one
    container group, sizes and cargo attributes identical, never split by the
    yard policy (spec §6: one destination block per batch).
    """

    work_order_id: str
    operation_type: str
    source_location_id: str
    containers: tuple[YardContainerView, ...]

    def __post_init__(self) -> None:
        where = f"request {self.work_order_id!r}"
        if not isinstance(self.work_order_id, str) or not re.match(WORK_ORDER_PATTERN, self.work_order_id):
            _fail(f"{where}: work_order_id must match WO-nnnnnn.")
        if self.operation_type not in YARD_OPERATION_SOURCE:
            _fail(f"{where}: yard decisions exist only for {tuple(YARD_OPERATION_SOURCE)} "
                  f"(got {self.operation_type!r}).")
        source_kind = YARD_OPERATION_SOURCE[self.operation_type]
        _id(self.source_location_id, "vessel" if source_kind == "VESSEL" else "gate",
            f"{where}.source_location_id")
        containers = _canonical(self.containers, YardContainerView, "container_id", f"{where}.containers")
        if not containers:
            _fail(f"{where}: a request needs at least one container.")
        _set(self, "containers", containers)
        first = containers[0]
        homogeneous = ("container_group_id", "container_size", "cargo_flow", "load_state",
                       "is_reefer", "is_hazardous", "origin_vessel_id", "destination_vessel_id")
        for c in containers[1:]:
            differing = [k for k in homogeneous if getattr(c, k) != getattr(first, k)]
            if differing:
                _fail(f"{where}: batch members must share one container group (D15); "
                      f"{c.container_id} differs in {differing}.")
        if first.cargo_flow not in YARD_OPERATION_FLOWS[self.operation_type]:
            _fail(f"{where}: {self.operation_type} cannot carry {first.cargo_flow} cargo.")
        expected_status = YARD_OPERATION_STATUS[self.operation_type]
        not_ready = [c.container_id for c in containers if c.status != expected_status]
        if not_ready:
            _fail(f"{where}: {self.operation_type} requires containers in {expected_status} "
                  f"(not yet in that state: {not_ready[:5]}).")
        if self.operation_type == "DISCHARGE" and first.origin_vessel_id != self.source_location_id:
            _fail(f"{where}: discharge cargo must come from its origin vessel {first.origin_vessel_id}.")

    @property
    def container_ids(self) -> tuple[str, ...]:
        return tuple(c.container_id for c in self.containers)

    @property
    def container_size(self) -> str:
        return self.containers[0].container_size

    @property
    def required_teu(self) -> float:
        return float(sum(c.size_teu for c in self.containers))

    @property
    def required_capabilities(self) -> tuple[str, ...]:
        return self.containers[0].required_capabilities


@dataclass(frozen=True)
class YardBlockView:
    """Block state at decision time. Storage (TEU) and handling (moves/h) are separate quantities."""

    block_id: str
    status: str
    capabilities: tuple[str, ...]
    allowed_sizes: tuple[str, ...]
    capacity_teu: float           # operating capacity (<= geometric x fill limit)
    occupied_teu: float
    reserved_teu: float
    blocked_teu: float = 0.0
    handling_capacity_moves_per_hour: float | None = None  # informational; not used by P_y
    transfer_point_x_m: float | None = None
    transfer_point_y_m: float | None = None

    def __post_init__(self) -> None:
        where = f"block {self.block_id!r}"
        _id(self.block_id, "block", where)
        if self.status not in YARD_BLOCK_STATUSES:
            _fail(f"{where}: unknown status {self.status!r}.")
        for name, vocab in (("capabilities", YARD_CAPABILITIES), ("allowed_sizes", CONTAINER_SIZES)):
            values = getattr(self, name)
            if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
                _fail(f"{where}.{name} must be a collection.")
            values = tuple(sorted(set(values)))
            if not values or any(v not in vocab for v in values):
                _fail(f"{where}.{name} must be a non-empty subset of {vocab}.")
            _set(self, name, values)
        _finite(self.capacity_teu, f"{where}.capacity_teu", minimum=TOL)
        for name in ("occupied_teu", "reserved_teu", "blocked_teu"):
            _finite(getattr(self, name), f"{where}.{name}", minimum=0.0)
        if self.occupied_teu + self.reserved_teu + self.blocked_teu > self.capacity_teu + TOL:
            _fail(f"{where}: occupied + reserved + blocked exceeds capacity_teu (DQ07).")
        if self.handling_capacity_moves_per_hour is not None:
            _finite(self.handling_capacity_moves_per_hour, f"{where}.handling_capacity_moves_per_hour",
                    minimum=TOL)
        for name in ("transfer_point_x_m", "transfer_point_y_m"):
            if getattr(self, name) is not None:
                _finite(getattr(self, name), f"{where}.{name}")

    @property
    def available_teu(self) -> float:
        """Spec §5.3 reservation test quantity: capacity - occupied - reserved - blocked."""
        return self.capacity_teu - self.occupied_teu - self.reserved_teu - self.blocked_teu

    @classmethod
    def from_scenario_block(cls, record: dict[str, Any], *, occupied_teu: float,
                            reserved_teu: float = 0.0, blocked_teu: float = 0.0,
                            status: str = "open") -> "YardBlockView":
        """Static fields of a Step 2 YardBlockRecord; occupancy and status supplied by the caller."""
        return cls(block_id=record["block_id"], status=status, capabilities=tuple(record["capabilities"]),
                   allowed_sizes=tuple(record["allowed_sizes"]), capacity_teu=float(record["capacity_teu"]),
                   occupied_teu=float(occupied_teu), reserved_teu=float(reserved_teu),
                   blocked_teu=float(blocked_teu),
                   handling_capacity_moves_per_hour=float(record["handling_capacity_moves_per_hour"]),
                   transfer_point_x_m=float(record["transfer_point_x_m"]),
                   transfer_point_y_m=float(record["transfer_point_y_m"]))


@dataclass(frozen=True)
class YardObservation:
    """Input of a yard destination decision for one request (spec §7 step 3, DISPATCH)."""

    time_min: float
    request: YardRequest
    blocks: tuple[YardBlockView, ...]
    decision_id: str | None = None
    schema_version: str = field(default=YARD_OBSERVATION_SCHEMA)

    def __post_init__(self) -> None:
        if self.schema_version != YARD_OBSERVATION_SCHEMA:
            _fail(f"Yard observation schema must be {YARD_OBSERVATION_SCHEMA}.")
        _finite(self.time_min, "time_min", minimum=0.0)
        if self.decision_id is not None and (not isinstance(self.decision_id, str) or not self.decision_id):
            _fail("decision_id must be a non-empty string or None.")
        if not isinstance(self.request, YardRequest):
            _fail("request must be a YardRequest.")
        blocks = _canonical(self.blocks, YardBlockView, "block_id", "blocks")
        if not blocks:
            _fail("A yard observation needs at least one block.")
        _set(self, "blocks", blocks)


__all__ = [
    "BERTHED_PHASES", "CRANE_OBSERVATION_SCHEMA", "CRANE_SERVICE_PHASES", "CRANE_STATUSES",
    "CraneObservation", "CraneVesselView", "CraneView", "ObservationError",
    "YARD_BLOCK_STATUSES", "YARD_OBSERVATION_SCHEMA", "YardBlockView", "YardContainerView",
    "YardObservation", "YardRequest",
]
