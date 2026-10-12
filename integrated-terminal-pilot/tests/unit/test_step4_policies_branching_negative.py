"""Step 3 policy integration (brief §42), clone/replay properties A-J (§47), negative tests (§48)."""

from __future__ import annotations

import copy
import json
import random

import pytest

from integrated_terminal_pilot.policies import (
    ActionContractError, CraneAction, CraneAssignment, FirstFitYardPolicy, GreedyBerthOrderCranePolicy, YardAction,
)
from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints
from integrated_terminal_pilot.simulator import (
    BerthAction, InvalidStatusTransition, InvariantViolation, PhysicalActionRejected, TerminalKernel,
    UnsupportedScenario, run_episode,
)
from integrated_terminal_pilot.simulator import invariants as inv
from integrated_terminal_pilot.simulator.invariants import shared_mutable_objects
from integrated_terminal_pilot.simulator.ledger import ledger_sha256, replay_audit
from integrated_terminal_pilot.simulator.trace import trace_digest
from tests.step4_support import (
    block, build_doc, cid, container, container_state, crane, kernel_for, ledger_rows, physics, policies, run,
    vessel, vessel_times,
)


def _drive_until(kernel, kind, p=None):
    p = p or policies()
    while True:
        request = kernel.advance()
        if getattr(request, "kind", None) == kind or request.__class__.__name__ != "DecisionRequest":
            return request
        if request.kind == "BERTH":
            kernel.apply_berth_action(p["berth_policy"].decide(kernel.berth_view()))
        elif request.kind == "CRANE":
            kernel.apply_crane_action(p["crane_policy"].decide(kernel.crane_observation()))
        else:
            kernel.apply_yard_action(p["yard_policy"].decide(kernel.yard_observation()))


def _snapshot(kernel) -> str:
    return json.dumps(kernel.snapshot(), sort_keys=True)


def _two_crane_doc():
    # Two vessels, two cranes; B01 holds exactly one 40 ft batch, B02 the rest.
    return build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 0.0, 200.0)],
                     containers=[container(1, "import", size="40_ft", origin="V001", pickup=900.0),
                                 container(2, "import", size="40_ft", origin="V002", pickup=900.0)],
                     blocks=[block("B01", 100.0, capacity=2.0), block("B02", 300.0)],
                     cranes=[crane("QC01"), crane("QC02")])


# ------------------------------------------------------------------ §42 Step 3 policy integration

def test_pc_through_kernel_observation_validation_and_commit():
    kernel = kernel_for(_two_crane_doc())
    request = _drive_until(kernel, "CRANE")
    observation = kernel.crane_observation()
    assert observation.decision_id == request.decision_id and observation.time_min == 0.0
    action = GreedyBerthOrderCranePolicy().decide(observation)
    assert [(a.vessel_id, a.crane_ids) for a in action.assignments] == [("V001", ("QC01",)), ("V002", ("QC02",))]
    kernel.apply_crane_action(action)
    crane_owner = {c.crane_id: c.assigned_vessel_id for c in kernel.state.cranes.values()}
    assert crane_owner == {"QC01": "V001", "QC02": "V002"}
    inv.check(kernel, full=True)
    assert run(kernel).status == "COMPLETED"
    assert {c.crane_id: c.moves_completed for c in kernel.state.cranes.values()} == {"QC01": 1, "QC02": 1}


