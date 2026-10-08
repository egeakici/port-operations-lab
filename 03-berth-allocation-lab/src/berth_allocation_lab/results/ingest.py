"""Hash-gated import of the four frozen Step 12 releases."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.inputs import sha256_file, verify_decision
from berth_allocation_lab.benchmark.stats import paired_summary, weighted_mean
from berth_allocation_lab.results.schema import create_schema, row_counts

PRIMARY = {
    "static": "experiments/benchmark/step12/static_locked_v1",
    "dynamic": "experiments/benchmark/step12/dynamic_h240_locked_v1",
    "diagnostics": "experiments/benchmark/step12b/locked_diagnostics_v3",
    "latency": "experiments/benchmark/step12b/cpu_latency_v2",
}
REQUIRED = {
    "static": {"source_inventory.json", "summary.json", "static_family_metrics.csv",
               "paired_differences.csv", "bootstrap_intervals.csv", "pairing_audit.json"},
    "dynamic": {"source_inventory.json", "summary.json", "dynamic_tiny_family_metrics.csv",
                "dynamic_medium_heavy_family_metrics.csv", "dynamic_seed_comparisons.csv",
                "paired_differences.csv", "bootstrap_intervals.csv", "pairing_audit.json"},
    "diagnostics": {"dynamic_wait_summary.csv", "dynamic_action_agreement.csv",
                    "dynamic_tail_risk.csv", "dynamic_worst_cases.csv",
                    "static_tail_risk.csv", "static_method_comparison.csv",
                    "dynamic_scenario_differences.csv", "dynamic_selected_traces.json",
                    "source_references.json"},
    "latency": {"latency_summary.csv", "latency_decisions.csv", "latency_manifest.json",
                "fixture_plan.json", "source_references.json"},
}


@dataclass(frozen=True)
class SourceBundle:
    root: Path
    paths: dict[str, Path]
    manifests: dict[str, dict[str, Any]]
    manifest_hashes: dict[str, str]
    artifact_hashes: dict[str, str]

    def read_json(self, source: str, name: str) -> Any:
        return json.loads((self.paths[source] / name).read_text(encoding="utf-8"))

    def read_csv(self, source: str, name: str) -> list[dict[str, str]]:
        with (self.paths[source] / name).open(newline="", encoding="utf-8") as stream:
            return list(csv.DictReader(stream))

    def relative(self, path: Path | str) -> str:
        value = Path(path)
        if not value.is_absolute():
            value = self.root / value
        return value.resolve().relative_to(self.root).as_posix()


def _commit_exists(root: Path, commit: str) -> bool:
    if not commit or len(commit) < 7:
        return False
    result = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                            cwd=root, capture_output=True, check=False)
    return result.returncode == 0


def verify_sources(root: Path) -> SourceBundle:
    """Fail closed before creating a release or even a temporary database."""
    root = root.resolve()
    paths, manifests, hashes, artifacts = {}, {}, {}, {}
    for key, relative in PRIMARY.items():
        path = root / relative
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            raise BenchmarkError(f"Required Step 12 release missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        derived = manifest.get("derived_output_sha256", manifest.get("derived_sha256"))
        if manifest.get("status") != "completed" or not isinstance(derived, dict):
            raise BenchmarkError(f"Incomplete Step 12 release: {manifest_path}")
        if not REQUIRED[key] <= set(derived):
            raise BenchmarkError(f"Missing required Step 12 files: {path}: {REQUIRED[key]-set(derived)}")
        if not _commit_exists(root, manifest.get("analysis_git_head", "")):
            raise BenchmarkError(f"Unknown analysis Git commit: {manifest_path}")
        for name, digest in derived.items():
            file_path = path / name
            if sha256_file(file_path) != digest:
                raise BenchmarkError(f"Step 12 derived hash mismatch: {file_path}")
            artifacts[file_path.relative_to(root).as_posix()] = digest
        for source_path, digest in manifest.get("source_evaluation_hashes", {}).items():
            original = Path(source_path)
            if not original.is_absolute():
                original = root / original
            if sha256_file(original) != digest:
                raise BenchmarkError(f"Frozen source evaluation hash mismatch: {original}")
            artifacts[original.resolve().relative_to(root).as_posix()] = digest
        paths[key], manifests[key] = path, manifest
        hashes[key] = sha256_file(manifest_path)
        artifacts[manifest_path.relative_to(root).as_posix()] = hashes[key]
    for branch in ("static", "dynamic"):
        manifest = manifests[branch]
        if manifest.get("formulation") != branch or manifest.get("benchmark_id") != Path(
                PRIMARY[branch]).name:
            raise BenchmarkError(f"Step 12A branch/benchmark mismatch: {branch}")
    for key, mode in (("diagnostics", "diagnostics"), ("latency", "latency")):
        manifest = manifests[key]
        if manifest.get("mode") != mode or manifest.get("diagnostic_id") != paths[key].name:
            raise BenchmarkError(f"Step 12B mode/ID mismatch: {key}")
        if manifest.get("training_performed") is not False or manifest.get(
                "test_inference_performed") is not False:
            raise BenchmarkError(f"Unexpected Step 12B training/test inference flag: {key}")
        for branch in ("static", "dynamic"):
            if (manifest["source_benchmark_ids"].get(branch) != paths[branch].name or
                    manifest["source_manifest_sha256"].get(branch) != hashes[branch]):
                raise BenchmarkError(f"Step 12B/12A source-chain mismatch: {key}/{branch}")
        references = json.loads((paths[key] / "source_references.json").read_text(encoding="utf-8"))
        for branch in ("static", "dynamic"):
            if (references[branch]["manifest_sha256"] != hashes[branch] or
                    references[branch]["summary_sha256"] != sha256_file(
                        paths[branch] / "summary.json")):
                raise BenchmarkError(f"Step 12B reference mismatch: {key}/{branch}")
    for branch in ("static", "dynamic"):
        for item in json.loads((paths[branch] / "source_inventory.json").read_text(encoding="utf-8")):
            for field, digest_field in (("checkpoint_path", "checkpoint_sha256"),
                                        ("evaluation_path", "evaluation_sha256")):
                original = Path(item[field])
                if not original.is_absolute():
                    original = root / original
                if sha256_file(original) != item[digest_field]:
                    raise BenchmarkError(f"Frozen {field} hash mismatch: {original}")
                artifacts[original.resolve().relative_to(root).as_posix()] = item[digest_field]
        config_file = root / "configs/benchmark" / ("step12_static.yaml" if branch == "static"
                                                    else "step12_dynamic_h240.yaml")
        config = BenchmarkConfig.load(config_file)
        for label, decision_path in config.decisions.items():
            path = config.resolve(decision_path)
            _, digest = verify_decision(path)
            if manifests[branch]["source_decision_hashes"].get(label) != digest:
                raise BenchmarkError(f"Step 12A decision hash mismatch: {path}")
            artifacts[path.relative_to(root).as_posix()] = digest
            sidecar = path.with_name(path.name + ".sha256")
            artifacts[sidecar.relative_to(root).as_posix()] = sha256_file(sidecar)
    return SourceBundle(root, paths, manifests, hashes, artifacts)


def _number(value: Any) -> float | None:
    return None if value in (None, "", "None") else float(value)


def _seed(value: Any) -> tuple[str, int | None]:
    if value in (None, "", "None"):
        return "none", None
    if value == "seed_mean":
        return "seed_mean", None
    return str(int(value)), int(value)


def _raw_metadata(bundle: SourceBundle) -> dict[tuple[str, str, str, str, str, str], dict]:
    """Supplement canonical Step 12A totals with recorded vessel/KPI fields."""
    metadata: dict[tuple[str, str, str, str, str, str], dict] = {}
    for branch in ("static", "dynamic"):
        inventory = bundle.read_json(branch, "source_inventory.json")
        for item in inventory:
            path = Path(item["evaluation_path"])
            if not path.is_absolute():
                path = bundle.root / path
            if sha256_file(path) != item["evaluation_sha256"]:
                raise BenchmarkError(f"Source metadata file changed: {path}")
            if branch == "static":
                with path.open(encoding="utf-8") as stream:
                    rows = (json.loads(line) for line in stream)
                    rows = [row for row in rows if row["suite"] == "test"]
            else:
                rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
            for row in rows:
                method = row["method"]
                if branch == "static" and method == "exact":
                    method = "candidate_space_exact"
                if branch == "static" and method == "ppo" and int(
                        row["training_seed"]) != int(item["training_seed"]):
                    continue
                if branch == "dynamic":
                    method = {"dynamic_online_fcfs_v1": "fcfs",
                              "dynamic_online_rollout_v1": "rollout",
                              "dynamic_maskable_ppo_v1": "ppo"}[method]
                seed_label = str(item["training_seed"]) if method == "ppo" else "none"
                key = (branch, item["regime"], item["version"], row["scenario_id"],
                       method, seed_label)
                value = {"vessel_count": int(row["vessel_count"]),
                         "total_waiting": float(row["total_waiting_time_min"]),
                         "mean_waiting": _number(row.get("mean_waiting_time_min")),
                         "p95_waiting": _number(row.get("p95_waiting_time_min")),
                         "mean_turnaround": _number(row.get("mean_turnaround_time_min")),
                         "p95_turnaround": _number(row.get("p95_turnaround_time_min"))}
                if key in metadata and metadata[key] != value:
                    raise BenchmarkError(f"Repeated baseline metadata differs: {key}")
                metadata[key] = value
    return metadata


def _insert_experiments(connection: sqlite3.Connection, bundle: SourceBundle) -> dict:
    by_seed = {}
    for branch in ("static", "dynamic"):
        for item in bundle.read_json(branch, "source_inventory.json"):
            checkpoint = Path(item["checkpoint_path"])
            if not checkpoint.is_absolute():
                checkpoint = bundle.root / checkpoint
            run_manifest = checkpoint.parent / "manifest.json"
            digest = sha256_file(run_manifest)
            bundle.artifact_hashes[bundle.relative(run_manifest)] = digest
            seed = int(item["training_seed"])
            connection.execute("""INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (item["experiment_id"], branch, item["regime"], item["policy_id"],
                                item["environment_version"], item["observation_version"],
                                seed, item.get("training_device"), item["evaluation_device"],
                                item["source_git_commit"], bundle.relative(run_manifest),
                                digest, item["completion_status"]))
            by_seed[branch, item["regime"], item["version"], seed] = item["experiment_id"]
    return by_seed


