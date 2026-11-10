from dataclasses import replace
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.contracts import *
from rail_crane_scheduler.kernel import CraneSchedulingKernel
from rail_crane_scheduler.validator import verify


def solved():
    k=CraneSchedulingKernel(fixture())
    k.step(SchedulingDecision("ASSIGN_TASK","Z_left","j1")); k.step(SchedulingDecision("ASSIGN_TASK","A_right","j2"))
    while k.can_wait(): k.step(SchedulingDecision("WAIT",None,None))
    return k


def test_manual_independent_two_tasks():
    k=solved(); report=verify(k.problem,k.schedule())
    assert k.status=="COMPLETED" and report.valid_complete and report.makespan_min==5
    assert k.completed=={"j1","j2"}


def test_illegal_atomic_clone_wait():
    k=CraneSchedulingKernel(fixture()); before=k.observation()
    with pytest.raises(ContractError): k.step(SchedulingDecision("WAIT",None,None))
    with pytest.raises(ContractError): k.step(SchedulingDecision("ASSIGN_TASK","bad","j1"))
    assert k.observation()==before
    clone=k.clone(); clone.step(SchedulingDecision("ASSIGN_TASK","Z_left","j1"))
    assert k.records==[] and len(clone.records)==1
    with pytest.raises(ContractError): clone.step(SchedulingDecision("ASSIGN_TASK","A_right","j1"))
    assert not clone.legal_pair("Z_left","j2")


@pytest.mark.parametrize("mutation,code",[
    (lambda s: replace(s,tasks=s.tasks+(s.tasks[0],)),"TASK_IDENTITY"),
    (lambda s: replace(s,segments=(replace(s.segments[0],end_min=0.5),)+s.segments[1:]),"TRAVEL_SPEED"),
    (lambda s: replace(s,tasks=(replace(s.tasks[0],completion_min=3.),)+s.tasks[1:]),"PROCESS_DURATION"),
    (lambda s: replace(s,stop_min=2.),"INCOMPLETE_ORIGINAL_WORK"),
    (lambda s: replace(s,problem_hash="bad"),"PROBLEM_HASH"),
])
def test_independent_negative(mutation,code):
    k=solved(); r=verify(k.problem,mutation(k.schedule()))
    assert not r.valid_complete and code in r.errors


@pytest.mark.parametrize("positions,speeds",[
    (((0,0,10),(5,8,2),(10,0,10)),(1.6,1.6)),
    (((0,2,14),(4,14,10),(6,8,12),(14,8,20)),(3.,1.)),
])
def test_coarse_endpoint_crossing_counterexamples(positions,speeds):
    p=fixture(); p=replace(p, tasks=(),declared_workload_moves=0,vessel=replace(p.vessel,length_m=22.),rail=replace(p.rail,upper_m=22.),cranes=tuple(replace(c,initial_position_m=positions[0][i+1],reach_upper_m=22.,travel_speed_m_per_min=speeds[i]) for i,c in enumerate(p.cranes)))
    segments=[]
    for i,c in enumerate(p.cranes):
        for a,b in zip(positions,positions[1:]):
            mode="IDLE" if a[i+1]==b[i+1] else "TRAVEL"
            segments.append(MotionSegment(c.crane_id,mode,float(a[0]),float(b[0]),float(a[i+1]),float(b[i+1]),None))
    schedule=CraneSchedule(SCHEMA,p.fingerprint,"counterexample","CANDIDATE_UNVERIFIED",None,(),tuple(segments),float(positions[-1][0]))
    assert positions[0][2]-positions[0][1]>=2 and positions[-1][2]-positions[-1][1]>=2
    assert "SWEPT_RAIL_CLEARANCE" in verify(p,schedule).errors


def test_horizon_empty_and_unreachable():
    p=fixture(); p=replace(p,rail=replace(p.rail,horizon_min=0.5))
    k=CraneSchedulingKernel(p); k.step(SchedulingDecision("ASSIGN_TASK","Z_left","j1")); k.step(SchedulingDecision("WAIT",None,None))
    assert k.status=="TRUNCATED_HORIZON" and not verify(p,k.schedule()).valid_complete
    empty=replace(fixture(),tasks=(),declared_workload_moves=0)
    k=CraneSchedulingKernel(empty); assert k.status=="COMPLETED" and verify(empty,k.schedule()).makespan_min==0
    p=fixture(); p=replace(p,cranes=(replace(p.cranes[0],reach_upper_m=1.),replace(p.cranes[1],reach_lower_m=19.)))
    k=CraneSchedulingKernel(p); k.mark_deadlock(); assert k.status=="DEADLOCK"


def test_opposite_assignment_cannot_cross_occupied_crane():
    k=CraneSchedulingKernel(fixture()); k.step(SchedulingDecision("ASSIGN_TASK","Z_left","j2"))
    assert not k.legal_pair("A_right","j1")


def test_asymmetric_effective_rates_and_body_profile_rejection():
    p=fixture(); p=replace(p,cranes=(p.cranes[0],replace(p.cranes[1],effective_moves_per_hour=120.)))
    k=CraneSchedulingKernel(p)
    k.step(SchedulingDecision('ASSIGN_TASK','Z_left','j1')); k.step(SchedulingDecision('ASSIGN_TASK','A_right','j2'))
    while k.can_wait(): k.step(SchedulingDecision('WAIT',None,None))
    assert verify(p,k.schedule()).makespan_min==4.
    with pytest.raises(ContractError): replace(p.rail,separation_model='BODY_ENVELOPE')
