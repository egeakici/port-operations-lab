"""Build derived Step 12A tables; never mutate locked source evidence."""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.inputs import LockedDataset, load_all, sha256_file
from berth_allocation_lab.benchmark.stats import (
    TRAINING_SEEDS, classify, gap_closed, improvement_percent,
    paired_bootstrap, paired_summary, scenario_seed_means, weighted_mean,
)
from berth_allocation_lab.tracking.git_metadata import get_git_metadata

COMMON_OUTPUT_NAMES = (
    "manifest.json", "source_inventory.json", "input_audit.json",
    "pairing_audit.json", "paired_differences.csv",
    "bootstrap_intervals.csv", "locked_result_reconciliation.json",
    "replay_audit.json", "summary.json", "summary.md",
)


def output_names(formulation: str) -> tuple[str, ...]:
    branch = (("static_family_metrics.csv",) if formulation == "static" else
              ("dynamic_tiny_family_metrics.csv", "dynamic_medium_heavy_family_metrics.csv",
               "dynamic_seed_comparisons.csv"))
    return COMMON_OUTPUT_NAMES + branch


def _family_values(dataset: LockedDataset, values: dict[str, float]) -> dict[str, list[float]]:
    if set(values) != set(dataset.scenarios):
        raise BenchmarkError("A method is missing a frozen physical scenario.")
    return {family: [values[sid] for sid in dataset.scenarios
                     if dataset.scenarios[sid]["family"] == family]
            for family in dataset.weights}


def _source_reconciliation(dataset: LockedDataset) -> dict[str, Any]:
    if dataset.source.version not in {"v1", "v2"}:
        raise BenchmarkError("Unsupported source version.")
    if not dataset.source.experiment_id.startswith("static_"):
        return {"status": "verified_canonical_per_scenario_rows",
                "evaluation_sha256": dataset.reconciliation["evaluation_sha256"]}
    path = Path(dataset.reconciliation["source_aggregate_path"])
    source = json.loads(path.read_text(encoding="utf-8"))
    groups = {(row["component"], row["method"]): row for row in source["groups"]
              if row["suite"] == "test"}
    checked = 0
    for method in dataset.methods():
        for seed in (TRAINING_SEEDS if method == "ppo" else (None,)):
            label = f"ppo[seed_{seed}]" if seed is not None else method
            values = dataset.series(method, seed)
            for family in [*dataset.weights, "ALL"]:
                key = family if family != "ALL" else "ALL"
                rows = [values[sid] for sid in dataset.scenarios
                        if family == "ALL" or dataset.scenarios[sid]["family"] == family]
                stored = groups.get((key, label))
                if stored is None or stored["n"] != len(rows) or not math.isclose(
                        statistics.fmean(rows), stored["mean_total_waiting_time_min"],
                        abs_tol=1e-6, rel_tol=0):
                    raise BenchmarkError(f"Static locked aggregate mismatch: {dataset.source.regime}/"
                                         f"{dataset.source.version}/{family}/{label}")
                checked += 1
    return {"status": "matched_locked_aggregate", "checked_groups": checked,
            "aggregate_sha256": sha256_file(path),
            "evaluation_sha256": dataset.reconciliation["evaluation_sha256"]}


