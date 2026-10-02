"""Static policy execution, validation, and scientific result assembly."""

from __future__ import annotations

import re
import sys
import time
import uuid
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from berth_allocation_lab import __version__
from berth_allocation_lab.core import (
    BAPPlacement,
    ScheduleViolationCode,
    find_schedule_violations,
    turnaround_time,
    waiting_time,
)
from berth_allocation_lab.core.numerics import is_close
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.evaluation.metrics import (
    METRIC_VERSION,
    PERCENTILE_METHOD,
    calculate_static_metrics,
)
from berth_allocation_lab.policies import (
    StaticFCFS,
    StaticGreedyRollout,
    StaticPolicy,
    StaticScheduleResult,
)
from berth_allocation_lab.solvers.reference_types import RECORDED_LIMIT_FAILURES
from berth_allocation_lab.tracking.git_metadata import get_git_metadata
from berth_allocation_lab.tracking.records import (
    RunManifest,
    RunSummary,
    ScientificRunResult,
    VesselResult,
)
from berth_allocation_lab.tracking.recorder import ScientificRunRecorder


def run_static_policy(
    scenario: BAPScenarioInstance,
    policy: StaticPolicy,
    output_dir: str | Path | None = None,
    *,
    run_id: str | None = None,
) -> ScientificRunResult:
    """Run one offline policy; invalid/failed schedules remain scientific records."""

    if scenario.formulation != "static":
        raise ValueError("Static policy runner requires a static scenario instance.")
    identifier = run_id or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
        raise ValueError("run_id must contain only letters, digits, underscore or hyphen.")
    git_commit, git_dirty = get_git_metadata()
    manifest = RunManifest(
        run_id=identifier,
        created_at=datetime.now(timezone.utc).isoformat(),
        project_version=__version__,
        git_commit_hash=git_commit,
        git_dirty=git_dirty,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        scenario_seed=scenario.seed,
        scenario_family=scenario.scenario_family,
        scenario_split=scenario.split,
        scenario_fingerprint=scenario.content_fingerprint,
        scenario_schema_version=scenario.scenario_schema_version,
        generator_version=scenario.generator_version,
        formulation=scenario.formulation,
        policy_id=policy.policy_id,
        policy_family=policy.policy_family,
        algorithm_version=policy.algorithm_version,
        data_provenance=scenario.data_provenance,
        problem_spec_version="step1_v1",
        candidate_generator_version="boundary_candidates_v1",
        objective_version="total_waiting_v1",
        metric_version=METRIC_VERSION,
        percentile_method=PERCENTILE_METHOD,
        python_version=sys.version.split()[0],
        status="started",
    )
    recorder = (
        ScientificRunRecorder(output_dir, identifier)
        if output_dir is not None
        else None
    )
    if recorder is not None:
        recorder.start(manifest, scenario)

    started_at = time.perf_counter()
    schedule: StaticScheduleResult | None = None
    violations = ()
    diagnostics = None
    incumbent_metrics = None
    limit_stop = False
    try:
        schedule = policy.schedule(scenario)
        runtime = time.perf_counter() - started_at
        diagnostics = schedule.solver_diagnostics
        if schedule.policy_id != policy.policy_id:
            raise ValueError("Policy result ID differs from policy identity.")
        if diagnostics is not None:
            if diagnostics.scenario_fingerprint != scenario.content_fingerprint:
                raise ValueError("Solver diagnostics belong to a different scenario.")
            if diagnostics.failure_type in RECORDED_LIMIT_FAILURES:
                limit_stop = True
            elif diagnostics.optimality_status == "failed":
                raise ValueError(diagnostics.failure_message or
                                 f"Reference search stopped: {diagnostics.termination_reason}.")
        violations = () if limit_stop else find_schedule_violations(
            scenario.vessels,
            schedule.placements,
            scenario.berth_length_m,
            scenario.min_clearance_m,
        )
        if limit_stop:
            # Recorded size/search-limit outcome without a schedule, not an exception.
            manifest = replace(
                manifest,
                status="failed",
                failure_type=diagnostics.failure_type,
                failure_message=diagnostics.failure_message,
            )
            summary = _failed_summary(
                scenario, policy.policy_id, identifier, runtime,
                "failed", diagnostics.failure_type, 0, schedule,
            )
            vessels = _vessel_results(
                scenario, identifier, policy.policy_id, schedule, valid=False
            )
        elif violations:
            unresolved = any(
                v.code is ScheduleViolationCode.MISSING_PLACEMENT
                for v in violations
            )
            status = "invalid_unresolved_vessels" if unresolved else "failed"
            manifest = replace(
                manifest,
                status=status,
                failure_type="invalid_schedule",
                failure_message="; ".join(v.message for v in violations),
            )
            summary = _failed_summary(
                scenario, policy.policy_id, identifier, runtime, status,
                "invalid_schedule", len(violations), schedule,
            )
            vessels = _vessel_results(
                scenario, identifier, policy.policy_id, schedule, valid=False
            )
        else:
            metrics = calculate_static_metrics(scenario, schedule.placements)
            if diagnostics is not None:
                if not is_close(metrics.objective_value, diagnostics.best_feasible_objective):
                    raise ValueError("Solver objective differs from validated metrics.")
                if diagnostics.optimality_status == "optimal" and not is_close(
                    metrics.objective_value, diagnostics.certified_optimal_objective
                ):
                    raise ValueError("Certified objective differs from validated metrics.")
            manifest = replace(manifest, status="completed")
            summary = RunSummary(
                run_id=identifier,
                scenario_id=scenario.scenario_id,
                scenario_version=scenario.scenario_version,
                seed=scenario.seed,
                formulation=scenario.formulation,
                policy_id=policy.policy_id,
                vessel_count_generated=scenario.vessel_count,
                vessel_count_completed=scenario.vessel_count,
                vessel_count_unresolved=0,
                nominal_duration_min=scenario.nominal_duration_min,
                simulation_end_time_min=metrics.schedule_end_time_min,
                total_waiting_time_min=metrics.total_waiting_time_min,
                mean_waiting_time_min=metrics.mean_waiting_time_min,
                p95_waiting_time_min=metrics.p95_waiting_time_min,
                mean_turnaround_time_min=metrics.mean_turnaround_time_min,
                p95_turnaround_time_min=metrics.p95_turnaround_time_min,
                berth_utilization=metrics.berth_utilization,
                occupied_quay_length_minutes=metrics.occupied_quay_length_minutes,
                utilization_window_min=metrics.utilization_window_min,
                throughput_vessels=metrics.throughput_vessels,
                algorithm_runtime_seconds=runtime,
                objective_value=metrics.objective_value,
                status="completed",
                is_valid=True,
                validation_status="valid",
                violation_count=0,
            )
            vessels = _vessel_results(
                scenario, identifier, policy.policy_id, schedule, valid=True
            )
    except Exception as error:
        runtime = time.perf_counter() - started_at
        manifest = replace(
            manifest,
            status="failed",
            failure_type=type(error).__name__,
            failure_message=str(error),
        )
        summary = _failed_summary(
            scenario, policy.policy_id, identifier, runtime,
            "failed", "exception", len(violations), schedule,
        )
        vessels = _vessel_results(
            scenario, identifier, policy.policy_id, schedule, valid=False
        )

    if diagnostics is not None:
        if limit_stop:
            # Keep the solver's status and size/search-limit classification.
            pass
        elif not summary.is_valid:
            # Prefer the solver's own error over the runner's wrapper, but never
            # let a limit label mask a genuine runner-side error.
            solver_error = diagnostics.failure_type not in {None, *RECORDED_LIMIT_FAILURES}
            manifest = replace(
                manifest, status="failed",
                failure_type=diagnostics.failure_type if solver_error else manifest.failure_type,
                failure_message=(
                    diagnostics.failure_message if solver_error else None
                ) or manifest.failure_message,
            )
            summary = replace(summary, status="failed")
            diagnostics = replace(
                diagnostics, optimality_status="failed",
                best_feasible_objective=None, certified_optimal_objective=None, optimality_gap=None,
                failure_type=manifest.failure_type,
                failure_message=manifest.failure_message,
            )
        elif diagnostics.optimality_status == "feasible":
            incumbent_metrics = metrics
            manifest = replace(manifest, status="completed_with_limit")
            # Keep physical completion/vessel records, but exclude an uncertified
            # incumbent from headline reference KPIs and certified gap tables.
            summary = replace(
                summary, status="completed_with_limit", validation_status="valid_uncertified",
                total_waiting_time_min=None, mean_waiting_time_min=None,
                p95_waiting_time_min=None, mean_turnaround_time_min=None,
                p95_turnaround_time_min=None, berth_utilization=None,
                occupied_quay_length_minutes=None, utilization_window_min=None,
                objective_value=None,
            )
        manifest = replace(
            manifest, solver_family=diagnostics.solver_family,
            solver_version=diagnostics.solver_version,
            reference_scope=diagnostics.reference_scope,
            optimality_status=diagnostics.optimality_status,
        )
        summary = replace(
            summary, reference_scope=diagnostics.reference_scope,
            optimality_status=diagnostics.optimality_status,
            best_feasible_objective=diagnostics.best_feasible_objective,
            certified_optimal_objective=diagnostics.certified_optimal_objective,
            solver_runtime_seconds=diagnostics.solver_runtime_seconds,
            time_limit_seconds=diagnostics.time_limit_seconds,
            optimality_gap=diagnostics.optimality_gap,
        )
        schedule = replace(schedule, solver_diagnostics=diagnostics)
    result = ScientificRunResult(
        scenario=scenario,
        manifest=manifest,
        schedule=schedule,
        decisions=schedule.decision_records if schedule is not None else (),
        vessels=vessels,
        summary=summary,
        violations=violations,
        solver_diagnostics=diagnostics,
        incumbent_metrics=incumbent_metrics,
    )
    if recorder is not None:
        try:
            recorder.finish(result)
        except (OSError, TypeError, ValueError) as error:
            failed_manifest = replace(
                result.manifest,
                status="failed",
                failure_type="serialization_failure",
                failure_message=str(error),
                optimality_status="failed" if diagnostics is not None else None,
            )
            failed_summary = _failed_summary(
                scenario, policy.policy_id, identifier,
                result.summary.algorithm_runtime_seconds,
                "failed", "recording_failed", len(result.violations), schedule,
            )
            result = replace(
                result,
                manifest=failed_manifest,
                summary=failed_summary,
                vessels=_vessel_results(
                    scenario, identifier, policy.policy_id, schedule, valid=False
                ),
                solver_diagnostics=(replace(
                    diagnostics, optimality_status="failed", best_feasible_objective=None,
                    certified_optimal_objective=None,
                    optimality_gap=None, failure_type="serialization_failure",
                    failure_message=str(error),
                ) if diagnostics is not None else None),
                incumbent_metrics=None,
            )
            if diagnostics is not None:
                failed_summary = replace(
                    failed_summary, reference_scope=diagnostics.reference_scope,
                    optimality_status="failed", solver_runtime_seconds=diagnostics.solver_runtime_seconds,
                    time_limit_seconds=diagnostics.time_limit_seconds,
                )
                result = replace(result, summary=failed_summary)
                result = replace(result, schedule=replace(
                    result.schedule, solver_diagnostics=result.solver_diagnostics,
                ))
            recorder.record_failure(failed_manifest, failed_summary, result.vessels)
            if result.solver_diagnostics is not None:
                recorder.record_solver_diagnostics(result)
    return result


