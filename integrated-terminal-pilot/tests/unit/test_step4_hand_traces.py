"""Hand-worked traces: integration specification §8.5 and container_yard_foundation §11.3.

Both Step 1 traces are illustrative. Where they conflict with a frozen rule the
frozen rule wins and the difference is asserted explicitly (documented in
docs/step4_integrated_simulator.md §10):

* §8.5 batches C-000001 (20 ft) with C-000002 (40 ft); D15 requires one container
  group per batch, so they are two batches (30-32, 32-34). All listed times hold.
* §8.5 says "occupied 3 TEU" in B01 at t = 34 although C-000101/102 (2 TEU) are in
  B01 from t = 0; the kernel reports the physical 5 TEU (3 discharged + 2 initial).
* §11.3 receives CNT-000004 into B02; frozen P_y (first fit) chooses B01. With a
  scripted yard choice of B02 the §11.3 timeline is reproduced exactly; with P_y the
  times are identical and only the block differs.
"""

from __future__ import annotations

from tests.step4_support import (
    QUIET, ScriptedYardPolicy, block, build_doc, cid, container, container_state, crane, kernel_for,
    ledger_rows, physics, run, vessel, vessel_times,
)
from integrated_terminal_pilot.scenarios.serialization import load_scenario
from integrated_terminal_pilot.simulator import TerminalKernel
from tests.conftest import GOLDEN_PATH


def _spec85():
    # Quay 600 m, clearance 20 m, one 30 moves/h crane, couplings non-binding, batch size 2.
    return build_doc(
        quay=600.0,
        vessels=[vessel("V001", 0.0, 200.0), vessel("V002", 10.0, 400.0)],
        containers=[container(1, "import", origin="V001", pickup=5000.0),
                    container(2, "import", size="40_ft", origin="V001", pickup=5000.0),
                    container(101, "export", dest="V001", block="B01"),
                    container(102, "export", dest="V001", block="B01")],
        blocks=[block("B01", 100.0)],
        physics_doc=physics(**QUIET, **{"work.batch_size_containers": 2}))


def test_spec_8_5_trace_times_statuses_and_counters():
    doc = _spec85()
    kernel = kernel_for(doc, validate=False)  # V002 has no cargo: allowed only in hand-written fixtures
    outcome = run(kernel)
    assert outcome.status == "COMPLETED"
    v1, v2 = vessel_times(kernel, "V001"), vessel_times(kernel, "V002")
    assert (v1["berth"], v1["position"], v1["handling_start"], v1["handling_end"], v1["departure"]) == \
        (0.0, 0.0, 30.0, 38.0, 58.0)
    # V002 (400 m) cannot berth beside V001 on a 600 m quay (200 + 20 + 400 = 620 > 600):
    # it waits until V001's real departure at 58, not its nominal end at 52.
    assert (v2["berth"], v2["position"]) == (58.0, 0.0)
    assert v2["berth"] - 10.0 == 48.0
    rows = ledger_rows(kernel)
    starts = [(t, e) for t, e, *_rest in rows if e in ("DISCHARGE_STARTED", "LOAD_STARTED")]
    assert starts == [(30.0, "DISCHARGE_STARTED"), (32.0, "DISCHARGE_STARTED"),
                      (34.0, "LOAD_STARTED"), (34.0, "LOAD_STARTED")]
    loads = [r for r in rows if r[1] == "LOAD_COMPLETED"]
    assert [r[0] for r in loads] == [38.0, 38.0]  # one batch {C-101, C-102} 34 -> 38
    assert container_state(kernel, cid(101)) == ("DEPARTED_BY_VESSEL", "VESSEL", "V001")
    assert container_state(kernel, cid(1)) == ("RELEASED_TO_LANDSIDE", "EXTERNAL_LANDSIDE", None)


def test_spec_8_5_counters_and_nominal_versus_physical_release():
    doc = _spec85()
    kernel = kernel_for(doc, validate=False)
    paused = run(kernel, until_min=34.0)
    assert kernel.current_time_min == 34.0
    # After WO-000002 completes at 34 and the load batch starts at 34:
    b01 = kernel.state.blocks["B01"]
    assert (b01.occupied_teu, b01.reserved_teu) == (3.0, 0.0)  # 2 initial + 3 discharged - 2 loading
    paused = run(kernel, until_min=52.0)
    assert paused.end.__class__.__name__ == "Paused"
    # At the last event before 58 V001 still physically occupies [0, 200]; the forecast release is 58,
    # later than the nominal end 0 + 52, and no legal position exists for V002.
    assert kernel.current_time_min == 38.0
    assert kernel.legal_berth_choices() == ()
    assert kernel.forecast_release("V001") == 58.0
    assert kernel.catalog.vessel_by_id["V001"].nominal_service_time_min == 52.0


