"""Versioned diagnostic forward-model intervention. NEVER used on the outer kernel.

The crane-off model supplies dedicated virtual capacity for each visible vessel,
120 moves/hour divided across its currently active batches. It retains cargo
availability, D15/D17 and berth geometry; it is not the Project03 nominal world.
"""
from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import pickle
from integrated_terminal_pilot.simulator.catalog import CraneRecord
from integrated_terminal_pilot.simulator.state import CraneState
from integrated_terminal_pilot.simulator.kernel import TerminalKernel
from integrated_terminal_pilot.benchmark.coordination_view import SafeProjection, require_view
from integrated_terminal_pilot.benchmark.coordination_policies import SharedRolloutEvaluator
from statistical import ContractError

VERSION = 'step8_model_coupling_v1'
SWITCHES = {'none': (False,False,False), 'crane-aware': (True,False,False),
            'yard-aware': (False,True,True), 'both': (True,True,True)}


class NominalCapacityKernel(TerminalKernel):
    """Private sanitized fork only. Clone retains intervention on WAIT branches."""
    def clone(self):
        if self._group is not None:
            raise ContractError('Cannot clone inside timestamp processing')
        return type(self)(self.catalog, self.state.clone(), invariant_mode='off')

    def _recompute_rates(self):
        counts = Counter(wo.vessel_id for wo in self._ship_work_orders())
        cranes = []
        for c in self.catalog.cranes:
            assigned = self.state.cranes[c.crane_id].assigned_vessel_id
            rate = 120. / max(1, counts[assigned])
            cranes.append(replace(c, nominal_moves_per_hour=rate))
        self.catalog = replace(self.catalog, cranes=tuple(cranes), crane_by_id={c.crane_id:c for c in cranes})
        super()._recompute_rates()


def transform_fork(kernel, variant):
    if variant not in SWITCHES:
        raise ContractError('Unknown model coupling variant')
    if not kernel.catalog.observable or kernel.catalog.identity is not None:
        raise ContractError('Model adapter accepts sanitized observable forks ONLY')
    crane_on, transport_on, yard_on = SWITCHES[variant]
    if variant == 'both':
        return kernel
    cat = kernel.catalog
    physics = replace(cat.physics, transport_enabled=transport_on, yard_constraints_enabled=yard_on)
    if not crane_on:
        if physics.service_minutes_per_move != .5:
            raise ContractError('Nominal crane-off contract requires .5 min/move')
        physics = replace(physics, efficiency_one=1., efficiency_two=1., efficiency_three=1., efficiency_four_plus=1.)
        cranes = []
        # Existing occupied cranes keep their work orders. Idle real cranes cannot
        # compete with dedicated per-visible-vessel virtual capacity.
        for c in cat.cranes:
            owner = kernel.state.cranes[c.crane_id].assigned_vessel_id
            cranes.append(replace(c, compatible_vessel_ids=() if owner is None else (owner,)))
        for vessel in cat.vessels:
            for index in range(vessel.max_cranes):
                cid = f'QC{len(cranes)+1:02d}'
                if cid in kernel.state.cranes:
                    raise ContractError('Virtual crane ID collision')
                record = dict(cat.cranes[0].record, crane_id=cid, nominal_moves_per_hour=120.,
                              compatible_vessel_ids=[vessel.vessel_id], unavailability_windows=[])
                cranes.append(CraneRecord(cid,120.,(vessel.vessel_id,),record))
                kernel.state.cranes[cid] = CraneState(cid)
        cat = replace(cat, cranes=tuple(cranes), crane_by_id={c.crane_id:c for c in cranes})
    cat = replace(cat, physics=physics)
    cls = TerminalKernel if crane_on else NominalCapacityKernel
    fork = cls(cat, kernel.state, invariant_mode='off')
    fork._recompute_rates()  # Reschedule active completions at the settled decision time.
    return fork


@dataclass(frozen=True)
class CouplingProjection(SafeProjection):
    variant: str = 'both'

    def fork(self):
        return transform_fork(super().fork(), self.variant)


def transformed_view(view, variant):
    require_view(view, need_projection=True)
    if variant not in SWITCHES:
        raise ContractError('Unknown coupling variant')
    if variant == 'both':
        return view
    p = view.projection
    digest = hashlib.sha256((p.digest+VERSION+variant).encode()).hexdigest()
    projection = CouplingProjection(p.schema,p.catalog,p.state_bytes,digest,p.assumptions,p.creation_seconds,variant)
    return replace(view, projection=projection, digest=hashlib.sha256((view.digest+digest).encode()).hexdigest())


class CouplingEvaluator(SharedRolloutEvaluator):
    def __init__(self, yard_policy_id, variant):
        super().__init__(yard_policy_id)
        if variant not in SWITCHES:
            raise ContractError('Unknown coupling variant')
        self.variant = variant
        if variant != 'both':
            self.fingerprint = hashlib.sha256((self.fingerprint+VERSION+variant).encode()).hexdigest()

    def evaluate(self, view, *, reverse_order=False):
        before = pickle.dumps(view.projection.catalog), view.projection.state_bytes
        result = super().evaluate(transformed_view(view,self.variant), reverse_order=reverse_order)
        if before != (pickle.dumps(view.projection.catalog),view.projection.state_bytes):
            raise ContractError('Shared projection mutation')
        return result
