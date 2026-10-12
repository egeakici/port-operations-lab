"""Step 4 developer workflow: physical smoke runs, trace validation, replay, equivalence, timing.

Everything here is a *correctness and engineering* tool. The berth decisions come from the
labelled physical integration fixture (Project 03 online FCFS over the kernel's legal set);
cranes and yard use the Step 3 primitives P_c / P_y. No policy is compared, no PPO is loaded
and only development scenarios are used. Outputs go to the Git-ignored ``experiments/``
directory and runs are written exclusively (an existing run directory is never overwritten).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT
from integrated_terminal_pilot.simulator.catalog import ScenarioCatalog
from integrated_terminal_pilot.simulator.drivers import default_policies, run_episode
from integrated_terminal_pilot.simulator.kernel import TerminalKernel
from integrated_terminal_pilot.simulator.trace import trace_digest, validate_trace_dir, write_trace

SMOKE_ROOT = PROJECT_ROOT / "experiments" / "step4_smoke"
EQUIVALENCE_ROOT = PROJECT_ROOT / "experiments" / "step4_equivalence"
PERFORMANCE_ROOT = PROJECT_ROOT / "experiments" / "step4_performance"
DEV_RUN = PROJECT_ROOT / "experiments" / "scenarios" / "development" / "dev_f5789d8c91_1ee66026"
LABEL = "primitive-FCFS physical smoke (integration fixture; NOT a Step 5 policy run)"


def load_source(source: dict[str, Any]) -> dict[str, Any]:
    """A development scenario from a file, or generated in memory (development split only)."""
    from integrated_terminal_pilot.scenarios import generate_scenario, load_generator_config, load_scenario

    if source.get("scenario_file"):
        doc = load_scenario(source["scenario_file"])
    else:
        doc = generate_scenario(load_generator_config(), source["family"], "development", int(source["seed"]),
                                source.get("profile", "standard_v1"))
    if doc["identity"]["split"] != "development":
        raise SystemExit("Step 4 tools accept development scenarios only.")
    return doc


def default_source(family: str, seed: int, profile: str) -> dict[str, Any]:
    stored = DEV_RUN / "scenarios" / f"{family}_development_seed{seed}.scenario.json"
    if profile == "standard_v1" and stored.exists():
        return {"scenario_file": str(stored)}
    return {"family": family, "seed": seed, "profile": profile}


def _condition(options: dict[str, Any]):
    from integrated_terminal_pilot.simulator.diagnostics import DiagnosticCondition

    return DiagnosticCondition(options.get("yard_policy", "yard_first_fit_v1"), options.get("crane_count") or 4,
                               options.get("efficiency_basis", "assigned"))


def run_once(doc: dict[str, Any], options: dict[str, Any]) -> tuple[TerminalKernel, Any, dict[str, float]]:
    from integrated_terminal_pilot.policies import create_policy
    from integrated_terminal_pilot.simulator.diagnostics import build_condition_catalog

    timings: dict[str, float] = {}
    condition = _condition(options)
    t0 = time.perf_counter()
    if condition.is_reference and not options.get("crane_count"):
        catalog = ScenarioCatalog.from_document(doc, validate=options.get("validate", True))
    else:  # Step 4 closure diagnostic override (in memory; source scenario untouched)
        catalog, _ = build_condition_catalog(doc, condition, validate=options.get("validate", True))
    timings["catalog_seconds"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    kernel = TerminalKernel.from_catalog(catalog, invariant_mode=options.get("invariants", "cheap"),
                                         full_check_interval=options.get("full_check_interval", 0))
    timings["kernel_init_seconds"] = time.perf_counter() - t0
    policies = default_policies()
    policies["yard_policy"] = create_policy(condition.yard_policy_id)
    run = run_episode(kernel, **policies, until_min=options.get("until_min"),
                      max_decisions=options.get("max_decisions"), max_cycles=options.get("max_cycles"))
    timings["run_seconds"] = run.wall_seconds
    return kernel, run, timings


def yard_diagnostics(kernel: TerminalKernel, result: dict[str, Any]) -> dict[str, Any]:
    """Resource-demand arithmetic next to observed block usage (bottleneck reality check, brief §44)."""
    elapsed = max(kernel.current_time_min, 1e-9)
    blocks = result["blocks"]
    busiest = max(blocks, key=lambda b: blocks[b]["handled_moves"]) if blocks else None
    mu = {b: blocks[b]["handling_capacity_moves_per_hour"] for b in blocks}
    return {
        "block_handling_capacity_moves_per_hour": sorted(set(mu.values())),
        "two_crane_vessel_demand_moves_per_hour": 2 * 30.0 * 0.92,
        "ship_side_share_with_landside_demand_moves_per_hour": sorted({0.8 * m for m in mu.values()}),
        "busiest_block": busiest,
        "busiest_block_busy_fraction": blocks[busiest]["busy_min"] / elapsed if busiest else None,
        "block_handled_moves": {b: round(blocks[b]["handled_moves"], 3) for b in sorted(blocks)},
        "peak_block_occupancy_fraction": result["kpi"]["peak_block_occupancy_fraction"],
        "crane_yard_shortfall_moves": result["kpi"]["crane_yard_shortfall_moves"],
        "crane_transport_shortfall_moves": result["kpi"]["crane_transport_shortfall_moves"],
        "yard_capacity_blocked_crane_min": result["kpi"]["yard_blocked_crane_min"],
        "gate_waiting_container_min": result["kpi"]["gate_waiting_container_min"],
        "mean_pickup_delay_min": result["kpi"]["mean_pickup_delay_min"],
        "peak_concurrent_landside_batches_per_block": result["kpi"]["peak_concurrent_landside_batches_per_block"],
    }


def summarize(kernel: TerminalKernel, run, result: dict[str, Any]) -> dict[str, Any]:
    kpi = result["kpi"]
    keys = ("total_turnaround_min", "mean_turnaround_min", "total_berth_waiting_min", "mean_realized_occupancy_min",
            "mean_handling_duration_min", "crane_productive_min", "crane_idle_min", "crane_blocked_min_by_reason",
            "crane_utilization", "container_throughput", "teu_throughput", "crane_moves_completed",
            "unfinished_workload_moves", "rolled_over_containers", "peak_yard_occupancy_teu", "makespan_min")
    return {
        "label": LABEL,
        "scenario_id": result["scenario_id"],
        "status": run.status,
        "kernel_status": kernel.status,
        "status_reason": result["status_reason"],
        "end_time_min": result["end_time_min"],
        "T_end_min": result["T_end_min"],
        "rejections": run.rejections,
        "failure": run.failure,
        "decisions": run.decisions,
        "counts": result["counts"],
        "kpi": {k: kpi[k] for k in keys},
        "audits_ok": result["audits"]["ok"],
        "audits": {k: v.get("ok") for k, v in result["audits"].items() if isinstance(v, dict)},
        "unresolved": result["status_details"].get("unresolved_vessels") if result["status"] != "COMPLETED" else None,
        "yard": yard_diagnostics(kernel, result),
    }


def cmd_smoke(args: argparse.Namespace) -> int:
    source = ({"scenario_file": args.scenario_file} if args.scenario_file
              else default_source(args.family, args.seed, args.profile))
    doc = load_source(source)
    options = {"until_min": args.until_min, "max_cycles": args.max_cycles, "max_decisions": args.max_decisions,
               "invariants": args.invariants, "full_check_interval": args.full_check_interval,
               "yard_policy": args.yard_policy, "crane_count": args.crane_count,
               "efficiency_basis": args.efficiency_basis}
    t0 = time.perf_counter()
    kernel, run, timings = run_once(doc, options)
    t1 = time.perf_counter()
    result = kernel.result()
    timings["result_and_audits_seconds"] = time.perf_counter() - t1
    timings["total_seconds"] = time.perf_counter() - t0
    summary = summarize(kernel, run, result)
    condition = _condition(options)
    summary["condition"] = {"condition_id": condition.condition_id, "is_reference": condition.is_reference,
                            "note": None if condition.is_reference else
                            "DIAGNOSTIC OVERRIDE (Step 4 closure): not the reference physics/policy"}
    summary["service_compliance"] = result["service_compliance"]
    summary["trace_sha256"] = trace_digest(kernel, rejections=run.rejections, result=result)
    if args.repeat:
        again, again_run, _ = run_once(doc, options)
        summary["repeat_trace_sha256"] = trace_digest(again, rejections=again_run.rejections)
        summary["deterministic_replay"] = summary["repeat_trace_sha256"] == summary["trace_sha256"]
    summary["timings"] = timings
    if not args.no_write:
        run_id = args.run_id or (f"{doc['identity']['scenario_id']}__"
                                 f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        out = Path(args.out_root) / run_id
        manifest = write_trace(kernel, out, run_id=run_id, rejections=run.rejections, mode=args.trace_mode,
                               result=result,
                               engineering={"timings": timings, "python": sys.version,
                                            "platform": platform.platform()},
                               metadata={"label": LABEL, "source": source, "options": options,
                                         "policies": {"berth": "fixture_p03_online_fcfs",
                                                      "crane": "primitive_crane_greedy_v1",
                                                      "yard": "yard_first_fit_v1"}})
        summary["run_dir"] = str(out)
        summary["trace_mode"] = args.trace_mode
        summary["trace_sizes_bytes"] = manifest["sizes_bytes"]
        summary["files_written"] = manifest["files_written"]
    print(json.dumps(summary, indent=1, sort_keys=True, default=str))
    return 0 if summary["status"] != "FAILED" and summary["audits_ok"] else 1


def cmd_validate(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    doc = load_source(manifest["source"])
    report = validate_trace_dir(run_dir, doc)
    if manifest.get("trace_mode") == "summary" and not args.replay:
        report["hint"] = "summary traces are digest-verifiable: re-run with --replay"
    if args.replay and manifest.get("trace_mode") == "summary":
        report["ok"] = True
        report["issues"] = []
    if args.replay:
        kernel, run, _ = run_once(doc, manifest["options"])
        replayed = trace_digest(kernel, rejections=run.rejections)
        report["replay_trace_sha256"] = replayed
        report["deterministic_replay"] = replayed == manifest["trace_sha256"]
        report["ok"] = report["ok"] and report["deterministic_replay"]
    if args.show_state:
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        report["final"] = {"status": result["status"], "status_reason": result["status_reason"],
                           "end_time_min": result["end_time_min"], "kpi": result["kpi"],
                           "audits_ok": result["audits"]["ok"]}
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0 if report["ok"] else 1


def cmd_equivalence(args: argparse.Namespace) -> int:
    from integrated_terminal_pilot.scenarios import generate_scenario, load_generator_config
    from integrated_terminal_pilot.simulator.equivalence import degenerate_equivalence

    config = load_generator_config()
    plan = dict(item.split("=") for item in (args.family or ["itp_medium=30", "itp_heavy=30", "itp_low=10",
                                                             "itp_yard_bottleneck=10"]))
    rows = []
    started = time.perf_counter()
    for family, count in plan.items():
        for seed in range(args.first_seed, args.first_seed + int(count)):
            doc = generate_scenario(config, family, "development", seed, "degenerate_equivalence_v1")
            report = degenerate_equivalence(doc, validate=not args.no_validate)
            rows.append(report)
            print(f"{family} {seed} pass={report['pass']} vessels={report['vessels']} cranes={report['cranes']} "
                  f"max_start_err={report['errors']['max_start_min']:.2e}", flush=True)
    summary = {
        "label": "Step 4 degenerate equivalence: integrated kernel (FCFS fixture + P_c/P_y) vs Project 03 "
                 "DynamicBAPEnv + online_fcfs_action on the berth projection",
        "plan": plan, "first_seed": args.first_seed, "scenarios": len(rows),
        "passed": sum(r["pass"] for r in rows), "failed": [r["scenario_id"] for r in rows if not r["pass"]],
        "max_errors": {k: max(r["errors"][k] for r in rows) for k in rows[0]["errors"]} if rows else {},
        "cargo_unavailable_crane_min_total": sum(r["integrated"]["cargo_unavailable_crane_min"] for r in rows),
        "yard_capacity_crane_min_total": sum(r["integrated"]["yard_capacity_crane_min"] for r in rows),
        "rolled_over_total": sum(r["integrated"]["rolled_over_containers"] for r in rows),
        "wall_seconds": time.perf_counter() - started,
    }
    if not args.no_write:
        out = Path(args.out_root) / datetime.now(timezone.utc).strftime("eq_%Y%m%dT%H%M%SZ")
        out.mkdir(parents=True, exist_ok=False)
        (out / "report.json").write_text(json.dumps({"summary": summary, "scenarios": rows}, indent=1,
                                                    sort_keys=True), encoding="utf-8")
        summary["report"] = str(out / "report.json")
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0 if summary["passed"] == summary["scenarios"] else 1


def _deep_size(obj, seen=None) -> int:
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return 0
    seen.add(id(obj))
    size = sys.getsizeof(obj)
    if isinstance(obj, dict):
        size += sum(_deep_size(k, seen) + _deep_size(v, seen) for k, v in obj.items())
    elif isinstance(obj, (list, tuple, set)):
        size += sum(_deep_size(v, seen) for v in obj)
    elif hasattr(obj, "__dataclass_fields__"):
        size += sum(_deep_size(getattr(obj, f), seen) for f in obj.__dataclass_fields__)
    return size


def cmd_measure(args: argparse.Namespace) -> int:
    """Engineering measurements (not an SLA): load, init, event step, action, clone time/memory, run, trace."""
    from integrated_terminal_pilot.scenarios import load_scenario

    source = default_source(args.family, args.seed, "standard_v1")
    out: dict[str, Any] = {"scenario": source, "python": sys.version, "platform": platform.platform()}
    t0 = time.perf_counter()
    doc = load_scenario(source["scenario_file"]) if "scenario_file" in source else load_source(source)
    out["scenario_load_seconds"] = time.perf_counter() - t0
    out["scenario_file_bytes"] = Path(source["scenario_file"]).stat().st_size if "scenario_file" in source else None
    t0 = time.perf_counter()
    catalog = ScenarioCatalog.from_document(doc, validate=True)
    out["catalog_build_with_step2_validation_seconds"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    catalog = ScenarioCatalog.from_document(doc, validate=False)
    out["catalog_build_seconds"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    kernel = TerminalKernel.from_catalog(catalog, invariant_mode="cheap")
    out["kernel_init_seconds"] = time.perf_counter() - t0
    policies = default_policies()
    run_episode(kernel, **policies, until_min=args.clone_at_min)
    state = kernel.state
    out["clone_state"] = {"time_min": state.now_min, "active_work_orders": len(state.work_orders),
                          "pending_events": len(state.events), "ledger_records": len(state.ledger),
                          "containers": len(catalog.containers)}
    repeats = args.repeats
    t0 = time.perf_counter()
    for _ in range(repeats):
        kernel.clone()
    out["clone_seconds_mean"] = (time.perf_counter() - t0) / repeats
    t0 = time.perf_counter()
    for _ in range(repeats):
        kernel.observable_clone()
    out["observable_clone_seconds_mean"] = (time.perf_counter() - t0) / repeats
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    clone = kernel.clone()
    out["clone_traced_allocation_bytes"] = tracemalloc.get_traced_memory()[0] - before
    tracemalloc.stop()
    out["clone_mutable_state_deep_bytes_excluding_shared_ledger_records"] = _deep_size(
        {k: v for k, v in vars(clone.state).items() if k not in ("ledger", "event_log")})
    out["catalog_deep_bytes_shared_not_copied"] = _deep_size(catalog.containers)
    # One event step and one decision application.
    probe = kernel.clone()
    while probe.advance().__class__.__name__ == "DecisionRequest":
        request = probe.pending_decision
        if request.kind == "YARD":
            obs = probe.yard_observation()
            action = policies["yard_policy"].decide(obs)
            t0 = time.perf_counter()
            probe.apply_yard_action(action)
            out["one_yard_action_apply_seconds"] = time.perf_counter() - t0
            break
        if request.kind == "CRANE":
            probe.apply_crane_action(policies["crane_policy"].decide(probe.crane_observation()))
        else:
            probe.apply_berth_action(policies["berth_policy"].decide(probe.berth_view()))
    probe = kernel.clone()
    steps, t0 = 0, time.perf_counter()
    while steps < 200 and probe.status == "RUNNING":
        request = probe.advance()
        if request.__class__.__name__ != "DecisionRequest":
            break
        if request.kind == "BERTH":
            probe.apply_berth_action(policies["berth_policy"].decide(probe.berth_view()))
        elif request.kind == "CRANE":
            probe.apply_crane_action(policies["crane_policy"].decide(probe.crane_observation()))
        else:
            probe.apply_yard_action(policies["yard_policy"].decide(probe.yard_observation()))
        steps += 1
    out["mean_seconds_per_decision_step_with_events"] = (time.perf_counter() - t0) / max(steps, 1)
    cycles_before, t0 = kernel.state.cycles, time.perf_counter()
    run = run_episode(kernel, **policies)
    elapsed = time.perf_counter() - t0
    out["remaining_run_seconds"] = elapsed
    out["mean_seconds_per_kernel_cycle"] = elapsed / max(kernel.state.cycles - cycles_before, 1)
    out["final_status"] = run.status
    out["kernel_cycles"] = kernel.state.cycles
    t0 = time.perf_counter()
    result = kernel.result()
    out["result_and_audits_seconds"] = time.perf_counter() - t0
    out["audits_ok"] = result["audits"]["ok"]
    from integrated_terminal_pilot.simulator.trace import canonical_files

    files = canonical_files(kernel, rejections=run.rejections)
    out["trace_sizes_bytes"] = {name: len(text.encode("utf-8")) for name, text in files.items()}
    if not args.no_write:
        path = Path(args.out_root) / datetime.now(timezone.utc).strftime(f"perf_{args.family}_%Y%m%dT%H%M%SZ.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(out, indent=1, sort_keys=True, default=str))
        out["written"] = str(path)
    print(json.dumps(out, indent=1, sort_keys=True, default=str))
    return 0


def cmd_closure(args: argparse.Namespace) -> int:
    from integrated_terminal_pilot.simulator import closure

    if args.plan:
        plan_dir, plan, digest = closure.ensure_plan(reason=args.deviation_reason)
        print(json.dumps({"plan_dir": str(plan_dir), "plan_sha256": digest, "unique_runs": plan["unique_runs"],
                          "conditions": [c["condition_id"] for c in plan["conditions"]]}, indent=1))
        return 0
    if args.report:
        report = closure.build_report()
        print(json.dumps({k: report[k] for k in ("plan_sha256", "unique_runs_planned", "runs_executed",
                                                 "report_path", "selection_statement")}, indent=1))
        return 0
    shard = tuple(int(x) for x in args.shard.split("/")) if args.shard else None
    outcome = closure.run_campaign(resume=args.resume, limit_runs=args.limit_runs, progress=args.progress,
                                   dry_run=args.dry_run, reason=args.deviation_reason, shard=shard)
    print(json.dumps(outcome, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project I Step 4 integrated-kernel developer tools.")
    sub = parser.add_subparsers(dest="command", required=True)
    smoke = sub.add_parser("smoke", help=LABEL)
    smoke.add_argument("--family", default="itp_low")
    smoke.add_argument("--seed", type=int, default=10_000_000)
    smoke.add_argument("--profile", default="standard_v1", choices=("standard_v1", "degenerate_equivalence_v1"))
    smoke.add_argument("--scenario-file")
    smoke.add_argument("--until-min", type=float)
    smoke.add_argument("--max-cycles", type=int)
    smoke.add_argument("--max-decisions", type=int)
    smoke.add_argument("--invariants", default="cheap", choices=("full", "cheap", "off"))
    smoke.add_argument("--full-check-interval", type=int, default=0)
    smoke.add_argument("--repeat", action="store_true", help="run twice and compare canonical trace digests")
    smoke.add_argument("--out-root", default=str(SMOKE_ROOT))
    smoke.add_argument("--run-id")
    smoke.add_argument("--no-write", action="store_true")
    smoke.add_argument("--trace-mode", default="full", choices=("full", "summary"))
    smoke.add_argument("--yard-policy", default="yard_first_fit_v1",
                       choices=("yard_first_fit_v1", "yard_occupancy_balance_v1"),
                       help="reference: yard_first_fit_v1 (AM-01 balanced is PROPOSED, diagnostic only)")
    smoke.add_argument("--crane-count", type=int, help="DIAGNOSTIC fleet override (development only)")
    smoke.add_argument("--efficiency-basis", default="assigned", choices=("assigned", "working"),
                       help="reference: assigned; working is a diagnostic override")
    smoke.set_defaults(func=cmd_smoke)
    validate = sub.add_parser("validate", help="validate a written trace (optionally replay it)")
    validate.add_argument("--run-dir", required=True)
    validate.add_argument("--replay", action="store_true")
    validate.add_argument("--show-state", action="store_true")
    validate.set_defaults(func=cmd_validate)
    equivalence = sub.add_parser("equivalence", help="degenerate equivalence gate against Project 03")
    equivalence.add_argument("--family", action="append", help="family=count (repeatable)")
    equivalence.add_argument("--first-seed", type=int, default=10_000_000)
    equivalence.add_argument("--no-validate", action="store_true")
    equivalence.add_argument("--out-root", default=str(EQUIVALENCE_ROOT))
    equivalence.add_argument("--no-write", action="store_true")
    equivalence.set_defaults(func=cmd_equivalence)
    measure = sub.add_parser("measure", help="engineering timing and clone-cost measurements")
    measure.add_argument("--family", default="itp_heavy")
    measure.add_argument("--seed", type=int, default=10_000_000)
    measure.add_argument("--clone-at-min", type=float, default=1500.0)
    measure.add_argument("--repeats", type=int, default=20)
    measure.add_argument("--out-root", default=str(PERFORMANCE_ROOT))
    measure.add_argument("--no-write", action="store_true")
    measure.set_defaults(func=cmd_measure)
    closure_parser = sub.add_parser("closure", help="Step 4 closure development characterization (FCFS only)")
    mode = closure_parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="write/verify the hashed pre-run plan only")
    mode.add_argument("--dry-run", action="store_true", help="show planned/completed counts, run nothing")
    mode.add_argument("--report", action="store_true", help="summarize executed runs (no new runs)")
    closure_parser.add_argument("--resume", action="store_true", help="continue after verifying existing runs")
    closure_parser.add_argument("--limit-runs", type=int, help="execute at most N new runs")
    closure_parser.add_argument("--progress", action="store_true")
    closure_parser.add_argument("--deviation-reason", help="required to record a changed plan")
    closure_parser.add_argument("--shard", help="K/N: execute only runs with plan index mod N == K (parallel)")
    closure_parser.set_defaults(func=cmd_closure)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


__all__ = ["build_parser", "load_source", "main", "run_once", "summarize", "yard_diagnostics"]
