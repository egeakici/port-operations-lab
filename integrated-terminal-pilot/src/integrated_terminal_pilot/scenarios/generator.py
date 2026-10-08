"""itp_generator_v1: deterministic synthetic integrated-terminal scenario definitions.

The generator produces immutable scenario inputs only. It never chooses berth
positions, assigns cranes, chooses yard blocks for vessel cargo, places
containers in slots, or simulates operations.

Draw structure (all draws via entity-keyed streams, protocol 6.3):

* Vessels ``V001..Vnnn`` in arrival order, following Project 03
  ``SyntheticScenarioGenerator`` logic: first arrival at 0, exponential
  inter-arrivals with the family mean, length ``U[min, max]`` rounded to 0.01 m,
  workload ``randint(min, max)``. Keys: ``vessel|Vxxx|interarrival|length|workload``.
* Workload split: ``discharge = round(workload x U[share_min, share_max])``
  (clamped to ``1 .. workload-1``), ``load = workload - discharge``.
* Transshipment (deterministic, no draws): each vessel's load needs
  ``round(load x transshipment_share_of_load)`` transshipment containers.
  These are served one by one from earlier vessels arriving at least
  ``min_transshipment_connection_min`` before it, each limited to
  ``floor(discharge x max_transshipment_share_of_discharge)``, choosing the
  source with the most remaining capacity (ties: earliest arrival, then id).
  Unserved demand becomes pre-episode transshipment inventory
  (origin ``PRE_EPISODE``, present at start).
* Containers are drafted under semantic keys
  ``{vessel}/discharge/{k}``, ``{vessel}/export/{k}``, ``{vessel}/ts_initial/{k}``,
  ``initial_import/{k}``. Their attributes (size, load state, weight,
  landside timing) are drawn from streams keyed by those semantic keys, so
  attribute families are independent of each other and of ID numbering.
* Container IDs ``CNT-nnnnnn`` are assigned in category order (discharge
  cargo by vessel, exports by vessel, pre-episode transshipment by vessel,
  initial import filler last). Changing the initial-occupancy target therefore
  never relabels vessel cargo.
* Initial inventory (pre-episode exports and transshipment, then import filler
  up to the occupancy target) is placed in blocks at block level only (G0
  ``BLOCK_ONLY``) by a deterministic balancing rule; no Bay/Row/Tier is invented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from berth_allocation_lab.scenarios.synthetic import planned_berth_occupancy_minutes
from mini_port_sim.scenario import ServiceConfig

from integrated_terminal_pilot.scenarios.config import GeneratorConfig
from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints
from integrated_terminal_pilot.scenarios.models import (
    PHYSICS_PROFILE_DEGENERATE, PHYSICS_PROFILE_STANDARD, PRE_EPISODE, SCHEMA_VERSION,
    TEU_BY_SIZE, expected_entry_exit, location, scenario_id_for,
)
from integrated_terminal_pilot.scenarios.random_streams import KeyedStreams

PROJECT_ID = "project_i_integrated_terminal_pilot"


class ScenarioGenerationError(RuntimeError):
    """A requested scenario cannot be generated without violating a contract.

    Carries a stable validation code; the generator never repairs data to avoid it.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GenerationResult:
    scenario: dict[str, Any]
    diagnostics: dict[str, Any]


def generate_scenario(config: GeneratorConfig, family: str, split: str, scenario_seed: int,
                      physics_profile: str = PHYSICS_PROFILE_STANDARD) -> dict[str, Any]:
    return generate_scenario_with_diagnostics(config, family, split, scenario_seed,
                                              physics_profile).scenario


