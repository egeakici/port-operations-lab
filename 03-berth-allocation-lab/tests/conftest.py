from __future__ import annotations

import pytest

from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput


@pytest.fixture
def manual_vessels() -> tuple[BAPVesselInput, ...]:
    """Small hand-verifiable fixture for Step 5 and later baseline tests."""

    return (
        BAPVesselInput("V001", 0.0, 200.0, 100.0),
        BAPVesselInput("V002", 0.0, 200.0, 100.0),
        BAPVesselInput("V003", 25.0, 120.0, 60.0),
        BAPVesselInput("V004", 100.0, 200.0, 100.0),
    )


@pytest.fixture
def manual_static_scenario() -> BAPScenarioInstance:
    """Three-vessel case where lookahead changes B's berth choice."""

    return BAPScenarioInstance(
        scenario_id="manual_static_001",
        scenario_version=1,
        scenario_family="manual",
        formulation="static",
        data_provenance="synthetic",
        split="train",
        seed=0,
        generator_version="manual_fixture_v1",
        scenario_schema_version=1,
        berth_length_m=500.0,
        min_clearance_m=10.0,
        nominal_duration_min=100.0,
        arrival_generation_end_min=100.0,
        vessels=(
            BAPVesselInput("A", 0.0, 100.0, 100.0),
            BAPVesselInput("B", 0.0, 250.0, 1000.0),
            BAPVesselInput("C", 100.0, 200.0, 100.0),
        ),
    )