def test_py_through_kernel_reserve_then_commit_and_reconcile():
    kernel = kernel_for(_two_crane_doc())
    _drive_until(kernel, "YARD")
    observation = kernel.yard_observation()
    assert observation.request.container_ids == (cid(1),) and observation.request.required_teu == 2.0
    action = FirstFitYardPolicy().decide(observation)
    assert action.block_id == "B01"
    kernel.apply_yard_action(action)
    b01 = kernel.state.blocks["B01"]
    assert (b01.occupied_teu, b01.reserved_teu) == (0.0, 2.0)  # reserved, not stored
    assert container_state(kernel, cid(1))[0] == "DISCHARGING"
    # The second batch now sees B01 full and first fit moves to B02.
    _drive_until(kernel, "YARD")
    second = FirstFitYardPolicy().decide(kernel.yard_observation())
    assert second.block_id == "B02"
    kernel.apply_yard_action(second)
    assert run(kernel).status == "COMPLETED"
    assert (kernel.state.blocks["B01"].occupied_teu, kernel.state.blocks["B01"].reserved_teu) == (0.0, 0.0)
    rows = ledger_rows(kernel, cid(1))
    assert [e for _, e, *_ in rows][:5] == ["VESSEL_ARRIVED_WITH_CARGO", "YARD_RESERVATION_CREATED",
                                            "DISCHARGE_STARTED", "YARD_RESERVATION_RELEASED",
                                            "DISCHARGE_COMPLETED"]
    assert replay_audit(kernel.catalog, kernel.state.ledger, kernel.state)["ok"]


def test_valid_no_action_is_recorded_and_blocks_the_crane():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", size="40_ft", origin="V001", pickup=900.0),
                                container(9, "import", block="B01", pickup=50.0)],
                    blocks=[block("B01", 100.0, capacity=2.0)])
    kernel = kernel_for(doc)
    _drive_until(kernel, "YARD")
    action = FirstFitYardPolicy().decide(kernel.yard_observation())
    assert (action.action_type, action.no_action_reason) == ("NO_ACTION", "INSUFFICIENT_CAPACITY")
    kernel.apply_yard_action(action)
    assert kernel.state.decision_log[-1][3][0] == "NO_ACTION"
    assert run(kernel).status == "COMPLETED"  # the pickup at 50 frees capacity; discharge resumes at 50
    assert next(t for t, e, *_ in ledger_rows(kernel, cid(1)) if e == "DISCHARGE_STARTED") == 50.0


def test_stale_action_and_resource_change_between_observation_and_application():
    kernel = kernel_for(_two_crane_doc())
    _drive_until(kernel, "YARD")
    first_observation = kernel.yard_observation()
    first_action = FirstFitYardPolicy().decide(first_observation)
    kernel.apply_yard_action(first_action)
    second_request = _drive_until(kernel, "YARD")
    before = _snapshot(kernel)
    with pytest.raises(PhysicalActionRejected) as error:  # the old action for the old decision
        kernel.apply_yard_action(first_action)
    assert error.value.rejection_code == "STALE_ACTION"
    # A policy acting on the stale observation (B01 looked free) for the new request: B01 is now
    # reserved, so the validator refuses it instead of overfilling.
    request = kernel.yard_observation().request
    stale_choice = YardAction(policy_id="stale", time_min=kernel.current_time_min,
                              work_order_id=request.work_order_id, action_type="ALLOCATE_BLOCK",
                              container_ids=request.container_ids, required_teu=request.required_teu,
                              block_id=first_observation.blocks[0].block_id,
                              decision_id=second_request.decision_id)
    with pytest.raises(PhysicalActionRejected) as error:
        kernel.apply_yard_action(stale_choice)
    assert error.value.rejection_code == "MISSING_DESTINATION_CAPACITY"
    assert _snapshot(kernel) == before


def test_rejections_are_recorded_deterministically_by_the_runner():
    class OverlappingBerthPolicy:
        policy_id = "bad"

        def decide(self, view):
            return BerthAction.assign(self.policy_id, view.legal_choices[-1][0], 0.0, view.decision_id)

    def attempt():
        kernel = kernel_for(_two_crane_doc())
        p = policies()
        p["berth_policy"] = OverlappingBerthPolicy()
        outcome = run_episode(kernel, **p)
        return outcome, _snapshot(kernel)

    (first, state1), (second, state2) = attempt(), attempt()
    assert first.status == second.status == "FAILED"
    assert first.rejections == second.rejections
    assert first.rejections[0]["rejection_code"] == "BERTH_OCCUPIED" and state1 == state2


# ------------------------------------------------------------------ §47 clone / replay properties

