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


class YardBlockValidationError(TerminalDomainError):
    """Geçersiz YardBlock verileri için kullanılır."""


class InvalidYardBlockStatusTransitionError(
    TerminalDomainError
):
    """Geçersiz YardBlock durum geçişlerinde kullanılır."""


class YardCapacityError(TerminalDomainError):
    """Yard kapasitesi veya stok miktarı ihlallerinde kullanılır."""


class YardCompatibilityError(TerminalDomainError):
    """Block ile konteyner gereksinimleri uyumsuz olduğunda kullanılır."""


class YardReservationError(TerminalDomainError):
    """Yard rezervasyon yaşam döngüsü hatalarında kullanılır."""


class ContainerGroupValidationError(TerminalDomainError):
    """Geçersiz ContainerGroup verileri için kullanılır."""


class ContainerFlowError(TerminalDomainError):
    """Konteyner akışı ve gemi bağlantısı hataları için kullanılır."""


class ContainerCargoError(TerminalDomainError):
    """Konteyner yük özelliklerindeki çelişkiler için kullanılır."""


class TaskLocationValidationError(TerminalDomainError):
    """Geçersiz task konumları için kullanılır."""


class OperationTaskValidationError(TerminalDomainError):
    """Geçersiz OperationTask temel verileri için kullanılır."""


class OperationRouteError(TerminalDomainError):
    """OperationType ile kaynak-hedef rotası uyumsuz olduğunda kullanılır."""


class InvalidOperationTaskStatusTransitionError(
    TerminalDomainError
):
    """Geçersiz OperationTask durum geçişlerinde kullanılır."""


class OperationTaskAssignmentError(TerminalDomainError):
    """Resource atama ve kaldırma hatalarında kullanılır."""


class OperationTaskProgressError(TerminalDomainError):
    """Task ilerleme miktarı hatalarında kullanılır."""


class OperationTaskStateError(TerminalDomainError):
    """Task davranışı mevcut durumda uygulanamıyorsa kullanılır."""


class TerminalEventValidationError(TerminalDomainError):
    """Geçersiz TerminalEvent temel verileri için kullanılır."""


class TerminalEventPayloadError(TerminalDomainError):
    """JSON uyumlu olmayan veya geçersiz event payload verileri için kullanılır."""


class TerminalEventEntityMismatchError(TerminalDomainError):
    """Event türü ile birincil entity türü uyuşmadığında kullanılır."""


class ContainerGroupLocationValidationError(TerminalDomainError):
    """Raised when container group location data is invalid."""


class TerminalStateValidationError(TerminalDomainError):
    """Raised when TerminalState snapshot data is invalid."""


class TerminalStateDuplicateEntityError(TerminalDomainError):
    """Raised when TerminalState capture finds a duplicate entity ID."""


class TerminalStateReferenceError(TerminalDomainError):
    """Raised when TerminalState has a missing cross-entity reference."""


class TerminalStateConsistencyError(TerminalDomainError):
    """Raised when TerminalState cross-entity invariants are violated."""


class TerminalStateLookupError(TerminalDomainError):
    """Raised when a TerminalState lookup cannot be resolved."""


class YardOperationError(TerminalDomainError):
    """Yard depolama, çıkarma ve operasyon durumu hatalarında kullanılır."""
