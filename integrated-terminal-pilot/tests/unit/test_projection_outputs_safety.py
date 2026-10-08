"""PPO support (36), immutable outputs (41-42), no training or inference (45)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from integrated_terminal_pilot.scenarios.berth_projection import (
    assess_ppo_support, build_berth_projection,
)
from integrated_terminal_pilot.scenarios.outputs import (
    RunExistsError, generate_run, plan_run, verify_manifest,
)


def test_projection_carries_only_berth_inputs(golden_doc):
    projection = build_berth_projection(golden_doc)
    data = projection.to_dict()
    assert data["split"] == "train" and data["formulation"] == "dynamic"
    assert data["future_horizon_min"] == 240.0 and data["termination_mode"] == "drain"
    assert set(data["vessels"][0]) == {"vessel_id", "arrival_time_min", "length_m",
                                       "service_time_min", "workload_moves"}
    assert data["vessels"][0]["service_time_min"] == 51.5
    text = json.dumps(data)
    for forbidden in ("container", "crane", "yard", "gate", "pickup", "CNT-"):
        assert forbidden not in text


def test_ppo_support_in_and_out(golden_doc, low_doc):
    assert assess_ppo_support(low_doc)["medium_heavy"]["status"] == "IN_SUPPORT"
    assert assess_ppo_support(low_doc)["tiny"]["status"] == "OUT_OF_SUPPORT"  # 1200 m quay
    support = assess_ppo_support(golden_doc)["medium_heavy"]
    assert support["status"] == "OUT_OF_SUPPORT"  # example workloads (3 moves) and lengths are illustrative
    assert any("workload" in reason for reason in support["reasons"])
    long_quay = json.loads(json.dumps(low_doc))
    long_quay["vessels"][0]["length_m"] = 380.0
    assert assess_ppo_support(long_quay)["medium_heavy"]["status"] == "OUT_OF_SUPPORT"
    many = json.loads(json.dumps(low_doc))
    many["vessels"] = many["vessels"] * 4
    assert any("vessel count" in r for r in assess_ppo_support(many)["medium_heavy"]["reasons"])


@pytest.fixture(scope="module")
def small_run(tmp_path_factory, config):
    root = tmp_path_factory.mktemp("runs")
    plan = plan_run(config, {"itp_low": 1}, output_root=root, run_id="unit_run")
    manifest = generate_run(config, plan, run_collision_audit=False)
    return root, plan, manifest


def test_run_is_immutable(small_run, config):
    root, plan, manifest = small_run
    assert manifest["row_status_counts"] == {"accepted": 1}
    with pytest.raises(RunExistsError):
        generate_run(config, plan, run_collision_audit=False)
    stale = plan_run(config, {"itp_low": 1}, output_root=root, run_id="stale_run")
    (root / "development" / "stale_run.partial").mkdir(parents=True)
    with pytest.raises(RunExistsError):
        generate_run(config, stale, run_collision_audit=False)


def test_manifest_and_file_hashes_verify_and_detect_tampering(small_run, tmp_path):
    import shutil
    root, plan, manifest = small_run
    run_dir = root / "development" / "unit_run"
    assert verify_manifest(run_dir)["passed"]
    assert manifest["policy_executed"] is False and manifest["rl_training_performed"] is False
    assert manifest["test_evaluation_performed"] is False and manifest["ppo_checkpoint_loaded"] is False
    copy_dir = tmp_path / "copy"
    shutil.copytree(run_dir, copy_dir)
    (copy_dir / "quality_report.md").write_text("tampered", encoding="utf-8")
    result = verify_manifest(copy_dir)
    assert not result["passed"] and "hash mismatch quality_report.md" in result["problems"]
    shutil.rmtree(copy_dir)
    shutil.copytree(run_dir, copy_dir)
    manifest_path = copy_dir / "manifest.json"
    manifest_path.write_text(manifest_path.read_text(encoding="utf-8").replace('"accepted": 1', '"accepted": 2'),
                             encoding="utf-8")
    assert "manifest.json does not match its SHA-256 sidecar" in verify_manifest(copy_dir)["problems"]


def test_dry_run_plan_writes_nothing(config, tmp_path):
    plan = plan_run(config, {"itp_medium": 2}, output_root=tmp_path)
    assert plan["families"][0]["seeds"] == [10_000_000, 10_000_001]
    assert not any(tmp_path.iterdir())


def test_generation_imports_no_training_or_inference_stack():
    code = (
        "import sys\n"
        "from integrated_terminal_pilot.scenarios import load_generator_config, generate_scenario, "
        "build_berth_projection, verify_dynamic_env_reset, validate_scenario\n"
        "c = load_generator_config()\n"
        "d = generate_scenario(c, 'itp_low', 'development', 10000002)\n"
        "assert validate_scenario(d, generator_config=c).ok\n"
        "verify_dynamic_env_reset(build_berth_projection(d), 24)\n"
        "bad = [m for m in ('torch', 'stable_baselines3', 'sb3_contrib') if m in sys.modules]\n"
        "print('LOADED', bad)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "LOADED []" in out.stdout
