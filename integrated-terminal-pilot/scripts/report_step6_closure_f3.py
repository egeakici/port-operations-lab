"""Reporter-only F3 diagnostics from immutable, approved development records.

Never runs an outer episode, changes a policy, calibrates a forecast, or reads a
held-out input. All actual future information is confined to this reporter.
"""
from __future__ import annotations

import argparse
import base64
import copy
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import pickle
from pathlib import Path
import time

import numpy as np

from integrated_terminal_pilot.benchmark import step6
from integrated_terminal_pilot.benchmark.adapter import adapt_berth_view, visible_state
from integrated_terminal_pilot.benchmark.runner import resolve_research_profile
from integrated_terminal_pilot.benchmark.step6_closure import (
    ROOT, APPROVAL, digest, file_hash, item_path, load_plan, publish, require_approval, verify_record,
)
from integrated_terminal_pilot.simulator.ledger import (
    L_SEQ, L_TIME, L_TYPE, L_CLASS, L_CONTAINER, L_FROM, L_TO, L_SOURCE, L_DEST,
    L_VESSEL, L_CAUSATION, ledger_sha256,
)
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT
from integrated_terminal_pilot.simulator.events import E_TYPE, E_SEQ

LABEL = 'UNCALIBRATED_SYNTHETIC_FORECAST'


def stats(values):
    if not values:
        return {'n': 0}
    a = np.asarray(values, dtype=float)
    return {'n': len(a), 'mean': float(a.mean()), 'p50': float(np.percentile(a, 50)),
            'p95': float(np.percentile(a, 95)), 'min': float(a.min()), 'max': float(a.max()),
            'mean_absolute': float(np.abs(a).mean())}


