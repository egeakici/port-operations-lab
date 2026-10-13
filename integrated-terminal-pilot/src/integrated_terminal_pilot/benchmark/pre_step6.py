"""Pre-Step 6 development characterization of the approved eight-crane research profile.

**DEVELOPMENT_CHARACTERIZATION only.** The plan is written (hashed, exclusive) before any run, covers
a fixed set of development scenarios and all five independent arms, and is never widened or narrowed
after results are seen. Nothing here selects a policy, fleet, yard rule, rollover rule, batch size,
cargo margin, B2 objective or checkpoint (decision firewall, safeguard S3): the primary profile is
asserted unchanged on every run and report. No validation (11M) or test (12M) seed is accepted.

Layout (Git-ignored)::

    experiments/pre_step6_characterization/
        plan_history.jsonl                                   append-only plan hashes
        <plan12>/plan.json (+ .sha256)                       written before any run
        <plan12>/runs/<kind>/<profile>/<arm>/<scenario>.json  one record per item ("x" mode)
        <plan12>/reports/report_<sha12>.json|.md             derived summaries (--report)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT
from integrated_terminal_pilot.scenarios.fingerprints import sha256_of

ROOT = PROJECT_ROOT / "experiments" / "pre_step6_characterization"
SOURCE_RUN = "dev_f5789d8c91_1ee66026"
PLAN_VERSION = "itp_pre_step6_characterization_plan_v1"
FAMILIES = ("itp_low", "itp_medium", "itp_heavy", "itp_yard_bottleneck")
SEEDS = (10_000_000, 10_000_001, 10_000_002)
ARMS = (("A1", None), ("A2", None), ("A3", 11), ("A3", 23), ("A3", 37))
PRIMARY = "itp_primary_balanced_qc8_v1"
SENSITIVITY = ("itp_sensitivity_balanced_qc4_v1", "itp_sensitivity_balanced_qc6_v1")
LABEL = "DEVELOPMENT_CHARACTERIZATION"
FLAGS = {"label": LABEL, "development_only": True, "validation_executed": False, "final_test_executed": False,
         "coordinator_used": False, "rl_training": False, "checkpoints_modified": False,
         "policy_selection": "none", "profile_selection": "none (AM-02 primary fixed before any run; safeguard S3)"}


class PreStep6Error(RuntimeError):
    pass


def _source_rows() -> dict[str, dict[str, str]]:
    index = PROJECT_ROOT / "experiments" / "scenarios" / "development" / SOURCE_RUN / "scenario_index.csv"
    if not index.exists():
        raise PreStep6Error(f"development source run {SOURCE_RUN} is missing")
    with index.open(encoding="utf-8") as stream:
        return {row["scenario_id"]: row for row in csv.DictReader(stream)}


def build_plan() -> dict[str, Any]:
    from integrated_terminal_pilot.benchmark.profiles import RESEARCH_PROFILES

    rows = _source_rows()
    scenarios = []
    for family in FAMILIES:
        for seed in SEEDS:
            if not 10_000_000 <= seed <= 10_999_999:
                raise PreStep6Error("development seeds only")
            scenario_id = f"{family}_development_seed{seed}"
            row = rows.get(scenario_id)
            if row is None or row["status"] != "accepted" or row["split"] != "development":
                raise PreStep6Error(f"{scenario_id} is not an accepted development scenario of {SOURCE_RUN}")
            scenarios.append({"scenario_id": scenario_id, "family": family, "scenario_seed": seed,
                              "file": f"experiments/scenarios/development/{SOURCE_RUN}/scenarios/{scenario_id}.scenario.json",
                              "file_sha256": row["file_sha256"], "physical_fingerprint": row["physical_fingerprint"],
                              "exogenous_schedule_fingerprint": row["exogenous_schedule_fingerprint"]})
    items = [{"kind": "primary", "profile": PRIMARY, "arm_id": a, "ppo_training_seed": k, "scenario_id": s["scenario_id"]}
             for s in scenarios for a, k in ARMS]
    items += [{"kind": "sensitivity", "profile": p, "arm_id": a, "ppo_training_seed": k, "scenario_id": s["scenario_id"]}
              for p in SENSITIVITY for s in scenarios if s["scenario_seed"] == SEEDS[0] for a, k in ARMS]
    items += [{"kind": "repeat", "profile": PRIMARY, "arm_id": "A1", "ppo_training_seed": None,
               "scenario_id": s["scenario_id"]} for s in scenarios if s["scenario_seed"] == SEEDS[0]]
    return {
        "plan_version": PLAN_VERSION, **FLAGS, "source_run": SOURCE_RUN, "split": "development",
        "families": list(FAMILIES), "scenario_seeds": list(SEEDS), "scenarios": scenarios,
        "arms": [{"arm_id": a, "ppo_training_seed": k} for a, k in ARMS],
        "primary_profile": PRIMARY, "sensitivity_profiles": list(SENSITIVITY),
        "profiles": {p: RESEARCH_PROFILES[p] for p in (PRIMARY, *SENSITIVITY)},
        "items": items,
        "counts": {"primary": sum(i["kind"] == "primary" for i in items),
                   "sensitivity": sum(i["kind"] == "sensitivity" for i in items),
                   "repeat": sum(i["kind"] == "repeat" for i in items)},
        "predeclared_partial_subset": "if a time cap stops the run: the primary items of scenario seed 10000000 "
                                      "for every family and all five arms (20 runs) are executed first",
        "cargo_metric": "itp_outbound_obligation_v1 (benchmark.cargo); cutoff T_end = last arrival + drain extension",
        "trace_mode": "summary",
        "decision_firewall": "Results are DEVELOPMENT_CHARACTERIZATION and never change the 8-crane primary profile, "
                             "common P_y, D15/D17/R5, cargo NI margin, B2 objective or checkpoints. Only a recorded "
                             "physical invalidity can trigger a STOP and an owner decision.",
    }


def _ordered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Execution order: the predeclared partial subset (primary, first seed) first, then the rest."""
    first = [i for i in items if i["kind"] == "primary" and i["scenario_id"].endswith(str(SEEDS[0]))]
    return first + [i for i in items if i not in first]


