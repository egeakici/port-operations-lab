from dataclasses import replace
import copy
import numpy as np
import pytest
from test_step02_contracts import fixture
from rail_crane_scheduler.encoding import *
from rail_crane_scheduler.environment import masked_rollout
from rail_crane_scheduler.contracts import ContractError


def encoded(problem=None):
    return EncodedCraneEnv(problem or fixture(),task_capacity=4,max_steps=40,reward_scale_min=2.,failure_margin_min=1.,invalid_action_mode='raise')


@pytest.mark.parametrize('seed',range(6))
def test_mask_iff_kernel_and_clone_stepping(seed):
    env=encoded(); obs,info=env.reset(seed=seed); rng=np.random.default_rng(seed); total=0.
    for _ in range(40):
        mask=env.action_masks()
        for a in range(env.action_space.n):
            clone=copy.deepcopy(env)
            if mask[a]: clone.step(a)
            else:
                with pytest.raises(ContractError): clone.step(a)
        choices=np.flatnonzero(mask); a=int(rng.choice(choices))
        obs,reward,done,truncated,info=env.step(a); total+=reward
        assert env.observation_space.contains(obs)
        if done or truncated:
            assert done and info['success'] and total==-info['makespan_min']/2
            break
    else: pytest.fail('finite progress failed')


def test_no_seed_or_identity_leak_and_padding():
    p=fixture(); q=replace(p,metadata=replace(p.metadata,seed=999,scenario_id='different'))
    a,_=encoded(p).reset(); b,_=encoded(q).reset()
    assert all(np.array_equal(a[k],b[k]) for k in a)
    assert np.all(a['tasks'][2:]==0) and a['task_mask'].tolist()==[1,1,0,0]
    e=encoded(); e.reset(); assert not e.action_masks()[3] and not e.action_masks()[4]
    assert interface_candidate(e)['status']=='PENDING_OWNER_APPROVAL'


def test_reward_failure_bound():
    e=EncodedCraneEnv(fixture(),task_capacity=4,max_steps=1,reward_scale_min=2.,failure_margin_min=1.,invalid_action_mode='truncate')
    e.reset(); _,r,term,trunc,info=e.step(1)
    assert trunc and not term and r < -fixture().rail.horizon_min/2 and not info['success']
