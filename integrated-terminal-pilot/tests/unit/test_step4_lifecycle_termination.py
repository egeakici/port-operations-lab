"""Container lifecycles, rollover, termination outcomes and deterministic event ordering.

Cases F (export gate-in after start), G (transshipment identity), M (deadlock),
O (simultaneous departure, arrival, landside request and horizon entry), plus
rollover (D17), pickup before availability, drain truncation and the livelock guard.
"""

from __future__ import annotations

import pytest

from integrated_terminal_pilot.simulator import KernelLivelockError, KernelTimeError
from integrated_terminal_pilot.simulator.events import push_event
from tests.step4_support import (
    QUIET, block, build_doc, cid, container, container_state, crane, kernel_for, ledger_rows, physics, run, vessel,
    vessel_times,
)


def test_case_f_export_gate_in_after_start_is_never_loaded_early():
    doc = build_doc(vessels=[vessel("V001", 400.0, 200.0)],
                    containers=[container(1, "export", dest="V001", gate_in=20.0)])
    kernel = kernel_for(doc)
    run(kernel, until_min=10.0)
    assert container_state(kernel, cid(1)) == ("EXPECTED_BY_LANDSIDE", "EXTERNAL_LANDSIDE", None)
    assert run(kernel).status == "COMPLETED"
    events = [(t, e) for t, e, *_ in ledger_rows(kernel, cid(1)) if not e.startswith("YARD_RESERVATION")]
    assert events == [(20.0, "GATE_ARRIVED"), (20.0, "RECEIVE_STARTED"), (21.0, "RECEIVE_COMPLETED"),
                      (430.0, "LOAD_STARTED"), (432.0, "LOAD_COMPLETED"), (452.0, "DEPARTED_WITH_VESSEL")]


def test_case_g_transshipment_keeps_one_identity_through_two_vessel_operations():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 100.0, 200.0)],
                    containers=[container(1, "transshipment", origin="V001", dest="V002")])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    physical = [(r[1], r[2], r[6], r[7], r[16]) for r in kernel.state.ledger if r[3] == "PHYSICAL"]
    assert physical == [
        (0.0, "VESSEL_ARRIVED_WITH_CARGO", "EXPECTED_BY_VESSEL", "ABOARD_ARRIVED_VESSEL", 1),
        (30.0, "DISCHARGE_STARTED", "ABOARD_ARRIVED_VESSEL", "DISCHARGING", 2),
        (32.0, "DISCHARGE_COMPLETED", "DISCHARGING", "IN_YARD", 3),
        (130.0, "LOAD_STARTED", "IN_YARD", "LOADING", 4),
        (132.0, "LOAD_COMPLETED", "LOADING", "LOADED", 5),
        (152.0, "DEPARTED_WITH_VESSEL", "LOADED", "DEPARTED_BY_VESSEL", 6)]
    assert {r[4] for r in kernel.state.ledger} == {cid(1)} and len(kernel.catalog.containers) == 1
    assert kernel.result()["kpi"]["crane_moves_completed"] == 2  # one container, two vessel moves


def test_transshipment_cannot_load_before_discharge_and_rolls_over_after_wait():
    # V002 (arrives 0) waits for a transshipment container still aboard V001 (arrives 1000).
    doc = build_doc(vessels=[vessel("V002", 0.0, 200.0), vessel("V001", 1000.0, 200.0)],
                    containers=[container(1, "transshipment", origin="V001", dest="V002")])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    v2 = vessel_times(kernel, "V002")
    # Handling starts at 30 with no other work; after max_load_wait_min = 240 the load is rolled over.
    assert (v2["handling_start"], v2["handling_end"], v2["departure"]) == (30.0, 270.0, 290.0)
    assert kernel.state.vessels["V002"].rolled_over_container_ids == (cid(1),)
    assert kernel.state.cranes["QC01"].blocked_min_by_reason["CARGO_UNAVAILABLE"] == pytest.approx(240.0)
    # The container is still discharged by V001 and stays as residual inventory (never loaded).
    assert container_state(kernel, cid(1)) == ("IN_YARD", "YARD_BLOCK", "B01")
    result = kernel.result()
    assert result["kpi"]["rolled_over_containers"] == 1 and result["audits"]["ok"]
    assert [r[2] for r in kernel.state.ledger if r[3] == "EXCEPTION"] == ["ROLLED_OVER"]


