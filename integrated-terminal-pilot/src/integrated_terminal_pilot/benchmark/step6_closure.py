"""Append-only Step 6 closure planning and approval-guarded development controller."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
from datetime import datetime, timezone

from integrated_terminal_pilot.benchmark import step6
from integrated_terminal_pilot.benchmark.coordination_policies import budget_fingerprint, DEFAULT_INNER_CYCLE_GUARD
from integrated_terminal_pilot.benchmark.profiles import approval_state
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT

ROOT = PROJECT_ROOT / 'experiments' / 'step6_closure'
APPROVAL = PROJECT_ROOT / 'configs' / 'protocol' / 'step6_closure_owner_approval.json'
YARD = 'yard_occupancy_balance_v1'
PENDING = 'PENDING_EXPLICIT_OWNER_APPROVAL'
DECISIONS = {
    'Q6-1': 'Existing B1_ESTIMATOR v1, sequential flows, release/FCFS tie-break; unavailable cargo is not an objective',
    'Q6-2': 'Future gate-in/pickup requests NOT_SIMULATED; observed requests continue; UNCALIBRATED_SYNTHETIC_FORECAST',
    'Q6-3': 'K5-A full visible cohort, all legal plus WAIT, no cap or fallback; proposed 2-second trigger becomes warning',
    'Q6-4': 'Visible nondeparted cohort; inner last-visible-arrival plus drain extension; censored turnaround; status-based U; selector-specific WAIT branches',
}


class ClosureError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def source_hashes():
    # Source-only roots: never inspect validation/test inputs or summaries.
    roots = [PROJECT_ROOT / 'src', PROJECT_ROOT / 'configs',
             PROJECT_ROOT.parent / '03-berth-allocation-lab' / 'src']
    return {str(p.relative_to(PROJECT_ROOT.parent)).replace('\\', '/'): file_hash(p)
            for root in roots for p in sorted(root.rglob('*'))
            if p.suffix in ('.py', '.yaml') and '__pycache__' not in p.parts}


def publish(path, value):
    """Exclusive atomic installation; existing identical content is idempotent.

    Hard-link installation refuses an existing target atomically, unlike replace().
    Only the uniquely named temporary file created here is removed.
    """
    import uuid
    path = Path(path)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ClosureError(f'immutable artifact mismatch: {path}')
        return path
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(temp, 'xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ClosureError(f'concurrent immutable artifact mismatch: {path}')
    finally:
        temp.unlink(missing_ok=True)
    return path


def build_plan():
    from integrated_terminal_pilot.benchmark.development import git_state, package_versions
    from integrated_terminal_pilot.benchmark.runner import resolve_research_profile, comparison_fingerprint
    scenarios = []
    for family in ('itp_heavy', 'itp_yard_bottleneck'):
        for seed in (10_000_000, 10_000_001):
            row = step6._scenario_row(family, seed)
            doc = step6._load(row)  # verifies stored SHA before use
            physical, cat, profile = resolve_research_profile(doc, step6.PRIMARY)
            row.update(N_out=sum(c.destination_vessel_id is not None for c in cat.containers),
                       T_end_min=cat.drain_limit_min,
                       comparison_fingerprint=comparison_fingerprint(physical, cat, YARD, research_profile=step6.PRIMARY),
                       resolved_physics_fingerprint=profile['resolved_physics_fingerprint'])
            scenarios.append(row)
    return {'plan_id': 'itp_step6_closure_f3_v1', **step6.FLAGS, 'split': 'development',
            'research_profile': step6.PRIMARY, 'scenarios': scenarios,
            'items': [{'scenario_id': s['scenario_id'], 'family': s['family'], 'seed': s['scenario_seed'], 'arm': arm}
                      for s in scenarios for arm in ('A2', 'B2-T', 'B2')],
            'expected_runs': 12, 'reuse': 'none; historical A2 aggregates lack complete per-decision evidence',
            'comparisons': [['B2', 'A2'], ['B2-T', 'A2'], ['B2', 'B2-T']],
            'owner_decisions': {k: {'proposal': v, 'approval_status': PENDING} for k, v in DECISIONS.items()},
            'budget_fingerprint': budget_fingerprint(DEFAULT_INNER_CYCLE_GUARD, YARD),
            'git_head': git_state()['head'],
            'source_sha256': source_hashes(), 'packages': package_versions(),
            'host': {'platform': platform.platform(), 'python': platform.python_version(), 'logical_cpus': os.cpu_count()},
            'resources': {'workers': 1, 'proposed_admission_budget_minutes': 180, 'rss_admission_limit_mb': 4096,
                          'stop_rule': 'check before each new episode; finish healthy in-flight episode; no candidate timeout'},
            'trace_mode': 'summary', 'artifact_layout': '<plan_sha12>/runs/<family>/<seed>/<arm>.json',
            'exit_gates': ['explicit owner approval', 'reviewed degenerate gate', 'source/scenario hashes match',
                           'development 10M only', 'failure stops campaign', 'budget reviewed before next admission'],
            'scientific_protocol_lock': 'BLOCKED', 'validation_authorized': False, 'step7_started': False}


def write_plan():
    plan = build_plan()
    sha = digest(plan)
    path = ROOT / sha[:12] / 'plan.json'
    publish(path, plan)
    publish(path.with_suffix('.sha256.json'), {'canonical_sha256': sha, 'file_sha256': file_hash(path)})
    return path, sha


def load_plan(path):
    path = Path(path)
    plan = json.loads(path.read_text(encoding='utf-8'))
    hashes = json.loads(path.with_suffix('.sha256.json').read_text(encoding='utf-8'))
    if hashes != {'canonical_sha256': digest(plan), 'file_sha256': file_hash(path)}:
        raise ClosureError('plan hash mismatch')
    if plan['split'] != 'development' or plan['research_profile'] != step6.PRIMARY:
        raise ClosureError('development primary profile required')
    if len(plan['items']) != 12 or any(not 10_000_000 <= s['scenario_seed'] < 11_000_000 for s in plan['scenarios']):
        raise ClosureError('invalid development plan coverage/seed band')
    if plan['source_sha256'] != source_hashes():
        raise ClosureError('source drift: publish a new reviewed plan; historical plans remain immutable')
    # Rebuild exclusively from the fixed development index, never from supplied paths.
    # This also prevents a rehashed plan from smuggling a forbidden file behind a 10M label.
    if plan != build_plan():
        raise ClosureError('plan differs from the predeclared development campaign')
    return plan


def require_approval(plan, path=APPROVAL):
    if not Path(path).exists():
        raise ClosureError('F3_BLOCKED_BY_OWNER_REVIEW: Q6-1 through Q6-4 need explicit owner approval')
    a = json.loads(Path(path).read_text(encoding='utf-8'))
    if (a.get('plan_sha256') != digest(plan) or a.get('decisions') != DECISIONS or
        a.get('approval_status') != 'APPROVED' or not a.get('owner_response_verbatim') or
        not a.get('approval_date') or a.get('approval_source') !=
            'explicit project-owner approval in this Step 6 Closure conversation'):
        raise ClosureError('approval does not identify this exact plan and all four decisions')
    if a.get('gate_review') not in ('PASS_WITH_SCOPED_CLAIMS', 'DOCUMENTED_NOT_EXACT_ELIGIBLE'):
        raise ClosureError('degenerate gate review missing')
    gate_sha = a.get('degenerate_gate_sha256', '')
    if len(gate_sha) != 64 or any(c not in '0123456789abcdef' for c in gate_sha):
        raise ClosureError('reviewed degenerate gate digest missing')
    gate_path = ROOT / 'gates' / (gate_sha + '.json')
    if not gate_path.exists():
        raise ClosureError('reviewed degenerate gate artifact missing')
    gate = json.loads(gate_path.read_text(encoding='utf-8'))
    if digest(gate) != gate_sha or gate.get('contract_defects') != 0 or gate.get('gate') != a['gate_review']:
        raise ClosureError('reviewed degenerate gate artifact does not match approval')
    if a.get('max_wall_minutes', 0) <= 0 or a.get('workers') != 1:
        raise ClosureError('explicit bounded single-worker resource authorization required')
    state = approval_state()
    if state['proposed_pending_review'] != 28 or state['formal_step7_lock_present'] or state['validation_authorized']:
        raise ClosureError('scientific boundary changed; closure cannot proceed')
    return a


def item_path(directory, item):
    return directory / 'runs' / item['family'] / str(item['seed']) / (item['arm'] + '.json')


def verify_record(path, plan, item):
    record = json.loads(path.read_text(encoding='utf-8'))
    checksum = json.loads(path.with_suffix('.sha256.json').read_text(encoding='utf-8'))
    if checksum != {'file_sha256': file_hash(path)} or record['plan_sha256'] != digest(plan) or record['item'] != item:
        raise ClosureError('stored run checksum/plan/item mismatch')
    scenario = next(s for s in plan['scenarios'] if s['scenario_id'] == item['scenario_id'])
    r = record['record']
    if (r['comparison_fingerprint'] != scenario['comparison_fingerprint'] or
        r['outbound_obligations']['N_out'] != scenario['N_out'] or r['T_end_min'] != scenario['T_end_min'] or
        r['scenario']['scenario_id'] != item['scenario_id'] or r['arm']['arm_id'] != item['arm']):
        raise ClosureError('unpaired run metadata')
    return record


def campaign_progress(directory, plan, *, elapsed_seconds=0, recent_seconds=()):
    rows = []
    for item in plan['items']:
        path = item_path(directory, item)
        status = (verify_record(path, plan, item)['record']['status'] if path.exists()
                  else 'INTERRUPTED_OR_RUNNING' if path.with_suffix('.started.json').exists()
                  else 'BLOCKED_BY_OWNER_REVIEW' if not APPROVAL.exists() else 'NOT_RUN')
        rows.append({'item': item, 'status': status})
    done = sum(r['status'] == 'COMPLETED' for r in rows)
    failed = sum(r['status'] not in ('COMPLETED', 'NOT_RUN', 'BLOCKED_BY_OWNER_REVIEW') for r in rows)
    mean = sum(recent_seconds) / len(recent_seconds) if recent_seconds else None
    return {'plan_sha256': digest(plan), 'coverage': rows, 'planned': len(rows), 'done': done,
            'failed_or_interrupted': failed,
            'blocked': sum(r['status'] == 'BLOCKED_BY_OWNER_REVIEW' for r in rows),
            'wall_seconds_this_invocation': elapsed_seconds,
            'last_log_utc': datetime.now(timezone.utc).isoformat(),
            'recent_completed_runs': len(recent_seconds),
            'recent_runs_per_hour': 3600 / mean if mean else None,
            'estimated_remaining_seconds': mean * (len(rows) - done) if mean else None,
            'estimate_note': 'Recent completed runs only; heterogeneous arms make this uncertain; null before completion'}


def run_plan(path, *, progress=False):
    import psutil
    from integrated_terminal_pilot.benchmark.runner import run_arm
    plan = load_plan(path)
    approval = require_approval(plan)  # before reading any run input or creating output
    directory = Path(path).parent
    lock = directory / 'worker.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ClosureError('worker lock exists; inspect interruption before explicit recovery')
    os.close(fd)
    started = time.perf_counter()
    process = psutil.Process()
    recent_seconds = []
    try:
        previous_seconds = sum(verify_record(item_path(directory, i), plan, i)['wall_seconds']
                               for i in plan['items'] if item_path(directory, i).exists())
        for item in plan['items']:
            target = item_path(directory, item)
            if target.exists():
                if verify_record(target, plan, item)['record']['status'] != 'COMPLETED':
                    raise ClosureError('previous failed/incomplete run requires triage; never automatically repeated')
                continue
            if (previous_seconds + time.perf_counter() - started) / 60 >= approval['max_wall_minutes']:
                raise ClosureError('approved admission budget exhausted; request budget revision')
            if process.memory_info().rss / 1024**2 > plan['resources']['rss_admission_limit_mb']:
                raise ClosureError('RSS admission limit exceeded; do not start another episode')
            scenario = next(s for s in plan['scenarios'] if s['scenario_id'] == item['scenario_id'])
            doc = step6._load(scenario)
            attempt = target.with_suffix('.started.json')
            if attempt.exists():
                raise ClosureError('incomplete prior attempt requires operator recovery; no silent duplicate')
            publish(attempt, {'item': item, 'plan_sha256': digest(plan), 'started_utc': datetime.now(timezone.utc).isoformat()})
            if progress:
                print(json.dumps(campaign_progress(directory, plan, elapsed_seconds=time.perf_counter() - started,
                                                   recent_seconds=recent_seconds)), flush=True)
            t0 = time.perf_counter()
            cpu0 = process.cpu_times()
            result = run_arm(doc, arm_id=item['arm'], research_profile=step6.PRIMARY, keep_kernel=True,
                             capture_decision_snapshots=True)
            if 'step6' in result:
                result['step6']['budget_approval_status'] = 'APPROVED_K5_A_FULL_COHORT'
            kernel, policy = result.pop('_kernel'), result.pop('_policy')
            result['closure_decisions'] = policy.records
            # Reporter-only realized evidence. Never exposed through CoordinationView.
            result['closure_ledger'] = kernel.state.ledger
            result['closure_events'] = kernel.state.event_log
            result['closure_blocking'] = kernel.state.block_episodes
            record = {'plan_sha256': digest(plan), 'item': item, 'record': result,
                      'k5_status': 'APPROVED_K5_A_FULL_COHORT',
                      'approval_sha256': digest(approval), 'source_scenario_sha256': scenario['file_sha256'],
                      'wall_seconds': time.perf_counter() - t0, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                      'rss_after_mb': process.memory_info().rss / 1024**2,
                      'cpu_seconds': process.cpu_times().user + process.cpu_times().system - cpu0.user - cpu0.system,
                      'memory_note': 'RSS sampled at episode boundaries; not a peak measurement',
                      'two_second_exceedances': sum(r['policy_seconds'] > 2 for r in policy.records)}
            publish(target, record)
            publish(target.with_suffix('.sha256.json'), {'file_sha256': file_hash(target)})
            verify_record(target, plan, item)
            if result['status'] == 'COMPLETED':
                recent_seconds = (recent_seconds + [record['wall_seconds']])[-3:]
            if progress:
                print(json.dumps(campaign_progress(directory, plan, elapsed_seconds=time.perf_counter() - started,
                                                   recent_seconds=recent_seconds)), flush=True)
            if result['status'] != 'COMPLETED' or not result['audits']['ok']:
                raise ClosureError('run failed or incomplete; stop for triage')
    finally:
        lock.unlink(missing_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    for flag in ('audit', 'dry-run', 'plan', 'degenerate-gate', 'run', 'resume', 'report'):
        mode.add_argument('--' + flag, action='store_true')
    p.add_argument('--plan-file', type=Path)
    p.add_argument('--progress', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.run or args.resume:
            if not APPROVAL.exists():
                raise ClosureError('F3_BLOCKED_BY_OWNER_REVIEW: no explicit Q6 approval record')
            if args.plan_file is None:
                raise ClosureError('--plan-file required')
            run_plan(args.plan_file, progress=args.progress)
        elif args.plan:
            path, sha = write_plan()
            print(json.dumps({'path': str(path), 'plan_sha256': sha}))
        elif args.degenerate_gate:
            from integrated_terminal_pilot.benchmark.closure_gate import run_gate
            report = run_gate()
            path = publish(ROOT / 'gates' / (digest(report) + '.json'), report)
            print(json.dumps({'gate': report['gate'], 'report': str(path)}))
            return int(report['contract_defects'] > 0)
        elif args.audit:
            print(json.dumps(step6.audit(), indent=2))
        elif args.report:
            if args.plan_file is None:
                raise ClosureError('--plan-file required')
            plan = load_plan(args.plan_file)
            print(json.dumps(campaign_progress(args.plan_file.parent, plan), indent=2))
        else:
            plan = build_plan()
            print(json.dumps({'plan_sha256': digest(plan), 'plan': plan}, indent=2))
        return 0
    except (ClosureError, step6.Step6Error) as error:
        print(str(error), file=sys.stderr)
        return 2
