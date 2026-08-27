from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VisualRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0


@dataclass(frozen=True)
class BerthReplayVisual:
    berth_id: str
    rect: VisualRect
    length_m: float
    min_clearance_m: float


@dataclass(frozen=True)
class VesselReplayVisual:
    vessel_id: str
    status: str
    rect: VisualRect
    length_m: float | None
    workload_moves: int | None = None
    berth_id: str | None = None
    start_position_m: float | None = None


@dataclass(frozen=True)
class CraneReplayVisual:
    crane_id: str
    status: str
    rect: VisualRect
    position_m: float
    assigned_vessel_id: str | None = None
    task_id: str | None = None
    moves_per_hour: float | None = None


@dataclass(frozen=True)
class YardReplayVisual:
    yard_id: str
    rect: VisualRect
    occupied_teu: float
    capacity_teu: float
    status: str = "open"

    @property
    def utilization(self) -> float:
        if self.capacity_teu <= 0:
            return 0.0
        return min(1.0, max(0.0, self.occupied_teu / self.capacity_teu))


@dataclass(frozen=True)
class TerminalReplayScene:
    width: float
    height: float
    elapsed_minutes: float
    event_id: str | None
    event_type: str | None
    berths: tuple[BerthReplayVisual, ...] = ()
    berthed_vessels: tuple[VesselReplayVisual, ...] = ()
    waiting_vessels: tuple[VesselReplayVisual, ...] = ()
    waiting_overflow_count: int = 0
    departed_vessels: tuple[VesselReplayVisual, ...] = ()
    cranes: tuple[CraneReplayVisual, ...] = ()
    yards: tuple[YardReplayVisual, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)
