"""PhysicalActionValidator, cloning (truth vs observable), snapshots, determinism, information isolation."""

from __future__ import annotations

import copy
import json

import pytest

from integrated_terminal_pilot.policies import (
    CraneAction, CraneAssignment, FirstFitYardPolicy, GreedyBerthOrderCranePolicy, YardAction,
)
from integrated_terminal_pilot.simulator import (
    BerthAction, DecisionProtocolError, PhysicalActionRejected, TerminalKernel, UnsupportedScenario,
)
from integrated_terminal_pilot.simulator.invariants import shared_mutable_objects
from integrated_terminal_pilot.simulator.ledger import ledger_jsonl_lines, ledger_sha256
from tests.step4_support import (
    block, build_doc, cid, container, crane, kernel_for, policies, run, vessel,
)


def _advance_to(kernel, kind):
    p = policies()
    while True:
        request = kernel.advance()
        if getattr(request, "kind", None) == kind:
            return request
        if request.kind == "BERTH":
            kernel.apply_berth_action(p["berth_policy"].decide(kernel.berth_view()))
        elif request.kind == "CRANE":
            kernel.apply_crane_action(p["crane_policy"].decide(kernel.crane_observation()))
        else:
            kernel.apply_yard_action(p["yard_policy"].decide(kernel.yard_observation()))


def _quay_doc():
    return build_doc(quay=600.0, vessels=[vessel("V001", 0.0, 300.0), vessel("V002", 0.0, 250.0, max_cranes=1)],
                     containers=[container(1, "import", origin="V001", pickup=900.0),
                                 container(2, "import", size="40_ft", origin="V002", pickup=900.0)],
                     blocks=[block("B01", 100.0, capacity=6.0, sizes=("20_ft",)), block("B02", 300.0)],
                     cranes=[crane("QC01"), crane("QC02")])


def _rejects(kernel, apply, action, code):
    before = json.dumps(kernel.snapshot(), sort_keys=True)
    with pytest.raises(PhysicalActionRejected) as error:
        apply(action)
    assert error.value.rejection_code == code
    assert json.dumps(kernel.snapshot(), sort_keys=True) == before  # byte-identical state


def test_berth_rejections_leave_state_byte_identical():
    kernel = kernel_for(_quay_doc())
    request = _advance_to(kernel, "BERTH")
    d = request.decision_id
    _rejects(kernel, kernel.apply_berth_action, BerthAction.assign("t", "V009", 0.0, d), "UNKNOWN_VESSEL")
    _rejects(kernel, kernel.apply_berth_action, BerthAction.assign("t", "V001", 400.0, d), "POSITION_OUTSIDE_QUAY")
    _rejects(kernel, kernel.apply_berth_action, BerthAction.assign("t", "V001", float("nan"), d),
             "NON_FINITE_POSITION")
    _rejects(kernel, kernel.apply_berth_action, BerthAction.wait("t", d), "WAIT_NOT_LEGAL")  # no visible future
    _rejects(kernel, kernel.apply_berth_action, BerthAction.assign("t", "V001", 0.0, "DEC-99999999"), "STALE_ACTION")
    kernel.apply_berth_action(BerthAction.assign("t", "V001", 0.0, d))
    d2 = kernel.advance().decision_id
    # V002 at 310 overlaps clearance (300 + 20 > 310); at 320 it fits; V001 is no longer WAITING.
    _rejects(kernel, kernel.apply_berth_action, BerthAction.assign("t", "V002", 310.0, d2), "BERTH_OCCUPIED")
    _rejects(kernel, kernel.apply_berth_action, BerthAction.assign("t", "V001", 320.0, d2), "VESSEL_NOT_WAITING")
    kernel.apply_berth_action(BerthAction.assign("t", "V002", 320.0, d2))  # any continuous legal position


def test_crane_rejections_leave_state_byte_identical():
    kernel = kernel_for(_quay_doc())
    request = _advance_to(kernel, "CRANE")
    obs = kernel.crane_observation()

    def action(*assignments, releases=()):
        return CraneAction(policy_id="t", time_min=obs.time_min, action_type="ASSIGN_CRANES",
                           assignments=tuple(assignments), releases=releases, decision_id=request.decision_id)

    _rejects(kernel, kernel.apply_crane_action, action(CraneAssignment("V002", ("QC01", "QC02"))),
             "MAX_CRANES_EXCEEDED")
    _rejects(kernel, kernel.apply_crane_action, action(CraneAssignment("V001", ("QC09",))), "UNKNOWN_CRANE")
    _rejects(kernel, kernel.apply_crane_action, action(CraneAssignment("V009", ("QC01",))), "UNKNOWN_VESSEL")
    _rejects(kernel, kernel.apply_crane_action,
             action(CraneAssignment("V001", ("QC02",)), releases=("QC01",)), "RELEASE_NOT_ASSIGNED")
    kernel.apply_crane_action(GreedyBerthOrderCranePolicy().decide(obs))
    assert kernel.state.cranes["QC01"].assigned_vessel_id == "V001"
    assert kernel.state.cranes["QC02"].assigned_vessel_id == "V002"


