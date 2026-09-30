from __future__ import annotations

from dataclasses import replace

import pytest

from berth_allocation_lab.core import BAPPlacement
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.evaluation.metrics import (
    calculate_static_metrics,
    percentile_type7,
    schedule_end_time,
)


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        ([0.0], 0.0),
        ([0.0, 10.0], 9.5),
        ([0.0, 10.0, 20.0, 30.0], 28.5),
    ],
)
def test_type7_p95_is_hand_calculable(sample: list[float], expected: float) -> None:
    assert percentile_type7(sample, 0.95) == pytest.approx(expected)


def test_metric_values_on_simple_complete_schedule(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    vessels = (
        BAPVesselInput("A", 0.0, 100.0, 10.0),
        BAPVesselInput("B", 5.0, 100.0, 20.0),
    )
    scenario = replace(manual_static_scenario, vessels=vessels, berth_length_m=200.0)
    placements = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 10.0),
        BAPPlacement("B", 0.0, 15.0, 100.0, 20.0),
    )
    metrics = calculate_static_metrics(scenario, placements)
    assert metrics.total_waiting_time_min == 10.0
    assert metrics.mean_waiting_time_min == 5.0
    assert metrics.p95_waiting_time_min == 9.5
    assert metrics.mean_turnaround_time_min == 20.0
    assert metrics.p95_turnaround_time_min == 29.0
    assert metrics.schedule_end_time_min == 35.0
    assert metrics.throughput_vessels == 2
    assert metrics.berth_utilization == pytest.approx(3000.0 / (200.0 * 35.0))
    assert metrics.objective_value == metrics.total_waiting_time_min


def test_empty_schedule_end_is_zero_but_not_a_complete_metric_run(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    assert schedule_end_time(()) == 0.0
    with pytest.raises(ValueError, match="valid complete"):
        calculate_static_metrics(manual_static_scenario, ())


def test_invalid_physical_schedule_rejected_before_metrics(
    manual_static_scenario: BAPScenarioInstance,
) -> None:
    placements = (
        BAPPlacement("A", 0.0, 0.0, 100.0, 100.0),
        BAPPlacement("B", 100.0, 0.0, 250.0, 1000.0),
        BAPPlacement("C", 0.0, 100.0, 200.0, 100.0),
    )
    with pytest.raises(ValueError, match="valid complete"):
        calculate_static_metrics(manual_static_scenario, placements)
