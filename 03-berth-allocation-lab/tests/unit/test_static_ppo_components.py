"""Step 9 components that do not need Stable-Baselines3 or any training."""

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml

from berth_allocation_lab.core import NUMERICAL_TOLERANCE as EPS
from berth_allocation_lab.envs import (
    MixtureScenarioProvider, StaticBAPEnv, SyntheticScenarioProvider, split_of_seed,
)
from berth_allocation_lab.rl import (
    RLConfigError, SplitLeakageError, StaticPPOExperimentConfig, audit_split_isolation,
    build_config_suite, build_config_suites, build_mixture, build_suite, physical_fingerprint,
)
from berth_allocation_lab.rl.decision import (
    ValidationDecisionError, record_validation_decision, seed_outcome, verify_validation_decision,
)
from berth_allocation_lab.rl.evaluation import (
    ReferenceCache, aggregate_rows, evaluate_suite, exact_reference_summary, is_improvement,
    select_checkpoint, validation_waiting,
)
from berth_allocation_lab.rl.suites import (
    HISTORICAL_TINY_FIXTURES, ScenarioSuite, audit_fresh_suites, historical_fixture_fingerprints,
    previously_examined_fingerprints, scenario_identity,
)
from berth_allocation_lab.rl.wrappers import TrainingRewardScale
from berth_allocation_lab.scenarios import SyntheticScenarioConfig
from berth_allocation_lab.solvers import CandidateEnumerationConfig

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"


def raw_config(name="static_ppo_tiny"):
    return yaml.safe_load((CONFIGS / "rl" / f"{name}.yaml").read_text(encoding="utf-8"))


def config_from(data):
    config = StaticPPOExperimentConfig.from_mapping(data)
    return replace(config, source_path=str(CONFIGS / "rl" / "inline.yaml"))


@pytest.fixture(scope="module")
def tiny_config():
    return StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / "static_ppo_tiny.yaml")


def tiny_provider(n, split, excluded=(0, 1, 42)):
    base = SyntheticScenarioConfig.load_yaml(CONFIGS / "scenarios" / "synthetic_tiny_congested.yaml")
    return SyntheticScenarioProvider(replace(base, traffic=replace(base.traffic, vessel_count=n)),
                                     base_scenario_id=f"bap_tiny_n{n}", split=split,
                                     excluded_seeds=frozenset(excluded))


# Configuration

@pytest.mark.parametrize("name", ["static_ppo_smoke", "static_ppo_tiny", "static_ppo_medium_heavy"])
def test_shipped_configs_validate_and_resolve(name):
    config = StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / f"{name}.yaml")
    assert config.ppo.gamma == 1.0 and config.ppo.policy == "MultiInputPolicy"
    assert config.reward_scale == pytest.approx(1 / 1440)
    assert config.project_root() == ROOT
    assert len(config.training.training_seeds) >= 2
    json.dumps(config.to_dict())  # serializable for run artifacts


def test_gamma_defaults_to_one_when_omitted():
    data = raw_config()
    del data["ppo"]["gamma"]
    assert config_from(data).ppo.gamma == 1.0


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d.update(unknown_field=1), "Unknown experiment"),
    (lambda d: d["ppo"].update(policy="MlpPolicy"), "MultiInputPolicy"),
    (lambda d: d["ppo"].update(gamma=0.99), "alternative_training_objective"),
    (lambda d: d["ppo"].update(gamma=1.5), r"\(0, 1\]"),
    (lambda d: d["ppo"].update(batch_size=1024), "batch_size"),
    (lambda d: d["ppo"].update(n_envs=0), "n_envs"),
    (lambda d: d["ppo"].update(vec_env="ray"), "vec_env"),
    (lambda d: d["ppo"].update(n_envs=2, n_steps=32, batch_size=128), "batch_size"),
    (lambda d: d["test"].update(first_seed=-1), "first_seed"),
    (lambda d: d.update(seed_exclusive_suites="yes"), "seed_exclusive_suites"),
    (lambda d: d["ppo"].update(learning_rate=0), "learning_rate"),
    (lambda d: d["ppo"].update(lr=1), "Unknown ppo"),
    (lambda d: d.update(reward_scale=-1.0), "reward_scale"),
    (lambda d: d.update(reward_scale=float("nan")), "reward_scale"),
    (lambda d: d["training"].update(training_seeds=[11, 11]), "distinct"),
    (lambda d: d["training"].update(total_timesteps=0), "total_timesteps"),
    (lambda d: d.update(components=[]), "component"),
    (lambda d: d["components"].append(dict(d["components"][0])), "distinct"),
    (lambda d: d["components"][0].update(weight=0), "weight"),
    (lambda d: d.update(max_vessels=0), "max_vessels"),
    (lambda d: d.update(policy_id="other"), "policy_id"),
    (lambda d: d["validation"].update(seeds_per_component=0), "seeds_per_component"),
])
def test_invalid_configs_are_rejected_before_training(mutate, message):
    data = copy.deepcopy(raw_config())
    mutate(data)
    with pytest.raises(RLConfigError, match=message):
        config_from(data)