def generate_scenario_with_diagnostics(config: GeneratorConfig, family: str, split: str,
                                       scenario_seed: int,
                                       physics_profile: str = PHYSICS_PROFILE_STANDARD,
                                       ) -> GenerationResult:
    _check_request(config, family, split, scenario_seed, physics_profile)
    fam = config.family(family)
    params = config.parameters
    streams = KeyedStreams(family, split, scenario_seed, params["stream_namespace"])
    physics = build_physics(config, physics_profile)
    terminal = fam["terminal"]
    quay = {"berth_length_m": float(terminal["berth_length_m"]),
            "min_clearance_m": float(terminal["min_clearance_m"]), "quay_line_y_m": 0.0}
    blocks = build_yard_blocks(fam, params["yard_layout"], quay["berth_length_m"])
    gates = [build_gate(fam, params["yard_layout"], quay["berth_length_m"])]

    vessels = _draw_vessels(streams, fam["traffic"], params["cargo"])
    plan = _plan_transshipment(vessels, params["cargo"])
    drafts = _draft_vessel_cargo(streams, vessels, plan, params, physics)
    scenario_id = scenario_id_for(family, split, scenario_seed, physics_profile)

    containers: list[dict[str, Any]] = []
    for index, draft in enumerate(drafts, start=1):
        containers.append(_container_record(f"CNT-{index:06d}", draft, scenario_id))
    placements, inventory = _place_initial_inventory(streams, containers, blocks, fam, params,
                                                     scenario_id)
    groups = _build_groups(containers)

    max_cranes = (int(terminal["max_cranes_per_vessel"]) if physics_profile == PHYSICS_PROFILE_STANDARD
                  else int(config.physics_profile(PHYSICS_PROFILE_DEGENERATE)["max_cranes_per_vessel"]))
    service = ServiceConfig(
        berthing_preparation_minutes=physics["service"]["berthing_preparation_minutes"],
        service_minutes_per_move=physics["service"]["service_minutes_per_move"],
        departure_preparation_minutes=physics["service"]["departure_preparation_minutes"],
        two_crane_efficiency=physics["crane"]["efficiency"]["two"],
        three_crane_efficiency=physics["crane"]["efficiency"]["three"],
        four_plus_crane_efficiency=physics["crane"]["efficiency"]["four_plus"],
    )
    vessel_records = [_vessel_record(v, containers, max_cranes, service) for v in vessels]
    cranes = build_cranes(config, fam, physics_profile, vessels, quay)

    locations = []
    for record in containers:
        cid = record["container_id"]
        if record["present_at_episode_start"]:
            loc = location("YARD_BLOCK", placements[cid], slot_resolution="BLOCK_ONLY")
            status = "IN_YARD"
        elif record["cargo_flow"] == "export":
            loc, status = location("EXTERNAL_LANDSIDE", None), "EXPECTED_BY_LANDSIDE"
        else:
            loc, status = location("VESSEL", record["origin_vessel_id"]), "EXPECTED_BY_VESSEL"
        locations.append({"container_id": cid, "status": status, "location": loc})

    doc = {
        "schema_version": SCHEMA_VERSION,
        "identity": {
            "scenario_id": scenario_id,
            "project_id": PROJECT_ID,
            "scenario_family": family,
            "split": split,
            "scenario_seed": scenario_seed,
            "generator_version": params["generator_version"],
            "data_provenance": "synthetic",
            "yard_fidelity": "G0",
            "physics_profile": physics_profile,
        },
        "terminal": {"quay": quay, "gates": gates, "yard_blocks": blocks},
        "resources": {"quay_cranes": cranes},
        "vessels": vessel_records,
        "container_groups": groups,
        "containers": containers,
        "initial_state": {
            "time_min": 0.0,
            "container_locations": locations,
            "block_status": {b["block_id"]: "open" for b in blocks},
        },
        "physics": physics,
    }
    doc = with_fingerprints(doc, generator_config_fingerprint=config.parameters_fingerprint)
    diagnostics = {
        "transshipment": plan["summary"],
        "initial_inventory": inventory,
        "crane_count": len(cranes),
    }
    return GenerationResult(doc, diagnostics)


def _check_request(config: GeneratorConfig, family: str, split: str, seed: int,
                   profile: str) -> None:
    config.family(family)
    blocked = config.blocked_decisions_for_family(family)
    if blocked:
        raise ScenarioGenerationError(
            "UNSUPPORTED_ASSUMPTION",
            f"Family {family} depends on BLOCKED decision(s) "
            f"{[d['decision_id'] for d in blocked]}; it cannot be generated until resolved.")
    allowed = config.parameters["generation_policy"]["allowed_splits"]
    if split not in allowed:
        raise ScenarioGenerationError(
            "SEED_NAMESPACE_VIOLATION",
            f"Split {split!r} may not be generated (allowed: {allowed}).")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ScenarioGenerationError("SEED_NAMESPACE_VIOLATION", "Scenario seed must be an integer.")
    first, last = config.seed_band(split)
    if not first <= seed <= last:
        raise ScenarioGenerationError(
            "SEED_NAMESPACE_VIOLATION",
            f"Seed {seed} is outside the {split} band [{first}, {last}].")
    config.physics_profile(profile)


