"""Step 9 end-to-end checks with real (tiny-budget) Maskable PPO training."""

import csv
import json
import random
import runpy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sb3_contrib", reason="requires the rl extra")
import torch  # noqa: E402
from sb3_contrib import MaskablePPO  # noqa: E402

from berth_allocation_lab.core import NUMERICAL_TOLERANCE as EPS, find_schedule_violations
from berth_allocation_lab.envs import StaticBAPEnv
from berth_allocation_lab.evaluation import run_static_policy
from berth_allocation_lab.rl import StaticPPOExperimentConfig, build_config_suite, physical_fingerprint
from berth_allocation_lab.rl.evaluation import LearnedPolicyEntry, evaluate_suite, evaluate_training_runs
from berth_allocation_lab.rl.policy import MaskablePPOStaticPolicy, load_checkpoint, masked_predict, save_checkpoint
from berth_allocation_lab.rl.suites import ScenarioSuite
from berth_allocation_lab.rl.training import run_directory, train_static_ppo

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "configs" / "rl" / "static_ppo_smoke.yaml"


@pytest.fixture(scope="module")
def config():
    return StaticPPOExperimentConfig.load_yaml(SMOKE)


@pytest.fixture(scope="module")
def trained(tmp_path_factory, config):
    root = tmp_path_factory.mktemp("rl_runs")
    manifest = train_static_ppo(config, 11, output_root=root, total_timesteps=512, eval_freq=256)
    return run_directory(config, 11, root), manifest


@pytest.fixture(scope="module")
def test_suite(config):
    return build_config_suite(config, config.test)


def parameters(model):
    return torch.cat([p.detach().flatten() for p in model.policy.parameters()])


# A. short learning run

def test_short_training_run_updates_parameters_and_records_metadata(trained, config):
    run_dir, manifest = trained
    assert manifest["status"] == "completed" and manifest["total_timesteps_completed"] == 512
    assert manifest["action_masking_enabled"] is True
    assert manifest["hyperparameters"]["gamma"] == 1.0
    assert manifest["training_reward_scale"] == pytest.approx(1 / 1440)
    assert manifest["training_seed"] == 11 and manifest["device"] == "cpu"
    for name in ("config.yaml", "manifest.json", "final_model.zip", "final_model.metadata.json",
                 "best_validation_model.zip", "training_log.csv", "train_episodes.csv",
                 "validation_metrics.json"):
        assert (run_dir / name).is_file(), name
    log = list(csv.DictReader((run_dir / "training_log.csv").open(encoding="utf-8")))
    assert [int(float(r["n_updates"])) for r in log] == [2, 4]  # n_epochs=2 per rollout
    assert all(np.isfinite(float(r["value_loss"])) for r in log)
    history = json.loads((run_dir / "validation_metrics.json").read_text())["history"]
    assert [h["timesteps"] for h in history] == [0, 256, 512]
    assert all(h["suite_split"] == "validation" and h["valid_count"] == 6 for h in history)

    final, metadata = load_checkpoint(run_dir / "final_model.zip")
    assert type(final.policy).__name__ == "MaskableMultiInputActorCriticPolicy"
    assert metadata["gamma"] == 1.0 and metadata["max_vessels"] == 8
    initial = MaskablePPO("MultiInputPolicy", StaticBAPEnv(scenario=first_test_scenario(config), max_vessels=8),
                          seed=11, device="cpu", policy_kwargs=config.ppo.policy_kwargs())
    assert not torch.equal(parameters(initial), parameters(final))


def first_test_scenario(config):
    return build_config_suite(config, config.test).scenarios[0]


# B/C. masked inference and save/load equivalence

def test_masked_deterministic_inference_completes_held_out_episodes(trained, test_suite):
    run_dir, _ = trained
    model, metadata = load_checkpoint(run_dir / "final_model.zip")
    policy = MaskablePPOStaticPolicy(model, metadata)
    for scenario in test_suite.scenarios:
        env = policy.make_env(scenario)
        observation, _ = env.reset()
        while not env.terminated:
            mask = env.action_masks()
            action = masked_predict(model, observation, mask)
            assert mask[action]
            observation, *_ = env.step(action)
        result = policy.schedule(scenario)
        assert result.placements == env.placements  # deterministic
        assert not find_schedule_violations(scenario.vessels, result.placements,
                                            scenario.berth_length_m, scenario.min_clearance_m)


