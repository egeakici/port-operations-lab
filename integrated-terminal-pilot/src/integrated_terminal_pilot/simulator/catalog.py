"""Immutable scenario definition used by the kernel (``ScenarioDefinition`` of spec §4).

The catalog is built once from an ``itp_scenario_v1`` document and is never
mutated. Kernel clones share it by reference; only mutable execution state is
copied (data contract §8.1). Containers are indexed ``0..N-1`` in
``container_id`` order, and the mutable state stores per-container facts in
flat lists over that index.

The catalog also holds derived, immutable indexes used by dispatch (discharge
containers of each vessel by group, load lists, exogenous schedules). None of
them is mutable state.

``redacted(...)`` builds the restricted catalog of an observable clone (spec
§10): hidden vessels, their inbound cargo, unreceived exports of hidden vessels
and all not-yet-occurred gate-in and pickup times are removed, together with
scenario identity and fingerprints.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from mini_port_sim.scenario import ServiceConfig

from integrated_terminal_pilot.scenarios.models import PRE_EPISODE, TEU_BY_SIZE
from integrated_terminal_pilot.simulator.errors import UnsupportedScenario


@dataclass(frozen=True)
class PhysicsConfig:
    """Physics block of the scenario (data contract §6), with derived helpers."""

    berthing_preparation_min: float
    service_minutes_per_move: float
    departure_preparation_min: float
    efficiency_one: float
    efficiency_two: float
    efficiency_three: float
    efficiency_four_plus: float
    productivity_factor: float
    transport_enabled: bool
    transport_speed_m_per_min: float
    transport_handover_min: float
    transport_units_per_crane: int
    yard_constraints_enabled: bool
    congestion_rho0: float
    congestion_g_min: float
    landside_reserved_fraction: float
    gate_flow_demand: str
    batch_size_containers: int
    max_load_wait_min: float
    future_horizon_min: float
    max_drain_extension_min: float
    same_timestamp_cycle_limit: int
    export_cutoff_min: float
    # Not part of the scenario schema. "assigned" is the frozen Step 4 reference (spec §5.1:
    # eff(n) with n = cranes assigned to the vessel). "working" (cranes actually working a batch)
    # exists only as a Step 4 closure *diagnostic* override; it is never read from a scenario.
    efficiency_basis: str = "assigned"

    @classmethod
    def from_document(cls, physics: dict[str, Any]) -> "PhysicsConfig":
        eff = physics["crane"]["efficiency"]
        config = cls(
            berthing_preparation_min=float(physics["service"]["berthing_preparation_minutes"]),
            service_minutes_per_move=float(physics["service"]["service_minutes_per_move"]),
            departure_preparation_min=float(physics["service"]["departure_preparation_minutes"]),
            efficiency_one=float(eff["one"]), efficiency_two=float(eff["two"]),
            efficiency_three=float(eff["three"]), efficiency_four_plus=float(eff["four_plus"]),
            productivity_factor=float(physics["crane"]["productivity_factor"]),
            transport_enabled=bool(physics["transport"]["enabled"]),
            transport_speed_m_per_min=float(physics["transport"]["speed_m_per_min"]),
            transport_handover_min=float(physics["transport"]["handover_min"]),
            transport_units_per_crane=int(physics["transport"]["units_per_crane"]),
            yard_constraints_enabled=bool(physics["yard"]["constraints_enabled"]),
            congestion_rho0=float(physics["yard"]["congestion_rho0"]),
            congestion_g_min=float(physics["yard"]["congestion_g_min"]),
            landside_reserved_fraction=float(physics["yard"]["landside_reserved_fraction"]),
            gate_flow_demand=str(physics["yard"]["gate_flow_demand"]),
            batch_size_containers=int(physics["work"]["batch_size_containers"]),
            max_load_wait_min=float(physics["work"]["max_load_wait_min"]),
            future_horizon_min=float(physics["visibility"]["future_horizon_min"]),
            max_drain_extension_min=float(physics["episode"]["max_drain_extension_min"]),
            same_timestamp_cycle_limit=int(physics["kernel"]["same_timestamp_cycle_limit"]),
            export_cutoff_min=float(physics["landside"]["export_cutoff_min"]),
        )
        config.check_supported()
        return config

    def check_supported(self) -> None:
        """Reject assumptions v1 physics does not execute (DQ20); never repair them."""
        problems = []
        if self.efficiency_one != 1.0:
            problems.append("crane.efficiency.one must be 1.0 (Project 02 ServiceConfig semantics)")
        if self.productivity_factor != 1.0:
            problems.append("crane.productivity_factor must be 1.0 (D19)")
        if self.gate_flow_demand != "block_handling_capacity":
            problems.append(f"yard.gate_flow_demand {self.gate_flow_demand!r} is not supported "
                            "(only block_handling_capacity, spec §5.4)")
        if self.batch_size_containers < 1:
            problems.append("work.batch_size_containers must be >= 1 (D15)")
        if self.same_timestamp_cycle_limit < 1:
            problems.append("kernel.same_timestamp_cycle_limit must be >= 1")
        for name in ("transport_speed_m_per_min", "transport_handover_min", "max_load_wait_min",
                     "max_drain_extension_min", "berthing_preparation_min",
                     "departure_preparation_min"):
            if getattr(self, name) < 0.0:
                problems.append(f"{name} must be >= 0")
        if self.transport_enabled and (self.transport_speed_m_per_min <= 0.0
                                       or self.transport_units_per_crane < 1):
            problems.append("enabled transport needs speed > 0 and >= 1 unit per crane")
        if not 0.0 <= self.congestion_rho0 < 1.0 or not 0.0 < self.congestion_g_min <= 1.0:
            problems.append("congestion needs rho0 in [0, 1) and g_min in (0, 1]")
        if not 0.0 <= self.landside_reserved_fraction <= 1.0:
            problems.append("landside_reserved_fraction must be in [0, 1]")
        if self.efficiency_basis not in ("assigned", "working"):
            problems.append(f"efficiency_basis {self.efficiency_basis!r} must be assigned or working")
        if problems:
            raise UnsupportedScenario("; ".join(problems))

    def service_config(self) -> ServiceConfig:
        """Project 02 ``ServiceConfig`` carrying this physics' nominal and efficiency values (D09, D20)."""
        return ServiceConfig(
            berthing_preparation_minutes=self.berthing_preparation_min,
            service_minutes_per_move=self.service_minutes_per_move,
            departure_preparation_minutes=self.departure_preparation_min,
            two_crane_efficiency=self.efficiency_two,
            three_crane_efficiency=self.efficiency_three,
            four_plus_crane_efficiency=self.efficiency_four_plus,
        )


