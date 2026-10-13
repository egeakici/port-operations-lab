"""Policy interfaces and the deterministic policy registry.

Interfaces are structural (``typing.Protocol``), so the Step 4 kernel can call
any policy without importing kernel code into this package, and policies need
no Project 01 ``Terminal``, SimPy, Streamlit, GPU or PyTorch.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from integrated_terminal_pilot.policies.actions import CraneAction, YardAction
from integrated_terminal_pilot.policies.crane import GreedyBerthOrderCranePolicy
from integrated_terminal_pilot.policies.observations import CraneObservation, YardObservation
from integrated_terminal_pilot.policies.yard import FirstFitYardPolicy, OccupancyBalancingYardPolicy


@runtime_checkable
class CranePolicy(Protocol):
    policy_id: str
    version: int

    def decide(self, observation: CraneObservation) -> CraneAction: ...


@runtime_checkable
class YardPolicy(Protocol):
    policy_id: str
    version: int

    def decide(self, observation: YardObservation) -> YardAction: ...


# role: "primitive" = the common component used identically in every arm of the primary research
#       profile; "diagnostic_reference" = retained unchanged for diagnostics and historical reproduction.
# AM-01 (approved 2026-10-13, configs/protocol/itp_protocol_control_register_v1.yaml) made the balanced
# rule the common P_y; first fit is the diagnostic reference P_y_ff. Only this metadata changed: both
# algorithms are untouched, and DEFAULT_YARD_POLICY_ID stays first fit so that the historical v1
# four-crane Step 4/5 fixtures and gates reproduce byte for byte (pre-Step 6 brief section 5.6). The
# primary research path selects P_y explicitly through benchmark.profiles.RESEARCH_PROFILES.
POLICY_REGISTRY: dict[str, dict[str, object]] = {
    GreedyBerthOrderCranePolicy.policy_id: {"factory": GreedyBerthOrderCranePolicy, "domain": "crane",
                                            "protocol_name": "P_c", "role": "primitive"},
    FirstFitYardPolicy.policy_id: {"factory": FirstFitYardPolicy, "domain": "yard",
                                   "protocol_name": "P_y_ff", "role": "diagnostic_reference"},
    OccupancyBalancingYardPolicy.policy_id: {"factory": OccupancyBalancingYardPolicy, "domain": "yard",
                                             "protocol_name": "P_y", "role": "primitive"},
}
DEFAULT_CRANE_POLICY_ID = GreedyBerthOrderCranePolicy.policy_id
# Historical v1 reproduction default (Step 4 fixtures, degenerate gates). Not the primary research P_y.
DEFAULT_YARD_POLICY_ID = FirstFitYardPolicy.policy_id
PRIMARY_RESEARCH_YARD_POLICY_ID = OccupancyBalancingYardPolicy.policy_id


def create_policy(policy_id: str):
    """Instantiate a registered policy by id (unknown ids are rejected, never substituted)."""
    try:
        entry = POLICY_REGISTRY[policy_id]
    except KeyError as error:
        raise KeyError(f"Unknown policy id {policy_id!r}; registered: {sorted(POLICY_REGISTRY)}") from error
    return entry["factory"]()


def policy_ids(domain: str | None = None) -> tuple[str, ...]:
    return tuple(sorted(pid for pid, e in POLICY_REGISTRY.items() if domain in (None, e["domain"])))


__all__ = ["CranePolicy", "DEFAULT_CRANE_POLICY_ID", "DEFAULT_YARD_POLICY_ID", "POLICY_REGISTRY",
           "PRIMARY_RESEARCH_YARD_POLICY_ID",
           "YardPolicy", "create_policy", "policy_ids"]