def plan_digest(plan: dict[str, Any]) -> str:
    return sha256_of(plan)


def plan_dir(digest: str) -> Path:
    return ROOT / digest[:12]


def write_plan(plan: dict[str, Any], reason: str = "initial plan") -> Path:
    digest = plan_digest(plan)
    directory = plan_dir(digest)
    path = directory / "plan.json"
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if plan_digest(stored) != digest:
            raise PreStep6Error(f"{path} exists with a different plan hash")
        return path
    directory.mkdir(parents=True, exist_ok=False)
    with open(path, "x", encoding="utf-8") as stream:
        stream.write(json.dumps(plan, indent=1, sort_keys=True))
    with open(directory / "plan.json.sha256", "x", encoding="utf-8") as stream:
        stream.write(f"{digest}  plan.json (canonical sha256_of)\n")
    with open(ROOT / "plan_history.jsonl", "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"plan_sha256": digest, "written_utc": datetime.now(timezone.utc).isoformat(),
                                 "reason": reason}) + "\n")
    return path


def _item_path(directory: Path, item: dict[str, Any]) -> Path:
    from integrated_terminal_pilot.benchmark.runner import arm_label

    return (directory / "runs" / item["kind"] / item["profile"] / arm_label(item["arm_id"], item["ppo_training_seed"])
            / f"{item['scenario_id']}.json")


def _load_doc(scenario: dict[str, Any]) -> dict[str, Any]:
    from integrated_terminal_pilot.scenarios.serialization import file_sha256, load_scenario

    path = PROJECT_ROOT / scenario["file"]
    if not path.exists():
        raise PreStep6Error(f"external scenario missing: {path}")
    if file_sha256(path) != scenario["file_sha256"]:
        raise PreStep6Error(f"{path.name}: SHA-256 differs from the source index (corrupt or changed input)")
    doc = load_scenario(path)
    if doc["identity"]["split"] != "development":
        raise PreStep6Error("source-split guard: development scenarios only")
    if doc["fingerprints"]["physical_fingerprint"] != scenario["physical_fingerprint"]:
        raise PreStep6Error(f"{path.name}: physical fingerprint differs from the index")
    if doc["fingerprints"]["exogenous_schedule_fingerprint"] != scenario["exogenous_schedule_fingerprint"]:
        raise PreStep6Error(f"{path.name}: exogenous fingerprint differs from the index")
    return doc


