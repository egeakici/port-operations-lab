"""Crane, transfer and yard execution on small fixtures with independently computed timings.

Cases of the Step 4 brief: A (one import), B (crane exclusivity), D/E (yard TEU in and
out), H/I (yard full blocks admission; a gate-out frees capacity and blocked work
resumes at the same instant), J (block handling rate binds), K (berth position changes
transfer time), plus multi-crane efficiency and rate-change rescheduling.
"""

from __future__ import annotations

import math
import random

import pytest

from integrated_terminal_pilot.policies import CraneAction, CraneAssignment, GreedyBerthOrderCranePolicy
from integrated_terminal_pilot.simulator import DecisionRequest, EpisodeEnd, PhysicalActionRejected
from integrated_terminal_pilot.simulator import invariants as inv
from tests.step4_support import (
    QUIET, block, build_doc, cid, container, container_state, crane, kernel_for, ledger_rows, physics,
    policies, run, vessel, vessel_times,
)


def test_case_a_one_vessel_one_crane_one_import():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=1000.0)])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    # 30 min berthing prep, 1 move at 30 moves/h = 2 min, 20 min departure prep.
    assert vessel_times(kernel, "V001") == {"phase": "DEPARTED", "berth": 0.0, "position": 0.0,
                                            "handling_start": 30.0, "handling_end": 32.0, "departure": 52.0}
    assert [(t, e) for t, e, *_ in ledger_rows(kernel, cid(1))] == [
        (0.0, "VESSEL_ARRIVED_WITH_CARGO"), (30.0, "YARD_RESERVATION_CREATED"), (30.0, "DISCHARGE_STARTED"),
        (32.0, "YARD_RESERVATION_RELEASED"), (32.0, "DISCHARGE_COMPLETED"), (1000.0, "RELEASE_STARTED"),
        (1001.0, "RELEASE_COMPLETED")]
    result = kernel.result()
    vessel_row = result["vessels"][0]
    assert vessel_row["nominal_service_time_min"] == 50.5 and vessel_row["realized_berth_occupancy_min"] == 52.0
    assert result["kpi"]["crane_moves_completed"] == 1 and result["audits"]["ok"]


def test_case_b_two_vessels_compete_for_one_crane():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=900.0),
                                container(2, "import", origin="V001", pickup=900.0),
                                container(3, "import", origin="V002", pickup=900.0)])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    v1, v2 = vessel_times(kernel, "V001"), vessel_times(kernel, "V002")
    assert (v1["position"], v2["position"]) == (0.0, 220.0)  # FCFS: V001 first, V002 at 200 + 20
    assert (v1["handling_end"], v1["departure"]) == (34.0, 54.0)  # 2 moves 30 -> 34
    # QC01 serves V001 first (berth order), is released at 34 and then serves V002 34 -> 36.
    assert (v2["handling_end"], v2["departure"]) == (36.0, 56.0)
    assert kernel.state.vessels["V002"].acc["handling_no_crane_min"] == pytest.approx(4.0)
    assigned = [entry[3][2] for entry in kernel.state.decision_log if entry[2] == "CRANE"]
    assert assigned == [(("V001", ("QC01",)),), (("V002", ("QC01",)),)]


def test_two_crane_efficiency_and_stale_completion_on_rate_change():
    """eff(2) = 0.92 applies to every crane of the vessel (D09); the first batch is rescheduled."""
    imports = [container(n, "import", origin="V001", pickup=5000.0) for n in range(1, 21)]
    doc = build_doc(vessels=[vessel("V002", 0.0, 200.0), vessel("V001", 1.0, 200.0, max_cranes=2)],
                    containers=imports + [container(30, "import", origin="V002", pickup=5000.0)],
                    cranes=[crane("QC01"), crane("QC02")])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    # V002 holds QC01 (max_cranes 1); V001 gets QC02 at t=1, starts batch 1 (10 moves) at 31 at 30/h.
    # At 32 QC01 joins V001: eff(2) = 0.92 -> 27.6 moves/h for both cranes (aggregate 55.2).
    first = 32.0 + 60.0 * 9.5 / 27.6
    second = 32.0 + 60.0 * 10.0 / 27.6
    completions = sorted(r[1] for r in kernel.state.ledger if r[2] == "DISCHARGE_COMPLETED" and r[13] == "V001")
    assert completions[0] == pytest.approx(first, abs=1e-9) and completions[-1] == pytest.approx(second, abs=1e-9)
    assert vessel_times(kernel, "V001")["handling_end"] == pytest.approx(second, abs=1e-9)
    assert kernel.state.stale_events_discarded >= 1
    assert 2 * 30.0 * 0.92 == pytest.approx(55.2)