def test_yard_rejections_leave_state_byte_identical():
    kernel = kernel_for(_quay_doc())
    request = _advance_to(kernel, "YARD")
    obs = kernel.yard_observation()
    req = obs.request

    def action(block_id, **overrides):
        values = dict(policy_id="t", time_min=obs.time_min, work_order_id=req.work_order_id,
                      action_type="ALLOCATE_BLOCK", container_ids=req.container_ids,
                      required_teu=req.required_teu, block_id=block_id, decision_id=request.decision_id)
        values.update(overrides)
        return YardAction(**values)

    assert req.container_ids == (cid(1),)
    _rejects(kernel, kernel.apply_yard_action, action("B09"), "UNKNOWN_BLOCK")
    _rejects(kernel, kernel.apply_yard_action, action("B01", container_ids=(cid(2),)), "CONTAINER_SET_MISMATCH")
    _rejects(kernel, kernel.apply_yard_action, action("B01", required_teu=2.0), "REQUIRED_TEU_MISMATCH")
    _rejects(kernel, kernel.apply_yard_action, action("B01", work_order_id="WO-000099"), "STALE_ACTION")
    kernel.apply_yard_action(FirstFitYardPolicy().decide(obs))  # B01 (20 ft allowed)
    request = _advance_to(kernel, "YARD")
    obs = kernel.yard_observation()
    assert obs.request.container_ids == (cid(2),)  # 40 ft import of V002
    _rejects(kernel, kernel.apply_yard_action,
             YardAction(policy_id="t", time_min=obs.time_min, work_order_id=obs.request.work_order_id,
                        action_type="ALLOCATE_BLOCK", container_ids=obs.request.container_ids,
                        required_teu=2.0, block_id="B01", decision_id=request.decision_id), "SIZE_NOT_ALLOWED")


def test_capacity_rejection_and_decision_protocol():
    doc = build_doc(vessels=[vessel("V001", 0.0, 200.0)],
                    containers=[container(1, "import", size="40_ft", origin="V001", pickup=900.0),
                                container(9, "import", block="B01", pickup=900.0)],
                    blocks=[block("B01", 100.0, capacity=2.0), block("B02", 300.0)])
    kernel = kernel_for(doc)
    request = _advance_to(kernel, "YARD")
    obs = kernel.yard_observation()
    with pytest.raises(DecisionProtocolError):
        kernel.crane_observation()
    _rejects(kernel, kernel.apply_yard_action,
             YardAction(policy_id="t", time_min=obs.time_min, work_order_id=obs.request.work_order_id,
                        action_type="ALLOCATE_BLOCK", container_ids=obs.request.container_ids, required_teu=2.0,
                        block_id="B01", decision_id=request.decision_id), "MISSING_DESTINATION_CAPACITY")
    with pytest.raises(PhysicalActionRejected) as error:
        kernel.apply_berth_action(BerthAction.wait("t", request.decision_id))
    assert error.value.rejection_code == "STALE_ACTION"


def test_g1_scenarios_are_unsupported_by_the_g0_kernel(golden_doc):
    doc = copy.deepcopy(golden_doc)
    doc["identity"]["yard_fidelity"] = "G1"
    with pytest.raises(UnsupportedScenario):
        TerminalKernel.from_scenario(doc, validate=False)


def _blocked_doc():
    background = [container(n, "import", block="B01", pickup=(100.0 if n == 11 else 9000.0)) for n in (11, 12, 13)]
    return build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 500.0, 200.0)],
                     containers=background + [container(1, "import", size="40_ft", origin="V001", pickup=9000.0),
                                              container(2, "export", dest="V002", gate_in=60.0),
                                              container(3, "import", origin="V002", pickup=9000.0)],
                     blocks=[block("B01", 100.0, capacity=4.0), block("B02", 300.0, capacity=1.0)])


def test_case_n_clone_during_blocked_work_continues_identically_and_is_isolated():
    original = kernel_for(_blocked_doc())
    run(original, until_min=50.0)
    assert original.state.cranes["QC01"].blocked_reason == "YARD_CAPACITY"
    clone = original.clone()
    assert clone.catalog is original.catalog  # immutable catalog shared
    assert shared_mutable_objects(original.state, clone.state) == []
    # Mutating the clone never changes the original.
    before = json.dumps(original.snapshot(), sort_keys=True)
    clone.state.blocks["B01"].occupied_teu += 1.0
    clone.state.c_status[0] = "MUTATED"
    clone.state.kpi["x"] = 1.0
    assert json.dumps(original.snapshot(), sort_keys=True) == before
    # Fresh clones continue identically to the original.
    a, b = original.clone(), original.clone()
    run(a), run(b), run(original)
    for k in (a, b):
        assert k.status == original.status == "COMPLETED"
        assert ledger_sha256(k.state.ledger) == ledger_sha256(original.state.ledger)
        assert k.result(audits=False)["kpi"] == original.result(audits=False)["kpi"]
        assert k.state.event_log == original.state.event_log


