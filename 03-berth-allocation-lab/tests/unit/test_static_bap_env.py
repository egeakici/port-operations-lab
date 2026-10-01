from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from berth_allocation_lab.core import (
    NUMERICAL_TOLERANCE as EPS, candidate_positions, earliest_feasible_start, total_waiting_time,
)
from berth_allocation_lab.data import BAPVesselInput as Vessel
from berth_allocation_lab.envs import (
    PROVIDER_SEED_UPPER_BOUND, StaticBAPEnv, StaticBAPEnvConsistencyError, SyntheticScenarioProvider,
)
from berth_allocation_lab.envs import static_bap_env as env_module
from berth_allocation_lab.scenarios import SyntheticScenarioConfig, SyntheticScenarioGenerator

CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "scenarios"
T = 1440.0


@pytest.fixture
def spec_example(manual_static_scenario):
    """Worked Example A from the problem specification (Q=500, d=20)."""
    return replace(manual_static_scenario, scenario_id="spec_example_a", berth_length_m=500.0,
                   min_clearance_m=20.0, vessels=(Vessel("A", 0.0, 180.0, 120.0),
                                                   Vessel("B", 30.0, 140.0, 90.0),
                                                   Vessel("C", 40.0, 260.0, 150.0)))


@pytest.fixture
def provider():
    config = SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_tiny_congested.yaml")
    return SyntheticScenarioProvider(config, base_scenario_id="step8_unit_tiny", split="validation")


def snapshot(env):
    return (env.placements, env.decision_records, env.episode_return, env.current_candidates,
            env.terminated, env.scenario, env.action_masks().tolist())


def assert_obs_equal(left, right):
    assert left.keys() == right.keys()
    for key in left:
        np.testing.assert_array_equal(left[key], right[key])


def run_first_valid(env, seed=None):
    obs, info = env.reset(seed=seed)
    rewards = []
    terminated = False
    while not terminated:
        obs, reward, terminated, truncated, info = env.step(int(np.flatnonzero(env.action_masks())[0]))
        rewards.append(reward)
    return obs, rewards, info


# Construction and validation

def test_fixed_scenario_construction(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=8)
    assert env.action_capacity == 16 and env.action_space.n == 16
    obs, info = env.reset(seed=42)
    assert env.scenario is manual_static_scenario
    assert info["scenario_id"] == "manual_static_001"
    assert info["scenario_seed"] == manual_static_scenario.seed
    assert info["scenario_fingerprint"] == manual_static_scenario.content_fingerprint
    assert env.observation_space.contains(obs)


def test_provider_construction(provider):
    env = StaticBAPEnv(scenario_provider=provider, max_vessels=8)
    obs, info = env.reset(seed=7)
    assert 0 <= info["scenario_seed"] < PROVIDER_SEED_UPPER_BOUND
    assert info["scenario_id"] == f"step8_unit_tiny_seed{info['scenario_seed']}"
    assert info["scenario_split"] == "validation"
    assert env.scenario.vessel_count == 6
    assert env.observation_space.contains(obs)


def test_scenario_modes_are_mutually_exclusive(manual_static_scenario, provider):
    with pytest.raises(ValueError, match="exactly one"):
        StaticBAPEnv(scenario=manual_static_scenario, scenario_provider=provider, max_vessels=8)
    with pytest.raises(ValueError, match="exactly one"):
        StaticBAPEnv(max_vessels=8)


@pytest.mark.parametrize("kwargs", [dict(max_vessels=0), dict(max_vessels=True), dict(max_vessels=2.0),
                                    dict(time_scale_min=0), dict(time_scale_min=float("nan")),
                                    dict(length_scale_m=-1), dict(policy_id=""),
                                    dict(render_mode="human")])
def test_invalid_constructor_arguments(manual_static_scenario, kwargs):
    with pytest.raises(ValueError):
        StaticBAPEnv(scenario=manual_static_scenario, **{"max_vessels": 8, **kwargs})


