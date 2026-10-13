"""``BerthViewAdapter`` (bap_compatibility_contract.md sections 2-3, 9): integrated berth view -> Project 03 inputs.

The only input is the kernel's immutable ``BerthView`` (``observations.build_berth_view``): revealed
vessels in slot order, current legal immediate assignments and the WAIT bit. It never sees the
kernel, the event queue, hidden vessels, gate/pickup times, crane or yard state. From that view the
adapter derives, without adding information:

* the Project 03 status of every revealed vessel (OCCUPYING -> IN_SERVICE, DEPARTED -> COMPLETED);
* one ``BAPPlacement`` per occupying vessel ending at its ``ServiceForecaster v1`` release
  (contract section 2.1, FORECAST-SUBSTITUTED); nominal service stays immutable in the vessel input;
* the Project 03 choice table ``(action, vessel_id, candidate_index, position, arrival)`` with
  ``action = 1 + slot * P + candidate_index``;
* the Project 03 WAIT bit.

Every adaptation re-derives the candidates with the *unchanged* Project 03 ``candidate_positions`` /
``is_placement_feasible`` on the adapter placements and requires them to equal the kernel's physical
legal set exactly (gates G08/G09), and re-derives the WAIT bit with the Project 03 rule (G08). A
forecast release at or before ``now`` for an occupying vessel is a kernel defect (G17). Any mismatch
raises :class:`AdapterContractError`; nothing is clamped, padded or repaired.
"""

from __future__ import annotations

from dataclasses import dataclass

from berth_allocation_lab.core import BAPPlacement, candidate_positions, is_placement_feasible
from berth_allocation_lab.data import BAPVesselInput

from integrated_terminal_pilot.simulator.errors import KernelError
from integrated_terminal_pilot.simulator.observations import BERTH_VIEW_SCHEMA, BerthView

ADAPTER_VERSION = "itp_berth_view_adapter_v1"
P03_STATUS = {"ANNOUNCED": "ANNOUNCED", "WAITING": "WAITING", "OCCUPYING": "IN_SERVICE",
              "DEPARTED": "COMPLETED"}
FORECAST_EXACT_TOL_MIN = 1e-9


class AdapterContractError(KernelError):
    """The integrated view cannot be mapped faithfully at this epoch (a gate check failed).

    A ``KernelError`` so that ``run_episode`` reports the run ``FAILED`` with code
    ``BERTH_POLICY_GATE_<gate>`` - never repaired, never replaced by a fallback action.
    """

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"{gate}: {message}", code=f"BERTH_POLICY_GATE_{gate}")
        self.gate = gate


@dataclass(frozen=True)
class OccupancyForecast:
    vessel_id: str
    berth_start_time_min: float
    nominal_end_time_min: float          # berth_start + nominal service (Project 03 meaning)
    forecast_release_time_min: float     # ServiceForecaster v1 (policy-visible end of occupancy)

    @property
    def mode(self) -> str:
        exact = abs(self.forecast_release_time_min - self.nominal_end_time_min) <= FORECAST_EXACT_TOL_MIN
        return "EXACT" if exact else "FORECAST"


@dataclass(frozen=True)
class AdaptedBerthState:
    """Project 03-shaped, strictly observable berth state at one decision epoch (immutable)."""

    decision_id: str
    time_min: float
    berth_length_m: float
    min_clearance_m: float
    future_horizon_min: float
    candidate_capacity: int                                  # P
    slot_ids: tuple[str, ...]
    vessels_by_slot: tuple[BAPVesselInput, ...]              # nominal service, never realized
    statuses_by_slot: tuple[str, ...]                        # Project 03 statuses
    placement_by_id: tuple[tuple[str, BAPPlacement], ...]    # occupying vessels, slot order
    legal_choices: tuple[tuple[int, str, int, float, float], ...]
    wait_legal: bool
    forecasts: tuple[OccupancyForecast, ...]

    @property
    def active_placements(self) -> tuple[BAPPlacement, ...]:
        return tuple(placement for _, placement in self.placement_by_id)

    @property
    def choice_by_action(self) -> dict[int, tuple[str, int, float]]:
        return {action: (vessel_id, index, position) for action, vessel_id, index, position, _ in self.legal_choices}

    @property
    def forecast_epoch_mode(self) -> str:
        if not self.forecasts:
            return "NO_OCCUPANCY"
        return "EXACT" if all(f.mode == "EXACT" for f in self.forecasts) else "FORECAST"