def test_crane_hold_and_wait_is_resolved_by_rollover_not_by_fake_completion():
    # One crane: V002 holds QC01 while waiting for cargo still aboard V001, so V001 cannot discharge it.
    doc = build_doc(vessels=[vessel("V002", 0.0, 200.0), vessel("V001", 100.0, 200.0)],
                    containers=[container(1, "transshipment", origin="V001", dest="V002"),
                                container(2, "import", origin="V002", pickup=5000.0)])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    # V002's other work ends at 32; the cargo is still missing 240 min later -> rolled over at 272.
    assert kernel.state.vessels["V002"].rolled_over_container_ids == (cid(1),)
    assert vessel_times(kernel, "V002")["handling_end"] == 272.0
    assert vessel_times(kernel, "V001")["handling_start"] == 130.0  # waits for QC01 until 272
    assert next(t for t, e, *_ in ledger_rows(kernel, cid(1)) if e == "DISCHARGE_STARTED") == 272.0


def test_rollover_timer_is_cancelled_when_cargo_arrives_in_time():
    doc = build_doc(vessels=[vessel("V002", 0.0, 200.0), vessel("V001", 100.0, 200.0)],
                    containers=[container(1, "transshipment", origin="V001", dest="V002"),
                                container(2, "import", origin="V002", pickup=5000.0)],
                    cranes=[crane("QC01"), crane("QC02")])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    assert kernel.state.vessels["V002"].rolled_over_container_ids == ()
    # V001 discharges it 130 -> 132; V002's timer (started at 32) is cancelled and it loads 132 -> 134.
    assert vessel_times(kernel, "V002")["handling_end"] == 134.0
    assert container_state(kernel, cid(1)) == ("DEPARTED_BY_VESSEL", "VESSEL", "V002")


def test_pickup_before_physical_availability_waits_without_negative_inventory():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=5.0)])
    kernel = kernel_for(doc)
    run(kernel, until_min=20.0)
    assert kernel.state.c_pickup_due[0] and container_state(kernel, cid(1))[0] == "ABOARD_ARRIVED_VESSEL"
    assert run(kernel).status == "COMPLETED"
    rows = [(t, e) for t, e, *_ in ledger_rows(kernel, cid(1))]
    assert (32.0, "DISCHARGE_COMPLETED") in rows and (32.0, "RELEASE_STARTED") in rows
    assert kernel.result()["kpi"]["mean_pickup_delay_min"] == pytest.approx(33.0 - 5.0)


def test_case_m_true_deadlock_is_reported_with_evidence():
    # Quay 600: V001 (400 m) and V002 (400 m) cannot share it. B01 (4 TEU) is full of exports for V002.
    # V001's 40 ft import cannot be discharged; V002 cannot berth until V001 leaves.
    exports = [container(n, "export", dest="V002", block="B01") for n in (11, 12, 13, 14)]
    doc = build_doc(quay=600.0, vessels=[vessel("V001", 0.0, 400.0), vessel("V002", 10.0, 400.0)],
                    containers=exports + [container(1, "import", size="40_ft", origin="V001", pickup=9000.0)],
                    blocks=[block("B01", 100.0, capacity=4.0)])
    kernel = kernel_for(doc)
    outcome = run(kernel)
    assert outcome.status == "DEADLOCK"
    details = kernel.state.status_details
    assert set(details["unresolved_vessels"]) == {"V001", "V002"}
    assert details["blocked_cranes"] == {"QC01": ["V001", "YARD_CAPACITY"]}
    assert details["next_event"] is None
    # The last exogenous event (the import's pickup request at 9000) changes nothing physically;
    # after it the queue is empty, work is unresolved and nothing can start: DEADLOCK at t = 9000.
    assert kernel.current_time_min == 9000.0
    result = kernel.result()
    assert result["status"] == "DEADLOCK" and result["audits"]["invariants"]["ok"]
    assert result["kpi"]["total_turnaround_min"] == pytest.approx(2 * kernel.catalog.drain_limit_min - 10.0)