def test_static_formulation_is_required_for_fixed_and_generated(manual_static_scenario):
    dynamic = replace(manual_static_scenario, formulation="dynamic")
    with pytest.raises(ValueError, match="static"):
        StaticBAPEnv(scenario=dynamic, max_vessels=8)
    env = StaticBAPEnv(scenario_provider=lambda seed: replace(dynamic, seed=seed), max_vessels=8)
    with pytest.raises(ValueError, match="static"):
        env.reset(seed=0)
    with pytest.raises(RuntimeError, match="reset"):
        env.step(0)


def test_oversized_scenarios_are_rejected_not_truncated(manual_static_scenario):
    with pytest.raises(ValueError, match="never truncated"):
        StaticBAPEnv(scenario=manual_static_scenario, max_vessels=2)
    env = StaticBAPEnv(scenario_provider=lambda seed: replace(manual_static_scenario, seed=seed),
                       max_vessels=2)
    with pytest.raises(ValueError, match="never truncated"):
        env.reset(seed=0)


def test_provider_must_record_drawn_seed(manual_static_scenario):
    env = StaticBAPEnv(scenario_provider=lambda seed: manual_static_scenario, max_vessels=8)
    with pytest.raises(ValueError, match="generation seed"):
        env.reset(seed=3)


def test_reset_rejects_options(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=8)
    env.reset(options={})
    with pytest.raises(ValueError, match="options"):
        env.reset(options={"scenario": manual_static_scenario})


# Initial state, order and observation contract

def test_empty_initial_schedule(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=4)
    obs, _ = env.reset()
    assert env.placements == () and env.decision_records == () and env.episode_return == 0.0
    assert not env.terminated
    assert obs["scheduled_mask"].tolist() == [0, 0, 0, 0]
    assert not obs["placement_features"].any()
    assert obs["current_vessel_index"] == 0
    vessel = env.ordered_vessels[0]
    q, d = manual_static_scenario.berth_length_m, manual_static_scenario.min_clearance_m
    assert [x for x, _, _ in env.current_candidates] == list(candidate_positions(vessel, (), q, d))


def test_canonical_order_and_arrival_tie_breaking(manual_static_scenario):
    # Valid arrival order with an ID tie listed as B before A.
    scenario = replace(manual_static_scenario, vessels=(Vessel("Z", 0.0, 100.0, 50.0),
                                                        Vessel("B", 10.0, 120.0, 50.0),
                                                        Vessel("A", 10.0, 130.0, 50.0)))
    env = StaticBAPEnv(scenario=scenario, max_vessels=3)
    obs, _ = env.reset()
    assert [v.vessel_id for v in env.ordered_vessels] == ["Z", "A", "B"]
    np.testing.assert_allclose(obs["vessel_features"][:, 1], np.array([100, 130, 120]) / 500.0, rtol=1e-6)
    _, _, info = run_first_valid(env)
    assert [p.vessel_id for p in env.placements] == ["Z", "A", "B"]
    assert [r.vessel_id for r in env.decision_records] == ["Z", "A", "B"]


def test_observation_shapes_dtypes_membership_and_finiteness(provider):
    env = StaticBAPEnv(scenario_provider=provider, max_vessels=8)
    obs, _ = env.reset(seed=1)
    expected = {
        "vessel_features": ((8, 3), np.float32), "vessel_mask": ((8,), np.int8),
        "placement_features": ((8, 3), np.float32), "scheduled_mask": ((8,), np.int8),
        "current_vessel_index": ((), np.int64), "current_vessel_features": ((3,), np.float32),
        "candidate_features": ((16, 3), np.float32), "candidate_mask": ((16,), np.int8),
        "terminal_features": ((2,), np.float32),
    }
    terminated = False
    while True:
        assert set(obs) == set(expected)
        for key, (shape, dtype) in expected.items():
            assert np.shape(obs[key]) == shape and obs[key].dtype == dtype, key
            assert np.all(np.isfinite(obs[key]))
        assert env.observation_space.contains(obs)
        if terminated:
            break
        obs, _, terminated, _, _ = env.step(int(np.flatnonzero(env.action_masks())[-1]))


