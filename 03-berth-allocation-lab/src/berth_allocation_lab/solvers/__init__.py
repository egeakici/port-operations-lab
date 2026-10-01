"""Tiny candidate-space references, distinct from continuous optimizers."""

from berth_allocation_lab.solvers.candidate_enumeration import StaticCandidateEnumeration
from berth_allocation_lab.solvers.reference_types import (
    SEARCH_LIMIT_FAILURE,
    CandidateEnumerationConfig,
    CandidateEnumerationDiagnostics,
    CandidateEnumerationResult,
)

__all__ = [
    "SEARCH_LIMIT_FAILURE", "StaticCandidateEnumeration", "CandidateEnumerationConfig",
    "CandidateEnumerationDiagnostics", "CandidateEnumerationResult",
]

