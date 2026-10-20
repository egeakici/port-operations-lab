"""Locked paired campaign. No sensitive draws or evaluations before verified authorization.

Reuses the frozen generator, arm runner, PPO gates and canonical trace streams.
Only outer episodes are scheduled; serial execution is the audited default.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import threading
import time
import uuid

from integrated_terminal_pilot.benchmark.step6_closure import ClosureError, digest, file_hash, publish
from integrated_terminal_pilot.scenarios.config import PROJECT_ROOT, load_generator_config
from integrated_terminal_pilot.benchmark.profiles import PRIMARY_RESEARCH_PROFILE, FORMAL_LOCK_PATH

REPO = PROJECT_ROOT.parent
ROOT = PROJECT_ROOT / 'experiments' / 'step7_paired_v1'
APPROVAL = PROJECT_ROOT / 'configs/protocol/step7_owner_28_approval.json'
PACKET = PROJECT_ROOT / 'configs/protocol/step7_pending_values_packet.json'
ANALYSIS = PROJECT_ROOT / 'configs/protocol/step7_analysis_contract.json'
PENDING_IDS = tuple('S2-' + x for x in ('005','007','008','010','011','012','013','014','015',
    '026','027','028','035','040','041','043','050','051','052','053','054','060','071','073',
    '074','077','078','079'))
ARMS = (('A1', None), ('A1n', None), ('B1', None), ('A2', None), ('B2', None), ('B2-T', None),
        ('A3', 11), ('A3', 23), ('A3', 37))
REFERENCE_ARMS = tuple(x for x in ARMS if x[0] in ('A1', 'A2', 'A3'))
COUNTS = {'validation': 20, 'test': 50}  # protocol 6.5, unchanged
VALID_ENDS = ('COMPLETED', 'TRUNCATED_DRAIN_LIMIT', 'DEADLOCK')
_VALIDATION_VERIFIED = set()  # per-process cache after full immutable validation verification


class CampaignError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.run(['git', *args], cwd=REPO, check=True, capture_output=True,
                          encoding='utf-8').stdout.strip()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def seal(path, value):
    publish(path, value)
    publish(Path(path).with_suffix(Path(path).suffix + '.sha256.json'),
            {'file_sha256': file_hash(path), 'canonical_sha256': digest(value)})
    return value


def unseal(path):
    value = read_json(path)
    side = read_json(Path(path).with_suffix(Path(path).suffix + '.sha256.json'))
    if side != {'file_sha256': file_hash(path), 'canonical_sha256': digest(value)}:
        raise CampaignError(f'checksum mismatch: {path}')
    return value


def value_rows(config=None):
    config = config or load_generator_config()
    rows = []
    for r in config.decisions:
        if r['decision_id'] in PENDING_IDS:
            rows.append({k: copy.deepcopy(r[k]) for k in ('decision_id', 'parameter_name',
                'parameter_paths', 'unit', 'source_kind', 'source_document', 'source_section',
                'rationale', 'impact_on_generator', 'impact_on_future_simulator')} |
                {'values_by_path': {p: copy.deepcopy(r.get('selected_values', {}).get(p, r['selected_value']))
                                    for p in r['parameter_paths']}})
    if tuple(sorted(r['decision_id'] for r in rows)) != PENDING_IDS:
        raise CampaignError('exact 28 decision IDs required')
    return rows


def require_owner(config=None):
    config = config or load_generator_config()
    packet = unseal(PACKET)
    if packet['rows'] != value_rows(config):
        raise CampaignError('owner packet values/source kind drift')
    if not APPROVAL.exists():
        raise CampaignError('LOCK_BLOCKED_OWNER_APPROVAL: 28 synthetic records still pending')
    approval = unseal(APPROVAL)
    if (approval.get('packet_sha256') != digest(packet) or
        approval.get('approved_ids') != list(PENDING_IDS) or
        approval.get('status') != 'EXPLICIT_OWNER_APPROVAL' or
        not approval.get('verbatim_message') or not approval.get('source') or not approval.get('date') or
        approval.get('scope') != 'UNCALIBRATED_SYNTHETIC_V1_MEDIUM_HEAVY_PRIMARY_LOW_BOTTLENECK_DIAGNOSTIC'):
        raise CampaignError('partial or mismatched 28-record approval provenance')
    records = {r['decision_id']: r for r in config.decisions}
    for key in PENDING_IDS:
        r = records[key]
        a = r.get('approval', {})
        if (r['status'] != 'FROZEN' or a.get('approved_by') != 'user' or
            a.get('approval_source') != f'Step 7 explicit owner message; packet {digest(packet)}' or
            a.get('approved_value') != json.dumps(next(x for x in packet['rows'] if x['decision_id'] == key)
                                                ['values_by_path'], sort_keys=True) or
            a.get('approval_date') != approval['date']):
            raise CampaignError(f'{key}: live register approval is missing or not linked')
    if any(r['status'] != 'FROZEN' for r in config.decisions):
        raise CampaignError('open decision record')
    return approval


def source_manifest():
    """Hash protected code/config/contracts, never any validation/test results."""
    paths = set()
    for directory in ('src', 'scripts', 'tests', 'configs'):
        paths.update(p for p in (PROJECT_ROOT / directory).rglob('*') if p.is_file()
                     and p.suffix in ('.py', '.ps1', '.yaml', '.json', '.toml') and '__pycache__' not in p.parts)
    for name in ('01-terminal-operations-core', '02-mini-port-simulation', '03-berth-allocation-lab'):
        for directory in ('src', 'configs', 'tests'):
            paths.update(p for p in (REPO / name / directory).rglob('*') if p.is_file()
                         and p.suffix in ('.py', '.yaml', '.json', '.toml') and '__pycache__' not in p.parts)
        paths.add(REPO/name/'pyproject.toml')
    paths.update(p for p in (PROJECT_ROOT / 'docs').glob('*.md') if not p.name.startswith('step7_'))
    paths.add(PROJECT_ROOT / 'pyproject.toml')
    if (PROJECT_ROOT/'.gitattributes').exists():paths.add(PROJECT_ROOT/'.gitattributes')
    return {p.relative_to(REPO).as_posix(): file_hash(p) for p in sorted(paths)}


def implementation_digest():
    # Regression evidence may predate owner-only status/provenance edits; all executable code and
    # test fixtures must match, plus an independent exact parameter-value fingerprint.
    return digest({p: h for p, h in source_manifest().items() if p.endswith(('.py', '.ps1', '.toml'))})


def assert_clean():
    tracked = git('status', '--porcelain', '--untracked-files=no')
    untracked = git('ls-files', '--others', '--exclude-standard', 'integrated-terminal-pilot')
    if tracked or untracked:
        raise CampaignError(f'unclean source worktree: {tracked}\n{untracked}')


def build_plan():
    from integrated_terminal_pilot.benchmark.coordination_policies import budget_fingerprint, DEFAULT_INNER_CYCLE_GUARD
    from integrated_terminal_pilot.benchmark.cargo_ni import COMPARATOR_MAP
    c = load_generator_config()
    families = sorted(n for n in c.family_names if c.family(n)['role'] == 'primary')
    if families != ['itp_heavy', 'itp_medium']:
        raise CampaignError('primary roles differ from protocol 6.5 / S2-014')
    scenarios, rows = [], []
    for split, count in COUNTS.items():
        first, last = c.seed_band(split)
        for family in families:
            for seed in range(first, first + count):
                if seed > last:
                    raise CampaignError('seed band overflow')
                sid = f'{family}_{split}_seed{seed}'
                recipe = {'family': family, 'split': split, 'scenario_seed': seed,
                          'generator': c.parameters['generator_version'], 'physics_profile': 'standard_v1',
                          'base_parameters_sha256': c.parameters_fingerprint,
                          'permission_overlay': ['development', 'validation', 'test']}
                scenarios.append({'scenario_id': sid, 'recipe': recipe, 'recipe_sha256': digest(recipe),
                    'source_scenario_sha256': 'DEFERRED_UNTIL_VERIFIED_LOCK',
                    'T_end': 'last_arrival_min + 10080.0; materialized only after lock',
                    'fingerprints': 'DEFERRED_UNTIL_VERIFIED_LOCK'})
                for world, arms in (('integrated', ARMS), ('reference', REFERENCE_ARMS)):
                    for arm, train in arms:
                        row = {'scenario_id': sid, 'family': family, 'split': split, 'scenario_seed': seed,
                               'world': world, 'arm': arm, 'ppo_training_seed': train,
                               'profile': PRIMARY_RESEARCH_PROFILE if world == 'integrated' else 'P03_NOMINAL_BERTH_PROJECTION',
                               'recipe_sha256': digest(recipe), 'preflight_status': 'ELIGIBLE_SUBJECT_TO_GATES',
                               'comparator': [r['reference'] for r in COMPARATOR_MAP if r['policy'] == arm],
                               'budget': 'FULL_VISIBLE_COHORT_ALL_LEGAL_AND_WAIT_NO_TIMEOUT' if arm in ('A2','B2','B2-T') else 'FROZEN_POLICY'}
                        row['row_id'] = f'{sid}__{world}__{arm}' + (f'-train{train}' if train else '')
                        rows.append(row)
    plan = {'version': 'itp_step7_paired_v1', 'scenarios': scenarios, 'rows': rows,
            'scenario_counts_per_family': COUNTS, 'integrated_episodes': 1260, 'reference_episodes': 700,
            'optional_diagnostic_episodes': 0, 'B3': 'NOT_IMPLEMENTED',
            'profile': PRIMARY_RESEARCH_PROFILE, 'source_sha256': source_manifest(),
            'parameter_values_sha256': c.parameters_fingerprint,
            'analysis_contract': read_json(ANALYSIS),
            'budget_fingerprint': budget_fingerprint(DEFAULT_INNER_CYCLE_GUARD, 'yard_occupancy_balance_v1'),
            'workers': 1, 'wall_time_admission_limit': None, 'candidate_timeout': None,
            'validation_then_test': 'complete validation; all valid audits; deadlock <5% per arm/family; no tuning options',
            'scenario_generation': 'exclusive after verified lock; runtime permission overlay only, stored Step2 config unchanged',
            'forecast_label': 'UNCALIBRATED_SYNTHETIC_FORECAST', 'step8_started': False}
    validate_plan(plan)
    return plan


def validate_plan(plan):
    ids = [r['row_id'] for r in plan['rows']]
    if len(ids) != len(set(ids)):
        raise CampaignError('duplicate scenario/arm/PPO identity')
    expected = set()
    for s in plan['scenarios']:
        r = s['recipe']
        if r['split'] not in COUNTS or r['family'] not in ('itp_medium', 'itp_heavy'):
            raise CampaignError('unapproved split/family')
        lo = 11_000_000 if r['split'] == 'validation' else 12_000_000
        if not lo <= r['scenario_seed'] < lo + COUNTS[r['split']] or digest(r) != s['recipe_sha256']:
            raise CampaignError('scenario recipe or band mismatch')
        for world, arms in (('integrated', ARMS), ('reference', REFERENCE_ARMS)):
            for arm, seed in arms:
                expected.add((s['scenario_id'], world, arm, seed))
    actual = {(r['scenario_id'], r['world'], r['arm'], r['ppo_training_seed']) for r in plan['rows']}
    if actual != expected or len(actual) != 1960 or len(plan['scenarios']) != 140:
        raise CampaignError('incomplete inventory')


def write_plan():
    plan = build_plan()
    path = ROOT / digest(plan)[:12] / 'plan.json'
    seal(path, plan)
    return path


def load_plan(path, *, current=True):
    plan = unseal(path)
    validate_plan(plan)
    if current and plan != build_plan():
        raise CampaignError('source/config/analysis plan drift')
    return plan


def verify_regressions(path):
    evidence = unseal(path)
    if evidence['implementation_digest'] != implementation_digest():
        raise CampaignError('regression executable source drift')
    if evidence['parameter_values_sha256'] != load_generator_config().parameters_fingerprint:
        raise CampaignError('regression parameter drift')
    for key in ('project_i_full', 'project03_eligible_fast'):
        e = evidence[key]
        if (e['exit_code'] != 0 or e['failed'] or e['errors'] or not e['passed'] or
            file_hash(PROJECT_ROOT / e['stdout']) != e['stdout_sha256'] or
            file_hash(PROJECT_ROOT / e['junit']) != e['junit_sha256']):
            raise CampaignError(f'clean mandatory regression missing: {key}')
        if e.get('skipped') or (key=='project_i_full' and e.get('deselected')):
            raise CampaignError(f'incomplete eligible regression scope: {key}; no missing-input/dependency skips allowed')
    if not evidence['project_i_full']['slow_passed'] == 9:
        raise CampaignError('all nine opt-in slow gates required')
    return evidence


def create_lock(plan_path, regression_path):
    assert_clean()
    approval = require_owner()
    plan = load_plan(plan_path)
    regressions = verify_regressions(regression_path)
    from integrated_terminal_pilot.benchmark.profiles import approval_state
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes
    if approval_state()['control_record_gaps']:
        raise CampaignError('control approval gaps')
    checkpoints = verify_all_hashes()
    if not checkpoints['ok']:
        raise CampaignError('checkpoint mismatch')
    # The evidence audit must be regenerated after administrative approval status updates.
    audit = unseal(ROOT / 'readiness_manifest.json')
    if not audit['step6_verified'] or audit['checkpoint_hashes'] != checkpoints:
        raise CampaignError('Step 6/checkpoint readiness not verified')
    lock = {'schema': 'protocol_lock_v1', 'created_utc': now(), 'source_revision': git('rev-parse','HEAD'),
            'source_sha256': source_manifest(), 'plan_path': Path(plan_path).relative_to(PROJECT_ROOT).as_posix(),
            'plan_sha256': digest(plan), 'owner_approval_sha256': digest(approval),
            'regression_evidence': str(Path(regression_path).relative_to(PROJECT_ROOT)),
            'regression_sha256': digest(regressions), 'readiness_sha256': digest(audit),
            'checkpoints': checkpoints, 'analysis': plan['analysis_contract'],
            'source_revision_rule': 'pre-lock implementation commit; later metadata commits allowed only with identical protected hashes',
            'packages': runtime()['packages']}
    if globals().get('PORTABLE_BUNDLE'):
        lock['portable_layout'] = 'step7_remote_bundle_v1'
        lock['effective_register_sha256'] = file_hash(ROOT/'inputs/approved_generator_decisions.yaml')
        lock['source_revision_rule'] = ('clean owner-committed source; generated approval overlay and exclusive '
                                        'lock live only in ignored portable bundle; no runtime Git commit')
    # Source protocol explicitly requires exclusive x mode for this lock, never a hand edit.
    with FORMAL_LOCK_PATH.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(lock, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    with FORMAL_LOCK_PATH.with_suffix('.json.sha256').open('x', encoding='utf-8') as f:
        f.write(file_hash(FORMAL_LOCK_PATH) + '  protocol_lock_v1.json\n')
    return {'lock_file_sha256': file_hash(FORMAL_LOCK_PATH), 'source_revision': lock['source_revision'],
            'status': ('WRITTEN_EXCLUSIVELY_IN_PORTABLE_BUNDLE; verify before execution' if globals().get('PORTABLE_BUNDLE')
                       else 'WRITTEN_EXCLUSIVELY; commit only lock and sidecar, then --verify before execution')}


def verify_lock(plan_path):
    # Never even open sensitive scenario/result paths until this completes.
    assert_clean()
    approval = require_owner()
    if not FORMAL_LOCK_PATH.exists():
        raise CampaignError('formal lock absent')
    lock = read_json(FORMAL_LOCK_PATH)
    side = FORMAL_LOCK_PATH.with_suffix('.json.sha256')
    if not side.exists() or side.read_text().split()[0] != file_hash(FORMAL_LOCK_PATH):
        raise CampaignError('tampered or partial protocol lock')
    if lock.get('schema') != 'protocol_lock_v1' or lock['source_sha256'] != source_manifest():
        raise CampaignError('locked scientific source drift')
    if globals().get('PORTABLE_BUNDLE') and (lock.get('portable_layout') != 'step7_remote_bundle_v1' or
        lock.get('effective_register_sha256') != file_hash(ROOT/'inputs/approved_generator_decisions.yaml')):
        raise CampaignError('portable approval register/lock mismatch')
    plan = load_plan(plan_path)
    if (lock['plan_sha256'] != digest(plan) or lock['owner_approval_sha256'] != digest(approval) or
        lock['analysis'] != plan['analysis_contract'] or
        lock['regression_sha256'] != digest(verify_regressions(PROJECT_ROOT / lock['regression_evidence']))):
        raise CampaignError('locked provenance mismatch')
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes
    if lock['checkpoints'] != verify_all_hashes() or lock['packages'] != runtime()['packages']:
        raise CampaignError('checkpoint/dependency drift')
    # HEAD may advance only with unchanged protected files; original revision must remain an ancestor.
    git('merge-base', '--is-ancestor', lock['source_revision'], 'HEAD')
    return lock


def runtime():
    from integrated_terminal_pilot.benchmark.development import package_versions
    return {'packages': package_versions(), 'python': platform.python_version(), 'platform': platform.platform(),
            'logical_cpus': os.cpu_count(), 'workers': 1, 'pid': os.getpid(), 'head': git('rev-parse','HEAD'),
            'execution_mode': 'OWNER_FOREGROUND_MANUAL', 'simulation_device': 'cpu', 'ppo_device': 'cpu'}


def require_split(plan_path, split):
    if split not in ('validation', 'test'):
        raise CampaignError('Step 7 cannot unseal diagnostic/unknown split')
    lock = verify_lock(plan_path)
    if split == 'test':
        validation_gate(plan_path)
    return lock


def scenario_path(directory, s):
    return directory / 'scenarios' / (s['scenario_id'] + '.json')


def scenario_input(plan_path, s):
    require_split(plan_path, s['recipe']['split'])
    directory = Path(plan_path).parent
    path = scenario_path(directory, s)
    if path.exists():
        envelope = unseal(path)
        if envelope['recipe_sha256'] != s['recipe_sha256']:
            raise CampaignError('stored scenario recipe mismatch')
        doc = envelope['document']
    else:
        from integrated_terminal_pilot.scenarios.generator import generate_scenario
        c = load_generator_config()
        params = c.snapshot()
        # S2-006 remains Step2-only development. This distinct lock-guarded runtime overlay
        # grants Step7 split generation without mutating any scientific parameter or stored config.
        params['generation_policy']['allowed_splits'] = ['development', 'validation', 'test']
        effective = replace(c, parameters=params)
        r = s['recipe']
        doc = generate_scenario(effective, r['family'], r['split'], r['scenario_seed'])
        seal(path, {'recipe_sha256': s['recipe_sha256'], 'document': doc})
    from integrated_terminal_pilot.scenarios.validation import validate_scenario
    quality = validate_scenario(doc)
    if not quality.ok:
        raise CampaignError(f'scenario validators failed: {quality}')
    identity, r = doc['identity'], s['recipe']
    if (identity['scenario_id'] != s['scenario_id'] or identity['scenario_family'] != r['family'] or
        identity['split'] != r['split'] or identity['scenario_seed'] != r['scenario_seed']):
        raise CampaignError('scenario identity differs from locked recipe')
    return doc


def run_path(directory, row):
    return directory / 'runs' / row['split'] / row['family'] / (row['row_id'] + '.json')


def verify_result(path, plan, row, *, full=True):
    e = unseal(path)
    if e['row'] != row or e['plan_sha256'] != digest(plan):
        raise CampaignError('result not from this exact row/plan')
    if e.get('status') not in ('COMPLETED', 'G_BLOCKED', 'FAILED'):
        raise CampaignError('unknown completion status')
    if e['status']=='G_BLOCKED' and (row['arm']!='A3' or not (e.get('gate') or e.get('result',{}).get('blocked_reasons'))):
        raise CampaignError('G block without an eligible A3 support-gate reason')
    if full:
        directory=Path(path).parents[3]
        scenario=next(x for x in plan['scenarios'] if x['scenario_id']==row['scenario_id'])
        source=scenario_path(directory,scenario)
        stored=unseal(source)
        if (file_hash(source)!=e['scenario_file_sha256'] or
            stored['recipe_sha256']!=scenario['recipe_sha256'] or
            stored['document']['fingerprints']!=e['pairing']['fingerprints'] or
            e['lock_file_sha256']!=file_hash(FORMAL_LOCK_PATH)):
            raise CampaignError('stored scenario/recipe/lock mismatch')
    if e['status'] == 'COMPLETED':
        if row['world'] == 'integrated':
            r = e['result']
            if (r['status'] not in VALID_ENDS or not r['audits']['ok'] or r['rejections'] or
                not r['per_vessel_move_reconciliation_ok']):
                raise CampaignError('invalid physical result labelled complete')
            if r['outbound_obligations']['N_out'] != e['pairing']['N_out'] or r['T_end_min'] != e['pairing']['T_end_min']:
                raise CampaignError('cargo denominator/cutoff drift')
            if not r['outbound_obligations']['reconciliation_ok']:
                raise CampaignError('outbound obligation reconciliation failed')
            if r['comparison_fingerprint']!=e['pairing']['comparison_fingerprint']:
                raise CampaignError('DQ17 physical pairing mismatch')
        if not e.get('traces') and row['world'] == 'integrated':
            raise CampaignError('required canonical ledger evidence absent')
        if row['world']=='integrated':
            from integrated_terminal_pilot.simulator.trace import CANONICAL_FILES
            from pathlib import PurePosixPath
            streams={PurePosixPath(x['path']).name.removesuffix('.gz'):x for x in e['traces']}
            if len(e['traces'])!=len(CANONICAL_FILES) or set(streams)!=set(CANONICAL_FILES):
                raise CampaignError('complete set of seven canonical streams required')
            if any(streams[n]['canonical_sha256']!=e['result']['digests']['files'][n] for n in CANONICAL_FILES):
                raise CampaignError('canonical stream digest differs from original runner')
            combined=hashlib.sha256(''.join(f'{n}:{streams[n]["canonical_sha256"]}\n' for n in CANONICAL_FILES).encode()).hexdigest()
            if combined!=e['result']['digests']['trace_sha256']:
                raise CampaignError('combined original trace digest mismatch')
    archives = list(e.get('traces', [])) + ([e['observations']] if e.get('observations') else [])
    if e['status']=='COMPLETED' and row['world']=='integrated' and not e.get('observations'):
        raise CampaignError('exact observable policy-input archive missing')
    for f in archives if full else []:
        from integrated_terminal_pilot.benchmark.step7_inputs import safe_path
        p = safe_path(Path(path).parents[3], f['path'])
        if file_hash(p) != f['gzip_sha256']:
            raise CampaignError('compressed trace corrupted')
        h = hashlib.sha256()
        with gzip.open(p, 'rb') as stream:
            for data in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(data)
        if h.hexdigest() != f['canonical_sha256']:
            raise CampaignError('canonical trace corrupted')
    return e


def index_path(path):
    return path.with_suffix('.index.json')


def install_index(path, e):
    """Small immutable progress cache; full results verified on resume and --verify/--report."""
    seal(index_path(path), {'row':e['row'],'plan_sha256':e['plan_sha256'],'status':e['status'],
                           'wall_seconds':e['wall_seconds'],'result_file_sha256':file_hash(path)})


def install_gzip(path, chunks):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    h = hashlib.sha256()
    try:
        with temp.open('xb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as z:
                for chunk in chunks:
                    b = chunk.encode('utf-8')
                    h.update(b)
                    z.write(b)
            raw.flush()
            os.fsync(raw.fileno())
        if path.exists():
            if file_hash(path) != file_hash(temp):
                raise CampaignError('immutable compressed output collision')
        else:
            os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return {'gzip_sha256': file_hash(path), 'canonical_sha256': h.hexdigest(), 'bytes': path.stat().st_size}


@contextmanager
def worker_lock(directory):
    import psutil
    path = directory / 'worker.lock'
    token = {'pid': os.getpid(), 'create_time': psutil.Process().create_time(), 'host': platform.node(), 'utc': now()}
    if path.exists():
        old = read_json(path)
        live = old.get('host') != platform.node()
        try:
            live = live or psutil.Process(old['pid']).create_time() == old['create_time']
        except psutil.NoSuchProcess:
            pass
        if live:
            raise CampaignError('live/foreign worker lock; refusing duplicate execution')
        # Archive stale ownership, never discard partial run evidence or silently retry.
        seal(directory / 'recoveries' / (digest(old) + '.json'), {'stale_lock': old})
        path.unlink()
    with path.open('x', encoding='utf-8') as f:
        json.dump(token, f)
    try:
        yield
    finally:
        if path.exists() and read_json(path) == token:
            path.unlink()


def pairing(doc):
    from integrated_terminal_pilot.benchmark.runner import resolve_research_profile, comparison_fingerprint
    physical, cat, p = resolve_research_profile(doc, PRIMARY_RESEARCH_PROFILE)
    return {'fingerprints': doc['fingerprints'], 'N_out': sum(c.destination_vessel_id is not None for c in cat.containers),
            'T_end_min': cat.drain_limit_min,
            'comparison_fingerprint': comparison_fingerprint(physical, cat, 'yard_occupancy_balance_v1', research_profile=PRIMARY_RESEARCH_PROFILE),
            'resolved_physics_fingerprint': p['resolved_physics_fingerprint']}


def execute_episode(doc, row, directory):
    """Reporter instrumentation is downstream of decisions; never changes model inputs."""
    from integrated_terminal_pilot.benchmark.runner import run_arm
    from integrated_terminal_pilot.benchmark.checkpoints import CheckpointGateError
    traces = []
    try:
        if row['world'] == 'reference':
            from berth_allocation_lab.rl.dynamic_evaluation import run_dynamic_episode, FCFS_ID, ROLLOUT_ID
            from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection
            from integrated_terminal_pilot.benchmark.checkpoints import CheckpointRef, load_checkpoint
            projection = build_berth_projection(doc)
            model = (load_checkpoint(CheckpointRef('medium_heavy', row['ppo_training_seed']), projection).model
                     if row['arm'] == 'A3' else None)
            ref = run_dynamic_episode(projection, horizon_min=240, max_vessels=24,
                method={'A1': FCFS_ID, 'A2': ROLLOUT_ID, 'A3': 'dynamic_maskable_ppo_v1'}[row['arm']], model=model)
            result = {'reference': ref}
            status = 'COMPLETED' if ref['status'] == 'completed_valid' else 'FAILED'
            ref['total_turnaround_min'] = (ref['mean_turnaround_time_min'] * ref['vessel_count']
                                           if ref.get('mean_turnaround_time_min') is not None else None)
        else:
            result = run_arm(doc, arm_id=row['arm'], training_seed=row['ppo_training_seed'],
                             research_profile=PRIMARY_RESEARCH_PROFILE, keep_kernel=True,
                             capture_decision_snapshots=True)
            if result['status'] == 'BLOCKED':
                return {'status': 'G_BLOCKED', 'result': result, 'traces': []}
            kernel, policy = result.pop('_kernel'), result.pop('_policy')
            if 'step6' in result:
                # Historical raw helper labels are retained, with current campaign provenance explicit.
                result['step7_scope'] = {'development_only': False, 'k5': 'APPROVED_FULL_COHORT',
                    'historical_step6_helper_labels_are_not_authorization': True}
            result['policy_decisions'] = policy.records
            result['scientific_scope'] = {'campaign': 'STEP7_PAIRED', 'development_only': False,
                'simulation_device': 'cpu', 'ppo_inference_device': 'cpu', 'step8_started': False}
            snapshots = result.pop('closure_observations')
            target = directory/'observations'/row['row_id']/'policy_inputs.jsonl.gz'
            archive = install_gzip(target, (json.dumps(x,sort_keys=True,allow_nan=False)+'\n' for x in snapshots))
            observation_archive = {'path':target.relative_to(directory).as_posix(), **archive}
            from integrated_terminal_pilot.simulator.trace import canonical_streams
            for name, chunks in canonical_streams(kernel, rejections=result['rejections']).items():
                target = directory / 'traces' / row['row_id'] / (name + '.gz')
                details = install_gzip(target, chunks)
                traces.append({'path': target.relative_to(directory).as_posix(), **details})
                if details['canonical_sha256'] != result['digests']['files'][name]:
                    raise CampaignError('instrumented trace differs from runner digest')
            result['complete_result'] = kernel.result()
            status = ('COMPLETED' if result['status'] in VALID_ENDS and result['audits']['ok'] and
                      not result['rejections'] and result['per_vessel_move_reconciliation_ok'] else 'FAILED')
        return {'status': status, 'result': result, 'traces': traces,
                **({'observations': observation_archive} if row['world']=='integrated' else {})}
    except CheckpointGateError as e:
        return {'status': 'G_BLOCKED', 'reason': str(e), 'gate': e.gate, 'traces': traces}


def progress(plan_path, *, authorized=False):
    plan = load_plan(plan_path, current=False)
    if not authorized:
        if not APPROVAL.exists() or not FORMAL_LOCK_PATH.exists():
            return {'status': 'LOCK_BLOCKED_OWNER_APPROVAL', 'planned': len(plan['rows']),
                    'completed': 0, 'not_run': len(plan['rows']), 'failed': 0, 'G_blocked': 0,
                    'sensitive_outputs_read': False}
        verify_lock(plan_path)
    directory = Path(plan_path).parent
    rows, durations = [], []
    for row in plan['rows']:
        path = run_path(directory, row)
        if path.exists():
            index = index_path(path)
            if index.exists():
                e = unseal(index)
                if e['row'] != row or e['plan_sha256'] != digest(plan):
                    raise CampaignError('progress index not paired with plan')
            else:
                e = verify_result(path, plan, row, full=False)
            status = e['status']
            durations.append(e['wall_seconds'])
        else:
            status = 'INTERRUPTED_REQUIRES_INSPECTION' if path.with_suffix('.started.json').exists() else 'NOT_RUN'
        rows.append({'row_id': row['row_id'], 'family': row['family'], 'split': row['split'], 'arm': row['arm'], 'status': status})
    counts = {s: sum(r['status'] == s for r in rows) for s in
              ('COMPLETED', 'G_BLOCKED', 'FAILED', 'INTERRUPTED_REQUIRES_INSPECTION', 'NOT_RUN')}
    families = {f: {s: sum(r['family'] == f and r['status'] == s for r in rows) for s in counts}
                for f in ('itp_medium', 'itp_heavy')}
    remaining = counts['NOT_RUN']
    recent = durations[-10:]
    return {'status': 'COMPLETE' if counts['COMPLETED'] + counts['G_BLOCKED'] == len(rows) else 'PARTIAL_EXPLICIT_COVERAGE',
            'plan_sha256': digest(plan), 'utc': now(), 'counts': counts, 'planned': len(rows), 'families': families,
            'rows': rows, 'recent_runs_per_hour': 3600 * len(recent) / sum(recent) if recent and sum(recent) else None,
            'observed_eta_seconds_range': [min(recent)*remaining, max(recent)*remaining] if recent else None,
            'eta_caveat': 'heterogeneous arms and congestion; observed range, not a guaranteed bound',
            'verification_scope': 'small sealed indexes for progress; full compressed evidence verified on resume/--verify/--report'}


def save_progress(plan_path):
    data = progress(plan_path, authorized=True)
    directory = Path(plan_path).parent
    seal(directory / 'progress' / (digest(data) + '.json'), data)
    temp = directory / ('progress.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.replace(temp, directory / 'campaign_progress.json')  # convenience pointer; immutable checkpoints above
    return data


def validation_gate(plan_path):
    plan = load_plan(plan_path)
    cache_key = (str(Path(plan_path).resolve()), digest(plan))
    if cache_key in _VALIDATION_VERIFIED:
        return
    directory = Path(plan_path).parent
    groups = {}
    for row in plan['rows']:
        if row['split'] != 'validation':
            continue
        path = run_path(directory, row)
        if not path.exists():
            raise CampaignError('test sealed until every validation row is accounted for')
        e = verify_result(path, plan, row)
        if e['status'] == 'FAILED':
            raise CampaignError('validation failed: scientific review required')
        if row['world'] == 'integrated' and e['status'] == 'COMPLETED':
            key = (row['family'], row['arm'], row['ppo_training_seed'])
            groups.setdefault(key, []).append(e['result']['status'] == 'DEADLOCK')
    if any(sum(g)/len(g) >= .05 for g in groups.values()):
        raise CampaignError('validation deadlock rate must be <5% per family/arm/checkpoint')
    seal(directory / 'validation_gate.json', {'status': 'PASS', 'plan_sha256': digest(plan),
                                             'no_policy_options_selected': True})
    _VALIDATION_VERIFIED.add(cache_key)


def run_campaign(plan_path, split=None, shard=0, shards=1, *, show_progress=False, stop_requested=None):
    import psutil
    from integrated_terminal_pilot.benchmark.execution import progress_bar
    verify_lock(plan_path)
    plan = load_plan(plan_path)
    directory = Path(plan_path).parent
    if shards < 1 or not 0 <= shard < shards:
        raise CampaignError('invalid resumable shard')
    process = psutil.Process()
    selected = [row for index, row in enumerate(plan['rows'])
                if (not split or row['split'] == split) and index % shards == shard]
    # These indexes provide display counts only; each stored completion is fully verified below.
    existing = 0
    for row in selected:
        path = run_path(directory, row)
        if path.exists():
            entry = unseal(index_path(path)) if index_path(path).exists() else unseal(path)
            existing += entry['status'] in ('COMPLETED', 'G_BLOCKED')
    with worker_lock(directory), progress_bar(len(selected), initial=existing,
            description='Step 7 accounted episodes', enabled=show_progress) as bar:
        for index, row in enumerate(plan['rows']):
            if (split and row['split'] != split) or index % shards != shard:
                continue
            if stop_requested is not None and stop_requested.is_set():
                break
            require_split(plan_path, row['split'])
            path = run_path(directory, row)
            if path.exists():
                if verify_result(path, plan, row)['status'] == 'FAILED':
                    raise CampaignError('failed attempt preserved; audited remediation required')
                continue
            start = path.with_suffix('.started.json')
            if start.exists():
                raise CampaignError(f'interrupted attempt needs inspection; no automatic retry: {start}')
            if psutil.virtual_memory().available < 1024**3:
                raise CampaignError('resource safety: less than 1 GiB available; no new episode admitted')
            if psutil.disk_usage(str(directory)).free < 2 * 1024**3:
                raise CampaignError('resource safety: less than 2 GiB disk free; no new episode admitted')
            s = next(s for s in plan['scenarios'] if s['scenario_id'] == row['scenario_id'])
            doc = scenario_input(plan_path, s)
            paired = pairing(doc)
            for other in (directory/'pairing').glob('*.json'):
                if other.name.endswith('.sha256.json') or other.stem==row['scenario_id']:
                    continue
                prior = unseal(other)
                if prior['fingerprints']['physical_fingerprint']==paired['fingerprints']['physical_fingerprint']:
                    raise CampaignError('duplicate physical scenario across identities/splits')
            paired_path = directory / 'pairing' / (row['scenario_id']+'.json')
            seal(paired_path, paired)  # any cross-arm DQ17/T_end/N_out/profile drift fails closed
            seal(start, {'row': row, 'utc': now(), 'host': runtime(), 'plan_sha256': digest(plan)})
            t, cpu = time.perf_counter(), time.process_time()
            samples, stop = [], threading.Event()
            heartbeat = directory / 'heartbeat.json'
            def monitor():
                while not stop.wait(15):
                    sample = {'utc': now(), 'rss_bytes': process.memory_info().rss,
                              'elapsed_seconds': time.perf_counter()-t, 'row_id': row['row_id']}
                    samples.append(sample)
                    temp = heartbeat.with_name('heartbeat.' + uuid.uuid4().hex + '.tmp')
                    temp.write_text(json.dumps(sample), encoding='utf-8')
                    os.replace(temp, heartbeat)
                    if show_progress:
                        bar.set_postfix(model='cpu', sim='CPU', arm=row['arm'],
                                        episode_seconds=int(sample['elapsed_seconds']), status='RUNNING')
            worker = threading.Thread(target=monitor, daemon=True)
            worker.start()
            try:
                result = execute_episode(doc, row, directory)
            except Exception as exc:
                result = {'status': 'FAILED', 'reason': f'{type(exc).__name__}: {exc}', 'traces': []}
            finally:
                stop.set()
                worker.join()
            e = {'row': row, 'plan_sha256': digest(plan), 'lock_file_sha256': file_hash(FORMAL_LOCK_PATH),
                 'pairing': paired, 'scenario_file_sha256': file_hash(scenario_path(directory, s)),
                 'finished_utc': now(), 'wall_seconds': time.perf_counter()-t,
                 'cpu_seconds': time.process_time()-cpu, 'rss_samples': samples,
                 'rss_after_bytes': process.memory_info().rss,
                 'memory_note': '15-second samples and boundary RSS, not continuous peak', 'runtime': runtime(), **result}
            e['two_second_compute_warnings'] = sum(d.get('policy_seconds',0)>2
                for d in e.get('result',{}).get('policy_decisions',[]))
            seal(path, e)
            verify_result(path, plan, row)
            install_index(path, e)
            save_progress(plan_path)
            if e['status'] in ('COMPLETED', 'G_BLOCKED'):
                bar.update(1)
            bar.set_postfix(model='cpu', sim='CPU', arm=row['arm'], status=e['status'])
            if e['status'] == 'FAILED':
                raise CampaignError(f'failed row preserved: {row["row_id"]}; stop affected inference')
        return save_progress(plan_path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    for name in ('preflight','plan','dry-run','lock','run','resume','status','verify','report'):
        modes.add_argument('--'+name, action='store_true')
    p.add_argument('--plan-file', type=Path)
    p.add_argument('--regression-evidence', type=Path)
    p.add_argument('--split', choices=('validation','test'))
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--shards', type=int, default=1)
    p.add_argument('--device', choices=('cpu','cuda'), default='cpu',
                   help='Step 7 is frozen to CPU; CUDA is accepted only by the separate development benchmark')
    p.add_argument('--no-progress', action='store_true')
    p.add_argument('--bundle',type=Path,help='explicit portable bundle; does not bypass any lock or split gate')
    a = p.parse_args(argv)
    if a.bundle:
        from integrated_terminal_pilot.benchmark.step7_workspace import configure
        configure(a.bundle)
    try:
        if a.device != 'cpu':
            raise CampaignError('frozen Step 7 inference is CPU; measure CUDA with benchmark_itp_devices.py; '
                                'changing scientific inference device requires separate parity review')
        if a.preflight:
            from integrated_terminal_pilot.benchmark.step7_readiness import audit
            out = audit()
        elif a.plan:
            path = write_plan()
            out = {'plan': str(path), 'canonical_sha256': digest(unseal(path)), 'sensitive_draws': 0}
        elif a.dry_run:
            plan = build_plan()
            out = {'sha256': digest(plan), 'scenarios': len(plan['scenarios']), 'episodes': len(plan['rows']),
                   'sensitive_draws': 0, 'authorization': 'NOT_GRANTED_BY_DRY_RUN'}
        else:
            if a.plan_file is None:
                raise CampaignError('--plan-file required')
            if a.lock:
                if a.regression_evidence is None:
                    raise CampaignError('--regression-evidence required')
                out = create_lock(a.plan_file, a.regression_evidence)
            elif a.run or a.resume:
                from integrated_terminal_pilot.benchmark.execution import finish_current_episode_on_interrupt
                with finish_current_episode_on_interrupt() as requested:
                    out = run_campaign(a.plan_file, a.split, a.shard, a.shards,
                                       show_progress=not a.no_progress, stop_requested=requested)
                if requested.is_set():
                    print(json.dumps({'interruption':'STOPPED_AT_SEALED_EPISODE_BOUNDARY', 'coverage':out}, indent=2))
                    return 130
            elif a.status:
                out = progress(a.plan_file)
            elif a.report:
                verify_lock(a.plan_file)
                from integrated_terminal_pilot.benchmark.step7_report import report
                out = report(a.plan_file)
            else:
                lock = verify_lock(a.plan_file)
                plan = load_plan(a.plan_file)
                for row in plan['rows']:
                    path = run_path(a.plan_file.parent,row)
                    if path.exists():
                        verify_result(path,plan,row)
                out = {'lock_file_sha256': file_hash(FORMAL_LOCK_PATH), 'coverage': progress(a.plan_file, authorized=True)}
        print(json.dumps(out, indent=2, allow_nan=False))
        return 0
    except (CampaignError, ClosureError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(exc)}))
        return 2