def _branch_doc():
    p = physics(**{"transport.units_per_crane": 1, "yard.constraints_enabled": False})
    return build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 5.0, 200.0)],
                     containers=[container(n, "import", origin="V001", pickup=900.0) for n in (1, 2, 3)]
                     + [container(n, "import", origin="V002", pickup=900.0) for n in (4, 5)]
                     + [container(7, "export", dest="V002", block="B02")],
                     blocks=[block("B01", 100.0, capacity=4.0), block("B02", 700.0)],
                     cranes=[crane("QC01"), crane("QC02")], physics_doc=p)


def test_a_clone_at_start_runs_identically():
    original = kernel_for(_branch_doc())
    clone = original.clone()
    run(original), run(clone)
    assert trace_digest(original) == trace_digest(clone)


def test_b_clone_during_handling_and_d_reservations_are_not_shared():
    original = kernel_for(_branch_doc())
    run(original, until_min=31.0)
    assert original.state.work_orders and any(b.reservations for b in original.state.blocks.values())
    clone = original.clone()
    assert shared_mutable_objects(original.state, clone.state) == []
    reserved = {b: blk.reserved_teu for b, blk in original.state.blocks.items()}
    run(clone)  # consumes and commits the clone's reservations
    assert {b: blk.reserved_teu for b, blk in original.state.blocks.items()} == reserved
    run(original)
    assert trace_digest(original) == trace_digest(clone)


def test_e_a_different_legal_action_changes_the_branch_but_not_the_original():
    original = kernel_for(_branch_doc())
    request = _drive_until(original, "BERTH")
    while original.state.vessels["V002"].phase != "WAITING" or not any(
            c[0] == "V002" for c in original.legal_berth_choices()):
        original.apply_berth_action(policies()["berth_policy"].decide(original.berth_view()))
        request = _drive_until(original, "BERTH")
    branch = original.clone()
    before = _snapshot(original)
    far = max(c[2] for c in branch.legal_berth_choices() if c[0] == "V002")
    branch.apply_berth_action(BerthAction.assign("alt", "V002", far, request.decision_id))
    run(branch)
    assert _snapshot(original) == before
    run(original)
    assert vessel_times(original, "V002")["position"] != vessel_times(branch, "V002")["position"]
    assert vessel_times(original, "V002")["handling_end"] != vessel_times(branch, "V002")["handling_end"]


def test_g_reordered_immutable_scenario_dictionaries_give_identical_physics():
    doc = _branch_doc()
    shuffled = copy.deepcopy(doc)
    rng = random.Random(3)
    for key in ("containers", "vessels", "container_groups"):
        rng.shuffle(shuffled[key])
    rng.shuffle(shuffled["terminal"]["yard_blocks"])
    rng.shuffle(shuffled["resources"]["quay_cranes"])
    rng.shuffle(shuffled["initial_state"]["container_locations"])
    shuffled["containers"] = [dict(reversed(list(c.items()))) for c in shuffled["containers"]]
    shuffled = with_fingerprints(shuffled, generator_config_fingerprint=None)
    a, b = kernel_for(doc), kernel_for(shuffled)
    run(a), run(b)
    assert ledger_sha256(a.state.ledger) == ledger_sha256(b.state.ledger)
    assert a.state.event_log == b.state.event_log and a.state.decision_log == b.state.decision_log
    assert a.result(audits=False)["kpi"] == b.result(audits=False)["kpi"]


def test_h_truth_clone_observations_carry_no_future_events():
    original = kernel_for(_branch_doc())
    _drive_until(original, "YARD")
    clone = original.clone()
    assert clone.yard_observation() == original.yard_observation()
    text = repr(clone.yard_observation())
    assert "GATE_IN_ARRIVAL" not in text and "PICKUP" not in text.upper().replace("PICKUP_DUE", "")
    assert not hasattr(clone.yard_observation(), "events")


