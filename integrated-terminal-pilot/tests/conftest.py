from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from integrated_terminal_pilot.scenarios.config import (
    DEFAULT_CONFIG_PATH, DEFAULT_DECISIONS_PATH, build_generator_config, load_generator_config,
)
from integrated_terminal_pilot.scenarios.fingerprints import with_fingerprints
from integrated_terminal_pilot.scenarios.generator import (
    generate_scenario, generate_scenario_with_diagnostics,
)
from integrated_terminal_pilot.scenarios.serialization import load_scenario

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = PROJECT_ROOT / "tests" / "fixtures" / "golden" / "itp_example_development_seed10000000.scenario.json"
DEV = "development"
SEED = 10_000_000
# Heavy seed 10_000_000 was rejected under the 4-block yard (YARD_CAPACITY_EXCEEDED); under the
# stabilized 12-block reference it is valid (test_b checks both contracts).
HEAVY_SEED = SEED
# Physical yard configuration that preceded the Step 2 stabilization (for regression contrasts).
PRE_STABILIZATION_YARD = {
    "families.itp_heavy.yard.block_count": 4, "families.itp_heavy.yard.block_line_count": 1,
    "families.itp_medium.yard.block_count": 4, "families.itp_medium.yard.block_line_count": 1,
}


def raw_config() -> tuple[dict[str, Any], dict[str, Any]]:
    params = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    register = yaml.safe_load(DEFAULT_DECISIONS_PATH.read_text(encoding="utf-8"))
    return params, register


def _set(mapping: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        mapping = mapping[part]
    mapping[parts[-1]] = value


def mutated_config(changes: dict[str, Any], *, statuses: dict[str, str] | None = None):
    """Config with parameter changes mirrored into their decision records (register stays consistent)."""
    params, register = raw_config()
    for path, value in changes.items():
        _set(params, path, value)
        for record in register["records"]:
            for covered in record["parameter_paths"]:
                if path == covered or path.startswith(covered + "."):
                    per_path = record.get("selected_values") or {
                        p: copy.deepcopy(record["selected_value"]) for p in record["parameter_paths"]}
                    if path == covered:
                        per_path[covered] = value
                    else:
                        _set(per_path[covered], path[len(covered) + 1:], value)
                    record["selected_values"] = per_path
                    record["selected_value"] = None
    for decision_id, status in (statuses or {}).items():
        for record in register["records"]:
            if record["decision_id"] == decision_id:
                record["status"] = status
    return build_generator_config(params, register)


def refingerprint(doc: dict[str, Any]) -> dict[str, Any]:
    return with_fingerprints(doc, generator_config_fingerprint=doc["fingerprints"]["generator_config_fingerprint"])


@pytest.fixture(scope="session")
def config():
    return load_generator_config()


@pytest.fixture(scope="session")
def low_result(config):
    return generate_scenario_with_diagnostics(config, "itp_low", DEV, SEED)


@pytest.fixture(scope="session")
def low_doc(low_result):
    return low_result.scenario


@pytest.fixture(scope="session")
def medium_doc(config):
    return generate_scenario(config, "itp_medium", DEV, SEED)


@pytest.fixture(scope="session")
def heavy_doc(config):
    return generate_scenario(config, "itp_heavy", DEV, HEAVY_SEED)


@pytest.fixture(scope="session")
def bottleneck_result(config):
    return generate_scenario_with_diagnostics(config, "itp_yard_bottleneck", DEV, SEED)


@pytest.fixture(scope="session")
def golden_doc():
    return load_scenario(GOLDEN_PATH)


@pytest.fixture()
def golden(golden_doc):
    """A fresh mutable copy of the golden fixture."""
    return json.loads(json.dumps(golden_doc))
