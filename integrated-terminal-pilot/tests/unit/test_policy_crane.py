"""P_c (primitive_crane_greedy_v1) on hand-worked decision-time fixtures (TEST FIXTURES, not episodes)."""

from __future__ import annotations

import dataclasses
import random

import pytest

from integrated_terminal_pilot.policies import (
    ActionContractError, CraneAction, CraneAssignment, CraneObservation, CraneVesselView, CraneView,
    GreedyBerthOrderCranePolicy, ObservationError,
)

P_C = GreedyBerthOrderCranePolicy()


def vessel(vid, start=0.0, *, max_cranes=2, remaining=100, phase="HANDLING", assigned=(), position=0.0):
    berthed = phase in ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP")
    return CraneVesselView(vid, phase, 250.0, position if berthed else None, start if berthed else None,
                           max_cranes, remaining, tuple(assigned))


def crane(cid, status="available", vessel_id=None, compatible=None):
    return CraneView(cid, status, vessel_id, 30.0, compatible, "IDLE" if vessel_id is None else "PRODUCTIVE")


def observe(vessels, cranes, t=100.0):
    return CraneObservation(time_min=t, vessels=tuple(vessels), cranes=tuple(cranes), decision_id="D-1")


def plan(action: CraneAction):
    return {a.vessel_id: a.crane_ids for a in action.assignments}


# 1-4 basic allocation -------------------------------------------------------------------

def test_one_vessel_one_crane():
    action = P_C.decide(observe([vessel("V001")], [crane("QC01")]))
    assert action.action_type == "ASSIGN_CRANES" and plan(action) == {"V001": ("QC01",)}
    assert action.policy_id == "primitive_crane_greedy_v1" and action.decision_id == "D-1"


def test_one_vessel_takes_cranes_in_crane_id_order_up_to_max():
    action = P_C.decide(observe([vessel("V001", max_cranes=2)], [crane("QC03"), crane("QC01"), crane("QC02")]))
    assert plan(action) == {"V001": ("QC01", "QC02")}


def test_two_vessels_compete_for_one_crane_earlier_berth_start_wins():
    action = P_C.decide(observe([vessel("V001", start=50.0), vessel("V002", start=20.0)], [crane("QC01")]))
    assert plan(action) == {"V002": ("QC01",)}


def test_fewer_cranes_than_demand_are_given_in_berth_order():
    vessels = [vessel("V001", 10.0, max_cranes=2), vessel("V002", 20.0, max_cranes=2),
               vessel("V003", 30.0, max_cranes=2)]
    action = P_C.decide(observe(vessels, [crane(f"QC0{i}") for i in range(1, 6)]))
    assert plan(action) == {"V001": ("QC01", "QC02"), "V002": ("QC03", "QC04"), "V003": ("QC05",)}
    assert [a.vessel_id for a in action.assignments] == ["V001", "V002", "V003"]  # visit order


# 5-9 existing assignments, limits, status and compatibility ----------------------------

def test_existing_assignments_count_toward_max_cranes():
    vessels = [vessel("V001", 0.0, max_cranes=2, assigned=("QC01",)), vessel("V002", 5.0, max_cranes=2)]
    cranes = [crane("QC01", "operating", "V001"), crane("QC02"), crane("QC03"), crane("QC04")]
    assert plan(P_C.decide(observe(vessels, cranes))) == {"V001": ("QC02",), "V002": ("QC03", "QC04")}


def test_vessel_at_max_cranes_receives_nothing():
    vessels = [vessel("V001", 0.0, max_cranes=1, assigned=("QC01",)), vessel("V002", 5.0, max_cranes=1)]
    cranes = [crane("QC01", "assigned", "V001"), crane("QC02"), crane("QC03")]
    action = P_C.decide(observe(vessels, cranes))
    assert plan(action) == {"V002": ("QC02",)}  # QC03 stays free: no over-allocation


@pytest.mark.parametrize("status", ["failed", "maintenance"])
def test_unavailable_cranes_are_never_proposed(status):
    action = P_C.decide(observe([vessel("V001")], [crane("QC01", status), crane("QC02")]))
    assert plan(action) == {"V001": ("QC02",)}


def test_crane_busy_on_another_vessel_is_not_reassigned():
    vessels = [vessel("V001", 0.0, max_cranes=1, assigned=("QC01",)), vessel("V002", 5.0)]
    action = P_C.decide(observe(vessels, [crane("QC01", "operating", "V001")]))
    assert action.action_type == "NO_ACTION" and action.no_action_reason == "NO_AVAILABLE_CRANE"