def test_alternative_gamma_must_be_labelled():
    data = raw_config()
    data["ppo"].update(gamma=0.99, alternative_training_objective=True)
    assert config_from(data).ppo.gamma == 0.99


def test_dynamic_presets_require_explicit_static_twin(tiny_config):
    data = raw_config("static_ppo_medium_heavy")
    data["components"][0]["static_twin"] = False
    config = config_from(data)
    with pytest.raises(RLConfigError, match="static_twin"):
        build_mixture(config.components, "train", ROOT, config.max_vessels)


def test_capacity_must_cover_every_component():
    data = raw_config()
    data["max_vessels"] = 7
    config = config_from(data)
    with pytest.raises(RLConfigError, match="max_vessels"):
        build_mixture(config.components, "train", ROOT, config.max_vessels)


# Split-aware mixture and identities

def test_mixture_selection_is_deterministic_and_seed_preserving():
    mixture = MixtureScenarioProvider([tiny_provider(n, "train") for n in (6, 7, 8)], [1, 1, 1])
    for seed in (3, 6, 300, 123456789):
        first, second = mixture(seed), mixture(seed)
        assert first == second and first.seed == seed and first.split == "train"
        component = mixture.component_for(seed)
        assert first.vessel_count == component.vessel_count
        assert first.scenario_id == f"{component.base_scenario_id}_train_seed{seed}"
    # Regression anchor for the documented sha256(seed // 3) rule.
    assert [mixture.component_for(3 * u).base_scenario_id for u in range(1, 7)] == [
        mixture.component_for(3 * u + 1).base_scenario_id for u in range(1, 7)]


def test_mixture_weights_shape_component_frequencies():
    mixture = MixtureScenarioProvider([tiny_provider(6, "train"), tiny_provider(8, "train")], [3, 1])
    picks = [mixture.component_for(3 * u).vessel_count for u in range(4000)]
    assert picks.count(6) / len(picks) == pytest.approx(0.75, abs=0.03)


def test_mixture_rejects_mixed_splits_and_bad_weights():
    with pytest.raises(ValueError, match="same split"):
        MixtureScenarioProvider([tiny_provider(6, "train"), tiny_provider(7, "test")], [1, 1])
    with pytest.raises(ValueError, match="positive"):
        MixtureScenarioProvider([tiny_provider(6, "train")], [0])
    with pytest.raises(ValueError, match="one weight"):
        MixtureScenarioProvider([tiny_provider(6, "train")], [1, 1])
    with pytest.raises(ValueError, match="distinct"):
        MixtureScenarioProvider([tiny_provider(6, "train"), tiny_provider(6, "train")], [1, 1])


def test_split_specific_generation_and_partition_separation():
    mixtures = {s: MixtureScenarioProvider([tiny_provider(n, s) for n in (6, 7, 8)], [1, 1, 1])
                for s in ("train", "validation", "test")}
    rng = np.random.default_rng(5)
    for split, mixture in mixtures.items():
        seeds = [mixture.sample_seed(rng) for _ in range(300)]
        assert all(split_of_seed(s) == split for s in seeds)
        for other, other_mixture in mixtures.items():
            if other != split:
                with pytest.raises(ValueError, match="belongs to"):
                    other_mixture(seeds[0])