def _dataset_results(config: BenchmarkConfig, dataset: LockedDataset,
                     selected_version: str | None) -> dict[str, Any]:
    source = dataset.source
    fcfs = dataset.series("fcfs")
    rollout = dataset.series("rollout")
    exact = dataset.series("exact") if "exact" in dataset.methods() else None
    by_seed = {seed: dataset.series("ppo", seed) for seed in TRAINING_SEEDS}
    seed_mean = scenario_seed_means(by_seed)
    methods: list[tuple[str, int | None, dict[str, float]]] = [
        ("fcfs", None, fcfs), ("rollout", None, rollout)]
    if exact is not None:
        methods.append(("candidate_space_exact", None, exact))
    methods.extend(("ppo", seed, by_seed[seed]) for seed in TRAINING_SEEDS)
    methods.append(("ppo_seed_mean", None, seed_mean))
    family_rows, comparison_rows, difference_rows, intervals = [], [], [], []
    aggregate: dict[str, float] = {}
    for method, seed, values in methods:
        grouped = _family_values(dataset, values)
        for family, scores in [*(grouped.items()),
                               ("WEIGHTED", [weighted_mean(grouped, dataset.weights)])]:
            mean = statistics.fmean(scores)
            if family == "WEIGHTED":
                aggregate[f"{method}:{seed}"] = mean
            family_rows.append({
                "formulation": config.formulation, "regime": source.regime,
                "source_version": source.version, "family": family,
                "family_weight": dataset.weights.get(family, 1.0),
                "method": method, "training_seed": seed if seed is not None else
                ("seed_mean" if method == "ppo_seed_mean" else None),
                "n_physical_scenarios": (len(dataset.scenarios) if family == "WEIGHTED"
                                         else len(scores)),
                "mean_total_waiting_time_min": mean,
                "exact_scope": ("fixed_order_finite_candidate_space" if method ==
                                "candidate_space_exact" else None),
                "previously_selected_version": selected_version,
                "is_previously_selected_version": (source.version == selected_version
                                                   if selected_version else None),
            })
    if config.formulation == "dynamic":
        for row in family_rows:
            if row["method"] not in {"ppo", "ppo_seed_mean"}:
                continue
            family = row["family"]
            reference_rows = {item["method"]: item["mean_total_waiting_time_min"]
                              for item in family_rows if item["family"] == family and
                              item["method"] in {"fcfs", "rollout"}}
            row["fcfs_improvement_percent"] = improvement_percent(
                row["mean_total_waiting_time_min"], reference_rows["fcfs"])
            row["fcfs_to_rollout_gap_closed"] = gap_closed(
                row["mean_total_waiting_time_min"], reference_rows["fcfs"],
                reference_rows["rollout"])
    candidates = [("ppo", seed, by_seed[seed]) for seed in TRAINING_SEEDS]
    candidates.append(("ppo_seed_mean", None, seed_mean))
    references = [("fcfs", fcfs), ("rollout", rollout)]
    if exact is not None:
        references.append(("candidate_space_exact", exact))
    for method, seed, candidate in candidates:
        for reference, baseline in references:
            differences = {sid: candidate[sid] - baseline[sid] for sid in dataset.scenarios}
            by_family = _family_values(dataset, differences)
            for sid in sorted(dataset.scenarios):
                difference_rows.append({
                    "formulation": config.formulation, "regime": source.regime,
                    "source_version": source.version, "scenario_id": sid,
                    "physical_fingerprint": dataset.scenarios[sid]["physical_fingerprint"],
                    "family": dataset.scenarios[sid]["family"],
                    "method": method, "training_seed": seed if seed is not None else "seed_mean",
                    "reference": reference, "candidate_waiting_min": candidate[sid],
                    "reference_waiting_min": baseline[sid],
                    "paired_delta_min": differences[sid], "outcome": classify(differences[sid]),
                })
            for family in [*dataset.weights, "WEIGHTED"]:
                subset = (by_family[family] if family != "WEIGHTED"
                          else list(differences.values()))
                summary = paired_summary(subset)
                if family == "WEIGHTED":
                    summary["mean_delta_min"] = weighted_mean(by_family, dataset.weights)
                row = {
                    "formulation": config.formulation, "regime": source.regime,
                    "source_version": source.version, "family": family,
                    "method": method, "training_seed": seed if seed is not None else "seed_mean",
                    "reference": reference, **summary,
                }
                comparison_rows.append(row)
                if family == "WEIGHTED":
                    interval = paired_bootstrap(
                        by_family, dataset.weights, resamples=config.bootstrap_resamples,
                        confidence_level=config.confidence_level, seed=config.bootstrap_seed)
                    intervals.append({key: row[key] for key in
                                      ("formulation", "regime", "source_version", "family",
                                       "method", "training_seed", "reference")} | interval)
    seed_scores = [aggregate[f"ppo:{seed}"] for seed in TRAINING_SEEDS]
    result: dict[str, Any] = {
        "regime": source.regime, "version": source.version,
        "selected_by_frozen_rule": source.version == selected_version if selected_version else None,
        "n_physical_scenarios": len(dataset.scenarios),
        "fcfs_weighted_mean_min": aggregate["fcfs:None"],
        "rollout_weighted_mean_min": aggregate["rollout:None"],
        "ppo_seed_weighted_means_min": {str(seed): score
                                       for seed, score in zip(TRAINING_SEEDS, seed_scores)},
        "ppo_seed_mean_weighted_min": aggregate["ppo_seed_mean:None"],
        "training_seed_min_min": min(seed_scores),
        "training_seed_max_min": max(seed_scores),
        "training_seed_range_min": max(seed_scores) - min(seed_scores),
        "training_seed_sample_sd_min": statistics.stdev(seed_scores),
    }
    if config.formulation == "dynamic":
        result["gap_closed_by_seed"] = {
            str(seed): gap_closed(score, result["fcfs_weighted_mean_min"],
                                  result["rollout_weighted_mean_min"])
            for seed, score in zip(TRAINING_SEEDS, seed_scores)}
        result["gap_closed_seed_mean"] = gap_closed(
            result["ppo_seed_mean_weighted_min"], result["fcfs_weighted_mean_min"],
            result["rollout_weighted_mean_min"])
        result["fcfs_improvement_percent_by_seed"] = {
            str(seed): improvement_percent(score, result["fcfs_weighted_mean_min"])
            for seed, score in zip(TRAINING_SEEDS, seed_scores)}
        result["fcfs_improvement_percent_seed_mean"] = improvement_percent(
            result["ppo_seed_mean_weighted_min"], result["fcfs_weighted_mean_min"])
    if exact is not None:
        result["exact_scope"] = "fixed_order_finite_candidate_space"
        result["exact_weighted_mean_min"] = aggregate["candidate_space_exact:None"]
    return {"summary": result, "family_metrics": family_rows,
            "comparisons": comparison_rows, "differences": difference_rows,
            "intervals": intervals}


