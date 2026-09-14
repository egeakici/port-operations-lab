from __future__ import annotations

from pathlib import Path

import pytest

from berth_allocation_lab.config import (
    ConfigFileNotFoundError,
    ConfigParseError,
    ConfigValidationError,
    ScenarioConfigMetadata,
    load_yaml_config,
)


def test_load_example_scenario_config() -> None:
    config = load_yaml_config(Path("configs/scenarios/example_static.yaml"))

    assert config["scenario_id"] == "example_static_scaffold"
    assert config["formulation"] == "static"
    assert config["min_clearance_m"] == 20.0
    assert "minimum_clearance_m" not in config


def test_scenario_metadata_from_mapping() -> None:
    config = load_yaml_config(Path("configs/scenarios/example_static.yaml"))
    metadata = ScenarioConfigMetadata.from_mapping(config)

    assert metadata.scenario_id == "example_static_scaffold"
    assert metadata.scenario_version == 1
    assert metadata.data_provenance == "synthetic"
    assert metadata.seed == 42


def test_missing_config_raises_useful_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(ConfigFileNotFoundError, match="does not exist"):
        load_yaml_config(missing_path)


def test_invalid_yaml_raises_parse_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text("scenario_id: [unterminated", encoding="utf-8")

    with pytest.raises(ConfigParseError, match="Invalid YAML"):
        load_yaml_config(invalid_path)


def test_non_mapping_yaml_raises_validation_error(tmp_path: Path) -> None:
    list_path = tmp_path / "list.yaml"
    list_path.write_text("- a\n- b\n", encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="top-level mapping"):
        load_yaml_config(list_path)

