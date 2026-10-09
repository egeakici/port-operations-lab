"""Step 2 stabilization: pre-staging, mandatory/optional inventory, multi-line yard, fingerprints.

Numbers in comments refer to the stabilization brief's required configuration tests (section 20).
"""

from __future__ import annotations

import collections
import json

import pytest

from integrated_terminal_pilot.scenarios.generator import (
    ScenarioGenerationError, export_prestaging, generate_scenario,
    generate_scenario_with_diagnostics,
)
from integrated_terminal_pilot.scenarios.models import PRE_EPISODE
from integrated_terminal_pilot.scenarios.outputs import generate_run, plan_run
from integrated_terminal_pilot.scenarios.validation import validate_scenario
from tests.conftest import DEV, SEED, mutated_config

CUTOFF = 360.0
REFERENCE_BLOCKS = [  # (block_id, origin_x_m, origin_y_m): 3 lines of 4 blocks, 40 m roads
    ("B01", 20.0, 100.0), ("B02", 320.0, 100.0), ("B03", 620.0, 100.0), ("B04", 920.0, 100.0),
    ("B05", 20.0, 179.2), ("B06", 320.0, 179.2), ("B07", 620.0, 179.2), ("B08", 920.0, 179.2),
    ("B09", 20.0, 258.4), ("B10", 320.0, 258.4), ("B11", 620.0, 258.4), ("B12", 920.0, 258.4),
]


def _vessel_cargo(doc):
    """Every container except optional background imports (PRE_EPISODE imports)."""
    return [c for c in doc["containers"]
            if not (c["origin_vessel_id"] == PRE_EPISODE and c["cargo_flow"] == "import")]


def _inventory(doc):
    present = [c for c in doc["containers"] if c["present_at_episode_start"]]
    mandatory = [c for c in present if c["cargo_flow"] != "import"]
    optional = [c for c in present if c["cargo_flow"] == "import"]
    return mandatory, optional


# --- 4-6: export pre-staging rule --------------------------------------------------------

@pytest.mark.parametrize("arrival, lead, expected", [
    (0.0, 0.0, (True, None)),            # vessel at t = 0: no admissible gate-in exists
    (300.0, 0.0, (True, None)),          # arrival before the cutoff: always pre-staged
    (CUTOFF, 0.0, (False, 0.0)),         # arrival exactly at the cutoff, zero lead: gate-in at t = 0
    (CUTOFF, 0.5, (True, None)),         # same arrival, any positive lead: entered before the episode
    (1000.0, 640.0, (False, 0.0)),       # request exactly at the minimum allowed gate-in time 0
    (1000.0, 640.001, (True, None)),     # just before t = 0
    (5000.0, 1000.0, (False, 3640.0)),  # late export: valid in-episode gate-in
    (5000.0, 0.0, (False, 4640.0)),      # zero lead: request equals the latest admissible time
])
def test_export_prestaging_boundaries(arrival, lead, expected):
    present, gate_in = export_prestaging(arrival, CUTOFF, lead)
    assert (present, gate_in) == (expected[0], pytest.approx(expected[1]) if expected[1] is not None else None)
    if not present:
        assert 0.0 <= gate_in <= arrival - CUTOFF  # DQ11, never after the cutoff


def test_generated_exports_follow_the_causal_rule(low_doc, heavy_doc):
    for doc in (low_doc, heavy_doc):
        vessels = {v["vessel_id"]: v["arrival_time_min"] for v in doc["vessels"]}
        cutoff = doc["physics"]["landside"]["export_cutoff_min"]
        exports = [c for c in doc["containers"] if c["cargo_flow"] == "export"]
        early = [c for c in exports if vessels[c["destination_vessel_id"]] < cutoff]
        assert early and all(c["present_at_episode_start"] for c in early)
        for c in exports:
            if c["present_at_episode_start"]:
                assert c["scheduled_gate_in_time_min"] is None
            else:
                assert 0.0 <= c["scheduled_gate_in_time_min"] <= vessels[c["destination_vessel_id"]] - cutoff
        prestaged_sizes = {c["container_size"] for c in exports if c["present_at_episode_start"]}
        assert prestaged_sizes == {"20_ft", "40_ft"}  # mixed-size pre-staged export cargo
        assert any(not c["present_at_episode_start"] for c in exports)  # in-episode gate-ins exist


