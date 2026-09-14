from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Base error for Project 03 configuration loading."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when an explicit configuration path does not exist."""


class ConfigParseError(ConfigError):
    """Raised when a configuration file cannot be parsed as YAML."""


class ConfigValidationError(ConfigError):
    """Raised when parsed configuration has the wrong top-level shape."""


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file as a top-level mapping."""

    config_path = Path(path)
    if not config_path.exists():
        raise ConfigFileNotFoundError(
            f"Configuration file does not exist: {config_path}"
        )

    if not config_path.is_file():
        raise ConfigValidationError(
            f"Configuration path is not a file: {config_path}"
        )

    try:
        with config_path.open("r", encoding="utf-8") as file:
            parsed = yaml.safe_load(file)
    except yaml.YAMLError as error:
        raise ConfigParseError(
            f"Invalid YAML in configuration file {config_path}: {error}"
        ) from error

    if parsed is None:
        return {}

    if not isinstance(parsed, dict):
        raise ConfigValidationError(
            f"Configuration file must contain a top-level mapping: {config_path}"
        )

    return dict(parsed)

