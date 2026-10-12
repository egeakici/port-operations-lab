"""``observable_clone()``: the kernel restricted to information visible at the current time.

Integration specification §10: "A forward model is the same kernel code run on
an ObservableClone. That clone is built by removing every hidden vessel and
every hidden landside event from the queue. It is never a raw deep copy of the
full state."

What the observable clone removes:

* every vessel that is not yet announced (``visibility == HIDDEN``): its record,
  its arrival and horizon-entry events and its state;
* containers that are neither physically in the terminal nor on the manifest of
  a visible vessel (inbound cargo of hidden vessels, unreceived exports of
  hidden vessels);
* every not-yet-occurred ``GATE_IN_ARRIVAL`` and ``PICKUP_DUE`` event, and the
  corresponding scheduled times in the container records (pickup times are kept
  only for requests that already occurred);
* scenario identity, seed and fingerprints, the ledger and the kernel event log;
* the true drain limit (replaced by the last *visible* arrival + extension).

What it keeps (all observable under foundation §2 / spec §10): the current
physical state, announced vessels (exact arrival, D18), the manifests of visible
vessels, the fields of containers already in the terminal, and the kernel's own
scheduled consequences of current state (batch completions, preparation ends,
departures, rollover timers).

Kept container records may *reference* the id of an unannounced vessel (a yard
export's destination, or a visible vessel's transshipment cargo still aboard an
unannounced vessel). The id is a field of an observable container record
(foundation §2); no record, arrival, length, workload or event of that vessel
is present. Landside forecast rules for forward models remain PROPOSED (D26,
Step 6): the clone simply has no future landside requests.
"""

from __future__ import annotations

import heapq

from integrated_terminal_pilot.simulator.events import (
    E_KEY, E_TYPE, HIDDEN_LANDSIDE_EVENTS, HORIZON_ENTRY, VESSEL_ARRIVAL,
)
from integrated_terminal_pilot.simulator.state import PendingDecision


def build_observable_clone(kernel):
    from integrated_terminal_pilot.simulator.kernel import TerminalKernel

    catalog, truth = kernel.catalog, kernel.state
    if kernel._group is not None:
        raise RuntimeError("cannot build an observable clone while an event group is being processed")
    visible = {vid for vid, v in truth.vessels.items() if v.visibility != "HIDDEN"}
    keep, due = [], []
    for c in catalog.containers:
        i = c.index
        status = truth.c_status[i]
        if status == "EXPECTED_BY_VESSEL":
            kept = c.origin_vessel_id in visible or c.destination_vessel_id in visible
        elif status == "EXPECTED_BY_LANDSIDE":
            kept = c.destination_vessel_id in visible
        else:
            kept = True  # physically in the terminal, or already left it
        if kept:
            keep.append(i)
            if truth.c_pickup_due[i]:
                due.append(i)
    remap = {old: new for new, old in enumerate(keep)}
    last_visible_arrival = max((catalog.vessel_by_id[v].arrival_time_min for v in visible), default=0.0)
    restricted = catalog.redacted(
        visible_vessel_ids=visible, keep_indices=keep, due_pickup_indices=due,
        drain_limit_min=last_visible_arrival + catalog.physics.max_drain_extension_min)

    state = truth.clone(keep_logs=False)
    state.ledger = None
    state.event_log = None
    state.vessels = {vid: v for vid, v in state.vessels.items() if vid in visible}
    for name in ("c_status", "c_loc_kind", "c_loc_id", "c_claim", "c_tindex", "c_entry_time",
                 "c_release_time", "c_rolled", "c_pickup_due", "c_gate_since"):
        values = getattr(state, name)
        setattr(state, name, [values[old] for old in keep])
    for wo in state.work_orders.values():
        wo.container_indices = tuple(remap[i] for i in wo.container_indices)
    state.load_ready = {vid: {key: [remap[i] for i in members] for key, members in by_key.items()}
                        for vid, by_key in state.load_ready.items() if vid in visible}
    state.releasable = {key: [remap[i] for i in members] for key, members in state.releasable.items()}
    state.gate_queue = {key: [remap[i] for i in members] for key, members in state.gate_queue.items()}
    events = []
    for entry in state.events:
        kind = entry[E_TYPE]
        if kind in HIDDEN_LANDSIDE_EVENTS:
            continue
        if kind in (VESSEL_ARRIVAL, HORIZON_ENTRY) and entry[E_KEY] not in visible:
            continue
        if kind == HORIZON_ENTRY:
            continue  # visible vessels are already announced
        events.append(entry)
    heapq.heapify(events)
    state.events = events
    if state.pending is not None and state.pending.kind == "YARD":
        request = list(state.pending.request)
        request[4] = tuple(remap[i] for i in request[4])
        state.pending = PendingDecision(state.pending.kind, state.pending.decision_id,
                                        state.pending.time_min, tuple(request))
    return TerminalKernel(restricted, state, invariant_mode=kernel.invariant_mode,
                          full_check_interval=kernel.full_check_interval)


__all__ = ["build_observable_clone"]
