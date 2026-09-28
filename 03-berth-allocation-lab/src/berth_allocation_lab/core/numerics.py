"""Shared floating-point comparison policy for the continuous BAP core."""

from __future__ import annotations

import math
from numbers import Real


# Absolute tolerance for meter and minute comparisons. It absorbs arithmetic
# noise without introducing a meaningful spatial or temporal discretization.
NUMERICAL_TOLERANCE = 1e-9


def is_finite_number(value: object) -> bool:
    """Return whether value is a finite real number, excluding booleans."""

    return (
        not isinstance(value, bool)
        and isinstance(value, Real)
        and math.isfinite(float(value))
    )


def is_close(left: float, right: float) -> bool:
    """Compare two physical values using the core absolute tolerance."""

    return math.isclose(
        float(left),
        float(right),
        rel_tol=0.0,
        abs_tol=NUMERICAL_TOLERANCE,
    )

