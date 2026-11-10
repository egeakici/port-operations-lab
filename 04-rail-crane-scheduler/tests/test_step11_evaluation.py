import pytest
from rail_crane_scheduler.evaluation import *


def test_empty_report_and_guard_before_reading_test():
    report=render_report([])
    assert 'SCIENTIFIC_EVIDENCE_NOT_YET_RUN' in report and 'checkpoints: 0' in report
    with pytest.raises(ContractError): evaluate_manual({'test_inputs':['never-read']},'absent','wrong','unused')


def test_cell_integrity_and_immutable_resume(tmp_path):
    cell=tmp_path/'cell'; commit_cell(cell,{'x':1},None)
    assert verify_cell(cell)=={'x':1}
    with pytest.raises(ContractError): commit_cell(cell,{'x':2},None)
    (cell/'result.json').write_text('{"x":2}',encoding='utf-8')
    with pytest.raises(ContractError): verify_cell(cell)


def test_nested_complete_pair_and_unconditional_failures():
    rows=[]
    for scenario in ('a','b'):
        for arm,seed,val in [('reference',None,10.),('ppo11',11,8.),('ppo23',23,6.)]:
            rows.append(dict(scenario_id=scenario,policy_id=arm,training_seed=seed,valid_complete=True,makespan_min=val))
    result=analyze_rows(rows,seeds=(11,23),reference_policy='reference',draws=50,bootstrap_seed=1,confidence=.95,min_scenarios=2)
    assert result['paired']['n_independent_scenarios']==2 and result['paired']['mean_delta_min']==-3
    rows[-1].update(valid_complete=False,makespan_min=None)
    result=analyze_rows(rows,seeds=(11,23),reference_policy='reference',draws=50,bootstrap_seed=1,confidence=.95,min_scenarios=2)
    assert result['paired'] is None and result['unconditional_failure_rate']['ppo23']==.5
    with pytest.raises(ContractError): analyze_rows(rows+[rows[0]],seeds=(11,23),reference_policy='reference',draws=10,bootstrap_seed=1,confidence=.95,min_scenarios=2)


def test_impossible_policy_cell_is_retained_failure():
    from dataclasses import replace
    from test_step02_contracts import fixture
    from test_step10_training import config
    p=fixture(); p=replace(p,cranes=(replace(p.cranes[0],reach_upper_m=1.),replace(p.cranes[1],reach_lower_m=19.)))
    class NeverPredict:
        def predict(self,*args,**kwargs): pytest.fail('deadlock must be recorded before inference')
    status,values,schedule,error=evaluate_policy(NeverPredict(),p,config(),None,'fixture_policy')
    assert status=='DEADLOCK' and values is None and error['code']=='DEADLOCK_INITIAL'


def test_evidence_plots_and_report_do_not_fabricate_empty_results():
    from rail_crane_scheduler.replay import png_bytes
    with pytest.raises(ContractError): analysis_figures([])
    rows=[{'scenario_id':'fixture','policy_id':'fixture_policy','status':'COMPLETED','origin':'TEST_FIXTURE_SYNTHETIC','valid_complete':True,'makespan_min':5.,'episode_wall_s':.1}]
    analysis={'paired':{'ci_lower_min':-2.,'ci_upper_min':0.,'mean_delta_min':-1.}}
    figures=analysis_figures(rows,analysis)
    assert set(figures)=={'runtime_quality','paired_interval'}
    assert all(png_bytes(fig).startswith(b'\x89PNG') for fig in figures.values())
    report=render_report(rows,analysis,'TEST_FIXTURE_MANIFEST')
    assert 'FIXTURE_ONLY_NOT_SCIENTIFIC' in report and 'unconditional failure rates' in report
