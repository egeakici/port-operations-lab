"""Gymnasium StaticBAP schedule-construction environment over the shared core.

The agent chooses one canonical candidate index for each vessel in the frozen
``(arrival_time_min, vessel_id)`` order. The Step 5 core supplies candidates and
earliest feasible starts; the reward is the negative canonical waiting time.
This is offline schedule construction with full static information, not a
chronological simulation: there is no clock, WAIT action or drain phase.
"""

from __future__ import annotations

from dataclasses import asdict
from numbers import Integral
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from berth_allocation_lab.core import (
    BAPPlacement,
    find_schedule_violations,
    total_waiting_time,
    waiting_time,
)
from berth_allocation_lab.core.numerics import is_close, is_finite_number
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.envs.static_observation import (
    CandidateChoice,
    build_observation_space,
    encode_observation,
)
from berth_allocation_lab.envs.static_scenario_provider import ScenarioProvider
from berth_allocation_lab.evaluation.metrics import StaticMetrics, calculate_static_metrics
from berth_allocation_lab.policies.base import (
    StaticDecisionRecord,
    candidate_starts,
    ordered_vessels,
    placement_at,
    require_static_scenario,
)


ENVIRONMENT_VERSION = "static_bap_env_v1"
# Generated scenarios draw seeds from [0, 2**31 - 1].
PROVIDER_SEED_UPPER_BOUND = 2**31


class StaticBAPEnvConsistencyError(RuntimeError):
    """Environment and shared core disagree; never an ordinary agent outcome."""


