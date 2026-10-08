"""Generator configuration and its Step 2 decision register.

The configuration (``itp_generator_v1.yaml``) holds parameter values only. The
decision register (``itp_generator_v1_decisions.yaml``) records, for every
parameter, its source, status and rationale. Loading fails unless every
configured leaf is covered by exactly one decision whose selected value equals
the configured value, so values and their justification cannot drift apart.
"""

from __future__ import annotations

import copy
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from integrated_terminal_pilot.scenarios.fingerprints import sha256_of

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "generator" / "itp_generator_v1.yaml"
DEFAULT_DECISIONS_PATH = PROJECT_ROOT / "configs" / "generator" / "itp_generator_v1_decisions.yaml"

GENERATOR_VERSION = "itp_generator_v1"
SCENARIO_SCHEMA_VERSION = "itp_scenario_v1"
SPLITS = ("development", "validation", "test", "diagnostic")
DECISION_STATUSES = ("FROZEN", "PROPOSED_PENDING_REVIEW", "BLOCKED", "DEFERRED")
SOURCE_KINDS = ("STEP1_FROZEN", "STEP1_PROPOSED", "STEP1_INFERRED", "REPOSITORY_DERIVED",
                "STEP2_PROVISIONAL", "STEP2_BRIEF")
METADATA_KEYS = ("config_schema_version",)
DECISION_FIELDS = (
    "decision_id", "parameter_name", "parameter_paths", "selected_value", "unit",
    "allowed_range", "source_kind", "source_document", "source_section", "rationale",
    "status", "linked_step1_decision", "impact_on_generator", "impact_on_future_simulator",
)
OPTIONAL_DECISION_FIELDS = ("selected_values", "blocks")
FAMILY_KEYS = {
    "role": None,
    "ppo_regime": None,
    "traffic": ("vessel_count", "mean_interarrival_minutes", "min_vessel_length_m",
                "max_vessel_length_m", "min_workload_moves", "max_workload_moves"),
    "terminal": ("berth_length_m", "min_clearance_m", "quay_crane_count",
                 "quay_crane_moves_per_hour", "max_cranes_per_vessel"),
    "yard": ("block_count", "capacity_teu", "bay_count", "row_count", "max_tiers",
             "handling_capacity_moves_per_hour", "initial_occupancy_fraction"),
}
TOP_LEVEL_KEYS = (
    "config_schema_version", "generator_version", "scenario_schema_version", "stream_namespace",
    "seed_bands", "generation_policy", "development_batch", "families", "yard_layout", "cargo",
    "landside", "physics_profiles",
)
PHYSICS_PROFILES = ("standard_v1", "degenerate_equivalence_v1")


class GeneratorConfigError(ValueError):
    """The generator configuration or its decision register is invalid."""


@dataclass(frozen=True)
class GeneratorConfig:
    """Validated generator parameters plus their decision records (never mutated)."""

    parameters: dict[str, Any]
    decisions: tuple[dict[str, Any], ...]
    config_path: str
    decisions_path: str
    config_file_sha256: str
    decisions_file_sha256: str

    @property
    def parameters_fingerprint(self) -> str:
        """Canonical hash of parameter values (format- and path-independent)."""
        return sha256_of(self.parameters)

    def family(self, name: str) -> dict[str, Any]:
        try:
            return self.parameters["families"][name]
        except KeyError as error:
            raise GeneratorConfigError(f"Unknown scenario family: {name}") from error

    @property
    def family_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.parameters["families"]))

    def seed_band(self, split: str) -> tuple[int, int]:
        band = self.parameters["seed_bands"][split]
        return int(band["first"]), int(band["last"])

    def split_of_seed(self, seed: int) -> str | None:
        for split in SPLITS:
            first, last = self.seed_band(split)
            if first <= seed <= last:
                return split
        return None

    def physics_profile(self, name: str) -> dict[str, Any]:
        if name not in PHYSICS_PROFILES:
            raise GeneratorConfigError(f"Unknown physics profile: {name}")
        return self.parameters["physics_profiles"][name]

    def decision_status_counts(self) -> dict[str, int]:
        counts = {status: 0 for status in DECISION_STATUSES}
        for record in self.decisions:
            counts[record["status"]] += 1
        return counts

    def blocked_decisions_for_family(self, family: str) -> list[dict[str, Any]]:
        """BLOCKED decisions that cover any parameter used by ``family`` (family or global paths)."""
        prefix = f"families.{family}"
        family_paths = ("families.",)
        blocked = []
        for record in self.decisions:
            if record["status"] != "BLOCKED":
                continue
            for path in record["parameter_paths"]:
                if path == prefix or path.startswith(prefix + ".") or not path.startswith(family_paths):
                    blocked.append(record)
                    break
        return blocked

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.parameters)