# --- 1-3, 8-9, 15, 23: mandatory and optional inventory ---------------------------------

def test_mandatory_inventory_is_a_lower_bound_and_backed_by_containers(low_result):
    doc, inv = low_result.scenario, low_result.diagnostics["initial_inventory"]
    mandatory, optional = _inventory(doc)
    assert inv["mandatory_initial_teu"] == sum(c["size_teu"] for c in mandatory) > 0
    assert inv["mandatory_initial_containers"] == len(mandatory)
    assert inv["optional_initial_teu"] == sum(c["size_teu"] for c in optional)
    assert inv["optional_initial_containers"] == len(optional)
    assert inv["initial_teu_total"] >= inv["mandatory_initial_teu"]
    assert {c["cargo_flow"] for c in mandatory} == {"export", "transshipment"}
    assert all(c["origin_vessel_id"] == PRE_EPISODE for c in optional)
    by_flow = collections.Counter()
    for c in mandatory:
        by_flow[c["cargo_flow"]] += c["size_teu"]
    assert inv["mandatory_initial_teu_by_flow"] == dict(by_flow)
    # Every occupied TEU is an individual container located in a block.
    occupied = collections.Counter()
    sizes = {c["container_id"]: c["size_teu"] for c in doc["containers"]}
    for entry in doc["initial_state"]["container_locations"]:
        if entry["status"] == "IN_YARD":
            occupied[entry["location"]["location_id"]] += sizes[entry["container_id"]]
    assert dict(occupied) == {k: v for k, v in inv["initial_teu_by_block"].items() if v}
    assert sum(occupied.values()) == inv["initial_teu_total"]


def test_optional_inventory_respects_target_and_capacity(low_result, bottleneck_result):
    for result in (low_result, bottleneck_result):
        doc, inv = result.scenario, result.diagnostics["initial_inventory"]
        assert inv["target_status"] == "MET"
        assert inv["initial_teu_total"] <= inv["target_teu"] + 1e-9
        assert inv["target_teu"] - inv["initial_teu_total"] < 2.0 * len(doc["terminal"]["yard_blocks"])
        blocks = {b["block_id"]: b for b in doc["terminal"]["yard_blocks"]}
        for block_id, teu in inv["initial_teu_by_block"].items():
            assert teu <= blocks[block_id]["capacity_teu"]


def test_target_infeasibility_is_reported_never_repaired(low_doc):
    low_target = mutated_config({"families.itp_low.yard.initial_occupancy_fraction": 0.02})
    result = generate_scenario_with_diagnostics(low_target, "itp_low", DEV, SEED)
    inv = result.diagnostics["initial_inventory"]
    assert inv["target_status"] == "MANDATORY_EXCEEDS_TARGET" and inv["exceeds_target"]
    assert inv["optional_initial_teu"] == 0 and inv["optional_initial_containers"] == 0
    assert inv["initial_teu_total"] == inv["mandatory_initial_teu"] > inv["target_teu"]
    # No mandatory or vessel container was removed, relabelled or resampled.
    assert result.scenario["containers"] == _vessel_cargo(low_doc)
    assert validate_scenario(result.scenario, generator_config=low_target).ok


def test_flow_teu_totals_reconcile(heavy_doc):
    vessels = {v["vessel_id"] for v in heavy_doc["vessels"]}
    containers = heavy_doc["containers"]
    discharge = sum(c["size_teu"] for c in containers if c["origin_vessel_id"] in vessels)
    load = sum(c["size_teu"] for c in containers if c["destination_vessel_id"] in vessels)
    assert discharge == sum(v["discharge_teu"] for v in heavy_doc["vessels"])
    assert load == sum(v["load_teu"] for v in heavy_doc["vessels"])
    teu = collections.Counter()
    for c in containers:
        teu[c["cargo_flow"]] += c["size_teu"]
    vessel_ts = sum(c["size_teu"] for c in containers
                    if c["cargo_flow"] == "transshipment" and c["origin_vessel_id"] in vessels)
    background = sum(c["size_teu"] for c in containers if c["origin_vessel_id"] == PRE_EPISODE
                     and c["cargo_flow"] == "import")
    # Load TEU = exports + all transshipment; discharge TEU = vessel imports + vessel transshipment.
    assert load == teu["export"] + teu["transshipment"]
    assert discharge == teu["import"] - background + vessel_ts
    assert sum(teu.values()) == sum(c["size_teu"] for c in containers)


