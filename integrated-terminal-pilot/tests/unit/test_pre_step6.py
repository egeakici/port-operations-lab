"""Pre-Step 6 protocol amendments, research profile, cargo metric and CARGO-NI rule (brief section 15).

Fast tests on hand-written fixtures and synthetic numbers. No validation/test data, no training, no
Step 6 code. Slow development-scenario checks live in tests/integration/test_pre_step6_profile.py.
"""

from __future__ import annotations

import copy
import hashlib
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml

from integrated_terminal_pilot.benchmark import cargo_ni, pre_step6, profiles, protocol_records
from integrated_terminal_pilot.benchmark.cargo import CLASSES, outbound_obligations
from integrated_terminal_pilot.benchmark.cargo_ni import ArmOutcome, ComparisonContractError
from integrated_terminal_pilot.benchmark.policies import create_berth_policy
from integrated_terminal_pilot.benchmark.runner import resolve_research_profile, run_arm
from integrated_terminal_pilot.policies import POLICY_REGISTRY, FirstFitYardPolicy, create_policy
from integrated_terminal_pilot.policies.registry import DEFAULT_YARD_POLICY_ID, PRIMARY_RESEARCH_YARD_POLICY_ID
from integrated_terminal_pilot.simulator import UnsupportedScenario
from integrated_terminal_pilot.simulator.diagnostics import derive_fleet
from integrated_terminal_pilot.simulator.trace import validate_trace_dir
from tests.step4_support import QUIET, block, build_doc, container, crane, kernel_for, physics, run, vessel
from tests.step5_support import flows_doc, overrun_doc

PROJECT = Path(__file__).resolve().parents[2]
PRIMARY = profiles.PRIMARY_RESEARCH_PROFILE


def _with_two_crane_vessels(doc):
    """Hand fixtures default to max_cranes = 1; the research profile requires the generator value 2."""
    from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints

    doc = copy.deepcopy(doc)
    for v in doc["vessels"]:
        v["max_cranes"] = 2
    return with_fingerprints(doc, generator_config_fingerprint=None)


def _homogeneous_fixture():
    return _with_two_crane_vessels(overrun_doc())     # four homogeneous cranes QC01..QC04, 1200 m quay


def _flows():
    return _with_two_crane_vessels(flows_doc())


# 1 ---------------------------------------------------------------- AM-01
def test_am01_is_recorded_approved_and_first_fit_is_preserved_as_diagnostic():
    records = protocol_records.load_control_register()
    assert records["AM-01"]["status"] == "APPROVED_IN_EFFECT" and records["AM-01"]["approval_date"] == "2026-10-13"
    assert records["P3-PY-FF"]["status"] == "SUPERSEDED" and records["P3-PY-FF"]["superseded_by"] == "AM-01"
    assert POLICY_REGISTRY["yard_occupancy_balance_v1"]["role"] == "primitive"
    assert POLICY_REGISTRY["yard_first_fit_v1"]["role"] == "diagnostic_reference"
    assert isinstance(create_policy("yard_first_fit_v1"), FirstFitYardPolicy)      # still selectable, unchanged
    assert DEFAULT_YARD_POLICY_ID == "yard_first_fit_v1"                          # historical v1 default kept
    assert PRIMARY_RESEARCH_YARD_POLICY_ID == "yard_occupancy_balance_v1"
    for name, spec in profiles.RESEARCH_PROFILES.items():
        expected = "yard_first_fit_v1" if spec["role"] == "APPROVED_HISTORICAL_V1_4QC" else "yard_occupancy_balance_v1"
        assert spec["yard_policy_id"] == expected, name
    text = (PROJECT / "docs/protocol_amendments.md").read_text(encoding="utf-8")
    assert "PROPOSED / PENDING USER APPROVAL" in text and "AM-01 APPROVED" in text and "SUPERSEDED_BY_AM-01" in text


# 2 ---------------------------------------------------------------- D15 / D17 / R5
def test_d15_d17_r5_approvals_do_not_approve_unrelated_records(config):
    records = {r["decision_id"]: r for r in config.decisions}
    s2075 = records["S2-075"]
    assert s2075["status"] == "FROZEN" and s2075["approval"]["approval_date"] == "2026-10-13"
    assert s2075["selected_value"] == {"batch_size_containers": 10, "max_load_wait_min": 240.0}
    assert set(s2075["parameter_paths"]) == {"physics_profiles.standard_v1.work"}
    for still_pending in ("S2-071", "S2-073", "S2-074", "S2-077", "S2-078", "S2-079", "S2-060", "S2-052"):
        assert records[still_pending]["status"] == "PROPOSED_PENDING_REVIEW", still_pending
    control = protocol_records.load_control_register()
    assert control["AM-03"]["value"]["decision_record"] == "S2-075"
    assert control["AM-04"]["value"]["rule"] == "R5" and control["AM-04"]["value"]["invariant"] == "INV15"
    assert not any(r["parameter_name"].startswith("R5") for r in config.decisions)   # no fake register value


