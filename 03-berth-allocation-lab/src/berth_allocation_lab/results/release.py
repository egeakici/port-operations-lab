"""Exclusive final release build, provenance, archive inventory and verifier."""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from berth_allocation_lab.benchmark.config import BenchmarkError
from berth_allocation_lab.benchmark.inputs import sha256_file
from berth_allocation_lab.results.ingest import PRIMARY, SourceBundle, ingest, verify_sources
from berth_allocation_lab.results.queries import run_documented_queries
from berth_allocation_lab.results.reporting import (
    EXPORTS, FIGURE_SOURCES, LIMITATIONS, export_tables, render_figures, verify_tables,
)
from berth_allocation_lab.results.schema import SCHEMA_VERSION, row_counts
from berth_allocation_lab.tracking.git_metadata import get_git_metadata

DEFAULT_RELEASE_ID = "project03_final_v1"
DEFAULT_ROOT = Path("experiments/results/project03")


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)


def _git_tracked(root: Path, relative: str) -> bool:
    command = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                             cwd=root, capture_output=True, check=False)
    return command.returncode == 0


def backup_inventory(bundle: SourceBundle, release_dir: Path) -> dict[str, Any]:
    """List actual required files; archive creation remains an explicit user action."""
    rows = []
    for relative, digest in sorted(bundle.artifact_hashes.items()):
        role = ("selected_checkpoint" if relative.endswith(".zip") else
                "decision_or_sidecar" if "validation_decision" in relative else
                "step12_primary" if "/benchmark/" in relative else
                "frozen_evaluation_or_manifest")
        rows.append({"path": relative, "role": role, "file_count": 1,
                     "sha256": digest, "git_tracked": _git_tracked(bundle.root, relative),
                     "required_for_scientific_reproduction": True})
    release_relative = release_dir.relative_to(bundle.root).as_posix()
    rows.append({"path": release_relative, "role": "step13_final_release",
                 "file_count_at_inventory": sum(p.is_file() for p in release_dir.rglob("*")),
                 "sha256": None, "hash_reference": "manifest.json per-file hashes",
                 "git_tracked": False, "required_for_scientific_reproduction": True})
    return {"project": "03-berth-allocation-lab", "archive_created": False,
            "root": str(bundle.root), "entries": rows,
            "note": "Git alone does not include ignored experiments. A ZIP is optional and never automatic."}


def _close(value: Any, expected: Any, label: str, tol: float = 1e-6) -> None:
    if value is None or expected is None or not math.isclose(float(value), float(expected),
                                                               rel_tol=0, abs_tol=tol):
        raise BenchmarkError(f"Final release reconciliation failed: {label}: {value} != {expected}")