def run_plan(*, progress: bool = False, limit_runs: int | None = None, kinds: tuple[str, ...] | None = None) -> dict:
    from integrated_terminal_pilot.benchmark.development import git_state, package_versions
    from integrated_terminal_pilot.benchmark.profiles import approval_state, assert_primary_profile_unchanged
    from integrated_terminal_pilot.benchmark.runner import run_arm

    plan = build_plan()
    assert_primary_profile_unchanged(plan["primary_profile"], reason="plan execution")
    digest = plan_digest(plan)
    directory = plan_dir(digest)
    if not (directory / "plan.json").exists():
        raise PreStep6Error("write the plan first (--plan); runs never start without a stored plan hash")
    header = {"plan_sha256": digest, "git": git_state(), "packages": package_versions(),
              "approval_state": {k: v for k, v in approval_state().items() if k != "pending_records"},
              "run_record_schema": "itp_pre_step6_run_v1"}
    scenarios = {s["scenario_id"]: s for s in plan["scenarios"]}
    todo = [i for i in _ordered(plan["items"]) if kinds is None or i["kind"] in kinds]
    executed = skipped = 0
    docs: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(todo, start=1):
        path = _item_path(directory, item)
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            if stored.get("plan_sha256") != digest or stored.get("item") != item:
                raise PreStep6Error(f"{path} does not belong to plan {digest[:12]}; refusing to resume")
            skipped += 1
            continue
        if limit_runs is not None and executed >= limit_runs:
            break
        scenario = scenarios[item["scenario_id"]]
        if item["scenario_id"] not in docs:
            docs.clear()
            docs[item["scenario_id"]] = _load_doc(scenario)
        started = time.perf_counter()
        record = run_arm(docs[item["scenario_id"]], arm_id=item["arm_id"], training_seed=item["ppo_training_seed"],
                         research_profile=item["profile"], trace_mode="summary")
        record = {**FLAGS, **header, "item": item, "scenario_file_sha256": scenario["file_sha256"],
                  "wall_seconds_total": time.perf_counter() - started, **record}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False, default=str))
        executed += 1
        if progress:
            o = record.get("outbound_obligations", {})
            sc = record.get("service_compliance", {})
            print(f"[{index}/{len(todo)}] {item['kind']} {item['profile']} {record['arm']['arm_label']} "
                  f"{item['scenario_id']} {record['status']} departed={sc.get('vessels_departed')} "
                  f"fulfilled={sc.get('vessels_cargo_fulfilled')} R={o.get('R_loss_rate')} "
                  f"{time.perf_counter() - started:.1f}s", flush=True)
    done = sum(_item_path(directory, i).exists() for i in plan["items"])
    return {"plan_dir": str(directory), "executed": executed, "already_present": skipped,
            "complete": done, "planned": len(plan["items"])}


# ------------------------------------------------------------------------------------------- report