def test_compatibility_filter_skips_cranes_but_keeps_order():
    vessels = [vessel("V001", 0.0, max_cranes=2), vessel("V002", 5.0, max_cranes=2)]
    cranes = [crane("QC01", compatible=("V002",)), crane("QC02"), crane("QC03", compatible=("V002",))]
    assert plan(P_C.decide(observe(vessels, cranes))) == {"V001": ("QC02",), "V002": ("QC01", "QC03")}
    only_v9 = [crane("QC01", compatible=("V009",))]
    action = P_C.decide(observe([vessel("V001")], only_v9))
    assert action.no_action_reason == "NO_COMPATIBLE_CRANE"


# 10-12 invalid input and readiness -------------------------------------------------------

@pytest.mark.parametrize("build", [
    lambda: crane("Q1"),                                                    # malformed crane id
    lambda: vessel("SHIP-7"),                                               # malformed vessel id
    lambda: observe([vessel("V001")], [crane("QC01", "assigned", "V009")]),  # unknown vessel reference
    lambda: observe([vessel("V001", assigned=("QC09",))], [crane("QC01")]),  # unknown crane reference
    lambda: observe([vessel("V001", assigned=("QC01",))], [crane("QC01")]),  # two owners disagree
    lambda: observe([vessel("V001"), vessel("V001")], [crane("QC01")]),       # duplicate vessel
    lambda: observe([vessel("V001")], [crane("QC01"), crane("QC01")]),        # duplicate crane
    lambda: crane("QC01", "assigned", None),                                # assigned without vessel
    lambda: crane("QC01", "failed", "V001"),                                # failed but holding a vessel
    lambda: vessel("V001", max_cranes=1, assigned=("QC01", "QC02")),        # already over max
    lambda: vessel("V001", phase="WAITING", assigned=("QC01",)),           # cranes on an unberthed vessel
    lambda: CraneVesselView("V001", "HANDLING", 250.0, None, None, 2, 10),   # berthed without berth data
    lambda: CraneObservation(time_min=-1.0, vessels=(), cranes=()),
    lambda: observe([vessel("V001", assigned=("QC01",))],
                    [crane("QC01", "operating", "V001", compatible=("V002",))]),  # incompatible holder
])
def test_malformed_observations_raise_invalid_input(build):
    with pytest.raises(ObservationError) as error:
        build()
    assert error.value.code == "INVALID_INPUT"


def test_wrong_input_type_is_rejected_not_decided():
    with pytest.raises(ObservationError):
        P_C.decide({"vessels": [], "cranes": []})


@pytest.mark.parametrize("phase", ["WAITING", "NOT_ARRIVED", "DEPARTURE_PREP"])
def test_vessels_not_in_service_phase_receive_no_crane(phase):
    action = P_C.decide(observe([vessel("V001", phase=phase)], [crane("QC01")]))
    assert action.no_action_reason == "NO_ELIGIBLE_VESSEL"


def test_berthing_prep_vessel_is_eligible_and_finished_vessel_is_not():
    vessels = [vessel("V001", 0.0, remaining=0), vessel("V002", 5.0, phase="BERTHING_PREP")]
    assert plan(P_C.decide(observe(vessels, [crane("QC01")]))) == {"V002": ("QC01",)}


# 13-17 no-ops, uniqueness, limits ---------------------------------------------------------

@pytest.mark.parametrize("vessels, cranes, reason", [
    ([], [crane("QC01")], "NO_ELIGIBLE_VESSEL"),
    ([vessel("V001")], [], "NO_AVAILABLE_CRANE"),
    ([vessel("V001")], [crane("QC01", "failed")], "NO_AVAILABLE_CRANE"),
    ([vessel("V001", max_cranes=1, assigned=("QC01",))], [crane("QC01", "assigned", "V001"), crane("QC02")],
     "MAX_CRANES_REACHED"),
])
def test_explicit_no_action_reasons(vessels, cranes, reason):
    action = P_C.decide(observe(vessels, cranes))
    assert action.action_type == "NO_ACTION" and action.no_action_reason == reason
    assert action.assignments == () and action.releases == ()


