"""Structured kernel errors (integration specification §8.3, foundation §9).

Every error carries a stable ``code``. Codes reuse the Step 1 taxonomy where one
exists (``INVALID_STATUS_TRANSITION``, ``YARD_CAPACITY_EXCEEDED``,
``UNAVAILABLE_SOURCE_INVENTORY``, ``MISSING_DESTINATION_CAPACITY`` ...). An
error is never repaired: the run is marked ``FAILED`` (or, for an action
rejection, the action is refused before any state mutation).
"""

from __future__ import annotations


class KernelError(RuntimeError):
    """Base class: a kernel failure with a stable code."""

    code = "KERNEL_FAILURE"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class KernelTimeError(KernelError):
    """An event was scheduled or popped before the current clock (spec §8.3)."""

    code = "KERNEL_TIME_ERROR"


class KernelLivelockError(KernelError):
    """The same-timestamp cycle limit was exceeded (spec §8.3)."""

    code = "KERNEL_LIVELOCK"


class InvalidStatusTransition(KernelError):
    """A container, vessel, crane or work-order transition outside its declared table (DQ15)."""

    code = "INVALID_STATUS_TRANSITION"


class InvariantViolation(KernelError):
    """A runtime physical invariant (INV01-INV20) failed."""

    code = "INVARIANT_VIOLATION"

    def __init__(self, invariant: str, message: str, *, code: str | None = None) -> None:
        super().__init__(f"{invariant}: {message}", code=code)
        self.invariant = invariant


class UnsupportedScenario(KernelError):
    """The scenario uses an assumption v1 physics does not execute (DQ20)."""

    code = "UNSUPPORTED_ASSUMPTION"


class DecisionProtocolError(KernelError):
    """The caller used the decision API out of order (no state is changed)."""

    code = "DECISION_PROTOCOL_ERROR"


class PhysicalActionRejected(KernelError):
    """The PhysicalActionValidator refused an action; the kernel state is unchanged.

    ``rejection_code`` is the structured reason; ``code`` stays the Step 3 outcome
    class ``PHYSICAL_ACTION_REJECTION``.
    """

    code = "PHYSICAL_ACTION_REJECTION"

    def __init__(self, rejection_code: str, message: str, *, decision_kind: str) -> None:
        super().__init__(f"[{decision_kind}/{rejection_code}] {message}")
        self.rejection_code = rejection_code
        self.decision_kind = decision_kind


__all__ = [
    "DecisionProtocolError", "InvalidStatusTransition", "InvariantViolation", "KernelError",
    "KernelLivelockError", "KernelTimeError", "PhysicalActionRejected", "UnsupportedScenario",
]
