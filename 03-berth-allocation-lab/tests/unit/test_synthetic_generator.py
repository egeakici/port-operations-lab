from __future__ import annotations

import random
from dataclasses import replace
from pathlib import Path

import pytest

from mini_port_sim.scenario import ServiceConfig, TerminalConfig, TrafficConfig

from berth_allocation_lab.scenarios import (
    SCENARIO_SCHEMA_VERSION,
    SYNTHETIC_GENERATOR_VERSION,
    SyntheticScenarioConfig,
    SyntheticScenarioGenerator,
    planned_berth_occupancy_minutes,
)
from berth_allocation_lab.data import BAPScenarioInstance


def _load_config(name: str = "synthetic_medium.yaml") -> SyntheticScenarioConfig:
    return SyntheticScenarioConfig.load_yaml(Path("configs/scenarios") / name)


def test_same_config_and_seed_generate_identical_instance() -> None:
    config = _load_config()
    generator = SyntheticScenarioGenerator()

    first = generator.generate(config)
    second = generator.generate(config)

    assert first == second
    assert first.content_fingerprint == second.content_fingerprint


def test_different_seed_changes_stochastic_content() -> None:
    config = _load_config()
    generator = SyntheticScenarioGenerator()

    first = generator.generate(config)
    second = generator.generate(replace(config, seed=config.seed + 1))

    assert first.vessels != second.vessels


def test_json_round_trip_preserves_instance(tmp_path: Path) -> None:
    instance = SyntheticScenarioGenerator().generate(_load_config())
    output_path = tmp_path / "scenario.json"

    instance.save_json(output_path)
    loaded = BAPScenarioInstance.load_json(output_path)

    assert loaded == instance
    assert loaded.content_fingerprint == instance.content_fingerprint


def test_vessel_ids_and_arrivals_are_deterministic_and_monotonic() -> None:
    instance = SyntheticScenarioGenerator().generate(_load_config())

    assert [vessel.vessel_id for vessel in instance.vessels[:3]] == [
        "V001",
        "V002",
        "V003",
    ]
    assert instance.vessels[0].arrival_time_min == 0.0
    assert tuple(sorted(v.arrival_time_min for v in instance.vessels)) == tuple(
        v.arrival_time_min for v in instance.vessels
    )


def test_generated_values_obey_config_bounds() -> None:
    config = _load_config("synthetic_heavy.yaml")
    instance = SyntheticScenarioGenerator().generate(config)

    assert instance.vessel_count == config.traffic.vessel_count
    for vessel in instance.vessels:
        assert config.traffic.min_vessel_length_m <= vessel.length_m
        assert vessel.length_m <= config.traffic.max_vessel_length_m
        assert vessel.length_m <= config.terminal.berth_length_m
        assert vessel.workload_moves is not None
        assert config.traffic.min_workload_moves <= vessel.workload_moves
        assert vessel.workload_moves <= config.traffic.max_workload_moves


def test_service_time_matches_planned_berth_occupancy_formula() -> None:
    config = _load_config()
    instance = SyntheticScenarioGenerator().generate(config)

    for vessel in instance.vessels:
        assert vessel.workload_moves is not None
        assert vessel.service_time_min == planned_berth_occupancy_minutes(
            service=config.service,
            workload_moves=vessel.workload_moves,
        )


def test_static_dynamic_twin_generation_shares_ground_truth() -> None:
    base = SyntheticScenarioConfig(
        scenario_id="synthetic_twin",
        scenario_version=1,
        scenario_family="twin",
        formulation="static",
        data_provenance="synthetic",
        split="test",
        seed=99,
        terminal=TerminalConfig(),
        traffic=TrafficConfig(vessel_count=6),
        service=ServiceConfig(),
    )
    dynamic = replace(base, formulation="dynamic")
    generator = SyntheticScenarioGenerator()

    static_instance = generator.generate(base)
    dynamic_instance = generator.generate(dynamic)

    assert static_instance.vessels == dynamic_instance.vessels
    assert static_instance.formulation == "static"
    assert dynamic_instance.formulation == "dynamic"


def test_split_and_versions_are_preserved() -> None:
    config = _load_config("synthetic_low.yaml")
    instance = SyntheticScenarioGenerator().generate(config)

    assert instance.split == "train"
    assert instance.data_provenance == "synthetic"
    assert instance.generator_version == SYNTHETIC_GENERATOR_VERSION
    assert instance.scenario_schema_version == SCENARIO_SCHEMA_VERSION


def test_generator_rejects_non_synthetic_provenance() -> None:
    config = _load_config()

    with pytest.raises(ValueError, match="only supports synthetic"):
        replace(config, data_provenance="ais_calibrated")


def test_generator_rejects_vessels_longer_than_berth() -> None:
    with pytest.raises(ValueError, match="Maximum vessel length"):
        SyntheticScenarioConfig(
            scenario_id="invalid",
            scenario_version=1,
            scenario_family="invalid",
            formulation="static",
            data_provenance="synthetic",
            split="test",
            seed=1,
            terminal=TerminalConfig(berth_length_m=200.0),
            traffic=TrafficConfig(
                vessel_count=2,
                min_vessel_length_m=250.0,
                max_vessel_length_m=300.0,
            ),
            service=ServiceConfig(),
        )


def test_static_config_rejects_future_horizon() -> None:
    config = _load_config("synthetic_low.yaml")

    with pytest.raises(ValueError, match="Static synthetic configs"):
        replace(config, future_horizon_min=240.0)


def test_generator_does_not_mutate_global_random_state() -> None:
    random.seed(12345)
    before = random.getstate()

    SyntheticScenarioGenerator().generate(_load_config())

    after = random.getstate()
    assert after == before

