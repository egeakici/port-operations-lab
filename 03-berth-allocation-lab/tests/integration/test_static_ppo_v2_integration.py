"""Short v2 PPO runs exercise masking, checkpoints and canonical replay."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("sb3_contrib", reason="requires the rl extra")

from berth_allocation_lab.evaluation import run_static_policy  # noqa: E402
from berth_allocation_lab.rl.candidate_scoring import CandidateScoringMaskablePolicy  # noqa: E402
from berth_allocation_lab.rl.config import StaticPPOExperimentConfig  # noqa: E402
from berth_allocation_lab.rl.policy import (  # noqa: E402
    CheckpointCompatibilityError, MaskablePPOStaticPolicy, check_checkpoint_compatibility,
    load_checkpoint, masked_predict,
)
from berth_allocation_lab.rl.suites import build_config_suites  # noqa: E402
from berth_allocation_lab.rl.training import run_directory, train_static_ppo  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("stem", ["tiny", "medium_heavy"])
def test_v2_short_training_and_adapter(stem, tmp_path):
    config = StaticPPOExperimentConfig.load_yaml(ROOT / "configs" / "rl" / f"static_ppo_{stem}_v2.yaml")
    short = replace(config, ppo=replace(config.ppo, n_envs=4, n_steps=64, batch_size=64, n_epochs=1),
                    validation=replace(config.validation, seeds_per_component=1),
                    test=replace(config.test, seeds_per_component=1),
                    diagnostics=tuple(replace(s, seeds_per_component=1) for s in config.diagnostics))
    manifest = train_static_ppo(short, 11, output_root=tmp_path, total_timesteps=256, eval_freq=256)
    run_dir = run_directory(short, 11, tmp_path)
    assert manifest["status"] == "completed" and manifest["total_timesteps_completed"] == 256
    assert manifest["policy_id"] == "static_maskable_ppo_v2"
    assert manifest["split_audit"]["groups"]["train_episodes"] > 0
    saved = json.loads((run_dir / "final_model.metadata.json").read_text(encoding="utf-8"))
    assert saved["policy_architecture"] == "candidate_scoring_v2"
    assert saved["architecture_hyperparameters"]["vessel_embedding_dim"] == 64
    model, metadata = load_checkpoint(run_dir / "final_model.zip", expected_architecture="candidate_scoring_v2")
    assert isinstance(model.policy, CandidateScoringMaskablePolicy)
    with pytest.raises(CheckpointCompatibilityError, match="policy_architecture"):
        load_checkpoint(run_dir / "final_model.zip", expected_architecture="flat_mlp_v1")
    policy = MaskablePPOStaticPolicy(model, metadata)
    scenario = build_config_suites(short)["test"].scenarios[0]
    env = policy.make_env(scenario)
    check_checkpoint_compatibility(metadata, model, env, expected_architecture="candidate_scoring_v2")
    changed_metadata = {**metadata, "architecture_hyperparameters": {
        **metadata["architecture_hyperparameters"], "context_dim": 32}}
    with pytest.raises(CheckpointCompatibilityError, match="architecture_hyperparameters.context_dim"):
        check_checkpoint_compatibility(changed_metadata, model, env)
    observation, _ = env.reset()
    while not env.terminated:
        action = masked_predict(model, observation, env.action_masks())
        assert env.action_masks()[action]
        observation, *_ = env.step(action)
    reloaded = MaskablePPOStaticPolicy.load(run_dir / "final_model.zip")
    result = run_static_policy(scenario, reloaded)
    assert result.summary.is_valid and result.placements == env.placements
    assert result.manifest.policy_id == "static_maskable_ppo_v2"


def test_existing_v1_checkpoint_predictions_are_unchanged(tmp_path, manual_static_scenario):
    from sb3_contrib import MaskablePPO
    from berth_allocation_lab.envs import StaticBAPEnv
    from berth_allocation_lab.rl.policy import save_checkpoint

    env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    model = MaskablePPO("MultiInputPolicy", env, seed=3, n_steps=16, batch_size=8, device="cpu")
    observation, _ = env.reset()
    mask = env.action_masks()
    before = masked_predict(model, observation, mask)
    path = save_checkpoint(model, tmp_path / "old.zip", {
        "max_vessels": 3, "time_scale_min": 1440.0, "length_scale_m": 1000.0})
    sidecar = path.with_name("old.metadata.json")
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    record.pop("policy_architecture")
    record.pop("architecture_hyperparameters")
    sidecar.write_text(json.dumps(record), encoding="utf-8")
    loaded, metadata = load_checkpoint(path, expected_architecture="flat_mlp_v1")
    assert "policy_architecture" not in metadata
    assert masked_predict(loaded, observation, mask) == before
    with pytest.raises(CheckpointCompatibilityError, match="policy_architecture"):
        load_checkpoint(path, expected_architecture="candidate_scoring_v2")