def load_generator_config(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    decisions_path: str | Path = DEFAULT_DECISIONS_PATH,
) -> GeneratorConfig:
    config_path, decisions_path = Path(config_path), Path(decisions_path)
    config_bytes = config_path.read_bytes()
    decisions_bytes = decisions_path.read_bytes()
    parameters = yaml.safe_load(config_bytes.decode("utf-8"))
    register = yaml.safe_load(decisions_bytes.decode("utf-8"))
    return build_generator_config(
        parameters, register, config_path=str(config_path), decisions_path=str(decisions_path),
        config_file_sha256=hashlib.sha256(config_bytes).hexdigest(),
        decisions_file_sha256=hashlib.sha256(decisions_bytes).hexdigest())


def build_generator_config(
    parameters: dict[str, Any],
    register: dict[str, Any],
    *,
    config_path: str = "<memory>",
    decisions_path: str = "<memory>",
    config_file_sha256: str = "",
    decisions_file_sha256: str = "",
) -> GeneratorConfig:
    if not isinstance(parameters, dict):
        raise GeneratorConfigError("Generator configuration must be a mapping.")
    parameters = copy.deepcopy(parameters)
    _validate_parameters(parameters)
    decisions = _validate_register(register, parameters)
    return GeneratorConfig(parameters, decisions, config_path, decisions_path,
                           config_file_sha256, decisions_file_sha256)


def get_path(mapping: dict[str, Any], dotted: str) -> Any:
    value: Any = mapping
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted)
        value = value[part]
    return value


def set_path(mapping: dict[str, Any], dotted: str, new_value: Any) -> None:
    parts = dotted.split(".")
    target = mapping
    for part in parts[:-1]:
        target = target[part]
    if parts[-1] not in target:
        raise KeyError(dotted)
    target[parts[-1]] = new_value


def leaf_paths(mapping: dict[str, Any], prefix: str = "") -> list[str]:
    paths: list[str] = []
    for key in sorted(mapping):
        path = f"{prefix}.{key}" if prefix else str(key)
        value = mapping[key]
        if isinstance(value, dict) and value:
            paths.extend(leaf_paths(value, path))
        else:
            paths.append(path)
    return paths


def _fail(message: str) -> None:
    raise GeneratorConfigError(message)


