"""Step 7 safety and pairing contracts, using development data or isolated synthetic files only."""
import copy
import gzip
import json
from pathlib import Path

import pytest

from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark.step6_closure import ClosureError


def test_exact_inventory_without_sensitive_draws(monkeypatch):
    from integrated_terminal_pilot.scenarios import generator
    monkeypatch.setattr(generator, 'generate_scenario', lambda *a, **k: pytest.fail('sensitive draw'))
    p=s.build_plan()
    assert len(p['scenarios'])==140 and len(p['rows'])==1960
    assert sum(r['world']=='integrated' for r in p['rows'])==1260
    for split,n in [('validation',560),('test',1400)]:
        assert sum(r['split']==split for r in p['rows'])==n
    assert p['wall_time_admission_limit'] is None and p['candidate_timeout'] is None
    assert {r['ppo_training_seed'] for r in p['rows'] if r['arm']=='A3'}=={11,23,37}
    assert {r['family'] for r in p['rows']}=={'itp_medium','itp_heavy'}


def test_duplicate_and_missing_inventory_rejected():
    p=s.build_plan()
    p['rows'].append(copy.deepcopy(p['rows'][0]))
    with pytest.raises(s.CampaignError,match='duplicate'):
        s.validate_plan(p)
    p['rows']=p['rows'][:-2]
    with pytest.raises(s.CampaignError,match='incomplete'):
        s.validate_plan(p)


@pytest.mark.parametrize('split',['validation','test','diagnostic'])
def test_no_prelock_generation_or_read(split,tmp_path,monkeypatch):
    def blocked(*a):
        raise s.CampaignError('owner gate pending')
    monkeypatch.setattr(s,'verify_lock',blocked)
    monkeypatch.setattr(s,'read_json',lambda *a:pytest.fail('sensitive file opened'))
    with pytest.raises(s.CampaignError):
        s.require_split(tmp_path/'plan.json',split)


def test_pending_28_values_are_not_authorization(tmp_path,monkeypatch):
    packet={'rows':s.value_rows()}
    p=tmp_path/'packet.json';s.seal(p,packet)
    monkeypatch.setattr(s,'PACKET',p)
    monkeypatch.setattr(s,'APPROVAL',tmp_path/'absent.json')
    with pytest.raises(s.CampaignError,match='28 synthetic'):
        s.require_owner()
    assert len(s.value_rows())==28


@pytest.mark.parametrize('defect',['ids','packet','verbatim','register'])
def test_partial_approval_fails_closed(defect,tmp_path,monkeypatch):
    packet={'rows':s.value_rows()}
    p=tmp_path/'packet.json';s.seal(p,packet)
    a={'packet_sha256':s.digest(packet),'approved_ids':list(s.PENDING_IDS),
       'status':'EXPLICIT_OWNER_APPROVAL','verbatim_message':'TEST FIXTURE ONLY',
       'source':'TEST FIXTURE ONLY','date':'2000-01-01',
       'scope':'UNCALIBRATED_SYNTHETIC_V1_MEDIUM_HEAVY_PRIMARY_LOW_BOTTLENECK_DIAGNOSTIC'}
    if defect=='ids':a['approved_ids'].pop()
    if defect=='packet':a['packet_sha256']='0'*64
    if defect=='verbatim':a['verbatim_message']=''
    approval=tmp_path/'approval.json';s.seal(approval,a)
    monkeypatch.setattr(s,'PACKET',p);monkeypatch.setattr(s,'APPROVAL',approval)
    with pytest.raises(s.CampaignError):s.require_owner()


def test_dirty_protected_worktree_blocks_lock(monkeypatch):
    monkeypatch.setattr(s,'git',lambda *a:' M integrated-terminal-pilot/src/a.py')
    with pytest.raises(s.CampaignError,match='unclean'):s.assert_clean()


def test_untracked_source_blocks_but_ignored_results_do_not(monkeypatch):
    monkeypatch.setattr(s,'git',lambda *a:'new_source.py' if a[0]=='ls-files' else '')
    with pytest.raises(s.CampaignError):s.assert_clean()
    monkeypatch.setattr(s,'git',lambda *a:'')
    s.assert_clean()