@dataclass(frozen=True)
class ContainerRecord:
    """Immutable container facts (foundation §2). ``index`` is the kernel's array index."""

    index: int
    container_id: str
    group_id: str
    container_size: str
    size_teu: float
    load_state: str
    is_reefer: bool
    is_hazardous: bool
    cargo_flow: str
    origin_vessel_id: str | None
    destination_vessel_id: str | None
    present_at_start: bool
    gate_in_time_min: float | None
    pickup_time_min: float | None

    @property
    def required_capabilities(self) -> frozenset[str]:
        if self.load_state == "empty":
            return frozenset({"empty"})
        required = {"general"}
        if self.is_reefer:
            required.add("reefer_power")
        if self.is_hazardous:
            required.add("hazardous")
        return frozenset(required)


@dataclass(frozen=True)
class VesselRecord:
    vessel_id: str
    arrival_time_min: float
    length_m: float
    max_cranes: int
    priority: int
    discharge_move_count: int
    load_move_count: int
    workload_moves: int
    nominal_service_time_min: float
    # (group_id, container indices in container_id order) per discharge group, groups in id order.
    discharge_groups: tuple[tuple[str, tuple[int, ...]], ...]
    load_container_indices: tuple[int, ...]


@dataclass(frozen=True)
class CraneRecord:
    crane_id: str
    nominal_moves_per_hour: float
    compatible_vessel_ids: tuple[str, ...] | None
    record: dict  # original scenario record (static fields for observation helpers)


@dataclass(frozen=True)
class BlockRecord:
    block_id: str
    capacity_teu: float
    capabilities: frozenset[str]
    allowed_sizes: frozenset[str]
    handling_capacity_moves_per_hour: float
    transfer_point_x_m: float
    transfer_point_y_m: float
    record: dict


