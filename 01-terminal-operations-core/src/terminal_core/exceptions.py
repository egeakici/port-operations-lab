class TerminalDomainError(Exception):
    """Base class for terminal domain errors."""
    pass


class VesselValidationError(TerminalDomainError):
    """Raised when vessel data is invalid."""
    pass


class InvalidStatusTransitionError(TerminalDomainError):
    """Raised when a vessel status transition is invalid."""
    pass


class BerthValidationError(TerminalDomainError):
    """Raised when berth or berth occupancy data is invalid."""
    pass


class BerthPlacementError(TerminalDomainError):
    """Raised when a vessel cannot be placed at a berth."""
    pass


class VesselNotFoundAtBerthError(TerminalDomainError):
    """Raised when removing a vessel that is not placed at the berth."""
    pass
