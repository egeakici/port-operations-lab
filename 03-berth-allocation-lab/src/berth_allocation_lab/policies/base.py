"""Shared static scheduling types and core-backed candidate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from berth_allocation_lab.core import (
    BAPPlacement,
    candidate_positions,
    earliest_feasible_start,
)
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput


@dataclass(frozen=True)
class StaticDecisionRecord:
    """One offline scheduling choice; decision_index is not simulation time."""

    decision_index: int
    vessel_id: str
    policy_id: str
    candidate_count: int
    candidate_positions_m: tuple[float, ...]
    selected_candidate_index: int
    selected_berth_position_m: float
    selected_start_time_min: float
    selected_waiting_time_min: float
    selected_score: float | None = None


@dataclass(frozen=True)
class StaticScheduleResult:
    """Policy output, independent of evaluation and file persistence."""

    policy_id: str
    placements: tuple[BAPPlacement, ...]
    decision_records: tuple[StaticDecisionRecord, ...]


class StaticPolicy(Protocol):
    policy_id: str
    policy_family: str
    algorithm_version: str

    def schedule(self, scenario: BAPScenarioInstance) -> StaticScheduleResult: ...


def ordered_vessels(
    vessels: Sequence[BAPVesselInput],
) -> tuple[BAPVesselInput, ...]:
    """Return the frozen v1 order shared by both static policies."""

    return tuple(sorted(vessels, key=lambda v: (v.arrival_time_min, v.vessel_id)))


def candidate_starts(
    vessel: BAPVesselInput,
    placements: Sequence[BAPPlacement],
    scenario: BAPScenarioInstance,
) -> tuple[tuple[float, float], ...]:
    """Pair each canonical berth candidate with its earliest feasible minute."""

    return tuple(
        (
            position,
            earliest_feasible_start(
                vessel,
                position,
                placements,
                scenario.berth_length_m,
                scenario.min_clearance_m,
            ),
        )
        for position in candidate_positions(
            vessel,
            placements,
            scenario.berth_length_m,
            scenario.min_clearance_m,
        )
    )


def placement_at(
    vessel: BAPVesselInput,
    position: float,
    start: float,
) -> BAPPlacement:
    return BAPPlacement(
        vessel_id=vessel.vessel_id,
        berth_position_m=position,
        berth_start_time_min=start,
        length_m=vessel.length_m,
        service_time_min=vessel.service_time_min,
    )
