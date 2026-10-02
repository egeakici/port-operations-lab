"""Paired evaluation of learned and reference static policies.

Every method runs on the same immutable scenario object through the shared
runner, so schedules are validated and KPIs come from the canonical metrics.
All objectives are raw vessel-minutes; training reward scaling never enters
evaluation. Exact gaps are reported only against certified references.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import time
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from berth_allocation_lab.core import NUMERICAL_TOLERANCE, find_schedule_violations, total_waiting_time
from berth_allocation_lab.evaluation.comparison import candidate_space_reference_gap
from berth_allocation_lab.evaluation.metrics import METRIC_VERSION
from berth_allocation_lab.evaluation.runner import run_static_policy
from berth_allocation_lab.policies import StaticFCFS, StaticGreedyRollout
from berth_allocation_lab.policies.base import StaticPolicy
from berth_allocation_lab.rl.config import StaticPPOExperimentConfig
from berth_allocation_lab.rl.progress import progress_bar
from berth_allocation_lab.rl.suites import (
    ScenarioSuite,
    audit_fresh_suites,
    audit_split_isolation,
    build_config_suite,
    build_config_suites,
    historical_fixture_fingerprints,
    previously_examined_fingerprints,
    scenario_identity,
)
from berth_allocation_lab.solvers import CandidateEnumerationConfig, StaticCandidateEnumeration
from berth_allocation_lab.tracking.git_metadata import get_git_metadata
from berth_allocation_lab.tracking.records import ScientificRunResult


EVALUATION_PROTOCOL_VERSION = "static_paired_eval_v1"
KPI_FIELDS = (
    "total_waiting_time_min", "mean_waiting_time_min", "p95_waiting_time_min",
    "mean_turnaround_time_min", "p95_turnaround_time_min", "berth_utilization",
)


@dataclass
class ReferenceCache:
    """FCFS/Rollout/Exact results keyed by (policy_id, scenario fingerprint).

    Each reference is computed once per immutable instance and reused for
    every training seed and any suite that contains the same instance.
    """

    results: dict[tuple[str, str], ScientificRunResult] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(self, policy: StaticPolicy, scenario, record_dir) -> ScientificRunResult:
        key = (policy.policy_id, scenario.content_fingerprint)
        if key in self.results:
            self.hits += 1
        else:
            self.misses += 1
            self.results[key] = run_static_policy(scenario, policy, record_dir)
        return self.results[key]


@dataclass(frozen=True)
class LearnedPolicyEntry:
    """A loaded checkpoint plus the identity recorded next to its results."""

    label: str
    training_seed: int
    checkpoint_id: str
    checkpoint_path: str
    policy: StaticPolicy


# ------------------------------------------------------- validation/selection


def validation_waiting(policy: StaticPolicy, suite: ScenarioSuite) -> dict[str, Any]:
    """Deterministic masked rollout of ``policy`` over a fixed suite.

    The mean is defined only when every scenario yields a valid complete
    schedule; otherwise it is None and the checkpoint cannot be selected.
    """

    rows = []
    for scenario in suite.scenarios:
        try:
            result = policy.schedule(scenario)
            violations = find_schedule_violations(
                scenario.vessels, result.placements, scenario.berth_length_m, scenario.min_clearance_m,
            )
            if violations:
                raise ValueError("; ".join(v.message for v in violations))
            rows.append({"scenario_id": scenario.scenario_id,
                         "total_waiting_time_min": total_waiting_time(scenario.vessels, result.placements),
                         "error": None})
        except Exception as error:  # recorded, never silently replaced
            rows.append({"scenario_id": scenario.scenario_id, "total_waiting_time_min": None,
                         "error": f"{type(error).__name__}: {error}"})
    values = [r["total_waiting_time_min"] for r in rows]
    valid = all(v is not None for v in values)
    return {
        "mean_total_waiting_time_min": statistics.fmean(values) if valid and values else None,
        "valid_count": sum(v is not None for v in values),
        "scenario_count": len(values),
        "per_scenario": rows,
    }


def is_improvement(candidate: float | None, incumbent: float | None) -> bool:
    """Strictly lower beyond tolerance; ties keep the earlier checkpoint."""

    if candidate is None:
        return False
    return incumbent is None or candidate < incumbent - NUMERICAL_TOLERANCE


def select_checkpoint(history: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Frozen rule: lowest mean validation waiting, earliest timestep on ties.

    Only validation evaluations are accepted; test data never reaches this rule.
    """

    best = None
    for entry in sorted(history, key=lambda e: e["timesteps"]):
        if entry.get("suite_split", "validation") != "validation":
            raise ValueError("Checkpoint selection accepts validation evaluations only.")
        if is_improvement(entry["mean_total_waiting_time_min"],
                          None if best is None else best["mean_total_waiting_time_min"]):
            best = entry
    return best