def compare_static_baselines(
    scenario: BAPScenarioInstance,
    output_dir: str | Path | None = None,
) -> tuple[ScientificRunResult, ScientificRunResult]:
    """Evaluate FCFS and Greedy against exactly the same static instance."""

    if scenario.formulation != "static":
        raise ValueError("Baseline comparison requires a static scenario instance.")
    return (
        run_static_policy(scenario, StaticFCFS(), output_dir),
        run_static_policy(scenario, StaticGreedyRollout(), output_dir),
    )


def _vessel_results(
    scenario: BAPScenarioInstance,
    run_id: str,
    policy_id: str,
    schedule: StaticScheduleResult | None,
    *,
    valid: bool,
) -> tuple[VesselResult, ...]:
    by_id = _unambiguous_placements(scenario, schedule)
    rows = []
    for vessel in scenario.vessels:
        placement = by_id.get(vessel.vessel_id)
        rows.append(
            VesselResult(
                run_id=run_id,
                scenario_id=scenario.scenario_id,
                policy_id=policy_id,
                vessel_id=vessel.vessel_id,
                arrival_time_min=vessel.arrival_time_min,
                length_m=vessel.length_m,
                service_time_min=vessel.service_time_min,
                berth_position_m=(placement.berth_position_m if placement else None),
                berth_start_time_min=(
                    placement.berth_start_time_min if placement else None
                ),
                service_end_time_min=(
                    placement.service_end_time_min if placement else None
                ),
                waiting_time_min=(
                    waiting_time(vessel, placement) if valid and placement else None
                ),
                turnaround_time_min=(
                    turnaround_time(vessel, placement) if valid and placement else None
                ),
                completed=valid,
                completion_status=(
                    "completed" if valid else "failed" if placement else "unresolved"
                ),
            )
        )
    return tuple(rows)