def test_reloaded_checkpoint_reproduces_predictions(trained, test_suite, tmp_path):
    run_dir, _ = trained
    model, metadata = load_checkpoint(run_dir / "final_model.zip")
    copy_path = save_checkpoint(model, tmp_path / "copy.zip", {k: metadata[k] for k in (
        "experiment_id", "training_run_id", "training_seed", "max_vessels", "time_scale_min",
        "length_scale_m", "reward_scale")})
    reloaded, _ = load_checkpoint(copy_path)
    assert torch.equal(parameters(model), parameters(reloaded))
    for scenario in test_suite.scenarios:
        env = StaticBAPEnv(scenario=scenario, max_vessels=8)
        observation, _ = env.reset()
        while not env.terminated:
            mask = env.action_masks()
            first = masked_predict(model, observation, mask)
            assert masked_predict(reloaded, observation, mask) == first
            observation, *_ = env.step(first)


# D/E/F. adapter, paired evaluation and certified exact gap

def test_adapter_produces_canonical_replayable_records(trained, test_suite):
    run_dir, _ = trained
    policy = MaskablePPOStaticPolicy.load(run_dir / "best_validation_model.zip")
    scenario = test_suite.scenarios[0]
    result = run_static_policy(scenario, policy)
    assert result.summary.is_valid and result.manifest.policy_family == "maskable_ppo"
    assert result.manifest.policy_id == "static_maskable_ppo_v1"
    env = StaticBAPEnv(scenario=scenario, max_vessels=8)
    env.reset()
    for record in result.decisions:
        assert tuple(x for x, _, _ in env.current_candidates) == record.candidate_positions_m
        env.step(record.selected_candidate_index)
    assert env.placements == result.placements
    assert env.final_metrics.objective_value == pytest.approx(result.summary.objective_value, abs=EPS)


def test_paired_evaluation_uses_identical_instances_and_certified_gaps(trained, test_suite):
    run_dir, manifest = trained
    entry = LearnedPolicyEntry("seed_11", 11, manifest["checkpoints"]["final"]["model_id"], "final_model.zip",
                               MaskablePPOStaticPolicy.load(run_dir / "final_model.zip"))
    suite = ScenarioSuite("test", "test", test_suite.scenarios[:3])
    rows = evaluate_suite(suite, [entry])
    by_scenario = {}
    for row in rows:
        by_scenario.setdefault(row["scenario_id"], []).append(row)
    for scenario in suite.scenarios:
        group = by_scenario[scenario.scenario_id]
        assert {r["method"] for r in group} == {"fcfs", "rollout", "exact", "ppo"}
        assert {r["scenario_fingerprint"] for r in group} == {scenario.content_fingerprint}
        exact = next(r for r in group if r["method"] == "exact")
        ppo = next(r for r in group if r["method"] == "ppo")
        assert exact["optimality_status"] == "optimal" and ppo["is_valid"]
        assert ppo["total_waiting_time_min"] >= exact["certified_optimal_objective"] - EPS
        assert ppo["exact_gap_abs_min"] == pytest.approx(
            ppo["total_waiting_time_min"] - exact["certified_optimal_objective"], abs=EPS)
        fcfs = next(r for r in group if r["method"] == "fcfs")
        assert ppo["delta_vs_fcfs_min"] == pytest.approx(
            ppo["total_waiting_time_min"] - fcfs["total_waiting_time_min"], abs=EPS)


# G. dataset isolation and failure classification