def test_reserved_historical_seeds_are_never_sampled_or_built():
    provider = tiny_provider(6, "train")
    with pytest.raises(ValueError, match="reserved"):
        provider(42)

    class Fixed:
        def __init__(self, values):
            self.values = iter(values)

        def integers(self, low, high):
            return next(self.values)

    # u=14 -> seed 42 (reserved) is skipped, u=15 -> 45 is returned.
    assert provider.sample_seed(Fixed([14, 15])) == 45
    mixture = MixtureScenarioProvider([tiny_provider(n, "train") for n in (6, 7, 8)], [1, 1, 1])
    # Seeds 0 and 42 are reserved in every tiny component, whichever one is selected.
    assert mixture.sample_seed(Fixed([0, 14, 15])) == 45


def test_training_stream_is_deterministic_per_seed():
    mixture = MixtureScenarioProvider([tiny_provider(n, "train") for n in (6, 7, 8)], [1, 1, 1])

    def stream(seed):
        env = StaticBAPEnv(scenario_provider=mixture, max_vessels=8)
        ids = [env.reset(seed=seed)[1]["scenario_id"]]
        ids += [env.reset()[1]["scenario_id"] for _ in range(5)]
        return ids

    assert stream(11) == stream(11)
    assert stream(11) != stream(23)
    assert len(set(stream(11))) == 6


def test_fixed_observation_capacity_across_tiny_sizes():
    mixture = MixtureScenarioProvider([tiny_provider(n, "train") for n in (6, 7, 8)], [1, 1, 1])
    env = StaticBAPEnv(scenario_provider=mixture, max_vessels=8)
    sizes = set()
    for seed in range(12):
        obs, _ = env.reset(seed=seed)
        sizes.add(env.scenario.vessel_count)
        assert env.observation_space.contains(obs) and env.action_space.n == 16
    assert sizes == {6, 7, 8}


# Suites and leakage audit

def test_suites_are_reproducible_split_specific_and_skip_fixtures(tiny_config):
    first = build_config_suite(tiny_config, tiny_config.validation)
    again = build_config_suite(tiny_config, tiny_config.validation)
    assert first.identities() == again.identities()
    assert len(first.scenarios) == 18 and first.split == "validation"
    assert all(s.seed % 3 == 1 and s.split == "validation" for s in first.scenarios)
    counts = {}
    for s in first.scenarios:
        counts[s.vessel_count] = counts.get(s.vessel_count, 0) + 1
    assert counts == {6: 6, 7: 6, 8: 6}
    historical = historical_fixture_fingerprints(ROOT)
    assert len(historical) == len(HISTORICAL_TINY_FIXTURES)
    assert not {physical_fingerprint(s) for s in first.scenarios} & historical
    test = build_config_suite(tiny_config, tiny_config.test)
    assert all(s.seed % 3 == 2 for s in test.scenarios)
    assert {s.scenario_id for s in first.scenarios}.isdisjoint({s.scenario_id for s in test.scenarios})


def test_explicit_suite_seeds_must_follow_partition(tiny_config):
    mixture = build_mixture(tiny_config.components, "test", ROOT, 8)
    suite = build_suite("test", mixture, seeds=[2, 5, 8])
    assert [s.seed for s in suite.scenarios] == [2, 5, 8]
    with pytest.raises(ValueError, match="not a test seed"):
        build_suite("test", mixture, seeds=[2, 13])
    with pytest.raises(ValueError, match="distinct"):
        build_suite("test", mixture, seeds=[2, 2])


