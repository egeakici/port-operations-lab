"""Step 5 integration tests (brief section 16, items 3, 8-13): shared kernel, fairness, compliance, CLI.

The full PASS-EXACT gate (80 degenerate development scenarios x A1/A2/A3-11/23/37) is the opt-in
``slow`` test (``ITP_RUN_SLOW=1``) and ``scripts/run_step5_independent_benchmark.py --exact-gate``.
"""

from __future__ import annotations

import json
import os

import pytest

from integrated_terminal_pilot.benchmark import development
from integrated_terminal_pilot.benchmark.exact_gate import exact_gate
from integrated_terminal_pilot.benchmark.runner import run_arm
from integrated_terminal_pilot.scenarios import generate_scenario
from integrated_terminal_pilot.simulator.drivers import FcfsBerthIntegrationDriver, default_policies, run_episode
from integrated_terminal_pilot.simulator.kernel import TerminalKernel
from integrated_terminal_pilot.simulator.trace import canonical_files, digest_files, validate_trace_dir
from tests.step4_support import QUIET, build_doc, container, physics, vessel
from tests.step5_support import flows_doc, overrun_doc

pytestmark = pytest.mark.integration
ARMS = [("A1", None), ("A2", None), ("A3", 11), ("A3", 23), ("A3", 37)]


# 3 ---------------------------------------------------------------- A1 = Step 4 FCFS fixture (full traces)
def _canonical(doc, berth_policy):
    kernel = TerminalKernel.from_scenario(doc)
    policies = default_policies() | {"berth_policy": berth_policy}
    outcome = run_episode(kernel, **policies)
    return outcome, canonical_files(kernel, rejections=outcome.rejections)


@pytest.mark.parametrize("which", ["low", "overrun"])
def test_a1_reproduces_the_step4_fcfs_fixture_trace_exactly(low_doc, which):
    from integrated_terminal_pilot.benchmark.policies import OnlineFcfsBerthPolicy

    doc = low_doc if which == "low" else overrun_doc()
    a1_outcome, a1 = _canonical(doc, OnlineFcfsBerthPolicy())
    fx_outcome, fixture = _canonical(doc, FcfsBerthIntegrationDriver())
    assert a1_outcome.status == fx_outcome.status
    # The only permitted difference is the recorded policy id in decision records.
    renamed = {name: text.replace(OnlineFcfsBerthPolicy.policy_id, FcfsBerthIntegrationDriver.policy_id)
               for name, text in a1.items()}
    assert digest_files(renamed) == digest_files(fixture)
    for name in ("events.jsonl", "ledger.jsonl", "blocking.jsonl"):
        assert a1[name] == fixture[name], name


# PASS-EXACT sample (one degenerate development scenario per family, every arm)
@pytest.mark.parametrize("family", ["itp_low", "itp_medium", "itp_heavy", "itp_yard_bottleneck"])
def test_pass_exact_first_seed(config, family):
    doc = generate_scenario(config, family, "development", 10_000_000, "degenerate_equivalence_v1")
    for arm, seed in ARMS:
        report = exact_gate(doc, arm, seed)
        assert report["pass"], (arm, seed, report)
        assert report["decisions"] > 0


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("ITP_RUN_SLOW") != "1", reason="full PASS-EXACT gate: set ITP_RUN_SLOW=1 "
                    "(or run scripts/run_step5_independent_benchmark.py --exact-gate)")
@pytest.mark.parametrize("family,count", [("itp_medium", 30), ("itp_heavy", 30), ("itp_low", 10),
                                          ("itp_yard_bottleneck", 10)])
def test_pass_exact_full_gate(config, family, count):
    for seed in range(10_000_000, 10_000_000 + count):
        doc = generate_scenario(config, family, "development", seed, "degenerate_equivalence_v1")
        for arm, training_seed in ARMS:
            assert exact_gate(doc, arm, training_seed)["pass"], (family, seed, arm, training_seed)


# 8 / 9 ------------------------------------------------------------ fairness and metadata
def test_only_the_berth_policy_differs_between_arms(low_doc):
    records = [run_arm(low_doc, arm_id=arm, training_seed=seed) for arm, seed in ARMS]
    assert [r["status"] for r in records] == ["COMPLETED"] * 5
    assert len({r["comparison_fingerprint"] for r in records}) == 1
    assert len({json.dumps(r["shared"], sort_keys=True) for r in records}) == 1
    assert len({json.dumps(r["scenario"], sort_keys=True) for r in records}) == 1
    assert records[0]["shared"]["yard_policy_id"] == "yard_first_fit_v1"
    assert records[0]["shared"]["crane_policy_id"] == "primitive_crane_greedy_v1"
    assert records[0]["shared"]["quay_crane_count"] == 4
    a3 = records[2]
    assert a3["arm"] == {"arm_id": "A3", "arm_label": "A3-train11", "ppo_training_seed": 11}
    assert a3["scenario"]["scenario_seed"] == 10_000_000 and a3["policy"]["checkpoint"]["training_seed"] == 11
    assert a3["engineering"]["checkpoint_load_seconds_excluded"] is not None
    assert {r["policy"]["policy_id"] for r in records[2:]} == {
        f"a3_p03_dynamic_maskable_ppo_v1_medium_heavy_train_seed{s}" for s in (11, 23, 37)}
    balanced = run_arm(low_doc, arm_id="A1", yard_profile_name="am01_balanced_diagnostic")
    assert balanced["shared"]["yard_profile_role"] == "development_diagnostic"
    assert balanced["comparison_fingerprint"] != records[0]["comparison_fingerprint"]


