from dataclasses import replace
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.baselines import *


@pytest.mark.parametrize("policy",POLICIES)
def test_hand_schedule_and_determinism(policy):
    p=fixture(); a=run(p,policy); b=run(p,policy)
    assert a.schedule.to_json()==b.schedule.to_json()
    assert a.metrics.valid_complete and a.metrics.makespan_min==5.
    assert a.metrics.productive_crane_min==5 and a.metrics.travel_min==2 and a.metrics.travel_m==4
    assert a.metrics.utilization==0.5 and a.metrics.idle_crane_min==1
    assert a.metrics.completed_moves==a.metrics.original_moves==5


def test_four_rules_are_meaningfully_distinct():
    p=fixture(); tasks=(replace(p.tasks[0],workload_moves=1),replace(p.tasks[1],workload_moves=10))
    p=replace(p,tasks=tasks,declared_workload_moves=11)
    k=CraneSchedulingKernel(p)
    assert choose(k,"ordered_sweep_v1").task_id=="j1"
    assert choose(k,"longest_work_v1").task_id=="j2"
    assert choose(k,"nearest_feasible_v1").crane_id=="Z_left"


def test_failures_zero_work_and_pairing():
    p=fixture(); dead=replace(p,cranes=(replace(p.cranes[0],reach_upper_m=1.),replace(p.cranes[1],reach_lower_m=19.)))
    result=run(dead,POLICIES[0]); assert result.status=="DEADLOCK" and result.metrics.makespan_min is None
    assert result.metrics.completed_moves==0
    empty=run(replace(p,tasks=(),declared_workload_moves=0),POLICIES[0])
    assert empty.metrics.makespan_min==0 and empty.metrics.utilization is None
    results=paired_development(p); assert len(results)==4 and len({r.problem_hash for r in results})==1
    with pytest.raises(ContractError): run(replace(p,metadata=replace(p.metadata,role="test")),POLICIES[0])
