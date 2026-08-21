from __future__ import annotations

from dataclasses import dataclass

from terminal_core import Berth, BerthOccupancy, Terminal, Vessel, VesselStatus


@dataclass(frozen=True)
class BerthDecision:
    vessel_id: str
    berth_id: str
    start_position_m: float

    def __post_init__(self) -> None:
        if not self.vessel_id.strip():
            raise ValueError("Berth decision vessel ID cannot be empty.")

        if not self.berth_id.strip():
            raise ValueError("Berth decision berth ID cannot be empty.")

        if self.start_position_m < 0:
            raise ValueError("Berth decision start position cannot be negative.")


class FCFSLeftmostPolicy:
    def choose(
        self,
        terminal: Terminal,
        waiting_vessel_ids: tuple[str, ...],
    ) -> BerthDecision | None:
        for vessel_id in waiting_vessel_ids:
            vessel = terminal.get_vessel(vessel_id)

            if vessel.status != VesselStatus.WAITING:
                continue

            for berth_id in terminal.berth_ids:
                berth = terminal.get_berth(berth_id)
                start_position = leftmost_feasible_position(
                    berth=berth,
                    vessel=vessel,
                )

                if start_position is not None:
                    return BerthDecision(
                        vessel_id=vessel_id,
                        berth_id=berth_id,
                        start_position_m=start_position,
                    )

        return None


def leftmost_feasible_position(
    *,
    berth: Berth,
    vessel: Vessel,
) -> float | None:
    clearance = berth.min_clearance_m

    if vessel.length_m > berth.length_m:
        return None

    occupancies = sorted(
        berth.occupancies,
        key=lambda occupancy: occupancy.start_position_m,
    )

    if not occupancies:
        return 0.0

    first = occupancies[0]
    if vessel.length_m + clearance <= first.start_position_m:
        return 0.0

    for left, right in zip(occupancies, occupancies[1:]):
        candidate = left.end_position_m + clearance

        if candidate + vessel.length_m + clearance <= right.start_position_m:
            return candidate

    last = occupancies[-1]
    candidate = last.end_position_m + clearance

    if candidate + vessel.length_m <= berth.length_m:
        return candidate

    return None
