"""Step 4 closure tests (closure brief §10, items 1-15; 16-17 are the Step 4 hand traces and the
degenerate-equivalence gate, which run unchanged)."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from integrated_terminal_pilot.policies import (
    DEFAULT_YARD_POLICY_ID, POLICY_REGISTRY, FirstFitYardPolicy, OccupancyBalancingYardPolicy, create_policy,
)
from integrated_terminal_pilot.simulator import UnsupportedScenario, run_episode
from integrated_terminal_pilot.simulator import closure
from integrated_terminal_pilot.simulator import invariants as inv
from integrated_terminal_pilot.simulator.diagnostics import (
    AM01_PROPOSED_YARD_POLICY_ID, REFERENCE_YARD_POLICY_ID, DiagnosticCondition, build_condition_catalog,
    derive_fleet, optimistic_crane_bound,
)
from integrated_terminal_pilot.simulator.drivers import default_policies
from integrated_terminal_pilot.simulator.kernel import TerminalKernel
from integrated_terminal_pilot.simulator.trace import (
    CANONICAL_FILES, SUMMARY_WRITTEN_FILES, canonical_files, digest_files, emit_trace, validate_trace_dir,
    write_trace,
)
from tests.step4_support import (
    QUIET, block, build_doc, cid, container, crane, kernel_for, physics, policies, run, vessel,
)

PROJECT = Path(__file__).resolve().parents[2]


def _decomposition(kernel):
    return kernel.result(audits=False)["time_decomposition"]


# 1 ------------------------------------------------------------------ D15 / D16 labels
def test_d15_is_batch_size_and_d16_is_sequencing_everywhere():
    offending = []
    for path in list((PROJECT / "docs").glob("*.md")) + list((PROJECT / "src").rglob("*.py")) \
            + list((PROJECT / "tests").rglob("*.py")):
        if path.name == "test_step4_closure.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "D16" in line and re.search(r"batch[ _]size|batch sizing|batches of at most", line) \
                    and "D15" not in line:
                offending.append(f"{path.name}:{number}")
    assert offending == []
    catalog_src = (PROJECT / "src/integrated_terminal_pilot/simulator/catalog.py").read_text(encoding="utf-8")
    assert "batch_size_containers must be >= 1 (D15)" in catalog_src
    assert TerminalKernel._dispatch_crane.__doc__.startswith("D16: discharge before load")


# 2 ------------------------------------------------------------------ R5 release admission
def test_r5_one_release_batch_per_block_with_fifo_and_reservations_intact():
    # Three imports of two groups (20 ft and 40 ft) all due at t = 10 in the same block.
    imports = [container(1, "import", block="B01", pickup=10.0),
               container(2, "import", size="40_ft", block="B01", pickup=10.0),
               container(3, "import", block="B01", pickup=10.0)]
    doc = build_doc(vessels=[vessel("V001", 500.0, 200.0)],
                    containers=imports + [container(9, "import", origin="V001", pickup=900.0)])
    kernel = kernel_for(doc)  # invariant_mode="full": INV15 release admission checked every cycle
    run(kernel, until_min=11.0)
    assert [w.container_indices for w in kernel.state.work_orders.values() if w.operation_type == "GATE_OUT"] \
        == [(0, 2)]  # head group {CNT-1, CNT-3} first; CNT-2 waits IN_YARD, still occupying its TEU
    assert kernel.state.c_status[1] == "IN_YARD" and kernel.state.blocks["B01"].occupied_teu == 2.0
    run(kernel)
    starts = {r[4]: r[1] for r in kernel.state.ledger if r[2] == "RELEASE_STARTED"}
    ends = {r[4]: r[1] for r in kernel.state.ledger if r[2] == "RELEASE_COMPLETED"}
    # 2 moves at 60 moves/h: 10 -> 12; then the 40 ft container 12 -> 13. No overlap.
    assert (starts[cid(1)], ends[cid(1)], starts[cid(2)], ends[cid(2)]) == (10.0, 12.0, 12.0, 13.0)
    inv.check(kernel, full=True)


# 3 ------------------------------------------------------------------ D17 rollover vs fulfilment
def test_d17_rollover_departs_but_is_not_cargo_fulfilled():
    doc = build_doc(vessels=[vessel("V002", 0.0, 200.0), vessel("V001", 1000.0, 200.0)],
                    containers=[container(1, "transshipment", origin="V001", dest="V002")])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    result = kernel.result()
    compliance = result["service_compliance"]
    assert compliance["terminal_status"] == "COMPLETED"
    assert compliance["vessels_departed"] == 2 and compliance["vessels_cargo_fulfilled"] == 1
    assert compliance["rolled_over_containers"] == 1 and compliance["rolled_over_moves"] == 1
    assert compliance["cargo_fulfillment_complete"] is False
    assert compliance["cargo_completion_ratio"] == pytest.approx(1 / 2)  # V001's discharge done, load not
    assert [r[2] for r in kernel.state.ledger if r[3] == "EXCEPTION"] == ["ROLLED_OVER"]
    row = next(v for v in result["time_decomposition"]["vessels"] if v["vessel_id"] == "V002")
    assert row["departed"] and not row["cargo_fulfilled"]
    assert row["handling_cause_min"]["CARGO_UNAVAILABLE"] == pytest.approx(240.0)


# 4-5 ---------------------------------------------------------------- AM-01 (approved 2026-10-13)
def test_am01_approval_keeps_the_historical_closure_reference_reproducible():
    # The Step 4 closure staged AM-01 as PROPOSED; the owner approved it on 2026-10-13 (append-only
    # record). The closure campaign's reference condition and the v1 fixture default stay first fit so
    # that historical runs reproduce; the primary research P_y is selected by research profile.
    assert REFERENCE_YARD_POLICY_ID == DEFAULT_YARD_POLICY_ID == "yard_first_fit_v1"
    assert isinstance(default_policies()["yard_policy"], FirstFitYardPolicy)
    assert POLICY_REGISTRY["yard_occupancy_balance_v1"]["role"] == "primitive"
    assert POLICY_REGISTRY["yard_first_fit_v1"]["role"] == "diagnostic_reference"
    text = (PROJECT / "docs/protocol_amendments.md").read_text(encoding="utf-8")
    assert "PROPOSED / PENDING USER APPROVAL" in text            # the 2026-10-12 record is preserved
    assert "AM-01 APPROVED" in text and "SUPERSEDED_BY_AM-01" in text
    assert AM01_PROPOSED_YARD_POLICY_ID == "yard_occupancy_balance_v1"


def test_both_yard_policies_are_selectable_by_registry_id():
    assert isinstance(create_policy("yard_occupancy_balance_v1"), OccupancyBalancingYardPolicy)
    assert isinstance(create_policy("yard_first_fit_v1"), FirstFitYardPolicy)
    assert DiagnosticCondition("yard_occupancy_balance_v1").condition_id == "balanced_qc4_assigned"
    assert DiagnosticCondition().is_reference and not DiagnosticCondition("yard_occupancy_balance_v1").is_reference


# 6 ------------------------------------------------------------------ yard-local isolation
def _yard_doc(*, v2_length=200.0, pickup=900.0, v3_arrival=2000.0):
    return build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 0.0, v2_length),
                              vessel("V003", v3_arrival, 200.0)],
                     containers=[container(1, "import", origin="V001", pickup=pickup),
                                 container(2, "import", origin="V002", pickup=pickup + 1),
                                 container(3, "import", origin="V003", pickup=v3_arrival + 900),
                                 container(8, "import", block="B01", pickup=pickup + 2)],
                     blocks=[block("B01", 100.0), block("B02", 400.0), block("B03", 700.0)],
                     cranes=[crane("QC01"), crane("QC02")])


def _first_yard_observation(doc):
    kernel = kernel_for(doc)
    p = policies()
    while True:
        request = kernel.advance()
        if request.kind == "YARD":
            return kernel.yard_observation()
        if request.kind == "BERTH":
            kernel.apply_berth_action(p["berth_policy"].decide(kernel.berth_view()))
        else:
            kernel.apply_crane_action(p["crane_policy"].decide(kernel.crane_observation()))


def test_balanced_yard_decision_uses_only_yard_local_observation():
    policy = OccupancyBalancingYardPolicy()
    base = _first_yard_observation(_yard_doc())
    # Berth position (V002's length moves nothing here but its own placement), hidden future truth.
    for doc in (_yard_doc(v2_length=300.0), _yard_doc(pickup=1200.0), _yard_doc(v3_arrival=2500.0)):
        observation = _first_yard_observation(doc)
        assert observation == base
        assert policy.decide(observation) == policy.decide(base)
    # Transport coordinates and handling rates are observation fields the policy must ignore.
    moved = dataclasses.replace(base, blocks=tuple(dataclasses.replace(
        b, transfer_point_x_m=(b.transfer_point_x_m or 0.0) + 500.0, handling_capacity_moves_per_hour=5.0)
        for b in base.blocks))
    assert policy.decide(moved).block_id == policy.decide(base).block_id
    assert policy.decide(base).block_id == "B02"  # B01 already holds 1 TEU; ties to lower id among empty


# 7-8 ---------------------------------------------------------------- trace modes
def test_full_and_summary_modes_have_identical_digests_and_physics(tmp_path, golden_doc):
    full_kernel, summary_kernel = TerminalKernel.from_scenario(golden_doc), TerminalKernel.from_scenario(golden_doc)
    run(full_kernel), run(summary_kernel)
    full = write_trace(full_kernel, tmp_path / "full", run_id="f", mode="full")
    summary = write_trace(summary_kernel, tmp_path / "summary", run_id="s", mode="summary")
    assert full["files"] == summary["files"] and full["trace_sha256"] == summary["trace_sha256"]
    assert full["files"] == digest_files(canonical_files(full_kernel))["files"]
    assert full_kernel.result()["kpi"] == summary_kernel.result()["kpi"]
    assert sorted(p.name for p in (tmp_path / "summary").iterdir()) == sorted(
        list(SUMMARY_WRITTEN_FILES) + ["manifest.json", "engineering.json"])
    assert summary["files_written"] == list(SUMMARY_WRITTEN_FILES)
    assert set(full["files_written"]) == set(CANONICAL_FILES)
    report = validate_trace_dir(tmp_path / "summary", golden_doc)
    assert report["ok"] is False and "digest-verifiable" in report["issues"][0]
    assert validate_trace_dir(tmp_path / "full", golden_doc)["ok"]
    with pytest.raises(FileExistsError):  # never overwrite a run directory
        write_trace(summary_kernel, tmp_path / "summary", run_id="s", mode="summary")
    assert emit_trace(summary_kernel, None, mode="summary")["written"] == []


# 9 ------------------------------------------------------------------ efficiency basis
@pytest.mark.parametrize("basis, rate", [("assigned", 27.6), ("working", 30.0)])
def test_assigned_versus_working_efficiency_basis(basis, rate):
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0, max_cranes=2)],
                    containers=[container(n, "import", origin="V001", pickup=5000.0) for n in (1, 2, 3)],
                    cranes=[crane("QC01"), crane("QC02")])
    catalog, _ = build_condition_catalog(doc, DiagnosticCondition("yard_first_fit_v1", 2, basis))
    digests = []
    for _ in range(2):
        kernel = TerminalKernel.from_catalog(catalog, invariant_mode="full")
        run_episode(kernel, **policies())
        assert kernel.state.vessels["V001"].handling_end_time_min == pytest.approx(30.0 + 60.0 * 3 / rate)
        digests.append(emit_trace(kernel, None)["trace_sha256"])
    assert digests[0] == digests[1]


# 10-11 -------------------------------------------------------------- fleet overrides
def test_fleet_override_preserves_source_and_fingerprints_distinctly():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0, max_cranes=2), vessel("V002", 0.0, 200.0, max_cranes=2)],
                    containers=[container(n, "import", origin=v, pickup=5000.0)
                                for n, v in ((1, "V001"), (2, "V001"), (3, "V002"), (4, "V002"))],
                    cranes=[crane("QC01"), crane("QC02")])
    before = json.dumps(doc, sort_keys=True)
    resolved = {}
    for count in (2, 4, 6):
        for basis in ("assigned", "working"):
            catalog, fp = build_condition_catalog(doc, DiagnosticCondition("yard_first_fit_v1", count, basis))
            assert [c.crane_id for c in catalog.cranes] == [f"QC{i:02d}" for i in range(1, count + 1)]
            assert fp["base_scenario_fingerprint"] == doc["fingerprints"]["scenario_fingerprint"]
            assert fp["derived_exogenous_schedule_fingerprint"] == doc["fingerprints"]["exogenous_schedule_fingerprint"]
            resolved[(count, basis)] = fp["resolved_physics_fingerprint"]
            kernel = TerminalKernel.from_catalog(catalog, invariant_mode="full")
            assert run_episode(kernel, **policies()).status == "COMPLETED"  # INV02/INV03 checked every cycle
    assert json.dumps(doc, sort_keys=True) == before
    assert len(set(resolved.values())) == len(resolved)


def test_fleet_override_refuses_a_non_homogeneous_fleet():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=900.0)],
                    cranes=[crane("QC01", 30.0), crane("QC02", 25.0)])
    with pytest.raises(UnsupportedScenario):
        derive_fleet(doc, 4)
    assert optimistic_crane_bound(4) == pytest.approx(110.4)
    assert optimistic_crane_bound(6) == pytest.approx(165.6)
    assert optimistic_crane_bound(8) == pytest.approx(220.8)
    assert optimistic_crane_bound(5) == pytest.approx(110.4 + 30.0)


# 12-13 -------------------------------------------------------------- phase reconciliation, causes
def _assert_reconciled(kernel):
    decomposition = _decomposition(kernel)
    assert decomposition["max_phase_reconciliation_error_min"] < 1e-6
    assert decomposition["handling_cause_reconciliation_error_min"] < 1e-6
    for row in decomposition["vessels"]:
        if row["arrived"]:
            parts = row["berth_wait_min"] + row["berthing_prep_min"] + row["handling_min"] + row["departure_prep_min"]
            assert parts == pytest.approx(row["observed_turnaround_min"], abs=1e-6)
            assert sum(row["handling_cause_min"].values()) == pytest.approx(row["handling_min"], abs=1e-6)
    return decomposition


def test_phase_times_reconcile_for_censored_waiting_and_partly_handled_vessels():
    doc = build_doc(quay=600.0, vessels=[vessel("V001", 0.0, 400.0), vessel("V002", 5.0, 400.0)],
                    containers=[container(n, "import", origin="V001", pickup=9000.0) for n in range(1, 11)]
                    + [container(20, "import", origin="V002", pickup=9000.0)],
                    physics_doc=physics(**QUIET, **{"episode.max_drain_extension_min": 40.0}))
    kernel = kernel_for(doc)
    assert run(kernel).status == "TRUNCATED_DRAIN_LIMIT"
    decomposition = _assert_reconciled(kernel)
    rows = {r["vessel_id"]: r for r in decomposition["vessels"]}
    assert rows["V001"]["observed_turnaround_kind"] == "restricted_censored"
    assert rows["V001"]["observed_turnaround_min"] == pytest.approx(45.0)  # T_end = 5 + 40
    assert rows["V001"]["handling_min"] == pytest.approx(15.0)  # elapsed part only, nothing extrapolated
    assert rows["V002"]["berth_wait_min"] == pytest.approx(40.0) and rows["V002"]["handling_min"] == 0.0
    compliance = kernel.result(audits=False)["service_compliance"]
    assert compliance["completed_only_mean_turnaround_min"] is None and compliance["vessels_departed"] == 0


def test_handling_causes_come_from_runtime_reasons():
    # Yard full 30..100 (YARD_STORAGE_FULL), then discharge at crane rate.
    background = [container(n, "import", block="B01", pickup=(100.0 if n == 11 else 9000.0)) for n in (11, 12, 13)]
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=background + [container(1, "import", size="40_ft", origin="V001", pickup=9000.0)],
                    blocks=[block("B01", 100.0, capacity=4.0)])
    kernel = kernel_for(doc)
    run(kernel)
    causes = _assert_reconciled(kernel)["vessels"][0]["handling_cause_min"]
    assert causes["YARD_STORAGE_FULL"] == pytest.approx(70.0)
    assert causes["AT_CRANE_RATE"] == pytest.approx(2.0)
    assert causes["UNATTRIBUTED"] == 0.0
    # Yard handling binds (case J of Step 4): 20 moves/h block, crane 30.
    p = physics(**{"transport.enabled": False, "yard.congestion_g_min": 1.0})
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=9000.0)],
                    blocks=[block("B01", 100.0, handling=20.0)], physics_doc=p)
    kernel = kernel_for(doc)
    run(kernel)
    causes = _assert_reconciled(kernel)["vessels"][0]["handling_cause_min"]
    assert causes["YARD_HANDLING_CONSTRAINED"] == pytest.approx(3.0)
    # No crane at all during handling: CRANE_SHORTAGE (one crane busy with another vessel).
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=900.0),
                                container(2, "import", origin="V002", pickup=900.0)])
    kernel = kernel_for(doc)
    run(kernel)
    rows = {r["vessel_id"]: r for r in _assert_reconciled(kernel)["vessels"]}
    assert rows["V002"]["handling_cause_min"]["CRANE_SHORTAGE"] == pytest.approx(2.0)


# 14-15 -------------------------------------------------------------- repeatability, plan, resume
def test_plan_hash_is_stable_and_counts_380_unique_runs():
    first, second = closure.build_plan(), closure.build_plan()
    assert closure.plan_hash(first) == closure.plan_hash(second)
    assert first["unique_runs"] == 380 == len(closure.planned_runs(first))
    per_condition = {c["condition_id"]: sum(1 for s in first["scenarios"] if s["family"] in c["families"])
                     for c in first["conditions"]}
    assert per_condition == {"first_fit_qc4_assigned": 80, "balanced_qc4_assigned": 80,
                             "balanced_qc6_assigned": 80, "balanced_qc8_assigned": 80,
                             "balanced_qc4_working": 60}
    assert all(s["scenario_id"].endswith(str(s["seed"])) and 10_000_000 <= s["seed"] < 10_000_030
               for s in first["scenarios"])


def test_resume_rejects_incompatible_outputs_and_never_overwrites(tmp_path):
    plan_dir, plan, digest = closure.ensure_plan(tmp_path)
    condition_row, scenario_row = closure.planned_runs(plan)[0]
    path = plan_dir / "runs" / condition_row["condition_id"] / f"{scenario_row['scenario_id']}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"plan_sha256": "0" * 64, "condition": condition_row}), encoding="utf-8")
    with pytest.raises(closure.ClosureError, match="use --resume"):
        closure.run_campaign(root=tmp_path, limit_runs=0)
    with pytest.raises(closure.ClosureError, match="incompatible"):
        closure.run_campaign(root=tmp_path, resume=True, limit_runs=0)
    assert closure.run_campaign(root=tmp_path, dry_run=True)["completed"] == 1
    assert closure.ensure_plan(tmp_path)[2] == digest  # an identical plan is reused, not rewritten


@pytest.mark.integration
def test_repeated_condition_runs_are_identical():
    plan = closure.build_plan()
    condition_row, scenario_row = next((c, s) for c, s in closure.planned_runs(plan)
                                       if c["condition_id"] == "balanced_qc4_assigned"
                                       and s["scenario_id"] == "itp_low_development_seed10000000")
    first = closure.execute_run(condition_row, scenario_row, "test")
    second = closure.execute_run(condition_row, scenario_row, "test")
    assert first["digests"] == second["digests"]
    for key in ("service_compliance", "kpi", "time_decomposition", "yard", "status"):
        assert first[key] == second[key]
    assert first["audits"]["ok"]