def test_training_scenarios_never_touch_evaluation_partitions(trained, config, test_suite):
    run_dir, manifest = trained
    episodes = list(csv.DictReader((run_dir / "train_episodes.csv").open(encoding="utf-8")))
    assert len(episodes) == manifest["training_episodes"] > 0
    assert all(int(e["scenario_seed"]) % 3 == 0 and e["scenario_split"] == "train" for e in episodes)
    assert all(int(e["scenario_seed"]) not in (0, 42) for e in episodes)
    held_out = {physical_fingerprint(s) for s in (*test_suite.scenarios,
                                                  *build_config_suite(config, config.validation).scenarios)}
    assert not held_out & {e["physical_fingerprint"] for e in episodes}
    assert all(s.seed % 3 == 2 for s in test_suite.scenarios)
    assert [r["scenario_fingerprint"] for r in manifest["test_scenario_set_identities"]] == [
        s.content_fingerprint for s in test_suite.scenarios]


def test_existing_run_directory_is_never_overwritten(trained, config):
    run_dir, _ = trained
    with pytest.raises(FileExistsError):
        train_static_ppo(config, 11, output_root=run_dir.parents[1], total_timesteps=256)


def test_run_without_valid_validation_checkpoint_is_failed(config, tmp_path, monkeypatch):
    from berth_allocation_lab.rl import training

    def invalid(policy, suite):
        return {"mean_total_waiting_time_min": None, "valid_count": 0, "scenario_count": len(suite.scenarios),
                "per_scenario": [{"scenario_id": s.scenario_id, "total_waiting_time_min": None,
                                  "error": "RuntimeError: forced"} for s in suite.scenarios]}

    monkeypatch.setattr(training, "validation_waiting", invalid)
    manifest = train_static_ppo(config, 5, output_root=tmp_path, total_timesteps=256, eval_freq=256)
    assert manifest["status"] == "failed" and manifest["failure_type"] == "no_valid_validation_checkpoint"
    assert "best_validation" not in manifest["checkpoints"]
    with pytest.raises(ValueError, match="only completed runs"):
        evaluate_training_runs(config, [run_directory(config, 5, tmp_path)], output_dir=tmp_path / "eval")


