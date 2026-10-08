"""Pure event-index replay and policy-visible snapshots from recorded events."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any

from berth_allocation_lab.replay.records import ReplayError, ReplayRun


@dataclass(frozen=True)
class ReplayEvent:
    time_min: float
    kind: str
    vessel_id: str | None
    origin: str
    decision_index: int | None
    source_index: int | None


@dataclass(frozen=True)
class ReplaySnapshot:
    time_min: float
    waiting: tuple[str, ...]
    announced: tuple[str, ...]
    active: tuple[str, ...]
    reserved: tuple[str, ...]
    completed: tuple[str, ...]


def events_for(run: ReplayRun, horizon_min: float) -> tuple[ReplayEvent, ...]:
    if run.events is not None:
        events = [ReplayEvent(float(e["simulation_time_min"]), e["event_type"],
                              e.get("vessel_id"), "recorded", e.get("decision_index"),
                              e["event_index"]) for e in run.events]
        known = {(e.kind, e.vessel_id, e.time_min) for e in events}
        extra = []
        for vessel in run.vessels:
            for kind, time in (("SERVICE_START", vessel.berth_start_time_min),
                               ("SERVICE_COMPLETION", vessel.service_end_time_min)):
                counterpart = "ASSIGNMENT" if kind == "SERVICE_START" else kind
                if (counterpart, vessel.vessel_id, time) not in known:
                    extra.append(ReplayEvent(time, kind, vessel.vessel_id,
                                             "derived from recorded placement", None, None))
        if extra:
            priority = {"SERVICE_COMPLETION": 0, "VESSEL_ARRIVAL": 1,
                        "HORIZON_ENTRY": 2, "SERVICE_START": 3}
            events.extend(extra)
            events.sort(key=lambda e: (e.time_min, priority.get(e.kind, 4),
                                       e.source_index if e.source_index is not None else 10**9))
        return tuple(events)
    priority = {"SERVICE_COMPLETION": 0, "VESSEL_ARRIVAL": 1,
                "HORIZON_ENTRY": 2, "SERVICE_START": 3}
    derived = []
    for vessel in run.vessels:
        if vessel.arrival_time_min > 0:
            derived.append(ReplayEvent(max(0.0, vessel.arrival_time_min - horizon_min),
                                       "HORIZON_ENTRY", vessel.vessel_id,
                                       "derived from recorded arrival", None, None))
        derived.extend((
            ReplayEvent(vessel.arrival_time_min, "VESSEL_ARRIVAL", vessel.vessel_id,
                        "derived from recorded arrival", None, None),
            ReplayEvent(vessel.berth_start_time_min, "SERVICE_START", vessel.vessel_id,
                        "derived from recorded placement", None, None),
            ReplayEvent(vessel.service_end_time_min, "SERVICE_COMPLETION", vessel.vessel_id,
                        "derived from recorded placement", None, None),
        ))
    return tuple(sorted(derived, key=lambda e: (e.time_min, priority[e.kind], e.vessel_id or "")))


def index_at_time(events: tuple[ReplayEvent, ...], time_min: float) -> int:
    if not events:
        return -1
    return bisect_right([event.time_min for event in events], time_min) - 1


def step_index(events: tuple[ReplayEvent, ...], index: int, direction: int) -> int:
    if not events:
        return -1
    return max(0, min(len(events) - 1, index + direction))


def switch_time(events: tuple[ReplayEvent, ...], absolute_time_min: float) -> int:
    """Preserve absolute time across policy trajectories, clamping to their duration."""
    return index_at_time(events, min(max(absolute_time_min, 0.0), events[-1].time_min))


def snapshot(run: ReplayRun, horizon_min: float, time_min: float,
             events: tuple[ReplayEvent, ...] | None = None,
             event_index: int | None = None) -> ReplaySnapshot:
    events = events_for(run, horizon_min) if events is None else events
    index = index_at_time(events, time_min) if event_index is None else event_index
    if index >= len(events) or (index >= 0 and events[index].time_min > time_min + 1e-6):
        raise ReplayError("Snapshot event index lies after requested time.")
    status = {v.vessel_id: "HIDDEN" for v in run.vessels}
    for event in events[:index + 1]:
        vessel = event.vessel_id
        if vessel is None:
            continue
        if vessel not in status:
            raise ReplayError(f"Unknown vessel in recorded event: {vessel}")
        if event.kind == "HORIZON_ENTRY":
            if status[vessel] == "HIDDEN":
                status[vessel] = "ANNOUNCED"
        elif event.kind == "VESSEL_ARRIVAL":
            status[vessel] = "WAITING"
        elif event.kind in {"ASSIGNMENT", "SERVICE_START"}:
            status[vessel] = "ASSIGNED"
        elif event.kind == "SERVICE_COMPLETION":
            status[vessel] = "COMPLETED"
    by_id = {v.vessel_id: v for v in run.vessels}
    def listed(name: str) -> tuple[str, ...]:
        return tuple(sorted(vessel for vessel, state in status.items() if state == name))
    assigned = listed("ASSIGNED")
    active = tuple(v for v in assigned if by_id[v].berth_start_time_min <= time_min <
                   by_id[v].service_end_time_min)
    reserved = tuple(v for v in assigned if time_min < by_id[v].berth_start_time_min)
    completed = tuple(sorted(set(listed("COMPLETED")) | {
        v for v in assigned if time_min >= by_id[v].service_end_time_min}))
    return ReplaySnapshot(time_min, listed("WAITING"), listed("ANNOUNCED"),
                          active, reserved, completed)


def decision_context(run: ReplayRun, horizon_min: float,
                     decision_index: int) -> tuple[dict[str, Any], ReplaySnapshot]:
    if run.decisions is None or run.events is None:
        raise ReplayError("Recorded decision/event history is unavailable; no action context can be shown.")
    decision = run.decisions[decision_index]
    matches = [e for e in run.events if e.get("decision_index") == decision_index and
               e.get("event_type") in {"WAIT", "ASSIGNMENT"}]
    if len(matches) != 1:
        raise ReplayError("Recorded decision has no unique event context.")
    event_index = matches[0]["event_index"]
    events = events_for(run, horizon_min)
    position = next((i for i, e in enumerate(events)
                     if e.source_index == event_index), None)
    if position is None:
        raise ReplayError("Recorded decision event is absent from replay timeline.")
    return decision, snapshot(run, horizon_min, float(decision["simulation_time_min"]),
                              events, position - 1)


def compare_compatible(*runs: ReplayRun) -> None:
    if not runs or len({r.fingerprint for r in runs}) != 1:
        raise ReplayError("Policy comparison requires one identical physical fingerprint.")
    if len({r.scenario_id for r in runs}) != 1 or len({r.source_split for r in runs}) != 1:
        raise ReplayError("Policy comparison requires the same scenario and source split.")
    physical = [tuple(sorted((v.vessel_id, v.arrival_time_min, v.length_m,
                              v.service_time_min) for v in r.vessels)) for r in runs]
    if any(item != physical[0] for item in physical[1:]):
        raise ReplayError("Policy comparison vessel inputs differ.")


def space_time_rectangles(run: ReplayRun) -> tuple[tuple[str, float, float, float, float], ...]:
    """Retrospective geometry: id, x0/x1 meters, y0/y1 simulation minutes."""
    return tuple((v.vessel_id, v.berth_position_m, v.berth_position_m + v.length_m,
                  v.berth_start_time_min, v.service_end_time_min) for v in run.vessels)
