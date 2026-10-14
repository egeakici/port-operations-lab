"""Diagnostic reference comparison. Never used by an experimental policy."""
from dataclasses import asdict
import copy
import hashlib
import json
import math

from integrated_terminal_pilot.benchmark.adapter import adapt_berth_view, visible_state
from integrated_terminal_pilot.benchmark.coordination_policies import SharedRolloutEvaluator, effective_leaf, select
from integrated_terminal_pilot.benchmark.coordination_view import build_coordination_view
from integrated_terminal_pilot.benchmark.policies import OnlineRolloutBerthPolicy
from integrated_terminal_pilot.policies import GreedyBerthOrderCranePolicy, create_policy
from integrated_terminal_pilot.simulator.kernel import DecisionRequest, TerminalKernel
from integrated_terminal_pilot.simulator.validator import BerthAction

YARD = 'yard_occupancy_balance_v1'


def applicability(kernel, declared_mismatches=()):
    """Conservative sufficient predicate; absence of proof is not exact eligibility."""
    p, s, cat = kernel.catalog.physics, kernel.state, kernel.catalog
    reasons = list(declared_mismatches)
    if p.transport_enabled or p.yard_constraints_enabled:
        reasons.append('position/resource dependent service not excluded')
    if any(v.max_cranes != 1 for v in cat.vessels) or len(cat.cranes) < len(cat.vessels):
        reasons.append('exclusive fixed-rate crane capacity not established')
    if any(c.nominal_moves_per_hour != 120 or c.compatible_vessel_ids is not None for c in cat.cranes):
        reasons.append('nominal/physical service mismatch')
    if (p.berthing_preparation_min, p.departure_preparation_min, p.efficiency_one, p.productivity_factor) != (30, 20, 1, 1):
        reasons.append('fixed service coefficients differ')
    if any(v.visibility == 'HIDDEN' for v in s.vessels.values()):
        reasons.append('full-episode visibility not established')
    if any(s.c_status[c.index] not in ('IN_YARD', 'LOADING', 'LOADED', 'DEPARTED_BY_VESSEL')
           for c in cat.containers if c.destination_vessel_id):
        reasons.append('outbound cargo not ready')
    # Serial service plus one WAIT to the latest arrival/release bounds these small fixtures.
    upper = max([s.now_min] + [v.arrival_time_min for v in cat.vessels]) + 2 * sum(
        v.nominal_service_time_min for v in cat.vessels)
    if upper >= cat.drain_limit_min:
        reasons.append('uncensored completion not guaranteed')
    if any(abs(kernel.forecast_release(v.vessel_id) -
               (v.berth_start_time_min + cat.vessel_by_id[v.vessel_id].nominal_service_time_min)) > 1e-9
           for v in s.vessels.values() if v.phase in ('BERTHING_PREP', 'HANDLING', 'DEPARTURE_PREP')):
        reasons.append('occupying forecast differs from fixed service')
    return {'label': 'NOT_EXACT_ELIGIBLE' if reasons else 'EXACT_ELIGIBLE', 'reasons': sorted(set(reasons))}


def next_berth(kernel):
    crane, yard = GreedyBerthOrderCranePolicy(), create_policy(YARD)
    while True:
        request = kernel.advance()
        if not isinstance(request, DecisionRequest) or request.kind == 'BERTH':
            return request
        if request.kind == 'CRANE':
            kernel.apply_crane_action(crane.decide(kernel.crane_observation()))
        else:
            kernel.apply_yard_action(yard.decide(kernel.yard_observation()))


