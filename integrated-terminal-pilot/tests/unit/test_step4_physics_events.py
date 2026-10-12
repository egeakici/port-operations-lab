"""Rate laws, capacity sharing, event-priority contract and decision-time observation contracts."""

from __future__ import annotations

import random

import pytest

from integrated_terminal_pilot.policies import CraneObservation, YardObservation
from integrated_terminal_pilot.simulator.events import EVENT_PRIORITY
from integrated_terminal_pilot.simulator.ledger import location_dict, record_to_dict
from integrated_terminal_pilot.simulator.physics import (
    allocate_block, congestion_factor, crane_rate_moves_per_hour, forecast_release_min,
    share_block_capacity, transfer_distance_m, transport_rate_moves_per_hour,
)
from mini_port_sim.scenario import ServiceConfig
from tests.step4_support import block, build_doc, container, kernel_for, policies, run, vessel


def test_event_priorities_are_the_frozen_d22_table():
    assert EVENT_PRIORITY == {"WORK_ORDER_COMPLETED": 10, "VESSEL_HANDLING_COMPLETED": 20, "VESSEL_DEPARTED": 30,
                              "BERTHING_PREP_COMPLETED": 40, "LOAD_WAIT_TIMEOUT": 50, "GATE_IN_ARRIVAL": 60,
                              "PICKUP_DUE": 65, "VESSEL_ARRIVAL": 70, "HORIZON_ENTRY": 80}


def test_crane_rate_reuses_project02_efficiency():
    service = ServiceConfig(two_crane_efficiency=0.92, three_crane_efficiency=0.82, four_plus_crane_efficiency=0.72)
    rates = [crane_rate_moves_per_hour(30.0, n, service, 1.0) for n in (1, 2, 3, 4, 5)]
    assert rates == pytest.approx([30.0, 27.6, 24.6, 21.6, 21.6])
    assert 2 * rates[1] == pytest.approx(55.2)  # two-crane aggregate, efficiency applied once


def test_transport_rate_examples_of_the_data_contract():
    # Data contract §6: d = 600 m -> cycle 6.8 min -> 35.3 moves/h; d = 1500 m -> 14 min -> 17.1.
    assert transport_rate_moves_per_hour(600.0, 250.0, 2.0, 4) == pytest.approx(4 * 60 / 6.8)
    assert transport_rate_moves_per_hour(1500.0, 250.0, 2.0, 4) == pytest.approx(4 * 60 / 14.0)
    assert transfer_distance_m(100.0, 126.0, 150.0) == 176.0  # rectilinear |dx| + y


def test_congestion_factor_is_piecewise_linear():
    assert congestion_factor(0.0, 100.0, 0.7, 0.5) == 1.0
    assert congestion_factor(70.0, 100.0, 0.7, 0.5) == 1.0
    assert congestion_factor(85.0, 100.0, 0.7, 0.5) == pytest.approx(0.75)
    assert congestion_factor(100.0, 100.0, 0.7, 0.5) == pytest.approx(0.5)
    assert congestion_factor(100.0, 100.0, 0.7, 1.0) == 1.0  # g_min = 1 disables congestion


def test_closed_form_allocation_equals_the_reference_sharing_rule():
    rng = random.Random(7)
    for _ in range(500):
        effective = rng.uniform(1.0, 100.0)
        ship = [(f"S{i}", rng.uniform(1.0, 60.0)) for i in range(rng.randint(0, 4))]
        n_land = rng.randint(0, 6)
        mu = rng.uniform(1.0, 100.0)
        land = [(f"L{i}", mu) for i in range(n_land)]
        reference = share_block_capacity(effective, 0.2, ship, land)
        ship_rates, per_flow = allocate_block(effective, 0.2, ship, n_land, mu)
        for flow_id, _ in ship:
            assert ship_rates[flow_id] == pytest.approx(reference[flow_id])
            assert ship_rates[flow_id] <= dict(ship)[flow_id] + 1e-12
        for flow_id, _ in land:
            assert per_flow == pytest.approx(reference[flow_id])
        assert sum(reference.values()) <= effective + 1e-9


def test_landside_share_and_return_of_unused_capacity():
    rates = share_block_capacity(60.0, 0.2, [("s", 100.0)], [("l", 60.0)])
    assert rates == pytest.approx({"s": 48.0, "l": 12.0})
    assert share_block_capacity(60.0, 0.2, [("s", 100.0)], []) == pytest.approx({"s": 60.0})
    assert share_block_capacity(60.0, 0.2, [("s", 20.0)], [("l", 60.0)]) == pytest.approx({"s": 20.0, "l": 40.0})


def test_forecaster_formula():
    common = dict(berthing_preparation_min=30.0, departure_preparation_min=20.0, service_minutes_per_move=0.5)
    assert forecast_release_min(now_min=10.0, phase="BERTHING_PREP", berth_start_time_min=0.0,
                                handling_end_time_min=None, remaining_moves=60.0,
                                current_rate_moves_per_hour=0.0, **common) == 10.0 + 20.0 + 30.0 + 20.0
    assert forecast_release_min(now_min=40.0, phase="HANDLING", berth_start_time_min=0.0,
                                handling_end_time_min=None, remaining_moves=30.0,
                                current_rate_moves_per_hour=60.0, **common) == 40.0 + 30.0 + 20.0
    assert forecast_release_min(now_min=45.0, phase="DEPARTURE_PREP", berth_start_time_min=0.0,
                                handling_end_time_min=40.0, remaining_moves=0.0,
                                current_rate_moves_per_hour=0.0, **common) == 60.0


def test_observations_are_step3_contracts_without_hidden_fields():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 900.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=700.0),
                                container(2, "export", dest="V002", gate_in=100.0)],
                    blocks=[block("B01", 100.0)])
    kernel = kernel_for(doc)
    seen = []
    while True:
        request = kernel.advance()
        if request.__class__.__name__ != "DecisionRequest":
            break
        p = policies()
        if request.kind == "BERTH":
            view = kernel.berth_view()
            assert {v.vessel_id for v in view.vessels} <= set(kernel.state.reveal_order)
            kernel.apply_berth_action(p["berth_policy"].decide(view))
        elif request.kind == "CRANE":
            observation = kernel.crane_observation()
            assert isinstance(observation, CraneObservation)
            seen.append(observation)
            kernel.apply_crane_action(p["crane_policy"].decide(observation))
        else:
            observation = kernel.yard_observation()
            assert isinstance(observation, YardObservation)
            seen.append(observation)
            kernel.apply_yard_action(p["yard_policy"].decide(observation))
    text = repr(seen)
    for hidden in ("gate_in", "pickup", "arrival_time", "fingerprint", "scenario_id", "seed", "weight"):
        assert hidden not in text
    # At t = 0 V002 (arrival 900, announced at 660) is invisible to the berth view.
    assert kernel.state.reveal_order == ["V001", "V002"]


def test_g0_ledger_never_carries_slot_fields(golden_doc):
    from integrated_terminal_pilot.simulator import TerminalKernel

    kernel = TerminalKernel.from_scenario(golden_doc)
    run(kernel)
    for record in kernel.state.ledger:
        row = record_to_dict(record, run_id=None, scenario_id=None)
        for loc in (row["source_location"], row["destination_location"]):
            assert loc["bay"] is None and loc["row"] is None and loc["tier"] is None
            assert loc["slot_resolution"] == ("BLOCK_ONLY" if loc["kind"] == "YARD_BLOCK" else None)
    assert location_dict(("YARD_BLOCK", "B01", "BLOCK_ONLY"))["slot_resolution"] == "BLOCK_ONLY"