def _check_database(connection: sqlite3.Connection, bundle: SourceBundle) -> dict[str, Any]:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise BenchmarkError("SQLite integrity_check failed.")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise BenchmarkError("SQLite foreign-key check failed.")
    version = connection.execute("SELECT version FROM schema_info").fetchone()
    if version is None or version[0] != SCHEMA_VERSION:
        raise BenchmarkError("Unexpected warehouse schema version.")
    for table in ("experiments", "scenarios", "scenario_results", "aggregate_metrics",
                  "scenario_differences", "paired_comparisons", "uncertainty_intervals",
                  "diagnostic_metrics", "latency_metrics", "artifacts"):
        if not any(row[3] == "pk" for row in connection.execute(f"PRAGMA index_list({table})")):
            raise BenchmarkError(f"Warehouse uniqueness constraint missing: {table}")
    counts = row_counts(connection)
    if (counts["experiments"] != 18 or counts["scenarios"] != 500 or
            counts["uncertainty_intervals"] != 56 or counts["latency_metrics"] != 6):
        raise BenchmarkError(f"Required release coverage missing: {counts}")
    branches = connection.execute("SELECT branch, COUNT(*) FROM scenarios GROUP BY branch").fetchall()
    if dict(branches) != {"dynamic": 250, "static": 250}:
        raise BenchmarkError("Static/Dynamic physical scenario coverage differs.")
    if connection.execute("SELECT COUNT(*) FROM scenarios WHERE split <> 'test'").fetchone()[0]:
        raise BenchmarkError("Non-test scenarios leaked into the final results warehouse.")
    coverage = connection.execute("""SELECT branch, source_version, method, seed_label, COUNT(*)
        FROM scenario_results GROUP BY branch, source_version, method, seed_label""").fetchall()
    for branch, version_name, method, seed, count in coverage:
        expected = (150 if method == "candidate_space_exact" else 250)
        if count != expected or (method == "candidate_space_exact" and branch != "static"):
            raise BenchmarkError(f"Incomplete scenario-result coverage: {branch}/{version_name}/{method}/{seed}")
    if len(coverage) != 20:
        raise BenchmarkError("Required method/version/seed coverage missing.")
    seed_rows = connection.execute("""SELECT regime, GROUP_CONCAT(DISTINCT training_seed)
        FROM experiments WHERE branch='dynamic' GROUP BY regime""").fetchall()
    if len(seed_rows) != 2 or any(set(map(int, value.split(","))) != {11, 23, 37}
                                  for _, value in seed_rows):
        raise BenchmarkError("Dynamic three-seed coverage missing.")
    if connection.execute("""SELECT COUNT(*) FROM scenario_results
        WHERE method='ppo_seed_mean' AND training_seed IS NOT NULL""").fetchone()[0]:
        raise BenchmarkError("Three-seed mean was mislabeled as a trained seed.")
    summaries = bundle.read_json("dynamic", "summary.json")["regimes"]
    for item in summaries:
        regime = item["regime"]
        def metric(method: str, name: str = "mean_total_waiting_time_min"):
            result = connection.execute("""SELECT value FROM aggregate_metrics WHERE
                branch='dynamic' AND regime=? AND family='WEIGHTED'
                AND method=? AND metric_name=?""", (regime, method, name)).fetchone()
            return result[0] if result else None
        _close(metric("fcfs"), item["fcfs_weighted_mean_min"], f"{regime}/fcfs")
        _close(metric("rollout"), item["rollout_weighted_mean_min"], f"{regime}/rollout")
        _close(metric("ppo_seed_mean"), item["ppo_seed_mean_weighted_min"], f"{regime}/ppo")
        _close(metric("ppo_seed_mean", "gap_closed"), item["gap_closed_seed_mean"],
               f"{regime}/gap_closed")
        _close((metric("fcfs") - metric("ppo_seed_mean")) /
               (metric("fcfs") - metric("rollout")), metric("ppo_seed_mean", "gap_closed"),
               f"{regime}/gap_formula")
    static_summary = bundle.read_json("static", "summary.json")
    for item in static_summary["regimes"]:
        stored = connection.execute("""SELECT value FROM aggregate_metrics WHERE
            branch='static' AND regime=? AND source_version=? AND family='WEIGHTED'
            AND method='ppo_seed_mean' AND metric_name='mean_total_waiting_time_min'""",
            (item["regime"], item["version"])).fetchone()
        _close(stored[0] if stored else None, item["ppo_seed_mean_weighted_min"],
               f"static/{item['regime']}/{item['version']}")
    for branch in ("static", "dynamic"):
        for row in bundle.read_csv(branch, "bootstrap_intervals.csv"):
            label = row["training_seed"] or "none"
            stored = connection.execute("""SELECT estimate, lower_bound, upper_bound FROM
                uncertainty_intervals WHERE branch=? AND regime=? AND source_version=? AND family=?
                AND candidate_method=? AND reference_method=? AND training_seed_rule=?""",
                (branch, row["regime"], row["source_version"], row["family"], row["method"],
                 row["reference"], label)).fetchone()
            if stored is None:
                raise BenchmarkError("Frozen bootstrap row missing from warehouse.")
            for actual, expected in zip(stored, (row["estimate_min"], row["ci_lower_min"],
                                                 row["ci_upper_min"])):
                _close(actual, expected, "bootstrap_interval")
    for row in bundle.read_csv("latency", "latency_summary.csv"):
        stored = connection.execute("""SELECT mean_decision_ms, median_decision_ms,
            p95_decision_ms, max_decision_ms FROM latency_metrics WHERE regime=? AND method=?""",
            (row["regime"], row["method"])).fetchone()
        if stored is None:
            raise BenchmarkError("Frozen latency row missing from warehouse.")
        for field, value in zip(("weighted_mean_decision_ms", "median_decision_ms",
                                 "p95_decision_ms", "max_decision_ms"), stored):
            _close(value, row[field], f"latency/{row['regime']}/{row['method']}/{field}")
    expected_tail = bundle.read_csv("diagnostics", "dynamic_tail_risk.csv")
    for row in expected_tail:
        if row["method"] != "ppo" or row["training_seed"] != "11":
            continue
        value = connection.execute("""SELECT value FROM diagnostic_metrics WHERE
            regime=? AND family=? AND method='ppo' AND seed_label='11'
            AND metric_name='p95_scenario_total_min'""",
            (row["regime"], row["family"])).fetchone()
        _close(value[0] if value else None, row["p95_scenario_total_min"], "tail_p95")
    queries = run_documented_queries(connection)
    if any(count == 0 for count in queries.values()):
        raise BenchmarkError(f"A documented SQL query returned no data: {queries}")
    return {"schema_version": SCHEMA_VERSION, "row_counts": counts,
            "documented_query_row_counts": queries,
            "source_reconciliation": "passed", "sqlite_integrity": "ok"}