def adapt_berth_view(view: BerthView, *, candidate_capacity: int) -> AdaptedBerthState:
    """Map one ``BerthView`` to Project 03 inputs; raise :class:`AdapterContractError` on any mismatch."""
    if not isinstance(view, BerthView) or view.schema_version != BERTH_VIEW_SCHEMA:
        raise AdapterContractError("G20", f"expected an {BERTH_VIEW_SCHEMA} BerthView")
    if candidate_capacity <= 0:
        raise ValueError("candidate_capacity must be positive")
    now = view.time_min
    slot_ids, vessels, statuses, placements, forecasts = [], [], [], [], []
    for expected_slot, vessel in enumerate(view.vessels):
        if vessel.slot_index != expected_slot:
            raise AdapterContractError("G10", f"slot of {vessel.vessel_id} is {vessel.slot_index}, "
                                              f"expected {expected_slot} (reveal order)")
        if vessel.status not in P03_STATUS:
            raise AdapterContractError("G08", f"unknown berth status {vessel.status!r}")
        slot_ids.append(vessel.vessel_id)
        vessels.append(BAPVesselInput(vessel.vessel_id, vessel.arrival_time_min, vessel.length_m,
                                      vessel.nominal_service_time_min))
        statuses.append(P03_STATUS[vessel.status])
        if vessel.status == "OCCUPYING":
            release = vessel.estimated_release_time_min
            if release is None or not release > now:
                raise AdapterContractError("G17", f"forecast release {release} of occupying {vessel.vessel_id} "
                                                  f"is not > now {now} (kernel defect, FAIL_RUN)")
            start = vessel.berth_start_time_min
            placements.append((vessel.vessel_id, BAPPlacement(vessel.vessel_id, vessel.berth_position_m, start,
                                                              vessel.length_m, release - start)))
            forecasts.append(OccupancyForecast(vessel.vessel_id, start, start + vessel.nominal_service_time_min,
                                               release))
    active = tuple(p for _, p in placements)
    derived: list[tuple[int, str, int, float, float]] = []
    for slot, (vessel_input, status) in enumerate(zip(vessels, statuses)):
        if status != "WAITING":
            continue
        positions = tuple(x for x in candidate_positions(vessel_input, active, view.berth_length_m,
                                                         view.min_clearance_m)
                          if is_placement_feasible(vessel_input, x, now, active, view.berth_length_m,
                                                   view.min_clearance_m))
        if len(positions) > candidate_capacity:
            raise AdapterContractError("G09", f"{vessel_input.vessel_id} has {len(positions)} candidates "
                                              f"> P = {candidate_capacity}")
        for index, position in enumerate(positions):
            derived.append((1 + slot * candidate_capacity + index, vessel_input.vessel_id, index, position,
                            vessel_input.arrival_time_min))
    physical = tuple((vessel_id, index, position) for vessel_id, index, position, _ in view.legal_choices)
    if tuple((v, i, x) for _, v, i, x, _ in derived) != physical:
        raise AdapterContractError("G08", "Project 03 candidate set on adapter placements differs from the "
                                          f"physical legal set: {derived} vs {physical}")
    visible_future = any(
        (status == "ANNOUNCED" and vessel_input.arrival_time_min > now)
        or (status == "IN_SERVICE" and dict(placements)[vessel_input.vessel_id].service_end_time_min > now)
        for vessel_input, status in zip(vessels, statuses))
    wait_legal = bool(derived) and visible_future
    if wait_legal != view.wait_legal:
        raise AdapterContractError("G08", f"Project 03 WAIT bit {wait_legal} differs from the kernel's "
                                          f"{view.wait_legal}")
    return AdaptedBerthState(
        decision_id=view.decision_id, time_min=now, berth_length_m=view.berth_length_m,
        min_clearance_m=view.min_clearance_m, future_horizon_min=view.future_horizon_min,
        candidate_capacity=candidate_capacity, slot_ids=tuple(slot_ids), vessels_by_slot=tuple(vessels),
        statuses_by_slot=tuple(statuses), placement_by_id=tuple(placements), legal_choices=tuple(derived),
        wait_legal=wait_legal, forecasts=tuple(forecasts))