def test_foundation_11_3_timeline_exact_with_scripted_b02_choice(golden_doc):
    kernel = TerminalKernel.from_scenario(golden_doc, invariant_mode="full")
    outcome = run(kernel, yard=ScriptedYardPolicy({"WO-000004": "B02"}))
    assert outcome.status == "COMPLETED"
    expected = [  # (time, event, container) of the §11.3 timeline
        (30.0, "DISCHARGE_STARTED", "CNT-000001"), (32.0, "DISCHARGE_COMPLETED", "CNT-000001"),
        (32.0, "DISCHARGE_STARTED", "CNT-000002"), (34.0, "DISCHARGE_COMPLETED", "CNT-000002"),
        (34.0, "DISCHARGE_STARTED", "CNT-000003"), (36.0, "DISCHARGE_COMPLETED", "CNT-000003"),
        (120.0, "GATE_ARRIVED", "CNT-000004"), (120.0, "RECEIVE_STARTED", "CNT-000004"),
        (121.5, "RECEIVE_COMPLETED", "CNT-000004"), (300.0, "RELEASE_STARTED", "CNT-000001"),
        (301.5, "RELEASE_COMPLETED", "CNT-000001"), (420.0, "RELEASE_STARTED", "CNT-000002"),
        (421.5, "RELEASE_COMPLETED", "CNT-000002"), (630.0, "LOAD_STARTED", "CNT-000003"),
        (632.0, "LOAD_COMPLETED", "CNT-000003"), (632.0, "LOAD_STARTED", "CNT-000004"),
        (632.0, "LOAD_STARTED", "CNT-000005"), (636.0, "LOAD_COMPLETED", "CNT-000004"),
        (636.0, "LOAD_COMPLETED", "CNT-000005"), (656.0, "DEPARTED_WITH_VESSEL", "CNT-000003"),
        (656.0, "DEPARTED_WITH_VESSEL", "CNT-000004"), (656.0, "DEPARTED_WITH_VESSEL", "CNT-000005"),
    ]
    physical = [(r[1], r[2], r[4]) for r in kernel.state.ledger
                if r[3] == "PHYSICAL" and r[2] != "VESSEL_ARRIVED_WITH_CARGO"]
    assert physical == expected
    # WO-000008 loads {CNT-000004, CNT-000005} from B02 in one batch, as in §11.3.
    wo8 = next(w for w in kernel.state.completed_work_orders if w[0] == "WO-000008")
    assert wo8[3] == ("CNT-000004", "CNT-000005") and wo8[8] == "B02"
    assert vessel_times(kernel, "V001")["departure"] == 56.0
    assert vessel_times(kernel, "V002")["departure"] == 656.0
    result = kernel.result()
    kpi = result["kpi"]
    assert (kpi["container_throughput"], kpi["crane_moves_completed"]) == (5, 6)
    assert result["audits"]["ledger_replay"]["yard_moves"] == 9
    assert result["audits"]["ok"]


def test_foundation_11_3_counters_at_each_row(golden_doc):
    """B01 / B02 occupied and reserved TEU after each §11.3 row (scripted B02 receipt)."""
    kernel = TerminalKernel.from_scenario(golden_doc, invariant_mode="full")
    policy = ScriptedYardPolicy({"WO-000004": "B02"})
    checkpoints = {30.0: (0, 1, 1, 0), 32.0: (1, 2, 1, 0), 34.0: (3, 2, 1, 0), 36.0: (5, 0, 1, 0),
                   120.0: (5, 0, 1, 1), 121.5: (5, 0, 2, 0), 300.0: (4, 0, 2, 0), 421.5: (2, 0, 2, 0),
                   630.0: (0, 0, 2, 0), 632.0: (0, 0, 0, 0)}
    for t, (b1_occ, b1_res, b2_occ, b2_res) in checkpoints.items():
        run(kernel, yard=policy, until_min=t)
        b1, b2 = kernel.state.blocks["B01"], kernel.state.blocks["B02"]
        assert (b1.occupied_teu, b1.reserved_teu, b2.occupied_teu, b2.reserved_teu) == \
            (b1_occ, b1_res, b2_occ, b2_res), t


def test_foundation_11_3_with_frozen_first_fit_differs_only_in_block(golden_doc):
    kernel = TerminalKernel.from_scenario(golden_doc, invariant_mode="full")
    assert run(kernel).status == "COMPLETED"
    received = [r for r in kernel.state.ledger if r[2] == "RECEIVE_COMPLETED"]
    assert [(r[1], r[9][1]) for r in received] == [(121.5, "B01")]  # P_y first fit
    assert vessel_times(kernel, "V002")["departure"] == 656.0


def test_golden_path_constant_is_the_fixture():
    assert load_scenario(GOLDEN_PATH)["identity"]["scenario_id"] == "itp_example_development_seed10000000"
