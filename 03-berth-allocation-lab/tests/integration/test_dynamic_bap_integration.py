"""Dynamic provider, generated scenarios and deterministic online replay."""

from dataclasses import replace

import pytest
import numpy as np

from berth_allocation_lab.core import total_waiting_time
from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.envs import (
    DynamicBAPEnv, DynamicSyntheticScenarioProvider, MixtureScenarioProvider,
    SyntheticScenarioProvider, split_of_seed,
)
from berth_allocation_lab.policies.dynamic_fcfs import run_online_fcfs
from berth_allocation_lab.scenarios import SyntheticScenarioConfig
from berth_allocation_lab.scenarios import SyntheticScenarioGenerator


def config(family):
    cfg = SyntheticScenarioConfig.load_yaml(f"configs/scenarios/synthetic_{family}.yaml")
    if family == "low":
        cfg = replace(cfg.with_formulation("dynamic"), future_horizon_min=240.0,
                      scenario_id="synthetic_low_dynamic")
    return cfg


@pytest.mark.parametrize("family", ["low", "medium", "heavy"])
@pytest.mark.parametrize("horizon", [0.0, 240.0])
def test_generated_online_fcfs_replay(family, horizon):
    cfg = config(family)
    provider = DynamicSyntheticScenarioProvider(cfg, f"dynamic_{family}", "test")
    assert provider(2).content_fingerprint == provider(2).content_fingerprint
    assert split_of_seed(provider.sample_seed(np.random.default_rng(7))) == "test"
    env = DynamicBAPEnv(scenario_provider=provider, max_vessels=cfg.traffic.vessel_count,
                        future_horizon_min=horizon)
    _, reward1, info1 = run_online_fcfs(env, seed=5)
    events1 = env.event_records
    placements1 = env.placements
    assert env.terminated and not env.truncated
    assert env.observation_space.contains(env._observation())
    assert reward1 == pytest.approx(-total_waiting_time(env._scenario.vessels, placements1))
    assert len(placements1) == cfg.traffic.vessel_count
    _, reward2, info2 = run_online_fcfs(env, seed=5)
    assert reward2 == reward1
    assert events1 == env.event_records
    assert placements1 == env.placements
    assert info1["scenario_fingerprint"] == info2["scenario_fingerprint"]


def test_dynamic_provider_guards_and_mixture():
    low = config("low")
    assert low.future_horizon_min == 240
    with pytest.raises(ValueError):
        SyntheticScenarioProvider(low, "static", "test")
    with pytest.raises(ValueError):
        DynamicSyntheticScenarioProvider(low.with_formulation("static"), "bad", "test")
    no_horizon = DynamicSyntheticScenarioProvider(replace(low, future_horizon_min=None),
                                                   "no_horizon", "test")
    missing = no_horizon(2)
    with pytest.raises(ValueError):
        DynamicBAPEnv(scenario=missing, max_vessels=low.traffic.vessel_count)
    DynamicBAPEnv(scenario=missing, max_vessels=low.traffic.vessel_count,
                  future_horizon_min=0).reset()
    provider = DynamicSyntheticScenarioProvider(low, "dynamic_low", "test",
                                                 excluded_seeds=frozenset({2}))
    with pytest.raises(ValueError):
        provider(2)
    with pytest.raises(ValueError):
        provider(1)
    other = DynamicSyntheticScenarioProvider(config("medium"), "dynamic_medium", "test")
    mix = MixtureScenarioProvider((provider, other), (1.0, 1.0))
    generated = mix(mix.sample_seed(np.random.default_rng(9)))
    assert generated.formulation == "dynamic" and generated.split == "test"


def test_provider_rng_stream_and_instance_immutability():
    cfg = config("low")
    provider = DynamicSyntheticScenarioProvider(cfg, "dynamic_low", "train")
    first = DynamicBAPEnv(scenario_provider=provider, max_vessels=cfg.traffic.vessel_count)
    second = DynamicBAPEnv(scenario_provider=provider, max_vessels=cfg.traffic.vessel_count)
    seeds = []
    for env in (first, second):
        _, start = env.reset(seed=47)
        _, continuation = env.reset(seed=None)
        seeds.append((start["scenario_seed"], continuation["scenario_seed"]))
    assert seeds[0] == seeds[1]
    assert seeds[0][0] != seeds[0][1]
    instance = provider(3)
    fingerprint = instance.content_fingerprint
    env = DynamicBAPEnv(scenario=instance, max_vessels=cfg.traffic.vessel_count)
    run_online_fcfs(env)
    assert instance.content_fingerprint == fingerprint
    assert provider(3).content_fingerprint == fingerprint


def test_generated_drain_limit_is_configurable():
    cfg = replace(config("low"), max_drain_extension_min=1.0)
    generated = SyntheticScenarioGenerator().generate(cfg)
    assert generated.max_drain_extension_min == 1.0
    assert BAPScenarioInstance.from_dict(generated.to_dict()).content_fingerprint == generated.content_fingerprint
