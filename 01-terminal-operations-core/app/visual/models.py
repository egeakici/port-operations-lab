from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VisualPoint:
    x: float
    y: float


@dataclass(frozen=True)
class VisualRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> VisualPoint:
        return VisualPoint(
            self.x + self.width / 2.0,
            self.y + self.height / 2.0,
        )


@dataclass(frozen=True)
class CargoBadgeVisual:
    group_id: str
    teu: float


@dataclass(frozen=True)
class BerthVisual:
    berth_id: str
    rect: VisualRect
    length_m: float
    min_clearance_m: float
    normalized_start: float
    normalized_width: float


@dataclass(frozen=True)
class VesselVisual:
    vessel_id: str
    status: str
    rect: VisualRect
    length_m: float
    cargo: tuple[CargoBadgeVisual, ...] = ()
    berth_id: str | None = None
    start_position_m: float | None = None
    normalized_x: float | None = None
    normalized_width: float | None = None
    eta: str | None = None
    departed: bool = False


@dataclass(frozen=True)
class CraneVisual:
    crane_id: str
    status: str
    rect: VisualRect
    position_m: float
    normalized_x: float
    assigned_vessel_id: str | None = None
    active_task_id: str | None = None
    failed: bool = False


@dataclass(frozen=True)
class YardBlockVisual:
    block_id: str
    status: str
    rect: VisualRect
    capacity_teu: float
    stored_teu: float
    reserved_teu: float
    available_teu: float
    capabilities: tuple[str, ...]
    stored_groups: tuple[CargoBadgeVisual, ...] = ()
    reservations: tuple[CargoBadgeVisual, ...] = ()


@dataclass(frozen=True)
class GateVisual:
    gate_id: str
    rect: VisualRect
    cargo: tuple[CargoBadgeVisual, ...] = ()


@dataclass(frozen=True)
class TaskFlowVisual:
    task_id: str
    task_type: str
    status: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    source: VisualPoint
    target: VisualPoint
    planned_teu: float
    completed_teu: float
    progress_pct: float
    blocked: bool = False


@dataclass(frozen=True)
class TerminalVisualScene:
    width: float
    height: float
    berths: tuple[BerthVisual, ...] = ()
    vessels: tuple[VesselVisual, ...] = ()
    anchorage_vessels: tuple[VesselVisual, ...] = ()
    departed_vessels: tuple[VesselVisual, ...] = ()
    cranes: tuple[CraneVisual, ...] = ()
    yard_blocks: tuple[YardBlockVisual, ...] = ()
    gates: tuple[GateVisual, ...] = ()
    task_flows: tuple[TaskFlowVisual, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (
            self.berths
            or self.vessels
            or self.anchorage_vessels
            or self.cranes
            or self.yard_blocks
            or self.gates
            or self.task_flows
        )

