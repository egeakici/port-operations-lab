"""OWNER-RUN bounded tests for transport, gating, nesting and immutable resume."""
import json
from pathlib import Path
import threading

import pytest

from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark.step7_inputs import safe_path,normalized_sha


@pytest.mark.parametrize('bad',['../escape','/absolute','C:/absolute','a\\b','a/../../escape'])
def test_transport_rejects_path_escape(tmp_path,bad):
    with pytest.raises(s.CampaignError):safe_path(tmp_path,bad)


def test_only_line_endings_are_equivalent(tmp_path):
    a=tmp_path/'a.py';b=tmp_path/'b.py'
    a.write_bytes(b'x = 1\r\n');b.write_bytes(b'x = 1\n')
    assert s.file_hash(a)!=s.file_hash(b) and normalized_sha(a)==normalized_sha(b)
    b.write_bytes(b'x = 2\n')
    assert normalized_sha(a)!=normalized_sha(b)


def test_configuring_bundle_is_not_permission(monkeypatch,tmp_path):
    from integrated_terminal_pilot.benchmark.step7_workspace import configure
    for name in ('ROOT','APPROVAL','FORMAL_LOCK_PATH','load_generator_config'):
        monkeypatch.setattr(s,name,getattr(s,name))
    monkeypatch.setattr(s,'PORTABLE_BUNDLE',None,raising=False)
    monkeypatch.setattr(s,'PROJECT_ROOT',tmp_path)
    root=tmp_path/'experiments/step7_remote/fixture'
    configure(root)
    assert s.FORMAL_LOCK_PATH==root/'protocol_lock_v1.json'
    with pytest.raises(s.CampaignError):s.require_owner()
    assert not root.exists()


def test_failed_regression_is_never_retried(monkeypatch,tmp_path):
    from integrated_terminal_pilot.benchmark import step7_remote as remote
    p=tmp_path/'regressions/project-i-full_fixture/result.json';p.parent.mkdir(parents=True);p.write_text('{}')
    monkeypatch.setattr(s,'unseal',lambda p:{'implementation_digest':'fixture','exit_code':1})
    monkeypatch.setattr(s,'implementation_digest',lambda:'fixture')
    monkeypatch.setattr(remote,'child',lambda *a:pytest.fail('failed attempt retried'))
    with pytest.raises(s.CampaignError,match='no automatic retry'):
        remote.regression(tmp_path,'project-i-full',threading.Event())


def test_corrupt_return_fails_before_source_or_policy_access(monkeypatch,tmp_path):
    from integrated_terminal_pilot.benchmark import step7_remote as remote
    (tmp_path/'payload').write_bytes(b'corrupt')
    monkeypatch.setattr(remote,'configure',lambda p:p)
    monkeypatch.setattr(s,'unseal',lambda p:{'schema':'step7_transfer_manifest_v1',
        'files':{'payload':{'sha256':'0'*64,'bytes':7}}})
    monkeypatch.setattr(s,'verify_lock',lambda *a:pytest.fail('execution verification invoked during return audit'))
    with pytest.raises(s.CampaignError,match='corrupted'):remote.verify_return(tmp_path)


def seed_rows(missing=False):
    result=[]
    for world,arms in [('integrated',{'A1':100,'A2':80}),('reference',{'A1':70,'A2':60})]:
        for arm,value in arms.items():
            result.append(dict(scenario_id='fixture',world=world,arm=arm,training_seed=None,
                status='COMPLETED',family='itp_medium',split='validation',N_out=10,T_end_min=1000,
                turnaround=value,U=3,R=.3))
        for seed,value,u in zip((11,23,37),(90,60,30) if world=='integrated' else (50,40,30),(3,0,0)):
            if missing and seed==37:continue
            result.append(dict(scenario_id='fixture',world=world,arm='A3',training_seed=seed,
                status='COMPLETED',family='itp_medium',split='validation',N_out=10,T_end_min=1000,
                turnaround=value,U=u,R=u/10))
    return result


def test_a3_nested_pairs_and_reference_difference_in_differences():
    from integrated_terminal_pilot.benchmark.step7_report import descriptive_pairs
    pairs,s1,averages=descriptive_pairs(seed_rows())
    p=next(x for x in pairs if x['contrast']=='A3-A1')
    assert p['turnaround_delta_min']==-40 and p['U_delta']==-2
    d=next(x for x in s1 if x['contrast']=='A3-A1')
    assert d['difference_in_differences_min']==-10 and len(averages)==2


def test_missing_a3_seed_cannot_create_a_survivor_average():
    from integrated_terminal_pilot.benchmark.step7_report import descriptive_pairs
    pairs,s1,averages=descriptive_pairs(seed_rows(missing=True))
    assert not averages and all('A3' not in p['contrast'] for p in pairs+s1)


def test_csv_install_is_idempotent_and_no_overwrite(tmp_path):
    from integrated_terminal_pilot.benchmark.step7_report import write_csv
    p=tmp_path/'table.csv'
    write_csv(p,[{'x':1}]);write_csv(p,[{'x':1}])
    with pytest.raises(s.CampaignError):write_csv(p,[{'x':2}])


def test_missing_profile_is_explicit_not_inferred_from_episode_counts(tmp_path):
    from integrated_terminal_pilot.benchmark.step7_export import profile_summary
    s.seal(tmp_path/'profiles/interrupted/started.json',{'split':'validation','rows_existing_before':[]})
    result=profile_summary(tmp_path)
    assert result['incomplete_profile_invocations']==1
    assert result['invocations'][0]['status']=='PROFILE_UNAVAILABLE'
    assert result['profiled_row_ids']==[]


def test_presentation_keeps_cargo_turnaround_tradeoff_and_zero_ties_separate():
    from integrated_terminal_pilot.benchmark.step7_export import presentation
    report={'paired_descriptive_contrasts':[
        dict(contrast='B2-A2',split='test',family='itp_medium',turnaround_delta_min=10,
             turnaround_delta_percent=5,U_delta=-2,R_delta=-.1),
        dict(contrast='B2-A2',split='test',family='itp_heavy',turnaround_delta_min=0,
             turnaround_delta_percent=0,U_delta=0,R_delta=0)]}
    text,claims=presentation(report)
    lookup={r['family']:r for r in claims}
    assert lookup['itp_medium']['descriptive_direction']=='CARGO_ONLY'
    assert lookup['itp_heavy']['descriptive_direction']=='NEITHER_STRICTLY_IMPROVES'
    assert 'Descriptive results only' in text and 'Step8' in text