@pytest.mark.parametrize('defect',['hash','source','plan','owner'])
def test_tampered_or_mismatched_lock(defect,tmp_path,monkeypatch):
    path=tmp_path/'protocol_lock_v1.json'
    lock={'schema':'protocol_lock_v1','source_sha256':{'x':'y'},'plan_sha256':'plan',
          'owner_approval_sha256':s.digest({'owner':'fixture'}),'analysis':{},
          'regression_evidence':'not_opened','regression_sha256':'x'}
    if defect=='source':lock['source_sha256']={'x':'changed'}
    if defect=='plan':lock['plan_sha256']='changed'
    if defect=='owner':lock['owner_approval_sha256']='changed'
    path.write_text(json.dumps(lock));path.with_suffix('.json.sha256').write_text(s.file_hash(path))
    if defect=='hash':path.write_text('{}')
    monkeypatch.setattr(s,'FORMAL_LOCK_PATH',path)
    monkeypatch.setattr(s,'assert_clean',lambda:None)
    monkeypatch.setattr(s,'require_owner',lambda:{'owner':'fixture'})
    monkeypatch.setattr(s,'source_manifest',lambda:{'x':'y'})
    monkeypatch.setattr(s,'load_plan',lambda *a:{'analysis_contract':{}})
    with pytest.raises(s.CampaignError):s.verify_lock(tmp_path/'plan.json')


def test_sealed_artifact_tamper_and_atomic_failure(tmp_path,monkeypatch):
    path=tmp_path/'run.json';s.seal(path,{'fixture':1})
    assert s.unseal(path)=={'fixture':1}
    path.write_text('{}')
    with pytest.raises(s.CampaignError,match='checksum'):s.unseal(path)
    from integrated_terminal_pilot.benchmark import step6_closure
    def fail(*a):raise OSError('simulated crash before install')
    monkeypatch.setattr(step6_closure.os,'link',fail)
    with pytest.raises(OSError):s.seal(tmp_path/'partial.json',{})
    assert not (tmp_path/'partial.json').exists()


def test_deterministic_gzip_is_content_verified(tmp_path):
    p=tmp_path/'ledger.gz';a=s.install_gzip(p,iter(['line1\n','line2\n']))
    assert gzip.decompress(p.read_bytes())==b'line1\nline2\n'
    assert s.install_gzip(p,iter(['line1\n','line2\n']))==a
    with pytest.raises(s.CampaignError,match='collision'):s.install_gzip(p,iter(['different']))


def test_stale_lock_archived_live_lock_rejected(tmp_path):
    import psutil
    with s.worker_lock(tmp_path):
        with pytest.raises(s.CampaignError,match='live'):
            with s.worker_lock(tmp_path):pass
    assert not (tmp_path/'worker.lock').exists()
    (tmp_path/'worker.lock').write_text(json.dumps({'pid':psutil.Process().pid,'create_time':-1,
                                                 'host':s.platform.node(),'utc':'fixture'}))
    with s.worker_lock(tmp_path):pass
    assert len(list((tmp_path/'recoveries').glob('*.json')))==2


def test_missing_ppo_seed_never_survivor_averaged():
    from integrated_terminal_pilot.benchmark.step7_report import average_complete_seeds
    rows=[{'training_seed':n,'status':'COMPLETED','N_out':10,'T_end_min':100,
           'turnaround':n,'U':n,'R':n/100} for n in (11,23,37)]
    assert average_complete_seeds(rows)['turnaround']==pytest.approx(71/3)
    assert average_complete_seeds(rows[:2]) is None
    rows[-1]['status']='G_BLOCKED'
    assert average_complete_seeds(rows) is None


