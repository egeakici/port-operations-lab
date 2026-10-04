"""Post-hoc descriptive diagnostics over verified, frozen test records."""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

import numpy as np

from berth_allocation_lab.benchmark.config import BenchmarkConfig, BenchmarkError
from berth_allocation_lab.benchmark.inputs import LockedDataset, load_all, sha256_file
from berth_allocation_lab.benchmark.stats import TRAINING_SEEDS, classify, scenario_seed_means
from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
from berth_allocation_lab.rl.dynamic_suites import dynamic_suites


def verify_step12a(configs: tuple[BenchmarkConfig, BenchmarkConfig]) -> dict[str, Any]:
    """Check complete Part A outputs and every listed source/output digest."""
    audited = {}
    required = {"source_inventory.json", "input_audit.json", "pairing_audit.json",
                "locked_result_reconciliation.json", "summary.json", "summary.md",
                "paired_differences.csv", "bootstrap_intervals.csv"}
    for config in configs:
        path = config.resolve(config.output_root) / config.benchmark_id
        manifest_path = path / "manifest.json"
        if not manifest_path.is_file():
            raise BenchmarkError(f"Step 12A manifest missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("status") != "completed" or
                manifest.get("benchmark_id") != config.benchmark_id or
                manifest.get("formulation") != config.formulation or
                not required <= set(manifest.get("derived_output_sha256", {}))):
            raise BenchmarkError(f"Incomplete Step 12A benchmark: {path}")
        for name, digest in manifest["derived_output_sha256"].items():
            if sha256_file(path / name) != digest:
                raise BenchmarkError(f"Step 12A derived hash mismatch: {path / name}")
        for name, digest in manifest["source_evaluation_hashes"].items():
            if sha256_file(Path(name)) != digest:
                raise BenchmarkError(f"Step 12A source hash mismatch: {name}")
        summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
        audited[config.formulation] = {
            "benchmark_id": config.benchmark_id,
            "manifest_path": str(manifest_path), "manifest_sha256": sha256_file(manifest_path),
            "summary_sha256": sha256_file(path / "summary.json"),
            "summary": summary,
        }
    return audited


def _percentile(values: list[float], q: int) -> float | None:
    return float(np.percentile(values, q)) if values else None


def _agreement_signature(row: dict[str, Any]) -> tuple[tuple[Any, ...], ...]:
    return tuple((d["action_type"], d["selected_vessel_id"],
                  d["selected_berth_position_m"], d["simulation_time_min"])
                 for d in row["decision_history"])


