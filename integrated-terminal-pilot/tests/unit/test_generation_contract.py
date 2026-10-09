"""Determinism, identities, splits, cargo reconciliation and landside timing (tests 1-2, 5-18, 23, 30, 32, 39-40)."""

from __future__ import annotations

import collections

import pytest

from integrated_terminal_pilot.scenarios.generator import (
    ScenarioGenerationError, generate_scenario, max_coexisting_vessels,
)
from integrated_terminal_pilot.scenarios.models import ID_PATTERNS, PRE_EPISODE, TEU_BY_SIZE
from integrated_terminal_pilot.scenarios.serialization import scenario_bytes
from integrated_terminal_pilot.scenarios.validation import validate_scenario
from tests.conftest import DEV, SEED, mutated_config


def test_same_seed_and_config_is_byte_identical(config, low_doc):
    again = generate_scenario(config, "itp_low", DEV, SEED)
    assert scenario_bytes(again) == scenario_bytes(low_doc)


def test_different_seeds_give_distinct_valid_scenarios(config, low_doc):
    other = generate_scenario(config, "itp_low", DEV, SEED + 1)
    assert validate_scenario(other, generator_config=config).ok
    for key in ("physical_fingerprint", "container_manifest_fingerprint",
                "exogenous_schedule_fingerprint", "berth_projection_fingerprint"):
        assert other["fingerprints"][key] != low_doc["fingerprints"][key]


def test_generated_scenario_passes_all_scenario_stage_checks(config, low_doc):
    report = validate_scenario(low_doc, generator_config=config)
    assert report.ok, report.to_dict()


def test_identifiers_are_stable_unique_and_well_formed(low_doc):
    ids = {
        "container": [c["container_id"] for c in low_doc["containers"]],
        "vessel": [v["vessel_id"] for v in low_doc["vessels"]],
        "crane": [c["crane_id"] for c in low_doc["resources"]["quay_cranes"]],
        "block": [b["block_id"] for b in low_doc["terminal"]["yard_blocks"]],
        "group": [g["group_id"] for g in low_doc["container_groups"]],
    }
    for kind, values in ids.items():
        assert len(values) == len(set(values)), kind
        assert all(ID_PATTERNS[kind].match(v) for v in values), kind
    assert ids["container"] == [f"CNT-{i:06d}" for i in range(1, len(ids["container"]) + 1)]
    assert ids["vessel"] == [f"V{i:03d}" for i in range(1, len(ids["vessel"]) + 1)]
    arrivals = [v["arrival_time_min"] for v in low_doc["vessels"]]
    assert arrivals == sorted(arrivals) and arrivals[0] == 0.0
    assert low_doc["identity"]["scenario_id"] == "itp_low_development_seed10000000"


def test_teu_conversion_and_count_vs_teu(low_doc):
    containers = low_doc["containers"]
    assert all(c["size_teu"] == TEU_BY_SIZE[c["container_size"]] for c in containers)
    sizes = collections.Counter(c["container_size"] for c in containers)
    assert sizes["20_ft"] > 0 and sizes["40_ft"] > 0
    teu = sum(c["size_teu"] for c in containers)
    assert teu == sizes["20_ft"] + 2 * sizes["40_ft"]
    assert teu != len(containers)  # container count and TEU are different quantities


def test_workload_group_and_vessel_reconciliation(low_doc):
    containers = {c["container_id"]: c for c in low_doc["containers"]}
    members = collections.defaultdict(list)
    for c in containers.values():
        members[c["container_group_id"]].append(c)
    for group in low_doc["container_groups"]:
        assert group["quantity"] == len(members[group["group_id"]])
        assert sum(c["size_teu"] for c in members[group["group_id"]]) == \
            group["quantity"] * TEU_BY_SIZE[group["container_size"]]
    total_moves = 0
    for vessel in low_doc["vessels"]:
        discharge = [c for c in containers.values() if c["origin_vessel_id"] == vessel["vessel_id"]]
        load = [c for c in containers.values() if c["destination_vessel_id"] == vessel["vessel_id"]]
        assert vessel["workload_moves"] == len(discharge) + len(load) == \
            vessel["discharge_move_count"] + vessel["load_move_count"]
        assert vessel["discharge_teu"] == sum(c["size_teu"] for c in discharge)
        assert vessel["load_teu"] == sum(c["size_teu"] for c in load)
        total_moves += vessel["workload_moves"]
    linked = sum((c["origin_vessel_id"] not in (None, PRE_EPISODE)) +
                 (c["destination_vessel_id"] is not None) for c in containers.values())
    assert total_moves == linked  # a transshipment container counts at both of its vessels


def test_flow_relationships_and_nullability(low_doc):
    vessels = {v["vessel_id"]: v for v in low_doc["vessels"]}
    flows = collections.Counter(c["cargo_flow"] for c in low_doc["containers"])
    assert set(flows) == {"import", "export", "transshipment"}
    for c in low_doc["containers"]:
        if c["cargo_flow"] == "import":
            assert c["origin_vessel_id"] is not None and c["destination_vessel_id"] is None
            assert (c["terminal_entry_mode"], c["terminal_exit_mode"]) == ("VESSEL", "LANDSIDE")
        elif c["cargo_flow"] == "export":
            assert c["origin_vessel_id"] is None and c["destination_vessel_id"] in vessels
            assert (c["terminal_entry_mode"], c["terminal_exit_mode"]) == ("LANDSIDE", "VESSEL")
        else:
            assert c["origin_vessel_id"] != c["destination_vessel_id"]
            assert c["destination_vessel_id"] in vessels
        if c["origin_vessel_id"] == PRE_EPISODE:
            assert c["present_at_episode_start"]
        if c["cargo_flow"] == "transshipment" and c["origin_vessel_id"] in vessels:
            origin, dest = vessels[c["origin_vessel_id"]], vessels[c["destination_vessel_id"]]
            assert dest["arrival_time_min"] >= origin["arrival_time_min"] + 720.0


