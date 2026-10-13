"""PASS-EXACT gate (implementation roadmap Step 5; bap_compatibility_contract.md section 5.1).

On a ``degenerate_equivalence_v1`` scenario the forecast release equals the nominal end, so the
integrated berth layer must behave exactly like Project 03. For each arm the gate runs:

* the integrated kernel with the Step 5 arm (adapter + unchanged Project 03 policy code), and
* the unchanged Project 03 ``DynamicBAPEnv`` on the scenario's berth projection with the same policy
  (``online_fcfs_action`` / ``online_rollout_choice`` / the same frozen checkpoint, CPU, deterministic),

and requires, decision by decision: the same decision time, the same Project 03 action index
(WAIT included), the same vessel and position, and a ``dynamic_obs_v1`` observation from the adapter
that is **bit-equal** (every key, dtype and value) to Project 03 ``encode_dynamic_observation``.

Exactness scope. The degenerate profile removes crane, transport and yard *delays*, but not cargo
availability: a berth schedule different from FCFS can start a vessel before its export cargo has
gated in, and the kernel then (correctly) extends handling (``CARGO_UNAVAILABLE``) or rolls cargo over
(D17). From the first nominal end at which an integrated vessel has *not* departed exactly at
``berth_start + nominal`` (``divergence_time_min``), Project 03's fixed-duration world and the
integrated world are physically different, so equality is neither expected nor meaningful. The gate
therefore compares every decision strictly before ``scope_end_min`` = min(``divergence_time_min``, the
first decision epoch whose observation is FORECAST-substituted) and reports the scope:
``FULL`` (no divergence: the whole episode is compared) or ``PREFIX`` (with the divergence time, the
vessels and the handling causes). Every compared epoch must be forecast-``EXACT``.

Scope: berth-layer equivalence under the degenerate profile. It does not establish crane, yard or
inventory correctness, and it is not evidence about any arm's performance.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from integrated_terminal_pilot.benchmark.adapter import adapt_berth_view, dynamic_observation
from integrated_terminal_pilot.benchmark.checkpoints import CheckpointRef, load_checkpoint
from integrated_terminal_pilot.benchmark.policies import NON_PPO_CANDIDATE_CAPACITY, create_berth_policy
from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection
from integrated_terminal_pilot.simulator.drivers import run_episode
from integrated_terminal_pilot.simulator.kernel import TerminalKernel

M_REFERENCE = 24
TIME_TOL_MIN = 1e-6


class _ViewRecorder:
    """Wraps a berth policy and keeps every (immutable) BerthView it was given."""

    def __init__(self, policy) -> None:
        self.policy = policy
        self.views = []

    def decide(self, view):
        self.views.append(view)
        return self.policy.decide(view)


def project03_episode(projection, arm_id: str, training_seed: int | None) -> list[dict[str, Any]]:
    """Unchanged Project 03 environment and policy code on the berth projection."""
    from berth_allocation_lab.envs import DynamicBAPEnv
    from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action
    from berth_allocation_lab.policies.dynamic_online_rollout import online_rollout_choice

    env = DynamicBAPEnv(scenario=projection, max_vessels=M_REFERENCE,
                        future_horizon_min=projection.future_horizon_min)
    observation, _ = env.reset()
    model = load_checkpoint(CheckpointRef("medium_heavy", training_seed), projection) if arm_id == "A3" else None
    rows = []
    while not env.terminated and not env.truncated:
        mask = env.action_masks()
        if arm_id == "A1":
            action = online_fcfs_action(env)
        elif arm_id == "A2":
            action = online_rollout_choice(env.visible_state()).action
        else:
            action = model.predict(observation, mask)
        choice = env.legal_choices
        picked = next((c for c in choice if c[0] == action), None)
        rows.append({"time_min": env.current_time_min, "action": int(action),
                     "vessel_id": None if picked is None else picked[1],
                     "berth_position_m": None if picked is None else picked[3],
                     "observation": {k: v.copy() for k, v in observation.items()}})
        observation, _, _, _, _ = env.step(action)
    rows.append({"terminated": env.terminated, "truncated": env.truncated})
    return rows


def exact_gate(doc: dict[str, Any], arm_id: str, training_seed: int | None = None) -> dict[str, Any]:
    if doc["identity"]["physics_profile"] != "degenerate_equivalence_v1":
        raise ValueError("the PASS-EXACT gate needs a degenerate_equivalence_v1 scenario")
    projection = build_berth_projection(doc)
    reference = project03_episode(projection, arm_id, training_seed)
    end = reference.pop()
    policy = create_berth_policy(arm_id, training_seed=training_seed,
                                 host_projection=projection if arm_id == "A3" else None)
    recorder = _ViewRecorder(policy)
    kernel = TerminalKernel.from_scenario(doc)
    run = run_episode(kernel, berth_policy=recorder, crane_policy=GreedyBerthOrderCranePolicy(),
                      yard_policy=create_policy("yard_first_fit_v1"))
    divergence_time, diverged = _divergence(kernel)
    first_forecast = min((r["time_min"] for r in policy.records if r["forecast_epoch_mode"] == "FORECAST"),
                         default=float("inf"))
    scope_end = min(divergence_time, first_forecast)
    integrated = [r for r in policy.records if r["time_min"] < scope_end - TIME_TOL_MIN]
    reference = [r for r in reference if r["time_min"] < scope_end - TIME_TOL_MIN]
    mismatches = []
    obs_mismatch = 0
    max_obs_abs_diff = 0.0
    modes = set()
    for index in range(max(len(reference), len(integrated))):
        if index >= len(reference) or index >= len(integrated):
            mismatches.append({"index": index, "reason": "decision count differs",
                               "reference": len(reference), "integrated": len(integrated)})
            break
        ref, got = reference[index], integrated[index]
        same = (abs(ref["time_min"] - got["time_min"]) <= TIME_TOL_MIN and ref["action"] == got["p03_action"]
                and ref["vessel_id"] == got["vessel_id"] and ref["berth_position_m"] == got["berth_position_m"])
        if not same:
            mismatches.append({"index": index, "reference": {k: ref[k] for k in ref if k != "observation"},
                               "integrated": {k: got[k] for k in ("time_min", "p03_action", "vessel_id",
                                                                   "berth_position_m")}})
            break
        state = adapt_berth_view(recorder.views[index], candidate_capacity=NON_PPO_CANDIDATE_CAPACITY)
        modes.add(state.forecast_epoch_mode)
        observation, _ = dynamic_observation(state, max_vessels=M_REFERENCE)
        for key, value in ref["observation"].items():
            other = observation[key]
            if other.dtype != value.dtype or other.shape != value.shape or not np.array_equal(other, value):
                obs_mismatch += 1
                if other.shape == value.shape:
                    max_obs_abs_diff = max(max_obs_abs_diff, float(np.max(np.abs(
                        other.astype(np.float64) - value.astype(np.float64)), initial=0.0)))
    checks = {
        "integrated_completed": run.status == "COMPLETED",
        "reference_terminated": bool(end["terminated"]) and not end["truncated"],
        "compared_decisions_nonempty": bool(integrated),
        "decisions_identical": not mismatches,
        "observations_bit_equal": obs_mismatch == 0,
        "all_epochs_exact_forecast": modes <= {"EXACT", "NO_OCCUPANCY"},
    }
    return {"scenario_id": doc["identity"]["scenario_id"], "family": doc["identity"]["scenario_family"],
            "scenario_seed": doc["identity"]["scenario_seed"], "arm_id": arm_id, "ppo_training_seed": training_seed,
            "scope": "FULL" if scope_end == float("inf") else "PREFIX",
            "scope_end_min": None if scope_end == float("inf") else scope_end,
            "divergence_time_min": None if not diverged else divergence_time,
            "first_forecast_epoch_min": None if first_forecast == float("inf") else first_forecast,
            "diverged_vessels": diverged,
            "decisions": len(integrated), "reference_decisions": len(reference),
            "total_integrated_decisions": len(policy.records),
            "wait_decisions": sum(r["action_type"] == "WAIT" for r in integrated),
            "pass": all(checks.values()), "checks": checks, "mismatches": mismatches,
            "observation_key_mismatches": obs_mismatch, "max_observation_abs_diff": max_obs_abs_diff,
            "status": run.status, "failure": run.failure, "rejections": run.rejections}


def _divergence(kernel) -> tuple[float, list[dict[str, Any]]]:
    """Earliest nominal end ``berth_start + nominal`` not matched by an exact integrated departure."""
    result = kernel.result()
    causes = {row["vessel_id"]: row.get("handling_cause_min") or {}
              for row in result["time_decomposition"]["vessels"]}
    diverged = []
    for row in result["vessels"]:
        start = row["berth_start_time_min"]
        if start is None:
            continue
        realized = row["realized_berth_occupancy_min"]
        if realized is None or abs(realized - row["nominal_service_time_min"]) > TIME_TOL_MIN:
            diverged.append({"vessel_id": row["vessel_id"], "nominal_end_min": start + row["nominal_service_time_min"],
                             "realized_occupancy_min": realized, "nominal_service_min": row["nominal_service_time_min"],
                             "handling_causes_min": {k: v for k, v in causes[row["vessel_id"]].items() if v}})
    diverged.sort(key=lambda d: (d["nominal_end_min"], d["vessel_id"]))
    return (diverged[0]["nominal_end_min"] if diverged else float("inf")), diverged


__all__ = ["exact_gate", "project03_episode"]
