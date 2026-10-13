"""Step 4 closure: isolated in-memory diagnostic overrides and input-side load/capacity arithmetic.

Overrides never touch ``itp_generator_v1.yaml``, the decision register or a scenario file:

* ``crane_count`` (4, 6, 8): a *derived* in-memory scenario whose extra cranes ``QC05``... are
  copies of the reference crane record (same nominal rate, rail, compatibility ``null`` and empty
  unavailability windows) - the generator's own crane construction. The derived document is
  re-validated by the Step 2 validator and re-fingerprinted; its exogenous fingerprints are
  unchanged. 6 and 8 cranes are **different physical fleets** on the same exogenous traffic, not
  same-physics S1/S2 contrasts.
* ``efficiency_basis`` (``assigned`` reference / ``working`` diagnostic): set on the catalog's
  resolved ``PhysicsConfig`` only.
* ``yard_policy_id``: a registered Step 3 policy, chosen by id. Algorithms are untouched.

Fingerprints: the **base** scenario fingerprints stay those of the immutable source file; the
**resolved-physics fingerprint** covers crane fleet, physics block and efficiency basis; the
**condition fingerprint** adds the policy ids. Nothing here is an experimental arm.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace
from typing import Any

from integrated_terminal_pilot.scenarios.fingerprints import sha256_of, with_fingerprints
from integrated_terminal_pilot.scenarios.generator import max_coexisting_vessels
from integrated_terminal_pilot.simulator.catalog import ScenarioCatalog
from integrated_terminal_pilot.simulator.errors import UnsupportedScenario

REFERENCE_CRANE_COUNT = 4
REFERENCE_EFFICIENCY_BASIS = "assigned"
REFERENCE_YARD_POLICY_ID = "yard_first_fit_v1"        # Step 4 closure reference condition (historical v1 P_y);
# AM-01 was approved on 2026-10-13: the primary research P_y is selected via benchmark.profiles, not here.
AM01_PROPOSED_YARD_POLICY_ID = "yard_occupancy_balance_v1"
YARD_POLICY_LABELS = {"yard_first_fit_v1": "first_fit", "yard_occupancy_balance_v1": "balanced"}
BERTH_DRIVER_ID = "fixture_p03_online_fcfs"
CRANE_POLICY_ID = "primitive_crane_greedy_v1"
NOMINAL_CRANE_RATE = 30.0
TWO_CRANE_EFFICIENCY = 0.92


@dataclass(frozen=True)
class DiagnosticCondition:
    yard_policy_id: str = REFERENCE_YARD_POLICY_ID
    crane_count: int = REFERENCE_CRANE_COUNT
    efficiency_basis: str = REFERENCE_EFFICIENCY_BASIS

    def __post_init__(self) -> None:
        if self.yard_policy_id not in YARD_POLICY_LABELS:
            raise ValueError(f"unknown yard policy {self.yard_policy_id!r}")
        if self.efficiency_basis not in ("assigned", "working"):
            raise ValueError("efficiency_basis must be assigned or working")
        if isinstance(self.crane_count, bool) or not isinstance(self.crane_count, int) or not 1 <= self.crane_count <= 99:
            raise ValueError("crane_count must be an integer in 1..99")

    @property
    def condition_id(self) -> str:
        return f"{YARD_POLICY_LABELS[self.yard_policy_id]}_qc{self.crane_count}_{self.efficiency_basis}"

    @property
    def is_reference(self) -> bool:
        return (self.yard_policy_id, self.crane_count, self.efficiency_basis) == (
            REFERENCE_YARD_POLICY_ID, REFERENCE_CRANE_COUNT, REFERENCE_EFFICIENCY_BASIS)


def derive_fleet(doc: dict[str, Any], crane_count: int) -> dict[str, Any]:
    """In-memory derived scenario with ``crane_count`` cranes (source document untouched)."""
    cranes = doc["resources"]["quay_cranes"]
    if crane_count == len(cranes):
        return doc
    if crane_count < len(cranes):
        raise UnsupportedScenario("diagnostic fleet overrides only add cranes")
    reference = cranes[-1]
    for crane in cranes:
        comparable = {k: v for k, v in crane.items() if k not in ("crane_id", "home_position_m")}
        if comparable != {k: v for k, v in reference.items() if k not in ("crane_id", "home_position_m")}:
            raise UnsupportedScenario("source cranes are not homogeneous; cloning the reference crane would "
                                      "construct a fleet the data contract does not describe")
    if reference["compatible_vessel_ids"] is not None or reference["unavailability_windows"]:
        raise UnsupportedScenario("reference crane has compatibility or unavailability data; refusing to clone")
    quay = doc["terminal"]["quay"]["berth_length_m"]
    added = []
    for index in range(len(cranes), crane_count):
        crane = dict(reference)
        crane["crane_id"] = f"QC{index + 1:02d}"
        # home_position_m is reserved for Project 04 and unused by v1 physics; the generator's even
        # spacing rule for the derived fleet size is used for the added cranes only.
        crane["home_position_m"] = round((index + 0.5) * quay / crane_count, 6)
        added.append(crane)
    ids = [c["crane_id"] for c in cranes + added]
    if len(ids) != len(set(ids)):
        raise UnsupportedScenario("derived crane ids are not unique")
    derived = dict(doc)
    derived["resources"] = {"quay_cranes": copy.deepcopy(cranes) + added}
    derived = with_fingerprints(derived, generator_config_fingerprint=doc["fingerprints"].get(
        "generator_config_fingerprint"))
    return derived


def build_condition_catalog(doc: dict[str, Any], condition: DiagnosticCondition, *,
                            validate: bool = True) -> tuple[ScenarioCatalog, dict[str, str]]:
    """Catalog for one diagnostic condition plus its base/resolved/condition fingerprints."""
    derived = derive_fleet(doc, condition.crane_count)
    catalog = ScenarioCatalog.from_document(derived, validate=validate)
    physics = replace(catalog.physics, efficiency_basis=condition.efficiency_basis)
    physics.check_supported()
    catalog = replace(catalog, physics=physics)
    base = doc["fingerprints"]
    resolved = sha256_of({"base_physical_fingerprint": base["physical_fingerprint"],
                          "resource_fingerprint": derived["fingerprints"]["resource_fingerprint"],
                          "physics_config_fingerprint": derived["fingerprints"]["physics_config_fingerprint"],
                          "quay_crane_count": condition.crane_count,
                          "efficiency_basis": condition.efficiency_basis})
    fingerprints = {
        "base_scenario_fingerprint": base["scenario_fingerprint"],
        "base_physical_fingerprint": base["physical_fingerprint"],
        "base_exogenous_schedule_fingerprint": base["exogenous_schedule_fingerprint"],
        "derived_exogenous_schedule_fingerprint": derived["fingerprints"]["exogenous_schedule_fingerprint"],
        "resolved_physics_fingerprint": resolved,
        "condition_fingerprint": sha256_of({"resolved_physics_fingerprint": resolved,
                                            "yard_policy_id": condition.yard_policy_id,
                                            "crane_policy_id": CRANE_POLICY_ID,
                                            "berth_driver_id": BERTH_DRIVER_ID}),
    }
    if fingerprints["derived_exogenous_schedule_fingerprint"] != fingerprints["base_exogenous_schedule_fingerprint"]:
        raise UnsupportedScenario("fleet override changed the exogenous schedule")
    return catalog, fingerprints


def optimistic_crane_bound(cranes: int, max_per_vessel: int = 2) -> float:
    """Upper bound (moves/h) with every crane working on vessels of at most two cranes.

    Pairs of cranes work at 2 x 30 x 0.92; an unmatched crane at 30. Optimistic: ignores quay
    geometry, vessel mix, missing work, handling and transport.
    """
    if max_per_vessel != 2:
        raise ValueError("bound derived for max_cranes_per_vessel = 2")
    return (cranes // 2) * 2 * NOMINAL_CRANE_RATE * TWO_CRANE_EFFICIENCY + (cranes % 2) * NOMINAL_CRANE_RATE


def load_capacity(doc: dict[str, Any], crane_count: int) -> dict[str, Any]:
    """Input-side load and capacity arithmetic for one scenario and fleet (no simulation)."""
    vessels = doc["vessels"]
    arrivals = sorted(v["arrival_time_min"] for v in vessels)
    first, last = arrivals[0], arrivals[-1]
    moves = sum(v["workload_moves"] for v in vessels)
    vessel_containers = sum(1 for c in doc["containers"]
                            if c["origin_vessel_id"] not in (None, "PRE_EPISODE")
                            or c["destination_vessel_id"] is not None)
    teu = sum(v["discharge_teu"] + v["load_teu"] for v in vessels)
    mean_nominal = sum(v["nominal_service_time_min"] for v in vessels) / len(vessels)
    drain = doc["physics"]["episode"]["max_drain_extension_min"]
    windows = {"arrival_window": last - first,
               "arrival_window_plus_mean_nominal_service": last - first + mean_nominal,
               "zero_to_T_end": last + drain}
    offered = {name: (moves / (span / 60.0) if span > 0 else None) for name, span in windows.items()}
    quay = doc["terminal"]["quay"]
    k_max = max_coexisting_vessels([v["length_m"] for v in vessels], quay["berth_length_m"],
                                   quay["min_clearance_m"])
    usable = min(crane_count, 2 * k_max)
    bound = optimistic_crane_bound(crane_count)
    geometry_bound = optimistic_crane_bound(usable)
    blocks = doc["terminal"]["yard_blocks"]
    mu = [b["handling_capacity_moves_per_hour"] for b in blocks]
    landside = doc["physics"]["yard"]["landside_reserved_fraction"]
    return {
        "vessels": len(vessels), "first_arrival_min": first, "last_arrival_min": last,
        "T_end_min": last + drain,
        "required_ship_moves": moves,
        "ship_moves_note": "transshipment discharge and reload counted separately (D14)",
        "vessel_related_containers": vessel_containers, "vessel_cargo_teu": teu,
        "windows_min": windows, "offered_moves_per_hour": offered,
        "optimistic_crane_bound_moves_per_hour": bound,
        "max_coexisting_vessels_shortest_first": k_max,
        "geometry_aware_crane_bound_moves_per_hour": geometry_bound,
        "offered_to_optimistic_ratio": {name: (rate / bound if rate is not None else None)
                                        for name, rate in offered.items()},
        "offered_to_geometry_ratio": {name: (rate / geometry_bound if rate is not None else None)
                                      for name, rate in offered.items()},
        "yard": {"blocks": len(blocks), "storage_teu_total": sum(b["capacity_teu"] for b in blocks),
                 "block_handling_moves_per_hour": sorted(set(mu)),
                 "ship_side_share_per_block_with_landside_demand": sorted({m * (1 - landside) for m in mu}),
                 "all_blocks_handling_moves_per_hour": sum(mu),
                 "initial_yard_teu": sum(c["size_teu"] for c in doc["containers"] if c["present_at_episode_start"])},
        "qualification": "optimistic bounds, necessary but not sufficient for feasibility; not sustained capacity",
    }


def is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


__all__ = ["AM01_PROPOSED_YARD_POLICY_ID", "DiagnosticCondition", "REFERENCE_YARD_POLICY_ID",
           "build_condition_catalog", "derive_fleet", "load_capacity", "optimistic_crane_bound"]
