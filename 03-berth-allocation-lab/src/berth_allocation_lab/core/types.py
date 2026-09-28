"""Immutable mathematical schedule types."""

from __future__ import annotations

from dataclasses import dataclass

from berth_allocation_lab.core.numerics import is_finite_number


@dataclass(frozen=True)
class BAPPlacement:
    """A vessel rectangle in continuous berth-position/time space.

    Positions and lengths are meters. Times and durations are elapsed minutes.
    The service interval is half-open: ``[start, service_end)``.
    """

    vessel_id: str
    berth_position_m: float
    berth_start_time_min: float
    length_m: float
    service_time_min: float

    def __post_init__(self) -> None:
        if not isinstance(self.vessel_id, str) or not self.vessel_id.strip():
            raise ValueError("Vessel ID cannot be empty.")
        _require_finite(self.berth_position_m, "Berth position")
        _require_finite(self.berth_start_time_min, "Berth start time")
        _require_positive(self.length_m, "Vessel length")
        _require_positive(self.service_time_min, "Service time")
        _require_finite(self.berth_end_position_m, "Berth end position")
        _require_finite(self.service_end_time_min, "Service end time")

    @property
    def berth_end_position_m(self) -> float:
        """Return the vessel's right edge in meters."""

        return self.berth_position_m + self.length_m

    @property
    def service_end_time_min(self) -> float:
        """Return the exclusive end of the service interval in minutes."""

        return self.berth_start_time_min + self.service_time_min


def _require_finite(value: object, field_name: str) -> None:
    if not is_finite_number(value):
        raise ValueError(f"{field_name} must be a finite number.")


def _require_positive(value: object, field_name: str) -> None:
    _require_finite(value, field_name)
    if float(value) <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero.")

