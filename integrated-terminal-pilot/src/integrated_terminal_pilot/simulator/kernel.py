"""``TerminalKernel``: the deterministic, cloneable integrated terminal kernel (D05, ADR-001).

One authoritative physical transition model. Berth occupancy, quay cranes,
transfer, yard storage and handling, landside requests and individual
containers share one clock and one event queue.

Kernel cycle at a timestamp (integration specification §8.2)::

    EVENTS    pop the earliest valid time t (>= now); settle progress and KPIs over
              [now, t]; process every valid event within 1e-9 min of t in
              (priority, stable key, sequence) order
    BERTH     only if a D07 epoch event occurred: query the berth policy until WAIT
              or no legal immediate assignment remains (re-query after each start)
    CRANE     once, if a crane is available and a berthed vessel is below max_cranes
              with remaining work
    DISPATCH  kernel-driven: landside releases, then ship-side batches by rule D16
              (vessels in berth order, cranes in id order), then gate receipts; the
              yard policy chooses the destination of every discharge / receive batch
    FINALIZE  rollover timers (D17), crane activity, rate recomputation (§5.4/§8.4),
              invariant checks; then the next cycle

Public API
----------
``advance(until_min=None)``  run until a policy decision is needed (``DecisionRequest``),
                             the episode ends (``EpisodeEnd``) or the next event lies
                             after ``until_min`` (``Paused``).
``apply_berth_action / apply_crane_action / apply_yard_action``
                             one decision application, validated atomically.
``step_event()``             process exactly one timestamp group (EVENTS phase only).
``peek_next_event()``        the next valid queue entry (kernel truth; never give the
                             truth kernel to a policy).
``berth_view() / crane_observation() / yard_observation()``  decision-time observations.
``clone()``                  truth-preserving copy (replay, regression, continuation).
``observable_clone()``       hidden future removed (forward models; spec §10).
``snapshot() / from_snapshot()``  plain-data state round trip.
``validate_invariants(full)``, ``result()``.
"""

from __future__ import annotations

import bisect
import heapq
from dataclasses import dataclass
from typing import Any

from berth_allocation_lab.core import candidate_positions
from berth_allocation_lab.data import BAPVesselInput

from integrated_terminal_pilot.simulator import invariants as inv
from integrated_terminal_pilot.simulator.catalog import ScenarioCatalog
from integrated_terminal_pilot.simulator.errors import (
    DecisionProtocolError, InvalidStatusTransition, KernelError, KernelLivelockError, KernelTimeError,
    PhysicalActionRejected,
)
from integrated_terminal_pilot.simulator.events import (
    BERTH_EPOCH_EVENTS, BERTHING_PREP_COMPLETED, E_GENERATION, E_KEY, E_PAYLOAD, E_PRIORITY, E_SEQ,
    E_TIME, E_TYPE, EVENT_PRIORITY, GATE_IN_ARRIVAL, HORIZON_ENTRY,
    LOAD_WAIT_TIMEOUT, PICKUP_DUE, TIME_TOL, VESSEL_ARRIVAL, VESSEL_DEPARTED,
    VESSEL_HANDLING_COMPLETED, WORK_ORDER_COMPLETED, event_id, push_event,
)
from integrated_terminal_pilot.simulator.ledger import (
    EXCEPTION, PHYSICAL, PLAN, TRANSITIONS, location_tuple,
)
from integrated_terminal_pilot.simulator.observations import (
    build_berth_view, build_crane_observation, build_yard_observation,
)
from integrated_terminal_pilot.simulator.physics import (
    allocate_block, congestion_factor, crane_rate_moves_per_hour, forecast_release_min,
    quay_transfer_x_m, transfer_distance_m, transport_rate_moves_per_hour,
)
from integrated_terminal_pilot.simulator.state import (
    BlockState, CraneState, KernelState, PendingDecision, SHIP_SIDE, VESSEL_PHASE_TRANSITIONS,
    VesselState, WorkOrderState,
)
from integrated_terminal_pilot.simulator.validator import (
    berth_position_rejection, occupying_placements, validate_berth_action, validate_crane_action,
    validate_yard_action,
)

KERNEL_VERSION = "itp_kernel_v1"
INVARIANT_MODES = ("full", "cheap", "off")
_RATE_REL_TOL = 1e-12
_PROGRESS_TOL = 1e-6  # moves; settled progress must match move_count at completion

# Pending YARD request tuple layout.
(_Y_OP, _Y_SOURCE_KIND, _Y_SOURCE_ID, _Y_GROUP, _Y_INDICES, _Y_CRANE, _Y_VESSEL, _Y_KEY, _Y_WO) = range(9)


@dataclass(frozen=True)
class DecisionRequest:
    kind: str           # BERTH | CRANE | YARD
    decision_id: str
    time_min: float


@dataclass(frozen=True)
class EpisodeEnd:
    status: str
    reason: str | None
    time_min: float


@dataclass(frozen=True)
class Paused:
    time_min: float
    next_event_time_min: float


@dataclass(frozen=True)
class YardRequestInfo:
    operation_type: str
    source_kind: str
    source_location_id: str
    group_id: str
    container_indices: tuple[int, ...]
    crane_id: str | None
    vessel_id: str | None
    request_key: str
    work_order_id: str


@dataclass(frozen=True)
class KernelEventView:
    time_min: float
    priority: int
    event_type: str
    key: str
    event_id: str


