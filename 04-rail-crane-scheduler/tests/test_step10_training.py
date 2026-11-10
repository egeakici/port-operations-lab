from dataclasses import replace
import json
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.training import *


def config():
    # API smoke values only. No call to learn() in this test suite.
    return TrainingConfig(TRAINER_VERSION,(11,23),4,40,1.,1.,16,8,4,1,.001,1.,.95,.2,0.,.5,.5,(8,),8,'cpu',False)


def test_untrained_model_mask_save_reload_and_corruption(tmp_path):
    c=config(); env=make_env(fixture(),c); obs,_=env.reset(seed=11)
    model=make_model(env,c,11)
    action,_=model.predict(obs,deterministic=True,action_masks=env.action_masks())
    assert env.action_masks()[int(action)] and model.num_timesteps==0
    path=tmp_path/'untrained'; data=save_checkpoint(model,path,c,env,seed=11,label='SMOKE_UNTRAINED_NOT_RESEARCH')
    loaded,metadata=load_checkpoint(path,c,env,expected_seed=11)
    other,_=loaded.predict(obs,deterministic=True,action_masks=env.action_masks())
    assert int(action)==int(other) and data['trained_steps']==0
    with pytest.raises(ContractError): load_checkpoint(path,c,env,require_trained=True)
    with pytest.raises(ContractError): save_checkpoint(model,path,c,env,seed=11,label='x')
    with pytest.raises(ContractError): load_checkpoint(path,replace(c,task_capacity=5),env)
    with (path/'model.zip').open('ab') as stream: stream.write(b'corrupt')
    with pytest.raises(ContractError): load_checkpoint(path,c,env)


def test_selection_splits_and_guard():
    assert selection_key({'success_rate':1.,'mean_valid_makespan_min':20.},5)<selection_key({'success_rate':.5,'mean_valid_makespan_min':1.},5)
    with pytest.raises(ContractError): replace(config(),gamma=.99)
    with pytest.raises(ContractError): train_manual({},'absent','wrong','unused')
    class NeverPredict:
        def predict(self,*a,**k): pytest.fail('must reject test input before inference')
    p=replace(fixture(),metadata=replace(fixture().metadata,role='test'))
    with pytest.raises(ContractError): validate_model(NeverPredict(),[p],config())


def test_rng_roundtrip_and_no_implicit_cuda():
    import torch
    state=_rng_state() if '_rng_state' in globals() else __import__('rail_crane_scheduler.training',fromlist=['_rng_state'])._rng_state()
    first=random.random(); restore_rng(state); assert random.random()==first
    if not torch.cuda.is_available():
        with pytest.raises(ContractError): resolve_device(replace(config(),device='cuda'))
        assert resolve_device(replace(config(),device='cuda',permit_cpu_fallback=True))=='cpu'