def test_i_cloned_event_counters_never_duplicate_ids():
    original = kernel_for(_branch_doc())
    run(original, until_min=31.0)
    next_event, next_ledger = original.state.next_event_seq, original.state.next_ledger_seq
    clone = original.clone()
    run(clone)
    ids = [e[0] for e in clone.state.event_log]
    assert len(ids) == len(set(ids))
    sequences = [r[0] for r in clone.state.ledger]
    assert sequences == sorted(set(sequences))
    assert clone.state.next_event_seq > next_event and clone.state.next_ledger_seq > next_ledger
    assert min(r[0] for r in clone.state.ledger if r[1] > 31.0) >= next_ledger


# ------------------------------------------------------------------ §48 negative tests

def test_berth_before_arrival_and_crane_negatives():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 10.0, 200.0)],
                    containers=[container(n, "import", origin="V001", pickup=900.0) for n in range(1, 11)]
                    + [container(20, "import", origin="V002", pickup=900.0)],
                    cranes=[crane("QC01"), {**crane("QC02"), "compatible_vessel_ids": ["V002"]}, crane("QC03")])
    kernel = kernel_for(doc)
    request = _drive_until(kernel, "BERTH")
    before = _snapshot(kernel)
    with pytest.raises(PhysicalActionRejected) as error:  # V002 is announced at t = 0 but arrives at 10
        kernel.apply_berth_action(BerthAction.assign("t", "V002", 300.0, request.decision_id))
    assert error.value.rejection_code == "VESSEL_NOT_WAITING" and _snapshot(kernel) == before
    kernel.apply_berth_action(BerthAction.assign("t", "V001", 0.0, request.decision_id))
    request = _drive_until(kernel, "CRANE")
    kernel.state.cranes["QC03"].status = "failed"  # failures are disabled in v1 (D19): white-box state
    before = _snapshot(kernel)
    for assignment, code in ((CraneAssignment("V001", ("QC03",)), "CRANE_NOT_AVAILABLE"),
                             (CraneAssignment("V001", ("QC02",)), "CRANE_INCOMPATIBLE"),
                             (CraneAssignment("V001", ("QC01", "QC02")), "CRANE_INCOMPATIBLE")):
        with pytest.raises(PhysicalActionRejected) as error:
            kernel.apply_crane_action(CraneAction(policy_id="t", time_min=0.0, action_type="ASSIGN_CRANES",
                                                  assignments=(assignment,), decision_id=request.decision_id))
        assert error.value.rejection_code == code and _snapshot(kernel) == before
    with pytest.raises(ActionContractError):  # the same crane for two vessels is not even expressible
        CraneAction(policy_id="t", time_min=0.0, action_type="ASSIGN_CRANES",
                    assignments=(CraneAssignment("V001", ("QC01",)), CraneAssignment("V002", ("QC01",))))
    kernel.apply_crane_action(CraneAction(policy_id="t", time_min=0.0, action_type="ASSIGN_CRANES",
                                          assignments=(CraneAssignment("V001", ("QC01",)),),
                                          decision_id=request.decision_id))
    request = _drive_until(kernel, "CRANE")  # V002 berths at 10 while QC01 still serves V001
    assert kernel.current_time_min == 10.0
    before = _snapshot(kernel)
    with pytest.raises(PhysicalActionRejected) as error:
        kernel.apply_crane_action(CraneAction(policy_id="t", time_min=10.0, action_type="ASSIGN_CRANES",
                                              assignments=(CraneAssignment("V002", ("QC01",)),),
                                              decision_id=request.decision_id))
    assert error.value.rejection_code == "CRANE_NOT_AVAILABLE" and _snapshot(kernel) == before


