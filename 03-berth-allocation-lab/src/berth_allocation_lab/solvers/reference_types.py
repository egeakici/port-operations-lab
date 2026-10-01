"""Versioned candidate-space reference configuration and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from berth_allocation_lab.core import BAPPlacement
from berth_allocation_lab.core.numerics import is_finite_number

if TYPE_CHECKING:
    from berth_allocation_lab.policies.base import StaticDecisionRecord


# A node/time limit stopped the search before any valid incumbent existed.
SEARCH_LIMIT_FAILURE = "search_limit_reached"
SEARCH_LIMIT_REASONS = frozenset({"node_limit", "time_limit"})


@dataclass(frozen=True)
class CandidateEnumerationConfig:
    max_vessels: int = 6
    max_search_nodes: int = 250_000
    time_limit_seconds: float | None = None
    initial_incumbent: Literal["none", "fcfs", "rollout"] = "fcfs"
    enable_pruning: bool = True
    stop_at_zero: bool = True

    def __post_init__(self) -> None:
        for name in ("max_vessels", "max_search_nodes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a finite positive integer.")
        if self.max_vessels > 8:
            raise ValueError("Tiny enumeration supports at most 8 vessels.")
        if self.time_limit_seconds is not None and (
            not is_finite_number(self.time_limit_seconds)
            or self.time_limit_seconds <= 0
        ):
            raise ValueError("time_limit_seconds must be finite and positive.")
        if self.initial_incumbent not in {"none", "fcfs", "rollout"}:
            raise ValueError("initial_incumbent must be none, fcfs or rollout.")
        if not isinstance(self.enable_pruning, bool) or not isinstance(self.stop_at_zero, bool):
            raise ValueError("Search switches must be booleans.")


@dataclass(frozen=True)
class CandidateEnumerationDiagnostics:
    scenario_fingerprint: str
    optimality_status: Literal["optimal", "feasible", "timeout", "failed"]
    best_feasible_objective: float | None
    certified_optimal_objective: float | None
    nodes_explored: int
    branches_pruned: int
    complete_schedules_evaluated: int
    solver_runtime_seconds: float
    termination_reason: str | None
    max_vessels: int
    max_search_nodes: int
    time_limit_seconds: float | None
    initial_incumbent: str
    enable_pruning: bool
    stop_at_zero: bool
    incumbent_source: str | None
    solver_family: str = "exhaustive_enumeration"
    solver_version: str = "v1"
    reference_scope: str = "candidate_space"
    optimality_gap: float | None = None
    record_schema_version: int = 1
    failure_type: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True)
class CandidateEnumerationResult:
    best_placements: tuple[BAPPlacement, ...]
    decision_records: tuple[StaticDecisionRecord, ...]
    diagnostics: CandidateEnumerationDiagnostics
