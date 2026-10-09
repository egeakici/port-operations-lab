"""P_c: primitive greedy crane allocation by berth order (protocol §3, FROZEN).

    At each CRANE decision, berthed vessels with remaining work are visited in
    (berth_start_time_min, vessel_id) order. Each receives available cranes in
    crane_id order up to max_cranes.

Lifted from Project 02 ``GreedyCranePolicy`` (one crane per READY task, cranes
in ``crane_id`` order, capped by ``max_cranes`` minus the vessel's current
cranes) from tasks to vessels. Generalisations (docs/step3_primitive_policies.md):

* no cap by the number of READY tasks: Project I cranes are assigned to the
  vessel, and the kernel's dispatch rule D16 chooses batches;
* crane eligibility also honours ``compatible_vessel_ids`` (Project 02 has none);
* several vessels are decided in one call; cranes claimed by an earlier vessel
  are skipped, as when Project 02's dispatcher applies each vessel's result
  before querying the next vessel.

The policy reads only its observation, returns a declarative action, and never
releases cranes.
"""

from __future__ import annotations

from integrated_terminal_pilot.policies.actions import CraneAction, CraneAssignment
from integrated_terminal_pilot.policies.observations import CraneObservation, ObservationError


class GreedyBerthOrderCranePolicy:
    """P_c."""

    policy_id = "primitive_crane_greedy_v1"
    protocol_name = "P_c"
    version = 1

    def decide(self, observation: CraneObservation) -> CraneAction:
        if not isinstance(observation, CraneObservation):
            raise ObservationError("P_c requires a CraneObservation.")
        candidates = [v for v in observation.vessels if v.crane_eligible]
        if not candidates:
            served = [v for v in observation.vessels
                      if v.phase in ("BERTHING_PREP", "HANDLING") and v.remaining_moves > 0]
            return self._no_action(observation, "MAX_CRANES_REACHED" if served else "NO_ELIGIBLE_VESSEL")
        free = [c for c in observation.cranes if c.status == "available"]  # canonical crane_id order
        if not free:
            return self._no_action(observation, "NO_AVAILABLE_CRANE")
        claimed: set[str] = set()
        assignments = []
        for vessel in sorted(candidates, key=lambda v: (v.berth_start_time_min, v.vessel_id)):
            chosen = [c.crane_id for c in free
                      if c.crane_id not in claimed and c.can_serve(vessel.vessel_id)]
            chosen = chosen[:vessel.spare_crane_capacity]
            if chosen:
                claimed.update(chosen)
                assignments.append(CraneAssignment(vessel.vessel_id, tuple(chosen)))
        if not assignments:
            return self._no_action(observation, "NO_COMPATIBLE_CRANE")
        return CraneAction(policy_id=self.policy_id, time_min=observation.time_min,
                           action_type="ASSIGN_CRANES", assignments=tuple(assignments),
                           decision_id=observation.decision_id)

    def _no_action(self, observation: CraneObservation, reason: str) -> CraneAction:
        return CraneAction(policy_id=self.policy_id, time_min=observation.time_min,
                           action_type="NO_ACTION", no_action_reason=reason,
                           decision_id=observation.decision_id)


__all__ = ["GreedyBerthOrderCranePolicy"]