def test_vessel_padding_and_masks(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=5)
    obs, _ = env.reset()
    assert obs["vessel_mask"].tolist() == [1, 1, 1, 0, 0]
    assert not obs["vessel_features"][3:].any()
    np.testing.assert_allclose(obs["vessel_features"][:3, 1], [0.2, 0.5, 0.4], rtol=1e-6)
    np.testing.assert_allclose(obs["vessel_features"][:3, 2], np.array([100, 1000, 100]) / T, rtol=1e-6)
    obs, *_ = env.step(0)
    # A placed at x=0: zero position is valid and scheduled_mask is authoritative.
    assert obs["scheduled_mask"].tolist() == [1, 0, 0, 0, 0]
    assert obs["placement_features"][0, 0] == 0.0


def test_current_vessel_features_and_terminal_sentinel(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=4)
    obs, _ = env.reset()
    for k in range(3):
        assert obs["current_vessel_index"] == k
        np.testing.assert_array_equal(obs["current_vessel_features"], obs["vessel_features"][k])
        assert obs["current_vessel_features"][0] == 0.0  # relative to its own arrival
        obs, _, terminated, _, _ = env.step(0)
    assert terminated
    assert obs["current_vessel_index"] == 4  # max_vessels sentinel, not a vessel row
    assert not obs["current_vessel_features"].any()
    assert not obs["candidate_mask"].any() and not obs["candidate_features"].any()
    assert obs["scheduled_mask"].tolist() == [1, 1, 1, 0]
    assert env.observation_space.contains(obs)


def test_relative_time_and_candidate_encoding_worked_example(spec_example):
    env = StaticBAPEnv(scenario=spec_example, max_vessels=4)
    env.reset()
    obs, *_ = env.step(0)  # A at x=0, [0, 120)
    # Decision 1 for B: reference time is B's arrival (30).
    np.testing.assert_allclose(obs["vessel_features"][:3, 0], np.array([-30, 0, 10]) / T, rtol=1e-6)
    np.testing.assert_allclose(obs["placement_features"][0], [0.0, -30 / T, 90 / T], rtol=1e-6)
    assert env.current_candidates == ((0.0, 120.0, 90.0), (200.0, 30.0, 0.0), (360.0, 30.0, 0.0))
    np.testing.assert_allclose(obs["candidate_features"][:3],
                               [[0.0, 90 / T, 90 / T], [0.4, 0.0, 0.0], [0.72, 0.0, 0.0]], rtol=1e-6)
    np.testing.assert_allclose(obs["terminal_features"], [0.5, 0.04], rtol=1e-6)
    env.step(1)  # B at the clearance boundary x = 180 + 20
    assert [x for x, _, _ in env.current_candidates] == [0.0, 200.0, 240.0]
    _, reward, terminated, _, info = env.step(0)  # specification: s_C = 120, W_C = 80
    assert reward == -80.0 and terminated
    assert env.placements[2].berth_start_time_min == 120.0
    assert info["total_waiting_time_min"] == 80.0 and info["episode_return"] == -80.0


def test_terminal_reference_time_is_last_vessel_arrival(spec_example):
    env = StaticBAPEnv(scenario=spec_example, max_vessels=3)
    env.reset()
    for _ in range(3):
        obs, *_ = env.step(0)
    np.testing.assert_allclose(obs["vessel_features"][:, 0], np.array([-40, -10, 0]) / T, rtol=1e-6)


def test_candidate_ordering_mask_and_feature_alignment(provider):
    env = StaticBAPEnv(scenario_provider=provider, max_vessels=6)
    obs, _ = env.reset(seed=11)
    for k in range(6):
        positions = [x for x, _, _ in env.current_candidates]
        assert positions == sorted(positions)
        mask = env.action_masks()
        assert mask.dtype == bool and mask.shape == (12,)
        assert mask.tolist() == obs["candidate_mask"].astype(bool).tolist()
        assert mask.sum() == len(positions) <= 2 + 2 * k
        np.testing.assert_allclose(obs["candidate_features"][: len(positions), 0],
                                   np.array(positions) / env.scenario.berth_length_m, rtol=1e-6)
        obs, *_ = env.step(len(positions) - 1)
    assert not env.action_masks().any()