def build_physics(config: GeneratorConfig, profile: str) -> dict[str, Any]:
    physics = config.snapshot()["physics_profiles"][PHYSICS_PROFILE_STANDARD]
    if profile == PHYSICS_PROFILE_DEGENERATE:
        degenerate = config.physics_profile(PHYSICS_PROFILE_DEGENERATE)
        physics["transport"]["enabled"] = degenerate["transport_enabled"]
        physics["yard"]["constraints_enabled"] = degenerate["yard_constraints_enabled"]
    return physics


def build_yard_blocks(family: dict[str, Any], layout: dict[str, Any],
                      berth_length_m: float) -> list[dict[str, Any]]:
    yard = family["yard"]
    count = int(yard["block_count"])
    slot_length = float(layout["ground_slot_length_m"])
    block_length = yard["bay_count"] * slot_length
    total = count * block_length + (count - 1) * layout["block_gap_m"]
    if total > berth_length_m + 1e-9:
        raise ScenarioGenerationError(
            "INVALID_YARD_GEOMETRY",
            f"Yard row of {count} blocks ({total} m) exceeds quay length {berth_length_m} m.")
    start = (berth_length_m - total) / 2.0
    geometric = int(yard["bay_count"] * yard["row_count"] * yard["max_tiers"])
    blocks = []
    for index in range(count):
        origin_x = round(start + index * (block_length + layout["block_gap_m"]), 6)
        origin_y = float(layout["apron_depth_m"])
        blocks.append({
            "block_id": f"B{index + 1:02d}",
            "origin_x_m": origin_x,
            "origin_y_m": origin_y,
            "bay_axis": layout["bay_axis"],
            "bay_count": int(yard["bay_count"]),
            "row_count": int(yard["row_count"]),
            "max_tiers": int(yard["max_tiers"]),
            "ground_slot_length_m": slot_length,
            "ground_slot_width_m": float(layout["ground_slot_width_m"]),
            "geometric_slot_count": geometric,
            "geometric_capacity_teu": float(geometric),
            "capacity_teu": float(yard["capacity_teu"]),
            "operating_fill_limit": (yard["max_tiers"] - 1) / yard["max_tiers"],
            "capabilities": sorted(layout["capabilities"]),
            "allowed_sizes": sorted(layout["allowed_sizes"]),
            "handling_capacity_moves_per_hour": float(yard["handling_capacity_moves_per_hour"]),
            "transfer_point_x_m": round(origin_x + block_length / 2.0, 6),
            "transfer_point_y_m": origin_y,
        })
    return blocks


def build_gate(family: dict[str, Any], layout: dict[str, Any], berth_length_m: float) -> dict[str, Any]:
    depth = family["yard"]["row_count"] * layout["ground_slot_width_m"]
    return {"gate_id": "G01", "x_m": berth_length_m / 2.0,
            "y_m": round(layout["apron_depth_m"] + depth + layout["gate_setback_m"], 6)}


def max_coexisting_vessels(lengths: list[float], berth_length_m: float, clearance_m: float) -> int:
    """Largest k such that the k shortest vessels fit the quay together with clearances.

    No berth policy can ever have more of these vessels on the quay at once, so a
    crane fleet of this size satisfies the degenerate profile for every policy.
    """
    occupied, count = 0.0, 0
    for length in sorted(lengths):
        needed = occupied + length + (clearance_m if count else 0.0)
        if needed > berth_length_m + 1e-9:
            break
        occupied, count = needed, count + 1
    return max(count, 1)


def build_cranes(config: GeneratorConfig, family: dict[str, Any], profile: str,
                 vessels: list[dict[str, Any]], quay: dict[str, float]) -> list[dict[str, Any]]:
    terminal = family["terminal"]
    if profile == PHYSICS_PROFILE_STANDARD:
        count, rate = int(terminal["quay_crane_count"]), float(terminal["quay_crane_moves_per_hour"])
    else:
        degenerate = config.physics_profile(PHYSICS_PROFILE_DEGENERATE)
        count = max_coexisting_vessels([v["length_m"] for v in vessels], quay["berth_length_m"],
                                       quay["min_clearance_m"])
        rate = float(degenerate["quay_crane_moves_per_hour"])
    return [{
        "crane_id": f"QC{index + 1:02d}",
        "nominal_moves_per_hour": rate,
        "rail_id": "R1",
        "home_position_m": round((index + 0.5) * quay["berth_length_m"] / count, 6),
        "compatible_vessel_ids": None,
        "unavailability_windows": [],
    } for index in range(count)]