@dataclass(frozen=True)
class ScenarioCatalog:
    scenario_id: str | None
    identity: dict | None
    fingerprints: dict | None
    yard_fidelity: str
    berth_length_m: float
    min_clearance_m: float
    gate_id: str
    physics: PhysicsConfig
    vessels: tuple[VesselRecord, ...]
    vessel_by_id: dict
    cranes: tuple[CraneRecord, ...]
    crane_by_id: dict
    blocks: tuple[BlockRecord, ...]
    block_by_id: dict
    groups: dict  # group_id -> group record (dict)
    containers: tuple[ContainerRecord, ...]
    container_index: dict  # container_id -> index
    initial_locations: tuple[tuple[str, str, str | None], ...]  # per index: (status, kind, location_id)
    initial_block_status: dict
    last_arrival_min: float
    drain_limit_min: float
    observable: bool = False

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_document(cls, doc: dict[str, Any], *, validate: bool = True) -> "ScenarioCatalog":
        """Build the catalog; ``validate`` runs the full Step 2 scenario validator first."""
        if validate:
            from integrated_terminal_pilot.scenarios.validation import validate_scenario

            report = validate_scenario(doc)
            if not report.ok:
                first = report.issues[0]
                raise UnsupportedScenario(
                    f"scenario failed Step 2 validation ({len(report.issues)} issue(s); first: "
                    f"{first.code} {first.message})", code=first.code)
        identity = doc["identity"]
        if identity["yard_fidelity"] != "G0":
            raise UnsupportedScenario("the v1 kernel executes G0 only; G1 bookkeeping is disabled "
                                      "in primary experiments (D12)")
        for crane in doc["resources"]["quay_cranes"]:
            if crane["unavailability_windows"]:
                raise UnsupportedScenario(f"crane {crane['crane_id']}: unavailability windows must be "
                                          "empty in v1 (D19)")
        if len(doc["terminal"]["gates"]) != 1:
            raise UnsupportedScenario("v1 kernel models exactly one gate")
        physics = PhysicsConfig.from_document(doc["physics"])
        quay = doc["terminal"]["quay"]

        container_docs = sorted(doc["containers"], key=lambda c: c["container_id"])
        containers = tuple(_container_record(i, c) for i, c in enumerate(container_docs))
        container_index = {c.container_id: c.index for c in containers}
        locations: list[Any] = [None] * len(containers)
        for entry in doc["initial_state"]["container_locations"]:
            loc = entry["location"]
            locations[container_index[entry["container_id"]]] = (entry["status"], loc["kind"],
                                                                  loc["location_id"])
        if any(entry is None for entry in locations):
            raise UnsupportedScenario("every container needs an initial location")
        groups = {g["group_id"]: dict(g) for g in doc["container_groups"]}
        vessels = tuple(_vessel_records(doc["vessels"], containers))
        cranes = tuple(CraneRecord(c["crane_id"], float(c["nominal_moves_per_hour"]),
                                   None if c["compatible_vessel_ids"] is None
                                   else tuple(sorted(c["compatible_vessel_ids"])), dict(c))
                       for c in sorted(doc["resources"]["quay_cranes"], key=lambda c: c["crane_id"]))
        blocks = tuple(BlockRecord(b["block_id"], float(b["capacity_teu"]), frozenset(b["capabilities"]),
                                   frozenset(b["allowed_sizes"]),
                                   float(b["handling_capacity_moves_per_hour"]),
                                   float(b["transfer_point_x_m"]), float(b["transfer_point_y_m"]), dict(b))
                       for b in sorted(doc["terminal"]["yard_blocks"], key=lambda b: b["block_id"]))
        last_arrival = max((v.arrival_time_min for v in vessels), default=0.0)
        return cls(
            scenario_id=identity["scenario_id"], identity=dict(identity),
            fingerprints=dict(doc.get("fingerprints") or {}), yard_fidelity=identity["yard_fidelity"],
            berth_length_m=float(quay["berth_length_m"]), min_clearance_m=float(quay["min_clearance_m"]),
            gate_id=doc["terminal"]["gates"][0]["gate_id"], physics=physics,
            vessels=vessels, vessel_by_id={v.vessel_id: v for v in vessels},
            cranes=cranes, crane_by_id={c.crane_id: c for c in cranes},
            blocks=blocks, block_by_id={b.block_id: b for b in blocks}, groups=groups,
            containers=containers, container_index=container_index,
            initial_locations=tuple(locations),
            initial_block_status=dict(doc["initial_state"]["block_status"]),
            last_arrival_min=last_arrival,
            drain_limit_min=last_arrival + physics.max_drain_extension_min,
        )

    # ------------------------------------------------------------------ queries
    def announce_time(self, vessel: VesselRecord) -> float | None:
        """Horizon entry time, or None when the arrival itself reveals the vessel (Project 03 rule)."""
        horizon = self.physics.future_horizon_min
        if horizon > 0.0 and vessel.arrival_time_min > 0.0:
            return max(0.0, vessel.arrival_time_min - horizon)
        return None

    def container(self, container_id: str) -> ContainerRecord:
        return self.containers[self.container_index[container_id]]

    # ------------------------------------------------------------------ observable redaction
    def redacted(self, *, visible_vessel_ids: Iterable[str], keep_indices: Iterable[int],
                 due_pickup_indices: Iterable[int], drain_limit_min: float) -> "ScenarioCatalog":
        """Catalog of an observable clone: only visible vessels and observable containers.

        ``keep_indices`` (old index space) are the containers that remain;
        gate-in times are dropped for all of them and pickup times are kept only
        for ``due_pickup_indices`` (requests that already occurred).
        """
        visible = set(visible_vessel_ids)
        keep = sorted(set(keep_indices))
        due = set(due_pickup_indices)
        remap = {old: new for new, old in enumerate(keep)}
        containers = tuple(replace(self.containers[old], index=remap[old], gate_in_time_min=None,
                                   pickup_time_min=(self.containers[old].pickup_time_min
                                                    if old in due else None))
                           for old in keep)
        vessels = []
        for vessel in self.vessels:
            if vessel.vessel_id not in visible:
                continue
            vessels.append(replace(
                vessel,
                discharge_groups=tuple((g, tuple(remap[i] for i in members))
                                       for g, members in vessel.discharge_groups),
                load_container_indices=tuple(remap[i] for i in vessel.load_container_indices
                                             if i in remap)))
        group_ids = {c.group_id for c in containers}
        return replace(
            self, scenario_id=None, identity=None, fingerprints=None,
            vessels=tuple(vessels), vessel_by_id={v.vessel_id: v for v in vessels},
            groups={g: rec for g, rec in self.groups.items() if g in group_ids},
            containers=containers, container_index={c.container_id: c.index for c in containers},
            initial_locations=tuple(self.initial_locations[old] for old in keep),
            last_arrival_min=max((v.arrival_time_min for v in vessels), default=0.0),
            drain_limit_min=drain_limit_min, observable=True)


