"""Step 4 kernel on generated Step 2 development scenarios (standard physics, P_c / P_y primitives).

These runs establish physical correctness and conservation on realistic scenario sizes
(10-17 thousand individual containers). They are engineering checks, not experimental
results: no arm is compared and no validation or test split is touched.
"""

from __future__ import annotations

import time

import pytest

from integrated_terminal_pilot.simulator import ScenarioCatalog, TerminalKernel, default_policies, run_episode
from integrated_terminal_pilot.simulator.audit import project01_snapshot_check
from integrated_terminal_pilot.simulator.invariants import shared_mutable_objects
from integrated_terminal_pilot.simulator.ledger import ledger_sha256

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def low_run(low_doc):
    kernel = TerminalKernel.from_scenario(low_doc, invariant_mode="cheap", full_check_interval=2000)
    outcome = run_episode(kernel, **default_policies())
    return kernel, outcome, kernel.result()


def test_low_family_episode_completes_with_clean_audits(low_run, low_doc):
    kernel, outcome, result = low_run
    assert outcome.status == "COMPLETED" and not outcome.rejections
    audits = result["audits"]
    assert audits["ok"], audits
    replay = audits["ledger_replay"]
    assert replay["crane_moves"] == sum(v["workload_moves"] for v in low_doc["vessels"])
    assert replay["container_throughput"] + result["kpi"]["rolled_over_containers"] <= len(low_doc["containers"])
    # Container count, TEU and moves stay distinct quantities.
    kpi = result["kpi"]
    assert kpi["teu_throughput"] > kpi["container_throughput"] and kpi["unfinished_workload_moves"] == 0
    for row in result["vessels"]:
        assert row["realized_berth_occupancy_min"] >= row["nominal_service_time_min"] - 1e-9
        assert row["service_explanation"]


def test_heavy_family_truncation_is_reported_and_censored(heavy_doc):
    kernel = TerminalKernel.from_scenario(heavy_doc, invariant_mode="cheap")
    outcome = run_episode(kernel, **default_policies())
    result = kernel.result()
    assert outcome.status in ("COMPLETED", "TRUNCATED_DRAIN_LIMIT")
    assert result["audits"]["ok"], result["audits"]
    t_end = kernel.catalog.drain_limit_min
    assert result["T_end_min"] == t_end
    for row in result["vessels"]:  # every vessel included; unfinished ones censored at T_end
        expected = (min(row["actual_departure_time_min"], t_end) if row["actual_departure_time_min"] is not None
                    else t_end) - row["arrival_time_min"]
        assert row["turnaround_min_censored"] == pytest.approx(expected)
    if outcome.status == "TRUNCATED_DRAIN_LIMIT":
        assert result["status_details"]["unresolved_vessels"]


def test_project01_projection_at_checkpoints(medium_doc):
    kernel = TerminalKernel.from_scenario(medium_doc, invariant_mode="cheap")
    policies = default_policies()
    for checkpoint in (0.0, 500.0, 1500.0, 3000.0):
        run_episode(kernel, **policies, until_min=checkpoint)
        check = project01_snapshot_check(kernel)
        assert check["ok"], (checkpoint, check)


def test_determinism_and_mid_episode_clone_on_a_generated_scenario(low_doc):
    catalog = ScenarioCatalog.from_document(low_doc, validate=False)
    first = TerminalKernel.from_catalog(catalog)
    run_episode(first, **default_policies(), until_min=1500.0)
    started = time.perf_counter()
    clone = first.clone()
    clone_seconds = time.perf_counter() - started
    assert shared_mutable_objects(first.state, clone.state) == []
    second = TerminalKernel.from_catalog(catalog)
    for kernel in (first, clone, second):
        run_episode(kernel, **default_policies())
    digest = ledger_sha256(first.state.ledger)
    assert ledger_sha256(clone.state.ledger) == digest == ledger_sha256(second.state.ledger)
    assert clone_seconds < 1.0  # engineering bound only (measured values are in the Step 4 report)


def test_observable_clone_on_a_generated_scenario(medium_doc):
    kernel = TerminalKernel.from_scenario(medium_doc, validate=False)
    run_episode(kernel, **default_policies(), until_min=600.0)
    observable = kernel.observable_clone()
    hidden = {vid for vid, v in kernel.state.vessels.items() if v.visibility == "HIDDEN"}
    assert hidden and not hidden & set(observable.catalog.vessel_by_id)
    assert not any(e[4] in ("GATE_IN_ARRIVAL", "PICKUP_DUE") for e in observable.state.events)
    observable.validate_invariants(full=True)
    run_episode(observable, **default_policies())
    assert observable.status in ("COMPLETED", "TRUNCATED_DRAIN_LIMIT", "DEADLOCK")
    assert kernel.status == "RUNNING"


def test_full_and_summary_trace_modes_agree_on_a_development_scenario(low_doc, tmp_path):
    """Step 4 closure: identical canonical digests, physics and audits in both trace modes."""
    import hashlib

    from integrated_terminal_pilot.simulator.trace import CANONICAL_FILES, write_trace

    manifests, kpis = {}, {}
    for mode in ("full", "summary"):
        kernel = TerminalKernel.from_scenario(low_doc, validate=False)
        outcome = run_episode(kernel, **default_policies())
        result = kernel.result()
        assert result["audits"]["ok"] and outcome.status == "COMPLETED"
        manifests[mode] = write_trace(kernel, tmp_path / mode, run_id=mode, mode=mode, result=result)
        kpis[mode] = (result["kpi"], result["service_compliance"], result["status"])
    assert manifests["full"]["files"] == manifests["summary"]["files"]
    assert manifests["full"]["trace_sha256"] == manifests["summary"]["trace_sha256"]
    assert kpis["full"] == kpis["summary"]
    for name in CANONICAL_FILES:  # the written full files really have the recorded digests
        assert hashlib.sha256((tmp_path / "full" / name).read_bytes()).hexdigest() == manifests["full"]["files"][name]
    assert not (tmp_path / "summary" / "ledger.jsonl").exists()
