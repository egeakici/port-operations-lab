"""Rule equivalence of P_c / P_y with Project 02 GreedyCranePolicy / FirstFitYardPolicy.

Project 01 ``Terminal`` states are built through its public operational API
(register, arrive, berth, reserve, mark ready, assign, fail, close), the original
Project 02 rule runs on them unchanged, and P_c / P_y run on the equivalent
Project I observation produced by a test-only adapter. Equivalence is claimed
only where the Project 02 rule is defined with the same semantics; documented
generalisations are tested separately (implementation roadmap, Step 3 gate).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mini_port_sim.policies import FirstFitYardPolicy as P02FirstFit
from mini_port_sim.policies import GreedyCranePolicy as P02Greedy
from terminal_core import (
    Berth, ContainerFlow, ContainerGroup, ContainerGroupLocation, ContainerLoadState, ContainerSize,
    OperationTask, OperationType, QuayCrane, TaskLocation, TaskLocationType, Terminal, Vessel, VesselStatus,
    YardBlock, YardCapability,
)

from integrated_terminal_pilot.policies import (
    CraneObservation, CraneVesselView, CraneView, FirstFitYardPolicy, GreedyBerthOrderCranePolicy,
    YardBlockView, YardContainerView, YardObservation, YardRequest,
)

pytestmark = pytest.mark.integration
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)  # data contract D02 projection epoch
PHASE = {VesselStatus.BERTHED: "BERTHING_PREP", VesselStatus.OPERATING: "HANDLING"}  # data contract §12


# ------------------------------------------------------------------ Project 01 fixture builders

class CraneFixture:
    """Berths vessels in the given order (minute k), creates READY discharge tasks per vessel."""

    def __init__(self, crane_count=4, blocks=(("B01", 10_000.0),)):
        self.t = Terminal.create(
            current_time=EPOCH, berths=(Berth("BERTH-1", 1200.0),),
            quay_cranes=tuple(QuayCrane(f"QC{i:02d}", 100.0 * i, 30.0) for i in range(1, crane_count + 1)),
            yard_blocks=tuple(YardBlock(bid, cap) for bid, cap in blocks))
        self.berth_minute: dict[str, float] = {}
        self.tasks: dict[str, list[str]] = {}
        self.position = 0.0

    def berth(self, vessel_id, *, max_cranes, ready_tasks, minute):
        when = EPOCH + timedelta(minutes=minute)
        self.t.register_vessel(Vessel(vessel_id, 250.0, when, 100, 2, max_cranes), occurred_at=when)
        self.t.arrive_vessel(vessel_id, occurred_at=when)
        self.t.berth_vessel(vessel_id, "BERTH-1", self.position, occurred_at=when)
        self.t.start_vessel_operations(vessel_id, occurred_at=when)
        self.position += 270.0
        self.berth_minute[vessel_id] = float(minute)
        self.tasks[vessel_id] = []
        for k in range(ready_tasks):
            gid, tid = f"G-{vessel_id}-{k}", f"T-{vessel_id}-{k}"
            self.t.register_container_group(
                ContainerGroup(gid, ContainerSize.TWENTY_FT, 1, ContainerFlow.IMPORT, ContainerLoadState.LADEN,
                               source_vessel_id=vessel_id),
                initial_locations=(ContainerGroupLocation(gid, TaskLocation(TaskLocationType.VESSEL, vessel_id),
                                                          1.0),), occurred_at=when)
            self.t.reserve_yard_capacity(block_id="B01", group_id=gid, teu=1.0, occurred_at=when)
            self.t.register_operation_task(OperationTask(
                tid, OperationType.DISCHARGE, gid, 1.0, TaskLocation(TaskLocationType.VESSEL, vessel_id),
                TaskLocation(TaskLocationType.YARD_BLOCK, "B01")), occurred_at=when)
            self.t.mark_task_ready(tid, occurred_at=when)
            self.tasks[vessel_id].append(tid)

    def assign_existing(self, vessel_id, crane_id):
        """A crane already working a task of this vessel (Project 01 ASSIGNED)."""
        self.t.assign_task_resource(self.tasks[vessel_id].pop(0), crane_id)


def crane_observation(fx: CraneFixture) -> CraneObservation:
    """Test-only adapter: Project 01 terminal -> Project I crane observation."""
    t = fx.t
    vessels = []
    for vid in t.vessel_ids:
        v = t.get_vessel(vid)
        held = tuple(c for c in t.quay_crane_ids if t.get_quay_crane(c).assigned_vessel_id == vid)
        vessels.append(CraneVesselView(vid, PHASE[v.status], v.length_m, 0.0, fx.berth_minute[vid],
                                       v.max_cranes, v.workload_moves, held, v.priority))
    cranes = [CraneView(c, t.get_quay_crane(c).status.value, t.get_quay_crane(c).assigned_vessel_id,
                        t.get_quay_crane(c).moves_per_hour) for c in t.quay_crane_ids]
    return CraneObservation(time_min=0.0, vessels=tuple(vessels), cranes=tuple(cranes))


def run_project02_dispatch(fx: CraneFixture) -> dict[str, tuple[str, ...]]:
    """Project 02 crane_dispatcher order: vessels in berth order, each result applied before the next."""
    policy, result = P02Greedy(), {}
    for vid in sorted(fx.berth_minute, key=lambda v: (fx.berth_minute[v], v)):
        ready = tuple(fx.tasks[vid])
        assignments = policy.choose(fx.t, vessel_id=vid, task_ids=ready)
        for a in assignments:
            fx.t.assign_task_resource(a.task_id, a.crane_id)
        if assignments:
            result[vid] = tuple(sorted(a.crane_id for a in assignments))
    return result


def p_c_plan(observation: CraneObservation) -> dict[str, tuple[str, ...]]:
    action = GreedyBerthOrderCranePolicy().decide(observation)
    return {a.vessel_id: a.crane_ids for a in action.assignments}


def _crane_case(name):
    fx = CraneFixture()
    if name == "one_vessel":
        fx.berth("V001", max_cranes=2, ready_tasks=3, minute=0)
    elif name == "failed_crane":
        fx.berth("V001", max_cranes=3, ready_tasks=5, minute=0)
        fx.t.fail_quay_crane("QC01")
    elif name == "maintenance_crane":
        fx.berth("V001", max_cranes=2, ready_tasks=4, minute=0)
        fx.t.start_quay_crane_maintenance("QC02")
    elif name == "berth_order_and_existing_assignment":
        fx.berth("V002", max_cranes=2, ready_tasks=4, minute=0)
        fx.berth("V001", max_cranes=2, ready_tasks=4, minute=10)
        fx.assign_existing("V002", "QC03")
    elif name == "scarce_cranes_three_vessels":
        fx.berth("V003", max_cranes=1, ready_tasks=2, minute=0)
        fx.berth("V001", max_cranes=2, ready_tasks=3, minute=5)
        fx.berth("V002", max_cranes=3, ready_tasks=4, minute=5)
    elif name == "vessel_at_max":
        fx.berth("V001", max_cranes=1, ready_tasks=3, minute=0)
        fx.assign_existing("V001", "QC01")
        fx.berth("V002", max_cranes=2, ready_tasks=3, minute=1)
    return fx


@pytest.mark.parametrize("case", ["one_vessel", "failed_crane", "maintenance_crane",
                                  "berth_order_and_existing_assignment", "scarce_cranes_three_vessels",
                                  "vessel_at_max"])
def test_p_c_reproduces_project02_greedy_crane_rule(case):
    fx = _crane_case(case)
    observation = crane_observation(fx)  # snapshot before Project 02 mutates its terminal
    assert p_c_plan(observation) == run_project02_dispatch(fx)


def test_documented_difference_ready_task_cap():
    """Project 02 assigns at most one crane per READY task; P_c (vessel level, D16) does not."""
    fx = CraneFixture()
    fx.berth("V001", max_cranes=3, ready_tasks=1, minute=0)
    observation = crane_observation(fx)
    assert run_project02_dispatch(fx) == {"V001": ("QC01",)}
    assert p_c_plan(observation) == {"V001": ("QC01", "QC02", "QC03")}


def test_documented_difference_compatibility_is_project_i_only():
    """Project 01 cranes have no compatibility list; P_c honours compatible_vessel_ids."""
    fx = CraneFixture()
    fx.berth("V001", max_cranes=2, ready_tasks=2, minute=0)
    base = crane_observation(fx)
    restricted = CraneObservation(time_min=0.0, vessels=base.vessels, cranes=tuple(
        CraneView(c.crane_id, c.status, c.assigned_vessel_id, c.nominal_moves_per_hour,
                  ("V009",) if c.crane_id == "QC01" else None) for c in base.cranes))
    assert run_project02_dispatch(fx) == {"V001": ("QC01", "QC02")}
    assert p_c_plan(restricted) == {"V001": ("QC02", "QC03")}


# ------------------------------------------------------------------ yard

def yard_terminal(blocks, *, occupied=(), reserved=(), closed=(), maintenance=()):
    """Existing yard stock is created through ``Terminal.create`` (consistent snapshot path);
    reservations, closures and maintenance through the operational API."""
    stock = {bid: {} for bid, _, _ in blocks}
    groups, locations = [], []
    for k, (bid, teu) in enumerate(occupied):
        gid = f"OCC-{k}"
        groups.append(ContainerGroup(gid, ContainerSize.TWENTY_FT, int(teu), ContainerFlow.IMPORT,
                                     ContainerLoadState.LADEN, source_vessel_id="VX"))
        locations.append(ContainerGroupLocation(gid, TaskLocation(TaskLocationType.YARD_BLOCK, bid), teu))
        stock[bid][gid] = teu
    yard = tuple(YardBlock.from_dict({"block_id": bid, "capacity_teu": cap,
                                      "capabilities": sorted(c.value for c in caps), "status": "open",
                                      "stored_groups": stock[bid], "reservations": {}})
                 for bid, cap, caps in blocks)
    t = Terminal.create(current_time=EPOCH, vessels=(Vessel("VX", 250.0, EPOCH, 100, 2, 1),),
                        yard_blocks=yard, container_groups=tuple(groups), group_locations=tuple(locations))
    for k, (bid, teu) in enumerate(reserved):
        gid = f"RES-{k}"
        t.register_container_group(
            ContainerGroup(gid, ContainerSize.TWENTY_FT, int(teu), ContainerFlow.IMPORT, ContainerLoadState.LADEN,
                           source_vessel_id="VX"),
            initial_locations=(ContainerGroupLocation(gid, TaskLocation(TaskLocationType.VESSEL, "VX"), teu),))
        t.reserve_yard_capacity(block_id=bid, group_id=gid, teu=teu)
    for bid in closed:
        t.close_yard_block(bid)
    for bid in maintenance:
        t.start_yard_block_maintenance(bid)
    return t


def yard_observation(t: Terminal, group: ContainerGroup) -> YardObservation:
    """Test-only adapter: Project 01 terminal + group -> Project I yard observation.

    Project 01 blocks have no size restriction, so both sizes are allowed; the
    group is expanded into its individually identified members.
    """
    blocks = tuple(YardBlockView(bid, b.status.value, tuple(c.value for c in b.capabilities),
                                 ("20_ft", "40_ft"), b.capacity_teu, b.occupied_teu, b.reserved_teu)
                   for bid in t.yard_block_ids for b in [t.get_yard_block(bid)])
    members = tuple(YardContainerView(f"CNT-{k + 1:06d}", "GRP-0001", group.container_size.value,
                                      group.teu_per_container, group.flow.value, group.load_state.value,
                                      group.is_reefer, group.is_hazardous, group.source_vessel_id,
                                      group.target_vessel_id, "ABOARD_ARRIVED_VESSEL")
                    for k in range(group.quantity))
    request = YardRequest("WO-000001", "DISCHARGE", group.source_vessel_id, members)
    return YardObservation(time_min=0.0, request=request, blocks=blocks)


GENERAL = (YardCapability.GENERAL,)
REEFER = (YardCapability.GENERAL, YardCapability.REEFER_POWER)


def group(size=ContainerSize.FORTY_FT, quantity=5, reefer=False):
    return ContainerGroup("GRP-NEW", size, quantity, ContainerFlow.IMPORT, ContainerLoadState.LADEN,
                          is_reefer=reefer, source_vessel_id="V001")


@pytest.mark.parametrize("terminal, g", [
    (lambda: yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, GENERAL)]), group()),
    (lambda: yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, GENERAL)], occupied=[("B01", 95.0)]),
     group()),                                                                           # 40 ft x5 = 10 TEU
    (lambda: yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, GENERAL)], occupied=[("B01", 95.0)]),
     group(ContainerSize.TWENTY_FT, 5)),                                                 # exactly 5 TEU left
    (lambda: yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, GENERAL), ("B03", 100.0, GENERAL)],
                           occupied=[("B01", 50.0)], reserved=[("B01", 45.0), ("B02", 92.0)]), group()),
    (lambda: yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, GENERAL), ("B03", 100.0, GENERAL)],
                           closed=["B01"], maintenance=["B02"]), group()),
    (lambda: yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, REEFER)]), group(reefer=True)),
    (lambda: yard_terminal([("B10", 100.0, GENERAL), ("B02", 100.0, GENERAL)], occupied=[("B02", 99.0)]),
     group(ContainerSize.TWENTY_FT, 1)),                                                 # id order, not insertion
    (lambda: yard_terminal([("B01", 8.0, GENERAL), ("B02", 9.0, GENERAL)]), group()),    # nothing fits
])
def test_p_y_reproduces_project02_first_fit(terminal, g):
    t = terminal()
    observation = yard_observation(t, g)
    p02 = P02FirstFit().choose(t, g)
    action = FirstFitYardPolicy().decide(observation)
    assert action.block_id == (None if p02 is None else p02.block_id)
    assert action.required_teu == g.total_teu


def test_documented_difference_size_restriction_is_project_i_only():
    """Project 01 blocks cannot restrict sizes; Project I blocks can (allowed_sizes)."""
    t = yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, GENERAL)])
    base = yard_observation(t, group())
    restricted = YardObservation(time_min=0.0, request=base.request, blocks=tuple(
        YardBlockView(b.block_id, b.status, b.capabilities, ("20_ft",) if b.block_id == "B01" else b.allowed_sizes,
                      b.capacity_teu, b.occupied_teu, b.reserved_teu) for b in base.blocks))
    assert P02FirstFit().choose(t, group()).block_id == "B01"
    assert FirstFitYardPolicy().decide(restricted).block_id == "B02"


def test_documented_difference_blocked_teu_and_individual_ids():
    """Project I subtracts blocked TEU (0 in v1) and keeps the exact member container ids."""
    t = yard_terminal([("B01", 100.0, GENERAL), ("B02", 100.0, GENERAL)], occupied=[("B01", 85.0)])
    base = yard_observation(t, group())
    blocked = YardObservation(time_min=0.0, request=base.request, blocks=tuple(
        YardBlockView(b.block_id, b.status, b.capabilities, b.allowed_sizes, b.capacity_teu, b.occupied_teu,
                      b.reserved_teu, 6.0 if b.block_id == "B01" else 0.0) for b in base.blocks))
    assert P02FirstFit().choose(t, group()).block_id == "B01"
    action = FirstFitYardPolicy().decide(blocked)
    assert action.block_id == "B02" and action.container_ids == tuple(f"CNT-{k:06d}" for k in range(1, 6))
