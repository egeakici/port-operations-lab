"""Step 6 ``CoordinationView``: the narrow, immutable information boundary of the B arms.

Information contract: integration specification section 10 (D26). B arms may read the current
crane, transport and yard state in addition to the Step 5 ``BerthView``. They never read hidden
vessels, future gate-in or pickup times, the event queue, scenario identity or the live kernel.

The builder (trusted side) inspects the live kernel once per decision and returns frozen
dataclasses of primitive values. The policy (untrusted side) receives only the view. The optional
``SafeProjection`` is the B2/B2-T forward-model seed:

1. ``TerminalKernel.observable_clone()`` (Step 4, spec section 10): hidden vessels, their cargo,
   every future GATE_IN_ARRIVAL / PICKUP_DUE event, gate-in times, not-yet-requested pickup times,
   scenario identity, fingerprints, ledger and event log are removed.
2. Step 6 sanitisation:
   - event sequence numbers are renumbered in queue order. Original numbers count hidden events
     scheduled at initialisation.
   - vessel ids that refer to unrevealed vessels are replaced by ``UNREVEALED`` in container and
     group records (hidden transshipment or export links).
3. The result is frozen as pickled bytes plus a redacted catalog. Each forward evaluation forks a
   private kernel from the bytes, so candidates cannot share or mutate state.

Landside forecast rule for forward models (D26, PROPOSED in Step 1): future gate-ins and pickups are
**not simulated**. Every fixed allowlisted field is listed in ``ALLOWLIST``; the projection is the
one documented aggregate exception.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict, dataclass, replace
from typing import Any

from integrated_terminal_pilot.simulator.errors import KernelError
from integrated_terminal_pilot.simulator.events import E_SEQ
from integrated_terminal_pilot.simulator.observations import BerthView

VIEW_SCHEMA = "itp_coordination_view_v1"
PROJECTION_SCHEMA = "itp_safe_projection_v1"
FORECAST_ASSUMPTIONS = {
    "version": "itp_step6_forecast_v1",
    "landside_future": "NOT_SIMULATED (spec section 10 / D26 PROPOSED rule: no future gate-in or pickup "
                       "requests; only requests that already occurred are processed)",
    "hidden_vessels": "ABSENT (not announced: no record, event, slot or count)",
    "announced_vessels": "arrive at their announced time (D18: no ETA noise)",
    "service": "same Step 4 kernel physics on the projected state (cranes, transport, yard, D15/D16/D17/R5)",
    "randomness": "none (deterministic kernel; replication count 1; common random numbers trivially shared)",
    "uncertainty": "UNCALIBRATED_SYNTHETIC_FORECAST",
}
UNREVEALED = "V000"   # reserved placeholder (generator vessel ids start at V001; Step 3 pattern "V" + 3 digits)
OCCUPYING = ("BERTHING_PREP", "HANDLING", "DEPARTURE_PREP")
LOADED_STATUSES = frozenset({"LOADED", "DEPARTED_BY_VESSEL", "LOADING"})

# field -> allowed source (spec section 10 row) - documentation and test anchor
ALLOWLIST = {
    "berth": "Step 5 BerthView (revealed vessels, forecasts, physical legal set, WAIT bit)",
    "cranes": "current crane status/assignment/activity (spec 10: crane assignments - observable to B arms)",
    "vessels": "manifest of revealed, not departed vessels (spec 10 row 1) + realized progress (row 3)",
    "blocks": "current yard occupancy, reservations, status, static block data (spec 10 row 3)",
    "physics": "published physics coefficients of the scenario (crane, transport, yard, service, work rules)",
    "projection": "sanitised observable clone (spec 10: forward models run the same kernel on an ObservableClone)",
}


class CoordinationViewError(KernelError):
    """A coordination input is malformed or not a CoordinationView (fails closed)."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"{gate}: {message}", code=f"B_POLICY_GATE_{gate}")
        self.gate = gate


@dataclass(frozen=True)
class CraneSnapshot:
    crane_id: str
    assigned_vessel_id: str | None
    activity: str
    working: bool
    nominal_moves_per_hour: float
    compatible_vessel_ids: tuple[str, ...] | None


@dataclass(frozen=True)
class VesselCargoSnapshot:
    vessel_id: str
    phase: str
    max_cranes: int
    assigned_cranes: int
    remaining_discharge_moves: int        # inbound containers still aboard this vessel
    outbound_obligations: int             # containers on this vessel's load manifest
    outbound_loaded: int                  # LOADING / LOADED / departed with the vessel
    outbound_in_yard_by_block: tuple[tuple[str, int], ...]
    outbound_not_in_terminal: int         # still aboard another vessel or not yet gated in
    rolled_over: int