def _insert_primary(connection: sqlite3.Connection, bundle: SourceBundle, experiment_ids: dict) -> None:
    raw = _raw_metadata(bundle)
    values: dict[tuple, tuple[float, str]] = {}
    scenario_meta = {}
    pending_differences = []
    for branch in ("static", "dynamic"):
        relative = f"{PRIMARY[branch]}/paired_differences.csv"
        for row in bundle.read_csv(branch, "paired_differences.csv"):
            sid, regime, version = row["scenario_id"], row["regime"], row["source_version"]
            scenario_key = branch, sid
            identity = row["family"], row["physical_fingerprint"], regime
            if scenario_key in scenario_meta and scenario_meta[scenario_key] != identity:
                raise BenchmarkError(f"Scenario identity mismatch in Step 12A: {scenario_key}")
            scenario_meta[scenario_key] = identity
            label, _ = _seed(row["training_seed"])
            for method, seed_label, total in ((row["method"], label,
                                               float(row["candidate_waiting_min"])),
                                              (row["reference"], "none",
                                               float(row["reference_waiting_min"]))):
                key = branch, regime, version, sid, method, seed_label
                if key in values and not math.isclose(values[key][0], total, rel_tol=0, abs_tol=1e-6):
                    raise BenchmarkError(f"Contradictory paired total: {key}")
                values[key] = total, relative
            pending_differences.append((branch, regime, version, sid, row["family"],
                                        row["method"], row["reference"], label,
                                        float(row["paired_delta_min"]), row["outcome"], relative))
    for (branch, sid), (family, fingerprint, regime) in sorted(scenario_meta.items()):
        counts = {meta["vessel_count"] for key, meta in raw.items()
                  if key[0] == branch and key[3] == sid}
        if len(counts) != 1:
            raise BenchmarkError(f"Vessel-count metadata missing/conflicting: {branch}/{sid}")
        connection.execute("""INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?)""",
                           (sid, branch, "test", regime, family, fingerprint, counts.pop(),
                            240.0 if branch == "dynamic" else None))
    connection.executemany("""INSERT INTO scenario_differences VALUES
                           (?,?,?,?,?,?,?,?,?,?,?)""", pending_differences)
    for key, (total, path) in sorted(values.items()):
        branch, regime, version, sid, method, seed_label = key
        detail = raw.get(key)
        if method != "ppo_seed_mean" and detail is None:
            raise BenchmarkError(f"Original result metadata missing: {key}")
        if detail and not math.isclose(detail["total_waiting"], total, rel_tol=0, abs_tol=1e-6):
            raise BenchmarkError(f"Step 12A/original total mismatch: {key}")
        seed = int(seed_label) if seed_label.isdigit() else None
        connection.execute("""INSERT INTO scenario_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (branch, regime, version, sid,
                            experiment_ids.get((branch, regime, version, seed)) if seed else None,
                            method, seed_label, seed, total,
                            detail["mean_waiting"] if detail else None,
                            detail["p95_waiting"] if detail else None,
                            detail["mean_turnaround"] if detail else None,
                            detail["p95_turnaround"] if detail else None,
                            1, 0, path))


def _insert_aggregates(connection: sqlite3.Connection, bundle: SourceBundle) -> None:
    for branch in ("static", "dynamic"):
        files = (["static_family_metrics.csv"] if branch == "static" else
                 ["dynamic_tiny_family_metrics.csv", "dynamic_medium_heavy_family_metrics.csv"])
        for name in files:
            source = f"{PRIMARY[branch]}/{name}"
            for row in bundle.read_csv(branch, name):
                label, _ = _seed(row["training_seed"])
                selected = (int(row["is_previously_selected_version"] == "True")
                            if row["is_previously_selected_version"] else None)
                for metric, value, unit in (
                        ("mean_total_waiting_time_min", row["mean_total_waiting_time_min"],
                         "vessel-minutes"),
                        ("fcfs_to_rollout_gap_closed", row.get("fcfs_to_rollout_gap_closed"),
                         "fraction"),
                        ("fcfs_improvement_percent", row.get("fcfs_improvement_percent"),
                         "percent")):
                    if value in (None, ""):
                        continue
                    connection.execute("""INSERT INTO aggregate_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                       (branch, "test", row["regime"], row["source_version"],
                                        row["family"], row["method"], label, metric,
                                        float(value), unit, int(row["n_physical_scenarios"]),
                                        selected, source))
    # Frozen summaries distinguish per-seed and scenario-mean estimates explicitly.
    for regime in bundle.read_json("dynamic", "summary.json")["regimes"]:
        for label, value in [*regime["gap_closed_by_seed"].items(),
                             ("seed_mean", regime["gap_closed_seed_mean"])]:
            connection.execute("""INSERT INTO aggregate_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               ("dynamic", "test", regime["regime"], regime["version"],
                                "WEIGHTED", "ppo" if label != "seed_mean" else "ppo_seed_mean",
                                label, "gap_closed", value, "fraction",
                                regime["n_physical_scenarios"], None,
                                f"{PRIMARY['dynamic']}/summary.json"))


def _insert_comparisons(connection: sqlite3.Connection, bundle: SourceBundle) -> None:
    for branch in ("static", "dynamic"):
        groups: dict[tuple, list[float]] = defaultdict(list)
        for row in bundle.read_csv(branch, "paired_differences.csv"):
            label, _ = _seed(row["training_seed"])
            key = row["regime"], row["source_version"], row["family"], row["method"], row["reference"], label
            groups[key].append(float(row["paired_delta_min"]))
        config_name = ("step12_static.yaml" if branch == "static" else "step12_dynamic_h240.yaml")
        config = BenchmarkConfig.load(bundle.root / "configs/benchmark" / config_name)
        weighted_groups: dict[tuple, dict[str, list[float]]] = defaultdict(dict)
        for key, deltas in groups.items():
            regime, version, family, candidate, reference, label = key
            weighted_groups[regime, version, candidate, reference, label][family] = deltas
        for (regime, version, candidate, reference, label), by_family in weighted_groups.items():
            weights = config.normalized_weights(regime)
            if set(by_family) != set(weights):
                raise BenchmarkError(f"Incomplete family comparison: {branch}/{regime}")
            for family, values in [*by_family.items(),
                                   ("WEIGHTED", [d for v in by_family.values() for d in v])]:
                summary = paired_summary(values)
                if family == "WEIGHTED":
                    summary["mean_delta_min"] = weighted_mean(by_family, weights)
                connection.execute("""INSERT INTO paired_comparisons VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                   (branch, "test", regime, version, family, candidate, reference,
                                    label, summary["mean_delta_min"], summary["median_delta_min"],
                                    summary["wins"], summary["ties"], summary["losses"],
                                    summary["win_fraction"], summary["n_physical_scenarios"],
                                    f"{PRIMARY[branch]}/paired_differences.csv"))
        if branch == "dynamic":
            for row in bundle.read_csv(branch, "dynamic_seed_comparisons.csv"):
                label, _ = _seed(row["training_seed"])
                stored = connection.execute("""SELECT mean_delta_min, wins, ties, losses FROM
                    paired_comparisons WHERE branch=? AND regime=? AND source_version=? AND family=?
                    AND candidate_method=? AND reference_method=? AND seed_label=?""",
                    (branch, row["regime"], row["source_version"], "WEIGHTED", row["method"],
                     row["reference"], label)).fetchone()
                if (stored is None or not math.isclose(stored[0], float(row["mean_delta_min"]),
                    abs_tol=1e-6, rel_tol=0) or tuple(stored[1:]) !=
                        (int(row["wins"]), int(row["ties"]), int(row["losses"]))):
                    raise BenchmarkError("Dynamic paired comparison differs from Step 12A.")
        for row in bundle.read_csv(branch, "bootstrap_intervals.csv"):
            label, _ = _seed(row["training_seed"])
            connection.execute("""INSERT INTO uncertainty_intervals VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (branch, "test", row["regime"], row["source_version"], row["family"],
                 row["method"], row["reference"], label, "paired_delta_total_waiting_min",
                 float(row["estimate_min"]), float(row["ci_lower_min"]),
                 float(row["ci_upper_min"]), float(row["confidence_level"]),
                 int(row["resamples"]), int(row["bootstrap_seed"]),
                 int(row["n_physical_scenarios"]),
                 f"{PRIMARY[branch]}/bootstrap_intervals.csv"))


def _insert_diagnostics(connection: sqlite3.Connection, bundle: SourceBundle) -> None:
    for name in ("dynamic_wait_summary.csv", "dynamic_action_agreement.csv",
                 "dynamic_tail_risk.csv"):
        for row in bundle.read_csv("diagnostics", name):
            label, _ = _seed(row.get("training_seed"))
            exclude = {"regime", "family", "method", "training_seed"}
            method = row.get("method") or "ppo_agreement"
            for field, raw in row.items():
                if field in exclude:
                    continue
                value = _number(raw)
                unit = ("fraction" if "rate" in field or "fraction" in field or
                        field == "assignment_agreement_same_state" else
                        "vessel-minutes" if field.endswith("_min") else "count")
                connection.execute("""INSERT INTO diagnostic_metrics VALUES (?,?,?,?,?,?,?,?)""",
                                   (row["regime"], row["family"], method, label, field,
                                    value, unit, f"{PRIMARY['diagnostics']}/{name}"))
    for row in bundle.read_csv("latency", "latency_summary.csv"):
        connection.execute("""INSERT INTO latency_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                           (row["regime"], row["method"], "cpu", int(row["fixture_count"]),
                            int(row["decision_count"]), float(row["weighted_mean_decision_ms"]),
                            float(row["median_decision_ms"]), float(row["p95_decision_ms"]),
                            float(row["max_decision_ms"]), float(row["total_policy_ms"]),
                            f"{PRIMARY['latency']}/latency_summary.csv"))


def _insert_artifacts(connection: sqlite3.Connection, bundle: SourceBundle) -> None:
    for path, digest in sorted(bundle.artifact_hashes.items()):
        producer = "step12b" if "/step12b/" in path else "step12a" if "/step12/" in path else "step9_or_11"
        role = "source" if producer == "step9_or_11" else "derived"
        artifact_type = "checkpoint" if path.endswith(".zip") else "manifest" if path.endswith(
            "manifest.json") else "result"
        git_commit = (bundle.manifests["diagnostics"]["analysis_git_head"] if producer == "step12b"
                      else bundle.manifests["static"]["analysis_git_head"] if producer == "step12a"
                      else None)
        connection.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?)",
                           (artifact_type, path, digest, role, producer, git_commit))


def ingest(connection: sqlite3.Connection, bundle: SourceBundle) -> dict[str, int]:
    create_schema(connection)
    with connection:
        ids = _insert_experiments(connection, bundle)
        _insert_primary(connection, bundle, ids)
        _insert_aggregates(connection, bundle)
        _insert_comparisons(connection, bundle)
        _insert_diagnostics(connection, bundle)
        _insert_artifacts(connection, bundle)
    return row_counts(connection)
