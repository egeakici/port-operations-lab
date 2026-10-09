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


# role: "primitive" = the protocol §3 component used identically in every arm;
#       "diagnostic" = yard-only alternative, never an experimental default.
POLICY_REGISTRY: dict[str, dict[str, object]] = {
    GreedyBerthOrderCranePolicy.policy_id: {"factory": GreedyBerthOrderCranePolicy, "domain": "crane",
                                            "protocol_name": "P_c", "role": "primitive"},
    FirstFitYardPolicy.policy_id: {"factory": FirstFitYardPolicy, "domain": "yard",
                                   "protocol_name": "P_y", "role": "primitive"},
    OccupancyBalancingYardPolicy.policy_id: {"factory": OccupancyBalancingYardPolicy, "domain": "yard",
                                             "protocol_name": None, "role": "diagnostic"},
}
DEFAULT_CRANE_POLICY_ID = GreedyBerthOrderCranePolicy.policy_id
DEFAULT_YARD_POLICY_ID = FirstFitYardPolicy.policy_id


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
           "YardPolicy", "create_policy", "policy_ids"]
