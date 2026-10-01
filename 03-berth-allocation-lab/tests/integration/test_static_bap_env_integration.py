import ast
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from berth_allocation_lab.core import NUMERICAL_TOLERANCE as EPS, find_schedule_violations, total_waiting_time
from berth_allocation_lab.data import BAPVesselInput as Vessel
from berth_allocation_lab.envs import StaticBAPEnv, SyntheticScenarioProvider
from berth_allocation_lab.evaluation import calculate_static_metrics
from berth_allocation_lab.policies import StaticFCFS, StaticGreedyRollout
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator
from berth_allocation_lab.solvers import CandidateEnumerationConfig as Config, StaticCandidateEnumeration as Solver

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs" / "scenarios"
ENV_SOURCES = ROOT / "src" / "berth_allocation_lab" / "envs"
OBSERVATION_KEYS = {
    "vessel_features", "vessel_mask", "placement_features", "scheduled_mask", "current_vessel_index",
    "current_vessel_features", "candidate_features", "candidate_mask", "terminal_features",
}


def tiny_congested(count, seed=42):
    """Same construction and IDs as the Step 7 validation series."""
    base = SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_tiny_congested.yaml")
    return SyntheticScenarioGenerator().generate(replace(
        base, scenario_id=f"synthetic_tiny_congested_n{count}_seed{seed}", seed=seed,
        traffic=replace(base.traffic, vessel_count=count)))


def one_vessel_config():
    base = SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_tiny_congested.yaml")
    return replace(base, traffic=replace(base.traffic, vessel_count=1))


def two_vessel_positive(manual_static_scenario):
    """Both 300 m vessels cannot share a 500 m quay: certified optimum is 100."""
    return replace(manual_static_scenario, scenario_id="manual_two_positive", vessels=(
        Vessel("A", 0.0, 300.0, 100.0), Vessel("B", 0.0, 300.0, 50.0)))


def replay(scenario, records, max_vessels=None):
    """Feed recorded indices through the public Gymnasium interface only."""
    env = StaticBAPEnv(scenario=scenario, max_vessels=max_vessels or scenario.vessel_count)
    obs, _ = env.reset(seed=0)
    rewards = []
    for record in records:
        mask = env.action_masks()
        assert mask[record.selected_candidate_index]
        assert mask.sum() == record.candidate_count
        assert np.flatnonzero(obs["candidate_mask"]).tolist() == np.flatnonzero(mask).tolist()
        assert tuple(x for x, _, _ in env.current_candidates) == record.candidate_positions_m
        obs, reward, terminated, truncated, info = env.step(record.selected_candidate_index)
        decision = env.decision_records[-1]
        assert decision.selected_berth_position_m == record.selected_berth_position_m
        assert decision.selected_start_time_min == record.selected_start_time_min
        assert decision.selected_waiting_time_min == record.selected_waiting_time_min
        assert env.observation_space.contains(obs)
        rewards.append(reward)
    assert terminated is True and truncated is False
    assert len(rewards) == scenario.vessel_count
    return env, rewards, info


def assert_replay_matches(scenario, result, max_vessels=None):
    env, rewards, info = replay(scenario, result.decision_records, max_vessels)
    assert env.placements == result.placements
    objective = total_waiting_time(scenario.vessels, result.placements)
    assert not find_schedule_violations(scenario.vessels, env.placements,
                                        scenario.berth_length_m, scenario.min_clearance_m)
    assert info["objective_value"] == pytest.approx(objective, abs=EPS)
    assert info["episode_return"] == pytest.approx(-objective, abs=EPS)
    assert sum(rewards) == pytest.approx(-objective, abs=EPS)
    assert calculate_static_metrics(scenario, env.placements) == env.final_metrics
    return env


def env_leaves(scenario):
    """Every legal trajectory, enumerated through reset/step/action_masks only."""
    env = StaticBAPEnv(scenario=scenario, max_vessels=scenario.vessel_count)
    leaves = []

    def visit(prefix):
        env.reset()
        for action in prefix:
            env.step(action)
        if env.terminated:
            leaves.append((env.episode_return, env.placements))
            return
        for action in np.flatnonzero(env.action_masks()):
            visit((*prefix, int(action)))

    visit(())
    return leaves


def checker_warnings_as_errors():
    context = warnings.catch_warnings()
    context.__enter__()
    warnings.simplefilter("error")
    # Unregistered env: Gymnasium cannot construct alternative render modes.
    warnings.filterwarnings("ignore", message=".*not having a spec")
    return context


# Gymnasium contract