def test_interrupted_training_is_recorded_and_not_declared_final(config, tmp_path, monkeypatch):
    def interrupt(self, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(MaskablePPO, "learn", interrupt)
    with pytest.raises(KeyboardInterrupt):
        train_static_ppo(config, 7, output_root=tmp_path, total_timesteps=256)
    run_dir = run_directory(config, 7, tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["status"] == "interrupted"
    assert (run_dir / "interrupted_model.zip").is_file() and not (run_dir / "final_model.zip").exists()


# H. multi-seed workflow through the scripts

@pytest.mark.slow
def test_multi_seed_training_and_evaluation_scripts(config, tmp_path):
    train = runpy.run_path(str(ROOT / "scripts" / "train_static_ppo.py"))["main"]
    evaluate = runpy.run_path(str(ROOT / "scripts" / "evaluate_static_ppo.py"))["main"]
    assert train(["--config", str(SMOKE), "--total-timesteps", "512", "--eval-freq", "256",
                  "--output-dir", str(tmp_path / "runs")]) == 0
    runs = [run_directory(config, seed, tmp_path / "runs") for seed in (11, 23)]
    manifests = [json.loads((r / "manifest.json").read_text()) for r in runs]
    assert [m["training_seed"] for m in manifests] == [11, 23]
    assert manifests[0]["training_run_id"] != manifests[1]["training_run_id"]
    streams = [[e["scenario_id"] for e in csv.DictReader((r / "train_episodes.csv").open(encoding="utf-8"))]
               for r in runs]
    assert streams[0][:5] != streams[1][:5]
    models = [load_checkpoint(r / "final_model.zip")[0] for r in runs]
    assert not torch.equal(parameters(models[0]), parameters(models[1]))

    output = tmp_path / "evaluation"
    assert evaluate(["--config", str(SMOKE), "--experiment-dir", str(tmp_path / "runs" / config.experiment_id),
                     "--output", str(output)]) == 0
    aggregate = json.loads((output / "aggregate.json").read_text())
    cross = next(c for c in aggregate["cross_seed"] if c["suite"] == "test" and c["component"] == "ALL")
    assert cross["n_training_seeds"] == 2 and set(cross["per_seed_mean_total_waiting_time_min"]) == {
        "seed_11", "seed_23"}
    rows = [json.loads(line) for line in (output / "per_instance.jsonl").read_text().splitlines()]
    assert {r["suite"] for r in rows} == {"test", "low_traffic"}
    assert all(r["is_valid"] for r in rows)
    evaluation_manifest = json.loads((output / "evaluation_manifest.json").read_text())
    assert evaluation_manifest["checkpoint_kind"] == "best_validation"
    assert set(evaluation_manifest["training_budgets"].values()) == {512}
    with pytest.raises(FileExistsError):
        evaluate(["--config", str(SMOKE), "--experiment-dir", str(tmp_path / "runs" / config.experiment_id),
                  "--output", str(output)])


# Extended v1 setup: vectorized environments and the test gate

def _vectorized(config, n_envs, vec_env="dummy"):
    return replace(config, ppo=replace(config.ppo, n_envs=n_envs, vec_env=vec_env, n_steps=64, batch_size=64))


def test_vectorized_training_reads_masks_from_every_sub_environment(config, tmp_path):
    from sb3_contrib.common.maskable.utils import get_action_masks
    from berth_allocation_lab.rl.training import _training_vec_env

    vec_config = _vectorized(config, 4)
    vec = _training_vec_env(vec_config, build_config_suite_mixture(vec_config))
    vec.seed(11 * 1000)
    vec.reset()
    masks = get_action_masks(vec)
    inner = [env.unwrapped for env in vec.envs]
    assert masks.shape == (4, 16)
    for row, env in zip(masks, inner):
        np.testing.assert_array_equal(row, env.action_masks())
    assert len({env.scenario.scenario_id for env in inner}) == 4  # distinct sub-environment streams
    vec.close()

    # Masked actions raise inside StaticBAPEnv, so a completed run submitted none.
    manifest = train_static_ppo(vec_config, 11, output_root=tmp_path, total_timesteps=512, eval_freq=256)
    assert manifest["status"] == "completed" and manifest["n_envs"] == 4
    assert manifest["environment_seeds"] == [11000, 11001, 11002, 11003]
    assert manifest["total_timesteps_completed"] == 512
    episodes = list(csv.DictReader((run_directory(vec_config, 11, tmp_path) / "train_episodes.csv").open(
        encoding="utf-8")))
    assert {int(e["env_index"]) for e in episodes} == {0, 1, 2, 3}
    assert all(int(e["scenario_seed"]) % 3 == 0 and e["scenario_split"] == "train" for e in episodes)
    assert sum(manifest["training_episodes_per_env"].values()) == len(episodes)
    assert manifest["split_audit"]["groups"]["train_episodes"] == len(episodes)


def build_config_suite_mixture(vec_config):
    from berth_allocation_lab.rl import build_mixture

    return build_mixture(vec_config.components, "train", vec_config.project_root(), vec_config.max_vessels)


def test_single_environment_seeding_is_unchanged(trained):
    _, manifest = trained
    assert manifest["environment_seeds"] == [11] and manifest["n_envs"] == 1


@pytest.mark.parametrize("n_envs", [1, 2])
def test_progress_preserves_training_history_selection_parameters_and_rng(config, tmp_path, capsys, n_envs):
    short = replace(config, ppo=replace(config.ppo, n_envs=n_envs, n_steps=32,
                                       batch_size=32, n_epochs=1))
    manifests, directories, states = [], [], []
    for enabled in (False, True):
        root = tmp_path / ("visible" if enabled else "quiet")
        manifests.append(train_static_ppo(
            short, 11, output_root=root, total_timesteps=128, eval_freq=64,
            progress=enabled, progress_description="tiny seed 11 (1/2)",
        ))
        directories.append(run_directory(short, 11, root))
        states.append((random.getstate(), np.random.get_state(), torch.get_rng_state()))
        captured = capsys.readouterr()
        assert captured.out == ""
        if enabled:
            assert "tiny seed 11 (1/2)" in captured.err
            assert "learning steps/s" in captured.err and "cache_hits" in captured.err
            for step in (0, 64, 128):
                assert f"timestep={step} validation=" in captured.err
            assert "FCFS=" in captured.err and "Rollout=" in captured.err and "best=" in captured.err
            assert "128/128" in captured.err
        else:
            assert captured.err == ""
    assert all(m["status"] == "completed" for m in manifests)
    assert manifests[0].keys() == manifests[1].keys()
    for field in ("selection", "validation_baselines", "hyperparameters", "environment_seeds",
                  "validation_scenario_set", "test_scenario_set_identities", "split_audit"):
        assert manifests[0][field] == manifests[1][field]
    assert states[0][0] == states[1][0]
    for first, second in zip(states[0][1], states[1][1]):
        np.testing.assert_equal(first, second)
    assert torch.equal(states[0][2], states[1][2])
    assert {p.name for p in directories[0].iterdir()} == {p.name for p in directories[1].iterdir()}
    histories = []
    for directory in directories:
        history = json.loads((directory / "validation_metrics.json").read_text())
        for entry in history["history"]:
            entry.pop("evaluation_seconds")  # wall-clock measurements are not deterministic
        histories.append(history)
        assert "progress" not in json.loads((directory / "manifest.json").read_text())["overrides"]
    assert histories[0] == histories[1]
    for name in ("train_episodes.csv", "training_log.csv"):
        assert (directories[0] / name).read_bytes() == (directories[1] / name).read_bytes()
    for checkpoint in ("final_model.zip", "best_validation_model.zip"):
        first = load_checkpoint(directories[0] / checkpoint)[0]
        second = load_checkpoint(directories[1] / checkpoint)[0]
        assert torch.equal(parameters(first), parameters(second))


def test_evaluation_progress_stays_on_stderr_and_preserves_rows(trained, config, tmp_path, capsys):
    evaluate = runpy.run_path(str(ROOT / "scripts" / "evaluate_static_ppo.py"))["main"]
    run_dir, _ = trained
    results = []
    for enabled in (False, True):
        output = tmp_path / ("visible" if enabled else "quiet")
        args = ["--config", str(SMOKE), "--run-dir", str(run_dir), "--output", str(output),
                "--seeds-per-component", "1"]
        assert evaluate([*args, "--progress"] if enabled else args) == 0
        captured = capsys.readouterr()
        assert "cache_hits" not in captured.out
        if enabled:
            for suite in ("test", "low_traffic"):
                for method in ("FCFS", "Rollout", "Exact", "PPO seed_11"):
                    assert f"{suite} {method}" in captured.err
        else:
            assert captured.err == ""
        rows = [json.loads(line) for line in (output / "per_instance.jsonl").read_text().splitlines()]
        for row in rows:
            row.pop("algorithm_runtime_seconds")
        results.append(rows)
    assert results[0] == results[1]


def test_test_suites_require_the_recorded_decision(trained, config, tmp_path):
    run_dir, _ = trained
    gated = replace(config, require_validation_decision=True)
    with pytest.raises(ValueError, match="requires the recorded validation decision"):
        evaluate_training_runs(gated, [run_dir], output_dir=tmp_path / "gated")
    # Validation-split evaluation is not gated.
    output = evaluate_training_runs(gated, [run_dir], output_dir=tmp_path / "validation", suites=["validation"])
    manifest = json.loads((output / "evaluation_manifest.json").read_text())
    assert manifest["validation_decision"] is None
    assert manifest["integrity"]["masked_action_errors"] == 0 and manifest["integrity"]["invalid_rows"] == 0
    assert manifest["exact_reference_summary"]["certified"] == manifest["exact_reference_summary"]["eligible"]
    assert manifest["reference_cache"]["misses"] == 3 * len(manifest["suites"]["validation"]["identities"])


@pytest.mark.slow
def test_subprocess_vector_environment_option(config, tmp_path):
    manifest = train_static_ppo(_vectorized(config, 2, "subproc"), 23, output_root=tmp_path,
                                total_timesteps=256, eval_freq=256)
    assert manifest["status"] == "completed" and manifest["vec_env"] == "subproc"
    assert manifest["environment_seeds"] == [23000, 23001]
