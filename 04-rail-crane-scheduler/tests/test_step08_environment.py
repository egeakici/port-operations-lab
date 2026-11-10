from dataclasses import replace
import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env
from test_step02_contracts import fixture
from rail_crane_scheduler.environment import *


def env_for(problem=None,**overrides):
    args=dict(task_capacity=4,max_steps=30,reward_scale_min=1.,failure_margin_min=1.,invalid_action_mode='truncate')
    args.update(overrides)
    return CraneSchedulingEnv(problem or fixture(),**args)


def test_actual_gymnasium_checker():
    # Gymnasium's checker samples unmasked actions and forbids a first-step
    # truncation. This masked-action domain rejects invalid actions by design.
    # Adapt random sampling, not step semantics or any checker assertion.
    env=env_for(task_capacity=2)
    env.reset(seed=0)
    reset_mask=env.action_masks().astype(np.int8)
    class LegalSamplingDiscrete(gym.spaces.Discrete):
        def sample(self,mask=None,probability=None):
            # check_step_determinism samples BEFORE reset (installed 1.2.3).
            # Its action must be valid in the reset state, not the prior state.
            if mask is None: mask=reset_mask
            return super().sample(mask=mask,probability=probability)
    env.action_space=LegalSamplingDiscrete(env.action_space.n)
    check_env(env,skip_render_check=True)


def test_reset_immutability_and_reward():
    env=env_for(); a,info=env.reset(seed=7); a['cranes'][0,0]=999
    b,info=env.reset(seed=7); assert b['cranes'][0,0]==0
    result,info=masked_rollout(env,7)
    assert info['success'] and result==-info['makespan_min']
    assert env.render().endswith('completed 2/2')


def test_invalid_action_truncates_without_mutation():
    env=env_for(); env.reset(); before=env.kernel.observation()
    _,reward,terminated,truncated,info=env.step(0)
    assert not terminated and truncated and not info['success'] and reward==-101
    assert env.kernel.observation()==before
    with pytest.raises(ContractError): env.step(1)
    env=env_for(invalid_action_mode='raise'); env.reset()
    with pytest.raises(ContractError): env.step(0)


def test_truncation_overflow_deadlock_and_repeatability():
    p=fixture()
    with pytest.raises(ContractError): env_for(task_capacity=1)
    dead=replace(p,cranes=(replace(p.cranes[0],reach_upper_m=1.),replace(p.cranes[1],reach_lower_m=19.)))
    with pytest.raises(ContractError): env_for(dead).reset()
    e=env_for(max_steps=1); e.reset(); _,_,term,trunc,info=e.step(1)
    assert trunc and not term and not info['success']
    a=masked_rollout(env_for(),11); b=masked_rollout(env_for(),11); assert a==b
