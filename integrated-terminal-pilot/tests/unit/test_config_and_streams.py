"""Generator configuration, decision register and keyed random streams (tests 33-35)."""

from __future__ import annotations

import copy
import hashlib

import pytest

from integrated_terminal_pilot.scenarios.config import (
    GeneratorConfigError, build_generator_config, leaf_paths,
)
from integrated_terminal_pilot.scenarios.random_streams import KeyedStreams
from integrated_terminal_pilot.scenarios.validation import SEED_BANDS
from tests.conftest import mutated_config, raw_config


def test_default_config_loads_with_full_decision_coverage(config):
    leaves = [p for p in leaf_paths(config.parameters) if p != "config_schema_version"]
    covered = set()
    for record in config.decisions:
        for path in record["parameter_paths"]:
            covered.update(leaf for leaf in leaves if leaf == path or leaf.startswith(path + "."))
    assert covered == set(leaves)
    counts = config.decision_status_counts()
    assert counts["FROZEN"] > 0 and counts["PROPOSED_PENDING_REVIEW"] > 0 and counts["BLOCKED"] == 1


def test_seed_bands_match_protocol(config):
    for split, band in SEED_BANDS.items():
        assert config.seed_band(split) == band


def test_uncovered_parameter_is_rejected():
    params, register = raw_config()
    register["records"] = [r for r in register["records"] if r["decision_id"] != "S2-052"]
    with pytest.raises(GeneratorConfigError, match="without a decision record"):
        build_generator_config(params, register)


def test_decision_value_must_equal_configured_value():
    params, register = raw_config()
    params["cargo"]["forty_ft_share"] = 0.5
    with pytest.raises(GeneratorConfigError, match="differs from configuration"):
        build_generator_config(params, register)


def test_invented_value_cannot_be_labelled_frozen():
    params, register = raw_config()
    record = next(r for r in register["records"] if r["decision_id"] == "S2-052")
    record["status"] = "FROZEN"
    with pytest.raises(GeneratorConfigError, match="may be FROZEN"):
        build_generator_config(params, register)


@pytest.mark.parametrize("changes, message", [
    ({"physics_profiles.standard_v1.service.service_minutes_per_move": 0.6}, "D20"),
    ({"physics_profiles.standard_v1.visibility.future_horizon_min": 120.0}, "D18"),
    ({"physics_profiles.standard_v1.crane.productivity_factor": 0.9}, "D19"),
    ({"seed_bands.validation": {"first": 10_500_000, "last": 11_999_999}}, "overlap"),
    ({"families.itp_low.yard.bay_count": 41}, "even"),
    ({"families.itp_low.yard.capacity_teu": 2300.0}, "operating fill limit"),
    ({"families.itp_low.terminal.max_cranes_per_vessel": 5}, "max_cranes_per_vessel"),
    ({"families.itp_low.traffic.max_vessel_length_m": 1300.0}, "exceeds quay length"),
    ({"physics_profiles.degenerate_equivalence_v1.quay_crane_moves_per_hour": 100.0}, "Step 1 profile"),
])
def test_invalid_configuration_is_rejected(changes, message):
    with pytest.raises(GeneratorConfigError, match=message):
        mutated_config(changes)


def test_yaml_and_memory_configs_have_same_fingerprint(config):
    params, register = raw_config()
    assert build_generator_config(params, register).parameters_fingerprint == config.parameters_fingerprint


def test_stream_seed_follows_frozen_protocol_formula():
    streams = KeyedStreams("itp_medium", "development", 10_000_000)
    key = "itp_v1|itp_medium|development|10000000|vessel|V007|length"
    expected = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
    assert streams.key("vessel", "V007", "length") == key
    assert streams.seed_for("vessel", "V007", "length") == expected


def test_streams_are_independent_per_key_and_reproducible():
    a = KeyedStreams("itp_medium", "development", 10_000_000)
    b = KeyedStreams("itp_medium", "development", 10_000_000)
    assert a.rng("vessel", "V001", "length").random() == b.rng("vessel", "V001", "length").random()
    # Consuming many draws from one key never changes another key's draw.
    first = a.rng("container", "V001/discharge/0000", "weight").random()
    noisy = a.rng("container", "V001/discharge/0000", "size")
    [noisy.random() for _ in range(1000)]
    assert a.rng("container", "V001/discharge/0000", "weight").random() == first
    seeds = {a.seed_for("vessel", f"V{i:03d}", attr) for i in range(1, 25)
             for attr in ("interarrival", "length", "workload", "discharge_share")}
    assert len(seeds) == 96


def test_stream_key_rejects_separator_injection():
    with pytest.raises(ValueError):
        KeyedStreams("itp|medium", "development", 1)
    with pytest.raises(ValueError):
        KeyedStreams("itp_medium", "development", 1).seed_for("vessel", "V001|x", "length")


def test_families_differ_for_the_same_seed():
    a = KeyedStreams("itp_medium", "development", 10_000_000).seed_for("vessel", "V002", "interarrival")
    b = KeyedStreams("itp_heavy", "development", 10_000_000).seed_for("vessel", "V002", "interarrival")
    assert a != b
