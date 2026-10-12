"""Hand-written Step 4 fixtures: small, exact ``itp_scenario_v1`` documents with known physics.

``build_doc`` derives every materialized field (groups, move counts, TEU, nominal
service, block geometry, transfer points, initial locations, fingerprints) from a
compact specification, so each test states only what matters for its physics.
Values are illustrative and synthetic.
"""

from __future__ import annotations

import copy
from typing import Any

from integrated_terminal_pilot.policies import FirstFitYardPolicy, GreedyBerthOrderCranePolicy
from integrated_terminal_pilot.policies.actions import YardAction
from integrated_terminal_pilot.scenarios.config import load_generator_config
from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints
from integrated_terminal_pilot.scenarios.generator import build_physics
from integrated_terminal_pilot.scenarios.models import TEU_BY_SIZE, expected_entry_exit, location
from integrated_terminal_pilot.simulator import FcfsBerthIntegrationDriver, TerminalKernel, run_episode

SCENARIO_ID = "itp_fixture_development_seed10000000"


def physics(**overrides: Any) -> dict[str, Any]:
    """Standard-profile physics with dotted-path overrides, e.g. ``{"transport.enabled": False}``."""
    doc = build_physics(load_generator_config(), "standard_v1")
    for dotted, value in overrides.items():
        section, key = dotted.split(".")
        doc[section][key] = value
    return doc


QUIET = {"transport.enabled": False, "yard.constraints_enabled": False}


def block(block_id: str, x: float, y: float = 100.0, *, capacity: float = 96.0, handling: float = 60.0,
          bays: int = 8, rows: int = 4, tiers: int = 4, sizes=("20_ft", "40_ft")) -> dict[str, Any]:
    geometric = bays * rows * tiers
    return {"block_id": block_id, "origin_x_m": float(x), "origin_y_m": float(y), "bay_axis": "X",
            "bay_count": bays, "row_count": rows, "max_tiers": tiers, "ground_slot_length_m": 6.5,
            "ground_slot_width_m": 2.8, "geometric_slot_count": geometric,
            "geometric_capacity_teu": float(geometric), "capacity_teu": float(capacity),
            "operating_fill_limit": (tiers - 1) / tiers, "capabilities": ["general"],
            "allowed_sizes": sorted(sizes), "handling_capacity_moves_per_hour": float(handling),
            "transfer_point_x_m": round(x + bays * 6.5 / 2.0, 6), "transfer_point_y_m": float(y)}


def crane(crane_id: str, rate: float = 30.0) -> dict[str, Any]:
    return {"crane_id": crane_id, "nominal_moves_per_hour": float(rate), "rail_id": "R1",
            "home_position_m": 100.0, "compatible_vessel_ids": None, "unavailability_windows": []}


def vessel(vessel_id: str, arrival: float, length: float, max_cranes: int = 1) -> dict[str, Any]:
    return {"vessel_id": vessel_id, "arrival_time_min": float(arrival), "length_m": float(length),
            "max_cranes": max_cranes}


def container(number: int, flow: str, *, size: str = "20_ft", origin: str | None = None,
              dest: str | None = None, block: str | None = None, gate_in: float | None = None,
              pickup: float | None = None) -> dict[str, Any]:
    return {"number": number, "flow": flow, "size": size, "origin": origin, "dest": dest, "block": block,
            "gate_in": gate_in, "pickup": pickup}


def cid(number: int) -> str:
    return f"CNT-{number:06d}"