def analyze(config: BenchmarkConfig, datasets: list[LockedDataset],
            decision_audit: dict[str, Any]) -> dict[str, Any]:
    selected = decision_audit.get("previously_selected", {})
    pieces = [_dataset_results(config, dataset, selected.get(dataset.source.regime))
              for dataset in datasets]
    metrics = [row for part in pieces for row in part["family_metrics"]]
    comparisons = [row for part in pieces for row in part["comparisons"]]
    differences = [row for part in pieces for row in part["differences"]]
    intervals = [row for part in pieces for row in part["intervals"]]
    summaries = [part["summary"] for part in pieces]
    reconciliation = {
        f"{dataset.source.regime}_{dataset.source.version}": _source_reconciliation(dataset)
        for dataset in datasets}
    pairing = {
        "formulation": config.formulation, "complete": True,
        "cross_formulation_pairing_performed": False,
        "sources": [{
            "regime": d.source.regime, "version": d.source.version,
            "n_physical_scenarios": len(d.scenarios),
            "scenario_fingerprints": {sid: row["physical_fingerprint"]
                                      for sid, row in d.scenarios.items()},
            "training_seed_coverage": list(TRAINING_SEEDS),
            "missing_rows": d.audit["missing_rows"],
        } for d in datasets],
    }
    return {"summaries": summaries, "family_metrics": metrics,
            "comparisons": comparisons, "differences": differences,
            "intervals": intervals, "reconciliation": reconciliation,
            "pairing_audit": pairing}


