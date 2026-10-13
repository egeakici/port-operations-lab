"""Independent berth policies A1/A2/A3 behind one ``BerthPolicy`` interface (Step 5).

Decision path, identical for every arm::

    kernel.berth_view()  ->  adapt_berth_view (G08/G09/G10/G17)  ->  policy rule  ->  BerthAction
                         ->  kernel.apply_berth_action (the Step 4 PhysicalActionValidator)

``decide(view)`` reads only the immutable ``BerthView``; it never receives the kernel. The decision
is a pure function of the view (the per-decision record list is logging only). A policy never
repairs or remaps an action: an action outside the legal set raises (G19) and the run is FAILED.

* **A1** ``OnlineFcfsBerthPolicy``: Project 03 ``online_fcfs_action`` unchanged, over the adapter's
  Project 03 choice table (key ``(arrival, vessel_id, position)``; never WAITs).
* **A2** ``OnlineRolloutBerthPolicy``: Project 03 ``online_rollout_choice`` unchanged, on the
  adapter's ``DynamicVisibleState`` (visible cohort, nominal service for unstarted vessels,
  forecast release for occupying vessels, FCFS continuation; berth-only forward model).
* **A3** ``FrozenPpoBerthPolicy``: one frozen medium/heavy checkpoint (training seed 11, 23 or 37),
  ``dynamic_obs_v1`` built by Project 03 ``encode_dynamic_observation`` on the adapted state,
  ``model.predict(obs, deterministic=True, action_masks=mask)`` on CPU.
"""

from __future__ import annotations

import time
from typing import Any

from integrated_terminal_pilot.benchmark.adapter import (
    ADAPTER_VERSION, AdaptedBerthState, AdapterContractError, adapt_berth_view, dynamic_observation,
    visible_state,
)
from integrated_terminal_pilot.simulator.validator import BerthAction

# P = 2M with the Project 03 medium/heavy M = 24. For A1/A2 the action index only orders choices
# (slot-major, then candidate); any P >= the candidate count gives the same order, and P = 48 makes
# the indices identical to Project 03's medium/heavy evaluation environment.
NON_PPO_MAX_VESSELS = 24
NON_PPO_CANDIDATE_CAPACITY = 2 * NON_PPO_MAX_VESSELS
# bap_compatibility_contract.md section 4: training maximum of the occupancy feature.
TRAINING_MAX_REMAINING_OCCUPANCY_FEATURE = (50.0 + 0.5 * 900) / 1440.0


class _LegalChoiceHost:
    """Exposes only ``legal_choices`` (all that ``online_fcfs_action`` reads)."""

    def __init__(self, legal_choices) -> None:
        self.legal_choices = legal_choices


