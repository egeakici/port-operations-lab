"""Step 2 integration tests A-T with installed Project 01-03 packages and repository files."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.scenarios.synthetic import planned_berth_occupancy_minutes
from mini_port_sim.scenario import ServiceConfig
from integrated_terminal_pilot.scenarios.berth_projection import (
    build_berth_projection, projection_physical_fingerprint, verify_dynamic_env_reset,
)
from integrated_terminal_pilot.scenarios.cli import main as cli_main
from integrated_terminal_pilot.scenarios.generator import (
    ScenarioGenerationError, generate_scenario, generate_scenario_with_diagnostics,
)
from integrated_terminal_pilot.scenarios.outputs import (
    DEFAULT_OUTPUT_ROOT, canonical_run_contents, generate_run, plan_run, validate_run, audit_run,
)
from integrated_terminal_pilot.scenarios.validation import validate_scenario
from tests.conftest import DEV, HEAVY_SEED, PROJECT_ROOT, SEED, mutated_config, refingerprint

pytestmark = pytest.mark.integration
REPO_ROOT = PROJECT_ROOT.parent
CHECKPOINT_SHA256 = {
    "dynamic_ppo_tiny_v1_extended_cuda/seed_11": "35a1a0ba0b8d231fb26b2aa2ecfebad49e9b3ab9a949c2ea306054dbe1a7f46d",
    "dynamic_ppo_tiny_v1_extended_cuda/seed_23": "4773a36832f02179e27bd00e4308829ae9a4eb00612ad8528b6975b88628c874",
    "dynamic_ppo_tiny_v1_extended_cuda/seed_37": "7a3138ce37f3ef18c7c1b74df7e20f7a977f552a2e69e21dea828c79a9cd956a",
    "dynamic_ppo_medium_heavy_v1_extended_cuda/seed_11": "3373e06060a6f14cae422d7041d863cf18001bed285d1b896bffbe4dfae32018",
    "dynamic_ppo_medium_heavy_v1_extended_cuda/seed_23": "a2a105108d9b030cec8e26538012cbe1c2c2bc872f992e1a11ac0cd428ffd625",
    "dynamic_ppo_medium_heavy_v1_extended_cuda/seed_37": "8318b49712fbbd04c6adbf1b357e2c5916fae539306b50272ded7464d002a3a6",
}


@pytest.mark.parametrize("fixture", ["medium_doc", "heavy_doc"])
def test_a_b_d_primary_families_generate_valid_reconciled_scenarios(request, config, fixture):
    doc = request.getfixturevalue(fixture)
    assert validate_scenario(doc, generator_config=config).ok
    expected_vessels = {"medium_doc": 16, "heavy_doc": 24}[fixture]
    assert len(doc["vessels"]) == expected_vessels
    containers = doc["containers"]
    assert len({c["container_id"] for c in containers}) == len(containers)
    moves = sum(v["workload_moves"] for v in doc["vessels"])
    linked = sum((c["origin_vessel_id"] not in (None, "PRE_EPISODE")) + (c["destination_vessel_id"] is not None)
                 for c in containers)
    assert moves == linked
    assert all(250 <= v["workload_moves"] <= 900 and 200 <= v["length_m"] <= 360 for v in doc["vessels"])


def test_b_heavy_rejection_is_explicit_and_not_repaired(config):
    with pytest.raises(ScenarioGenerationError) as error:
        generate_scenario(config, "itp_heavy", DEV, SEED)
    assert error.value.code == "YARD_CAPACITY_EXCEEDED"


def test_c_yard_bottleneck_is_blocked_with_evidence(config):
    with pytest.raises(ScenarioGenerationError) as error:
        generate_scenario(config, "itp_yard_bottleneck", DEV, SEED)
    assert error.value.code == "UNSUPPORTED_ASSUMPTION"
    unblocked = mutated_config({}, statuses={"S2-025": "PROPOSED_PENDING_REVIEW"})
    with pytest.raises(ScenarioGenerationError) as infeasible:
        generate_scenario(unblocked, "itp_yard_bottleneck", DEV, SEED)
    assert infeasible.value.code == "YARD_CAPACITY_EXCEEDED"


@pytest.mark.parametrize("fixture", ["medium_doc", "heavy_doc", "low_doc"])
def test_e_f_g_h_i_projection_and_dynamic_env_reset(request, fixture):
    doc = request.getfixturevalue(fixture)
    projection = build_berth_projection(doc)
    assert isinstance(projection, BAPScenarioInstance)
    assert BAPScenarioInstance.from_dict(projection.to_dict()) == projection
    assert projection.content_fingerprint == doc["fingerprints"]["berth_projection_fingerprint"]
    assert projection_physical_fingerprint(projection) == doc["fingerprints"]["berth_projection_physical_fingerprint"]
    service = ServiceConfig()
    by_id = {v["vessel_id"]: v for v in doc["vessels"]}
    for vessel in projection.vessels:
        nominal = planned_berth_occupancy_minutes(service=service, workload_moves=vessel.workload_moves)
        assert vessel.service_time_min == nominal == 30.0 + 0.5 * vessel.workload_moves + 20.0
        assert vessel.workload_moves == by_id[vessel.vessel_id]["workload_moves"]
    reset = verify_dynamic_env_reset(projection, 24)
    assert reset["reset_ok"] and reset["observation_in_space"] and reset["projection_fingerprint_matches"]
    assert reset["action_space_n"] == 1153 and len(reset["observation_keys"]) == 9


def test_j_no_invented_runtime_decisions(medium_doc):
    def keys(value, found):
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(key)
                keys(item, found)
        elif isinstance(value, list):
            for item in value:
                keys(item, found)
        return found
    present = keys(medium_doc, set())
    for runtime in ("berth_position_m", "berth_start_time_min", "assigned_vessel_id",
                    "departure_time_min", "terminal_entry_time_min", "actual_release_time_min",
                    "completed_moves", "slot_occupancy"):
        assert runtime not in present
    yard = [e["location"] for e in medium_doc["initial_state"]["container_locations"]
            if e["location"]["kind"] == "YARD_BLOCK"]
    assert yard and all(loc["slot_resolution"] == "BLOCK_ONLY" and loc["bay"] is None for loc in yard)


def test_k_golden_fixture(golden_doc):
    assert validate_scenario(golden_doc).ok
    assert golden_doc["identity"]["generator_version"] == "hand_written_example"
    assert golden_doc["fingerprints"]["generator_config_fingerprint"] is None
    assert len(golden_doc["containers"]) == 5
    assert sum(c["size_teu"] for c in golden_doc["containers"]) == 7.0
    assert sum(v["workload_moves"] for v in golden_doc["vessels"]) == 6
    assert [v["nominal_service_time_min"] for v in golden_doc["vessels"]] == [51.5, 51.5]
    assert [(b["transfer_point_x_m"], b["transfer_point_y_m"]) for b in golden_doc["terminal"]["yard_blocks"]] == \
        [(126.0, 150.0), (426.0, 150.0)]


def test_l_q_generate_twice_identical_and_hash_verified(config, tmp_path):
    first = plan_run(config, {"itp_low": 2, "itp_medium": 1}, output_root=tmp_path / "a", run_id="twice")
    second = plan_run(config, {"itp_low": 2, "itp_medium": 1}, output_root=tmp_path / "b", run_id="twice")
    manifest = generate_run(config, first)
    generate_run(config, second, run_collision_audit=False)
    a_dir, b_dir = Path(first["output_dir"]), Path(second["output_dir"])
    a, b = canonical_run_contents(a_dir), canonical_run_contents(b_dir)
    a.pop("fingerprint_audit.json")
    b.pop("fingerprint_audit.json")  # differs only by the skipped collision audit
    assert a == b
    assert manifest["collision_audit_passed"] is True
    assert validate_run(a_dir, config)["passed"]
    audit = audit_run(a_dir, output_root=tmp_path / "a")
    assert audit["passed"], audit
    assert audit["project03_collision_audit"]["project03_examined_fingerprint_count"] > 800


def test_m_weight_change_leaves_arrivals_and_ids_unchanged(config, low_doc):
    changed = mutated_config({"cargo.laden_weight_kg.20_ft.max": 26000})
    other = generate_scenario(changed, "itp_low", DEV, SEED)
    assert other["vessels"] == low_doc["vessels"]
    assert [c["container_id"] for c in other["containers"]] == [c["container_id"] for c in low_doc["containers"]]
    assert other["fingerprints"]["berth_projection_fingerprint"] == low_doc["fingerprints"]["berth_projection_fingerprint"]
    assert other["fingerprints"]["container_manifest_fingerprint"] != low_doc["fingerprints"]["container_manifest_fingerprint"]


def test_n_yard_parameter_change_leaves_projection_unchanged(config, low_doc):
    changed = mutated_config({"families.itp_low.yard.handling_capacity_moves_per_hour": 45.0})
    other = generate_scenario(changed, "itp_low", DEV, SEED)
    assert other["fingerprints"]["berth_projection_fingerprint"] == low_doc["fingerprints"]["berth_projection_fingerprint"]
    assert other["fingerprints"]["physical_fingerprint"] != low_doc["fingerprints"]["physical_fingerprint"]
    occupancy = mutated_config({"families.itp_low.yard.initial_occupancy_fraction": 0.3})
    lower = generate_scenario(occupancy, "itp_low", DEV, SEED)
    vessel_cargo = [c for c in low_doc["containers"] if c["origin_vessel_id"] != "PRE_EPISODE"
                    or c["cargo_flow"] != "import"]
    assert lower["containers"][:len(vessel_cargo)] == vessel_cargo  # filler is last; cargo IDs stable
    assert len(lower["containers"]) < len(low_doc["containers"])


def test_o_negative_fixture_on_generated_scenario(medium_doc):
    doc = json.loads(json.dumps(medium_doc))
    doc["containers"][0]["size_teu"] = 3.0
    assert "TEU_SIZE_MISMATCH" in validate_scenario(doc).codes
    doc = json.loads(json.dumps(medium_doc))
    doc["containers"][1]["container_id"] = doc["containers"][0]["container_id"]
    assert "DUPLICATE_CONTAINER_ID" in validate_scenario(doc).codes


def test_p_cli_refuses_to_overwrite_and_validates(config, tmp_path, capsys):
    args = ["--family", "itp_low=1", "--output-root", str(tmp_path), "--run-id", "cli_run"]
    assert cli_main(["--dry-run", *args]) == 0
    assert not any(tmp_path.iterdir())
    assert cli_main(["--generate", *args]) == 0
    with pytest.raises(FileExistsError):
        cli_main(["--generate", *args])
    run_dir = tmp_path / "development" / "cli_run"
    assert cli_main(["--validate", "--run-dir", str(run_dir)]) == 0
    capsys.readouterr()


def test_degenerate_profile_keeps_exogenous_inputs(config, medium_doc):
    result = generate_scenario_with_diagnostics(config, "itp_medium", DEV, SEED, "degenerate_equivalence_v1")
    doc = result.scenario
    assert validate_scenario(doc, generator_config=config).ok
    assert doc["identity"]["scenario_id"].endswith("__degenerate_equivalence_v1")
    assert doc["physics"]["transport"]["enabled"] is False and doc["physics"]["yard"]["constraints_enabled"] is False
    assert doc["physics"]["service"] == medium_doc["physics"]["service"]
    assert all(c["nominal_moves_per_hour"] == 120.0 for c in doc["resources"]["quay_cranes"])
    assert all(v["max_cranes"] == 1 for v in doc["vessels"])
    strip = lambda vs: [{k: v for k, v in x.items() if k != "max_cranes"} for x in vs]
    assert strip(doc["vessels"]) == strip(medium_doc["vessels"])
    # Same berth physics; content fingerprints differ only through the scenario id.
    assert doc["fingerprints"]["berth_projection_physical_fingerprint"] == \
        medium_doc["fingerprints"]["berth_projection_physical_fingerprint"]
    assert doc["fingerprints"]["berth_projection_fingerprint"] != medium_doc["fingerprints"]["berth_projection_fingerprint"]
    # Cargo and initial state are identical across profiles (manifest fingerprint is ID-free).
    assert doc["fingerprints"]["container_manifest_fingerprint"] == medium_doc["fingerprints"]["container_manifest_fingerprint"]
    assert doc["fingerprints"]["physical_fingerprint"] != medium_doc["fingerprints"]["physical_fingerprint"]


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def test_r_projects_01_to_03_unchanged():
    paths = ["01-terminal-operations-core", "02-mini-port-simulation", "03-berth-allocation-lab"]
    assert _git("status", "--porcelain", "--", *paths) == ""
    assert _git("diff", "--stat", "HEAD", "--", *paths) == ""


def test_s_frozen_checkpoints_unmodified():
    root = REPO_ROOT / "03-berth-allocation-lab" / "experiments" / "rl" / "dynamic_extended_cuda"
    if not root.exists():
        pytest.skip("Frozen Project 03 checkpoints are local, Git-ignored artifacts and are absent here.")
    for relative, expected in CHECKPOINT_SHA256.items():
        path = root / relative / "best_validation_model.zip"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative


def test_t_no_held_out_or_validation_namespace_generated(config):
    for name in ("validation", "test", "diagnostic"):
        assert not (DEFAULT_OUTPUT_ROOT / name).exists()
    with pytest.raises(ScenarioGenerationError):
        plan_run(config, {"itp_medium": 1}, split="test")
