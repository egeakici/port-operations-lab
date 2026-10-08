"""Negative scenario-stage validation with the Step 1 DQ codes (tests 6-9, 19-22, 24-27, 31, 43-44)."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from integrated_terminal_pilot.scenarios.validation import ERROR_CODES, validate_scenario
from tests.conftest import refingerprint


def _container(doc: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(c for c in doc["containers"] if c["container_id"] == cid)


def _location(doc: dict[str, Any], cid: str) -> dict[str, Any]:
    return next(e for e in doc["initial_state"]["container_locations"] if e["container_id"] == cid)


def dup_container(d):
    _container(d, "CNT-000002")["container_id"] = "CNT-000001"


def dup_vessel(d):
    d["vessels"][1]["vessel_id"] = "V001"


def dup_crane(d):
    d["resources"]["quay_cranes"].append(dict(d["resources"]["quay_cranes"][0]))


def dup_block(d):
    d["terminal"]["yard_blocks"][1]["block_id"] = "B01"


def bad_size(d):
    _container(d, "CNT-000001")["container_size"] = "45_ft"


def teu_mismatch(d):
    _container(d, "CNT-000002")["size_teu"] = 1.0


def bad_weight(d):
    _container(d, "CNT-000001")["gross_weight_kg"] = 99_000


def import_with_destination(d):
    _container(d, "CNT-000001")["destination_vessel_id"] = "V002"


def export_with_origin(d):
    _container(d, "CNT-000004")["origin_vessel_id"] = "V001"


def transshipment_same_vessels(d):
    _container(d, "CNT-000003")["destination_vessel_id"] = "V001"


def fictional_vessel(d):
    _container(d, "CNT-000004")["destination_vessel_id"] = "V099"


def pre_episode_misuse(d):
    _container(d, "CNT-000001")["origin_vessel_id"] = "PRE_EPISODE"


def wrong_group(d):
    _container(d, "CNT-000001")["container_group_id"] = "GRP-0002"


def unknown_group(d):
    _container(d, "CNT-000001")["container_group_id"] = "GRP-0099"


def group_quantity(d):
    d["container_groups"][3]["quantity"] = 3


def workload_mismatch(d):
    d["vessels"][0]["discharge_move_count"] = 4


def nominal_mismatch(d):
    d["vessels"][0]["nominal_service_time_min"] = 60.0


def initial_overfill(d):
    d["terminal"]["yard_blocks"][1]["capacity_teu"] = 0.5


def capacity_above_geometry(d):
    d["terminal"]["yard_blocks"][0]["capacity_teu"] = 120.0


def block_outside_terminal(d):
    block = d["terminal"]["yard_blocks"][1]
    block["origin_x_m"] = 1180.0
    block["transfer_point_x_m"] = 1180.0 + 26.0


def block_odd_bays(d):
    d["terminal"]["yard_blocks"][0]["bay_count"] = 7


def size_not_allowed(d):
    d["terminal"]["yard_blocks"][1]["allowed_sizes"] = ["40_ft"]


def fabricated_slot_in_g0(d):
    _location(d, "CNT-000005")["location"].update(bay=3, row=2, tier=1)


def gate_after_cutoff(d):
    _container(d, "CNT-000004")["scheduled_gate_in_time_min"] = 500.0


def pickup_before_arrival(d):
    d["vessels"][0]["arrival_time_min"] = 400.0  # CNT-000001 pickup request is at 300


def present_but_expected(d):
    _location(d, "CNT-000005").update(status="EXPECTED_BY_LANDSIDE",
                                      location={"kind": "EXTERNAL_LANDSIDE", "location_id": None, "bay": None,
                                                "row": None, "tier": None, "slot_resolution": None})


def missing_field(d):
    del _container(d, "CNT-000001")["gross_weight_kg"]


def unknown_field(d):
    _container(d, "CNT-000001")["colour"] = "blue"


def schema_version(d):
    d["schema_version"] = "itp_scenario_v0"


def crane_impossible(d):
    d["vessels"][0]["max_cranes"] = 3


def seed_outside_band(d):
    d["identity"]["scenario_seed"] = 12_000_005
    d["identity"]["scenario_id"] = "itp_example_development_seed12000005"


def extra_work(d):
    d["vessels"][0]["extra_work_units"] = 2


CASES: list[tuple[str, Callable[[dict], None], str]] = [
    ("duplicate container id", dup_container, "DUPLICATE_CONTAINER_ID"),
    ("duplicate vessel id", dup_vessel, "DUPLICATE_ENTITY_ID"),
    ("duplicate crane id", dup_crane, "DUPLICATE_ENTITY_ID"),
    ("duplicate block id", dup_block, "DUPLICATE_ENTITY_ID"),
    ("unsupported size", bad_size, "INVALID_CONTAINER_SIZE"),
    ("TEU mismatch", teu_mismatch, "TEU_SIZE_MISMATCH"),
    ("weight", bad_weight, "INVALID_WEIGHT"),
    ("import with destination", import_with_destination, "INVALID_CARGO_FLOW"),
    ("export with origin", export_with_origin, "INVALID_CARGO_FLOW"),
    ("transshipment same vessel", transshipment_same_vessels, "INVALID_CARGO_FLOW"),
    ("fictional vessel reference", fictional_vessel, "UNKNOWN_REFERENCE"),
    ("PRE_EPISODE on arriving cargo", pre_episode_misuse, "INVALID_CARGO_FLOW"),
    ("member fields differ from group", wrong_group, "GROUP_MEMBERSHIP_ERROR"),
    ("unknown group", unknown_group, "GROUP_MEMBERSHIP_ERROR"),
    ("group quantity", group_quantity, "GROUP_TEU_MISMATCH"),
    ("vessel move count", workload_mismatch, "WORKLOAD_RECONCILIATION_FAILURE"),
    ("nominal service", nominal_mismatch, "WORKLOAD_RECONCILIATION_FAILURE"),
    ("initial occupancy over capacity", initial_overfill, "YARD_CAPACITY_EXCEEDED"),
    ("capacity above geometric limit", capacity_above_geometry, "YARD_CAPACITY_EXCEEDED"),
    ("block outside terminal", block_outside_terminal, "INVALID_YARD_GEOMETRY"),
    ("odd bay count", block_odd_bays, "INVALID_YARD_GEOMETRY"),
    ("size not allowed in block", size_not_allowed, "SLOT_SIZE_CONFLICT"),
    ("fabricated G1 slot in G0", fabricated_slot_in_g0, "FIDELITY_MISLABEL"),
    ("gate-in after cutoff", gate_after_cutoff, "CAUSALITY_VIOLATION"),
    ("pickup before arrival", pickup_before_arrival, "CAUSALITY_VIOLATION"),
    ("present container not in yard", present_but_expected, "INVALID_STATUS_TRANSITION"),
    ("missing required field", missing_field, "UNSUPPORTED_ASSUMPTION"),
    ("unknown field", unknown_field, "UNSUPPORTED_ASSUMPTION"),
    ("schema version", schema_version, "UNSUPPORTED_ASSUMPTION"),
    ("impossible crane count", crane_impossible, "INVALID_ENTITY_ATTRIBUTE"),
    ("seed outside split band", seed_outside_band, "SEED_NAMESPACE_VIOLATION"),
    ("extra work units", extra_work, "UNSUPPORTED_ASSUMPTION"),
]


def test_golden_fixture_is_valid(golden_doc):
    assert validate_scenario(golden_doc).ok


@pytest.mark.parametrize("name, mutate, code", CASES, ids=[c[0] for c in CASES])
def test_invalid_scenario_fails_with_expected_code(golden, name, mutate, code):
    mutate(golden)
    report = validate_scenario(golden)
    assert not report.ok
    assert code in report.codes, report.to_dict()
    issue = next(i for i in report.issues if i.code == code)
    assert issue.dq_rule == ERROR_CODES[code]
    assert issue.entity_type and issue.entity_id and issue.field_path and issue.message
    assert issue.severity == "REJECT_SCENARIO"


def test_validation_is_deterministic(golden):
    dup_container(golden)
    bad_weight(golden)
    assert validate_scenario(golden).issues == validate_scenario(golden).issues


def test_validator_never_repairs_input(golden):
    bad_weight(golden)
    before = repr(golden)
    validate_scenario(golden)
    assert repr(golden) == before


def test_fingerprint_mismatch_and_incomplete(golden, golden_doc):
    _container(golden, "CNT-000001")["gross_weight_kg"] = 18001  # valid value, stale fingerprints
    assert "FINGERPRINT_MISMATCH" in validate_scenario(golden).codes
    assert validate_scenario(refingerprint(golden)).ok
    del golden["fingerprints"]["physical_fingerprint"]
    assert "FINGERPRINT_INCOMPLETE" in validate_scenario(golden).codes


def test_non_object_documents_are_rejected():
    for value in (None, [], "scenario"):
        report = validate_scenario(value)
        assert not report.ok and report.codes == {"UNSUPPORTED_ASSUMPTION"}
