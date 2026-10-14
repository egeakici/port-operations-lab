"""Episode runner and the Step 4 berth *integration fixture*.

``FcfsBerthIntegrationDriver`` is a **physical integration fixture/driver**, used
to exercise berth physics end to end and for the degenerate equivalence test.
It calls Project 03 ``online_fcfs_action`` unchanged on a duck-typed host whose
``legal_choices`` are the kernel's physical legal set. It is NOT the Step 5
production ``BerthViewAdapter``, it is not an experimental berth policy, and it
never WAITs (exactly like Project 03 FCFS).

``run_episode`` alternates ``kernel.advance()`` and policy decisions. A
validator rejection is never repaired and no fallback policy is used: the run is
reported ``FAILED`` with the rejection recorded (protocol §7 "invalid physical
actions", gate G19).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from integrated_terminal_pilot.simulator.errors import KernelError, PhysicalActionRejected
from integrated_terminal_pilot.simulator.kernel import DecisionRequest, EpisodeEnd, Paused
from integrated_terminal_pilot.simulator.validator import BerthAction


class _LegalChoiceHost:
    """Duck-typed stand-in exposing only ``legal_choices`` (what ``online_fcfs_action`` reads)."""

    def __init__(self, legal_choices: tuple) -> None:
        self.legal_choices = legal_choices


class FcfsBerthIntegrationDriver:
    """Integration fixture: Project 03 online FCFS over the kernel's physical legal set."""

    policy_id = "fixture_p03_online_fcfs"
    version = 1
    role = "physical_integration_fixture"

    def decide(self, view) -> BerthAction:
        from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action

        choices = tuple((index, vessel_id, candidate, position, arrival)
                        for index, (vessel_id, candidate, position, arrival)
                        in enumerate(view.legal_choices, start=1))
        action = online_fcfs_action(_LegalChoiceHost(choices))
        _, vessel_id, _, position, _ = next(c for c in choices if c[0] == action)
        return BerthAction.assign(self.policy_id, vessel_id, position, decision_id=view.decision_id)


@dataclass
class EpisodeRun:
    end: Any
    rejections: list = field(default_factory=list)
    failure: str | None = None
    decisions: dict = field(default_factory=lambda: {"BERTH": 0, "CRANE": 0, "YARD": 0})
    decision_seconds: dict = field(default_factory=lambda: {"BERTH": 0.0, "CRANE": 0.0, "YARD": 0.0})
    wall_seconds: float = 0.0
    # Step 5: per berth decision, view build / policy decide / validated apply wall seconds.
    berth_timings: list = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.rejections or self.failure:
            return "FAILED"
        return getattr(self.end, "status", "RUNNING")


def run_episode(kernel, *, berth_policy, crane_policy, yard_policy, until_min: float | None = None,
                max_decisions: int | None = None, max_cycles: int | None = None,
                berth_observer=None) -> EpisodeRun:
    """Drive ``kernel`` with the given policies until it ends, pauses (``until_min`` / ``max_cycles``),
    exceeds ``max_decisions``, or fails.

    ``berth_observer`` (Step 6, optional): a trusted builder ``observer(kernel) -> observation`` used
    instead of ``kernel.berth_view()`` for the berth policy (the B arms' ``CoordinationView``). The
    policy still receives only the observation, never the kernel. Default: unchanged Step 4/5 path.
    """
    run = EpisodeRun(end=None)
    started = time.perf_counter()
    count = 0
    try:
        while True:
            request = kernel.advance(until_min=until_min, max_cycles=max_cycles)
            if isinstance(request, (EpisodeEnd, Paused)):
                run.end = request
                break
            assert isinstance(request, DecisionRequest)
            count += 1
            if max_decisions is not None and count > max_decisions:
                run.failure = f"decision limit {max_decisions} exceeded"
                break
            t0 = time.perf_counter()
            if request.kind == "BERTH":
                view = kernel.berth_view() if berth_observer is None else berth_observer(kernel)
                t1 = time.perf_counter()
                action = berth_policy.decide(view)
                t2 = time.perf_counter()
                kernel.apply_berth_action(action)
                run.berth_timings.append({"view_seconds": t1 - t0, "decide_seconds": t2 - t1,
                                          "apply_seconds": time.perf_counter() - t2})
            elif request.kind == "CRANE":
                kernel.apply_crane_action(crane_policy.decide(kernel.crane_observation()))
            else:
                kernel.apply_yard_action(yard_policy.decide(kernel.yard_observation()))
            run.decisions[request.kind] += 1
            run.decision_seconds[request.kind] += time.perf_counter() - t0
    except PhysicalActionRejected as error:
        run.rejections.append({"decision_kind": error.decision_kind, "rejection_code": error.rejection_code,
                               "message": str(error), "time_min": kernel.current_time_min})
        run.end = EpisodeEnd("FAILED", "PHYSICAL_ACTION_REJECTION", kernel.current_time_min)
    except KernelError as error:
        run.failure = str(error)
        run.end = EpisodeEnd("FAILED", error.code, kernel.current_time_min)
    run.wall_seconds = time.perf_counter() - started
    return run


def default_policies() -> dict[str, Any]:
    """A1 primitives of protocol §3 with the FCFS integration fixture as the berth driver."""
    from integrated_terminal_pilot.policies import FirstFitYardPolicy, GreedyBerthOrderCranePolicy

    return {"berth_policy": FcfsBerthIntegrationDriver(), "crane_policy": GreedyBerthOrderCranePolicy(),
            "yard_policy": FirstFitYardPolicy()}


__all__ = ["EpisodeRun", "FcfsBerthIntegrationDriver", "default_policies", "run_episode"]
