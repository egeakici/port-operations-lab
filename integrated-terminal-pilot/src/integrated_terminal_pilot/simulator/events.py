"""Kernel event types, D22 priorities and the deterministic event queue.

Total order of queue entries (integration specification §8.1, D22)::

    (time_min, priority, stable_key, sequence)

* ``time_min`` - finite, >= the clock when scheduled (``KernelTimeError`` otherwise).
* ``priority`` - the frozen D22 table below; releases precede acquisitions.
* ``stable_key`` - the entity id the event concerns (vessel, work order, container).
* ``sequence`` - monotonic scheduling counter (also the ``KE-nnnnnnnn`` event id).

Events whose times are within ``TIME_TOL`` of the earliest pending time form one
timestamp group and are processed together in (priority, key, sequence) order.
An event scheduled *during* the processing of a group at the group's own
timestamp joins the remainder of that group (it is never processed earlier than
an event already processed, so there is no priority regression).

Entries are plain tuples, so the queue is plain data and a ``list`` copy clones
it. Stale entries (superseded ``rate_generation`` / timer generation) are
discarded when popped; they are never processed.

Decision points (BERTH, CRANE, DISPATCH/YARD) are *phases* that follow each
timestamp group (spec §7, §8.2 steps 4-5), not queue entries; retries after a
capacity-freeing event therefore happen in the same timestamp without polling.
"""

from __future__ import annotations

import heapq
import math

from berth_allocation_lab.core.numerics import NUMERICAL_TOLERANCE

from integrated_terminal_pilot.simulator.errors import KernelTimeError

# Same-timestamp grouping tolerance: Project 03 ``is_close`` (absolute 1e-9 min), spec §8.1.
TIME_TOL = NUMERICAL_TOLERANCE

WORK_ORDER_COMPLETED = "WORK_ORDER_COMPLETED"
VESSEL_HANDLING_COMPLETED = "VESSEL_HANDLING_COMPLETED"
VESSEL_DEPARTED = "VESSEL_DEPARTED"
BERTHING_PREP_COMPLETED = "BERTHING_PREP_COMPLETED"
LOAD_WAIT_TIMEOUT = "LOAD_WAIT_TIMEOUT"
GATE_IN_ARRIVAL = "GATE_IN_ARRIVAL"
PICKUP_DUE = "PICKUP_DUE"
VESSEL_ARRIVAL = "VESSEL_ARRIVAL"
HORIZON_ENTRY = "HORIZON_ENTRY"

# Frozen D22 priority table (integration specification §8.1).
EVENT_PRIORITY = {
    WORK_ORDER_COMPLETED: 10,
    VESSEL_HANDLING_COMPLETED: 20,
    VESSEL_DEPARTED: 30,
    BERTHING_PREP_COMPLETED: 40,
    LOAD_WAIT_TIMEOUT: 50,
    GATE_IN_ARRIVAL: 60,
    PICKUP_DUE: 65,
    VESSEL_ARRIVAL: 70,
    HORIZON_ENTRY: 80,
}
# Events that open a berth decision epoch (D07).
BERTH_EPOCH_EVENTS = frozenset({VESSEL_DEPARTED, VESSEL_ARRIVAL, HORIZON_ENTRY})
# Exogenous events that are hidden until they occur (spec §10) - removed by observable_clone().
HIDDEN_LANDSIDE_EVENTS = frozenset({GATE_IN_ARRIVAL, PICKUP_DUE})

# Queue entry layout.
E_TIME, E_PRIORITY, E_KEY, E_SEQ, E_TYPE, E_PAYLOAD, E_GENERATION = range(7)


def event_id(sequence: int) -> str:
    return f"KE-{sequence:08d}"


def push_event(queue: list, now_min: float, sequence: int, time_min: float, event_type: str,
               key: str, payload: tuple = (), generation: int = 0) -> tuple:
    """Schedule one event; returns the entry. ``sequence`` must come from the kernel counter."""
    if not math.isfinite(time_min) or time_min < 0.0:
        raise KernelTimeError(f"{event_type} {key}: event time {time_min!r} is not finite and >= 0.")
    if time_min < now_min - TIME_TOL:
        raise KernelTimeError(f"{event_type} {key}: event time {time_min} precedes clock {now_min}.")
    entry = (float(time_min), EVENT_PRIORITY[event_type], key, sequence, event_type, payload,
             generation)
    heapq.heappush(queue, entry)
    return entry


__all__ = [
    "BERTHING_PREP_COMPLETED", "BERTH_EPOCH_EVENTS", "EVENT_PRIORITY", "E_GENERATION", "E_KEY",
    "E_PAYLOAD", "E_PRIORITY", "E_SEQ", "E_TIME", "E_TYPE", "GATE_IN_ARRIVAL",
    "HIDDEN_LANDSIDE_EVENTS", "HORIZON_ENTRY", "LOAD_WAIT_TIMEOUT", "PICKUP_DUE", "TIME_TOL",
    "VESSEL_ARRIVAL", "VESSEL_DEPARTED", "VESSEL_HANDLING_COMPLETED", "WORK_ORDER_COMPLETED",
    "event_id", "push_event",
]
