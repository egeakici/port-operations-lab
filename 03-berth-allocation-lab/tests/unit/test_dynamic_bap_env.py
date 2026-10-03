"""Hand-worked online physics, causality and Gymnasium contract tests."""

from dataclasses import replace

import numpy as np
import pytest

from berth_allocation_lab.core import candidate_positions, total_waiting_time
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.envs import DynamicBAPEnv, StaticBAPEnv
from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action, run_online_fcfs


def scenario(*items, quay=100.0, clearance=0.0, horizon=0.0, drain=1000.0):
    vessels = tuple(BAPVesselInput(*item) for item in sorted(items, key=lambda v: v[1]))
    return BAPScenarioInstance(
        scenario_id="fixture", scenario_version=1, scenario_family="test",
        formulation="dynamic", data_provenance="synthetic", split="test", seed=2,
        generator_version="synthetic_v1", scenario_schema_version=1,
        berth_length_m=quay, min_clearance_m=clearance,
        nominal_duration_min=max(v.arrival_time_min for v in vessels),
        arrival_generation_end_min=max(v.arrival_time_min for v in vessels),
        vessels=vessels, future_horizon_min=horizon, termination_mode="drain",
        max_drain_extension_min=drain,
    )


def assert_complete(env, expected_wait, expected_end):
    assert env.terminated and not env.truncated
    assert env.current_time_min == pytest.approx(expected_end)
    assert total_waiting_time(env._scenario.vessels, env.placements) == pytest.approx(expected_wait)
    assert env.episode_return == pytest.approx(-expected_wait)
    assert sum(r["reward"] for r in env.decision_records) == pytest.approx(-expected_wait)


def test_a_immediate_and_f_no_future_wait():
    env = DynamicBAPEnv(scenario=scenario(("A", 0, 100, 10)), max_vessels=2)
    obs, _ = env.reset(seed=3)
    assert env.observation_space.contains(obs)
    assert env.action_masks()[0] == 0
    assert env.action_space.n == 1 + 2 * 4
    _, reward, done, truncated, _ = env.step(online_fcfs_action(env))
    assert reward == 0 and done and not truncated
    assert_complete(env, 0, 10)


def test_b_single_queue_and_i_completed_vessel_does_not_block():
    s = scenario(("A", 0, 100, 20), ("B", 10, 100, 5))
    env = DynamicBAPEnv(scenario=s, max_vessels=2)
    _, total, _ = run_online_fcfs(env)
    assert total == pytest.approx(-10)
    assert_complete(env, 10, 25)
    assert env.placements[1].berth_position_m == 0
    assert env.placements[1].berth_start_time_min == 20
    assert env.event_records[1]["event_type"] == "ASSIGNMENT"
    assert any(r["transition_type"] == "automatic_advance" for r in env.event_records)
    assert not any(r["transition_type"] == "agent_wait" for r in env.event_records)


def test_i_completed_vessel_creates_no_dynamic_candidates():
    s = scenario(("A", 0, 30, 10), ("B", 10, 20, 5), quay=100, clearance=5)
    env = DynamicBAPEnv(scenario=s, max_vessels=2)
    env.reset()
    env.step(online_fcfs_action(env))
    assert env.current_time_min == 10
    assert [item[3] for item in env.legal_choices] == [0, 80]
    assert candidate_positions(s.vessels[1], env.placements, 100, 5) == (0, 35, 80)


def test_c_simultaneous_arrivals_and_g_drain():
    env = DynamicBAPEnv(scenario=scenario(("B", 0, 40, 10), ("A", 0, 40, 20)),
                        max_vessels=2)
    env.reset()
    assert [r["vessel_id"] for r in env.event_records[:2]] == ["A", "B"]
    env.step(online_fcfs_action(env))
    assert env.current_time_min == 0
    env.step(online_fcfs_action(env))
    assert_complete(env, 0, 20)
    assert [p.berth_start_time_min for p in env.placements] == [0, 0]


def test_d_wait_and_h_announcement_cost():
    env = DynamicBAPEnv(scenario=scenario(("A", 0, 100, 10), ("B", 100, 100, 10),
                                          horizon=60), max_vessels=2)
    obs, _ = env.reset()
    assert obs["visible_mask"].sum() == 1
    assert env.action_masks()[0]
    obs, reward, done, _, _ = env.step(0)
    assert env.current_time_min == 40 and reward == pytest.approx(-40)
    assert obs["status_features"][1, 0] == 1
    assert not any(choice[1] == "B" for choice in env.legal_choices)
    assert env.event_records[-1]["event_type"] == "HORIZON_ENTRY"
    env.step(online_fcfs_action(env))
    assert env.placements[0].berth_start_time_min == 40  # no backdating to arrival at 0
    assert env.current_time_min == 100
    env.step(online_fcfs_action(env))
    assert_complete(env, 40, 110)


