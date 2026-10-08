"""Field definitions of ``itp_scenario_v1`` (single source for generator and validator).

Scenario documents are plain JSON-compatible dicts. This module lists the exact
keys of every record, following docs/unified_data_contract.md and
docs/container_yard_foundation.md. Mutable operational state is not part of a
scenario definition; ``initial_state`` describes only time zero.
"""

from __future__ import annotations

import re

SCHEMA_VERSION = "itp_scenario_v1"
PRE_EPISODE = "PRE_EPISODE"
PHYSICS_PROFILE_STANDARD = "standard_v1"
PHYSICS_PROFILE_DEGENERATE = "degenerate_equivalence_v1"

TOP_LEVEL_KEYS = (
    "schema_version", "identity", "terminal", "resources", "vessels", "container_groups",
    "containers", "initial_state", "physics", "fingerprints",
)
# Data contract 2.1 plus the additive Step 2 key physics_profile (amendment A2).
IDENTITY_KEYS = (
    "scenario_id", "project_id", "scenario_family", "split", "scenario_seed",
    "generator_version", "data_provenance", "yard_fidelity", "physics_profile",
)
TERMINAL_KEYS = ("quay", "gates", "yard_blocks")
QUAY_KEYS = ("berth_length_m", "min_clearance_m", "quay_line_y_m")
GATE_KEYS = ("gate_id", "x_m", "y_m")
YARD_BLOCK_KEYS = (
    "block_id", "origin_x_m", "origin_y_m", "bay_axis", "bay_count", "row_count", "max_tiers",
    "ground_slot_length_m", "ground_slot_width_m", "geometric_slot_count",
    "geometric_capacity_teu", "capacity_teu", "operating_fill_limit", "capabilities",
    "allowed_sizes", "handling_capacity_moves_per_hour", "transfer_point_x_m",
    "transfer_point_y_m",
)
RESOURCES_KEYS = ("quay_cranes",)
CRANE_KEYS = (
    "crane_id", "nominal_moves_per_hour", "rail_id", "home_position_m", "compatible_vessel_ids",
    "unavailability_windows",
)
VESSEL_KEYS = (
    "vessel_id", "arrival_time_min", "length_m", "max_cranes", "priority",
    "discharge_move_count", "load_move_count", "extra_work_units", "workload_moves",
    "discharge_teu", "load_teu", "nominal_service_time_min",
)
GROUP_KEYS = (
    "group_id", "container_size", "quantity", "flow", "load_state", "is_reefer",
    "is_hazardous", "source_vessel_id", "target_vessel_id",
)
CONTAINER_KEYS = (
    "container_id", "container_group_id", "container_size", "size_teu", "load_state",
    "is_reefer", "is_hazardous", "gross_weight_kg", "cargo_flow", "origin_vessel_id",
    "destination_vessel_id", "terminal_entry_mode", "terminal_exit_mode",
    "present_at_episode_start", "scheduled_gate_in_time_min", "scheduled_pickup_time_min",
    "source_scenario_id",
)
INITIAL_STATE_KEYS = ("time_min", "container_locations", "block_status")
INITIAL_STATE_G1_KEYS = INITIAL_STATE_KEYS + ("slot_occupancy",)
INITIAL_LOCATION_KEYS = ("container_id", "status", "location")
LOCATION_KEYS = ("kind", "location_id", "bay", "row", "tier", "slot_resolution")
SLOT_BLOCK_KEYS = ("block_id", "slots")
SLOT_KEYS = ("container_id", "bay", "row", "tier", "bay_span")

PHYSICS_KEYS = ("service", "crane", "transport", "yard", "work", "visibility", "episode",
                "kernel", "landside")

LOCATION_KINDS = ("VESSEL", "TRANSFER", "YARD_BLOCK", "GATE", "EXTERNAL_LANDSIDE")
CONTAINER_STATUSES = (
    "EXPECTED_BY_VESSEL", "ABOARD_ARRIVED_VESSEL", "DISCHARGING", "EXPECTED_BY_LANDSIDE",
    "AT_GATE", "RECEIVING", "IN_YARD", "RETRIEVING_TO_LANDSIDE", "RELEASED_TO_LANDSIDE",
    "LOADING", "LOADED", "DEPARTED_BY_VESSEL",
)
TEU_BY_SIZE = {"20_ft": 1.0, "40_ft": 2.0}
SPLITS = ("development", "validation", "test", "diagnostic")

ID_PATTERNS = {
    "vessel": re.compile(r"^V\d{3}$"),
    "crane": re.compile(r"^QC\d{2}$"),
    "block": re.compile(r"^B\d{2}$"),
    "gate": re.compile(r"^G\d{2}$"),
    "container": re.compile(r"^CNT-\d{6}$"),
    "group": re.compile(r"^GRP-\d{4}$"),
}


def scenario_id_for(family: str, split: str, seed: int, profile: str) -> str:
    """Amendment A1: ``{scenario_family}_{split}_seed{seed}`` (family carries the itp_ prefix),
    plus ``__{profile}`` for non-standard physics profiles (amendment A2)."""
    base = f"{family}_{split}_seed{seed}"
    return base if profile == PHYSICS_PROFILE_STANDARD else f"{base}__{profile}"


def expected_entry_exit(flow: str) -> tuple[str, str]:
    entry = "LANDSIDE" if flow == "export" else "VESSEL"
    exit_mode = "LANDSIDE" if flow == "import" else "VESSEL"
    return entry, exit_mode


def location(kind: str, location_id: str | None, *, slot_resolution: str | None = None,
             bay: int | None = None, row: int | None = None, tier: int | None = None) -> dict:
    return {"kind": kind, "location_id": location_id, "bay": bay, "row": row, "tier": tier,
            "slot_resolution": slot_resolution}