def test_audit_detects_every_prohibited_overlap(tiny_config):
    validation = build_config_suite(tiny_config, tiny_config.validation).identities()
    test = build_config_suite(tiny_config, tiny_config.test).identities()
    historical = historical_fixture_fingerprints(ROOT)
    summary = audit_split_isolation({"validation": validation, "test": test}, historical)
    assert summary["groups"] == {"validation": 18, "test": 30}

    leaked = dict(test[0], scenario_split="train", scenario_seed=3,
                  scenario_id=test[0]["scenario_id"].replace("_test_seed2", "_train_seed3"))
    with pytest.raises(SplitLeakageError, match="repeats"):
        audit_split_isolation({"train_episodes": [leaked], "test": test})
    relabelled = dict(test[0], scenario_split="train")
    with pytest.raises(SplitLeakageError, match="Inconsistent identity"):
        audit_split_isolation({"train_episodes": [relabelled]})
    clash = dict(test[1], scenario_id=test[0]["scenario_id"])
    with pytest.raises(SplitLeakageError, match="Inconsistent identity|two different"):
        audit_split_isolation({"test": [test[0], clash]})

    base = SyntheticScenarioConfig.load_yaml(CONFIGS / "scenarios" / "synthetic_tiny_congested.yaml")
    fixture = SyntheticScenarioProvider(base, base_scenario_id="bap_tiny_n6", split="train")(42)
    with pytest.raises(SplitLeakageError, match="Step 7 fixture"):
        audit_split_isolation({"train_episodes": [scenario_identity(fixture)]}, historical)


# Training-only reward scale

def test_reward_wrapper_scales_training_signal_only(manual_static_scenario):
    raw_env = StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3)
    env = TrainingRewardScale(StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3), 1 / 1440)
    raw_env.reset()
    env.reset()
    scaled, raw = [], []
    for action in (0, 0, 0):
        np.testing.assert_array_equal(env.action_masks(), raw_env.action_masks())
        _, reward, terminated, _, info = env.step(action)
        _, raw_reward, *_ = raw_env.step(action)
        assert info["raw_reward"] == raw_reward and reward == pytest.approx(raw_reward / 1440)
        scaled.append(reward)
        raw.append(raw_reward)
    assert terminated and info["scenario_id"] == "manual_static_001"
    assert info["physical_fingerprint"] == physical_fingerprint(manual_static_scenario)
    assert info["episode_return"] == sum(raw) == -1100.0  # canonical return is untouched
    assert env.unwrapped.episode_return == -1100.0
    for bad in (0.0, -1.0, float("inf"), True):
        with pytest.raises(ValueError):
            TrainingRewardScale(StaticBAPEnv(scenario=manual_static_scenario, max_vessels=3), bad)


# Selection, gaps and failure records

def test_checkpoint_selection_rule():
    history = [
        {"timesteps": 0, "mean_total_waiting_time_min": 100.0},
        {"timesteps": 10, "mean_total_waiting_time_min": None},  # invalid schedules
        {"timesteps": 20, "mean_total_waiting_time_min": 90.0},
        {"timesteps": 30, "mean_total_waiting_time_min": 90.0 + EPS / 2},  # tie keeps earlier
        {"timesteps": 40, "mean_total_waiting_time_min": 95.0},
    ]
    assert select_checkpoint(history)["timesteps"] == 20
    assert select_checkpoint(list(reversed(history)))["timesteps"] == 20
    assert select_checkpoint([{"timesteps": 0, "mean_total_waiting_time_min": None}]) is None
    assert is_improvement(1.0, None) and not is_improvement(None, 1.0) and not is_improvement(1.0, 1.0)


def test_selection_refuses_test_evaluations():
    with pytest.raises(ValueError, match="validation evaluations only"):
        select_checkpoint([{"timesteps": 0, "mean_total_waiting_time_min": 1.0, "suite_split": "test"}])


class _FailingPolicy:
    policy_id = "static_maskable_ppo_v1"
    policy_family = "maskable_ppo"
    algorithm_version = "v1"

    def schedule(self, scenario):
        raise RuntimeError("controlled inference failure")