class StaticBAPEnv(gym.Env):
    """Sequential static schedule construction with masked candidate indices.

    Exactly one of ``scenario`` (fixed instance) or ``scenario_provider``
    (``provider(seed) -> BAPScenarioInstance``) must be given. Masked, out of
    range or non-integer actions raise without changing any state.
    """

    metadata = {"render_modes": ["ansi"], "render_fps": 1}

    def __init__(
        self,
        *,
        scenario: BAPScenarioInstance | None = None,
        scenario_provider: ScenarioProvider | None = None,
        max_vessels: int,
        time_scale_min: float = 1440.0,
        length_scale_m: float = 1000.0,
        policy_id: str = "external_agent",
        render_mode: str | None = None,
    ) -> None:
        if (scenario is None) == (scenario_provider is None):
            raise ValueError("Provide exactly one of scenario or scenario_provider.")
        if isinstance(max_vessels, bool) or not isinstance(max_vessels, Integral) or max_vessels <= 0:
            raise ValueError("max_vessels must be a positive integer.")
        for name, value in (("time_scale_min", time_scale_min), ("length_scale_m", length_scale_m)):
            if not is_finite_number(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number.")
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise ValueError("policy_id must be a non-empty string.")
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(f"Unsupported render_mode: {render_mode!r}.")
        if scenario_provider is not None and not callable(scenario_provider):
            raise TypeError("scenario_provider must be callable as provider(seed).")

        self.max_vessels = int(max_vessels)
        # candidate_positions emits two quay boundaries plus two clearance-adjusted
        # sides per existing placement: at most 2 + 2k <= 2 * max_vessels.
        self.action_capacity = 2 * self.max_vessels
        self.time_scale_min = float(time_scale_min)
        self.length_scale_m = float(length_scale_m)
        self.policy_id = policy_id
        self.render_mode = render_mode
        self.action_space = spaces.Discrete(self.action_capacity)
        self.observation_space = build_observation_space(self.max_vessels, self.action_capacity)

        if scenario is not None:
            self._validate_scenario(scenario)
        self._fixed_scenario = scenario
        self._provider = scenario_provider

        self._scenario: BAPScenarioInstance | None = None
        self._fingerprint: str | None = None
        self._vessels: tuple[BAPVesselInput, ...] = ()
        self._placements: tuple[BAPPlacement, ...] = ()
        self._decisions: tuple[StaticDecisionRecord, ...] = ()
        # Computed once per decision; shared by observation, mask and step.
        self._candidates: tuple[CandidateChoice, ...] = ()
        self._episode_return = 0.0
        self._terminated = False
        self._final_metrics: StaticMetrics | None = None
        self._needs_reset = True

    # ------------------------------------------------------------------ API

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        super().reset(seed=seed)
        if options:
            raise ValueError("StaticBAPEnv.reset does not accept options.")
        # A failed reset leaves no usable episode behind.
        self._needs_reset = True
        if self._provider is None:
            scenario = self._fixed_scenario
        else:
            generation_seed = int(self.np_random.integers(0, PROVIDER_SEED_UPPER_BOUND))
            scenario = self._provider(generation_seed)
            self._validate_scenario(scenario)
            if scenario.seed != generation_seed:
                raise ValueError("Scenario provider must record the drawn generation seed as scenario.seed.")
        vessels = ordered_vessels(scenario.vessels)
        candidates = self._evaluate_candidates(scenario, vessels[0], ())

        self._scenario = scenario
        self._fingerprint = scenario.content_fingerprint
        self._vessels = vessels
        self._placements = ()
        self._decisions = ()
        self._candidates = candidates
        self._episode_return = 0.0
        self._terminated = False
        self._final_metrics = None
        self._needs_reset = False
        return self._observation(), {
            "scenario_id": scenario.scenario_id,
            "scenario_seed": scenario.seed,
            "scenario_fingerprint": self._fingerprint,
            "scenario_split": scenario.split,
            "vessel_count": scenario.vessel_count,
            "environment_version": ENVIRONMENT_VERSION,
        }

    def step(self, action: Any) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        index = self._validate_action(action)
        decision_index = len(self._placements)
        vessel = self._vessels[decision_index]
        position, start, waiting = self._candidates[index]
        placement = placement_at(vessel, position, start)
        placements = (*self._placements, placement)
        reward = -waiting if waiting else 0.0
        episode_return = self._episode_return + reward
        record = StaticDecisionRecord(
            decision_index=decision_index,
            vessel_id=vessel.vessel_id,
            policy_id=self.policy_id,
            candidate_count=len(self._candidates),
            candidate_positions_m=tuple(x for x, _, _ in self._candidates),
            selected_candidate_index=index,
            selected_berth_position_m=position,
            selected_start_time_min=start,
            selected_waiting_time_min=waiting,
        )
        terminated = len(placements) == len(self._vessels)
        # Everything that can fail runs before any state is committed.
        if terminated:
            metrics = self._validate_final(placements, episode_return)
            candidates: tuple[CandidateChoice, ...] = ()
        else:
            metrics = None
            candidates = self._evaluate_candidates(
                self._scenario, self._vessels[decision_index + 1], placements,
            )

        self._placements = placements
        self._decisions = (*self._decisions, record)
        self._candidates = candidates
        self._episode_return = episode_return
        self._terminated = terminated
        self._final_metrics = metrics

        info: dict[str, Any] = {
            "decision_index": decision_index,
            "vessel_id": vessel.vessel_id,
            "candidate_count": record.candidate_count,
            "selected_candidate_index": index,
            "selected_berth_position_m": position,
            "selected_start_time_min": start,
            "incremental_waiting_time_min": waiting,
        }
        if terminated:
            info.update(
                total_waiting_time_min=metrics.total_waiting_time_min,
                episode_return=episode_return,
                objective_value=metrics.objective_value,
                schedule_valid=True,
                vessel_count_completed=len(placements),
                static_metrics=asdict(metrics),
            )
        return self._observation(), float(reward), terminated, False, info

    def action_masks(self) -> np.ndarray:
        """Boolean mask over the fixed action capacity for Maskable PPO.

        The first ``candidate_count`` indices are valid; all are False after
        termination. Reads the cached candidate list and never recomputes it.
        """

        if self._needs_reset:
            raise RuntimeError("Call reset() before action_masks().")
        mask = np.zeros(self.action_capacity, dtype=bool)
        mask[: len(self._candidates)] = True
        return mask

    def render(self) -> str | None:
        if self.render_mode is None:
            return None
        if self._needs_reset:
            return "StaticBAPEnv: call reset() first."
        lines = [
            f"StaticBAPEnv {self._scenario.scenario_id}: "
            f"{len(self._placements)}/{len(self._vessels)} vessels placed, "
            f"return {self._episode_return:.3f}",
        ]
        lines += [
            f"  {p.vessel_id}: x={p.berth_position_m:.3f} m, "
            f"[{p.berth_start_time_min:.3f}, {p.service_end_time_min:.3f}) min"
            for p in self._placements
        ]
        if not self._terminated:
            lines.append(f"  next {self._vessels[len(self._placements)].vessel_id}:")
            lines += [
                f"    [{j}] x={x:.3f} m, start={s:.3f}, wait={w:.3f}"
                for j, (x, s, w) in enumerate(self._candidates)
            ]
        return "\n".join(lines)

    def close(self) -> None:
        pass

    # ------------------------------------------------------- read-only state

    @property
    def scenario(self) -> BAPScenarioInstance | None:
        return self._scenario

    @property
    def ordered_vessels(self) -> tuple[BAPVesselInput, ...]:
        return self._vessels

    @property
    def placements(self) -> tuple[BAPPlacement, ...]:
        return self._placements

    @property
    def decision_records(self) -> tuple[StaticDecisionRecord, ...]:
        return self._decisions

    @property
    def current_candidates(self) -> tuple[CandidateChoice, ...]:
        """(berth_position_m, start_min, waiting_min) for the current vessel."""

        return self._candidates

    @property
    def episode_return(self) -> float:
        return self._episode_return

    @property
    def terminated(self) -> bool:
        return self._terminated

    @property
    def final_metrics(self) -> StaticMetrics | None:
        return self._final_metrics

    # ------------------------------------------------------------- internals

    def _validate_scenario(self, scenario: object) -> None:
        if not isinstance(scenario, BAPScenarioInstance):
            raise TypeError("Scenario must be a BAPScenarioInstance.")
        require_static_scenario(scenario)
        if scenario.vessel_count > self.max_vessels:
            raise ValueError(
                f"Scenario {scenario.scenario_id} has {scenario.vessel_count} vessels, "
                f"above max_vessels={self.max_vessels}; vessels are never truncated."
            )

    def _evaluate_candidates(
        self,
        scenario: BAPScenarioInstance,
        vessel: BAPVesselInput,
        placements: tuple[BAPPlacement, ...],
    ) -> tuple[CandidateChoice, ...]:
        choices = candidate_starts(vessel, placements, scenario)
        if not choices:
            raise StaticBAPEnvConsistencyError(
                f"No candidate for vessel {vessel.vessel_id}; StaticBAP v1 has no WAIT or skip."
            )
        if len(choices) > self.action_capacity:
            raise StaticBAPEnvConsistencyError(
                f"{len(choices)} candidates for vessel {vessel.vessel_id} exceed action "
                f"capacity {self.action_capacity}; the candidate generator changed."
            )
        return tuple(
            (position, start, waiting_time(vessel, placement_at(vessel, position, start)))
            for position, start in choices
        )

    def _validate_action(self, action: Any) -> int:
        if self._needs_reset:
            raise RuntimeError("Call reset() before step().")
        if self._terminated:
            raise RuntimeError("Episode has terminated; call reset() before another step().")
        if isinstance(action, np.ndarray):
            if action.shape != ():
                raise TypeError("Action must be a scalar candidate index.")
            action = action[()]
        if isinstance(action, (bool, np.bool_)) or not isinstance(action, (int, np.integer)):
            raise TypeError(f"Action must be an integer candidate index, not {type(action).__name__}.")
        index = int(action)
        if not 0 <= index < self.action_capacity:
            raise ValueError(f"Action {index} is outside action space [0, {self.action_capacity}).")
        if index >= len(self._candidates):
            raise ValueError(
                f"Action {index} is masked; valid candidate indices are 0..{len(self._candidates) - 1}."
            )
        return index

    def _validate_final(
        self,
        placements: tuple[BAPPlacement, ...],
        episode_return: float,
    ) -> StaticMetrics:
        scenario = self._scenario
        if [p.vessel_id for p in placements] != [v.vessel_id for v in self._vessels]:
            raise StaticBAPEnvConsistencyError("Final schedule does not place each vessel once in order.")
        violations = find_schedule_violations(
            scenario.vessels, placements, scenario.berth_length_m, scenario.min_clearance_m,
        )
        if violations:
            raise StaticBAPEnvConsistencyError(
                "Final schedule is invalid: " + "; ".join(v.message for v in violations)
            )
        total = total_waiting_time(scenario.vessels, placements)
        if not is_close(episode_return, -total):
            raise StaticBAPEnvConsistencyError("Episode return differs from negative total waiting.")
        metrics = calculate_static_metrics(scenario, placements)
        if not is_close(metrics.objective_value, total):
            raise StaticBAPEnvConsistencyError("Static metrics objective differs from total waiting.")
        if scenario.content_fingerprint != self._fingerprint:
            raise StaticBAPEnvConsistencyError("Scenario content changed during the episode.")
        return metrics

    def _observation(self) -> dict[str, Any]:
        return encode_observation(
            scenario=self._scenario,
            vessels=self._vessels,
            placements=self._placements,
            candidates=self._candidates,
            max_vessels=self.max_vessels,
            action_capacity=self.action_capacity,
            time_scale_min=self.time_scale_min,
            length_scale_m=self.length_scale_m,
        )