def test_e_variable_lengths_and_candidate_cache():
    env = DynamicBAPEnv(scenario=scenario(("A", 0, 40, 20), ("B", 0, 30, 10),
                                          ("C", 0, 20, 5), quay=100, clearance=5),
                        max_vessels=3)
    obs, _ = env.reset()
    before = env.action_masks()
    before[:] = False
    assert env.action_masks().any()
    assert env.observation_space.contains(obs)
    _, total, info = run_online_fcfs(env)
    assert total == 0 and info["schedule_valid"]
    assert_complete(env, 0, 20)


def test_multi_queue_wait_and_partial_release():
    env = DynamicBAPEnv(scenario=scenario(("A", 0, 100, 10), ("B", 0, 100, 10),
                                          ("C", 5, 100, 10)), max_vessels=3)
    env.reset()
    _, first_reward, _, _, _ = env.step(online_fcfs_action(env))
    assert first_reward == pytest.approx(-15)
    _, reward, _, _, _ = env.step(online_fcfs_action(env))
    assert reward == pytest.approx(-10)  # C waits another 10 minutes after B starts.
    env.step(online_fcfs_action(env))
    assert_complete(env, 25, 30)


def test_two_waiting_vessels_for_ten_minutes_cost_twenty():
    env = DynamicBAPEnv(scenario=scenario(("A", 0, 100, 20), ("B", 10, 100, 5),
                                          ("C", 10, 100, 5)), max_vessels=3)
    env.reset()
    _, first_reward, _, _, _ = env.step(online_fcfs_action(env))
    assert first_reward == pytest.approx(-20)
    assert env.current_time_min == 20
    env.step(online_fcfs_action(env))
    env.step(online_fcfs_action(env))
    assert_complete(env, 25, 30)


def test_invalid_actions_are_atomic_and_terminal_observation_valid():
    env = DynamicBAPEnv(scenario=scenario(("A", 0, 100, 10)), max_vessels=2)
    obs, _ = env.reset()
    snapshot = (env.current_time_min, env.event_records, env.decision_records,
                env.placements, env.episode_return, env.action_masks().copy())
    for bad, error in ((0, ValueError), (8, ValueError), (True, TypeError),
                       (1.2, TypeError), (np.array([1]), TypeError)):
        with pytest.raises(error):
            env.step(bad)
        assert snapshot[:-1] == (env.current_time_min, env.event_records,
                                 env.decision_records, env.placements, env.episode_return)
        np.testing.assert_array_equal(snapshot[-1], env.action_masks())
    terminal, _, done, _, _ = env.step(np.int64(online_fcfs_action(env)))
    assert done and env.observation_space.contains(terminal)
    assert not env.action_masks().any()
    with pytest.raises(RuntimeError):
        env.step(1)


@pytest.mark.parametrize("horizon", [0, 240])
def test_counterfactual_nonanticipativity(horizon):
    common = (("A", 0, 100, 10), ("B", 100, 100, 10),
              ("C", 300, 100, 10), ("D", 600, 100, 10))
    base = scenario(*common, horizon=horizon)
    other = scenario(*common, ("V", 500, 100, 10), horizon=horizon)
    left = DynamicBAPEnv(scenario=base, max_vessels=5)
    right = DynamicBAPEnv(scenario=other, max_vessels=5)
    for env in (left, right):
        env.reset()
    assert "vessel_count" not in left._observation()
    assert "vessel_count" not in right._observation()
    assert right._observation()["visible_mask"].sum() == left._observation()["visible_mask"].sum()
    while left.current_time_min < 500 - horizon and not left.terminated:
        lo, ro = left._observation(), right._observation()
        for key in lo:
            np.testing.assert_array_equal(lo[key], ro[key])
        np.testing.assert_array_equal(left.action_masks(), right.action_masks())
        action = online_fcfs_action(left)
        left.step(action)
        right.step(action)
    # A hidden vessel can change future event timing, but not preceding decisions.
    assert right.current_time_min >= 500 - horizon
    if horizon:
        assert any(r["event_type"] == "HORIZON_ENTRY" and r["vessel_id"] == "V"
                   and r["event_time_min"] == 260 for r in right.event_records)
    else:
        assert any(
            r["event_type"] == "VESSEL_ARRIVAL" and r["vessel_id"] == "V"
            and r["event_time_min"] == 500 for r in right.event_records)


def test_drain_limit_reports_unresolved():
    env = DynamicBAPEnv(scenario=scenario(("A", 0, 100, 20), drain=5), max_vessels=1)
    env.reset()
    obs, reward, done, truncated, info = env.step(online_fcfs_action(env))
    assert not done and truncated and reward == 0
    assert info["unresolved_vessel_ids"] == ("A",)
    assert env.observation_space.contains(obs)


def test_static_formulation_guard():
    dynamic = scenario(("A", 0, 100, 10))
    with pytest.raises(ValueError):
        StaticBAPEnv(scenario=dynamic, max_vessels=1)
    static = replace(dynamic, formulation="static", termination_mode=None,
                     max_drain_extension_min=None, future_horizon_min=None)
    with pytest.raises(ValueError):
        DynamicBAPEnv(scenario=static, max_vessels=1)