def test_candidate_list_is_computed_once_per_decision(manual_static_scenario, monkeypatch):
    calls = []
    original = env_module.candidate_starts
    monkeypatch.setattr(env_module, "candidate_starts", lambda *a: calls.append(1) or original(*a))
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    env.reset()
    for _ in range(3):
        env.action_masks()
    assert len(calls) == 1
    env.step(0)
    env.action_masks()
    assert len(calls) == 2


def test_returned_arrays_are_fresh_copies(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    reference = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    obs, _ = env.reset()
    reference.reset()
    for value in obs.values():
        if isinstance(value, np.ndarray) and value.ndim:
            value.fill(0)
    mask = env.action_masks()
    mask[:] = False
    assert env.action_masks().tolist() == reference.action_masks().tolist()
    assert env.action_masks() is not env.action_masks()
    assert_obs_equal(env.step(1)[0], reference.step(1)[0])


# Actions, rewards and termination

def test_action_capacity_follows_max_vessels_not_solver_limit(manual_static_scenario):
    for m in (1, 3, 12, 40):
        env = StaticBAPEnv(scenario=replace(manual_static_scenario, vessels=manual_static_scenario.vessels[:1]),
                           max_vessels=m)
        assert env.action_capacity == env.action_space.n == 2 * m


@pytest.mark.parametrize("action", [-1, 16, 99, 3, True, np.bool_(False), 1.0, np.float32(0),
                                    "0", None, np.array([0]), np.array(0.0)])
def test_invalid_actions_raise_without_mutation(manual_static_scenario, action):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=8)
    env.reset()
    env.step(0)
    before = snapshot(env)
    obs_before = env._observation()
    with pytest.raises((ValueError, TypeError)):
        env.step(action)
    assert snapshot(env) == before
    assert_obs_equal(env._observation(), obs_before)


def test_masked_and_out_of_range_messages(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=8)
    env.reset()
    count = len(env.current_candidates)
    with pytest.raises(ValueError, match="masked"):
        env.step(count)
    with pytest.raises(ValueError, match="outside"):
        env.step(env.action_capacity)
    with pytest.raises(TypeError, match="integer"):
        env.step(True)


@pytest.mark.parametrize("action", [0, np.int64(0), np.int32(0), np.uint8(0), np.array(0)])
def test_integer_scalar_actions_are_accepted(manual_static_scenario, action):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=8)
    env.reset()
    env.step(action)
    assert env.decision_records[0].selected_candidate_index == 0


def test_valid_step_placement_start_reward_and_index(manual_static_scenario):
    scenario = manual_static_scenario
    q, d = scenario.berth_length_m, scenario.min_clearance_m
    env = StaticBAPEnv(scenario=scenario, max_vessels=3)
    env.reset()
    total = 0.0
    for k, action in enumerate((0, 0, 0)):
        vessel = env.ordered_vessels[k]
        partial = env.placements
        x = candidate_positions(vessel, partial, q, d)[action]
        start = earliest_feasible_start(vessel, x, partial, q, d)
        obs, reward, terminated, truncated, info = env.step(action)
        placement = env.placements[-1]
        assert (placement.vessel_id, placement.berth_position_m, placement.berth_start_time_min) == (
            vessel.vessel_id, x, start)
        assert (placement.length_m, placement.service_time_min) == (vessel.length_m, vessel.service_time_min)
        assert isinstance(reward, float) and reward == -(start - vessel.arrival_time_min)
        assert type(terminated) is bool and type(truncated) is bool and truncated is False
        assert info["decision_index"] == k and len(env.placements) == k + 1
        assert info["incremental_waiting_time_min"] == -reward
        assert env.decision_records[-1].selected_waiting_time_min == -reward
        total += reward
        assert terminated is (k == 2)
    # A@0, B@0 waits for A until 100, C@0 waits for B until 1100.
    assert total == -(100.0 + 1000.0) == env.episode_return


