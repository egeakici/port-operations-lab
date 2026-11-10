from dataclasses import replace
import json
import pytest
from rail_crane_scheduler.contracts import *


def fixture():
    # TEST_FIXTURE_SYNTHETIC; not production/research defaults.
    return QCSPProblem(
        ProblemMetadata(SCHEMA, "QCSP_V1", "fixture", "tiny", "development", "p04/fixture", 0, "TEST_FIXTURE_SYNTHETIC", ASSUMPTIONS, "Project04", None),
        VesselContext("V", "B", 20., 0., 1, 0., None),
        RailGeometry("R", "quay_x_m", 0., 20., 2., "REFERENCE_POINT", 1e-9, 1e-9, 100.),
        (CraneDefinition("Z_left", "R", 0, 0., 0., 20., 2., 60., 1., 0.), CraneDefinition("A_right", "R", 1, 20., 0., 20., 2., 60., 1., 0.)),
        (BayDefinition("b1", 2., 2.), BayDefinition("b2", 18., 18.)),
        (CraneTaskGroup("j1", "V", "b1", "DISCHARGE", 2, 0., (), (), ()), CraneTaskGroup("j2", "V", "b2", "LOAD", 3, 0., (), (), ())),
        5, ("min", "m", "moves", "moves/hour"))


def test_canonical_roundtrip_and_order():
    p = fixture()
    assert QCSPProblem.from_json(p.to_json()) == p
    assert QCSPProblem.from_dict(dict(reversed(list(p.to_dict().items())))).fingerprint == p.fingerprint
    assert p.cranes[0].crane_id > p.cranes[1].crane_id
    assert len(p.fingerprint) == 64


@pytest.mark.parametrize("mutation", [
    lambda p: replace(p, declared_workload_moves=4),
    lambda p: replace(p, tasks=p.tasks + (p.tasks[0],)),
    lambda p: replace(p, cranes=p.cranes[:1]),
    lambda p: replace(p, units=("hour", "m", "moves", "moves/hour")),
    lambda p: replace(p, bays=(replace(p.bays[0], verified_global_m=3.),)),
    lambda p: replace(p, cranes=(replace(p.cranes[0], initial_position_m=21.), p.cranes[1])),
    lambda p: replace(p, tasks=(replace(p.tasks[0], bay_id="missing"),)),
    lambda p: replace(p, metadata=replace(p.metadata, origin="REAL_AIS")),
    lambda p: replace(p, metadata=replace(p.metadata, schema_version="2")),
    lambda p: replace(p, tasks=(replace(p.tasks[0], workload_moves=True),)),
    lambda p: replace(p, tasks=(replace(p.tasks[0], workload_moves=-1),)),
    lambda p: replace(p, tasks=(replace(p.tasks[0], predecessor_ids=("x",)),)),
    lambda p: replace(p, tasks=(replace(p.tasks[0], release_min=2.),)),
    lambda p: replace(p, rail=replace(p.rail, lower_m=float("nan"))),
])
def test_rejections(mutation):
    with pytest.raises(ContractError): mutation(fixture())


def test_orientation_and_missing_transform():
    v = replace(fixture().vessel, orientation=-1)
    assert local_to_global(v, 2) == 18
    with pytest.raises(ContractError): VesselContext.from_dict({"vessel_id": "V"})
    with pytest.raises(ContractError): local_to_global(v, True)
    assert moves_per_minute(60) == 1


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{'])
def test_strict_json(text):
    with pytest.raises(ContractError): strict_json(text)


def test_unknown_and_candidate_boundary():
    d = fixture().to_dict(); d["future_field"] = 1
    with pytest.raises(ContractError): QCSPProblem.from_dict(d)
    assert SchedulingDecision("WAIT", None, None).tag == "WAIT"
    with pytest.raises(ContractError): SchedulingDecision("CANCEL", None, None)
    with pytest.raises(ContractError): CraneSchedule(SCHEMA, "x", "p", "VALIDATED_FEASIBLE", None, (), (), 0.)
    # Null is serializable, but cannot execute; not converted into zero.
    p = fixture(); p = replace(p, rail=replace(p.rail, min_clearance_m=None))
    assert QCSPProblem.from_json(p.to_json()).rail.min_clearance_m is None
    with pytest.raises(ContractError): p.require_fixture_execution()


def test_multiple_jobs_same_bay():
    p = fixture(); tasks = (p.tasks[0], replace(p.tasks[1], bay_id="b1"))
    assert replace(p, tasks=tasks).declared_workload_moves == 5
