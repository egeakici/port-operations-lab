"""Minimal online FCFS policy for DynamicBAP environment validation."""

from __future__ import annotations

from berth_allocation_lab.envs.dynamic_bap_env import DynamicBAPEnv


def online_fcfs_action(env: DynamicBAPEnv) -> int:
    """Pick earliest-arrived eligible vessel, then lowest feasible position."""
    choices = env.legal_choices
    if not choices:
        raise ValueError("No immediate legal assignment is available.")
    return min(choices, key=lambda item: (item[4], item[1], item[3]))[0]


def run_online_fcfs(env: DynamicBAPEnv, *, seed: int | None = None):
    """Run a complete episode using only public online choices and observations."""
    observation, info = env.reset(seed=seed)
    total_reward = 0.0
    while not env.terminated and not env.truncated:
        action = online_fcfs_action(env)
        observation, reward, _, _, info = env.step(action)
        total_reward += reward
    return observation, total_reward, info
