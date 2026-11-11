"""Immutable wire contracts. Structural acceptance is never physical PASS.

Canonical bytes: sorted keys, UTF-8, compact separators, floats normalized for
float-typed fields, ordered tuples preserved. Unknown fields/duplicate keys fail.
No implicit migrations, unit conversion, guessed geometry or production defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
import math
from types import UnionType
from typing import get_args, get_origin, get_type_hints

SCHEMA = "p04_contracts_v1"
ASSUMPTIONS = "p04_reference_point_constant_speed_proposed_v1"


@dataclass(frozen=True)
class ExecutionPermit:
    """Created by owner-manual lock verification, not by scenario metadata."""
    approved_payload_hash: str
    problem_hashes: tuple[str, ...]
    roles: tuple[str, ...]


class ContractError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        self.code, self.path, self.message = code, path, message
        super().__init__(f"{code} at {path}: {message}")


def require(condition, code, path, message):
    if not condition:
        raise ContractError(code, path, message)


def _typed(tp, value, path, decode=False):
    origin, args = get_origin(tp), get_args(tp)
    if origin is UnionType:
        for choice in args:
            try:
                return _typed(choice, value, path, decode)
            except ContractError:
                pass
        raise ContractError("TYPE", path, "no matching union variant")
    if tp is type(None):
        require(value is None, "TYPE", path, "expected null")
    elif origin is tuple:
        require(isinstance(value, (list, tuple)), "TYPE", path, "expected array")
        require(decode or type(value) is tuple, "IMMUTABILITY", path, "direct constructors require immutable tuples")
        require(len(args) == 2 and args[1] is Ellipsis, "TYPE", path, "unsupported tuple shape")
        return tuple(_typed(args[0], x, f"{path}[{i}]", decode) for i, x in enumerate(value))
    elif is_dataclass(tp):
        if decode:
            require(isinstance(value, dict), "TYPE", path, "expected object")
            names = {f.name for f in fields(tp)}
            require(set(value) == names, "FIELDS", path, f"expected exactly {sorted(names)}")
            hints = get_type_hints(tp)
            return tp(**{k: _typed(hints[k], v, path + "." + k, True) for k, v in value.items()})
        require(type(value) is tp, "TYPE", path, f"expected {tp.__name__}")
    elif tp is float:
        require(not isinstance(value, int) or abs(value) <= 2**53, "PRECISION", path, "integer cannot be represented losslessly as float")
        require(type(value) in (int, float) and math.isfinite(value), "FINITE_NUMBER", path, "finite number required, bool forbidden")
        return float(value)
    elif tp is int:
        require(type(value) is int, "TYPE", path, "integer required, bool forbidden")
    else:
        require(type(value) is tp, "TYPE", path, f"expected {tp.__name__}")
    return value


class Wire:
    def __post_init__(self):
        for key, tp in get_type_hints(type(self)).items():
            _typed(tp, getattr(self, key), key)

    def to_dict(self):
        def encode(tp, value):
            if isinstance(value, Wire):
                return value.to_dict()
            if isinstance(value, tuple):
                subtype = get_args(tp)[0]
                return [encode(subtype, v) for v in value]
            if tp is float and value is not None:
                return float(value)
            if get_origin(tp) is UnionType and float in get_args(tp) and value is not None:
                return float(value)
            return value
        hints = get_type_hints(type(self))
        return {f.name: encode(hints[f.name], getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_dict(cls, value):
        return _typed(cls, value, cls.__name__, True)

    def to_json(self):
        return canonical(self.to_dict()).decode("utf-8")

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(strict_json(text))

    @property
    def fingerprint(self):
        return digest(self.to_dict())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_json(text):
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, "DUPLICATE_KEY", k, "duplicate JSON member")
            out[k] = v
        return out
    def constant(x):
        raise ContractError("NONSTANDARD_JSON", "$", x)
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ContractError("JSON_SYNTAX", "$", str(exc)) from exc


@dataclass(frozen=True)
class ProblemMetadata(Wire):
    schema_version: str
    problem_type: str
    scenario_id: str
    family: str
    role: str
    seed_namespace: str
    seed: int
    origin: str
    assumptions_version: str
    source_project: str
    source_snapshot: str | None

    def __post_init__(self):
        super().__post_init__()
        require(self.schema_version == SCHEMA and self.problem_type == "QCSP_V1", "VERSION", "metadata", "unsupported schema/problem")
        require(self.role in {"development", "train", "validation", "test", "diagnostic"}, "ROLE", "metadata.role", "unsupported role")
        require(self.origin in {"TEST_FIXTURE_SYNTHETIC", "PROPOSED_SYNTHETIC", "OWNER_APPROVED_SYNTHETIC"}, "PROVENANCE", "metadata.origin", "empirical provenance not supported without a separate verified schema")
        require(self.seed >= 0 and bool(self.scenario_id.strip()) and bool(self.seed_namespace.strip()), "IDENTITY", "metadata", "nonempty identity/namespace and nonnegative seed required")
        require(bool(self.source_project.strip()) and (self.source_snapshot is None or (len(self.source_snapshot) in {40,64} and all(c in '0123456789abcdef' for c in self.source_snapshot))),"SOURCE_PROVENANCE","metadata.source_snapshot","unknown is null; provided commit/SHA256 must be correctly shaped")


@dataclass(frozen=True)
class VesselContext(Wire):
    vessel_id: str
    berth_id: str
    length_m: float
    berth_origin_m: float
    orientation: int
    planning_start_min: float
    epoch_iso8601: str | None

    def __post_init__(self):
        super().__post_init__()
        require(self.orientation in {-1, 1} and self.length_m > 0 and self.planning_start_min >= 0, "VESSEL_FRAME", "vessel", "length/time/orientation invalid")
        require(bool(self.vessel_id.strip()) and bool(self.berth_id.strip()),"VESSEL_IDENTITY","vessel","nonempty vessel/berth IDs required")
        if self.epoch_iso8601 is not None:
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(self.epoch_iso8601)
            except ValueError as exc:
                raise ContractError("EPOCH", "vessel.epoch_iso8601", str(exc)) from exc
            require(dt.tzinfo is not None and dt.utcoffset() is not None, "EPOCH", "vessel.epoch_iso8601", "timezone required")


def local_to_global(vessel, local_m):
    local_m = _typed(float, local_m, "bay.local_m")
    require(0 <= local_m <= vessel.length_m, "BAY_BOUNDS", "bay.local_m", "outside hull")
    return vessel.berth_origin_m + (local_m if vessel.orientation == 1 else vessel.length_m - local_m)


def moves_per_minute(rate_per_hour):
    rate = _typed(float, rate_per_hour, "rate")
    require(rate > 0, "RATE", "rate", "positive rate required")
    return rate / 60


@dataclass(frozen=True)
class RailGeometry(Wire):
    rail_id: str
    axis: str
    lower_m: float
    upper_m: float
    min_clearance_m: float | None
    separation_model: str
    time_tolerance_min: float | None
    position_tolerance_m: float | None
    horizon_min: float | None

    def __post_init__(self):
        super().__post_init__()
        require(self.lower_m < self.upper_m, "RAIL_BOUNDS", "rail", "empty/reversed rail")
        require(bool(self.rail_id.strip()) and bool(self.axis.strip()),"RAIL_FRAME","rail","explicit nonempty rail identity/axis required")
        require(self.separation_model in {"UNRESOLVED", "REFERENCE_POINT"}, "SEPARATION_MODEL", "rail", "body-aware physics not yet supported")
        for name in ("min_clearance_m", "time_tolerance_min", "position_tolerance_m", "horizon_min"):
            x = getattr(self, name)
            require(x is None or x >= 0, "PHYSICS_VALUE", "rail." + name, "negative parameter")
        require(self.horizon_min is None or self.horizon_min > 0, "HORIZON", "rail.horizon_min", "positive horizon required")


@dataclass(frozen=True)
class CraneDefinition(Wire):
    crane_id: str
    rail_id: str
    rail_rank: int
    initial_position_m: float
    reach_lower_m: float
    reach_upper_m: float
    travel_speed_m_per_min: float | None
    effective_moves_per_hour: float | None
    setup_min: float | None
    available_at_min: float

    def __post_init__(self):
        super().__post_init__()
        require(self.reach_lower_m <= self.reach_upper_m, "REACH", "crane", "reversed reach")
        for name in ("travel_speed_m_per_min", "effective_moves_per_hour"):
            x = getattr(self, name)
            require(x is None or x > 0, "RATE", "crane." + name, "positive parameter required")
        require(self.setup_min is None or self.setup_min >= 0, "SETUP", "crane.setup_min", "negative setup")


@dataclass(frozen=True)
class BayDefinition(Wire):
    bay_id: str
    local_m: float
    verified_global_m: float | None


@dataclass(frozen=True)
class CraneTaskGroup(Wire):
    task_id: str
    vessel_id: str
    bay_id: str
    operation_kind: str
    workload_moves: int
    release_min: float
    predecessor_ids: tuple[str, ...]
    source_task_ids: tuple[str, ...]
    source_container_ids: tuple[str, ...]

    def __post_init__(self):
        super().__post_init__()
        require(0 < self.workload_moves <= 2**53, "WORKLOAD", "task.workload_moves", "positive exactly representable integer moves required; use empty task list for zero work")
        require(self.operation_kind in {"LOAD", "DISCHARGE"}, "OPERATION", "task.operation_kind", "unsupported operation")
        require(not self.predecessor_ids, "DEFERRED_PRECEDENCE", "task.predecessor_ids", "v1 has no stack precedence")


@dataclass(frozen=True)
class QCSPProblem(Wire):
    metadata: ProblemMetadata
    vessel: VesselContext
    rail: RailGeometry
    cranes: tuple[CraneDefinition, ...]
    bays: tuple[BayDefinition, ...]
    tasks: tuple[CraneTaskGroup, ...]
    declared_workload_moves: int
    units: tuple[str, ...]

    def __post_init__(self):
        super().__post_init__()
        require(self.units == ("min", "m", "moves", "moves/hour"), "UNITS", "units", "exact unit declaration required")
        require(len(self.cranes) == 2, "FLEET", "cranes", "QCSP v1 requires two cranes")
        for name, seq, key in (("cranes", self.cranes, "crane_id"), ("bays", self.bays, "bay_id"), ("tasks", self.tasks, "task_id")):
            ids = [getattr(x, key) for x in seq]
            require(all(x.strip() for x in ids) and len(set(ids)) == len(ids), "DUPLICATE_ID", name, "unique nonempty IDs required")
        require([c.rail_rank for c in self.cranes] == [0, 1], "RAIL_ORDER", "cranes", "array is physical rank order, not lexical ID order")
        for c in self.cranes:
            require(c.rail_id == self.rail.rail_id and self.rail.lower_m <= c.initial_position_m <= self.rail.upper_m, "INITIAL_POSITION", c.crane_id, "wrong rail or initial position")
            require(self.rail.lower_m <= c.reach_lower_m <= c.reach_upper_m <= self.rail.upper_m and c.available_at_min >= self.vessel.planning_start_min, "REACH_AVAILABILITY", c.crane_id, "invalid reach/availability")
        gap = self.cranes[1].initial_position_m - self.cranes[0].initial_position_m
        require(gap >= 0 and (self.rail.min_clearance_m is None or gap >= self.rail.min_clearance_m), "INITIAL_SEPARATION", "cranes", "initial order/clearance conflict")
        require(self.rail.lower_m <= self.vessel.berth_origin_m and self.vessel.berth_origin_m + self.vessel.length_m <= self.rail.upper_m, "HULL_BOUNDS", "vessel", "hull outside declared rail/quay")
        for b in self.bays:
            x = local_to_global(self.vessel, b.local_m)
            require(b.verified_global_m is None or b.verified_global_m == x, "COORDINATE_MISMATCH", b.bay_id, "supplied global coordinate disagrees with transform")
        for t in self.tasks:
            require(t.vessel_id == self.vessel.vessel_id and t.bay_id in {b.bay_id for b in self.bays}, "REFERENCE", t.task_id, "unknown vessel/bay")
            require(t.release_min == self.vessel.planning_start_min, "DEFERRED_RELEASE", t.task_id, "v1 known-ready workload only")
        require(sum(t.workload_moves for t in self.tasks) == self.declared_workload_moves, "WORKLOAD_TOTAL", "declared_workload_moves", "aggregate mismatch")

    @property
    def physical_fingerprint(self):
        payload = self.to_dict()
        del payload["metadata"]
        return digest(payload)

    def require_fixture_execution(self, permit=None):
        if self.metadata.origin != "TEST_FIXTURE_SYNTHETIC":
            require(type(permit) is ExecutionPermit and self.fingerprint in permit.problem_hashes and self.metadata.role in permit.roles, "OWNER_APPROVAL_REQUIRED", "metadata.origin", "exact input must be covered by separately approved owner-manual lock")
        require(self.metadata.assumptions_version == ASSUMPTIONS and self.rail.separation_model == "REFERENCE_POINT", "PHYSICS_PROFILE", "metadata", "explicit supported fixture model required")
        params = [self.rail.min_clearance_m, self.rail.time_tolerance_min, self.rail.position_tolerance_m, self.rail.horizon_min]
        params += [x for c in self.cranes for x in (c.travel_speed_m_per_min, c.effective_moves_per_hour, c.setup_min)]
        require(all(x is not None for x in params), "PHYSICS_UNRESOLVED", "problem", "missing required explicit physics input")
        span=self.rail.upper_m-self.rail.lower_m
        max_work=max((t.workload_moves for t in self.tasks),default=0)
        require(math.isfinite(self.vessel.planning_start_min+self.rail.horizon_min) and all(math.isfinite(span/c.travel_speed_m_per_min+c.setup_min+60*max_work/c.effective_moves_per_hour) for c in self.cranes),"PHYSICS_RANGE","problem","timings cannot be represented finitely")


@dataclass(frozen=True)
class SchedulingDecision(Wire):
    tag: str
    crane_id: str | None
    task_id: str | None

    def __post_init__(self):
        super().__post_init__()
        require((self.tag == "WAIT" and self.crane_id is None and self.task_id is None) or (self.tag == "ASSIGN_TASK" and bool(self.crane_id) and bool(self.task_id)), "ACTION_SHAPE", "action", "invalid tag/payload; legality is Step 04")


@dataclass(frozen=True)
class MotionSegment(Wire):
    crane_id: str
    mode: str
    start_min: float
    end_min: float
    start_m: float
    end_m: float
    task_id: str | None

    def __post_init__(self):
        super().__post_init__()
        require(self.mode in {"TRAVEL", "SETUP", "PROCESS", "IDLE"} and self.end_min >= self.start_min >= 0, "SEGMENT", "segment", "invalid mode/time order")


@dataclass(frozen=True)
class ScheduledTask(Wire):
    task_id: str
    crane_id: str
    departure_min: float
    setup_start_min: float
    process_start_min: float
    completion_min: float

    def __post_init__(self):
        super().__post_init__()
        require(0 <= self.departure_min <= self.setup_start_min <= self.process_start_min <= self.completion_min, "TASK_TIMES", self.task_id, "timestamps must be nonnegative and ordered; duration feasibility is not certified")


@dataclass(frozen=True)
class CraneSchedule(Wire):
    schema_version: str
    problem_hash: str
    policy_id: str
    outcome: str
    solver_status: str | None
    tasks: tuple[ScheduledTask, ...]
    segments: tuple[MotionSegment, ...]
    stop_min: float

    def __post_init__(self):
        super().__post_init__()
        require(self.schema_version == SCHEMA, "VERSION", "schedule", "unsupported schema")
        require(self.outcome in {"CANDIDATE_UNVERIFIED", "PARTIAL", "DEADLOCK", "TRUNCATED_HORIZON", "TIMEOUT", "INFEASIBLE"}, "CANDIDATE_ONLY", "schedule.outcome", "physical verdict belongs to independent verifier, never producer")
        require(self.solver_status in {None, "OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "MODEL_INVALID", "DEPENDENCY_PENDING", "UNSUPPORTED_FORMULATION"}, "SOLVER_STATUS", "schedule", "unsupported solver status")


@dataclass(frozen=True)
class CraneTraceEvent(Wire):
    schema_version: str
    event_id: str
    sequence: int
    time_min: float
    kind: str
    crane_id: str | None
    task_id: str | None

    def __post_init__(self):
        super().__post_init__()
        require(self.schema_version == SCHEMA and self.sequence >= 0 and self.time_min >= 0 and bool(self.event_id), "TRACE_SHAPE", "event", "invalid version, identity or time")


@dataclass(frozen=True)
class CraneObservation(Wire):
    schema_version: str
    time_min: float
    positions_m: tuple[float, ...]
    available: tuple[bool, ...]
    completed_task_ids: tuple[str, ...]
    assigned_task_ids: tuple[str, ...]
    visibility: str

    def __post_init__(self):
        super().__post_init__()
        require(self.schema_version == SCHEMA and self.time_min >= 0 and len(self.positions_m) == len(self.available) == 2 and self.visibility == "CURRENT_VESSEL_KNOWN_WORKLOAD", "OBSERVATION_SHAPE", "observation", "invalid visible-state shape")


@dataclass(frozen=True)
class MetricRecord(Wire):
    problem_hash: str
    valid_complete: bool
    makespan_min: float | None
    original_moves: int
    completed_moves: int
    travel_min: float
    travel_m: float
    productive_crane_min: float
    utilization: float | None
    idle_crane_min: float
    policy_latency_s: tuple[float, ...]

    def __post_init__(self):
        super().__post_init__()
        require(0 <= self.completed_moves <= self.original_moves, "METRIC_WORK", "metrics", "work must reconcile")
        require((self.valid_complete and self.makespan_min is not None and self.makespan_min >= 0) or (not self.valid_complete and self.makespan_min is None), "METRIC_VALIDITY", "metrics", "failure cannot have successful makespan")
        require(all(x >= 0 for x in self.policy_latency_s), "METRIC_LATENCY", "metrics", "negative latency")
