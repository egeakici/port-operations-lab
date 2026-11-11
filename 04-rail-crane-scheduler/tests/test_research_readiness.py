"""Engineering-only fixtures. No primary generation, optimizer or held-out run."""
from dataclasses import replace
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import pytest
from test_step02_contracts import fixture
from test_step03_generator import config as generator_config
from test_step10_training import config as training_config
from rail_crane_scheduler.contracts import *
from rail_crane_scheduler.readiness import PROJECT,proposed_profile,validate_profile,generator_configs,environment
from rail_crane_scheduler.campaign import Campaign,commit_files,verify_files,immutable_json,checkpoint_boundaries
from rail_crane_scheduler.progress import Progress


@pytest.fixture
def proposal(tmp_path):
    p=proposed_profile()
    path=tmp_path/'candidate.json'; path.write_bytes(canonical(p))
    return p,path,Campaign(path,workdir=tmp_path/'campaign')


def test_actual_isolated_environment_and_tensor():
    result=environment()
    assert result['status']=='VERIFIED' and result['selected_device']=='cpu'
    assert result['cpu_tensor_verified'] and result['identity']['packages']['ortools']=='9.12.4544'
    assert Path(result['executable']).resolve()==Path(sys.executable).resolve()


def test_candidate_is_fully_explicit_without_primary_generation(proposal):
    profile,path,c=proposal
    result=validate_profile(profile)
    configs=list(generator_configs(profile))
    assert result['scenario_configs_validated']==896 and result['primary_scenarios_generated']==0
    assert {r:sum(x.template.metadata.role==r for x in configs) for r in profile['cohorts']}=={'train':512,'validation':128,'test':256}
    assert all(x.template.tasks==() and x.template.metadata.origin=='PROPOSED_SYNTHETIC' for x in configs)
    assert max(x.task_count for x in configs)==32 and len({x.template.metadata.seed for x in configs})==896
    assert not c.work.exists() and not c.approval.exists()


def test_generation_plan_is_idempotent_and_unapproved_run_rejected(proposal):
    p,path,c=proposal
    result=c.prepare('generation')
    assert c.prepare('generation')==result
    before=c.plan_path('generation').read_bytes()
    with pytest.raises((OSError,ContractError)): c.generate()
    assert c.plan_path('generation').read_bytes()==before
    assert not (c.work/'generation').exists() and not c.approval.exists()


def test_profile_source_and_environment_changes_reject(proposal):
    p,path,c=proposal
    changed=copy.deepcopy(p); changed['source_sha256']={}
    with pytest.raises(ContractError,match='SOURCE_CHANGED'): validate_profile(changed)
    changed=copy.deepcopy(p); changed['environment_lock_sha256']='0'*64
    with pytest.raises(ContractError,match='ENVIRONMENT_CHANGED'): validate_profile(changed)


def test_exact_root_derivation_in_memory_only(proposal):
    # This is an in-memory schema fixture, not a persisted owner approval.
    from rail_crane_scheduler.campaign import verify_derived_plan
    p,path,c=proposal; payload=c.build_plan('generation')
    receipt={'status':'OWNER_APPROVED','approved_payload_sha256':digest(p),'owner_evidence':'IN_MEMORY_UNIT_TEST_ONLY_NOT_OWNER_AUTHORIZATION'}
    verify_derived_plan(payload,receipt)
    bad=copy.deepcopy(payload); bad['configs'][0]['max_moves']+=1
    with pytest.raises(ContractError,match='PLAN_DERIVATION'): verify_derived_plan(bad,receipt)
    bad=copy.deepcopy(payload); bad['campaign']['operation']='training'
    with pytest.raises((OSError,ContractError)): verify_derived_plan(bad,receipt)
    with pytest.raises(ContractError): verify_derived_plan(payload,{**receipt,'approved_payload_sha256':'0'*64})
    assert not c.approval.exists()


@pytest.mark.parametrize('operation',['training','baselines','evaluation'])
def test_future_plan_requires_actual_frozen_inputs_and_selections(proposal,operation):
    p,path,c=proposal
    with pytest.raises((OSError,ContractError)): c.prepare(operation)
    assert not c.plan_path(operation).exists()


def test_commit_boundaries_are_atomic_and_hash_verified(tmp_path):
    cell=tmp_path/'cell'; commit_files(cell,{'data.json':b'{"fixture":true}'})
    assert set(verify_files(cell)['files'])=={'data.json'}
    with pytest.raises(ContractError): commit_files(cell,{'data.json':b'changed'})
    (cell/'data.json').write_bytes(b'changed')
    with pytest.raises(ContractError,match='CELL_HASH'): verify_files(cell)


def test_partial_checkpoint_is_never_a_resume_boundary(tmp_path):
    base=tmp_path/'attempt_0001/seed_11'
    partial=base/'checkpoint_000000000008.partial_not_committed'; partial.mkdir(parents=True)
    (partial/'metadata.json').write_text('{}')
    assert checkpoint_boundaries(tmp_path)==[]
    valid=base/'checkpoint_000000000008'; valid.mkdir(); (valid/'metadata.json').write_text('{}')
    assert checkpoint_boundaries(tmp_path)==[valid/'metadata.json']


