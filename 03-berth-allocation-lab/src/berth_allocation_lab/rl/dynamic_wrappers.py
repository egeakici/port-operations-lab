"""Training-only constant reward scale and terminal scientific identity."""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np

from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.rl.dynamic_config import REWARD_SCALE
from berth_allocation_lab.rl.suites import scenario_identity


class DynamicTrainingRewardScale(gym.Wrapper):
    def __init__(self, env: DynamicBAPEnv) -> None:
        if not isinstance(env.unwrapped, DynamicBAPEnv):
            raise TypeError("DynamicTrainingRewardScale requires DynamicBAPEnv.")
        super().__init__(env)
        self._identity: dict[str, object] = {}

    def reset(self, **kwargs: Any):
        observation, info = self.env.reset(**kwargs)
        self._identity = scenario_identity(self.env.unwrapped._scenario)
        return observation, info

    def step(self, action: Any):
        observation, reward, terminated, truncated, info = self.env.step(action)
        info = {**info, "raw_reward": reward}
        if terminated or truncated:
            info.update(self._identity)
        return observation, reward * REWARD_SCALE, terminated, truncated, info

    def action_masks(self) -> np.ndarray:
        return self.env.unwrapped.action_masks()
