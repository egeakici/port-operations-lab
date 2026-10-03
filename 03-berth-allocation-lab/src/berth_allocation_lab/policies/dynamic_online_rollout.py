"""Causal one-step lookahead over the currently visible vessel cohort."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass

from berth_allocation_lab.core import (
    BAPPlacement, candidate_positions, is_placement_feasible,
)
from berth_allocation_lab.envs.dynamic_visible_state import DynamicVisibleState

POLICY_ID = "dynamic_online_rollout_v1"


@dataclass(frozen=True)
class OnlineRolloutDecision:
    action: int
    scores: tuple[tuple[int, float], ...]
    runtime_seconds: float


class _VisibleContinuation:
    """Local state; all inputs come from DynamicVisibleState, never an env queue."""

    def __init__(self, visible: DynamicVisibleState) -> None:
        self.time = visible.current_time_min
        self.quay = visible.berth_length_m
        self.clearance = visible.min_clearance_m
        self.vessels = {v.vessel_id: v for v in visible.vessels_by_slot}
        self.status = dict(zip(self.vessels, visible.statuses_by_slot))
        self.active = {p.vessel_id: p for p in visible.active_placements}
        self.waiting_cost = 0.0

    def _positions(self, vessel_id: str) -> tuple[float, ...]:
        vessel = self.vessels[vessel_id]
        active = tuple(self.active.values())
        return tuple(x for x in candidate_positions(vessel, active, self.quay, self.clearance)
                     if is_placement_feasible(vessel, x, self.time, active,
                                              self.quay, self.clearance))

    def assign(self, vessel_id: str, position: float) -> None:
        if self.status[vessel_id] != "WAITING" or position not in self._positions(vessel_id):
            raise ValueError("Visible rollout assignment is not immediately feasible.")
        vessel = self.vessels[vessel_id]
        self.active[vessel_id] = BAPPlacement(vessel_id, position, self.time,
                                               vessel.length_m, vessel.service_time_min)
        self.status[vessel_id] = "IN_SERVICE"

    def advance(self) -> None:
        times = [p.service_end_time_min for p in self.active.values() if p.service_end_time_min > self.time]
        times += [v.arrival_time_min for v in self.vessels.values()
                  if self.status[v.vessel_id] == "ANNOUNCED" and v.arrival_time_min > self.time]
        if not times:
            raise ValueError("Visible cohort has unresolved vessels and no future event.")
        next_time = min(times)
        self.waiting_cost += sum(s == "WAITING" for s in self.status.values()) * (next_time - self.time)
        self.time = next_time
        for vessel_id in sorted(tuple(self.active)):
            if self.active[vessel_id].service_end_time_min == next_time:
                del self.active[vessel_id]
                self.status[vessel_id] = "COMPLETED"
        for vessel_id in sorted(self.vessels):
            vessel = self.vessels[vessel_id]
            if self.status[vessel_id] == "ANNOUNCED" and vessel.arrival_time_min == next_time:
                self.status[vessel_id] = "WAITING"

    def finish_with_fcfs(self) -> float:
        while any(s in {"WAITING", "ANNOUNCED"} for s in self.status.values()):
            choices = ((self.vessels[vessel_id].arrival_time_min, vessel_id, position)
                       for vessel_id, state in self.status.items() if state == "WAITING"
                       for position in self._positions(vessel_id))
            chosen = min(choices, default=None)
            if chosen is None:
                self.advance()
            else:
                self.assign(chosen[1], chosen[2])
        return self.waiting_cost

    def finish_after_wait(self) -> float:
        """At the next revealed decision, compare legal starts before FCFS resumes."""
        while True:
            choices = ((self.vessels[vessel_id].arrival_time_min, vessel_id, position)
                       for vessel_id, state in self.status.items() if state == "WAITING"
                       for position in self._positions(vessel_id))
            available = tuple(choices)
            if available:
                return min(self._score_next_assignment(vessel_id, position)
                           for _, vessel_id, position in available)
            self.advance()

    def _score_next_assignment(self, vessel_id: str, position: float) -> float:
        branch = copy.deepcopy(self)
        branch.assign(vessel_id, position)
        return branch.finish_with_fcfs()


def score_visible_action(visible: DynamicVisibleState, action: int) -> float:
    """Future queue cost for one legal action, with no hidden-vessel clairvoyance."""
    continuation = _VisibleContinuation(visible)
    if action == 0:
        if not visible.wait_legal:
            raise ValueError("WAIT is masked in the visible state.")
        continuation.advance()
        return continuation.finish_after_wait()
    else:
        choice = next((choice for choice in visible.legal_choices if choice[0] == action), None)
        if choice is None:
            raise ValueError(f"Assignment action {action} is not legal in the visible state.")
        continuation.assign(choice[1], choice[3])
    return continuation.finish_with_fcfs()


def online_rollout_choice(visible: DynamicVisibleState) -> OnlineRolloutDecision:
    """Evaluate every current legal action; tie-break by action index."""
    started = time.perf_counter()
    actions = ((0,) if visible.wait_legal else ()) + tuple(choice[0] for choice in visible.legal_choices)
    if not actions:
        raise ValueError("No legal decision exists in the visible state.")
    scores = tuple((action, score_visible_action(visible, action)) for action in actions)
    best = min(scores, key=lambda pair: (pair[1], pair[0]))[0]
    return OnlineRolloutDecision(best, scores, time.perf_counter() - started)


def online_rollout_action(env) -> int:
    """Policy entry point reads only the public visible-state snapshot."""
    return online_rollout_choice(env.visible_state()).action
