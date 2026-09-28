from __future__ import annotations

import pytest

from berth_allocation_lab.data import BAPVesselInput


@pytest.fixture
def manual_vessels() -> tuple[BAPVesselInput, ...]:
    """Small hand-verifiable fixture for Step 5 and later baseline tests."""

    return (
        BAPVesselInput("V001", 0.0, 200.0, 100.0),
        BAPVesselInput("V002", 0.0, 200.0, 100.0),
        BAPVesselInput("V003", 25.0, 120.0, 60.0),
        BAPVesselInput("V004", 100.0, 200.0, 100.0),
    )

