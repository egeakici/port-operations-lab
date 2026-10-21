"""Pre-Step 6 checks on stored development scenarios (brief section 15, items 3, 5, 6, 13).

Uses the stored development batch only (10M seed band). Skips when it is not present.
"""

from __future__ import annotations

import json

import pytest

from integrated_terminal_pilot.benchmark import pre_step6
from integrated_terminal_pilot.benchmark.profiles import PRIMARY_RESEARCH_PROFILE
from integrated_terminal_pilot.benchmark.runner import run_arm
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT
from integrated_terminal_pilot.scenarios.serialization import file_sha256

pytestmark = pytest.mark.integration
SOURCE = PROJECT_ROOT / "experiments" / "scenarios" / "development" / pre_step6.SOURCE_RUN
STEP5_SMOKE = PROJECT_ROOT / "experiments" / "step5_development" / "s5dev_smoke_v1"
ARMS = [("A1", None), ("A2", None), ("A3", 11), ("A3", 23), ("A3", 37)]

needs_source = pytest.mark.skipif(not SOURCE.exists(), reason="development scenario batch not present")


@needs_source
def test_stored_development_sources_are_unchanged():
    for scenario in pre_step6.build_plan()["scenarios"]:
        assert file_sha256(PROJECT_ROOT / scenario["file"]) == scenario["file_sha256"], scenario["scenario_id"]


@needs_source
def test_primary_profile_pairs_all_five_arms_on_identical_physics_and_obligations():
    plan = pre_step6.build_plan()
    low = next(s for s in plan["scenarios"] if s["scenario_id"] == "itp_low_development_seed10000000")
    doc = pre_step6._load_doc(low)
    records = [run_arm(doc, arm_id=a, training_seed=k, research_profile=PRIMARY_RESEARCH_PROFILE) for a, k in ARMS]
    assert [r["status"] for r in records] == ["COMPLETED"] * 5
    assert len({r["comparison_fingerprint"] for r in records}) == 1
    assert len({r["research_profile"]["resolved_physics_fingerprint"] for r in records}) == 1
    assert len({r["research_profile"]["derived_fingerprints"]["exogenous_schedule_fingerprint"] for r in records}) == 1
    assert records[0]["research_profile"]["derived_fingerprints"]["exogenous_schedule_fingerprint"] == \
        low["exogenous_schedule_fingerprint"]
    assert len({r["outbound_obligations"]["N_out"] for r in records}) == 1
    assert all(r["outbound_obligations"]["reconciliation_ok"] for r in records)
    assert {(r["shared"]["crane_policy_id"], r["shared"]["yard_policy_id"], r["shared"]["quay_crane_count"])
            for r in records} == {("primitive_crane_greedy_v1", "yard_occupancy_balance_v1", 8)}
    assert [r["arm"]["ppo_training_seed"] for r in records] == [None, None, 11, 23, 37]
    assert {r["scenario"]["scenario_seed"] for r in records} == {10_000_000}
    for r in records[2:]:
        ppo = r["decisions"]["ppo_support"]
        assert ppo["vessel_epoch_values"]["n"] == len(ppo["occupancy_features"]) > 0


@pytest.mark.skipif(not STEP5_SMOKE.exists(), reason="Step 5 smoke run not present")
@needs_source
def test_historical_four_crane_first_fit_runs_still_reproduce_their_step5_digests():
    plan = pre_step6.build_plan()
    low = next(s for s in plan["scenarios"] if s["scenario_id"] == "itp_low_development_seed10000000")
    doc = pre_step6._load_doc(low)
    for label, (arm, seed) in (("A1", ("A1", None)), ("A3-train11", ("A3", 11))):
        stored = json.loads((STEP5_SMOKE / "runs" / "protocol_v1_first_fit" / label /
                             "itp_low_development_seed10000000.json").read_text(encoding="utf-8"))
        again = run_arm(doc, arm_id=arm, training_seed=seed)
        differences={name:{'expected':expected,'actual':again['digests']['files'].get(name)}
                     for name,expected in stored['digests']['files'].items()
                     if again['digests']['files'].get(name)!=expected}
        assert again["digests"]["trace_sha256"] == stored["digests"]["trace_sha256"], json.dumps({
            'arm':label,'differing_canonical_streams':differences,
            'expected_kpi':stored['kpi'],'actual_kpi':again['kpi']},indent=2)
        assert again["comparison_fingerprint"] == stored["comparison_fingerprint"], label
