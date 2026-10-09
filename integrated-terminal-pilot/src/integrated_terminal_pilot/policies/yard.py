"""Yard destination policies: P_y (first fit, FROZEN) and a diagnostic balancing heuristic.

P_y (protocol §3): the first OPEN block in ``block_id`` order that supports the
batch's capabilities and size and passes the TEU test. This is Project 02
``FirstFitYardPolicy``. The TEU test is the reservation test of the
integration specification §5.3::

    capacity_teu - occupied_teu - reserved_teu - blocked_teu >= batch_teu

Both policies choose a storage-compatible block for the whole batch or return
a no-op. Batches are never split (one destination block per batch, spec §6).
Handling capacity (moves/h) is not a storage admission criterion; queuing and
blocking on it are Step 4 physics. Nothing is reserved, moved or placed below
block level (G0).
"""

from __future__ import annotations

from integrated_terminal_pilot.policies.actions import YardAction
from integrated_terminal_pilot.policies.observations import (
    TOL, ObservationError, YardBlockView, YardObservation,
)


def eligible_blocks(observation: YardObservation) -> tuple[tuple[YardBlockView, ...], str | None]:
    """Blocks passing every P_y test, in block_id order, plus the reason if none does.

    Filters apply in a fixed order; the reason names the first filter that
    leaves no block.
    """
    request = observation.request
    blocks = [b for b in observation.blocks if b.status == "open"]
    if not blocks:
        return (), "NO_OPEN_BLOCK"
    blocks = [b for b in blocks if request.container_size in b.allowed_sizes]
    if not blocks:
        return (), "NO_SIZE_COMPATIBLE_BLOCK"
    required = set(request.required_capabilities)
    blocks = [b for b in blocks if required <= set(b.capabilities)]
    if not blocks:
        return (), "NO_CAPABLE_BLOCK"
    blocks = [b for b in blocks if b.available_teu + TOL >= request.required_teu]
    if not blocks:
        return (), "INSUFFICIENT_CAPACITY"
    return tuple(blocks), None


class _YardPolicyBase:
    policy_id = ""

    def _action(self, observation: YardObservation, block_id: str | None,
                reason: str | None) -> YardAction:
        request = observation.request
        return YardAction(policy_id=self.policy_id, time_min=observation.time_min,
                          work_order_id=request.work_order_id,
                          action_type="ALLOCATE_BLOCK" if block_id else "NO_ACTION",
                          container_ids=request.container_ids, required_teu=request.required_teu,
                          block_id=block_id, no_action_reason=reason,
                          decision_id=observation.decision_id)

    def _candidates(self, observation: YardObservation):
        if not isinstance(observation, YardObservation):
            raise ObservationError(f"{self.policy_id} requires a YardObservation.")
        return eligible_blocks(observation)


class FirstFitYardPolicy(_YardPolicyBase):
    """P_y: the experimental default yard policy of every arm."""

    policy_id = "yard_first_fit_v1"
    protocol_name = "P_y"
    version = 1

    def decide(self, observation: YardObservation) -> YardAction:
        blocks, reason = self._candidates(observation)
        return self._action(observation, blocks[0].block_id if blocks else None, reason)


class OccupancyBalancingYardPolicy(_YardPolicyBase):
    """Diagnostic yard-only heuristic; NOT P_y and not used by any protocol arm.

    Among the blocks eligible under P_y, choose the lowest
    ``(occupied_teu + reserved_teu + required_teu) / capacity_teu``; ties by block_id.
    """

    policy_id = "yard_occupancy_balance_v1"
    protocol_name = None
    version = 1

    def decide(self, observation: YardObservation) -> YardAction:
        blocks, reason = self._candidates(observation)
        if not blocks:
            return self._action(observation, None, reason)
        required = observation.request.required_teu
        best = min(blocks, key=lambda b: ((b.occupied_teu + b.reserved_teu + required) / b.capacity_teu,
                                          b.block_id))
        return self._action(observation, best.block_id, None)


__all__ = ["FirstFitYardPolicy", "OccupancyBalancingYardPolicy", "eligible_blocks"]