def test_no_terminal_bonus_and_return_equals_negative_total(provider):
    env = StaticBAPEnv(scenario_provider=provider, max_vessels=6)
    _, rewards, info = run_first_valid(env, seed=5)
    total = total_waiting_time(env.scenario.vessels, env.placements)
    assert rewards[-1] == -env.decision_records[-1].selected_waiting_time_min
    assert sum(rewards) == pytest.approx(-total, abs=EPS)
    assert info["episode_return"] == pytest.approx(-total, abs=EPS)
    assert info["objective_value"] == env.final_metrics.objective_value == pytest.approx(total, abs=EPS)
    assert info["schedule_valid"] is True and info["vessel_count_completed"] == 6


def test_post_termination_rejection_and_reset(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    first_obs, _ = env.reset()
    run_first_valid(env)
    assert not env.action_masks().any()
    before = snapshot(env)
    with pytest.raises(RuntimeError, match="terminated"):
        env.step(0)
    assert snapshot(env) == before
    obs, info = env.reset()
    assert env.placements == () and env.decision_records == () and env.episode_return == 0.0
    assert not env.terminated and env.final_metrics is None
    assert_obs_equal(obs, first_obs)


def test_step_and_mask_before_reset_raise(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    with pytest.raises(RuntimeError, match="reset"):
        env.step(0)
    with pytest.raises(RuntimeError, match="reset"):
        env.action_masks()


# Determinism, seeds and identity

def test_fixed_scenario_determinism(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    obs_a, info_a = env.reset(seed=1)
    obs_b, info_b = env.reset(seed=2)
    assert_obs_equal(obs_a, obs_b)
    assert info_a == info_b
    assert env.scenario is manual_static_scenario


def test_generated_scenario_determinism(provider):
    left, right = (StaticBAPEnv(scenario_provider=provider, max_vessels=6) for _ in range(2))
    obs_l, info_l = left.reset(seed=42)
    obs_r, info_r = right.reset(seed=42)
    assert info_l == info_r
    assert_obs_equal(obs_l, obs_r)
    obs_again, info_again = left.reset(seed=42)
    assert info_again == info_l
    assert_obs_equal(obs_again, obs_l)


def test_reset_without_seed_continues_rng_stream(provider):
    def seeds(env, first_seed):
        return [env.reset(seed=first_seed)[1]["scenario_seed"], *(env.reset()[1]["scenario_seed"] for _ in range(3))]

    env = StaticBAPEnv(scenario_provider=provider, max_vessels=6)
    stream = seeds(env, 42)
    assert len(set(stream)) == 4
    assert seeds(StaticBAPEnv(scenario_provider=provider, max_vessels=6), 42) == stream
    assert env.reset(seed=42)[1]["scenario_seed"] == stream[0]


def test_scenario_identity_and_fingerprint_integrity(provider):
    env = StaticBAPEnv(scenario_provider=provider, max_vessels=6)
    _, info = env.reset(seed=3)
    seed = info["scenario_seed"]
    expected = provider(seed)
    assert env.scenario == expected
    assert info["scenario_fingerprint"] == expected.content_fingerprint == env.scenario.content_fingerprint
    assert env.scenario.seed == seed and env.scenario.split == "validation"
    _, other = env.reset()
    assert other["scenario_fingerprint"] != info["scenario_fingerprint"]


def test_time_translation_consistency(spec_example):
    shift = 512.0
    shifted = replace(spec_example, scenario_id="spec_example_shifted",
                      vessels=tuple(replace(v, arrival_time_min=v.arrival_time_min + shift)
                                    for v in spec_example.vessels))
    left, right = StaticBAPEnv(scenario=spec_example, max_vessels=4), StaticBAPEnv(scenario=shifted, max_vessels=4)
    obs_l, _ = left.reset()
    obs_r, _ = right.reset()
    for action in (1, 2, 0):
        for key in obs_l:
            np.testing.assert_allclose(obs_l[key], obs_r[key], atol=1e-7)
        assert [x for x, _, _ in left.current_candidates] == [x for x, _, _ in right.current_candidates]
        obs_l, reward_l, *_ = left.step(action)
        obs_r, reward_r, *_ = right.step(action)
        assert reward_l == reward_r
        assert right.placements[-1].berth_start_time_min == left.placements[-1].berth_start_time_min + shift
    assert left.episode_return == right.episode_return


def test_source_scenario_is_not_mutated(manual_static_scenario):
    before = manual_static_scenario.to_dict()
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    run_first_valid(env, seed=0)
    env.reset()
    assert manual_static_scenario.to_dict() == before


# Consistency failures are explicit

def test_empty_candidate_list_is_a_consistency_error(manual_static_scenario, monkeypatch):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    env.reset()
    before = snapshot(env)
    monkeypatch.setattr(env_module, "candidate_starts", lambda *a: ())
    with pytest.raises(StaticBAPEnvConsistencyError, match="No candidate"):
        env.step(0)
    assert snapshot(env) == before
    with pytest.raises(StaticBAPEnvConsistencyError, match="No candidate"):
        env.reset()


def test_capacity_overflow_raises_instead_of_truncating(manual_static_scenario, monkeypatch):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    overflow = tuple((float(i), 0.0) for i in range(env.action_capacity + 1))
    monkeypatch.setattr(env_module, "candidate_starts", lambda *a: overflow)
    with pytest.raises(StaticBAPEnvConsistencyError, match="exceed action capacity"):
        env.reset()


def test_render_ansi_and_disabled(manual_static_scenario):
    assert StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3).render() is None
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3, render_mode="ansi")
    env.reset()
    text = env.render()
    assert "manual_static_001" in text and "[0] x=0.000" in text


# Provider

def test_provider_identity_split_and_no_config_mutation(provider):
    source = provider.config
    first, again, other = provider(5), provider(5), provider(6)
    assert first == again and first.content_fingerprint == again.content_fingerprint
    assert first.content_fingerprint != other.content_fingerprint and first.vessels != other.vessels
    assert first.scenario_id == "step8_unit_tiny_seed5" and first.seed == 5
    assert first.split == "validation" and source.split == "test"
    assert provider.config is source and source.seed == 42
    assert source.scenario_id == "synthetic_tiny_congested_n6_seed42"
    for field in ("scenario_family", "formulation", "data_provenance", "generator_version"):
        assert getattr(first, field) == getattr(source, field)
    assert first.berth_length_m == source.terminal.berth_length_m
    assert first.vessel_count == source.traffic.vessel_count
    direct = SyntheticScenarioGenerator().generate(
        replace(source, scenario_id="step8_unit_tiny_seed5", seed=5, split="validation"))
    assert direct == first


@pytest.mark.parametrize("kwargs,error", [
    (dict(base_scenario_id="tiny_seed42"), ValueError), (dict(base_scenario_id=" "), ValueError),
    (dict(split="training"), ValueError), (dict(config="not-a-config"), TypeError),
])
def test_provider_rejects_ambiguous_arguments(provider, kwargs, error):
    with pytest.raises(error):
        SyntheticScenarioProvider(**{"config": provider.config, "base_scenario_id": "tiny",
                                     "split": "train", **kwargs})


def test_provider_rejects_dynamic_config_and_bad_seeds(provider):
    dynamic = SyntheticScenarioConfig.load_yaml(CONFIGS / "synthetic_medium.yaml")
    with pytest.raises(ValueError, match="static"):
        SyntheticScenarioProvider(dynamic, base_scenario_id="medium", split="train")
    twin = SyntheticScenarioProvider(dynamic.with_formulation("static"), base_scenario_id="medium", split="train")
    assert twin(0).formulation == "static"
    for seed in (-1, True, 1.5):
        with pytest.raises(ValueError):
            provider(seed)