def test_initial_inventory_is_backed_by_containers(low_doc, low_result):
    blocks = {b["block_id"]: b for b in low_doc["terminal"]["yard_blocks"]}
    sizes = {c["container_id"]: c["size_teu"] for c in low_doc["containers"]}
    occupied = collections.Counter()
    for entry in low_doc["initial_state"]["container_locations"]:
        loc = entry["location"]
        if entry["status"] == "IN_YARD":
            assert loc["slot_resolution"] == "BLOCK_ONLY" and loc["bay"] is None
            occupied[loc["location_id"]] += sizes[entry["container_id"]]
    for block_id, teu in occupied.items():
        assert teu <= blocks[block_id]["capacity_teu"]
    assert dict(occupied) == low_result.diagnostics["initial_inventory"]["initial_teu_by_block"]


def test_landside_requests_are_causal(low_doc):
    vessels = {v["vessel_id"]: v for v in low_doc["vessels"]}
    cutoff = low_doc["physics"]["landside"]["export_cutoff_min"]
    for c in low_doc["containers"]:
        if c["scheduled_gate_in_time_min"] is not None:
            assert 0 <= c["scheduled_gate_in_time_min"] <= vessels[c["destination_vessel_id"]]["arrival_time_min"] - cutoff
        if c["cargo_flow"] == "export" and not c["present_at_episode_start"]:
            assert c["scheduled_gate_in_time_min"] is not None
        if c["cargo_flow"] == "import":
            floor = 0.0 if c["present_at_episode_start"] else vessels[c["origin_vessel_id"]]["arrival_time_min"]
            assert c["scheduled_pickup_time_min"] >= floor
        else:
            assert c["scheduled_pickup_time_min"] is None


def test_exogenous_event_identities_are_stable(config, low_doc):
    def events(doc):
        out = [("VESSEL_ARRIVAL", v["vessel_id"], v["arrival_time_min"]) for v in doc["vessels"]]
        out += [("GATE_IN_ARRIVAL", c["container_id"], c["scheduled_gate_in_time_min"])
                for c in doc["containers"] if c["scheduled_gate_in_time_min"] is not None]
        out += [("PICKUP_DUE", c["container_id"], c["scheduled_pickup_time_min"])
                for c in doc["containers"] if c["scheduled_pickup_time_min"] is not None]
        return out
    first = events(low_doc)
    assert len({(kind, entity) for kind, entity, _ in first}) == len(first)
    assert events(generate_scenario(config, "itp_low", DEV, SEED)) == first


def test_no_runtime_outcomes_in_scenario(low_doc):
    text = scenario_bytes(low_doc).decode()
    for forbidden in ("berth_position_m", "berth_start_time_min", "assigned_vessel_id",
                      "departure_time_min", "waiting", "throughput", "actual_release_time_min",
                      "terminal_entry_time_min", "realized"):
        assert f'"{forbidden}"' not in text
    statuses = {e["status"] for e in low_doc["initial_state"]["container_locations"]}
    assert statuses <= {"EXPECTED_BY_VESSEL", "EXPECTED_BY_LANDSIDE", "IN_YARD"}


def test_split_labels_and_namespace_protection(config, low_doc):
    assert low_doc["identity"]["split"] == "development"
    for split, seed in (("validation", 11_000_000), ("test", 12_000_000), ("diagnostic", 13_000_000)):
        with pytest.raises(ScenarioGenerationError) as error:
            generate_scenario(config, "itp_low", split, seed)
        assert error.value.code == "SEED_NAMESPACE_VIOLATION"
    for seed in (9_999_999, 11_000_000, 6_000_000):
        with pytest.raises(ScenarioGenerationError) as error:
            generate_scenario(config, "itp_low", DEV, seed)
        assert error.value.code == "SEED_NAMESPACE_VIOLATION"


def test_blocked_decision_refuses_generation(config):
    """A BLOCKED family-scoped decision refuses only that family; a global one refuses all."""
    blocked = mutated_config({}, statuses={"S2-033": "BLOCKED"})
    with pytest.raises(ScenarioGenerationError) as error:
        generate_scenario(blocked, "itp_yard_bottleneck", DEV, SEED)
    assert error.value.code == "UNSUPPORTED_ASSUMPTION" and "S2-033" in error.value.message
    assert [d["decision_id"] for d in blocked.blocked_decisions_for_family("itp_low")] == []
    global_block = mutated_config({}, statuses={"S2-060": "BLOCKED"})
    for family in global_block.family_names:
        with pytest.raises(ScenarioGenerationError, match="S2-060"):
            generate_scenario(global_block, family, DEV, SEED)


def test_max_coexisting_vessels_bound():
    assert max_coexisting_vessels([200.0] * 10, 1200.0, 20.0) == 5  # 5*200 + 4*20 = 1080
    assert max_coexisting_vessels([360.0, 300.0, 250.0, 200.0], 1200.0, 20.0) == 4  # 1110 + 60
    assert max_coexisting_vessels([360.0, 360.0, 360.0, 360.0], 1200.0, 20.0) == 3