def test_no_container_is_both_initial_and_future_cargo(heavy_doc):
    locations = heavy_doc["initial_state"]["container_locations"]
    assert len(locations) == len({e["container_id"] for e in locations}) == len(heavy_doc["containers"])
    for c in heavy_doc["containers"]:
        if c["present_at_episode_start"]:
            assert c["scheduled_gate_in_time_min"] is None
            assert c["origin_vessel_id"] in (None, PRE_EPISODE)  # never also discharged in-episode
    status = {e["container_id"]: e["status"] for e in locations}
    assert {status[c["container_id"]] for c in heavy_doc["containers"]
            if c["present_at_episode_start"]} == {"IN_YARD"}
    assert "IN_YARD" not in {status[c["container_id"]] for c in heavy_doc["containers"]
                             if not c["present_at_episode_start"]}


def test_no_silent_container_dropping(config, heavy_doc):
    """Vessel cargo is identical with and without the yard change; every move is a container."""
    small_yard = mutated_config({"families.itp_heavy.yard.block_count": 8,
                                 "families.itp_heavy.yard.block_line_count": 2})
    other = generate_scenario(small_yard, "itp_heavy", DEV, SEED)
    assert _vessel_cargo(other) == _vessel_cargo(heavy_doc)
    for doc in (heavy_doc, other):
        linked = sum((c["origin_vessel_id"] not in (None, PRE_EPISODE))
                     + (c["destination_vessel_id"] is not None) for c in doc["containers"])
        assert linked == sum(v["workload_moves"] for v in doc["vessels"])


# --- 10-16: yard geometry and placement -------------------------------------------------

def test_block_size_eligibility_is_enforced():
    """Aggregate TEU would suffice, but no block accepts 40 ft boxes: explicit rejection."""
    only_20 = mutated_config({"yard_layout.allowed_sizes": ["20_ft"]})
    with pytest.raises(ScenarioGenerationError) as error:
        generate_scenario(only_20, "itp_low", DEV, SEED)
    assert error.value.code == "YARD_CAPACITY_EXCEEDED" and "40_ft" in error.value.message


def test_reference_layout_coordinates_capacity_and_gate(low_doc, bottleneck_result):
    for doc in (low_doc, bottleneck_result.scenario):
        blocks = doc["terminal"]["yard_blocks"]
        assert [(b["block_id"], b["origin_x_m"], b["origin_y_m"]) for b in blocks] == REFERENCE_BLOCKS
        footprints = []
        for b in blocks:
            length = b["bay_count"] * b["ground_slot_length_m"]
            depth = b["row_count"] * b["ground_slot_width_m"]
            assert b["geometric_slot_count"] == b["bay_count"] * b["row_count"] * b["max_tiers"] == 2800
            assert b["capacity_teu"] == 2200.0 <= b["geometric_slot_count"] * b["operating_fill_limit"]
            assert (b["transfer_point_x_m"], b["transfer_point_y_m"]) == (b["origin_x_m"] + length / 2,
                                                                          b["origin_y_m"])
            assert 0.0 <= b["origin_x_m"] and b["origin_x_m"] + length <= 1200.0
            footprints.append((b["origin_x_m"], b["origin_x_m"] + length, b["origin_y_m"],
                               b["origin_y_m"] + depth))
        for i, a in enumerate(footprints):
            for c in footprints[i + 1:]:
                assert not (a[0] < c[1] and c[0] < a[1] and a[2] < c[3] and c[2] < a[3])
        assert doc["terminal"]["gates"] == [{"gate_id": "G01", "x_m": 600.0, "y_m": 397.6}]
        assert doc["terminal"]["gates"][0]["y_m"] > max(f[3] for f in footprints)
        assert sum(b["capacity_teu"] for b in blocks) == 26400.0