@dataclass(frozen=True)
class BlockSnapshot:
    block_id: str
    status: str
    capacity_teu: float
    occupied_teu: float
    reserved_teu: float
    blocked_teu: float
    handling_capacity_moves_per_hour: float
    transfer_point_x_m: float
    transfer_point_y_m: float
    capabilities: tuple[str, ...]
    allowed_sizes: tuple[str, ...]
    active_ship_flows: int
    active_landside_flows: int


@dataclass(frozen=True)
class PublicPhysics:
    efficiency: tuple[float, float, float, float]  # one, two, three, four_plus
    productivity_factor: float
    transport_enabled: bool
    transport_speed_m_per_min: float
    transport_handover_min: float
    transport_units_per_crane: int
    yard_constraints_enabled: bool
    congestion_rho0: float
    congestion_g_min: float
    landside_reserved_fraction: float
    berthing_preparation_min: float
    departure_preparation_min: float
    service_minutes_per_move: float
    batch_size_containers: int
    max_load_wait_min: float


@dataclass(frozen=True)
class SafeProjection:
    """Forward-model seed: redacted catalog + pickled sanitised state (never a live kernel)."""

    schema: str
    catalog: Any          # ScenarioCatalog (frozen; observable=True; identity/fingerprints None)
    state_bytes: bytes
    digest: str
    assumptions: tuple[tuple[str, str], ...]
    creation_seconds: float

    def fork(self):
        """A private kernel for one forward evaluation (independent of every other fork)."""
        from integrated_terminal_pilot.simulator.kernel import TerminalKernel

        return TerminalKernel(self.catalog, pickle.loads(self.state_bytes), invariant_mode="off")


@dataclass(frozen=True)
class CoordinationView:
    schema: str
    time_min: float
    decision_id: str
    berth: BerthView
    cranes: tuple[CraneSnapshot, ...]
    vessels: tuple[VesselCargoSnapshot, ...]
    blocks: tuple[BlockSnapshot, ...]
    physics: PublicPhysics
    projection: SafeProjection | None
    digest: str


def _sanitise_state(state, visible: set[str]) -> None:
    """In-place on a clone: renumber event sequence numbers in queue order."""
    events = sorted(state.events)
    renumbered = []
    for seq, entry in enumerate(events, start=1):
        renumbered.append(tuple(seq if i == E_SEQ else value for i, value in enumerate(entry)))
    state.events = renumbered          # sorted list is a valid heap
    state.next_event_seq = len(renumbered) + 1


def _sanitise_catalog(catalog, visible: set[str]):
    def vid(value):
        return value if value is None or value in visible or value == "PRE_EPISODE" else UNREVEALED

    containers = tuple(replace(c, origin_vessel_id=vid(c.origin_vessel_id),
                               destination_vessel_id=vid(c.destination_vessel_id)) for c in catalog.containers)
    groups = {}
    for gid, record in catalog.groups.items():
        record = dict(record)
        for key in ("source_vessel_id", "target_vessel_id"):
            if key in record:
                record[key] = vid(record[key])
        groups[gid] = record
    return replace(catalog, containers=containers, groups=groups)


def build_projection(kernel) -> SafeProjection:
    import time

    started = time.perf_counter()
    clone = kernel.observable_clone()
    visible = set(clone.state.vessels)
    state = clone.state
    _sanitise_state(state, visible)
    catalog = _sanitise_catalog(clone.catalog, visible)
    if catalog.identity is not None or catalog.fingerprints is not None or catalog.scenario_id is not None:
        raise CoordinationViewError("G6-02", "projection catalog still carries scenario identity")
    if state.ledger is not None or state.event_log is not None:
        raise CoordinationViewError("G6-02", "projection state still carries the ledger or event log")
    blob = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
    catalog_digest = hashlib.sha256(repr((catalog.vessels, catalog.containers, sorted(catalog.groups.items()),
                                          catalog.drain_limit_min, catalog.physics)).encode()).hexdigest()
    digest = hashlib.sha256(blob + catalog_digest.encode()).hexdigest()
    return SafeProjection(PROJECTION_SCHEMA, catalog, blob, digest, tuple(sorted(FORECAST_ASSUMPTIONS.items())),
                          time.perf_counter() - started)


