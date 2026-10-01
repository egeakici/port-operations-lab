"""Training-only wrapper: constant reward scale plus raw-unit audit info."""

from __future__ import annotations

import math
from typing import Any

import gymnasium as gym
import numpy as np

from berth_allocation_lab.envs import StaticBAPEnv
from berth_allocation_lab.rl.suites import scenario_identity


class TrainingRewardScale(gym.Wrapper):
    """Multiply rewards by one fixed positive constant for PPO training only.

    With gamma = 1 a constant positive scale preserves the ordering of complete
    episode returns, so the optimal policy set is unchanged; it only changes
    numerical training dynamics. The raw reward is kept in ``info`` and the
    episode's scenario identity is attached to the terminal step's ``info``.
    Evaluation must use an unwrapped StaticBAPEnv and raw vessel-minutes.
    """

    def __init__(self, env: StaticBAPEnv, reward_scale: float) -> None:
        if not isinstance(env.unwrapped, StaticBAPEnv):
            raise TypeError("TrainingRewardScale wraps a StaticBAPEnv.")
        if isinstance(reward_scale, bool) or not math.isfinite(reward_scale) or reward_scale <= 0:
            raise ValueError("reward_scale must be a finite positive constant.")
        super().__init__(env)
        self.reward_scale = float(reward_scale)
        self._identity: dict[str, object] = {}

    def reset(self, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        observation, info = self.env.reset(**kwargs)
        self._identity = scenario_identity(self.env.unwrapped.scenario)
        return observation, info

    def step(self, action: Any) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        observation, reward, terminated, truncated, info = self.env.step(action)
        info = {**info, "raw_reward": reward}
        if terminated or truncated:
            info.update(self._identity)
        return observation, reward * self.reward_scale, terminated, truncated, info

    def action_masks(self) -> np.ndarray:
        return self.env.unwrapped.action_masks()
