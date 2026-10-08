"""Read-only projection of an integrated scenario to Project 03's berth-only scenario.

Implements unified data contract section 11 with Project 03's canonical
``BAPScenarioInstance`` / ``BAPVesselInput``. The projection carries only vessel
identity, arrival, length, nominal service and workload plus quay geometry, H
and drain settings. It never carries crane, yard, container, landside or
realized information. This module executes no policy and loads no checkpoint.
"""

from __future__ import annotations

from typing import Any

from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.rl.suites import physical_fingerprint as _p03_physical_fingerprint

PROJECTION_GENERATOR_VERSION = "itp_berth_projection_v1"
# data contract 11: label mapping only; the Project I record is authoritative.
PROJECTION_SPLIT = {"development": "train", "validation": "validation", "test": "test",
                    "diagnostic": "test"}
# BAPScenarioInstance requires positive integers; data contract 11 does not name values,
# so the Project 03 v1 values are used (Step 2 clarification A5).
PROJECTION_SCENARIO_VERSION = 1
PROJECTION_SCHEMA_VERSION = 1

# bap_compatibility_contract.md section 4 (frozen PPO support envelopes).
PPO_SUPPORT = {
    "medium_heavy": {"berth_length_m": 1200.0, "min_clearance_m": 20.0, "max_vessels": 24,
                     "length_m": (200.0, 360.0), "workload_moves": (250, 900),
                     "future_horizon_min": 240.0},
    "tiny": {"berth_length_m": 600.0, "min_clearance_m": 20.0, "max_vessels": 8,
             "length_m": (200.0, 360.0), "workload_moves": (250, 900),
             "future_horizon_min": 240.0},
}


def build_berth_projection(doc: dict[str, Any]) -> BAPScenarioInstance:
    identity = doc["identity"]
    quay = doc["terminal"]["quay"]
    physics = doc["physics"]
    vessels = sorted(doc["vessels"], key=lambda v: (v["arrival_time_min"], v["vessel_id"]))
    last_arrival = max(v["arrival_time_min"] for v in vessels)
    family = identity["scenario_family"]
    if identity["split"] == "diagnostic":
        family = f"{family}_diagnostic"
    return BAPScenarioInstance(
        scenario_id=f"{identity['scenario_id']}__berth_projection",
        scenario_version=PROJECTION_SCENARIO_VERSION,
        scenario_family=family,
        formulation="dynamic",
        data_provenance="synthetic",
        split=PROJECTION_SPLIT[identity["split"]],
        seed=identity["scenario_seed"],
        generator_version=PROJECTION_GENERATOR_VERSION,
        scenario_schema_version=PROJECTION_SCHEMA_VERSION,
        berth_length_m=float(quay["berth_length_m"]),
        min_clearance_m=float(quay["min_clearance_m"]),
        nominal_duration_min=float(last_arrival),
        arrival_generation_end_min=float(last_arrival),
        vessels=tuple(
            BAPVesselInput(
                vessel_id=v["vessel_id"],
                arrival_time_min=float(v["arrival_time_min"]),
                length_m=float(v["length_m"]),
                service_time_min=float(v["nominal_service_time_min"]),
                workload_moves=int(v["workload_moves"]),
            )
            for v in vessels
        ),
        future_horizon_min=float(physics["visibility"]["future_horizon_min"]),
        termination_mode="drain",
        max_drain_extension_min=float(physics["episode"]["max_drain_extension_min"]),
    )


def projection_physical_fingerprint(projection: BAPScenarioInstance) -> str:
    """Project 03 ``rl.suites.physical_fingerprint`` (quay, clearance, vessel inputs; ID-free)."""
    return _p03_physical_fingerprint(projection)


def assess_ppo_support(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Exogenous input support for each frozen PPO regime (gate checks G11, G12, G14, G16).

    This is a data-compatibility statement only; it is not a gate PASS, which also
    requires the Step 5 adapter checks.
    """
    quay = doc["terminal"]["quay"]
    horizon = doc["physics"]["visibility"]["future_horizon_min"]
    result = {}
    for regime, envelope in PPO_SUPPORT.items():
        reasons = []
        if quay["berth_length_m"] != envelope["berth_length_m"]:
            reasons.append(f"berth_length_m {quay['berth_length_m']} != {envelope['berth_length_m']}")
        if quay["min_clearance_m"] != envelope["min_clearance_m"]:
            reasons.append(f"min_clearance_m {quay['min_clearance_m']} != {envelope['min_clearance_m']}")
        if len(doc["vessels"]) > envelope["max_vessels"]:
            reasons.append(f"vessel count {len(doc['vessels'])} > {envelope['max_vessels']}")
        if horizon != envelope["future_horizon_min"]:
            reasons.append(f"future_horizon_min {horizon} != {envelope['future_horizon_min']}")
        low, high = envelope["length_m"]
        out_len = [v["vessel_id"] for v in doc["vessels"] if not low <= v["length_m"] <= high]
        if out_len:
            reasons.append(f"vessel length outside [{low}, {high}]: {out_len}")
        low_w, high_w = envelope["workload_moves"]
        out_w = [v["vessel_id"] for v in doc["vessels"] if not low_w <= v["workload_moves"] <= high_w]
        if out_w:
            reasons.append(f"workload outside [{low_w}, {high_w}]: {out_w}")
        result[regime] = {"status": "OUT_OF_SUPPORT" if reasons else "IN_SUPPORT",
                          "max_vessels": envelope["max_vessels"], "reasons": reasons}
    return result


def verify_dynamic_env_reset(projection: BAPScenarioInstance, max_vessels: int) -> dict[str, Any]:
    """Construct and reset Project 03 ``DynamicBAPEnv`` on the projection (no policy, no step)."""
    from berth_allocation_lab.envs import DynamicBAPEnv

    env = DynamicBAPEnv(scenario=projection, max_vessels=max_vessels,
                        future_horizon_min=projection.future_horizon_min)
    observation, info = env.reset()
    space_ok = bool(env.observation_space.contains(observation))
    env.close()
    return {
        "reset_ok": True,
        "max_vessels": max_vessels,
        "action_space_n": int(env.action_space.n),
        "observation_keys": sorted(observation),
        "observation_in_space": space_ok,
        "scenario_fingerprint_in_info": info["scenario_fingerprint"],
        "projection_fingerprint_matches": info["scenario_fingerprint"] == projection.content_fingerprint,
    }
