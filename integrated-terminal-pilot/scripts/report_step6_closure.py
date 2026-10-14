"""Publish a new immutable Phase A evidence summary; never authorize execution."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

from integrated_terminal_pilot.benchmark.step6_closure import (
    ROOT, APPROVAL, DECISIONS, PENDING, campaign_progress, digest, file_hash,
    load_plan, publish, source_hashes,
)
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT


def read_text(path):
    raw = Path(path).read_bytes()
    return raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')


def summarize_log(path):
    text = read_text(path)
    counts = {k: int(v) for v, k in re.findall(r'(\d+) (passed|failed|error|errors|skipped|deselected)', text)}
    return {'path': str(path.relative_to(PROJECT_ROOT)).replace('\\', '/'),
            'sha256': file_hash(path), 'counts': counts,
            'status': 'FAIL_OR_ENVIRONMENT_ERROR' if counts.get('failed') or counts.get('errors') or counts.get('error')
                      else 'PASS' if counts.get('passed') else 'NO_COMPLETION_SUMMARY',
            'summary_tail': text.splitlines()[-4:]}


def reconstruct_full_progress(phase):
    """Retain progress evidence when pytest's temp-dir teardown loses its summary."""
    log = phase / 'project_i_tests.log'
    collection = phase / 'collected_tests.log'
    slow_collection = phase / 'collected_slow_tests.log'
    statuses = ''.join(m.group(1) for line in read_text(log).splitlines()
                       if (m := re.fullmatch(r'([.EFs]+)(?:\s+\[\s*\d+%\])?', line.strip())))
    # This long run collected before the additive closure test module existed.
    # No pre-existing test was edited. Remove only that new module from the
    # separately archived collection order; insist on exact count alignment.
    nodes = [line for line in read_text(collection).splitlines()
             if line.startswith('tests/') and 'tests/unit/test_step6_closure.py' not in line]
    assert len(nodes) == len(statuses) == 462
    observed = dict(zip(nodes, statuses))
    slow = [line for line in read_text(slow_collection).splitlines() if line.startswith('tests/')]
    assert len(slow) == 9 and all(observed[node] == '.' for node in slow)
    errors = [node for node in nodes if observed[node] == 'E']
    retry = summarize_log(phase / 'project_i_fast_final.log')
    assert retry['counts'].get('passed') == 472 and not any(node in slow for node in errors)
    stat = log.stat()
    return {'label': 'RECONSTRUCTED_PROGRESS_NOT_A_NORMAL_PYTEST_SUMMARY',
            'log_sha256': file_hash(log), 'collection_sha256': file_hash(collection),
            'slow_collection_sha256': file_hash(slow_collection),
            'collected_original_tests': len(nodes), 'passed_indicators': statuses.count('.'),
            'error_indicators': statuses.count('E'), 'failed_indicators': statuses.count('F'),
            'skipped_indicators': statuses.count('s'), 'error_nodes': errors,
            'slow_tests': {node: 'PASS' for node in slow},
            'step4_cases': 80, 'step5_cases': 400,
            'scope_counts_current_run': 'NOT_RETAINED_BY_EXISTING_PYTEST_WRAPPER',
            'environment_evidence': 'WinError 5 on pytest basetemp during sessionfinish; no normal summary',
            'individual_error_tracebacks': 'NOT_EMITTED_AFTER_SESSIONFINISH_ABORT',
            'all_error_nodes_covered_by_clean_non_slow_retry': True,
            'retry': retry,
            'approximate_command_seconds_from_log_file_lifetime': stat.st_mtime - stat.st_birthtime,
            'count_method': 'Original collection order reconstructed by excluding only the new closure module; '
                            '462 progress symbols map exactly to 462 unchanged original tests. '
                            'All 9 selected slow nodes have pass symbols; no repeated gate execution.'}


