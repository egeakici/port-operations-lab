"""Step 3 policies on decision-time snapshots built from real Step 2 scenarios (development only).

Every snapshot here is a TEST FIXTURE: a hand-constructed, physically possible
operational state (which vessels are berthed, which cranes are busy, which
batch awaits a block). It is not an executed episode and yields no KPI.
Static fields come from the generated scenario through the ``from_scenario_*``
helpers; dynamic state is set by the test.
"""

from __future__ import annotations

import collections
import copy
import statistics
import time

import pytest

from integrated_terminal_pilot.policies import (
    CraneObservation, CraneVesselView, CraneView, FirstFitYardPolicy, GreedyBerthOrderCranePolicy,
    ObservationError, OccupancyBalancingYardPolicy, YardBlockView, YardContainerView, YardObservation,
    YardRequest, create_policy,
)
from integrated_terminal_pilot.scenarios.models import PRE_EPISODE

pytestmark = pytest.mark.integration
P_C, P_Y, BALANCE = GreedyBerthOrderCranePolicy(), FirstFitYardPolicy(), OccupancyBalancingYardPolicy()


# ------------------------------------------------------------------ snapshot helpers (test fixtures)

def initial_occupancy(doc):
    sizes = {c["container_id"]: c["size_teu"] for c in doc["containers"]}
    occupied = collections.Counter()
    for entry in doc["initial_state"]["container_locations"]:
        if entry["status"] == "IN_YARD":
            occupied[entry["location"]["location_id"]] += sizes[entry["container_id"]]
    return occupied


def block_views(doc, overrides=None):
    occupied = initial_occupancy(doc)
    overrides = overrides or {}
    return tuple(YardBlockView.from_scenario_block(b, **{"occupied_teu": occupied[b["block_id"]],
                                                        **overrides.get(b["block_id"], {})})
                 for b in doc["terminal"]["yard_blocks"])


def discharge_batch(doc, vessel_id, flow, *, size=None, limit=10):
    """First ``limit`` containers of one homogeneous group discharged by ``vessel_id``."""
    groups = collections.defaultdict(list)
    for c in doc["containers"]:
        if c["origin_vessel_id"] == vessel_id and c["cargo_flow"] == flow and size in (None, c["container_size"]):
            groups[c["container_group_id"]].append(c)
    members = sorted(groups[min(groups)], key=lambda c: c["container_id"])[:limit]
    return YardRequest("WO-000001", "DISCHARGE", vessel_id, tuple(
        YardContainerView.from_scenario_container(c, status="ABOARD_ARRIVED_VESSEL") for c in members))


def gate_in_request(doc):
    """One export at the gate: a container whose (hidden) gate-in request has already happened."""
    record = min((c for c in doc["containers"] if c["cargo_flow"] == "export" and not c["present_at_episode_start"]),
                 key=lambda c: (c["scheduled_gate_in_time_min"], c["container_id"]))
    request = YardRequest("WO-000002", "GATE_IN", "G01",
                          (YardContainerView.from_scenario_container(record, status="AT_GATE"),))
    return request, record["scheduled_gate_in_time_min"]


def crane_snapshot(doc):
    """V001 and V002 berthed (V001 first); the last crane already works V002; the rest available."""
    vessels = {v["vessel_id"]: v for v in doc["vessels"]}
    cranes = doc["resources"]["quay_cranes"]
    busy = cranes[-1]["crane_id"]
    v1, v2 = vessels["V001"], vessels["V002"]
    views = (
        CraneVesselView("V001", "HANDLING", v1["length_m"], 0.0, v1["arrival_time_min"], v1["max_cranes"],
                        v1["workload_moves"]),
        CraneVesselView("V002", "BERTHING_PREP", v2["length_m"], v1["length_m"] + 20.0, v2["arrival_time_min"],
                        v2["max_cranes"], v2["workload_moves"], (busy,)),
    )
    crane_views = tuple(CraneView.from_scenario_crane(c, status="operating", assigned_vessel_id="V002",
                                                      activity="PRODUCTIVE") if c["crane_id"] == busy
                        else CraneView.from_scenario_crane(c) for c in cranes)
    return CraneObservation(time_min=v2["arrival_time_min"], vessels=views, cranes=crane_views,
                            decision_id="TEST-FIXTURE-CRANE")


@pytest.fixture(scope="module")
def docs(medium_doc, heavy_doc, low_doc, bottleneck_result):
    return {"itp_medium": medium_doc, "itp_heavy": heavy_doc, "itp_low": low_doc,
            "itp_yard_bottleneck": bottleneck_result.scenario}


FAMILIES = ["itp_medium", "itp_heavy", "itp_low", "itp_yard_bottleneck"]


# ------------------------------------------------------------------ crane