def _verify_release_files(target: Path, manifest: dict, bundle: SourceBundle,
                          *, building: bool = False) -> None:
    expected = ("building", "pending") if building else ("completed", "passed")
    if (manifest.get("status"), manifest.get("verification_status")) != expected:
        raise BenchmarkError("Final release manifest is not completed/verified.")
    if (manifest.get("release_id") != target.name or manifest.get("project_step") != 13 or
            manifest.get("warehouse_schema_version") != SCHEMA_VERSION):
        raise BenchmarkError("Final release identity/schema mismatch.")
    for key in ("training_performed", "test_inference_performed", "new_diagnostic_scenarios_generated"):
        if manifest.get(key) is not False:
            raise BenchmarkError(f"Forbidden final release activity flag: {key}")
    if manifest.get("source_manifest_hashes") != bundle.manifest_hashes or manifest.get(
            "source_benchmark_ids") != {key: path.name for key, path in bundle.paths.items()}:
        raise BenchmarkError("Final source-chain hashes/IDs changed.")
    for name, digest in manifest["release_file_sha256"].items():
        if sha256_file(target / name) != digest:
            raise BenchmarkError(f"Final release file hash mismatch: {target / name}")
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    if actual != set(manifest["release_file_sha256"]) | {"manifest.json"}:
        raise BenchmarkError("Unexpected or missing file in final release directory.")
    if manifest["warehouse_sha256"] != sha256_file(target / "project03_results.sqlite"):
        raise BenchmarkError("Warehouse SHA-256 changed.")
    if manifest["report_hash"] != sha256_file(target / "report/project03_final_report.md"):
        raise BenchmarkError("Final report SHA-256 changed.")
    source_rows = json.loads((target / "provenance/source_artifacts.json").read_text(encoding="utf-8"))
    inventory = json.loads((target / "provenance/backup_manifest.json").read_text(encoding="utf-8"))
    expected = {item["path"]: item["sha256"] for item in source_rows}
    archived = {item["path"]: item["sha256"] for item in inventory["entries"]
                if item.get("role") != "step13_final_release"}
    release_entries = [item for item in inventory["entries"]
                       if item.get("role") == "step13_final_release"]
    if (len(expected) != len(source_rows) or expected != archived or
            len(expected) != manifest["source_artifact_count"] or
            len(release_entries) != 1 or
            release_entries[0]["path"] != target.relative_to(bundle.root).as_posix()):
        raise BenchmarkError("Backup/source artifact inventory mismatch.")
    for relative, digest in expected.items():
        path = (bundle.root / relative).resolve()
        if not path.is_relative_to(bundle.root) or sha256_file(path) != digest:
            raise BenchmarkError(f"Backup source file changed: {relative}")
    for figure, table in manifest["figure_source_tables"].items():
        if not (target / "figures" / figure).is_file() or not (target / "tables" / table).is_file():
            raise BenchmarkError(f"Figure has no machine-readable source table: {figure}")
    for document in ("docs/project03_final_report.md", "docs/project03_results_queries.md",
                     "docs/scientific_benchmark_results.md"):
        if not (bundle.root / document).is_file():
            raise BenchmarkError(f"Final documentation missing: {document}")
    report = (target / "report/project03_final_report.md").read_text(encoding="utf-8")
    if not all(name in report for name in ("static_summary.csv", "dynamic_summary.csv",
                                                 "latency_summary.csv", "bootstrap_intervals.csv")):
        raise BenchmarkError("Final report lacks machine-readable table links.")
    if any(p.suffix in {".zip", ".pt", ".pth"} for p in target.rglob("*")):
        raise BenchmarkError("Unexpected model/training artifact in final release.")


