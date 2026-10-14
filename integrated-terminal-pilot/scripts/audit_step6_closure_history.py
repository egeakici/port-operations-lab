"""Read-only historical development diagnostics; outputs only new closure artifacts."""
import json
from pathlib import Path
import numpy as np

from integrated_terminal_pilot.benchmark import step6
from integrated_terminal_pilot.benchmark.step6_closure import ROOT, digest, file_hash, publish
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT


def quantiles(values):
    a = np.array(values)
    return {'n': len(values), 'mean': float(a.mean()), 'p50': float(np.percentile(a, 50)),
            'p95': float(np.percentile(a, 95)), 'max': float(a.max()), 'min': float(a.min())} if len(a) else {'n': 0}


def leaf(candidate, selector):
    leaves = ([candidate['leaf']] if candidate['leaf'] else
              [candidate['wait_terminal']] if candidate['wait_terminal'] else candidate['wait_branches'])
    return min(leaves, key=lambda l: ((l['predicted_unfulfilled_outbound'],) if selector == 'B2' else ()) +
                                   (l['predicted_turnaround_min'], l['action']))


def analyze():
    base = PROJECT_ROOT / 'experiments'
    history = base / 'step6_development' / '9babfb3068b4'
    files = {}
    def read(path):
        files[str(path.relative_to(PROJECT_ROOT)).replace('\\', '/')] = file_hash(path)
        return json.loads(path.read_text(encoding='utf-8'))
    profile = read(base / 'step6_development/compute_profile/20261013T210006Z/profile.json')
    timing = []
    for path in sorted((base / 'pre_step6_characterization/33eaf016a12d/runs/primary/itp_primary_balanced_qc8_v1/A2').glob('*.json')):
        r = read(path)
        assert r['scenario']['split'] == 'development' and 10_000_000 <= r['scenario']['scenario_seed'] < 11_000_000
        timing.append({'scenario': r['scenario'], 'policy_seconds': r['decisions']['seconds']['policy'],
                       'legal_assignments': r['decisions']['legal_assignments_per_epoch'],
                       'root_evaluations': r['decisions'].get('rollout_root_evaluations'),
                       'waits': r['decisions']['wait_selected'], 'packages': r['packages'], 'git': r['git']})
    rows, decisions, matches = [], [], []
    records = {}
    for path in sorted((history / 'runs').rglob('*.json')):
        if '__repeat' in path.name:
            continue
        r = read(path)
        assert r['scenario']['split'] == 'development'
        family, seed, arm = r['scenario']['family'], r['scenario']['scenario_seed'], r['arm']['arm_id']
        records[family, arm] = r
        cargo = r['outbound_obligations']
        assert cargo['N_out'] == cargo['loaded'] + cargo['U_not_loaded'] and cargo['reconciliation_ok']
        rows.append({'family': family, 'seed': seed, 'arm': arm, 'source': str(path.relative_to(PROJECT_ROOT)),
                     'cargo': cargo, 'service_compliance': r['service_compliance'],
                     'decision_summary': r['decisions'], 'D24': r['kpi']['total_turnaround_min'],
                     'handling_causes_by_vessel': [{'vessel_id': v['vessel_id'], 'rolled': v['rolled_over_containers'],
                                                   'handling_cause_min': v['handling_cause_min']} for v in r['vessels']]})
        preds = r.get('step6', {}).get('decision_predictions', [])
        if not preds:
            continue
        scenario = step6._scenario_row(family, seed)
        doc = step6._load(scenario)
        arrivals = {v['vessel_id']: v['arrival_time_min'] for v in doc['vessels']}
        actual = {v['vessel_id']: v['observed_turnaround_min'] for v in r['vessels']}
        for index, d in enumerate(preds):
            candidates = d['candidates']
            chosen = next(c for c in candidates if c['action'] == d['chosen'])
            selected = leaf(chosen, arm)
            t_inner = max(arrivals[v] for v in d['cohort']) + doc['physics']['episode']['max_drain_extension_min']
            realized = sum(min(arrivals[v] + actual[v], t_inner) - arrivals[v] for v in d['cohort'])
            b2 = min(candidates, key=lambda c: (leaf(c, 'B2')['predicted_unfulfilled_outbound'],
                                                leaf(c, 'B2')['predicted_turnaround_min'], c['action']))
            bt = min(candidates, key=lambda c: (leaf(c, 'B2-T')['predicted_turnaround_min'], c['action']))
            all_leaves = [l for c in candidates for l in ([c['leaf']] if c['leaf'] else
                          [c['wait_terminal']] if c['wait_terminal'] else c['wait_branches'])]
            decisions.append({'family': family, 'arm': arm, 'ordinal': index + 1, 'time_min': d['time_min'],
                              'cohort': d['cohort'], 'chosen': d['chosen'], 'wait': chosen['kind'] == 'WAIT',
                              'next_decision_min': preds[index+1]['time_min'] if index+1 < len(preds) else None,
                              'wait_elapsed_min': preds[index+1]['time_min']-d['time_min']
                                  if chosen['kind'] == 'WAIT' and index+1 < len(preds) else None,
                              'legal_candidates': len(candidates), 'wait_branches': len(chosen['wait_branches']),
                              'selected_leaf': selected, 'inner_horizon_min': t_inner,
                              'realized_same_cohort_turnaround': realized,
                              'signed_error': selected['predicted_turnaround_min']-realized,
                              'cargo_pivotal': b2['action'] != bt['action'],
                              'any_predicted_cargo_difference': len({l['predicted_unfulfilled_outbound'] for l in all_leaves}) > 1,
                              'future_unannounced_vessels': [v for v, a in arrivals.items() if a-240 > d['time_min']],
                              'uncertainty': 'UNCALIBRATED_SYNTHETIC_FORECAST'})
    for family in ('itp_low', 'itp_medium'):
        a, b = records[family, 'B2'], records[family, 'B2-T']
        pa, pb = a['step6']['decision_predictions'], b['step6']['decision_predictions']
        matches.append({'family': family, 'decisions': len(pa), 'same_candidate_records': pa == pb,
                        'same_prediction_digests': a['step6']['prediction_digests'] == b['step6']['prediction_digests'],
                        'qualification': 'historical prediction evidence identical; full view bytes were not archived'})
    return {'label': 'DEVELOPMENT_ONLY', 'input_sha256': files, 'compute_profile': profile,
            'historical_primary_a2_timing': timing, 'outcomes': rows, 'decisions': decisions,
            'matched_prediction_records': matches,
            'forecast_errors': {f'{f}/{a}': quantiles([d['signed_error'] for d in decisions if d['family']==f and d['arm']==a])
                                for f in ('itp_low','itp_medium') for a in ('B2','B2-T')},
            'limitations': ['Historical A2 records contain aggregate timing, not per-state cohorts or WAIT branches.',
                           'Historical B records omit resource snapshots, branch decision times and raw immutable views.',
                           'Handling-time categories overlap container causes; unique causal attribution is not established.',
                           'Historical cargo classifications are ledger-derived summaries; no new ledger replay claimed.',
                           'No matched-state causal WAIT effect can be inferred from different policy trajectories.']}


if __name__ == '__main__':
    result = analyze()
    path = publish(ROOT / 'phase_a' / ('history_' + digest(result)[:12] + '.json'), result)
    print(path)
    print(json.dumps({'forecast_errors': result['forecast_errors'],
                      'medium_waits': [d for d in result['decisions'] if d['family']=='itp_medium' and d['arm']=='B2' and d['wait']]}, indent=2))
