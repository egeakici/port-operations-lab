"""Step 4 closure: predeclared development-only characterization campaign (FCFS fixture only).

**Development diagnosis, not an experiment.** Every run uses the Step 4 FCFS physical
integration fixture for berths, the Step 3 P_c for cranes and one of the two registered Step 3
yard policies. These runs are not A1 results, not S1/S2 evidence and not a Step 5 evaluation, and
they select nothing: no fleet, family or yard baseline is chosen or frozen from them.

Layout (Git-ignored)::

    experiments/step4_closure/
        plan_history.jsonl                      append-only: every plan hash ever used (+ reason)
        <plan_sha256[:12]>/plan.json            the hashed, pre-run plan (never rewritten)
        <plan_sha256[:12]>/plan.json.sha256
        <plan_sha256[:12]>/runs/<condition_id>/<scenario_id>.json   one result per run ("x" mode)
        <plan_sha256[:12]>/reports/report_<sha12>.json|.md          derived summaries

Resume verifies each existing run file (plan hash, source file SHA-256, condition and
resolved-physics fingerprints) and refuses a mismatch; completed runs are never re-run or
overwritten.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy

from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT
from integrated_terminal_pilot.scenarios.fingerprints import sha256_of
from integrated_terminal_pilot.scenarios.serialization import file_sha256, load_scenario
from integrated_terminal_pilot.simulator.diagnostics import (
    BERTH_DRIVER_ID, CRANE_POLICY_ID, DiagnosticCondition, build_condition_catalog, load_capacity,
)
from integrated_terminal_pilot.simulator.drivers import FcfsBerthIntegrationDriver, run_episode
from integrated_terminal_pilot.simulator.kernel import TerminalKernel
from integrated_terminal_pilot.simulator.trace import emit_trace

CLOSURE_ROOT = PROJECT_ROOT / "experiments" / "step4_closure"
SOURCE_RUN = "dev_f5789d8c91_1ee66026"
PLAN_VERSION = "itp_step4_closure_plan_v1"
FAMILY_SEEDS = {"itp_low": 10, "itp_medium": 30, "itp_heavy": 30, "itp_yard_bottleneck": 10}
FIRST_SEED = 10_000_000
BOOTSTRAP_SEED = 20261012
BOOTSTRAP_RESAMPLES = 10_000
ALL = tuple(FAMILY_SEEDS)
CONDITIONS = (  # (condition, families), deduplicated across C1/C2/C3
    (DiagnosticCondition("yard_first_fit_v1", 4, "assigned"), ALL),
    (DiagnosticCondition("yard_occupancy_balance_v1", 4, "assigned"), ALL),
    (DiagnosticCondition("yard_occupancy_balance_v1", 6, "assigned"), ALL),
    (DiagnosticCondition("yard_occupancy_balance_v1", 8, "assigned"), ALL),
    (DiagnosticCondition("yard_occupancy_balance_v1", 4, "working"), ("itp_medium", "itp_heavy")),
)
CONTRASTS = (  # (name, block, minuend condition id, subtrahend condition id, families)
    ("C1_balanced_minus_first_fit_qc4", "C1", "balanced_qc4_assigned", "first_fit_qc4_assigned", ALL),
    ("C2_balanced_qc6_minus_qc4", "C2", "balanced_qc6_assigned", "balanced_qc4_assigned", ALL),
    ("C2_balanced_qc8_minus_qc4", "C2", "balanced_qc8_assigned", "balanced_qc4_assigned", ALL),
    ("C3_working_minus_assigned_qc4", "C3", "balanced_qc4_working", "balanced_qc4_assigned",
     ("itp_medium", "itp_heavy")),
)
CONTRAST_METRICS = ("vessels_departed", "vessels_cargo_fulfilled", "unfinished_ship_moves_at_stop",
                    "cargo_completion_ratio", "T_end_censored_total_turnaround_min",
                    "restricted_observed_turnaround_total_min", "berth_wait_min", "handling_min",
                    "handling_YARD_HANDLING_CONSTRAINED_min", "handling_CRANE_SHORTAGE_min",
                    "busiest_block_ship_share")


class ClosureError(RuntimeError):
    pass


# ---------------------------------------------------------------------------------- plan

def _source_rows() -> dict[str, dict[str, str]]:
    index = PROJECT_ROOT / "experiments" / "scenarios" / "development" / SOURCE_RUN / "scenario_index.csv"
    if not index.exists():
        raise ClosureError(f"development source run {SOURCE_RUN} is missing; regenerate development inputs "
                           "and reconcile fingerprints before running the closure campaign")
    with index.open(encoding="utf-8") as stream:
        return {row["scenario_id"]: row for row in csv.DictReader(stream)}


def build_plan() -> dict[str, Any]:
    rows = _source_rows()
    run_dir = PROJECT_ROOT / "experiments" / "scenarios" / "development" / SOURCE_RUN
    scenarios = []
    for family, count in FAMILY_SEEDS.items():
        for seed in range(FIRST_SEED, FIRST_SEED + count):
            scenario_id = f"{family}_development_seed{seed}"
            row = rows.get(scenario_id)
            if row is None or row["status"] != "accepted":
                raise ClosureError(f"{scenario_id} is not an accepted scenario of {SOURCE_RUN}")
            scenarios.append({"scenario_id": scenario_id, "family": family, "seed": seed,
                              "file": f"experiments/scenarios/development/{SOURCE_RUN}/scenarios/"
                                      f"{scenario_id}.scenario.json",
                              "file_sha256": row["file_sha256"],
                              "physical_fingerprint": row["physical_fingerprint"],
                              "exogenous_schedule_fingerprint": row["exogenous_schedule_fingerprint"]})
    runs = [(condition.condition_id, s["scenario_id"]) for condition, families in CONDITIONS
            for s in scenarios if s["family"] in families]
    plan = {
        "plan_version": PLAN_VERSION,
        "label": "Step 4 closure development diagnosis (FCFS physical fixture only; not A1, not S1/S2 evidence, "
                 "not Step 5; selects and freezes nothing)",
        "source": {"run": SOURCE_RUN, "manifest_sha256": (run_dir / "manifest.json.sha256").read_text(
            encoding="utf-8").split()[0], "split": "development"},
        "scenarios": scenarios,
        "conditions": [{"condition_id": c.condition_id, "yard_policy_id": c.yard_policy_id,
                        "crane_count": c.crane_count, "efficiency_basis": c.efficiency_basis,
                        "families": list(f), "is_reference_physics": c.is_reference} for c, f in CONDITIONS],
        "condition_blocks": {"C1": ["first_fit_qc4_assigned", "balanced_qc4_assigned"],
                             "C2": ["balanced_qc4_assigned", "balanced_qc6_assigned", "balanced_qc8_assigned"],
                             "C3": ["balanced_qc4_assigned", "balanced_qc4_working"]},
        "unique_runs": len(runs),
        "fixed_policies": {"berth": BERTH_DRIVER_ID, "crane": CRANE_POLICY_ID, "max_cranes_per_vessel": 2},
        "immutable_reference_values": {"quay_crane_count": 4, "quay_crane_moves_per_hour": 30.0,
                                       "max_cranes_per_vessel": 2, "two_crane_efficiency": 0.92,
                                       "yard_block_count": 12, "total_yard_operating_capacity_teu": 26400.0,
                                       "block_handling_moves_per_hour": {"reference": 60.0, "bottleneck": 30.0},
                                       "initial_occupancy_target": {"reference": 0.5, "bottleneck": 0.7}},
        "user_pending_choices": ["AM-01 common yard baseline (yard_occupancy_balance_v1)", "D15 batch size 10",
                                 "D17 max_load_wait_min 240", "R5 release admission", "R1 efficiency basis",
                                 "reference crane fleet (4 stays unless explicitly amended)",
                                 "remaining PROPOSED_PENDING_REVIEW physics coefficients"],
        "trace_mode": "summary",
        "measures": ["termination status", "departed / cargo-fulfilled vessels", "rollover", "unfinished moves",
                     "D24 T_end-censored turnaround", "restricted observed turnaround", "berth waiting",
                     "realized/nominal service ratio", "crane productive/blocked/idle time",
                     "per-block handling utilization and ship-side work share", "yard occupancy peak",
                     "queue at final arrival", "time from final arrival to stop",
                     "phase decomposition and handling-cause bookkeeping", "event/ledger digests", "wall clock"],
        "definitions": {
            "comparison_horizon": "fixed per scenario: T_end = last arrival + max_drain_extension_min "
                                  "(identical drain definition in every condition)",
            "T_end_censored_turnaround": "D24 total turnaround, departure or T_end",
            "restricted_observed_turnaround": "min(departure, run stop) - arrival, arrived vessels",
            "berth_waiting_never_berthed": "waiting counted until the run stop (restricted)",
            "cargo_fulfilled": "departed with every original ship-side move completed (rollover = unfulfilled)",
            "busiest_block_ship_share": "largest share of completed ship-side moves handled by one block",
        },
        "comparison_approach": {"paired_by": "exogenous scenario seed", "statistic": "mean paired difference",
                                "interval": f"percentile paired bootstrap over seeds, {BOOTSTRAP_RESAMPLES} "
                                            f"resamples, numpy RandomState({BOOTSTRAP_SEED})",
                                "small_families": "10-seed families: exploratory/unstable intervals",
                                "contrasts": [c[0] for c in CONTRASTS]},
        "acceptance_criteria_decision_support_only": {
            "offered_load_ratio_below": 0.9,
            "all_runs_physically_completed": True,
            "cargo_fulfillment_reported_with_rollover_separate": True,
            "note": "heuristic engineering checklist; reported, never used to select or freeze anything"},
    }
    return plan


def plan_hash(plan: dict[str, Any]) -> str:
    return sha256_of(plan)


def ensure_plan(root: Path = CLOSURE_ROOT, *, reason: str | None = None) -> tuple[Path, dict[str, Any], str]:
    plan = build_plan()
    digest = plan_hash(plan)
    plan_dir = root / digest[:12]
    root.mkdir(parents=True, exist_ok=True)
    history = root / "plan_history.jsonl"
    if plan_dir.exists():
        stored = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
        if plan_hash(stored) != digest:
            raise ClosureError(f"{plan_dir} holds a different plan; refusing to overwrite")
        return plan_dir, plan, digest
    previous = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()] \
        if history.exists() else []
    if previous and not reason:
        raise ClosureError("a different plan already exists; pass --deviation-reason to record a plan change")
    plan_dir.mkdir(parents=True)
    with (plan_dir / "plan.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(plan, sort_keys=True, indent=1) + "\n")
    with (plan_dir / "plan.json.sha256").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{digest}  plan.json\n")
    with history.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"plan_sha256": digest, "previous": previous[-1]["plan_sha256"] if previous else None,
                                 "reason": reason or "initial plan",
                                 "recorded_at": datetime.now(timezone.utc).isoformat()}, sort_keys=True) + "\n")
    return plan_dir, plan, digest


def planned_runs(plan: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    scenarios = plan["scenarios"]
    return [(c, s) for c in plan["conditions"] for s in scenarios if s["family"] in c["families"]]


# ---------------------------------------------------------------------------------- one run

def _ship_moves_by_block(kernel: TerminalKernel) -> dict[str, int]:
    counts = {b.block_id: 0 for b in kernel.catalog.blocks}
    for record in kernel.state.ledger or ():
        if record[2] == "DISCHARGE_COMPLETED":
            counts[record[9][1]] += 1
        elif record[2] == "LOAD_STARTED":
            counts[record[8][1]] += 1
    return counts


def execute_run(condition_row: dict[str, Any], scenario_row: dict[str, Any], plan_digest: str) -> dict[str, Any]:
    path = PROJECT_ROOT / scenario_row["file"]
    source_sha = file_sha256(path)
    if source_sha != scenario_row["file_sha256"]:
        raise ClosureError(f"{path.name}: SHA-256 differs from the source manifest index")
    doc = load_scenario(path)
    if doc["fingerprints"]["physical_fingerprint"] != scenario_row["physical_fingerprint"]:
        raise ClosureError(f"{path.name}: physical fingerprint differs from the index")
    condition = DiagnosticCondition(condition_row["yard_policy_id"], condition_row["crane_count"],
                                    condition_row["efficiency_basis"])
    started = time.perf_counter()
    catalog, fingerprints = build_condition_catalog(doc, condition, validate=True)
    kernel = TerminalKernel.from_catalog(catalog, invariant_mode="cheap")
    run = run_episode(kernel, berth_policy=FcfsBerthIntegrationDriver(),
                      crane_policy=GreedyBerthOrderCranePolicy(), yard_policy=create_policy(condition.yard_policy_id))
    run_seconds = time.perf_counter() - started
    result = kernel.result()
    digests = emit_trace(kernel, None, mode="summary", rejections=run.rejections, result=result)
    s = kernel.state
    last_arrival = max(v.arrival_time_min for v in catalog.vessels)
    queue_at_last_arrival = sum(1 for v in catalog.vessels
                                if v.arrival_time_min <= last_arrival
                                and (s.vessels[v.vessel_id].berth_start_time_min is None
                                     or s.vessels[v.vessel_id].berth_start_time_min > last_arrival))
    ship_by_block = _ship_moves_by_block(kernel)
    ship_total = sum(ship_by_block.values())
    elapsed = max(s.now_min, 1e-9)
    decomposition = result["time_decomposition"]
    ratios = [row["realized_berth_occupancy_min"] / row["nominal_service_time_min"]
              for row in result["vessels"] if row["realized_berth_occupancy_min"] is not None]
    vessel_rows = [{k: row[k] for k in ("vessel_id", "arrived", "departed", "cargo_fulfilled", "required_moves",
                                         "completed_moves", "rolled_over_containers", "unfinished_moves")
                    } | {k: row.get(k) for k in ("berth_wait_min", "berthing_prep_min", "handling_min",
                                                 "departure_prep_min", "unclassified_min",
                                                 "observed_turnaround_min", "observed_turnaround_kind",
                                                 "handling_cause_min", "handling_capacity_equivalent_min")}
                   for row in decomposition["vessels"]]
    return {
        "plan_sha256": plan_digest,
        "condition": condition_row,
        "scenario": scenario_row | {"verified_file_sha256": source_sha},
        "fingerprints": fingerprints,
        "status": run.status,
        "kernel_status": kernel.status,
        "status_reason": result["status_reason"],
        "rejections": run.rejections,
        "end_time_min": result["end_time_min"], "T_end_min": result["T_end_min"],
        "last_arrival_min": last_arrival,
        "queue_at_final_arrival": queue_at_last_arrival,
        "final_arrival_to_stop_min": s.now_min - last_arrival,
        "service_compliance": result["service_compliance"],
        "kpi": result["kpi"],
        "counts": result["counts"],
        "audits": {k: v.get("ok") for k, v in result["audits"].items() if isinstance(v, dict)} |
                  {"ok": result["audits"]["ok"]},
        "realized_to_nominal_ratios": ratios,
        "time_decomposition": {k: v for k, v in decomposition.items() if k != "vessels"},
        "vessels": vessel_rows,
        "yard": {"ship_moves_by_block": ship_by_block,
                 "busiest_block_ship_share": (max(ship_by_block.values()) / ship_total) if ship_total else None,
                 "busiest_block": max(ship_by_block, key=ship_by_block.get) if ship_total else None,
                 "busy_fraction_by_block": {b: info["busy_min"] / elapsed for b, info in result["blocks"].items()},
                 "peak_block_occupancy_fraction": result["kpi"]["peak_block_occupancy_fraction"],
                 "storage_capacity_violations": 0 if result["audits"]["invariants"]["ok"] else None},
        "capacity_inputs": load_capacity(doc, condition.crane_count),
        "digests": {"files": digests["files"], "trace_sha256": digests["trace_sha256"],
                    "canonical_sizes_bytes": digests["sizes_bytes"]},
        "engineering": {"run_seconds": run_seconds, "total_seconds": time.perf_counter() - started},
    }


def _run_path(plan_dir: Path, condition_id: str, scenario_id: str) -> Path:
    return plan_dir / "runs" / condition_id / f"{scenario_id}.json"


def verify_existing(path: Path, plan_digest: str, condition_row: dict, scenario_row: dict) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    if data.get("plan_sha256") != plan_digest:
        problems.append("plan hash")
    if data.get("condition") != condition_row:
        problems.append("condition")
    if data.get("scenario", {}).get("file_sha256") != scenario_row["file_sha256"]:
        problems.append("source file hash")
    if not data.get("digests", {}).get("trace_sha256"):
        problems.append("missing digests")
    if problems:
        raise ClosureError(f"{path}: existing output is incompatible ({', '.join(problems)}); refusing to overwrite")


def run_campaign(*, root: Path = CLOSURE_ROOT, resume: bool = False, limit_runs: int | None = None,
                 progress: bool = False, dry_run: bool = False, reason: str | None = None,
                 shard: tuple[int, int] | None = None) -> dict[str, Any]:
    """Execute planned runs in plan order. ``shard=(k, n)`` executes only runs whose plan index is
    ``k mod n`` (independent deterministic runs; several shard processes may run in parallel)."""
    plan_dir, plan, digest = ensure_plan(root, reason=reason)
    runs = planned_runs(plan)
    if len(runs) != plan["unique_runs"]:
        raise ClosureError("planned run count differs from the plan")
    existing = [(c, s) for c, s in runs if _run_path(plan_dir, c["condition_id"], s["scenario_id"]).exists()]
    if dry_run:
        return {"plan_dir": str(plan_dir), "plan_sha256": digest, "unique_runs": len(runs),
                "completed": len(existing), "remaining": len(runs) - len(existing)}
    if existing and not resume:
        raise ClosureError(f"{len(existing)} runs already exist in {plan_dir}; use --resume to continue")
    for condition_row, scenario_row in existing:
        verify_existing(_run_path(plan_dir, condition_row["condition_id"], scenario_row["scenario_id"]),
                        digest, condition_row, scenario_row)
    executed, started = 0, time.perf_counter()
    for index, (condition_row, scenario_row) in enumerate(runs):
        if shard is not None and index % shard[1] != shard[0]:
            continue
        path = _run_path(plan_dir, condition_row["condition_id"], scenario_row["scenario_id"])
        stale = path.with_name(path.name + ".partial")
        if stale.exists() and not path.exists():
            stale.unlink()  # an interrupted write is not a completed output; this run is redone
        if path.exists():
            continue
        if limit_runs is not None and executed >= limit_runs:
            break
        record = execute_run(condition_row, scenario_row, digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        with partial.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, sort_keys=True, indent=1, allow_nan=False) + "\n")
        os.rename(partial, path)  # atomic; fails rather than overwrite an existing result
        executed += 1
        if progress:
            sc = record["service_compliance"]
            print(f"[{len(existing) + executed}/{len(runs)}] {condition_row['condition_id']} "
                  f"{scenario_row['scenario_id']} {record['status']} departed={sc['vessels_departed']}/"
                  f"{sc['vessels_total']} unfinished={sc['unfinished_ship_moves_at_stop']} "
                  f"{record['engineering']['total_seconds']:.1f}s", flush=True)
    completed = sum(1 for c, s in runs if _run_path(plan_dir, c["condition_id"], s["scenario_id"]).exists())
    return {"plan_dir": str(plan_dir), "plan_sha256": digest, "unique_runs": len(runs), "executed_now": executed,
            "completed": completed, "remaining": len(runs) - completed,
            "wall_seconds": time.perf_counter() - started}


# ---------------------------------------------------------------------------------- report

def _metrics(record: dict[str, Any]) -> dict[str, float]:
    sc, td = record["service_compliance"], record["time_decomposition"]
    causes = td["handling_cause_totals_min"]
    return {"vessels_departed": sc["vessels_departed"], "vessels_cargo_fulfilled": sc["vessels_cargo_fulfilled"],
            "unfinished_ship_moves_at_stop": sc["unfinished_ship_moves_at_stop"],
            "cargo_completion_ratio": sc["cargo_completion_ratio"],
            "T_end_censored_total_turnaround_min": record["kpi"]["total_turnaround_min"],
            "restricted_observed_turnaround_total_min": sc["restricted_observed_turnaround_total_min"],
            "berth_wait_min": td["phase_totals_min"]["berth_wait_min"],
            "handling_min": td["phase_totals_min"]["handling_min"],
            "handling_YARD_HANDLING_CONSTRAINED_min": causes["YARD_HANDLING_CONSTRAINED"],
            "handling_CRANE_SHORTAGE_min": causes["CRANE_SHORTAGE"],
            "busiest_block_ship_share": record["yard"]["busiest_block_ship_share"] or 0.0}


def _bootstrap(diffs: list[float]) -> dict[str, Any]:
    values = numpy.asarray(diffs, dtype=float)
    rng = numpy.random.RandomState(BOOTSTRAP_SEED)
    means = values[rng.randint(0, len(values), size=(BOOTSTRAP_RESAMPLES, len(values)))].mean(axis=1)
    return {"n": len(values), "mean": float(values.mean()), "ci95": [float(numpy.percentile(means, 2.5)),
                                                                    float(numpy.percentile(means, 97.5))],
            "min": float(values.min()), "max": float(values.max()),
            "stability": "exploratory/unstable" if len(values) < 30 else "development-only"}


def _pct(values: list[float], q: float) -> float | None:
    return float(numpy.percentile(values, q)) if values else None


def build_report(root: Path = CLOSURE_ROOT) -> dict[str, Any]:
    plan_dir, plan, digest = ensure_plan(root)
    runs = planned_runs(plan)
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for condition_row, scenario_row in runs:
        path = _run_path(plan_dir, condition_row["condition_id"], scenario_row["scenario_id"])
        if path.exists():
            verify_existing(path, digest, condition_row, scenario_row)
            records[(condition_row["condition_id"], scenario_row["scenario_id"])] = json.loads(
                path.read_text(encoding="utf-8"))
    families = list(FAMILY_SEEDS)
    summaries: dict[str, dict[str, Any]] = {}
    for condition_row in plan["conditions"]:
        cid = condition_row["condition_id"]
        for family in families:
            if family not in condition_row["families"]:
                continue
            planned = [s for s in plan["scenarios"] if s["family"] == family]
            got = [records[(cid, s["scenario_id"])] for s in planned if (cid, s["scenario_id"]) in records]
            key = f"{family}|{cid}"
            if not got:
                summaries[key] = {"family": family, "condition_id": cid, "planned": len(planned), "executed": 0}
                continue
            statuses: dict[str, int] = {}
            truncation_causes: dict[str, int] = {}
            for r in got:
                statuses[r["status"]] = statuses.get(r["status"], 0) + 1
                if r["status"] == "TRUNCATED_DRAIN_LIMIT":
                    sc_r = r["service_compliance"]
                    cause = ("ship_side_work_unfinished" if sc_r["unfinished_ship_moves_at_stop"] > 0
                             or sc_r["vessels_departed"] < sc_r["vessels_total"]
                             else "landside_backlog_only (all vessels departed, ship work done)")
                    truncation_causes[cause] = truncation_causes.get(cause, 0) + 1
            sc = [r["service_compliance"] for r in got]
            vessels = [v for r in got for v in r["vessels"]]
            waits = [v["berth_wait_min"] for v in vessels if v["arrived"]]
            complete = [v["observed_turnaround_min"] for v in vessels if v["departed"]]
            ratios = [x for r in got for x in r["realized_to_nominal_ratios"]]
            causes: dict[str, float] = {}
            handling = 0.0
            for r in got:
                handling += r["time_decomposition"]["phase_totals_min"]["handling_min"]
                for c, m in r["time_decomposition"]["handling_cause_totals_min"].items():
                    causes[c] = causes.get(c, 0.0) + m
            block_shares: dict[str, list[float]] = {}
            block_busy: dict[str, list[float]] = {}
            for r in got:
                total = sum(r["yard"]["ship_moves_by_block"].values()) or 1
                for b, n in r["yard"]["ship_moves_by_block"].items():
                    block_shares.setdefault(b, []).append(n / total)
                for b, f in r["yard"]["busy_fraction_by_block"].items():
                    block_busy.setdefault(b, []).append(f)
            crane_count = condition_row["crane_count"]
            productive = [r["kpi"]["crane_productive_min"] / (crane_count * r["end_time_min"]) for r in got]
            blocked = [sum(r["kpi"]["crane_blocked_min_by_reason"].values()) / (crane_count * r["end_time_min"])
                       for r in got]
            idle = [r["kpi"]["crane_idle_min"] / (crane_count * r["end_time_min"]) for r in got]
            cap = [r["capacity_inputs"] for r in got]
            summaries[key] = {
                "family": family, "condition_id": cid, "planned": len(planned), "executed": len(got),
                "status_counts": statuses,
                "truncation_causes": truncation_causes,
                "vessels_departed": sum(x["vessels_departed"] for x in sc),
                "vessels_cargo_fulfilled": sum(x["vessels_cargo_fulfilled"] for x in sc),
                "vessels_total": sum(x["vessels_total"] for x in sc),
                "rolled_over_containers": sum(x["rolled_over_containers"] for x in sc),
                "unfinished_ship_moves_at_stop": sum(x["unfinished_ship_moves_at_stop"] for x in sc),
                "cargo_completion_ratio_mean": statistics.fmean(x["cargo_completion_ratio"] for x in sc),
                "completed_only_mean_turnaround_min_conditional": statistics.fmean(complete) if complete else None,
                "restricted_observed_turnaround_mean_min": statistics.fmean(
                    x["restricted_observed_turnaround_mean_min"] for x in sc),
                "T_end_censored_mean_turnaround_min": statistics.fmean(r["kpi"]["mean_turnaround_min"] for r in got),
                "berth_wait_mean_min": statistics.fmean(waits) if waits else None,
                "berth_wait_p95_min": _pct(waits, 95),
                "realized_to_nominal_median": statistics.median(ratios) if ratios else None,
                "realized_to_nominal_p90": _pct(ratios, 90),
                "crane_productive_fraction_mean": statistics.fmean(productive),
                "crane_blocked_fraction_mean": statistics.fmean(blocked),
                "crane_idle_unassigned_fraction_mean": statistics.fmean(idle),
                "busiest_block_ship_share_mean": statistics.fmean(
                    r["yard"]["busiest_block_ship_share"] or 0.0 for r in got),
                "ship_share_by_block_mean": {b: statistics.fmean(v) for b, v in sorted(block_shares.items())},
                "busy_fraction_by_block_mean": {b: statistics.fmean(v) for b, v in sorted(block_busy.items())},
                "peak_block_occupancy_fraction_max": max(r["yard"]["peak_block_occupancy_fraction"] for r in got),
                "storage_capacity_violations": sum(0 if r["audits"]["invariants"] else 1 for r in got),
                "audits_all_ok": all(r["audits"]["ok"] for r in got),
                "queue_at_final_arrival_mean": statistics.fmean(r["queue_at_final_arrival"] for r in got),
                "final_arrival_to_stop_mean_min": statistics.fmean(r["final_arrival_to_stop_min"] for r in got),
                "handling_cause_shares": {c: (m / handling if handling else None) for c, m in sorted(causes.items())},
                "unattributed_share": (causes.get("UNATTRIBUTED", 0.0) / handling) if handling else None,
                "max_phase_reconciliation_error_min": max(
                    r["time_decomposition"]["max_phase_reconciliation_error_min"] for r in got),
                "required_ship_moves_mean": statistics.fmean(c["required_ship_moves"] for c in cap),
                "offered_rate_arrival_window_mean": statistics.fmean(
                    c["offered_moves_per_hour"]["arrival_window"] for c in cap),
                "offered_rate_arrival_plus_service_mean": statistics.fmean(
                    c["offered_moves_per_hour"]["arrival_window_plus_mean_nominal_service"] for c in cap),
                "optimistic_crane_bound": cap[0]["optimistic_crane_bound_moves_per_hour"],
                "geometry_bound_min": min(c["geometry_aware_crane_bound_moves_per_hour"] for c in cap),
                "offered_ratio_arrival_window": {"mean": statistics.fmean(
                    c["offered_to_optimistic_ratio"]["arrival_window"] for c in cap),
                    "max": max(c["offered_to_optimistic_ratio"]["arrival_window"] for c in cap)},
                "offered_ratio_arrival_plus_service": {"mean": statistics.fmean(
                    c["offered_to_optimistic_ratio"]["arrival_window_plus_mean_nominal_service"] for c in cap),
                    "max": max(c["offered_to_optimistic_ratio"]["arrival_window_plus_mean_nominal_service"]
                               for c in cap)},
                "unique_trace_digests": len({r["digests"]["trace_sha256"] for r in got}),
                "run_seconds_mean": statistics.fmean(r["engineering"]["total_seconds"] for r in got),
            }
    contrasts = []
    for name, block, plus, minus, fams in CONTRASTS:
        for family in fams:
            seeds = [s["scenario_id"] for s in plan["scenarios"] if s["family"] == family]
            pairs = [(records[(plus, sid)], records[(minus, sid)]) for sid in seeds
                     if (plus, sid) in records and (minus, sid) in records]
            entry = {"contrast": name, "block": block, "family": family, "matched_seeds": len(pairs),
                     "planned_seeds": len(seeds)}
            if pairs:
                entry["metrics"] = {m: _bootstrap([_metrics(a)[m] - _metrics(b)[m] for a, b in pairs])
                                    for m in CONTRAST_METRICS}
                entry["status_pairs"] = sorted({f"{a['status']}->{b['status']}" for a, b in pairs})
            if block == "C2":
                entry["note"] = "varies physical infrastructure (crane fleet); not an effect of berth coordination"
            contrasts.append(entry)
    checklist = []
    for family in families:
        for crane_count in (4, 6, 8):
            key = f"{family}|balanced_qc{crane_count}_assigned"
            summary = summaries.get(key)
            if not summary or not summary.get("executed"):
                continue
            checklist.append({
                "family": family, "cranes": crane_count, "executed": summary["executed"],
                "offered_ratio_arrival_window_mean_below_0.9":
                    summary["offered_ratio_arrival_window"]["mean"] < 0.9,
                "offered_ratio_arrival_plus_service_mean_below_0.9":
                    summary["offered_ratio_arrival_plus_service"]["mean"] < 0.9,
                "all_runs_completed": summary["status_counts"].get("COMPLETED", 0) == summary["executed"],
                "cargo_completion_ratio_mean": summary["cargo_completion_ratio_mean"],
                "rolled_over_containers": summary["rolled_over_containers"],
                "yard_handling_constrained_share": summary["handling_cause_shares"].get("YARD_HANDLING_CONSTRAINED"),
                "crane_shortage_share": summary["handling_cause_shares"].get("CRANE_SHORTAGE"),
                "busiest_block_ship_share_mean": summary["busiest_block_ship_share_mean"],
                "crane_productive_fraction_mean": summary["crane_productive_fraction_mean"],
                "departed_of_total": f"{summary['vessels_departed']}/{summary['vessels_total']}",
            })
    report = {"plan_sha256": digest, "plan_dir": str(plan_dir), "unique_runs_planned": len(runs),
              "runs_executed": len(records),
              "label": plan["label"], "summaries": summaries, "contrasts": contrasts,
              "decision_support_checklist": checklist,
              "selection_statement": "No fleet, family or yard baseline is selected or frozen by this report."}
    body = json.dumps(report, sort_keys=True, indent=1, allow_nan=False)
    report_digest = hashlib.sha256(body.encode()).hexdigest()
    out = plan_dir / "reports"
    out.mkdir(exist_ok=True)
    target = out / f"report_{report_digest[:12]}.json"
    if not target.exists():
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(body + "\n")
    markdown = target.with_suffix(".md")
    if not markdown.exists():
        with markdown.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render_markdown(report))
    report["report_path"] = str(target)
    report["markdown_path"] = str(markdown)
    return report


def _f(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Step 4 closure report — plan `{report['plan_sha256'][:12]}`", "",
             f"{report['label']}", "", f"Runs executed: **{report['runs_executed']} / "
             f"{report['unique_runs_planned']}**. {report['selection_statement']}", "",
             "## Family × condition", "",
             "| Family | Condition | Runs | Status | Truncation causes | Departed | Cargo-fulfilled | Rolled over | "
             "Unfinished moves | Completion ratio | T_end-censored mean turnaround | Mean berth wait | "
             "Realized/nominal median | Crane productive | Busiest-block ship share | Yard-handling share | "
             "Crane-shortage share | Unattributed |",
             "| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
             "---: | ---: | ---: |"]
    for key in sorted(report["summaries"]):
        s = report["summaries"][key]
        if not s.get("executed"):
            lines.append(f"| {s['family']} | {s['condition_id']} | 0/{s['planned']} | not executed | | | | | | | | | "
                         "| | | | | |")
            continue
        shares = s["handling_cause_shares"]
        lines.append(
            f"| {s['family']} | {s['condition_id']} | {s['executed']}/{s['planned']} | {s['status_counts']} | "
            f"{s['truncation_causes'] or '—'} | {s['vessels_departed']}/{s['vessels_total']} | "
            f"{s['vessels_cargo_fulfilled']}/{s['vessels_total']} | {s['rolled_over_containers']} | "
            f"{s['unfinished_ship_moves_at_stop']} | {_f(s['cargo_completion_ratio_mean'], 3)} | "
            f"{_f(s['T_end_censored_mean_turnaround_min'], 0)} | {_f(s['berth_wait_mean_min'], 0)} | "
            f"{_f(s['realized_to_nominal_median'])} | {_f(s['crane_productive_fraction_mean'])} | "
            f"{_f(s['busiest_block_ship_share_mean'])} | {_f(shares.get('YARD_HANDLING_CONSTRAINED'))} | "
            f"{_f(shares.get('CRANE_SHORTAGE'))} | {_f(s['unattributed_share'], 3)} |")
    lines += ["", "## Paired contrasts (mean difference, 95 % percentile paired bootstrap)", "",
              "| Contrast | Family | Seeds | Departed | Cargo-fulfilled | Unfinished moves | T_end-censored total "
              "turnaround (min) | Berth wait (min) | Busiest-block share | Interval stability |",
              "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |"]
    for c in report["contrasts"]:
        if not c.get("metrics"):
            lines.append(f"| {c['contrast']} | {c['family']} | 0/{c['planned_seeds']} | not executed | | | | | | |")
            continue
        m = c["metrics"]

        def cell(name: str, digits: int = 1) -> str:
            x = m[name]
            return f"{x['mean']:.{digits}f} [{x['ci95'][0]:.{digits}f}, {x['ci95'][1]:.{digits}f}]"
        lines.append(f"| {c['contrast']} | {c['family']} | {c['matched_seeds']}/{c['planned_seeds']} | "
                     f"{cell('vessels_departed', 2)} | {cell('vessels_cargo_fulfilled', 2)} | "
                     f"{cell('unfinished_ship_moves_at_stop', 0)} | {cell('T_end_censored_total_turnaround_min', 0)} | "
                     f"{cell('berth_wait_min', 0)} | {cell('busiest_block_ship_share', 2)} | "
                     f"{m['vessels_departed']['stability']} |")
    lines += ["", "## Decision-support checklist (reported, not used to choose)", "",
              "| Family | Cranes | Offered/optimistic (arrival window) < 0.9 | (arrival + service window) < 0.9 | "
              "All COMPLETED | Completion ratio | Rolled over | Yard-handling share | Crane-shortage share | "
              "Crane productive | Departed |",
              "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for c in report["decision_support_checklist"]:
        lines.append(f"| {c['family']} | {c['cranes']} | {c['offered_ratio_arrival_window_mean_below_0.9']} | "
                     f"{c['offered_ratio_arrival_plus_service_mean_below_0.9']} | {c['all_runs_completed']} | "
                     f"{_f(c['cargo_completion_ratio_mean'], 3)} | {c['rolled_over_containers']} | "
                     f"{_f(c['yard_handling_constrained_share'])} | {_f(c['crane_shortage_share'])} | "
                     f"{_f(c['crane_productive_fraction_mean'])} | {c['departed_of_total']} |")
    return "\n".join(lines) + "\n"


__all__ = ["CLOSURE_ROOT", "CONDITIONS", "ClosureError", "build_plan", "build_report", "ensure_plan",
           "execute_run", "plan_hash", "planned_runs", "run_campaign"]