@pytest.mark.parametrize("render_mode", [None, "ansi"])
def test_gymnasium_checker_on_one_vessel_fixture(manual_static_scenario, render_mode):
    # Two distinct, always-valid boundary candidates, so action_space.sample()
    # never hits a masked index. Multi-vessel masks are tested separately below.
    scenario = replace(manual_static_scenario, vessels=(Vessel("A", 0.0, 100.0, 100.0),))
    env = StaticBAPEnv(scenario=scenario, max_vessels=1, render_mode=render_mode)
    env.reset()
    assert [x for x, _, _ in env.current_candidates] == [0.0, 400.0]
    context = checker_warnings_as_errors()
    try:
        check_env(env)
        check_env(StaticBAPEnv(scenario_provider=SyntheticScenarioProvider(
            one_vessel_config(), base_scenario_id="step8_checker", split="validation"), max_vessels=1))
    finally:
        context.__exit__(None, None, None)


def test_multi_vessel_observation_contract_under_random_legal_actions():
    provider = SyntheticScenarioProvider(
        SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_tiny_congested.yaml"),
        base_scenario_id="step8_contract", split="validation")
    env = StaticBAPEnv(scenario_provider=provider, max_vessels=8)
    rng = np.random.default_rng(0)
    obs, _ = env.reset(seed=123)
    for _episode in range(10):
        terminated, k = False, 0
        while not terminated:
            assert set(obs) == OBSERVATION_KEYS
            assert env.observation_space.contains(obs)
            assert all(np.all(np.isfinite(v)) for v in obs.values())
            mask = env.action_masks()
            assert mask.tolist() == obs["candidate_mask"].astype(bool).tolist()
            assert obs["current_vessel_index"] == k and obs["scheduled_mask"].sum() == k
            assert 1 <= mask.sum() <= 2 + 2 * k
            with pytest.raises(ValueError, match="masked"):
                env.step(int(mask.sum()))
            obs, reward, terminated, truncated, info = env.step(int(rng.choice(np.flatnonzero(mask))))
            assert isinstance(reward, float) and reward <= 0.0 and truncated is False
            k += 1
        assert k == env.scenario.vessel_count and env.observation_space.contains(obs)
        assert info["episode_return"] == pytest.approx(-info["total_waiting_time_min"], abs=EPS)
        obs, _ = env.reset()


def test_generated_trajectories_are_reproducible():
    provider = SyntheticScenarioProvider(
        SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_tiny_congested.yaml"),
        base_scenario_id="step8_repro", split="validation")

    def trajectory():
        env = StaticBAPEnv(scenario_provider=provider, max_vessels=6)
        rng = np.random.default_rng(9)
        rows = []
        for seed in (5, None, None):
            _, info = env.reset(seed=seed)
            while not env.terminated:
                env.step(int(rng.choice(np.flatnonzero(env.action_masks()))))
            rows.append((info["scenario_fingerprint"], env.placements, env.episode_return))
        return rows

    first = trajectory()
    assert first == trajectory()
    assert len({fingerprint for fingerprint, _, _ in first}) == 3


# Replays of independent policies and the certified reference

