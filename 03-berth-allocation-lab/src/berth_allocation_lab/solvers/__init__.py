"""Tiny candidate-space references, distinct from continuous optimizers."""

from berth_allocation_lab.solvers.candidate_enumeration import StaticCandidateEnumeration
from berth_allocation_lab.solvers.reference_types import (
    RECORDED_LIMIT_FAILURES,
    SEARCH_LIMIT_FAILURE,
    SIZE_LIMIT_FAILURE,
    CandidateEnumerationConfig,
    CandidateEnumerationDiagnostics,
    CandidateEnumerationResult,
)

__all__ = [
    "RECORDED_LIMIT_FAILURES", "SEARCH_LIMIT_FAILURE", "SIZE_LIMIT_FAILURE",
    "StaticCandidateEnumeration", "CandidateEnumerationConfig",
    "CandidateEnumerationDiagnostics", "CandidateEnumerationResult",
]

