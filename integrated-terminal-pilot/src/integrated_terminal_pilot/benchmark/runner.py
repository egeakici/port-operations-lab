"""One independent-arm run on the shared Step 4 kernel, and its provenance-complete result record.

Every arm runs through the same path: ``ScenarioCatalog`` of the scenario (its own crane fleet and
physics; no override) -> ``TerminalKernel`` -> ``run_episode`` with the arm's berth policy, the Step 3
``primitive_crane_greedy_v1`` and the profile's common P_y. Only ``berth_policy`` differs between
arms. ``comparison_fingerprint`` (scenario, resolved physics, P_c, P_y) is berth-policy independent
and must be identical across A1/A2/A3 on one scenario.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from integrated_terminal_pilot.benchmark.adapter import ADAPTER_VERSION
from integrated_terminal_pilot.benchmark.policies import create_berth_policy
from integrated_terminal_pilot.benchmark.profiles import CRANE_POLICY_ID, EFFICIENCY_BASIS, yard_profile
from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
from integrated_terminal_pilot.scenarios.berth_projection import assess_ppo_support, build_berth_projection
from integrated_terminal_pilot.scenarios.fingerprints import sha256_of
from integrated_terminal_pilot.simulator.catalog import ScenarioCatalog
from integrated_terminal_pilot.simulator.drivers import run_episode
from integrated_terminal_pilot.simulator.kernel import TerminalKernel
from integrated_terminal_pilot.simulator.trace import emit_trace, write_trace

RUN_RECORD_VERSION = "itp_step5_run_v1"


def arm_label(arm_id: str, training_seed: int | None) -> str:
    return arm_id if training_seed is None else f"{arm_id}-train{training_seed}"


def comparison_fingerprint(doc: dict[str, Any], catalog: ScenarioCatalog, yard_policy_id: str) -> str:
    """Everything a fair A-arm comparison must hold fixed; contains no berth-policy identity."""
    fp = doc["fingerprints"]
    return sha256_of({"scenario_fingerprint": fp["scenario_fingerprint"],
                      "physical_fingerprint": fp["physical_fingerprint"],
                      "exogenous_schedule_fingerprint": fp["exogenous_schedule_fingerprint"],
                      "physics_config_fingerprint": fp["physics_config_fingerprint"],
                      "resource_fingerprint": fp["resource_fingerprint"],
                      "quay_crane_count": len(catalog.cranes), "efficiency_basis": catalog.physics.efficiency_basis,
                      "crane_policy_id": CRANE_POLICY_ID, "yard_policy_id": yard_policy_id})


def a3_scenario_gate(doc: dict[str, Any]) -> dict[str, Any]:
    """Per-scenario exogenous support for the medium/heavy checkpoints (G11, G12, G14, G16)."""
    support = assess_ppo_support(doc)["medium_heavy"]
    return {"status": "PASS" if support["status"] == "IN_SUPPORT" else "BLOCK", "reasons": support["reasons"]}


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))]
    return {"n": len(values), "total": sum(values), "mean": statistics.fmean(values),
            "median": statistics.median(values), "p95": p95, "max": ordered[-1]}


def _decision_summary(records: list[dict[str, Any]], kernel_timings: list[dict[str, Any]]) -> dict[str, Any]:
    out = {
        "berth_decisions": len(records),
        "wait_selected": sum(r["action_type"] == "WAIT" for r in records),
        "wait_legal_epochs": sum(r["wait_legal"] for r in records),
        "assignments": sum(r["action_type"] == "ASSIGN" for r in records),
        "legal_assignments_per_epoch": _stats([r["legal_assignments"] for r in records]),
        "timeouts": sum(r["timeout"] for r in records),
        "forecast_epoch_modes": {m: sum(r["forecast_epoch_mode"] == m for r in records)
                                 for m in ("NO_OCCUPANCY", "EXACT", "FORECAST")},
        "forecast_substituted_vessel_epochs": sum(r["forecast_substituted_vessels"] for r in records),
        "seconds": {
            "view_build": _stats([t["view_seconds"] for t in kernel_timings]),
            "adapter": _stats([r["adapter_seconds"] for r in records]),
            "policy": _stats([r["policy_seconds"] for r in records]),
            "apply": _stats([t["apply_seconds"] for t in kernel_timings]),
        },
    }
    for key in ("encode_seconds", "inference_seconds", "mask_check_seconds", "rollout_runtime_seconds"):
        values = [r[key] for r in records if key in r]
        if values:
            out["seconds"][key.removesuffix("_seconds")] = _stats(values)
    if any("root_evaluations" in r for r in records):
        out["rollout_root_evaluations"] = _stats([r["root_evaluations"] for r in records])
    if any("max_remaining_occupancy_feature" in r for r in records):
        out["ppo_support"] = {
            "max_remaining_occupancy_feature": max(r["max_remaining_occupancy_feature"] for r in records),
            "epochs_above_training_max": sum(r["occupancy_feature_above_training_max"] for r in records),
            "mask_true_count": _stats([r["mask_true_count"] for r in records])}
    return out


def _backlog(kernel) -> dict[str, int]:
    """Containers by status at stop (gate / pickup backlog included)."""
    counts: dict[str, int] = {}
    for status in kernel.state.c_status:
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def run_arm(doc: dict[str, Any], *, arm_id: str, training_seed: int | None = None,
            yard_profile_name: str = "protocol_v1_first_fit", trace_mode: str = "summary",
            trace_dir=None, max_decisions: int | None = None, keep_kernel: bool = False) -> dict[str, Any]:
    """Run one arm on one scenario; never raises for a policy/kernel failure (status FAILED is recorded)."""
    profile_name, profile = yard_profile(yard_profile_name)
    yard_policy_id = profile["yard_policy_id"]
    started = time.perf_counter()
    catalog = ScenarioCatalog.from_document(doc, validate=True)
    if catalog.physics.efficiency_basis != EFFICIENCY_BASIS:
        raise ValueError("Step 5 runs use the 'assigned' efficiency reference")
    projection = build_berth_projection(doc)
    identity = doc["identity"]
    base = {
        "record_version": RUN_RECORD_VERSION,
        "scenario": {"scenario_id": identity["scenario_id"], "family": identity["scenario_family"],
                     "split": identity["split"], "scenario_seed": identity["scenario_seed"],
                     "physics_profile": identity["physics_profile"], "fingerprints": dict(doc["fingerprints"])},
        "arm": {"arm_id": arm_id, "arm_label": arm_label(arm_id, training_seed),
                "ppo_training_seed": training_seed},
        "shared": {"kernel": "TerminalKernel (Step 4)", "crane_policy_id": CRANE_POLICY_ID,
                   "yard_profile": profile_name, "yard_policy_id": yard_policy_id, "yard_profile_role": profile["role"],
                   "quay_crane_count": len(catalog.cranes), "efficiency_basis": catalog.physics.efficiency_basis,
                   "batch_size_containers": catalog.physics.batch_size_containers,
                   "max_load_wait_min": catalog.physics.max_load_wait_min,
                   "future_horizon_min": catalog.physics.future_horizon_min,
                   "adapter_version": ADAPTER_VERSION},
        "comparison_fingerprint": comparison_fingerprint(doc, catalog, yard_policy_id),
    }
    if arm_id == "A3":
        gate = a3_scenario_gate(doc)
        base["a3_scenario_gate"] = gate
        if gate["status"] != "PASS":
            return base | {"status": "BLOCKED", "blocked_reasons": gate["reasons"]}
    t_setup = time.perf_counter()
    policy = create_berth_policy(arm_id, training_seed=training_seed,
                                 host_projection=projection if arm_id == "A3" else None)
    policy_setup_seconds = time.perf_counter() - t_setup   # imports + (cached) checkpoint load; not run time
    started += policy_setup_seconds
    kernel = TerminalKernel.from_catalog(catalog, invariant_mode="cheap")
    run = run_episode(kernel, berth_policy=policy, crane_policy=GreedyBerthOrderCranePolicy(),
                      yard_policy=create_policy(yard_policy_id), max_decisions=max_decisions)
    run_seconds = time.perf_counter() - started
    result = kernel.result()
    t0 = time.perf_counter()
    if trace_dir is None:
        digests = emit_trace(kernel, None, mode=trace_mode, rejections=run.rejections, result=result)
    else:
        digests = write_trace(kernel, trace_dir, run_id=f"{identity['scenario_id']}__{arm_label(arm_id, training_seed)}",
                              rejections=run.rejections, mode=trace_mode, result=result,
                              metadata={"arm_id": arm_id, "ppo_training_seed": training_seed,
                                        "berth_policy_id": policy.policy_id, "yard_policy_id": yard_policy_id,
                                        "development_only": True})
    trace_seconds = time.perf_counter() - t0
    compliance = result["service_compliance"]
    decomposition = result["time_decomposition"]
    ratios = [row["realized_berth_occupancy_min"] / row["nominal_service_time_min"]
              for row in result["vessels"] if row["realized_berth_occupancy_min"] is not None]
    reconciliation = [{"vessel_id": r["vessel_id"], "ok": r["required_moves"] == r["completed_moves"]
                       + r["rolled_over_moves"] + r["unfinished_moves"]} for r in decomposition["vessels"]]
    record = base | {
        "policy": policy.describe(),
        "status": run.status, "kernel_status": kernel.status, "status_reason": result["status_reason"],
        "failure": run.failure, "rejections": run.rejections,
        "end_time_min": result["end_time_min"], "T_end_min": result["T_end_min"],
        "service_compliance": compliance,
        "kpi": result["kpi"], "counts": result["counts"],
        "time_decomposition": {k: v for k, v in decomposition.items() if k != "vessels"},
        "vessels": decomposition["vessels"],
        "per_vessel_move_reconciliation_ok": all(r["ok"] for r in reconciliation),
        "container_status_at_stop": _backlog(kernel),
        "realized_to_nominal_occupancy": _stats(ratios),
        "audits": {k: v.get("ok") for k, v in result["audits"].items() if isinstance(v, dict)}
                  | {"ok": result["audits"]["ok"]},
        "decisions": {"counts": run.decisions} | _decision_summary(policy.records, run.berth_timings),
        "digests": {"trace_mode": trace_mode, "files": digests["files"], "trace_sha256": digests["trace_sha256"]},
        "engineering": {"run_wall_seconds": run_seconds, "trace_seconds": trace_seconds,
                        "policy_setup_seconds_excluded": policy_setup_seconds,
                        "policy_decision_wall_seconds_total": sum(r["adapter_seconds"] + r["policy_seconds"]
                                                                  for r in policy.records),
                        "simulated_minutes": result["end_time_min"],
                        "checkpoint_load_seconds_excluded": (policy.loaded.load_seconds if arm_id == "A3" else None)},
    }
    if keep_kernel:
        record["_kernel"] = kernel
        record["_policy"] = policy
    return record


__all__ = ["RUN_RECORD_VERSION", "a3_scenario_gate", "arm_label", "comparison_fingerprint", "run_arm"]
