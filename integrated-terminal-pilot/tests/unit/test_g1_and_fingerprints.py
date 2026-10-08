"""G1 slot rules (tests 27-29), fingerprints (37-38), serialization (3-4)."""

from __future__ import annotations

import json

import pytest

from integrated_terminal_pilot.scenarios.fingerprints import canonical_json
from integrated_terminal_pilot.scenarios.serialization import load_scenario, scenario_bytes, write_scenario
from integrated_terminal_pilot.scenarios.validation import (
    _Collector, validate_g1_block_slots, validate_scenario,
)
from tests.conftest import refingerprint

# docs/container_yard_foundation.md 11.5 (illustrative G1 snapshot of B01 at t = 36).
FOUNDATION_SNAPSHOT = [
    {"container_id": "CNT-000001", "bay": 1, "row": 1, "tier": 1, "bay_span": 1},
    {"container_id": "CNT-000003", "bay": 5, "row": 2, "tier": 1, "bay_span": 2},
    {"container_id": "CNT-000002", "bay": 5, "row": 2, "tier": 2, "bay_span": 2},
]


def _slot_codes(golden_doc, slots):
    collector = _Collector()
    containers = {c["container_id"]: c for c in golden_doc["containers"]}
    block = golden_doc["terminal"]["yard_blocks"][0]
    validate_g1_block_slots(collector, block, slots, containers, "fixture")
    return {issue.code for issue in collector.items}


def test_foundation_g1_snapshot_is_valid(golden_doc):
    assert _slot_codes(golden_doc, FOUNDATION_SNAPSHOT) == set()


@pytest.mark.parametrize("change, code", [
    ({2: {"tier": 3}}, "FLOATING_STACK"),
    ({1: {"bay": 6}}, "INVALID_STACK_POSITION"),          # 40 ft anchor must be odd
    ({0: {"bay": 9}}, "INVALID_STACK_POSITION"),          # bay outside 1..8
    ({0: {"tier": 0}}, "INVALID_STACK_POSITION"),         # 1-based tiers
    ({1: {"bay_span": 1}}, "SLOT_SIZE_CONFLICT"),          # 40 ft spans two bays
    ({0: {"bay": 5, "row": 2, "tier": 1}}, "DUPLICATE_PHYSICAL_LOCATION"),
    ({0: {"bay": 6, "row": 2, "tier": 3}}, "SLOT_SIZE_CONFLICT"),  # 20 ft on a 40 ft stack position
])
def test_invalid_g1_slots_are_rejected(golden_doc, change, code):
    slots = [dict(s) for s in FOUNDATION_SNAPSHOT]
    for index, update in change.items():
        slots[index].update(update)
    assert code in _slot_codes(golden_doc, slots)


def _g1_variant(golden):
    """Test-only G1 variant: the pre-episode container CNT-000005 gets an explicit slot."""
    golden["identity"]["yard_fidelity"] = "G1"
    entry = next(e for e in golden["initial_state"]["container_locations"]
                 if e["container_id"] == "CNT-000005")
    entry["location"].update(bay=3, row=2, tier=1, slot_resolution="SLOT")
    golden["initial_state"]["slot_occupancy"] = [
        {"block_id": "B02", "slots": [{"container_id": "CNT-000005", "bay": 3, "row": 2, "tier": 1,
                                       "bay_span": 1}]}]
    return golden


def test_g1_scenario_variant_is_valid_and_consistent(golden):
    variant = refingerprint(_g1_variant(golden))
    assert validate_scenario(variant).ok, validate_scenario(variant).to_dict()
    variant["initial_state"]["slot_occupancy"][0]["slots"][0]["tier"] = 2
    report = validate_scenario(variant)
    assert {"FLOATING_STACK", "FIDELITY_MISLABEL"} <= report.codes


def test_g0_scenario_cannot_carry_slot_occupancy(golden):
    golden["initial_state"]["slot_occupancy"] = []
    assert "FIDELITY_MISLABEL" in validate_scenario(golden).codes


def test_fingerprints_are_stable(config, low_doc):
    from integrated_terminal_pilot.scenarios.fingerprints import compute_fingerprints
    recomputed = compute_fingerprints(low_doc, generator_config_fingerprint=config.parameters_fingerprint)
    assert recomputed == low_doc["fingerprints"]


@pytest.mark.parametrize("mutate, changed, unchanged", [
    (lambda d: d["containers"][0].update(container_size="40_ft", size_teu=2.0) or
     d["container_groups"][0].update(container_size="40_ft"),
     {"container_manifest_fingerprint", "physical_fingerprint"},
     {"terminal_geometry_fingerprint", "berth_projection_fingerprint"}),
    (lambda d: d["terminal"]["quay"].update(min_clearance_m=25.0),
     {"terminal_geometry_fingerprint", "physical_fingerprint", "berth_projection_fingerprint",
      "berth_projection_physical_fingerprint"},
     {"container_manifest_fingerprint"}),
    (lambda d: d["initial_state"]["container_locations"][4]["location"].update(location_id="B01"),
     {"container_manifest_fingerprint", "physical_fingerprint"},
     {"exogenous_schedule_fingerprint", "berth_projection_fingerprint"}),
    (lambda d: d["containers"][0].update(scheduled_pickup_time_min=310.0),
     {"exogenous_schedule_fingerprint", "physical_fingerprint"},
     {"berth_projection_fingerprint", "terminal_geometry_fingerprint"}),
    (lambda d: d["terminal"]["yard_blocks"][0].update(handling_capacity_moves_per_hour=45.0),
     {"terminal_geometry_fingerprint", "physical_fingerprint"},
     {"berth_projection_fingerprint", "berth_projection_physical_fingerprint"}),
    (lambda d: d["vessels"][0].update(max_cranes=2),
     {"exogenous_schedule_fingerprint", "physical_fingerprint"},
     {"berth_projection_fingerprint"}),
])
def test_fingerprint_changes_only_where_physics_changes(golden, golden_doc, mutate, changed, unchanged):
    mutate(golden)
    after = refingerprint(golden)["fingerprints"]
    before = golden_doc["fingerprints"]
    for key in changed:
        assert after[key] != before[key], key
    for key in unchanged:
        assert after[key] == before[key], key


def test_formatting_and_key_order_do_not_change_fingerprints(golden_doc, tmp_path):
    reordered = json.loads(json.dumps(golden_doc, indent=7), object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert refingerprint(reordered)["fingerprints"] == golden_doc["fingerprints"]
    assert canonical_json(reordered) == canonical_json(golden_doc)


def test_serialization_round_trip_and_stable_ordering(golden_doc, tmp_path):
    path = write_scenario(golden_doc, tmp_path)
    assert path.name == "itp_example_development_seed10000000.scenario.json"
    loaded = load_scenario(path)
    assert loaded == golden_doc
    assert path.read_bytes() == scenario_bytes(loaded)
    text = path.read_text(encoding="utf-8")
    top_keys = [line.split('"')[1] for line in text.splitlines() if line.startswith('  "')]
    assert top_keys == sorted(top_keys)
    with pytest.raises(FileExistsError):
        write_scenario(golden_doc, tmp_path)


def test_non_finite_numbers_are_rejected(tmp_path):
    path = tmp_path / "bad.scenario.json"
    path.write_text('{"x": NaN}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_scenario(path)