def dry_run(config: BenchmarkConfig) -> dict[str, Any]:
    datasets, decisions = load_all(config)
    return {
        "status": "ready", "resolved_config": config.public_dict(),
        "project_root": str(config.project_root),
        "output_path": str(config.resolve(config.output_root) / config.benchmark_id),
        "output_already_exists": (config.resolve(config.output_root) / config.benchmark_id).exists(),
        "source_experiments": [
            {"experiment_id": d.source.experiment_id, "regime": d.source.regime,
             "version": d.source.version,
             "evaluation_path": d.source.evaluation_path,
             "required_artifacts": sorted({d.source.config_path, d.source.evaluation_path,
                                            *(row["checkpoint_path"] for row in d.inventory)}),
             "optional_artifacts": ["H=0-trained dynamic controls (not required for Part A)"]
             if config.formulation == "dynamic" else [],
             "training_seeds": list(TRAINING_SEEDS),
             "checkpoint_sha256": {str(row["training_seed"]): row["checkpoint_sha256"]
                                   for row in d.inventory},
             "test_scenario_count": len(d.scenarios), "audit": d.audit}
            for d in datasets],
        "decisions": decisions, "locked_per_scenario_records_available": True,
        "physical_fingerprint_audit_status": "passed",
        "missing_information": [], "replay_needed": False,
        "estimated_replay_episodes": 0,
        "predicted_output_files": list(output_names(config.formulation)),
        "future_diagnostic_seed_region_reserved": "8000000+; no instances generated",
    }


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(config: BenchmarkConfig) -> Path:
    target = config.resolve(config.output_root) / config.benchmark_id
    if target.exists():
        raise BenchmarkError(f"Benchmark output already exists; never overwrite: {target}")
    datasets, decisions = load_all(config)
    results = analyze(config, datasets, decisions)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)
    inventory = [row for dataset in datasets for row in dataset.inventory]
    input_audit = {f"{d.source.regime}_{d.source.version}": d.audit for d in datasets}
    _write_json(target / "source_inventory.json", inventory)
    _write_json(target / "input_audit.json", input_audit)
    _write_json(target / "pairing_audit.json", results["pairing_audit"])
    _write_json(target / "locked_result_reconciliation.json", results["reconciliation"])
    _write_json(target / "replay_audit.json", {
        "status": "not_required", "mode": config.replay_mode,
        "reason": "All locked test records contain complete per-scenario canonical metrics.",
        "replayed_episodes": 0,
    })
    if config.formulation == "static":
        _write_csv(target / "static_family_metrics.csv", results["family_metrics"])
    else:
        _write_csv(target / "dynamic_tiny_family_metrics.csv",
                   [row for row in results["family_metrics"] if row["regime"] == "tiny"])
        _write_csv(target / "dynamic_medium_heavy_family_metrics.csv",
                   [row for row in results["family_metrics"] if row["regime"] == "medium_heavy"])
        _write_csv(target / "dynamic_seed_comparisons.csv",
                   [row for row in results["comparisons"] if row["family"] == "WEIGHTED"])
    _write_csv(target / "paired_differences.csv", results["differences"])
    _write_csv(target / "bootstrap_intervals.csv", results["intervals"])
    summary = {
        "benchmark_id": config.benchmark_id, "formulation": config.formulation,
        "primary_suite": "test", "decision_audit": decisions,
        "regimes": results["summaries"],
        "comparison_rows": len(results["comparisons"]),
        "paired_scenario_rows": len(results["differences"]),
        "uncertainty_intervals": len(results["intervals"]),
        "limitations": [
            "Synthetic, uncalibrated traffic only.",
            "Scenario bootstrap is conditional on the three frozen models.",
            "Static and dynamic test distributions are not directly rankable.",
            "No H=0-trained dynamic control exists.",
            "CPU/CUDA action parity is not established.",
        ],
    }
    _write_json(target / "summary.json", summary)
    lines = [f"# Step 12A {config.formulation.title()} Locked Benchmark",
             "", "All values use the frozen held-out test suite and raw vessel-minutes.",
             "No replay, training, checkpoint selection or new diagnostic episodes occurred.",
             "", "| Regime | Version | FCFS | Rollout | PPO seed mean | PPO seed SD | Gap closed |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in results["summaries"]:
        gap = row.get("gap_closed_seed_mean")
        lines.append(
            f"| {row['regime']} | {row['version']} | {row['fcfs_weighted_mean_min']:.3f} | "
            f"{row['rollout_weighted_mean_min']:.3f} | {row['ppo_seed_mean_weighted_min']:.3f} | "
            f"{row['training_seed_sample_sd_min']:.3f} | "
            f"{'n/a' if gap is None else f'{gap:.5f}'} |")
    lines.extend(["", "Bootstrap intervals are in `bootstrap_intervals.csv`.",
                  "Static Exact is limited to the fixed-order finite candidate space.",
                  "See source inventory, pairing audit and reconciliation for provenance.", ""])
    with (target / "summary.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    head, dirty = get_git_metadata()
    output_hashes = {name: sha256_file(target / name) for name in output_names(config.formulation)
                     if name != "manifest.json"}
    _write_json(target / "manifest.json", {
        "schema_version": 1, "status": "completed", "benchmark_id": config.benchmark_id,
        "formulation": config.formulation, "analysis_git_head": head,
        "analysis_git_dirty": dirty, "config_path": str(config.source_path),
        "config_sha256": sha256_file(config.source_path),
        "source_decision_hashes": {key: value["sha256"] for key, value in decisions.items()
                                   if isinstance(value, dict) and "sha256" in value},
        "source_evaluation_hashes": {
            row["evaluation_path"]: row.get("evaluation_sha256")
            for row in inventory if row.get("evaluation_sha256")},
        "derived_output_sha256": output_hashes, "replay_status": "not_required",
    })
    return target