def _q(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    import numpy as np

    a = np.asarray(values, dtype=float)
    return {"n": len(values), "mean": float(a.mean()), "p50": float(np.percentile(a, 50)),
            "p95": float(np.percentile(a, 95)), "max": float(a.max())}


def build_report(directory: Path) -> dict[str, Any]:
    from integrated_terminal_pilot.benchmark.profiles import assert_primary_profile_unchanged

    plan = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
    digest = plan_digest(plan)
    assert_primary_profile_unchanged(plan["primary_profile"], reason="report")
    records = {}
    for item in plan["items"]:
        path = _item_path(directory, item)
        if path.exists():
            records[json.dumps(item, sort_keys=True)] = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for key, r in records.items():
        item = json.loads(key)
        if item["kind"] == "repeat":
            continue
        o, sc, kpi, d = r["outbound_obligations"], r["service_compliance"], r["kpi"], r["decisions"]
        rows.append({
            "kind": item["kind"], "profile": item["profile"], "family": r["scenario"]["family"],
            "scenario_id": item["scenario_id"], "arm": r["arm"]["arm_label"], "status": r["status"],
            "rejections": len(r["rejections"]), "audits_ok": r["audits"]["ok"],
            "vessels_total": sc["vessels_total"], "departed": sc["vessels_departed"],
            "cargo_fulfilled": sc["vessels_cargo_fulfilled"], "rolled_over": sc["rolled_over_containers"],
            "N_out": o["N_out"], "U": o["U_not_loaded"], "R": o["R_loss_rate"], "outbound_classes": o["classes"],
            "outbound_reconciliation_ok": o["reconciliation_ok"],
            "unfinished_moves": sc["unfinished_ship_moves_at_stop"],
            "D24_total_turnaround": kpi["total_turnaround_min"],
            "completed_only_mean_turnaround": sc["completed_only_mean_turnaround_min"],
            "completed_only_vessels": sc["completed_only_vessels"],
            "mean_wait": kpi["mean_berth_waiting_min"], "p95_wait": kpi["p95_berth_waiting_min"],
            "realized_to_nominal_mean": r["realized_to_nominal_occupancy"].get("mean"),
            "realized_to_nominal_max": r["realized_to_nominal_occupancy"].get("max"),
            "crane_utilization": kpi["crane_utilization"], "crane_moves": kpi["crane_moves_completed"],
            "busiest_block_share": r["yard_work"]["busiest_block_ship_share"],
            "phase_totals_min": r["time_decomposition"]["phase_totals_min"],
            "handling_cause_shares": r["time_decomposition"]["handling_cause_shares"],
            "comparison_fingerprint": r["comparison_fingerprint"],
            "resolved_physics_fingerprint": r["research_profile"]["resolved_physics_fingerprint"],
            "exogenous": r["research_profile"]["derived_fingerprints"]["exogenous_schedule_fingerprint"],
            "trace_sha256": r["digests"]["trace_sha256"],
            "ppo": d.get("ppo_support"), "decisions": d["berth_decisions"], "waits": d["wait_selected"],
            "seconds": d["seconds"], "run_wall_seconds": r["engineering"]["run_wall_seconds"],
            "setup_seconds_excluded": r["engineering"]["policy_setup_seconds_excluded"],
        })
    # paired identity checks (within profile x scenario: one comparison/physics/exogenous/N_out)
    pairing: dict[str, set] = {}
    for row in rows:
        key = f"{row['profile']}|{row['scenario_id']}"
        pairing.setdefault(key, set()).add((row["comparison_fingerprint"], row["resolved_physics_fingerprint"],
                                            row["exogenous"], row["N_out"]))
    physics_by_profile: dict[str, set] = {}
    for row in rows:
        physics_by_profile.setdefault(row["scenario_id"], set()).add((row["profile"], row["resolved_physics_fingerprint"]))
    distinct_physics = all(len({p for p, _ in v}) == len({f for _, f in v}) for v in physics_by_profile.values())
    repeats = []
    for key, r in records.items():
        item = json.loads(key)
        if item["kind"] != "repeat":
            continue
        twin_item = dict(item, kind="primary")
        twin = records.get(json.dumps(twin_item, sort_keys=True))
        repeats.append({"scenario_id": item["scenario_id"], "identical_trace_digest":
                        twin is not None and twin["digests"]["trace_sha256"] == r["digests"]["trace_sha256"]})
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        g = groups.setdefault(f"{row['profile']}|{row['family']}|{row['arm']}", {"rows": []})
        g["rows"].append(row)
    summary = {}
    for key, g in sorted(groups.items()):
        rs = g["rows"]
        ppo_values = [x for r in rs if r["ppo"] for x in r["ppo"]["occupancy_features"]]
        summary[key] = {
            "runs": len(rs), "status": {s: sum(r["status"] == s for r in rs) for s in sorted({r["status"] for r in rs})},
            "departed": sum(r["departed"] for r in rs), "cargo_fulfilled": sum(r["cargo_fulfilled"] for r in rs),
            "vessels": sum(r["vessels_total"] for r in rs), "rolled_over": sum(r["rolled_over"] for r in rs),
            "N_out": sum(r["N_out"] for r in rs), "U": sum(r["U"] for r in rs),
            "R_per_scenario": [r["R"] for r in rs], "unfinished_moves": sum(r["unfinished_moves"] for r in rs),
            "D24_total_turnaround_mean": statistics.fmean(r["D24_total_turnaround"] for r in rs),
            "mean_wait_mean": statistics.fmean(r["mean_wait"] for r in rs),
            "busiest_block_share_mean": statistics.fmean(r["busiest_block_share"] for r in rs
                                                          if r["busiest_block_share"] is not None),
            "crane_utilization_mean": statistics.fmean(r["crane_utilization"] for r in rs if r["crane_utilization"]),
            "rejections": sum(r["rejections"] for r in rs), "audits_ok": all(r["audits_ok"] for r in rs),
            "outbound_reconciliation_ok": all(r["outbound_reconciliation_ok"] for r in rs),
            "ppo_occupancy_feature": (_q(ppo_values) | {
                "above_training_bound": sum(x > 0.347222 for x in ppo_values),
                "fraction_above": (sum(x > 0.347222 for x in ppo_values) / len(ppo_values)) if ppo_values else None})
            if ppo_values else None,
            "policy_seconds": _q([r["seconds"]["policy"].get("p95", 0.0) for r in rs]),
            "policy_seconds_max": max(r["seconds"]["policy"].get("max", 0.0) for r in rs),
            "view_seconds_mean": statistics.fmean(r["seconds"]["view_build"].get("mean", 0.0) for r in rs),
            "run_wall_seconds": _q([r["run_wall_seconds"] for r in rs]),
        }
    return {"report_version": "itp_pre_step6_report_v1", **FLAGS, "plan_sha256": digest,
            "complete": len(records), "planned": len(plan["items"]),
            "missing_items": [i for i in plan["items"] if json.dumps(i, sort_keys=True) not in records],
            "pairing_identical": {k: len(v) == 1 for k, v in pairing.items()},
            "physics_fingerprints_distinct_across_profiles": distinct_physics,
            "determinism_repeats": repeats, "summary": summary, "rows": rows,
            "interpretation": "DEVELOPMENT_CHARACTERIZATION: descriptive only. No arm, fleet or rule is selected; "
                              "PPO out-of-distribution measurements are reported as OUT_OF_DISTRIBUTION_MEASURED."}


def report(directory: Path) -> Path:
    data = build_report(directory)
    text = json.dumps(data, indent=1, sort_keys=True, allow_nan=False, default=str)
    out = directory / "reports"
    out.mkdir(exist_ok=True)
    path = out / f"report_{hashlib.sha256(text.encode()).hexdigest()[:12]}.json"
    if not path.exists():
        path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_pre_step6_characterization",
                                     description="Pre-Step 6 development characterization (8-crane research profile).")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="write the hashed plan (exclusive) before any run")
    mode.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    mode.add_argument("--run", action="store_true", help="execute missing plan items (resume-safe)")
    mode.add_argument("--report", action="store_true", help="summarize existing records; runs nothing")
    mode.add_argument("--resume", action="store_true", help="same as --run: continue an existing plan")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--limit-runs", type=int)
    parser.add_argument("--kind", action="append", choices=("primary", "sensitivity", "repeat"))
    parser.add_argument("--research-profile", default=PRIMARY,
                        help="must be the approved primary profile; other values are refused (safeguard S3)")
    args = parser.parse_args(argv)
    from integrated_terminal_pilot.benchmark.profiles import ProfileSelectionError, assert_primary_profile_unchanged

    try:
        assert_primary_profile_unchanged(args.research_profile, reason="command line")
        plan = build_plan()
        digest = plan_digest(plan)
        if args.dry_run:
            print(json.dumps({"plan_sha256": digest, "writes": "nothing", **{k: plan[k] for k in (
                "counts", "scenarios", "primary_profile", "sensitivity_profiles", "predeclared_partial_subset",
                "decision_firewall")}}, indent=1, default=str))
            return 0
        if args.plan:
            print(json.dumps({"plan": str(write_plan(plan)), "plan_sha256": digest, "items": len(plan["items"])}))
            return 0
        if args.run or args.resume:
            print(json.dumps(run_plan(progress=args.progress, limit_runs=args.limit_runs,
                                      kinds=tuple(args.kind) if args.kind else None), indent=1))
            return 0
        print(json.dumps({"report": str(report(plan_dir(digest)))}))
        return 0
    except (PreStep6Error, ProfileSelectionError) as error:
        print(f"pre_step6: {error}", file=sys.stderr)
        return 2


__all__ = ["FLAGS", "PRIMARY", "PreStep6Error", "ROOT", "build_plan", "build_report", "main", "plan_digest",
           "run_plan", "write_plan"]
