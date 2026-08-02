class TerminalDomainError(Exception):
    """Base class for terminal domain errors."""


class VesselValidationError(TerminalDomainError):
    """Raised when vessel data is invalid."""


class InvalidStatusTransitionError(TerminalDomainError):
    """Raised when a vessel status transition is invalid."""


class BerthValidationError(TerminalDomainError):
    """Raised when berth or berth occupancy data is invalid."""


class BerthPlacementError(TerminalDomainError):
    """Raised when a vessel cannot be placed at a berth."""


class VesselNotFoundAtBerthError(TerminalDomainError):
    """Raised when removing a vessel that is not placed at the berth."""


class QuayCraneValidationError(TerminalDomainError):
    """Geçersiz quay crane verileri için kullanılır."""


class InvalidCraneStatusTransitionError(TerminalDomainError):
    """Geçersiz vinç durum geçişlerinde kullanılır."""


class CraneAssignmentError(TerminalDomainError):
    """Vinç-gemi atama işlemlerindeki hatalar için kullanılır."""


class CraneOperationError(TerminalDomainError):
    """Vinç operasyonu, hareketi, arızası ve bakımı hataları."""

    