def verify_release(target: Path, *, bundle: SourceBundle | None = None,
                   _building: bool = False) -> dict[str, Any]:
    target = target.resolve()
    root = (next((parent for parent in target.parents
                  if (parent / "experiments/benchmark/step12").is_dir()), None)
            if bundle is None else bundle.root)
    if root is None:
        raise BenchmarkError(f"Cannot find Project 03 source root above {target}")
    bundle = bundle or verify_sources(root)
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file():
        raise BenchmarkError(f"Final release manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_release_files(target, manifest, bundle, building=_building)
    uri = f"file:{(target / 'project03_results.sqlite').as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        checks = _check_database(connection, bundle)
        verify_tables(connection, target / "tables")
    if checks["row_counts"] != manifest["row_counts"]:
        raise BenchmarkError("Final release row counts changed.")
    if checks["row_counts"]["artifacts"] != manifest["source_artifact_count"]:
        raise BenchmarkError("Source artifact inventory count changed.")
    return {"status": "passed", "release_id": target.name,
            "manifest_sha256": sha256_file(manifest_path), **checks}


def dry_run(root: Path, release_id: str = DEFAULT_RELEASE_ID) -> dict[str, Any]:
    bundle = verify_sources(root)
    target = bundle.root / DEFAULT_ROOT / release_id
    with closing(sqlite3.connect(":memory:")) as connection:
        counts = ingest(connection, bundle)
        _check_database(connection, bundle)
    return {"status": "ready", "release_id": release_id, "output_path": str(target),
            "output_already_exists": target.exists(),
            "primary_sources": {key: {"path": str(path), "manifest_sha256":
                             bundle.manifest_hashes[key]} for key, path in bundle.paths.items()},
            "source_artifact_count": len(bundle.artifact_hashes), "expected_row_counts": counts,
            "predicted_tables": [*EXPORTS, "limitations.csv"],
            "predicted_figures": list(FIGURE_SOURCES),
            "training_or_inference_required": False}


def build_release(root: Path, release_id: str = DEFAULT_RELEASE_ID,
                  *, output_root: Path | None = None) -> Path:
    bundle = verify_sources(root)
    if (not release_id or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                              for c in release_id)):
        raise BenchmarkError("Release ID must be a safe lowercase name.")
    base = output_root.resolve() if output_root is not None else bundle.root / DEFAULT_ROOT
    if not base.is_relative_to(bundle.root):
        raise BenchmarkError("Release directory must stay inside Project 03.")
    target = base / release_id
    if target.exists():
        raise BenchmarkError(f"Final release already exists; never overwrite: {target}")
    for document in ("docs/project03_final_report.md", "docs/project03_results_queries.md"):
        if not (bundle.root / document).is_file():
            raise BenchmarkError(f"Required final source document missing: {document}")
    base.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)
    database = target / "project03_results.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            counts = ingest(connection, bundle)
            checks = _check_database(connection, bundle)
            table_counts = export_tables(connection, target / "tables")
    figure_sources = render_figures(target / "tables", target / "figures")
    (target / "report").mkdir()
    shutil.copyfile(bundle.root / "docs/project03_final_report.md",
                    target / "report/project03_final_report.md")
    (target / "provenance").mkdir()
    _write_json(target / "provenance/source_artifacts.json", [
        {"path": path, "sha256": digest} for path, digest in sorted(bundle.artifact_hashes.items())])
    _write_json(target / "provenance/source_hashes.json", {
        "manifest_sha256": bundle.manifest_hashes,
        "source_benchmark_ids": {key: path.name for key, path in bundle.paths.items()},
        "source_analysis_git_heads": {key: value["analysis_git_head"]
                                      for key, value in bundle.manifests.items()},
        "source_analysis_git_dirty": {key: value["analysis_git_dirty"]
                                      for key, value in bundle.manifests.items()},
    })
    _write_json(target / "provenance/release_checks.json", {
        **checks, "export_row_counts": table_counts, "figure_source_tables": figure_sources})
    _write_json(target / "provenance/backup_manifest.json", backup_inventory(bundle, target))
    head, dirty = get_git_metadata()
    files = {p.relative_to(target).as_posix(): sha256_file(p)
             for p in sorted(target.rglob("*")) if p.is_file()}
    manifest = {
        "release_id": release_id, "project": "03-berth-allocation-lab", "project_step": 13,
        "status": "building", "created_at": datetime.now(timezone.utc).isoformat(),
        "source_git_head": head, "source_git_dirty": dirty,
        "source_benchmark_ids": {key: path.name for key, path in bundle.paths.items()},
        "source_manifest_hashes": bundle.manifest_hashes,
        "warehouse_schema_version": SCHEMA_VERSION,
        "warehouse_sha256": files["project03_results.sqlite"],
        "exported_table_hashes": {key: value for key, value in files.items()
                                  if key.startswith("tables/")},
        "figure_hashes": {key: value for key, value in files.items()
                          if key.startswith("figures/")},
        "figure_source_tables": figure_sources,
        "report_hash": files["report/project03_final_report.md"],
        "source_artifact_count": len(bundle.artifact_hashes),
        "row_counts": counts, "release_file_sha256": files,
        "training_performed": False, "test_inference_performed": False,
        "new_diagnostic_scenarios_generated": False,
        "limitations": [topic for topic, _, _ in LIMITATIONS],
        "verification_status": "pending",
    }
    _write_json(target / "manifest.json", manifest)
    verify_release(target, bundle=bundle, _building=True)
    manifest["status"] = "completed"
    manifest["verification_status"] = "passed"
    replacement = target / "manifest.pending.json"
    _write_json(replacement, manifest)
    replacement.replace(target / "manifest.json")
    verify_release(target, bundle=bundle)
    return target