def test_no_duplicate_crane_and_no_over_allocation_on_random_states():
    rng = random.Random(20261009)
    for _ in range(300):
        n_cranes, n_vessels = rng.randint(0, 6), rng.randint(0, 5)
        statuses = [rng.choice(["available", "available", "failed", "maintenance"]) for _ in range(n_cranes)]
        vessels = []
        cranes = []
        owners = {}
        for i in range(n_vessels):
            vid = f"V{i + 1:03d}"
            vessels.append((vid, rng.choice(["HANDLING", "BERTHING_PREP", "WAITING", "DEPARTURE_PREP"]),
                            rng.randint(1, 3), rng.randint(0, 50), float(rng.randint(0, 9))))
        for j, status in enumerate(statuses):
            cid = f"QC{j + 1:02d}"
            holders = [v for v in vessels if v[1] in ("HANDLING", "BERTHING_PREP")
                       and sum(o == v[0] for o in owners.values()) < v[2]]
            if status == "available" and holders and rng.random() < 0.3:
                owners[cid] = rng.choice(holders)[0]
            compat = None if cid in owners or rng.random() < 0.7 else tuple(rng.sample([v[0] for v in vessels], k=min(1, n_vessels)))
            cranes.append(crane(cid, "operating" if cid in owners else status, owners.get(cid), compat))
        obs = observe([vessel(v, s, max_cranes=m, remaining=r, phase=p,
                              assigned=tuple(c for c, o in owners.items() if o == v))
                       for v, p, m, r, s in vessels], cranes)
        action = P_C.decide(obs)
        assigned = [c for a in action.assignments for c in a.crane_ids]
        assert len(assigned) == len(set(assigned))
        by_id = {c.crane_id: c for c in obs.cranes}
        views = {v.vessel_id: v for v in obs.vessels}
        for a in action.assignments:
            v = views[a.vessel_id]
            assert v.crane_eligible and len(v.assigned_crane_ids) + len(a.crane_ids) <= v.max_cranes
            assert all(by_id[c].status == "available" and by_id[c].can_serve(v.vessel_id) for c in a.crane_ids)


def test_action_contract_rejects_duplicate_cranes():
    with pytest.raises(ActionContractError):
        CraneAction("p", 0.0, "ASSIGN_CRANES", (CraneAssignment("V001", ("QC01",)),
                                                CraneAssignment("V002", ("QC01",))))
    with pytest.raises(ActionContractError):
        CraneAssignment("V001", ("QC02", "QC01"))  # must be sorted


# 18-19 determinism ------------------------------------------------------------------------

def test_equal_berth_start_ties_break_by_vessel_id():
    vessels = [vessel("V002", 30.0, max_cranes=1), vessel("V001", 30.0, max_cranes=1)]
    assert plan(P_C.decide(observe(vessels, [crane("QC02"), crane("QC01")]))) == {"V001": ("QC01",),
                                                                                    "V002": ("QC02",)}


def test_record_order_does_not_change_the_decision():
    vessels = [vessel("V001", 40.0), vessel("V002", 10.0, max_cranes=1), vessel("V003", 10.0, max_cranes=3)]
    cranes = [crane(f"QC0{i}") for i in range(1, 6)] + [crane("QC06", "failed")]
    reference = P_C.decide(observe(vessels, cranes))
    rng = random.Random(7)
    for _ in range(20):
        v, c = vessels[:], cranes[:]
        rng.shuffle(v)
        rng.shuffle(c)
        shuffled = observe(v, c)
        assert shuffled == observe(vessels, cranes)
        assert P_C.decide(shuffled) == reference


# 20-23 immutability, no side effects, no hidden information --------------------------------

def test_observation_is_deeply_immutable_and_not_mutated():
    assigned = ["QC01"]
    v = vessel("V001", assigned=assigned)
    assigned.append("QC02")  # mutating the caller's list cannot reach the observation
    assert v.assigned_crane_ids == ("QC01",)
    obs = observe([v], [crane("QC01", "operating", "V001"), crane("QC02")])
    before = repr(obs)
    P_C.decide(obs)
    assert repr(obs) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.vessels = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.vessels[0].max_cranes = 9
    assert isinstance(obs.vessels, tuple) and isinstance(obs.vessels[0].assigned_crane_ids, tuple)


def test_decision_is_pure_and_declarative():
    obs = observe([vessel("V001")], [crane("QC01")])
    first, second = P_C.decide(obs), P_C.decide(obs)
    assert first == second and hash(first) == hash(second)
    fields = {f.name for f in dataclasses.fields(CraneAction)}
    assert not fields & {"completion_time_min", "events", "next_time_min", "service_time_min"}


def test_crane_views_expose_no_hidden_future_fields():
    hidden = {"arrival_time_min", "announce_time_min", "nominal_service_time_min", "workload_moves",
              "discharge_move_count", "load_move_count", "unavailability_windows", "scenario_id",
              "scenario_seed", "departure_time_min", "handling_end_time_min"}
    for cls in (CraneObservation, CraneVesselView, CraneView):
        assert not {f.name for f in dataclasses.fields(cls)} & hidden, cls.__name__


# 25 Project I-only states ------------------------------------------------------------------

def test_vessel_level_allocation_is_not_capped_by_ready_tasks():
    """Project 02 caps by READY tasks; P_c assigns up to max_cranes whenever work remains (D16 dispatches)."""
    action = P_C.decide(observe([vessel("V001", max_cranes=3, remaining=1)], [crane(f"QC0{i}") for i in (1, 2, 3)]))
    assert plan(action) == {"V001": ("QC01", "QC02", "QC03")}