def test_control_register_validator_fails_closed(tmp_path):
    data = yaml.safe_load(protocol_records.CONTROL_REGISTER_PATH.read_text(encoding="utf-8"))
    for mutate, message in ((lambda d: d["records"][1].update(status="SORT_OF_APPROVED"), "unknown status"),
                            (lambda d: d["records"].append(copy.deepcopy(d["records"][1])), "duplicate"),
                            (lambda d: d["records"][1].pop("approval_date"), "missing"),
                            (lambda d: d["records"][1].update(supersedes="AM-99"), "unknown")):
        broken = copy.deepcopy(data)
        mutate(broken)
        path = tmp_path / "register.yaml"
        path.write_text(yaml.safe_dump(broken), encoding="utf-8")
        with pytest.raises(protocol_records.ControlRegisterError, match=message):
            protocol_records.load_control_register(path)


# 3 / 4 ------------------------------------------------------------ immutable sources, derived 8-crane fleet
def test_source_configuration_is_byte_identical_to_head():
    for relative in ("configs/generator/itp_generator_v1.yaml",):
        head = subprocess.run(["git", "show", f"HEAD:integrated-terminal-pilot/{relative}"], cwd=PROJECT,
                              capture_output=True, check=True).stdout
        assert hashlib.sha256(head.replace(b"\r\n", b"\n")).hexdigest() == hashlib.sha256(
            (PROJECT / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_eight_crane_profile_derives_a_validated_distinct_fleet_on_identical_traffic():
    doc = _homogeneous_fixture()
    snapshot = copy.deepcopy(doc)
    derived, catalog, prov = resolve_research_profile(doc, PRIMARY)
    assert doc == snapshot                                                     # source untouched
    assert [c["crane_id"] for c in derived["resources"]["quay_cranes"]] == [f"QC{n:02d}" for n in range(1, 9)]
    assert len(catalog.cranes) == 8 and prov["max_cranes_per_vessel"] == 2
    assert prov["two_crane_efficiency"] == 0.92 and prov["efficiency_basis"] == "assigned"
    src, der = prov["source_fingerprints"], prov["derived_fingerprints"]
    assert der["exogenous_schedule_fingerprint"] == src["exogenous_schedule_fingerprint"]
    assert der["physical_fingerprint"] != src["physical_fingerprint"]
    assert der["resource_fingerprint"] != src["resource_fingerprint"]
    fps = {p: resolve_research_profile(doc, p)[2]["resolved_physics_fingerprint"]
           for p in ("itp_sensitivity_balanced_qc4_v1", "itp_sensitivity_balanced_qc6_v1", PRIMARY)}
    assert len(set(fps.values())) == 3                                         # 4 / 6 / 8 are different physics
    kernel = kernel_for(derived)                                               # full invariants every cycle
    assert run(kernel, yard=create_policy("yard_occupancy_balance_v1")).status == "COMPLETED"
    assert kernel.result()["audits"]["ok"]


def test_unsupported_fleets_and_profiles_fail_with_structured_errors():
    doc = _homogeneous_fixture()
    bad = copy.deepcopy(doc)
    bad["resources"]["quay_cranes"][1]["nominal_moves_per_hour"] = 25.0
    with pytest.raises(UnsupportedScenario):
        derive_fleet(bad, 8)
    with pytest.raises(profiles.ProfileSelectionError):
        profiles.research_profile("itp_primary_balanced_qc12")


# 5 (fixture level) -------------------------------------------------- shared physics across arms
def test_primary_profile_arms_share_physics_policies_and_cargo_denominator():
    doc = _flows()
    records = [run_arm(doc, arm_id=a, research_profile=PRIMARY) for a in ("A1", "A2")]
    blocked = run_arm(doc, arm_id="A3", training_seed=11, research_profile=PRIMARY)
    assert blocked["status"] == "BLOCKED"            # hand fixture workloads are outside PPO support (G16)
    for r in records + [blocked]:
        assert r["shared"]["yard_policy_id"] == "yard_occupancy_balance_v1" and r["shared"]["quay_crane_count"] == 8
    assert len({r["comparison_fingerprint"] for r in records + [blocked]}) == 1
    assert len({r["research_profile"]["resolved_physics_fingerprint"] for r in records + [blocked]}) == 1
    assert {r["outbound_obligations"]["N_out"] for r in records} == {4}
    historical = run_arm(doc, arm_id="A1")
    assert historical["comparison_fingerprint"] != records[0]["comparison_fingerprint"]
    assert "research_profile" not in historical and historical["shared"]["quay_crane_count"] == 2


# 7 ---------------------------------------------------------------- outbound obligation metric
def test_outbound_metric_counts_exports_and_transshipment_once_and_never_imports():
    doc = build_doc(vessels=[vessel("V002", 0.0, 250.0), vessel("V001", 1000.0, 250.0)],
                    containers=[container(1, "transshipment", origin="V001", dest="V002"),
                                container(2, "export", size="40_ft", dest="V002", block="B01"),
                                container(3, "import", origin="V001", pickup=3000.0),
                                container(4, "import", size="40_ft", origin="V002", pickup=3000.0)])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    metric = outbound_obligations(kernel)
    assert (metric["N_out"], metric["loaded"], metric["U_not_loaded"]) == (2, 1, 1)
    assert metric["classes"]["LOADED_DEPARTED"] == 1 and metric["classes"]["NOT_LOADED_ROLLED_OVER"] == 1
    assert metric["R_loss_rate"] == 0.5 and metric["reconciliation_ok"]
    assert metric["teu"] == {"obligations": 3.0, "not_loaded": 1.0}
    assert set(metric["by_flow"]) == {"export", "transshipment"}


def test_outbound_metric_separates_loaded_but_not_departed_and_unfinished_at_t_end():
    exports = [container(n, "export", size="20_ft" if n % 2 else "40_ft", dest="V001", block="B01")
               for n in range(1, 13)]
    doc = build_doc(vessels=[vessel("V001", 0.0, 250.0)], containers=exports,
                    blocks=[block("B01", 100.0, capacity=96.0)],
                    physics_doc=physics(**QUIET, **{"episode.max_drain_extension_min": 50.0}))
    kernel = kernel_for(doc)
    assert run(kernel).status == "TRUNCATED_DRAIN_LIMIT"
    metric = outbound_obligations(kernel)
    classes = metric["classes"]
    assert metric["N_out"] == 12 and sum(classes.values()) == 12 and set(classes) == set(CLASSES)
    assert classes["LOADED_VESSEL_AT_TERMINAL"] > 0 and classes["NOT_LOADED_VESSEL_PRESENT"] > 0
    assert classes["LOADED_DEPARTED"] == 0 and metric["loaded_but_vessel_not_departed"] == classes[
        "LOADED_VESSEL_AT_TERMINAL"]
    assert metric["U_not_loaded"] == classes["NOT_LOADED_VESSEL_PRESENT"] and metric["reconciliation_ok"]
    assert metric["cutoff_min"] == metric["T_end_min"] == 50.0


def test_outbound_metric_reports_not_applicable_without_obligations():
    doc = build_doc(vessels=[vessel("V001", 0.0, 250.0)],
                    containers=[container(1, "import", origin="V001", pickup=900.0)])
    kernel = kernel_for(doc)
    run(kernel)
    metric = outbound_obligations(kernel)
    assert metric["N_out"] == 0 and metric["R_loss_rate"] is None and metric["applicability"] == "NOT_APPLICABLE"


# 8 ---------------------------------------------------------------- comparator map
def test_comparator_map_is_exact_and_fails_closed():
    pairs = {(r["policy"], r["reference"]) for r in cargo_ni.COMPARATOR_MAP}
    assert {("A2", "A1"), ("A3", "A1"), ("B1", "A1"), ("B2", "A2"), ("B2-T", "A2"), ("B2", "B2-T"),
            ("A3-train11", "A1"), ("B3-train23", "A3-train23"), ("B3", "A3")} <= pairs
    assert cargo_ni.comparison("B2-T", "A2")["kind"] == "objective_ablation"
    for bad in (("A1", "A1"), ("A3-train11", "A2"), ("B2", "A1"), ("B3-train11", "A3-train23"), ("B1", "A2"),
                ("A3-train99", "A1")):
        with pytest.raises(ComparisonContractError):
            cargo_ni.comparison(*bad)
    with pytest.raises(ComparisonContractError):
        cargo_ni.references_for("A1")


# 9 ---------------------------------------------------------------- nested A3 + bootstrap
def _outcomes(rates_by_arm: dict[str, list[float]], n_out: int = 100) -> list[ArmOutcome]:
    out = []
    for arm, rates in rates_by_arm.items():
        for index, rate in enumerate(rates):
            out.append(ArmOutcome(f"s{index:02d}", "itp_medium", arm, n_out,
                                  None if rate is None else int(round(rate * n_out))))
    return out


def test_a3_is_averaged_within_scenario_and_resampled_over_scenarios_only():
    a1 = [0.10] * 12
    seeds = {"A3-train11": [0.10] * 12, "A3-train23": [0.13] * 12, "A3-train37": [0.10] * 12}
    result = cargo_ni.paired_differences(_outcomes({"A1": a1, **seeds}), "A3", "A1")
    assert len(result["pairs"]) == 12                    # one pair per scenario, not 36
    assert all(abs(p["d"] - 0.01) < 1e-12 for p in result["pairs"])
    missing = dict(seeds, **{"A3-train37": [None] + [0.10] * 11})
    partial = cargo_ni.paired_differences(_outcomes({"A1": a1, **missing}), "A3", "A1")
    assert len(partial["pairs"]) == 11
    assert partial["excluded"] == [{"scenario_id": "s00", "reason": "MISSING_INCOMPLETE_SEEDS"}]
    per_seed = cargo_ni.paired_differences(_outcomes({"A1": a1, **seeds}), "A3-train23", "A1")
    assert all(abs(p["d"] - 0.03) < 1e-12 for p in per_seed["pairs"])


def test_noninferiority_verdicts_bound_and_margin():
    rng = np.random.default_rng(1)
    clear = cargo_ni.noninferiority(list(rng.normal(0.0, 0.002, 30)))
    assert clear["verdict"] == "NON_INFERIOR" and clear["upper_bound"] <= 0.01 and clear["margin"] == 0.01
    noisy = cargo_ni.noninferiority([0.0, 0.04, -0.03, 0.03, -0.02, 0.02, 0.0, 0.0])
    assert noisy["verdict"] == "INCONCLUSIVE" and noisy["upper_bound"] > 0.01 >= noisy["estimate"]
    assert any("small N" in d for d in noisy["diagnostics"])
    worse = cargo_ni.noninferiority([0.05, 0.06, 0.04, 0.05, 0.07, 0.05, 0.06, 0.05, 0.04, 0.06])
    assert worse["verdict"] == "INFERIOR"
    values = np.asarray([0.0, 0.04, -0.03, 0.03, -0.02, 0.02, 0.0, 0.0])
    rng = np.random.default_rng(cargo_ni.BOOTSTRAP_SEED)
    means = values[rng.integers(0, 8, size=(10_000, 8))].mean(axis=1)
    assert noisy["upper_bound"] == pytest.approx(float(np.percentile(means, 95)))
    flat = cargo_ni.noninferiority([0.0] * 12)
    assert flat["upper_bound"] == 0.0 and any("zero variance" in d for d in flat["diagnostics"])
    strict = cargo_ni.noninferiority([0.001] * 12, margin=cargo_ni.SENSITIVITY_MARGIN)
    assert strict["verdict"] == "INFERIOR"               # the 0.00 sensitivity margin is stricter
    assert cargo_ni.turnaround_claim_label(True, noisy) == "TURNAROUND_GAIN_WITH_UNPROVEN_OR_EXCESS_CARGO_LOSS"
    assert cargo_ni.turnaround_claim_label(True, clear) == "TURNAROUND_GAIN_CARGO_NON_INFERIOR"


def test_mismatched_denominators_are_not_a_paired_case():
    outcomes = [ArmOutcome("s00", "itp_low", "A1", 100, 5), ArmOutcome("s00", "itp_low", "A2", 90, 5)]
    with pytest.raises(ComparisonContractError, match="N_out differs"):
        cargo_ni.paired_differences(outcomes, "A2", "A1")


# 10 / 11 ---------------------------------------------------------- B2 / B2-T pre-registration only
def test_b2_and_b2t_are_preregistered_and_confined_to_step6_modules():
    control = protocol_records.load_control_register()
    for record_id in ("AM-06", "AM-07", "AM-08"):
        assert control[record_id]["status"] == "APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED"
    design = (PROJECT / "docs/pre_step6_design_decisions.md").read_text(encoding="utf-8")
    for phrase in ("coordination-package", "same visible information", "turnaround only", "pivotal",
                   "B2-T vs B2", "A2 vs B2-T", "violation"):
        assert phrase in design, phrase
    # Pre-Step 6 asserted that no B2 code existed. Step 6 (owner-authorized) adds it, confined to the
    # Step 6 modules; the Step 5 A-arm registry below still refuses every B arm.
    step6_modules = {"coordination_policies.py", "coordination_view.py", "step6.py"}
    for path in (PROJECT / "src").rglob("*.py"):
        if path.name in step6_modules:
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in ("class B2", "def b2_", "class Coordinator", "def rollout_integrated"):
            assert forbidden not in text, (path.name, forbidden)
    for arm in ("B1", "B2", "B2-T", "B3"):
        with pytest.raises(KeyError):
            create_berth_policy(arm)


# 12 ---------------------------------------------------------------- no automatic profile switching
def test_automatic_primary_profile_switch_is_refused():
    profiles.assert_primary_profile_unchanged(PRIMARY)
    for other in ("itp_sensitivity_balanced_qc6_v1", "itp_v1_reference_qc4_first_fit"):
        with pytest.raises(profiles.ProfileSelectionError, match="safeguard S3"):
            profiles.assert_primary_profile_unchanged(other, reason="PPO out of distribution")
    assert pre_step6.main(["--dry-run", "--research-profile", "itp_sensitivity_balanced_qc4_v1"]) == 2


# 13 ---------------------------------------------------------------- determinism, parity, guards
def test_primary_profile_repeat_and_full_summary_digest_parity(tmp_path):
    doc = _flows()
    first = run_arm(doc, arm_id="A2", research_profile=PRIMARY)
    again = run_arm(doc, arm_id="A2", research_profile=PRIMARY)
    full = run_arm(doc, arm_id="A2", research_profile=PRIMARY, trace_mode="full", trace_dir=tmp_path / "t")
    assert first["digests"]["trace_sha256"] == again["digests"]["trace_sha256"] == full["digests"]["trace_sha256"]
    derived, _, _ = resolve_research_profile(doc, PRIMARY)
    assert validate_trace_dir(tmp_path / "t", derived)["ok"]


def test_plan_is_development_only_and_inputs_are_verified(tmp_path):
    plan = pre_step6.build_plan()
    assert all(10_000_000 <= s["scenario_seed"] <= 10_999_999 for s in plan["scenarios"])
    assert plan["counts"] == {"primary": 60, "sensitivity": 40, "repeat": 4}
    assert plan["primary_profile"] == PRIMARY and plan["label"] == "DEVELOPMENT_CHARACTERIZATION"
    scenario = dict(plan["scenarios"][0])
    with pytest.raises(pre_step6.PreStep6Error, match="SHA-256"):
        pre_step6._load_doc(dict(scenario, file_sha256="0" * 64))
    with pytest.raises(pre_step6.PreStep6Error, match="missing"):
        pre_step6._load_doc(dict(scenario, file="experiments/scenarios/development/none.scenario.json"))
    assert not any("validation" in p.name or "test" in p.name for p in (PROJECT / "experiments" / "scenarios").glob("*"))


# 16 ---------------------------------------------------------------- lock semantics
def test_lock_stays_blocked_with_pending_records_or_without_the_step7_lock(tmp_path, monkeypatch):
    state = profiles.approval_state()
    assert state["scientific_protocol_lock"] == "BLOCKED" and state["validation_authorized"] is False
    assert state["proposed_pending_review"] == 28 and not state["control_record_gaps"]
    assert not profiles.FORMAL_LOCK_PATH.exists()
    register = yaml.safe_load(profiles.DECISIONS_PATH.read_text(encoding="utf-8"))
    for record in register["records"]:
        record["status"] = "FROZEN"
    path = tmp_path / "decisions.yaml"
    path.write_text(yaml.safe_dump(register), encoding="utf-8")
    monkeypatch.setattr(profiles, "DECISIONS_PATH", path)
    all_approved = profiles.approval_state()
    assert all_approved["lock_review_readiness"] == "READY_FOR_LOCK_REVIEW"
    assert all_approved["scientific_protocol_lock"] == "BLOCKED"        # Step 7 lock absent
    assert all_approved["validation_authorized"] is False
    monkeypatch.setattr(profiles, "load_control_register", lambda: {})
    assert profiles.approval_state()["lock_review_readiness"] == "NOT_READY"