def test_failed_policy_rows_carry_no_fabricated_metrics(manual_static_scenario):
    from berth_allocation_lab.rl.evaluation import LearnedPolicyEntry

    suite = ScenarioSuite("test", "test", (replace(manual_static_scenario, split="test", seed=2,
                                                   scenario_id="manual_test_seed2"),))
    entry = LearnedPolicyEntry("seed_1", 1, "ckpt", "ckpt.zip", _FailingPolicy())
    rows = evaluate_suite(suite, [entry])
    ppo = next(r for r in rows if r["method"] == "ppo")
    assert ppo["is_valid"] is False and ppo["run_status"] == "failed"
    assert ppo["failure_type"] == "RuntimeError"
    assert all(ppo[k] is None for k in ("total_waiting_time_min", "mean_waiting_time_min",
                                         "delta_vs_fcfs_min", "delta_vs_rollout_min", "exact_gap_abs_min"))
    stats = next(g for g in aggregate_rows(rows)["groups"] if g["method"] == "ppo[seed_1]"
                 and g["component"] == "ALL")
    assert stats["n_invalid"] == 1 and stats["mean_total_waiting_time_min"] is None
    assert validation_waiting(_FailingPolicy(), suite)["mean_total_waiting_time_min"] is None


def test_exact_gaps_require_certification_and_handle_zero_optimum(manual_static_scenario, monkeypatch):
    from berth_allocation_lab.policies import StaticFCFS

    suite = ScenarioSuite("test", "test", (replace(manual_static_scenario, split="test", seed=2,
                                                   scenario_id="manual_test_seed2"),))
    rows = evaluate_suite(suite, [])
    exact = next(r for r in rows if r["method"] == "exact")
    fcfs = next(r for r in rows if r["method"] == "fcfs")
    assert exact["optimality_status"] == "optimal" and exact["certified_optimal_objective"] == 0.0
    # Zero certified optimum, positive heuristic waiting: absolute gap only.
    assert fcfs["exact_gap_abs_min"] == 900.0 and fcfs["exact_gap_rel"] is None
    stats = next(g for g in aggregate_rows(rows)["groups"] if g["method"] == "fcfs" and g["component"] == "ALL")
    assert stats["n_exact_gap_rel_undefined"] == 1

    from berth_allocation_lab.solvers import CandidateEnumerationConfig
    uncertified = evaluate_suite(suite, [], exact_config=CandidateEnumerationConfig(max_search_nodes=2))
    exact = next(r for r in uncertified if r["method"] == "exact")
    assert exact["optimality_status"] == "feasible" and exact["total_waiting_time_min"] is None
    assert all(r["exact_gap_abs_min"] is None and r["exact_certified"] is False for r in uncertified)


def test_aggregate_reports_per_seed_and_cross_seed_spread():
    def row(label, value, component="c"):
        return {"suite": "test", "component": component, "method": "ppo", "ppo_label": label,
                "is_valid": True, "total_waiting_time_min": value, "delta_vs_fcfs_min": value - 10,
                "delta_vs_rollout_min": None, "exact_certified": False, "exact_gap_abs_min": None,
                "exact_gap_rel": None, "algorithm_runtime_seconds": 0.1}

    aggregate = aggregate_rows([row("seed_1", 10.0), row("seed_1", 20.0), row("seed_2", 40.0)])
    cross = next(c for c in aggregate["cross_seed"] if c["component"] == "ALL")
    assert cross["per_seed_mean_total_waiting_time_min"] == {"seed_1": 15.0, "seed_2": 40.0}
    assert cross["mean_of_seed_means"] == 27.5 and cross["std_of_seed_means"] == pytest.approx(17.6776695)
    seed_1 = next(g for g in aggregate["groups"] if g["method"] == "ppo[seed_1]" and g["component"] == "c")
    assert (seed_1["n"], seed_1["median_total_waiting_time_min"], seed_1["mean_delta_vs_fcfs_min"]) == (2, 15.0, 5.0)


# Extended v1: seed independence, freshness, references and decision rule

EXTENDED = ("static_ppo_tiny_extended", "static_ppo_medium_heavy_extended")


def test_shared_vessel_streams_make_seed_exclusivity_necessary():
    # Same seed: the 6-vessel tiny instance is the 8-vessel instance's prefix.
    n6, n8 = tiny_provider(6, "test")(5), tiny_provider(8, "test")(5)
    assert n8.vessels[:6] == n6.vessels


