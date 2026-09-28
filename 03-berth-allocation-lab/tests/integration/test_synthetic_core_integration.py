from __future__ import annotations

from pathlib import Path

from berth_allocation_lab.core import (
    BAPPlacement,
    candidate_positions,
    earliest_feasible_start,
    is_placement_feasible,
    waiting_time,
)
from berth_allocation_lab.scenarios import (
    SyntheticScenarioConfig,
    SyntheticScenarioGenerator,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_generated_scenario_flows_into_continuous_core() -> None:
    config = SyntheticScenarioConfig.load_yaml(
        PROJECT_ROOT / "configs" / "scenarios" / "synthetic_low.yaml"
    )
    scenario = SyntheticScenarioGenerator().generate(config)
    vessel = scenario.vessels[0]

    positions = candidate_positions(
        vessel,
        (),
        scenario.berth_length_m,
        scenario.min_clearance_m,
    )
    start = earliest_feasible_start(
        vessel,
        positions[0],
        (),
        scenario.berth_length_m,
        scenario.min_clearance_m,
    )
    placement = BAPPlacement(
        vessel_id=vessel.vessel_id,
        berth_position_m=positions[0],
        berth_start_time_min=start,
        length_m=vessel.length_m,
        service_time_min=vessel.service_time_min,
    )

    assert is_placement_feasible(
        vessel,
        placement.berth_position_m,
        placement.berth_start_time_min,
        (),
        scenario.berth_length_m,
        scenario.min_clearance_m,
    )
    assert waiting_time(vessel, placement) == 0.0