def compare_state(kernel, reasons=()):
    from berth_allocation_lab.policies.dynamic_online_rollout import online_rollout_choice, _VisibleContinuation
    eligibility = applicability(kernel, reasons)  # evaluated BEFORE candidate scores
    view = build_coordination_view(kernel, include_projection=True)
    adapted = adapt_berth_view(view.berth, candidate_capacity=48)
    visible = visible_state(adapted)
    reference = online_rollout_choice(visible)  # authentic, read-only P03 reference
    a2 = OnlineRolloutBerthPolicy()
    a2.decide(view.berth)
    integrated = SharedRolloutEvaluator(YARD).evaluate(view)  # separate physical implementation
    p03 = dict(reference.scores)
    constant = 0.0
    for v in view.berth.vessels:
        if v.status in ('WAITING', 'ANNOUNCED'):
            constant += v.nominal_service_time_min + max(view.time_min - v.arrival_time_min, 0)
        elif v.status == 'OCCUPYING':
            constant += v.estimated_release_time_min - v.arrival_time_min
    table = []
    for candidate in integrated.candidates:
        leaf = effective_leaf(candidate, 'B2-T')
        table.append({'action': candidate.action, 'kind': candidate.kind,
                      'p03_future_wait': p03[candidate.action],
                      'b2t_turnaround': leaf.predicted_turnaround_min,
                      'constant_residual': leaf.predicted_turnaround_min - p03[candidate.action] - constant,
                      'prediction': asdict(candidate)})
    # Inspect P03 WAIT branches independently; no reference evidence flows into B2.
    branches = []
    if visible.wait_legal:
        cont = _VisibleContinuation(visible)
        cont.advance()
        while True:
            choices = [(v, x) for v, status in cont.status.items() if status == 'WAITING'
                       for x in cont._positions(v)]
            if choices:
                break
            cont.advance()
        for vid, x in choices:
            branch = copy.deepcopy(cont)
            branch.assign(vid, x)
            branches.append({'vessel_id': vid, 'position': x, 'time_min': cont.time,
                             'future_wait': branch.finish_with_fcfs()})
    wait = next((c for c in integrated.candidates if c.kind == 'WAIT'), None)
    branch_ok = True
    wait_time = None
    wait_epoch_ok = True
    if wait:
        physical = view.projection.fork()
        physical.apply_berth_action(BerthAction.wait('closure_diagnostic', decision_id=view.decision_id))
        request = next_berth(physical)
        if isinstance(request, DecisionRequest):
            wait_time = request.time_min
            wait_epoch_ok = wait_time == cont.time
        else:
            wait_epoch_ok = False
        by_key = {(b.vessel_id, b.position): b for b in wait.wait_branches}
        branch_ok = set(by_key) == {(b['vessel_id'], b['position']) for b in branches}
        branch_ok &= all(math.isclose(by_key[(b['vessel_id'], b['position'])].predicted_turnaround_min,
                                     b['future_wait'] + constant, abs_tol=1e-8)
                         for b in branches if (b['vessel_id'], b['position']) in by_key)
    p_order = [a for a, score in sorted(reference.scores, key=lambda x: (x[1], x[0]))]
    b_order = [c.action for c in sorted(integrated.candidates,
              key=lambda c: (effective_leaf(c, 'B2-T').predicted_turnaround_min, c.action))]
    checks = {'candidates': [a for a, _ in reference.scores] == [c.action for c in integrated.candidates],
              'a2_authentic_reference': a2.records[-1]['p03_action'] == reference.action,
              'constant': all(abs(r['constant_residual']) < 1e-8 for r in table),
              'full_preference_order': p_order == b_order,
              'selected_action': reference.action == select(integrated, 'B2-T').action,
              'wait_subbranches': branch_ok, 'wait_next_epoch': wait_epoch_ok}
    return {'eligibility': eligibility, 'time_min': view.time_min, 'decision_id': view.decision_id,
            'cohort': integrated.cohort, 'constant': constant, 'table': table,
            'reference_wait_branches': branches, 'physical_wait_next_decision_min': wait_time,
            'p03_order': p_order, 'b2t_order': b_order,
            'checks': checks, 'selected_a2': reference.action, 'selected_b2t': select(integrated, 'B2-T').action,
            'result': ('PASS' if all(checks.values()) else 'CONTRACT_DEFECT')
                      if eligibility['label'] == 'EXACT_ELIGIBLE' else 'NOT_EXACT_ELIGIBLE'}


def run_gate():
    from tests.step6_closure_support import fixtures
    rows = []
    for name, doc, occupied, reasons in fixtures():
        # The unavailable-export control deliberately violates generator cutoff, not kernel physics.
        kernel = TerminalKernel.from_scenario(doc, validate=name != 'export_unavailable', invariant_mode='full')
        next_berth(kernel)
        if occupied:
            choice = kernel.berth_view().legal_choices[0]
            kernel.apply_berth_action(BerthAction.assign('fixture_setup', choice[0], choice[2],
                                                       decision_id=kernel.pending_decision.decision_id))
            next_berth(kernel)
        comparisons = []
        while isinstance(kernel.pending_decision, DecisionRequest):
            row = compare_state(kernel, reasons)
            comparisons.append(row)
            if row['result'] != 'PASS':
                break
            a2 = OnlineRolloutBerthPolicy()
            kernel.apply_berth_action(a2.decide(kernel.berth_view()))
            if not isinstance(next_berth(kernel), DecisionRequest):
                break
        good = all(r['result'] == 'PASS' for r in comparisons)
        rows.append({'fixture_id': name, 'fixture_sha256': hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest(),
                     'scope': 'FULL' if good else ('PREFIX' if len(comparisons) > 1 else 'NOT_EXACT_ELIGIBLE'),
                     'decisions': comparisons, 'first_divergence': next((r for r in comparisons if r['result'] != 'PASS'), None)})
    defects = sum(r['result'] == 'CONTRACT_DEFECT' for f in rows for r in f['decisions'])
    return {'gate': 'CONTRACT_DEFECT' if defects else 'PASS_WITH_SCOPED_CLAIMS',
            'fixtures': rows, 'full': sum(f['scope'] == 'FULL' for f in rows),
            'prefix': sum(f['scope'] == 'PREFIX' for f in rows),
            'noneligible': sum(f['scope'] == 'NOT_EXACT_ELIGIBLE' for f in rows),
            'eligible_decisions': sum(r['eligibility']['label'] == 'EXACT_ELIGIBLE' for f in rows for r in f['decisions']),
            'contract_defects': defects}
