"""Static policy execution, validation, and scientific result assembly."""

from __future__ import annotations

import re
import sys
import time
import uuid
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
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.evaluation.metrics import (
    METRIC_VERSION,
    calculate_static_metrics,
)
from berth_allocation_lab.policies import (
    StaticFCFS,
    StaticGreedyLookahead,
    StaticPolicy,
    StaticScheduleResult,
)
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
    try:
        schedule = policy.schedule(scenario)
        runtime = time.perf_counter() - started_at
        if schedule.policy_id != policy.policy_id:
            raise ValueError("Policy result ID differs from policy identity.")
        violations = find_schedule_violations(
            scenario.vessels,
            schedule.placements,
            scenario.berth_length_m,
            scenario.min_clearance_m,
        )
        if violations:
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
                "invalid_schedule", len(violations),
            )
            vessels = _vessel_results(
                scenario, identifier, policy.policy_id, schedule, valid=False
            )
        else:
            metrics = calculate_static_metrics(scenario, schedule.placements)
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
                throughput_vessels=metrics.throughput_vessels,
                schedule_end_time_min=metrics.schedule_end_time_min,
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
            "failed", "exception", len(violations),
        )
        vessels = _vessel_results(
            scenario, identifier, policy.policy_id, schedule, valid=False
        )

    result = ScientificRunResult(
        scenario=scenario,
        manifest=manifest,
        schedule=schedule,
        decisions=schedule.decision_records if schedule is not None else (),
        vessels=vessels,
        summary=summary,
        violations=violations,
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
            )
            failed_summary = _failed_summary(
                scenario, policy.policy_id, identifier,
                result.summary.algorithm_runtime_seconds,
                "failed", "recording_failed", len(result.violations),
            )
            result = replace(
                result,
                manifest=failed_manifest,
                summary=failed_summary,
                vessels=_vessel_results(
                    scenario, identifier, policy.policy_id, schedule, valid=False
                ),
            )
            recorder.record_failure(failed_manifest, failed_summary)
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
        run_static_policy(scenario, StaticGreedyLookahead(), output_dir),
    )


def _vessel_results(
    scenario: BAPScenarioInstance,
    run_id: str,
    policy_id: str,
    schedule: StaticScheduleResult | None,
    *,
    valid: bool,
) -> tuple[VesselResult, ...]:
    by_id: dict[str, BAPPlacement] = {}
    duplicate_ids: set[str] = set()
    if schedule is not None:
        for placement in schedule.placements:
            if not isinstance(placement, BAPPlacement):
                continue
            if placement.vessel_id in by_id:
                duplicate_ids.add(placement.vessel_id)
            else:
                by_id[placement.vessel_id] = placement
    rows = []
    for vessel in scenario.vessels:
        placement = (
            None if vessel.vessel_id in duplicate_ids else by_id.get(vessel.vessel_id)
        )
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


def _failed_summary(
    scenario: BAPScenarioInstance,
    policy_id: str,
    run_id: str,
    runtime: float,
    status: str,
    validation_status: str,
    violation_count: int,
) -> RunSummary:
    return RunSummary(
        run_id=run_id,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        seed=scenario.seed,
        formulation=scenario.formulation,
        policy_id=policy_id,
        vessel_count_generated=scenario.vessel_count,
        vessel_count_completed=0,
        vessel_count_unresolved=scenario.vessel_count,
        nominal_duration_min=scenario.nominal_duration_min,
        simulation_end_time_min=None,
        total_waiting_time_min=None,
        mean_waiting_time_min=None,
        p95_waiting_time_min=None,
        mean_turnaround_time_min=None,
        p95_turnaround_time_min=None,
        berth_utilization=None,
        throughput_vessels=0,
        schedule_end_time_min=None,
        algorithm_runtime_seconds=runtime,
        objective_value=None,
        status=status,
        is_valid=False,
        validation_status=validation_status,
        violation_count=violation_count,
    )