def _draw_vessels(streams: KeyedStreams, traffic: dict[str, Any],
                  cargo: dict[str, Any]) -> list[dict[str, Any]]:
    vessels = []
    arrival = 0.0
    for index in range(1, int(traffic["vessel_count"]) + 1):
        vessel_id = f"V{index:03d}"
        if index > 1:
            arrival += streams.rng("vessel", vessel_id, "interarrival").expovariate(
                1.0 / traffic["mean_interarrival_minutes"])
        length = round(streams.rng("vessel", vessel_id, "length").uniform(
            traffic["min_vessel_length_m"], traffic["max_vessel_length_m"]), 2)
        workload = streams.rng("vessel", vessel_id, "workload").randint(
            traffic["min_workload_moves"], traffic["max_workload_moves"])
        share = streams.rng("vessel", vessel_id, "discharge_share").uniform(
            cargo["discharge_share_min"], cargo["discharge_share_max"])
        discharge = min(workload - 1, max(1, round(workload * share)))
        vessels.append({"vessel_id": vessel_id, "arrival_time_min": arrival, "length_m": length,
                        "workload_moves": workload, "discharge": discharge,
                        "load": workload - discharge, "order": index - 1})
    return vessels


def _plan_transshipment(vessels: list[dict[str, Any]], cargo: dict[str, Any]) -> dict[str, Any]:
    capacity = {v["vessel_id"]: math.floor(v["discharge"] * cargo["max_transshipment_share_of_discharge"])
                for v in vessels}
    outbound: dict[str, list[str]] = {v["vessel_id"]: [] for v in vessels}
    initial_demand: dict[str, int] = {}
    demand_total = served_by_vessels = 0
    connection = cargo["min_transshipment_connection_min"]
    for target in vessels:
        demand = round(target["load"] * cargo["transshipment_share_of_load"])
        demand_total += demand
        for _ in range(demand):
            eligible = [u for u in vessels
                        if u["vessel_id"] != target["vessel_id"]
                        and u["arrival_time_min"] + connection <= target["arrival_time_min"]
                        and len(outbound[u["vessel_id"]]) < capacity[u["vessel_id"]]]
            if eligible:
                source = min(eligible, key=lambda u: (
                    -(capacity[u["vessel_id"]] - len(outbound[u["vessel_id"]])),
                    u["arrival_time_min"], u["vessel_id"]))
                outbound[source["vessel_id"]].append(target["vessel_id"])
                served_by_vessels += 1
            else:
                initial_demand[target["vessel_id"]] = initial_demand.get(target["vessel_id"], 0) + 1
    return {
        "outbound": outbound,
        "initial_demand": initial_demand,
        "demand": {v["vessel_id"]: round(v["load"] * cargo["transshipment_share_of_load"])
                   for v in vessels},
        "summary": {"transshipment_demand": demand_total,
                    "served_by_scenario_vessels": served_by_vessels,
                    "served_by_pre_episode_inventory": demand_total - served_by_vessels},
    }


def _draw_unit(streams: KeyedStreams, key: str, cargo: dict[str, Any]) -> dict[str, Any]:
    size = "40_ft" if streams.rng("container", key, "size").random() < cargo["forty_ft_share"] else "20_ft"
    empty = streams.rng("container", key, "load_state").random() < cargo["empty_share"]
    reefer = (not empty) and streams.rng("container", key, "reefer").random() < cargo["reefer_share"]
    hazardous = (not empty) and streams.rng("container", key, "hazardous").random() < cargo["hazardous_share"]
    if empty:
        weight = int(cargo["empty_weight_kg"][size])
    else:
        bounds = cargo["laden_weight_kg"][size]
        weight = streams.rng("container", key, "weight").randint(bounds["min"], bounds["max"])
    return {"container_size": size, "load_state": "empty" if empty else "laden",
            "is_reefer": reefer, "is_hazardous": hazardous, "gross_weight_kg": weight}