def _container_record(index: int, c: dict[str, Any]) -> ContainerRecord:
    if c["container_size"] not in TEU_BY_SIZE:
        raise UnsupportedScenario(f"{c['container_id']}: unsupported size {c['container_size']}")
    return ContainerRecord(
        index=index, container_id=c["container_id"], group_id=c["container_group_id"],
        container_size=c["container_size"], size_teu=float(c["size_teu"]), load_state=c["load_state"],
        is_reefer=bool(c["is_reefer"]), is_hazardous=bool(c["is_hazardous"]),
        cargo_flow=c["cargo_flow"], origin_vessel_id=c["origin_vessel_id"],
        destination_vessel_id=c["destination_vessel_id"],
        present_at_start=bool(c["present_at_episode_start"]),
        gate_in_time_min=(None if c["scheduled_gate_in_time_min"] is None
                          else float(c["scheduled_gate_in_time_min"])),
        pickup_time_min=(None if c["scheduled_pickup_time_min"] is None
                         else float(c["scheduled_pickup_time_min"])))


def _vessel_records(vessel_docs: list[dict[str, Any]],
                    containers: tuple[ContainerRecord, ...]) -> list[VesselRecord]:
    by_origin: dict[str, dict[str, list[int]]] = {}
    by_destination: dict[str, list[int]] = {}
    for c in containers:
        if c.origin_vessel_id not in (None, PRE_EPISODE) and not c.present_at_start:
            by_origin.setdefault(c.origin_vessel_id, {}).setdefault(c.group_id, []).append(c.index)
        if c.destination_vessel_id is not None:
            by_destination.setdefault(c.destination_vessel_id, []).append(c.index)
    records = []
    for v in sorted(vessel_docs, key=lambda v: (v["arrival_time_min"], v["vessel_id"])):
        vid = v["vessel_id"]
        groups = by_origin.get(vid, {})
        discharge = tuple((g, tuple(groups[g])) for g in sorted(groups))
        loads = tuple(by_destination.get(vid, ()))
        if sum(len(m) for _, m in discharge) != v["discharge_move_count"] or len(loads) != v["load_move_count"]:
            raise UnsupportedScenario(f"{vid}: move counts do not reconcile with containers "
                                      "(WORKLOAD_RECONCILIATION_FAILURE)",
                                      code="WORKLOAD_RECONCILIATION_FAILURE")
        if v["extra_work_units"] != 0:
            raise UnsupportedScenario(f"{vid}: extra_work_units must be 0 (D14)")
        records.append(VesselRecord(
            vessel_id=vid, arrival_time_min=float(v["arrival_time_min"]), length_m=float(v["length_m"]),
            max_cranes=int(v["max_cranes"]), priority=int(v["priority"]),
            discharge_move_count=int(v["discharge_move_count"]),
            load_move_count=int(v["load_move_count"]), workload_moves=int(v["workload_moves"]),
            nominal_service_time_min=float(v["nominal_service_time_min"]),
            discharge_groups=discharge, load_container_indices=loads))
    return records


__all__ = ["BlockRecord", "ContainerRecord", "CraneRecord", "PhysicsConfig", "ScenarioCatalog",
           "VesselRecord"]
