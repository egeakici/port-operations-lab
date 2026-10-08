"""Scenario-stage validation of ``itp_scenario_v1`` documents.

Implements the generator-time part of container_yard_foundation.md section 9
(DQ01-DQ07, DQ09-DQ11, DQ16, DQ19, DQ20 and the time-zero prerequisites of
DQ08 and DQ15). Runtime invariants that need an evolving state (transfer
double-location, crane exclusivity over time, ledger conservation, DQ12-DQ14,
DQ17, DQ18) are Step 4+ responsibilities and are not claimed here.

Every issue carries a stable code, the DQ rule, the entity, a field path and a
message. Issues are sorted deterministically. Nothing is repaired.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from integrated_terminal_pilot.scenarios import models as m

# Step 1 taxonomy (container_yard_foundation.md 9) and Step 2 additive codes (amendment A6).
ERROR_CODES: dict[str, str] = {
    "DUPLICATE_CONTAINER_ID": "DQ01",
    "INVALID_CONTAINER_ID": "DQ01",
    "INVALID_CONTAINER_SIZE": "DQ02",
    "TEU_SIZE_MISMATCH": "DQ02",
    "INVALID_WEIGHT": "DQ02",
    "INVALID_CARGO_FLOW": "DQ03",
    "UNKNOWN_REFERENCE": "DQ03",
    "GROUP_MEMBERSHIP_ERROR": "DQ04",
    "GROUP_TEU_MISMATCH": "DQ05",
    "WORKLOAD_RECONCILIATION_FAILURE": "DQ06",
    "YARD_CAPACITY_EXCEEDED": "DQ07",
    "DUPLICATE_PHYSICAL_LOCATION": "DQ08",
    "INVALID_STACK_POSITION": "DQ09",
    "SLOT_SIZE_CONFLICT": "DQ09",
    "FLOATING_STACK": "DQ10",
    "CAUSALITY_VIOLATION": "DQ11",
    "INVALID_STATUS_TRANSITION": "DQ15",
    "FINGERPRINT_INCOMPLETE": "DQ16",
    "FINGERPRINT_MISMATCH": "DQ16",
    "FIDELITY_MISLABEL": "DQ19",
    "UNSUPPORTED_ASSUMPTION": "DQ20",
    # Additive Step 2 codes (not in Step 1); see docs/step2_scenario_generator.md A6.
    "DUPLICATE_ENTITY_ID": "DQ01",
    "INVALID_ENTITY_ID": "DQ01",
    "INVALID_ENTITY_ATTRIBUTE": "DQ21",
    "INVALID_YARD_GEOMETRY": "DQ21",
    "YARD_CAPABILITY_MISMATCH": "DQ21",
    "SEED_NAMESPACE_VIOLATION": "DQ22",
}
SCENARIO_STAGE_SEVERITY = "REJECT_SCENARIO"
# Protocol 6.1 seed bands (FROZEN; diagnostic band PROPOSED).
SEED_BANDS = {"development": (10_000_000, 10_999_999), "validation": (11_000_000, 11_999_999),
              "test": (12_000_000, 12_999_999), "diagnostic": (13_000_000, 13_999_999)}
# Contract-level sanity bounds for any scenario (not calibrated; generator bounds are
# tighter and are checked when a generator configuration is supplied).
CONTRACT_WEIGHT_BOUNDS_KG = (1000, 36000)
FROZEN_SERVICE = {"berthing_preparation_minutes": 30.0, "service_minutes_per_move": 0.5,
                  "departure_preparation_minutes": 20.0}
YARD_BLOCK_STATUSES = ("open", "closed", "maintenance")
TOL = 1e-9


@dataclass(frozen=True, order=True)
class ValidationIssue:
    code: str
    entity_type: str
    entity_id: str
    field_path: str
    message: str
    dq_rule: str = ""
    severity: str = SCENARIO_STAGE_SEVERITY

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationReport:
    scenario_id: str
    issues: tuple[ValidationIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> set[str]:
        return {issue.code for issue in self.issues}

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        return {"scenario_id": self.scenario_id, "valid": self.ok,
                "issue_counts": dict(sorted(counts.items())),
                "issues": [issue.to_dict() for issue in self.issues]}


class ScenarioValidationError(ValueError):
    def __init__(self, report: ValidationReport) -> None:
        first = report.issues[0]
        super().__init__(f"{len(report.issues)} validation issue(s); first: {first.code} "
                         f"{first.entity_type} {first.entity_id} {first.field_path}: {first.message}")
        self.report = report


class _Collector:
    def __init__(self) -> None:
        self.items: list[ValidationIssue] = []

    def add(self, code: str, entity_type: str, entity_id: Any, path: str, message: str) -> None:
        self.items.append(ValidationIssue(code, entity_type, str(entity_id), path, message,
                                          ERROR_CODES[code]))

    def keys(self, obj: Any, expected: Iterable[str], entity_type: str, entity_id: Any,
             path: str) -> bool:
        expected = tuple(expected)
        if not isinstance(obj, dict):
            self.add("UNSUPPORTED_ASSUMPTION", entity_type, entity_id, path, "must be an object")
            return False
        missing = [k for k in expected if k not in obj]
        extra = sorted(set(obj) - set(expected))
        if missing:
            self.add("UNSUPPORTED_ASSUMPTION", entity_type, entity_id, path,
                     f"missing required fields {missing}")
        if extra:
            self.add("UNSUPPORTED_ASSUMPTION", entity_type, entity_id, path,
                     f"unknown fields {extra}")
        return not missing


def _num(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int)


def validate_scenario(doc: Any, *, generator_config: Any = None,
                      check_fingerprints: bool = True) -> ValidationReport:
    c = _Collector()
    scenario_id = doc.get("identity", {}).get("scenario_id", "<unknown>") if isinstance(doc, dict) else "<unknown>"
    if not c.keys(doc, m.TOP_LEVEL_KEYS, "scenario", scenario_id, "$"):
        return _report(scenario_id, c)
    if doc["schema_version"] != m.SCHEMA_VERSION:
        c.add("UNSUPPORTED_ASSUMPTION", "scenario", scenario_id, "schema_version",
              f"expected {m.SCHEMA_VERSION}, got {doc['schema_version']!r}")
        return _report(scenario_id, c)
    structural_before = len(c.items)
    identity_ok = _check_identity(c, doc)
    quay_ok = _check_quay(c, doc)
    if not (identity_ok and quay_ok):
        return _report(scenario_id, c)
    blocks = _check_blocks(c, doc)
    cranes = _check_cranes(c, doc)
    vessels = _check_vessels_shape(c, doc)
    physics_ok = _check_physics(c, doc, cranes, vessels)
    containers = _check_containers(c, doc, vessels, physics_ok, generator_config)
    _check_groups(c, doc, containers)
    _check_vessel_reconciliation(c, doc, vessels, containers, cranes, physics_ok)
    _check_initial_state(c, doc, containers, blocks)
    if check_fingerprints and len(c.items) == structural_before:
        _check_fingerprints(c, doc)
    elif check_fingerprints and "fingerprints" in doc:
        _check_fingerprint_keys(c, doc)
    return _report(scenario_id, c)


def require_valid(doc: Any, **kwargs: Any) -> ValidationReport:
    report = validate_scenario(doc, **kwargs)
    if not report.ok:
        raise ScenarioValidationError(report)
    return report


def _report(scenario_id: str, c: _Collector) -> ValidationReport:
    return ValidationReport(scenario_id, tuple(sorted(set(c.items))))


def _check_identity(c: _Collector, doc: dict[str, Any]) -> bool:
    identity = doc["identity"]
    sid = identity.get("scenario_id", "<unknown>") if isinstance(identity, dict) else "<unknown>"
    if not c.keys(identity, m.IDENTITY_KEYS, "identity", sid, "identity"):
        return False
    ok = True
    if identity["split"] not in m.SPLITS:
        c.add("SEED_NAMESPACE_VIOLATION", "identity", sid, "identity.split",
              f"unknown split {identity['split']!r}")
        ok = False
    seed = identity["scenario_seed"]
    if not _int(seed):
        c.add("SEED_NAMESPACE_VIOLATION", "identity", sid, "identity.scenario_seed", "must be an integer")
        ok = False
    elif identity["split"] in SEED_BANDS:
        first, last = SEED_BANDS[identity["split"]]
        if not first <= seed <= last:
            c.add("SEED_NAMESPACE_VIOLATION", "identity", sid, "identity.scenario_seed",
                  f"seed {seed} outside the {identity['split']} band [{first}, {last}]")
    if identity["physics_profile"] not in (m.PHYSICS_PROFILE_STANDARD, m.PHYSICS_PROFILE_DEGENERATE):
        c.add("UNSUPPORTED_ASSUMPTION", "identity", sid, "identity.physics_profile",
              f"unknown physics profile {identity['physics_profile']!r}")
        ok = False
    if identity["yard_fidelity"] not in ("G0", "G1"):
        c.add("UNSUPPORTED_ASSUMPTION", "identity", sid, "identity.yard_fidelity",
              "yard_fidelity must be G0 or G1")
        ok = False
    if identity["data_provenance"] != "synthetic":
        c.add("UNSUPPORTED_ASSUMPTION", "identity", sid, "identity.data_provenance",
              "Project I v1 scenarios are synthetic")
    if identity["project_id"] != "project_i_integrated_terminal_pilot":
        c.add("UNSUPPORTED_ASSUMPTION", "identity", sid, "identity.project_id", "unexpected project id")
    for key in ("scenario_id", "scenario_family", "generator_version"):
        if not isinstance(identity[key], str) or not identity[key]:
            c.add("UNSUPPORTED_ASSUMPTION", "identity", sid, f"identity.{key}", "must be a non-empty string")
            ok = False
    if ok and identity["scenario_id"] != m.scenario_id_for(
            identity["scenario_family"], identity["split"], seed, identity["physics_profile"]):
        c.add("INVALID_ENTITY_ID", "identity", sid, "identity.scenario_id",
              "scenario_id must equal {scenario_family}_{split}_seed{seed}[__{profile}]")
    return ok


def _check_quay(c: _Collector, doc: dict[str, Any]) -> bool:
    terminal = doc["terminal"]
    if not c.keys(terminal, m.TERMINAL_KEYS, "terminal", "terminal", "terminal"):
        return False
    quay = terminal["quay"]
    if not c.keys(quay, m.QUAY_KEYS, "quay", "quay", "terminal.quay"):
        return False
    ok = True
    if not _num(quay["berth_length_m"]) or quay["berth_length_m"] <= 0:
        c.add("INVALID_ENTITY_ATTRIBUTE", "quay", "quay", "terminal.quay.berth_length_m",
              "must be a positive finite number")
        ok = False
    if not _num(quay["min_clearance_m"]) or quay["min_clearance_m"] < 0:
        c.add("INVALID_ENTITY_ATTRIBUTE", "quay", "quay", "terminal.quay.min_clearance_m",
              "must be a non-negative finite number")
        ok = False
    if quay["quay_line_y_m"] != 0.0:
        c.add("UNSUPPORTED_ASSUMPTION", "quay", "quay", "terminal.quay.quay_line_y_m",
              "quay line must be y = 0 (D03)")
    gates = terminal["gates"]
    if not isinstance(gates, list):
        c.add("UNSUPPORTED_ASSUMPTION", "gate", "-", "terminal.gates", "must be a list")
        return False
    seen = set()
    for i, gate in enumerate(gates):
        path = f"terminal.gates[{i}]"
        if not c.keys(gate, m.GATE_KEYS, "gate", gate.get("gate_id", i) if isinstance(gate, dict) else i, path):
            continue
        gid = gate["gate_id"]
        if not isinstance(gid, str) or not m.ID_PATTERNS["gate"].match(gid):
            c.add("INVALID_ENTITY_ID", "gate", gid, f"{path}.gate_id", "must match G\\d{2}")
        if gid in seen:
            c.add("DUPLICATE_ENTITY_ID", "gate", gid, f"{path}.gate_id", "duplicate gate id")
        seen.add(gid)
        if not (_num(gate["x_m"]) and _num(gate["y_m"])):
            c.add("INVALID_ENTITY_ATTRIBUTE", "gate", gid, path, "coordinates must be finite numbers")
    return ok


def _check_blocks(c: _Collector, doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from terminal_core import ContainerSize, YardCapability

    quay_length = doc["terminal"]["quay"]["berth_length_m"]
    blocks: dict[str, dict[str, Any]] = {}
    raw = doc["terminal"]["yard_blocks"]
    if not isinstance(raw, list) or not raw:
        c.add("UNSUPPORTED_ASSUMPTION", "yard_block", "-", "terminal.yard_blocks",
              "must be a non-empty list")
        return blocks
    footprints = []
    for i, block in enumerate(raw):
        path = f"terminal.yard_blocks[{i}]"
        bid = block.get("block_id", i) if isinstance(block, dict) else i
        if not c.keys(block, m.YARD_BLOCK_KEYS, "yard_block", bid, path):
            continue
        if not isinstance(bid, str) or not m.ID_PATTERNS["block"].match(bid):
            c.add("INVALID_ENTITY_ID", "yard_block", bid, f"{path}.block_id", "must match B\\d{2}")
        if bid in blocks:
            c.add("DUPLICATE_ENTITY_ID", "yard_block", bid, f"{path}.block_id", "duplicate block id")
            continue
        geometry_ok = True
        for key in ("bay_count", "row_count", "max_tiers", "geometric_slot_count"):
            if not _int(block[key]) or block[key] < 1:
                c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.{key}",
                      "must be a positive integer (1-based grid)")
                geometry_ok = False
        for key in ("origin_x_m", "origin_y_m", "ground_slot_length_m", "ground_slot_width_m",
                    "geometric_capacity_teu", "capacity_teu", "operating_fill_limit",
                    "handling_capacity_moves_per_hour", "transfer_point_x_m", "transfer_point_y_m"):
            if not _num(block[key]):
                c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.{key}",
                      "must be a finite number")
                geometry_ok = False
        if block["bay_axis"] != "X":
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.bay_axis",
                  "bay_axis must be 'X' (FROZEN v1)")
        if not isinstance(block["capabilities"], list) or not block["capabilities"] or any(
                v not in {cap.value for cap in YardCapability} for v in block["capabilities"]):
            c.add("INVALID_ENTITY_ATTRIBUTE", "yard_block", bid, f"{path}.capabilities",
                  "must be a non-empty list of YardCapability values")
        if not isinstance(block["allowed_sizes"], list) or not block["allowed_sizes"] or any(
                v not in {s.value for s in ContainerSize} for v in block["allowed_sizes"]):
            c.add("INVALID_ENTITY_ATTRIBUTE", "yard_block", bid, f"{path}.allowed_sizes",
                  "must be a non-empty list of ContainerSize values")
        blocks[bid] = block
        if not geometry_ok:
            continue
        if block["bay_count"] % 2:
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.bay_count",
                  "bay_count must be even (40 ft bay pairs)")
        if block["max_tiers"] < 2:
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.max_tiers", "must be >= 2")
        slots = block["bay_count"] * block["row_count"] * block["max_tiers"]
        if block["geometric_slot_count"] != slots or block["geometric_capacity_teu"] != float(slots):
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.geometric_slot_count",
                  f"derived geometric capacity must equal bays x rows x tiers = {slots}")
        fill = (block["max_tiers"] - 1) / block["max_tiers"]
        if abs(block["operating_fill_limit"] - fill) > TOL:
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.operating_fill_limit",
                  f"must equal (max_tiers - 1) / max_tiers = {fill}")
        if block["capacity_teu"] <= 0 or block["capacity_teu"] > slots * block["operating_fill_limit"] + TOL:
            c.add("YARD_CAPACITY_EXCEEDED", "yard_block", bid, f"{path}.capacity_teu",
                  f"capacity_teu {block['capacity_teu']} must be in (0, geometric slots x operating "
                  f"fill limit = {slots * block['operating_fill_limit']}]")
        if block["handling_capacity_moves_per_hour"] <= 0:
            c.add("INVALID_ENTITY_ATTRIBUTE", "yard_block", bid,
                  f"{path}.handling_capacity_moves_per_hour", "must be > 0")
        length = block["bay_count"] * block["ground_slot_length_m"]
        depth = block["row_count"] * block["ground_slot_width_m"]
        if block["ground_slot_length_m"] <= 0 or block["ground_slot_width_m"] <= 0:
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, path, "slot footprint must be positive")
            continue
        if (abs(block["transfer_point_x_m"] - (block["origin_x_m"] + length / 2)) > 1e-6
                or abs(block["transfer_point_y_m"] - block["origin_y_m"]) > 1e-6):
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, f"{path}.transfer_point_x_m",
                  "transfer point must be the middle of the quay-side edge")
        if (block["origin_y_m"] <= doc["terminal"]["quay"]["quay_line_y_m"]
                or block["origin_x_m"] < -1e-6 or block["origin_x_m"] + length > quay_length + 1e-6):
            c.add("INVALID_YARD_GEOMETRY", "yard_block", bid, path,
                  "block footprint must lie inland of the quay line within x in [0, quay length]")
        footprints.append((bid, block["origin_x_m"], block["origin_x_m"] + length,
                           block["origin_y_m"], block["origin_y_m"] + depth))
    for i, a in enumerate(footprints):
        for b in footprints[i + 1:]:
            if a[1] < b[2] - 1e-6 and b[1] < a[2] - 1e-6 and a[3] < b[4] - 1e-6 and b[3] < a[4] - 1e-6:
                c.add("INVALID_YARD_GEOMETRY", "yard_block", f"{a[0]}/{b[0]}", "terminal.yard_blocks",
                      "block footprints overlap")
    return blocks


def _check_cranes(c: _Collector, doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    resources = doc["resources"]
    cranes: dict[str, dict[str, Any]] = {}
    if not c.keys(resources, m.RESOURCES_KEYS, "resources", "resources", "resources"):
        return cranes
    raw = resources["quay_cranes"]
    if not isinstance(raw, list) or not raw:
        c.add("UNSUPPORTED_ASSUMPTION", "quay_crane", "-", "resources.quay_cranes",
              "must be a non-empty list")
        return cranes
    quay_length = doc["terminal"]["quay"]["berth_length_m"]
    vessel_ids = {v.get("vessel_id") for v in doc["vessels"] if isinstance(v, dict)} if isinstance(doc["vessels"], list) else set()
    for i, crane in enumerate(raw):
        path = f"resources.quay_cranes[{i}]"
        cid = crane.get("crane_id", i) if isinstance(crane, dict) else i
        if not c.keys(crane, m.CRANE_KEYS, "quay_crane", cid, path):
            continue
        if not isinstance(cid, str) or not m.ID_PATTERNS["crane"].match(cid):
            c.add("INVALID_ENTITY_ID", "quay_crane", cid, f"{path}.crane_id", "must match QC\\d{2}")
        if cid in cranes:
            c.add("DUPLICATE_ENTITY_ID", "quay_crane", cid, f"{path}.crane_id", "duplicate crane id")
            continue
        cranes[cid] = crane
        if not _num(crane["nominal_moves_per_hour"]) or crane["nominal_moves_per_hour"] <= 0:
            c.add("INVALID_ENTITY_ATTRIBUTE", "quay_crane", cid, f"{path}.nominal_moves_per_hour",
                  "must be > 0")
        if not isinstance(crane["rail_id"], str) or not crane["rail_id"]:
            c.add("INVALID_ENTITY_ATTRIBUTE", "quay_crane", cid, f"{path}.rail_id", "must be a string")
        if not _num(crane["home_position_m"]) or not 0 <= crane["home_position_m"] <= quay_length:
            c.add("INVALID_ENTITY_ATTRIBUTE", "quay_crane", cid, f"{path}.home_position_m",
                  "must lie on the quay")
        compatible = crane["compatible_vessel_ids"]
        if compatible is not None and (not isinstance(compatible, list)
                                       or any(v not in vessel_ids for v in compatible)):
            c.add("UNKNOWN_REFERENCE", "quay_crane", cid, f"{path}.compatible_vessel_ids",
                  "must be null or a list of scenario vessel ids")
        if crane["unavailability_windows"] != []:
            c.add("UNSUPPORTED_ASSUMPTION", "quay_crane", cid, f"{path}.unavailability_windows",
                  "crane unavailability is disabled in v1 (D19)")
    return cranes


def _check_vessels_shape(c: _Collector, doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    vessels: dict[str, dict[str, Any]] = {}
    raw = doc["vessels"]
    if not isinstance(raw, list) or not raw:
        c.add("UNSUPPORTED_ASSUMPTION", "vessel", "-", "vessels", "must be a non-empty list")
        return vessels
    quay_length = doc["terminal"]["quay"]["berth_length_m"]
    for i, vessel in enumerate(raw):
        path = f"vessels[{i}]"
        vid = vessel.get("vessel_id", i) if isinstance(vessel, dict) else i
        if not c.keys(vessel, m.VESSEL_KEYS, "vessel", vid, path):
            continue
        if not isinstance(vid, str) or not m.ID_PATTERNS["vessel"].match(vid):
            c.add("INVALID_ENTITY_ID", "vessel", vid, f"{path}.vessel_id",
                  "must match V\\d{3} (PRE_EPISODE is not a vessel record)")
        if vid in vessels:
            c.add("DUPLICATE_ENTITY_ID", "vessel", vid, f"{path}.vessel_id", "duplicate vessel id")
            continue
        vessels[vid] = vessel
        if not _num(vessel["arrival_time_min"]) or vessel["arrival_time_min"] < 0:
            c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", vid, f"{path}.arrival_time_min",
                  "must be a finite number >= 0")
        if not _num(vessel["length_m"]) or not 0 < vessel["length_m"] <= quay_length:
            c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", vid, f"{path}.length_m",
                  "must be > 0 and <= quay length")
        if not _int(vessel["priority"]) or not 1 <= vessel["priority"] <= 3:
            c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", vid, f"{path}.priority", "must be 1..3")
        if vessel["extra_work_units"] != 0:
            c.add("UNSUPPORTED_ASSUMPTION", "vessel", vid, f"{path}.extra_work_units",
                  "must be 0 (D14 single lift)")
        for key in ("discharge_move_count", "load_move_count", "workload_moves", "max_cranes"):
            if not _int(vessel[key]) or vessel[key] < 0:
                c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", vid, f"{path}.{key}",
                      "must be a non-negative integer")
        if _int(vessel["workload_moves"]) and vessel["workload_moves"] < 1:
            c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", vid, f"{path}.workload_moves",
                  "generated vessels need workload_moves >= 1")
        for key in ("discharge_teu", "load_teu", "nominal_service_time_min"):
            if not _num(vessel[key]) or vessel[key] < 0:
                c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", vid, f"{path}.{key}",
                      "must be a non-negative finite number")
    return vessels


def _check_physics(c: _Collector, doc: dict[str, Any], cranes: dict[str, Any],
                   vessels: dict[str, Any]) -> bool:
    physics = doc["physics"]
    if not c.keys(physics, m.PHYSICS_KEYS, "physics", "physics", "physics"):
        return False
    ok = True
    if physics["service"] != FROZEN_SERVICE:
        c.add("UNSUPPORTED_ASSUMPTION", "physics", "service", "physics.service",
              "must equal ServiceConfig(30, 0.5, 20) (D20, FROZEN)")
        ok = False
    crane = physics["crane"]
    if not isinstance(crane, dict) or crane.get("productivity_factor") != 1.0:
        c.add("UNSUPPORTED_ASSUMPTION", "physics", "crane", "physics.crane.productivity_factor",
              "must be 1.0 (D19, FROZEN)")
    else:
        eff = crane.get("efficiency")
        try:
            from mini_port_sim.scenario import ServiceConfig
            if not isinstance(eff, dict) or eff.get("one") != 1.0:
                raise ValueError("efficiency.one must be 1.0")
            ServiceConfig(two_crane_efficiency=eff["two"], three_crane_efficiency=eff["three"],
                          four_plus_crane_efficiency=eff["four_plus"])
        except (KeyError, TypeError, ValueError) as error:
            c.add("INVALID_ENTITY_ATTRIBUTE", "physics", "crane", "physics.crane.efficiency",
                  f"rejected by Project 02 ServiceConfig: {error}")
            ok = False
    if physics.get("visibility") != {"future_horizon_min": 240.0}:
        c.add("UNSUPPORTED_ASSUMPTION", "physics", "visibility", "physics.visibility",
              "future_horizon_min must be 240.0 (D18, FROZEN)")
        ok = False
    landside = physics["landside"]
    if (not isinstance(landside, dict) or set(landside) != {"export_cutoff_min"}
            or not _num(landside["export_cutoff_min"]) or landside["export_cutoff_min"] < 0):
        c.add("UNSUPPORTED_ASSUMPTION", "physics", "landside", "physics.landside",
              "must be {export_cutoff_min: >= 0}")
        ok = False
    episode = physics["episode"]
    if (not isinstance(episode, dict) or not _num(episode.get("max_drain_extension_min"))
            or episode["max_drain_extension_min"] <= 0):
        c.add("UNSUPPORTED_ASSUMPTION", "physics", "episode", "physics.episode.max_drain_extension_min",
              "must be a positive finite number")
        ok = False
    for section, keys in (("transport", ("enabled", "speed_m_per_min", "handover_min", "units_per_crane")),
                          ("yard", ("constraints_enabled", "congestion_rho0", "congestion_g_min",
                                    "landside_reserved_fraction", "gate_flow_demand")),
                          ("work", ("batch_size_containers", "max_load_wait_min")),
                          ("kernel", ("same_timestamp_cycle_limit",))):
        if not c.keys(physics[section], keys, "physics", section, f"physics.{section}"):
            ok = False
    if doc["identity"]["physics_profile"] == m.PHYSICS_PROFILE_DEGENERATE and ok:
        from integrated_terminal_pilot.scenarios.generator import max_coexisting_vessels
        if physics["transport"]["enabled"] or physics["yard"]["constraints_enabled"]:
            c.add("UNSUPPORTED_ASSUMPTION", "physics", "degenerate", "physics",
                  "degenerate profile requires transport and yard couplings disabled")
        if any(cr["nominal_moves_per_hour"] != 120.0 for cr in cranes.values()):
            c.add("INVALID_ENTITY_ATTRIBUTE", "quay_crane", "*", "resources.quay_cranes",
                  "degenerate profile requires 120 moves/h cranes")
        if any(v["max_cranes"] != 1 for v in vessels.values()):
            c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", "*", "vessels.max_cranes",
                  "degenerate profile requires max_cranes = 1")
        lengths = [v["length_m"] for v in vessels.values() if _num(v["length_m"])]
        quay = doc["terminal"]["quay"]
        if lengths and len(cranes) < max_coexisting_vessels(lengths, quay["berth_length_m"],
                                                            quay["min_clearance_m"]):
            c.add("INVALID_ENTITY_ATTRIBUTE", "quay_crane", "*", "resources.quay_cranes",
                  "degenerate profile requires cranes >= maximum co-existing vessels")
    return ok


def _check_containers(c: _Collector, doc: dict[str, Any], vessels: dict[str, Any], physics_ok: bool,
                      generator_config: Any) -> dict[str, dict[str, Any]]:
    containers: dict[str, dict[str, Any]] = {}
    raw = doc["containers"]
    if not isinstance(raw, list) or not raw:
        c.add("UNSUPPORTED_ASSUMPTION", "container", "-", "containers", "must be a non-empty list")
        return containers
    sid = doc["identity"]["scenario_id"]
    cutoff = doc["physics"]["landside"]["export_cutoff_min"] if physics_ok else None
    generator_bounds = None
    if generator_config is not None and doc["identity"]["generator_version"] == generator_config.parameters["generator_version"]:
        generator_bounds = generator_config.parameters["cargo"]
    for i, record in enumerate(raw):
        path = f"containers[{i}]"
        cid = record.get("container_id", i) if isinstance(record, dict) else i
        if not c.keys(record, m.CONTAINER_KEYS, "container", cid, path):
            continue
        if not isinstance(cid, str) or not m.ID_PATTERNS["container"].match(cid):
            c.add("INVALID_CONTAINER_ID", "container", cid, f"{path}.container_id",
                  "must match CNT-\\d{6}")
        if cid in containers:
            c.add("DUPLICATE_CONTAINER_ID", "container", cid, f"{path}.container_id",
                  "container id is not unique")
            continue
        containers[cid] = record
        size = record["container_size"]
        if size not in m.TEU_BY_SIZE:
            c.add("INVALID_CONTAINER_SIZE", "container", cid, f"{path}.container_size",
                  f"unsupported size {size!r} (supported: 20_ft, 40_ft)")
        elif record["size_teu"] != m.TEU_BY_SIZE[size]:
            c.add("TEU_SIZE_MISMATCH", "container", cid, f"{path}.size_teu",
                  f"{size} must be {m.TEU_BY_SIZE[size]} TEU, got {record['size_teu']!r}")
        if record["load_state"] not in ("laden", "empty"):
            c.add("UNSUPPORTED_ASSUMPTION", "container", cid, f"{path}.load_state",
                  "must be laden or empty")
        for key in ("is_reefer", "is_hazardous", "present_at_episode_start"):
            if not isinstance(record[key], bool):
                c.add("UNSUPPORTED_ASSUMPTION", "container", cid, f"{path}.{key}", "must be boolean")
        if record["load_state"] == "empty" and (record["is_reefer"] is True or record["is_hazardous"] is True):
            c.add("INVALID_ENTITY_ATTRIBUTE", "container", cid, path,
                  "empty containers cannot be reefer or hazardous (Project 01 rule)")
        weight = record["gross_weight_kg"]
        if weight is not None:
            low, high = CONTRACT_WEIGHT_BOUNDS_KG
            if not _int(weight) or not low <= weight <= high:
                c.add("INVALID_WEIGHT", "container", cid, f"{path}.gross_weight_kg",
                      f"must be an integer within contract sanity bounds [{low}, {high}] kg")
            elif generator_bounds is not None and size in m.TEU_BY_SIZE:
                if record["load_state"] == "laden":
                    b = generator_bounds["laden_weight_kg"][size]
                    if not b["min"] <= weight <= b["max"]:
                        c.add("INVALID_WEIGHT", "container", cid, f"{path}.gross_weight_kg",
                              f"outside generator bounds [{b['min']}, {b['max']}] kg for laden {size}")
                elif weight != generator_bounds["empty_weight_kg"][size]:
                    c.add("INVALID_WEIGHT", "container", cid, f"{path}.gross_weight_kg",
                          "empty weight differs from generator tare")
        _check_flow(c, record, cid, path, vessels, sid, cutoff)
    return containers


def _check_flow(c: _Collector, r: dict[str, Any], cid: str, path: str, vessels: dict[str, Any],
                sid: str, cutoff: float | None) -> None:
    flow, origin, destination = r["cargo_flow"], r["origin_vessel_id"], r["destination_vessel_id"]
    present = r["present_at_episode_start"] is True
    if flow not in ("import", "export", "transshipment"):
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.cargo_flow", f"unknown flow {flow!r}")
        return
    needs_origin = flow in ("import", "transshipment")
    needs_destination = flow in ("export", "transshipment")
    if needs_origin and origin is None:
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.origin_vessel_id",
              f"{flow} requires an origin vessel")
    if not needs_origin and origin is not None:
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.origin_vessel_id",
              "export must not define an origin vessel")
    if needs_destination and destination is None:
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.destination_vessel_id",
              f"{flow} requires a destination vessel")
    if not needs_destination and destination is not None:
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.destination_vessel_id",
              "import must not define a destination vessel")
    if origin is not None and origin == destination:
        c.add("INVALID_CARGO_FLOW", "container", cid, path, "origin and destination vessels must differ")
    if origin == m.PRE_EPISODE and not present:
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.origin_vessel_id",
              "PRE_EPISODE origin is only allowed for initial inventory")
    if origin is not None and origin != m.PRE_EPISODE and origin not in vessels:
        c.add("UNKNOWN_REFERENCE", "container", cid, f"{path}.origin_vessel_id",
              f"unknown vessel {origin!r}")
    if destination is not None and destination not in vessels:
        c.add("UNKNOWN_REFERENCE", "container", cid, f"{path}.destination_vessel_id",
              f"unknown vessel {destination!r} (PRE_EPISODE may only be an origin)")
    if present and origin is not None and origin != m.PRE_EPISODE:
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.origin_vessel_id",
              "initial inventory cannot have been discharged by a scenario vessel")
    if (r["terminal_entry_mode"], r["terminal_exit_mode"]) != m.expected_entry_exit(flow):
        c.add("INVALID_CARGO_FLOW", "container", cid, f"{path}.terminal_entry_mode",
              f"entry/exit modes must be {m.expected_entry_exit(flow)} for {flow}")
    if r["source_scenario_id"] != sid:
        c.add("UNKNOWN_REFERENCE", "container", cid, f"{path}.source_scenario_id",
              "must equal identity.scenario_id")
    gate_in, pickup = r["scheduled_gate_in_time_min"], r["scheduled_pickup_time_min"]
    if flow == "export" and not present and gate_in is None:
        c.add("UNSUPPORTED_ASSUMPTION", "container", cid, f"{path}.scheduled_gate_in_time_min",
              "export not present at start requires a gate-in request time")
    if gate_in is not None and (flow != "export" or present):
        c.add("CAUSALITY_VIOLATION", "container", cid, f"{path}.scheduled_gate_in_time_min",
              "only exports outside the terminal at start may have a gate-in request")
    if flow == "import" and pickup is None:
        c.add("UNSUPPORTED_ASSUMPTION", "container", cid, f"{path}.scheduled_pickup_time_min",
              "imports require a pickup request time")
    if pickup is not None and flow != "import":
        c.add("CAUSALITY_VIOLATION", "container", cid, f"{path}.scheduled_pickup_time_min",
              "only imports leave by landside pickup")
    if gate_in is not None and flow == "export" and not present:
        if not _num(gate_in) or gate_in < 0:
            c.add("CAUSALITY_VIOLATION", "container", cid, f"{path}.scheduled_gate_in_time_min",
                  "gate-in request must be a finite time >= 0")
        elif destination in vessels and cutoff is not None and _num(vessels[destination]["arrival_time_min"]):
            latest = vessels[destination]["arrival_time_min"] - cutoff
            if gate_in > latest + TOL:
                c.add("CAUSALITY_VIOLATION", "container", cid, f"{path}.scheduled_gate_in_time_min",
                      f"gate-in {gate_in} later than destination arrival - export_cutoff_min ({latest})")
    if pickup is not None and flow == "import":
        if not _num(pickup) or pickup < 0:
            c.add("CAUSALITY_VIOLATION", "container", cid, f"{path}.scheduled_pickup_time_min",
                  "pickup request must be a finite time >= 0")
        elif origin in vessels and _num(vessels[origin]["arrival_time_min"]) and \
                pickup < vessels[origin]["arrival_time_min"] - TOL:
            c.add("CAUSALITY_VIOLATION", "container", cid, f"{path}.scheduled_pickup_time_min",
                  "pickup request precedes the origin vessel's arrival")


def _check_groups(c: _Collector, doc: dict[str, Any], containers: dict[str, dict[str, Any]]) -> None:
    from terminal_core import ContainerGroup
    from terminal_core.exceptions import (
        ContainerCargoError, ContainerFlowError, ContainerGroupValidationError,
    )

    raw = doc["container_groups"]
    if not isinstance(raw, list) or not raw:
        c.add("UNSUPPORTED_ASSUMPTION", "container_group", "-", "container_groups",
              "must be a non-empty list")
        return
    groups: dict[str, dict[str, Any]] = {}
    for i, group in enumerate(raw):
        path = f"container_groups[{i}]"
        gid = group.get("group_id", i) if isinstance(group, dict) else i
        if not c.keys(group, m.GROUP_KEYS, "container_group", gid, path):
            continue
        if not isinstance(gid, str) or not m.ID_PATTERNS["group"].match(gid):
            c.add("INVALID_ENTITY_ID", "container_group", gid, f"{path}.group_id", "must match GRP-\\d{4}")
        if gid in groups:
            c.add("DUPLICATE_ENTITY_ID", "container_group", gid, f"{path}.group_id", "duplicate group id")
            continue
        try:
            ContainerGroup.from_dict(group)
        except ContainerFlowError as error:
            c.add("INVALID_CARGO_FLOW", "container_group", gid, path, f"Project 01: {error}")
        except ContainerCargoError as error:
            c.add("INVALID_ENTITY_ATTRIBUTE", "container_group", gid, path, f"Project 01: {error}")
        except ContainerGroupValidationError as error:
            c.add("GROUP_MEMBERSHIP_ERROR", "container_group", gid, path, f"Project 01: {error}")
        groups[gid] = group
    members: dict[str, list[dict[str, Any]]] = {gid: [] for gid in groups}
    field_map = (("container_size", "container_size"), ("cargo_flow", "flow"),
                 ("load_state", "load_state"), ("is_reefer", "is_reefer"),
                 ("is_hazardous", "is_hazardous"), ("origin_vessel_id", "source_vessel_id"),
                 ("destination_vessel_id", "target_vessel_id"))
    for cid, record in containers.items():
        gid = record["container_group_id"]
        if gid not in groups:
            c.add("GROUP_MEMBERSHIP_ERROR", "container", cid, "container_group_id",
                  f"references unknown group {gid!r}")
            continue
        members[gid].append(record)
        mismatched = [field for field, group_field in field_map
                      if record[field] != groups[gid][group_field]]
        if mismatched:
            c.add("GROUP_MEMBERSHIP_ERROR", "container", cid, "container_group_id",
                  f"fields {mismatched} differ from group {gid}")
    for gid, group in groups.items():
        size = group["container_size"]
        quantity = group["quantity"]
        if len(members[gid]) != quantity:
            c.add("GROUP_TEU_MISMATCH", "container_group", gid, "quantity",
                  f"quantity {quantity} differs from member count {len(members[gid])}")
        if size in m.TEU_BY_SIZE and _int(quantity):
            expected_teu = quantity * m.TEU_BY_SIZE[size]
            member_teu = sum(r["size_teu"] for r in members[gid] if _num(r["size_teu"]))
            if abs(member_teu - expected_teu) > TOL:
                c.add("GROUP_TEU_MISMATCH", "container_group", gid, "quantity",
                      f"group TEU {expected_teu} differs from member TEU {member_teu}")


def _check_vessel_reconciliation(c: _Collector, doc: dict[str, Any], vessels: dict[str, Any],
                                 containers: dict[str, Any], cranes: dict[str, Any],
                                 physics_ok: bool) -> None:
    discharge: dict[str, list[dict[str, Any]]] = {vid: [] for vid in vessels}
    load: dict[str, list[dict[str, Any]]] = {vid: [] for vid in vessels}
    for record in containers.values():
        if record["origin_vessel_id"] in discharge:
            discharge[record["origin_vessel_id"]].append(record)
        if record["destination_vessel_id"] in load:
            load[record["destination_vessel_id"]].append(record)
    service = None
    if physics_ok:
        from mini_port_sim.scenario import ServiceConfig
        s = doc["physics"]["service"]
        service = ServiceConfig(berthing_preparation_minutes=s["berthing_preparation_minutes"],
                                service_minutes_per_move=s["service_minutes_per_move"],
                                departure_preparation_minutes=s["departure_preparation_minutes"])
    from berth_allocation_lab.scenarios.synthetic import planned_berth_occupancy_minutes

    for vid, vessel in vessels.items():
        checks = (("discharge_move_count", len(discharge[vid])), ("load_move_count", len(load[vid])),
                  ("discharge_teu", sum(r["size_teu"] for r in discharge[vid])),
                  ("load_teu", sum(r["size_teu"] for r in load[vid])))
        for key, expected in checks:
            if vessel[key] != expected:
                c.add("WORKLOAD_RECONCILIATION_FAILURE", "vessel", vid, key,
                      f"{key} {vessel[key]!r} differs from container-derived {expected!r}")
        if _int(vessel["workload_moves"]) and vessel["workload_moves"] != (
                vessel["discharge_move_count"] + vessel["load_move_count"] + vessel["extra_work_units"]):
            c.add("WORKLOAD_RECONCILIATION_FAILURE", "vessel", vid, "workload_moves",
                  "workload_moves must equal discharge + load + extra_work_units (D14)")
        if service is not None and _int(vessel["workload_moves"]):
            nominal = planned_berth_occupancy_minutes(service=service,
                                                      workload_moves=vessel["workload_moves"])
            if not _num(vessel["nominal_service_time_min"]) or abs(vessel["nominal_service_time_min"] - nominal) > TOL:
                c.add("WORKLOAD_RECONCILIATION_FAILURE", "vessel", vid, "nominal_service_time_min",
                      f"must equal 30 + 0.5 x workload + 20 = {nominal} (D20)")
        if _int(vessel["max_cranes"]) and not 1 <= vessel["max_cranes"] <= max(len(cranes), 1):
            c.add("INVALID_ENTITY_ATTRIBUTE", "vessel", vid, "max_cranes",
                  f"max_cranes must be in 1..{len(cranes)} (crane fleet size)")


_INITIAL_STATUS_KIND = {"EXPECTED_BY_VESSEL": "VESSEL", "EXPECTED_BY_LANDSIDE": "EXTERNAL_LANDSIDE",
                        "IN_YARD": "YARD_BLOCK"}


def _check_initial_state(c: _Collector, doc: dict[str, Any], containers: dict[str, Any],
                         blocks: dict[str, Any]) -> None:
    fidelity = doc["identity"]["yard_fidelity"]
    state = doc["initial_state"]
    expected_keys = m.INITIAL_STATE_G1_KEYS if fidelity == "G1" else m.INITIAL_STATE_KEYS
    if isinstance(state, dict) and fidelity == "G0" and "slot_occupancy" in state:
        c.add("FIDELITY_MISLABEL", "initial_state", "-", "initial_state.slot_occupancy",
              "a G0 scenario must not carry slot occupancy")
        state = {k: v for k, v in state.items() if k != "slot_occupancy"}
    if not c.keys(state, expected_keys, "initial_state", "-", "initial_state"):
        return
    if state["time_min"] != 0.0:
        c.add("UNSUPPORTED_ASSUMPTION", "initial_state", "-", "initial_state.time_min", "must be 0.0")
    status_map = state["block_status"]
    if not isinstance(status_map, dict) or set(status_map) != set(blocks) or any(
            v not in YARD_BLOCK_STATUSES for v in status_map.values()):
        c.add("UNSUPPORTED_ASSUMPTION", "initial_state", "-", "initial_state.block_status",
              "must map every block id to open, closed or maintenance")
    locations = state["container_locations"]
    if not isinstance(locations, list):
        c.add("UNSUPPORTED_ASSUMPTION", "initial_state", "-", "initial_state.container_locations",
              "must be a list")
        return
    seen: dict[str, dict[str, Any]] = {}
    occupied: dict[str, float] = {bid: 0.0 for bid in blocks}
    for i, entry in enumerate(locations):
        path = f"initial_state.container_locations[{i}]"
        cid = entry.get("container_id", i) if isinstance(entry, dict) else i
        if not c.keys(entry, m.INITIAL_LOCATION_KEYS, "container", cid, path):
            continue
        if cid not in containers:
            c.add("UNKNOWN_REFERENCE", "container", cid, f"{path}.container_id", "unknown container")
            continue
        if cid in seen:
            c.add("DUPLICATE_PHYSICAL_LOCATION", "container", cid, path,
                  "container has more than one initial location")
            continue
        loc = entry["location"]
        if not c.keys(loc, m.LOCATION_KEYS, "container", cid, f"{path}.location"):
            continue
        seen[cid] = entry
        record = containers[cid]
        status, kind = entry["status"], loc["kind"]
        if status not in m.CONTAINER_STATUSES or kind not in m.LOCATION_KINDS:
            c.add("UNSUPPORTED_ASSUMPTION", "container", cid, path, "unknown status or location kind")
            continue
        if _INITIAL_STATUS_KIND.get(status) != kind:
            c.add("INVALID_STATUS_TRANSITION", "container", cid, f"{path}.status",
                  f"{status} at {kind} is not a valid time-zero state")
            continue
        present = record["present_at_episode_start"] is True
        flow = record["cargo_flow"]
        if status == "IN_YARD" and not present or status != "IN_YARD" and present:
            c.add("INVALID_STATUS_TRANSITION", "container", cid, f"{path}.status",
                  "present_at_episode_start containers must start IN_YARD and only they may")
        if status == "EXPECTED_BY_VESSEL" and (flow == "export" or loc["location_id"] != record["origin_vessel_id"]):
            c.add("INVALID_STATUS_TRANSITION", "container", cid, f"{path}.location",
                  "EXPECTED_BY_VESSEL requires import/transshipment aboard its origin vessel")
        if status == "EXPECTED_BY_LANDSIDE" and (flow != "export" or loc["location_id"] is not None):
            c.add("INVALID_STATUS_TRANSITION", "container", cid, f"{path}.location",
                  "EXPECTED_BY_LANDSIDE requires an export outside the terminal")
        slot_fields = (loc["bay"], loc["row"], loc["tier"])
        if kind != "YARD_BLOCK":
            if any(v is not None for v in slot_fields) or loc["slot_resolution"] is not None:
                c.add("FIDELITY_MISLABEL", "container", cid, f"{path}.location",
                      "slot fields are only meaningful in a yard block")
            continue
        bid = loc["location_id"]
        if bid not in blocks:
            c.add("UNKNOWN_REFERENCE", "container", cid, f"{path}.location.location_id",
                  f"unknown yard block {bid!r}")
            continue
        if fidelity == "G0" and (loc["slot_resolution"] != "BLOCK_ONLY" or any(v is not None for v in slot_fields)):
            c.add("FIDELITY_MISLABEL", "container", cid, f"{path}.location",
                  "G0 yard locations must be BLOCK_ONLY with null bay/row/tier (DQ19)")
        if fidelity == "G1" and loc["slot_resolution"] != "SLOT":
            c.add("FIDELITY_MISLABEL", "container", cid, f"{path}.location",
                  "G1 yard locations must be slot-resolved")
        block = blocks[bid]
        if record["container_size"] not in block["allowed_sizes"]:
            c.add("SLOT_SIZE_CONFLICT", "container", cid, f"{path}.location",
                  f"{record['container_size']} not allowed in block {bid}")
        required = {"empty"} if record["load_state"] == "empty" else (
            {"general"} | ({"reefer_power"} if record["is_reefer"] else set())
            | ({"hazardous"} if record["is_hazardous"] else set()))
        if not required <= set(block["capabilities"]):
            c.add("YARD_CAPABILITY_MISMATCH", "container", cid, f"{path}.location",
                  f"block {bid} lacks capabilities {sorted(required - set(block['capabilities']))}")
        if _num(record["size_teu"]):
            occupied[bid] += record["size_teu"]
    for cid in containers:
        if cid not in seen:
            c.add("UNSUPPORTED_ASSUMPTION", "container", cid, "initial_state.container_locations",
                  "container has no initial location")
    for bid, teu in occupied.items():
        capacity = blocks[bid]["capacity_teu"]
        if _num(capacity) and teu > capacity + TOL:
            c.add("YARD_CAPACITY_EXCEEDED", "yard_block", bid, "initial_state",
                  f"initial occupancy {teu} TEU exceeds capacity {capacity} TEU")
    if fidelity == "G1":
        _check_g1_slots(c, state["slot_occupancy"], containers, blocks, seen)


def _check_g1_slots(c: _Collector, slot_occupancy: Any, containers: dict[str, Any],
                    blocks: dict[str, Any], locations: dict[str, dict[str, Any]]) -> None:
    if not isinstance(slot_occupancy, list):
        c.add("UNSUPPORTED_ASSUMPTION", "initial_state", "-", "initial_state.slot_occupancy",
              "must be a list of {block_id, slots}")
        return
    listed: set[str] = set()
    for i, entry in enumerate(slot_occupancy):
        path = f"initial_state.slot_occupancy[{i}]"
        if not c.keys(entry, m.SLOT_BLOCK_KEYS, "yard_block", entry.get("block_id", i) if isinstance(entry, dict) else i, path):
            continue
        bid = entry["block_id"]
        if bid not in blocks:
            c.add("UNKNOWN_REFERENCE", "yard_block", bid, f"{path}.block_id", "unknown yard block")
            continue
        validate_g1_block_slots(c, blocks[bid], entry["slots"], containers, path)
        for j, slot in enumerate(entry["slots"] if isinstance(entry["slots"], list) else []):
            if not isinstance(slot, dict) or slot.get("container_id") not in containers:
                continue
            cid = slot["container_id"]
            listed.add(cid)
            loc = locations.get(cid, {}).get("location", {})
            if (loc.get("location_id"), loc.get("bay"), loc.get("row"), loc.get("tier")) != (
                    bid, slot.get("bay"), slot.get("row"), slot.get("tier")):
                c.add("FIDELITY_MISLABEL", "container", cid, f"{path}.slots[{j}]",
                      "slot occupancy disagrees with the container's initial location")
    for cid, entry in locations.items():
        if entry["location"]["kind"] == "YARD_BLOCK" and cid not in listed:
            c.add("FIDELITY_MISLABEL", "container", cid, "initial_state.slot_occupancy",
                  "slot-resolved container missing from slot occupancy")


def validate_g1_block_slots(c: _Collector, block: dict[str, Any], slots: Any,
                            containers: dict[str, Any], path: str) -> None:
    """Foundation 6.4 simplified v1 slot rules for one block."""
    bid = block["block_id"]
    if not isinstance(slots, list):
        c.add("UNSUPPORTED_ASSUMPTION", "yard_block", bid, f"{path}.slots", "must be a list")
        return
    cells: dict[tuple[int, int, int], str] = {}
    classes: dict[tuple[int, int], set[str]] = {}
    placed = []
    for j, slot in enumerate(slots):
        spath = f"{path}.slots[{j}]"
        cid = slot.get("container_id", j) if isinstance(slot, dict) else j
        if not c.keys(slot, m.SLOT_KEYS, "container", cid, spath):
            continue
        if cid not in containers:
            c.add("UNKNOWN_REFERENCE", "container", cid, spath, "unknown container")
            continue
        bay, row, tier, span = slot["bay"], slot["row"], slot["tier"], slot["bay_span"]
        if not all(_int(v) for v in (bay, row, tier, span)):
            c.add("INVALID_STACK_POSITION", "container", cid, spath, "bay/row/tier/bay_span must be integers")
            continue
        size = containers[cid]["container_size"]
        expected_span = 2 if size == "40_ft" else 1
        if span != expected_span:
            c.add("SLOT_SIZE_CONFLICT", "container", cid, f"{spath}.bay_span",
                  f"{size} must span {expected_span} bay(s)")
            continue
        if size not in block["allowed_sizes"]:
            c.add("SLOT_SIZE_CONFLICT", "container", cid, spath, f"{size} not allowed in block {bid}")
        if not (1 <= bay and bay + span - 1 <= block["bay_count"] and 1 <= row <= block["row_count"]
                and 1 <= tier <= block["max_tiers"]):
            c.add("INVALID_STACK_POSITION", "container", cid, spath,
                  f"address outside 1-based grid (bays {block['bay_count']}, rows "
                  f"{block['row_count']}, tiers {block['max_tiers']})")
            continue
        if span == 2 and bay % 2 == 0:
            c.add("INVALID_STACK_POSITION", "container", cid, f"{spath}.bay",
                  "40 ft anchor bay must be odd (covers bay and bay + 1)")
            continue
        conflict = False
        for b in range(bay, bay + span):
            if (b, row, tier) in cells:
                c.add("DUPLICATE_PHYSICAL_LOCATION", "container", cid, spath,
                      f"cell bay {b} row {row} tier {tier} already holds {cells[(b, row, tier)]}")
                conflict = True
        if conflict:
            continue
        for b in range(bay, bay + span):
            cells[(b, row, tier)] = cid
        pair = (bay - (bay - 1) % 2, row)
        classes.setdefault(pair, set()).add(size)
        placed.append((cid, bay, row, tier, span, spath))
    for (pair_bay, row), sizes in classes.items():
        if len(sizes) > 1:
            c.add("SLOT_SIZE_CONFLICT", "yard_block", bid, path,
                  f"stack position bays {pair_bay}-{pair_bay + 1} row {row} mixes 20 ft and 40 ft")
    for cid, bay, row, tier, span, spath in placed:
        if tier > 1 and any((b, row, tier - 1) not in cells for b in range(bay, bay + span)):
            c.add("FLOATING_STACK", "container", cid, spath,
                  f"tier {tier} lacks support at tier {tier - 1} under its full footprint")


def _check_fingerprint_keys(c: _Collector, doc: dict[str, Any]) -> bool:
    from integrated_terminal_pilot.scenarios.fingerprints import FINGERPRINT_KEYS

    block = doc["fingerprints"]
    if not isinstance(block, dict) or set(block) != set(FINGERPRINT_KEYS):
        missing = sorted(set(FINGERPRINT_KEYS) - set(block)) if isinstance(block, dict) else list(FINGERPRINT_KEYS)
        c.add("FINGERPRINT_INCOMPLETE", "scenario", doc["identity"]["scenario_id"], "fingerprints",
              f"fingerprint block must contain exactly {list(FINGERPRINT_KEYS)}; missing {missing}")
        return False
    return True


def _check_fingerprints(c: _Collector, doc: dict[str, Any]) -> None:
    from integrated_terminal_pilot.scenarios.fingerprints import compute_fingerprints

    if not _check_fingerprint_keys(c, doc):
        return
    sid = doc["identity"]["scenario_id"]
    stored = doc["fingerprints"]
    generator_fp = stored["generator_config_fingerprint"]
    if generator_fp is not None and not isinstance(generator_fp, str):
        c.add("FINGERPRINT_INCOMPLETE", "scenario", sid, "fingerprints.generator_config_fingerprint",
              "must be a string or null")
        return
    try:
        recomputed = compute_fingerprints(doc, generator_config_fingerprint=generator_fp)
    except (KeyError, TypeError, ValueError) as error:
        c.add("UNSUPPORTED_ASSUMPTION", "scenario", sid, "fingerprints",
              f"fingerprints (including the berth projection) could not be recomputed: {error}")
        return
    for key, value in recomputed.items():
        if stored[key] != value:
            c.add("FINGERPRINT_MISMATCH", "scenario", sid, f"fingerprints.{key}",
                  "stored fingerprint differs from the recomputed value")
