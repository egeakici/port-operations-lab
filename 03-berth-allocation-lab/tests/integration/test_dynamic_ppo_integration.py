"""Short real MaskablePPO integration over event-driven DynamicBAPEnv."""

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.rl.dynamic_joint_scoring import DynamicJointMaskablePolicy
from berth_allocation_lab.rl.dynamic_checkpoint import load_dynamic_checkpoint, save_dynamic_checkpoint
from berth_allocation_lab.rl.policy import CheckpointCompatibilityError
import pytest


def tiny_env():
    vessels = (BAPVesselInput("A", 0, 60, 100), BAPVesselInput("B", 10, 100, 10))
    scenario = BAPScenarioInstance(
        scenario_id="dynamic_rl_smoke", scenario_version=1, scenario_family="tiny",
        formulation="dynamic", data_provenance="synthetic", split="train", seed=0,
        generator_version="synthetic_v1", scenario_schema_version=1,
        berth_length_m=100, min_clearance_m=0, nominal_duration_min=10,
        arrival_generation_end_min=10, vessels=vessels, future_horizon_min=240,
    )
    return DynamicBAPEnv(scenario=scenario, max_vessels=2)


def test_masked_training_prediction_save_load(tmp_path):
    torch.set_num_threads(1)
    env = tiny_env()
    model = MaskablePPO(DynamicJointMaskablePolicy, env, gamma=1.0,
                        n_steps=16, batch_size=16, n_epochs=1, seed=11, device="cpu")
    before = {k: v.detach().clone() for k, v in model.policy.scoring_network.state_dict().items()}
    model.learn(total_timesteps=16, use_masking=True)
    after = model.policy.scoring_network.state_dict()
    assert any(not torch.equal(before[k], after[k]) for k in before)
    observation, _ = env.reset(seed=11)
    mask = env.action_masks()
    action, _ = model.predict(observation, deterministic=True, action_masks=mask)
    assert mask[int(action)]
    path = tmp_path / "dynamic_model.zip"
    model.save(path)
    loaded = MaskablePPO.load(path, env=env, device="cpu")
    loaded_action, _ = loaded.predict(observation, deterministic=True, action_masks=mask)
    assert int(action) == int(loaded_action)
    typed_path = tmp_path / "typed_dynamic.zip"
    save_dynamic_checkpoint(model, typed_path, {
        "max_vessels": 2, "horizon_min": 240.0, "time_scale_min": 1440.0,
        "length_scale_m": 1000.0, "training_seed": 11})
    typed, _ = load_dynamic_checkpoint(typed_path, env)
    typed_action, _ = typed.predict(observation, deterministic=True, action_masks=mask)
    assert int(action) == int(typed_action)
    other_horizon = tiny_env()
    other_horizon._horizon_override = 0.0
    other_horizon.reset()
    with pytest.raises(CheckpointCompatibilityError, match="H differs"):
        load_dynamic_checkpoint(typed_path, other_horizon)
    cross_horizon, _ = load_dynamic_checkpoint(typed_path, other_horizon,
                                               allow_cross_horizon=True)
    cross_observation, _ = other_horizon.reset()
    cross_action, _ = cross_horizon.predict(cross_observation, deterministic=True,
                                            action_masks=other_horizon.action_masks())
    assert other_horizon.action_masks()[int(cross_action)]
    while not env.terminated and not env.truncated:
        action, _ = loaded.predict(observation, deterministic=True, action_masks=env.action_masks())
        observation, _, _, _, _ = env.step(int(action))
    assert env.terminated and not env.truncated
    assert env.episode_return == -env._info()["total_waiting_time_min"]