def report(plan_path):
    plan = load_plan(plan_path)
    phase = ROOT / 'phase_a'
    gate_path = ROOT / 'gates' / '7cb84b87c78f3b2a6628a59ce4a2013b90ba8d66c347230eab24d6095f18c5c2.json'
    gate = json.loads(read_text(gate_path))
    assert digest(gate) == gate_path.stem
    history_path = phase / 'history_981f78c74152.json'
    history = json.loads(read_text(history_path))
    preserved = {p: file_hash(PROJECT_ROOT / p) == sha for p, sha in history['input_sha256'].items()}
    assert all(preserved.values()), 'historical input drift'
    historical_gates = {}
    for name, rel in (
        ('step4', 'step4_equivalence/eq_20261013T213721Z/report.json'),
        ('step5', 'step5_development/exact_gate_20261013T224141Z/report.json'),
    ):
        path = PROJECT_ROOT / 'experiments' / rel
        old = json.loads(read_text(path))
        entry = {'path': str(path.relative_to(PROJECT_ROOT)), 'sha256': file_hash(path), 'summary': old['summary']}
        if name == 'step5':
            from collections import Counter
            entry['scope_counts'] = dict(Counter(r['scope'] for r in old['rows']))
        historical_gates[name] = entry
    repo = PROJECT_ROOT.parent
    unchanged = {}
    for rel in ('03-berth-allocation-lab/src/berth_allocation_lab/dynamic_online_rollout.py',
                'integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/coordination_policies.py',
                'integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/coordination_view.py'):
        # Resolve the authentic module by tracked filename if its package has a different name.
        candidates = subprocess.check_output(['git', 'ls-files', '*' + Path(rel).name], cwd=repo, text=True).splitlines()
        actual = next(p for p in candidates if p.startswith(rel.split('/')[0] + '/'))
        import hashlib
        original = hashlib.sha256(subprocess.check_output(['git', 'show', 'HEAD:' + actual], cwd=repo)).hexdigest()
        raw = (repo / actual).read_bytes()
        current = file_hash(repo / actual)
        normalized = hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()
        unchanged[actual] = {'HEAD_sha256': original, 'current_file_sha256': current,
                             'current_LF_sha256': normalized, 'unchanged': original == normalized,
                             'comparison_note': 'Git blob versus checkout with CRLF normalized to LF'}
    assert all(r['unchanged'] for r in unchanged.values())
    logs = {}
    for name in ('project_i_tests', 'project_i_fast_final', 'closure_readiness_tests', 'closure_archive_tests',
                 'closure_persistence_tests',
                 'project01_retry', 'project02_retry', 'project03_tests'):
        logs[name] = summarize_log(phase / (name + '.log'))
    progress = reconstruct_full_progress(phase)
    progress_path = publish(phase / ('full_progress_' + digest(progress)[:12] + '.json'), progress)
    return {
        'label': 'STEP6_CLOSURE_PHASE_A_DEVELOPMENT_ONLY',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'starting_head': '76ced62b94e5419fea98933b3cb17debf1bd8a62',
        'ending_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
        'worktree': subprocess.check_output(['git', 'status', '--short'], cwd=repo, text=True).splitlines(),
        'automatic_commit': False,
        'specification': {'path': 'Project_I_Step_6_Closure_Contract_Gate_and_F3_Codex_Prompt.md',
                          'sha256': file_hash(repo / 'Project_I_Step_6_Closure_Contract_Gate_and_F3_Codex_Prompt.md'),
                          'owner_confirmed_single_complete_prompt': True},
        'owner_decisions': {k: {'proposal': v, 'status': PENDING} for k, v in DECISIONS.items()},
        'real_owner_approval_file_present': APPROVAL.exists(),
        'gate': {k: v for k, v in gate.items() if k != 'fixtures'},
        'gate_artifact': {'path': str(gate_path.relative_to(PROJECT_ROOT)), 'canonical_sha256': digest(gate),
                          'file_sha256': file_hash(gate_path)},
        'f3': campaign_progress(plan_path.parent, plan),
        'f3_authorized': 0, 'f3_executed': 0, 'f3_failed': 0, 'f3_reused': 0,
        'f3_wall_seconds': 0, 'plan_file_sha256': file_hash(plan_path),
        'source_sha256': source_hashes(), 'unchanged_reference_sources': unchanged,
        'historical_inputs_verified': preserved, 'historical_input_sha256': history['input_sha256'],
        'historical_gate_reports': historical_gates,
        'history_artifact': {'path': str(history_path.relative_to(PROJECT_ROOT)), 'sha256': file_hash(history_path)},
        'audit': json.loads(read_text(phase / 'audit.json')), 'test_logs': logs,
        'full_suite_progress_evidence': progress,
        'full_suite_progress_artifact': str(progress_path.relative_to(PROJECT_ROOT)),
        'phase_a_complete': True,
        'overall_closure_status': 'PARTIAL_F3_BLOCKED_BY_OWNER_REVIEW',
        'project03_exclusions': ['dynamic/static PPO integration training tests',
                                 'historical results release/results tests',
                                 'scientific benchmark and benchmark diagnostics integration tests',
                                 'slow marker (5 deselected)'],
        'diagnostics': {'historical_b2_decisions': 29, 'predicted_cargo_difference_sets': 0,
                        'cargo_pivotal': 0, 'medium_waits': 4,
                        'forecast_label': 'UNCALIBRATED_SYNTHETIC_FORECAST',
                        'heavy_bottleneck_f3_diagnostics': 'NOT_RUN_OWNER_APPROVAL_REQUIRED'},
        'blockers': ['Q6-1 through Q6-4 and bounded F3 resources need explicit owner approval',
                     '12 Heavy/Bottleneck F3 episodes and their decision/ledger diagnostics remain blocked',
                     'Historical A2 slowest state was not archived; runtime cause is not uniquely identified',
                     'Historical WAIT trajectories do not establish a causal performance decomposition',
                     'Unique cargo-loss causes lack sufficient event evidence',
                     'Degenerate equivalence is conditional; general model/horizon differences remain',
                     '28 parameter decisions pending; formal Step 7 lock absent'],
        'validation_authorized': False, 'heldout_used': False, 'step7_started': False,
        'ppo_retrained': False, 'protocol_lock': 'BLOCKED',
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-file', type=Path, required=True)
    args = parser.parse_args()
    result = report(args.plan_file)
    path = publish(ROOT / 'phase_a' / ('closure_report_' + digest(result)[:12] + '.json'), result)
    print(path)
