from dataclasses import replace
import copy
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.integration import *
from rail_crane_scheduler.baselines import run,POLICIES


def inputs():
    p=fixture(); p=replace(p,tasks=tuple(replace(t,source_task_ids=('synthetic_source_'+t.task_id,)) for t in p.tasks))
    observation={'schema_version':'itp_crane_observation_v1','time_min':0.,'decision_id':'fixture_decision','vessels':[{'vessel_id':'V','max_cranes':2,'remaining_moves':5,'phase':'HANDLING','berth_position_m':0.,'length_m':20.}],'cranes':[{'crane_id':c.crane_id,'status':'available'} for c in p.cranes]}
    return observation,p


def test_isolated_smoke_freshness_and_source_unchanged():
    observation,p=inputs(); original=copy.deepcopy(observation)
    request=from_primitive(observation,p,expected_axis='quay_x_m',expected_clearance_m=2.)
    result=run(request.problem,POLICIES[0]); proposal=to_proposal(request,result.schedule)
    assert IntegratedProposal.from_json(proposal.to_json())==proposal
    actual=isolated_smoke(request,proposal,current_state_hash=request.source_state_hash,current_decision_id=request.decision_id,current_time_min=0.)
    assert actual['status']=='ISOLATED_SMOKE_PASS' and actual['executed_moves']==5 and not actual['cargo_ledger_mutated']
    assert observation==original
    with pytest.raises(ContractError): isolated_smoke(request,proposal,current_state_hash='changed',current_decision_id=request.decision_id,current_time_min=0.)
    with pytest.raises(ContractError): legacy_crane_action(proposal)


@pytest.mark.parametrize('issue',['missing','axis','clearance','provenance','fleet'])
def test_explicit_gaps(issue):
    observation,p=inputs(); axis='quay_x_m'; clearance=2.
    if issue=='missing': p=None
    if issue=='axis': axis='other_axis'
    if issue=='clearance': clearance=3.
    if issue=='provenance': p=replace(p,tasks=tuple(replace(t,source_task_ids=()) for t in p.tasks))
    if issue=='fleet': observation['cranes'].pop()
    with pytest.raises(ContractError): from_primitive(observation,p,expected_axis=axis,expected_clearance_m=clearance)