def test_assigned_crane_without_startable_batch_is_blocked_not_productive():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0, max_cranes=2)],
                    containers=[container(n, "import", origin="V001", pickup=5000.0) for n in (1, 2, 3)],
                    cranes=[crane("QC01"), crane("QC02")])
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    q1, q2 = kernel.state.cranes["QC01"], kernel.state.cranes["QC02"]
    # One batch of 3 moves: QC01 works it at 27.6 moves/h (two cranes assigned), QC02 has no work.
    assert q1.moves_completed == 3 and q2.moves_completed == 0
    assert q2.productive_min == 0.0
    assert q2.blocked_min_by_reason["NO_REMAINING_WORK"] == pytest.approx(60.0 * 3 / 27.6)
    assert vessel_times(kernel, "V001")["handling_end"] == pytest.approx(30.0 + 60.0 * 3 / 27.6)


def test_case_d_and_e_yard_teu_in_and_out():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", size="40_ft", origin="V001", pickup=5000.0),
                                container(2, "export", size="40_ft", dest="V001", block="B01")])
    kernel = kernel_for(doc)
    assert kernel.state.blocks["B01"].occupied_teu == 2.0
    run(kernel, until_min=30.0)
    assert (kernel.state.blocks["B01"].occupied_teu, kernel.state.blocks["B01"].reserved_teu) == (2.0, 2.0)
    run(kernel, until_min=32.0)  # discharge completes (+2 TEU) and the load starts (-2 TEU, T9)
    assert (kernel.state.blocks["B01"].occupied_teu, kernel.state.blocks["B01"].reserved_teu) == (2.0, 0.0)
    assert container_state(kernel, cid(2))[0] == "LOADING"
    assert run(kernel).status == "COMPLETED"
    assert container_state(kernel, cid(2)) == ("DEPARTED_BY_VESSEL", "VESSEL", "V001")
    assert vessel_times(kernel, "V001")["handling_end"] == 34.0


def _yard_full_doc(*, with_pickup: bool):
    # B01 holds 4 TEU; three background 20 ft imports occupy 3 TEU; V001 brings one 40 ft import (2 TEU).
    background = [container(n, "import", block="B01", pickup=(100.0 if with_pickup and n == 11 else 9000.0))
                  for n in (11, 12, 13)]
    return build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                     containers=background + [container(1, "import", size="40_ft", origin="V001", pickup=9000.0)],
                     blocks=[block("B01", 100.0, capacity=4.0)])


def test_case_h_yard_full_blocks_admission_without_overfill():
    kernel = kernel_for(_yard_full_doc(with_pickup=False))
    run(kernel, until_min=60.0)
    b01 = kernel.state.blocks["B01"]
    assert (b01.occupied_teu, b01.reserved_teu) == (3.0, 0.0)
    assert container_state(kernel, cid(1)) == ("ABOARD_ARRIVED_VESSEL", "VESSEL", "V001")
    qc = kernel.state.cranes["QC01"]
    assert (qc.status, qc.activity, qc.blocked_reason) == ("assigned", "BLOCKED", "YARD_CAPACITY")
    no_actions = [d for d in kernel.state.decision_log if d[2] == "YARD" and d[3][0] == "NO_ACTION"]
    assert len(no_actions) == 1  # re-queried only after capacity-freeing events, never polled


def test_case_i_gate_out_frees_capacity_and_blocked_work_resumes_at_the_same_instant():
    kernel = kernel_for(_yard_full_doc(with_pickup=True))
    assert run(kernel).status != "FAILED"
    rows = ledger_rows(kernel, cid(1))
    started = next(t for t, e, *_ in rows if e == "DISCHARGE_STARTED")
    assert started == 100.0  # the release of CNT-000011 starts at 100 and frees 1 TEU (T7) at that instant
    assert next(t for t, e, *_ in ledger_rows(kernel, cid(11)) if e == "RELEASE_STARTED") == 100.0
    episodes = [e for e in kernel.state.block_episodes if e[2] == "YARD_CAPACITY"]
    assert episodes == [("QC01", "V001", "YARD_CAPACITY", 30.0, 100.0)]


