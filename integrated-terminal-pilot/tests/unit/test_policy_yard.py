"""P_y (yard_first_fit_v1) and the diagnostic balancing heuristic on hand-worked fixtures.

TEST FIXTURES: decision-time snapshots, not executed episodes.
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from integrated_terminal_pilot.policies import (
    ActionContractError, FirstFitYardPolicy, ObservationError, OccupancyBalancingYardPolicy, YardAction,
    YardBlockView, YardContainerView, YardObservation, YardRequest, eligible_blocks,
)

P_Y = FirstFitYardPolicy()
BALANCE = OccupancyBalancingYardPolicy()


def box(n, size="20_ft", flow="import", *, group="GRP-0001", origin="V001", destination=None, status=None,
        load_state="laden", reefer=False, hazardous=False):
    if flow == "export":
        origin = None
        destination = destination or "V002"
    if flow == "transshipment":
        destination = destination or "V002"
    status = status or ("AT_GATE" if flow == "export" else "ABOARD_ARRIVED_VESSEL")
    return YardContainerView(f"CNT-{n:06d}", group, size, 2.0 if size == "40_ft" else 1.0, flow, load_state,
                             reefer, hazardous, origin, destination, status)


def request(*containers, op=None, source=None, wo="WO-000001"):
    op = op or ("GATE_IN" if containers[0].cargo_flow == "export" else "DISCHARGE")
    source = source or ("G01" if op == "GATE_IN" else containers[0].origin_vessel_id)
    return YardRequest(wo, op, source, tuple(containers))


def block(bid, capacity=100.0, occupied=0.0, reserved=0.0, *, status="open", sizes=("20_ft", "40_ft"),
          caps=("general",), blocked=0.0, handling=60.0):
    return YardBlockView(bid, status, caps, sizes, capacity, occupied, reserved, blocked, handling)


def observe(req, blocks, t=50.0):
    return YardObservation(time_min=t, request=req, blocks=tuple(blocks), decision_id="Y-1")


def choose(req, blocks, policy=P_Y):
    return policy.decide(observe(req, blocks))


# 1-8 basic selection and TEU -------------------------------------------------------------

def test_one_container_one_block():
    action = choose(request(box(1)), [block("B01")])
    assert (action.action_type, action.block_id, action.container_ids) == ("ALLOCATE_BLOCK", "B01", ("CNT-000001",))
    assert action.work_order_id == "WO-000001" and action.decision_id == "Y-1"
    assert action.policy_id == "yard_first_fit_v1"


def test_first_fit_takes_the_first_eligible_block_in_block_id_order():
    blocks = [block("B03"), block("B02"), block("B10")]
    assert choose(request(box(1)), blocks).block_id == "B02"


@pytest.mark.parametrize("size, teu", [("20_ft", 1.0), ("40_ft", 2.0)])
def test_teu_requirement_follows_container_size(size, teu):
    req = request(box(1, size), box(2, size), box(3, size))
    action = choose(req, [block("B01")])
    assert action.required_teu == req.required_teu == 3 * teu and action.container_count == 3


def test_block_too_full_for_forty_but_fine_for_twenty():
    nearly_full = block("B01", capacity=100.0, occupied=99.0)  # 1 TEU free
    assert choose(request(box(1, "40_ft")), [nearly_full, block("B02")]).block_id == "B02"
    assert choose(request(box(1, "20_ft")), [nearly_full, block("B02")]).block_id == "B01"


# 9-15 reservations, status, size, capability, boundaries --------------------------------

def test_reserved_and_blocked_teu_reduce_availability():
    blocks = [block("B01", 100.0, occupied=90.0, reserved=8.0), block("B02")]
    assert choose(request(box(1, "40_ft")), blocks).block_id == "B01"            # exactly 2 TEU left
    assert choose(request(box(1, "40_ft"), box(2, "40_ft")), blocks).block_id == "B02"
    with_blocked = [block("B01", 100.0, occupied=90.0, reserved=8.0, blocked=1.0), block("B02")]
    assert choose(request(box(1, "40_ft")), with_blocked).block_id == "B02"


@pytest.mark.parametrize("status", ["closed", "maintenance"])
def test_closed_or_maintenance_blocks_are_skipped(status):
    assert choose(request(box(1)), [block("B01", status=status), block("B02")]).block_id == "B02"


def test_size_and_capability_filters():
    blocks = [block("B01", sizes=("20_ft",)), block("B02", caps=("empty",)), block("B03")]
    # B01 rejects 40 ft; B02 lacks 'general' capability for laden cargo.
    assert choose(request(box(1, "40_ft")), blocks).block_id == "B03"
    reefer = request(box(1, reefer=True))
    capable = [block("B01"), block("B02", caps=("general", "reefer_power"))]
    assert choose(reefer, capable).block_id == "B02"
    empty = request(box(1, load_state="empty"))
    assert choose(empty, [block("B01"), block("B02", caps=("empty",))]).block_id == "B02"


@pytest.mark.parametrize("blocks, req, reason", [
    ([block("B01", status="closed"), block("B02", status="maintenance")], request(box(1)), "NO_OPEN_BLOCK"),
    ([block("B01", sizes=("20_ft",))], request(box(1, "40_ft")), "NO_SIZE_COMPATIBLE_BLOCK"),
    ([block("B01")], request(box(1, hazardous=True)), "NO_CAPABLE_BLOCK"),
    ([block("B01", 10.0, occupied=9.5)], request(box(1)), "INSUFFICIENT_CAPACITY"),
    ([block("B01", 10.0, occupied=9.0), block("B02", 10.0, reserved=9.0)],
     request(box(1, "40_ft")), "INSUFFICIENT_CAPACITY"),
])
def test_no_eligible_block_returns_a_reasoned_no_action(blocks, req, reason):
    action = choose(req, blocks)
    assert action.action_type == "NO_ACTION" and action.block_id is None and action.no_action_reason == reason
    assert action.container_ids == req.container_ids  # the request is never silently dropped


def test_exact_capacity_boundary_is_admitted():
    req = request(*(box(i, "40_ft") for i in range(1, 6)))  # 10 TEU
    assert choose(req, [block("B01", 30.0, occupied=15.0, reserved=5.0)]).block_id == "B01"
    assert choose(req, [block("B01", 30.0, occupied=15.0, reserved=5.5)]).no_action_reason == \
        "INSUFFICIENT_CAPACITY"


def test_batches_are_never_split_across_blocks():
    req = request(*(box(i, "40_ft") for i in range(1, 6)))  # 10 TEU, each block holds 6
    action = choose(req, [block("B01", 6.0), block("B02", 6.0)])
    assert action.action_type == "NO_ACTION" and action.no_action_reason == "INSUFFICIENT_CAPACITY"


# 16-22 flows, identity, batches ----------------------------------------------------------

def test_import_export_and_transshipment_requests():
    imp = choose(request(box(1, flow="import")), [block("B01")])
    exp = choose(request(box(2, flow="export")), [block("B01")])
    ts = choose(request(box(3, flow="transshipment", destination="V005")), [block("B01")])
    assert {imp.block_id, exp.block_id, ts.block_id} == {"B01"}
    assert request(box(2, flow="export")).operation_type == "GATE_IN"
    assert request(box(3, flow="transshipment", destination="V005")).containers[0].destination_vessel_id == "V005"


@pytest.mark.parametrize("build", [
    lambda: request(box(1, flow="export", status="EXPECTED_BY_LANDSIDE")),          # gate-in not happened
    lambda: request(box(1, status="EXPECTED_BY_VESSEL")),                           # vessel not arrived
    lambda: request(box(1), op="LOAD", source="V001"),                              # no yard decision for loads
    lambda: request(box(1), op="GATE_IN", source="G01"),                            # import cannot gate in
    lambda: request(box(1, origin="V001"), source="V002"),                          # wrong source vessel
    lambda: request(box(1), box(1)),                                                # duplicate container id
    lambda: request(box(1, "20_ft"), box(2, "40_ft")),                              # mixed sizes in a batch
    lambda: request(box(1), box(2, group="GRP-0002")),                              # mixed groups
    lambda: YardRequest("WO-000001", "DISCHARGE", "V001", ()),                      # empty batch
    lambda: YardRequest("WO-1", "DISCHARGE", "V001", (box(1),)),                    # bad work order id
    lambda: YardContainerView("CNT-000001", "GRP-0001", "40_ft", 1.0, "import", "laden", False, False,
                              "V001", None, "ABOARD_ARRIVED_VESSEL"),               # 40 ft declared as 1 TEU
    lambda: YardContainerView("CNT-000001", "GRP-0001", "45_ft", 2.0, "import", "laden", False, False,
                              "V001", None, "ABOARD_ARRIVED_VESSEL"),               # unsupported size
    lambda: YardContainerView("CNT-000001", "GRP-0001", "20_ft", 1.0, "export", "laden", False, False,
                              None, None, "AT_GATE"),                                # export without vessel
    lambda: YardContainerView("CNT-000001", "GRP-0001", "20_ft", 1.0, "import", "laden", False, False,
                              "PRE_EPISODE", None, "ABOARD_ARRIVED_VESSEL"),         # sentinel is not a vessel
    lambda: block("B01", 10.0, occupied=8.0, reserved=3.0),                         # overfilled snapshot (DQ07)
    lambda: block("B01", sizes=("45_ft",)),
    lambda: observe(request(box(1)), [block("B01"), block("B01")]),                 # duplicate block
    lambda: observe(request(box(1)), []),
])
def test_malformed_yard_inputs_raise_invalid_input(build):
    with pytest.raises(ObservationError) as error:
        build()
    assert error.value.code == "INVALID_INPUT"


def test_batch_keeps_exact_member_ids_and_reconciles_teu():
    members = [box(i, "40_ft") for i in (17, 3, 9)]
    req = request(*members)
    action = choose(req, [block("B01")])
    assert action.container_ids == ("CNT-000003", "CNT-000009", "CNT-000017")
    assert action.required_teu == sum(m.size_teu for m in members) == 6.0
    assert action.container_count == 3 != action.required_teu  # containers and TEU are distinct


def test_action_contract_rejects_fabricated_or_inconsistent_actions():
    with pytest.raises(ActionContractError):
        YardAction("p", 0.0, "WO-000001", "ALLOCATE_BLOCK", ("CNT-000002", "CNT-000001"), 2.0, "B01")
    with pytest.raises(ActionContractError):
        YardAction("p", 0.0, "WO-000001", "NO_ACTION", ("CNT-000001",), 1.0, "B01", "INSUFFICIENT_CAPACITY")
    assert not {"bay", "row", "tier", "slot", "slot_resolution"} & {f.name for f in dataclasses.fields(YardAction)}


# 24 diagnostic balancing ---------------------------------------------------------------------

def test_occupancy_balancing_picks_lowest_projected_fraction_among_eligible_blocks():
    blocks = [block("B01", 100.0, occupied=50.0), block("B02", 200.0, occupied=60.0),
              block("B03", 100.0, occupied=10.0, sizes=("20_ft",)), block("B04", 100.0, status="closed")]
    req = request(box(1, "40_ft"))
    assert choose(req, blocks).block_id == "B01"                       # first fit
    assert choose(req, blocks, BALANCE).block_id == "B02"              # 62/200 < 52/100; B03 size-ineligible
    tie = [block("B02", 100.0, occupied=20.0), block("B01", 200.0, occupied=40.0, reserved=2.0)]
    assert choose(req, tie, BALANCE).block_id == "B01"                 # 44/200 = 22/100: tie -> block_id
    assert choose(req, [block("B01", 2.0, occupied=1.0)], BALANCE).no_action_reason == "INSUFFICIENT_CAPACITY"
    assert BALANCE.policy_id == "yard_occupancy_balance_v1" and BALANCE.protocol_name is None


# 25-30 determinism, immutability, purity, information ----------------------------------------

def test_record_order_does_not_change_the_decision():
    blocks = [block(f"B{i:02d}", 100.0, occupied=float(100 - i)) for i in range(1, 13)]
    members = [box(i, "40_ft") for i in range(1, 5)]
    reference = (choose(request(*members), blocks), choose(request(*members), blocks, BALANCE))
    rng = random.Random(11)
    for _ in range(20):
        b, m = blocks[:], members[:]
        rng.shuffle(b)
        rng.shuffle(m)
        assert (choose(request(*m), b), choose(request(*m), b, BALANCE)) == reference


def test_yard_observation_is_immutable_and_unchanged_by_decisions():
    caps = ["general"]
    blk = YardBlockView("B01", "open", caps, ["20_ft", "40_ft"], 100.0, 0.0, 0.0)
    caps.append("hazardous")
    assert blk.capabilities == ("general",)
    obs = observe(request(box(1)), [blk])
    before = repr(obs)
    for policy in (P_Y, BALANCE):
        policy.decide(obs)
    assert repr(obs) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.blocks[0].occupied_teu = 0.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.request.containers[0].container_size = "40_ft"


def test_decision_reserves_nothing_and_creates_no_event():
    obs = observe(request(box(1, "40_ft")), [block("B01", 2.0)])
    first = P_Y.decide(obs)
    assert first.block_id == "B01" and obs.blocks[0].reserved_teu == 0.0 and obs.blocks[0].available_teu == 2.0
    assert P_Y.decide(obs) == first  # a second identical decision still fits: nothing was consumed
    assert not {"events", "completion_time_min", "reservation_id"} & {f.name for f in dataclasses.fields(YardAction)}


def test_yard_views_expose_no_hidden_landside_fields():
    hidden = {"scheduled_gate_in_time_min", "scheduled_pickup_time_min", "gross_weight_kg",
              "present_at_episode_start", "source_scenario_id", "scenario_id", "arrival_time_min"}
    for cls in (YardObservation, YardRequest, YardContainerView, YardBlockView):
        assert not {f.name for f in dataclasses.fields(cls)} & hidden, cls.__name__


def test_eligible_blocks_helper_matches_first_fit():
    obs = observe(request(box(1, "40_ft")), [block("B02"), block("B01", 1.0)])
    blocks, reason = eligible_blocks(obs)
    assert [b.block_id for b in blocks] == ["B02"] and reason is None


# package boundary ---------------------------------------------------------------------------

def test_policy_contract_tables_match_scenario_schema():
    from integrated_terminal_pilot.policies import observations
    from integrated_terminal_pilot.scenarios import models
    assert observations.TEU_BY_SIZE == models.TEU_BY_SIZE
    assert {k: p.pattern for k, p in observations.ID_PATTERNS.items()} == \
        {k: p.pattern for k, p in models.ID_PATTERNS.items()}


def test_policy_package_needs_no_simulation_or_ml_stack():
    import subprocess
    import sys
    code = ("import sys, integrated_terminal_pilot.policies\n"
            "heavy = ('simpy', 'streamlit', 'torch', 'stable_baselines3', 'gymnasium', 'terminal_core',\n"
            "         'mini_port_sim', 'berth_allocation_lab', 'integrated_terminal_pilot.scenarios')\n"
            "print('LOADED', sorted(m for m in heavy if m in sys.modules))\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "LOADED []" in out.stdout