def _draft_vessel_cargo(streams: KeyedStreams, vessels: list[dict[str, Any]], plan: dict[str, Any],
                        params: dict[str, Any], physics: dict[str, Any]) -> list[dict[str, Any]]:
    cargo, landside = params["cargo"], params["landside"]
    cutoff = physics["landside"]["export_cutoff_min"]
    order = {v["vessel_id"]: v["order"] for v in vessels}
    drafts: list[dict[str, Any]] = []
    for vessel in vessels:
        vid = vessel["vessel_id"]
        destinations = sorted(plan["outbound"][vid], key=order.__getitem__)
        for k in range(vessel["discharge"]):
            key = f"{vid}/discharge/{k:04d}"
            draft = {"key": key, **_draw_unit(streams, key, cargo), "origin": vid,
                     "present": False, "gate_in": None, "pickup": None}
            if k < len(destinations):
                draft.update(flow="transshipment", destination=destinations[k])
            else:
                delay = streams.rng("container", key, "pickup_delay").uniform(
                    landside["import_dwell_min_min"], landside["import_dwell_max_min"])
                draft.update(flow="import", destination=None,
                             pickup=vessel["arrival_time_min"] + delay)
            drafts.append(draft)
    for vessel in vessels:
        vid = vessel["vessel_id"]
        exports = vessel["load"] - plan["demand"][vid]
        for k in range(exports):
            key = f"{vid}/export/{k:04d}"
            lead = streams.rng("container", key, "gate_lead").uniform(
                0.0, landside["export_gate_lead_max_min"])
            gate_in = vessel["arrival_time_min"] - cutoff - lead
            present = gate_in < 0.0
            drafts.append({"key": key, **_draw_unit(streams, key, cargo), "flow": "export",
                           "origin": None, "destination": vid, "present": present,
                           "gate_in": None if present else gate_in, "pickup": None})
    for vessel in vessels:
        vid = vessel["vessel_id"]
        for k in range(plan["initial_demand"].get(vid, 0)):
            key = f"{vid}/ts_initial/{k:04d}"
            drafts.append({"key": key, **_draw_unit(streams, key, cargo), "flow": "transshipment",
                           "origin": PRE_EPISODE, "destination": vid, "present": True,
                           "gate_in": None, "pickup": None})
    return drafts


