"""Paired comparisons against a certified candidate-space reference only."""

from dataclasses import dataclass

from berth_allocation_lab.core import NUMERICAL_TOLERANCE
from berth_allocation_lab.core.numerics import is_finite_number
from berth_allocation_lab.solvers.reference_types import CandidateEnumerationDiagnostics
from berth_allocation_lab.tracking.records import ScientificRunResult


@dataclass(frozen=True)
class CandidateReferenceGap:
    absolute_gap_min: float
    relative_gap: float | None
    label: str = "candidate-space reference gap"


def candidate_space_reference_gap(
    heuristic_objective: float,
    reference: CandidateEnumerationDiagnostics,
) -> CandidateReferenceGap:
    """Numeric helper; the caller must pair identical scenarios/formulations."""
    optimum = reference.certified_optimal_objective
    if (reference.optimality_status != "optimal"
            or reference.reference_scope != "candidate_space"
            or optimum is None or not is_finite_number(optimum) or optimum < 0):
        raise ValueError("A certified candidate-space optimal reference is required.")
    if not is_finite_number(heuristic_objective) or heuristic_objective < 0:
        raise ValueError("Heuristic objective must be finite and non-negative.")
    gap = heuristic_objective - optimum
    if gap < -NUMERICAL_TOLERANCE:
        raise ValueError("Heuristic beats the certified candidate-space reference.")
    if abs(gap) <= NUMERICAL_TOLERANCE:
        gap = 0.0
    relative = gap / optimum if optimum > 0 else (0.0 if gap == 0 else None)
    return CandidateReferenceGap(gap, relative)


def compare_to_candidate_reference(
    heuristic: ScientificRunResult,
    reference: ScientificRunResult,
) -> CandidateReferenceGap:
    if heuristic.scenario.content_fingerprint != reference.scenario.content_fingerprint:
        raise ValueError("Candidate-space comparison requires identical scenarios.")
    if (not heuristic.summary.is_valid or heuristic.summary.objective_value is None
            or not reference.summary.is_valid or reference.manifest.status != "completed"
            or reference.solver_diagnostics is None):
        raise ValueError("Comparison requires valid completed runs and a reference.")
    return candidate_space_reference_gap(
        heuristic.summary.objective_value, reference.solver_diagnostics,
    )