def _number(value: Any, where: str, *, positive: bool = False, minimum: float | None = None,
            maximum: float | None = None, integer: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(f"{where} must be a finite number.")
    if integer and not isinstance(value, int):
        _fail(f"{where} must be an integer.")
    if positive and value <= 0:
        _fail(f"{where} must be greater than zero.")
    if minimum is not None and value < minimum:
        _fail(f"{where} must be >= {minimum}.")
    if maximum is not None and value > maximum:
        _fail(f"{where} must be <= {maximum}.")


def _exact_keys(mapping: Any, expected: tuple[str, ...], where: str) -> None:
    if not isinstance(mapping, dict):
        _fail(f"{where} must be a mapping.")
    missing = sorted(set(expected) - set(mapping))
    extra = sorted(set(mapping) - set(expected))
    if missing or extra:
        _fail(f"{where}: missing keys {missing}, unknown keys {extra}.")


def _validate_parameters(p: dict[str, Any]) -> None:
    _exact_keys(p, TOP_LEVEL_KEYS, "configuration")
    if p["config_schema_version"] != 1:
        _fail("config_schema_version must be 1.")
    if p["generator_version"] != GENERATOR_VERSION:
        _fail(f"generator_version must be {GENERATOR_VERSION}.")
    if p["scenario_schema_version"] != SCENARIO_SCHEMA_VERSION:
        _fail(f"scenario_schema_version must be {SCENARIO_SCHEMA_VERSION}.")
    if p["stream_namespace"] != "itp_v1":
        _fail("stream_namespace must be itp_v1 (protocol 6.3).")

    _exact_keys(p["seed_bands"], SPLITS, "seed_bands")
    bands = []
    for split in SPLITS:
        band = p["seed_bands"][split]
        _exact_keys(band, ("first", "last"), f"seed_bands.{split}")
        _number(band["first"], f"seed_bands.{split}.first", integer=True, minimum=0)
        _number(band["last"], f"seed_bands.{split}.last", integer=True, minimum=band["first"])
        bands.append((band["first"], band["last"], split))
    bands.sort()
    for (_, last, a), (first, _, b) in zip(bands, bands[1:]):
        if first <= last:
            _fail(f"Seed bands {a} and {b} overlap.")

    _exact_keys(p["generation_policy"], ("allowed_splits",), "generation_policy")
    allowed = p["generation_policy"]["allowed_splits"]
    if not isinstance(allowed, list) or not allowed or any(s not in SPLITS for s in allowed):
        _fail("generation_policy.allowed_splits must list known splits.")

    families = p["families"]
    if not isinstance(families, dict) or not families:
        _fail("families must be a non-empty mapping.")
    for name, family in families.items():
        if not isinstance(name, str) or not name.startswith("itp_"):
            _fail(f"Family names must start with 'itp_': {name!r}.")
        _validate_family(name, family)
    batch = p["development_batch"]
    if not isinstance(batch, dict) or set(batch) - set(families):
        _fail("development_batch must reference configured families.")
    for name, count in batch.items():
        _number(count, f"development_batch.{name}", integer=True, minimum=0)

    layout = p["yard_layout"]
    _exact_keys(layout, ("apron_depth_m", "block_gap_m", "ground_slot_length_m",
                         "ground_slot_width_m", "gate_setback_m", "bay_axis", "capabilities",
                         "allowed_sizes"), "yard_layout")
    for key in ("apron_depth_m", "block_gap_m", "ground_slot_length_m", "ground_slot_width_m",
                "gate_setback_m"):
        _number(layout[key], f"yard_layout.{key}", positive=True)
    if layout["bay_axis"] != "X":
        _fail("yard_layout.bay_axis must be 'X' (FROZEN v1).")
    from terminal_core import ContainerSize, YardCapability
    for value in layout["capabilities"]:
        if value not in {c.value for c in YardCapability}:
            _fail(f"Unknown yard capability {value!r}.")
    if not layout["allowed_sizes"] or any(
            value not in {s.value for s in ContainerSize} for value in layout["allowed_sizes"]):
        _fail("yard_layout.allowed_sizes must be non-empty ContainerSize values.")

    cargo = p["cargo"]
    _exact_keys(cargo, ("discharge_share_min", "discharge_share_max",
                        "transshipment_share_of_load", "max_transshipment_share_of_discharge",
                        "min_transshipment_connection_min", "forty_ft_share", "empty_share",
                        "reefer_share", "hazardous_share", "laden_weight_kg", "empty_weight_kg"),
                "cargo")
    _number(cargo["discharge_share_min"], "cargo.discharge_share_min", minimum=0.0, maximum=1.0)
    _number(cargo["discharge_share_max"], "cargo.discharge_share_max",
            minimum=cargo["discharge_share_min"], maximum=1.0)
    if not 0.0 < cargo["discharge_share_min"] or not cargo["discharge_share_max"] < 1.0:
        _fail("Discharge shares must lie strictly inside (0, 1).")
    for key in ("transshipment_share_of_load", "max_transshipment_share_of_discharge",
                "forty_ft_share", "empty_share", "reefer_share", "hazardous_share"):
        _number(cargo[key], f"cargo.{key}", minimum=0.0, maximum=1.0)
    _number(cargo["min_transshipment_connection_min"], "cargo.min_transshipment_connection_min",
            minimum=0.0)
    for size in ("20_ft", "40_ft"):
        bounds = cargo["laden_weight_kg"].get(size)
        _exact_keys(bounds, ("min", "max"), f"cargo.laden_weight_kg.{size}")
        _number(bounds["min"], f"cargo.laden_weight_kg.{size}.min", integer=True, positive=True)
        _number(bounds["max"], f"cargo.laden_weight_kg.{size}.max", integer=True,
                minimum=bounds["min"])
        _number(cargo["empty_weight_kg"].get(size), f"cargo.empty_weight_kg.{size}",
                integer=True, positive=True)
    _exact_keys(cargo["laden_weight_kg"], ("20_ft", "40_ft"), "cargo.laden_weight_kg")
    _exact_keys(cargo["empty_weight_kg"], ("20_ft", "40_ft"), "cargo.empty_weight_kg")

    landside = p["landside"]
    _exact_keys(landside, ("export_gate_lead_max_min", "import_dwell_min_min",
                           "import_dwell_max_min", "initial_import_pickup_max_min"), "landside")
    for key, value in landside.items():
        _number(value, f"landside.{key}", minimum=0.0)
    if landside["import_dwell_min_min"] > landside["import_dwell_max_min"]:
        _fail("landside.import_dwell_min_min exceeds import_dwell_max_min.")

    _validate_physics_profiles(p["physics_profiles"])


def _validate_family(name: str, family: Any) -> None:
    _exact_keys(family, tuple(FAMILY_KEYS), f"families.{name}")
    if family["role"] not in ("primary", "development_diagnostic"):
        _fail(f"families.{name}.role must be primary or development_diagnostic.")
    if family["ppo_regime"] not in ("medium_heavy", "tiny"):
        _fail(f"families.{name}.ppo_regime must be medium_heavy or tiny.")
    for section in ("traffic", "terminal", "yard"):
        _exact_keys(family[section], FAMILY_KEYS[section], f"families.{name}.{section}")
    t, term, yard = family["traffic"], family["terminal"], family["yard"]
    where = f"families.{name}"
    _number(t["vessel_count"], f"{where}.traffic.vessel_count", integer=True, minimum=1,
            maximum=999)
    _number(t["mean_interarrival_minutes"], f"{where}.traffic.mean_interarrival_minutes",
            positive=True)
    _number(t["min_vessel_length_m"], f"{where}.traffic.min_vessel_length_m", positive=True)
    _number(t["max_vessel_length_m"], f"{where}.traffic.max_vessel_length_m",
            minimum=t["min_vessel_length_m"])
    _number(t["min_workload_moves"], f"{where}.traffic.min_workload_moves", integer=True,
            minimum=2)
    _number(t["max_workload_moves"], f"{where}.traffic.max_workload_moves", integer=True,
            minimum=t["min_workload_moves"])
    _number(term["berth_length_m"], f"{where}.terminal.berth_length_m", positive=True)
    _number(term["min_clearance_m"], f"{where}.terminal.min_clearance_m", minimum=0.0)
    if t["max_vessel_length_m"] > term["berth_length_m"]:
        _fail(f"{where}: maximum vessel length exceeds quay length.")
    _number(term["quay_crane_count"], f"{where}.terminal.quay_crane_count", integer=True,
            minimum=1, maximum=99)
    _number(term["quay_crane_moves_per_hour"], f"{where}.terminal.quay_crane_moves_per_hour",
            positive=True)
    _number(term["max_cranes_per_vessel"], f"{where}.terminal.max_cranes_per_vessel",
            integer=True, minimum=1, maximum=term["quay_crane_count"])
    _number(yard["block_count"], f"{where}.yard.block_count", integer=True, minimum=1, maximum=99)
    _number(yard["capacity_teu"], f"{where}.yard.capacity_teu", positive=True)
    _number(yard["bay_count"], f"{where}.yard.bay_count", integer=True, minimum=2)
    if yard["bay_count"] % 2:
        _fail(f"{where}.yard.bay_count must be even (40 ft bay pairs).")
    _number(yard["row_count"], f"{where}.yard.row_count", integer=True, minimum=1)
    _number(yard["max_tiers"], f"{where}.yard.max_tiers", integer=True, minimum=2)
    _number(yard["handling_capacity_moves_per_hour"],
            f"{where}.yard.handling_capacity_moves_per_hour", positive=True)
    _number(yard["initial_occupancy_fraction"], f"{where}.yard.initial_occupancy_fraction",
            minimum=0.0, maximum=1.0)
    geometric = yard["bay_count"] * yard["row_count"] * yard["max_tiers"]
    fill = (yard["max_tiers"] - 1) / yard["max_tiers"]
    if yard["capacity_teu"] > geometric * fill + 1e-9:
        _fail(f"{where}.yard.capacity_teu exceeds geometric slots x operating fill limit "
              f"({geometric} x {fill:.3f}).")


def _validate_physics_profiles(profiles: Any) -> None:
    _exact_keys(profiles, PHYSICS_PROFILES, "physics_profiles")
    standard = profiles["standard_v1"]
    _exact_keys(standard, ("service", "crane", "transport", "yard", "work", "visibility",
                           "episode", "kernel", "landside"), "physics_profiles.standard_v1")
    from mini_port_sim.scenario import ServiceConfig
    service = standard["service"]
    _exact_keys(service, ("berthing_preparation_minutes", "service_minutes_per_move",
                          "departure_preparation_minutes"), "physics.service")
    if (service["berthing_preparation_minutes"], service["service_minutes_per_move"],
            service["departure_preparation_minutes"]) != (30.0, 0.5, 20.0):
        _fail("physics.service must equal ServiceConfig(30, 0.5, 20) (D20, FROZEN).")
    crane = standard["crane"]
    _exact_keys(crane, ("efficiency", "productivity_factor"), "physics.crane")
    _exact_keys(crane["efficiency"], ("one", "two", "three", "four_plus"), "physics.crane.efficiency")
    if crane["efficiency"]["one"] != 1.0:
        _fail("physics.crane.efficiency.one must be 1.0 (ServiceConfig.crane_efficiency(1)).")
    try:
        ServiceConfig(two_crane_efficiency=crane["efficiency"]["two"],
                      three_crane_efficiency=crane["efficiency"]["three"],
                      four_plus_crane_efficiency=crane["efficiency"]["four_plus"])
    except ValueError as error:
        _fail(f"physics.crane.efficiency rejected by Project 02 ServiceConfig: {error}")
    if crane["productivity_factor"] != 1.0:
        _fail("physics.crane.productivity_factor must be 1.0 (D19, FROZEN).")
    transport = standard["transport"]
    _exact_keys(transport, ("enabled", "speed_m_per_min", "handover_min", "units_per_crane"),
                "physics.transport")
    if not isinstance(transport["enabled"], bool):
        _fail("physics.transport.enabled must be boolean.")
    _number(transport["speed_m_per_min"], "physics.transport.speed_m_per_min", positive=True)
    _number(transport["handover_min"], "physics.transport.handover_min", minimum=0.0)
    _number(transport["units_per_crane"], "physics.transport.units_per_crane", integer=True,
            minimum=1)
    yard = standard["yard"]
    _exact_keys(yard, ("constraints_enabled", "congestion_rho0", "congestion_g_min",
                       "landside_reserved_fraction", "gate_flow_demand"), "physics.yard")
    if not isinstance(yard["constraints_enabled"], bool):
        _fail("physics.yard.constraints_enabled must be boolean.")
    _number(yard["congestion_rho0"], "physics.yard.congestion_rho0", minimum=0.0, maximum=0.999999)
    _number(yard["congestion_g_min"], "physics.yard.congestion_g_min", minimum=1e-9, maximum=1.0)
    _number(yard["landside_reserved_fraction"], "physics.yard.landside_reserved_fraction",
            minimum=0.0, maximum=1.0)
    if yard["gate_flow_demand"] != "block_handling_capacity":
        _fail("physics.yard.gate_flow_demand must be 'block_handling_capacity' (spec 5.4).")
    work = standard["work"]
    _exact_keys(work, ("batch_size_containers", "max_load_wait_min"), "physics.work")
    _number(work["batch_size_containers"], "physics.work.batch_size_containers", integer=True,
            minimum=1)
    _number(work["max_load_wait_min"], "physics.work.max_load_wait_min", positive=True)
    _exact_keys(standard["visibility"], ("future_horizon_min",), "physics.visibility")
    if standard["visibility"]["future_horizon_min"] != 240.0:
        _fail("physics.visibility.future_horizon_min must be 240.0 (D18, FROZEN).")
    _exact_keys(standard["episode"], ("max_drain_extension_min",), "physics.episode")
    _number(standard["episode"]["max_drain_extension_min"],
            "physics.episode.max_drain_extension_min", positive=True)
    _exact_keys(standard["kernel"], ("same_timestamp_cycle_limit",), "physics.kernel")
    _number(standard["kernel"]["same_timestamp_cycle_limit"],
            "physics.kernel.same_timestamp_cycle_limit", integer=True, minimum=1)
    _exact_keys(standard["landside"], ("export_cutoff_min",), "physics.landside")
    _number(standard["landside"]["export_cutoff_min"], "physics.landside.export_cutoff_min",
            minimum=0.0)
    degenerate = profiles["degenerate_equivalence_v1"]
    _exact_keys(degenerate, ("base_profile", "quay_crane_moves_per_hour", "max_cranes_per_vessel",
                             "quay_crane_count_rule", "transport_enabled",
                             "yard_constraints_enabled"), "physics_profiles.degenerate_equivalence_v1")
    expected = {"base_profile": "standard_v1", "quay_crane_moves_per_hour": 120.0,
                "max_cranes_per_vessel": 1, "quay_crane_count_rule": "max_coexisting_vessels",
                "transport_enabled": False, "yard_constraints_enabled": False}
    if degenerate != expected:
        _fail("physics_profiles.degenerate_equivalence_v1 must equal the Step 1 profile "
              "(data contract 6).")


def _validate_register(register: Any, parameters: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    if not isinstance(register, dict) or register.get("register_version") != 1:
        _fail("Decision register must be a mapping with register_version 1.")
    records = register.get("records")
    if not isinstance(records, list) or not records:
        _fail("Decision register needs records.")
    leaves = [path for path in leaf_paths(parameters) if path.split(".")[0] not in METADATA_KEYS]
    covered: dict[str, str] = {}
    ids: set[str] = set()
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            _fail("Each decision record must be a mapping.")
        missing = [f for f in DECISION_FIELDS if f not in record]
        extra = sorted(set(record) - set(DECISION_FIELDS) - set(OPTIONAL_DECISION_FIELDS))
        if missing or extra:
            _fail(f"Decision {record.get('decision_id')}: missing {missing}, unknown {extra}.")
        decision_id = record["decision_id"]
        if decision_id in ids:
            _fail(f"Duplicate decision_id {decision_id}.")
        ids.add(decision_id)
        if record["status"] not in DECISION_STATUSES:
            _fail(f"Decision {decision_id}: invalid status {record['status']!r}.")
        if record["source_kind"] not in SOURCE_KINDS:
            _fail(f"Decision {decision_id}: invalid source_kind {record['source_kind']!r}.")
        if record["status"] == "FROZEN" and record["source_kind"] not in ("STEP1_FROZEN",
                                                                         "STEP2_BRIEF"):
            _fail(f"Decision {decision_id}: only Step 1 FROZEN or Step 2 brief rules may be FROZEN.")
        paths = record["parameter_paths"]
        if not isinstance(paths, list) or not paths:
            _fail(f"Decision {decision_id}: parameter_paths must be a non-empty list.")
        per_path = record.get("selected_values")
        if per_path is not None:
            if record["selected_value"] is not None or set(per_path) != set(paths):
                _fail(f"Decision {decision_id}: selected_values must map exactly its paths and "
                      "selected_value must be null.")
        for path in paths:
            try:
                configured = get_path(parameters, path)
            except KeyError:
                _fail(f"Decision {decision_id}: unknown parameter path {path}.")
            expected = per_path[path] if per_path is not None else record["selected_value"]
            if configured != expected:
                _fail(f"Decision {decision_id}: selected value for {path} ({expected!r}) differs "
                      f"from configuration ({configured!r}).")
            sub_leaves = ([leaf for leaf in leaves if leaf == path or leaf.startswith(path + ".")])
            if not sub_leaves:
                _fail(f"Decision {decision_id}: path {path} covers no parameter.")
            for leaf in sub_leaves:
                if leaf in covered:
                    _fail(f"Parameter {leaf} covered by both {covered[leaf]} and {decision_id}.")
                covered[leaf] = decision_id
        normalized.append(copy.deepcopy(record))
    uncovered = [leaf for leaf in leaves if leaf not in covered]
    if uncovered:
        _fail(f"Parameters without a decision record: {uncovered}.")
    return tuple(normalized)
