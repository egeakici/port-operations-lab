"""Step 6 gates on stored development data and determinism (G6-05, G6-14, G6-16)."""

from __future__ import annotations

import os

import pytest

from integrated_terminal_pilot.benchmark import pre_step6, step6
from integrated_terminal_pilot.benchmark.runner import run_arm
from integrated_terminal_pilot.simulator.trace import validate_trace_dir
from tests.step6_support import leakage_doc

pytestmark = pytest.mark.integration
PRIMARY = "itp_primary_balanced_qc8_v1"
SOURCE = pre_step6.PROJECT_ROOT / "experiments" / "scenarios" / "development" / pre_step6.SOURCE_RUN
needs_source = pytest.mark.skipif(not SOURCE.exists(), reason="development scenario batch not present")


def _low():
    scenario = step6._scenario_row("itp_low", 10_000_000)
    return scenario, step6._load(scenario)


@needs_source
def test_g6_05_a_and_b_arms_share_physics_policies_and_obligations():
    scenario, doc = _low()
    records = [run_arm(doc, arm_id=arm, research_profile=PRIMARY) for arm in ("A1", "A1n", "B1")]
    assert [r["status"] for r in records] == ["COMPLETED"] * 3
    assert len({r["comparison_fingerprint"] for r in records}) == 1
    assert len({r["research_profile"]["resolved_physics_fingerprint"] for r in records}) == 1
    assert {r["research_profile"]["derived_fingerprints"]["exogenous_schedule_fingerprint"] for r in records} == {
        scenario["exogenous_schedule_fingerprint"]}
    assert len({r["outbound_obligations"]["N_out"] for r in records}) == 1
    assert {(r["shared"]["crane_policy_id"], r["shared"]["yard_policy_id"]) for r in records} == {
        ("primitive_crane_greedy_v1", "yard_occupancy_balance_v1")}
    assert records[2]["step6"]["factor_labels"]["information_level"] == "integrated_current_state"


def test_g6_14_b_arm_repeats_and_full_summary_parity(tmp_path):
    from tests.unit.test_pre_step6 import _with_two_crane_vessels

    doc = _with_two_crane_vessels(leakage_doc())
    for arm in ("B1", "B2", "B2-T"):
        first = run_arm(doc, arm_id=arm, research_profile=PRIMARY)
        again = run_arm(doc, arm_id=arm, research_profile=PRIMARY, trace_mode="full", trace_dir=tmp_path / arm)
        assert first["status"] == "COMPLETED" and first["digests"]["trace_sha256"] == again["digests"]["trace_sha256"]
        if arm != "B1":
            assert first["step6"]["prediction_digests"] == again["step6"]["prediction_digests"]
        from integrated_terminal_pilot.benchmark.runner import resolve_research_profile

        assert validate_trace_dir(tmp_path / arm, resolve_research_profile(doc, PRIMARY)[0])["ok"]


def test_step6_plan_is_development_only_and_defers_heavy_rollouts():
    plan = step6.build_plan()
    assert all(10_000_000 <= s["scenario_seed"] <= 10_999_999 for s in plan["scenarios"])
    assert "F3" in plan["deferred"] and "BLOCKED_BY_COMPUTE_REVIEW" in plan["deferred"]["F3"]
    assert {i["arm_id"] for i in plan["items"] if i["stage"] == "F2"} == {"A2", "B2", "B2-T"}
    with pytest.raises(step6.Step6Error):
        step6._scenario_row("itp_low", 11_000_000)                       # validation band refused
    with pytest.raises(step6.Step6Error):
        step6._scenario_row("itp_low", 12_000_000)                       # test band refused
    assert step6.main(["--dry-run", "--research-profile", "itp_sensitivity_balanced_qc6_v1"]) == 2


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("ITP_RUN_SLOW") != "1", reason="B2 on a development scenario: ITP_RUN_SLOW=1")
@needs_source
def test_b2_and_b2t_on_a_development_scenario_share_every_prediction():
    _, doc = _low()
    b2 = run_arm(doc, arm_id="B2", research_profile=PRIMARY)
    b2t = run_arm(doc, arm_id="B2-T", research_profile=PRIMARY)
    assert b2["step6"]["budget_fingerprint"] == b2t["step6"]["budget_fingerprint"]
    first = b2["step6"]["decision_predictions"][0]["candidates"]
    assert first == b2t["step6"]["decision_predictions"][0]["candidates"]