@pytest.mark.parametrize("name", EXTENDED)
def test_extended_suites_never_reuse_a_seed_within_a_split(name):
    config = StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / f"{name}.yaml")
    suites = build_config_suites(config)
    components = len(config.components)
    assert len(suites["validation"].scenarios) == 20 * components
    assert len(suites["test"].scenarios) == 50 * components
    seen = {}
    for suite in suites.values():
        for scenario in suite.scenarios:
            key = (suite.split, scenario.seed)
            assert key not in seen, f"seed {scenario.seed} in {seen.get(key)} and {suite.name}"
            seen[key] = suite.name
            assert split_of_seed(scenario.seed) == suite.split
    assert build_config_suites(config)["test"].identities() == suites["test"].identities()


@pytest.mark.parametrize("name", EXTENDED)
def test_extended_suites_are_fresh_relative_to_the_pilot(name):
    config = StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / f"{name}.yaml")
    examined = previously_examined_fingerprints(config)
    assert len(examined) == 90  # distinct physical instances of the three pilot configs
    assert audit_fresh_suites(build_config_suites(config).values(), examined)["checked_instances"] > 0
    stale = replace(config, test=replace(config.test, first_seed=0))
    with pytest.raises(SplitLeakageError, match="already examined"):
        audit_fresh_suites(build_config_suites(stale).values(), examined)


def test_pilot_configs_keep_their_original_suites(tiny_config):
    assert not tiny_config.seed_exclusive_suites
    assert build_config_suites(tiny_config)["test"].identities() == build_config_suite(
        tiny_config, tiny_config.test).identities()


def test_explicit_seeds_cannot_reuse_a_split_seed():
    mixture = MixtureScenarioProvider([tiny_provider(n, "test") for n in (6, 7, 8)], [1, 1, 1])
    used = set()
    build_suite("a", mixture, seeds=[2, 5], used_seeds=used)
    with pytest.raises(SplitLeakageError, match="already used"):
        build_suite("b", mixture, seeds=[5, 8], used_seeds=used)


def test_reference_cache_computes_each_instance_once(manual_static_scenario):
    scenario = replace(manual_static_scenario, split="test", seed=2, scenario_id="manual_test_seed2")
    cache = ReferenceCache()
    rows = evaluate_suite(ScenarioSuite("test", "test", (scenario,)), [], reference_cache=cache)
    again = evaluate_suite(ScenarioSuite("diag", "test", (scenario,)), [], reference_cache=cache)
    assert (cache.misses, cache.hits) == (3, 3)
    assert [r["total_waiting_time_min"] for r in rows] == [r["total_waiting_time_min"] for r in again]
    assert exact_reference_summary(rows) == {
        "eligible": 1, "certified": 1, "limit_stopped": 0, "failed": 0, "not_eligible": 0}
    limited = evaluate_suite(ScenarioSuite("test", "test", (scenario,)), [],
                             exact_config=CandidateEnumerationConfig(max_search_nodes=2))
    assert exact_reference_summary(limited)["limit_stopped"] == 1


def _fake_run(root, seed, ppo, fcfs, rollout, config, status="completed"):
    run = root / f"seed_{seed}"
    run.mkdir(parents=True)
    (run / "best_validation_model.zip").write_bytes(f"weights-{seed}".encode())
    (run / "manifest.json").write_text(json.dumps({
        "status": status, "training_seed": seed, "experiment_id": config.experiment_id,
        "config_sha256": config.source_sha256, "git_commit_hash": "abc", "git_dirty": False,
        "total_timesteps_completed": 1000,
        "selection": {"selected_timesteps": 500, "selected_mean_total_waiting_time_min": ppo},
        "validation_baselines": {"fcfs_mean_total_waiting_time_min": fcfs,
                                 "rollout_mean_total_waiting_time_min": rollout},
        "checkpoints": {"best_validation": {"path": "best_validation_model.zip",
                                            "model_id": f"run{seed}/best_validation@500"}},
    }), encoding="utf-8")
    return run