@pytest.mark.parametrize("family", FAMILIES)
def test_crane_snapshot_on_generated_scenario(docs, family):
    doc = docs[family]
    assert doc["identity"]["split"] == "development"
    obs = crane_snapshot(doc)
    action = P_C.decide(obs)
    # 4 cranes, max_cranes 2: V001 (earlier berth start) takes QC01+QC02; V002 holds QC04, gets QC03.
    assert [c["crane_id"] for c in doc["resources"]["quay_cranes"]] == ["QC01", "QC02", "QC03", "QC04"]
    assert {a.vessel_id: a.crane_ids for a in action.assignments} == {"V001": ("QC01", "QC02"),
                                                                      "V002": ("QC03",)}
    assert action.decision_id == "TEST-FIXTURE-CRANE"


# ------------------------------------------------------------------ yard

@pytest.mark.parametrize("family", FAMILIES)
def test_first_fit_on_the_twelve_block_reference_yard(docs, family):
    doc = docs[family]
    blocks = block_views(doc)
    assert [b.block_id for b in blocks] == [f"B{i:02d}" for i in range(1, 13)]
    req = discharge_batch(doc, "V001", "import", size="40_ft")
    action = P_Y.decide(YardObservation(time_min=0.0, request=req, blocks=blocks))
    assert action.block_id == "B01" and action.required_teu == 2.0 * len(req.containers)
    # Fill B01-B05 to within 1 TEU: a 40 ft batch must skip them; B06 is the first block that fits.
    full = {f"B{i:02d}": {"occupied_teu": 2199.0} for i in range(1, 6)}
    action = P_Y.decide(YardObservation(time_min=0.0, request=req, blocks=block_views(doc, full)))
    assert action.block_id == "B06"
    twenty = discharge_batch(doc, "V001", "import", size="20_ft", limit=1)
    assert P_Y.decide(YardObservation(time_min=0.0, request=twenty, blocks=block_views(doc, full))).block_id == "B01"


@pytest.mark.parametrize("family", FAMILIES)
def test_all_three_flows_on_generated_scenario(docs, family):
    doc = docs[family]
    blocks = block_views(doc)
    ts = discharge_batch(doc, next(c["origin_vessel_id"] for c in doc["containers"]
                                   if c["cargo_flow"] == "transshipment" and c["origin_vessel_id"] != PRE_EPISODE),
                         "transshipment")
    assert all(c.destination_vessel_id for c in ts.containers)
    gate, gate_time = gate_in_request(doc)
    for req, t in ((ts, 0.0), (gate, gate_time)):
        action = P_Y.decide(YardObservation(time_min=t, request=req, blocks=blocks))
        assert action.action_type == "ALLOCATE_BLOCK" and action.container_ids == req.container_ids


def test_export_cannot_be_allocated_before_its_gate_in(low_doc):
    """At t = 0 an in-episode export is EXPECTED_BY_LANDSIDE: it cannot form a gate-in request."""
    record = next(c for c in low_doc["containers"] if c["cargo_flow"] == "export" and not c["present_at_episode_start"])
    status = next(e["status"] for e in low_doc["initial_state"]["container_locations"]
                  if e["container_id"] == record["container_id"])
    assert status == "EXPECTED_BY_LANDSIDE"
    with pytest.raises(ObservationError):
        YardRequest("WO-000003", "GATE_IN", "G01", (YardContainerView.from_scenario_container(record, status=status),))


def test_bottleneck_handling_capacity_does_not_change_storage_choice(docs):
    doc = docs["itp_yard_bottleneck"]
    blocks = block_views(doc)
    assert {b.handling_capacity_moves_per_hour for b in blocks} == {30.0}
    assert all(abs(b.occupied_teu / b.capacity_teu - 0.7) < 1e-3 for b in blocks)
    req = discharge_batch(doc, "V001", "import")
    reference = P_Y.decide(YardObservation(time_min=0.0, request=req, blocks=blocks))
    faster = block_views(doc, {b.block_id: {} for b in blocks})
    faster = tuple(YardBlockView(b.block_id, b.status, b.capabilities, b.allowed_sizes, b.capacity_teu,
                                 b.occupied_teu, b.reserved_teu, b.blocked_teu, 60.0) for b in faster)
    assert P_Y.decide(YardObservation(time_min=0.0, request=req, blocks=faster)) == reference
    assert reference.block_id == "B01"  # 660 TEU free per block: storage is not the constraint here


def test_balancing_diagnostic_on_generated_yard(medium_doc):
    occupied = {f"B{i:02d}": {"occupied_teu": 1500.0 - 10.0 * i} for i in range(1, 13)}
    req = discharge_batch(medium_doc, "V001", "import")
    obs = YardObservation(time_min=0.0, request=req, blocks=block_views(medium_doc, occupied))
    assert P_Y.decide(obs).block_id == "B01" and BALANCE.decide(obs).block_id == "B12"


