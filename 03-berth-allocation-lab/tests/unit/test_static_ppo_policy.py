"""Checkpoint metadata, compatibility and masked inference without training."""

import json
from dataclasses import replace

import numpy as np
import pytest
from sb3_contrib import MaskablePPO

from berth_allocation_lab.envs import OBSERVATION_VERSION, StaticBAPEnv
from berth_allocation_lab.rl.policy import (
    CheckpointCompatibilityError, MaskablePPOStaticPolicy, MaskedActionError, check_checkpoint_compatibility,
    load_checkpoint, masked_predict, metadata_path, save_checkpoint,
)

RUN_METADATA = {"experiment_id": "unit", "training_run_id": "unit_run", "training_seed": 3,
                "max_vessels": 3, "time_scale_min": 1440.0, "length_scale_m": 1000.0,
                "reward_scale": 1 / 1440, "checkpoint_kind": "final", "timesteps": 0, "model_id": "unit/final@0"}


@pytest.fixture
def untrained(manual_static_scenario):
    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    model = MaskablePPO("MultiInputPolicy", env, gamma=1.0, n_steps=16, batch_size=8, seed=3, device="cpu",
                        policy_kwargs={"net_arch": {"pi": [8], "vf": [8]}})
    return model, env


def test_checkpoint_sidecar_records_versions_and_identity(untrained, tmp_path):
    model, _ = untrained
    path = save_checkpoint(model, tmp_path / "final_model.zip", RUN_METADATA)
    record = json.loads(metadata_path(path).read_text(encoding="utf-8"))
    for key in ("policy_id", "algorithm", "environment_version", "observation_definition_version",
                "reward_definition_version", "candidate_generator_version", "action_capacity",
                "dependency_versions", "created_at", "training_seed", "reward_scale", "model_id"):
        assert key in record, key
    assert record["policy_id"] == "static_maskable_ppo_v1" and record["action_capacity"] == 6
    assert record["observation_definition_version"] == OBSERVATION_VERSION
    loaded, metadata = load_checkpoint(path)
    assert metadata == record and int(loaded.action_space.n) == 6


def test_missing_sidecar_is_rejected(untrained, tmp_path):
    model, _ = untrained
    model.save(tmp_path / "bare.zip")
    with pytest.raises(CheckpointCompatibilityError, match="missing"):
        load_checkpoint(tmp_path / "bare.zip")


@pytest.mark.parametrize("change, message", [
    ({"max_vessels": 4}, "max_vessels"),
    ({"time_scale_min": 60.0}, "time_scale_min"),
    ({"observation_definition_version": "static_obs_v0"}, "observation_definition_version"),
    ({"policy_id": "other"}, "policy_id"),
    ({"dependency_versions": {"stable_baselines3": "1.8.0", "sb3_contrib": "1.8.0"}}, "major version"),
])
def test_incompatible_checkpoints_are_rejected(untrained, tmp_path, change, message):
    model, env = untrained
    _, metadata = load_checkpoint(save_checkpoint(model, tmp_path / "m.zip", RUN_METADATA))
    check_checkpoint_compatibility(metadata, model, env)
    with pytest.raises(CheckpointCompatibilityError, match=message):
        check_checkpoint_compatibility({**metadata, **change}, model, env)


def test_capacity_mismatch_between_model_and_environment(untrained, tmp_path, manual_static_scenario):
    model, _ = untrained
    _, metadata = load_checkpoint(save_checkpoint(model, tmp_path / "m.zip", RUN_METADATA))
    wider = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=4)
    with pytest.raises(CheckpointCompatibilityError, match="action"):
        check_checkpoint_compatibility(metadata, model, wider)


class _FakeModel:
    def __init__(self, action):
        self.action = action

    def predict(self, observation, action_masks=None, deterministic=False):
        assert action_masks is not None and deterministic is True
        return self.action, None


@pytest.mark.parametrize("action", [np.array(1), np.array([1]), np.int64(1), 1])
def test_masked_predict_returns_plain_int(action):
    assert masked_predict(_FakeModel(action), {}, np.array([True, True, False])) == 1


@pytest.mark.parametrize("action", [np.array(2), np.array(7), np.array(-1), np.array([0, 1]), np.array(0.0)])
def test_masked_predict_never_accepts_a_forbidden_index(action):
    with pytest.raises(MaskedActionError):
        masked_predict(_FakeModel(action), {}, np.array([True, True, False]))


def test_untrained_policy_respects_masks_on_every_decision(untrained, tmp_path, manual_static_scenario):
    model, _ = untrained
    policy = MaskablePPOStaticPolicy(*load_checkpoint(save_checkpoint(model, tmp_path / "m.zip", RUN_METADATA)))
    for shift in (0.0, 30.0, 500.0):
        scenario = replace(manual_static_scenario, vessels=tuple(
            replace(v, arrival_time_min=v.arrival_time_min + shift) for v in manual_static_scenario.vessels))
        result = policy.schedule(scenario)
        assert len(result.placements) == 3
        assert all(r.selected_candidate_index < r.candidate_count for r in result.decision_records)
        assert all(r.policy_id == "static_maskable_ppo_v1" for r in result.decision_records)
        assert policy.schedule(scenario) == result  # deterministic inference