# 10 --------------------------------------------------------------- departure vs cargo fulfillment, censoring
@pytest.mark.parametrize("arm,seed", [("A1", None), ("A2", None)])
def test_rolled_over_vessel_departs_but_is_not_cargo_fulfilled(arm, seed):
    doc = build_doc(vessels=[vessel("V002", 0.0, 250.0), vessel("V001", 1000.0, 250.0)],
                    containers=[container(1, "transshipment", origin="V001", dest="V002")])
    record = run_arm(doc, arm_id=arm, training_seed=seed)
    sc = record["service_compliance"]
    assert record["status"] == "COMPLETED"
    assert (sc["vessels_departed"], sc["vessels_cargo_fulfilled"], sc["rolled_over_containers"]) == (2, 1, 1)
    assert sc["cargo_fulfillment_complete"] is False
    row = next(v for v in record["vessels"] if v["vessel_id"] == "V002")
    assert row["departed"] and not row["cargo_fulfilled"]


def test_censored_vessels_stay_in_every_denominator():
    doc = build_doc(vessels=[vessel("V001", 0.0, 250.0)],
                    containers=[container(n, "import", origin="V001", pickup=9000.0) for n in range(1, 11)],
                    physics_doc=physics(**QUIET, **{"episode.max_drain_extension_min": 40.0}))
    record = run_arm(doc, arm_id="A2")
    sc = record["service_compliance"]
    assert record["status"] == "TRUNCATED_DRAIN_LIMIT"
    assert sc["vessels_total"] == 1 and sc["vessels_departed"] == 0 and sc["completed_only_vessels"] == 0
    assert record["kpi"]["total_turnaround_min"] == 40.0          # censored at T_end, never dropped
    assert sc["unfinished_ship_moves_at_stop"] == 10


# 11 --------------------------------------------------------------- import/export/transshipment reconciliation
def test_a3_is_blocked_not_run_outside_exogenous_training_support():
    # Hand fixtures carry 1-50 moves per vessel, below the [250, 900] training support (G16).
    for seed in (11, 23, 37):
        record = run_arm(flows_doc(), arm_id="A3", training_seed=seed)
        assert record["status"] == "BLOCKED" and "service_compliance" not in record
        assert any("workload outside" in reason for reason in record["blocked_reasons"])
    assert record["comparison_fingerprint"] == run_arm(flows_doc(), arm_id="A1")["comparison_fingerprint"]


@pytest.mark.parametrize("arm,seed", [("A1", None), ("A2", None)])
def test_flows_fixture_reconciles_every_container_and_teu(arm, seed):
    record = run_arm(flows_doc(), arm_id=arm, training_seed=seed)
    assert record["status"] == "COMPLETED" and record["audits"]["ok"]
    assert record["per_vessel_move_reconciliation_ok"]
    assert sum(record["container_status_at_stop"].values()) == 7
    assert record["container_status_at_stop"] == {"DEPARTED_BY_VESSEL": 4, "RELEASED_TO_LANDSIDE": 3}
    kpi = record["kpi"]
    assert (kpi["container_throughput"], kpi["teu_throughput"], kpi["crane_moves_completed"]) == (7, 10.0, 9)
    assert record["service_compliance"]["vessels_cargo_fulfilled"] == 2


# 12 --------------------------------------------------------------- determinism, digest parity, timing fields
def test_repeat_runs_and_full_summary_digest_parity(tmp_path):
    first = run_arm(overrun_doc(), arm_id="A2")
    again = run_arm(overrun_doc(), arm_id="A2")
    full = run_arm(overrun_doc(), arm_id="A2", trace_mode="full", trace_dir=tmp_path / "trace")
    assert first["digests"]["trace_sha256"] == again["digests"]["trace_sha256"] == full["digests"]["trace_sha256"]
    assert validate_trace_dir(tmp_path / "trace", overrun_doc())["ok"]
    seconds = first["decisions"]["seconds"]
    assert {"view_build", "adapter", "policy", "apply", "encode", "rollout_runtime"} <= set(seconds)
    assert first["decisions"]["rollout_root_evaluations"]["n"] == first["decisions"]["berth_decisions"] == 5
    assert first["decisions"]["forecast_epoch_modes"] == {"NO_OCCUPANCY": 1, "EXACT": 1, "FORECAST": 3}


def test_cli_dry_run_smoke_manifest_resume_and_report(tmp_path, monkeypatch, capsys):
    if not (development.PROJECT_ROOT / "experiments" / "scenarios" / "development" / development.SOURCE_RUN).exists():
        pytest.skip("development scenario batch not present")
    monkeypatch.setattr(development, "STEP5_ROOT", tmp_path)
    assert development.main(["--dry-run", "--policy", "A1"]) == 0
    assert list(tmp_path.iterdir()) == []                           # dry run writes nothing
    args = ["--smoke", "--policy", "A1", "--max-runs", "1", "--run-id", "t1"]
    assert development.main(args) == 0
    manifest = json.loads((tmp_path / "t1" / "manifest.json").read_text(encoding="utf-8"))
    for key, value in development.FLAGS.items():
        assert manifest[key] == value
    assert manifest["scientific_protocol_lock"] == "BLOCKED" and manifest["planned_runs"] == 1
    runs = list((tmp_path / "t1" / "runs").rglob("*.json"))
    assert len(runs) == 1
    record = json.loads(runs[0].read_text(encoding="utf-8"))
    assert record["validation_executed"] is False and record["arm"]["arm_id"] == "A1"
    assert record["scenario"]["split"] == "development"
    assert development.main(args) == 2                               # no overwrite
    capsys.readouterr()
    assert development.main(args + ["--resume"]) == 0
    assert '"executed": 0' in capsys.readouterr().out
    assert development.main(["--report", "--run-id", "t1"]) == 0
    assert list((tmp_path / "t1" / "reports").glob("report_*.json"))