class BerthPolicy:
    """Common interface: ``decide(BerthView) -> BerthAction``; records one row per decision."""

    arm_id: str = ""
    policy_id: str = ""
    p03_policy_id: str = ""
    version: str = "1"
    candidate_capacity: int = NON_PPO_CANDIDATE_CAPACITY

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    # -- subclasses implement _choose(state) -> (p03_action:int, extra:dict)
    def _choose(self, state: AdaptedBerthState) -> tuple[int, dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def decide(self, view) -> BerthAction:
        t0 = time.perf_counter()
        state = adapt_berth_view(view, candidate_capacity=self.candidate_capacity)
        t1 = time.perf_counter()
        action, extra = self._choose(state)
        t2 = time.perf_counter()
        choices = state.choice_by_action
        if action == 0:
            if not state.wait_legal:
                raise AdapterContractError("G19", f"{self.policy_id} chose WAIT, which is masked")
            berth_action = BerthAction.wait(self.policy_id, decision_id=view.decision_id)
            vessel_id = position = None
        elif action in choices:
            vessel_id, _, position = choices[action]
            berth_action = BerthAction.assign(self.policy_id, vessel_id, position, decision_id=view.decision_id)
        else:
            raise AdapterContractError("G19", f"{self.policy_id} chose action {action} outside the legal set")
        self.records.append({
            "decision_id": view.decision_id, "time_min": view.time_min, "p03_action": int(action),
            "action_type": "WAIT" if action == 0 else "ASSIGN", "vessel_id": vessel_id,
            "berth_position_m": position, "legal_assignments": len(state.legal_choices),
            "wait_legal": state.wait_legal, "revealed_vessels": len(state.slot_ids),
            "announced_vessels": sum(s == "ANNOUNCED" for s in state.statuses_by_slot),
            "occupying_vessels": len(state.forecasts),
            "forecast_substituted_vessels": sum(f.mode == "FORECAST" for f in state.forecasts),
            "forecast_epoch_mode": state.forecast_epoch_mode,
            "adapter_seconds": t1 - t0, "policy_seconds": t2 - t1, "timeout": False, **extra})
        return berth_action

    def describe(self) -> dict[str, Any]:
        return {"arm_id": self.arm_id, "policy_id": self.policy_id, "p03_policy_id": self.p03_policy_id,
                "version": self.version, "adapter_version": ADAPTER_VERSION,
                "candidate_capacity": self.candidate_capacity,
                "information_contract": "BerthView only: revealed vessels (H = 240 announcement), statuses, "
                                        "nominal service, actual berth position/start, ServiceForecaster v1 "
                                        "release of occupying vessels, physical legal set, WAIT bit; no "
                                        "hidden vessels, gate/pickup events, crane or yard state",
                "timeout_policy": "none (no per-decision cap, no fallback action)"}


class OnlineFcfsBerthPolicy(BerthPolicy):
    arm_id = "A1"
    policy_id = "a1_p03_dynamic_online_fcfs_v1"
    p03_policy_id = "dynamic_online_fcfs_v1"

    def _choose(self, state):
        from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action

        return online_fcfs_action(_LegalChoiceHost(state.legal_choices)), {}


class OnlineRolloutBerthPolicy(BerthPolicy):
    arm_id = "A2"
    policy_id = "a2_p03_dynamic_online_rollout_v1"
    p03_policy_id = "dynamic_online_rollout_v1"

    def _choose(self, state):
        from berth_allocation_lab.policies.dynamic_online_rollout import online_rollout_choice

        t0 = time.perf_counter()
        visible = visible_state(state)
        t1 = time.perf_counter()
        decision = online_rollout_choice(visible)
        return decision.action, {"encode_seconds": t1 - t0, "rollout_runtime_seconds": decision.runtime_seconds,
                                 "root_evaluations": len(decision.scores),
                                 "scores": [[a, s] for a, s in decision.scores]}

    def describe(self):
        return super().describe() | {"search_budget": {
            "candidates": "every legal action at the epoch (all legal (vessel, position) pairs, plus WAIT if legal)",
            "root_forward_simulations_per_decision": "one per candidate (recorded per decision)",
            "forward_model": "Project 03 _VisibleContinuation: visible cohort only, nominal service for "
                             "unstarted vessels, occupying vessels release at their forecast, FCFS "
                             "continuation to completion; WAIT branch advances to the next visible event "
                             "and takes the best immediate legal assignment",
            "search_horizon": "until every visible vessel is completed (bounded by the visible cohort)",
            "tie_break": "minimum score, then lowest Project 03 action index (WAIT = 0 first)",
            "device": "CPU, single process", "timeout": "none", "fallback": "none"}}


class FrozenPpoBerthPolicy(BerthPolicy):
    arm_id = "A3"
    p03_policy_id = "dynamic_maskable_ppo_v1"

    def __init__(self, loaded) -> None:
        super().__init__()
        self.loaded = loaded
        self.max_vessels = loaded.ref.max_vessels
        self.candidate_capacity = 2 * self.max_vessels
        self.policy_id = f"a3_p03_dynamic_maskable_ppo_v1_{loaded.ref.regime}_train_seed{loaded.ref.training_seed}"
        self._space = loaded.model.observation_space
        self._keys = tuple(sorted(self._space.spaces))

    def _choose(self, state):
        t0 = time.perf_counter()
        observation, mask = dynamic_observation(state, max_vessels=self.max_vessels,
                                                time_scale_min=self.loaded.metadata["time_scale_min"],
                                                length_scale_m=self.loaded.metadata["length_scale_m"])
        t1 = time.perf_counter()
        if tuple(sorted(observation)) != self._keys:
            raise AdapterContractError("G20", f"observation keys {sorted(observation)} != {list(self._keys)}")
        if not self._space.contains(observation):
            raise AdapterContractError("G05", "observation is outside the checkpoint observation space")
        t2 = time.perf_counter()
        action = self.loaded.predict(observation, mask)
        t3 = time.perf_counter()
        if not 0 <= action < mask.shape[0] or not mask[action]:
            raise AdapterContractError("G19", f"PPO returned masked action {action}")
        end_feature = observation["placement_features"][:, 2]
        return action, {"encode_seconds": t1 - t0, "mask_check_seconds": t2 - t1, "inference_seconds": t3 - t2,
                        "mask_true_count": int(mask.sum()),
                        "max_remaining_occupancy_feature": float(end_feature.max(initial=0.0)),
                        "occupancy_feature_above_training_max": bool(
                            end_feature.max(initial=0.0) > TRAINING_MAX_REMAINING_OCCUPANCY_FEATURE)}

    def describe(self):
        ref = self.loaded.ref
        from integrated_terminal_pilot.benchmark.checkpoints import INFERENCE_CONFIG

        return super().describe() | {
            "checkpoint": {"regime": ref.regime, "training_seed": ref.training_seed, "path": str(ref.model_path),
                           "sha256": self.loaded.sha256, "max_vessels": self.max_vessels,
                           "action_capacity": 1 + self.max_vessels * self.candidate_capacity,
                           "load_seconds": self.loaded.load_seconds, "torch_threads": self.loaded.torch_threads},
            "inference": INFERENCE_CONFIG}


ARMS = ("A1", "A2", "A3")


def create_berth_policy(arm_id: str, *, training_seed: int | None = None, host_projection=None) -> BerthPolicy:
    """Deterministic registry: A1, A2, or A3 with one explicit training seed (11, 23 or 37)."""
    if arm_id == "A1":
        if training_seed is not None:
            raise ValueError("A1 takes no checkpoint seed")
        return OnlineFcfsBerthPolicy()
    if arm_id == "A2":
        if training_seed is not None:
            raise ValueError("A2 takes no checkpoint seed")
        return OnlineRolloutBerthPolicy()
    if arm_id == "A3":
        from integrated_terminal_pilot.benchmark.checkpoints import TRAINING_SEEDS, CheckpointRef, load_checkpoint

        if training_seed not in TRAINING_SEEDS:
            raise ValueError(f"A3 needs one training seed of {TRAINING_SEEDS}; checkpoints are never pooled")
        if host_projection is None:
            raise ValueError("A3 needs the scenario's berth projection as the G04 loader host")
        return FrozenPpoBerthPolicy(load_checkpoint(CheckpointRef("medium_heavy", training_seed), host_projection))
    raise KeyError(f"unknown arm {arm_id!r}; registered: {ARMS}")


__all__ = ["ARMS", "BerthPolicy", "FrozenPpoBerthPolicy", "NON_PPO_CANDIDATE_CAPACITY", "OnlineFcfsBerthPolicy",
           "OnlineRolloutBerthPolicy", "TRAINING_MAX_REMAINING_OCCUPANCY_FEATURE", "create_berth_policy"]