@pytest.mark.parametrize('arm',['A1','A1n','B1','A2','B2','B2-T'])
def test_serial_report_instrumentation_does_not_change_policy_or_trace(arm,tmp_path):
    from tests.step6_support import leakage_doc
    from integrated_terminal_pilot.benchmark.runner import run_arm
    doc=leakage_doc()
    baseline=run_arm(doc,arm_id=arm,research_profile=s.PRIMARY_RESEARCH_PROFILE,keep_kernel=True)
    row={'world':'integrated','arm':arm,'ppo_training_seed':None,'row_id':'dev_fixture'}
    recorded=s.execute_episode(doc,row,tmp_path)
    r=recorded['result']
    assert recorded['status']=='COMPLETED'
    assert r['digests']==baseline['digests']
    assert [x['p03_action'] for x in r['policy_decisions']]==[x['p03_action'] for x in baseline['_policy'].records]
    if arm in ('B2','B2-T'):
        assert r['step6']['prediction_digests']==baseline['step6']['prediction_digests']
    assert len(recorded['traces'])==7


def test_serial_reference_retains_full_corresponding_projection_evidence(tmp_path):
    from tests.step6_support import leakage_doc
    doc=leakage_doc()
    row={'world':'reference','arm':'A2','ppo_training_seed':None,'row_id':'dev_fixture'}
    out=s.execute_episode(doc,row,tmp_path)
    r=out['result']['reference']
    assert out['status']=='COMPLETED' and r['vessel_results'] and r['decision_history']
    assert r['total_turnaround_min']==pytest.approx(sum(v['turnaround_time_min'] for v in r['vessel_results']))


def test_status_before_lock_never_opens_sensitive_results(tmp_path,monkeypatch):
    monkeypatch.setattr(s,'load_plan',lambda *a,**k:{'rows':[{}]*1960})
    monkeypatch.setattr(s,'APPROVAL',tmp_path/'absent')
    monkeypatch.setattr(s,'verify_result',lambda *a:pytest.fail('sensitive results'))
    assert s.progress(tmp_path/'plan.json')['not_run']==1960


@pytest.mark.parametrize('status',['COMPLETED','FAILED'])
def test_serial_resume_skips_verified_completion_and_never_retries_failure(status,tmp_path,monkeypatch):
    from tests.step6_support import leakage_doc
    doc=leakage_doc()
    row={'row_id':'dev_fixture','world':'integrated','arm':'A2','ppo_training_seed':None,
         'family':'itp_medium','split':'development','scenario_id':'dev_fixture'}
    scenario={'scenario_id':'dev_fixture','recipe_sha256':'TEST_FIXTURE_ONLY'}
    plan={'rows':[row],'scenarios':[scenario]}
    monkeypatch.setattr(s,'verify_lock',lambda *a:{})
    monkeypatch.setattr(s,'load_plan',lambda *a,**k:plan)
    monkeypatch.setattr(s,'require_split',lambda *a:{})
    monkeypatch.setattr(s,'scenario_input',lambda *a:doc)
    monkeypatch.setattr(s,'runtime',lambda:{'TEST_FIXTURE':True})
    monkeypatch.setattr(s,'FORMAL_LOCK_PATH',tmp_path/'fixture_lock')
    s.FORMAL_LOCK_PATH.write_text('TEST FIXTURE ONLY')
    s.seal(s.scenario_path(tmp_path,scenario),{'document':doc,'recipe_sha256':'TEST_FIXTURE_ONLY'})
    original=s.execute_episode
    calls=[]
    def execute(*args):
        calls.append(1)
        return original(*args) if status=='COMPLETED' else {'status':'FAILED','reason':'controlled fixture','traces':[]}
    monkeypatch.setattr(s,'execute_episode',execute)
    if status=='COMPLETED':
        s.run_campaign(tmp_path/'plan.json')
        s.run_campaign(tmp_path/'plan.json')
    else:
        with pytest.raises(s.CampaignError,match='failed row'):s.run_campaign(tmp_path/'plan.json')
        with pytest.raises(s.CampaignError,match='failed attempt'):s.run_campaign(tmp_path/'plan.json')
    assert calls==[1]
    target=s.run_path(tmp_path,row)
    assert s.unseal(target)['status']==status
    target.write_text('{}')
    with pytest.raises(s.CampaignError,match='checksum'):s.run_campaign(tmp_path/'plan.json')
    assert calls==[1]
