"""Serializable scientific records for static policy runs."""

from __future__ import annotations

from dataclasses import dataclass

from berth_allocation_lab.core import BAPPlacement, ScheduleViolation
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.policies import StaticDecisionRecord, StaticScheduleResult


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    created_at: str
    project_version: str
    git_commit_hash: str | None
    git_dirty: bool | None
    scenario_id: str
    scenario_version: int
    scenario_seed: int
    scenario_family: str
    scenario_split: str
    scenario_fingerprint: str
    scenario_schema_version: int
    generator_version: str
    formulation: str
    policy_id: str
    policy_family: str
    algorithm_version: str
    data_provenance: str
    problem_spec_version: str
    candidate_generator_version: str
    objective_version: str
    metric_version: str
    percentile_method: str
    python_version: str
    status: str
    failure_type: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True)
class VesselResult:
    run_id: str
    scenario_id: str
    policy_id: str
    vessel_id: str
    arrival_time_min: float
    length_m: float
    service_time_min: float
    berth_position_m: float | None
    berth_start_time_min: float | None
    service_end_time_min: float | None
    waiting_time_min: float | None
    turnaround_time_min: float | None
    completed: bool
    completion_status: str


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    scenario_id: str
    scenario_version: int
    seed: int
    formulation: str
    policy_id: str
    vessel_count_generated: int
    vessel_count_completed: int
    vessel_count_unresolved: int
    nominal_duration_min: float
    simulation_end_time_min: float | None
    total_waiting_time_min: float | None
    mean_waiting_time_min: float | None
    p95_waiting_time_min: float | None
    mean_turnaround_time_min: float | None
    p95_turnaround_time_min: float | None
    berth_utilization: float | None
    occupied_quay_length_minutes: float | None
    utilization_window_min: float | None
    throughput_vessels: int
    algorithm_runtime_seconds: float
    objective_value: float | None
    status: str
    is_valid: bool
    validation_status: str
    violation_count: int


@dataclass(frozen=True)
class ScientificRunResult:
    scenario: BAPScenarioInstance
    manifest: RunManifest
    schedule: StaticScheduleResult | None
    decisions: tuple[StaticDecisionRecord, ...]
    vessels: tuple[VesselResult, ...]
    summary: RunSummary
    violations: tuple[ScheduleViolation, ...]

    @property
    def placements(self) -> tuple[BAPPlacement, ...]:
        return self.schedule.placements if self.schedule is not None else ()