def test_overlapping_block_lines_are_rejected(golden):
    from tests.conftest import refingerprint
    block = golden["terminal"]["yard_blocks"][1]
    first = golden["terminal"]["yard_blocks"][0]
    block.update(origin_x_m=first["origin_x_m"], origin_y_m=first["origin_y_m"] + 10.0,
                 transfer_point_x_m=first["transfer_point_x_m"], transfer_point_y_m=first["origin_y_m"] + 10.0)
    report = validate_scenario(refingerprint(golden))
    assert "INVALID_YARD_GEOMETRY" in report.codes
    assert any("overlap" in issue.message for issue in report.issues)


def test_g0_inventory_has_no_fabricated_slots(bottleneck_result):
    doc = bottleneck_result.scenario
    assert doc["identity"]["yard_fidelity"] == "G0" and "slot_occupancy" not in doc["initial_state"]
    yard = [e["location"] for e in doc["initial_state"]["container_locations"]
            if e["location"]["kind"] == "YARD_BLOCK"]
    assert yard and all(loc["slot_resolution"] == "BLOCK_ONLY"
                        and (loc["bay"], loc["row"], loc["tier"]) == (None, None, None) for loc in yard)


# --- 7, 17-20: identity and fingerprint behaviour ---------------------------------------

def test_yard_edits_keep_ids_vessels_and_berth_projection(low_doc):
    for change in ({"families.itp_low.yard.capacity_teu": 2100.0},
                   {"families.itp_low.yard.handling_capacity_moves_per_hour": 45.0},
                   {"families.itp_low.yard.block_count": 8, "families.itp_low.yard.block_line_count": 2}):
        other = generate_scenario(mutated_config(change), "itp_low", DEV, SEED)
        cargo = _vessel_cargo(low_doc)
        assert other["containers"][:len(cargo)] == cargo  # IDs and attributes of all vessel cargo
        assert other["vessels"] == low_doc["vessels"]
        for key in ("berth_projection_fingerprint", "berth_projection_physical_fingerprint"):
            assert other["fingerprints"][key] == low_doc["fingerprints"][key]
        for key in ("terminal_geometry_fingerprint", "physical_fingerprint"):
            assert other["fingerprints"][key] != low_doc["fingerprints"][key]
    capacity = generate_scenario(mutated_config({"families.itp_low.yard.capacity_teu": 2100.0}),
                                 "itp_low", DEV, SEED)
    # Less capacity -> less optional background: container manifest and pickup schedule change.
    for key in ("container_manifest_fingerprint", "exogenous_schedule_fingerprint"):
        assert capacity["fingerprints"][key] != low_doc["fingerprints"][key]


def test_prestaging_assumption_changes_landside_fingerprints_not_berth_projection(low_doc):
    other = generate_scenario(mutated_config({"landside.export_gate_lead_max_min": 1440.0}),
                              "itp_low", DEV, SEED)
    assert other["vessels"] == low_doc["vessels"]
    assert sum(c["present_at_episode_start"] for c in _vessel_cargo(other)) < \
        sum(c["present_at_episode_start"] for c in _vessel_cargo(low_doc))
    for key in ("container_manifest_fingerprint", "exogenous_schedule_fingerprint", "physical_fingerprint"):
        assert other["fingerprints"][key] != low_doc["fingerprints"][key]
    assert other["fingerprints"]["berth_projection_fingerprint"] == low_doc["fingerprints"]["berth_projection_fingerprint"]
    # A cargo change that alters vessel workload must change the berth projection.
    workload = generate_scenario(mutated_config({"families.itp_low.traffic.max_workload_moves": 800}),
                                 "itp_low", DEV, SEED)
    assert workload["fingerprints"]["berth_projection_physical_fingerprint"] != \
        low_doc["fingerprints"]["berth_projection_physical_fingerprint"]


