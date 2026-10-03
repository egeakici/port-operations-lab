"""Frozen dynamic learning, split and decision contracts."""

from dataclasses import replace

import pytest

from berth_allocation_lab.rl.dynamic_config import DynamicConfigError, DynamicPPOConfig
from berth_allocation_lab.rl.dynamic_decision import (
    DynamicDecisionError, dynamic_rule, gap_closed, record_dynamic_decision,
)
from berth_allocation_lab.rl.dynamic_evaluation import percentage_improvement, weighted_validation_mean
from berth_allocation_lab.rl.dynamic_suites import audit_dynamic_suites, dynamic_suites
from berth_allocation_lab.rl.dynamic_training import train_dynamic_ppo
from berth_allocation_lab.rl.dynamic_wrappers import DynamicTrainingRewardScale
from berth_allocation_lab.envs import DynamicBAPEnv
from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action


@pytest.fixture
def config():
    return DynamicPPOConfig.load_yaml("configs/rl/dynamic_ppo_smoke.yaml")


def test_frozen_config_and_action_capacity(config):
    assert config.ppo.gamma == 1.0
    assert config.ppo.device == "cpu"
    assert config.reward_scale == pytest.approx(1 / 1440)
    assert config.horizon_min == 240
    with pytest.raises(DynamicConfigError, match="observation"):
        replace(config, observation_version="static_obs_v1").validate()
    with pytest.raises(DynamicConfigError, match="gamma"):
        replace(config, ppo=replace(config.ppo, gamma=0.99)).validate()
    with pytest.raises(DynamicConfigError, match="ppo.device"):
        replace(config, ppo=replace(config.ppo, device="auto")).validate()
    assert replace(config, horizon_min=0).validate() is None
    with pytest.raises(DynamicConfigError, match="H=0 or H=240"):
        replace(config, horizon_min=60).validate()


def test_cuda_configs_only_change_device_and_run_identity():
    for regime in ("tiny", "medium_heavy"):
        base = DynamicPPOConfig.load_yaml(f"configs/rl/dynamic_ppo_{regime}_extended.yaml")
        cuda = DynamicPPOConfig.load_yaml(f"configs/rl/dynamic_ppo_{regime}_extended_cuda.yaml")
        assert base.ppo.device == "cpu" and cuda.ppo.device == "cuda"
        assert replace(cuda.ppo, device="cpu") == base.ppo
        assert cuda.components == base.components
        assert cuda.validation == base.validation and cuda.test == base.test
        assert cuda.training == base.training
        assert cuda.experiment_id != base.experiment_id
        assert cuda.output_dir != base.output_dir
        assert cuda.source_sha256 != base.source_sha256


def test_cuda_unavailable_fails_before_creating_run(monkeypatch, tmp_path):
    cuda = DynamicPPOConfig.load_yaml("configs/rl/dynamic_ppo_tiny_extended_cuda.yaml")
    monkeypatch.setattr("torch.cuda.is_available", lambda: False)
    root = tmp_path / "runs"
    with pytest.raises(RuntimeError, match="CUDA requested"):
        train_dynamic_ppo(cuda, 11, output_root=root)
    assert not root.exists()


def test_dynamic_rule_both_outcomes_and_undefined_gap():
    win = dynamic_rule([80, 90, 120], 100, 50)
    assert win["r1_useful_learning"] and win["r1_seed_wins_vs_fcfs"] == 2
    assert win["r2_gap_closed_mean"] == pytest.approx((100 - 290 / 3) / 50)
    lose = dynamic_rule([80, 120, 120], 100, 110)
    assert not lose["r1_useful_learning"]
    assert lose["r2_gap_closed_mean"] is None
    assert gap_closed(80, 100, 100) is None
    assert percentage_improvement(0, 0) is None
    with pytest.raises(DynamicDecisionError):
        dynamic_rule([80, 90], 100, 50)


def test_horizon_decisions_cannot_mix(tmp_path):
    primary = DynamicPPOConfig.load_yaml("configs/rl/dynamic_ppo_tiny_extended.yaml")
    with pytest.raises(DynamicDecisionError, match="same horizon"):
        record_dynamic_decision((primary, replace(primary, horizon_min=0)),
                                tmp_path / "decision.json")
    assert not (tmp_path / "decision.json").exists()


def test_incomplete_episode_not_counted_as_complete(config):
    rows = [{"status": "truncated", "scenario_id": "dynamic_tiny_n6_validation_seed1",
             "total_waiting_time_min": None}]
    assert weighted_validation_mean(rows, config) is None


def test_reward_scale_does_not_change_raw_environment(config):
    scenario = dynamic_suites(config)["validation"].scenarios[0]
    raw = DynamicBAPEnv(scenario=scenario, max_vessels=config.max_vessels,
                        future_horizon_min=config.horizon_min)
    scaled = DynamicTrainingRewardScale(DynamicBAPEnv(
        scenario=scenario, max_vessels=config.max_vessels,
        future_horizon_min=config.horizon_min))
    raw.reset()
    scaled.reset()
    while not raw.terminated:
        action = online_fcfs_action(raw)
        _, reward, _, _, _ = raw.step(action)
        _, scaled_reward, _, _, info = scaled.step(action)
        assert info["raw_reward"] == pytest.approx(reward)
        assert scaled_reward == pytest.approx(reward / 1440)
    assert raw.episode_return == pytest.approx(-raw._info()["total_waiting_time_min"])


@pytest.mark.slow
def test_cross_formulation_prior_exposure_audit(config):
    suites = dynamic_suites(config)
    result = audit_dynamic_suites(config, suites)
    assert result["prior_exposure"]["previously_examined_instances"] > 0
    assert result["prior_exposure"]["checked_instances"] == sum(len(s.scenarios) for s in suites.values())
