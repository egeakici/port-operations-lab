"""Step 6 berth decision rules: A1n, B1, and the shared B2 / B2-T integrated rollout.

Protocol sources:

* ``scientific_experiment_protocol.md`` section 3 (arms) and section 5 (budget);
* AM-07 (cargo-first B2) and AM-08 (matched B2-T) in ``protocol_amendments.md``.

* **A1n** (protocol 3, secondary control): greedy minimum *estimated release time* over all legal
  (vessel, position), estimate from **nominal** service; ties by the FCFS key; never WAITs. Berth-only.
* **B1** (protocol 3, primary): the same greedy rule with estimates from the **integrated one-step
  estimator**: crane availability, multi-crane efficiency, transport distance from the candidate
  position to the vessel's load and preview-discharge blocks, current yard congestion. The protocol
  leaves the estimator's details to Step 6: ``B1_ESTIMATOR`` is
  ``PROPOSED_STEP6_DETAIL_NEEDS_OWNER_APPROVAL``.
* **B2 / B2-T** (protocol 3 B2 + AM-07 + AM-08):
  - Candidate set: the same as A2's, i.e. all legal actions plus WAIT if legal.
  - Evaluation: each candidate is scored by an observable-clone kernel run of the visible cohort to
    completion, with FCFS berth continuation and the common P_c / P_y.
  - WAIT: scored with the Project 03 ``finish_after_wait`` semantics. The fork advances to the next
    berth decision; each legal assignment there is rolled out; the best one under the arm's own key
    is used.
  - One evaluator produces the ``CandidatePrediction`` records; two pure selectors read the same
    records.
  - B2 key: (predicted unfulfilled visible outbound obligations, predicted visible-cohort
    turnaround, action index).
  - B2-T key: (predicted turnaround, action index); cargo predictions are logged only.
  - No weights, no tolerance, no fallback, no pruning.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from integrated_terminal_pilot.benchmark.adapter import AdapterContractError, adapt_berth_view
from integrated_terminal_pilot.benchmark.coordination_view import (
    FORECAST_ASSUMPTIONS, CoordinationViewError, require_view,
)
from integrated_terminal_pilot.benchmark.policies import NON_PPO_CANDIDATE_CAPACITY, BerthPolicy
from integrated_terminal_pilot.simulator.kernel import DecisionRequest, EpisodeEnd, Paused
from integrated_terminal_pilot.simulator.physics import (
    congestion_factor, quay_transfer_x_m, transfer_distance_m, transport_rate_moves_per_hour,
)
from integrated_terminal_pilot.simulator.validator import BerthAction

EVALUATOR_VERSION = "itp_b2_shared_rollout_evaluator_v1"
B1_ESTIMATOR = {
    "version": "itp_b1_one_step_estimator_v1",
    "status": "PROPOSED_STEP6_DETAIL_NEEDS_OWNER_APPROVAL",
    "formula": "release = now + crane_delay + berthing_prep + sum_over_flows(60 * moves_b / rate_b) + departure_prep",
    "cranes": "n = min(max_cranes, free compatible cranes now); if n = 0: n = 1 and crane_delay = earliest "
              "(forecast_release - departure_prep - now) of an occupying vessel holding cranes",
    "flows": "discharge: all inbound moves to the preview block (AM-01 balanced order: lowest "
             "(occupied+reserved)/capacity among open blocks with free TEU, ties by block_id); load: outbound "
             "containers per current yard block; outbound not yet in the yard: preview block; D16 discharge "
             "then load, flows summed sequentially",
    "rate": "rate_b = min(n x nominal x eff(n) x productivity, n x transport_rate(distance(candidate quay "
            "transfer point, block b)), mu_b x g(rho_b) x (1 - landside_reserve if landside flows > 0 else 1) "
            "/ (1 + active ship flows at b))",
    "rank": "(estimated release, arrival, vessel_id, position); never WAIT",
}
CONTINUATION = {"berth": "fixture_p03_online_fcfs (Project 03 online_fcfs_action over the physical legal set)",
                "crane": "primitive_crane_greedy_v1", "yard": "common P_y of the research profile"}
DEFAULT_INNER_CYCLE_GUARD = 400_000   # engineering guard per rollout leaf (not a policy budget)
UNFULFILLED_STATUSES_EXCLUDED = frozenset({"LOADED", "DEPARTED_BY_VESSEL"})


class B2EvaluationError(AdapterContractError):
    """A forward evaluation failed or exceeded the engineering guard (symmetric: the run fails)."""


# ------------------------------------------------------------------------------------------------ A1n

class A1nNominalGreedyPolicy(BerthPolicy):
    """Protocol 3 A1n: greedy minimum nominal release over legal (vessel, position); FCFS tie; no WAIT."""

    arm_id = "A1n"
    policy_id = "a1n_nominal_greedy_release_v1"
    p03_policy_id = "none (Project I protocol section 3 A1n)"

    def _choose(self, state):
        service = {v.vessel_id: v.service_time_min for v in state.vessels_by_slot}
        if not state.legal_choices:
            raise AdapterContractError("G19", "A1n has no legal assignment")
        best = min(state.legal_choices,
                   key=lambda c: (state.time_min + service[c[1]], c[4], c[1], c[3]))
        return best[0], {"key": "nominal_release"}


# ------------------------------------------------------------------------------------------------ B1

def _efficiency(physics, n: int) -> float:
    one, two, three, four = physics.efficiency
    return {1: one, 2: two, 3: three}.get(n, four) if n >= 1 else 0.0


def _preview_block(view):
    open_blocks = [b for b in view.blocks if b.status == "open"
                   and b.capacity_teu - b.occupied_teu - b.reserved_teu - b.blocked_teu > 0]
    if not open_blocks:
        return None
    return min(open_blocks, key=lambda b: ((b.occupied_teu + b.reserved_teu) / b.capacity_teu, b.block_id))


def b1_release_estimate(view, vessel_id: str, position: float) -> dict[str, Any]:
    """Integrated one-step estimate of the release time of starting ``vessel_id`` at ``position`` now."""
    phys = view.physics
    berth_vessel = next(v for v in view.berth.vessels if v.vessel_id == vessel_id)
    cargo = next(v for v in view.vessels if v.vessel_id == vessel_id)
    free = [c for c in view.cranes if c.assigned_vessel_id is None
            and (c.compatible_vessel_ids is None or vessel_id in c.compatible_vessel_ids)]
    n = min(cargo.max_cranes, len(free))
    delay = 0.0
    if n == 0:
        holders = {c.assigned_vessel_id for c in view.cranes if c.assigned_vessel_id is not None}
        releases = [v.estimated_release_time_min - phys.departure_preparation_min - view.time_min
                    for v in view.berth.vessels if v.vessel_id in holders and v.estimated_release_time_min]
        delay = max(0.0, min(releases)) if releases else 0.0
        n = 1
    nominal = min(c.nominal_moves_per_hour for c in (free or view.cranes))
    crane_cap = n * nominal * _efficiency(phys, n) * phys.productivity_factor
    quay_x = quay_transfer_x_m(position, berth_vessel.length_m)
    blocks = {b.block_id: b for b in view.blocks}
    preview = _preview_block(view)
    flows: list[tuple[str, str, int]] = []
    if cargo.remaining_discharge_moves:
        flows.append(("discharge", preview.block_id if preview else "", cargo.remaining_discharge_moves))
    for block_id, count in cargo.outbound_in_yard_by_block:
        flows.append(("load", block_id, count))
    if cargo.outbound_not_in_terminal:
        flows.append(("load", preview.block_id if preview else "", cargo.outbound_not_in_terminal))
    handling = 0.0
    details = []
    for kind, block_id, moves in flows:
        rate = crane_cap
        block = blocks.get(block_id)
        if block is not None:
            if phys.transport_enabled:
                d = transfer_distance_m(quay_x, block.transfer_point_x_m, block.transfer_point_y_m)
                rate = min(rate, n * transport_rate_moves_per_hour(d, phys.transport_speed_m_per_min,
                                                                   phys.transport_handover_min,
                                                                   phys.transport_units_per_crane))
            if phys.yard_constraints_enabled:
                g = congestion_factor(block.occupied_teu, block.capacity_teu, phys.congestion_rho0,
                                      phys.congestion_g_min)
                share = 1.0 - phys.landside_reserved_fraction if block.active_landside_flows else 1.0
                rate = min(rate, block.handling_capacity_moves_per_hour * g * share / (1 + block.active_ship_flows))
        minutes = 60.0 * moves / rate if rate > 0 else float("inf")
        handling += minutes
        details.append({"flow": kind, "block": block_id, "moves": moves, "rate_mph": rate, "minutes": minutes})
    release = (view.time_min + delay + phys.berthing_preparation_min + handling + phys.departure_preparation_min)
    return {"release_min": release, "cranes": n, "crane_delay_min": delay, "handling_min": handling,
            "flows": details}


class B1IntegratedGreedyPolicy:
    """Protocol 3 B1: greedy minimum integrated one-step release estimate; FCFS tie; never WAIT."""

    arm_id = "B1"
    policy_id = "b1_integrated_greedy_release_v1"
    observation = "coordination_view_no_projection"

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def decide(self, view) -> BerthAction:
        t0 = time.perf_counter()
        view = require_view(view, need_projection=False)
        state = adapt_berth_view(view.berth, candidate_capacity=NON_PPO_CANDIDATE_CAPACITY)
        if not state.legal_choices:
            raise AdapterContractError("G19", "B1 has no legal assignment")
        scored = []
        for action, vessel_id, _, position, arrival in state.legal_choices:
            est = b1_release_estimate(view, vessel_id, position)
            scored.append(((est["release_min"], arrival, vessel_id, position), action, vessel_id, position, est))
        key, action, vessel_id, position, est = min(scored, key=lambda s: s[0])
        self.records.append({
            "decision_id": view.decision_id, "time_min": view.time_min, "p03_action": action,
            "action_type": "ASSIGN", "vessel_id": vessel_id, "berth_position_m": position,
            "legal_assignments": len(state.legal_choices), "wait_legal": state.wait_legal,
            "candidates": [{"action": a, "vessel_id": v, "position": x, "release_min": e["release_min"],
                            "cranes": e["cranes"], "crane_delay_min": e["crane_delay_min"]}
                           for (_, a, v, x, e) in scored],
            "chosen_rationale": est, "view_digest": view.digest, "view_schema": view.schema,
            "tie_break": "(estimated release, arrival, vessel_id, position)",
            "adapter_seconds": 0.0, "policy_seconds": time.perf_counter() - t0, "timeout": False,
            "forecast_epoch_mode": state.forecast_epoch_mode, "revealed_vessels": len(state.slot_ids),
            "announced_vessels": sum(s == "ANNOUNCED" for s in state.statuses_by_slot),
            "occupying_vessels": len(state.forecasts),
            "forecast_substituted_vessels": sum(f.mode == "FORECAST" for f in state.forecasts)})
        return BerthAction.assign(self.policy_id, vessel_id, position, decision_id=view.decision_id)

    def describe(self) -> dict[str, Any]:
        return {"arm_id": self.arm_id, "policy_id": self.policy_id, "estimator": B1_ESTIMATOR,
                "factor_labels": FACTOR_LABELS["B1"],
                "information_contract": "CoordinationView without projection (spec 10: current crane, transport, "
                                        "yard state and visible manifests; no hidden or future data)"}


# ------------------------------------------------------------------------------------------------ B2/B2-T

@dataclass(frozen=True)
class LeafPrediction:
    action: int                    # action index at the branching decision (outer, or inner for WAIT branches)
    vessel_id: str | None
    position: float | None
    status: str                    # inner episode end: COMPLETED / TRUNCATED_DRAIN_LIMIT / DEADLOCK
    predicted_unfulfilled_outbound: int
    predicted_turnaround_min: float
    censored_vessels: int
    inner_end_min: float
    inner_cycles: int


@dataclass(frozen=True)
class CandidatePrediction:
    action: int                    # 0 = WAIT
    kind: str                      # WAIT | ASSIGN
    vessel_id: str | None
    position: float | None
    leaf: LeafPrediction | None            # ASSIGN
    wait_branches: tuple[LeafPrediction, ...]   # WAIT: assignments at the next revealed decision
    wait_terminal: LeafPrediction | None        # WAIT with no further berth decision


@dataclass(frozen=True)
class EvaluationRecord:
    evaluator_version: str
    decision_id: str
    time_min: float
    view_digest: str
    projection_digest: str
    cohort: tuple[str, ...]
    known_outbound_obligations: int
    candidates: tuple[CandidatePrediction, ...]
    budget_fingerprint: str
    prediction_digest: str
    timing: dict


def budget_fingerprint(cycle_guard: int, yard_policy_id: str) -> str:
    spec = {"evaluator": EVALUATOR_VERSION, "candidates": "all legal assignments + WAIT if legal (protocol 3 B2)",
            "horizon": "visible cohort to completion (inner drain limit = last visible arrival + extension)",
            "wait_semantics": "Project 03 finish_after_wait (next revealed decision, all legal assignments)",
            "continuation": dict(CONTINUATION, yard=yard_policy_id), "forecast": FORECAST_ASSUMPTIONS,
            "replications": 1, "engineering_cycle_guard_per_leaf": cycle_guard}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()


class SharedRolloutEvaluator:
    """One evaluator for B2 and B2-T (AM-08): every candidate is simulated exactly once."""

    def __init__(self, yard_policy_id: str, *, cycle_guard: int = DEFAULT_INNER_CYCLE_GUARD) -> None:
        from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
        from integrated_terminal_pilot.simulator.drivers import FcfsBerthIntegrationDriver

        self.yard_policy_id = yard_policy_id
        self.cycle_guard = cycle_guard
        self._berth = FcfsBerthIntegrationDriver()
        self._crane = GreedyBerthOrderCranePolicy()
        self._yard = create_policy(yard_policy_id)
        self.fingerprint = budget_fingerprint(cycle_guard, yard_policy_id)

    # -- inner simulation helpers (private kernels only) ------------------------------------
    def _continue(self, kernel) -> str:
        from integrated_terminal_pilot.simulator.drivers import run_episode

        start = kernel.state.cycles
        run = run_episode(kernel, berth_policy=self._berth, crane_policy=self._crane, yard_policy=self._yard,
                          max_cycles=start + self.cycle_guard)
        if isinstance(run.end, Paused):
            raise B2EvaluationError("G6-12", f"inner rollout exceeded the engineering guard of {self.cycle_guard} "
                                             "cycles (INCOMPLETE_ENGINEERING_PROBE)")
        if run.rejections or (run.failure and run.end.status == "FAILED"):
            raise B2EvaluationError("G6-15", f"inner rollout failed: {run.failure or run.rejections}")
        return run.end.status

    def _leaf(self, kernel, start_cycles: int, action: int, vessel_id, position, status: str, cohort, arrivals,
              obligations, t_end: float) -> LeafPrediction:
        s = kernel.state
        turnaround = 0.0
        censored = 0
        for vid in cohort:
            departure = s.vessels[vid].departure_time_min
            if departure is None:
                censored += 1
                departure = t_end
            turnaround += min(departure, t_end) - arrivals[vid]
        unfulfilled = sum(1 for i in obligations if s.c_status[i] not in UNFULFILLED_STATUSES_EXCLUDED)
        return LeafPrediction(action, vessel_id, position, status, unfulfilled, turnaround, censored,
                              min(s.now_min, t_end), s.cycles - start_cycles)

    def _advance_to_next_berth_decision(self, kernel):
        while True:
            request = kernel.advance()
            if isinstance(request, EpisodeEnd):
                return request
            if isinstance(request, Paused):  # pragma: no cover - advance() without limits never pauses
                raise B2EvaluationError("G6-12", "unexpected pause")
            if request.kind == "BERTH":
                return request
            if request.kind == "CRANE":
                kernel.apply_crane_action(self._crane.decide(kernel.crane_observation()))
            else:
                kernel.apply_yard_action(self._yard.decide(kernel.yard_observation()))

    def evaluate(self, view, *, reverse_order: bool = False) -> EvaluationRecord:
        """Simulate every candidate once. ``reverse_order`` (probe/test only) proves order invariance:
        records are always stored in action order, so the prediction digest must not change."""
        view = require_view(view, need_projection=True)
        t0 = time.perf_counter()
        state = adapt_berth_view(view.berth, candidate_capacity=NON_PPO_CANDIDATE_CAPACITY)
        projection = view.projection
        catalog = projection.catalog
        cohort = tuple(v.vessel_id for v in view.berth.vessels if v.status != "DEPARTED")
        arrivals = {v.vessel_id: v.arrival_time_min for v in view.berth.vessels}
        cohort_set = set(cohort)
        obligations = tuple(c.index for c in catalog.containers if c.destination_vessel_id in cohort_set)
        t_end = catalog.drain_limit_min
        actions = ([(0, None, None)] if state.wait_legal else []) + [
            (a, v, x) for a, v, _, x, _ in state.legal_choices]
        candidates, leaf_seconds = [], []
        fork_seconds = 0.0
        for action, vessel_id, position in (list(reversed(actions)) if reverse_order else actions):
            f0 = time.perf_counter()
            kernel = projection.fork()
            fork_seconds += time.perf_counter() - f0
            if kernel.state.pending is None or kernel.state.pending.decision_id != view.decision_id:
                raise B2EvaluationError("G6-15", "projection is not at the view's berth decision")
            start = kernel.state.cycles
            l0 = time.perf_counter()
            if action == 0:
                kernel.apply_berth_action(BerthAction.wait("b2_inner", decision_id=view.decision_id))
                request = self._advance_to_next_berth_decision(kernel)
                if isinstance(request, EpisodeEnd):
                    terminal = self._leaf(kernel, start, 0, None, None, request.status, cohort, arrivals,
                                          obligations, t_end)
                    candidates.append(CandidatePrediction(0, "WAIT", None, None, None, (), terminal))
                else:
                    inner = adapt_berth_view(kernel.berth_view(), candidate_capacity=NON_PPO_CANDIDATE_CAPACITY)
                    branches = []
                    for sub_action, sub_vessel, _, sub_position, _ in inner.legal_choices:
                        branch = kernel.clone()   # private copy of an already sanitised projection fork
                        branch.apply_berth_action(BerthAction.assign("b2_inner", sub_vessel, sub_position,
                                                                     decision_id=inner.decision_id))
                        status = self._continue(branch)
                        branches.append(self._leaf(branch, start, sub_action, sub_vessel, sub_position, status,
                                                   cohort, arrivals, obligations, t_end))
                    candidates.append(CandidatePrediction(0, "WAIT", None, None, None, tuple(branches), None))
            else:
                kernel.apply_berth_action(BerthAction.assign("b2_inner", vessel_id, position,
                                                             decision_id=view.decision_id))
                status = self._continue(kernel)
                candidates.append(CandidatePrediction(action, "ASSIGN", vessel_id, position,
                                                      self._leaf(kernel, start, action, vessel_id, position, status,
                                                                 cohort, arrivals, obligations, t_end), (), None))
            leaf_seconds.append(time.perf_counter() - l0)
        candidates.sort(key=lambda c: c.action)
        predictions = [asdict(c) for c in candidates]
        digest = hashlib.sha256(json.dumps(predictions, sort_keys=True).encode()).hexdigest()
        return EvaluationRecord(
            EVALUATOR_VERSION, view.decision_id, view.time_min, view.digest, projection.digest, cohort,
            len(obligations), tuple(candidates), self.fingerprint, digest,
            {"total_seconds": time.perf_counter() - t0, "fork_seconds": fork_seconds,
             "projection_build_seconds": projection.creation_seconds, "candidate_seconds": leaf_seconds,
             "projection_bytes": len(projection.state_bytes)})


def _leaf_keys(selector: str):
    if selector == "B2":
        return lambda leaf: (leaf.predicted_unfulfilled_outbound, leaf.predicted_turnaround_min)
    if selector == "B2-T":
        return lambda leaf: (leaf.predicted_turnaround_min,)
    raise ValueError(f"unknown selector {selector!r}")


def effective_leaf(candidate: CandidatePrediction, selector: str) -> LeafPrediction:
    """The prediction a selector uses for a candidate (WAIT: best next-decision branch under its own key)."""
    if candidate.kind == "ASSIGN":
        return candidate.leaf
    if candidate.wait_terminal is not None:
        return candidate.wait_terminal
    if not candidate.wait_branches:
        raise B2EvaluationError("G6-15", "WAIT candidate without any evaluated branch")
    key = _leaf_keys(selector)
    return min(candidate.wait_branches, key=lambda leaf: key(leaf) + (leaf.action,))


def select(record: EvaluationRecord, selector: str) -> CandidatePrediction:
    """Pure selector: B2 = (U, turnaround, action); B2-T = (turnaround, action). No other input."""
    key = _leaf_keys(selector)
    return min(record.candidates, key=lambda c: key(effective_leaf(c, selector)) + (c.action,))


def pivotal_diagnostic(record: EvaluationRecord) -> dict[str, Any]:
    """Safeguard S4: B2 vs B2-T choice on identical predictions."""
    b2, b2t = select(record, "B2"), select(record, "B2-T")
    l2, lt = effective_leaf(b2, "B2"), effective_leaf(b2t, "B2-T")
    pivotal = b2.action != b2t.action
    return {"b2_action": b2.action, "b2t_action": b2t.action, "choices_differ": pivotal,
            "cargo_pivotal": pivotal,
            "b2_choice_predicted": {"unfulfilled": l2.predicted_unfulfilled_outbound,
                                    "turnaround_min": l2.predicted_turnaround_min},
            "b2t_choice_predicted": {"unfulfilled": lt.predicted_unfulfilled_outbound,
                                     "turnaround_min": lt.predicted_turnaround_min},
            "predicted_cargo_advantage": lt.predicted_unfulfilled_outbound - l2.predicted_unfulfilled_outbound,
            "predicted_turnaround_sacrifice_min": l2.predicted_turnaround_min - lt.predicted_turnaround_min,
            "one_container_pivotal": pivotal and (lt.predicted_unfulfilled_outbound
                                                  - l2.predicted_unfulfilled_outbound) == 1,
            "legal_candidates": len(record.candidates), "visible_cohort": len(record.cohort),
            "uncertainty": FORECAST_ASSUMPTIONS["uncertainty"]}


class IntegratedRolloutPolicy:
    """B2 (cargo-first) or B2-T (turnaround-only): one shared evaluator, one pure selector."""

    observation = "coordination_view_with_projection"

    def __init__(self, selector: str, yard_policy_id: str, *, cycle_guard: int = DEFAULT_INNER_CYCLE_GUARD):
        if selector not in ("B2", "B2-T"):
            raise ValueError("selector must be B2 or B2-T")
        self.selector = selector
        self.arm_id = selector
        self.policy_id = ("b2_integrated_cargo_first_rollout_v1" if selector == "B2"
                          else "b2t_integrated_turnaround_rollout_v1")
        self.evaluator = SharedRolloutEvaluator(yard_policy_id, cycle_guard=cycle_guard)
        self.records: list[dict[str, Any]] = []

    def decide(self, view) -> BerthAction:
        t0 = time.perf_counter()
        record = self.evaluator.evaluate(view)
        chosen = select(record, self.selector)
        diagnostic = pivotal_diagnostic(record)
        policy_seconds = time.perf_counter() - t0
        self.records.append({
            "decision_id": view.decision_id, "time_min": view.time_min, "p03_action": chosen.action,
            "action_type": chosen.kind, "vessel_id": chosen.vessel_id, "berth_position_m": chosen.position,
            "legal_assignments": sum(c.kind == "ASSIGN" for c in record.candidates),
            "wait_legal": any(c.kind == "WAIT" for c in record.candidates),
            "evaluation": asdict(record), "pivotal": diagnostic, "selector": self.selector,
            "adapter_seconds": 0.0, "policy_seconds": policy_seconds, "timeout": False,
            "forecast_epoch_mode": "n/a", "revealed_vessels": len(view.berth.vessels),
            "announced_vessels": sum(v.status == "ANNOUNCED" for v in view.berth.vessels),
            "occupying_vessels": sum(v.status == "OCCUPYING" for v in view.berth.vessels),
            "forecast_substituted_vessels": 0})
        if chosen.kind == "WAIT":
            return BerthAction.wait(self.policy_id, decision_id=view.decision_id)
        return BerthAction.assign(self.policy_id, chosen.vessel_id, chosen.position, decision_id=view.decision_id)

    def describe(self) -> dict[str, Any]:
        return {"arm_id": self.arm_id, "policy_id": self.policy_id, "selector": self.selector,
                "evaluator_version": EVALUATOR_VERSION, "budget_fingerprint": self.evaluator.fingerprint,
                "factor_labels": FACTOR_LABELS[self.arm_id], "forecast": FORECAST_ASSUMPTIONS,
                "continuation": CONTINUATION, "engineering_cycle_guard_per_leaf": self.evaluator.cycle_guard}


FACTOR_LABELS = {
    "A1": {"information_level": "berth_only", "forward_model_fidelity": "none", "objective": "fcfs_rule",
           "search_budget_id": "none"},
    "A1n": {"information_level": "berth_only", "forward_model_fidelity": "nominal_one_step_estimate",
            "objective": "min_estimated_release", "search_budget_id": "none"},
    "B1": {"information_level": "integrated_current_state", "forward_model_fidelity": "integrated_one_step_estimate",
           "objective": "min_estimated_release", "search_budget_id": "none"},
    "A2": {"information_level": "berth_only", "forward_model_fidelity": "nominal_berth_rollout",
           "objective": "visible_cohort_waiting (monotone in turnaround)", "search_budget_id": "p03_full_visible_cohort"},
    "B2": {"information_level": "integrated_current_state", "forward_model_fidelity": "integrated_kernel_rollout",
           "objective": "lexicographic(predicted_unfulfilled_outbound, predicted_turnaround)",
           "search_budget_id": "protocol5_full_visible_cohort"},
    "B2-T": {"information_level": "integrated_current_state", "forward_model_fidelity": "integrated_kernel_rollout",
             "objective": "predicted_turnaround", "search_budget_id": "protocol5_full_visible_cohort"},
}


__all__ = ["A1nNominalGreedyPolicy", "B1IntegratedGreedyPolicy", "B1_ESTIMATOR", "B2EvaluationError",
           "CandidatePrediction", "EVALUATOR_VERSION", "EvaluationRecord", "FACTOR_LABELS", "IntegratedRolloutPolicy",
           "LeafPrediction", "SharedRolloutEvaluator", "b1_release_estimate", "effective_leaf", "pivotal_diagnostic",
           "select"]
