from __future__ import annotations

from pathlib import Path

from mini_port_sim import RandomStreams
from mini_port_sim.scenario import ServiceConfig, TerminalConfig, TrafficConfig

from berth_allocation_lab.scenarios import (
    SyntheticScenarioConfig,
    SyntheticScenarioGenerator,
)


def test_synthetic_config_uses_project_02_config_types() -> None:
    config = SyntheticScenarioConfig.load_yaml(
        Path("configs/scenarios/synthetic_medium.yaml")
    )

    assert isinstance(config.terminal, TerminalConfig)
    assert isinstance(config.traffic, TrafficConfig)
    assert isinstance(config.service, ServiceConfig)


def test_generator_uses_project_02_random_stream_semantics() -> None:
    config = SyntheticScenarioConfig.load_yaml(
        Path("configs/scenarios/synthetic_medium.yaml")
    )
    instance = SyntheticScenarioGenerator().generate(config)

    streams = RandomStreams(master_seed=config.seed)
    expected_first_length = round(
        streams.get("vessel").uniform(
            config.traffic.min_vessel_length_m,
            config.traffic.max_vessel_length_m,
        ),
        2,
    )

    assert instance.vessels[0].length_m == expected_first_length