# ------------------------------------------------------------ paired runs


def evaluate_suite(
    suite: ScenarioSuite,
    learned: Sequence[LearnedPolicyEntry],
    *,
    exact_max_vessels: int = 8,
    exact_config: CandidateEnumerationConfig | None = None,
    record_dir: str | Path | None = None,
    reference_cache: ReferenceCache | None = None,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """Run FCFS, Rollout, certified-tiny Exact and each learned policy per scenario."""

    exact_config = exact_config or CandidateEnumerationConfig(max_vessels=min(exact_max_vessels, 8))
    cache = reference_cache if reference_cache is not None else ReferenceCache()
    rows: list[dict[str, Any]] = []
    with ExitStack() as stack:
        count = len(suite.scenarios)
        labels = [("FCFS", count), ("Rollout", count),
                  ("Exact", sum(s.vessel_count <= exact_max_vessels for s in suite.scenarios)),
                  *((f"PPO {entry.label}", count) for entry in learned)]
        bars = [stack.enter_context(progress_bar(
            enabled=progress, total=total, description=f"{suite.name} {label}", position=index,
        )) for index, (label, total) in enumerate(labels)]

        def advance(index: int) -> None:
            bar = bars[index]
            if bar is not None:
                if index < 3:
                    bar.set_postfix(cache_hits=cache.hits, refresh=False)
                bar.update(1)

        # Preserve the original scenario-major execution and artifact row order.
        for scenario in suite.scenarios:
            base = {"suite": suite.name, "component": component_of(scenario.scenario_id, scenario.split),
                    **scenario_identity(scenario)}
            fcfs = cache.get(StaticFCFS(), scenario, record_dir)
            advance(0)
            rollout = cache.get(StaticGreedyRollout(), scenario, record_dir)
            advance(1)
            exact = (cache.get(StaticCandidateEnumeration(exact_config), scenario, record_dir)
                     if scenario.vessel_count <= exact_max_vessels else None)
            if exact is not None:
                advance(2)
            references = (_objective(fcfs), _objective(rollout), _certified(exact))
            rows.append(_row(base, "fcfs", fcfs, references))
            rows.append(_row(base, "rollout", rollout, references))
            if exact is not None:
                rows.append(_row(base, "exact", exact, references))
            for index, entry in enumerate(learned, start=3):
                result = run_static_policy(scenario, entry.policy, record_dir)
                advance(index)
                rows.append({**_row(base, "ppo", result, references), "ppo_label": entry.label,
                             "training_seed": entry.training_seed, "checkpoint_id": entry.checkpoint_id,
                             "checkpoint_path": entry.checkpoint_path})
    return rows


def component_of(scenario_id: str, split: str) -> str:
    return scenario_id.rsplit(f"_{split}_seed", 1)[0]


def _objective(result: ScientificRunResult) -> float | None:
    return result.summary.objective_value if result.summary.is_valid else None


def _certified(result: ScientificRunResult | None):
    if result is None or result.manifest.status != "completed" or result.solver_diagnostics is None:
        return None
    diagnostics = result.solver_diagnostics
    return diagnostics if diagnostics.optimality_status == "optimal" else None


def _row(base: dict[str, Any], method: str, result: ScientificRunResult, references) -> dict[str, Any]:
    fcfs, rollout, certified = references
    summary, manifest = result.summary, result.manifest
    objective = _objective(result)
    row = {
        **base,
        "method": method,
        "policy_id": manifest.policy_id,
        "run_status": manifest.status,
        "is_valid": summary.is_valid,
        "validation_status": summary.validation_status,
        **{name: getattr(summary, name) for name in KPI_FIELDS},
        "vessel_count_completed": summary.vessel_count_completed,
        "algorithm_runtime_seconds": summary.algorithm_runtime_seconds,
        "failure_type": manifest.failure_type,
        "failure_message": manifest.failure_message,
        "delta_vs_fcfs_min": None if objective is None or fcfs is None else objective - fcfs,
        "delta_vs_rollout_min": None if objective is None or rollout is None else objective - rollout,
        "exact_certified": certified is not None,
        "exact_gap_abs_min": None,
        "exact_gap_rel": None,
    }
    if objective is not None and certified is not None:
        gap = candidate_space_reference_gap(objective, certified)
        row["exact_gap_abs_min"], row["exact_gap_rel"] = gap.absolute_gap_min, gap.relative_gap
    diagnostics = result.solver_diagnostics
    if diagnostics is not None:
        row.update(optimality_status=diagnostics.optimality_status,
                   certified_optimal_objective=diagnostics.certified_optimal_objective,
                   best_feasible_objective=diagnostics.best_feasible_objective,
                   termination_reason=diagnostics.termination_reason,
                   nodes_explored=diagnostics.nodes_explored)
    return row


# ------------------------------------------------------------- aggregation


def aggregate_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Per suite/component/method(/seed) statistics plus cross-seed spread.

    Means use valid rows only and always report the invalid count; paired
    deltas and gaps use only scenarios where both sides are valid.
    """

    rows = list(rows)
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        method = row["method"] if row["method"] != "ppo" else f"ppo[{row['ppo_label']}]"
        for component in (row["component"], "ALL"):
            groups.setdefault((row["suite"], component, method), []).append(row)
    summary = [{"suite": s, "component": c, "method": m, **_stats(g)}
               for (s, c, m), g in sorted(groups.items())]

    cross_seed = []
    seeds: dict[tuple, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        if row["method"] == "ppo":
            for component in (row["component"], "ALL"):
                seeds.setdefault((row["suite"], component), {}).setdefault(row["ppo_label"], []).append(row)
    for (suite, component), by_label in sorted(seeds.items()):
        means = {label: _stats(group)["mean_total_waiting_time_min"] for label, group in by_label.items()}
        defined = [m for m in means.values() if m is not None]
        cross_seed.append({
            "suite": suite, "component": component, "n_training_seeds": len(means),
            "per_seed_mean_total_waiting_time_min": means,
            "mean_of_seed_means": statistics.fmean(defined) if defined else None,
            "std_of_seed_means": statistics.stdev(defined) if len(defined) > 1 else None,
            "min_seed_mean": min(defined, default=None), "max_seed_mean": max(defined, default=None),
        })
    return {"protocol_version": EVALUATION_PROTOCOL_VERSION, "groups": summary, "cross_seed": cross_seed}


def _stats(group: list[dict[str, Any]]) -> dict[str, Any]:
    values = [r["total_waiting_time_min"] for r in group if r["is_valid"]
              and r["total_waiting_time_min"] is not None]

    def mean_of(key: str) -> float | None:
        defined = [r[key] for r in group if r.get(key) is not None]
        return statistics.fmean(defined) if defined else None

    return {
        "n": len(group),
        "n_valid": len(values),
        "n_invalid": len(group) - len(values),
        "mean_total_waiting_time_min": statistics.fmean(values) if values else None,
        "median_total_waiting_time_min": statistics.median(values) if values else None,
        "std_total_waiting_time_min": statistics.stdev(values) if len(values) > 1 else None,
        "mean_delta_vs_fcfs_min": mean_of("delta_vs_fcfs_min"),
        "mean_delta_vs_rollout_min": mean_of("delta_vs_rollout_min"),
        "n_exact_certified": sum(bool(r.get("exact_certified")) for r in group),
        "mean_exact_gap_abs_min": mean_of("exact_gap_abs_min"),
        "mean_exact_gap_rel": mean_of("exact_gap_rel"),
        "n_exact_gap_rel_undefined": sum(r.get("exact_gap_abs_min") is not None
                                         and r.get("exact_gap_rel") is None for r in group),
        "mean_algorithm_runtime_seconds": mean_of("algorithm_runtime_seconds"),
    }


# ------------------------------------------------------------------ output


def write_evaluation(output_dir: str | Path, rows: list[dict[str, Any]],
                     aggregate: dict[str, Any], manifest: dict[str, Any]) -> Path:
    """Write per-instance rows, aggregates, a manifest and a Markdown report."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "per_instance.jsonl").exists():
        raise FileExistsError(f"{output} already holds evaluation results.")
    with (output / "per_instance.jsonl").open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, sort_keys=True, default=_json_default) + "\n")
    fields = sorted({key for row in rows for key in row})
    with (output / "per_instance.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (output / "aggregate.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8")
    (output / "evaluation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    (output / "report.md").write_text(render_report(aggregate, manifest), encoding="utf-8")
    return output


def render_report(aggregate: dict[str, Any], manifest: dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.3f}" if math.isfinite(value) else str(value)
        return str(value)

    lines = [
        "# Static Maskable PPO paired evaluation", "",
        f"Protocol `{aggregate['protocol_version']}`; all waiting values are raw vessel-minutes.",
        f"Checkpoint kind: `{manifest.get('checkpoint_kind')}`. Training budgets: "
        f"{manifest.get('training_budgets')}.",
        "Exact gaps use certified candidate-space optima only; PPO is a learned heuristic.", "",
        "| suite | component | method | n | invalid | mean J | median J | std J | "
        "mean delta vs FCFS | mean delta vs Rollout | certified | mean exact gap | mean rel gap |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in aggregate["groups"]:
        lines.append("| " + " | ".join(fmt(v) for v in (
            g["suite"], g["component"], g["method"], g["n"], g["n_invalid"],
            g["mean_total_waiting_time_min"], g["median_total_waiting_time_min"],
            g["std_total_waiting_time_min"], g["mean_delta_vs_fcfs_min"], g["mean_delta_vs_rollout_min"],
            g["n_exact_certified"], g["mean_exact_gap_abs_min"], g["mean_exact_gap_rel"])) + " |")
    lines += ["", "## Variation across training seeds", "",
              "| suite | component | seeds | mean of seed means | std of seed means | min | max |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for c in aggregate["cross_seed"]:
        lines.append("| " + " | ".join(fmt(v) for v in (
            c["suite"], c["component"], c["n_training_seeds"], c["mean_of_seed_means"],
            c["std_of_seed_means"], c["min_seed_mean"], c["max_seed_mean"])) + " |")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------- experiment driver


def evaluate_training_runs(
    config: StaticPPOExperimentConfig,
    run_dirs: Sequence[str | Path],
    *,
    output_dir: str | Path,
    suites: Sequence[str] | None = None,
    checkpoint: str = "best",
    seeds_per_component: int | None = None,
    seeds: Sequence[int] | None = None,
    record_runs: bool = False,
    device: str = "cpu",
    validation_decision: str | Path | None = None,
    progress: bool = False,
) -> Path:
    """Evaluate completed training runs on frozen suites without retraining.

    Only runs whose selection finished (status ``completed``) are accepted,
    the config must be byte-identical to the one used for training, and the
    default test/diagnostic suites must match the identities recorded at
    training time. With ``require_validation_decision`` any test-split suite
    needs the pre-recorded, hash-verified validation decision.
    """

    from berth_allocation_lab.rl.decision import verify_validation_decision
    from berth_allocation_lab.rl.policy import MaskablePPOStaticPolicy, dependency_versions

    if checkpoint not in {"best", "final"}:
        raise ValueError("checkpoint must be best or final.")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"{output} exists; evaluation never overwrites results.")
    started_at, started = datetime.now(timezone.utc).isoformat(), time.perf_counter()
    root = config.project_root()
    kind = "best_validation" if checkpoint == "best" else "final"
    learned, budgets, training_records, recorded_test, recorded_diagnostics = [], {}, [], None, None
    checkpoint_hashes = {}
    for run_dir in map(Path, run_dirs):
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "completed":
            raise ValueError(f"{run_dir} has status {manifest.get('status')}; only completed runs are evaluated.")
        if (manifest.get("experiment_id") != config.experiment_id
                or manifest.get("config_sha256") != config.source_sha256):
            raise ValueError(f"{run_dir} was trained with a different experiment config.")
        reference = manifest["checkpoints"][kind]
        label = f"seed_{manifest['training_seed']}"
        checkpoint_hashes[reference["model_id"]] = hashlib.sha256(
            (run_dir / reference["path"]).read_bytes()).hexdigest()
        learned.append(LearnedPolicyEntry(
            label=label, training_seed=manifest["training_seed"], checkpoint_id=reference["model_id"],
            checkpoint_path=_portable(run_dir / reference["path"], root),
            policy=MaskablePPOStaticPolicy.load(run_dir / reference["path"], device=device)))
        budgets[label] = manifest.get("total_timesteps_completed")
        with (run_dir / "train_episodes.csv").open(encoding="utf-8", newline="") as file:
            training_records += list(csv.DictReader(file))
        recorded_test = recorded_test or manifest.get("test_scenario_set_identities")
        recorded_diagnostics = recorded_diagnostics or manifest.get("diagnostic_scenario_set_identities")
    if not learned or len({e.label for e in learned}) != len(learned):
        raise ValueError("Provide at least one run directory and at most one run per training seed.")

    specs = {"validation": config.validation, "test": config.test,
             **{spec.name: spec for spec in config.diagnostics}}
    names = list(suites) if suites else ["test", *(spec.name for spec in config.diagnostics)]
    if seeds is not None and len(names) != 1:
        raise ValueError("Explicit seeds apply to exactly one suite.")
    unknown = [name for name in names if name not in specs]
    if unknown:
        raise ValueError(f"Unknown suite {unknown[0]}; choose from {', '.join(specs)}.")
    overridden = seeds is not None or seeds_per_component is not None
    frozen = None if overridden else build_config_suites(config)
    recorded = {"test": recorded_test, **(recorded_diagnostics or {})}
    built = []
    for name in names:
        if frozen is not None:
            suite = frozen[name]
            if recorded.get(name) is not None and [r["scenario_fingerprint"] for r in recorded[name]] != [
                    r["scenario_fingerprint"] for r in suite.identities()]:
                raise ValueError(f"Rebuilt {name} suite differs from the identities recorded at training time.")
        else:
            spec = specs[name]
            if seeds_per_component is not None:
                spec = replace(spec, seeds_per_component=seeds_per_component)
            suite = build_config_suite(config, spec, seeds)
        built.append(suite)
    audit = audit_split_isolation({"train_episodes": training_records,
                                   **{suite.name: suite.identities() for suite in built}},
                                  historical_fixture_fingerprints(root))
    freshness = (audit_fresh_suites(built, previously_examined_fingerprints(config))
                 if config.prior_configs else None)
    decision = None
    if config.require_validation_decision and any(suite.split == "test" for suite in built):
        if validation_decision is None:
            raise ValueError("This experiment requires the recorded validation decision before testing.")
        decision = verify_validation_decision(validation_decision, config, checkpoint_hashes)

    rows = []
    cache = ReferenceCache()
    for suite in built:
        rows += evaluate_suite(suite, learned, exact_max_vessels=config.exact_max_vessels,
                               record_dir=output / "runs" if record_runs else None, reference_cache=cache,
                               progress=progress)
    git_commit, git_dirty = get_git_metadata()
    manifest = {
        "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
        "metric_version": METRIC_VERSION,
        "experiment_id": config.experiment_id,
        "config_source": _portable(Path(config.source_path), root) if config.source_path else None,
        "config_sha256": config.source_sha256,
        "checkpoint_kind": kind,
        "checkpoints": [{"label": e.label, "training_seed": e.training_seed, "checkpoint_id": e.checkpoint_id,
                         "checkpoint_path": e.checkpoint_path} for e in learned],
        "training_budgets": budgets,
        "suites": {suite.name: {"split": suite.split, "identities": suite.identities()} for suite in built},
        "split_audit": audit,
        "freshness_audit": freshness,
        "validation_decision": decision,
        "checkpoint_sha256": checkpoint_hashes,
        "exact_max_vessels": config.exact_max_vessels,
        "exact_reference_summary": exact_reference_summary(rows),
        "reference_cache": {"hits": cache.hits, "misses": cache.misses},
        "integrity": integrity_summary(rows),
        "runtime_seconds_by_method": runtime_totals(rows),
        "deterministic_inference": True,
        "action_masking_enabled": True,
        "objective_units": "vessel-minutes (raw, unscaled)",
        "git_commit_hash": git_commit,
        "git_dirty": git_dirty,
        "dependency_versions": dependency_versions(),
        "started_at": started_at,
        "evaluation_runtime_seconds": time.perf_counter() - started,
    }
    return write_evaluation(output, rows, aggregate_rows(rows), manifest)


def exact_reference_summary(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Certified, limit-stopped, failed and ineligible exact references."""

    exact = [r for r in rows if r["method"] == "exact"]
    scenarios = {r["scenario_fingerprint"] for r in rows}
    limit = {"node_limit", "time_limit"}
    certified = sum(r["optimality_status"] == "optimal" and r["run_status"] == "completed" for r in exact)
    stopped = sum(r.get("termination_reason") in limit and r["optimality_status"] != "optimal" for r in exact)
    return {"eligible": len(exact), "certified": certified, "limit_stopped": stopped,
            "failed": len(exact) - certified - stopped, "not_eligible": len(scenarios) - len(exact)}


def integrity_summary(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    failures = Counter(r["failure_type"] for r in rows if not r["is_valid"])
    return {"rows": len(rows), "invalid_rows": sum(not r["is_valid"] for r in rows),
            "invalid_ppo_rows": sum(not r["is_valid"] for r in rows if r["method"] == "ppo"),
            "masked_action_errors": failures.get("MaskedActionError", 0),
            "failure_types": dict(failures)}


def runtime_totals(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Summed per-instance runtime by method (PPO = inference, Exact separate)."""

    totals: dict[str, float] = {}
    for row in rows:
        method = row["method"] if row["method"] != "ppo" else f"ppo[{row['ppo_label']}]"
        totals[method] = totals.get(method, 0.0) + (row["algorithm_runtime_seconds"] or 0.0)
    return totals


def _portable(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")