def test_snapshot_round_trip_continues_identically():
    original = kernel_for(_blocked_doc())
    run(original, until_min=110.0)
    restored = TerminalKernel.from_snapshot(original.catalog, json.loads(json.dumps(original.snapshot())))
    run(original), run(restored)
    assert ledger_sha256(restored.state.ledger) == ledger_sha256(original.state.ledger)
    assert restored.snapshot() == original.snapshot()


def test_two_runs_have_byte_identical_ledgers(golden_doc):
    first, second = TerminalKernel.from_scenario(golden_doc), TerminalKernel.from_scenario(golden_doc)
    run(first), run(second)
    assert list(ledger_jsonl_lines(first.state.ledger, run_id="r", scenario_id="s")) == \
        list(ledger_jsonl_lines(second.state.ledger, run_id="r", scenario_id="s"))
    assert ledger_sha256(first.state.ledger) == ledger_sha256(second.state.ledger)


def _hidden_doc(*, v003_arrival=1000.0, pickup=700.0, gate_in=300.0):
    return build_doc(vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 100.0, 200.0),
                              vessel("V003", v003_arrival, 200.0)],
                     containers=[container(1, "import", origin="V001", pickup=pickup),
                                 container(2, "import", origin="V003", pickup=v003_arrival + 900.0),
                                 container(3, "export", dest="V003", gate_in=gate_in),
                                 container(4, "export", dest="V002", block="B01"),
                                 container(5, "import", block="B02", pickup=pickup + 1.0)],
                     blocks=[block("B01", 100.0), block("B02", 300.0)], cranes=[crane("QC01"), crane("QC02")])


def test_observable_clone_removes_hidden_vessels_and_landside_events():
    kernel = kernel_for(_hidden_doc())
    run(kernel, until_min=40.0)
    obs = kernel.observable_clone()
    assert set(obs.catalog.vessel_by_id) == {"V001", "V002"}  # V003 not yet announced (1000 - 240 > 40)
    assert obs.catalog.scenario_id is None and obs.catalog.fingerprints is None
    assert obs.state.ledger is None and obs.state.event_log is None
    kinds = {e[4] for e in obs.state.events}
    assert "GATE_IN_ARRIVAL" not in kinds and "PICKUP_DUE" not in kinds
    assert all(e[2] != "V003" for e in obs.state.events)
    ids = {c.container_id for c in obs.catalog.containers}
    assert cid(2) not in ids and cid(3) not in ids  # cargo of the hidden vessel
    assert all(c.gate_in_time_min is None and c.pickup_time_min is None for c in obs.catalog.containers)
    # Same kernel code runs on the clone; the truth kernel is untouched.
    run(obs)
    assert obs.status == "COMPLETED"
    assert kernel.status == "RUNNING"


def test_hidden_future_perturbation_leaves_observable_clone_and_decisions_unchanged():
    def capture(doc):
        kernel = kernel_for(doc)
        observations = []
        p = policies()
        while True:
            request = kernel.advance(until_min=100.0)
            if request.__class__.__name__ != "DecisionRequest":
                break
            if request.kind == "BERTH":
                view = kernel.berth_view()
                observations.append(view)
                kernel.apply_berth_action(p["berth_policy"].decide(view))
            elif request.kind == "CRANE":
                view = kernel.crane_observation()
                observations.append(view)
                kernel.apply_crane_action(p["crane_policy"].decide(view))
            else:
                view = kernel.yard_observation()
                observations.append(view)
                kernel.apply_yard_action(p["yard_policy"].decide(view))
        snapshot = kernel.observable_clone().snapshot()
        return observations, snapshot

    base_obs, base_snap = capture(_hidden_doc())
    for changed in (_hidden_doc(v003_arrival=1500.0), _hidden_doc(pickup=650.0), _hidden_doc(gate_in=320.0)):
        obs, snap = capture(changed)
        assert obs == base_obs  # identical observations -> identical policy decisions
        assert snap == base_snap


def test_forecaster_never_reads_the_event_queue():
    kernel = kernel_for(_hidden_doc())
    run(kernel, until_min=40.0)

    class Exploding(list):
        def __getattribute__(self, name):
            raise AssertionError("forecaster read the event queue")

    queue = kernel.state.events
    kernel.state.events = Exploding()
    try:
        release = kernel.forecast_release("V001")
    finally:
        kernel.state.events = queue
    assert release > kernel.current_time_min