def _unambiguous_placements(
    scenario: BAPScenarioInstance,
    schedule: StaticScheduleResult | None,
) -> dict[str, BAPPlacement]:
    """Keep only known vessel IDs with exactly one valid placement object."""

    input_counts = Counter(v.vessel_id for v in scenario.vessels)
    if schedule is None:
        return {}
    placement_counts = Counter(
        placement.vessel_id
        for placement in schedule.placements
        if isinstance(placement, BAPPlacement)
    )
    return {
        placement.vessel_id: placement
        for placement in schedule.placements
        if isinstance(placement, BAPPlacement)
        and input_counts[placement.vessel_id] == 1
        and placement_counts[placement.vessel_id] == 1
    }


def _failed_summary(
    scenario: BAPScenarioInstance,
    policy_id: str,
    run_id: str,
    runtime: float,
    status: str,
    validation_status: str,
    violation_count: int,
    schedule: StaticScheduleResult | None,
) -> RunSummary:
    unambiguous = _unambiguous_placements(scenario, schedule)
    unresolved_count = sum(
        vessel.vessel_id not in unambiguous for vessel in scenario.vessels
    )
    return RunSummary(
        run_id=run_id,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        seed=scenario.seed,
        formulation=scenario.formulation,
        policy_id=policy_id,
        vessel_count_generated=scenario.vessel_count,
        vessel_count_completed=0,
        vessel_count_unresolved=unresolved_count,
        nominal_duration_min=scenario.nominal_duration_min,
        simulation_end_time_min=None,
        total_waiting_time_min=None,
        mean_waiting_time_min=None,
        p95_waiting_time_min=None,
        mean_turnaround_time_min=None,
        p95_turnaround_time_min=None,
        berth_utilization=None,
        occupied_quay_length_minutes=None,
        utilization_window_min=None,
        throughput_vessels=0,
        algorithm_runtime_seconds=runtime,
        objective_value=None,
        status=status,
        is_valid=False,
        validation_status=validation_status,
        violation_count=violation_count,
    )