def test_immutable_plan_rejects_change(tmp_path):
    path=tmp_path/'plan.json'; immutable_json(path,{'fixture':1})
    immutable_json(path,{'fixture':1})
    with pytest.raises(ContractError): immutable_json(path,{'fixture':2})


def test_real_fixture_generation_progress_and_json_stderr(tmp_path,capsys):
    from rail_crane_scheduler.scenarios import write_fixture_batch
    c=generator_config(); other=replace(c,template=replace(c.template,metadata=replace(c.template.metadata,seed=999)))
    out=tmp_path/'batch'; manifests=write_fixture_batch([c,other],out)
    lines=[json.loads(x) for x in (out/'progress.jsonl').read_text().splitlines()]
    assert len(manifests)==2 and lines[-1]['completed']==lines[-1]['total']==2
    assert all(m['origin']=='TEST_FIXTURE_SYNTHETIC' for m in manifests)
    captured=capsys.readouterr()
    assert captured.out=='' and 'Fixture generation' in captured.err and '100%' in captured.err
    with pytest.raises(ContractError): write_fixture_batch([c]*9,tmp_path/'too_large')


def test_ctrl_c_retains_completed_progress_and_cells(tmp_path):
    out=tmp_path/'interrupted'
    with pytest.raises(KeyboardInterrupt):
        with Progress(2,'Fixture interrupt',out) as progress:
            progress.start(method='in_flight_fixture')
            assert progress.completed==0
            commit_files(out/'first',{'fixture.json':b'{}'})
            progress.advance(failures=0)
            raise KeyboardInterrupt
    assert verify_files(out/'first')
    state=json.loads((out/'progress.jsonl').read_text().splitlines()[-1])
    assert state['event']=='INTERRUPTED' and state['completed']==1 and state['total']==2


def test_timestep_callback_on_real_fixture_steps_without_optimizer(tmp_path):
    from rail_crane_scheduler.training import make_model,make_env,timestep_callback_class
    c=training_config(); env=make_env(fixture(),c); model=make_model(env,c,c.seeds[0]); obs,_=env.reset(seed=11)
    with Progress(c.total_steps,'Fixture callback',tmp_path,unit='step') as progress:
        callback=timestep_callback_class(progress,c,11)(); callback.init_callback(model)
        for step in range(1,3):
            action,_=model.predict(obs,deterministic=True,action_masks=env.action_masks())
            obs,_,done,truncated,_=env.step(int(action))
            model.num_timesteps=step # callback receives actual completed fixture decisions
            assert callback.on_step()
            if done or truncated: break
        assert progress.completed==model.num_timesteps and model._n_updates==0
        progress.record('FIXTURE_ONLY_ZERO_OPTIMIZER_UPDATES',optimizer_updates=model._n_updates)
    assert not list(tmp_path.rglob('model.zip'))


def test_all_failed_selection_has_finite_canonical_key():
    from rail_crane_scheduler.training import selection_key
    key=selection_key({'success_rate':0.,'mean_valid_makespan_min':None},8)
    assert canonical(key)
    assert key>selection_key({'success_rate':.5,'mean_valid_makespan_min':999.},8)


def test_resume_verification_does_not_reseed_training_rng(tmp_path):
    from rail_crane_scheduler.training import make_model,make_env,save_checkpoint,verify_checkpoint_preserving_rng,_rng_state
    import random
    import numpy as np
    import torch
    c=training_config(); env=make_env(fixture(),c); model=make_model(env,c,11)
    checkpoint=tmp_path/'untrained_rng_check'
    save_checkpoint(model,checkpoint,c,env,seed=11,label='SMOKE_UNTRAINED_NOT_RESEARCH')
    random.seed(999); np.random.seed(999); torch.manual_seed(999)
    before=_rng_state()
    data=verify_checkpoint_preserving_rng(checkpoint,c,env,expected_seed=11)
    assert _rng_state()==before and data['optimizer_updates']==0
    with pytest.raises(ContractError): verify_checkpoint_preserving_rng(checkpoint,c,env,require_trained=True)
    assert _rng_state()==before
    sidecar=json.loads((checkpoint/'metadata.json').read_text()); sidecar['trained_steps']=1
    (checkpoint/'metadata.json').write_bytes(canonical(sidecar))
    with pytest.raises(ContractError,match='CHECKPOINT_STATE'):
        verify_checkpoint_preserving_rng(checkpoint,c,env)
    assert _rng_state()==before


def test_cp_budget_timeout_does_not_claim_infeasibility():
    from rail_crane_scheduler.cpsat import solve
    result=solve(fixture(),tick_min=1.,wall_limit_s=1e-12,max_nodes=1000)
    assert result.status=='TIMEOUT' and result.schedule is None and result.bound_min is None