def test_case_j_block_handling_rate_binds_and_is_shared_with_landside():
    # Block handling 20 moves/h < crane 30 moves/h; congestion off (g_min = 1); landside share 0.2.
    p = physics(**{"transport.enabled": False, "yard.congestion_g_min": 1.0})
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=9000.0),
                                container(2, "import", origin="V001", pickup=9000.0),
                                container(9, "import", block="B01", pickup=30.0)],
                    blocks=[block("B01", 100.0, handling=20.0)], physics_doc=p)
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    # From 30: ship demand 30, landside demand 20, E = 20 -> landside guaranteed 4, ship 16 moves/h.
    # Discharge of 2 moves at 16/h ends at 37.5; the 1-move release has done 0.5 by then and finishes
    # the remaining 0.5 at 20/h -> 39.0.
    assert next(t for t, e, *_ in ledger_rows(kernel, cid(2)) if e == "DISCHARGE_COMPLETED") == pytest.approx(37.5)
    assert next(t for t, e, *_ in ledger_rows(kernel, cid(9)) if e == "RELEASE_COMPLETED") == pytest.approx(39.0)
    qc = kernel.state.cranes["QC01"]
    assert qc.yard_shortfall_moves == pytest.approx((30.0 - 16.0) * 7.5 / 60.0)
    assert qc.transport_shortfall_moves == 0.0


def test_case_k_transfer_distance_changes_timing():
    # One transport unit per crane: time per move = cycle = 2 d / 250 + 2.
    p = physics(**{"transport.units_per_crane": 1, "yard.constraints_enabled": False})
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 0.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=9000.0),
                                container(2, "import", origin="V002", pickup=9000.0)],
                    blocks=[block("B01", 100.0)], cranes=[crane("QC01"), crane("QC02")], physics_doc=p)
    kernel = kernel_for(doc)
    assert run(kernel).status == "COMPLETED"
    # B01 transfer point (126, 100). V001 at [0, 200] -> x = 100, d = 126 m; V002 at [220, 420] -> d = 294 m.
    near = 30.0 + 2 * 126 / 250 + 2
    far = 30.0 + 2 * 294 / 250 + 2
    assert next(t for t, e, *_ in ledger_rows(kernel, cid(1)) if e == "DISCHARGE_COMPLETED") == pytest.approx(near)
    assert next(t for t, e, *_ in ledger_rows(kernel, cid(2)) if e == "DISCHARGE_COMPLETED") == pytest.approx(far)
    assert far > near


def test_crane_exclusivity_under_random_actions():
    """Property test: random (often illegal) crane actions never break INV02/INV03 or partially apply."""
    rng = random.Random(20261009)
    vessels = [vessel(f"V00{i}", 10.0 * i, 200.0, max_cranes=rng.choice((1, 2))) for i in range(1, 5)]
    containers = [container(10 * i + k, "import", origin=f"V00{i}", pickup=9000.0)
                  for i in range(1, 5) for k in range(1, 4)]
    doc = build_doc(vessels=vessels, containers=containers,
                    cranes=[crane("QC01"), crane("QC02"), crane("QC03")])
    kernel = kernel_for(doc)
    p = policies()
    accepted = rejected = 0
    while True:
        request = kernel.advance()
        if isinstance(request, EpisodeEnd):
            break
        if request.kind == "CRANE":
            observation = kernel.crane_observation()
            vessel_ids = [v.vessel_id for v in observation.vessels]
            for _ in range(3):
                crane_ids = tuple(sorted(rng.sample(["QC01", "QC02", "QC03"], rng.randint(1, 3))))
                action = CraneAction(policy_id="random", time_min=observation.time_min, action_type="ASSIGN_CRANES",
                                     assignments=(CraneAssignment(rng.choice(vessel_ids), crane_ids),),
                                     decision_id=observation.decision_id)
                before = kernel.snapshot()
                try:
                    kernel.apply_crane_action(action)
                    accepted += 1
                    break
                except PhysicalActionRejected:
                    rejected += 1
                    assert kernel.snapshot() == before
            else:
                kernel.apply_crane_action(GreedyBerthOrderCranePolicy().decide(observation))
        elif request.kind == "BERTH":
            kernel.apply_berth_action(p["berth_policy"].decide(kernel.berth_view()))
        else:
            kernel.apply_yard_action(p["yard_policy"].decide(kernel.yard_observation()))
        inv.check(kernel, full=True)
    assert kernel.status == "COMPLETED" and accepted > 0 and rejected > 0