def test_decision_rule_thresholds_and_edge_cases():
    # Tiny: (FCFS - PPO) / (FCFS - Rollout) >= 0.25; undefined ratio never passes.
    assert seed_outcome("tiny", 75.0, 100.0, 0.0) == {"gap_closure": 0.25, "passes": True}
    assert seed_outcome("tiny", 76.0, 100.0, 0.0)["passes"] is False
    assert seed_outcome("tiny", 50.0, 100.0, 100.0) == {"gap_closure": None, "passes": False}
    assert seed_outcome("tiny", None, 100.0, 0.0)["passes"] is False
    # MEDIUM/HEAVY: PPO <= 1.10 * FCFS.
    assert seed_outcome("medium_heavy", 110.0, 100.0, 50.0)["passes"] is True
    assert seed_outcome("medium_heavy", 110.5, 100.0, 50.0)["passes"] is False


def test_decision_is_recorded_once_and_verified(tmp_path):
    tiny = StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / "static_ppo_tiny_extended.yaml")
    heavy = StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / "static_ppo_medium_heavy_extended.yaml")
    # Tiny: seeds 11 and 23 close >= 25 % of the gap; MEDIUM/HEAVY: only seed 11 within 10 % of FCFS.
    tiny_runs = [_fake_run(tmp_path / "tiny", s, p, 3000.0, 2600.0, tiny)
                 for s, p in ((11, 2850.0), (23, 2899.0), (37, 2950.0))]
    heavy_runs = [_fake_run(tmp_path / "mh", s, p, 1000.0, 800.0, heavy)
                  for s, p in ((11, 1090.0), (23, 1500.0), (37, 9000.0))]
    output = tmp_path / "decision" / "validation_decision.json"
    decision = record_validation_decision(tiny, tiny_runs, heavy, heavy_runs, output)
    assert decision["regimes"]["tiny"]["criterion_met"] is True
    assert decision["regimes"]["tiny"]["passing_seeds"] == 2
    assert decision["regimes"]["medium_heavy"]["criterion_met"] is False
    assert "candidate-scoring v2" in decision["conclusion"]
    assert decision["final_testing_permitted"] is True and decision["uses_test_results"] is False
    assert output.with_name(output.name + ".sha256").read_text().split()[0] == decision["sha256"]
    with pytest.raises(FileExistsError):
        record_validation_decision(tiny, tiny_runs, heavy, heavy_runs, output)

    hashes = {"run11/best_validation@500": hashlib.sha256(b"weights-11").hexdigest()}
    assert verify_validation_decision(output, tiny, hashes)["criterion_met"] is True
    with pytest.raises(ValidationDecisionError, match="not the recorded selection"):
        verify_validation_decision(output, tiny, {"run11/best_validation@500": "0" * 64})
    output.write_text(output.read_text().replace('"criterion_met": false', '"criterion_met": true'))
    with pytest.raises(ValidationDecisionError, match="SHA-256"):
        verify_validation_decision(output, tiny, hashes)


def test_incomplete_campaign_does_not_permit_testing(tmp_path):
    tiny = StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / "static_ppo_tiny_extended.yaml")
    heavy = StaticPPOExperimentConfig.load_yaml(CONFIGS / "rl" / "static_ppo_medium_heavy_extended.yaml")
    tiny_runs = [_fake_run(tmp_path / "tiny", s, 2800.0, 3000.0, 2600.0, tiny) for s in (11, 23)]
    heavy_runs = [_fake_run(tmp_path / "mh", s, 900.0, 1000.0, 800.0, heavy, status=st)
                  for s, st in ((11, "completed"), (23, "completed"), (37, "interrupted"))]
    decision = record_validation_decision(tiny, tiny_runs, heavy, heavy_runs, tmp_path / "d.json")
    assert decision["final_testing_permitted"] is False and decision["conclusion"] is None
    assert any("differ from configured" in p for p in decision["regimes"]["tiny"]["problems"])
    assert any("interrupted" in p for p in decision["regimes"]["medium_heavy"]["problems"])