def test_same_family_seed_and_config_reproduce_exogenous_data(config, bottleneck_result):
    again = generate_scenario(config, "itp_yard_bottleneck", DEV, SEED)
    assert again["fingerprints"] == bottleneck_result.scenario["fingerprints"]


# --- 21-22: unsupported configurations and no resampling --------------------------------

def test_capacity_shortfall_is_rejected_deterministically():
    tiny = mutated_config({"families.itp_low.yard.capacity_teu": 150.0})
    messages = set()
    for _ in range(2):
        with pytest.raises(ScenarioGenerationError) as error:
            generate_scenario(tiny, "itp_low", DEV, SEED)
        assert error.value.code == "YARD_CAPACITY_EXCEEDED"
        messages.add(error.value.message)
    assert len(messages) == 1


def test_infeasible_seeds_are_reported_not_resampled(tmp_path):
    tiny = mutated_config({"families.itp_low.yard.capacity_teu": 150.0})
    plan = plan_run(tiny, {"itp_low": 2}, output_root=tmp_path, run_id="infeasible")
    manifest = generate_run(tiny, plan, run_collision_audit=False)
    assert manifest["row_status_counts"] == {"rejected": 2}
    assert manifest["scenario_family_counts"]["itp_low"]["planned"] == 2
    assert manifest["scenario_family_counts"]["itp_low"]["not_accepted"] == 2
    index = (tmp_path / "development" / "infeasible" / "scenario_index.csv").read_text(encoding="utf-8")
    assert "seed10000000" in index and "seed10000001" in index and "seed10000002" not in index


# --- 24-27: decision statuses, bottleneck design, degenerate profile --------------------

def test_stabilization_values_are_not_silently_frozen(config):
    records = {r["decision_id"]: r for r in config.decisions}
    for decision_id in ("S2-008", "S2-019", "S2-022", "S2-023", "S2-031", "S2-032", "S2-033",
                        "S2-034", "S2-035", "S2-040", "S2-060", "S2-079"):
        assert records[decision_id]["status"] == "PROPOSED_PENDING_REVIEW", decision_id
    for record in config.decisions:
        if record["status"] == "FROZEN":
            assert record["source_kind"] in ("STEP1_FROZEN", "STEP2_BRIEF")
    assert config.family("itp_medium")["terminal"]["quay_crane_count"] == 4  # brief 9 reference fleet


def test_bottleneck_constraints_are_tighter_than_the_reference(config):
    reference, bottleneck = config.family("itp_medium"), config.family("itp_yard_bottleneck")
    assert bottleneck["intended_bottleneck"] == "yard_block_handling"
    assert reference["intended_bottleneck"] == "none"
    geometry = ("block_count", "block_line_count", "capacity_teu", "bay_count", "row_count", "max_tiers")
    assert {k: bottleneck["yard"][k] for k in geometry} == {k: reference["yard"][k] for k in geometry}
    assert bottleneck["yard"]["handling_capacity_moves_per_hour"] < reference["yard"]["handling_capacity_moves_per_hour"]
    assert bottleneck["yard"]["initial_occupancy_fraction"] > reference["yard"]["initial_occupancy_fraction"]
    assert bottleneck["terminal"] == reference["terminal"]


def test_degenerate_profile_on_bottleneck_family(config, bottleneck_result):
    doc = generate_scenario(config, "itp_yard_bottleneck", DEV, SEED, "degenerate_equivalence_v1")
    assert validate_scenario(doc, generator_config=config).ok
    assert doc["physics"]["yard"]["constraints_enabled"] is False
    standard = bottleneck_result.scenario
    assert doc["fingerprints"]["container_manifest_fingerprint"] == standard["fingerprints"]["container_manifest_fingerprint"]
    assert doc["fingerprints"]["berth_projection_physical_fingerprint"] == \
        standard["fingerprints"]["berth_projection_physical_fingerprint"]
    assert json.dumps(doc["terminal"], sort_keys=True) == json.dumps(standard["terminal"], sort_keys=True)
