"""Chronological online berth allocation with horizon-bounded observations."""

from __future__ import annotations

import heapq
from numbers import Integral
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from berth_allocation_lab.core import (
    BAPPlacement, candidate_positions, find_schedule_violations,
    is_placement_feasible, total_waiting_time,
)
from berth_allocation_lab.core.numerics import NUMERICAL_TOLERANCE, is_close, is_finite_number
from berth_allocation_lab.data import BAPScenarioInstance, BAPVesselInput
from berth_allocation_lab.envs.dynamic_observation import (
    OBSERVATION_VERSION, build_dynamic_observation_space, encode_dynamic_observation,
)
from berth_allocation_lab.envs.static_bap_env import PROVIDER_SEED_UPPER_BOUND

ENVIRONMENT_VERSION = "dynamic_bap_env_v1"
_EVENT_PRIORITY = {"SERVICE_COMPLETION": 0, "VESSEL_ARRIVAL": 1, "HORIZON_ENTRY": 2}


class DynamicBAPEnvConsistencyError(RuntimeError):
    """Physical, event or reward accounting invariant was violated."""


class DynamicBAPEnv(gym.Env):
    """Choose a waiting vessel and a position now, or deliberately WAIT.

    Action 0 is WAIT. Action ``1 + slot * P + candidate_index`` is an
    immediate assignment; P = 2 * max_vessels. Slots are allocated upon first
    reveal and never reused. Masked actions raise before changing state.
    """

    metadata = {"render_modes": ["ansi"], "render_fps": 1}

    def __init__(
        self, *, scenario: BAPScenarioInstance | None = None,
        scenario_provider=None, max_vessels: int,
        future_horizon_min: float | None = None,
        time_scale_min: float = 1440.0, length_scale_m: float = 1000.0,
        render_mode: str | None = None,
    ) -> None:
        if (scenario is None) == (scenario_provider is None):
            raise ValueError("Provide exactly one of scenario or scenario_provider.")
        if isinstance(max_vessels, bool) or not isinstance(max_vessels, Integral) or max_vessels <= 0:
            raise ValueError("max_vessels must be a positive integer.")
        for name, value in (("future_horizon_min", future_horizon_min),
                            ("time_scale_min", time_scale_min), ("length_scale_m", length_scale_m)):
            if value is not None and (not is_finite_number(value) or
                                      (value < 0 if name == "future_horizon_min" else value <= 0)):
                raise ValueError(f"{name} must be finite and non-negative/positive as appropriate.")
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(f"Unsupported render_mode: {render_mode}.")
        if scenario_provider is not None and not callable(scenario_provider):
            raise TypeError("scenario_provider must be callable.")
        self.max_vessels = int(max_vessels)
        # At most M-1 vessels can be active when a waiting vessel is considered.
        # candidate_positions emits two quay boundaries plus two sides per active vessel.
        self.candidate_capacity = 2 * self.max_vessels
        self.action_space = spaces.Discrete(1 + self.max_vessels * self.candidate_capacity)
        self.observation_space = build_dynamic_observation_space(self.max_vessels, self.action_space.n)
        self.time_scale_min = float(time_scale_min)
        self.length_scale_m = float(length_scale_m)
        self._horizon_override = None if future_horizon_min is None else float(future_horizon_min)
        self.render_mode = render_mode
        self._fixed_scenario = scenario
        self._provider = scenario_provider
        if scenario is not None:
            self._validate_scenario(scenario)
        self._needs_reset = True

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        if options:
            raise ValueError("DynamicBAPEnv.reset does not accept options.")
        self._needs_reset = True
        if self._provider is None:
            scenario = self._fixed_scenario
        else:
            sample_seed = getattr(self._provider, "sample_seed", None)
            generation_seed = (int(sample_seed(self.np_random)) if callable(sample_seed)
                               else int(self.np_random.integers(0, PROVIDER_SEED_UPPER_BOUND)))
            scenario = self._provider(generation_seed)
            self._validate_scenario(scenario)
            if scenario.seed != generation_seed:
                raise ValueError("Provider must record its generation seed.")
        self._scenario = scenario
        self._scenario_fingerprint = scenario.content_fingerprint
        self.future_horizon_min = (self._horizon_override if self._horizon_override is not None
                                   else float(scenario.future_horizon_min))
        self.current_time_min = 0.0
        self._drain_limit_min = max(v.arrival_time_min for v in scenario.vessels) + scenario.max_drain_extension_min
        self._vessel_by_id = {v.vessel_id: v for v in scenario.vessels}
        self._status = {v.vessel_id: "HIDDEN" for v in scenario.vessels}
        self._slot_ids: list[str] = []
        self._slot_by_id: dict[str, int] = {}
        self._placement_by_id: dict[str, BAPPlacement] = {}
        self._placements: list[BAPPlacement] = []
        self._events: list[tuple[float, int, str, str]] = []
        self._choices: dict[int, tuple[str, int, float]] = {}
        self._candidate_by_slot: dict[int, tuple[float, ...]] = {}
        self._event_records: list[dict[str, Any]] = []
        self._decision_records: list[dict[str, Any]] = []
        self._waiting_cost = 0.0
        self._episode_return = 0.0
        self._terminated = False
        self._truncated = False
        self._forced_advances = 0
        self._peak_queue = 0
        self._last_event_time = 0.0
        for vessel in scenario.vessels:
            self._push(vessel.arrival_time_min, "VESSEL_ARRIVAL", vessel.vessel_id)
            if self.future_horizon_min > 0 and vessel.arrival_time_min > 0:
                self._push(max(0.0, vessel.arrival_time_min - self.future_horizon_min),
                           "HORIZON_ENTRY", vessel.vessel_id)
        self._needs_reset = False
        self._advance_to_decision()
        return self._observation(), self._info()

    def step(self, action: Any):
        index = self._validate_action(action)
        decision_time = self.current_time_min
        decision_index = len(self._decision_records)
        event_start = len(self._event_records)
        cost_before = self._waiting_cost
        if index == 0:
            self._record_event("WAIT", None, "agent_wait", decision_index,
                               selected_action_type="wait", wait_selected=True,
                               feasible_assignment_count=len(self._choices))
            action_type, vessel_id, candidate_index, position = "WAIT", None, None, None
            self._advance_to_decision(force_event=True)
        else:
            vessel_id, candidate_index, position = self._choices[index]
            vessel = self._vessel_by_id[vessel_id]
            placement = BAPPlacement(vessel_id, position, decision_time,
                                     vessel.length_m, self._service_duration_min(vessel))
            if not is_placement_feasible(vessel, position, decision_time,
                                         self._active_placements(), self._scenario.berth_length_m,
                                         self._scenario.min_clearance_m):
                raise DynamicBAPEnvConsistencyError("Cached action is no longer feasible.")
            self._status[vessel_id] = "IN_SERVICE"
            self._placements.append(placement)
            self._placement_by_id[vessel_id] = placement
            self._push(placement.service_end_time_min, "SERVICE_COMPLETION", vessel_id)
            self._record_event("ASSIGNMENT", vessel_id, "agent_assignment", decision_index,
                               berth_position_m=position, selected_action_type="assignment",
                               selected_vessel_id=vessel_id,
                               selected_candidate_index=candidate_index,
                               selected_berth_position_m=position,
                               wait_selected=False)
            action_type = "ASSIGN"
            self._advance_to_decision()
        reward = -(self._waiting_cost - cost_before)
        self._episode_return += reward
        if self._terminated and not is_close(self._episode_return, -self._waiting_cost):
            raise DynamicBAPEnvConsistencyError("Episode return differs from integrated queue cost.")
        record = {
            "decision_index": decision_index, "simulation_time_min": decision_time,
            "action_type": action_type, "selected_vessel_id": vessel_id,
            "selected_candidate_index": candidate_index,
            "selected_berth_position_m": position,
            "service_start_time_min": decision_time if vessel_id is not None else None,
            "reward": reward, "cumulative_waiting_cost_min": self._waiting_cost,
        }
        self._decision_records.append(record)
        info = self._info()
        info.update(record)
        info["events_processed"] = len(self._event_records) - event_start
        return self._observation(), float(reward), self._terminated, self._truncated, info

    def action_masks(self) -> np.ndarray:
        if self._needs_reset:
            raise RuntimeError("Call reset() before action_masks().")
        mask = np.zeros(self.action_space.n, dtype=bool)
        if not self._terminated and not self._truncated:
            mask[0] = bool(self._choices and self._has_visible_future_event())
            for action in self._choices:
                mask[action] = True
        return mask

    def _has_visible_future_event(self) -> bool:
        """Use revealed vessel state only; the internal event queue includes hidden arrivals."""
        return any(
            (self._status[vessel_id] == "ANNOUNCED"
             and self._vessel_by_id[vessel_id].arrival_time_min > self.current_time_min)
            or (self._status[vessel_id] == "IN_SERVICE"
                and self._placement_by_id[vessel_id].service_end_time_min > self.current_time_min)
            for vessel_id in self._slot_ids
        )

    def render(self) -> str | None:
        if self.render_mode is None:
            return None
        if self._needs_reset:
            return "DynamicBAPEnv: call reset() first."
        return (f"DynamicBAPEnv t={self.current_time_min:.3f} min, "
                f"waiting={sum(s == 'WAITING' for s in self._status.values())}, "
                f"active={sum(s == 'IN_SERVICE' for s in self._status.values())}, "
                f"completed={sum(s == 'COMPLETED' for s in self._status.values())}")

    def close(self) -> None:
        pass

    @property
    def placements(self) -> tuple[BAPPlacement, ...]:
        return tuple(self._placements)

    @property
    def event_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(record.copy() for record in self._event_records)

    @property
    def decision_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(record.copy() for record in self._decision_records)

    @property
    def episode_return(self) -> float:
        return self._episode_return

    @property
    def terminated(self) -> bool:
        return self._terminated

    @property
    def truncated(self) -> bool:
        return self._truncated

    @property
    def legal_choices(self) -> tuple[tuple[int, str, int, float, float], ...]:
        """Public online choices; no hidden vessels or future event times."""
        return tuple((action, vessel_id, candidate_index, position,
                      self._vessel_by_id[vessel_id].arrival_time_min)
                     for action, (vessel_id, candidate_index, position) in self._choices.items())

    def _validate_scenario(self, scenario: object) -> None:
        if not isinstance(scenario, BAPScenarioInstance):
            raise TypeError("Scenario must be BAPScenarioInstance.")
        if scenario.formulation != "dynamic":
            raise ValueError("DynamicBAPEnv requires a dynamic scenario.")
        if scenario.future_horizon_min is None and self._horizon_override is None:
            raise ValueError("Dynamic scenario requires a horizon or constructor override.")
        if scenario.vessel_count > self.max_vessels:
            raise ValueError("Scenario exceeds max_vessels; no truncation is allowed.")
        ids = [v.vessel_id for v in scenario.vessels]
        if len(ids) != len(set(ids)):
            raise ValueError("Dynamic scenario vessel IDs must be unique.")

    def _push(self, time: float, kind: str, vessel_id: str) -> None:
        heapq.heappush(self._events, (float(time), _EVENT_PRIORITY[kind], vessel_id, kind))

    def _reveal(self, vessel_id: str, status: str) -> None:
        if vessel_id not in self._slot_by_id:
            slot = len(self._slot_ids)
            if slot >= self.max_vessels:
                raise DynamicBAPEnvConsistencyError("Visible slot capacity exceeded.")
            self._slot_ids.append(vessel_id)
            self._slot_by_id[vessel_id] = slot
        self._status[vessel_id] = status

    def _record_event(self, kind: str, vessel_id: str | None, transition: str,
                      decision_index: int | None = None, **extra: Any) -> None:
        record = {
            "event_index": len(self._event_records), "event_type": kind,
            "transition_type": transition, "simulation_time_min": self.current_time_min,
            "event_time_min": self.current_time_min, "vessel_id": vessel_id,
            "waiting_vessel_count": sum(s == "WAITING" for s in self._status.values()),
            "berthed_vessel_count": sum(s == "IN_SERVICE" for s in self._status.values()),
            "decision_index": decision_index,
            "delta_time_min": self.current_time_min - self._last_event_time,
        }
        record.update(extra)
        self._event_records.append(record)
        self._last_event_time = self.current_time_min

    def _active_placements(self) -> tuple[BAPPlacement, ...]:
        return tuple(self._placement_by_id[vessel_id] for vessel_id in self._slot_ids
                     if self._status[vessel_id] == "IN_SERVICE")

    def _service_duration_min(self, vessel: BAPVesselInput) -> float:
        return vessel.service_time_min

    def _process_next_timestamp(self) -> None:
        timestamp = self._events[0][0]
        if timestamp < self.current_time_min - NUMERICAL_TOLERANCE:
            raise DynamicBAPEnvConsistencyError("Event time moved backwards.")
        delta = timestamp - self.current_time_min
        self._waiting_cost += sum(s == "WAITING" for s in self._status.values()) * delta
        self.current_time_min = timestamp
        while self._events and is_close(self._events[0][0], timestamp):
            _, _, vessel_id, kind = heapq.heappop(self._events)
            status = self._status[vessel_id]
            if kind == "SERVICE_COMPLETION":
                if status != "IN_SERVICE":
                    raise DynamicBAPEnvConsistencyError("Completion for non-active vessel.")
                self._status[vessel_id] = "COMPLETED"
                position = self._placement_by_id[vessel_id].berth_position_m
                self._record_event(kind, vessel_id, "system_event", berth_position_m=position)
            elif kind == "VESSEL_ARRIVAL":
                if status not in {"HIDDEN", "ANNOUNCED"}:
                    raise DynamicBAPEnvConsistencyError("Duplicate or invalid arrival.")
                self._reveal(vessel_id, "WAITING")
                self._peak_queue = max(self._peak_queue,
                                       sum(s == "WAITING" for s in self._status.values()))
                self._record_event(kind, vessel_id, "system_event")
            elif status == "HIDDEN":
                self._reveal(vessel_id, "ANNOUNCED")
                self._record_event(kind, vessel_id, "system_event")

    def _cache_choices(self) -> None:
        self._choices = {}
        self._candidate_by_slot = {}
        if self._terminated or self._truncated:
            return
        active = self._active_placements()
        for slot, vessel_id in enumerate(self._slot_ids):
            if self._status[vessel_id] != "WAITING":
                continue
            vessel = self._vessel_by_id[vessel_id]
            positions = tuple(x for x in candidate_positions(
                vessel, active, self._scenario.berth_length_m, self._scenario.min_clearance_m)
                if is_placement_feasible(vessel, x, self.current_time_min, active,
                                         self._scenario.berth_length_m, self._scenario.min_clearance_m))
            if len(positions) > self.candidate_capacity:
                raise DynamicBAPEnvConsistencyError("Candidate capacity bound violated.")
            self._candidate_by_slot[slot] = positions
            for candidate_index, position in enumerate(positions):
                action = 1 + slot * self.candidate_capacity + candidate_index
                self._choices[action] = (vessel_id, candidate_index, position)

    def _advance_to_decision(self, *, force_event: bool = False) -> None:
        if not force_event:
            self._cache_choices()
            if self._choices:
                return
        while True:
            if all(s == "COMPLETED" for s in self._status.values()):
                self._validate_final()
                self._terminated = True
                self._choices = {}
                return
            if not self._events:
                raise DynamicBAPEnvConsistencyError("Unresolved vessels with no future event.")
            next_time = self._events[0][0]
            if next_time > self._drain_limit_min + NUMERICAL_TOLERANCE:
                delta = self._drain_limit_min - self.current_time_min
                previous_time = self.current_time_min
                if delta > 0:
                    self._waiting_cost += sum(s == "WAITING" for s in self._status.values()) * delta
                    self._forced_advances += 1
                self.current_time_min = self._drain_limit_min
                self._truncated = True
                self._choices = {}
                self._record_event("DRAIN_LIMIT", None, "system_event")
                if delta > 0:
                    self._record_event("AUTOMATIC_ADVANCE", None, "automatic_advance",
                                       advance_from_time_min=previous_time,
                                       advance_duration_min=delta,
                                       selected_action_type="none", wait_selected=False)
                return
            automatic = not force_event and next_time > self.current_time_min + NUMERICAL_TOLERANCE
            previous_time = self.current_time_min
            self._forced_advances += int(automatic)
            self._process_next_timestamp()
            if automatic:
                self._record_event("AUTOMATIC_ADVANCE", None, "automatic_advance",
                                   advance_from_time_min=previous_time,
                                   advance_duration_min=self.current_time_min - previous_time,
                                   selected_action_type="none", wait_selected=False)
            force_event = False
            self._cache_choices()
            if self._choices:
                return

    def _validate_final(self) -> None:
        scenario = self._scenario
        violations = find_schedule_violations(
            scenario.vessels, self._placements, scenario.berth_length_m,
            scenario.min_clearance_m)
        if violations:
            raise DynamicBAPEnvConsistencyError("Invalid final schedule: " +
                                                "; ".join(v.message for v in violations))
        for placement in self._placements:
            if not is_close(placement.service_end_time_min,
                            placement.berth_start_time_min +
                            self._service_duration_min(self._vessel_by_id[placement.vessel_id])):
                raise DynamicBAPEnvConsistencyError("Service duration mismatch.")
        total = total_waiting_time(scenario.vessels, self._placements)
        if not is_close(self._waiting_cost, total):
            raise DynamicBAPEnvConsistencyError("Integrated queue cost differs from total waiting.")
        if scenario.content_fingerprint != self._scenario_fingerprint:
            raise DynamicBAPEnvConsistencyError("Scenario content changed during episode.")

    def _validate_action(self, action: Any) -> int:
        if self._needs_reset:
            raise RuntimeError("Call reset() before step().")
        if self._terminated or self._truncated:
            raise RuntimeError("Episode is over; reset before step().")
        if isinstance(action, np.ndarray):
            if action.shape != ():
                raise TypeError("Action must be a scalar integer.")
            action = action[()]
        if isinstance(action, (bool, np.bool_)) or not isinstance(action, (int, np.integer)):
            raise TypeError("Action must be an integer.")
        index = int(action)
        if not 0 <= index < self.action_space.n:
            raise ValueError("Action is outside action space.")
        if not self.action_masks()[index]:
            raise ValueError(f"Action {index} is masked.")
        return index

    def _observation(self):
        return encode_dynamic_observation(self)

    def _info(self) -> dict[str, Any]:
        info = {
            "environment_version": ENVIRONMENT_VERSION,
            "observation_version": OBSERVATION_VERSION,
            "scenario_id": self._scenario.scenario_id,
            "scenario_fingerprint": self._scenario_fingerprint,
            "scenario_seed": self._scenario.seed,
            "scenario_split": self._scenario.split,
            "simulation_time_min": self.current_time_min,
            "simulation_end_time_min": self.current_time_min,
            "nominal_duration_min": self._scenario.nominal_duration_min,
            "future_horizon_min": self.future_horizon_min,
            "termination_mode": self._scenario.termination_mode,
            "max_drain_extension_min": self._scenario.max_drain_extension_min,
            "waiting_cost_min": self._waiting_cost,
            "episode_return": self._episode_return,
            "vessel_count_completed": sum(s == "COMPLETED" for s in self._status.values()),
            "forced_advances": self._forced_advances,
            "peak_waiting_queue": self._peak_queue,
        }
        if self._terminated:
            info.update(schedule_valid=True, total_waiting_time_min=self._waiting_cost,
                        vessel_count=len(self._scenario.vessels),
                        vessel_count_unresolved=0,
                        drain_duration_min=max(0.0, self.current_time_min - self._scenario.arrival_generation_end_min))
        if self._truncated:
            info.update(schedule_valid=False,
                        vessel_count_unresolved=sum(v != "COMPLETED" for v in self._status.values()),
                        drain_duration_min=max(0.0, self.current_time_min - self._scenario.arrival_generation_end_min),
                        unresolved_vessel_ids=tuple(sorted(k for k, v in self._status.items()
                                                           if v != "COMPLETED")))
        return info
