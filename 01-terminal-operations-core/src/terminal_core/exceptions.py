class TerminalDomainError(Exception):
    """Terminal domain kurallarından kaynaklanan temel hata sınıfı."""
    pass

class VesselValidationError(TerminalDomainError):
    """Geçersiz Vessel verisi verildiğinde oluşur."""
    pass

class InvalidStatusTransitionError(TerminalDomainError):
    """Geçersiz gemi durum geçişinde oluşur."""
    pass