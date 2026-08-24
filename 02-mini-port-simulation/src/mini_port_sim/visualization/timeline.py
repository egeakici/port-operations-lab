from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mini_port_sim.metrics.collector import (
    _berth_intervals,
    _crane_failed_intervals,
    _crane_operating_intervals,
)

if TYPE_CHECKING:
    from mini_port_sim.simulation import PortSimulation


@dataclass(frozen=True)
class BerthTimelineSegment:
    vessel_id: str
    berth_id: str
    start_position_m: float
    end_position_m: float
    start_minutes: float
    end_minutes: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel_id": self.vessel_id,
            "berth_id": self.berth_id,
            "start_position_m": self.start_position_m,
            "end_position_m": self.end_position_m,
            "start_minutes": self.start_minutes,
            "end_minutes": self.end_minutes,
        }


@dataclass(frozen=True)
class CraneTimelineSegment:
    crane_id: str
    state: str
    start_minutes: float
    end_minutes: float
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "crane_id": self.crane_id,
            "state": self.state,
            "start_minutes": self.start_minutes,
            "end_minutes": self.end_minutes,
            "task_id": self.task_id,
        }


@dataclass(frozen=True)
class VesselTimelineSegment:
    vessel_id: str
    state: str
    start_minutes: float
    end_minutes: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "vessel_id": self.vessel_id,
            "state": self.state,
            "start_minutes": self.start_minutes,
            "end_minutes": self.end_minutes,
        }


def build_berth_timeline(
    simulation: "PortSimulation",
) -> tuple[BerthTimelineSegment, ...]:
    segments = [
        BerthTimelineSegment(
            vessel_id=str(interval["vessel_id"]),
            berth_id=str(interval["berth_id"]),
            start_position_m=float(interval["start_position_m"]),
            end_position_m=float(interval["end_position_m"]),
            start_minutes=float(interval["start_minutes"]),
            end_minutes=float(interval["end_minutes"]),
        )
        for interval in _berth_intervals(
            simulation,
            simulation.elapsed_minutes,
        )
    ]

    return tuple(
        sorted(
            segments,
            key=lambda segment: (
                segment.berth_id,
                segment.start_minutes,
                segment.start_position_m,
            ),
        )
    )


def build_crane_timeline(
    simulation: "PortSimulation",
) -> tuple[CraneTimelineSegment, ...]:
    segments = [
        CraneTimelineSegment(
            crane_id=crane_id,
            state="operating",
            start_minutes=start_minutes,
            end_minutes=end_minutes,
            task_id=task_id,
        )
        for crane_id, task_id, start_minutes, end_minutes
        in _crane_operating_intervals(
            simulation,
            simulation.elapsed_minutes,
        )
    ]
    segments.extend(
        CraneTimelineSegment(
            crane_id=crane_id,
            state="failed",
            start_minutes=start_minutes,
            end_minutes=end_minutes,
        )
        for crane_id, start_minutes, end_minutes in _crane_failed_intervals(
            simulation,
            simulation.elapsed_minutes,
        )
    )

    return tuple(
        sorted(
            segments,
            key=lambda segment: (
                segment.crane_id,
                segment.start_minutes,
                segment.state,
            ),
        )
    )


def build_vessel_timeline(
    simulation: "PortSimulation",
) -> tuple[VesselTimelineSegment, ...]:
    metrics = simulation.collect_metrics().vessel_metrics
    segments: list[VesselTimelineSegment] = []
    horizon = simulation.elapsed_minutes

    for vessel in metrics:
        if vessel.berth_time_minutes is None:
            _append_segment(
                segments,
                vessel.vessel_id,
                "waiting",
                vessel.arrival_time_minutes,
                horizon,
            )
            continue

        _append_segment(
            segments,
            vessel.vessel_id,
            "waiting",
            vessel.arrival_time_minutes,
            vessel.berth_time_minutes,
        )

        if vessel.operation_start_minutes is None:
            _append_segment(
                segments,
                vessel.vessel_id,
                "berthed_preparation",
                vessel.berth_time_minutes,
                horizon,
            )
            continue

        _append_segment(
            segments,
            vessel.vessel_id,
            "berthed_preparation",
            vessel.berth_time_minutes,
            vessel.operation_start_minutes,
        )

        operating_end = vessel.operation_end_minutes or horizon
        _append_segment(
            segments,
            vessel.vessel_id,
            "operating",
            vessel.operation_start_minutes,
            operating_end,
        )

        if vessel.operation_end_minutes is not None:
            _append_segment(
                segments,
                vessel.vessel_id,
                "ready_to_depart",
                vessel.operation_end_minutes,
                vessel.departure_time_minutes or horizon,
            )

    return tuple(segments)


def _append_segment(
    segments: list[VesselTimelineSegment],
    vessel_id: str,
    state: str,
    start_minutes: float,
    end_minutes: float,
) -> None:
    if end_minutes <= start_minutes:
        return

    segments.append(
        VesselTimelineSegment(
            vessel_id=vessel_id,
            state=state,
            start_minutes=start_minutes,
            end_minutes=end_minutes,
        )
    )


def save_berth_timeline_png(
    segments: tuple[BerthTimelineSegment, ...],
    file_path: str | Path,
) -> None:
    _save_segment_png(
        [
            (segment.berth_id, segment.start_minutes, segment.end_minutes)
            for segment in segments
        ],
        "Berth Timeline",
        file_path,
    )


def save_vessel_timeline_png(
    segments: tuple[VesselTimelineSegment, ...],
    file_path: str | Path,
) -> None:
    _save_segment_png(
        [
            (
                f"{segment.vessel_id}:{segment.state}",
                segment.start_minutes,
                segment.end_minutes,
            )
            for segment in segments
        ],
        "Vessel Timeline",
        file_path,
    )


def save_crane_timeline_png(
    segments: tuple[CraneTimelineSegment, ...],
    file_path: str | Path,
) -> None:
    _save_segment_png(
        [
            (
                f"{segment.crane_id}:{segment.state}",
                segment.start_minutes,
                segment.end_minutes,
            )
            for segment in segments
        ],
        "Crane Timeline",
        file_path,
    )


def _save_segment_png(
    rows: list[tuple[str, float, float]],
    title: str,
    file_path: str | Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "PNG timeline export requires matplotlib to be installed."
        ) from error

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = sorted({label for label, _, _ in rows})
    label_index = {label: index for index, label in enumerate(labels)}

    _, axis = plt.subplots(figsize=(10, max(3, len(labels) * 0.35)))
    for label, start, end in rows:
        axis.barh(
            label_index[label],
            end - start,
            left=start,
            height=0.7,
        )

    axis.set_yticks(range(len(labels)))
    axis.set_yticklabels(labels)
    axis.set_xlabel("Simulation minutes")
    axis.set_title(title)
    axis.grid(axis="x", alpha=0.2)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def save_timeline_json(
    *,
    berth_segments: tuple[BerthTimelineSegment, ...],
    crane_segments: tuple[CraneTimelineSegment, ...],
    vessel_segments: tuple[VesselTimelineSegment, ...] = (),
    file_path: str | Path,
) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "berth_timeline": [
                    segment.to_dict() for segment in berth_segments
                ],
                "vessel_timeline": [
                    segment.to_dict() for segment in vessel_segments
                ],
                "crane_timeline": [
                    segment.to_dict() for segment in crane_segments
                ],
            },
            file,
            ensure_ascii=False,
            indent=2,
        )