def visible_state(state: AdaptedBerthState):
    """Project 03 ``DynamicVisibleState`` (the only input of ``online_rollout_choice``)."""
    from berth_allocation_lab.envs.dynamic_visible_state import DynamicVisibleState

    return DynamicVisibleState(
        current_time_min=state.time_min, berth_length_m=state.berth_length_m,
        min_clearance_m=state.min_clearance_m, future_horizon_min=state.future_horizon_min,
        vessels_by_slot=state.vessels_by_slot, statuses_by_slot=state.statuses_by_slot,
        active_placements=state.active_placements, legal_choices=state.legal_choices,
        wait_legal=state.wait_legal)


class _Scenario:
    def __init__(self, berth_length_m: float, min_clearance_m: float) -> None:
        self.berth_length_m = berth_length_m
        self.min_clearance_m = min_clearance_m


class P03ObservationHost:
    """Duck-typed host exposing exactly the attributes Project 03 ``encode_dynamic_observation`` reads.

    The encoder itself is called unchanged, so feature order, normalization, dtypes and the
    action-mask meaning are Project 03's by construction (gates G05-G07, G20).
    """

    def __init__(self, state: AdaptedBerthState, *, max_vessels: int, time_scale_min: float,
                 length_scale_m: float) -> None:
        from gymnasium import spaces

        if len(state.slot_ids) > max_vessels:
            raise AdapterContractError("G11", f"{len(state.slot_ids)} revealed vessels > M = {max_vessels} "
                                              "(slots are never reused; no truncation)")
        if state.candidate_capacity != 2 * max_vessels:
            raise AdapterContractError("G07", f"P = {state.candidate_capacity} != 2M = {2 * max_vessels}")
        self._scenario = _Scenario(state.berth_length_m, state.min_clearance_m)
        self.current_time_min = state.time_min
        self.time_scale_min = time_scale_min
        self.length_scale_m = length_scale_m
        self.max_vessels = max_vessels
        self.candidate_capacity = state.candidate_capacity
        self.future_horizon_min = state.future_horizon_min
        self.action_space = spaces.Discrete(1 + max_vessels * state.candidate_capacity)
        self._slot_ids = list(state.slot_ids)
        self._vessel_by_id = {v.vessel_id: v for v in state.vessels_by_slot}
        self._status = dict(zip(state.slot_ids, state.statuses_by_slot))
        self._placement_by_id = dict(state.placement_by_id)
        self._choices = state.choice_by_action
        self._wait_legal = state.wait_legal

    def action_masks(self):
        import numpy as np

        mask = np.zeros(self.action_space.n, dtype=bool)
        mask[0] = self._wait_legal
        for action in self._choices:
            mask[action] = True
        return mask


def dynamic_observation(state: AdaptedBerthState, *, max_vessels: int, time_scale_min: float = 1440.0,
                        length_scale_m: float = 1000.0):
    """``dynamic_obs_v1`` from the adapted state via Project 03 ``encode_dynamic_observation``."""
    from berth_allocation_lab.envs.dynamic_observation import encode_dynamic_observation

    host = P03ObservationHost(state, max_vessels=max_vessels, time_scale_min=time_scale_min,
                              length_scale_m=length_scale_m)
    return encode_dynamic_observation(host), host.action_masks()


__all__ = ["ADAPTER_VERSION", "AdaptedBerthState", "AdapterContractError", "OccupancyForecast",
           "P03ObservationHost", "P03_STATUS", "adapt_berth_view", "dynamic_observation", "visible_state"]