class TerminalKernel:
    """The single authoritative physical transition model (see module docstring)."""

    def __init__(self, catalog: ScenarioCatalog, state: KernelState, *, invariant_mode: str = "cheap",
                 full_check_interval: int = 0) -> None:
        if invariant_mode not in INVARIANT_MODES:
            raise ValueError(f"invariant_mode must be one of {INVARIANT_MODES}")
        self.catalog = catalog
        self.state = state
        self.invariant_mode = invariant_mode
        self.full_check_interval = int(full_check_interval)
        self._service = catalog.physics.service_config()
        self._group: list | None = None
        self._group_time: float | None = None

    # ================================================================== construction
    @classmethod
    def from_scenario(cls, doc: dict[str, Any], *, validate: bool = True, record_ledger: bool = True,
                      record_event_log: bool = True, invariant_mode: str = "cheap",
                      full_check_interval: int = 0) -> "TerminalKernel":
        catalog = ScenarioCatalog.from_document(doc, validate=validate)
        return cls.from_catalog(catalog, record_ledger=record_ledger, record_event_log=record_event_log,
                                invariant_mode=invariant_mode, full_check_interval=full_check_interval)

    @classmethod
    def from_catalog(cls, catalog: ScenarioCatalog, *, record_ledger: bool = True,
                     record_event_log: bool = True, invariant_mode: str = "cheap",
                     full_check_interval: int = 0) -> "TerminalKernel":
        state = _initial_state(catalog, record_ledger=record_ledger, record_event_log=record_event_log)
        kernel = cls(catalog, state, invariant_mode=invariant_mode,
                     full_check_interval=full_check_interval)
        kernel._schedule_initial_events()
        if invariant_mode != "off":
            inv.check(kernel, full=True)
        return kernel

    @classmethod
    def from_snapshot(cls, catalog: ScenarioCatalog, snapshot: dict[str, Any], *,
                      invariant_mode: str = "cheap") -> "TerminalKernel":
        return cls(catalog, KernelState.from_dict(snapshot), invariant_mode=invariant_mode)

    def _schedule_initial_events(self) -> None:
        for vessel in self.catalog.vessels:
            self._schedule(vessel.arrival_time_min, VESSEL_ARRIVAL, vessel.vessel_id, (vessel.vessel_id,))
            announce = self.catalog.announce_time(vessel)
            if announce is not None:
                self._schedule(announce, HORIZON_ENTRY, vessel.vessel_id, (vessel.vessel_id,))
        for c in self.catalog.containers:
            if c.gate_in_time_min is not None and self.state.c_status[c.index] == "EXPECTED_BY_LANDSIDE":
                self._schedule(c.gate_in_time_min, GATE_IN_ARRIVAL, c.container_id, (c.container_id,))
            if c.pickup_time_min is not None and c.cargo_flow == "import":
                self._schedule(c.pickup_time_min, PICKUP_DUE, c.container_id, (c.container_id,))

    # ================================================================== simple queries
    @property
    def current_time_min(self) -> float:
        return self.state.now_min

    @property
    def status(self) -> str:
        return self.state.status

    @property
    def pending_decision(self) -> DecisionRequest | None:
        p = self.state.pending
        return None if p is None else DecisionRequest(p.kind, p.decision_id, p.time_min)

    def crane_count_by_vessel(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for crane in self.state.cranes.values():
            if crane.assigned_vessel_id is not None:
                counts[crane.assigned_vessel_id] = counts.get(crane.assigned_vessel_id, 0) + 1
        return counts

    def remaining_moves(self, vessel_id: str) -> int:
        """Ship-side moves not yet completed and not rolled over (integer, data contract §5)."""
        v = self.state.vessels[vessel_id]
        record = self.catalog.vessel_by_id[vessel_id]
        return record.workload_moves - v.completed_moves - len(v.rolled_over_container_ids)

    def vessel_rate_moves_per_hour(self, vessel_id: str) -> float:
        return sum(wo.rate_moves_per_hour for wo in self._ship_work_orders() if wo.vessel_id == vessel_id)

    def forecast_release(self, vessel_id: str) -> float:
        """``ServiceForecaster v1`` for an occupying vessel; reads current state only (never the queue)."""
        s = self.state
        v = s.vessels[vessel_id]
        in_progress = sum(wo.completed_moves for wo in self._ship_work_orders() if wo.vessel_id == vessel_id)
        remaining = max(0.0, self.remaining_moves(vessel_id) - in_progress)
        physics = self.catalog.physics
        release = forecast_release_min(
            now_min=s.now_min, phase=v.phase, berth_start_time_min=v.berth_start_time_min,
            handling_end_time_min=v.handling_end_time_min, remaining_moves=remaining,
            current_rate_moves_per_hour=self.vessel_rate_moves_per_hour(vessel_id),
            berthing_preparation_min=physics.berthing_preparation_min,
            departure_preparation_min=physics.departure_preparation_min,
            service_minutes_per_move=physics.service_minutes_per_move)
        if not release > s.now_min:
            raise KernelError(f"forecast release {release} of {vessel_id} is not > now {s.now_min} "
                              "(G17 kernel defect)", code="FORECAST_NOT_AFTER_NOW")
        return release

    def legal_berth_choices(self) -> tuple[tuple[str, int, float, float], ...]:
        """Immediate legal (vessel, position) pairs: Project 03 candidates filtered by physical legality."""
        s, catalog = self.state, self.catalog
        if s.status != "RUNNING":
            return ()
        placements = None
        choices = []
        for vessel_id in s.reveal_order:
            if s.vessels[vessel_id].phase != "WAITING":
                continue
            if placements is None:
                placements = occupying_placements(self)
            record = catalog.vessel_by_id[vessel_id]
            vessel_input = BAPVesselInput(vessel_id, record.arrival_time_min, record.length_m,
                                          record.nominal_service_time_min, record.workload_moves)
            positions = candidate_positions(vessel_input, placements, catalog.berth_length_m,
                                            catalog.min_clearance_m)
            legal = [x for x in positions
                     if berth_position_rejection(self, vessel_id, x, placements=placements) is None]
            for index, position in enumerate(legal):
                choices.append((vessel_id, index, position, record.arrival_time_min))
        return tuple(choices)

    def berth_wait_legal(self) -> bool:
        """Project 03 WAIT rule on visible data: a legal assignment and a visible future event."""
        s = self.state
        if not self.legal_berth_choices():
            return False
        for vessel_id in s.reveal_order:
            v = s.vessels[vessel_id]
            record = self.catalog.vessel_by_id[vessel_id]
            if v.phase == "NOT_ARRIVED" and record.arrival_time_min > s.now_min:
                return True
            if v.phase in ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP") \
                    and self.forecast_release(vessel_id) > s.now_min:
                return True
        return False

    def pending_yard_request(self) -> YardRequestInfo:
        p = self.state.pending
        if p is None or p.kind != "YARD":
            raise DecisionProtocolError("no pending YARD decision")
        r = p.request
        return YardRequestInfo(r[_Y_OP], r[_Y_SOURCE_KIND], r[_Y_SOURCE_ID], r[_Y_GROUP], tuple(r[_Y_INDICES]),
                               r[_Y_CRANE], r[_Y_VESSEL], r[_Y_KEY], r[_Y_WO])

    def peek_next_event(self) -> KernelEventView | None:
        """Next valid queue entry. Kernel truth: includes hidden future events."""
        entry = self._peek_valid()
        if entry is None:
            return None
        return KernelEventView(entry[E_TIME], entry[E_PRIORITY], entry[E_TYPE], entry[E_KEY],
                               event_id(entry[E_SEQ]))

    # ================================================================== observations
    def berth_view(self):
        self._require_pending("BERTH")
        return build_berth_view(self)

    def crane_observation(self):
        self._require_pending("CRANE")
        return build_crane_observation(self, self.state.pending.decision_id)

    def yard_observation(self):
        self._require_pending("YARD")
        return build_yard_observation(self)

    def _require_pending(self, kind: str) -> None:
        p = self.state.pending
        if p is None or p.kind != kind:
            raise DecisionProtocolError(f"no pending {kind} decision "
                                        f"(pending: {None if p is None else p.kind})")

    # ================================================================== driving the kernel
    def advance(self, until_min: float | None = None, *, max_cycles: int | None = None):
        """Run until a decision is needed, the episode ends, the next event is after ``until_min``,
        or ``max_cycles`` kernel cycles (timestamp groups) have been completed in total."""
        s = self.state
        try:
            while True:
                if s.pending is not None:
                    return DecisionRequest(s.pending.kind, s.pending.decision_id, s.pending.time_min)
                if s.status != "RUNNING":
                    return EpisodeEnd(s.status, s.status_reason, s.now_min)
                if s.phase == "EVENTS":
                    if max_cycles is not None and s.cycles >= max_cycles:
                        head = self._peek_valid()
                        return Paused(s.now_min, head[E_TIME] if head is not None else s.now_min)
                    if until_min is not None:
                        head = self._peek_valid()
                        if head is not None and head[E_TIME] > until_min + TIME_TOL \
                                and head[E_TIME] <= self.catalog.drain_limit_min + TIME_TOL:
                            return Paused(s.now_min, head[E_TIME])
                    self._events_phase()
                elif s.phase == "BERTH":
                    if s.berth_epoch and self.legal_berth_choices():
                        self._open_decision("BERTH")
                    else:
                        s.phase = "CRANE"
                elif s.phase == "CRANE":
                    if self._crane_decision_needed():
                        self._open_decision("CRANE")
                    else:
                        s.phase = "DISPATCH"
                elif s.phase == "DISPATCH":
                    if not self._dispatch():
                        s.phase = "FINALIZE"
                elif s.phase == "FINALIZE":
                    self._finalize_cycle()
                    s.phase = "EVENTS"
                else:  # pragma: no cover - defensive
                    raise KernelError(f"unknown kernel phase {s.phase}")
        except (PhysicalActionRejected, DecisionProtocolError):
            raise
        except KernelError as error:
            self._fail(error)
            raise

    def step_event(self) -> tuple[tuple[str, str], ...]:
        """Process exactly one timestamp group; the decision phase of that timestamp stays pending."""
        s = self.state
        if s.pending is not None or s.phase != "EVENTS":
            raise DecisionProtocolError("step_event() needs a completed decision phase (phase EVENTS, "
                                        f"no pending decision); phase is {s.phase}")
        if s.status != "RUNNING":
            return ()
        try:
            return self._events_phase()
        except KernelError as error:
            self._fail(error)
            raise

    def apply_berth_action(self, action) -> None:
        validate_berth_action(self, action)
        self._guarded(self._commit_berth_action, action)

    def apply_crane_action(self, action) -> None:
        validate_crane_action(self, action)
        self._guarded(self._commit_crane_action, action)

    def apply_yard_action(self, action) -> None:
        validate_yard_action(self, action)
        self._guarded(self._commit_yard_action, action)

    def _guarded(self, function, *args) -> None:
        try:
            function(*args)
        except KernelError as error:
            self._fail(error)
            raise

    def _fail(self, error: KernelError) -> None:
        s = self.state
        if s.status == "RUNNING":
            s.status = "FAILED"
            s.status_reason = error.code
            s.status_details = {"message": str(error), "time_min": s.now_min, "phase": s.phase}
            s.pending = None

    # ================================================================== cloning
    def clone(self) -> "TerminalKernel":
        """Truth-preserving copy for replay, regression and continuation; NOT a legal oracle for a policy."""
        if self._group is not None:
            raise DecisionProtocolError("cannot clone while an event group is being processed")
        return TerminalKernel(self.catalog, self.state.clone(), invariant_mode=self.invariant_mode,
                              full_check_interval=self.full_check_interval)

    def observable_clone(self) -> "TerminalKernel":
        from integrated_terminal_pilot.simulator.observable import build_observable_clone

        return build_observable_clone(self)

    def snapshot(self) -> dict[str, Any]:
        return self.state.to_dict()

    def validate_invariants(self, *, full: bool = True) -> None:
        inv.check(self, full=full)

    def result(self, **kwargs) -> dict[str, Any]:
        from integrated_terminal_pilot.simulator.metrics import build_result

        return build_result(self, **kwargs)

    # ================================================================== event queue helpers
    def _schedule(self, time_min: float, event_type: str, key: str, payload: tuple = (),
                  generation: int = 0) -> None:
        s = self.state
        sequence = s.next_event_seq
        s.next_event_seq += 1
        if self._group is not None and time_min <= self._group_time + TIME_TOL:
            if time_min < s.now_min - TIME_TOL:
                raise KernelTimeError(f"{event_type} {key}: event time {time_min} precedes clock {s.now_min}")
            entry = (float(time_min), EVENT_PRIORITY[event_type], key, sequence, event_type, payload,
                     generation)
            bisect.insort(self._group, entry, key=_group_order)
            return
        push_event(s.events, s.now_min, sequence, time_min, event_type, key, payload, generation)

    def _is_valid(self, entry: tuple) -> bool:
        s = self.state
        kind = entry[E_TYPE]
        if kind == WORK_ORDER_COMPLETED:
            wo = s.work_orders.get(entry[E_PAYLOAD][0])
            return wo is not None and wo.rate_generation == entry[E_GENERATION]
        if kind == LOAD_WAIT_TIMEOUT:
            v = s.vessels.get(entry[E_PAYLOAD][0])
            return v is not None and v.load_wait_generation == entry[E_GENERATION] \
                and v.load_wait_deadline_min is not None
        return True

    def _peek_valid(self) -> tuple | None:
        queue = self.state.events
        while queue and not self._is_valid(queue[0]):
            heapq.heappop(queue)
            self.state.stale_events_discarded += 1
        return queue[0] if queue else None

    # ================================================================== EVENTS phase
    def _events_phase(self) -> tuple[tuple[str, str], ...]:
        s, catalog = self.state, self.catalog
        head = self._peek_valid()
        if head is None:
            self._terminate_without_events()
            return ()
        t = head[E_TIME]
        if t > catalog.drain_limit_min + TIME_TOL:
            self._settle(max(s.now_min, catalog.drain_limit_min))
            self._end("TRUNCATED_DRAIN_LIMIT", "next event after drain limit",
                      self._unresolved_details(next_event=(t, head[E_TYPE], head[E_KEY])))
            return ()
        if t < s.now_min - TIME_TOL:
            raise KernelTimeError(f"event {head[E_TYPE]} {head[E_KEY]} at {t} precedes clock {s.now_min}")
        if s.cycles > 0 and t <= s.now_min + TIME_TOL:
            s.same_time_cycles += 1
            if s.same_time_cycles > catalog.physics.same_timestamp_cycle_limit:
                raise KernelLivelockError(f"more than {catalog.physics.same_timestamp_cycle_limit} cycles "
                                          f"at t = {s.now_min}")
        else:
            s.same_time_cycles = 0
        self._settle(t)
        group = []
        while s.events and s.events[0][E_TIME] <= t + TIME_TOL:
            group.append(heapq.heappop(s.events))
        group.sort(key=_group_order)
        self._group, self._group_time = group, t
        processed = []
        berth_epoch = False
        try:
            while self._group:
                entry = self._group.pop(0)
                if not self._is_valid(entry):
                    s.stale_events_discarded += 1
                    continue
                self._process(entry)
                processed.append((entry[E_TYPE], entry[E_KEY]))
                if entry[E_TYPE] in BERTH_EPOCH_EVENTS:
                    berth_epoch = True
        finally:
            self._group, self._group_time = None, None
        s.berth_epoch = berth_epoch
        s.phase = "BERTH"
        return tuple(processed)

    def _process(self, entry: tuple) -> None:
        s = self.state
        if s.event_log is not None:
            s.event_log.append((entry[E_SEQ], s.now_min, entry[E_PRIORITY], entry[E_TYPE], entry[E_KEY],
                                entry[E_GENERATION]))
        cause = event_id(entry[E_SEQ])
        kind = entry[E_TYPE]
        payload = entry[E_PAYLOAD]
        if kind == WORK_ORDER_COMPLETED:
            self._on_work_order_completed(payload[0], cause)
        elif kind == VESSEL_HANDLING_COMPLETED:
            self._on_handling_completed(payload[0], cause)
        elif kind == VESSEL_DEPARTED:
            self._on_departed(payload[0], cause)
        elif kind == BERTHING_PREP_COMPLETED:
            self._on_berthing_prep_completed(payload[0])
        elif kind == LOAD_WAIT_TIMEOUT:
            self._on_load_wait_timeout(payload[0], cause)
        elif kind == GATE_IN_ARRIVAL:
            self._on_gate_in_arrival(payload[0], cause)
        elif kind == PICKUP_DUE:
            self._on_pickup_due(payload[0])
        elif kind == VESSEL_ARRIVAL:
            self._on_vessel_arrival(payload[0], cause)
        elif kind == HORIZON_ENTRY:
            self._on_horizon_entry(payload[0])
        else:  # pragma: no cover - defensive
            raise KernelError(f"unknown event type {kind}")

    # ------------------------------------------------------------------ settle
    def _settle(self, t: float) -> None:
        """Settle fluid progress and KPI integrals over [now, t] (rates are piecewise constant)."""
        s, catalog = self.state, self.catalog
        dt = t - s.now_min
        if dt > 0.0:
            kpi = s.kpi
            busy_blocks = set()
            for crane in s.cranes.values():
                if crane.current_work_order_id is not None:
                    wo = s.work_orders[crane.current_work_order_id]
                    delta = wo.rate_moves_per_hour * dt / 60.0
                    wo.completed_moves += delta
                    s.blocks[wo.block_id].handled_moves += delta
                    busy_blocks.add(wo.block_id)
            for block_id, block in s.blocks.items():
                if block.land_heap:
                    block.land_v += block.land_rate * dt / 60.0
                    block.handled_moves += block.land_rate * len(block.land_heap) * dt / 60.0
                    busy_blocks.add(block_id)
            counts = self.crane_count_by_vessel()
            for crane in s.cranes.values():
                vessel_acc = s.vessels[crane.assigned_vessel_id].acc if crane.assigned_vessel_id else None
                if crane.assigned_vessel_id is None:
                    crane.idle_min += dt
                elif crane.activity == "PRODUCTIVE":
                    crane.productive_min += dt
                    wo = s.work_orders[crane.current_work_order_id]
                    nominal = catalog.crane_by_id[crane.crane_id].nominal_moves_per_hour
                    crane.rate_shortfall_moves += (wo.crane_rate_moves_per_hour - wo.rate_moves_per_hour) * dt / 60.0
                    crane.transport_shortfall_moves += (wo.crane_rate_moves_per_hour - wo.demand_moves_per_hour) * dt / 60.0
                    crane.yard_shortfall_moves += (wo.demand_moves_per_hour - wo.rate_moves_per_hour) * dt / 60.0
                    _add(vessel_acc, "crane_min_productive", dt)
                    _add(vessel_acc, "efficiency_loss_moves", (nominal - wo.crane_rate_moves_per_hour) * dt / 60.0)
                    _add(vessel_acc, "transport_shortfall_moves",
                         (wo.crane_rate_moves_per_hour - wo.demand_moves_per_hour) * dt / 60.0)
                    _add(vessel_acc, "yard_shortfall_moves",
                         (wo.demand_moves_per_hour - wo.rate_moves_per_hour) * dt / 60.0)
                else:
                    reason = crane.blocked_reason or "UNSPECIFIED"
                    crane.blocked_min_by_reason[reason] = crane.blocked_min_by_reason.get(reason, 0.0) + dt
                    _add(vessel_acc, f"crane_min_blocked_{reason}", dt)
            waiting = 0
            for vessel_id, v in s.vessels.items():
                if v.phase in ("NOT_ARRIVED", "DEPARTED"):
                    continue
                _add(v.acc, f"phase_min_{v.phase}", dt)
                if v.phase == "WAITING":
                    waiting += 1
                elif v.phase == "HANDLING":
                    if counts.get(vessel_id, 0) == 0:
                        _add(v.acc, "handling_no_crane_min", dt)
                    cause, equivalent = self._handling_cause(vessel_id)
                    _add(v.acc, f"handling_cause_min_{cause}", dt)
                    _add(v.acc, "handling_capacity_equivalent_min", dt * equivalent)
            kpi["waiting_vessel_min"] = kpi.get("waiting_vessel_min", 0.0) + waiting * dt
            at_gate = sum(len(q) for q in s.gate_queue.values())
            kpi["gate_waiting_container_min"] = kpi.get("gate_waiting_container_min", 0.0) + at_gate * dt
            for block_id, block in s.blocks.items():
                block.teu_minutes += block.occupied_teu * dt
                if block_id in busy_blocks:
                    block.busy_min += dt
        if t > s.now_min:
            s.now_min = t

    # Exclusive bookkeeping categories for HANDLING minutes (closure diagnostics). Precedence is a
    # documented accounting convention, not identification of a unique causal bottleneck.
    HANDLING_CAUSES = ("CRANE_SHORTAGE", "YARD_STORAGE_FULL", "CARGO_UNAVAILABLE", "SEQUENCING_ASSIGNED_IDLE",
                       "YARD_HANDLING_CONSTRAINED", "TRANSPORT_CONSTRAINED", "MULTIPLE_CONSTRAINTS",
                       "AT_CRANE_RATE", "UNATTRIBUTED")

    def _handling_cause(self, vessel_id: str) -> tuple[str, float]:
        """Category of the current HANDLING interval of a vessel, from runtime state only.

        1. no crane assigned -> CRANE_SHORTAGE;
        2. cranes assigned, none working -> the cranes' runtime blocked reason
           (YARD_CAPACITY -> YARD_STORAGE_FULL, CARGO_UNAVAILABLE, NO_REMAINING_WORK ->
           SEQUENCING_ASSIGNED_IDLE; several reasons or none -> UNATTRIBUTED);
        3. at least one crane working -> the rate caps actually binding on the working batches
           (yard share below demand -> YARD_HANDLING_CONSTRAINED; transport below crane rate ->
           TRANSPORT_CONSTRAINED; both -> MULTIPLE_CONSTRAINTS; neither -> AT_CRANE_RATE).

        Also returns the vessel's modelled processing rate relative to its reference rate
        ``r_ref = max_cranes x nominal x eff(max_cranes)`` (capped at 1): integrating it gives
        productive-capacity-equivalent minutes. A model-equivalent quantity, not causal proof.
        """
        s, catalog = self.state, self.catalog
        cranes = [c for c in s.cranes.values() if c.assigned_vessel_id == vessel_id]
        record = catalog.vessel_by_id[vessel_id]
        nominal = catalog.cranes[0].nominal_moves_per_hour if catalog.cranes else 0.0
        r_ref = record.max_cranes * nominal * self._service.crane_efficiency(record.max_cranes)
        working = [s.work_orders[c.current_work_order_id] for c in cranes if c.current_work_order_id]
        rate = sum(wo.rate_moves_per_hour for wo in working)
        equivalent = min(1.0, rate / r_ref) if r_ref > 0 else 0.0
        if not cranes:
            return "CRANE_SHORTAGE", equivalent
        if not working:
            reasons = {c.blocked_reason for c in cranes}
            mapping = {"YARD_CAPACITY": "YARD_STORAGE_FULL", "CARGO_UNAVAILABLE": "CARGO_UNAVAILABLE",
                       "NO_REMAINING_WORK": "SEQUENCING_ASSIGNED_IDLE"}
            if len(reasons) == 1 and next(iter(reasons)) in mapping:
                return mapping[next(iter(reasons))], equivalent
            return "UNATTRIBUTED", equivalent
        tol = 1e-9
        yard = any(wo.rate_moves_per_hour < wo.demand_moves_per_hour - tol for wo in working)
        transport = any(wo.demand_moves_per_hour < wo.crane_rate_moves_per_hour - tol for wo in working)
        if yard and transport:
            return "MULTIPLE_CONSTRAINTS", equivalent
        if yard:
            return "YARD_HANDLING_CONSTRAINED", equivalent
        if transport:
            return "TRANSPORT_CONSTRAINED", equivalent
        return "AT_CRANE_RATE", equivalent

    # ------------------------------------------------------------------ container transitions
    def _move(self, i: int, event_type: str, to_location: tuple[str, str | None], *, cause: str,
              work_order_id: str | None = None, resource: str | None = None, vessel_id: str | None = None,
              crane_moves: int = 0) -> None:
        s = self.state
        expected_from, expected_to, source_kind, dest_kind = TRANSITIONS[event_type]
        if s.c_status[i] != expected_from or s.c_loc_kind[i] != source_kind or to_location[0] != dest_kind:
            raise InvalidStatusTransition(
                f"{self.catalog.containers[i].container_id}: {event_type} requires {expected_from} at "
                f"{source_kind}, container is {s.c_status[i]} at {s.c_loc_kind[i]}/{s.c_loc_id[i]}")
        source = location_tuple(s.c_loc_kind[i], s.c_loc_id[i])
        s.c_status[i] = expected_to
        s.c_loc_kind[i], s.c_loc_id[i] = to_location
        s.c_tindex[i] += 1
        self._ledger(event_type, PHYSICAL, i, expected_from, expected_to, source,
                     location_tuple(*to_location), crane_moves, resource, vessel_id, work_order_id, cause,
                     s.c_tindex[i])

    def _ledger(self, event_type: str, event_class: str, i: int, from_status, to_status, source, dest,
                crane_moves: int, resource, vessel_id, work_order_id, cause, tindex) -> None:
        s = self.state
        sequence = s.next_ledger_seq
        s.next_ledger_seq += 1
        if s.ledger is None:
            return
        c = self.catalog.containers[i]
        s.ledger.append((sequence, s.now_min, event_type, event_class, c.container_id, c.group_id,
                         from_status, to_status, source, dest, c.size_teu, crane_moves, resource,
                         vessel_id, work_order_id, cause, tindex))

    def _plan_record(self, event_type: str, i: int, work_order_id: str, block_id: str, cause: str,
                     vessel_id: str | None) -> None:
        s = self.state
        here = location_tuple(s.c_loc_kind[i], s.c_loc_id[i])
        self._ledger(event_type, PLAN, i, None, None, here, here, 0, block_id, vessel_id, work_order_id,
                     cause, None)

    def _vessel_phase(self, v: VesselState, new_phase: str) -> None:
        if new_phase not in VESSEL_PHASE_TRANSITIONS[v.phase]:
            raise InvalidStatusTransition(f"vessel {v.vessel_id}: {v.phase} -> {new_phase} is not allowed")
        v.phase = new_phase

    def _reveal(self, v: VesselState, visibility: str) -> None:
        if v.slot_index is None:
            v.slot_index = len(self.state.reveal_order)
            self.state.reveal_order.append(v.vessel_id)
        v.visibility = visibility

    # ------------------------------------------------------------------ event handlers
    def _on_vessel_arrival(self, vessel_id: str, cause: str) -> None:
        v = self.state.vessels[vessel_id]
        if v.visibility == "ARRIVED":
            raise InvalidStatusTransition(f"duplicate arrival of {vessel_id}")
        self._vessel_phase(v, "WAITING")
        self._reveal(v, "ARRIVED")
        for _group, members in self.catalog.vessel_by_id[vessel_id].discharge_groups:
            for i in members:
                self._move(i, "VESSEL_ARRIVED_WITH_CARGO", ("VESSEL", vessel_id), cause=cause,
                           vessel_id=vessel_id)

    def _on_horizon_entry(self, vessel_id: str) -> None:
        v = self.state.vessels[vessel_id]
        if v.visibility == "HIDDEN":
            self._reveal(v, "ANNOUNCED")

    def _on_berthing_prep_completed(self, vessel_id: str) -> None:
        v = self.state.vessels[vessel_id]
        self._vessel_phase(v, "HANDLING")
        v.handling_start_time_min = self.state.now_min
        self._maybe_complete_handling(vessel_id)

    def _on_gate_in_arrival(self, container_id: str, cause: str) -> None:
        s = self.state
        i = self.catalog.container_index[container_id]
        self._move(i, "GATE_ARRIVED", ("GATE", self.catalog.gate_id), cause=cause,
                   vessel_id=self.catalog.containers[i].destination_vessel_id)
        s.c_entry_time[i] = s.now_min
        s.c_gate_since[i] = s.now_min
        s.gate_queue.setdefault(self.catalog.containers[i].group_id, []).append(i)

    def _on_pickup_due(self, container_id: str) -> None:
        s = self.state
        i = self.catalog.container_index[container_id]
        if s.c_pickup_due[i]:
            raise InvalidStatusTransition(f"duplicate pickup request for {container_id}")
        s.c_pickup_due[i] = True
        if s.c_status[i] == "IN_YARD" and s.c_claim[i] is None:
            self._add_releasable(i)

    def _add_releasable(self, i: int) -> None:
        """Due import physically in the yard: queue it (FIFO) for its block's release stream."""
        self.state.releasable.setdefault(self.state.c_loc_id[i], []).append(i)

    def _add_load_ready(self, i: int) -> None:
        s = self.state
        c = self.catalog.containers[i]
        if c.destination_vessel_id not in s.vessels or s.c_rolled[i]:
            return
        key = f"{c.group_id}|{s.c_loc_id[i]}"
        bisect.insort(s.load_ready.setdefault(c.destination_vessel_id, {}).setdefault(key, []), i)

    def _on_work_order_completed(self, work_order_id: str, cause: str) -> None:
        s = self.state
        wo = s.work_orders[work_order_id]
        if wo.status != "IN_PROGRESS":
            raise InvalidStatusTransition(f"completion for {work_order_id} in status {wo.status}")
        progress = self.work_order_progress(wo)
        if abs(progress - wo.move_count) > _PROGRESS_TOL:
            raise KernelError(f"{work_order_id}: settled progress {progress} != {wo.move_count} "
                              "moves at its completion event", code="PROGRESS_MISMATCH")
        wo.completed_moves = float(wo.move_count)
        block = s.blocks[wo.block_id]
        op = wo.operation_type
        if op not in SHIP_SIDE:
            if not block.land_heap or block.land_heap[0][1] != work_order_id:
                raise KernelError(f"{work_order_id} completes out of landside order at {wo.block_id}",
                                  code="PROGRESS_MISMATCH")
            if block.land_scheduled_wo != work_order_id:
                raise KernelError(f"{work_order_id} completes without holding {wo.block_id}'s landside event",
                                  code="PROGRESS_MISMATCH")
            heapq.heappop(block.land_heap)
            block.land_scheduled_wo = None
            if block.land_heap and block.land_heap[0][0] <= block.land_v + 1e-9:
                # The next landside batch finishes at this same instant (equal per-flow rates).
                nxt = s.work_orders[block.land_heap[0][1]]
                nxt.rate_generation += 1
                self._schedule(s.now_min, WORK_ORDER_COMPLETED, nxt.work_order_id, (nxt.work_order_id,),
                               nxt.rate_generation)
                nxt.scheduled_generation = nxt.rate_generation
                block.land_scheduled_wo = nxt.work_order_id
        for i in wo.container_indices:
            c = self.catalog.containers[i]
            if op in ("DISCHARGE", "GATE_IN"):
                self._plan_record("YARD_RESERVATION_RELEASED", i, work_order_id, wo.block_id, cause, wo.vessel_id)
                self._move(i, "DISCHARGE_COMPLETED" if op == "DISCHARGE" else "RECEIVE_COMPLETED",
                           ("YARD_BLOCK", wo.block_id), cause=cause, work_order_id=work_order_id,
                           resource=wo.crane_id if op == "DISCHARGE" else wo.block_id,
                           vessel_id=wo.vessel_id if op == "DISCHARGE" else c.destination_vessel_id,
                           crane_moves=1 if op == "DISCHARGE" else 0)
                block.occupied_teu += c.size_teu
                block.occupied_count += 1
                s.c_claim[i] = None
                if c.cargo_flow == "import":
                    if s.c_pickup_due[i]:
                        self._add_releasable(i)
                else:
                    self._add_load_ready(i)
            elif op == "LOAD":
                self._move(i, "LOAD_COMPLETED", ("VESSEL", wo.vessel_id), cause=cause,
                           work_order_id=work_order_id, resource=wo.crane_id, vessel_id=wo.vessel_id,
                           crane_moves=1)
                s.c_claim[i] = None
            else:  # GATE_OUT
                self._move(i, "RELEASE_COMPLETED", ("EXTERNAL_LANDSIDE", None), cause=cause,
                           work_order_id=work_order_id, resource=wo.block_id)
                s.c_release_time[i] = s.now_min
                s.c_claim[i] = None
        if op == "GATE_OUT":
            if block.active_release_wo != work_order_id:
                raise KernelError(f"{work_order_id} is not {wo.block_id}'s active release batch",
                                  code="INVALID_STATUS_TRANSITION")
            block.active_release_wo = None
        if op in ("DISCHARGE", "GATE_IN"):
            reserved = block.reservations.pop(work_order_id, None)
            if reserved is None or abs(reserved - wo.planned_teu) > 1e-9:
                raise KernelError(f"{work_order_id}: reservation {reserved} != planned {wo.planned_teu}",
                                  code="RESERVATION_MISMATCH")
            total = sum(b.occupied_teu for b in s.blocks.values())
            s.kpi["peak_yard_teu"] = max(s.kpi.get("peak_yard_teu", 0.0), total)
            block.peak_occupied_teu = max(block.peak_occupied_teu, block.occupied_teu)
        if op in SHIP_SIDE:
            crane = s.cranes[wo.crane_id]
            crane.moves_completed += wo.move_count
            crane.current_work_order_id = None
            v = s.vessels[wo.vessel_id]
            if op == "DISCHARGE":
                v.discharge_completed += wo.move_count
            else:
                v.loads_completed += wo.move_count
        wo.status = "COMPLETED"
        wo.completion_time_min = s.now_min
        del s.work_orders[work_order_id]
        s.completed_work_orders.append((
            wo.work_order_id, wo.operation_type, wo.container_group_id,
            tuple(self.catalog.containers[i].container_id for i in wo.container_indices), wo.move_count,
            wo.planned_teu, wo.vessel_id, wo.crane_id, wo.block_id, wo.created_time_min, wo.start_time_min,
            wo.completion_time_min))
        if op in SHIP_SIDE:
            self._maybe_complete_handling(wo.vessel_id)

    def _maybe_complete_handling(self, vessel_id: str) -> None:
        s = self.state
        v = s.vessels[vessel_id]
        record = self.catalog.vessel_by_id[vessel_id]
        if v.phase != "HANDLING" or v.handling_completion_scheduled:
            return
        rolled = len(v.rolled_over_container_ids)
        if (v.discharge_completed == record.discharge_move_count
                and v.loads_completed + rolled == record.load_move_count
                and v.discharge_started == v.discharge_completed and v.loads_started == v.loads_completed):
            v.handling_completion_scheduled = True
            self._schedule(s.now_min, VESSEL_HANDLING_COMPLETED, vessel_id, (vessel_id,))

    def _on_handling_completed(self, vessel_id: str, cause: str) -> None:
        s = self.state
        v = s.vessels[vessel_id]
        record = self.catalog.vessel_by_id[vessel_id]
        for _group, members in record.discharge_groups:
            for i in members:
                if s.c_status[i] in ("EXPECTED_BY_VESSEL", "ABOARD_ARRIVED_VESSEL", "DISCHARGING"):
                    raise InvalidStatusTransition(f"{vessel_id} cannot enter DEPARTURE_PREP: "
                                                  f"{self.catalog.containers[i].container_id} still aboard "
                                                  "(orphaned cargo)")
        for i in record.load_container_indices:
            if s.c_status[i] != "LOADED" and not s.c_rolled[i]:
                raise InvalidStatusTransition(f"{vessel_id}: load {self.catalog.containers[i].container_id} "
                                              f"is {s.c_status[i]} and not rolled over")
        self._vessel_phase(v, "DEPARTURE_PREP")
        v.handling_end_time_min = s.now_min
        if v.load_wait_deadline_min is not None:
            v.load_wait_deadline_min = None
            v.load_wait_generation += 1
        for crane in s.cranes.values():
            if crane.assigned_vessel_id == vessel_id:
                if crane.current_work_order_id is not None:
                    raise KernelError(f"{crane.crane_id} still in batch at handling completion",
                                      code="INVALID_STATUS_TRANSITION")
                self._release_crane(crane)
        self._schedule(s.now_min + self.catalog.physics.departure_preparation_min, VESSEL_DEPARTED,
                       vessel_id, (vessel_id,))

    def _release_crane(self, crane: CraneState) -> None:
        self._close_block_episode(crane)
        crane.status = "available"
        crane.assigned_vessel_id = None
        crane.activity = "IDLE"
        crane.blocked_reason = None
        crane.rate_moves_per_hour = 0.0

    def _on_departed(self, vessel_id: str, cause: str) -> None:
        s = self.state
        v = s.vessels[vessel_id]
        if v.handling_end_time_min is None:
            raise InvalidStatusTransition(f"{vessel_id} departs before handling completion (INV13)")
        self._vessel_phase(v, "DEPARTED")
        v.departure_time_min = s.now_min
        for i in self.catalog.vessel_by_id[vessel_id].load_container_indices:
            if s.c_status[i] == "LOADED":
                self._move(i, "DEPARTED_WITH_VESSEL", ("VESSEL", vessel_id), cause=cause, vessel_id=vessel_id)
                s.c_release_time[i] = s.now_min
        s.load_ready.pop(vessel_id, None)

    def _on_load_wait_timeout(self, vessel_id: str, cause: str) -> None:
        s = self.state
        v = s.vessels[vessel_id]
        if v.phase != "HANDLING":
            raise InvalidStatusTransition(f"LOAD_WAIT_TIMEOUT for {vessel_id} in phase {v.phase}")
        v.load_wait_deadline_min = None
        v.load_wait_generation += 1
        if not self._load_wait_condition(vessel_id):
            # Cargo became available earlier in this timestamp group (e.g. a receipt completed
            # at the deadline): work is startable again, so the timer is cancelled (D17).
            return
        rolled = []
        for i in self.catalog.vessel_by_id[vessel_id].load_container_indices:
            if s.c_rolled[i] or s.c_status[i] in ("LOADING", "LOADED"):
                continue
            if s.c_status[i] == "IN_YARD":
                raise KernelError(f"rollover of {self.catalog.containers[i].container_id}, which is "
                                  "available in the yard", code="INVALID_STATUS_TRANSITION")
            s.c_rolled[i] = True
            here = location_tuple(s.c_loc_kind[i], s.c_loc_id[i])
            self._ledger("ROLLED_OVER", EXCEPTION, i, s.c_status[i], s.c_status[i], here, here, 0, None,
                         vessel_id, None, cause, None)
            rolled.append(self.catalog.containers[i].container_id)
        v.rolled_over_container_ids = tuple(sorted(v.rolled_over_container_ids + tuple(rolled)))
        self._maybe_complete_handling(vessel_id)

    # ================================================================== decisions
    def _open_decision(self, kind: str, request: tuple = ()) -> None:
        s = self.state
        decision_id = f"DEC-{s.next_decision_seq:08d}"
        s.next_decision_seq += 1
        s.pending = PendingDecision(kind, decision_id, s.now_min, request)

    def _log_decision(self, decision_id: str, kind: str, summary: tuple) -> None:
        self.state.decision_log.append((decision_id, self.state.now_min, kind, summary))

    def _commit_berth_action(self, action) -> None:
        s = self.state
        decision_id = s.pending.decision_id
        s.pending = None
        if action.action_type == "WAIT":
            self._log_decision(decision_id, "BERTH", ("WAIT", action.policy_id))
            s.phase = "CRANE"
            return
        v = s.vessels[action.vessel_id]
        self._vessel_phase(v, "BERTHING_PREP")
        v.berth_position_m = float(action.berth_position_m)
        v.berth_start_time_min = s.now_min
        self._schedule(s.now_min + self.catalog.physics.berthing_preparation_min, BERTHING_PREP_COMPLETED,
                       action.vessel_id, (action.vessel_id,))
        self._log_decision(decision_id, "BERTH", ("ASSIGN", action.policy_id, action.vessel_id,
                                                  v.berth_position_m))
        s.phase = "BERTH"  # same-timestamp re-query (D07)

    def _crane_decision_needed(self) -> bool:
        s = self.state
        if not any(c.status == "available" for c in s.cranes.values()):
            return False
        counts = self.crane_count_by_vessel()
        for vessel_id in s.reveal_order:
            v = s.vessels[vessel_id]
            if v.phase in ("BERTHING_PREP", "HANDLING") and self.remaining_moves(vessel_id) > 0 \
                    and counts.get(vessel_id, 0) < self.catalog.vessel_by_id[vessel_id].max_cranes:
                return True
        return False

    def _commit_crane_action(self, action) -> None:
        s = self.state
        decision_id = s.pending.decision_id
        s.pending = None
        for crane_id in action.releases:
            self._release_crane(s.cranes[crane_id])
        for assignment in action.assignments:
            for crane_id in assignment.crane_ids:
                crane = s.cranes[crane_id]
                crane.status = "assigned"
                crane.assigned_vessel_id = assignment.vessel_id
                crane.activity = "BLOCKED"
                crane.blocked_reason = None  # set at FINALIZE
        self._log_decision(decision_id, "CRANE", (action.action_type, action.policy_id,
                                                  tuple((a.vessel_id, a.crane_ids) for a in action.assignments),
                                                  tuple(action.releases), action.no_action_reason))
        s.phase = "DISPATCH"

    def _commit_yard_action(self, action) -> None:
        s = self.state
        request = self.pending_yard_request()
        decision_id = s.pending.decision_id
        s.pending = None
        if action.action_type == "NO_ACTION":
            s.yard_blocked[request.request_key] = s.capacity_version
            self._log_decision(decision_id, "YARD", ("NO_ACTION", action.policy_id, request.work_order_id,
                                                     request.operation_type, action.no_action_reason))
            return  # stay in DISPATCH
        s.yard_blocked.pop(request.request_key, None)
        self._log_decision(decision_id, "YARD", ("ALLOCATE_BLOCK", action.policy_id, request.work_order_id,
                                                 request.operation_type, action.block_id))
        if request.operation_type == "DISCHARGE":
            v = s.vessels[request.vessel_id]
            v.discharge_cursor[request.group_id] = v.discharge_cursor.get(request.group_id, 0) + \
                len(request.container_indices)
            v.discharge_started += len(request.container_indices)
        else:
            queue = s.gate_queue[request.group_id]
            for i in request.container_indices:
                queue.remove(i)
            if not queue:
                del s.gate_queue[request.group_id]
        self._start_work_order(request.operation_type, request.group_id, request.container_indices,
                               vessel_id=request.vessel_id, crane_id=request.crane_id,
                               block_id=action.block_id, cause=decision_id,
                               expected_id=request.work_order_id)

    # ================================================================== DISPATCH phase
    def _next_work_order_id(self) -> str:
        return f"WO-{self.state.next_work_order_seq:06d}"

    def _dispatch(self) -> bool:
        """Kernel-driven dispatch; returns True when a YARD decision was opened."""
        s, catalog = self.state, self.catalog
        batch = catalog.physics.batch_size_containers
        while True:
            started = self._start_releases()
            for vessel_id in self._vessels_in_berth_order("HANDLING"):
                idle = sorted(c.crane_id for c in s.cranes.values()
                              if c.assigned_vessel_id == vessel_id and c.current_work_order_id is None)
                for crane_id in idle:
                    outcome = self._dispatch_crane(vessel_id, crane_id, batch)
                    if outcome == "DECISION":
                        return True
                    started = started or outcome == "STARTED"
            for group_id in sorted(s.gate_queue):
                key = f"G|{group_id}"
                if s.yard_blocked.get(key) == s.capacity_version:
                    continue
                indices = tuple(s.gate_queue[group_id][:batch])
                self._open_decision("YARD", ("GATE_IN", "GATE", catalog.gate_id, group_id, indices, None,
                                             None, key, self._next_work_order_id()))
                return True
            if not started:
                return False

    def _vessels_in_berth_order(self, phase: str) -> list[str]:
        s = self.state
        return [vid for _, vid in sorted((v.berth_start_time_min, vid) for vid, v in s.vessels.items()
                                         if v.phase == phase)]

    def _dispatch_crane(self, vessel_id: str, crane_id: str, batch: int) -> str:
        """D16: discharge before load; a load starts only when no discharge batch can start."""
        s, catalog = self.state, self.catalog
        v = s.vessels[vessel_id]
        for group_id, members in catalog.vessel_by_id[vessel_id].discharge_groups:
            cursor = v.discharge_cursor.get(group_id, 0)
            if cursor >= len(members):
                continue
            key = f"D|{vessel_id}|{group_id}"
            if s.yard_blocked.get(key) == s.capacity_version:
                continue
            indices = tuple(members[cursor:cursor + batch])
            self._open_decision("YARD", ("DISCHARGE", "VESSEL", vessel_id, group_id, indices, crane_id,
                                         vessel_id, key, self._next_work_order_id()))
            return "DECISION"
        ready = s.load_ready.get(vessel_id)
        if ready:
            key = min(ready)
            members = ready[key]
            indices = tuple(members[:batch])
            del members[:batch]
            if not members:
                del ready[key]
            if not ready:
                del s.load_ready[vessel_id]
            decision_id = f"DEC-{s.next_decision_seq:08d}"
            s.next_decision_seq += 1
            group_id, block_id = key.split("|")
            v.loads_started += len(indices)
            self._start_work_order("LOAD", group_id, indices, vessel_id=vessel_id, crane_id=crane_id,
                                   block_id=block_id, cause=decision_id)
            self._log_decision(decision_id, "DISPATCH", ("LOAD", self._last_work_order_id()))
            return "STARTED"
        return "NONE"

    def _last_work_order_id(self) -> str:
        return f"WO-{self.state.next_work_order_seq - 1:06d}"

    def _start_releases(self) -> bool:
        """Landside release admission: at most one GATE_OUT batch in progress per block.

        Spec §7.3 starts landside releases "when block capacity allows". A single landside
        batch already demands the block's whole handling capacity (gate_flow_demand = mu_b,
        §5.4), so a second concurrent release adds no throughput; because T7 frees storage at
        release *start*, it would only let new cargo occupy storage that retrieving containers
        still hold. Waiting releases therefore stay IN_YARD (occupying their TEU) in FIFO order of
        their pickup requests. The next batch is the head container's group, up to the batch size.
        """
        s = self.state
        batch = self.catalog.physics.batch_size_containers
        started = False
        for block_id in sorted(s.releasable):
            block = s.blocks[block_id]
            queue = s.releasable[block_id]
            if block.active_release_wo is not None or not queue:
                continue
            group_id = self.catalog.containers[queue[0]].group_id
            indices = tuple([i for i in queue if self.catalog.containers[i].group_id == group_id][:batch])
            chosen = set(indices)
            queue[:] = [i for i in queue if i not in chosen]
            if not queue:
                del s.releasable[block_id]
            decision_id = f"DEC-{s.next_decision_seq:08d}"
            s.next_decision_seq += 1
            self._start_work_order("GATE_OUT", group_id, indices, vessel_id=None, crane_id=None,
                                   block_id=block_id, cause=decision_id)
            block.active_release_wo = self._last_work_order_id()
            self._log_decision(decision_id, "DISPATCH", ("GATE_OUT", self._last_work_order_id()))
            started = True
        return started

    def _start_work_order(self, op: str, group_id: str, indices: tuple[int, ...], *, vessel_id: str | None,
                          crane_id: str | None, block_id: str, cause: str,
                          expected_id: str | None = None) -> None:
        s, catalog = self.state, self.catalog
        work_order_id = self._next_work_order_id()
        if expected_id is not None and expected_id != work_order_id:
            raise KernelError(f"work order id drift: expected {expected_id}, next {work_order_id}",
                              code="DECISION_PROTOCOL_ERROR")
        s.next_work_order_seq += 1
        teu = float(sum(catalog.containers[i].size_teu for i in indices))
        transfer = ("TRANSFER", work_order_id)
        block = s.blocks[block_id]
        if op == "DISCHARGE":
            source, destination = ("VESSEL", vessel_id), ("YARD_BLOCK", block_id)
        elif op == "GATE_IN":
            source, destination = ("GATE", catalog.gate_id), ("YARD_BLOCK", block_id)
        elif op == "LOAD":
            source, destination = ("YARD_BLOCK", block_id), ("VESSEL", vessel_id)
        else:
            source, destination = ("YARD_BLOCK", block_id), ("EXTERNAL_LANDSIDE", None)
        if op in ("DISCHARGE", "GATE_IN"):
            available = (catalog.block_by_id[block_id].capacity_teu - block.occupied_teu - block.reserved_teu
                         - block.blocked_teu)
            if available + 1e-9 < teu:
                raise KernelError(f"{work_order_id}: {block_id} cannot reserve {teu} TEU",
                                  code="MISSING_DESTINATION_CAPACITY")
            block.reservations[work_order_id] = teu
        for i in indices:
            c = catalog.containers[i]
            if s.c_claim[i] is not None:
                raise KernelError(f"{c.container_id} already claimed by {s.c_claim[i]}",
                                  code="UNAVAILABLE_SOURCE_INVENTORY")
            if op == "DISCHARGE":
                self._plan_record("YARD_RESERVATION_CREATED", i, work_order_id, block_id, cause, vessel_id)
                self._move(i, "DISCHARGE_STARTED", transfer, cause=cause, work_order_id=work_order_id,
                           resource=crane_id, vessel_id=vessel_id)
                s.c_entry_time[i] = s.now_min
            elif op == "GATE_IN":
                self._plan_record("YARD_RESERVATION_CREATED", i, work_order_id, block_id, cause,
                                  c.destination_vessel_id)
                self._move(i, "RECEIVE_STARTED", transfer, cause=cause, work_order_id=work_order_id,
                           resource=block_id, vessel_id=c.destination_vessel_id)
            elif op == "LOAD":
                if s.c_loc_id[i] != block_id:
                    raise KernelError(f"{c.container_id} not in source block {block_id}",
                                      code="UNAVAILABLE_SOURCE_INVENTORY")
                self._move(i, "LOAD_STARTED", transfer, cause=cause, work_order_id=work_order_id,
                           resource=crane_id, vessel_id=vessel_id)
                block.occupied_teu -= c.size_teu
                block.occupied_count -= 1
            else:
                if not s.c_pickup_due[i] or s.c_loc_id[i] != block_id:
                    raise KernelError(f"{c.container_id}: release before its pickup request or from the "
                                      "wrong block", code="INVALID_STATUS_TRANSITION")
                self._move(i, "RELEASE_STARTED", transfer, cause=cause, work_order_id=work_order_id,
                           resource=block_id)
                block.occupied_teu -= c.size_teu
                block.occupied_count -= 1
            s.c_claim[i] = work_order_id
        if op in ("LOAD", "GATE_OUT"):
            s.capacity_version += 1  # yard TEU freed at start (foundation T7/T9): retry blocked work
        s.work_orders[work_order_id] = WorkOrderState(
            work_order_id=work_order_id, operation_type=op, container_group_id=group_id,
            container_indices=tuple(indices), move_count=len(indices), planned_teu=teu,
            vessel_id=vessel_id, crane_id=crane_id, source=source, destination=destination,
            block_id=block_id, land_v_start=block.land_v, created_time_min=s.now_min,
            start_time_min=s.now_min, decision_id=cause)
        if op not in SHIP_SIDE:
            heapq.heappush(block.land_heap, (block.land_v + len(indices), work_order_id))
        if crane_id is not None:
            crane = s.cranes[crane_id]
            if crane.current_work_order_id is not None or crane.assigned_vessel_id != vessel_id:
                raise KernelError(f"{crane_id} cannot start {work_order_id}", code="INVALID_STATUS_TRANSITION")
            crane.current_work_order_id = work_order_id
        if op in ("DISCHARGE", "GATE_IN"):
            s.kpi["yard_reservations_created"] = s.kpi.get("yard_reservations_created", 0.0) + 1

    # ================================================================== FINALIZE phase
    def _finalize_cycle(self) -> None:
        s = self.state
        self._update_load_wait_timers()
        self._update_crane_activity()
        self._recompute_rates()
        s.cycles += 1
        landside = max((len(b.land_heap) for b in s.blocks.values()), default=0)
        if landside > s.kpi.get("peak_concurrent_landside_batches_per_block", 0.0):
            s.kpi["peak_concurrent_landside_batches_per_block"] = float(landside)
        if self.invariant_mode == "full":
            inv.check(self, full=True)
        elif self.invariant_mode == "cheap":
            full = self.full_check_interval > 0 and s.cycles % self.full_check_interval == 0
            inv.check(self, full=full)

    def _load_wait_condition(self, vessel_id: str) -> bool:
        s = self.state
        v = s.vessels[vessel_id]
        record = self.catalog.vessel_by_id[vessel_id]
        if v.discharge_completed != record.discharge_move_count:
            return False
        if v.discharge_started != v.discharge_completed or v.loads_started != v.loads_completed:
            return False
        if s.load_ready.get(vessel_id):
            return False
        unavailable = record.load_move_count - v.loads_started - len(v.rolled_over_container_ids)
        return unavailable > 0

    def _update_load_wait_timers(self) -> None:
        s = self.state
        for vessel_id, v in s.vessels.items():
            active = v.phase == "HANDLING" and self._load_wait_condition(vessel_id)
            if active and v.load_wait_deadline_min is None:
                v.load_wait_generation += 1
                v.load_wait_deadline_min = s.now_min + self.catalog.physics.max_load_wait_min
                self._schedule(v.load_wait_deadline_min, LOAD_WAIT_TIMEOUT, vessel_id, (vessel_id,),
                               v.load_wait_generation)
            elif not active and v.load_wait_deadline_min is not None:
                v.load_wait_deadline_min = None
                v.load_wait_generation += 1  # cancels the scheduled timeout

    def _blocked_reason(self, vessel_id: str) -> str:
        s = self.state
        v = s.vessels[vessel_id]
        record = self.catalog.vessel_by_id[vessel_id]
        if v.phase == "BERTHING_PREP":
            return "VESSEL_NOT_READY"
        if v.discharge_started < record.discharge_move_count:
            return "YARD_CAPACITY"
        if s.load_ready.get(vessel_id):
            return "YARD_CAPACITY"  # unreachable after dispatch; kept explicit
        unavailable = record.load_move_count - v.loads_started - len(v.rolled_over_container_ids)
        return "CARGO_UNAVAILABLE" if unavailable > 0 else "NO_REMAINING_WORK"

    def _update_crane_activity(self) -> None:
        s = self.state
        for crane_id in sorted(s.cranes):
            crane = s.cranes[crane_id]
            if crane.assigned_vessel_id is None:
                status, activity, reason = "available", "IDLE", None
            elif crane.current_work_order_id is not None:
                status, activity, reason = "operating", "PRODUCTIVE", None
            else:
                status, activity, reason = "assigned", "BLOCKED", self._blocked_reason(crane.assigned_vessel_id)
            if (activity, reason) != (crane.activity, crane.blocked_reason) or \
                    (activity == "BLOCKED" and crane_id not in s.open_block_episodes):
                self._close_block_episode(crane)
                if activity == "BLOCKED":
                    s.open_block_episodes[crane_id] = (crane.assigned_vessel_id, reason, s.now_min)
                crane.activity_since_min = s.now_min
            crane.status, crane.activity, crane.blocked_reason = status, activity, reason
            if activity != "PRODUCTIVE":
                crane.rate_moves_per_hour = 0.0

    def _close_block_episode(self, crane: CraneState) -> None:
        s = self.state
        episode = s.open_block_episodes.pop(crane.crane_id, None)
        if episode is not None:
            vessel_id, reason, start = episode
            s.block_episodes.append((crane.crane_id, vessel_id, reason, start, s.now_min))

    def work_order_progress(self, wo: WorkOrderState) -> float:
        """Settled moves of a batch (landside batches progress on their block's virtual clock)."""
        if wo.operation_type in SHIP_SIDE:
            return wo.completed_moves
        return min(float(wo.move_count), self.state.blocks[wo.block_id].land_v - wo.land_v_start)

    def _ship_work_orders(self) -> list[WorkOrderState]:
        s = self.state
        return [s.work_orders[c.current_work_order_id] for _, c in sorted(s.cranes.items())
                if c.current_work_order_id is not None]

    def _recompute_rates(self) -> None:
        """Spec §5.4 / §8.4: piecewise-constant rates; reschedule only completions whose rate changed.

        Ship-side batches (one per busy crane) each get their own completion event. Landside
        batches of a block all demand ``mu_b`` and so share equally (``allocate_block``); they
        complete in order of their virtual targets, so only the block's head batch needs an event.
        """
        s, catalog = self.state, self.catalog
        physics = catalog.physics
        if physics.efficiency_basis == "working":  # closure diagnostic only (see PhysicsConfig)
            counts: dict[str, int] = {}
            for wo in self._ship_work_orders():
                counts[wo.vessel_id] = counts.get(wo.vessel_id, 0) + 1
        else:  # frozen reference: cranes assigned to the vessel (spec §5.1)
            counts = self.crane_count_by_vessel()
        ship: dict[str, list] = {}
        for wo in self._ship_work_orders():
            block_record = catalog.block_by_id[wo.block_id]
            crane_rate = crane_rate_moves_per_hour(
                catalog.crane_by_id[wo.crane_id].nominal_moves_per_hour, counts[wo.vessel_id],
                self._service, physics.productivity_factor)
            demand = crane_rate
            if physics.transport_enabled:
                v = s.vessels[wo.vessel_id]
                quay_x = quay_transfer_x_m(v.berth_position_m, catalog.vessel_by_id[wo.vessel_id].length_m)
                distance = transfer_distance_m(quay_x, block_record.transfer_point_x_m,
                                               block_record.transfer_point_y_m)
                demand = min(demand, transport_rate_moves_per_hour(
                    distance, physics.transport_speed_m_per_min, physics.transport_handover_min,
                    physics.transport_units_per_crane))
            wo.crane_rate_moves_per_hour = crane_rate
            wo.demand_moves_per_hour = demand
            ship.setdefault(wo.block_id, []).append((wo.work_order_id, demand))
        for block_id in sorted(s.blocks):
            block = s.blocks[block_id]
            flows_ship = ship.get(block_id, [])
            if not flows_ship and not block.land_heap:
                block.land_rate = 0.0
                continue
            block_record = catalog.block_by_id[block_id]
            land_demand = block_record.handling_capacity_moves_per_hour  # gate_flow_demand (spec §5.4)
            if physics.yard_constraints_enabled:
                g = congestion_factor(block.occupied_teu, block_record.capacity_teu, physics.congestion_rho0,
                                      physics.congestion_g_min)
                ship_rates, land_rate = allocate_block(
                    block_record.handling_capacity_moves_per_hour * g, physics.landside_reserved_fraction,
                    flows_ship, len(block.land_heap), land_demand)
            else:  # Coupling C disabled: every flow receives its demand
                ship_rates = dict(flows_ship)
                land_rate = land_demand if block.land_heap else 0.0
            for work_order_id, rate in ship_rates.items():
                wo = s.work_orders[work_order_id]
                self._set_rate(wo, rate)
                s.cranes[wo.crane_id].rate_moves_per_hour = rate
                self._schedule_completion(wo, wo.move_count - wo.completed_moves)
            if block.land_heap:
                if not land_rate > 0.0:
                    raise KernelError(f"{block_id}: non-positive landside rate (unreachable in v1)",
                                      code="ZERO_RATE")
                target, head_id = block.land_heap[0]
                rate_changed = abs(land_rate - block.land_rate) > _RATE_REL_TOL * max(1.0, land_rate)
                if block.land_scheduled_wo is not None and (rate_changed or block.land_scheduled_wo != head_id):
                    previous = s.work_orders.get(block.land_scheduled_wo)
                    if previous is not None:
                        previous.rate_generation += 1  # its queued completion is now stale
                    block.land_scheduled_wo = None
                block.land_rate = land_rate
                head = s.work_orders[head_id]
                head.rate_moves_per_hour = land_rate
                head.demand_moves_per_hour = land_demand
                if block.land_scheduled_wo is None:
                    head.rate_generation += 1
                    self._schedule(s.now_min + 60.0 * max(0.0, target - block.land_v) / land_rate,
                                   WORK_ORDER_COMPLETED, head_id, (head_id,), head.rate_generation)
                    head.scheduled_generation = head.rate_generation
                    block.land_scheduled_wo = head_id
            else:
                block.land_rate = 0.0
                block.land_scheduled_wo = None

    def _set_rate(self, wo: WorkOrderState, rate: float) -> None:
        if not rate > 0.0:
            raise KernelError(f"{wo.work_order_id}: non-positive rate {rate} (unreachable in v1)",
                              code="ZERO_RATE")
        if wo.rate_generation == 0 or abs(rate - wo.rate_moves_per_hour) > _RATE_REL_TOL * max(1.0, rate):
            wo.rate_generation += 1  # any queued completion of the old rate becomes stale
        wo.rate_moves_per_hour = rate

    def _schedule_completion(self, wo: WorkOrderState, remaining: float) -> None:
        if wo.scheduled_generation == wo.rate_generation:
            return
        self._schedule(self.state.now_min + 60.0 * max(0.0, remaining) / wo.rate_moves_per_hour,
                       WORK_ORDER_COMPLETED, wo.work_order_id, (wo.work_order_id,), wo.rate_generation)
        wo.scheduled_generation = wo.rate_generation

    # ================================================================== termination
    def _resolved(self) -> bool:
        s = self.state
        return (all(v.phase == "DEPARTED" for v in s.vessels.values()) and not s.work_orders
                and not any(s.gate_queue.values()) and not any(s.releasable.values()))

    def _terminate_without_events(self) -> None:
        if self._resolved():
            self._end("COMPLETED", None, {})
        else:
            self._end("DEADLOCK", "unresolved work, no valid future event and no startable action",
                      self._unresolved_details(next_event=None))

    def _end(self, status: str, reason: str | None, details: dict) -> None:
        s = self.state
        for crane in s.cranes.values():
            self._close_block_episode(crane)
        s.status, s.status_reason, s.status_details = status, reason, details
        s.phase = "DONE"

    def _unresolved_details(self, *, next_event) -> dict[str, Any]:
        s, catalog = self.state, self.catalog
        vessels = {}
        for vessel_id, v in sorted(s.vessels.items()):
            if v.phase == "DEPARTED":
                continue
            record = catalog.vessel_by_id[vessel_id]
            vessels[vessel_id] = {
                "phase": v.phase, "remaining_moves": self.remaining_moves(vessel_id),
                "discharge_unstarted": record.discharge_move_count - v.discharge_started,
                "loads_unstarted": record.load_move_count - v.loads_started - len(v.rolled_over_container_ids),
                "loads_ready_in_yard": sum(len(x) for x in s.load_ready.get(vessel_id, {}).values()),
                "cranes": sorted(c.crane_id for c in s.cranes.values() if c.assigned_vessel_id == vessel_id),
            }
        return {
            "time_min": s.now_min,
            "next_event": None if next_event is None else list(next_event),
            "unresolved_vessels": vessels,
            "active_work_orders": sorted(s.work_orders),
            "blocked_cranes": {c.crane_id: [c.assigned_vessel_id, c.blocked_reason]
                               for c in s.cranes.values() if c.activity == "BLOCKED"},
            "containers_at_gate": sum(len(q) for q in s.gate_queue.values()),
            "releasable_waiting": sum(len(q) for q in s.releasable.values()),
            "pickups_due_not_in_yard": sum(1 for i, due in enumerate(s.c_pickup_due)
                                           if due and s.c_status[i] not in ("IN_YARD", "RETRIEVING_TO_LANDSIDE",
                                                                            "RELEASED_TO_LANDSIDE")),
            "yard_blocked_requests": dict(sorted(s.yard_blocked.items())),
            "block_occupancy": {b: [blk.occupied_teu, blk.reserved_teu, catalog.block_by_id[b].capacity_teu]
                                for b, blk in sorted(s.blocks.items())},
            "pending_exogenous_events": len(s.events),
        }


def _group_order(entry: tuple) -> tuple:
    return (entry[E_PRIORITY], entry[E_KEY], entry[E_SEQ])


def _add(acc: dict | None, key: str, value: float) -> None:
    if acc is not None:
        acc[key] = acc.get(key, 0.0) + value


def _initial_state(catalog: ScenarioCatalog, *, record_ledger: bool, record_event_log: bool) -> KernelState:
    n = len(catalog.containers)
    c_status, c_kind, c_loc = [None] * n, [None] * n, [None] * n
    for i, (status, kind, location_id) in enumerate(catalog.initial_locations):
        c_status[i], c_kind[i], c_loc[i] = status, kind, location_id
    blocks = {}
    for record in catalog.blocks:
        blocks[record.block_id] = BlockState(record.block_id,
                                             status=catalog.initial_block_status.get(record.block_id, "open"))
    vessels = {v.vessel_id: VesselState(v.vessel_id) for v in catalog.vessels}
    load_ready: dict[str, dict[str, list[int]]] = {}
    for c in catalog.containers:
        if c_kind[c.index] == "YARD_BLOCK":
            block = blocks[c_loc[c.index]]
            block.occupied_teu += c.size_teu
            block.occupied_count += 1
            if c.destination_vessel_id in vessels:
                key = f"{c.group_id}|{c_loc[c.index]}"
                load_ready.setdefault(c.destination_vessel_id, {}).setdefault(key, []).append(c.index)
    for block in blocks.values():
        block.peak_occupied_teu = block.occupied_teu
    return KernelState(
        now_min=0.0, phase="EVENTS", berth_epoch=False, same_time_cycles=0, cycles=0,
        next_event_seq=1, next_ledger_seq=1, next_work_order_seq=1, next_decision_seq=1, capacity_version=0,
        events=[], vessels=vessels, reveal_order=[],
        cranes={c.crane_id: CraneState(c.crane_id) for c in catalog.cranes}, blocks=blocks,
        work_orders={}, completed_work_orders=[],
        c_status=c_status, c_loc_kind=c_kind, c_loc_id=c_loc, c_claim=[None] * n, c_tindex=[0] * n,
        c_entry_time=[None] * n, c_release_time=[None] * n, c_rolled=[False] * n,
        c_pickup_due=[False] * n, c_gate_since=[None] * n,
        load_ready=load_ready, releasable={}, gate_queue={}, yard_blocked={}, pending=None,
        status="RUNNING", status_reason=None, status_details={},
        kpi={"peak_yard_teu": sum(b.occupied_teu for b in blocks.values())},
        block_episodes=[], open_block_episodes={},
        ledger=[] if record_ledger else None, event_log=[] if record_event_log else None,
        decision_log=[], stale_events_discarded=0)


__all__ = ["DecisionRequest", "EpisodeEnd", "KERNEL_VERSION", "KernelEventView", "Paused", "TerminalKernel",
           "YardRequestInfo"]
