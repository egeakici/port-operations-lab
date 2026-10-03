"""Causal visible-only online rollout and its WAIT decision."""

from dataclasses import replace

import pytest

from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action, run_online_fcfs
from berth_allocation_lab.policies.dynamic_online_rollout import (
    online_rollout_choice, score_visible_action,
)


def fixture(vessels, horizon=240):
    ordered = tuple(sorted((BAPVesselInput(*v) for v in vessels), key=lambda v: v.arrival_time_min))
    return BAPScenarioInstance(
        scenario_id="rollout_fixture", scenario_version=1, scenario_family="test",
        formulation="dynamic", data_provenance="synthetic", split="test", seed=2,
        generator_version="synthetic_v1", scenario_schema_version=1,
        berth_length_m=100, min_clearance_m=0, nominal_duration_min=ordered[-1].arrival_time_min,
        arrival_generation_end_min=ordered[-1].arrival_time_min, vessels=ordered,
        future_horizon_min=horizon,
    )


def test_wait_fixture_exact_scores_and_complete_schedules():
    instance = fixture((("A", 0, 60, 100), ("B", 10, 100, 10)))
    env = DynamicBAPEnv(scenario=instance, max_vessels=2)
    env.reset()
    visible = env.visible_state()
    assert visible.wait_legal
    assert {v.vessel_id for v in visible.vessels_by_slot} == {"A", "B"}
    decision = online_rollout_choice(visible)
    assert decision.action == 0
    assert dict(decision.scores)[0] == pytest.approx(20)
    assert all(score == pytest.approx(90) for action, score in decision.scores if action != 0)
    _, fcfs_reward, _ = run_online_fcfs(DynamicBAPEnv(scenario=instance, max_vessels=2))
    assert fcfs_reward == pytest.approx(-90)
    env.step(decision.action)
    env.step(online_rollout_choice(env.visible_state()).action)
    while not env.terminated:
        env.step(online_fcfs_action(env))
    assert env.episode_return == pytest.approx(-20)


def test_visible_fcfs_continuation_reproduces_environment():
    instance = fixture((("A", 0, 60, 100), ("B", 10, 100, 10)))
    env = DynamicBAPEnv(scenario=instance, max_vessels=2)
    env.reset()
    choice = online_fcfs_action(env)
    predicted = score_visible_action(env.visible_state(), choice)
    _, actual_reward, _ = run_online_fcfs(env)
    assert predicted == pytest.approx(-actual_reward)


@pytest.mark.parametrize("horizon", [0, 240])
def test_rollout_does_not_read_hidden_future(horizon):
    base = fixture((("A", 0, 60, 100), ("B", 10, 30, 10)), horizon=horizon)
    other = replace(base, vessels=(*base.vessels, BAPVesselInput("V", 500, 100, 10)),
                    nominal_duration_min=500, arrival_generation_end_min=500)
    left, right = (DynamicBAPEnv(scenario=s, max_vessels=3) for s in (base, other))
    left.reset()
    right.reset()
    assert left.visible_state() == right.visible_state()
    assert online_rollout_choice(left.visible_state()).action == online_rollout_choice(right.visible_state()).action