# ------------------------------------------------------------------ golden fixture

def test_golden_fixture_snapshot(golden_doc):
    blocks = block_views(golden_doc)
    assert [(b.block_id, b.occupied_teu) for b in blocks] == [("B01", 0.0), ("B02", 1.0)]
    by_id = {c["container_id"]: c for c in golden_doc["containers"]}
    ts = YardRequest("WO-000001", "DISCHARGE", "V001",
                     (YardContainerView.from_scenario_container(by_id["CNT-000003"], status="ABOARD_ARRIVED_VESSEL"),))
    action = P_Y.decide(YardObservation(time_min=36.0, request=ts, blocks=blocks))
    assert (action.block_id, action.required_teu, action.container_ids) == ("B01", 2.0, ("CNT-000003",))
    v1 = golden_doc["vessels"][0]
    crane = CraneObservation(time_min=0.0, vessels=(CraneVesselView("V001", "BERTHING_PREP", v1["length_m"], 50.0, 0.0,
                                                                     v1["max_cranes"], v1["workload_moves"]),),
                             cranes=(CraneView.from_scenario_crane(golden_doc["resources"]["quay_cranes"][0]),))
    assert P_C.decide(crane).assignments[0].crane_ids == ("QC01",)


# ------------------------------------------------------------------ information isolation

def test_hidden_scenario_fields_cannot_influence_decisions(low_doc):
    """Perturb only hidden future truth; identical observations and decisions follow."""
    hidden = copy.deepcopy(low_doc)
    for c in hidden["containers"]:
        if c["scheduled_gate_in_time_min"] is not None:
            c["scheduled_gate_in_time_min"] += 1.0
        if c["scheduled_pickup_time_min"] is not None:
            c["scheduled_pickup_time_min"] *= 2.0
        c["gross_weight_kg"] = 1234
        c["source_scenario_id"] = "other"
    for v in hidden["vessels"][2:]:
        v["arrival_time_min"] += 999.0  # future, unannounced vessels
    req, req_hidden = discharge_batch(low_doc, "V001", "import"), discharge_batch(hidden, "V001", "import")
    assert req == req_hidden
    obs = YardObservation(time_min=0.0, request=req, blocks=block_views(low_doc))
    obs_hidden = YardObservation(time_min=0.0, request=req_hidden, blocks=block_views(hidden))
    assert obs == obs_hidden and P_Y.decide(obs) == P_Y.decide(obs_hidden)
    assert crane_snapshot(low_doc) == crane_snapshot(hidden)


def test_scenario_documents_are_not_observations(low_doc):
    for policy in (P_C, P_Y, BALANCE):
        with pytest.raises(ObservationError):
            policy.decide(low_doc)


def test_policies_never_mutate_the_scenario(low_doc):
    before = copy.deepcopy(low_doc)
    P_C.decide(crane_snapshot(low_doc))
    P_Y.decide(YardObservation(time_min=0.0, request=discharge_batch(low_doc, "V001", "import"),
                               blocks=block_views(low_doc)))
    assert low_doc == before


def test_registry_ids_and_defaults():
    assert create_policy("primitive_crane_greedy_v1").protocol_name == "P_c"
    assert create_policy("yard_first_fit_v1").protocol_name == "P_y"
    with pytest.raises(KeyError):
        create_policy("yard_best_fit_v9")


# ------------------------------------------------------------------ engineering timing (not an SLA)

def test_decision_overhead_is_small(heavy_doc, capsys):
    yard_obs = YardObservation(time_min=0.0, request=discharge_batch(heavy_doc, "V001", "import"),
                               blocks=block_views(heavy_doc))
    crane_obs = CraneObservation(time_min=500.0, vessels=tuple(
        CraneVesselView(f"V{i:03d}", "HANDLING", 250.0, 270.0 * (i - 1), float(i), 2, 300) for i in range(1, 5)),
        cranes=tuple(CraneView(f"QC{i:02d}", "available", None, 30.0) for i in range(1, 5)))
    timings = {}
    for name, fn in (("crane P_c (4 vessels, 4 cranes)", lambda: P_C.decide(crane_obs)),
                     ("yard P_y (12 blocks, 10-container batch)", lambda: P_Y.decide(yard_obs)),
                     ("yard balance (12 blocks)", lambda: BALANCE.decide(yard_obs))):
        samples = []
        for _ in range(2000):
            started = time.perf_counter()
            fn()
            samples.append(time.perf_counter() - started)
        timings[name] = (statistics.median(samples) * 1e6, max(samples) * 1e6)
    with capsys.disabled():
        for name, (median_us, max_us) in timings.items():
            print(f"\n[step3 timing] {name}: median {median_us:.1f} us, max {max_us:.1f} us")
    assert all(median_us < 5000.0 for median_us, _ in timings.values())  # loose sanity bound, not an SLA