def _container_record(container_id: str, draft: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    entry, exit_mode = expected_entry_exit(draft["flow"])
    return {
        "container_id": container_id,
        "container_group_id": "",  # assigned by _build_groups
        "container_size": draft["container_size"],
        "size_teu": TEU_BY_SIZE[draft["container_size"]],
        "load_state": draft["load_state"],
        "is_reefer": draft["is_reefer"],
        "is_hazardous": draft["is_hazardous"],
        "gross_weight_kg": draft["gross_weight_kg"],
        "cargo_flow": draft["flow"],
        "origin_vessel_id": draft["origin"],
        "destination_vessel_id": draft["destination"],
        "terminal_entry_mode": entry,
        "terminal_exit_mode": exit_mode,
        "present_at_episode_start": draft["present"],
        "scheduled_gate_in_time_min": draft["gate_in"],
        "scheduled_pickup_time_min": draft["pickup"],
        "source_scenario_id": scenario_id,
    }


def _required_capabilities(record: dict[str, Any]) -> set[str]:
    if record["load_state"] == "empty":
        return {"empty"}
    required = {"general"}
    if record["is_reefer"]:
        required.add("reefer_power")
    if record["is_hazardous"]:
        required.add("hazardous")
    return required


def _choose_block(blocks: list[dict[str, Any]], used: dict[str, float], limit: dict[str, float],
                  record: dict[str, Any]) -> str | None:
    teu = record["size_teu"]
    required = _required_capabilities(record)
    candidates = [b for b in blocks
                  if record["container_size"] in b["allowed_sizes"]
                  and required <= set(b["capabilities"])
                  and used[b["block_id"]] + teu <= limit[b["block_id"]] + 1e-9]
    if not candidates:
        return None
    best = min(candidates, key=lambda b: (-(limit[b["block_id"]] - used[b["block_id"]]),
                                          b["block_id"]))
    return best["block_id"]


def _place_initial_inventory(streams: KeyedStreams, containers: list[dict[str, Any]],
                             blocks: list[dict[str, Any]], family: dict[str, Any],
                             params: dict[str, Any], scenario_id: str,
                             ) -> tuple[dict[str, str], dict[str, Any]]:
    fraction = family["yard"]["initial_occupancy_fraction"]
    capacity = {b["block_id"]: b["capacity_teu"] for b in blocks}
    target = {bid: fraction * cap for bid, cap in capacity.items()}
    used = {bid: 0.0 for bid in capacity}
    placements: dict[str, str] = {}
    required_teu = 0.0
    for record in containers:
        if not record["present_at_episode_start"]:
            continue
        required_teu += record["size_teu"]
        block = _choose_block(blocks, used, target, record) or _choose_block(blocks, used, capacity, record)
        if block is None:
            raise ScenarioGenerationError(
                "YARD_CAPACITY_EXCEEDED",
                f"Pre-episode inventory needs {required_teu} TEU or more, exceeding available "
                f"yard capacity {sum(capacity.values())} TEU (container {record['container_id']}).")
        placements[record["container_id"]] = block
        used[block] += record["size_teu"]
    filler = 0
    landside, cargo = params["landside"], params["cargo"]
    while True:
        key = f"initial_import/{filler:05d}"
        unit = _draw_unit(streams, key, cargo)
        pickup = streams.rng("container", key, "pickup_delay").uniform(
            0.0, landside["initial_import_pickup_max_min"])
        draft = {"key": key, **unit, "flow": "import", "origin": PRE_EPISODE, "destination": None,
                 "present": True, "gate_in": None, "pickup": pickup}
        record = _container_record(f"CNT-{len(containers) + 1:06d}", draft, scenario_id)
        block = _choose_block(blocks, used, target, record)
        if block is None:
            break
        containers.append(record)
        placements[record["container_id"]] = block
        used[block] += record["size_teu"]
        filler += 1
    return placements, {
        "target_teu": sum(target.values()),
        "required_pre_episode_teu": required_teu,
        "filler_import_containers": filler,
        "initial_teu_by_block": dict(sorted(used.items())),
        "initial_teu_total": sum(used.values()),
        "capacity_teu_total": sum(capacity.values()),
        "exceeds_target": required_teu > sum(target.values()) + 1e-9,
    }


def _build_groups(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys: dict[tuple, list[dict[str, Any]]] = {}
    for record in containers:
        key = (record["container_size"], record["cargo_flow"], record["load_state"],
               record["is_reefer"], record["is_hazardous"], record["origin_vessel_id"],
               record["destination_vessel_id"])
        keys.setdefault(key, []).append(record)
    groups = []
    for index, (key, members) in enumerate(keys.items(), start=1):  # insertion = first-member order
        group_id = f"GRP-{index:04d}"
        if index > 9999:
            raise ScenarioGenerationError("INVALID_ENTITY_ID", "More than 9999 container groups.")
        for record in members:
            record["container_group_id"] = group_id
        size, flow, load_state, reefer, hazardous, origin, destination = key
        groups.append({"group_id": group_id, "container_size": size, "quantity": len(members),
                       "flow": flow, "load_state": load_state, "is_reefer": reefer,
                       "is_hazardous": hazardous, "source_vessel_id": origin,
                       "target_vessel_id": destination})
    return groups


def _vessel_record(vessel: dict[str, Any], containers: list[dict[str, Any]], max_cranes: int,
                   service: ServiceConfig) -> dict[str, Any]:
    vid = vessel["vessel_id"]
    discharge = [c for c in containers if c["origin_vessel_id"] == vid]
    load = [c for c in containers if c["destination_vessel_id"] == vid]
    if len(discharge) != vessel["discharge"] or len(load) != vessel["load"]:
        raise ScenarioGenerationError(
            "WORKLOAD_RECONCILIATION_FAILURE",
            f"{vid}: drafted cargo ({len(discharge)}+{len(load)}) differs from workload split "
            f"({vessel['discharge']}+{vessel['load']}).")
    workload = len(discharge) + len(load)
    return {
        "vessel_id": vid,
        "arrival_time_min": vessel["arrival_time_min"],
        "length_m": vessel["length_m"],
        "max_cranes": max_cranes,
        "priority": 2,
        "discharge_move_count": len(discharge),
        "load_move_count": len(load),
        "extra_work_units": 0,
        "workload_moves": workload,
        "discharge_teu": sum(c["size_teu"] for c in discharge),
        "load_teu": sum(c["size_teu"] for c in load),
        "nominal_service_time_min": planned_berth_occupancy_minutes(service=service,
                                                                    workload_moves=workload),
    }