def _same_schedule(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left["placements"], right["placements"]
    if len(a) != len(b):
        return False
    return all(x["vessel_id"] == y["vessel_id"] and
               abs(x["berth_position_m"] - y["berth_position_m"]) <= 1e-6 and
               abs(x["berth_start_time_min"] - y["berth_start_time_min"]) <= 1e-6
               for x, y in zip(a, b))


def _read_dynamic_rows(config: BenchmarkConfig, datasets: list[LockedDataset]):
    rows: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    for dataset in datasets:
        regime = dataset.source.regime
        for inventory in dataset.inventory:
            seed = inventory["training_seed"]
            path = Path(inventory["evaluation_path"])
            if sha256_file(path) != inventory["evaluation_sha256"]:
                raise BenchmarkError(f"Dynamic locked evaluation changed: {path}")
            for row in json.loads(path.read_text(encoding="utf-8"))["rows"]:
                method = row["method"]
                key = regime, seed, row["scenario_id"], method
                if key in rows:
                    raise BenchmarkError(f"Duplicate diagnostic row: {key}")
                if (row["status"] != "completed_valid" or row["truncated"] or
                        not row["schedule_valid"] or
                        row["physical_fingerprint"] !=
                        dataset.scenarios[row["scenario_id"]]["physical_fingerprint"]):
                    raise BenchmarkError(f"Invalid diagnostic row: {key}")
                rows[key] = row
    return rows


def _dynamic_details(dataset: LockedDataset, rows: dict, regime: str, scenarios: dict):
    methods = {"fcfs": "dynamic_online_fcfs_v1", "rollout": "dynamic_online_rollout_v1",
               "ppo": "dynamic_maskable_ppo_v1"}
    scenario_rows, waits, agreement, tails, ranked = [], [], [], [], []
    for family in dataset.weights:
        sids = sorted(sid for sid, meta in dataset.scenarios.items()
                      if meta["family"] == family)
        for seed in TRAINING_SEEDS:
            by_method = {name: [rows[(regime, seed, sid, policy)] for sid in sids]
                         for name, policy in methods.items()}
            for method, records in by_method.items():
                decisions = sum(r["decision_count"] for r in records)
                legal = sum(r["legal_wait_opportunities"] for r in records)
                chosen = sum(r["intentional_waits"] for r in records)
                announced_decisions = sum(
                    bool(_observable_snapshot(scenarios[(regime, r["scenario_id"])], r, i)
                         ["announced_vessel_ids"])
                    for r in records for i in range(len(r["decision_history"])))
                if any(sum(d["action_type"] == "WAIT" for d in r["decision_history"]) !=
                       r["intentional_waits"] for r in records):
                    raise BenchmarkError("WAIT count disagrees with decision history.")
                waits.append({"regime": regime, "family": family, "training_seed": seed,
                              "method": method, "scenario_count": len(records),
                              "decision_count": decisions,
                              "assignment_count": sum(r["assignments"] for r in records),
                              "legal_wait_opportunities": legal, "intentional_waits": chosen,
                              "wait_rate_per_opportunity": chosen / legal if legal else None,
                              "mean_waits_per_scenario": chosen / len(records),
                              "episodes_with_wait": sum(r["intentional_waits"] > 0 for r in records),
                              "waits_with_announced": sum(r["waits_with_announced_vessel"]
                                                          for r in records),
                              "decisions_with_announced": announced_decisions,
                              "waiting_after_wait_sum_min": sum(
                                  sum(r["waiting_after_wait_actions_min"]) for r in records),
                              "forced_advances": sum(r["forced_advances"] for r in records)})
                waits_vessel = [v["waiting_time_min"] for r in records
                                for v in r["vessel_results"]]
                totals = [r["total_waiting_time_min"] for r in records]
                tails.append({"regime": regime, "family": family, "training_seed": seed,
                              "method": method, "n_scenarios": len(records),
                              "n_vessels": len(waits_vessel),
                              "mean_scenario_total_min": statistics.fmean(totals),
                              "median_scenario_total_min": statistics.median(totals),
                              "p95_scenario_total_min": _percentile(totals, 95),
                              "max_scenario_total_min": max(totals),
                              "p95_vessel_waiting_min": _percentile(waits_vessel, 95),
                              "max_vessel_waiting_min": max(waits_vessel)})
            ppo = by_method["ppo"]
            fcfs = by_method["fcfs"]
            assignment_total = sum(r["assignments"] for r in ppo)
            assignment_agreed = sum(r["assignment_agreement_with_fcfs"] * r["assignments"]
                                    for r in ppo)
            equality = sum(abs(a["total_waiting_time_min"] - b["total_waiting_time_min"]) <= 1e-6
                           for a, b in zip(ppo, fcfs))
            identical = sum(_same_schedule(a, b) for a, b in zip(ppo, fcfs))
            order_disagreed = sum([p["vessel_id"] for p in a["placements"]] !=
                                  [p["vessel_id"] for p in b["placements"]]
                                  for a, b in zip(ppo, fcfs))
            position_disagreed = sum(any(abs(p["berth_position_m"] -
                                             {q["vessel_id"]: q for q in b["placements"]}
                                             [p["vessel_id"]]["berth_position_m"]) > 1e-6
                                          for p in a["placements"])
                                      for a, b in zip(ppo, fcfs))
            agreement.append({"regime": regime, "family": family, "training_seed": seed,
                              "assignment_agreement_same_state": assignment_agreed / assignment_total,
                              "assignment_agreed": assignment_agreed,
                              "assignment_count": assignment_total,
                              "identical_schedules": identical,
                              "identical_schedule_fraction": identical / len(sids),
                              "equal_waiting_totals": equality,
                              "equal_waiting_fraction": equality / len(sids),
                              "same_cost_different_schedule": equality - identical,
                              "vessel_order_disagreed_scenarios": order_disagreed,
                              "berth_position_disagreed_scenarios": position_disagreed})
            for sid in sids:
                p = rows[(regime, seed, sid, methods["ppo"])]
                f = rows[(regime, seed, sid, methods["fcfs"])]
                for reference in ("fcfs", "rollout"):
                    r = rows[(regime, seed, sid, methods[reference])]
                    delta = p["total_waiting_time_min"] - r["total_waiting_time_min"]
                    scenario_rows.append({"regime": regime, "family": family,
                                          "training_seed": seed, "scenario_id": sid,
                                          "physical_fingerprint": p["physical_fingerprint"],
                                          "reference": reference, "ppo_total_min": p["total_waiting_time_min"],
                                          "reference_total_min": r["total_waiting_time_min"],
                                          "paired_delta_min": delta, "outcome": classify(delta),
                                          "intentional_waits": p["intentional_waits"],
                                          "vessel_count": p["vessel_count"],
                                          "identical_fcfs_schedule": _same_schedule(p, f)
                                          if reference == "fcfs" else None,
                                          "source_evaluation": next(item["evaluation_path"] for item in
                                                                    dataset.inventory if item["training_seed"] == seed)})
    for family in dataset.weights:
        for seed in TRAINING_SEEDS:
            for reference in ("fcfs", "rollout"):
                subset = [r for r in scenario_rows if r["family"] == family and
                          r["training_seed"] == seed and r["reference"] == reference]
                deltas = [r["paired_delta_min"] for r in subset]
                tails.append({"regime": regime, "family": family, "training_seed": seed,
                              "method": f"ppo_minus_{reference}", "n_scenarios": len(subset),
                              "mean_paired_delta_min": statistics.fmean(deltas),
                              "p95_paired_delta_min": _percentile(deltas, 95),
                              "max_paired_delta_min": max(deltas),
                              "fraction_ppo_worse": sum(classify(d) == "loss" for d in deltas) / len(deltas)})
    for reference in ("fcfs", "rollout"):
        for seed in TRAINING_SEEDS:
            subset = [r for r in scenario_rows if r["reference"] == reference and
                      r["training_seed"] == seed]
            for direction, ordered in (("deterioration", sorted(subset, key=lambda r:
                         (-r["paired_delta_min"], r["scenario_id"]))),
                         ("improvement", sorted(subset, key=lambda r:
                          (r["paired_delta_min"], r["scenario_id"])))):
                for rank, row in enumerate(ordered[:5], 1):
                    ranked.append({**row, "rank": rank, "ranking": direction,
                                   "paired_percent": (100 * row["paired_delta_min"] /
                                                      row["reference_total_min"]
                                                      if row["reference_total_min"] > 0 else None),
                                   "schedule_valid": True})
    return scenario_rows, waits, agreement, tails, ranked


def _static_details(dataset: LockedDataset):
    metrics, tails = [], []
    for family in dataset.weights:
        sids = sorted(sid for sid, item in dataset.scenarios.items() if item["family"] == family)
        fcfs = dataset.series("fcfs")
        rollout = dataset.series("rollout")
        for method in dataset.methods():
            for seed in (TRAINING_SEEDS if method == "ppo" else (None,)):
                costs = dataset.series(method, seed)
                totals = [costs[sid] for sid in sids]
                tails.append({"regime": dataset.source.regime, "version": dataset.source.version,
                              "family": family, "method": method, "training_seed": seed,
                              "n_scenarios": len(sids),
                              "mean_scenario_total_min": statistics.fmean(totals),
                              "median_scenario_total_min": statistics.median(totals),
                              "p95_scenario_total_min": _percentile(totals, 95),
                              "max_scenario_total_min": max(totals),
                              "vessel_level_p95": None, "placements_available": False})
                for reference, baseline in (("fcfs", fcfs), ("rollout", rollout)):
                    deltas = [(costs[sid] - baseline[sid], sid) for sid in sids]
                    metrics.append({"regime": dataset.source.regime,
                                    "version": dataset.source.version, "family": family,
                                    "method": method, "training_seed": seed, "reference": reference,
                                    "mean_delta_min": statistics.fmean(d for d, _ in deltas),
                                    "best_delta_min": min(deltas)[0],
                                    "best_scenario_id": min(deltas)[1],
                                    "worst_delta_min": max(deltas)[0],
                                    "worst_scenario_id": max(deltas)[1],
                                    "exact_scope": "fixed_order_finite_candidate_space"
                                    if method == "exact" else None})
    return metrics, tails


def _observable_snapshot(scenario: Any, record: dict[str, Any], index: int) -> dict[str, Any]:
    decision = record["decision_history"][index]
    t = decision["simulation_time_min"]
    previous = {d["selected_vessel_id"] for d in record["decision_history"][:index]
                if d["action_type"] == "ASSIGN"}
    placements = {p["vessel_id"]: p for p in record["placements"] if p["vessel_id"] in previous}
    waiting = sorted(v.vessel_id for v in scenario.vessels
                     if v.arrival_time_min <= t + 1e-9 and v.vessel_id not in previous)
    announced = sorted(v.vessel_id for v in scenario.vessels
                       if t + 1e-9 < v.arrival_time_min <= t + 240 + 1e-9)
    active = sorted(p["vessel_id"] for p in placements.values()
                    if p["berth_start_time_min"] <= t + 1e-9 and
                    p["berth_start_time_min"] + p["service_time_min"] > t + 1e-9)
    return {"simulation_time_min": t, "waiting_vessel_ids": waiting,
            "announced_vessel_ids": announced, "active_vessel_ids": active,
            "basis": "frozen arrivals and recorded assignment prefix; full action mask unavailable"}


def _selected_traces(scenario_rows: list[dict], rows: dict, scenarios: dict) -> list[dict]:
    def choose(reference: str, reverse: bool, family: str | None = None,
               wait: bool = False, same: bool = False):
        options = [r for r in scenario_rows if r["reference"] == reference and
                   (family is None or r["family"] == family) and
                   (not wait or r["intentional_waits"] > 0) and
                   (not same or r["identical_fcfs_schedule"])]
        if not options:
            return None
        return sorted(options, key=lambda r: ((-r["paired_delta_min"] if reverse else
                                              r["paired_delta_min"]), r["scenario_id"],
                                             r["training_seed"]))[0]
    choices = [("best_fcfs_improvement", choose("fcfs", False)),
               ("worst_fcfs_deterioration", choose("fcfs", True)),
               ("worst_rollout_deterioration", choose("rollout", True)),
               ("intentional_wait", choose("fcfs", True, wait=True)),
               ("medium_fcfs_like", choose("fcfs", False, family="dynamic_medium", same=True))]
    traces, used = [], set()
    for category, choice in choices:
        if choice is None:
            continue
        key = choice["regime"], choice["training_seed"], choice["scenario_id"]
        if key in used:
            continue
        used.add(key)
        regime, seed, sid = key
        ppo = rows[(regime, seed, sid, "dynamic_maskable_ppo_v1")]
        fcfs = rows[(regime, seed, sid, "dynamic_online_fcfs_v1")]
        pdec = ppo["decision_history"]
        fdec = fcfs["decision_history"]
        first_difference = next((i for i in range(min(len(pdec), len(fdec)))
                                 if _agreement_signature({"decision_history": [pdec[i]]}) !=
                                 _agreement_signature({"decision_history": [fdec[i]]})),
                                min(len(pdec), len(fdec)))
        index = next((i for i, d in enumerate(pdec) if d["action_type"] == "WAIT"),
                     first_difference) if category == "intentional_wait" else first_difference
        if index >= len(pdec):
            index = 0
        comparable = index <= first_difference and index < len(fdec) and all(
            _agreement_signature({"decision_history": [pdec[j]]}) ==
            _agreement_signature({"decision_history": [fdec[j]]}) for j in range(index))
        traces.append({"category": category, "regime": regime, "family": choice["family"],
                       "training_seed": seed, "scenario_id": sid,
                       "physical_fingerprint": choice["physical_fingerprint"],
                       "source_evaluation": choice["source_evaluation"],
                       "reference": choice["reference"],
                       "reference_total_waiting_min": choice["reference_total_min"],
                       "paired_delta_reference_min": choice["paired_delta_min"],
                       "ppo_total_waiting_min": ppo["total_waiting_time_min"],
                       "fcfs_total_waiting_min": fcfs["total_waiting_time_min"],
                       "paired_delta_fcfs_min": ppo["total_waiting_time_min"] - fcfs["total_waiting_time_min"],
                       "selected_decision_index": index,
                       "observable_snapshot": _observable_snapshot(scenarios[(regime, sid)], ppo, index),
                       "ppo_action": pdec[index],
                       "fcfs_action_at_same_state": fdec[index] if comparable else None,
                       "fcfs_comparison_available": comparable,
                       "legal_alternatives": None,
                       "downstream_placements": ppo["placements"],
                       "interpretation": "Observed action and downstream schedule only; model motive unknown."})
    return traces


def build_diagnostics(static_config: BenchmarkConfig, dynamic_config: BenchmarkConfig,
                      sources: dict[str, Any]) -> dict[str, Any]:
    static_datasets, static_decision = load_all(static_config)
    dynamic_datasets, dynamic_decision = load_all(dynamic_config)
    rows = _read_dynamic_rows(dynamic_config, dynamic_datasets)
    all_scenario, all_wait, all_agreement, all_tail, all_ranked = [], [], [], [], []
    scenarios = {}
    for dataset in dynamic_datasets:
        regime = dataset.source.regime
        frozen = DynamicPPOConfig.load_yaml(dynamic_config.resolve(dataset.source.config_path))
        suite = dynamic_suites(frozen)["test"]
        for scenario in suite.scenarios:
            if dataset.scenarios[scenario.scenario_id]["physical_fingerprint"] != rows[
                    (regime, 11, scenario.scenario_id, "dynamic_maskable_ppo_v1")]["physical_fingerprint"]:
                raise BenchmarkError("Trace scenario fingerprint differs from frozen record.")
            scenarios[(regime, scenario.scenario_id)] = scenario
        pieces = _dynamic_details(dataset, rows, regime, scenarios)
        for target, part in zip((all_scenario, all_wait, all_agreement, all_tail, all_ranked), pieces):
            target.extend(part)
    static_metrics, static_tails = [], []
    for dataset in static_datasets:
        metrics, tails = _static_details(dataset)
        static_metrics.extend(metrics)
        static_tails.extend(tails)
    traces = _selected_traces(all_scenario, rows, scenarios)
    cross_seed_wait = {}
    for family in sorted({r["family"] for r in all_wait}):
        seed_rows = [r for r in all_wait if r["family"] == family and r["method"] == "ppo"]
        counts = [r["intentional_waits"] for r in seed_rows]
        cross_seed_wait[family] = {"training_seeds": list(TRAINING_SEEDS),
                                   "intentional_waits_by_seed": {str(r["training_seed"]):
                                                                 r["intentional_waits"] for r in seed_rows},
                                   "mean_waits_per_seed": statistics.fmean(counts),
                                   "min_waits_per_seed": min(counts),
                                   "max_waits_per_seed": max(counts),
                                   "interpretation": "descriptive three-model variation; not 3N independent scenarios"}
    expected = {row["regime"]: row["gap_closed_seed_mean"] for row in
                sources["dynamic"]["summary"]["regimes"]}
    for dataset in dynamic_datasets:
        fcfs = dataset.series("fcfs")
        rollout = dataset.series("rollout")
        by_seed = scenario_seed_means({seed: dataset.series("ppo", seed) for seed in TRAINING_SEEDS})
        weights = dataset.weights
        def weighted(values):
            return sum(weights[family] * statistics.fmean(values[sid] for sid in dataset.scenarios
                   if dataset.scenarios[sid]["family"] == family) for family in weights)
        gap = (weighted(fcfs) - weighted(by_seed)) / (weighted(fcfs) - weighted(rollout))
        if not math.isclose(gap, expected[dataset.source.regime], abs_tol=1e-6, rel_tol=0):
            raise BenchmarkError("Step 12B gap closure differs from frozen Step 12A result.")
    return {"dynamic_scenario_differences": all_scenario,
            "dynamic_wait_summary": all_wait, "dynamic_action_agreement": all_agreement,
            "dynamic_tail_risk": all_tail, "dynamic_worst_cases": all_ranked,
            "dynamic_selected_traces": traces, "static_method_comparison": static_metrics,
            "static_tail_risk": static_tails,
            "findings": {"static_selection": static_decision["previously_selected"],
                         "dynamic_rule_1": dynamic_decision["r1_r2"],
                         "step12a_gap_closed": expected,
                         "cross_seed_wait_by_family": cross_seed_wait,
                         "trace_count": len(traces),
                         "missing": ["Per-decision full action masks and legal alternatives are not recorded.",
                                     "Static historical placement/vessel traces are unavailable.",
                                     "CPU/CUDA inference parity is unverified.",
                                     "No H=0-trained control is available."]}}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
