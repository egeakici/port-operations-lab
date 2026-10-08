"""Canonical JSON and scientific fingerprints (unified data contract section 10).

Step 2 clarifications (documented in docs/step2_scenario_generator.md, amendment A3):

* ``container_manifest_fingerprint`` covers containers (without the identity-only
  ``source_scenario_id``), container groups **and** the initial state, so initial
  yard locations are fingerprinted (DQ16).
* ``exogenous_schedule_fingerprint`` covers the full vessel records in addition to
  arrival, gate-in and pickup times, so vessel lengths and crane limits are
  fingerprinted (DQ16).
* ``physics_config_fingerprint`` also covers ``yard_fidelity`` and ``physics_profile``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

FINGERPRINT_KEYS = (
    "scenario_fingerprint",
    "terminal_geometry_fingerprint",
    "resource_fingerprint",
    "container_manifest_fingerprint",
    "exogenous_schedule_fingerprint",
    "physics_config_fingerprint",
    "physical_fingerprint",
    "berth_projection_fingerprint",
    "berth_projection_physical_fingerprint",
    "generator_config_fingerprint",
)
COMPONENT_ORDER = (
    "terminal_geometry_fingerprint",
    "resource_fingerprint",
    "container_manifest_fingerprint",
    "exogenous_schedule_fingerprint",
    "physics_config_fingerprint",
)


def canonical_json(value: Any) -> str:
    """Data contract 10: sorted keys, compact separators, no NaN, UTF-8 characters kept."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _by(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: record[key])


def component_payloads(doc: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical payload hashed by each component fingerprint."""
    terminal = doc["terminal"]
    containers = []
    for record in doc["containers"]:
        stripped = dict(record)
        stripped.pop("source_scenario_id", None)
        containers.append(stripped)
    gate_in = sorted((c["container_id"], c["scheduled_gate_in_time_min"])
                     for c in doc["containers"] if c["scheduled_gate_in_time_min"] is not None)
    pickups = sorted((c["container_id"], c["scheduled_pickup_time_min"])
                     for c in doc["containers"] if c["scheduled_pickup_time_min"] is not None)
    return {
        "terminal_geometry_fingerprint": {
            "quay": terminal["quay"],
            "gates": _by(terminal["gates"], "gate_id"),
            "yard_blocks": _by(terminal["yard_blocks"], "block_id"),
        },
        "resource_fingerprint": {"quay_cranes": _by(doc["resources"]["quay_cranes"], "crane_id")},
        "container_manifest_fingerprint": {
            "containers": _by(containers, "container_id"),
            "container_groups": _by(doc["container_groups"], "group_id"),
            "initial_state": doc["initial_state"],
        },
        "exogenous_schedule_fingerprint": {
            "vessels": _by(doc["vessels"], "vessel_id"),
            "gate_in_requests": [list(item) for item in gate_in],
            "pickup_requests": [list(item) for item in pickups],
        },
        "physics_config_fingerprint": {
            "physics": doc["physics"],
            "yard_fidelity": doc["identity"]["yard_fidelity"],
            "physics_profile": doc["identity"]["physics_profile"],
        },
    }


def compute_fingerprints(doc: dict[str, Any], *, generator_config_fingerprint: str | None) -> dict[str, Any]:
    """Compute every fingerprint of a scenario document (its own block is ignored)."""
    from integrated_terminal_pilot.scenarios.berth_projection import (
        build_berth_projection, projection_physical_fingerprint,
    )

    components = {name: sha256_of(payload) for name, payload in component_payloads(doc).items()}
    body = {key: value for key, value in doc.items() if key != "fingerprints"}
    projection = build_berth_projection(doc)
    result = {
        "scenario_fingerprint": sha256_of(body),
        **components,
        "physical_fingerprint": sha256_of([components[name] for name in COMPONENT_ORDER]),
        "berth_projection_fingerprint": projection.content_fingerprint,
        "berth_projection_physical_fingerprint": projection_physical_fingerprint(projection),
        "generator_config_fingerprint": generator_config_fingerprint,
    }
    return {key: result[key] for key in FINGERPRINT_KEYS}


def with_fingerprints(doc: dict[str, Any], *, generator_config_fingerprint: str | None) -> dict[str, Any]:
    """Return a shallow copy of ``doc`` with its fingerprint block (``doc`` is not modified)."""
    result = {key: value for key, value in doc.items() if key != "fingerprints"}
    result["fingerprints"] = compute_fingerprints(
        result, generator_config_fingerprint=generator_config_fingerprint)
    return result