def test_container_source_and_identity_negatives():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 1000.0, 200.0)],
                    containers=[container(1, "import", origin="V001", pickup=900.0),
                                container(2, "transshipment", origin="V002", dest="V001"),
                                container(3, "import", origin="V001", pickup=900.0)],
                    blocks=[block("B01", 100.0)])
    kernel = kernel_for(doc)
    _drive_until(kernel, "YARD")
    observation = kernel.yard_observation()
    with pytest.raises(ActionContractError):  # duplicate container ids are not a valid batch identity
        YardAction(policy_id="t", time_min=0.0, work_order_id=observation.request.work_order_id,
                   action_type="ALLOCATE_BLOCK", container_ids=(cid(1), cid(1)), required_teu=2.0, block_id="B01")
    # A container that is no longer at the request's source (stored elsewhere) is refused.
    i = kernel.catalog.container_index[cid(1)]
    saved = (kernel.state.c_status[i], kernel.state.c_loc_kind[i], kernel.state.c_loc_id[i])
    kernel.state.c_status[i], kernel.state.c_loc_kind[i], kernel.state.c_loc_id[i] = "IN_YARD", "YARD_BLOCK", "B01"
    with pytest.raises(PhysicalActionRejected) as error:
        kernel.apply_yard_action(FirstFitYardPolicy().decide(observation))
    assert error.value.rejection_code == "UNAVAILABLE_SOURCE_INVENTORY"
    kernel.state.c_status[i], kernel.state.c_loc_kind[i], kernel.state.c_loc_id[i] = saved
    # Loading the transshipment container still aboard its (unarrived) inbound vessel is impossible.
    j = kernel.catalog.container_index[cid(2)]
    with pytest.raises(InvalidStatusTransition):
        kernel._move(j, "LOAD_STARTED", ("TRANSFER", "WO-999999"), cause="test")
    # Completing an already-completed move: the second completion is an illegal transition.
    kernel.apply_yard_action(FirstFitYardPolicy().decide(observation))
    run(kernel, until_min=40.0)
    assert container_state(kernel, cid(1))[0] == "IN_YARD"
    with pytest.raises(InvalidStatusTransition):
        kernel._move(i, "DISCHARGE_COMPLETED", ("YARD_BLOCK", "B01"), cause="test")


def test_unreceived_export_cannot_be_loaded():
    doc = build_doc(vessels=[vessel("V001", 400.0, 200.0)],
                    containers=[container(1, "export", dest="V001", gate_in=30.0)])
    kernel = kernel_for(doc)
    i = kernel.catalog.container_index[cid(1)]
    with pytest.raises(InvalidStatusTransition):
        kernel._move(i, "LOAD_STARTED", ("TRANSFER", "WO-999999"), cause="test")
    assert container_state(kernel, cid(1))[0] == "EXPECTED_BY_LANDSIDE"


def test_ledger_and_inventory_negatives():
    kernel = kernel_for(_two_crane_doc())
    assert run(kernel).status == "COMPLETED"
    ledger = list(kernel.state.ledger)
    assert replay_audit(kernel.catalog, ledger, kernel.state)["ok"]
    duplicated = ledger + [ledger[-1]]
    report = replay_audit(kernel.catalog, duplicated, kernel.state)
    assert not report["ok"] and {i["code"] for i in report["issues"]} >= {"INVENTORY_CONSERVATION_FAILURE",
                                                                         "EVENT_ORDER_VIOLATION"}
    reservation = next(r for r in ledger if r[2] == "YARD_RESERVATION_RELEASED")
    unheld = list(reservation)
    unheld[0], unheld[14] = ledger[-1][0] + 1, "WO-999999"
    report = replay_audit(kernel.catalog, ledger + [tuple(unheld)], kernel.state)
    assert any("missing reservation" in i["message"] for i in report["issues"])
    kernel.state.blocks["B01"].occupied_teu = -1.0
    with pytest.raises(InvariantViolation):
        inv.check(kernel)


def test_unsupported_physical_configuration_is_rejected():
    doc = _two_crane_doc()
    doc["physics"]["yard"]["gate_flow_demand"] = "fixed_rate"
    with pytest.raises(UnsupportedScenario):
        TerminalKernel.from_scenario(doc, validate=False)
    doc = _two_crane_doc()
    doc["physics"]["crane"]["productivity_factor"] = 0.9
    with pytest.raises(UnsupportedScenario):
        TerminalKernel.from_scenario(doc, validate=False)
