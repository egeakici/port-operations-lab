"""Run Step 12B locked-record diagnostics or bounded validation-fixture CPU timing."""

from __future__ import annotations

import os

for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[name] = "1"

import argparse
import json
import sys
from pathlib import Path

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.diagnostics import (
    build_diagnostics, verify_step12a, write_csv,
)
from berth_allocation_lab.benchmark.inputs import sha256_file
from berth_allocation_lab.benchmark.latency import fixture_plan, measure_latency
from berth_allocation_lab.tracking.git_metadata import get_git_metadata

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "configs/benchmark/step12_static.yaml"
DYNAMIC = ROOT / "configs/benchmark/step12_dynamic_h240.yaml"
OUTPUT = ROOT / "experiments/benchmark/step12b"


def _json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)


def _prepare(mode: str, diagnostic_id: str) -> Path:
    if not diagnostic_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in diagnostic_id):
        raise BenchmarkError("diagnostic-id must be a safe lowercase name.")
    target = OUTPUT / diagnostic_id
    if target.exists():
        raise BenchmarkError(f"Diagnostic output already exists; never overwrite: {target}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)
    return target


def _finish(target: Path, mode: str, sources: dict) -> None:
    head, dirty = get_git_metadata()
    _json(target / "manifest.json", {
        "status": "completed", "mode": mode, "diagnostic_id": target.name,
        "analysis_git_head": head, "analysis_git_dirty": dirty,
        "source_benchmark_ids": {key: value["benchmark_id"] for key, value in sources.items()},
        "source_manifest_sha256": {key: value["manifest_sha256"]
                                   for key, value in sources.items()},
        "derived_sha256": {path.name: sha256_file(path) for path in target.iterdir()
                           if path.is_file() and path.name != "manifest.json"},
        "training_performed": False, "test_inference_performed": False,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--diagnostics", action="store_true")
    modes.add_argument("--latency", action="store_true")
    parser.add_argument("--diagnostic-id")
    parser.add_argument("--per-family", type=int, default=2)
    parser.add_argument("--passes", type=int, default=3)
    args = parser.parse_args(argv)
    if not any((args.dry_run, args.diagnostics, args.latency)):
        parser.error("Choose --dry-run, --diagnostics or --latency.")
    mode = "latency" if args.latency else "diagnostics"
    diagnostic_id = args.diagnostic_id or ("cpu_latency_v2" if args.latency else "locked_diagnostics_v3")
    try:
        configs = (BenchmarkConfig.load(STATIC), BenchmarkConfig.load(DYNAMIC))
        sources = verify_step12a(configs)
        plan = fixture_plan(configs[1], args.per_family)
        if args.dry_run:
            print(json.dumps({"status": "ready", "source_benchmarks": {
                key: {"id": value["benchmark_id"], "manifest_sha256": value["manifest_sha256"]}
                for key, value in sources.items()},
                "diagnostics_available": True, "requires_test_inference": False,
                "latency_fixture_plan": plan, "latency_training_seed": 11,
                "latency_warmup_passes": 1, "latency_timed_passes": args.passes,
                "latency_estimated_episodes": len(plan) * 3 * (args.passes + 1),
                "latency_status": "pending" if not (OUTPUT / "cpu_latency_v2").exists()
                else "recorded", "output_root": str(OUTPUT)}, indent=2))
            return 0
        target = OUTPUT / diagnostic_id
        if target.exists():
            raise BenchmarkError(f"Diagnostic output already exists; never overwrite: {target}")
        if args.diagnostics:
            result = build_diagnostics(configs[0], configs[1], sources)
            target = _prepare(mode, diagnostic_id)
            for name in ("dynamic_scenario_differences", "dynamic_wait_summary",
                         "dynamic_action_agreement", "dynamic_tail_risk",
                         "dynamic_worst_cases", "static_method_comparison", "static_tail_risk"):
                write_csv(target / f"{name}.csv", result[name])
            _json(target / "dynamic_selected_traces.json", result["dynamic_selected_traces"])
            _json(target / "scientific_findings.json", result["findings"])
            _json(target / "source_references.json", {key: {field: value[field] for field in
                   ("benchmark_id", "manifest_path", "manifest_sha256", "summary_sha256")}
                   for key, value in sources.items()})
            _json(target / "input_audit.json", {"step12a_hashes_verified": True,
                                                  "dynamic_rows_verified": True,
                                                  "static_placements_available": False,
                                                  "latency_status": "pending_or_separate"})
            with (target / "summary.md").open("x", encoding="utf-8") as stream:
                stream.write("# Step 12B Locked-Record Diagnostics\n\n"
                             "Exploratory post-hoc analysis; no training or test inference.\n\n"
                             f"Selected source-grounded traces: {len(result['dynamic_selected_traces'])}.\n"
                             "See CSV/JSON tables for family and seed detail.\n")
        else:
            result = measure_latency(configs[1], per_family=args.per_family, passes=args.passes)
            target = _prepare(mode, diagnostic_id)
            _json(target / "latency_manifest.json", result["manifest"])
            _json(target / "fixture_plan.json", result["fixture_plan"])
            write_csv(target / "latency_measurements.csv", result["measurements"])
            write_csv(target / "latency_decisions.csv", result["decision_samples"])
            write_csv(target / "latency_summary.csv", result["summary"])
            _json(target / "source_references.json", {key: {field: value[field] for field in
                   ("benchmark_id", "manifest_path", "manifest_sha256", "summary_sha256")}
                   for key, value in sources.items()})
        _finish(target, mode, sources)
        print(json.dumps({"status": "completed", "mode": mode, "output": str(target)}))
        return 0
    except (BenchmarkError, FileNotFoundError, KeyError, ValueError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
