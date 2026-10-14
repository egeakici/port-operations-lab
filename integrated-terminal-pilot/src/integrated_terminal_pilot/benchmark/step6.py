"""Step 6 development workflow: audit, K5 compute profile, hashed plan, smoke, bounded run/resume, report.

**Development only** (10M seed band, stored batch ``dev_f5789d8c91_1ee66026``) on the approved primary
research profile ``itp_primary_balanced_qc8_v1``. No validation/test mode exists. Nothing here selects
a policy, a budget or a physics value. Outputs (Git-ignored)::

    experiments/step6_development/
        compute_profile/<UTC>/profile.json          --profile-compute (K5 Phase P)
        plan_history.jsonl
        <plan12>/plan.json (+ .sha256)              written before any run
        <plan12>/runs/<stage>/<arm>/<scenario>.json one record per item (temp + rename, never overwritten)
        <plan12>/reports/report_<sha12>.json
        smoke/<UTC>_<arm>_<scenario>.json           --smoke
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT
from integrated_terminal_pilot.scenarios.fingerprints import sha256_of

ROOT = PROJECT_ROOT / "experiments" / "step6_development"
PRIMARY = "itp_primary_balanced_qc8_v1"
FAMILIES = ("itp_low", "itp_medium", "itp_heavy", "itp_yard_bottleneck")
PLAN_VERSION = "itp_step6_development_plan_v1"
PROBE_DECISION_ORDINALS = (1, 5, 10, 15, 20)
FLAGS = {"label": "STEP6_DEVELOPMENT_CHARACTERIZATION", "development_only": True, "validation_executed": False,
         "final_test_executed": False, "rl_training": False, "step7_started": False,
         "scientific_claims": "none (no winner, no CI, no CARGO-NI verdict)"}


class Step6Error(RuntimeError):
    pass


def _scenario_row(family: str, seed: int) -> dict[str, Any]:
    from integrated_terminal_pilot.benchmark import pre_step6

    if not 10_000_000 <= seed <= 10_999_999:
        raise Step6Error(f"seed {seed} is outside the development band; validation/test seeds are refused")
    rows = pre_step6._source_rows()
    scenario_id = f"{family}_development_seed{seed}"
    row = rows.get(scenario_id)
    if row is None or row["status"] != "accepted" or row["split"] != "development":
        raise Step6Error(f"{scenario_id} is not an accepted development scenario")
    return {"scenario_id": scenario_id, "family": family, "scenario_seed": seed,
            "file": f"experiments/scenarios/development/{pre_step6.SOURCE_RUN}/scenarios/{scenario_id}.scenario.json",
            "file_sha256": row["file_sha256"], "physical_fingerprint": row["physical_fingerprint"],
            "exogenous_schedule_fingerprint": row["exogenous_schedule_fingerprint"]}


def _load(scenario: dict[str, Any]) -> dict[str, Any]:
    from integrated_terminal_pilot.benchmark.pre_step6 import PreStep6Error, _load_doc

    try:
        return _load_doc(scenario)
    except PreStep6Error as error:
        raise Step6Error(str(error)) from error


# ------------------------------------------------------------------------------------------------ audit

def audit() -> dict[str, Any]:
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes
    from integrated_terminal_pilot.benchmark.coordination_policies import (
        B1_ESTIMATOR, EVALUATOR_VERSION, FACTOR_LABELS,
    )
    from integrated_terminal_pilot.benchmark.coordination_view import ALLOWLIST, FORECAST_ASSUMPTIONS
    from integrated_terminal_pilot.benchmark.profiles import RESEARCH_PROFILES, approval_state

    state = approval_state()
    checks = {
        "control_records_complete": not state["control_record_gaps"],
        "am07_am08_step6_design": state["control_records"].get("AM-07") ==
        state["control_records"].get("AM-08") == "APPROVED_FOR_STEP6_DESIGN_NOT_VALIDATION_LOCKED",
        "primary_profile": RESEARCH_PROFILES[PRIMARY]["role"] == "APPROVED_PRIMARY_RESEARCH_QC8",
        "lock_blocked": state["scientific_protocol_lock"] == "BLOCKED" and not state["validation_authorized"],
        "pending_records": state["proposed_pending_review"],
        "checkpoints_unchanged": verify_all_hashes()["ok"],
        "no_validation_or_test_scenarios": not any(
            (PROJECT_ROOT / "experiments" / "scenarios" / split).exists() for split in ("validation", "test")),
    }
    return {**FLAGS, "checks": checks, "pass": all(v for k, v in checks.items() if k != "pending_records"),
            "approval_state": {k: v for k, v in state.items() if k != "pending_records"},
            "coordination_allowlist": ALLOWLIST, "forecast_assumptions": FORECAST_ASSUMPTIONS,
            "b1_estimator": B1_ESTIMATOR, "evaluator_version": EVALUATOR_VERSION, "factor_labels": FACTOR_LABELS,
            "owner_decisions_needed": OWNER_QUESTIONS}


OWNER_QUESTIONS = [
    {"id": "Q6-1 B1_ESTIMATOR", "status": "PROPOSED_STEP6_DETAIL_NEEDS_OWNER_APPROVAL",
     "question": "Approve the B1 integrated one-step estimator (coordination_policies.B1_ESTIMATOR) and, with it, "
                 "the A1n nominal estimate, as the frozen Step 6 detail of protocol section 3?"},
    {"id": "Q6-2 FORWARD_LANDSIDE_RULE", "status": "PROPOSED (spec section 10 / D26)",
     "question": "Freeze the spec's PROPOSED forward-model landside rule 'future gate-ins and pickups are not "
                 "simulated' for B2/B2-T?"},
    {"id": "Q6-3 K5_COHORT_CAP", "status": "PROPOSED_NEEDS_OWNER_REVIEW (protocol section 5)",
     "question": "B2 mean decision time exceeds the PROPOSED 2.0 s trigger on development states; choose: keep the "
                 "frozen full-cohort structural budget (accept the cost), or approve a cohort cap applied to A2, B2 "
                 "and B2-T alike (cap value to be chosen on development data only)."},
    {"id": "Q6-4 B2_PREDICTION_DEFINITIONS", "status": "PROPOSED_STEP6_DETAIL_NEEDS_OWNER_APPROVAL",
     "question": "Approve the inner prediction definitions: cohort = revealed, not departed vessels at the "
                 "decision; turnaround = sum(min(departure, inner T_end) - arrival); unfulfilled = cohort outbound "
                 "obligations not LOADED/DEPARTED at the inner stop; inner T_end = last visible arrival + drain "
                 "extension; WAIT = Project 03 finish_after_wait semantics?"},
]


# ------------------------------------------------------------------------------------------------ K5 probe

def _drive_to_ordinals(doc, ordinals, callback) -> None:
    """Drive A1 (FCFS) on the primary profile and call ``callback(kernel, ordinal)`` at chosen berth epochs."""
    from integrated_terminal_pilot.benchmark.runner import resolve_research_profile
    from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
    from integrated_terminal_pilot.simulator.drivers import FcfsBerthIntegrationDriver
    from integrated_terminal_pilot.simulator.kernel import DecisionRequest, TerminalKernel

    _, catalog, _ = resolve_research_profile(doc, PRIMARY)
    kernel = TerminalKernel.from_catalog(catalog, invariant_mode="cheap")
    berth, crane, yard = FcfsBerthIntegrationDriver(), GreedyBerthOrderCranePolicy(), create_policy(
        "yard_occupancy_balance_v1")
    ordinal = 0
    while True:
        request = kernel.advance()
        if not isinstance(request, DecisionRequest):
            return
        if request.kind == "BERTH":
            ordinal += 1
            if ordinal in ordinals:
                callback(kernel, ordinal)
            kernel.apply_berth_action(berth.decide(kernel.berth_view()))
        elif request.kind == "CRANE":
            kernel.apply_crane_action(crane.decide(kernel.crane_observation()))
        else:
            kernel.apply_yard_action(yard.decide(kernel.yard_observation()))


def profile_compute(*, families=FAMILIES, ordinals=PROBE_DECISION_ORDINALS, memory_family: str = "itp_low",
                    max_wall_minutes: float | None = None) -> dict[str, Any]:
    """K5 Phase P: measured costs of A2, B1, A1n and the shared B2/B2-T evaluator at predeclared states."""
    from integrated_terminal_pilot.benchmark.coordination_policies import (
        A1nNominalGreedyPolicy, B1IntegratedGreedyPolicy, SharedRolloutEvaluator, select,
    )
    from integrated_terminal_pilot.benchmark.coordination_view import build_coordination_view
    from integrated_terminal_pilot.benchmark.development import git_state, package_versions
    from integrated_terminal_pilot.benchmark.policies import create_berth_policy

    started = time.perf_counter()
    probes, partial = [], False
    evaluator = SharedRolloutEvaluator("yard_occupancy_balance_v1")
    for family in families:
        scenario = _scenario_row(family, 10_000_000)
        doc = _load(scenario)

        def probe(kernel, ordinal, family=family):
            nonlocal partial
            if max_wall_minutes is not None and time.perf_counter() - started > 60 * max_wall_minutes:
                partial = True
                return
            row: dict[str, Any] = {"family": family, "scenario_id": scenario["scenario_id"], "decision_ordinal": ordinal}
            t = time.perf_counter()
            view = build_coordination_view(kernel, include_projection=True)
            row["view_build_seconds"] = time.perf_counter() - t
            row["visible_vessels"] = sum(v.status != "DEPARTED" for v in view.berth.vessels)
            row["legal_assignments"] = len(view.berth.legal_choices)
            row["wait_legal"] = view.berth.wait_legal
            row["projection_build_seconds"] = view.projection.creation_seconds
            row["projection_bytes"] = len(view.projection.state_bytes)
            a2 = create_berth_policy("A2")
            t = time.perf_counter()
            a2.decide(view.berth)
            row["A2_seconds"] = time.perf_counter() - t
            row["A2_root_evaluations"] = a2.records[-1]["root_evaluations"]
            for name, policy, arg in (("B1", B1IntegratedGreedyPolicy(), view), ("A1n", A1nNominalGreedyPolicy(),
                                                                                 view.berth)):
                t = time.perf_counter()
                policy.decide(arg)
                row[f"{name}_seconds"] = time.perf_counter() - t
            track = family == memory_family
            if track:
                tracemalloc.start()
            record = evaluator.evaluate(view)
            if track:
                row["B2_peak_memory_mb"] = tracemalloc.get_traced_memory()[1] / 1e6
                tracemalloc.stop()
                reverse = evaluator.evaluate(view, reverse_order=True)
                row["candidate_order_invariant"] = reverse.prediction_digest == record.prediction_digest
                again = evaluator.evaluate(view)
                row["replication_identical"] = again.prediction_digest == record.prediction_digest
            row["B2_B2T_shared_evaluation_seconds"] = record.timing["total_seconds"]
            row["B2_candidates"] = len(record.candidates)
            row["B2_leaf_rollouts"] = sum(1 if c.kind == "ASSIGN" or c.wait_terminal else len(c.wait_branches)
                                          for c in record.candidates)
            leaves = [c.leaf for c in record.candidates if c.leaf] + [b for c in record.candidates
                                                                      for b in c.wait_branches]
            row["inner_cycles_per_leaf"] = [leaf.inner_cycles for leaf in leaves]
            row["candidate_seconds"] = record.timing["candidate_seconds"]
            row["fork_seconds"] = record.timing["fork_seconds"]
            row["selected"] = {"B2": select(record, "B2").action, "B2-T": select(record, "B2-T").action}
            row["prediction_digest"] = record.prediction_digest
            row["serialized_prediction_bytes"] = len(json.dumps([c.__dict__ for c in record.candidates],
                                                                default=lambda o: o.__dict__))
            probes.append(row)
            print(f"[K5] {family} #{ordinal} visible={row['visible_vessels']} legal={row['legal_assignments']} "
                  f"wait={row['wait_legal']} A2={row['A2_seconds']:.2f}s B2/B2-T shared="
                  f"{row['B2_B2T_shared_evaluation_seconds']:.2f}s leaves={row['B2_leaf_rollouts']}", flush=True)

        _drive_to_ordinals(doc, set(ordinals), probe)
        if partial:
            break

    def q(values):
        import numpy as np

        if not values:
            return {"n": 0}
        a = np.asarray(values, dtype=float)
        return {"n": len(values), "p50": float(np.percentile(a, 50)), "p90": float(np.percentile(a, 90)),
                "p95": float(np.percentile(a, 95)), "max": float(a.max()), "mean": float(a.mean()),
                "total": float(a.sum())}

    summary = {name: q([p[key] for p in probes]) for name, key in (
        ("A2", "A2_seconds"), ("B2_B2T_shared", "B2_B2T_shared_evaluation_seconds"), ("B1", "B1_seconds"),
        ("A1n", "A1n_seconds"), ("projection_build", "projection_build_seconds"))}
    summary["per_family_B2_mean"] = {f: q([p["B2_B2T_shared_evaluation_seconds"] for p in probes
                                          if p["family"] == f]) for f in families}
    summary["exceeds_protocol5_proposed_2s_trigger"] = (summary["B2_B2T_shared"].get("mean", 0) > 2.0)
    return {**FLAGS, "kind": "K5_PHASE_P_COMPUTE_PROFILE", "status": "PARTIAL" if partial else "MEASURED",
            "predeclared_states": {"families": list(families), "scenario_seed": 10_000_000,
                                   "berth_decision_ordinals": list(ordinals),
                                   "trajectory": "A1 (FCFS) on the primary profile reaches each state"},
            "host": {"python": platform.python_version(), "platform": platform.platform(),
                     "processor": platform.processor(), "cpu_count": os.cpu_count(),
                     "note": "single process; other tools may have run concurrently (host load not controlled)"},
            "git": git_state(), "packages": package_versions(), "summary": summary, "probes": probes,
            "wall_seconds": time.perf_counter() - started,
            "timing_method": "time.perf_counter around each decision call; imports, checkpoint loading and "
                             "trajectory driving excluded; memory via tracemalloc on one family only"}


# ------------------------------------------------------------------------------------------------ plan / run

def build_plan() -> dict[str, Any]:
    from integrated_terminal_pilot.benchmark.coordination_policies import B1_ESTIMATOR, EVALUATOR_VERSION

    scenarios = [_scenario_row(f, 10_000_000) for f in FAMILIES]
    by_family = {s["family"]: s for s in scenarios}
    items = []
    for s in scenarios:                                                 # F1: no-search arms, every family
        for arm in ("A1", "A1n", "B1"):
            items.append({"stage": "F1", "arm_id": arm, "scenario_id": s["scenario_id"], "repeat": False})
    for family in ("itp_low", "itp_medium"):                            # F2: rollout arms, bounded by K5 probe
        for arm in ("A2", "B2-T", "B2"):
            items.append({"stage": "F2", "arm_id": arm, "scenario_id": by_family[family]["scenario_id"],
                          "repeat": False})
    items.append({"stage": "F2", "arm_id": "B2", "scenario_id": by_family["itp_low"]["scenario_id"], "repeat": True})
    items.append({"stage": "F1", "arm_id": "B1", "scenario_id": by_family["itp_low"]["scenario_id"], "repeat": True})
    return {
        "plan_version": PLAN_VERSION, **FLAGS, "research_profile": PRIMARY, "split": "development",
        "scenarios": scenarios, "items": items,
        "deferred": {"F3": "B2/B2-T/A2 on itp_heavy and itp_yard_bottleneck and seeds 10000001-10000002: "
                           "BLOCKED_BY_COMPUTE_REVIEW until the owner decides the K5 budget (Q6-3); the "
                           "pre-Step 6 A2 heavy decisions already reached ~10 s and the K5 probe measures B2"},
        "evaluator_version": EVALUATOR_VERSION, "b1_estimator_version": B1_ESTIMATOR["version"],
        "engineering_caps": {"per_run": "none (runs are executed whole or not at all)",
                             "session": "--max-new-runs / --max-wall-minutes stop BEFORE starting a new run"},
    }


def plan_digest(plan: dict[str, Any]) -> str:
    return sha256_of(plan)


def _plan_dir(digest: str) -> Path:
    return ROOT / digest[:12]


def write_plan() -> Path:
    plan = build_plan()
    digest = plan_digest(plan)
    directory = _plan_dir(digest)
    path = directory / "plan.json"
    if path.exists():
        if plan_digest(json.loads(path.read_text(encoding="utf-8"))) != digest:
            raise Step6Error(f"{path} exists with a different hash")
        return path
    directory.mkdir(parents=True, exist_ok=False)
    _atomic_write(path, plan)
    (directory / "plan.json.sha256").write_text(f"{digest}  plan.json (canonical sha256_of)\n", encoding="utf-8")
    with open(ROOT / "plan_history.jsonl", "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"plan_sha256": digest, "written_utc": datetime.now(timezone.utc).isoformat()}) + "\n")
    return path


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    if path.exists():
        raise Step6Error(f"{path} exists; outputs are never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, sort_keys=True, allow_nan=False, default=str))
    os.replace(tmp, path)


def _item_path(directory: Path, item: dict[str, Any]) -> Path:
    name = item["scenario_id"] + ("__repeat" if item["repeat"] else "")
    return directory / "runs" / item["stage"] / item["arm_id"] / f"{name}.json"


def _execute(doc, scenario, arm_id) -> dict[str, Any]:
    from integrated_terminal_pilot.benchmark.development import git_state, package_versions
    from integrated_terminal_pilot.benchmark.profiles import approval_state
    from integrated_terminal_pilot.benchmark.runner import run_arm

    started = time.perf_counter()
    record = run_arm(doc, arm_id=arm_id, research_profile=PRIMARY, trace_mode="summary")
    state = approval_state()
    return {**FLAGS, "scenario_file_sha256": scenario["file_sha256"], "git": git_state(), "packages": package_versions(),
            "approval_summary": {k: state[k] for k in ("frozen", "proposed_pending_review", "scientific_protocol_lock",
                                                       "validation_authorized")},
            "pending_record_ids": [r["decision_id"] for r in state["pending_records"]],
            "wall_seconds_total": time.perf_counter() - started, **record}


def run_plan(*, progress: bool, max_new_runs: int | None, max_wall_minutes: float | None,
             stages: tuple[str, ...] | None) -> dict[str, Any]:
    plan = build_plan()
    digest = plan_digest(plan)
    directory = _plan_dir(digest)
    if not (directory / "plan.json").exists():
        raise Step6Error("write the plan first (--plan)")
    scenarios = {s["scenario_id"]: s for s in plan["scenarios"]}
    started = time.perf_counter()
    executed = 0
    stop_reason = None
    for index, item in enumerate(plan["items"], start=1):
        if stages and item["stage"] not in stages:
            continue
        path = _item_path(directory, item)
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            if stored.get("plan_sha256") != digest or stored.get("item") != item:
                raise Step6Error(f"{path} belongs to another plan; refusing to resume")
            continue
        if max_new_runs is not None and executed >= max_new_runs:
            stop_reason = "PARTIAL: --max-new-runs reached"
            break
        if max_wall_minutes is not None and time.perf_counter() - started > 60 * max_wall_minutes:
            stop_reason = "PARTIAL: --max-wall-minutes reached (no run was interrupted)"
            break
        scenario = scenarios[item["scenario_id"]]
        doc = _load(scenario)
        t = time.perf_counter()
        record = {"plan_sha256": digest, "item": item, **_execute(doc, scenario, item["arm_id"])}
        _atomic_write(path, record)
        executed += 1
        if progress:
            sc = record.get("service_compliance", {})
            print(f"[{index}/{len(plan['items'])}] {item['stage']} {item['arm_id']} {item['scenario_id']}"
                  f"{' (repeat)' if item['repeat'] else ''} {record['status']} departed={sc.get('vessels_departed')} "
                  f"fulfilled={sc.get('vessels_cargo_fulfilled')} U={record['outbound_obligations']['U_not_loaded']} "
                  f"{time.perf_counter() - t:.1f}s", flush=True)
    complete = sum(_item_path(directory, i).exists() for i in plan["items"])
    return {"plan_dir": str(directory), "executed": executed, "complete": complete, "planned": len(plan["items"]),
            "stop_reason": stop_reason}


def build_report() -> dict[str, Any]:
    plan = build_plan()
    digest = plan_digest(plan)
    directory = _plan_dir(digest)
    rows, missing, repeats = [], [], []
    records = {}
    for item in plan["items"]:
        path = _item_path(directory, item)
        if not path.exists():
            missing.append(item)
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        records[json.dumps(item, sort_keys=True)] = r
    for key, r in records.items():
        item = json.loads(key)
        if item["repeat"]:
            twin = records.get(json.dumps(dict(item, repeat=False), sort_keys=True))
            repeats.append({"arm": item["arm_id"], "scenario_id": item["scenario_id"],
                            "identical_trace_digest": twin is not None and
                            twin["digests"]["trace_sha256"] == r["digests"]["trace_sha256"],
                            "identical_prediction_digests": twin is not None and
                            twin.get("step6", {}).get("prediction_digests") ==
                            r.get("step6", {}).get("prediction_digests")})
            continue
        o, sc, kpi = r["outbound_obligations"], r["service_compliance"], r["kpi"]
        s6 = r.get("step6", {})
        rows.append({"stage": item["stage"], "arm": item["arm_id"], "scenario_id": item["scenario_id"],
                     "family": r["scenario"]["family"], "status": r["status"], "rejections": len(r["rejections"]),
                     "audits_ok": r["audits"]["ok"], "departed": sc["vessels_departed"],
                     "vessels": sc["vessels_total"], "cargo_fulfilled": sc["vessels_cargo_fulfilled"],
                     "rolled_over": sc["rolled_over_containers"], "N_out": o["N_out"], "U": o["U_not_loaded"],
                     "R": o["R_loss_rate"], "outbound_classes": o["classes"],
                     "D24_total_turnaround": kpi["total_turnaround_min"], "T_end": r["T_end_min"],
                     "censored_vessels": sc["vessels_total"] - sc["vessels_departed"],
                     "mean_wait": kpi["mean_berth_waiting_min"], "p95_wait": kpi["p95_berth_waiting_min"],
                     "crane_utilization": kpi["crane_utilization"],
                     "busiest_block_share": r["yard_work"]["busiest_block_ship_share"],
                     "decisions": r["decisions"]["berth_decisions"], "waits": r["decisions"]["wait_selected"],
                     "policy_seconds": r["decisions"]["seconds"]["policy"],
                     "comparison_fingerprint": r["comparison_fingerprint"],
                     "resolved_physics": r["research_profile"]["resolved_physics_fingerprint"],
                     "trace_sha256": r["digests"]["trace_sha256"], "factor_labels": s6.get("factor_labels"),
                     "s4_pivotal": s6.get("s4_pivotal"), "evaluation_seconds": s6.get("evaluation_seconds"),
                     "budget_fingerprint": s6.get("budget_fingerprint"), "run_wall_seconds":
                         r["engineering"]["run_wall_seconds"]})
    pairing: dict[str, set] = {}
    for row in rows:
        pairing.setdefault(row["scenario_id"], set()).add((row["comparison_fingerprint"], row["resolved_physics"],
                                                           row["N_out"]))
    budgets = {row["budget_fingerprint"] for row in rows if row["arm"] in ("B2", "B2-T")}
    return {"report_version": "itp_step6_report_v1", **FLAGS, "plan_sha256": digest,
            "planned": len(plan["items"]), "complete": len(records), "missing_items": missing,
            "deferred": plan["deferred"], "rows": rows, "determinism_repeats": repeats,
            "pairing_identical": {k: len(v) == 1 for k, v in pairing.items()},
            "b2_b2t_budget_fingerprints": sorted(budgets)}


def report() -> Path:
    data = build_report()
    text = json.dumps(data, indent=1, sort_keys=True, allow_nan=False, default=str)
    out = _plan_dir(data["plan_sha256"]) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"report_{hashlib.sha256(text.encode()).hexdigest()[:12]}.json"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    return path


def smoke(arm_id: str, family: str, seed: int) -> Path:
    scenario = _scenario_row(family, seed)
    doc = _load(scenario)
    record = {"item": {"stage": "smoke", "arm_id": arm_id, "scenario_id": scenario["scenario_id"]},
              **_execute(doc, scenario, arm_id)}
    path = ROOT / "smoke" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{arm_id}_{scenario['scenario_id']}.json"
    _atomic_write(path, record)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_step6_coordination",
                                     description="Project I Step 6 integrated coordination - development only.")
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag, text in (("--audit", "read-only contract/prerequisite check"),
                       ("--profile-compute", "K5 Phase P: bounded cost probe at predeclared states"),
                       ("--plan", "write the hashed development plan"), ("--dry-run", "print the plan; write nothing"),
                       ("--smoke", "one development run"), ("--run", "execute missing plan items"),
                       ("--resume", "same as --run"), ("--report", "summarize existing records; runs nothing")):
        mode.add_argument(flag, action="store_true", help=text)
    parser.add_argument("--policy", choices=("A1", "A1n", "B1", "A2", "B2", "B2-T"))
    parser.add_argument("--family", choices=FAMILIES)
    parser.add_argument("--seed", type=int, default=10_000_000)
    parser.add_argument("--research-profile", default=PRIMARY)
    parser.add_argument("--stage", action="append", choices=("F1", "F2"))
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--max-new-runs", type=int)
    parser.add_argument("--max-wall-minutes", type=float)
    parser.add_argument("--probe-family", action="append", choices=FAMILIES)
    args = parser.parse_args(argv)
    from integrated_terminal_pilot.benchmark.profiles import ProfileSelectionError, assert_primary_profile_unchanged

    try:
        assert_primary_profile_unchanged(args.research_profile, reason="Step 6 command line")
        if args.audit:
            data = audit()
            print(json.dumps(data, indent=1, default=str))
            return 0 if data["pass"] else 1
        if args.profile_compute:
            data = profile_compute(families=tuple(args.probe_family) if args.probe_family else FAMILIES,
                                   max_wall_minutes=args.max_wall_minutes)
            path = ROOT / "compute_profile" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") / "profile.json"
            _atomic_write(path, data)
            print(json.dumps({"profile": str(path), "status": data["status"], "summary": data["summary"]}, indent=1))
            return 0
        if args.dry_run:
            plan = build_plan()
            print(json.dumps({"plan_sha256": plan_digest(plan), "writes": "nothing", "items": plan["items"],
                              "deferred": plan["deferred"]}, indent=1))
            return 0
        if args.plan:
            print(json.dumps({"plan": str(write_plan()), "plan_sha256": plan_digest(build_plan())}))
            return 0
        if args.smoke:
            if not (args.policy and args.family):
                raise Step6Error("--smoke needs --policy and --family")
            print(json.dumps({"smoke": str(smoke(args.policy, args.family, args.seed))}))
            return 0
        if args.run or args.resume:
            print(json.dumps(run_plan(progress=args.progress, max_new_runs=args.max_new_runs,
                                      max_wall_minutes=args.max_wall_minutes,
                                      stages=tuple(args.stage) if args.stage else None), indent=1))
            return 0
        print(json.dumps({"report": str(report())}))
        return 0
    except (Step6Error, ProfileSelectionError) as error:
        print(f"step6: {error}", file=sys.stderr)
        return 2


__all__ = ["FLAGS", "OWNER_QUESTIONS", "audit", "build_plan", "build_report", "main", "plan_digest",
           "profile_compute", "run_plan", "write_plan"]