@pytest.fixture(params=["manual", "tiny_n6", "low_static_n8"])
def replay_scenario(request, manual_static_scenario):
    if request.param == "manual":
        return manual_static_scenario
    if request.param == "tiny_n6":
        return tiny_congested(6)
    return SyntheticScenarioGenerator().generate(SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_low.yaml"))


def test_fcfs_replay(replay_scenario):
    assert_replay_matches(replay_scenario, StaticFCFS().schedule(replay_scenario), max_vessels=8)


def test_greedy_rollout_replay(replay_scenario):
    assert_replay_matches(replay_scenario, StaticGreedyRollout().schedule(replay_scenario), max_vessels=8)


@pytest.mark.parametrize("name,expected", [("manual", 0.0), ("two_positive", 100.0),
                                           ("tiny_n3", 282.313763), ("tiny_n6", 1612.784630)])
def test_exact_reference_replay(manual_static_scenario, name, expected):
    scenario = {"manual": manual_static_scenario, "two_positive": two_vessel_positive(manual_static_scenario),
                "tiny_n3": tiny_congested(3), "tiny_n6": tiny_congested(6)}[name]
    result = Solver().schedule(scenario)
    diagnostics = result.solver_diagnostics
    assert diagnostics.optimality_status == "optimal"
    assert diagnostics.reference_scope == "candidate_space"
    optimum = diagnostics.certified_optimal_objective
    assert optimum == pytest.approx(expected, abs=1e-6)
    env = assert_replay_matches(scenario, result)
    assert env.episode_return == pytest.approx(-optimum, abs=EPS)
    assert len(env.decision_records) == scenario.vessel_count
    for heuristic in (StaticFCFS(), StaticGreedyRollout()):
        heuristic_env, _, _ = replay(scenario, heuristic.schedule(scenario).decision_records)
        assert heuristic_env.episode_return <= -optimum + EPS


@pytest.mark.slow
def test_exact_reference_replay_eight_vessels_with_positive_rollout_gap():
    scenario = tiny_congested(8)
    result = Solver(Config(max_vessels=8)).schedule(scenario)
    optimum = result.solver_diagnostics.certified_optimal_objective
    assert result.solver_diagnostics.optimality_status == "optimal"
    assert optimum == pytest.approx(3188.254108, abs=1e-6)
    env = assert_replay_matches(scenario, result)
    rollout_env, _, _ = replay(scenario, StaticGreedyRollout().schedule(scenario).decision_records)
    assert rollout_env.episode_return == pytest.approx(-3297.398421, abs=1e-6)
    assert rollout_env.episode_return < env.episode_return - 1.0


@pytest.mark.parametrize("name", ["manual", "two_positive", "tiny_n3", "tiny_n4"])
def test_no_legal_trajectory_beats_certified_reference(manual_static_scenario, name):
    scenario = {"manual": manual_static_scenario, "two_positive": two_vessel_positive(manual_static_scenario),
                "tiny_n3": tiny_congested(3), "tiny_n4": tiny_congested(4)}[name]
    leaves = env_leaves(scenario)
    unpruned = Solver(Config(initial_incumbent="none", enable_pruning=False, stop_at_zero=False)).solve(scenario)
    optimum = unpruned.diagnostics.certified_optimal_objective
    # The environment's decision tree is exactly the Step 7 decision tree.
    assert len(leaves) == unpruned.diagnostics.complete_schedules_evaluated > 1
    assert all(episode_return <= -optimum + EPS for episode_return, _ in leaves)
    best = max(episode_return for episode_return, _ in leaves)
    assert best == pytest.approx(-optimum, abs=EPS)
    first_best = next(placements for r, placements in leaves if r >= best - EPS)
    assert first_best == unpruned.best_placements
    assert Solver().solve(scenario).diagnostics.certified_optimal_objective == pytest.approx(optimum, abs=EPS)


# Episodes of several sizes

@pytest.mark.parametrize("count", [1, 2, 3, 6, 8, 24, 40])
def test_manual_first_valid_episode_smoke(count):
    scenario = tiny_congested(count, seed=7)
    env = StaticBAPEnv(scenario=scenario, max_vessels=max(count, 8))
    obs, info = env.reset(seed=42)
    rewards, done = [], False
    while not done:
        valid_actions = np.flatnonzero(env.action_masks())
        obs, reward, terminated, truncated, info = env.step(int(valid_actions[0]))
        rewards.append(reward)
        done = terminated or truncated
    assert terminated and not truncated and len(rewards) == count
    assert info["vessel_count_completed"] == count and info["schedule_valid"] is True
    assert not find_schedule_violations(scenario.vessels, env.placements,
                                        scenario.berth_length_m, scenario.min_clearance_m)
    total = total_waiting_time(scenario.vessels, env.placements)
    assert sum(rewards) == pytest.approx(-total, abs=EPS)
    assert env.observation_space.contains(obs)


def test_larger_static_twin_episode_with_tight_capacity():
    heavy = SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_heavy.yaml").with_formulation("static")
    provider = SyntheticScenarioProvider(heavy, base_scenario_id="step8_heavy_twin", split="validation")
    env = StaticBAPEnv(scenario_provider=provider, max_vessels=24)
    _, info = env.reset(seed=2026)
    scenario = env.scenario
    assert scenario.vessel_count == 24 == env.max_vessels and scenario.formulation == "static"
    assert_replay_matches(scenario, StaticFCFS().schedule(scenario), max_vessels=24)
    rng = np.random.default_rng(1)
    while not env.terminated:
        env.step(int(rng.choice(np.flatnonzero(env.action_masks()))))
    assert env.final_metrics.throughput_vessels == 24


def test_dynamic_inputs_are_rejected():
    dynamic = SyntheticScenarioGenerator().generate(SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_medium.yaml"))
    assert dynamic.formulation == "dynamic"
    with pytest.raises(ValueError, match="static"):
        StaticBAPEnv(scenario=dynamic, max_vessels=16)
    env = StaticBAPEnv(scenario_provider=lambda seed: replace(dynamic, seed=seed), max_vessels=16)
    with pytest.raises(ValueError, match="static"):
        env.reset(seed=1)


# Policy independence

def test_environment_exposes_no_reference_or_policy_information(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    before, _ = env.reset()
    Solver().solve(manual_static_scenario)
    StaticGreedyRollout().schedule(manual_static_scenario)
    after, info = env.reset()
    assert set(before) == set(after) == OBSERVATION_KEYS
    for key in before:
        np.testing.assert_array_equal(before[key], after[key])
    assert not any(word in key for key in (*after, *info) for word in ("optim", "reference", "score", "rollout"))
    forbidden = ("berth_allocation_lab.solvers", "berth_allocation_lab.policies.fcfs",
                 "berth_allocation_lab.policies.greedy", "berth_allocation_lab.tracking",
                 "berth_allocation_lab.evaluation.runner", "stable_baselines3", "sb3_contrib", "torch")
    for source in ENV_SOURCES.glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        assert not [name for name in imported if name and name.startswith(forbidden)], source.name
