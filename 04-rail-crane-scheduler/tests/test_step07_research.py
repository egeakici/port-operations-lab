from dataclasses import replace
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.research import *
from rail_crane_scheduler.baselines import paired_development


def test_pairing_metrics_and_missing_duplicates():
    p=fixture(); rows=paired_development(p)
    assert verify_records(rows,p)
    with pytest.raises(ContractError): verify_records(rows+(rows[0],),p)
    with pytest.raises(ContractError): verify_records((replace(rows[0],problem_hash='bad'),),p)
    bad=replace(rows[0],metrics=replace(rows[0].metrics,makespan_min=1.))
    with pytest.raises(ContractError): verify_records((bad,),p)


def test_nested_seed_independence_and_bootstrap():
    means=nested_seed_means([('a',11,4.),('a',23,6.),('b',11,8.),('b',23,10.)],(11,23))
    assert means=={'a':5.,'b':9.}
    result=paired_summary(means,{'a':6.,'b':10.},draws=100,seed=9,confidence=.95,min_scenarios=2)
    assert result['n_independent_scenarios']==2 and result['mean_delta_min']==-1
    assert result==paired_summary(means,{'a':6.,'b':10.},draws=100,seed=9,confidence=.95,min_scenarios=2)
    with pytest.raises(ContractError): nested_seed_means([('a',11,4.)],(11,23))
    assert holm({'a':.001,'b':.04,'c':.9},.05)=={'a':True,'b':False,'c':False}


def test_no_fake_lock_or_write_overwrite(tmp_path):
    candidate=candidate_lock(); assert candidate['primary_profile']=='PRIMARY_PROFILE_NOT_LOCKED'
    with pytest.raises(ContractError): manual_gate(candidate,tmp_path/'absent','wrong')
    p=fixture(); rows=paired_development(p); write_development(p,rows,tmp_path/'run')
    with pytest.raises(ContractError): write_development(p,rows,tmp_path/'run')