def hash_json_lines(rows):
    result = hashlib.sha256()
    for row in rows:
        result.update((json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode())
    return result.hexdigest()


def canonical_value(value):
    if isinstance(value, dict):
        return {str(key): canonical_value(val) for key, val in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((canonical_value(val) for val in value), key=lambda val: json.dumps(val, sort_keys=True))
    if isinstance(value, (tuple, list)):
        return [canonical_value(val) for val in value]
    return value


def leaves(candidate):
    return ([candidate['leaf']] if candidate['leaf'] is not None else
            [candidate['wait_terminal']] if candidate['wait_terminal'] is not None else candidate['wait_branches'])


def best_leaf(candidate, selector):
    return min(leaves(candidate), key=lambda x: (
        ((x['predicted_unfulfilled_outbound'],) if selector == 'B2' else ()) +
        (x['predicted_turnaround_min'], x['action'])))


def select_candidate(candidates, selector):
    return min(candidates, key=lambda c: (
        ((best_leaf(c, selector)['predicted_unfulfilled_outbound'],) if selector == 'B2' else ()) +
        (best_leaf(c, selector)['predicted_turnaround_min'], c['action'])))


def interval_overlap(a, b, c, d):
    return max(0.0, min(b, d) - max(a, c))


def physical_status_at(initial, history, cutoff, max_sequence=None):
    status, kind, location = initial
    last = None
    for row in history:
        if max_sequence is not None and row[L_SEQ] > max_sequence:
            break
        if row[L_TIME] > cutoff + 1e-9:
            break
        if row[L_CLASS] == 'PHYSICAL':
            status, kind, location = row[L_TO], row[L_DEST][0], row[L_DEST][1]
            last = row[L_SEQ]
    return {'status': status, 'location_kind': kind, 'location_id': location, 'last_physical_ledger_sequence': last}


def actual_cohort(berth, actual_vessels, horizon, scenario_stop):
    cohort = [v for v in berth.vessels if v.status != 'DEPARTED']
    censored = [v.vessel_id for v in cohort if actual_vessels[v.vessel_id]['actual_departure_time_min'] is None
                or actual_vessels[v.vessel_id]['actual_departure_time_min'] > horizon]
    turnaround = sum(min(actual_vessels[v.vessel_id]['actual_departure_time_min']
                         if actual_vessels[v.vessel_id]['actual_departure_time_min'] is not None else scenario_stop,
                         horizon) - v.arrival_time_min for v in cohort)
    future_wait = sum(max(0, min(actual_vessels[v.vessel_id]['berth_start_time_min']
                                if actual_vessels[v.vessel_id]['berth_start_time_min'] is not None
                                else min(horizon, scenario_stop), horizon)
                             - max(berth.time_min, v.arrival_time_min))
                      for v in cohort if v.status in ('WAITING', 'ANNOUNCED'))
    return turnaround, future_wait, censored


def cargo_audit(record, catalog):
    """Reconcile the frozen primary metric and retain direct D17 evidence."""
    ledger = record['closure_ledger']
    history = defaultdict(list)
    for row in ledger:
        history[row[L_CONTAINER]].append(row)
    loaded = {row[L_CONTAINER]: row[L_TIME] for row in ledger if row[L_TYPE] == 'LOAD_COMPLETED'}
    departed = {row[L_CONTAINER] for row in ledger if row[L_TYPE] == 'DEPARTED_WITH_VESSEL'}
    rolled = {row[L_CONTAINER]: row for row in ledger if row[L_TYPE] == 'ROLLED_OVER'}
    obligations = [c for c in catalog.containers if c.destination_vessel_id is not None]
    metric = record['outbound_obligations']
    loaded_out = sum(c.container_id in loaded and loaded[c.container_id] <= catalog.drain_limit_min + 1e-9
                     for c in obligations)
    assert metric['N_out'] == len(obligations) == loaded_out + metric['U_not_loaded']
    assert loaded_out == metric['loaded'] and metric['reconciliation_ok']
    assert not (set(rolled) & set(loaded))
    assert len(rolled) == metric['classes']['NOT_LOADED_ROLLED_OVER']
    event_by_id = {f'KE-{e[0]:08d}': e for e in record['closure_events']}
    losses = []
    for c in obligations:
        if c.container_id in loaded and loaded[c.container_id] <= catalog.drain_limit_min + 1e-9:
            continue
        roll = rolled.get(c.container_id)
        cutoff = roll[L_TIME] if roll else min(record['T_end_min'], record['outbound_obligations']['cutoff_min'])
        initial = catalog.initial_locations[c.index]
        state = physical_status_at(initial, history[c.container_id], cutoff,
                                   max_sequence=roll[L_SEQ] if roll else None)
        tags = []
        if roll:
            tags.append('D17_ROLLOVER')
            assert roll[L_FROM] == state['status'] and state['status'] != 'IN_YARD'
            if c.cargo_flow == 'export' and state['status'] == 'EXPECTED_BY_LANDSIDE':
                tags.append('EXPORT_NOT_YET_GATED_IN_AT_D17')
            elif c.cargo_flow == 'export' and state['status'] in ('AT_GATE', 'RECEIVING'):
                tags.append('EXPORT_RECEIPT_NOT_COMPLETED_AT_D17')
            elif c.cargo_flow == 'transshipment' and state['status'] in (
                    'EXPECTED_BY_VESSEL', 'ABOARD_ARRIVED_VESSEL', 'DISCHARGING'):
                tags.append('TRANSSHIPMENT_NOT_DISCHARGED_TO_YARD_AT_D17')
            else:
                tags.append('CARGO_NOT_LOADABLE_AT_D17')
        else:
            tags.append('STOP_OR_CENSORING_BEFORE_LOAD_COMPLETION')
        source = event_by_id.get(roll[L_CAUSATION]) if roll else None
        if roll:
            assert source is not None and source[3] == 'LOAD_WAIT_TIMEOUT'
        first_ready = next((r[L_TIME] for r in history[c.container_id]
                            if r[L_TYPE] in ('DISCHARGE_COMPLETED', 'RECEIVE_COMPLETED')), None)
        if initial[0] == 'IN_YARD':
            first_ready = 0.0
        losses.append({'container_id': c.container_id, 'flow': c.cargo_flow,
                       'destination_vessel': c.destination_vessel_id, 'origin_vessel': c.origin_vessel_id,
                       'cutoff_min': cutoff, 'state_at_cutoff': state,
                       'first_recorded_yard_ready_min': first_ready,
                       'rollover_ledger_sequence': roll[L_SEQ] if roll else None,
                       'rollover_causation_event': source,
                       'd17_timer_window_start_min_rule_derived': cutoff - catalog.physics.max_load_wait_min if roll else None,
                       'd17_window_note': 'Derived from approved 240-minute rule and timeout event; no timer-start event is claimed',
                       'evidence_tags_overlapping': tags,
                       'primary_causal_reason': 'UNKNOWN_OR_MULTIPLE_CONSTRAINTS'})
    return {'metric': metric, 'losses': losses, 'evidence_tag_counts_overlapping': dict(Counter(
        tag for x in losses for tag in x['evidence_tags_overlapping'])),
        'primary_cause_counts': dict(Counter(x['primary_causal_reason'] for x in losses)),
        'rollover_by_status': dict(Counter(x['state_at_cutoff']['status'] for x in losses
                                         if 'D17_ROLLOVER' in x['evidence_tags_overlapping'])),
        'not_loaded_container_ids': [x['container_id'] for x in losses],
        'loaded_but_not_departed': sum(c.container_id in loaded and c.container_id not in departed for c in obligations),
        'unfinished_ship_moves': record['service_compliance']['unfinished_ship_moves_at_stop'],
        'loaded_at': loaded, 'obligation_ids_by_vessel': {
            v.vessel_id: [catalog.containers[i].container_id for i in v.load_container_indices]
            for v in catalog.vessels},
        'ledger_history': history}


def a2_wait_details(berth, root_scores):
    """Reporter-only authentic nominal WAIT branch reconstruction; no outer rerun."""
    from berth_allocation_lab.policies.dynamic_online_rollout import _VisibleContinuation
    class CountedContinuation(_VisibleContinuation):
        # Reporter-only counters; return values and inherited FCFS rule unchanged.
        epochs = 0
        nominal_events = 0

        def advance(self):
            active = tuple(self.active.values())
            announced = [v for vid, v in self.vessels.items() if self.status[vid] == 'ANNOUNCED']
            super().advance()
            self.epochs += 1
            self.nominal_events += sum(p.service_end_time_min == self.time for p in active)
            self.nominal_events += sum(v.arrival_time_min == self.time for v in announced)

    cont = CountedContinuation(visible_state(adapt_berth_view(berth, candidate_capacity=48)))
    cont.advance()
    advance_epochs = 1
    while True:
        choices = [(vid, x) for vid, status in cont.status.items() if status == 'WAITING'
                   for x in cont._positions(vid)]
        if choices:
            break
        cont.advance()
        advance_epochs += 1
    branches = []
    for vid, x in choices:
        branch = copy.deepcopy(cont)
        branch.assign(vid, x)
        score = branch.finish_with_fcfs()
        branches.append({'vessel_id': vid, 'position': x, 'future_wait_min': score,
                         'nominal_advance_epochs': branch.epochs, 'nominal_arrival_release_events': branch.nominal_events})
    best = min(x['future_wait_min'] for x in branches)
    assert best == root_scores[0], 'Archived A2 WAIT score did not reproduce exactly'
    return {'next_nominal_decision_min': cont.time, 'branches': branches,
            'best_branches': [b for b in branches if b['future_wait_min'] == best],
            'branch_choice_note': 'P03 returns a minimum scalar; tied branch identity is not retained by the policy',
            'advance_epochs_to_next_decision': advance_epochs, 'depth': 'WAIT -> one assignment -> FCFS',
            'prefix_nominal_arrival_release_events': cont.nominal_events,
            'predicted_turnaround': 'NOT_APPLICABLE_DIFFERENT_OBJECTIVE', 'predicted_cargo': 'NOT_PREDICTED_BY_A2'}


def observed_resources(snapshot):
    return {'cranes': snapshot['cranes'], 'vessels': snapshot['vessels'], 'blocks': snapshot['blocks'],
            'assigned_cranes': sum(c['assigned_vessel_id'] is not None for c in snapshot['cranes']),
            'working_cranes': sum(c['working'] for c in snapshot['cranes']),
            'yard_occupied_teu': sum(b['occupied_teu'] for b in snapshot['blocks']),
            'yard_reserved_teu': sum(b['reserved_teu'] for b in snapshot['blocks']),
            'max_block_occupancy_fraction': max((b['occupied_teu'] / b['capacity_teu'] for b in snapshot['blocks']), default=0)}


def analyze_run(wrapper, doc, catalog, *, derive_wait=True, reconstruction_allowed=lambda: True):
    r = wrapper['record']
    item = wrapper['item']
    cargo = cargo_audit(r, catalog)
    assert ledger_sha256(r['closure_ledger'], scenario_id=catalog.scenario_id) == r['digests']['files']['ledger.jsonl']
    assert hash_json_lines({'event_id': f'KE-{e[0]:08d}', 'time_min': e[1], 'priority': e[2],
                           'event_type': e[3], 'entity_key': e[4], 'generation': e[5]}
                          for e in r['closure_events']) == r['digests']['files']['events.jsonl']
    assert hash_json_lines({'crane_id': e[0], 'vessel_id': e[1], 'reason': e[2], 'start_min': e[3], 'end_min': e[4]}
                          for e in r['closure_blocking']) == r['digests']['files']['blocking.jsonl']
    assert len(r['closure_observations']) == len(r['closure_decisions']) == r['decisions']['berth_decisions']
    assert r['audits']['ok'] and r['per_vessel_move_reconciliation_ok'] and r['status'] == 'COMPLETED'
    departures = {e[4]: e for e in r['closure_events'] if e[3] == 'VESSEL_DEPARTED'}
    assignments = {p['vessel_id']: p for p in r['closure_decisions'] if p['action_type'] == 'ASSIGN'}
    actual_vessels = {v['vessel_id']: dict(v,
        actual_departure_time_min=departures[v['vessel_id']][1] if v['vessel_id'] in departures else None,
        berth_start_time_min=assignments[v['vessel_id']]['time_min'] if v['vessel_id'] in assignments else None)
        for v in r['vessels']}
    for vid, vessel in actual_vessels.items():
        assert vessel['departed'] == (vid in departures)
        if vessel['departed']:
            assert vid in assignments
            assert abs((departures[vid][1] - catalog.vessel_by_id[vid].arrival_time_min)
                       - vessel['observed_turnaround_min']) < 1e-7
    source_vessels = {v.vessel_id: v for v in catalog.vessels}
    decisions = []
    for i, (p, snapshot) in enumerate(zip(r['closure_decisions'], r['closure_observations'])):
        raw = base64.b64decode(snapshot['policy_observation_pickle_base64'])
        view = pickle.loads(raw)  # trusted local artifact, verified checksum/source before this function
        berth = view if item['arm'] == 'A2' else view.berth
        adapted = adapt_berth_view(berth, candidate_capacity=48)
        t = p['time_min']
        assert berth.decision_id == p['decision_id'] and berth.time_min == t
        assert all(max(0, v.arrival_time_min - berth.future_horizon_min) <= t + 1e-9 for v in berth.vessels)
        cohort = [v.vessel_id for v in berth.vessels if v.status != 'DEPARTED']
        horizon = (max(v.arrival_time_min for v in berth.vessels) + catalog.physics.max_drain_extension_min
                   if item['arm'] == 'A2' else view.projection.catalog.drain_limit_min)
        actual_end = min(r['T_end_min'], horizon)
        actual_ta, future_wait, actual_censored = actual_cohort(berth, actual_vessels, horizon, r['T_end_min'])
        full_ids = [cid for vid in cohort for cid in cargo['obligation_ids_by_vessel'][vid]]
        actual_full_u = sum(cid not in cargo['loaded_at'] or cargo['loaded_at'][cid] > horizon + 1e-9 for cid in full_ids)
        next_t = r['closure_decisions'][i + 1]['time_min'] if i + 1 < len(r['closure_decisions']) else None
        row = {'scenario_id': item['scenario_id'], 'family': item['family'], 'seed': item['seed'], 'arm': item['arm'],
               'ordinal': i + 1, 'decision_id': p['decision_id'], 'time_min': t,
               'visible_vessels': [asdict(v) for v in berth.vessels], 'cohort': cohort,
               'legal_candidates': [list(c) for c in adapted.legal_choices], 'wait_legal': berth.wait_legal,
               'selected_action': p['p03_action'], 'selected_type': p['action_type'],
               'next_actual_decision_min': next_t, 'resources': observed_resources(snapshot),
               'policy_seconds': p['policy_seconds'], 'two_second_warning': p['policy_seconds'] > 2,
               'policy_input_archive_sha256': hashlib.sha256(raw).hexdigest(),
               'actual_same_cohort_turnaround': actual_ta, 'inner_horizon_min': horizon,
               'horizon_source': ('Reporter diagnostic last-revealed arrival plus extension; A2 itself has no drain cutoff'
                                  if item['arm'] == 'A2' else 'Exact archived SafeProjection catalog drain_limit_min'),
               'actual_measurement_end_min': actual_end, 'actual_censored_vessels': actual_censored,
               'actual_full_cohort_outbound': len(full_ids), 'actual_full_cohort_unloaded': actual_full_u,
               'forecast_label': LABEL}
        row['berth_input_sha256'] = digest(asdict(berth))
        row['state_context_sha256'] = digest({'berth': asdict(berth), **{
            key: snapshot[key] for key in ('cranes', 'vessels', 'blocks', 'physics')}})
        if item['arm'] == 'A2':
            scores = {int(a): score for a, score in p['scores']}
            assert p['p03_action'] == min(scores, key=lambda a: (scores[a], a))
            row['input_comparison_sha256'] = digest(asdict(berth))
            row.update(root_future_wait_scores=p['scores'], predicted_selected_future_wait=scores[p['p03_action']],
                       root_evaluations=len(scores), leaf_rollouts=None if berth.wait_legal else len(adapted.legal_choices),
                       actual_same_cohort_future_wait=future_wait,
                       future_wait_error=scores[p['p03_action']] - future_wait,
                       turnaround_prediction_comparability='NOT_APPLICABLE_A2_FUTURE_QUEUE_OBJECTIVE')
            if berth.wait_legal and derive_wait:
                if reconstruction_allowed():
                    row['wait_inner'] = a2_wait_details(berth, scores)
                    row['leaf_rollouts'] = len(adapted.legal_choices) + len(row['wait_inner']['branches'])
                else:
                    row['wait_reconstruction_status'] = 'NOT_RUN_COMPUTE_BUDGET'
        else:
            e = p['evaluation']
            assert view.digest == e['view_digest'] and view.projection.digest == e['projection_digest']
            safe = view.projection
            safe_state = pickle.loads(safe.state_bytes)
            assert safe.catalog.identity is None and safe.catalog.scenario_id is None and safe.catalog.fingerprints is None
            assert safe_state.ledger is None and safe_state.event_log is None
            assert {v.vessel_id for v in safe.catalog.vessels} <= {v.vessel_id for v in berth.vessels}
            assert not any(event[E_TYPE] in ('GATE_IN_ARRIVAL', 'PICKUP_DUE') for event in safe_state.events)
            assert sorted(event[E_SEQ] for event in safe_state.events) == list(range(1, len(safe_state.events) + 1))
            assert safe_state.next_event_seq == len(safe_state.events) + 1
            assert e['cohort'] == cohort
            assert hashlib.sha256(json.dumps(e['candidates'], sort_keys=True).encode()).hexdigest() == e['prediction_digest']
            canonical_input = {'observable': asdict(replace(view, projection=None)),
                               'projection_schema': view.projection.schema,
                               'state_base64': base64.b64encode(view.projection.state_bytes).decode('ascii'),
                               'catalog': canonical_value(asdict(view.projection.catalog)),
                               'assumptions': view.projection.assumptions}
            row['input_comparison_sha256'] = digest(canonical_input)
            row['input_comparison_note'] = 'Canonical complete input bytes; excludes only projection creation wall time'
            row['prediction_digest'] = e['prediction_digest']
            row['candidates'] = e['candidates']
            c2, ct = select_candidate(e['candidates'], 'B2'), select_candidate(e['candidates'], 'B2-T')
            l2, lt = best_leaf(c2, 'B2'), best_leaf(ct, 'B2-T')
            selected = select_candidate(e['candidates'], item['arm'])
            chosen = best_leaf(selected, item['arm'])
            assert selected['action'] == p['p03_action']
            assert p['pivotal']['cargo_pivotal'] == (c2['action'] != ct['action'])
            known_ids = [c.container_id for c in view.projection.catalog.containers if c.destination_vessel_id in cohort]
            assert len(known_ids) == e['known_outbound_obligations']
            actual_known_u = sum(cid not in cargo['loaded_at'] or cargo['loaded_at'][cid] > horizon + 1e-9 for cid in known_ids)
            all_leaves = [leaf for c in e['candidates'] for leaf in leaves(c)]
            row.update(selected_prediction=chosen, cargo_pivotal=p['pivotal'],
                       root_evaluations=len(e['candidates']),
                       any_predicted_cargo_difference=len({x['predicted_unfulfilled_outbound'] for x in all_leaves}) > 1,
                       candidate_selected_cargo_difference=len({best_leaf(c, item['arm'])['predicted_unfulfilled_outbound']
                                                               for c in e['candidates']}) > 1,
                       actual_known_cohort_outbound=len(known_ids), actual_known_cohort_unloaded=actual_known_u,
                       cargo_denominator_matches_full_cohort=set(known_ids) == set(full_ids),
                       predicted_minus_actual_turnaround=chosen['predicted_turnaround_min'] - actual_ta,
                       predicted_minus_actual_known_unloaded=chosen['predicted_unfulfilled_outbound'] - actual_known_u,
                       evaluation_timing=e['timing'], leaf_rollouts=len(all_leaves),
                       sum_leaf_path_inner_cycles=sum(x['inner_cycles'] for x in all_leaves),
                       cycle_note='Leaf paths include the WAIT prefix in each branch; this sum is not distinct executed work',
                       inner_event_count='NOT_RECORDED_CYCLES_ARE_NOT_EVENTS')
            wait_candidate = next((c for c in e['candidates'] if c['kind'] == 'WAIT'), None)
            if wait_candidate:
                row['wait_inner'] = {'branches': wait_candidate['wait_branches'],
                                     'terminal': wait_candidate['wait_terminal'],
                                     'selected_branch': best_leaf(wait_candidate, item['arm']),
                                     'depth': 'WAIT -> one assignment -> FCFS'}
                if derive_wait and reconstruction_allowed():
                    from integrated_terminal_pilot.benchmark.coordination_policies import SharedRolloutEvaluator
                    from integrated_terminal_pilot.simulator.validator import BerthAction
                    # Reconstruct only WAIT's next projected epoch, not its candidate continuations.
                    # Enable private diagnostic logging on this fork only; no policy input changes.
                    kernel = view.projection.fork()
                    kernel.state.event_log = []
                    before = kernel.state.cycles
                    kernel.apply_berth_action(BerthAction.wait('post_run_wait_diagnostic', decision_id=view.decision_id))
                    request = SharedRolloutEvaluator('yard_occupancy_balance_v1')._advance_to_next_berth_decision(kernel)
                    row['wait_inner'].update(next_projected_epoch_min=kernel.current_time_min,
                        next_projected_epoch_kind=type(request).__name__,
                        reconstructed_advance_cycles=kernel.state.cycles - before,
                        reconstructed_advance_processed_events=len(kernel.state.event_log),
                        reconstruction_note='Reporter-only private-fork advance; candidate scores reused unchanged')
                    row['reconstructed_distinct_inner_cycles'] = row['sum_leaf_path_inner_cycles'] - max(
                        0, len(wait_candidate['wait_branches']) - 1) * (kernel.state.cycles - before)
                elif derive_wait:
                    row['wait_reconstruction_status'] = 'NOT_RUN_COMPUTE_BUDGET'
            else:
                row['reconstructed_distinct_inner_cycles'] = row['sum_leaf_path_inner_cycles']
        if p['action_type'] == 'WAIT':
            end = next_t if next_t is not None else r['outbound_obligations']['cutoff_min']
            next_snapshot = r['closure_observations'][i + 1] if next_t is not None else None
            hidden = [v.vessel_id for v in catalog.vessels
                      if max(0, v.arrival_time_min - catalog.physics.future_horizon_min) > t + 1e-9]
            row['wait_actual'] = {'elapsed_min_to_next_decision_or_stop': end - t,
                'next_is_episode_stop': next_t is None,
                'events_in_open_closed_time_window': [e for e in r['closure_events'] if t < e[1] <= end],
                'crane_blocking_overlap_minutes_by_reason': dict(Counter()),
                'future_unannounced_vessels_at_decision': hidden,
                'new_announcements_in_interval': [vid for vid in hidden if
                    max(0, source_vessels[vid].arrival_time_min - catalog.physics.future_horizon_min) <= end + 1e-9],
                'departures_in_interval': [vid for vid, v in actual_vessels.items()
                    if v['actual_departure_time_min'] is not None and t < v['actual_departure_time_min'] <= end],
                'legal_assignments_before_after': [len(berth.legal_choices),
                    len(next_snapshot['berth']['legal_choices']) if next_snapshot else None],
                'occupied_berth_length_m_before_after': [sum(v.length_m for v in berth.vessels if v.status == 'OCCUPYING'),
                    sum(v['length_m'] for v in next_snapshot['berth']['vessels'] if v['status'] == 'OCCUPYING')
                    if next_snapshot else None],
                'working_cranes_before_after': [row['resources']['working_cranes'],
                    sum(c['working'] for c in next_snapshot['cranes']) if next_snapshot else None],
                'causal_claim': 'NONE: observed time window, not a matched counterfactual WAIT effect'}
            for crane, vid, reason, a, b in r['closure_blocking']:
                overlap = interval_overlap(t, end, a, b)
                if overlap:
                    table = row['wait_actual']['crane_blocking_overlap_minutes_by_reason']
                    table[reason] = table.get(reason, 0) + overlap
        decisions.append(row)
    for loss in cargo['losses']:
        vid = loss['destination_vessel']
        berth_start = actual_vessels[vid]['berth_start_time_min']
        loss['earlier_wait_decisions_with_destination_visible'] = [d['ordinal'] for d in decisions
            if 'wait_actual' in d and vid in d['cohort'] and d['time_min'] < loss['cutoff_min']]
        loss['observed_wait_overlap_during_destination_service_min'] = sum(
            interval_overlap(d['time_min'], d['time_min'] + d['wait_actual']['elapsed_min_to_next_decision_or_stop'],
                             berth_start, loss['cutoff_min'])
            for d in decisions if 'wait_actual' in d) if berth_start is not None else None
        loss['wait_interpretation'] = 'Temporal coexistence only; no causal assignment of rollover to WAIT'
    public_cargo = {k: v for k, v in cargo.items() if k not in ('loaded_at', 'obligation_ids_by_vessel', 'ledger_history')}
    return {'item': item, 'decisions': decisions, 'cargo': public_cargo,
            'pairing': {key: r[key] for key in ('comparison_fingerprint', 'shared', 'T_end_min', 'research_profile')},
            'outcome': {'total_turnaround_min': r['kpi']['total_turnaround_min'],
                        'service_compliance': r['service_compliance'], 'container_status_at_stop': r['container_status_at_stop'],
                        'audits': r['audits']},
            'compute': {k: wrapper[k] for k in ('wall_seconds', 'cpu_seconds', 'rss_after_mb', 'two_second_exceedances')},
            'trace_sha256': r['digests']['trace_sha256'], 'ledger_digest_verified': True,
            'event_and_blocking_digests_verified': True, 'real_input_boundary_checks': 'PASS',
            'actual_vessel_timing_evidence': {vid: {'departure_event': departures.get(vid),
                'assignment_decision_id': assignments[vid]['decision_id'] if vid in assignments else None,
                'berth_start_time_min': v['berth_start_time_min'],
                'departure_time_min': v['actual_departure_time_min']} for vid, v in actual_vessels.items()},
            'event_count': len(r['closure_events']), 'ledger_records': len(r['closure_ledger'])}


def read_progress(directory):
    checkpoints, errors = [], []
    for path in sorted(directory.glob('execution_*.log')):
        raw = path.read_bytes()
        text = raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig', errors='replace')
        for line in text.splitlines():
            if line.startswith('{'):
                try:
                    row = json.loads(line)
                    if 'coverage' in row:
                        checkpoints.append(row)
                except json.JSONDecodeError:
                    pass
            if any(word in line for word in ('budget exhausted', 'RSS admission limit', 'run failed', 'Traceback')):
                errors.append(line)
    admissions = [p for p in checkpoints if any(c['status'] == 'INTERRUPTED_OR_RUNNING' for c in p['coverage'])]
    telemetry = []
    for path in directory.glob('telemetry_*.jsonl'):
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip():
                value = json.loads(line)
                telemetry.append({k: v for k, v in value.items() if k != 'line'})
    return {'last_checkpoint': checkpoints[-1] if checkpoints else None,
            'admission_checkpoint_elapsed_seconds': [p['wall_seconds_this_invocation'] for p in admissions],
            'error_lines': errors, 'sampled_telemetry': telemetry,
            'max_sampled_rss_mb': max((s['rss_mb'] for s in telemetry if s.get('rss_mb') is not None), default=None),
            'rss_note': 'Approximate 45-second process RSS samples plus episode boundaries; not peak RSS'}


def historical_context(plan):
    """Reuse existing context only; never rerun or count it toward fresh F3 coverage."""
    pre = PROJECT_ROOT / 'experiments/pre_step6_characterization/33eaf016a12d/runs/primary/itp_primary_balanced_qc8_v1'
    step = PROJECT_ROOT / 'experiments/step6_development/9babfb3068b4/runs/F1'
    rows, missing = [], []
    for scenario in plan['scenarios']:
        sid = scenario['scenario_id']
        paths = [(pre / arm / (sid + '.json'), arm) for arm in ('A1', 'A3-train11', 'A3-train23', 'A3-train37')]
        if scenario['scenario_seed'] == 10000000:
            paths += [(step / arm / (sid + '.json'), arm) for arm in ('A1n', 'B1')]
        for path, label in paths:
            if not path.exists():
                missing.append(str(path.relative_to(PROJECT_ROOT)))
                continue
            record = json.loads(path.read_text(encoding='utf-8'))
            reasons = []
            metric = record.get('outbound_obligations')
            if record['scenario']['split'] != 'development' or record['scenario']['scenario_id'] != sid:
                reasons.append('scenario identity/split')
            if record['comparison_fingerprint'] != scenario['comparison_fingerprint']:
                reasons.append('comparison fingerprint')
            if record.get('research_profile', {}).get('resolved_physics_fingerprint') != scenario['resolved_physics_fingerprint']:
                reasons.append('resolved research-profile physics')
            if record['shared'].get('quay_crane_count') != 8 or record['shared'].get('efficiency_basis') != 'assigned':
                reasons.append('QC8 or assigned efficiency')
            if record['scenario'].get('fingerprints', {}).get('exogenous_schedule_fingerprint') != scenario['exogenous_schedule_fingerprint']:
                reasons.append('exogenous fingerprint')
            if metric is None or metric['N_out'] != scenario['N_out'] or record.get('T_end_min') != scenario['T_end_min']:
                reasons.append('N_out or T_end')
            if not record.get('audits', {}).get('ok') or record['status'] != 'COMPLETED':
                reasons.append('incomplete or failed historical audit')
            expected_arm = 'A3' if label.startswith('A3-') else label
            if record['arm']['arm_id'] != expected_arm or (expected_arm == 'A3' and
                    record['arm']['ppo_training_seed'] != int(label.split('train')[1])):
                reasons.append('policy identity/training seed')
            rows.append({'scenario_id': sid, 'family': scenario['family'], 'seed': scenario['scenario_seed'],
                         'arm': label, 'status': 'REJECTED_UNPAIRED_CONTEXT' if reasons else 'VERIFIED_HISTORICAL_CONTEXT',
                         'reasons': reasons, 'file': str(path.relative_to(PROJECT_ROOT)), 'file_sha256': file_hash(path),
                         'comparison_fingerprint': record['comparison_fingerprint'],
                         'total_turnaround_min': record.get('kpi', {}).get('total_turnaround_min'),
                         'cargo': metric, 'git': record.get('git'), 'packages': record.get('packages'),
                         'source_note': 'Existing audited record; not freshly replayed, not an F3 main run'})
    aggregates = []
    for scenario in plan['scenarios']:
        selected = [r for r in rows if r['scenario_id'] == scenario['scenario_id'] and r['arm'].startswith('A3-')
                    and r['status'] == 'VERIFIED_HISTORICAL_CONTEXT']
        if {r['arm'] for r in selected} == {'A3-train11', 'A3-train23', 'A3-train37'}:
            aggregates.append({'scenario_id': scenario['scenario_id'], 'training_seeds': [11, 23, 37],
                               'mean_turnaround_min': sum(r['total_turnaround_min'] for r in selected) / 3,
                               'mean_U_containers': sum(r['cargo']['U_not_loaded'] for r in selected) / 3,
                               'mean_loss_rate': sum(r['cargo']['R_loss_rate'] for r in selected) / 3,
                               'nesting': 'Training seeds averaged within one scenario; never independent traffic samples'})
    return {'records': rows, 'a3_within_scenario_means': aggregates, 'missing': missing,
            'fresh_main_runs_reused': 0, 'historical_experiments_rerun': 0}


def replay_selected_inputs(inputs, allowed):
    """New F3 diagnostic: fixed B2-T ordinals 1/5 per case, no outer replay."""
    from integrated_terminal_pilot.benchmark.coordination_policies import SharedRolloutEvaluator, select

    class EventCounterEvaluator(SharedRolloutEvaluator):
        def __init__(self):
            super().__init__('yard_occupancy_balance_v1')
            self.path_events = []
            self.wait_prefix_events = 0

        def _continue(self, kernel):
            if kernel.state.event_log is None:
                kernel.state.event_log = []
            return super()._continue(kernel)

        def _advance_to_next_berth_decision(self, kernel):
            kernel.state.event_log = []
            result = super()._advance_to_next_berth_decision(kernel)
            self.wait_prefix_events = len(kernel.state.event_log)
            return result

        def _leaf(self, kernel, *args, **kwargs):
            result = super()._leaf(kernel, *args, **kwargs)
            self.path_events.append({'action': result.action, 'vessel_id': result.vessel_id,
                                     'position': result.position, 'processed_events': len(kernel.state.event_log),
                                     'inner_cycles': result.inner_cycles})
            return result

    results = []
    for sample in inputs:
        identity = {k: sample[k] for k in ('item', 'ordinal')}
        if not allowed():
            results.append({**identity, 'status': 'NOT_RUN_COMPUTE_BUDGET'})
            continue
        view = pickle.loads(base64.b64decode(sample['input']))
        evaluator = EventCounterEvaluator()
        t0 = time.perf_counter()
        evaluation = evaluator.evaluate(view)
        predictions = [asdict(c) for c in evaluation.candidates]
        assert json.dumps(predictions, sort_keys=True).encode() == json.dumps(
            sample['evaluation']['candidates'], sort_keys=True).encode(), 'F3 selected-input replay changed prediction bytes'
        assert evaluation.prediction_digest == sample['evaluation']['prediction_digest']
        assert evaluation.budget_fingerprint == sample['evaluation']['budget_fingerprint']
        wait = next((c for c in evaluation.candidates if c.kind == 'WAIT'), None)
        shared_repetitions = max(0, len(wait.wait_branches) - 1) if wait else 0
        results.append({**identity, 'status': 'PASS', 'wall_seconds': time.perf_counter() - t0,
            'input_archive_sha256': hashlib.sha256(base64.b64decode(sample['input'])).hexdigest(),
            'prediction_digest': evaluation.prediction_digest,
            'b2_action': select(evaluation, 'B2').action, 'b2t_action': select(evaluation, 'B2-T').action,
            'leaf_path_events': evaluator.path_events, 'wait_prefix_events': evaluator.wait_prefix_events,
            'distinct_processed_events': sum(p['processed_events'] for p in evaluator.path_events)
                                         - shared_repetitions * evaluator.wait_prefix_events,
            'method': 'Same immutable archived input; private event logging only; all candidate predictions exactly reproduced'})
    return {'predeclared_selection': 'B2-T ordinals 1 and 5 on every selected scenario, chosen by ordinal not outcome',
            'planned': 8, 'available': len(inputs), 'executed': sum(r['status'] == 'PASS' for r in results),
            'new_outer_episodes': 0, 'results': results}


def consolidate(plan, approval, runs, run_hashes, missing, failures=()):
    from integrated_terminal_pilot.benchmark.development import git_state
    all_decisions = [d for r in runs for d in r['decisions']]
    b_decisions = [d for d in all_decisions if d['arm'] != 'A2']
    by_case = defaultdict(dict)
    for r in runs:
        by_case[r['item']['scenario_id']][r['item']['arm']] = r
    comparisons, fairness = [], []
    for scenario_id, arms in by_case.items():
        for field in ('comparison_fingerprint', 'shared', 'T_end_min', 'research_profile'):
            assert len({digest(r['pairing'][field]) for r in arms.values()}) == 1, (scenario_id, field)
        assert len({r['cargo']['metric']['N_out'] for r in arms.values()}) == 1
        fairness.append({'scenario_id': scenario_id, 'present_arms': sorted(arms), 'paired': True,
                         'comparison_fingerprint': next(iter(arms.values()))['pairing']['comparison_fingerprint'],
                         'N_out': next(iter(arms.values()))['cargo']['metric']['N_out']})
        for policy, comparator in plan['comparisons']:
            if policy not in arms or comparator not in arms:
                continue
            a, b = arms[policy], arms[comparator]
            comparisons.append({'scenario_id': scenario_id, 'policy': policy, 'comparator': comparator,
                'turnaround_difference_min': a['outcome']['total_turnaround_min'] - b['outcome']['total_turnaround_min'],
                'unloaded_difference_containers': a['cargo']['metric']['U_not_loaded'] - b['cargo']['metric']['U_not_loaded'],
                'loss_rate_difference': a['cargo']['metric']['R_loss_rate'] - b['cargo']['metric']['R_loss_rate'],
                'interpretation': 'DESCRIPTIVE_DEVELOPMENT_ONLY_NO_CARGO_NI_INFERENCE'})
    matched_integrated, matched_a2, unmatched = [], [], []
    for scenario_id, arms in by_case.items():
        if 'B2' in arms and 'B2-T' in arms:
            lookup = {d['input_comparison_sha256']: d for d in arms['B2-T']['decisions']}
            for d in arms['B2']['decisions']:
                other = lookup.get(d['input_comparison_sha256'])
                if other is None:
                    unmatched.append({'scenario_id': scenario_id, 'arm': 'B2', 'ordinal': d['ordinal']})
                    continue
                assert d['prediction_digest'] == other['prediction_digest'], 'Matched input predictions differ'
                assert d['candidates'] == other['candidates'], 'Matched candidate bytes differ'
                matched_integrated.append({'scenario_id': scenario_id, 'b2_ordinal': d['ordinal'],
                    'b2t_ordinal': other['ordinal'], 'input_comparison_sha256': d['input_comparison_sha256'],
                    'prediction_digest': d['prediction_digest'], 'selected_actions': [d['selected_action'], other['selected_action']],
                    'same_raw_pickled_archive_bytes': d['policy_input_archive_sha256'] == other['policy_input_archive_sha256'],
                    'qualification': 'Complete canonical inputs identical excluding projection construction wall time; '
                                     'not a claim that raw archives with wall-time metadata are byte-identical'})
        if 'A2' in arms and 'B2-T' in arms:
            lookup = {d['state_context_sha256']: d for d in arms['A2']['decisions']}
            for d in arms['B2-T']['decisions']:
                other = lookup.get(d['state_context_sha256'])
                if other:
                    matched_a2.append({'scenario_id': scenario_id, 'a2_ordinal': other['ordinal'],
                        'b2t_ordinal': d['ordinal'], 'context_sha256': d['state_context_sha256'],
                        'a2_action': other['selected_action'], 'b2t_action': d['selected_action'],
                        'interpretation': 'Matched observed physical context; forward model/objectives still differ'})
    unique_b = {}
    for d in b_decisions:
        key = (d['scenario_id'], d['input_comparison_sha256'])
        if key in unique_b:
            assert unique_b[key]['prediction_digest'] == d['prediction_digest']
        else:
            unique_b[key] = d
    pivotal = [d for d in unique_b.values() if d['cargo_pivotal']['cargo_pivotal']]
    variation = sum(d['any_predicted_cargo_difference'] for d in unique_b.values())
    pivotal_interpretation = (
        'MODEL_LIMITATION_NO_PREDICTED_CARGO_DISCRIMINATION: all evaluated cargo predictions are tied '
        'within each candidate set, so cargo priority cannot change an action. Actual losses, if any, '
        'must not be used to tune a forecast or synthesize an objective-effect winner.' if variation == 0 else
        'PREDICTED_CARGO_VARIATION_WITHOUT_ROOT_ACTION_CHANGE: both selectors retain the same root; '
        'stored leaf/branch records distinguish ties and nonbinding variation.' if not pivotal else
        'CARGO_PRIORITY_CHANGED_ROOT_ACTIONS: report predicted cargo/turnaround tradeoffs; '
        'realized alternative trajectories are not observed counterfactuals.')
    distributions = {}
    for family in ('itp_heavy', 'itp_yard_bottleneck'):
        for arm in ('A2', 'B2-T', 'B2'):
            ds = [d for d in all_decisions if d['family'] == family and d['arm'] == arm]
            rs = [r for r in runs if r['item']['family'] == family and r['item']['arm'] == arm]
            bds = [d for d in ds if arm != 'A2']
            distributions[family + '/' + arm] = {
                'runs': len(rs), 'decisions': len(ds), 'waits': sum(d['selected_type'] == 'WAIT' for d in ds),
                'policy_seconds': stats([d['policy_seconds'] for d in ds]),
                'two_second_warnings': sum(d['two_second_warning'] for d in ds),
                'visible_non_deported_cohort': stats([len(d['cohort']) for d in ds]),
                'legal_assignments': stats([len(d['legal_candidates']) for d in ds]),
                'wait_elapsed_min': stats([d['wait_actual']['elapsed_min_to_next_decision_or_stop'] for d in ds if 'wait_actual' in d]),
                'forecast_turnaround_errors': stats([d['predicted_minus_actual_turnaround'] for d in bds]),
                'forecast_known_cargo_errors': stats([d['predicted_minus_actual_known_unloaded'] for d in bds]),
                'a2_future_wait_errors': stats([d['future_wait_error'] for d in ds if arm == 'A2']),
                'projection_build_seconds': stats([d['evaluation_timing']['projection_build_seconds'] for d in bds]),
                'evaluation_seconds': stats([d['evaluation_timing']['total_seconds'] for d in bds]),
                'root_evaluations': sum(d['root_evaluations'] for d in ds),
                'leaf_rollouts': sum(d['leaf_rollouts'] for d in ds if d.get('leaf_rollouts') is not None),
                'leaf_counts_unavailable_decisions': sum(d.get('leaf_rollouts') is None for d in ds),
                'sum_leaf_path_inner_cycles': sum(d['sum_leaf_path_inner_cycles'] for d in bds),
                'reconstructed_distinct_inner_cycles': sum(d.get('reconstructed_distinct_inner_cycles', 0) for d in bds),
                'decisions_without_distinct_cycle_reconstruction': sum('reconstructed_distinct_inner_cycles' not in d for d in bds),
                'predicted_cargo_difference_sets': sum(d['any_predicted_cargo_difference'] for d in bds),
                'cargo_pivotal': sum(d['cargo_pivotal']['cargo_pivotal'] for d in bds),
                'one_container_pivotal': sum(d['cargo_pivotal']['one_container_pivotal'] for d in bds)}
    autopsies = []
    for family in ('itp_heavy', 'itp_yard_bottleneck'):
        candidates = [d for d in all_decisions if d['family'] == family and 'wait_actual' in d]
        # Descriptive illustrations, not selection of confirmatory cases.
        for arm in ('A2', 'B2-T', 'B2'):
            subset = [d for d in candidates if d['arm'] == arm]
            if subset:
                d = max(subset, key=lambda x: abs(x.get('predicted_minus_actual_turnaround', x.get('future_wait_error', 0))))
                autopsies.append(d)
    progress = read_progress(ROOT / digest(plan)[:12])
    admiss = progress['admission_checkpoint_elapsed_seconds']
    assert all(t < approval['max_wall_minutes'] * 60 + 1 for t in admiss), 'Admission after budget limit'
    return {'label': 'STEP6_CLOSURE_F3_DEVELOPMENT_ONLY', 'forecast_label': LABEL,
        'plan_sha256': digest(plan), 'approval_sha256': digest(approval),
        'degenerate_gate_sha256': approval['degenerate_gate_sha256'], 'source_sha256': plan['source_sha256'],
        'git_head': plan['git_head'], 'ending_git_state': git_state(),
        'host': plan['host'], 'packages': plan['packages'], 'research_profile': plan['research_profile'],
        'budget_fingerprint': plan['budget_fingerprint'], 'created_utc': datetime.now(timezone.utc).isoformat(),
        'summary': {'planned': 12, 'completed': len(runs), 'missing': len(missing), 'failed': len(failures),
                    'status': 'COMPLETE' if len(runs) == 12 else 'PARTIAL',
                    'decisions': len(all_decisions), 'integrated_decisions': len(b_decisions),
                    'unique_integrated_inputs': len(unique_b), 'cargo_pivotal_unique_inputs': len(pivotal),
                    'cargo_difference_unique_inputs': sum(d['any_predicted_cargo_difference'] for d in unique_b.values()),
                    'one_container_pivotal_unique_inputs': sum(d['cargo_pivotal']['one_container_pivotal'] for d in unique_b.values()),
                    'max_pivotal_predicted_turnaround_sacrifice_min': max((
                        d['cargo_pivotal']['predicted_turnaround_sacrifice_min'] for d in pivotal), default=None),
                    'completed_episode_wall_seconds': sum(r['compute']['wall_seconds'] for r in runs),
                    'all_attempt_wall_seconds': sum(r['compute']['wall_seconds'] for r in runs)
                                                + sum(r['wall_seconds'] for r in failures),
                    'cpu_seconds': sum(r['compute']['cpu_seconds'] for r in runs),
                    'max_episode_boundary_rss_mb': max((r['compute']['rss_after_mb'] for r in runs), default=None),
                    'matched_integrated_decisions': len(matched_integrated), 'unmatched_b2_decisions': len(unmatched)},
        'run_artifacts': run_hashes, 'runs': [{k: v for k, v in r.items() if k != 'decisions'} for r in runs],
        'distributions': distributions, 'pairing_checks': fairness, 'paired_descriptive_differences': comparisons,
        'matched_integrated_states': matched_integrated, 'matched_a2_b2t_contexts': matched_a2,
        'unmatched_b2_states': unmatched, 'cargo_pivotal_examples': pivotal,
        'cargo_pivotal_interpretation': pivotal_interpretation,
        'wait_autopsies': autopsies[:5], 'missing_items': missing, 'failed_items': list(failures), 'progress_and_budget': progress,
        'approved_resources': plan['resources'], 'outer_repetition_runs': 'NOT_RUN_NO_DUPLICATE_EPISODES',
        'owner_decisions': {key: 'APPROVED' for key in plan['owner_decisions']},
        'approval_file': str(APPROVAL.relative_to(PROJECT_ROOT)),
        'approved_plan_file': str((ROOT / digest(plan)[:12] / 'plan.json').relative_to(PROJECT_ROOT)),
        'exact_owner_message': 'configs/protocol/step6_closure_approval_history/owner_message_6401_verbatim.txt',
        'historical_context': historical_context(plan),
        'regressions': {'phase_a_report': 'experiments/step6_closure/phase_a/closure_report_638ac8c0fa9f.json',
                        'repeated': False, 'reason': 'Owner forbids repeating completed Phase A/tests without demonstrated failure'},
        'limits': ['Two scenario seeds per family: no winner, S2 success, inferential ranking or primary CARGO-NI verdict.',
                   'A2 predicts future queue waiting; its numeric scores are not integrated turnaround forecasts.',
                   'Per-leaf integrated event counts are unavailable; cycles and leaves are explicitly distinct.',
                   'No causal WAIT effect is inferred from unmatched outer trajectories or overlapping time-window events.',
                   'D17 status evidence establishes availability at rollover, not a unique upstream causal explanation.',
                   'RSS is sampled at episode boundaries, not peak RSS; healthy episodes may finish after admission budget.'],
        'pending_parameter_records': 28, 'scientific_protocol_lock': 'BLOCKED', 'validation_authorized': False,
        'heldout_used': False, 'step7_started': False, 'ppo_retrained': False, 'policy_retuned': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-file', required=True, type=Path)
    parser.add_argument('--without-wait-reconstruction', action='store_true')
    args = parser.parse_args()
    args.plan_file = args.plan_file.resolve()
    started = time.perf_counter()
    plan = load_plan(args.plan_file)
    approval = require_approval(plan)
    assert json.loads(APPROVAL.with_suffix('.sha256.json').read_text(encoding='utf-8')) == {
        'canonical_sha256': digest(approval), 'file_sha256': file_hash(APPROVAL)}
    rows, run_hashes, missing, failures, replay_inputs = [], {}, [], [], []
    directory = args.plan_file.parent
    assert not (directory / 'worker.lock').exists(), 'Post-run private-model diagnostics require the outer worker to be stopped'
    progress_before = read_progress(directory)
    campaign_elapsed = (progress_before['last_checkpoint'] or {}).get('wall_seconds_this_invocation', 0)
    def reconstruction_allowed():
        return campaign_elapsed + time.perf_counter() - started < approval['max_wall_minutes'] * 60
    for item in plan['items']:
        path = item_path(directory, item)
        if not path.exists():
            missing.append(item)
            continue
        wrapper = verify_record(path, plan, item)
        assert wrapper['approval_sha256'] == digest(approval)
        if wrapper['record']['status'] != 'COMPLETED' or not wrapper['record']['audits']['ok']:
            failures.append({'item': item, 'status': wrapper['record']['status'],
                             'failure': wrapper['record'].get('failure'), 'audits': wrapper['record']['audits'],
                             'file_sha256': file_hash(path), 'wall_seconds': wrapper['wall_seconds']})
            continue
        scenario = next(s for s in plan['scenarios'] if s['scenario_id'] == item['scenario_id'])
        doc = step6._load(scenario)
        assert wrapper['source_scenario_sha256'] == scenario['file_sha256']
        _, catalog, _ = resolve_research_profile(doc, step6.PRIMARY)
        if item['arm'] == 'B2-T':
            for ordinal in (1, 5):
                if len(wrapper['record']['closure_decisions']) >= ordinal:
                    replay_inputs.append({'item': item, 'ordinal': ordinal,
                        'input': wrapper['record']['closure_observations'][ordinal - 1]['policy_observation_pickle_base64'],
                        'evaluation': wrapper['record']['closure_decisions'][ordinal - 1]['evaluation']})
        row = analyze_run(wrapper, doc, catalog, derive_wait=not args.without_wait_reconstruction,
                          reconstruction_allowed=reconstruction_allowed)
        result_path = publish(directory / 'diagnostics' / (item['scenario_id'] + '__' + item['arm'] + '__' + digest(row)[:12] + '.json'), row)
        rows.append(row)
        run_hashes[str(path.relative_to(PROJECT_ROOT))] = {'file_sha256': file_hash(path),
                                                         'diagnostic_sha256': digest(row),
                                                         'diagnostic_file': str(result_path.relative_to(PROJECT_ROOT))}
        print(json.dumps({'analyzed': item, 'decisions': len(row['decisions']), 'diagnostic': str(result_path)}), flush=True)
    report = consolidate(plan, approval, rows, run_hashes, missing, failures)
    report['new_f3_determinism_probes'] = replay_selected_inputs(replay_inputs, reconstruction_allowed)
    report['reporter_source_sha256'] = {
        str(path.relative_to(PROJECT_ROOT)): file_hash(path)
        for path in (Path(__file__), PROJECT_ROOT / 'scripts/render_step6_closure_f3.py',
                     PROJECT_ROOT / 'tests/unit/test_step6_closure_f3_report.py')}
    report['reporter_wall_seconds'] = time.perf_counter() - started
    report['wait_reconstructions_not_run_budget'] = sum(d.get('wait_reconstruction_status') == 'NOT_RUN_COMPUTE_BUDGET'
                                                       for r in rows for d in r['decisions'])
    report['diagnostic_status'] = ('PARTIAL' if report['wait_reconstructions_not_run_budget']
                                   or args.without_wait_reconstruction
                                   or report['new_f3_determinism_probes']['executed'] != 8 else 'COMPLETE')
    report['resume_state'] = {'worker_lock_present': (directory / 'worker.lock').exists(),
                            'started_without_result': [i for i in plan['items'] if
                                item_path(directory, i).with_suffix('.started.json').exists()
                                and not item_path(directory, i).exists()],
                            'completed_results_repeated': 0}
    path = publish(directory / 'reports' / ('f3_' + digest(report)[:12] + '.json'), report)
    print(json.dumps({'report': str(path), 'sha256': digest(report), 'summary': report['summary']}, indent=2))


if __name__ == '__main__':
    main()