def build_coordination_view(kernel, *, include_projection: bool) -> CoordinationView:
    """Trusted builder: a frozen snapshot of permitted current information (spec section 10)."""
    catalog, s = kernel.catalog, kernel.state
    berth = kernel.berth_view()
    held: dict[str, int] = {}
    cranes = []
    for crane_id in sorted(s.cranes):
        c = s.cranes[crane_id]
        record = catalog.crane_by_id[crane_id]
        if c.assigned_vessel_id is not None:
            held[c.assigned_vessel_id] = held.get(c.assigned_vessel_id, 0) + 1
        cranes.append(CraneSnapshot(crane_id, c.assigned_vessel_id, c.activity, c.current_work_order_id is not None,
                                    record.nominal_moves_per_hour, record.compatible_vessel_ids))
    vessels = []
    for vessel_id in s.reveal_order:
        v = s.vessels[vessel_id]
        if v.phase == "DEPARTED":
            continue
        record = catalog.vessel_by_id[vessel_id]
        inbound = [i for _, members in record.discharge_groups for i in members]
        aboard = sum(1 for i in inbound if s.c_status[i] in ("EXPECTED_BY_VESSEL", "ABOARD_ARRIVED_VESSEL"))
        by_block: dict[str, int] = {}
        loaded = not_in_terminal = 0
        for i in record.load_container_indices:
            status = s.c_status[i]
            if status in LOADED_STATUSES:
                loaded += 1
            elif s.c_loc_kind[i] == "YARD_BLOCK" and status == "IN_YARD":
                by_block[s.c_loc_id[i]] = by_block.get(s.c_loc_id[i], 0) + 1
            elif status in ("EXPECTED_BY_VESSEL", "EXPECTED_BY_LANDSIDE", "ABOARD_ARRIVED_VESSEL", "AT_GATE",
                            "DISCHARGING", "RECEIVING"):
                not_in_terminal += 1
            else:
                not_in_terminal += 1   # any other transient state counts as not yet loadable
        vessels.append(VesselCargoSnapshot(
            vessel_id, v.phase, record.max_cranes, held.get(vessel_id, 0), aboard,
            len(record.load_container_indices), loaded, tuple(sorted(by_block.items())), not_in_terminal,
            len(v.rolled_over_container_ids)))
    flows: dict[str, list[int]] = {}
    for wo in s.work_orders.values():
        if wo.status != "IN_PROGRESS":
            continue
        counts = flows.setdefault(wo.block_id, [0, 0])
        counts[0 if wo.operation_type in ("DISCHARGE", "LOAD") else 1] += 1
    blocks = []
    for record in catalog.blocks:
        b = s.blocks[record.block_id]
        ship, land = flows.get(record.block_id, [0, 0])
        blocks.append(BlockSnapshot(record.block_id, b.status, record.capacity_teu, b.occupied_teu,
                                    sum(b.reservations.values()), b.blocked_teu,
                                    record.handling_capacity_moves_per_hour, record.transfer_point_x_m,
                                    record.transfer_point_y_m, tuple(sorted(record.capabilities)),
                                    tuple(sorted(record.allowed_sizes)), ship, land))
    p = catalog.physics
    physics = PublicPhysics((p.efficiency_one, p.efficiency_two, p.efficiency_three, p.efficiency_four_plus),
                            p.productivity_factor, p.transport_enabled, p.transport_speed_m_per_min,
                            p.transport_handover_min, p.transport_units_per_crane, p.yard_constraints_enabled,
                            p.congestion_rho0, p.congestion_g_min, p.landside_reserved_fraction,
                            p.berthing_preparation_min, p.departure_preparation_min, p.service_minutes_per_move,
                            p.batch_size_containers, p.max_load_wait_min)
    projection = build_projection(kernel) if include_projection else None
    payload = {"schema": VIEW_SCHEMA, "time": berth.time_min, "decision": berth.decision_id,
               "berth": asdict(berth), "cranes": [asdict(c) for c in cranes], "vessels": [asdict(v) for v in vessels],
               "blocks": [asdict(b) for b in blocks], "physics": asdict(physics),
               "projection": None if projection is None else projection.digest}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=list).encode()).hexdigest()
    return CoordinationView(VIEW_SCHEMA, berth.time_min, berth.decision_id, berth, tuple(cranes), tuple(vessels),
                            tuple(blocks), physics, projection, digest)


def require_view(view, *, need_projection: bool) -> CoordinationView:
    if not isinstance(view, CoordinationView) or view.schema != VIEW_SCHEMA:
        raise CoordinationViewError("G6-02", f"expected a {VIEW_SCHEMA} CoordinationView, got {type(view).__name__}")
    if need_projection and not isinstance(view.projection, SafeProjection):
        raise CoordinationViewError("G6-02", "this policy needs the safe projection")
    return view


def coordination_observer(*, include_projection: bool):
    """Observer for ``run_episode(berth_observer=...)``: trusted builder side only."""

    def observe(kernel):
        return build_coordination_view(kernel, include_projection=include_projection)

    observe.observation_schema = VIEW_SCHEMA
    return observe


__all__ = ["ALLOWLIST", "BlockSnapshot", "CoordinationView", "CoordinationViewError", "CraneSnapshot",
           "FORECAST_ASSUMPTIONS", "PROJECTION_SCHEMA", "PublicPhysics", "SafeProjection", "UNREVEALED",
           "VIEW_SCHEMA", "VesselCargoSnapshot", "build_coordination_view", "build_projection",
           "coordination_observer", "require_view"]