def test_drain_limit_truncation_censors_unfinished_vessels():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(n, "import", origin="V001", pickup=9000.0) for n in range(1, 11)],
                    physics_doc=physics(**QUIET, **{"episode.max_drain_extension_min": 40.0}))
    kernel = kernel_for(doc)
    outcome = run(kernel)
    assert outcome.status == "TRUNCATED_DRAIN_LIMIT"
    assert kernel.current_time_min == 40.0
    result = kernel.result()
    assert result["kpi"]["total_turnaround_min"] == 40.0  # censored at T_end = last arrival + 40
    assert result["kpi"]["unfinished_workload_moves"] == 10
    assert result["status_details"]["unresolved_vessels"]["V001"]["phase"] == "HANDLING"


def test_livelock_guard_stops_a_malformed_configuration():
    # Zero berthing preparation and a zero rollover wait (not v1 values; validate=False) create
    # repeated cycles at t = 0: arrival -> berthing prep end -> rollover timeout.
    p = physics(**QUIET, **{"kernel.same_timestamp_cycle_limit": 1, "work.max_load_wait_min": 0.0})
    p["service"]["berthing_preparation_minutes"] = 0.0
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 500.0, 200.0)],
                    containers=[container(1, "transshipment", origin="V002", dest="V001")], physics_doc=p)
    kernel = kernel_for(doc, validate=False)
    outcome = run(kernel)
    assert outcome.status == "FAILED" and kernel.status == "FAILED"
    assert kernel.state.status_reason == KernelLivelockError.code


def test_forecast_guard_rejects_zero_duration_occupancy():
    # Zero departure preparation lets a forecast equal "now" (G17): a kernel error, never clamped.
    p = physics(**QUIET)
    p["service"]["berthing_preparation_minutes"] = 0.0
    p["service"]["departure_preparation_minutes"] = 0.0
    doc = build_doc(quay=600.0, vessels=[vessel("V001", 0.0, 500.0), vessel("V002", 0.0, 500.0)],
                    containers=[container(9, "import", block="B01", pickup=9000.0)], physics_doc=p)
    kernel = kernel_for(doc, validate=False)
    assert run(kernel).status == "FAILED"
    assert kernel.state.status_reason == "FORECAST_NOT_AFTER_NOW"


def test_scheduling_in_the_past_raises():
    queue = []
    with pytest.raises(KernelTimeError):
        push_event(queue, 10.0, 1, 9.0, "PICKUP_DUE", "CNT-000001")
    with pytest.raises(KernelTimeError):
        push_event(queue, 10.0, 1, float("nan"), "PICKUP_DUE", "CNT-000001")
    assert queue == []


def test_case_o_simultaneous_departure_arrival_request_and_horizon_entry():
    # V001 departs at 52.0 exactly when V002 arrives; a pickup and V003's horizon entry are also at 52.
    doc = build_doc(vessels=[vessel("V001", 0.0, 700.0), vessel("V002", 52.0, 700.0),
                             vessel("V003", 292.0, 300.0)],
                    containers=[container(1, "import", origin="V001", pickup=900.0),
                                container(2, "import", origin="V002", pickup=900.0),
                                container(3, "import", origin="V003", pickup=900.0),
                                container(9, "import", block="B01", pickup=52.0)])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    at_52 = [(e[3], e[4]) for e in kernel.state.event_log if e[1] == 52.0]
    assert at_52 == [("VESSEL_DEPARTED", "V001"), ("PICKUP_DUE", cid(9)), ("VESSEL_ARRIVAL", "V002"),
                     ("HORIZON_ENTRY", "V003")]
    assert vessel_times(kernel, "V002")["berth"] == 52.0  # the released quay is reused at once
    assert kernel.state.reveal_order == ["V001", "V002", "V003"]