def build_doc(*, vessels: list[dict], containers: list[dict], blocks: list[dict] | None = None,
              cranes: list[dict] | None = None, quay: float = 1200.0, clearance: float = 20.0,
              physics_doc: dict | None = None) -> dict[str, Any]:
    blocks = blocks or [block("B01", 100.0)]
    cranes = cranes or [crane("QC01")]
    records, groups, group_of = [], [], {}
    for spec in sorted(containers, key=lambda s: s["number"]):
        flow = spec["flow"]
        present = spec["block"] is not None
        origin = spec["origin"]
        if present and flow in ("import", "transshipment") and origin is None:
            origin = "PRE_EPISODE"
        key = (spec["size"], flow, origin, spec["dest"])
        if key not in group_of:
            group_of[key] = f"GRP-{len(group_of) + 1:04d}"
            groups.append({"group_id": group_of[key], "container_size": spec["size"], "quantity": 0,
                           "flow": flow, "load_state": "laden", "is_reefer": False, "is_hazardous": False,
                           "source_vessel_id": origin, "target_vessel_id": spec["dest"]})
        group = next(g for g in groups if g["group_id"] == group_of[key])
        group["quantity"] += 1
        entry, exit_mode = expected_entry_exit(flow)
        records.append({
            "container_id": cid(spec["number"]), "container_group_id": group_of[key],
            "container_size": spec["size"], "size_teu": TEU_BY_SIZE[spec["size"]], "load_state": "laden",
            "is_reefer": False, "is_hazardous": False, "gross_weight_kg": 15000, "cargo_flow": flow,
            "origin_vessel_id": origin, "destination_vessel_id": spec["dest"], "terminal_entry_mode": entry,
            "terminal_exit_mode": exit_mode, "present_at_episode_start": present,
            "scheduled_gate_in_time_min": spec["gate_in"], "scheduled_pickup_time_min": spec["pickup"],
            "source_scenario_id": SCENARIO_ID})
    locations = []
    for spec, record in zip(sorted(containers, key=lambda s: s["number"]), records):
        if spec["block"] is not None:
            loc, status = location("YARD_BLOCK", spec["block"], slot_resolution="BLOCK_ONLY"), "IN_YARD"
        elif spec["flow"] == "export":
            loc, status = location("EXTERNAL_LANDSIDE", None), "EXPECTED_BY_LANDSIDE"
        else:
            loc, status = location("VESSEL", record["origin_vessel_id"]), "EXPECTED_BY_VESSEL"
        locations.append({"container_id": record["container_id"], "status": status, "location": loc})
    vessel_records = []
    for v in vessels:
        vid = v["vessel_id"]
        discharge = [r for r in records if r["origin_vessel_id"] == vid]
        load = [r for r in records if r["destination_vessel_id"] == vid]
        workload = len(discharge) + len(load)
        vessel_records.append({
            **v, "priority": 2, "discharge_move_count": len(discharge), "load_move_count": len(load),
            "extra_work_units": 0, "workload_moves": workload,
            "discharge_teu": float(sum(r["size_teu"] for r in discharge)),
            "load_teu": float(sum(r["size_teu"] for r in load)),
            "nominal_service_time_min": 30.0 + 0.5 * workload + 20.0})
    doc = {
        "schema_version": "itp_scenario_v1",
        "identity": {"scenario_id": SCENARIO_ID, "project_id": "project_i_integrated_terminal_pilot",
                     "scenario_family": "itp_fixture", "split": "development", "scenario_seed": 10_000_000,
                     "generator_version": "hand_written_fixture", "data_provenance": "synthetic",
                     "yard_fidelity": "G0", "physics_profile": "standard_v1"},
        "terminal": {"quay": {"berth_length_m": float(quay), "min_clearance_m": float(clearance),
                              "quay_line_y_m": 0.0},
                     "gates": [{"gate_id": "G01", "x_m": float(quay) / 2.0, "y_m": 400.0}],
                     "yard_blocks": copy.deepcopy(blocks)},
        "resources": {"quay_cranes": copy.deepcopy(cranes)},
        "vessels": vessel_records,
        "container_groups": groups,
        "containers": records,
        "initial_state": {"time_min": 0.0, "container_locations": locations,
                          "block_status": {b["block_id"]: "open" for b in blocks}},
        "physics": physics_doc if physics_doc is not None else physics(**QUIET),
    }
    return with_fingerprints(doc, generator_config_fingerprint=None)


def kernel_for(doc: dict, *, validate: bool = True, invariant_mode: str = "full") -> TerminalKernel:
    return TerminalKernel.from_scenario(doc, validate=validate, invariant_mode=invariant_mode)


def policies(yard=None) -> dict[str, Any]:
    return {"berth_policy": FcfsBerthIntegrationDriver(), "crane_policy": GreedyBerthOrderCranePolicy(),
            "yard_policy": yard or FirstFitYardPolicy()}


def run(kernel: TerminalKernel, *, yard=None, until_min: float | None = None):
    return run_episode(kernel, **policies(yard), until_min=until_min)


class ScriptedYardPolicy:
    """Test-only yard policy: a fixed block per work order (fallback: first fit)."""

    policy_id = "test_scripted_yard"
    version = 1

    def __init__(self, blocks_by_work_order: dict[str, str]) -> None:
        self.blocks = blocks_by_work_order
        self.fallback = FirstFitYardPolicy()

    def decide(self, observation) -> YardAction:
        request = observation.request
        block_id = self.blocks.get(request.work_order_id)
        if block_id is None:
            return self.fallback.decide(observation)
        return YardAction(policy_id=self.policy_id, time_min=observation.time_min,
                          work_order_id=request.work_order_id, action_type="ALLOCATE_BLOCK",
                          container_ids=request.container_ids, required_teu=request.required_teu,
                          block_id=block_id, decision_id=observation.decision_id)


def ledger_rows(kernel: TerminalKernel, container_id: str | None = None) -> list[tuple]:
    rows = []
    for record in kernel.state.ledger:
        if container_id is None or record[4] == container_id:
            rows.append((record[1], record[2], record[6], record[7], record[9][0], record[9][1], record[14]))
    return rows


def container_state(kernel: TerminalKernel, container_id: str) -> tuple:
    i = kernel.catalog.container_index[container_id]
    s = kernel.state
    return s.c_status[i], s.c_loc_kind[i], s.c_loc_id[i]


def vessel_times(kernel: TerminalKernel, vessel_id: str) -> dict[str, Any]:
    v = kernel.state.vessels[vessel_id]
    return {"phase": v.phase, "berth": v.berth_start_time_min, "position": v.berth_position_m,
            "handling_start": v.handling_start_time_min, "handling_end": v.handling_end_time_min,
            "departure": v.departure_time_min}