def test_cp_unsupported_and_no_path_statuses():
    from rail_crane_scheduler.cpsat import solve
    p=fixture(); p=replace(p,cranes=(replace(p.cranes[0],reach_upper_m=1.),replace(p.cranes[1],reach_lower_m=19.)))
    r=solve(p,tick_min=1.,wall_limit_s=5.,max_nodes=1000)
    assert r.status=='INFEASIBLE' and r.schedule is None
    r=solve(fixture(),tick_min=.7,wall_limit_s=5.,max_nodes=1000)
    assert r.status=='UNSUPPORTED_FORMULATION' and r.bound_min is None


def test_fractional_cp_certificate_respects_declared_numeric_precision():
    from rail_crane_scheduler.evaluation import certified_gap
    from rail_crane_scheduler.cpsat import FORMULATION
    ref={'solver_status':'OPTIMAL','valid_complete':True,'solver_formulation':FORMULATION,'problem_hash':'fixture',
         'solver_bound_min':60.53333333333333,'makespan_min':60.53333333333334,'numeric_time_tolerance_min':1e-8}
    assert certified_gap({'problem_hash':'fixture','valid_complete':True,'makespan_min':60.53333333333333},ref)==0.
    with pytest.raises(ContractError): certified_gap({'problem_hash':'fixture','valid_complete':True,'makespan_min':58.},ref)
    with pytest.raises(ContractError): certified_gap({'problem_hash':'fixture','valid_complete':True,'makespan_min':70.},{**ref,'solver_bound_min':59.})


def test_report_nested_bootstrap_uses_all_submitted_cells(tmp_path):
    from rail_crane_scheduler.statistics_report import infer
    p=proposed_profile(); p['cohorts']['test']['count_per_family']=2
    p['analysis'].update(draws=64,minimum_pairs_per_family=2)
    rows=[]
    refs=p['analysis']['confirmatory_references']
    for family in p['families']:
        for i in range(2):
            for arm in [*refs,*[f'crane_ppo_seed_{s}' for s in p['training_config']['seeds']],'cpsat_finite_dispatch_v1']:
                ppo=arm.startswith('crane_ppo_seed_'); cp=arm.startswith('cpsat_')
                skipped=cp and family!='tiny'
                rows.append({'scenario_id':f'fixture_{family}_{i}','family':family,'policy_id':arm,'valid_complete':not skipped,
                             'makespan_min':None if skipped else 8. if ppo else 10.,'status':'SKIPPED_NOT_ELIGIBLE' if skipped else 'COMPLETED'})
    a=infer(rows,p,tmp_path/'stats')
    assert all(v['n_independent_scenarios']==8 for v in a['contrasts'].values())
    assert all(v['mean_delta_min']==-2 for v in a['contrasts'].values())
    assert all(v['per_contrast_confidence']==.99375 for v in a['contrasts'].values())
    assert a['primary_superiority_supported'] and not a['scientifically_closed']
    failed=copy.deepcopy(rows); failed[4].update(valid_complete=False,makespan_min=None,status='DEADLOCK')
    b=infer(failed,p,tmp_path/'failures')
    assert not b['primary_superiority_supported']
    assert all(v['status']=='INSUFFICIENT_COMPLETE_PAIR_SUPPORT' for v in b['contrasts'].values())
    with pytest.raises(ContractError): infer(rows[:-1],p)


def test_wrapper_help_environment_status_and_rejection(proposal):
    p,path,c=proposal; script=PROJECT/'scripts/Project04.ps1'
    for action in ('Help','ValidateEnvironment'):
        result=subprocess.run(['powershell','-NoProfile','-File',str(script),action],capture_output=True,text=True,timeout=40)
        assert result.returncode==0,result.stdout+result.stderr
        if action=='ValidateEnvironment': assert json.loads(result.stdout)['status']=='VERIFIED'
    for action in ('Status','ValidateProfile','PrepareGeneration'):
        result=subprocess.run(['powershell','-NoProfile','-File',str(script),action,'-Profile',str(path),'-WorkDirectory',str(c.work)],
                              capture_output=True,text=True,timeout=40)
        assert result.returncode==0,result.stdout+result.stderr
        assert isinstance(json.loads(result.stdout),dict)
    result=subprocess.run(['powershell','-NoProfile','-File',str(script),'Generate','-Profile',str(path),'-WorkDirectory',str(c.work)],
                          capture_output=True,text=True,timeout=40)
    assert result.returncode==2 and json.loads(result.stdout)['status']=='REJECTED'
    assert not c.approval.exists() and not (c.work/'generation').exists()


def test_no_approval_recording_without_exact_declaration(proposal,capsys):
    from rail_crane_scheduler.campaign_cli import main
    p,path,c=proposal
    assert main(['RecordApproval','--profile',str(path),'--workdir',str(c.work),'--approval-text','approve'])==2
    assert not c.approval.exists()
